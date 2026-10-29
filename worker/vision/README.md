# worker/vision - description des images et des tableaux (VLM du hub)

Worker Celery qui **décrit** les images et les tableaux d'une page scannée à partir de leur recadrage. Fait partie de
l'extraction par layout ; le worker d'extraction (`worker/document_process`) lui envoie les régions retenues et écrit la
description dans le texte de la page (`[Image : ...]`, ou sous le tableau).

- Tâche `app.tasks.describe_regions(document_id, page_number, image_key, regions, prompt=None, model=None)` sur la queue
  `document_vision`. `image_key` est l'image de la page en S3 ; `regions` une liste de `{"id", "box", "kind"}` (boîte entre
  0 et 1). Le résultat est un `PageDescriptions` en JSON (`app/contracts.py`) : une description **par id** (une région dont
  le modèle ne dit rien est absente), le modèle et la consommation (`usage` : jetons comptés par le hub, secondes).
- **Aucun modèle n'est embarqué** : chaque recadrage est montré à un VLM du hub (API compatible OpenAI,
  `OPENAI_API_BASE_URL` / `OPENAI_API_KEY`, modèle `VLM_MODEL` - le même que `worker/classification`, ou `model` s'il est
  donné). Sans `prompt`, une question pour une image et une pour un tableau, en français.
- `app/contracts.py` est une **copie** de `worker/document_process/app/ocr/contracts.py` : un test échoue si elles divergent.

## Image

`python:3.12-slim`, `pip` retiré, non root. Légère : ni PyTorch ni modèle.

## Tests

```bash
uv run pytest
```
