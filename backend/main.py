"""FastAPI entrypoint for ChatMyAPI."""
from __future__ import annotations

import json
import logging
import pathlib
import time
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
from backend.summarizer import extract_relevant_items, summarize_error, summarize_results

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
    start_time = time.perf_counter()
    try:
        api_call = generate_api_call(payload.message, api)
        response_json, call_meta = execute_api_call(api, api_call, api_key)
    except HTTPException as exc:
        summary = summarize_error(str(exc.detail))
        raise HTTPException(status_code=exc.status_code, detail=summary) from exc

    insights = extract_relevant_items(
        response_json, {"user_query": payload.message, "api_name": api.name}
    )
    human_summary, reasoning = summarize_results(
        response_json,
        payload.message,
        api.name,
        api_call.notes,
        insights,
        payload.verbose,
    )

    duration_ms = (time.perf_counter() - start_time) * 1000
    metadata = {
        **call_meta,
        "pipeline_ms": round(duration_ms, 2),
        "api": api.name,
        "endpoint": api_call.endpoint,
        "method": api_call.method,
        "verbose": payload.verbose,
    }
    if insights.get("metrics"):
        metadata["metrics"] = insights["metrics"]

    return ChatResponse(
        api_call=api_call,
        human_summary=human_summary,
        raw_json=response_json,
        notes=api_call.notes,
        reasoning=reasoning,
        ranked_items=insights.get("top_items", []),
        metadata=metadata,
        response_text=human_summary,
        response_json=response_json,
    )


@app.post("/run_api", response_model=ChatResponse)
def run_api(payload: RunAPIRequest, loader: APILoader = Depends(get_loader)) -> ChatResponse:
    api = loader.get(payload.selected_api)
    api_key = key_storage.load_api_key(api.name)
    try:
        response_json, call_meta = execute_api_call(api, payload.api_call, api_key)
    except HTTPException as exc:
        summary = summarize_error(str(exc.detail))
        raise HTTPException(status_code=exc.status_code, detail=summary) from exc

    message = payload.user_message or "API run request"
    insights = extract_relevant_items(
        response_json, {"user_query": message, "api_name": api.name}
    )
    human_summary, reasoning = summarize_results(
        response_json,
        message,
        api.name,
        payload.api_call.notes,
        insights,
        payload.verbose,
    )

    metadata = {
        **call_meta,
        "api": api.name,
        "endpoint": payload.api_call.endpoint,
        "method": payload.api_call.method,
        "verbose": payload.verbose,
    }
    if insights.get("metrics"):
        metadata["metrics"] = insights["metrics"]

    return ChatResponse(
        api_call=payload.api_call,
        human_summary=human_summary,
        raw_json=response_json,
        notes=payload.api_call.notes,
        reasoning=reasoning,
        ranked_items=insights.get("top_items", []),
        metadata=metadata,
        response_text=human_summary,
        response_json=response_json,
    )


@app.post("/ollama_chat", response_model=OllamaChatResponse)
def ollama_chat(payload: OllamaChatRequest) -> OllamaChatResponse:
    response_text = chat_with_ollama(message=payload.message, system_prompt=payload.system_prompt)
    return OllamaChatResponse(response_text=response_text)


@app.exception_handler(HTTPException)
async def http_exception_handler(_, exc: HTTPException) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
