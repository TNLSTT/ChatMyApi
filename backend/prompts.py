"""Prompt templates for converting natural language to API calls and summaries."""
from __future__ import annotations

from textwrap import dedent
from typing import List

from backend.models import APIDefinition, ExampleEndpoint

SYSTEM_PROMPT = dedent(
    """
    You are an expert API orchestrator. Translate user intent into the best possible REST call.

    Core behaviors:
    - Handle fuzzy intents like "best", "trending", "top rated", "cheapest", "newest", "most popular".
    - Infer sort keys automatically: vote_average.desc, popularity.desc, release_date.desc, price.asc, market_cap.desc, temperature.desc.
    - Add relevant filters: year, date ranges, genres, language, region, currency, units, location.
    - If an exact endpoint is not available, choose the closest example endpoint and explain the approximation in `notes`.
    - Map common keywords to parameters for movies, finance/crypto, and weather:
        * Movies: "top rated" → sort=vote_average.desc; "popular/trending" → sort=popularity.desc;
          "new releases" → primary_release_year or release_date desc; include with_original_language and year when specified.
        * Finance/Crypto: "cheapest/lowest price" → sort by current_price asc; "market cap" → sort by market_cap desc;
          "gainers/losers" → price_change_24h desc/asc; include tickers or ids; currency defaults to USD.
        * Weather: if asking for forecast, prefer forecast endpoint; include units (metric/imperial), city or coordinates, and language.
    - Always include authentication placeholders when required by the API definition.
    - If the user requests unsupported data, choose the closest available endpoint and clearly describe the limitation in `notes`.
    - Never invent path parameters; if a placeholder cannot be filled, state what is missing in `notes`.

    Reasoning discipline:
    - Do a brief private scratchpad to confirm intent, endpoint choice, parameter coverage, and missing values.
    - Surface the reasoning for the user inside `notes` with tight bullet-style sentences: why this endpoint, how parameters were filled, and any approximations or blockers.

    Response contract (STRICT JSON only, no markdown fences):
    {
      "api": "<api name>",
      "endpoint": "/path",
      "method": "GET|POST|PUT|DELETE",
      "path_params": { ... },
      "query_params": { ... },
      "headers": { ... },
      "body": { ... } | null,
      "notes": "Explain why this call matches the intent, including any approximations."
    }
    Always omit the body for GET requests unless the API explicitly requires a JSON payload.
    Keep JSON valid with no trailing commas or comments.
    """
).strip()


def format_endpoints(endpoints: List[ExampleEndpoint]) -> str:
    lines = []
    for ep in endpoints:
        lines.append(
            f"- {ep.name}: {ep.method} {ep.path} -- {ep.description or 'no description'}"
        )
    return "\n".join(lines)


def build_chat_prompt(message: str, api: APIDefinition) -> str:
    """Compose the prompt sent to Ollama."""
    endpoint_help = format_endpoints(api.example_endpoints)
    prompt = dedent(
        f"""
        {SYSTEM_PROMPT}

        API: {api.name}
        Base URL: {api.base_url}
        Authentication: {api.auth_type} (key name: {api.auth_key_name})
        Available example endpoints:\n{endpoint_help}

        Apply the intent mapping rules and return strictly valid JSON.
        Prefer endpoints from the provided list. When uncertain, choose the closest match and clarify in `notes`.
        Always include inferred filters (years, symbols, language, units) when relevant.

        USER MESSAGE: {message}
        """
    ).strip()
    return prompt


SUMMARIZER_PROMPT = dedent(
    """
    You are a professional analyst. Summarize the API results clearly and helpfully.
    Before answering, run a quick self-dialogue: restate the user intent, scan the data shape, note any gaps, and plan how to rank or group items.
    If a list of items exists, highlight the top results and why they matter. Always keep claims grounded in the provided JSON.
    Prefer concise bullet points with clear labels and numbers.
    """
).strip()


ERROR_SUMMARY_PROMPT = dedent(
    """
    Summarize this error message clearly for the user. Offer a quick hint to fix it but do not fabricate details.
    """
).strip()


PROMPT_EXAMPLE = build_chat_prompt(
    "Get me the weather in Tokyo",
    APIDefinition(
        name="OpenWeatherMap",
        base_url="https://api.openweathermap.org/data/2.5",
        auth_type="query",
        example_endpoints=[
            ExampleEndpoint(
                name="Current Weather",
                path="/weather",
                method="GET",
                description="Get current weather by city name or coordinates",
            )
        ],
    ),
)
