"""Optional post-processing helpers for API responses."""
from __future__ import annotations

import re
from typing import Any, Tuple

from backend.models import APICall, APIDefinition


def _extract_prefix_from_message(message: str) -> str | None:
    pattern = re.compile(
        r"(?:start|starting|begin|beginning)[^a-zA-Z]+(?:with\s+)?(?:the\s+)?(?:letter\s+)?['\"]?([A-Za-z]{1,20})",
        re.IGNORECASE,
    )
    match = pattern.search(message)
    if match:
        return match.group(1)
    return None


def _extract_prefix_from_query(query: dict[str, Any]) -> str | None:
    candidate = query.get("name") or query.get("country")
    if isinstance(candidate, str):
        cleaned = candidate.strip().rstrip("*%")
        if cleaned:
            return cleaned
    return None


def _filter_countries_by_prefix(items: Any, prefix: str) -> Any:
    if not isinstance(items, list):
        return items

    prefix_norm = prefix.lower()
    filtered = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name_data = item.get("name")
        if isinstance(name_data, dict):
            name_val = name_data.get("common") or name_data.get("official")
        else:
            name_val = item.get("name") if isinstance(item.get("name"), str) else None
        if isinstance(name_val, str) and name_val.lower().startswith(prefix_norm):
            filtered.append(item)

    return filtered if filtered else items


def apply_post_processing(
    api_def: APIDefinition, call: APICall, user_message: str, response_json: Any
) -> Tuple[Any, str | None]:
    """Apply per-API client-side fixes that the LLM cannot express directly."""

    notes = []
    updated_json = response_json

    if api_def.name.lower() == "restcountries":
        prefix = _extract_prefix_from_query(call.query) or _extract_prefix_from_message(user_message)
        if prefix:
            filtered = _filter_countries_by_prefix(response_json, prefix)
            if filtered is not response_json:
                notes.append(f"Client-side filter applied for country names starting with '{prefix}'.")
            updated_json = filtered

    extra_note = " ".join(notes) if notes else None
    return updated_json, extra_note
