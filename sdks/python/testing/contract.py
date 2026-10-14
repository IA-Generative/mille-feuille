"""Outils de comparaison des modèles pydantic du SDK avec l'OpenAPI du backend."""

from __future__ import annotations

import json
import typing
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel

OPENAPI = json.loads((Path(__file__).resolve().parents[1] / "openapi.json").read_text())
SCHEMAS: dict[str, Any] = OPENAPI["components"]["schemas"]


def _enum_classes(annotation: Any) -> list[type[Enum]]:
    found: list[type[Enum]] = []
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        found.append(annotation)
    for arg in typing.get_args(annotation):
        found.extend(_enum_classes(arg))
    return found


def _enum_refs(prop: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    if "$ref" in prop and "enum" in SCHEMAS[prop["$ref"].split("/")[-1]]:
        refs.append(prop["$ref"].split("/")[-1])
    for key in ("anyOf", "allOf"):
        for sub in prop.get(key, []):
            refs.extend(_enum_refs(sub))
    if "items" in prop:
        refs.extend(_enum_refs(prop["items"]))
    return refs


def check(model: type[BaseModel], schema_name: str) -> list[str]:
    """Renvoie la liste des écarts entre `model` et le schéma `schema_name` du backend."""
    schema = SCHEMAS[schema_name]
    properties: dict[str, Any] = schema["properties"]
    required = set(schema.get("required", []))
    fields = model.model_fields
    problems: list[str] = []
    if missing := set(properties) - set(fields):
        problems.append(f"champs du backend absents du SDK : {sorted(missing)}")
    if extra := set(fields) - set(properties):
        problems.append(f"champs du SDK inconnus du backend : {sorted(extra)}")
    for name in set(properties) & set(fields):
        field = fields[name]
        if field.is_required() != (name in required):
            problems.append(
                f"{name} : obligatoire={name in required} côté backend, {field.is_required()} côté SDK"
            )
        backend_enums = sorted(_enum_refs(properties[name]))
        sdk_enums = _enum_classes(field.annotation)
        if len(backend_enums) != len(sdk_enums):
            problems.append(
                f"{name} : enum backend {backend_enums} vs SDK {[e.__name__ for e in sdk_enums]}"
            )
            continue
        for ref, enum_cls in zip(
            backend_enums, sorted(sdk_enums, key=lambda e: e.__name__), strict=False
        ):
            if [m.value for m in enum_cls] != SCHEMAS[ref]["enum"]:
                problems.append(
                    f"{name} : valeurs {[m.value for m in enum_cls]} != {SCHEMAS[ref]['enum']}"
                )
    return problems


def example(schema_name: str, **overrides: Any) -> dict[str, Any]:
    """Construit une réponse JSON valide d'après le schéma OpenAPI du backend (pas écrite à la main)."""
    value = _build({"$ref": f"#/components/schemas/{schema_name}"}, depth=0)
    assert isinstance(value, dict)
    value.update(overrides)
    return value


def _build(prop: dict[str, Any], depth: int) -> Any:
    if "$ref" in prop:
        return _build(SCHEMAS[prop["$ref"].split("/")[-1]], depth)
    if "enum" in prop:
        return prop["enum"][0]
    if "anyOf" in prop:
        non_null = [p for p in prop["anyOf"] if p.get("type") != "null"]
        return _build(non_null[0], depth)
    kind = prop.get("type")
    if kind == "object":
        if "properties" not in prop:
            return {}
        return {name: _build(p, depth + 1) for name, p in prop["properties"].items()}
    if kind == "array":
        return [_build(prop["items"], depth + 1)] if depth < 12 else []
    if kind == "string":
        return {
            "uuid": "3f2b8c1e-5d4a-4e6b-9a7c-1d2e3f4a5b6c",
            "date-time": "2026-09-30T10:00:00Z",
            "date": "2026-09-30",
        }.get(prop.get("format", ""), "texte")
    if kind == "integer":
        return 1
    if kind == "number":
        return 0.5
    if kind == "boolean":
        return True
    if kind is None and not {"properties", "items", "enum", "anyOf", "$ref"} & set(
        prop
    ):
        # Propriété sans type (`Any` côté backend, ex. la valeur par défaut d'une colonne) : n'importe quel JSON convient.
        return "texte"
    raise AssertionError(f"type OpenAPI non géré : {prop}")
