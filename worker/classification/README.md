# worker/classification

Worker Celery **dédié à la classification** des pages d'un dossier. Code, image et file Celery séparés de
`worker/agent_execution` et de `worker/extraction`.

- File : `classification` (le backend y dépose `app.tasks.classify_dossier`, voir `backend/app/celery_client.py`).
- Pour chaque page : capture lue sur S3, description par un VLM, puis classification par un LLM en structured output
  parmi les labels de l'analyse. Mono-label par défaut ; multi-label si `analyses.multi_label` est vrai (une
  prédiction par label retenu).
- Il parle au backend par l'API interne (`/api/internal/*`) : aucun accès direct à la base.

Variables : `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` (ou `REDIS_URL`), `BACKEND_INTERNAL_URL`,
`INTERNAL_WORKER_TOKEN`, `AWS_*` (S3), `OPENAI_API_KEY`, `OPENAI_API_BASE_URL`, `LLM_MODEL`, `VLM_MODEL`.

Tests : `uv run pytest`.
