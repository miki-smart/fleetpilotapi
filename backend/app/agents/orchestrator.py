"""
Agent orchestrator — coordinates AI tool-calling with deterministic business logic.
Supports Groq (preferred) and Gemini. Falls back to demo mode if neither is configured.
"""
import json
from datetime import datetime, date
from typing import Optional
from sqlalchemy.orm import Session

from app.agents.prompts import FLEET_AGENT_SYSTEM_PROMPT
from app.agents.fleet_agent import AGENT_TOOL_DEFINITIONS
from app.agents.schemas import IncidentAnalysis
from app.agents import tools as tool_handlers
from app.integrations.groq_client import call_groq_with_tools, groq_is_configured
from app.integrations.gemini import call_gemini_with_tools, gemini_is_configured
from app.core.ai_config import get_ai_config
from app.database.models import (
    Incident, Vehicle, AgentAction, MaintenanceTask,
    IncidentStatus, IncidentSeverity, VehicleStatus,
    AgentActionType, AgentActionStatus, TaskStatus,
)
from app.core.logging import get_logger

logger = get_logger(__name__)


async def run_incident_analysis(incident_id: str, db: Session) -> dict:
    """
    Main agent entry point.
    1. Load the incident.
    2. Run the Gemini agentic loop with tools.
    3. Apply business rules to the AI output.
    4. Persist all results.
    5. Return a structured summary for the frontend.
    """
    import uuid
    uid = uuid.UUID(incident_id)
    incident = db.query(Incident).filter(Incident.id == uid).first()
    if not incident:
        return {"error": "Incident not found."}

    vehicle = db.query(Vehicle).filter(Vehicle.id == incident.vehicle_id).first()
    if not vehicle:
        return {"error": "Vehicle not found."}

    # Mark as analyzing
    incident.status = IncidentStatus.ANALYZING
    db.commit()

    action_log = []

    def log_action(action_type: str, description: str, tool_name: str, tool_input: dict, tool_output: dict, status: str = "SUCCESS"):
        action = AgentAction(
            incident_id=uid,
            action_type=AgentActionType(action_type),
            description=description,
            status=AgentActionStatus.SUCCESS if status == "SUCCESS" else AgentActionStatus.FAILED,
            tool_name=tool_name,
            tool_input=tool_input,
            tool_output=tool_output,
            completed_at=datetime.utcnow(),
        )
        db.add(action)
        db.flush()
        action_log.append({
            "id": str(action.id),
            "action_type": action_type,
            "description": description,
            "status": status,
            "tool_name": tool_name,
        })
        return action

    # Log analysis start
    log_action("ANALYZE_INCIDENT", f"Received maintenance report for vehicle {vehicle.fleet_number}", "analyze_incident", {"incident_id": incident_id}, {"status": "started"})

    # Select AI provider based on the user's runtime choice; fall back to the
    # other provider if the chosen one has no key, then demo mode if neither.
    ai_cfg = get_ai_config()
    chosen = ai_cfg.provider
    if chosen == "groq" and groq_is_configured():
        use_groq = True
    elif chosen == "gemini" and gemini_is_configured():
        use_groq = False
    elif groq_is_configured():
        use_groq = True
    elif gemini_is_configured():
        use_groq = False
    else:
        return await _demo_mode_analysis(incident, vehicle, db, log_action)

    provider = "Groq" if use_groq else "Gemini"
    logger.info("ai_provider_selected", provider=provider)

    async def _call_ai(system_prompt, message, tools, executor, final_tool_name=None):
        if use_groq:
            return await call_groq_with_tools(system_prompt, message, tools, executor, final_tool_name=final_tool_name)
        return await call_gemini_with_tools(system_prompt, message, tools, executor, final_tool_name=final_tool_name)

    # Tool executor — called by the AI during the agentic loop
    def execute_tool(tool_name: str, tool_args: dict) -> dict:
        try:
            if tool_name == "get_vehicle":
                result = tool_handlers.tool_get_vehicle(tool_args["fleet_number"], db)
                log_action("GET_VEHICLE", f"Retrieved vehicle {tool_args.get('fleet_number')}", tool_name, tool_args, result)
                return result

            elif tool_name == "get_vehicle_maintenance_history":
                result = tool_handlers.tool_get_maintenance_history(tool_args["vehicle_id"], db)
                log_action("GET_MAINTENANCE_HISTORY", "Retrieved maintenance history", tool_name, tool_args, {"record_count": result.get("record_count", 0)})
                return result

            elif tool_name == "create_maintenance_task":
                result = tool_handlers.tool_create_maintenance_task(
                    vehicle_id=tool_args["vehicle_id"],
                    incident_id=tool_args.get("incident_id", incident_id),
                    title=tool_args["title"],
                    description=tool_args["description"],
                    severity=tool_args["severity"],
                    db=db,
                )
                log_action("CREATE_MAINTENANCE_TASK", f"Created task: {tool_args.get('title')}", tool_name, tool_args, result)
                return result

            elif tool_name == "update_vehicle_status":
                result = tool_handlers.tool_update_vehicle_status(tool_args["vehicle_id"], tool_args["new_status"], db)
                log_action("UPDATE_VEHICLE_STATUS", f"Vehicle status → {tool_args.get('new_status')}", tool_name, tool_args, result)
                return result

            elif tool_name == "create_parts_request":
                result = tool_handlers.tool_create_parts_request(tool_args["task_id"], tool_args.get("parts", []), db)
                log_action("CREATE_PARTS_REQUEST", f"Created {result.get('count', 0)} parts requests", tool_name, tool_args, result)
                return result

            elif tool_name == "send_notification":
                result = tool_handlers.tool_send_notification(
                    recipient=tool_args.get("recipient", "Fleet Manager"),
                    subject=tool_args["subject"],
                    message=tool_args["message"],
                    channel=tool_args.get("channel", "IN_APP"),
                    related_entity_type=tool_args.get("related_entity_type"),
                    related_entity_id=tool_args.get("related_entity_id"),
                    db=db,
                )
                log_action("SEND_NOTIFICATION", f"Notification sent to {tool_args.get('recipient', 'Fleet Manager')}", tool_name, tool_args, result)
                return result

            elif tool_name == "submit_analysis":
                # Terminal tool: the model delivers its structured verdict here.
                # The loop returns these args as the final JSON, so there is
                # nothing to do but record it.
                log_action("ANALYZE_INCIDENT", "Submitted final incident analysis", tool_name, tool_args, {"received": True})
                return {"success": True}

            else:
                return {"error": f"Unknown tool: {tool_name}"}
        except Exception as e:
            logger.error("tool_execution_error", tool=tool_name, error=str(e))
            return {"error": str(e)}

    # Build the user message for Gemini
    user_message = f"""
Maintenance incident report:

Vehicle: {vehicle.fleet_number} ({vehicle.year} {vehicle.make} {vehicle.model})
Current Mileage: {vehicle.mileage:,} km
Report: {incident.description}

Incident ID: {incident_id}

Please analyze this incident. Start by retrieving the vehicle information and maintenance history,
then perform your analysis, create a maintenance task, update the vehicle status if necessary,
create parts requests, and send a notification to the fleet manager.

When every other tool call is complete, call submit_analysis exactly once with your final
assessment. Its arguments are:
{{
  "category": "<BRAKE_SYSTEM|ENGINE|TRANSMISSION|ELECTRICAL|SUSPENSION|COOLING_SYSTEM|FUEL_SYSTEM|EXHAUST|TIRES|BODY_DAMAGE|GENERAL_MAINTENANCE|UNKNOWN>",
  "severity": "<LOW|MEDIUM|HIGH|CRITICAL>",
  "vehicle_status": "<ACTIVE|MAINTENANCE_DUE|OUT_OF_SERVICE>",
  "summary": "<clear summary>",
  "possible_causes": ["<cause1>", "<cause2>"],
  "recommended_actions": ["<action1>", "<action2>"],
  "required_parts": [{{"name": "<part>", "quantity": <n>}}],
  "requires_manager_approval": <true|false>
}}
"""

    final_text, tool_call_log = await _call_ai(
        system_prompt=FLEET_AGENT_SYSTEM_PROMPT,
        message=user_message,
        tools=AGENT_TOOL_DEFINITIONS,
        executor=execute_tool,
        final_tool_name="submit_analysis",
    )

    if final_text is None and not tool_call_log:
        # The provider failed before doing anything at all — nothing has been
        # written for this incident yet, so the deterministic path is safe to run.
        logger.warning("ai_fallback", incident_id=incident_id, provider=provider)
        return await _demo_mode_analysis(incident, vehicle, db, log_action)

    # Parse structured output from AI
    analysis = _parse_analysis(final_text)
    if not analysis:
        retry_text, _ = await _call_ai(
            system_prompt=FLEET_AGENT_SYSTEM_PROMPT,
            message=f"Return ONLY the JSON analysis object for the incident. No other text.\n\n{user_message}",
            tools=[],
            executor=lambda t, a: {},
        )
        analysis = _parse_analysis(retry_text)

    if analysis:
        # Apply deterministic business rules on top of AI output
        analysis = _apply_business_rules(analysis)

        incident.severity = IncidentSeverity(analysis["severity"])
        incident.category = analysis["category"]
        incident.ai_analysis = analysis
        incident.status = IncidentStatus.AWAITING_APPROVAL if analysis.get("requires_manager_approval") else IncidentStatus.APPROVED
    else:
        # Tools already ran and were committed, so re-running the deterministic
        # path here would duplicate tasks and parts requests. Reset to NEW so the
        # incident can be retried, and report the failure instead of a blank success.
        incident.status = IncidentStatus.NEW
        logger.error("ai_analysis_parse_failed", incident_id=incident_id, provider=provider)
        db.commit()
        return {
            "incident_id": incident_id,
            "error": (
                f"{provider} completed its tool calls but did not return a usable "
                "analysis. The incident has been reset to NEW — try again, or pick a "
                "different model in Settings."
            ),
            "analysis": None,
            "agent_actions": action_log,
            "status": incident.status.value,
        }

    db.commit()

    return {
        "incident_id": incident_id,
        "analysis": analysis,
        "agent_actions": action_log,
        "status": incident.status.value,
    }


def _parse_analysis(text: Optional[str]) -> Optional[dict]:
    if not text:
        return None
    # Extract JSON from markdown code blocks if present
    import re
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    json_str = match.group(1) if match else text.strip()
    # Find JSON object in the text
    start = json_str.find("{")
    end = json_str.rfind("}") + 1
    if start == -1 or end == 0:
        return None
    try:
        data = json.loads(json_str[start:end])
        # Validate required fields
        if "severity" in data and "category" in data:
            return data
        return None
    except (json.JSONDecodeError, ValueError):
        return None


def _apply_business_rules(analysis: dict) -> dict:
    """Enforce deterministic rules — the backend decides, not the LLM."""
    severity = analysis.get("severity", "MEDIUM").upper()

    # Rule: CRITICAL → OUT_OF_SERVICE + requires approval
    if severity == "CRITICAL":
        analysis["vehicle_status"] = "OUT_OF_SERVICE"
        analysis["requires_manager_approval"] = True

    # Rule: HIGH → MAINTENANCE_DUE + requires approval
    elif severity == "HIGH":
        if analysis.get("vehicle_status") == "ACTIVE":
            analysis["vehicle_status"] = "MAINTENANCE_DUE"
        analysis["requires_manager_approval"] = True

    # Rule: LOW → no approval needed
    elif severity == "LOW":
        analysis["requires_manager_approval"] = False

    return analysis


async def _demo_mode_analysis(incident: Incident, vehicle: Vehicle, db: Session, log_action) -> dict:
    """Fallback analysis when Gemini API key is not configured — for local demo."""
    description = incident.description.lower()

    # Simple keyword-based classification for demo
    if any(word in description for word in ["brake", "braking", "pedal"]):
        analysis = {
            "category": "BRAKE_SYSTEM",
            "severity": "CRITICAL",
            "vehicle_status": "OUT_OF_SERVICE",
            "summary": "The reported symptoms indicate a potentially unsafe brake-system condition requiring immediate attention.",
            "possible_causes": ["Worn brake pads", "Damaged brake rotor", "Hydraulic brake fluid leak"],
            "recommended_actions": ["Stop vehicle operation immediately", "Inspect brake pads and rotors", "Check brake fluid level and lines"],
            "required_parts": [{"name": "Brake pads (front)", "quantity": 1}, {"name": "Brake pads (rear)", "quantity": 1}, {"name": "Brake fluid DOT 4", "quantity": 2}],
            "requires_manager_approval": True,
        }
    elif any(word in description for word in ["engine", "oil", "overheating", "coolant"]):
        analysis = {
            "category": "ENGINE",
            "severity": "HIGH",
            "vehicle_status": "MAINTENANCE_DUE",
            "summary": "Engine issue reported. Vehicle requires prompt inspection to prevent further damage.",
            "possible_causes": ["Low oil level", "Cooling system failure", "Engine wear"],
            "recommended_actions": ["Check engine oil level", "Inspect cooling system", "Schedule engine diagnostic"],
            "required_parts": [{"name": "Engine oil 15W-40", "quantity": 5}, {"name": "Oil filter", "quantity": 1}],
            "requires_manager_approval": True,
        }
    else:
        analysis = {
            "category": "GENERAL_MAINTENANCE",
            "severity": "MEDIUM",
            "vehicle_status": "MAINTENANCE_DUE",
            "summary": "Vehicle requires maintenance inspection based on the reported issue.",
            "possible_causes": ["Normal wear", "Deferred maintenance"],
            "recommended_actions": ["Schedule full vehicle inspection", "Check all fluid levels"],
            "required_parts": [],
            "requires_manager_approval": False,
        }

    analysis = _apply_business_rules(analysis)

    # Log demo tool calls
    log_action("GET_VEHICLE", f"Retrieved vehicle {vehicle.fleet_number} (demo mode)", "get_vehicle", {"fleet_number": vehicle.fleet_number}, {"found": True, "fleet_number": vehicle.fleet_number})
    log_action("GET_MAINTENANCE_HISTORY", "Retrieved maintenance history (demo mode)", "get_vehicle_maintenance_history", {"vehicle_id": str(vehicle.id)}, {"record_count": 3})
    log_action("ANALYZE_INCIDENT", "Analysis complete (demo mode — configure GEMINI_API_KEY for live AI)", "analyze_incident", {}, analysis)

    # Execute business actions
    task_result = tool_handlers.tool_create_maintenance_task(
        vehicle_id=str(vehicle.id),
        incident_id=str(incident.id),
        title=f"MR-{vehicle.fleet_number.replace('-', '')}: {analysis['category'].replace('_', ' ').title()} Issue",
        description=analysis["summary"],
        severity=analysis["severity"],
        db=db,
    )
    log_action("CREATE_MAINTENANCE_TASK", f"Created maintenance task: {task_result.get('title', '')}", "create_maintenance_task", {}, task_result)

    if task_result.get("success") and analysis.get("required_parts"):
        parts_result = tool_handlers.tool_create_parts_request(
            task_id=task_result["task_id"],
            parts=analysis["required_parts"],
            db=db,
        )
        log_action("CREATE_PARTS_REQUEST", f"Created {parts_result.get('count', 0)} parts requests", "create_parts_request", {}, parts_result)

    status_result = tool_handlers.tool_update_vehicle_status(str(vehicle.id), analysis["vehicle_status"], db)
    log_action("UPDATE_VEHICLE_STATUS", f"Vehicle status → {analysis['vehicle_status']}", "update_vehicle_status", {}, status_result)

    notif_result = tool_handlers.tool_send_notification(
        recipient="Fleet Manager",
        subject=f"[{analysis['severity']}] {analysis['category'].replace('_', ' ').title()} — {vehicle.fleet_number}",
        message=analysis["summary"],
        channel="IN_APP",
        related_entity_type="incident",
        related_entity_id=str(incident.id),
        db=db,
    )
    log_action("SEND_NOTIFICATION", f"Notification sent to Fleet Manager", "send_notification", {}, notif_result)

    incident.severity = IncidentSeverity(analysis["severity"])
    incident.category = analysis["category"]
    incident.ai_analysis = analysis
    incident.status = IncidentStatus.AWAITING_APPROVAL if analysis.get("requires_manager_approval") else IncidentStatus.APPROVED
    db.commit()

    return {
        "incident_id": str(incident.id),
        "analysis": analysis,
        "agent_actions": [],
        "status": incident.status.value,
        "demo_mode": True,
    }
