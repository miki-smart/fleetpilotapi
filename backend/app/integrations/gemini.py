"""
Gemini client — centralizes model configuration and API interaction.
Keeps all AI calls server-side; API key never exposed to frontend.
"""
import json
from typing import Optional
from app.core.config import get_settings
from app.core.ai_config import get_ai_config
from app.core.logging import get_logger

logger = get_logger(__name__)

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False


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


def get_gemini_model():
    """Return a configured Gemini GenerativeModel instance."""
    if not _ensure_client():
        return None
    cfg = get_ai_config()
    return genai.GenerativeModel(
        model_name=cfg.gemini_model,
        generation_config=genai.GenerationConfig(
            temperature=0.1,  # Low temperature for deterministic operational reasoning
            max_output_tokens=4096,
        ),
    )


async def call_gemini_with_tools(
    system_prompt: str,
    user_message: str,
    tool_definitions: list[dict],
    tool_executor,  # callable(tool_name, tool_args) -> dict
    max_iterations: int = 10,
    final_tool_name: Optional[str] = None,
) -> tuple[Optional[str], list[dict]]:
    """
    Agentic Gemini loop:
    1. Send message with tool definitions.
    2. If Gemini returns tool calls, execute them and pass results back.
    3. Continue until Gemini produces a text response (final analysis).
    Returns (final_text, tool_call_log).
    """
    if not _ensure_client():
        return None, []

    cfg = get_ai_config()
    model = genai.GenerativeModel(
        model_name=cfg.gemini_model,
        system_instruction=system_prompt,
        generation_config=genai.GenerationConfig(temperature=0.1, max_output_tokens=4096),
        tools=_build_gemini_tools(tool_definitions) if tool_definitions else None,
    )

    chat = model.start_chat()
    tool_call_log = []
    iterations = 0

    try:
        response = chat.send_message(user_message)
    except Exception as e:
        logger.warning("gemini_api_error", error=str(e)[:200])
        return None, tool_call_log

    while iterations < max_iterations:
        iterations += 1
        part = response.candidates[0].content.parts[0]

        # Check for function call
        if hasattr(part, "function_call") and part.function_call.name:
            fn = part.function_call
            tool_name = fn.name
            tool_args = dict(fn.args) if fn.args else {}

            logger.info("agent_tool_call", tool=tool_name, args=tool_args)

            tool_result = tool_executor(tool_name, tool_args)
            tool_call_log.append({"tool": tool_name, "args": tool_args, "result": tool_result})

            # The final tool carries the analysis - return its arguments as the
            # final JSON rather than waiting for a separate text turn.
            if final_tool_name and tool_name == final_tool_name:
                return json.dumps(tool_args), tool_call_log

            # Feed result back to Gemini
            response = chat.send_message(
                genai.protos.Content(
                    parts=[genai.protos.Part(
                        function_response=genai.protos.FunctionResponse(
                            name=tool_name,
                            response={"result": tool_result},
                        )
                    )]
                )
            )
        else:
            # Gemini produced a text response — extract it
            text = response.text if hasattr(response, "text") else ""
            return text, tool_call_log

    return None, tool_call_log


def _build_gemini_tools(tool_definitions: list[dict]):
    """Convert our tool definition dicts to Gemini function declarations."""
    import google.generativeai.types as genai_types
    declarations = []
    for td in tool_definitions:
        declarations.append(
            genai.protos.FunctionDeclaration(
                name=td["name"],
                description=td["description"],
                parameters=genai.protos.Schema(
                    type=genai.protos.Type.OBJECT,
                    properties={
                        k: _schema_property(v)
                        for k, v in td.get("parameters", {}).get("properties", {}).items()
                    },
                    required=td.get("parameters", {}).get("required", []),
                ),
            )
        )
    return [genai.protos.Tool(function_declarations=declarations)]


def _schema_property(prop: dict):
    type_map = {
        "string": genai.protos.Type.STRING,
        "integer": genai.protos.Type.INTEGER,
        "number": genai.protos.Type.NUMBER,
        "boolean": genai.protos.Type.BOOLEAN,
        "array": genai.protos.Type.ARRAY,
        "object": genai.protos.Type.OBJECT,
    }
    schema_type = type_map.get(prop.get("type", "string"), genai.protos.Type.STRING)
    kwargs = {"type": schema_type, "description": prop.get("description", "")}
    if schema_type == genai.protos.Type.ARRAY and "items" in prop:
        kwargs["items"] = genai.protos.Schema(
            type=type_map.get(prop["items"].get("type", "object"), genai.protos.Type.OBJECT)
        )
    return genai.protos.Schema(**kwargs)
