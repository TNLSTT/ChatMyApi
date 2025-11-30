"""Client for interacting with local Ollama server."""
from __future__ import annotations

import json
import os
import logging
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
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise

        cleaned = text[start : end + 1]
        return json.loads(cleaned)


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
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "The model response was not valid JSON. Please retry your request or "
                "clarify the desired endpoint."
            ),
        ) from exc

    try:
        api_call = APICall(**data)
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
