"""
Groq client — uses Groq's OpenAI-compatible API with tool calling.
Preferred over Gemini when GROQ_API_KEY is set (much faster, generous free tier).
"""
import json
import time
from typing import Optional
from app.core.config import get_settings
from app.core.ai_config import get_ai_config
from app.core.logging import get_logger

logger = get_logger(__name__)

try:
    from groq import AsyncGroq, Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False

# Per-request HTTP timeout. The SDK default is 60s, which is the same as a
# typical proxy read timeout — give each call room without letting one hang.
REQUEST_TIMEOUT_SECONDS = 90.0

# Wall-clock budget for a whole agentic loop, so a slow model can never hold a
# request open indefinitely.
LOOP_BUDGET_SECONDS = 210.0


def groq_is_configured() -> bool:
    return GROQ_AVAILABLE and bool(get_ai_config().groq_api_key)


def check_groq_key() -> tuple[bool, Optional[str], int]:
    """Validate the configured key with a cheap models.list call."""
    if not GROQ_AVAILABLE:
        return False, "groq SDK not installed.", 0
    cfg = get_ai_config()
    if not cfg.groq_api_key:
        return False, "No Groq API key configured.", 0
    try:
        client = Groq(api_key=cfg.groq_api_key)
        return True, None, len(client.models.list().data)
    except Exception as e:
        text = str(e).strip().splitlines()[0] if str(e).strip() else type(e).__name__
        if "401" in text or "invalid_api_key" in text.lower() or "Invalid API Key" in text:
            return False, "Groq rejected this key as invalid (401).", 0
        return False, text[:220], 0


def list_groq_models() -> list[str]:
    """Return tool-capable chat models available for the current Groq key."""
    if not GROQ_AVAILABLE:
        return []
    cfg = get_ai_config()
    if not cfg.groq_api_key:
        return []
    try:
        client = Groq(api_key=cfg.groq_api_key)
        models = client.models.list()
        # Exclude audio/guard/embedding-only models that don't do chat tool calling
        excluded = ("whisper", "guard", "tts", "orpheus", "allam")
        ids = [m.id for m in models.data if not any(x in m.id.lower() for x in excluded)]
        return sorted(ids)
    except Exception as e:
        logger.warning("groq_list_models_error", error=str(e)[:200])
        return []



async def generate_text(system_prompt: str, user_message: str, max_tokens: int = 1500) -> Optional[str]:
    """Plain text generation (no tools) — used for the fleet digest."""
    if not groq_is_configured():
        return None
    cfg = get_ai_config()
    client = AsyncGroq(api_key=cfg.groq_api_key, timeout=REQUEST_TIMEOUT_SECONDS)
    try:
        response = await client.chat.completions.create(
            model=cfg.groq_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=0.2,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.warning("groq_generate_error", error=str(e)[:300])
        return None


def _build_groq_tools(tool_definitions: list[dict]) -> list[dict]:
    return [
        {"type": "function", "function": {
            "name": td["name"],
            "description": td["description"],
            "parameters": td.get("parameters", {"type": "object", "properties": {}}),
        }}
        for td in tool_definitions
    ]


async def call_groq_with_tools(
    system_prompt: str,
    user_message: str,
    tool_definitions: list[dict],
    tool_executor,
    max_iterations: int = 10,
    final_tool_name: Optional[str] = None,
) -> tuple[Optional[str], list[dict]]:
    """
    Agentic Groq tool-calling loop (OpenAI-compatible).

    Terminates when the model calls `final_tool_name` (its arguments are returned
    as the final JSON text) or produces a text response with no further tool calls.

    Reasoning models such as openai/gpt-oss-120b will not reliably emit a plain
    text final answer — they keep emitting tool calls, and Groq rejects any call
    naming a tool that was not declared. Routing the final answer through a real
    declared tool avoids that failure mode entirely.
    """
    cfg = get_ai_config()
    client = AsyncGroq(api_key=cfg.groq_api_key, timeout=REQUEST_TIMEOUT_SECONDS)
    tools = _build_groq_tools(tool_definitions)
    tool_call_log = []
    deadline = time.monotonic() + LOOP_BUDGET_SECONDS

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    valid_tool_names = {td["name"] for td in tool_definitions}

    try:
        for _ in range(max_iterations):
            if time.monotonic() > deadline:
                logger.warning("groq_loop_budget_exceeded", tool_calls=len(tool_call_log))
                return None, tool_call_log

            create_kwargs = {
                "model": cfg.groq_model,
                "messages": messages,
                "temperature": 0.1,
                "max_tokens": 4096,
            }
            if tools:
                create_kwargs["tools"] = tools
                create_kwargs["tool_choice"] = "auto"
            else:
                # No tools on offer: constrain the model to plain JSON so it does
                # not try to answer with a tool call it has no way to make.
                create_kwargs["response_format"] = {"type": "json_object"}

            response = await client.chat.completions.create(**create_kwargs)

            msg = response.choices[0].message

            # No tool calls -> final answer
            if not msg.tool_calls:
                return msg.content, tool_call_log

            # Append assistant message with tool calls
            messages.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in msg.tool_calls
                ],
            })

            # Execute each requested tool and append results
            for tc in msg.tool_calls:
                tool_name = tc.function.name
                try:
                    tool_args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    tool_args = {}

                if tool_name not in valid_tool_names:
                    result = {"error": f"Tool '{tool_name}' is not available. Use only the declared tools."}
                else:
                    logger.info("groq_tool_call", tool=tool_name, args=tool_args)
                    result = tool_executor(tool_name, tool_args)
                    tool_call_log.append({"tool": tool_name, "args": tool_args, "result": result})

                    # The final tool carries the analysis — stop here rather than
                    # spending another round trip waiting for a text reply.
                    if final_tool_name and tool_name == final_tool_name:
                        return json.dumps(tool_args), tool_call_log

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result),
                })

    except Exception as e:
        logger.error("groq_api_error", error=str(e)[:300])
        return None, tool_call_log

    logger.warning("groq_max_iterations_reached", tool_calls=len(tool_call_log))
    return None, tool_call_log
