"""Application configuration."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


_BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    cors_origins: str = "http://localhost:3000"

    database_url: str = "postgresql+asyncpg://travelai:travelai@localhost:5432/travelai"
    redis_url: str = "redis://localhost:6379/0"

    # LLM: openrouter (default) | ollama | auto
    llm_provider: str = "openrouter"

    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    model_planner: str = "poolside/laguna-xs.2:free"
    model_validator: str = "poolside/laguna-xs.2:free"
    model_synthesizer: str = "poolside/laguna-m.1:free"
    model_specialist: str = "openai/gpt-4o-mini"

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"
    use_ollama_fallback: bool = False

    langsmith_api_key: str = ""
    langsmith_project: str = "travelai"
    langsmith_tracing: bool = True

    max_repair_rounds: int = 2
    rag_top_k: int = 5

    # Tavily web search (supplementary to RAG — not a replacement)
    tavily_api_key: str = ""
    tavily_enabled: bool = True
    tavily_max_results: int = 3
    tavily_search_depth: str = "basic"  # basic | advanced
    tavily_timeout_seconds: float = 20.0
    tavily_min_rag_chunks: int = 2  # run Tavily if RAG returns fewer than this
    agent_max_tokens_planner: int = 1024
    agent_max_tokens_specialist: int = 2048
    agent_max_tokens_synthesizer: int = 4096

    datasets_path: str = str(Path(__file__).resolve().parents[3] / "datasets")
    destination_guides_path: str = ""

    @property
    def guides_path(self) -> Path:
        if self.destination_guides_path:
            return Path(self.destination_guides_path)
        return Path(self.datasets_path) / "destination_guides"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
