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
.

En cas d'échec, de délai dépassé ou d'arrêt du worker, le run et l'analyse créés par la tâche sont arrêtés et supprimés.

## Format des messages

Le schéma d'entrée fait foi dans [`contrat.json`](contrat.json) (manifeste `mic-worker`, validé au démarrage et par les tests).

Entrée (`data.body`), `analysis` **ou** `analyse_id` (1 à 20 fichiers) :

```json
{
  "analysis": {
    "name": "Vérification CNI",
    "classification_prompt": "Classe le document",
    "multi_label": false,
    "labels": [{ "name": "CNI", "definition": "Carte nationale d'identité" }],
    "extraction_prompt": "Extrait nom et prénom",
    "entities": [{ "name": "nom", "type": "texte" }],
    "agents": [{ "name": "vérif", "prompt": "Vérifie la cohérence des données", "tools": ["lecture_document"] }]
  },
  "files": [{ "file_id": "astree/a1b2c3d4/cni.pdf", "name": "cni.pdf" }],
  "ttl_hours": 24
}
```

Ce que la plateforme n'ouvre pas, à dessein : `persist` (un run de plateforme n'est jamais conservé — le
résultat est rendu dans la réponse et le run supprimé), les outils d'agent qui sortent du dossier
(`recherche_web`, `base_connaissances`, `appel_agent` : seuls `lecture_document`, `calculatrice` et
`verification_coherence` sont acceptés) et un `ttl_hours` au-delà de 168 h. Le manifeste déclare aussi
`taille_max_fichier_mio: 50` (= `MAX_FILE_SIZE_BYTES`) : async-api refuse en `413` à la soumission ce que le
worker refuserait après coup, et `files.maxItems: 20` (= `MAX_FILES`), refusé en `422`.

Sortie : messages `started`, `progress` (`0.0` à `1.0`), puis `success` dont `response` est un **résumé borné**
du run (256 Kio au plus) :

```json
{
  "status": "terminé",
  "run_id": "3f2b8c1e-…",
  "resultat_file_id": "astree/<task_id>/resultat.json",
  "resultat_octets": 184320,
  "documents": [
    {
      "name": "cni.pdf",
      "page_count": 2,
      "pages": [{ "page_number": 1, "labels": [{ "name": "CNI", "confidence": 0.96, "source": "textual" }] }],
      "entities": [{ "name": "nom", "value": "Dupont", "confidence": 0.9, "source": "textual", "pages": [1] }]
    }
  ],
  "agents": [{ "label": "vérif", "status": "terminé", "output": "…", "tronque": false }],
  "durees": { "created_at": "…", "started_at": "…", "ended_at": "…" },
  "tronque": false
}
```

Le run **complet** (texte de chaque page, boîtes, journaux d'étapes — 20 à 50 Kio par page) est déposé sur le
stockage d'async-api à `{client_id}/{task_id}/resultat.json` (`resultat_file_id`, clé déterministe : une
redélivrance réécrit la même), sous le préfixe du client qui a soumis les fichiers — lui seul peut le lire, et
le soumettre à son tour à un autre service. Si le résumé dépasse la borne, les entités puis les pages en sont
retirées par moitiés et `tronque` vaut `true` ; le fichier garde tout. La sortie d'un agent est coupée à 64 Kio
dans le résumé (`agents[].tronque`).

Échec : `failure` avec un `error_message` au format `CODE: détail`, le code étant stable et unique dans la
plateforme : `INVALID_REQUEST`, `TOO_MANY_FILES`, `FILE_TOO_LARGE`, `FILE_NOT_FOUND`, `ANALYSIS_NOT_FOUND`
(l'`analyse_id` fourni n'est pas visible du jeton du worker), `RUN_FAILED` (avec les libellés des étapes en
échec — jamais leur sortie, qui reste au journal), `RUN_TIMEOUT`, `UPSTREAM_ERROR` (le service d'analyse ne
répond pas ou répond 5xx : réessayer plus tard), `WORKER_ERROR` (panne technique du worker). Ni URL, ni statut
HTTP, ni texte brut du backend ne sortent vers le consommateur.

## Configuration

Variables d'environnement (voir [`.env.example`](.env.example)) :

| Variable | Défaut | Rôle |
|---|---|---|
| `BROKER_URL` | (obligatoire) | RabbitMQ |
| `IN_QUEUE_NAME` / `OUT_QUEUE_NAME` | `mille_feuille_queue_in` / `_out` | files du service |
| `WORKER_CONCURRENCY` | `2` | tâches simultanées |
| `SERVICE_CLASS` | (aucune) | classe de service d'async-api ; `long` pour émettre la progression |
| `AWS_*` | (obligatoires) | stockage objet d'AsyncTaskAPI : lecture des fichiers déposés avant la tâche, **écriture** de `resultat.json` sous le préfixe du client |
| `MILLEFEUILLE_BASE_URL` | (obligatoire) | backend mille-feuille |
| `MILLEFEUILLE_API_TOKEN` | (obligatoire) | token API (`X-App-Token`), créé via `POST /api/app-tokens` |
| `MAX_FILE_SIZE_BYTES` / `MAX_TOTAL_SIZE_BYTES` / `MAX_FILES` | 50 Mo / 100 Mo / 20 | bornes mémoire |
| `RUN_TIMEOUT_SECONDS` / `POLL_INTERVAL_SECONDS` | `900` / `3` | attente du run ; refusé au démarrage si attente + transferts + nettoyage dépassent 1 080 s (60 % de l'échéance d'acquittement de 30 min du courtier) |
| `MILLEFEUILLE_UPLOAD_TIMEOUT` | `180` | délai du seul appel qui porte les fichiers (dépôt multipart) ; doit couvrir `MAX_TOTAL_SIZE_BYTES` à 2 Mio/s |
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
(vivacité) et `/ready` (stockage objet), sur le port `8084` ; `/__version__` et `/metrics` sur le même port.

**Mise à l'échelle** : KEDA sur la file d'entrée RabbitMQ (`extraObjects.millefeuille-keda-async-api` dans
`common-values.yaml`, déclencheur `rabbitmq` en AMQP, `QueueLength`, `value` = `WORKER_CONCURRENCY`, URL lue dans le secret —
**en FQDN**, l'opérateur KEDA est dans un autre namespace). `WORKER_CONCURRENCY × maxReplicaCount` doit rester sous ce que
les workers Celery et le hub absorbent : au-delà, les runs attendent dans mille-feuille et le pont les fait expirer
(`RUN_TIMEOUT`). Pas de descente à zéro au premier lot. Les ressources sont des valeurs de départ, fixées par le test de
charge sur beta. Un exemple de values pour internal-gw : `millefeuille/values/examples/values-internal-gw-beta.yaml`.

L'image `worker-async-api` doit être publiée avant d'activer le composant (voir ci-dessous).

## CI

`lint.yml`, `unit-tests.yml` et le build d'image de `ci.yml` ont besoin du secret de dépôt **`ASYNC_API_TOKEN`** :
un jeton fine-grained en lecture (*Contents: read*) sur `IA-Generative/async-api`. Sans lui, ces jobs sont ignorés
avec un avertissement (le reste de la CI n'est pas affecté).

**Publication de l'image à la release** : `cd.yml` ne construit pas encore l'image `worker-async-api` (son build a
besoin du secret `ASYNC_API_TOKEN`, et un build en échec bloquerait `bump-chart` et `release-chart`). Tant que ce n'est
pas fait, le composant Helm reste désactivé, ou pointe vers une image construite à la main.
