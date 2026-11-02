"""Les réponses du modèle qu'on ne peut pas montrer telles quelles : vides, ou du JSON écrit en texte. Certains modèles
écrivent leur appel d'outil dans le message au lieu de le passer par l'API (`{"name": ..., "arguments": {...}}`), ou ne
rendent rien après avoir lu des pages : sans garde, la personne voit du JSON, ou des sources sans réponse."""

import json
import re
import uuid
from typing import Any

# Ce que la personne lit quand le modèle n'a rien produit d'exploitable, même après une relance.
FALLBACK_ANSWER = "Je n'ai pas réussi à formuler une réponse. Pouvez-vous reformuler votre question ?"

# La relance, une seule fois par réponse : le modèle reprend là où il s'est arrêté.
RETRY_NOTICE = (
    "Ta réponse précédente n'était pas exploitable (vide ou JSON). Réponds maintenant à la personne par un texte en "
    "français. Si tu as besoin d'un outil, appelle-le par l'interface d'appel d'outils, sans écrire son appel dans ta "
    "réponse."
)

_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)


def _json_of(content: str) -> Any | None:
    text = content.strip()
    fenced = _FENCE.match(text)
    if fenced:
        text = fenced.group(1)
    if not text.startswith(("{", "[")):
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def recovered_call(content: str, tool_names: set[str]) -> dict[str, Any] | None:
    """L'appel d'outil que le modèle a écrit en texte, au format des appels de l'API ; None si ce n'en est pas un. Seul
    un appel qui nomme un outil connu est repris : des arguments seuls ne disent pas quel outil appeler."""
    data = _json_of(content)
    if isinstance(data, dict) and isinstance(data.get("function"), dict):
        data = data["function"]
    if not isinstance(data, dict) or data.get("name") not in tool_names:
        return None
    arguments = data.get("arguments", data.get("parameters", {}))
    if isinstance(arguments, str):
        arguments = _json_of(arguments)
    if not isinstance(arguments, dict):
        return None
    return {
        "id": f"recovered-{uuid.uuid4().hex[:8]}",
        "type": "function",
        "function": {"name": data["name"], "arguments": json.dumps(arguments)},
    }


def unusable(content: str) -> bool:
    """Vide, ou rien qu'un objet ou un tableau JSON : pas une réponse pour la personne."""
    return not content.strip() or _json_of(content) is not None


def shown(content: str) -> str:
    """Le texte à montrer à la personne : la réponse du modèle, ou le repli quand elle est inutilisable."""
    return FALLBACK_ANSWER if unusable(content) else content


def tool_names(definitions: list[dict[str, Any]]) -> set[str]:
    return {definition["function"]["name"] for definition in definitions}


_LEADING_FENCE = re.compile(r"^\s*```[a-zA-Z]*\s*")
_ANSWER_KEY = re.compile(r'"answer"\s*:\s*"')
_JSON_START = re.compile(r'\{\s*"')
_ESCAPES = {'"': '"', "\\": "\\", "/": "/", "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t"}


def visible_answer(raw: str) -> str:
    """Ce qu'on peut montrer de la réponse écrite jusqu'ici, pendant que la suite arrive. Un texte qui ne commence pas
    par `{` se montre tel quel. S'il commence par `{` (le modèle écrit du JSON), on ne montre que le texte du champ
    « answer », décodé jusqu'où il est arrivé : un JSON sans ce champ n'affiche rien. Le texte montré ne fait que
    grandir, pour que le navigateur n'ait qu'à y ajouter la suite."""
    text = _LEADING_FENCE.sub("", raw, count=1)
    if not text.lstrip().startswith("{"):
        return raw
    start = _ANSWER_KEY.search(text)
    if start is None:
        return ""
    out: list[str] = []
    i = start.end()
    while i < len(text):
        char = text[i]
        if char == '"':
            break
        if char != "\\":
            out.append(char)
            i += 1
            continue
        if i + 1 >= len(text):
            break  # un échappement coupé en deux : sa fin n'est pas encore là
        code = text[i + 1]
        if code == "u":
            digits = text[i + 2 : i + 6]
            if len(digits) < 4:
                break
            try:
                out.append(chr(int(digits, 16)))
            except ValueError:
                pass
            i += 6
            continue
        out.append(_ESCAPES.get(code, code))
        i += 2
    return "".join(out)


def final_answer(raw: str) -> str:
    """La réponse écrite en entier : le champ « answer » d'un JSON, le texte tel quel sinon ; vide quand il n'y a rien à
    montrer (rien, ou un JSON sans réponse)."""
    data = _json_of(raw)
    if isinstance(data, dict) and isinstance(data.get("answer"), str):
        return data["answer"]
    if unusable(raw):
        return ""
    if _JSON_START.match(_LEADING_FENCE.sub("", raw, count=1).lstrip()):
        return visible_answer(raw)  # un JSON coupé (limite de longueur) : ce qu'on avait de la réponse
    return raw
