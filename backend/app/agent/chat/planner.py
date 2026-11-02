"""Le premier appel du chat : décider, en une fois, de ce qu'il faut faire avant de répondre.

Un seul appel court (JSON), qui remplace les allers-retours du modèle avec ses outils pour une simple question :
répondre tout de suite, poser une question, renvoyer vers l'assistant de l'application, passer aux outils (note,
correction de l'analyse, outil externe) ou chercher dans le dossier — et dans ce cas, quoi chercher. La recherche, elle,
est du code (voir research.py). Si le plan échoue, on cherche avec la question telle quelle : un essai vaut mieux
qu'un blocage."""

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from app.agent import llm
from app.agent.ask_user import normalize_questions
from app.agent.runner import settings

logger = logging.getLogger(__name__)

MODES = ("direct", "clarify", "assistant", "act", "search")
MAX_QUERIES = 3
MAX_PAGES = 3
HISTORY_TURNS = 6
HISTORY_CHARS = 1200

_SYSTEM_PROMPT = (
    "Tu es le planificateur de l'assistant d'un dossier. Lis le dernier message de l'instructeur, à la lumière de la "
    "conversation, et décide ce qui doit se passer avant qu'une réponse soit écrite. Réponds uniquement par un objet "
    'JSON avec la clé "mode", l\'une de :\n'
    '- "direct" : répondre tout de suite, sans le dossier — une salutation, un remerciement, une question sur toi ou '
    'sur ce que tu sais faire. Mets la réponse complète dans "answer", courte et aimable.\n'
    '- "clarify" : la demande est impossible à traiter sans précision, et seulement alors. Donne "questions" : '
    'un tableau d\'objets avec "question", "header", "multi_select" et "options" (tableau d\'objets avec "label" '
    'et "description", 2 à 4). Dans le doute, cherche : un essai vaut mieux que bloquer la personne.\n'
    '- "assistant" : la demande porte sur l\'application elle-même (créer ou configurer une analyse, créer ou '
    "lancer un dossier, retrouver des analyses, comprendre la plateforme) et non sur le contenu du dossier. "
    'Mets dans "answer" une phrase courte, et dans "standalone_query" la demande reformulée pour l\'assistant de '
    "l'application.\n"
    "- \"act\" : la personne demande d'agir : ajouter une note, corriger ou compléter l'analyse du dossier, ou "
    "utiliser un des outils listés ci-dessous. Seulement si le message le demande explicitement.\n"
    '- "search" : tout ce qui demande le contenu du dossier (le cas par défaut).\n\n'
    'Pour "search", donne aussi :\n'
    '- "standalone_query" : le message réécrit pour se suffire à lui-même (résous « il », « elle », « ce document » '
    "avec la conversation) ; inchangé s'il se suffit déjà.\n"
    '- "queries" : 1 à 3 recherches indépendantes, des mots du sujet plutôt que des phrases entières. Une question '
    "simple n'en a qu'une ; plusieurs seulement si elle a vraiment plusieurs volets (une comparaison : une recherche "
    "par côté). Elles s'exécutent en parallèle.\n"
    '- "pages" : les numéros des pages à lire en entier, seulement si le message en désigne (« la page 3 »).'
)


@dataclass
class Plan:
    mode: str = "search"
    answer: str = ""
    questions: list[dict[str, Any]] = field(default_factory=list)
    standalone_query: str = ""
    queries: list[str] = field(default_factory=list)
    pages: list[int] = field(default_factory=list)


def fallback(question: str) -> Plan:
    return Plan(mode="search", standalone_query=question, queries=[question])


def _overview(dossier: dict) -> str:
    lines = [
        f"- {document.get('name', '?')} ({len(document.get('pages', []))} page(s))"
        for document in dossier.get("documents", [])
    ]
    return "\n".join(lines) or "(aucun document)"


def _history(messages: list[dict]) -> str:
    turns = [m for m in messages[:-1] if m.get("role") in ("user", "assistant") and m.get("content")][-HISTORY_TURNS:]
    return "\n".join(f"{m['role']}: {str(m['content'])[:HISTORY_CHARS]}" for m in turns)


def parse(raw: str, question: str) -> Plan:
    """Le plan que le modèle a écrit, ramené à ce qui est exploitable ; à défaut, la recherche de la question."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return fallback(question)
    if not isinstance(data, dict) or data.get("mode") not in MODES:
        return fallback(question)
    mode = data["mode"]
    answer = str(data.get("answer") or "").strip()
    standalone = str(data.get("standalone_query") or "").strip() or question
    if mode == "direct":
        return Plan("direct", answer=answer) if answer else fallback(question)
    if mode == "clarify":
        questions = normalize_questions({"questions": data.get("questions")})
        return Plan("clarify", questions=questions) if questions else fallback(question)
    if mode == "assistant":
        return Plan("assistant", answer=answer, standalone_query=standalone)
    if mode == "act":
        return Plan("act", standalone_query=standalone)
    queries = [q.strip() for q in data.get("queries") or [] if isinstance(q, str) and q.strip()][:MAX_QUERIES]
    pages = [p for p in data.get("pages") or [] if isinstance(p, int) and not isinstance(p, bool)][:MAX_PAGES]
    return Plan("search", standalone_query=standalone, queries=queries or [standalone], pages=pages)


async def make_plan(
    *, question: str, messages: list[dict], dossier: dict, abilities: list[str], model: str | None
) -> Plan:
    """`abilities` : ce que le chat peut faire avec des outils (noter, corriger l'analyse, outils externes)."""
    capabilities = "\n".join(f"- {ability}" for ability in abilities) or "(aucun)"
    user = (
        f"--- Documents du dossier ---\n{_overview(dossier)}\n\n"
        f"--- Outils disponibles pour le mode « act » ---\n{capabilities}\n\n"
        f"--- Conversation ---\n{_history(messages) or '(début de la conversation)'}\n\n"
        f"--- Dernier message ---\n{question}"
    )
    try:
        response = await llm.complete(
            model=settings.CHAT_PLAN_MODEL or model or settings.LLM_MODEL,
            messages=[{"role": "system", "content": _SYSTEM_PROMPT}, {"role": "user", "content": user}],
            response_format={"type": "json_object"},
            temperature=0,
            max_tokens=500,
        )
        return parse(response.choices[0].message.content or "", question)
    except Exception:
        logger.warning("Plan du chat impossible : recherche de la question telle quelle", exc_info=True)
        return fallback(question)
