from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.agent.orchestrator import handle_chat
from app.retrieval.store import get_store
from app.schemas import ChatRequest, ChatResponse, HealthResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Build the embedding index once at boot, not lazily on the first
    # /chat call — embedding 377 entries (plus a first-run model download)
    # takes far longer than the 30s per-call timeout allows.
    get_store()
    yield


app = FastAPI(title="Conversational Assessment Recommender", lifespan=lifespan)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse()


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    return handle_chat(request)
