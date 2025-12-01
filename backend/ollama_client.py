"""Client for interacting with local Ollama server."""
from __future__ import annotations

import json
import os
import logging
import re
import urllib.parse
from typing import Any, Dict

import httpx
from fastapi import HTTPException

from backend.models import APIDefinition, APICall
from backend.prompts import build_chat_prompt

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_CHAT_URL = os.getenv("OLLAMA_CHAT_URL", "http://localhost:11434/api/chat")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")

logger = logging.getLogger(__name__)


def parse_ollama_response(content: Dict[str, Any]) -> str:
    # Ollama's generate API returns {"response": "..."}
    response_text = content.get("response")
    if not response_text:
        raise HTTPException(status_code=502, detail="No response text from Ollama")
    return response_text.strip()


def _load_json_payload(text: str) -> Dict[str, Any]:
    """Attempt to load JSON from the LLM response, even if extra text is present."""

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        if start == -1:
            raise

        candidate = text[start:]

        end = candidate.rfind("}")
        if end != -1 and end > 0:
            candidate = candidate[: end + 1]

        open_braces = candidate.count("{")
        close_braces = candidate.count("}")
        if close_braces < open_braces:
            candidate = f"{candidate}{'}' * (open_braces - close_braces)}"

        # Strip JavaScript-style line comments that frequently appear in LLM output.
        cleaned_lines = []
        for line in candidate.splitlines():
            cleaned_lines.append(re.sub(r"//.*", "", line))
        candidate = "\n".join(cleaned_lines)

        return json.loads(candidate)


def _apply_path_params(endpoint: str, path_params: Dict[str, Any]) -> str:
    """Fill templated path parameters in the endpoint string."""

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in path_params:
            raise ValueError(f"Missing path parameter: {key}")
        return urllib.parse.quote(str(path_params[key]), safe="")

    return re.sub(r"{([^}]+)}", replace, endpoint)


def _normalize_api_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    required_keys = {"endpoint", "method", "headers", "query", "body", "notes", "path_params"}
    if not isinstance(data, dict):
        raise ValueError("LLM response must be a JSON object")

    normalized: Dict[str, Any] = {}
    # Support both new contract (`path_params`, `query_params`) and legacy (`query`).
    for key in required_keys:
        if key not in data:
            if key in {"headers", "query", "body", "path_params"}:
                normalized[key] = {}
            else:
                normalized[key] = None
        else:
            normalized[key] = data.get(key)

    if "query_params" in data and not data.get("query"):
        normalized["query"] = data.get("query_params", {})

    normalized["method"] = str(normalized.get("method", "GET")).upper()
    for mapping_key in ("headers", "query", "body", "path_params"):
        value = normalized.get(mapping_key)
        if not isinstance(value, dict):
            normalized[mapping_key] = {}

    notes_val = normalized.get("notes")
    if notes_val is None:
        normalized["notes"] = ""
    elif not isinstance(notes_val, str):
        normalized["notes"] = str(notes_val)

    endpoint_val = normalized.get("endpoint")
    if isinstance(endpoint_val, str):
        endpoint_val = endpoint_val.strip()
        if endpoint_val:
            normalized["endpoint"] = endpoint_val
        else:
            raise ValueError("Endpoint must be a string")
    else:
        raise ValueError("Endpoint must be a string")

    try:
        normalized["endpoint"] = _apply_path_params(
            normalized["endpoint"], normalized.get("path_params", {})
        )
    except ValueError as exc:
        raise ValueError(str(exc))

    return normalized


def generate_api_call(message: str, api_definition: APIDefinition) -> APICall:
    """Call Ollama to translate a NL request into an API call."""
    prompt = build_chat_prompt(message=message, api=api_definition)
    payload = {"model": OLLAMA_MODEL, "prompt": prompt, "stream": False}

    logger.info(
        "Sending generate request to Ollama | model=%s api=%s prompt=\n%s",
        OLLAMA_MODEL,
        api_definition.name,
        prompt,
    )

    try:
        resp = httpx.post(OLLAMA_URL, json=payload, timeout=60)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Ollama request failed: {exc}") from exc

    try:
        payload = resp.json()
        result_text = parse_ollama_response(payload)
        logger.info("Received generate response from Ollama: %s", payload)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Invalid Ollama response: {exc}") from exc

    try:
        data = _load_json_payload(result_text)
        normalized = _normalize_api_payload(data)
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "The model response was not valid JSON. Please retry your request or "
                "clarify the desired endpoint."
            ),
        ) from exc

    try:
        api_call = APICall(**normalized)
        logger.info("Parsed APICall from Ollama response: %s", api_call)
        return api_call
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Ollama JSON failed validation: {exc}") from exc


def chat_with_ollama(message: str, system_prompt: str | None = None) -> str:
    """Send a free-form message to Ollama's chat API."""

    chat_messages = []
    if system_prompt:
        chat_messages.append({"role": "system", "content": system_prompt})
    chat_messages.append({"role": "user", "content": message})

    payload = {"model": OLLAMA_MODEL, "messages": chat_messages, "stream": False}

    logger.info(
        "Sending chat request to Ollama | model=%s messages=%s",
        OLLAMA_MODEL,
        chat_messages,
    )

    try:
        resp = httpx.post(OLLAMA_CHAT_URL, json=payload, timeout=60)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Ollama request failed: {exc}") from exc

    try:
        content = resp.json()
        logger.info("Received chat response from Ollama: %s", content)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail="Invalid JSON from Ollama") from exc

    # Chat responses can arrive in either chat or generate format.
    if isinstance(content, dict):
        message_obj = content.get("message")
        if isinstance(message_obj, dict):
            response_text = message_obj.get("content")
            if response_text:
                return response_text.strip()
        if "response" in content:
            return parse_ollama_response(content)

    raise HTTPException(status_code=502, detail="No response text from Ollama")
