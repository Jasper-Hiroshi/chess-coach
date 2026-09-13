from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./chess_coach.db"
    chess_com_user_agent: str = "chess-coach/0.1 (local personal app)"
    stockfish_path: str = "stockfish"
    analysis_fast_nodes: int = 100_000
    analysis_deep_nodes: int = 500_000
    analysis_version: str = "stockfish19-wdl-v1"
    api_cors_origins: str = "http://127.0.0.1:5173,http://localhost:5173"
    opening_cache_hours: int = 24
    worker_poll_seconds: float = 1.0

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.api_cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

