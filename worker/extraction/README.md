# worker/extraction

Worker Celery **dédié à l'extraction des entités** d'un dossier. Code, image et file Celery séparés de
`worker/agent_execution` et de `worker/classification`.

- File : `entity_extraction` (le backend y dépose `app.tasks.extract_dossier_entities`, voir
  `backend/app/celery_client.py`).
- Deux extractions par document, déposées avec un champ `source` et chacune dans sa propre unité de calcul :
  - **LLM** (`source=textual`) : le texte des pages est découpé en lots selon un budget de jetons (`EXTRACTION_*`),
    chaque lot est envoyé au LLM en structured output avec un groupe de définitions d'entités, puis les doublons
    entre lots sont fusionnés ;
  - **GLiNER2.5** (`source=gliner`) : un modèle d'extraction (CPU, torch) reçoit les définitions comme descriptions
    (`nom -> définition`) et extrait des valeurs littéralement présentes dans chaque page, au-dessus de
    `GLINER_THRESHOLD`. Une même valeur trouvée sur plusieurs pages est une seule entité qui couvre ces pages. Les
    entités de type booléen sont ignorées (ce ne sont pas des empans de texte). Voir `app/gliner.py`. Un échec
    GLiNER n'interrompt pas l'extraction LLM. `GLINER_ENABLED=false` le désactive.
- Le modèle (`GLINER_MODEL`, `fastino/gliner2.5-multi-v1` par défaut, multilingue) est embarqué dans l'image au
  build : le worker ne télécharge rien au démarrage. Prévoir ~1,5 Go de mémoire.
- Pas de S3 : seul le texte des pages est lu, via l'API interne du backend (`/api/internal/*`).

Variables : `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` (ou `REDIS_URL`), `BACKEND_INTERNAL_URL`,
`INTERNAL_WORKER_TOKEN`, `OPENAI_API_KEY`, `OPENAI_API_BASE_URL`, `LLM_MODEL`, `EXTRACTION_*`, `GLINER_ENABLED`,
`GLINER_MODEL`, `GLINER_NUM_THREADS`, `GLINER_THRESHOLD`.

Tests : `uv run pytest`.
