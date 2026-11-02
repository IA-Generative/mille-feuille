# mille-feuille backend

BFF (Backend For Frontend) FastAPI. Configuration entièrement par variables
d'environnement (pydantic-settings). En dev via `docker compose`, ces
variables sont injectées par `docker-compose.yaml` (racine du repo), qui
lui-même lit `.env` à la racine pour les `${VARIABLE}` qu'il référence -
voir `.env.example` à la racine du repo et la section _Configuration_ du
[README principal](../README.md).

## Variables d'environnement

### Base de données (`DatabaseSettings`)

| Variable       | Défaut                                                              | Description                    |
| -------------- | ------------------------------------------------------------------- | ------------------------------ |
| `DATABASE_URL` | `postgresql+asyncpg://millefeuille:millefeuille@localhost:5432/millefeuille` | URL Postgres (driver asyncpg). |

### Redis (`RedisSettings`)

| Variable    | Défaut                     | Description                                         |
| ----------- | -------------------------- | --------------------------------------------------- |
| `REDIS_URL` | `redis://localhost:6379/0` | Broker Celery + cache (ex : liste des modèles LLM). |

### Stockage S3 / RustFS (`StorageSettings`)

| Variable          | Défaut                  | Description                                       |
| ----------------- | ----------------------- | ------------------------------------------------- |
| `AWS_ENDPOINT_URL` | `http://localhost:9000` | RustFS en local/dev, un vrai endpoint S3 en prod. |
| `AWS_ACCESS_KEY_ID`   | `rustfsadmin`           |                                                   |
| `AWS_SECRET_ACCESS_KEY`   | `rustfsadmin`           |                                                   |
| `AWS_S3_BUCKET_NAME`       | `mille-feuille`           |                                                   |
| `AWS_DEFAULT_REGION`       | `us-east-1`             |                                                   |

### Keycloak / sessions (`KeycloakSettings`)

| Variable                  | Défaut                               | Description                                                          |
| ------------------------- | ------------------------------------ | -------------------------------------------------------------------- |
| `KEYCLOAK_URL`            | `http://localhost:8080`              | URL backend → Keycloak (nom de service Docker en dev).               |
| `KEYCLOAK_PUBLIC_URL`     | _(vide, retombe sur `KEYCLOAK_URL`)_ | URL Keycloak côté navigateur si différente (reverse proxy).          |
| `KEYCLOAK_REALM`          | `mille-feuille`                        |                                                                      |
| `KEYCLOAK_CLIENT_ID`      | `mille-feuille-backend`                |                                                                      |
| `KEYCLOAK_CLIENT_SECRET`  | _(vide)_                             | À définir en prod.                                                   |
| `BACKEND_PUBLIC_URL`      | `http://localhost:8000`              | Sert à construire le `redirect_uri` OAuth2 enregistré côté Keycloak. |
| `FRONTEND_URL`            | `http://localhost:5173`              | Où rediriger après login/logout ; aussi utilisé pour CORS.           |
| `SESSION_COOKIE_NAME`     | `millefeuille_session`                  |                                                                      |
| `SESSION_COOKIE_SECURE`   | `true`                               |                                                                      |
| `SESSION_COOKIE_SAMESITE` | `lax`                                |                                                                      |
| `SESSION_TTL_SECONDS`     | `604800` (7 jours)                   |                                                                      |

### Partage & jetons internes (`SharingSettings`)

| Variable                  | Défaut                               | Description                                                                             |
| ------------------------- | ------------------------------------ | --------------------------------------------------------------------------------------- |
| `SHARE_SECRET_KEY`        | `dev-only-share-secret-not-for-prod` | Clé HMAC des liens de partage d'analyse par email. À changer en prod.                   |
| `SHARE_DEFAULT_TTL_HOURS` | `168` (7 jours)                      |                                                                                         |
| `INTERNAL_WORKER_TOKEN`   | `dev-only-worker-token-not-for-prod` | Jeton statique de bootstrap pour les workers Celery (`X-App-Token`). À changer en prod. |

### Agent (`AgentSettings`, `SearchSettings`)

Les agents d'analyse, le chat d'un dossier, les résumés et l'indexation de la recherche tournent dans le backend
(voir [docs/backend/agent-dans-le-backend.md](../docs/backend/agent-dans-le-backend.md)).

| Variable                | Défaut                   | Description                                                                         |
| ----------------------- | ------------------------ | ----------------------------------------------------------------------------------- |
| `LLM_MODEL`             | `llama-3.3-70b-instruct` | Modèle texte des agents, du chat, des résumés et des propositions.                  |
| `CHAT_PLAN_MODEL`       | _(vide)_                 | Modèle du premier appel du chat (le plan) ; vide : celui du chat.                   |
| `MAX_CONCURRENT_JOBS`   | `8`                      | Travaux de l'agent menés en même temps dans un pod ; les suivants attendent.        |
| `AGENT_MAX_ITERATIONS`  | `10`                     | Tours d'outils au plus pour un agent ou une réponse du chat.                        |
| `QDRANT_URL`            | _(vide)_                 | Index de recherche des dossiers ; `:memory:` pour les tests. Vide : pas de recherche. |
| `QDRANT_API_KEY`        | _(vide)_                 | Clé d'API de Qdrant.                                                                |

### Modèles LLM (`LlmSettings`)

| Variable                        | Défaut   | Description                                                 |
| ------------------------------- | -------- | ----------------------------------------------------------- |
| `OPENAI_API_KEY`                | _(vide)_ | Clé du hub LLM (compatible API OpenAI).                     |
| `OPENAI_API_BASE_URL`           | _(vide)_ | URL de base du hub (ex : `https://mon-hub.example.com/v1`). |
| `CHAT_MODELS_CACHE_TTL_SECONDS` | `3600`   | Durée de mise en cache Redis de la liste des modèles.       |

`GET /api/models` utilise la librairie [`openai`](https://pypi.org/project/openai/)
(client `AsyncOpenAI`, ajouté aux dépendances du projet) pour interroger ce
hub : `models.list()` énumère tout ce qu'il sert (chat, embeddings, etc.),
puis chaque modèle candidat est testé avec un appel `chat.completions.create`
minimal pour ne garder que ceux qui savent réellement faire du chat. Le
résultat est mis en cache dans Redis (`CHAT_MODELS_CACHE_TTL_SECONDS`) pour
éviter de re-sonder le hub à chaque appel.

Sans `OPENAI_API_KEY`/`OPENAI_API_BASE_URL`, la route répond `503 Service
Unavailable` plutôt que de parler à un hub public par défaut - le frontend
affiche alors un sélecteur de modèle vide au lieu de planter.

Ces deux variables sont aussi ce qui alimente les sélecteurs de modèle
d'une conversation et d'un agent (`model` stocké sur `Conversation`/`Agent`,
voir `PUT .../conversations/{id}/model` et `PUT .../agents/{id}/model`).

## API éphémère et serveur MCP

`/api/ephemeral/*` expose une API d'analyse à la demande, temporaire par
défaut (TTL) - voir [docs/ephemeral-api.md](../docs/ephemeral-api.md).
Elle est aussi exposée via [MCP](https://modelcontextprotocol.io/) sous
`/mcp`, pour qu'un agent puisse l'utiliser directement - voir
[app/mcp/README.md](app/mcp/README.md).

## Migrations et schéma de la base

Chaque migration Alembic (`backend/migrations/versions/`) s'accompagne de la **mise à jour du schéma de la base** (`docs/backend/data-model.png`), commitée avec elle :

```bash
cd backend && uv run --group dev python scripts/generate_data_model.py
```

Le schéma est généré à partir des modèles SQLAlchemy (aucune base nécessaire ; il faut Graphviz, la commande `dot`). Pour tester une migration sans toucher à la base de développement, créer une base à part et la cibler avec `DATABASE_URL` :

```bash
docker exec mille-feuille-postgres-1 psql -U millefeuille -d postgres -c "CREATE DATABASE millefeuille_test"
export DATABASE_URL=postgresql+asyncpg://millefeuille:millefeuille@localhost:5432/millefeuille_test
uv run alembic upgrade head && uv run pytest
```

## Configuration locale

Depuis la racine du repo :

```bash
cp .env.example .env
```

`.env.example` est versionné (valeurs par défaut/placeholders, aucun
secret réel). `.env` ne l'est jamais (voir `.gitignore`) : c'est là que
vont les vraies clés/URLs (LLM hub, secrets Keycloak/partage en prod...).
`docker compose up` le lit automatiquement.
