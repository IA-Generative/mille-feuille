# worker/classification

Worker Celery **dédié à la classification** des pages d'un dossier. Code, image et file Celery séparés de
`worker/agent_execution` et de `worker/extraction`.

- File : `classification` (le backend y dépose `app.tasks.classify_dossier`, voir `backend/app/celery_client.py`).
- Deux classifications par page, déposées avec un champ `source` et chacune dans sa propre unité de calcul :
  - **textuelle** (`source=textual`) : capture lue sur S3, description par un VLM, puis classification par un LLM en
    structured output parmi les labels de l'analyse ;
  - **visuelle** (`source=visual`) : CLIP en zero-shot sur la capture (CPU, torch), le texte « nom : définition » de
    chaque label étant comparé à l'image. Voir `app/clip.py`. Un échec visuel n'interrompt pas la textuelle ; une page
    sans capture n'a pas de classification visuelle. `CLIP_ENABLED=false` la désactive.
- Mono-label par défaut ; multi-label si `analyses.multi_label` est vrai (une prédiction par label retenu ; en visuel,
  ceux dont la probabilité atteint `CLIP_MULTI_LABEL_THRESHOLD`, au moins le meilleur).
- Le modèle CLIP (`CLIP_MODEL`, `openai/clip-vit-base-patch32` par défaut) est embarqué dans l'image au build : le
  worker ne télécharge rien au démarrage. Prévoir ~1,5 Go de mémoire.
- Il parle au backend par l'API interne (`/api/internal/*`) : aucun accès direct à la base.

Variables : `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` (ou `REDIS_URL`), `BACKEND_INTERNAL_URL`,
`INTERNAL_WORKER_TOKEN`, `AWS_*` (S3), `OPENAI_API_KEY`, `OPENAI_API_BASE_URL`, `OPENAI_TIMEOUT_SECONDS`, `OPENAI_MAX_RETRIES`, `LLM_MAX_OUTPUT_TOKENS`, `LLM_MODEL`, `VLM_MODEL`,
`CLIP_ENABLED`, `CLIP_MODEL`, `CLIP_NUM_THREADS`, `CLIP_MULTI_LABEL_THRESHOLD`.

Tests : `uv run pytest`.
