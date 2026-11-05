"""Les réponses prêtes aux questions fréquentes d'une analyse, pour un dossier (issue #422).

Calculées à la fin de l'analyse du dossier, en tâche de fond, pour que la conversation les affiche sans appel au modèle.
Chaque question est traitée comme le chat traite une question : recherche dans le dossier, passages numérotés, un
appel qui écrit la réponse — et qui dit d'abord si le dossier permet d'y répondre. Une question sans réponse n'est pas
suggérée.

Une réponse garde l'empreinte de ce qu'elle a lu (pages, éléments de l'analyse, synthèses des agents) : tant qu'elle est
inchangée, la question n'est pas recalculée. `full` distingue la fin d'une analyse (la liste des questions de l'analyse
fait foi : on ajoute, on retire) d'une simple correction (on ne rafraîchit que les réponses existantes) : une question
ajoutée à l'analyse n'apparaît sur un dossier qu'à sa relance."""

import asyncio
import copy
import hashlib
import json
import logging
import uuid

from sqlalchemy import delete, select

from app.agent import llm, model_router, usage
from app.agent.chat.history import extract_syntheses, sources_to_api
from app.agent.chat.prompts import answer_prompt
from app.agent.chat.research import research
from app.agent.documents import load_dossier
from app.agent.tools import AgentTools, NotIndexedError
from app.db import async_session_factory
from app.models.question_answer import DossierQuestionAnswer, QuestionAnswerStatus
from app.models.search_index import DossierSearchIndex, SearchIndexStatus
from app.repositories.analyse_repository import AnalyseRepository
from app.repositories.dossier_analysis_repository import DossierAnalysisRepository
from app.repositories.dossier_repository import DossierRepository
from app.services.search.retrieval import DossierSearcher

logger = logging.getLogger(__name__)

POLL_INTERVAL = 2  # secondes entre deux lectures de l'état de l'index
INDEX_TIMEOUT = 180  # on n'attend pas l'index plus de 3 minutes
DEBOUNCE = 2  # après une correction : quelques corrections de suite ne donnent qu'un recalcul
CONCURRENCY = 4  # questions traitées en même temps pour un dossier
FINAL = (QuestionAnswerStatus.REPONDUE, QuestionAnswerStatus.SANS_REPONSE)

_JSON_INSTRUCTION = (
    '\n\nRéponds uniquement par un objet JSON : {"answerable": true ou false, "answer": "…"}. '
    "`answerable` est false quand les passages ci-dessus ne permettent pas de répondre à la question (`answer` est "
    "alors vide) ; sinon `answer` est la réponse, en markdown, avec ses citations [n]."
)


async def _index_ready(dossier_id: uuid.UUID) -> bool:
    """Attend que l'index de recherche du dossier soit prêt. Faux s'il n'y en a pas (Qdrant absent, échec)."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + INDEX_TIMEOUT
    while True:
        async with async_session_factory() as db:
            index = await db.get(DossierSearchIndex, dossier_id)
        if index is not None and index.status == SearchIndexStatus.READY:
            return True
        if index is not None and index.status == SearchIndexStatus.ERROR:
            return False
        if loop.time() >= deadline:
            return False
        await asyncio.sleep(POLL_INTERVAL)


def _fingerprint(question: str, dossier: dict, elements: list[dict]) -> str:
    """Ce que la réponse a lu : si rien de cela ne change, elle reste juste."""
    pages = [
        [page["id"], hashlib.sha256((page.get("content") or "").encode()).hexdigest()]
        for document in dossier.get("documents", [])
        for page in document.get("pages", [])
    ]
    retained = [
        [element["id"], json.dumps((element.get("retained_version") or {}).get("value"), sort_keys=True)]
        for element in elements
    ]
    syntheses = [[s["label"], s["output"]] for s in extract_syntheses(dossier)]
    payload = json.dumps([question, pages, retained, syntheses], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()[:24]


def _overview(tools: AgentTools) -> str:
    parts = [text for text in (tools.view_classifications(), tools.view_entities()) if not text.startswith("Aucune")]
    return "\n\n".join(parts)


async def _write(row_id: uuid.UUID, **fields: object) -> None:
    async with async_session_factory() as db:
        row = await db.get(DossierQuestionAnswer, row_id)
        if row is not None:
            for name, value in fields.items():
                setattr(row, name, value)
            await db.commit()


async def _compute(question: str, dossier_id: str, dossier: dict, description: str | None) -> tuple[str | None, list]:
    """(réponse, sources), ou (None, []) quand le dossier ne permet pas de répondre."""
    tools = AgentTools(copy.deepcopy(dossier), searcher=DossierSearcher(dossier_id))
    evidence = await research(tools, [question], [])
    if evidence.empty:
        return None, []
    system = (
        answer_prompt(
            evidence=evidence.text,
            overview=_overview(tools),
            syntheses=extract_syntheses(dossier),
            analyse_description=description,
        )
        + _JSON_INSTRUCTION
    )
    response = await llm.complete(
        model=await model_router.for_difficulty(2),
        messages=[{"role": "system", "content": system}, {"role": "user", "content": question}],
        response_format={"type": "json_object"},
        temperature=0,
        max_tokens=1200,
    )
    data = json.loads(response.choices[0].message.content or "{}")
    answer = str(data.get("answer") or "").strip()
    if not data.get("answerable") or not answer:
        return None, []
    return answer, sources_to_api(tools.consulted_sources())


async def _answer_one(
    row: DossierQuestionAnswer,
    dossier_id: str,
    dossier: dict,
    elements: list[dict],
    description: str | None,
    slots: asyncio.Semaphore,
) -> None:
    fingerprint = _fingerprint(row.question, dossier, elements)
    if row.fingerprint == fingerprint and row.status in FINAL:
        return
    async with slots:
        await _write(row.id, status=QuestionAnswerStatus.EN_COURS, error=None)
        try:
            answer, sources = await _compute(row.question, dossier_id, dossier, description)
        except NotIndexedError:
            # L'index a disparu en route : on laisse la ligne telle qu'elle était, la prochaine analyse recommencera.
            await _write(row.id, status=row.status if row.status in FINAL else QuestionAnswerStatus.ECHEC)
            return
        except Exception as error:
            logger.warning("Question %r du dossier %s : réponse impossible", row.question, dossier_id, exc_info=True)
            await _write(row.id, status=QuestionAnswerStatus.ECHEC, error=str(error), fingerprint="")
            return
    if answer is None:
        await _write(
            row.id,
            status=QuestionAnswerStatus.SANS_REPONSE,
            answer=None,
            sources=[],
            fingerprint=fingerprint,
            model=await model_router.for_difficulty(2),
        )
    else:
        await _write(
            row.id,
            status=QuestionAnswerStatus.REPONDUE,
            answer=answer,
            sources=sources,
            fingerprint=fingerprint,
            model=await model_router.for_difficulty(2),
        )


async def _sync_rows(dossier_id: uuid.UUID, questions: list[str], full: bool) -> list[DossierQuestionAnswer]:
    """Les lignes à traiter. `full` : elles suivent la liste de l'analyse (ajout, retrait, ordre) ; sinon on garde
    celles qui existent."""
    async with async_session_factory() as db:
        rows = (
            (await db.execute(select(DossierQuestionAnswer).where(DossierQuestionAnswer.dossier_id == dossier_id)))
            .scalars()
            .all()
        )
        existing = {row.question: row for row in rows}
        if full:
            wanted = set(questions)
            await db.execute(
                delete(DossierQuestionAnswer).where(
                    DossierQuestionAnswer.dossier_id == dossier_id,
                    DossierQuestionAnswer.question.not_in(wanted) if wanted else True,
                )
            )
            for position, question in enumerate(questions):
                row = existing.get(question)
                if row is None:
                    db.add(DossierQuestionAnswer(dossier_id=dossier_id, question=question, position=position))
                else:
                    row.position = position
            await db.commit()
        result = (
            (
                await db.execute(
                    select(DossierQuestionAnswer)
                    .where(DossierQuestionAnswer.dossier_id == dossier_id)
                    .order_by(DossierQuestionAnswer.position)
                )
            )
            .scalars()
            .all()
        )
        for row in result:
            db.expunge(row)
        return list(result)


async def answer_questions(dossier_id: str, full: bool = True) -> None:
    usage.bind("run_question_answers", dossier_id=dossier_id)
    if not full:
        await asyncio.sleep(DEBOUNCE)
    dossier_uuid = uuid.UUID(dossier_id)
    async with async_session_factory() as db:
        dossier_row = await DossierRepository(db).get(dossier_uuid)
        analyse = (
            await AnalyseRepository(db).get(dossier_row.analyse_id) if dossier_row and dossier_row.analyse_id else None
        )
        if analyse is None:
            return
        questions = list(analyse.frequent_questions)
        description = analyse.description or None
    if full:
        if not questions:
            # Plus aucune question : les réponses qui restaient disparaissent avec elles.
            await _sync_rows(dossier_uuid, [], full=True)
            return
        if not await _index_ready(dossier_uuid):
            logger.info("Dossier %s sans index de recherche : questions fréquentes ignorées", dossier_id)
            return
        rows = await _sync_rows(dossier_uuid, questions, full=True)
    else:
        rows = await _sync_rows(dossier_uuid, questions, full=False)
        if not rows or not await _index_ready(dossier_uuid):
            return
    if not rows:
        return
    async with async_session_factory() as db:
        dossier = await load_dossier(db, dossier_id)
        analysis = await DossierAnalysisRepository(db).get_current(dossier_uuid)
        elements = (
            (await DossierAnalysisRepository(db).build_out(analysis)).model_dump(mode="json")["elements"]
            if analysis
            else []
        )
    slots = asyncio.Semaphore(CONCURRENCY)
    await asyncio.gather(*(_answer_one(row, dossier_id, dossier, elements, description, slots) for row in rows))
    logger.info("Questions fréquentes du dossier %s : %d traitée(s)", dossier_id, len(rows))
