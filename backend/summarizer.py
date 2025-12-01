"""Helpers for ranking API responses and summarizing with LLM."""
from __future__ import annotations

import json
import math
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

from fastapi import HTTPException

from backend.ollama_client import chat_with_ollama
from backend.prompts import ERROR_SUMMARY_PROMPT, SUMMARIZER_PROMPT


def _as_number(value: Any) -> Optional[float]:
    try:
        if isinstance(value, (int, float)):
            if math.isnan(value):  # type: ignore[arg-type]
                return None
            return float(value)
        if isinstance(value, str):
            cleaned = value.replace(",", "").strip()
            return float(cleaned)
    except (ValueError, TypeError):
        return None
    return None


def _as_date(value: Any) -> Optional[datetime]:
    if not isinstance(value, str):
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m", "%Y"):
        try:
            return datetime.strptime(value[: len(fmt)], fmt)
        except ValueError:
            continue
    return None


def _get_list_from_response(response_json: Any) -> List[Any]:
    if isinstance(response_json, list):
        return response_json
    if isinstance(response_json, dict):
        for key in ("results", "data", "list", "items"):
            items = response_json.get(key)
            if isinstance(items, list):
                return items
    return []


def _infer_domain(context: Dict[str, Any]) -> str:
    text = f"{context.get('user_query', '')} {context.get('api_name', '')}".lower()
    if any(word in text for word in ["movie", "film", "tmdb", "tv"]):
        return "movies"
    if any(word in text for word in ["coin", "stock", "finance", "crypto", "market"]):
        return "finance"
    if any(word in text for word in ["weather", "forecast", "temperature", "rain"]):
        return "weather"
    return "generic"


def _item_name(item: Dict[str, Any]) -> str:
    for key in ("title", "name", "id", "symbol"):
        if key in item and item[key]:
            return str(item[key])
    return "item"


def _sort_candidates_for_domain(domain: str) -> List[Tuple[List[str], bool]]:
    if domain == "movies":
        return [(["vote_average", "rating"], True), (["popularity"], True), (["release_date", "first_air_date"], True)]
    if domain == "finance":
        return [(["market_cap", "marketCap"], True), (["current_price", "regularMarketPrice", "price"], True), (["price_change_24h"], True)]
    if domain == "weather":
        return [(["temp", "temperature"], True), (["humidity"], True)]
    return [(["score", "rank", "popularity"], True)]


def _choose_sort_key(items: List[Dict[str, Any]], domain: str) -> Tuple[Optional[str], bool]:
    for keys, desc in _sort_candidates_for_domain(domain):
        for key in keys:
            if any(key in item for item in items):
                return key, desc
    return None, True


def _collect_metric(items: Iterable[Dict[str, Any]], key: str, reverse: bool = True) -> Optional[Dict[str, Any]]:
    scored: List[Tuple[float, Dict[str, Any]]] = []
    for item in items:
        val = _as_number(item.get(key))
        if val is None:
            continue
        scored.append((val, item))
    if not scored:
        return None
    scored.sort(key=lambda pair: pair[0], reverse=reverse)
    return scored[0][1]


def _collect_date_metric(items: Iterable[Dict[str, Any]], key: str) -> Optional[Dict[str, Any]]:
    scored: List[Tuple[datetime, Dict[str, Any]]] = []
    for item in items:
        date_val = _as_date(item.get(key))
        if date_val:
            scored.append((date_val, item))
    if not scored:
        return None
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return scored[0][1]


def extract_relevant_items(response_json: Any, context: Dict[str, Any]) -> Dict[str, Any]:
    """Heuristically rank list payloads to help the LLM summarizer and UI."""

    items_raw = _get_list_from_response(response_json)
    items = [item for item in items_raw if isinstance(item, dict)]
    domain = _infer_domain(context)

    insights: Dict[str, Any] = {"domain": domain, "item_count": len(items_raw)}
    if not items:
        return {**insights, "top_items": []}

    sort_key, descending = _choose_sort_key(items, domain)
    if sort_key:
        sortable: List[Tuple[float, Dict[str, Any]]] = []
        for item in items:
            val = _as_number(item.get(sort_key))
            if val is None:
                continue
            sortable.append((val, item))
        if sortable:
            sortable.sort(key=lambda pair: pair[0], reverse=descending)
            insights["top_items"] = [
                {
                    "rank": idx + 1,
                    "name": _item_name(item),
                    "score_key": sort_key,
                    "score": score,
                    "metadata": {
                        k: v
                        for k, v in item.items()
                        if k in {sort_key, "vote_count", "popularity", "release_date", "first_air_date", "market_cap", "current_price", "regularMarketPrice", "symbol", "id", "title", "name", "overview"}
                    },
                }
                for idx, (score, item) in enumerate(sortable[:5])
            ]
    else:
        insights["top_items"] = []

    # Additional metrics
    metrics: Dict[str, Any] = {}
    metrics_keys = {
        "top_by_rating": ("vote_average", True),
        "top_by_popularity": ("popularity", True),
        "lowest_price": ("current_price", False),
        "highest_market_cap": ("market_cap", True),
    }
    for label, (key, reverse) in metrics_keys.items():
        best = _collect_metric(items, key, reverse=reverse)
        if best:
            metrics[label] = {"name": _item_name(best), "value": best.get(key), "raw": best}

    recent = None
    for key in ("release_date", "first_air_date", "date", "timestamp"):
        recent = _collect_date_metric(items, key)
        if recent:
            metrics["most_recent"] = {"name": _item_name(recent), "value": recent.get(key), "raw": recent}
            break

    if metrics:
        insights["metrics"] = metrics

    return insights


def _format_reasoning(reasoning_val: Any) -> Optional[str]:
    """Normalize the reasoning field from LLM output into display-ready text."""

    if reasoning_val is None:
        return None

    def _as_lines(val: Any) -> List[str]:
        if val is None:
            return []
        if isinstance(val, list):
            return [str(item).strip() for item in val if str(item).strip()]
        if isinstance(val, str):
            stripped = val.strip()
            return [stripped] if stripped else []
        return [str(val).strip()]

    if isinstance(reasoning_val, dict):
        ordered_keys = [
            ("Steps", "steps"),
            ("Checks", "checks"),
            ("Assumptions", "assumptions"),
            ("Follow-ups", "followups"),
            ("Notes", "notes"),
        ]
        lines: List[str] = []
        for label, key in ordered_keys:
            section_lines = _as_lines(reasoning_val.get(key))
            if section_lines:
                lines.append(f"{label}:")
                lines.extend(f"• {line}" for line in section_lines)
        if lines:
            return "\n".join(lines)

    lines = _as_lines(reasoning_val)
    if not lines:
        return None
    return "\n".join(f"• {line}" for line in lines)


def _format_answer(answer: Any) -> str:
    """Turn the parsed LLM answer into a concise, human-friendly string.

    The summarizer prompt encourages JSON output; when that JSON is a
    structured object (e.g., {"countries": [...]}) we want to present a clear
    textual summary instead of a Python dict repr.
    """

    def _format_list(items: List[Any], label: str) -> str:
        names: List[str] = []
        for item in items:
            if isinstance(item, dict):
                name = item.get("name") or item.get("title") or item.get("id")
                code = item.get("cca2") or item.get("symbol") or item.get("code")
                if name:
                    names.append(f"{name}{f' ({code})' if code else ''}")
                    continue
            names.append(str(item))
        shown = names[:20]
        more = "" if len(names) <= 20 else f" … +{len(names) - 20} more"
        return f"{label}: {', '.join(shown)}{more}" if shown else label

    if answer is None:
        return "No summary returned by the model."
    if isinstance(answer, str):
        return answer
    if isinstance(answer, list):
        return _format_list(answer, "Items")
    if isinstance(answer, dict):
        # Special-case common list-bearing keys so the UI shows helpful text.
        for key in ("countries", "items", "results", "data"):
            if isinstance(answer.get(key), list):
                return _format_list(answer[key], key.capitalize())
        # Fallback to JSON for any other structured answer.
        return json.dumps(answer, ensure_ascii=False)
    return str(answer)


def _load_summary_payload(text: str) -> Dict[str, Any]:
    """Best-effort JSON loader for summarizer output."""

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        candidate = text[start : end + 1]
        return json.loads(candidate)


def summarize_results(
    response_json: Any,
    user_message: str,
    api_name: str,
    notes: Optional[str],
    extracted: Dict[str, Any],
    verbose: bool,
) -> Tuple[str, Optional[str]]:
    """Call the LLM to turn JSON into a human-friendly summary."""

    serialized = json.dumps(response_json, ensure_ascii=False, default=str)
    truncated = serialized[:6000]
    context_blob = json.dumps(extracted, ensure_ascii=False, default=str)
    verbosity_hint = (
        "Offer explicit, step-by-step reasoning tied to the data before the final answer."
        if verbose
        else "Keep it concise but informative."
    )

    message = (
        "User query: "
        f"{user_message}\n"
        f"API: {api_name}\n"
        f"Model notes: {notes or 'n/a'}\n"
        f"Heuristic highlights: {context_blob}\n"
        f"Raw JSON (truncated to 6000 chars if needed): {truncated}"
    )
    try:
        llm_output = chat_with_ollama(
            message=message,
            system_prompt=(
                f"{SUMMARIZER_PROMPT}\n"
                "Respond ONLY with JSON containing 'reasoning' (a list, string, or an object with 'steps', 'checks', and 'followups')"
                " and 'answer' (string). Keep the reasoning terse, as if you are talking to yourself.\n"
                f"{verbosity_hint}"
            ),
        )
    except HTTPException:
        # If summarization fails, fall back to a simple string representation
        return "Summary unavailable. Raw data returned for review.", None

    reasoning_text: Optional[str] = None
    human_summary = llm_output

    try:
        parsed = _load_summary_payload(llm_output)
        human_summary = _format_answer(parsed.get("answer") or parsed.get("summary"))
        reasoning_text = _format_reasoning(parsed.get("reasoning"))
    except (json.JSONDecodeError, ValueError, TypeError):
        # If parsing fails, keep the raw LLM output as the summary and no structured reasoning
        pass

    if reasoning_text is None:
        fallback_lines = [
            f"Domain guess: {extracted.get('domain', 'generic')}",
            f"Items detected: {extracted.get('item_count', 0)}",
        ]
        if notes:
            fallback_lines.append(f"Model notes: {notes}")
        reasoning_text = "\n".join(f"• {line}" for line in fallback_lines if line)

    return human_summary, reasoning_text


def summarize_error(message: str) -> str:
    try:
        return chat_with_ollama(message=message, system_prompt=ERROR_SUMMARY_PROMPT)
    except HTTPException:
        return message
