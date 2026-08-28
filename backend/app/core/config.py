from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    # Check both backend/ and project root for .env
    model_config = SettingsConfigDict(env_file=["../.env", ".env"], extra="ignore")

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5433/fleetpilot"

    # AI providers. Gemini is the primary provider; Groq is a switchable alternative.
    # AI_PROVIDER pins the startup default ("gemini" | "groq"); empty = Gemini if it has a key, else Groq.
    ai_provider: str = ""
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.6-flash"

    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"

    # Email via Resend. Without a verified domain Resend only delivers from
    # onboarding@resend.dev to the address that owns the Resend account, so
    # FLEET_MANAGER_EMAIL should be that address for the demo.
    resend_api_key: str = ""
    resend_from_email: str = "FleetPilot <onboarding@resend.dev>"
    fleet_manager_email: str = ""

    # NHTSA (free, no key): vPIC for VIN decoding, recalls API for open campaigns
    nhtsa_base_url: str = "https://vpic.nhtsa.dot.gov/api"
    nhtsa_recalls_base_url: str = "https://api.nhtsa.gov"

    # Proactive automation
    scheduler_enabled: bool = True
    scheduler_timezone: str = "Africa/Addis_Ababa"
    scan_schedule_cron: str = "0 6 * * *"   # daily fleet health scan
    scan_interval_minutes: int = 0          # demo: also run every N minutes (0 = off)
    scheduler_token: str = ""               # shared secret for Cloud Scheduler / GitHub Actions
    approval_reminder_hours: int = 24       # nag the manager when approvals wait longer than this

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
