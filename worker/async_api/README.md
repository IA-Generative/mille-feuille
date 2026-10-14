# worker/async_api : mille-feuille pour AsyncTaskAPI

Worker **séparé, sans Celery**, qui rend mille-feuille consommable par
[AsyncTaskAPI](https://github.com/IA-Generative/async-api). Il est écrit avec la bibliothèque
[`mic-worker`](https://github.com/IA-Generative/async-api/tree/main/workers/python/mic-worker) : il consomme
une file RabbitMQ, exécute la tâche et publie sa progression puis son résultat sur la file de sortie.

Il **ne réimplémente pas le pipeline** : chaque tâche passe par l'API éphémère de mille-feuille
(`/api/ephemeral/*`, voir [docs/ephemeral-api.md](../../docs/ephemeral-api.md)) grâce au SDK
[`millefeuille-ephemeral`](../../sdks/python/millefeuille-ephemeral/README.md). Les workers Celery
(`document_process`, `agent_execution`, `classification`, `extraction`) et le backend ne sont pas modifiés.

## Déroulement d'une tâche

1. Validation du message et des limites (nombre et taille des fichiers, `HEAD` S3 **avant** tout téléchargement).
2. Téléchargement des fichiers depuis le stockage d'AsyncTaskAPI.
3. Création de l'analyse éphémère (si `analysis` est fourni) puis lancement du run.
4. Attente de la fin du run ; progression = étapes d'exécution terminées / total, entre 0.25 et 0.95.
5. Message `success` avec le résultat complet du run, puis suppression du résultat conservé côté mille-feuille
   (sauf `persist: true`).

En cas d'échec, de délai dépassé ou d'arrêt du worker, le run et l'analyse créés par la tâche sont arrêtés et supprimés.

## Format des messages

Le schéma d'entrée fait foi dans [`contrat.json`](contrat.json) (manifeste `mic-worker`, validé au démarrage et par les tests).

Entrée (`data.body`), `analysis` **ou** `analyse_id` :

```json
{
  "analysis": {
    "name": "Vérification CNI",
    "classification_prompt": "Classe le document",
    "multi_label": false,
    "labels": [{ "name": "CNI", "definition": "Carte nationale d'identité" }],
    "extraction_prompt": "Extrait nom et prénom",
    "entities": [{ "name": "nom", "type": "texte" }],
    "agents": [{ "name": "vérif", "prompt": "Vérifie la cohérence des données" }]
  },
  "files": [{ "file_id": "astree/a1b2c3d4/cni.pdf", "name": "cni.pdf" }],
  "ttl_hours": 24,
  "persist": false
}
```

Sortie : messages `started`, `progress` (`0.0` à `1.0`), puis `success` dont `response` est le run
(`status`, `execution_steps` avec les sorties des agents, `documents` avec pages et prédictions, `expires_at`...),
ou `failure` avec un `error_message` lisible (message invalide, fichier trop gros, run en échec, délai dépassé, erreur de l'API).

## Configuration

Variables d'environnement (voir [`.env.example`](.env.example)) :

| Variable | Défaut | Rôle |
|---|---|---|
| `BROKER_URL` | (obligatoire) | RabbitMQ |
| `IN_QUEUE_NAME` / `OUT_QUEUE_NAME` | `mille_feuille_queue_in` / `_out` | files du service |
| `WORKER_CONCURRENCY` | `2` | tâches simultanées |
| `SERVICE_CLASS` | (aucune) | classe de service d'async-api ; `long` pour émettre la progression |
| `AWS_*` | (obligatoires) | stockage objet d'AsyncTaskAPI (fichiers déposés avant la tâche) |
| `MILLEFEUILLE_BASE_URL` | (obligatoire) | backend mille-feuille |
| `MILLEFEUILLE_API_TOKEN` | (obligatoire) | token API (`X-App-Token`), créé via `POST /api/app-tokens` |
| `MAX_FILE_SIZE_BYTES` / `MAX_TOTAL_SIZE_BYTES` / `MAX_FILES` | 50 Mo / 100 Mo / 20 | bornes mémoire |
| `RUN_TIMEOUT_SECONDS` / `POLL_INTERVAL_SECONDS` | `900` / `3` | attente du run |
| `DELETE_RUN_AFTER_RESULT` | `true` | supprime le résultat conservé une fois renvoyé |

Health check HTTP sur le port `8084` (`/health`, `/ready` qui éprouve le stockage objet).

**Mémoire et redélivrance** (contrat de service d'async-api) : les fichiers sont chargés en mémoire, d'où les
bornes de taille vérifiées par `HEAD`. Le pic vaut `WORKER_CONCURRENCY × taille des fichiers` : à régler sur une
mesure réelle. Une redélivrance du message recrée un run (pas de clé d'idempotence côté backend) ; le doublon est
purgé au TTL.

## Secrets

Trois endroits, selon l'usage. Le détail (Vault, création des jetons, rotation) est dans [docs/secrets.md](../../docs/secrets.md).

| Où | Secret | Contenu |
|---|---|---|
| Kubernetes (Vault, via le chart) | `millefeuille-async-api-worker` | `BROKER_URL`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `MILLEFEUILLE_API_TOKEN` (identifiants uniquement) |
| GitHub Actions | `ASYNC_API_TOKEN` | Jeton en lecture sur le dépôt privé `async-api` (installation de `mic-worker` : lint, tests, build d'image) |
| Local / docker compose | `.env` | `ASYNC_API_WORKER_TOKEN` (token API mille-feuille), `GH_TOKEN` (build), `RABBITMQ_USER` / `RABBITMQ_PASSWORD` (facultatifs, valeurs de dev par défaut) |

Le `MILLEFEUILLE_API_TOKEN` se crée avec `POST /api/app-tokens` (session ou jeton Keycloak) et n'est affiché qu'une fois.
Les autres réglages (files, endpoint et bucket S3, `SERVICE_CLASS`, `WORKER_CONCURRENCY`, limites, délais...) ne sont pas des secrets : ils sont dans `env` de `common-values.yaml`, avec leur valeur par défaut.

## Développement

Python 3.13 (exigé par `mic-worker`). `mic-worker` est dans un dépôt **privé** : `uv sync` a besoin d'un accès Git
à `IA-Generative/async-api` (par exemple `gh auth login`).

```bash
cd worker/async_api
uv sync --group dev
uv run ruff check . && uv run ruff format --check .
uv run pytest
```

## Image Docker et docker compose

Le contexte de build est la **racine du dépôt** (l'image embarque les SDK). Le secret BuildKit `github_token`
(lecture sur `async-api`) n'est jamais écrit dans une couche.

```bash
export GH_TOKEN=$(gh auth token)
docker build -f worker/async_api/Dockerfile --secret id=github_token,env=GH_TOKEN -t mille-feuille-async-api-worker .

# ou, avec RabbitMQ local (profil `async-api`, hors `docker compose up` par défaut) :
ASYNC_API_WORKER_TOKEN=<token API> docker compose --profile async-api up --build worker-async-api
```

## Déploiement Helm

Le chart [`millefeuille`](../../millefeuille/README.md) porte le composant `worker_async_api` (Deployment, sans Service :
le worker ne reçoit aucun trafic). Il est **désactivé par défaut** : il faut un RabbitMQ et le stockage objet
d'AsyncTaskAPI, que le chart ne fournit pas.

```bash
helm template millefeuille ./millefeuille -f millefeuille/values/common-values.yaml --set worker_async_api.enabled=true
```

Les identifiants (`BROKER_URL`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `MILLEFEUILLE_API_TOKEN`) viennent du secret
`millefeuille-async-api-worker` (Vault) ; tout le reste est dans `env`, avec des valeurs par défaut (`common-values.yaml`). Sondes : `/health`
(vivacité) et `/ready` (stockage objet), sur le port `8084`. Pas de mise à l'échelle KEDA : le worker consomme
RabbitMQ, pas les files Celery ; régler `WORKER_CONCURRENCY` et `replicaCount` selon la mémoire.

L'image `worker-async-api` doit être publiée avant d'activer le composant (voir ci-dessous).

## CI

`lint.yml`, `unit-tests.yml` et le build d'image de `ci.yml` ont besoin du secret de dépôt **`ASYNC_API_TOKEN`** :
un jeton fine-grained en lecture (*Contents: read*) sur `IA-Generative/async-api`. Sans lui, ces jobs sont ignorés
avec un avertissement (le reste de la CI n'est pas affecté).

**Publication de l'image à la release** : `cd.yml` ne construit pas encore l'image `worker-async-api` (son build a
besoin du secret `ASYNC_API_TOKEN`, et un build en échec bloquerait `bump-chart` et `release-chart`). Tant que ce n'est
pas fait, le composant Helm reste désactivé, ou pointe vers une image construite à la main.
