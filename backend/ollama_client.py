"""Client for interacting with local Ollama server."""
from __future__ import annotations

import json
import os
from typing import Any, Dict

import httpx
from fastapi import HTTPException

from backend.models import APIDefinition, APICall
from backend.prompts import build_chat_prompt

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")


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
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise

        cleaned = text[start : end + 1]
        return json.loads(cleaned)


def generate_api_call(message: str, api_definition: APIDefinition) -> APICall:
    """Call Ollama to translate a NL request into an API call."""
    prompt = build_chat_prompt(message=message, api=api_definition)
    payload = {"model": OLLAMA_MODEL, "prompt": prompt, "stream": False}

    try:
        resp = httpx.post(OLLAMA_URL, json=payload, timeout=60)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Ollama request failed: {exc}") from exc

    try:
        payload = resp.json()
        result_text = parse_ollama_response(payload)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Invalid Ollama response: {exc}") from exc

    try:
        data = _load_json_payload(result_text)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "The model response was not valid JSON. Please retry your request or "
                "clarify the desired endpoint."
            ),
        ) from exc

    try:
        return APICall(**data)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Ollama JSON failed validation: {exc}") from exc
