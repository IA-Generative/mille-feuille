"""Classification visuelle d'une page avec CLIP (zero-shot, CPU).

CLIP place l'image de la page et le texte de chaque label (« nom : définition ») dans un même espace : le label
dont le texte ressemble le plus à la capture l'emporte. Aucun entraînement : les labels de l'analyse suffisent.

Le modèle est chargé une fois par process, à la première page à classer (le chargement prend quelques secondes).
CLIP a surtout vu de l'anglais et ne lit que 77 jetons : un label court et descriptif donne de meilleurs résultats
qu'une longue définition (qui est coupée).
"""

import io
import logging
import threading

from app.config import settings
from app.llm import LabelPrediction

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_loaded: tuple | None = None


def _load():
    """(modèle, processeur) CLIP, chargés une seule fois. Les imports sont différés : torch ne se charge pas tant
    que la classification visuelle n'est pas demandée."""
    global _loaded
    with _lock:
        if _loaded is None:
            import torch
            from transformers import CLIPModel, CLIPProcessor

            torch.set_num_threads(settings.CLIP_NUM_THREADS)
            model = CLIPModel.from_pretrained(settings.CLIP_MODEL).eval()
            processor = CLIPProcessor.from_pretrained(settings.CLIP_MODEL)
            _loaded = (model, processor)
            logger.info("CLIP model %s loaded on CPU", settings.CLIP_MODEL)
        return _loaded


def label_text(label: dict) -> str:
    """Le texte comparé à l'image : « nom : définition » (ou le seul nom si la définition est vide)."""
    definition = (label.get("definition") or "").strip()
    return f"{label['name']}: {definition}" if definition else label["name"]


def scores(image_bytes: bytes, label_definitions: list[dict]) -> list[float]:
    """Probabilité de chaque label pour la capture (softmax, somme à 1), dans l'ordre des définitions."""
    import torch
    from PIL import Image

    model, processor = _load()
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    inputs = processor(
        text=[label_text(label) for label in label_definitions],
        images=image,
        return_tensors="pt",
        padding=True,
        truncation=True,
    )
    with torch.no_grad():
        logits = model(**inputs).logits_per_image[0]
    return logits.softmax(dim=-1).tolist()


def classify_image(image_bytes: bytes, label_definitions: list[dict], *, multi_label: bool) -> list[LabelPrediction]:
    """Label le plus probable ; en multi-label, tous ceux dont la probabilité atteint
    CLIP_MULTI_LABEL_THRESHOLD (au moins le meilleur). Triés par probabilité décroissante."""
    probabilities = scores(image_bytes, label_definitions)
    ranked = sorted(zip(label_definitions, probabilities, strict=True), key=lambda pair: -pair[1])
    if multi_label:
        kept = [pair for pair in ranked if pair[1] >= settings.CLIP_MULTI_LABEL_THRESHOLD] or ranked[:1]
    else:
        kept = ranked[:1]
    return [LabelPrediction(label_name=label["name"], confidence=min(1.0, probability)) for label, probability in kept]
