"""Outil du chat pour poser une question à choix à la personne (plutôt que deviner).

Comme la confirmation d'un outil, la question n'attend pas : elle est enregistrée avec le message de l'assistant, la
tâche se termine, et la réponse de la personne devient le résultat de l'appel à la relance. Réservé au chat : un agent
d'analyse tourne sans personne.

Les arguments du modèle sont **nettoyés** avant d'être montrés : ce qui n'est pas exploitable (moins de 2 options, texte
vide) est écarté, et sans question valable l'outil répond au modèle plutôt que d'interrompre la discussion."""

from typing import Any

ASK_USER = "ask_user"
MAX_QUESTIONS = 4  # le plafond du backend (schemas/chat_tool_call.py)
MIN_OPTIONS = 2
MAX_OPTIONS = 4
MAX_TEXT = 300

INVALID = (
    "La question n'a pas pu être posée : donne 1 à 4 questions, chacune avec un intitulé et 2 à 4 options "
    "(libellé + description courte). Corrige l'appel ou continue sans poser de question."
)

DEFINITION: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": ASK_USER,
        "description": (
            "Pose une ou plusieurs questions à choix à la personne quand une précision change vraiment le résultat "
            "et ne se trouve pas dans le dossier. La personne peut toujours répondre par un texte libre. "
            "Après l'appel, n'écris rien de plus : sa réponse te sera donnée."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "questions": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": MAX_QUESTIONS,
                    "items": {
                        "type": "object",
                        "properties": {
                            "question": {
                                "type": "string",
                                "description": "La question, complète, qui finit par « ? ».",
                            },
                            "header": {
                                "type": "string",
                                "description": "Un mot ou deux pour l'onglet (12 caractères).",
                            },
                            "multi_select": {
                                "type": "boolean",
                                "description": "Vrai si plusieurs options peuvent être choisies ensemble.",
                            },
                            "options": {
                                "type": "array",
                                "minItems": MIN_OPTIONS,
                                "maxItems": MAX_OPTIONS,
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "label": {"type": "string", "description": "Le choix, en quelques mots."},
                                        "description": {"type": "string", "description": "Ce que ce choix implique."},
                                    },
                                    "required": ["label"],
                                },
                            },
                        },
                        "required": ["question", "options"],
                    },
                }
            },
            "required": ["questions"],
        },
    },
}


def _text(value: Any, limit: int = MAX_TEXT) -> str:
    return " ".join(value.split())[:limit] if isinstance(value, str) else ""


def normalize_questions(arguments: dict[str, Any]) -> list[dict[str, Any]]:
    """Les questions exploitables, au format que le backend enregistre ; vide si aucune ne l'est."""
    questions: list[dict[str, Any]] = []
    raw_questions = arguments.get("questions")
    for raw in (raw_questions if isinstance(raw_questions, list) else [])[:MAX_QUESTIONS]:
        if not isinstance(raw, dict) or not _text(raw.get("question")):
            continue
        options: list[dict[str, str]] = []
        for option in raw.get("options") if isinstance(raw.get("options"), list) else []:
            label = _text(option.get("label") if isinstance(option, dict) else option, 100)
            if label and label not in {kept["label"] for kept in options}:
                options.append(
                    {
                        "label": label,
                        "description": _text(option.get("description")) if isinstance(option, dict) else "",
                    }
                )
        if len(options) < MIN_OPTIONS:
            continue
        questions.append(
            {
                "question": _text(raw["question"]),
                "header": _text(raw.get("header"), 12),
                "multi_select": raw.get("multi_select") is True,
                "options": options[:MAX_OPTIONS],
            }
        )
    return questions
