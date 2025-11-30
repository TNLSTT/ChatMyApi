"""FastAPI entrypoint for ChatMyAPI."""
from __future__ import annotations

import json
import logging
import pathlib
from functools import lru_cache
from typing import Dict, List

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend import key_storage
from backend.api_call_executor import execute_api_call
from backend.models import (
    APIDefinition,
    ChatRequest,
    ChatResponse,
    HealthResponse,
    OllamaChatRequest,
    OllamaChatResponse,
    RunAPIRequest,
    SaveKeyRequest,
)
from backend.ollama_client import chat_with_ollama, generate_api_call

BASE_DIR = pathlib.Path(__file__).resolve().parent
API_DEFINITION_DIR = BASE_DIR / "api_definitions"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

app = FastAPI(title="ChatMyAPI", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class APILoader:
    """Simple dependency for loading API definitions into memory."""

    def __init__(self) -> None:
        self._definitions = self._load_definitions()

    def _load_definitions(self) -> Dict[str, APIDefinition]:
        definitions: Dict[str, APIDefinition] = {}
        for path in API_DEFINITION_DIR.glob("*.json"):
            with path.open("r", encoding="utf-8") as file:
                data = json.load(file)
                api_def = APIDefinition(**data)
                definitions[api_def.name] = api_def
        if not definitions:
            raise RuntimeError("No API definitions found")
        return definitions

    def get(self, name: str) -> APIDefinition:
        api = self._definitions.get(name)
        if not api:
            raise HTTPException(status_code=404, detail=f"Unknown API: {name}")
        return api

    @property
    def all(self) -> List[APIDefinition]:
        return list(self._definitions.values())


@lru_cache(maxsize=1)
def get_loader() -> APILoader:
    return APILoader()


def _format_value(value: object) -> str:
    if isinstance(value, dict):
        return f"object with {len(value)} keys"
    if isinstance(value, list):
        return f"list with {len(value)} items"
    if isinstance(value, str):
        return value if len(value) <= 60 else f"{value[:57]}..."
    return str(value)


def _summarize_dict(data: dict) -> str:
    if not data:
        return "Received an empty object."

    results = data.get("results")
    if isinstance(results, list) and results:
        names = []
        for item in results[:3]:
            if isinstance(item, dict):
                name = item.get("title") or item.get("name")
                if name:
                    names.append(str(name))

        if names:
            total = data.get("total_results") or len(results)
            total_text = f"{total} result(s)" if total else f"{len(results)} item(s)"
            sample_text = ", ".join(names)
            return f"Found {total_text}. Top examples include: {sample_text}."

    preview_items = list(data.items())[:5]
    preview_text = ", ".join(f"{k}: {_format_value(v)}" for k, v in preview_items)
    extra = " …" if len(data) > len(preview_items) else ""
    return f"Received an object with {len(data)} key(s). Top fields -> {preview_text}{extra}."


def _summarize_list(data: list) -> str:
    if not data:
        return "Received an empty list."

    prefix = f"Received a list with {len(data)} item(s)."
    first = data[0]
    if isinstance(first, dict):
        preview_items = list(first.items())[:5]
        preview_text = ", ".join(f"{k}: {_format_value(v)}" for k, v in preview_items)
        extra = " …" if len(first) > len(preview_items) else ""
        return f"{prefix} Sample item -> {preview_text}{extra}."

    if not isinstance(first, (list, dict)):
        preview_values = ", ".join(_format_value(item) for item in data[:5])
        extra = " …" if len(data) > 5 else ""
        return f"{prefix} Examples -> {preview_values}{extra}."

    return prefix


def summarize_response(data: object, notes: str | None) -> str:
    if isinstance(data, dict):
        base = _summarize_dict(data)
    elif isinstance(data, list):
        base = _summarize_list(data)
    else:
        base = str(data)

    if notes:
        return f"{notes} {base}".strip()
    return base


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get("/apis")
def list_apis(loader: APILoader = Depends(get_loader)) -> List[APIDefinition]:
    return loader.all


@app.post("/save_key")
def save_key(payload: SaveKeyRequest) -> JSONResponse:
    key_storage.save_api_key(payload.api_name, payload.api_key)
    return JSONResponse({"status": "saved"})


@app.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest, loader: APILoader = Depends(get_loader)) -> ChatResponse:
    api = loader.get(payload.selected_api)
    api_key = key_storage.load_api_key(api.name)
    api_call = generate_api_call(payload.message, api)
    response_json = execute_api_call(api, api_call, api_key)
    response_text = summarize_response(response_json, api_call.notes)
    return ChatResponse(api_call=api_call, response_text=response_text, response_json=response_json)


@app.post("/run_api", response_model=ChatResponse)
def run_api(payload: RunAPIRequest, loader: APILoader = Depends(get_loader)) -> ChatResponse:
    api = loader.get(payload.selected_api)
    api_key = key_storage.load_api_key(api.name)
    response_json = execute_api_call(api, payload.api_call, api_key)
    response_text = summarize_response(response_json, payload.api_call.notes)
    return ChatResponse(api_call=payload.api_call, response_text=response_text, response_json=response_json)


@app.post("/ollama_chat", response_model=OllamaChatResponse)
def ollama_chat(payload: OllamaChatRequest) -> OllamaChatResponse:
    response_text = chat_with_ollama(message=payload.message, system_prompt=payload.system_prompt)
    return OllamaChatResponse(response_text=response_text)


@app.exception_handler(HTTPException)
async def http_exception_handler(_, exc: HTTPException) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
