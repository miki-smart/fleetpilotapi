"""
Gemini client — primary AI provider.
Keeps all AI calls server-side; the API key never reaches the frontend.

The SDK is synchronous, so every network call runs in a worker thread to keep the
event loop free (the UI polls the incident while an analysis is in flight).
"""
import asyncio
import json
from typing import Optional
from app.core.ai_config import get_ai_config
from app.core.logging import get_logger

logger = get_logger(__name__)

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

_MAX_RETRIES = 4          # free tier is rate-limited per minute; back off across the window instead of failing
_INITIAL_DELAY_S = 10.0


def _ensure_client() -> bool:
    """Configure the Gemini SDK with the current runtime API key."""
    cfg = get_ai_config()
    if not cfg.gemini_api_key:
        return False
    if not GEMINI_AVAILABLE:
        logger.warning("google-generativeai not installed.")
        return False
    genai.configure(api_key=cfg.gemini_api_key)
    return True


def gemini_is_configured() -> bool:
    return GEMINI_AVAILABLE and bool(get_ai_config().gemini_api_key)


def check_gemini_key() -> tuple[bool, Optional[str], int]:
    """Validate the configured key with a cheap list_models call.
    Returns (ok, human-readable error, number of generateContent models)."""
    if not _ensure_client():
        return False, "No Gemini API key configured.", 0
    try:
        count = sum(1 for m in genai.list_models() if "generateContent" in m.supported_generation_methods)
        return True, None, count
    except Exception as e:
        return False, _friendly_error(e), 0


def _friendly_error(exc: Exception) -> str:
    text = str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__
    if "CONSUMER_SUSPENDED" in str(exc) or "suspended" in text.lower():
        return "Google rejected this key: it has been suspended (CONSUMER_SUSPENDED). Create a new key in Google AI Studio."
    if "API_KEY_INVALID" in str(exc) or "API key not valid" in text:
        return "Google rejected this key as invalid (API_KEY_INVALID)."
    if "429" in text or "quota" in text.lower():
        return "Key is valid but currently rate-limited (429). Try again in a minute."
    return text[:220]


def list_gemini_models() -> list[str]:
    """Return models that support generateContent for the current Gemini key."""
    if not _ensure_client():
        return []
    try:
        models = [
            m.name.replace("models/", "")
            for m in genai.list_models()
            if "generateContent" in m.supported_generation_methods
        ]
        return sorted(models)
    except Exception as e:
        logger.warning("gemini_list_models_error", error=str(e)[:200])
        return []


def _generation_config(max_tokens: int = 4096):
    # Low temperature for deterministic operational reasoning
    return genai.GenerationConfig(temperature=0.1, max_output_tokens=max_tokens)


def _is_retryable(exc: Exception) -> bool:
    # The SDK raises a bare IndexError ("index: 0") when a throttled call comes back
    # with no candidates — treat it like the 429 it usually is.
    if isinstance(exc, IndexError):
        return True
    raw = str(exc)
    text = f"{type(exc).__name__} {raw}".lower()
    # A per-day quota will not clear within our back-off window — fail fast so the
    # orchestrator can fail over to the other provider instead of waiting a minute.
    if "perday" in text or "per_day" in text or "daily" in text:
        return False
    if "suspended" in text or "permission" in text or "api_key_invalid" in text or "api key not valid" in text:
        return False
    return any(marker in text for marker in ("429", "resourceexhausted", "resource_exhausted", "quota", "503", "unavailable", "deadline"))


async def _run_with_retry(fn, *args):
    """Run a blocking SDK call off the event loop, backing off on rate limits.
    Delays 10s → 18s → 32s span the free tier's per-minute window."""
    delay = _INITIAL_DELAY_S
    for attempt in range(_MAX_RETRIES):
        try:
            return await asyncio.to_thread(fn, *args)
        except Exception as e:
            if not _is_retryable(e) or attempt == _MAX_RETRIES - 1:
                raise
            logger.warning("gemini_rate_limited", attempt=attempt + 1, retry_in=round(delay))
            await asyncio.sleep(delay)
            delay *= 1.8


async def generate_text(system_prompt: str, user_message: str, max_tokens: int = 1500) -> Optional[str]:
    """Plain text generation (no tools) — used for the fleet digest."""
    if not _ensure_client():
        return None
    cfg = get_ai_config()
    model = genai.GenerativeModel(
        model_name=cfg.gemini_model,
        system_instruction=system_prompt,
        generation_config=_generation_config(max_tokens),
    )
    try:
        response = await _run_with_retry(model.generate_content, user_message)
        return _response_text(response)
    except Exception as e:
        logger.warning("gemini_generate_error", error=str(e)[:300])
        return None


async def call_gemini_with_tools(
    system_prompt: str,
    user_message: str,
    tool_definitions: list[dict],
    tool_executor,  # callable(tool_name, tool_args) -> dict
    max_iterations: int = 12,
    final_tool_name: Optional[str] = None,
) -> tuple[Optional[str], list[dict]]:
    """
    Agentic Gemini loop:
    1. Send message with tool definitions.
    2. Execute every function call Gemini returns in the turn and send all results back.
    3. Stop when Gemini calls `final_tool_name` (its arguments are the final JSON) or
       produces a plain text response.
    Returns (final_text, tool_call_log).
    """
    if not _ensure_client():
        return None, []

    cfg = get_ai_config()
    model = genai.GenerativeModel(
        model_name=cfg.gemini_model,
        system_instruction=system_prompt,
        generation_config=_generation_config(),
        tools=_build_gemini_tools(tool_definitions) if tool_definitions else None,
    )
    chat = model.start_chat()
    tool_call_log: list[dict] = []

    try:
        response = await _run_with_retry(chat.send_message, user_message)

        for _ in range(max_iterations):
            calls = _extract_function_calls(response)
            if not calls:
                return _response_text(response), tool_call_log

            response_parts = []
            for call in calls:
                tool_name, tool_args = call["name"], call["args"]
                logger.info("agent_tool_call", provider="gemini", tool=tool_name, args=tool_args)
                result = tool_executor(tool_name, tool_args)
                tool_call_log.append({"tool": tool_name, "args": tool_args, "result": result})

                # The final tool carries the analysis — return its arguments as the
                # final JSON rather than waiting for a separate text turn.
                if final_tool_name and tool_name == final_tool_name:
                    return json.dumps(tool_args), tool_call_log

                response_parts.append(
                    genai.protos.Part(
                        function_response=genai.protos.FunctionResponse(
                            name=tool_name, response={"result": result}
                        )
                    )
                )

            response = await _run_with_retry(chat.send_message, genai.protos.Content(parts=response_parts))
    except Exception as e:
        logger.error("gemini_api_error", error=str(e)[:300], tool_calls=len(tool_call_log))
        return None, tool_call_log

    logger.warning("gemini_max_iterations_reached", tool_calls=len(tool_call_log))
    return None, tool_call_log


def _extract_function_calls(response) -> list[dict]:
    """All function calls in the first candidate, as plain Python dicts."""
    calls = []
    try:
        parts = response.candidates[0].content.parts
    except (IndexError, AttributeError):
        return calls
    for part in parts:
        fc = getattr(part, "function_call", None)
        if fc and fc.name:
            # MapComposite is not JSON-serializable; to_dict gives plain dict/list values.
            as_dict = type(fc).to_dict(fc)
            calls.append({"name": fc.name, "args": as_dict.get("args") or {}})
    return calls


def _response_text(response) -> str:
    try:
        return response.text
    except Exception:
        try:
            return "".join(p.text for p in response.candidates[0].content.parts if getattr(p, "text", None))
        except Exception:
            return ""


# --- schema translation -------------------------------------------------------

_TYPE_MAP = {
    "string": "STRING",
    "integer": "INTEGER",
    "number": "NUMBER",
    "boolean": "BOOLEAN",
    "array": "ARRAY",
    "object": "OBJECT",
}


def _build_gemini_tools(tool_definitions: list[dict]):
    """Convert our JSON-Schema tool definitions to Gemini function declarations."""
    declarations = []
    for td in tool_definitions:
        params = td.get("parameters", {}) or {}
        declarations.append(
            genai.protos.FunctionDeclaration(
                name=td["name"],
                description=td["description"],
                parameters=genai.protos.Schema(
                    type=genai.protos.Type.OBJECT,
                    properties={k: _to_schema(v) for k, v in params.get("properties", {}).items()},
                    required=params.get("required", []),
                ),
            )
        )
    return [genai.protos.Tool(function_declarations=declarations)]


def _to_schema(prop: dict):
    """Recursive JSON-Schema → genai.protos.Schema. Gemini rejects OBJECT schemas with
    no properties, so a property-less object degrades to a free-form STRING."""
    type_name = _TYPE_MAP.get(prop.get("type", "string"), "STRING")
    schema_type = getattr(genai.protos.Type, type_name)
    kwargs = {"type": schema_type}
    if prop.get("description"):
        kwargs["description"] = prop["description"]

    if type_name == "ARRAY":
        kwargs["items"] = _to_schema(prop.get("items") or {"type": "string"})
    elif type_name == "OBJECT":
        props = prop.get("properties") or {}
        if props:
            kwargs["properties"] = {k: _to_schema(v) for k, v in props.items()}
            if prop.get("required"):
                kwargs["required"] = prop["required"]
        else:
            kwargs = {"type": genai.protos.Type.STRING, "description": prop.get("description", "JSON-encoded object")}
    elif type_name == "STRING" and prop.get("enum"):
        kwargs["enum"] = prop["enum"]

    return genai.protos.Schema(**kwargs)
