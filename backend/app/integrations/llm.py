"""
Provider selection shared by the incident agent and the fleet digest.

Order of preference: the provider chosen in Settings, then whichever provider has a
key, then None (callers fall back to deterministic demo behaviour). When the chosen
provider is unavailable (rate limit, suspended key, outage) callers fail over to the
other configured provider via `fallback_provider`.
"""
from typing import Optional
from app.core.ai_config import get_ai_config
from app.integrations.gemini import gemini_is_configured, generate_text as _gemini_generate
from app.integrations.groq_client import groq_is_configured, generate_text as _groq_generate
from app.core.logging import get_logger

logger = get_logger(__name__)

_LABELS = {"gemini": "Gemini", "groq": "Groq"}


def configured_providers() -> dict[str, bool]:
    return {"gemini": gemini_is_configured(), "groq": groq_is_configured()}


def select_provider() -> Optional[str]:
    cfg = get_ai_config()
    configured = configured_providers()
    if configured.get(cfg.provider):
        return cfg.provider
    for provider in ("gemini", "groq"):
        if configured[provider]:
            return provider
    return None


def fallback_provider(primary: Optional[str]) -> Optional[str]:
    """The other configured provider, if any."""
    other = "groq" if primary == "gemini" else "gemini"
    return other if configured_providers().get(other) else None


def provider_label(provider: Optional[str]) -> str:
    return _LABELS.get(provider or "", "Demo mode")


async def _generate(provider: str, system_prompt: str, user_message: str, max_tokens: int) -> Optional[str]:
    if provider == "gemini":
        return await _gemini_generate(system_prompt, user_message, max_tokens)
    if provider == "groq":
        return await _groq_generate(system_prompt, user_message, max_tokens)
    return None


async def generate_text(system_prompt: str, user_message: str, max_tokens: int = 1500) -> tuple[Optional[str], Optional[str]]:
    """Returns (text, provider_used). Fails over to the other configured provider when
    the preferred one returns nothing. text is None when no provider could answer."""
    primary = select_provider()
    if primary is None:
        return None, None
    text = await _generate(primary, system_prompt, user_message, max_tokens)
    if text:
        return text, primary
    alt = fallback_provider(primary)
    if alt:
        logger.warning("ai_provider_failover", **{"from": primary, "to": alt, "task": "generate_text"})
        text = await _generate(alt, system_prompt, user_message, max_tokens)
        if text:
            return text, alt
    return None, None
