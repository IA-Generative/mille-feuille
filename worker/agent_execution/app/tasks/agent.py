"""Tâche d'exécution des agents LangGraph.

Cette tâche est déposée sur la file agent_execution en même temps que la
classification et l'extraction, mais elle attend que ces deux étapes soient
terminées avant de lancer les agents. Chaque agent reçoit :
- Son prompt (défini dans l'analyse)
- Un socle d'outils (recherche BM25, lecture de page, classifications,
  entités) qui accèdent aux données du dossier, toujours donné
- Les outils choisis pour l'agent : calculatrice, dates, serveurs MCP (appelés
  au nom de la personne qui a lancé l'analyse, par le backend)
- Le modèle LLM configuré pour l'agent (ou le modèle par défaut)

Le résultat de chaque agent est déposé comme output de son execution_step.
Si l'agent a output=True, le résultat est visible dans la page de résultat
du dossier.
"""

import logging
import time
import uuid

from app import api_client, usage
from app.agent_graph import run_agent
from app.agent_tool_set import ExtraTools, build_extra_tools
from app.celery_app import celery_app
from app.tools import AgentTools

logger = logging.getLogger(__name__)

_STATUS_TERMINE = "terminé"
_STATUS_ECHEC = "échec"

_POLL_INTERVAL = 5  # secondes entre chaque vérification
_POLL_TIMEOUT = 600  # 10 minutes max à attendre classification + extraction


def _wait_for_steps(client, dossier: dict, step_kinds: list[str]) -> dict[str, str | None]:
    """Attend que les étapes spécifiées soient terminées (status=terminé ou
    échec). Renvoie un mapping kind -> status. Si une étape est en échec,
    on continue quand même : l'agent peut fonctionner avec des données
    partielles."""
    deadline = time.time() + _POLL_TIMEOUT
    result: dict[str, str | None] = {}

    while time.time() < deadline:
        fresh_dossier = api_client.get_dossier(client, dossier["id"])
        all_done = True
        for step in fresh_dossier.get("execution_steps", []):
            if step["kind"] in step_kinds:
                result[step["kind"]] = step["status"]
                if step["status"] not in (_STATUS_TERMINE, _STATUS_ECHEC):
                    all_done = False
        if all_done:
            return result
        time.sleep(_POLL_INTERVAL)

    logger.warning("Timed out waiting for steps %s after %ds", step_kinds, _POLL_TIMEOUT)
    return result


def _with_notice(prompt: str, extra: ExtraTools) -> str:
    """Le prompt de l'agent, suivi de ce qu'il doit savoir de ses outils (sorties externes, outils absents)."""
    return f"{prompt}\n\n{extra.notice}" if extra.notice else prompt


def _log_missing_tools(client, step_id: str, extra: ExtraTools) -> None:
    """Dit dans le journal de l'étape les outils qui n'ont pas été donnés à l'agent : l'exécution continue sans eux."""
    if extra.skipped:
        message = "Outils ignorés (retirés ou pas encore disponibles) : " + ", ".join(extra.skipped)
        api_client.add_execution_log(client, step_id, level="warning", message=message)
    if extra.unavailable:
        count = len(extra.unavailable)
        message = f"{count} outil(s) MCP non utilisables dans cette exécution (droits, session ou serveur)"
        api_client.add_execution_log(client, step_id, level="warning", message=message)


def _run_single_agent(client, dossier: dict, agent: dict, step_id: str | None, acting_user: str | None = None) -> str:
    """Exécute un agent unique et dépose son résultat sur son execution_step.
    Renvoie la réponse de l'agent."""
    if step_id:
        api_client.add_execution_log(
            client,
            step_id,
            message=f"Agent '{agent['name']}' démarré",
        )

    # Récupère le dossier à jour (avec les prédictions déposées par
    # classification + extraction) pour construire les outils.
    fresh_dossier = api_client.get_dossier(client, dossier["id"])
    run_id = f"agent-{dossier['id']}-{agent.get('id', 'x')}-{uuid.uuid4().hex[:8]}"
    extra = build_extra_tools(client, agent.get("tools", []), acting_user=acting_user, run_id=run_id)
    if step_id:
        _log_missing_tools(client, step_id, extra)
    tools = AgentTools(fresh_dossier, extra=extra)

    answer = run_agent(
        agent_prompt=_with_notice(agent["prompt"], extra),
        tools=tools,
        model=agent.get("model"),
    )

    if step_id:
        api_client.complete_execution_step(client, step_id, status=_STATUS_TERMINE, output=answer)
    logger.info("Agent '%s' completed: %d chars", agent["name"], len(answer))
    return answer


@celery_app.task(name="app.tasks.run_agents", bind=True)
def run_agents(self, dossier_id: str, acting_user: str | None = None) -> None:
    """`acting_user` : la personne qui a lancé l'analyse ; les outils MCP sont appelés en son nom. Absente
    (exécution sans personne), seuls les outils internes sont utilisables."""
    usage.bind("run_agents", dossier_id=dossier_id)
    with api_client.get_client() as client:
        dossier = api_client.get_dossier(client, dossier_id)
        analyse_id = dossier["analyse_id"]

        try:
            definitions = api_client.get_analyse_definitions(client, analyse_id)
            agents = definitions.get("agents", [])

            if not agents:
                logger.info("No agents defined for analyse %s, nothing to run", analyse_id)

            # Attend que la classification et l'extraction soient terminées
            # avant de lancer les agents (les agents utilisent les
            # prédictions déposées par ces étapes). Sans agent, on attend aussi : le
            # résumé du dossier, lancé plus bas, s'appuie sur ces résultats.
            _wait_for_steps(client, dossier, ["classification", "extraction"])

            for agent in agents:
                step_id = _find_step_by_label(dossier, agent["name"])
                # Relance incrémentale (#119) : agent et entrées inchangés, la synthèse
                # de l'exécution précédente est reprise sans appeler le LLM.
                reused_output = api_client.reuse_agent_unit(client, dossier_id, step_id) if step_id else None
                if reused_output is not None:
                    api_client.add_execution_log(
                        client, step_id, message="Synthèse reprise de l'exécution précédente (entrées inchangées)"
                    )
                    api_client.complete_execution_step(client, step_id, status=_STATUS_TERMINE, output=reused_output)
                    logger.info("Agent '%s' reused for dossier %s", agent["name"], dossier_id)
                    continue
                try:
                    _run_single_agent(client, dossier, agent, step_id, acting_user)
                except Exception as agent_error:
                    logger.exception(
                        "Agent '%s' failed for dossier %s",
                        agent["name"],
                        dossier_id,
                    )
                    if step_id:
                        api_client.add_execution_log(
                            client,
                            step_id,
                            level="error",
                            message=str(agent_error),
                        )
                        api_client.complete_execution_step(
                            client,
                            step_id,
                            status=_STATUS_ECHEC,
                            output=str(agent_error),
                        )

        except Exception:
            logger.exception("Agent execution failed for dossier %s", dossier_id)
            raise
        else:
            # Déclenche la génération du résumé global du dossier (issue #52) :
            # tous les agents ont terminé, les synthèses sont disponibles. Aussi pour une
            # analyse sans agent : un `return` dans le `try` sautait ce bloc, et un dossier
            # sans agent n'avait jamais de résumé.
            celery_app.send_task(
                "app.tasks.run_dossier_summary",
                args=[dossier_id],
                queue="agent_execution",
            )


def _find_step_by_label(dossier: dict, label: str) -> str | None:
    """Trouve l'execution_step d'un agent par son label (nom de l'agent).
    Contrairement à classification/extraction qui utilisent kind, les
    agents partagent le même kind='agent' - on les distingue par leur label."""
    for step in dossier.get("execution_steps", []):
        if step["kind"] == "agent" and step["label"] == label:
            return step["id"]
    return None
