"""
Runtime AI configuration — lets the user switch provider/model/API key at runtime
via the Settings API, without restarting the backend.

Initialized from environment settings, overlaid with values previously saved from
the Settings page (persisted to a small JSON file so a restart does not silently
revert them). API keys are kept server-side and never returned to the frontend.
"""
import json
import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional
from threading import Lock
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

VALID_PROVIDERS = ("groq", "gemini")

# backend/.runtime/ai_settings.json — gitignored; in Docker it lives on the mounted volume.
_STATE_PATH = Path(os.getenv("AI_SETTINGS_PATH") or Path(__file__).resolve().parents[2] / ".runtime" / "ai_settings.json")


@dataclass
class AIRuntimeConfig:
    provider: str
    groq_api_key: str
    groq_model: str
    gemini_api_key: str
    gemini_model: str


_config: Optional[AIRuntimeConfig] = None
_lock = Lock()


def _load_persisted() -> dict:
    try:
        if _STATE_PATH.exists():
            data = json.loads(_STATE_PATH.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.warning("ai_settings_load_failed", path=str(_STATE_PATH), error=str(e)[:200])
    return {}


def _persist(cfg: AIRuntimeConfig) -> None:
    try:
        _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _STATE_PATH.write_text(json.dumps(asdict(cfg), indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning("ai_settings_persist_failed", path=str(_STATE_PATH), error=str(e)[:200])


def get_ai_config() -> AIRuntimeConfig:
    global _config
    if _config is None:
        with _lock:
            if _config is None:
                s = get_settings()
                saved = _load_persisted()
                # Gemini is the primary provider; Groq only wins the default when it is
                # the only key configured.
                env_provider = (s.ai_provider or "").strip().lower()
                if env_provider in VALID_PROVIDERS:
                    default_provider = env_provider
                else:
                    default_provider = "gemini" if s.gemini_api_key else ("groq" if s.groq_api_key else "gemini")
                provider = saved.get("provider") if saved.get("provider") in VALID_PROVIDERS else default_provider
                _config = AIRuntimeConfig(
                    provider=provider,
                    groq_api_key=saved.get("groq_api_key") or s.groq_api_key,
                    groq_model=saved.get("groq_model") or s.groq_model,
                    gemini_api_key=saved.get("gemini_api_key") or s.gemini_api_key,
                    gemini_model=saved.get("gemini_model") or s.gemini_model,
                )
                if saved:
                    logger.info("ai_settings_restored", path=str(_STATE_PATH), provider=provider)
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
        _persist(cfg)
    return cfg


def reset_ai_config_to_env() -> AIRuntimeConfig:
    """Discard saved runtime settings and go back to the .env values."""
    global _config
    with _lock:
        try:
            if _STATE_PATH.exists():
                _STATE_PATH.unlink()
        except Exception as e:
            logger.warning("ai_settings_reset_failed", error=str(e)[:200])
        _config = None
    return get_ai_config()


def active_key_configured(cfg: AIRuntimeConfig) -> bool:
    if cfg.provider == "groq":
        return bool(cfg.groq_api_key)
    if cfg.provider == "gemini":
        return bool(cfg.gemini_api_key)
    return False
