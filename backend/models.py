"""Pydantic models for ChatMyAPI backend."""
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, field_validator


HttpMethod = Literal["GET", "POST", "PUT", "DELETE"]


class ExampleEndpoint(BaseModel):
    name: str
    path: str
    method: HttpMethod
    description: Optional[str] = None
    allowed_query_params: Optional[List[str]] = None
    allowed_body_params: Optional[List[str]] = None


class APIDefinition(BaseModel):
    name: str
    base_url: str
    auth_type: Literal["header", "query", "oauth2", "rapidapi", "none"] = "none"
    auth_key_name: str = "api_key"
    example_endpoints: List[ExampleEndpoint] = Field(default_factory=list)


class APICall(BaseModel):
    endpoint: str
    method: HttpMethod
    headers: Dict[str, Any] = Field(default_factory=dict)
    path_params: Dict[str, Any] = Field(default_factory=dict)
    query: Dict[str, Any] = Field(default_factory=dict)
    body: Dict[str, Any] = Field(default_factory=dict)
    notes: Optional[str] = None

    @field_validator("endpoint")
    @classmethod
    def endpoint_format(cls, v: str) -> str:
        if not v.startswith("/"):
            raise ValueError("endpoint must start with a slash, e.g. /data")
        return v


class ChatRequest(BaseModel):
    message: str
    selected_api: str
    verbose: bool = False


class ChatResponse(BaseModel):
    api_call: APICall
    human_summary: str
    raw_json: Any
    notes: Optional[str] = None
    reasoning: Optional[str] = None
    ranked_items: List[Dict[str, Any]] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    response_text: Optional[str] = None
    response_json: Any | None = None


class RunAPIRequest(BaseModel):
    selected_api: str
    api_call: APICall
    user_message: Optional[str] = None
    verbose: bool = False


class OllamaChatRequest(BaseModel):
    message: str
    system_prompt: Optional[str] = None


class OllamaChatResponse(BaseModel):
    response_text: str


class SaveKeyRequest(BaseModel):
    api_name: str
    api_key: str


class HealthResponse(BaseModel):
    status: str
