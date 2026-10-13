"""Tâche d'extraction d'entités nommées.

Stratégie : regrouper les pages par batch (EXTRACTION_BATCH_SIZE, défaut 5)
pour optimiser le contexte et le coût. Pour chaque batch :
1. Envoyer le texte de toutes les pages au LLM avec les définitions
   d'entités et le prompt d'extraction.
2. Le LLM renvoie un structured output (ExtractionResult) listant les
   entités trouvées, avec pour chacune les numéros de pages où elle
   apparaît.
3. Déposer chaque entité comme une prédiction (kind=ENTITY) sur la
   première page où elle apparaît, en référençant toutes les pages
   concernées via page_ids.

Une entité qui s'étend sur plusieurs pages n'est déposée qu'une fois (sur
la première page), avec page_ids pointant vers toutes les pages où elle
apparaît - cohérent avec le modèle DocumentPrediction qui supporte les
entités multi-pages.
"""

import logging
from functools import partial

from app import api_client, gliner, llm
from app.celery_app import celery_app
from app.config import settings
from app.extraction_planner import group_definitions, new_entities, normalize_value, plan_lots, text_budget
from app.fingerprint import extraction_fingerprint, gliner_extraction_fingerprint

logger = logging.getLogger(__name__)

_STATUS_TERMINE = "terminé"
_STATUS_ECHEC = "échec"


def _find_step_id(dossier: dict, kind: str) -> str | None:
    for step in dossier.get("execution_steps", []):
        if step["kind"] == kind:
            return step["id"]
    return None


def _collect_pages(dossier: dict) -> tuple[list[dict], dict[int, str]]:
    """Collecte toutes les pages de tous les documents. Renvoie la liste des
    pages (avec page_number, content, id) et un mapping page_number -> id."""
    all_pages: list[dict] = []
    page_id_by_number: dict[int, str] = {}
    for document in dossier["documents"]:
        for page in document["pages"]:
            page_number = page["page_number"]
            all_pages.append(
                {
                    "page_number": page_number,
                    "content": page.get("content") or "",
                    "id": page["id"],
                }
            )
            page_id_by_number[page_number] = page["id"]
    return all_pages, page_id_by_number


def _deposit_entity(
    client,
    entity_value,
    entity_def_by_name: dict,
    page_id_by_number: dict,
    batch_page_numbers: set,
    unit_id: str | None = None,
) -> bool:
    """Dépose une entité extraite comme prédiction. Renvoie True si le dépôt
    a réussi, False si l'entité n'est pas dans les définitions."""
    entity_def = entity_def_by_name.get(entity_value.entity_name)
    if entity_def is None:
        logger.warning("Entity '%s' not in definitions, skipping", entity_value.entity_name)
        return False

    entity_page_numbers = [pn for pn in entity_value.page_numbers if pn in batch_page_numbers]
    if not entity_page_numbers:
        entity_page_numbers = [min(batch_page_numbers)]

    first_page_id = page_id_by_number[entity_page_numbers[0]]
    all_page_ids = [page_id_by_number[pn] for pn in entity_page_numbers]

    api_client.add_prediction(
        client,
        first_page_id,
        kind="entity",
        name=entity_value.entity_name,
        value=entity_value.value,
        confidence=entity_value.confidence,
        entity_definition_id=entity_def["id"],
        page_ids=all_page_ids,
        unit_id=unit_id,
    )
    logger.info(
        "Entity '%s' = '%s' (confidence=%.2f, pages=%s)",
        entity_value.entity_name,
        entity_value.value,
        entity_value.confidence,
        entity_page_numbers,
    )
    return True


def _process_batch(
    client,
    batch: list[dict],
    entity_defs: list[dict],
    entity_def_by_name: dict,
    extraction_prompt: str,
    page_id_by_number: dict,
    unit_id: str | None = None,
    seen: set[tuple[str, str]] | None = None,
) -> int:
    """Traite un batch de pages : extraction LLM + dépôt des entités.
    Renvoie le nombre d'entités déposées. ``seen`` (mode par document) écarte
    les entités déjà extraites par un lot précédent du même document et du
    même groupe de définitions (recouvrement entre lots)."""
    batch_page_numbers = {p["page_number"] for p in batch}

    result = llm.extract_entities_batch(
        pages=[{"page_number": p["page_number"], "content": p["content"]} for p in batch],
        entity_definitions=entity_defs,
        extraction_prompt=extraction_prompt,
    )

    entities = [e for e in result.entities if e.entity_name in entity_def_by_name]
    if seen is not None:
        entities = new_entities(entities, seen)

    count = 0
    for entity_value in entities:
        if _deposit_entity(
            client,
            entity_value,
            entity_def_by_name,
            page_id_by_number,
            batch_page_numbers,
            unit_id,
        ):
            count += 1
    return count


def _page_dicts(document: dict) -> tuple[list[dict], dict[int, str]]:
    """Pages d'un document (page_number, content, id) et mapping page_number -> id.
    Les numéros de page sont propres à chaque document : le mapping aussi."""
    pages = [
        {"page_number": page["page_number"], "content": page.get("content") or "", "id": page["id"]}
        for page in document.get("pages", [])
    ]
    return pages, {page["page_number"]: page["id"] for page in pages}


def _run_unit(
    client,
    dossier_id: str,
    description: dict,
    fingerprint: str,
    work,
    on_reused=None,
) -> int:
    """Déclare une unité, exécute le travail, la marque terminée ou en échec
    (l'erreur remonte comme avant). Une unité **reprise** de l'analyse précédente
    (même empreinte, #119) n'est pas calculée : ses éléments sont déjà copiés."""
    unit = api_client.declare_unit(client, dossier_id, "extraction", description, fingerprint=fingerprint)
    if unit is not None and unit.reused:
        if on_reused is not None:
            on_reused(unit.entities)
        return 0
    unit_id = unit.id if unit else None
    try:
        count = work(unit_id)
    except Exception:
        api_client.complete_unit(client, unit_id, _STATUS_ECHEC)
        raise
    api_client.complete_unit(client, unit_id, _STATUS_TERMINE)
    return count


def _seed_seen(seen: set[tuple[str, str]], entities: list[tuple[str, str]]) -> None:
    """Une unité reprise n'est pas recalculée : ses entités amorcent la fusion des
    doublons pour les lots suivants du même document et du même groupe."""
    seen.update((name, normalize_value(value)) for name, value in entities)


def _extract_legacy(
    client,
    dossier_id: str,
    all_pages: list[dict],
    page_id_by_number: dict,
    entity_defs: list[dict],
    extraction_prompt: str,
) -> int:
    """Ancien découpage (EXTRACTION_MODE=legacy) : lots de EXTRACTION_BATCH_SIZE
    pages sur tout le dossier, toutes les définitions dans un seul appel. Une
    unité par lot, avec son empreinte."""
    entity_def_by_name = {entity["name"]: entity for entity in entity_defs}
    batch_size = settings.EXTRACTION_BATCH_SIZE
    total = 0
    for i in range(0, len(all_pages), batch_size):
        batch = all_pages[i : i + batch_size]
        total += _run_unit(
            client,
            dossier_id,
            {"page_numbers": [p["page_number"] for p in batch], "page_ids": [p["id"] for p in batch]},
            extraction_fingerprint(batch, entity_defs, extraction_prompt),
            lambda unit_id, batch=batch: _process_batch(
                client, batch, entity_defs, entity_def_by_name, extraction_prompt, page_id_by_number, unit_id
            ),
        )
    return total


def _extract_by_document(
    client, dossier_id: str, dossier: dict, entity_defs: list[dict], extraction_prompt: str
) -> int:
    """Découpage par document (issue #126) : pour chaque document, chaque groupe
    de définitions et chaque lot de pages (défini par un budget de jetons, avec
    recouvrement), un appel au LLM = une unité de calcul avec son empreinte.
    Aucun lot ne chevauche deux documents."""
    groups = group_definitions(entity_defs, settings.EXTRACTION_DEFINITIONS_PER_GROUP)
    total = 0
    for document in dossier["documents"]:
        pages, page_id_by_number = _page_dicts(document)
        if not pages:
            continue
        for group_index, group in enumerate(groups):
            group_by_name = {entity["name"]: entity for entity in group}
            budget = text_budget(
                max_tokens=settings.EXTRACTION_MAX_TOKENS,
                reserved_output_tokens=settings.EXTRACTION_RESERVED_OUTPUT_TOKENS,
                prompt=extraction_prompt,
                definitions=group,
            )
            seen: set[tuple[str, str]] = set()
            for lot in plan_lots(pages, budget=budget, overlap=settings.EXTRACTION_OVERLAP_PAGES):
                total += _run_unit(
                    client,
                    dossier_id,
                    {
                        "document_id": document["id"],
                        "page_numbers": [p["page_number"] for p in lot],
                        "page_ids": [p["id"] for p in lot],
                        "group": group_index,
                        "definition_ids": [entity["id"] for entity in group],
                    },
                    extraction_fingerprint(lot, group, extraction_prompt),
                    partial(
                        _process_batch,
                        client,
                        lot,
                        group,
                        group_by_name,
                        extraction_prompt,
                        page_id_by_number,
                        seen=seen,
                    ),
                    on_reused=partial(_seed_seen, seen),
                )
    return total


def _gliner_entities(pages: list[dict], entity_defs: list[dict]) -> dict[tuple[str, str], dict]:
    """Passe chaque page dans GLiNER et fusionne les doublons du document : une même valeur trouvée sur plusieurs
    pages est une seule entité, qui couvre ces pages (comme une entité multi-pages du LLM). Clé : (définition, valeur
    normalisée) ; valeur : valeur lue, meilleure confiance et numéros de page."""
    merged: dict[tuple[str, str], dict] = {}
    for page in pages:
        for name, value, confidence in gliner.extract(page["content"], entity_defs):
            entity = merged.setdefault(
                (name, normalize_value(value)), {"name": name, "value": value, "confidence": confidence, "pages": []}
            )
            entity["confidence"] = max(entity["confidence"], confidence)
            if page["page_number"] not in entity["pages"]:
                entity["pages"].append(page["page_number"])
    return merged


def _process_gliner_document(
    client, pages: list[dict], page_id_by_number: dict, entity_defs: list[dict], unit_id: str | None
) -> int:
    """Extrait les entités d'un document avec GLiNER et les dépose (source=gliner), chacune sur la première page où
    elle apparaît et en référençant toutes ses pages. Renvoie le nombre d'entités déposées."""
    by_name = {entity["name"]: entity for entity in entity_defs}
    count = 0
    for entity in _gliner_entities(pages, entity_defs).values():
        numbers = sorted(entity["pages"])
        api_client.add_prediction(
            client,
            page_id_by_number[numbers[0]],
            kind="entity",
            name=entity["name"],
            value=entity["value"],
            confidence=entity["confidence"],
            source="gliner",
            entity_definition_id=by_name[entity["name"]]["id"],
            page_ids=[page_id_by_number[n] for n in numbers],
            unit_id=unit_id,
        )
        logger.info(
            "GLiNER entity '%s' = '%s' (confidence=%.2f, pages=%s)",
            entity["name"],
            entity["value"],
            entity["confidence"],
            numbers,
        )
        count += 1
    return count


def _extract_with_gliner(client, dossier_id: str, dossier: dict, entity_defs: list[dict]) -> tuple[int, int]:
    """Extraction GLiNER de chaque document, une unité de calcul par document (avec son empreinte). C'est un
    complément du LLM : un échec sur un document est journalisé et ne fait pas échouer l'étape. Renvoie
    (entités déposées, documents en échec)."""
    defs = gliner.supported(entity_defs)
    if not defs:
        return 0, 0
    total = failed = 0
    for document in dossier["documents"]:
        pages, page_id_by_number = _page_dicts(document)
        if not pages:
            continue
        try:
            total += _run_unit(
                client,
                dossier_id,
                {"document_id": document["id"], "page_ids": [p["id"] for p in pages], "source": "gliner"},
                gliner_extraction_fingerprint(pages, defs),
                partial(_process_gliner_document, client, pages, page_id_by_number, defs),
            )
        except Exception:
            logger.warning("GLiNER extraction failed for document %s", document["id"], exc_info=True)
            failed += 1
    return total, failed


@celery_app.task(name="app.tasks.extract_dossier_entities", bind=True)
def extract_dossier_entities(self, dossier_id: str) -> None:
    with api_client.get_client() as client:
        dossier = api_client.get_dossier(client, dossier_id)
        analyse_id = dossier["analyse_id"]

        step_id = _find_step_id(dossier, "extraction")
        if step_id:
            api_client.add_execution_log(client, step_id, message="Extraction d'entités démarrée")

        try:
            definitions = api_client.get_analyse_definitions(client, analyse_id)
            entity_defs = definitions["extraction"]["entities"]
            extraction_prompt = definitions["extraction"]["prompt"]

            if not entity_defs:
                logger.warning(
                    "No entity definitions for analyse %s, skipping extraction",
                    analyse_id,
                )
                if step_id:
                    api_client.complete_execution_step(
                        client,
                        step_id,
                        status=_STATUS_TERMINE,
                        output="Aucune entité définie",
                    )
                return

            all_pages, page_id_by_number = _collect_pages(dossier)

            if not all_pages:
                if step_id:
                    api_client.complete_execution_step(
                        client,
                        step_id,
                        status=_STATUS_TERMINE,
                        output="Aucune page à traiter",
                    )
                return

            if settings.EXTRACTION_MODE == "legacy":
                total_entities = _extract_legacy(
                    client, dossier_id, all_pages, page_id_by_number, entity_defs, extraction_prompt
                )
            else:
                total_entities = _extract_by_document(client, dossier_id, dossier, entity_defs, extraction_prompt)

            output = f"{total_entities} entité(s) extraite(s) sur {len(all_pages)} page(s)"
            if settings.GLINER_ENABLED:
                gliner_entities, gliner_failed = _extract_with_gliner(client, dossier_id, dossier, entity_defs)
                output += f", {gliner_entities} par GLiNER"
                if gliner_failed:
                    output += f" ({gliner_failed} document(s) en échec)"
            if step_id:
                api_client.complete_execution_step(client, step_id, status=_STATUS_TERMINE, output=output)
            logger.info("Extraction complete for dossier %s: %s", dossier_id, output)

        except Exception as error:
            logger.exception("Extraction failed for dossier %s", dossier_id)
            if step_id:
                api_client.add_execution_log(client, step_id, level="error", message=str(error))
                api_client.complete_execution_step(client, step_id, status=_STATUS_ECHEC, output=str(error))
            raise
