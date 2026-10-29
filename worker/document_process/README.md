# worker/document_process - extraction du texte des documents

Worker Celery (`app.tasks.extract_document_text`) : télécharge le document depuis S3, en extrait le texte page par page, les
blocs de mise en page (bbox), le texte positionné (lignes et mots) et une capture par page, et écrit le tout côté backend.
Le résumé et l'indexation dans la recherche du dossier partent ensuite sur la file `agent_execution`.

## OCR des pages scannées

`liteparse` lit le fichier. Ce qui lit les pages **scannées** dépend de `OCR_ENGINE` :

| `OCR_ENGINE` | Ce qui lit une page scannée |
|---|---|
| `tesseract` (défaut) | l'OCR de liteparse (Tesseract, `OCR_LANGUAGE=fra`) |
| `layout` | les pods PaddleOCR ci-dessous ; une page qu'ils ne savent pas lire retombe sur Tesseract |

Avec `layout`, liteparse ne lance pas d'OCR : il dit, page par page, si elle est scannée (`app/ocr/scanned.py::is_scanned`).
Ces pages sont rendues à `OCR_PAGE_DPI`, déposées sur S3 (`ocr-pages/<document>/page-<n>.png`, supprimées ensuite) et envoyées
par Celery, `OCR_PAGE_WINDOW` à la fois, à des pods qui ont chacun leur file :

```
layout (worker/layout, PP-DocLayoutV3)  ->  régions typées, boîtes, ordre de lecture
   ├─ ocr   (worker/ocr,   PP-OCRv5)       texte des régions de texte : lignes et mots positionnés
   ├─ table (worker/table, SLANet_plus)    structure et cellules des tableaux
   └─ vision (worker/vision, VLM du hub)   description des images et des tableaux
```

`app/ocr/assemble.py` en fait le markdown de la page (titres `#`/`##`, paragraphes, listes, tableaux en Markdown,
`[Image : ...]`) et les lignes positionnées dont `build_text_boxes` tire le surlignage. Les en-têtes, pieds de page,
numéros de page, sigles, tampons et formules n'y sont pas.

Les pods sont des images à part (`worker/layout`, `worker/ocr`, `worker/table`, `worker/vision`) : ce worker leur envoie des
tâches par nom, il ne les importe pas. `app/ocr/contracts.py` est le contrat commun - chaque pod en porte une **copie**
(un test échoue si elles divergent : `cp worker/document_process/app/ocr/contracts.py worker/<pod>/app/contracts.py`).

### Réglages

| Variable | Défaut | Rôle |
|---|---|---|
| `OCR_ENGINE` | `tesseract` | `layout` pour les pods PaddleOCR |
| `LAYOUT_QUEUE_NAME` / `OCR_QUEUE_NAME` / `TABLE_QUEUE_NAME` / `VISION_QUEUE_NAME` | `document_layout` / `document_ocr` / `document_table` / `document_vision` | files des pods (les mêmes des deux côtés) |
| `OCR_PAGE_DPI` | `200` | résolution des pages confiées aux pods |
| `OCR_SCANNED_MIN_CHARS` | `20` | une page avec moins de texte natif que cela et des images est scannée |
| `OCR_PAGE_WINDOW` | `4` | pages d'un document entre les mains des pods en même temps |
| `OCR_STAGE_TIMEOUT_SECONDS` | `900` | durée maximale d'une étape d'une page (attente en file comprise) avant le repli sur Tesseract |
| `OCR_POLL_SECONDS` | `0.5` | intervalle de sondage des résultats |
| `OCR_READ_TABLES_AS_TEXT` | `false` | `true` : un tableau est lu comme du texte, une ligne par ligne, sans le pod `table` |
| `OCR_TABLE_MIN_SCORE` | `0.6` | score minimal d'un tableau pour être dit fiable (sinon `[Structure du tableau douteuse]`) |
| `VISION_POD_ENABLED` | `false` | décrire les images et tableaux avec le pod `vision` |
| `CAPTION_MODEL` | *(vide)* | modèle du hub qui décrit ; vide : le `VLM_MODEL` du pod |
| `CAPTION_MIN_PIXELS` / `CAPTION_MAX_PER_PAGE` / `CAPTION_MAX_PER_DOCUMENT` | `96` / `5` / `50` | quelles images sont décrites, et combien |
| `CAPTION_TABLES` | `true` | décrire aussi les tableaux lus comme tableaux |
| `TASK_TIME_LIMIT_SECONDS` | `0` | limite dure de la tâche ; 0 : 300 s avec Tesseract, 3600 s avec `layout` |

Les réglages du modèle (`OCR_REGION_MIN_SCORE`, `LAYOUT_TABLE_MIN_SCORE`, `ONNX_INTRA_OP_THREADS`...) sont ceux du pod
concerné, voir son README.

### Les lancer

```bash
OCR_ENGINE=layout VISION_POD_ENABLED=true docker compose --profile ocr up --build
```

Dans le chart, `worker_ocr_layout`, `worker_ocr`, `worker_ocr_table` et `worker_ocr_vision` sont désactivés par défaut
(`enabled: false`) : activez-les avec `OCR_ENGINE: layout` sur `worker_document`.

## Développer

```bash
cd worker/document_process
uv sync
uv run pytest -q
uv run ruff check . && uv run ruff format --check .
```
