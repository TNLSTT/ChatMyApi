"""FastAPI entrypoint for ChatMyAPI."""
from __future__ import annotations

import json
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
    RunAPIRequest,
    SaveKeyRequest,
)
from backend.ollama_client import generate_api_call

BASE_DIR = pathlib.Path(__file__).resolve().parent
API_DEFINITION_DIR = BASE_DIR / "api_definitions"

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


def summarize_response(data: object, notes: str | None) -> str:
    if isinstance(data, dict):
        keys = ", ".join(list(data.keys())[:8])
        base = f"Response contains keys: {keys}."
    elif isinstance(data, list):
        base = f"Received a list with {len(data)} items."
    else:
        base = str(data)
    if notes:
        return f"{notes} {base}"
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


@app.exception_handler(HTTPException)
async def http_exception_handler(_, exc: HTTPException) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
