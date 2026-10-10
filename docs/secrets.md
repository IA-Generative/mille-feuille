# Secrets Kubernetes — mille-feuille

Les secrets sont gérés via **HashiCorp Vault** (Vault Static Secrets via VSO) et référencés
dans `millefeuille/values/common-values.yaml` sous `extraObjects`.

Chaque secret ci-dessous correspond à un **chemin Vault** (`mirai` mount, kv-v2) et à un
**Secret Kubernetes** créé automatiquement par le Vault Secrets Operator.

---

## Tableau récapitulatif

| Secret K8s                | Chemin Vault (`exploration/`)       | Type K8s                    | Utilisé par                          |
| ------------------------- | ------------------------------ | --------------------------- | ------------------------------------ |
| `millefeuille-s3`            | `millefeuille-s3`                 | Opaque                      | backend, worker_document, worker_agent, worker_render |
| `millefeuille-keycloak`      | `millefeuille-keycloak`           | Opaque                      | backend                               |
| `millefeuille-openai`        | `millefeuille-openai`             | Opaque                      | backend, worker_agent                 |
| `millefeuille-worker`        | `millefeuille-worker`             | Opaque                      | backend, worker_document, worker_agent |
| `millefeuille-redis`         | `millefeuille-redis`              | Opaque                      | backend, worker_document, worker_agent, worker_render, redis sub-chart, KEDA |
| `millefeuille-meilisearch`   | `millefeuille-meilisearch`        | Opaque                      | backend (envFrom)                     |
| `millefeuille-db-superuser`  | `millefeuille-db-superuser`       | kubernetes.io/basic-auth    | CNPG (superuserSecret)                |
| `millefeuille-db-appuser`    | `millefeuille-db-appuser`         | kubernetes.io/basic-auth    | CNPG (initdb.secret)                  |
| `millefeuille-db-infos`      | `millefeuille-db-appuser`         | Opaque (transformé)         | backend, job de migration             |
| `millefeuille-db-backups`    | `millefeuille-db-backups`         | Opaque                      | CNPG (barmanObjectStore)              |
| `millefeuille-async-api-worker` | `millefeuille-async-api-worker` | Opaque                   | worker_async_api                      |
| `registry-pull-secret`    | — (manuel ou ArgoCD)           | kubernetes.io/dockerconfigjson | Tous les pods (imagePullSecrets)    |

---

## 1. `millefeuille-s3` — Stockage objet S3

Variables attendues dans Vault :

| Variable          | Description                                      | Exemple                          |
| ----------------- | ------------------------------------------------ | -------------------------------- |
| `AWS_ACCESS_KEY_ID`   | Clé d'accès S3 (access key ID)                    | `AKIA...`                        |
| `AWS_SECRET_ACCESS_KEY`   | Clé secrète S3 (secret access key)               | `xxxxxxxxxxxx`                   |
| `AWS_S3_BUCKET_NAME`       | Nom du bucket S3                                 | `millefeuille-prod`                 |
| `AWS_DEFAULT_REGION`       | Région S3                                        | `fr-par`                         |
| `AWS_ENDPOINT_URL` | Endpoint S3 (un hôte sans scheme reçoit `https://` côté worker_render) | `s3.fr-par.scw.cloud`         |

> **Note** : `AWS_ENDPOINT_URL` est défini en clair dans `common-values.yaml` (`https://s3.fr-par.scw.cloud`).
> Seules les credentials (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`) et le bucket/région viennent du secret.

**Consommateurs** : backend (`StorageSettings`), worker_document (`WorkerSettings`),
worker_agent (`WorkerSettings`), worker_render (`WorkerSettings` : `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_S3_BUCKET_NAME`).
Ce dernier lit le modèle ODT et **écrit** les documents générés et les aperçus dans le bucket. Il ajoute
`https://` à un `AWS_ENDPOINT_URL` sans schéma (`s3.fr-par.scw.cloud`) : boto3 refuse un hôte nu.

---

## 2. `millefeuille-keycloak` — Authentification Keycloak

Variables attendues dans Vault :

| Variable                  | Description                                              | Exemple                              |
| ------------------------- | -------------------------------------------------------- | ------------------------------------ |
| `KEYCLOAK_URL`            | URL interne Keycloak (backend → Keycloak, Docker service) | `http://keycloak:8080`             |
| `KEYCLOAK_PUBLIC_URL`     | URL publique Keycloak (navigateur, si différente)        | `https://sso.example.com`           |
| `KEYCLOAK_CLIENT_SECRET`  | Secret client OAuth2 (confidentiel)                      | `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxx`  |
| `BACKEND_PUBLIC_URL`      | URL publique du backend (pour `redirect_uri`)            | `https://api.example.com`           |
| `FRONTEND_URL`            | URL publique du frontend (redirect post-login/logout)    | `https://app.example.com`           |
| `SHARE_SECRET_KEY`        | Clé HMAC pour les liens de partage d'analyse (magic link) | (aléatoire, 32+ caractères)        |
| `INTERNAL_WORKER_TOKEN`   | Token partagé pour l'authentification des workers sur `/api/internal/*` | (aléatoire, 32+ caractères) |

> **Variables en clair** (dans `common-values.yaml`, pas dans le secret) :
> `KEYCLOAK_REALM`, `KEYCLOAK_CLIENT_ID`, `SESSION_COOKIE_SECURE`.

**Consommateurs** : backend (`KeycloakSettings`, `SharingSettings`).

---

## 3. `millefeuille-openai` — Hub LLM (compatible API OpenAI)

Variables attendues dans Vault :

| Variable              | Description                                          | Exemple                              |
| --------------------- | ---------------------------------------------------- | ------------------------------------ |
| `OPENAI_API_KEY`      | Clé API pour le hub LLM                              | `sk-xxxxxxxx`                        |
| `OPENAI_API_BASE_URL` | URL de base du hub LLM (compatible OpenAI)          | `https://llm-hub.example.com/v1`    |

> **Note** : `OPENAI_API_BASE_URL` est aussi défini en clair dans `common-values.yaml`
> (commenté). Si la valeur est publique, elle peut rester en clair ; sinon la mettre dans le secret.

**Consommateurs** : backend (`LlmSettings`), worker_agent.

---

## 4. `millefeuille-worker` — Configuration partagée des workers

Variables attendues dans Vault :

| Variable                | Description                                                        | Exemple                              |
| ----------------------- | ------------------------------------------------------------------ | ------------------------------------ |
| `INTERNAL_WORKER_TOKEN` | Token pour l'authentification des workers sur `/api/internal/*`     | (identique à `millefeuille-keycloak`)   |
| `OPENAI_API_KEY`        | Clé API pour le hub LLM (VLM + LLM classification/extraction)     | `sk-xxxxxxxx`                        |
| `OPENAI_API_BASE_URL`   | URL de base du hub LLM                                             | `https://llm-hub.example.com/v1`    |
| `VLM_MODEL`             | Modèle vision pour la description des pages (worker_agent)         | `pixtral-12b-2409`                   |
| `LLM_MODEL`             | Modèle texte pour classification/extraction (worker_agent)        | `llama-3.3-70b-instruct`             |

> **Important** : `INTERNAL_WORKER_TOKEN` doit être **identique** à celui du secret
> `millefeuille-keycloak` (le backend le vérifie, les workers l'envoient).

**Consommateurs** : worker_document, worker_agent. **Pas** worker_render : il n'appelle ni le backend ni le LLM, il ne reçoit donc
ni `INTERNAL_WORKER_TOKEN` ni la clé du LLM (principe du moindre privilège : ce secret n'est pas dans son `envFrom`).

---

## 5. `millefeuille-redis` — Redis (broker Celery + checkpointer LangGraph)

Variables attendues dans Vault :

| Variable          | Description                                                        | Exemple                              |
| ----------------- | ------------------------------------------------------------------ | ------------------------------------ |
| `REDIS_PASSWORD`  | Mot de passe Redis                                                 | (aléatoire, 24+ caractères)          |

> **Transformation VSO** : le secret K8s généré contient en plus une variable `REDIS_URL`
> calculée automatiquement :
> ```
> redis://:<REDIS_PASSWORD>@millefeuille-redis:6379/0
> ```

**Consommateurs** :
- backend (`RedisSettings` → `REDIS_URL`)
- worker_document, worker_agent, worker_render (`REDIS_URL`, pris comme broker et backend de résultats Celery faute de `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND`)
- redis sub-chart (`auth.existingSecret`)
- KEDA `TriggerAuthentication` (pour le scaling sur la longueur de queue)

---

## Variables d'environnement du worker `worker_render`

Le worker de rendu de documents (`worker/document_render`, voir son [README](../worker/document_render/README.md)) lit les
variables suivantes. **Aucun secret propre** : il réutilise `millefeuille-s3` et `millefeuille-redis`, et rien d'autre.

| Variable | Rôle | Origine en Kubernetes | Valeur par défaut |
| --- | --- | --- | --- |
| `REDIS_URL` | URL Redis (avec mot de passe) : broker **et** résultats Celery | secret `millefeuille-redis` (champ calculé par VSO) | `redis://localhost:6379/0` |
| `CELERY_BROKER_URL` | Broker Celery, si différent de `REDIS_URL` | non défini | `REDIS_URL` |
| `CELERY_RESULT_BACKEND` | Backend de résultats, si différent de `REDIS_URL` | non défini | `REDIS_URL` |
| `AWS_ACCESS_KEY_ID` | Clé d'accès S3 | secret `millefeuille-s3` | `rustfsadmin` |
| `AWS_SECRET_ACCESS_KEY` | Clé secrète S3 | secret `millefeuille-s3` | `rustfsadmin` |
| `AWS_S3_BUCKET_NAME` | Bucket (modèles lus ; documents et aperçus écrits) | secret `millefeuille-s3` | `mille-feuille` |
| `AWS_ENDPOINT_URL` | Endpoint S3 (docker-compose : RustFS) ; un hôte sans schéma reçoit `https://` | `values/common-values.yaml` (en clair) | `http://localhost:9000` |
| `CELERY_QUEUE_NAME` | Nom de la file (indicatif : l'image écoute `document_render`) | `values/common-values.yaml` | — |
| `SOFFICE_BINARY` | Binaire LibreOffice | image | `soffice` |
| `SOFFICE_TIMEOUT_SECONDS` | Délai maximal d'une conversion (au-delà, le processus est tué) | image | `120` |
| `FC_MATCH_BINARY` | Binaire fontconfig (contrôle des polices à l'import) | image | `fc-match` |

> `AWS_DEFAULT_REGION` du secret n'est pas utilisé par ce worker. `millefeuille-worker` (jeton interne, clé du LLM) **n'est pas fourni** à ce
> pod : il n'en a pas besoin.

---

## 6. `millefeuille-meilisearch` — Meilisearch (recherche)

Variables attendues dans Vault :

| Variable              | Description                          | Exemple                              |
| --------------------- | ------------------------------------ | ------------------------------------ |
| `MEILISEARCH_URL`     | URL du service Meilisearch           | `http://millefeuille-meilisearch:7700`  |
| `MEILISEARCH_API_KEY` | Clé API Meilisearch                  | (aléatoire, 32+ caractères)          |

> **Note** : ce secret est référencé dans le `envFrom` du backend mais n'est pas encore
> consommé par le code applicatif (`backend/app/config/` n'a pas de `MeilisearchSettings`).
> Il est probablement réservé pour une fonctionnalité future.

**Consommateurs** : backend (envFrom).

---

## 7. `millefeuille-db-superuser` — Superuser PostgreSQL (CNPG)

Type : `kubernetes.io/basic-auth` (CNPG l'exige, pas Opaque).

Variables attendues dans Vault :

| Variable   | Description                          | Exemple              |
| ---------- | ------------------------------------ | -------------------- |
| `username` | Nom du superuser PostgreSQL          | `postgres`           |
| `password` | Mot de passe du superuser            | (aléatoire, 24+ car.) |

> **Type** : `kubernetes.io/basic-auth` — obligatoire pour CNPG `superuserSecret`.

**Consommateurs** : CNPG (`cluster.superuserSecret`).

---

## 8. `millefeuille-db-appuser` — Utilisateur applicatif PostgreSQL (CNPG)

Type : `kubernetes.io/basic-auth` (CNPG l'exige, pas Opaque).

Variables attendues dans Vault :

| Variable   | Description                          | Exemple              |
| ---------- | ------------------------------------ | -------------------- |
| `username` | Nom de l'utilisateur applicatif      | `millefeuille`          |
| `password` | Mot de passe de l'utilisateur app.   | (aléatoire, 24+ car.) |

> **Transformation VSO** : le secret `millefeuille-db-infos` (ci-dessous) est généré à partir
> de ce même chemin Vault, avec une transformation qui crée `DATABASE_URL`.

**Consommateurs** : CNPG (`cluster.initdb.secret`).

---

## 9. `millefeuille-db-infos` — URL de connexion base de données (calculée)

Ce secret est **généré par transformation VSO** à partir du chemin Vault `millefeuille-db-appuser`.

Variables dans le secret K8s généré :

| Variable       | Description                                                        | Source                              |
| -------------- | ------------------------------------------------------------------ | ----------------------------------- |
| `DATABASE_URL` | URL de connexion SQLAlchemy (asyncpg)                              | Calculée : `postgresql+asyncpg://<username>:<password>@millefeuille-pg-cluster-rw:5432/millefeuille` |

> **Transformation** : VSO lit `username` et `password` depuis le chemin Vault
> `millefeuille-db-appuser` et construit la `DATABASE_URL` complète.
> Le `excludes: [".*"]` masque `username`/`password` dans le secret final (seul `DATABASE_URL` est exposé).

**Consommateurs** : backend (`DatabaseSettings`), job de migration Alembic.

---

## 10. `millefeuille-db-backups` — Credentials S3 pour les backups CNPG

Variables attendues dans Vault :

| Variable              | Description                                          | Exemple                          |
| --------------------- | ---------------------------------------------------- | -------------------------------- |
| `AWS_ACCESS_KEY_ID`   | Clé d'accès S3 pour les backups                      | `AKIA...`                        |
| `AWS_SECRET_ACCESS_KEY` | Clé secrète S3 pour les backups                    | `xxxxxxxxxxxx`                   |
| `AWS_REGION`          | Région du bucket de backup                           | `fr-par`                         |

> **Note** : le bucket et l'endpoint sont définis en clair dans `common-values.yaml`
> (`endpointURL: https://s3.fr-par.scw.cloud`). Seules les credentials viennent du secret.

**Consommateurs** : CNPG (`backups.secret`, `recovery.secret`, `replica.origin.objectStore.secret`).

---

## 11. `registry-pull-secret` — Pull secret du registry Harbor

Type : `kubernetes.io/dockerconfigjson`.

Ce secret n'est **pas** géré par Vault/VSO. Il doit être créé manuellement (ou via ArgoCD) :

```bash
kubectl create secret docker-registry registry-pull-secret \
  --docker-server=harbor.sdid.cpin.numerique-interieur.com \
  --docker-username=<username> \
  --docker-password=<password> \
  --docker-email=<email> \
  -n <namespace>
```

**Consommateurs** : tous les pods (via `global.imagePullSecrets`).

---

## 12. `millefeuille-async-api-worker` — Worker AsyncTaskAPI (optionnel)

Utilisé par le composant `worker_async_api` (activé par `worker_async_api.enabled: true`). Le `VaultStaticSecret`
est déclaré sans condition dans `extraObjects` (`millefeuille/values/common-values.yaml`), comme les autres : **créer le
chemin Vault avant la synchronisation**, même si le composant n'est pas encore activé.

Ce secret ne contient que des **identifiants**. Tout le reste est un réglage normal, avec une valeur par défaut dans
`env` de `worker_async_api` (`common-values.yaml`) : files, `SERVICE_CLASS`, `WORKER_CONCURRENCY`, endpoint, bucket et
région S3, `MILLEFEUILLE_BASE_URL`, limites de taille, délais...

Variables attendues dans Vault :

| Variable              | Description                                                                   | Exemple                                  |
| --------------------- | ----------------------------------------------------------------------------- | ---------------------------------------- |
| `BROKER_URL`          | URL RabbitMQ d'AsyncTaskAPI, identifiants compris                              | `amqps://user:password@rabbitmq:5672`    |
| `AWS_ACCESS_KEY_ID`       | Clé d'accès au stockage objet **d'AsyncTaskAPI** (lecture seule suffit : lecture des objets et `HEAD` du bucket) | `SCW...` |
| `AWS_SECRET_ACCESS_KEY`       | Clé secrète associée                                                           | `xxxxxxxx`                               |
| `MILLEFEUILLE_API_TOKEN` | Token API de mille-feuille (en-tête `X-App-Token`), voir ci-dessous              | `ddd_...`                                |

> **Ce n'est pas le stockage de mille-feuille** : `millefeuille-s3` ne sert pas ici. Le worker lit les fichiers dans le
> stockage d'AsyncTaskAPI (endpoint et bucket dans `env`), puis les envoie à mille-feuille par son API.

**Créer `MILLEFEUILLE_API_TOKEN`** : le token est renvoyé **une seule fois** à sa création, par un utilisateur Keycloak
(les routes `/api/app-tokens` n'acceptent pas un token API) :

```bash
curl -s -X POST https://api.example.com/api/app-tokens \
  -H "Authorization: Bearer $KEYCLOAK_ACCESS_TOKEN" -H "Content-Type: application/json" \
  -d '{"name": "async-api-worker"}' | jq -r .token
```

Un token par déploiement, à révoquer avec `DELETE /api/app-tokens/{id}` (rotation : en créer un nouveau, mettre à jour
Vault, redémarrer le worker, puis révoquer l'ancien). Le token donne accès à `/api/ephemeral/*` et `/api/internal/*`
pour le créateur seul : les analyses et runs créés par le worker ne sont visibles que par lui.

**Consommateurs** : worker_async_api.

---

## Commandes Vault de référence

### Lister les chemins Vault existants

```bash
vault kv list mirai/
```

### Lire un secret Vault

```bash
vault kv get mirai/millefeuille-s3
```

### Créer / mettre à jour un secret Vault

```bash
# Exemple : millefeuille-s3
vault kv put mirai/millefeuille-s3 \
  AWS_ACCESS_KEY_ID="AKIA..." \
  AWS_SECRET_ACCESS_KEY="xxxxxxxxxxxx" \
  AWS_S3_BUCKET_NAME="millefeuille-prod" \
  AWS_DEFAULT_REGION="fr-par" \
  AWS_ENDPOINT_URL="s3.fr-par.scw.cloud"

# Exemple : millefeuille-keycloak
vault kv put mirai/millefeuille-keycloak \
  KEYCLOAK_URL="http://keycloak:8080" \
  KEYCLOAK_PUBLIC_URL="https://sso.example.com" \
  KEYCLOAK_CLIENT_SECRET="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxx" \
  BACKEND_PUBLIC_URL="https://api.example.com" \
  FRONTEND_URL="https://app.example.com" \
  SHARE_SECRET_KEY="$(openssl rand -hex 32)" \
  INTERNAL_WORKER_TOKEN="$(openssl rand -hex 32)"

# Exemple : millefeuille-openai
vault kv put mirai/millefeuille-openai \
  OPENAI_API_KEY="sk-xxxxxxxx" \
  OPENAI_API_BASE_URL="https://llm-hub.example.com/v1"

# Exemple : millefeuille-worker
vault kv put mirai/millefeuille-worker \
  INTERNAL_WORKER_TOKEN="<identique à millefeuille-keycloak>" \
  OPENAI_API_KEY="sk-xxxxxxxx" \
  OPENAI_API_BASE_URL="https://llm-hub.example.com/v1" \
  VLM_MODEL="pixtral-12b-2409" \
  LLM_MODEL="llama-3.3-70b-instruct"

# Exemple : millefeuille-async-api-worker (worker AsyncTaskAPI, optionnel)
vault kv put mirai/millefeuille-async-api-worker \
  BROKER_URL="amqps://user:password@rabbitmq.example.com:5672" \
  AWS_ACCESS_KEY_ID="SCW..." \
  AWS_SECRET_ACCESS_KEY="xxxxxxxx" \
  MILLEFEUILLE_API_TOKEN="ddd_..."

# Exemple : millefeuille-redis
vault kv put mirai/millefeuille-redis \
  REDIS_PASSWORD="$(openssl rand -base64 24)"

# Exemple : millefeuille-meilisearch
vault kv put mirai/millefeuille-meilisearch \
  MEILISEARCH_URL="http://millefeuille-meilisearch:7700" \
  MEILISEARCH_API_KEY="$(openssl rand -hex 32)"

# Exemple : millefeuille-db-superuser (type: kubernetes.io/basic-auth)
vault kv put mirai/millefeuille-db-superuser \
  username="postgres" \
  password="$(openssl rand -base64 24)"

# Exemple : millefeuille-db-appuser (type: kubernetes.io/basic-auth)
vault kv put mirai/millefeuille-db-appuser \
  username="millefeuille" \
  password="$(openssl rand -base64 24)"

# Exemple : millefeuille-db-backups
vault kv put mirai/millefeuille-db-backups \
  AWS_ACCESS_KEY_ID="AKIA..." \
  AWS_SECRET_ACCESS_KEY="xxxxxxxxxxxx" \
  AWS_REGION="fr-par"
```

---

## Vérification post-déploiement

```bash
# Lister les secrets K8s générés par VSO
kubectl get secrets -n <namespace> | grep millefeuille

# Vérifier le contenu d'un secret
kubectl get secret millefeuille-s3 -n <namespace> -o jsonpath='{.data}' | jq 'to_entries[] | "\(.key): \(.value | @base64d)\n"'

# Vérifier que les VaultStaticSecrets sont synchronisés
kubectl get vaultstaticsecret -n <namespace>
```

---

## Notes importantes

1. **`INTERNAL_WORKER_TOKEN`** doit être **identique** entre `millefeuille-keycloak` et
   `millefeuille-worker` — le backend le vérifie côté `/api/internal/*`, les workers l'envoient
   en header `Authorization`.

2. **`millefeuille-db-infos`** n'a pas de chemin Vault propre — il est généré par transformation
   VSO à partir de `millefeuille-db-appuser` (même chemin Vault, `DATABASE_URL` calculée).

3. **`millefeuille-db-superuser` et `millefeuille-db-appuser`** doivent être de type
   `kubernetes.io/basic-auth` (pas Opaque) — CNPG l'exige pour `superuserSecret` et
   `initdb.secret`.

4. **`BACKEND_API_URL` vs `BACKEND_INTERNAL_URL`** : le chart définit `BACKEND_API_URL`
   en clair dans `common-values.yaml`, mais le code des workers attend `BACKEND_INTERNAL_URL`.
   Vérifier que la variable correcte est utilisée (potentiellement à corriger dans le chart).

5. **`REDIS_URL`** est calculée par transformation VSO à partir de `REDIS_PASSWORD` —
   ne pas la stocker manuellement dans Vault.

---

## Secrets GitHub Actions

Distincts des secrets Kubernetes : ils servent à la CI, pas au déploiement.

| Secret (Settings → Secrets and variables → Actions) | Obligatoire | Rôle |
| --------------------------------------------------- | ----------- | ---- |
| `ASYNC_API_TOKEN` | non (jobs ignorés sans lui) | Accès en lecture au dépôt **privé** `IA-Generative/async-api`, qui héberge `mic-worker` (dépendance du worker `worker/async_api`). Utilisé par les jobs de lint, de tests et de build d'image de ce worker. |

Créer le jeton : *Settings → Developer settings → Personal access tokens → Fine-grained tokens*, **Resource owner**
`IA-Generative`, **Only select repositories** → `async-api`, permission **Contents : Read-only** (et rien d'autre).
L'organisation peut exiger l'approbation du jeton par un propriétaire. Choisir une expiration et la noter : à l'expiration, les jobs du worker sont de nouveau ignorés (avertissement dans la CI).
Un compte de service ou une GitHub App limitée à ce dépôt vaut mieux qu'un jeton personnel. Ne jamais utiliser un jeton classic.

En local, `docker compose --profile async-api build` lit le même jeton dans `GH_TOKEN` (`export GH_TOKEN=$(gh auth token)`).

