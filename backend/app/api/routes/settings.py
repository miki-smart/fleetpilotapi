from fastapi import APIRouter, Query
from pydantic import BaseModel
from typing import Optional

from app.core.ai_config import get_ai_config, update_ai_config, reset_ai_config_to_env, active_key_configured
from app.integrations.groq_client import list_groq_models, check_groq_key, GROQ_AVAILABLE
from app.integrations.gemini import list_gemini_models, check_gemini_key, GEMINI_AVAILABLE

router = APIRouter(prefix="/api/settings", tags=["settings"])


class UpdateAISettings(BaseModel):
    provider: Optional[str] = None
    groq_model: Optional[str] = None
    groq_api_key: Optional[str] = None
    gemini_model: Optional[str] = None
    gemini_api_key: Optional[str] = None


def _mask(key: str) -> Optional[str]:
    if not key:
        return None
    if len(key) <= 8:
        return "••••"
    return f"{key[:4]}••••{key[-4:]}"


def _serialize() -> dict:
    cfg = get_ai_config()
    return {
        "provider": cfg.provider,
        "active_key_configured": active_key_configured(cfg),
        "groq": {
            "model": cfg.groq_model,
            "key_configured": bool(cfg.groq_api_key),
            "key_hint": _mask(cfg.groq_api_key),
            "available": GROQ_AVAILABLE,
        },
        "gemini": {
            "model": cfg.gemini_model,
            "key_configured": bool(cfg.gemini_api_key),
            "key_hint": _mask(cfg.gemini_api_key),
            "available": GEMINI_AVAILABLE,
        },
    }


def _validate(provider: str) -> dict:
    """Cheap live check of the configured key so the UI can say *why* a key is unusable."""
    provider = (provider or "").strip().lower()
    if provider == "gemini":
        ok, error, models = check_gemini_key()
    elif provider == "groq":
        ok, error, models = check_groq_key()
    else:
        ok, error, models = False, f"Unknown provider '{provider}'.", 0
    return {"provider": provider, "ok": ok, "error": error, "models": models}


@router.get("/ai")
def get_ai_settings():
    return {"success": True, "data": _serialize()}


@router.post("/ai")
def update_ai_settings(payload: UpdateAISettings):
    """Apply immediately (persisted to backend/.runtime so restarts keep it) and
    validate the key of the provider that was just saved."""
    cfg = update_ai_config(
        provider=payload.provider,
        groq_model=payload.groq_model,
        groq_api_key=payload.groq_api_key,
        gemini_model=payload.gemini_model,
        gemini_api_key=payload.gemini_api_key,
    )
    data = _serialize()
    data["validation"] = _validate(payload.provider or cfg.provider)
    return {"success": True, "data": data}


@router.get("/ai/validate")
def validate_ai_key(provider: str = Query(...)):
    return {"success": True, "data": _validate(provider)}


@router.post("/ai/reset")
def reset_ai_settings():
    """Forget Settings-page overrides and return to the .env configuration."""
    reset_ai_config_to_env()
    return {"success": True, "data": _serialize()}


@router.get("/ai/models")
def get_ai_models(provider: str):
    provider = provider.strip().lower()
    if provider == "groq":
        models = list_groq_models()
    elif provider == "gemini":
        models = list_gemini_models()
    else:
        models = []
    return {"success": True, "data": {"provider": provider, "models": models}}
