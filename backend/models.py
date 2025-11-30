"""Pydantic models for ChatMyAPI backend."""
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, field_validator


HttpMethod = Literal["GET", "POST", "PUT", "DELETE"]


class ExampleEndpoint(BaseModel):
    name: str
    path: str
    method: HttpMethod
    description: Optional[str] = None


class APIDefinition(BaseModel):
    name: str
    base_url: str
    auth_type: Literal["header", "query", "oauth2", "none"] = "none"
    auth_key_name: str = "api_key"
    example_endpoints: List[ExampleEndpoint] = Field(default_factory=list)


class APICall(BaseModel):
    endpoint: str
    method: HttpMethod
    headers: Dict[str, Any] = Field(default_factory=dict)
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


class ChatResponse(BaseModel):
    api_call: APICall
    response_text: str
    response_json: Any


class RunAPIRequest(BaseModel):
    selected_api: str
    api_call: APICall


class SaveKeyRequest(BaseModel):
    api_name: str
    api_key: str


class HealthResponse(BaseModel):
    status: str
