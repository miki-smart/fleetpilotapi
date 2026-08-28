from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    # Check both backend/ and project root for .env
    model_config = SettingsConfigDict(env_file=["../.env", ".env"], extra="ignore")

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/fleetpilot"

    gemini_api_key: str = ""
    gemini_model: str = "gemini-flash-latest"

    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"

    resend_api_key: str = ""
    resend_from_email: str = "fleet@fleetpilot.ai"

    nhtsa_base_url: str = "https://vpic.nhtsa.dot.gov/api"

    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",")]

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()
