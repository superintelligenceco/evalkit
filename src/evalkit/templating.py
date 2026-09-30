"""Minimal ``{{ name }}`` templating used for prompts, grader values, and request bodies."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

_PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z_][\w.]*)\s*\}\}")


class TemplateError(ValueError):
    """Raised when a template references a variable that does not exist."""


def _lookup(context: Mapping[str, Any], dotted: str) -> Any:
    current: Any = context
    for part in dotted.split("."):
        if isinstance(current, Mapping) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            raise TemplateError(f"unknown template variable '{{{{{dotted}}}}}'")
    return current


def _stringify(value: Any) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    if isinstance(value, dict | list):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def render(template: str, context: Mapping[str, Any]) -> str:
    """Replace every ``{{ var }}`` in ``template`` with its value from ``context``.

    Dotted paths such as ``{{ vars.city }}`` walk nested mappings. Dicts and lists
    render as JSON so they can be embedded in prompts verbatim.
    """
    return _PLACEHOLDER.sub(lambda m: _stringify(_lookup(context, m.group(1))), template)


def render_value(value: Any, context: Mapping[str, Any]) -> Any:
    """Render templates inside an arbitrary JSON-like structure.

    A string that consists of exactly one placeholder keeps the type of the value
    it points to, so ``"{{ expected }}"`` can resolve to a number or an object.
    """
    if isinstance(value, str):
        match = _PLACEHOLDER.fullmatch(value.strip())
        if match:
            return _lookup(context, match.group(1))
        return render(value, context)
    if isinstance(value, list):
        return [render_value(item, context) for item in value]
    if isinstance(value, dict):
        return {key: render_value(item, context) for key, item in value.items()}
    return value


def has_placeholders(template: str) -> bool:
    return bool(_PLACEHOLDER.search(template))
