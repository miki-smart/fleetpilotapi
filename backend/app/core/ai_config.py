"""
Runtime AI configuration — lets the user switch provider/model/API key at runtime
via the Settings API, without restarting the backend.

Initialized from environment settings, then mutable in-memory. API keys are kept
server-side and never returned to the frontend.
"""
from dataclasses import dataclass
from typing import Optional
from threading import Lock
from app.core.config import get_settings

VALID_PROVIDERS = ("groq", "gemini")


@dataclass
class AIRuntimeConfig:
    provider: str
    groq_api_key: str
    groq_model: str
    gemini_api_key: str
    gemini_model: str


_config: Optional[AIRuntimeConfig] = None
_lock = Lock()


def get_ai_config() -> AIRuntimeConfig:
    global _config
    if _config is None:
        with _lock:
            if _config is None:
                s = get_settings()
                default_provider = "groq" if s.groq_api_key else ("gemini" if s.gemini_api_key else "groq")
                _config = AIRuntimeConfig(
                    provider=default_provider,
                    groq_api_key=s.groq_api_key,
                    groq_model=s.groq_model,
                    gemini_api_key=s.gemini_api_key,
                    gemini_model=s.gemini_model,
                )
    return _config


def update_ai_config(
    provider: Optional[str] = None,
    groq_api_key: Optional[str] = None,
    groq_model: Optional[str] = None,
    gemini_api_key: Optional[str] = None,
    gemini_model: Optional[str] = None,
) -> AIRuntimeConfig:
    cfg = get_ai_config()
    with _lock:
        if provider is not None:
            p = provider.strip().lower()
            if p in VALID_PROVIDERS:
                cfg.provider = p
        # Empty string is ignored so a save without a key doesn't wipe an existing one
        if groq_api_key:
            cfg.groq_api_key = groq_api_key.strip()
        if groq_model:
            cfg.groq_model = groq_model.strip()
        if gemini_api_key:
            cfg.gemini_api_key = gemini_api_key.strip()
        if gemini_model:
            cfg.gemini_model = gemini_model.strip()
    return cfg


def active_key_configured(cfg: AIRuntimeConfig) -> bool:
    if cfg.provider == "groq":
        return bool(cfg.groq_api_key)
    if cfg.provider == "gemini":
        return bool(cfg.gemini_api_key)
    return False
