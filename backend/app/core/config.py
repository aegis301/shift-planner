from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://shift_planner:shift_planner@localhost:5432/shift_planner"
    session_secret: str = Field(default="dev-session-secret", min_length=8)
    admin_email: str = "admin@example.com"
    admin_password: str = "change-me"
    doctor_seed_password: str = "change-me-doctors"
    planner_seed_email: str | None = None
    planner_seed_password: str = "change-me-planner"
    mcp_admin_token: str = "change-me-mcp-token"
    default_organization_id: int = 1
    backend_cors_origins: str = "http://localhost:3000"

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.backend_cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

