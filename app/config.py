from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent
CATALOG_PATH = BASE_DIR / "catalog" / "data" / "catalog.json"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    groq_api_key: str = ""
    gemini_api_key: str = ""
    openrouter_api_key: str = ""
    llm_provider: str = "groq"
    llm_model: str = "llama-3.3-70b-versatile"
    gemini_model: str = "gemini-2.5-flash"
    openrouter_model: str = "openai/gpt-oss-20b:free"

    max_turns: int = 8
    request_timeout_seconds: int = 18

    retrieval_top_k: int = 30
    max_recommendations: int = 10
    min_constraints_to_recommend: int = 1


settings = Settings()
