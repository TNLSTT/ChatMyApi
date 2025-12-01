"""Execute API calls defined by the LLM output."""
from __future__ import annotations

import json
import logging
import re
import time
import urllib.parse
from typing import Any, Dict, Tuple

import httpx
from fastapi import HTTPException

from backend.models import APICall, APIDefinition, ExampleEndpoint

logger = logging.getLogger(__name__)

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


def _redact_sensitive_data(data: Dict[str, Any], additional_keys: set[str] | None = None) -> Dict[str, Any]:
    """Return a shallow copy with likely secrets masked."""

    redacted: Dict[str, Any] = {}
    sensitive_keys = {"authorization", "api_key", "apikey", "token", "key"}
    if additional_keys:
        sensitive_keys |= {key.lower() for key in additional_keys}
    for key, value in data.items():
        key_lower = str(key).lower()
        if key_lower in sensitive_keys:
            redacted[key] = "***"
        else:
            redacted[key] = value
    return redacted


def _truncate(text: str, limit: int = 500) -> str:
    if len(text) <= limit:
        return text
    return f"{text[:limit]}... (truncated)"


def _resolve_endpoint(call: APICall) -> str:
    """Replace templated path params with provided values."""

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in call.path_params:
            raise HTTPException(status_code=400, detail=f"Missing path parameter: {key}")
        return urllib.parse.quote(str(call.path_params[key]), safe="")

    return re.sub(r"{([^}]+)}", replace, call.endpoint)


def _normalize_path(path: str) -> str:
    """Return a comparable endpoint path without query strings or trailing slashes."""

    parsed = urllib.parse.urlsplit(path)
    cleaned = parsed.path.rstrip("/")
    return cleaned or "/"


def _paths_match(call_path: str, example_path: str) -> bool:
    """Match resolved call paths against templated example paths."""

    cleaned_call = _normalize_path(call_path)
    cleaned_example = _normalize_path(example_path)

    pattern = re.sub(r"{[^/]+}", "[^/]+", cleaned_example)
    return re.fullmatch(pattern, cleaned_call) is not None


def _validate_endpoint(api_def: APIDefinition, call: APICall) -> ExampleEndpoint:
    match = next(
        (
            ep
            for ep in api_def.example_endpoints
            if _paths_match(call.endpoint, ep.path) and ep.method == call.method
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


def _apply_api_defaults(
    api_def: APIDefinition, matched_endpoint: ExampleEndpoint, query: Dict[str, Any]
) -> None:
    """Set per-API default query params when missing.

    RestCountries can return a 400 without an explicit `fields` selection, so we
    default to a lightweight set when none is provided.
    """

    if (
        api_def.name.lower() == "restcountries"
        and matched_endpoint.allowed_query_params
        and "fields" in matched_endpoint.allowed_query_params
        and "fields" not in query
    ):
        # Keep the selection small to reduce payload size while remaining useful.
        query["fields"] = "name,capital,region,cca2,cca3"


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
    elif api_def.auth_type == "rapidapi":
        host = urllib.parse.urlsplit(api_def.base_url).netloc
        if not host:
            raise HTTPException(status_code=400, detail="RapidAPI base_url is missing a host")

        headers.setdefault("X-RapidAPI-Key", api_key)
        headers.setdefault("X-RapidAPI-Host", host)
    else:
        headers.setdefault("Authorization", f"Bearer {api_key}")


def execute_api_call(api_def: APIDefinition, call: APICall, api_key: str | None) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    if call.method not in ALLOWED_METHODS:
        raise HTTPException(status_code=400, detail=f"Unsupported HTTP method: {call.method}")

    resolved_endpoint = _resolve_endpoint(call)
    call.endpoint = resolved_endpoint

    matched_endpoint = _validate_endpoint(api_def, call)

    headers = {"Accept": "application/json"}
    headers.update(call.headers or {})
    query = _filter_params(dict(call.query or {}), matched_endpoint.allowed_query_params)
    _apply_api_defaults(api_def, matched_endpoint, query)
    body = _filter_params(call.body or {}, matched_endpoint.allowed_body_params)

    _apply_auth(api_def, headers, query, api_key)

    url = f"{api_def.base_url.rstrip('/')}{resolved_endpoint}"
    cache_key = _build_cache_key(api_def, call, query, body)
    sensitive_names = {api_def.auth_key_name} if api_def.auth_key_name else set()
    request_details = {
        "url": url,
        "method": call.method,
        "headers": _redact_sensitive_data(dict(headers), additional_keys=sensitive_names),
        "query": _redact_sensitive_data(dict(query), additional_keys=sensitive_names),
        "body": _redact_sensitive_data(dict(body), additional_keys=sensitive_names),
    }

    logger.info(
        "Prepared API request | api=%s method=%s url=%s query=%s body_keys=%s headers=%s",
        api_def.name,
        call.method,
        url,
        request_details["query"],
        sorted(body.keys()),
        request_details["headers"],
    )

    if call.method == "GET":
        cached = response_cache.get(cache_key)
        if cached is not None:
            logger.info(
                "Cache hit for %s %s | query=%s",
                call.method,
                url,
                request_details["query"],
            )
            return cached, {
                "from_cache": True,
                "url": url,
                "method": call.method,
                "duration_ms": 0.0,
                "status_code": 200,
                "request": request_details,
                "response_preview": "served-from-cache",
            }

    response = None
    duration_ms = 0.0
    last_error: httpx.HTTPError | None = None
    attempts = []
    trust_env_used: bool | None = None
    for trust_env in (True, False):
        start = time.perf_counter()
        try:
            logger.info(
                "Dispatching API request | api=%s url=%s method=%s trust_env=%s",
                api_def.name,
                url,
                call.method,
                trust_env,
            )
            with httpx.Client(timeout=60, trust_env=trust_env) as client:
                candidate = client.request(
                    method=call.method,
                    url=url,
                    params=query if query else None,
                    headers=headers,
                    json=body if body else None,
                )
            candidate.raise_for_status()
            response = candidate
            duration_ms = (time.perf_counter() - start) * 1000
            trust_env_used = trust_env
            attempts.append(
                {
                    "trust_env": trust_env,
                    "status_code": candidate.status_code,
                    "duration_ms": round(duration_ms, 2),
                }
            )
            logger.info(
                "API call succeeded | api=%s status=%s duration_ms=%.2f trust_env=%s",
                api_def.name,
                candidate.status_code,
                duration_ms,
                trust_env,
            )
            break
        except httpx.ProxyError as exc:
            last_error = exc
            attempts.append({"trust_env": trust_env, "error": str(exc)})
            if trust_env:
                continue
            raise HTTPException(status_code=502, detail=f"API request failed: {exc}") from exc
        except httpx.HTTPStatusError as exc:
            content = exc.response.text
            attempts.append(
                {
                    "trust_env": trust_env,
                    "status_code": exc.response.status_code,
                    "error": _truncate(content),
                }
            )
            logger.error(
                "API returned error | api=%s status=%s trust_env=%s body=%s",
                api_def.name,
                exc.response.status_code,
                trust_env,
                _truncate(content),
            )
            raise HTTPException(
                status_code=exc.response.status_code,
                detail=f"API returned an error ({exc.response.status_code}): {_truncate(content)}",
            ) from exc
        except httpx.HTTPError as exc:
            last_error = exc
            attempts.append({"trust_env": trust_env, "error": str(exc)})
            if trust_env and isinstance(exc, httpx.ConnectError):
                continue
            raise HTTPException(status_code=502, detail=f"API request failed: {exc}") from exc

    if response is None:
        logger.error(
            "API request failed after retries | api=%s url=%s attempts=%s",
            api_def.name,
            url,
            attempts,
        )
        raise HTTPException(
            status_code=502,
            detail=f"API request failed: {last_error or 'unknown error'}",
        )

    try:
        parsed = response.json()
    except json.JSONDecodeError:
        parsed = {"text": response.text}
        logger.warning(
            "Response was not valid JSON | api=%s status=%s preview=%s",
            api_def.name,
            response.status_code,
            _truncate(response.text),
        )

    metadata = {
        "from_cache": False,
        "url": url,
        "method": call.method,
        "duration_ms": round(duration_ms, 2),
        "status_code": response.status_code,
        "request": request_details,
        "response_preview": _truncate(response.text),
        "attempts": attempts,
        "trust_env_used": trust_env_used,
    }

    if call.method == "GET":
        response_cache.set(cache_key, parsed)

    return parsed, metadata
