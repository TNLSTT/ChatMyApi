"""Execute API calls defined by the LLM output."""
from __future__ import annotations

import json
import time
import urllib.parse
from typing import Any, Dict, Tuple

import httpx
from fastapi import HTTPException

from backend.models import APICall, APIDefinition, ExampleEndpoint

ALLOWED_METHODS = {"GET", "POST", "PUT", "DELETE"}


class SimpleCache:
    def __init__(self, maxsize: int = 64, ttl: int = 120) -> None:
        self.maxsize = maxsize
        self.ttl = ttl
        self._store: Dict[str, Tuple[float, Any]] = {}

    def _prune(self) -> None:
        now = time.time()
        expired = [key for key, (ts, _) in self._store.items() if now - ts > self.ttl]
        for key in expired:
            self._store.pop(key, None)
        while len(self._store) > self.maxsize:
            oldest = min(self._store.items(), key=lambda item: item[1][0])[0]
            self._store.pop(oldest, None)

    def get(self, key: str) -> Any | None:
        self._prune()
        entry = self._store.get(key)
        if not entry:
            return None
        ts, value = entry
        if time.time() - ts > self.ttl:
            self._store.pop(key, None)
            return None
        return value

    def set(self, key: str, value: Any) -> None:
        self._store[key] = (time.time(), value)
        self._prune()


response_cache = SimpleCache()


def _normalize_path(path: str) -> str:
    """Return a comparable endpoint path without query strings or trailing slashes."""

    parsed = urllib.parse.urlsplit(path)
    cleaned = parsed.path.rstrip("/")
    return cleaned or "/"


def _validate_endpoint(api_def: APIDefinition, call: APICall) -> ExampleEndpoint:
    call_path = _normalize_path(call.endpoint)

    match = next(
        (
            ep
            for ep in api_def.example_endpoints
            if _normalize_path(ep.path) == call_path and ep.method == call.method
        ),
        None,
    )
    if match is None:
        raise HTTPException(
            status_code=400,
            detail="Endpoint or method not recognized for this API. Please adjust your request.",
        )
    return match


def _filter_params(params: Dict[str, Any], allowed: Any | None) -> Dict[str, Any]:
    if not allowed:
        return params
    filtered = {k: v for k, v in params.items() if k in set(allowed)}
    return filtered


def _build_cache_key(
    api_def: APIDefinition, call: APICall, query: Dict[str, Any], body: Dict[str, Any]
) -> str:
    safe_query = {k: v for k, v in query.items() if k != api_def.auth_key_name}
    serialized = json.dumps(
        {
            "api": api_def.name,
            "endpoint": _normalize_path(call.endpoint),
            "method": call.method,
            "query": safe_query,
            "body": body,
        },
        sort_keys=True,
        default=str,
    )
    return serialized


def _apply_auth(
    api_def: APIDefinition, headers: Dict[str, Any], query: Dict[str, Any], api_key: str | None
) -> None:
    if api_def.auth_type == "none":
        return
    if not api_key:
        raise HTTPException(status_code=401, detail="API key not configured for this API")

    if api_def.auth_type == "header":
        headers.setdefault("Authorization", f"Bearer {api_key}")
    elif api_def.auth_type == "query":
        query.setdefault(api_def.auth_key_name, api_key)
    else:
        headers.setdefault("Authorization", f"Bearer {api_key}")


def execute_api_call(api_def: APIDefinition, call: APICall, api_key: str | None) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    if call.method not in ALLOWED_METHODS:
        raise HTTPException(status_code=400, detail=f"Unsupported HTTP method: {call.method}")

    matched_endpoint = _validate_endpoint(api_def, call)

    headers = {"Accept": "application/json"}
    headers.update(call.headers or {})
    query = _filter_params(dict(call.query or {}), matched_endpoint.allowed_query_params)
    body = _filter_params(call.body or {}, matched_endpoint.allowed_body_params)

    _apply_auth(api_def, headers, query, api_key)

    url = f"{api_def.base_url.rstrip('/')}{call.endpoint}"
    cache_key = _build_cache_key(api_def, call, query, body)
    if call.method == "GET":
        cached = response_cache.get(cache_key)
        if cached is not None:
            return cached, {
                "from_cache": True,
                "url": url,
                "method": call.method,
                "duration_ms": 0.0,
                "status_code": 200,
            }

    start = time.perf_counter()
    try:
        with httpx.Client(timeout=60) as client:
            response = client.request(
                method=call.method,
                url=url,
                params=query if query else None,
                headers=headers,
                json=body if body else None,
            )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        content = exc.response.text
        raise HTTPException(
            status_code=exc.response.status_code,
            detail=f"API returned an error ({exc.response.status_code}): {content}",
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"API request failed: {exc}") from exc

    duration_ms = (time.perf_counter() - start) * 1000

    try:
        parsed = response.json()
    except json.JSONDecodeError:
        parsed = {"text": response.text}

    metadata = {
        "from_cache": False,
        "url": url,
        "method": call.method,
        "duration_ms": round(duration_ms, 2),
        "status_code": response.status_code,
    }

    if call.method == "GET":
        response_cache.set(cache_key, parsed)

    return parsed, metadata
