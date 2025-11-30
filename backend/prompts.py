"""Prompt templates for converting natural language to API calls."""
from __future__ import annotations

from textwrap import dedent
from typing import List

from backend.models import APIDefinition, ExampleEndpoint

SYSTEM_PROMPT = (
    "You convert natural language requests into structured REST API calls. "
    "Always return ONLY valid JSON with keys: endpoint, method, headers, query, body, notes. "
    "Do not include markdown fences or additional commentary."
)


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

        API you are calling: {api.name}
        Base URL: {api.base_url}
        Authentication type: {api.auth_type}
        Available example endpoints:\n{endpoint_help}

        The user will ask for an action. Respond with JSON like:
        {{
          "endpoint": "/path",
          "method": "GET",
          "headers": {{"X-Some": "value"}},
          "query": {{"param": "value"}},
          "body": {{"payload": "value"}},
          "notes": "Concise explanation of what this call does"
        }}

        If data is unavailable, still propose the best matching endpoint.

        USER MESSAGE: {message}
        """
    ).strip()
    return prompt


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
