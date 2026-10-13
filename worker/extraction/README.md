# worker/extraction

Worker Celery **dédié à l'extraction des entités** d'un dossier. Code, image et file Celery séparés de
`worker/agent_execution` et de `worker/classification`.

- File : `entity_extraction` (le backend y dépose `app.tasks.extract_dossier_entities`, voir
  `backend/app/celery_client.py`).
- Le texte des pages est découpé en lots selon un budget de jetons (`EXTRACTION_*`), chaque lot est envoyé au LLM en
  structured output avec un groupe de définitions d'entités, puis les doublons entre lots sont fusionnés.
- Pas de S3 : seul le texte des pages est lu, via l'API interne du backend (`/api/internal/*`).

Variables : `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` (ou `REDIS_URL`), `BACKEND_INTERNAL_URL`,
`INTERNAL_WORKER_TOKEN`, `OPENAI_API_KEY`, `OPENAI_API_BASE_URL`, `LLM_MODEL`, `EXTRACTION_*`.

Tests : `uv run pytest`.
