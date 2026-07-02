from typing import Literal, Optional

from pydantic import BaseModel, Field


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    messages: list[Message]


class Recommendation(BaseModel):
    name: str
    url: str
    test_type: Optional[str] = None


class ChatResponse(BaseModel):
    reply: str
    recommendations: list[Recommendation] = Field(default_factory=list)
    end_of_conversation: bool = False


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
