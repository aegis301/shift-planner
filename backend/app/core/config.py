from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://shift_planner:shift_planner@localhost:5432/shift_planner"
    session_secret: str = Field(default="dev-session-secret", min_length=8)
    admin_email: str = "admin@example.com"
    admin_password: str = "change-me"
    team_member_seed_password: str = "change-me-team-members"
    planner_seed_email: str | None = None
    planner_seed_password: str = "change-me-planner"
    mcp_admin_token: str = "change-me-mcp-token"
    mcp_organization_id: int | None = None
    default_organization_id: int = 1
    backend_cors_origins: str = "http://localhost:3000"
    session_cookie_secure: bool = False

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.backend_cors_origins.split(",") if origin.strip()]

    @field_validator("mcp_organization_id", mode="before")
    @classmethod
    def _mcp_org_id_empty_as_none(cls, v: object) -> object:
        if v == "" or v is None:
            return None
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

