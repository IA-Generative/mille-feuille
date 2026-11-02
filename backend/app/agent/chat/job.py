"""Répondre à un message du chat d'un dossier.

Comme dans Muffin, un premier appel court décide de tout (`planner`), la recherche est du code (`research`) et un second
appel écrit la réponse, en streaming (`answer`). Une question sur le dossier coûte donc deux appels au modèle ; les
demandes d'agir (note, correction de l'analyse, outil externe) et les reprises après une décision passent par la
boucle d'outils (`react`), qui sert aussi de repli quand la recherche ne trouve rien.

    message -> plan -> { direct | clarify | assistant | act -> outils | agent -> l'agent répond |
                         search -> passages -> réponse en streaming }

Le travail se termine toujours par un événement `done` ou `error` : le navigateur ne reste jamais en attente."""

import asyncio
import logging
import uuid
from typing import Any

from app.agent import model_output, usage
from app.agent.agent_tool_set import ExtraTools, build_extra_tools
from app.agent.analysis_agents import load_agents
from app.agent.analysis_reader import AnalysisReader
from app.agent.analysis_tools import AnalysisProposer, proposals_marker
from app.agent.chat import agent_reply, react
from app.agent.chat import history as chat_history
from app.agent.chat.answer import stream_answer
from app.agent.chat.events import ChatEvents
from app.agent.chat.planner import Plan, make_plan
from app.agent.chat.prompts import agent_marker, answer_prompt, assistant_suggestion_marker, build_system_prompt
from app.agent.chat.research import research
from app.agent.documents import load_dossier
from app.agent.knowledge_tools import TOOL_ID as KNOWLEDGE_TOOL_ID
from app.agent.knowledge_tools import KnowledgeContext
from app.agent.note_tools import NoteWriter
from app.agent.runner import settings
from app.agent.tools import AgentTools, NotIndexedError
from app.db import async_session_factory
from app.repositories.analyse_repository import AnalyseRepository
from app.repositories.dossier_note_repository import DossierNoteRepository
from app.schemas.dossier import InternalMessageIn
from app.services.chat_conversation import deposit_assistant_message, load_chat_conversation
from app.services.chat_tool_calls import record_approved_result
from app.services.search.retrieval import DossierSearcher

logger = logging.getLogger(__name__)

# Combien de tours de la conversation le modèle relit pour écrire sa réponse.
ANSWER_HISTORY_MESSAGES = 10


async def _load_conversation(conversation_id: str) -> dict:
    async with async_session_factory() as db:
        conversation = await load_chat_conversation(db, uuid.UUID(conversation_id))
    if conversation is None:
        raise LookupError(f"Conversation {conversation_id} introuvable")
    return conversation.model_dump(mode="json")


async def _load_notes(dossier_id: str) -> list[dict]:
    """Tolérant : sans les notes, le chat répond comme avant."""
    try:
        async with async_session_factory() as db:
            notes = await DossierNoteRepository(db).list(uuid.UUID(dossier_id))
            return [{"content": note.current.content} for note in notes]
    except Exception:
        logger.warning("Notes du dossier %s illisibles", dossier_id, exc_info=True)
        return []


async def _knowledge_context(analyse_id: str | None, tool_ids: list[str]) -> KnowledgeContext | None:
    """Les collections de la base de connaissances de l'analyse, lues seulement si la conversation a l'outil."""
    if KNOWLEDGE_TOOL_ID not in tool_ids or not analyse_id:
        return None
    async with async_session_factory() as db:
        analyse = await AnalyseRepository(db).get(uuid.UUID(analyse_id))
    return KnowledgeContext(analyse_id, list(analyse.knowledge_collections)) if analyse else None


async def _run_approved_calls(conversation: dict, tools: AgentTools, events: ChatEvents) -> None:
    """Exécute les appels que la personne a autorisés, avec les arguments qu'elle a vus, et garde leur résultat. Les
    appels de la conversation sont mis à jour pour que l'historique les porte."""
    for message in conversation.get("messages", []):
        for call in message.get("tool_calls") or []:
            if call["status"] != "approved" or call.get("result"):
                continue
            name = call["function_name"]
            await events.emit("tool_call", {"tool_name": call["tool_name"], "arguments": call["arguments"]})
            result = (
                await tools.dispatch_tool(name, call["arguments"]) if tools.has_extra(name) else chat_history.TOOL_GONE
            )
            async with async_session_factory() as db:
                await record_approved_result(db, uuid.UUID(call["id"]), result)
            await events.emit("tool_result", {"tool_name": call["tool_name"], "preview": result[:200], "full": result})
            call["status"], call["result"] = "executed", result


def _abilities(tools: AgentTools, extra: ExtraTools) -> list[str]:
    """Ce que le chat sait faire avec des outils, pour que le plan reconnaisse une demande d'agir."""
    abilities = []
    if tools.has_analysis:
        abilities.append("corriger ou compléter l'analyse du dossier (propose_update)")
    if tools.can_add_notes:
        abilities.append("ajouter une note interne au dossier (add_note)")
    for definition in extra.definitions():
        function = definition["function"]
        abilities.append(f"{function['name']} : {(function.get('description') or '')[:120]}")
    return abilities


def _overview(tools: AgentTools) -> str:
    """Les classifications et entités déjà établies : peu de texte, souvent la réponse."""
    parts = [text for text in (tools.view_classifications(), tools.view_entities()) if not text.startswith("Aucune")]
    return "\n\n".join(parts)


def _answer_messages(history: list[dict]) -> list[dict]:
    plain = [m for m in history if m["role"] in ("user", "assistant") and not m.get("tool_calls") and m["content"]]
    return plain[-ANSWER_HISTORY_MESSAGES:]


async def _answer_from_search(
    *,
    plan: Plan,
    tools: AgentTools,
    events: ChatEvents,
    speculative: asyncio.Task | None,
    history: list[dict],
    model: str | None,
    syntheses: list[dict],
    notes: list[str],
) -> str | None:
    """La réponse écrite d'un trait à partir des passages trouvés ; None si la recherche ne donne rien (le chat se
    replie alors sur les outils)."""
    for query in plan.queries:
        await events.emit("tool_call", {"tool_name": "search_documents", "arguments": {"query": query}})
    try:
        evidence = await research(tools, plan.queries, plan.pages, speculative)
    except NotIndexedError:
        logger.info("Dossier non indexé : repli sur les outils")
        return None
    except Exception:
        logger.warning("Recherche dans le dossier impossible : repli sur les outils", exc_info=True)
        return None
    preview = evidence.text[:200] + "..." if len(evidence.text) > 200 else evidence.text
    await events.emit("tool_result", {"tool_name": "search_documents", "preview": preview, "full": evidence.text})
    if evidence.empty:
        return None
    system = answer_prompt(evidence=evidence.text, overview=_overview(tools), syntheses=syntheses, notes=notes or None)
    answer = await stream_answer(model=model, system=system, messages=_answer_messages(history), events=events)
    # Rien n'a été écrit : le chat se replie sur les outils plutôt que de déposer des sources sans réponse.
    return answer if answer.strip() else None


async def _respond(
    *,
    conversation: dict,
    dossier: dict,
    tools: AgentTools,
    extra: ExtraTools,
    events: ChatEvents,
    notes: list[str],
) -> tuple[str, AgentTools]:
    """Le texte de la réponse (les marqueurs en plus) et les outils qui ont lu le dossier pour l'écrire (ceux du chat,
    ou ceux de l'agent qui a répondu) : de là viennent les sources du message. Les appels qui attendent la personne
    sont dans `tools.confirmation_batch`."""
    model = conversation.get("model")
    history = chat_history.build_conversation_history(conversation)
    syntheses = chat_history.extract_syntheses(dossier)
    messages = conversation.get("messages", [])

    def tool_loop_prompt() -> str:
        return build_system_prompt(
            history,
            syntheses,
            can_propose_updates=tools.has_analysis,
            notes=notes,
            can_add_notes=tools.can_add_notes,
            tools_notice=tools.extra_notice,
            can_ask_user=tools.can_ask_user,
        )

    async def with_tools() -> str:
        result = await react.run_tool_loop(
            model=model, system_prompt=tool_loop_prompt(), messages=history, tools=tools, events=events
        )
        events.meta["iterations"] = result.iterations
        return result.answer

    events.meta["model"] = model or settings.LLM_MODEL
    # Une décision ou une réponse relance le chat sans nouveau message : le modèle reprend là où il s'était arrêté.
    if messages and messages[-1]["role"] == "assistant" and messages[-1].get("tool_calls"):
        events.meta["mode"] = "resume"
        return await with_tools(), tools

    question = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
    speculative = asyncio.ensure_future(tools.search_hits(question)) if question.strip() else None
    if speculative is not None:
        # Une erreur de la recherche spéculative est sans importance si le plan n'en veut pas.
        speculative.add_done_callback(lambda task: task.cancelled() or task.exception())
    agents = await load_agents(dossier.get("analyse_id"))
    named = agent_reply.mentioned(question, agents)
    if named is not None:
        # Une mention appelle l'agent à coup sûr : pas d'appel au plan.
        plan = Plan("agent", agent=named[0].ref, standalone_query=named[1])
    else:
        candidates = await agent_reply.shortlist(dossier.get("analyse_id"), question, agents)
        plan = await make_plan(
            question=question,
            messages=history,
            dossier=dossier,
            abilities=_abilities(tools, extra),
            model=model,
            agents=agent_reply.agents_for_plan(candidates),
        )
    logger.info("Plan du chat : %s", plan.mode)
    events.meta["mode"] = plan.mode

    answer: str | None = None
    source_tools = tools
    if plan.mode == "direct":
        answer = plan.answer
    elif plan.mode == "clarify":
        answer = react.store_question(tools, plan.questions)
    elif plan.mode == "assistant":
        tools.suggest_assistant(plan.standalone_query)
        answer = plan.answer or "L'assistant de l'application peut s'en charger."
    elif plan.mode == "agent":
        agent = next(agent for agent in agents if agent.ref == plan.agent)
        events.meta["model"] = agent.model or model or settings.LLM_MODEL
        answer, source_tools = await agent_reply.answer_as_agent(
            agent=agent,
            others=[other for other in agents if other.ref != agent.ref],
            dossier=dossier,
            history=history,
            events=events,
            acting_user=conversation.get("user_id", ""),
            conversation_id=conversation["id"],
            knowledge=await _knowledge_context(dossier.get("analyse_id"), agent.tools),
            model=model,
        )
        answer += agent_marker(agent.name)
    elif plan.mode == "search":
        answer = await _answer_from_search(
            plan=plan,
            tools=tools,
            events=events,
            speculative=speculative,
            history=history,
            model=model,
            syntheses=syntheses,
            notes=notes,
        )
    if speculative is not None and not speculative.done():
        speculative.cancel()
    if answer is None:
        if plan.mode == "search":
            events.note("La recherche dans le dossier n'a rien donné : repli sur les outils.")
        answer = await with_tools()

    if not answer.strip():
        logger.warning("Chat: réponse vide, repli sur le message d'excuse")
        answer = model_output.FALLBACK_ANSWER
    assistant_question = tools.assistant_question()
    if assistant_question:
        answer += assistant_suggestion_marker(assistant_question)
    proposals = tools.analysis_proposals()
    if proposals:
        answer += proposals_marker(*proposals)
    return answer, source_tools


async def run_chat(conversation_id: str, dossier_id: str) -> None:
    usage.bind("run_chat", dossier_id=dossier_id)
    events = ChatEvents(conversation_id)
    await events.start()
    try:
        conversation, dossier, note_rows = await asyncio.gather(
            _load_conversation(conversation_id), _load_dossier(dossier_id), _load_notes(dossier_id)
        )
        user_id = conversation.get("user_id", "")
        usage.bind("run_chat", user_id=user_id, dossier_id=dossier_id)
        model = conversation.get("model")
        tool_ids = conversation.get("tool_ids", [])

        proposer = AnalysisProposer(
            dossier_id=dossier_id,
            user_id=user_id,
            model=model or settings.LLM_MODEL,
            source_message_id=chat_history.last_user_message_id(conversation),
        )
        # Les outils que l'analyse autorise (ses agents), moins ceux que la personne a retirés : calculatrice, dates,
        # serveurs MCP, appelés en son nom. Un outil qui modifie des données est donné, mais son appel attend l'accord
        # de la personne (la tâche se termine, la décision relance le chat).
        reader = AnalysisReader(dossier=dossier, analyse_id=dossier.get("analyse_id"), user_id=user_id)
        knowledge, *_ = await asyncio.gather(
            _knowledge_context(dossier.get("analyse_id"), tool_ids), proposer.load(), reader.load()
        )
        extra = await build_extra_tools(
            tool_ids,
            acting_user=user_id,
            run_id=f"chat-{conversation_id}-{uuid.uuid4().hex[:8]}",
            confirm_side_effects=True,
            knowledge=knowledge,
        )
        tools = AgentTools(
            dossier,
            analysis=proposer,
            notes=NoteWriter(dossier_id=dossier_id, user_id=user_id),
            extra=extra,
            ask_user=True,
            searcher=DossierSearcher(dossier_id),
            reader=reader,
        )
        notes = chat_history.notes_for_prompt(note_rows)

        await _run_approved_calls(conversation, tools, events)
        answer, source_tools = await _respond(
            conversation=conversation, dossier=dossier, tools=tools, extra=extra, events=events, notes=notes
        )

        message: dict[str, Any] = {
            "content": answer,
            "sources": chat_history.sources_to_api(source_tools.consulted_sources()),
            "tool_calls": tools.confirmation_batch,
            "external_sources": source_tools.external_sources(),
            "execution": events.execution(),
        }
        async with async_session_factory() as db:
            await deposit_assistant_message(db, uuid.UUID(conversation_id), InternalMessageIn.model_validate(message))
        await events.emit("done", {})
        logger.info("Chat terminé (conversation %s) : %d caractères", conversation_id, len(answer))
    except Exception as error:
        logger.exception("Chat en échec (conversation %s, dossier %s)", conversation_id, dossier_id)
        await events.emit("error", {"message": str(error)})


async def _load_dossier(dossier_id: str) -> dict:
    async with async_session_factory() as db:
        return await load_dossier(db, dossier_id)
