"""Execute API calls defined by the LLM output."""
from __future__ import annotations

import json
from typing import Any, Dict

import httpx
from fastapi import HTTPException

from backend.models import APICall, APIDefinition

ALLOWED_METHODS = {"GET", "POST", "PUT", "DELETE"}


def _validate_endpoint(api_def: APIDefinition, call: APICall) -> None:
    match = next(
        (
            ep
            for ep in api_def.example_endpoints
            if ep.path == call.endpoint and ep.method == call.method
        ),
        None,
    )
    if match is None:
        raise HTTPException(
            status_code=400,
            detail="Endpoint or method not recognized for this API. Please adjust your request.",
        )


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


def execute_api_call(api_def: APIDefinition, call: APICall, api_key: str | None) -> Dict[str, Any]:
    if call.method not in ALLOWED_METHODS:
        raise HTTPException(status_code=400, detail="Unsupported HTTP method")

    _validate_endpoint(api_def, call)

    headers = {"Accept": "application/json"}
    headers.update(call.headers or {})
    query = dict(call.query or {})
    body = call.body or {}

    _apply_auth(api_def, headers, query, api_key)

    url = f"{api_def.base_url.rstrip('/')}{call.endpoint}"

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
            detail=f"API returned an error: {content}",
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"API request failed: {exc}") from exc

    try:
        return response.json()
    except json.JSONDecodeError:
        return {"text": response.text}
