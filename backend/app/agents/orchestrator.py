"""
Agent orchestrator — coordinates LLM tool-calling with deterministic business logic.

Gemini is the primary provider; Groq is a switchable alternative. If no provider is
configured, or the provider fails before doing any work, a keyword-based demo mode
runs the same tool chain so every UI flow still works.

The model recommends; the backend guarantees. After the model's final verdict,
`_enforce_actions` makes sure the consequences of that severity actually happened
(task exists, vehicle status escalated, manager emailed) even if the model skipped a
tool call.
"""
import json
import re
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session

from app.agents.prompts import FLEET_AGENT_SYSTEM_PROMPT
from app.agents.fleet_agent import AGENT_TOOL_DEFINITIONS
from app.agents.schemas import IncidentAnalysis, IncidentCategory
from app.agents import tools as tool_handlers
from app.integrations.groq_client import call_groq_with_tools
from app.integrations.gemini import call_gemini_with_tools
from app.integrations.llm import select_provider, fallback_provider, provider_label
from app.integrations.notification import NotificationService
from app.database.models import (
    Incident, Vehicle, AgentAction,
    IncidentStatus, IncidentSeverity,
    AgentActionType, AgentActionStatus,
)
from app.core.logging import get_logger

logger = get_logger(__name__)

SEVERITIES = ("LOW", "MEDIUM", "HIGH", "CRITICAL")
VEHICLE_STATUSES = ("ACTIVE", "MAINTENANCE_DUE", "OUT_OF_SERVICE")
_STATUS_RANK = {"ACTIVE": 0, "MAINTENANCE_DUE": 1, "OUT_OF_SERVICE": 2}


async def run_incident_analysis(incident_id: str, db: Session) -> dict:
    """
    Main agent entry point.
    1. Load the incident.
    2. Run the agentic tool loop (Gemini or Groq).
    3. Normalize + apply business rules to the AI output.
    4. Enforce the consequences the rules demand.
    5. Persist and return a structured summary for the frontend.
    """
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

    action_log: list[dict] = []
    # What the model actually accomplished — consulted by the deterministic safety net.
    outcome = {"task_id": None, "email_sent": False}

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
        # Commit per action so the UI can poll the incident and render the timeline live.
        db.commit()
        action_log.append({
            "id": str(action.id),
            "action_type": action_type,
            "description": description,
            "status": status,
            "tool_name": tool_name,
        })
        return action

    log_action("ANALYZE_INCIDENT", f"Received maintenance report for vehicle {vehicle.fleet_number}", "analyze_incident", {"incident_id": incident_id}, {"status": "started"})

    provider = select_provider()
    if provider is None:
        return await _demo_mode_analysis(incident, vehicle, db, log_action, action_log, reason="no AI provider key configured")

    logger.info("ai_provider_selected", provider=provider)

    async def _call_ai(system_prompt, message, tools, executor, final_tool_name=None):
        if provider == "groq":
            return await call_groq_with_tools(system_prompt, message, tools, executor, final_tool_name=final_tool_name)
        return await call_gemini_with_tools(system_prompt, message, tools, executor, final_tool_name=final_tool_name)

    # Tool executor — called by the AI during the agentic loop
    def execute_tool(tool_name: str, tool_args: dict) -> dict:
        try:
            if tool_name == "get_vehicle":
                result = tool_handlers.tool_get_vehicle(tool_args.get("fleet_number") or vehicle.fleet_number, db)
                log_action("GET_VEHICLE", f"Retrieved vehicle {tool_args.get('fleet_number', vehicle.fleet_number)}", tool_name, tool_args, result)
                return result

            elif tool_name == "get_vehicle_maintenance_history":
                result = tool_handlers.tool_get_maintenance_history(tool_args.get("vehicle_id") or str(vehicle.id), db)
                log_action("GET_MAINTENANCE_HISTORY", f"Retrieved maintenance history — {result.get('record_count', 0)} records", tool_name, tool_args, {"record_count": result.get("record_count", 0)})
                return result

            elif tool_name == "decode_vin":
                result = tool_handlers.tool_decode_vin(tool_args.get("vin") or vehicle.vin or "", db)
                label = f"{result.get('year') or ''} {result.get('make') or ''} {result.get('model') or ''}".strip() or "no match"
                log_action("DECODE_VIN", f"Decoded VIN via NHTSA vPIC — {label}", tool_name, tool_args, result)
                return result

            elif tool_name == "check_safety_recalls":
                result = tool_handlers.tool_check_recalls(
                    tool_args.get("make") or vehicle.make,
                    tool_args.get("model") or vehicle.model,
                    tool_args.get("year") or vehicle.year,
                )
                count = result.get("recall_count", 0)
                campaigns = [r.get("campaign_number") for r in result.get("recalls", [])][:5]
                log_action("CHECK_RECALLS", f"NHTSA recall check — {count} open campaign(s)" + (f": {', '.join(c for c in campaigns if c)}" if campaigns else ""), tool_name, tool_args, {"recall_count": count, "campaigns": campaigns, "error": result.get("error")})
                return result

            elif tool_name == "create_maintenance_task":
                result = tool_handlers.tool_create_maintenance_task(
                    vehicle_id=tool_args.get("vehicle_id") or str(vehicle.id),
                    incident_id=tool_args.get("incident_id") or incident_id,
                    title=tool_args.get("title", "Maintenance task"),
                    description=tool_args.get("description", ""),
                    severity=tool_args.get("severity", "MEDIUM"),
                    db=db,
                )
                if result.get("success"):
                    outcome["task_id"] = result["task_id"]
                log_action("CREATE_MAINTENANCE_TASK", f"Created task: {tool_args.get('title')}", tool_name, tool_args, result, "SUCCESS" if result.get("success") else "FAILED")
                return result

            elif tool_name == "update_vehicle_status":
                result = tool_handlers.tool_update_vehicle_status(tool_args.get("vehicle_id") or str(vehicle.id), tool_args.get("new_status", ""), db)
                log_action("UPDATE_VEHICLE_STATUS", f"Vehicle status → {tool_args.get('new_status')}", tool_name, tool_args, result, "SUCCESS" if result.get("success") else "FAILED")
                return result

            elif tool_name == "create_parts_request":
                result = tool_handlers.tool_create_parts_request(tool_args.get("task_id") or outcome["task_id"] or "", tool_args.get("parts", []), db)
                log_action("CREATE_PARTS_REQUEST", f"Created {result.get('count', 0)} parts requests", tool_name, tool_args, result, "SUCCESS" if result.get("success") else "FAILED")
                return result

            elif tool_name == "send_notification":
                result = tool_handlers.tool_send_notification(
                    recipient=tool_args.get("recipient", "Fleet Manager"),
                    subject=tool_args.get("subject", f"FleetPilot update — {vehicle.fleet_number}"),
                    message=tool_args.get("message", ""),
                    channel=tool_args.get("channel", "IN_APP"),
                    related_entity_type=tool_args.get("related_entity_type") or "incident",
                    related_entity_id=tool_args.get("related_entity_id") or incident_id,
                    db=db,
                )
                if result.get("success") and result.get("channel") == "EMAIL":
                    outcome["email_sent"] = True
                log_action("SEND_NOTIFICATION", f"{result.get('channel', 'IN_APP').replace('_', '-').title()} notification → {result.get('recipient', 'Fleet Manager')} ({result.get('status')})", tool_name, tool_args, result)
                return result

            elif tool_name == "submit_analysis":
                # Terminal tool: the model delivers its structured verdict here.
                log_action("ANALYZE_INCIDENT", "Submitted final incident analysis", tool_name, tool_args, {"received": True})
                return {"success": True}

            else:
                return {"error": f"Unknown tool: {tool_name}"}
        except Exception as e:
            logger.error("tool_execution_error", tool=tool_name, error=str(e))
            db.rollback()
            return {"error": str(e)}

    user_message = f"""
Maintenance incident report:

Vehicle: {vehicle.fleet_number} ({vehicle.year} {vehicle.make} {vehicle.model})
VIN: {vehicle.vin or 'not recorded'}
Current Mileage: {vehicle.mileage:,} km
Reported by: {incident.reported_by}
Report: {incident.description}

Incident ID: {incident_id}

Please analyze this incident. Start by retrieving the vehicle information and maintenance history,
check open NHTSA safety recalls for this make/model/year, then perform your analysis, create a
maintenance task, update the vehicle status if necessary, create parts requests, and notify the
fleet manager (channel EMAIL for CRITICAL/HIGH).

When every other tool call is complete, call submit_analysis exactly once with your final assessment.
"""

    final_text, tool_call_log = await _call_ai(
        system_prompt=FLEET_AGENT_SYSTEM_PROMPT,
        message=user_message,
        tools=AGENT_TOOL_DEFINITIONS,
        executor=execute_tool,
        final_tool_name="submit_analysis",
    )

    if final_text is None and not tool_call_log:
        # The provider failed before doing anything at all (rate limit, suspended key,
        # outage). Nothing has been written yet, so fail over to the other configured
        # provider and rerun the loop from scratch.
        alt = fallback_provider(provider)
        if alt:
            logger.warning("ai_provider_failover", **{"from": provider, "to": alt, "incident_id": incident_id})
            log_action("ANALYZE_INCIDENT", f"{provider_label(provider)} unavailable (rate limit or key problem) — failing over to {provider_label(alt)}", "provider_failover", {"from": provider, "to": alt}, {"status": "retrying"})
            provider = alt
            final_text, tool_call_log = await _call_ai(
                system_prompt=FLEET_AGENT_SYSTEM_PROMPT,
                message=user_message,
                tools=AGENT_TOOL_DEFINITIONS,
                executor=execute_tool,
                final_tool_name="submit_analysis",
            )

    if final_text is None and not tool_call_log:
        # Every configured provider failed before doing any work — the deterministic
        # path is safe to run.
        logger.warning("ai_fallback", incident_id=incident_id, provider=provider)
        return await _demo_mode_analysis(incident, vehicle, db, log_action, action_log, reason=f"{provider_label(provider)} API call failed")

    analysis = _parse_analysis(final_text)
    analysis_source = "model"
    if not analysis:
        # One more chance, with the record of what the tools already did.
        retry_text, _ = await _call_ai(
            system_prompt=FLEET_AGENT_SYSTEM_PROMPT,
            message=(
                "Return ONLY the JSON analysis object for the incident (keys: category, severity, vehicle_status, "
                "summary, possible_causes, recommended_actions, required_parts, related_recalls, requires_manager_approval). "
                f"No other text.\n\n{user_message}\n\nTool calls already executed:\n{_compact_tool_log(tool_call_log)}"
            ),
            tools=[],
            executor=lambda t, a: {},
        )
        analysis = _parse_analysis(retry_text)

    if not analysis:
        # The provider stopped (typically a free-tier rate limit) after doing the work
        # but before submitting the verdict. Rebuild the verdict from the actions that
        # actually ran rather than leaving a half-processed incident.
        analysis = _synthesize_analysis(incident, tool_call_log)
        if analysis:
            analysis_source = "synthesized_from_actions"
            log_action("ANALYZE_INCIDENT", f"{provider_label(provider)} stopped before submit_analysis — verdict synthesized from the executed actions", "synthesize_analysis", {}, {"tool_calls": len(tool_call_log)})

    if not analysis:
        # Tools already ran and were committed, so re-running the deterministic
        # path here would duplicate tasks and parts requests. Reset to NEW so the
        # incident can be retried, and report the failure instead of a blank success.
        incident.status = IncidentStatus.NEW
        logger.error("ai_analysis_parse_failed", incident_id=incident_id, provider=provider)
        db.commit()
        return {
            "incident_id": incident_id,
            "error": (
                f"{provider_label(provider)} completed its tool calls but did not return a usable "
                "analysis. The incident has been reset to NEW — try again, or pick a "
                "different model in Settings."
            ),
            "analysis": None,
            "agent_actions": action_log,
            "status": incident.status.value,
            "provider": provider_label(provider),
        }

    analysis = _apply_business_rules(analysis)
    _enforce_actions(incident, vehicle, analysis, outcome, db, log_action)

    incident.severity = IncidentSeverity(analysis["severity"])
    incident.category = analysis["category"]
    incident.ai_analysis = analysis
    incident.status = IncidentStatus.AWAITING_APPROVAL if analysis.get("requires_manager_approval") else IncidentStatus.APPROVED
    db.commit()

    return {
        "incident_id": incident_id,
        "analysis": analysis,
        "analysis_source": analysis_source,
        "agent_actions": action_log,
        "status": incident.status.value,
        "provider": provider_label(provider),
        "demo_mode": False,
    }


# --- parsing / normalization -------------------------------------------------------

_CATEGORY_KEYWORDS = [
    ("BRAKE_SYSTEM", ("brake", "braking", "pedal", "abs")),
    ("COOLING_SYSTEM", ("coolant", "radiator", "overheat", "temperature")),
    ("ENGINE", ("engine", "oil", "misfire", "stall", "knock", "power loss")),
    ("TRANSMISSION", ("transmission", "gear", "clutch", "shift")),
    ("ELECTRICAL", ("electrical", "battery", "wiring", "cluster", "dashboard", "light", "alternator", "fuse")),
    ("SUSPENSION", ("suspension", "shock", "spring", "steering", "vibration")),
    ("FUEL_SYSTEM", ("fuel", "injector", "diesel leak")),
    ("EXHAUST", ("exhaust", "smoke", "muffler")),
    ("TIRES", ("tyre", "tire", "puncture", "wheel")),
    ("BODY_DAMAGE", ("body", "dent", "windshield", "windscreen", "door", "mirror")),
]


def _keyword_category(*texts: str) -> str:
    blob = " ".join(t or "" for t in texts).lower()
    for category, words in _CATEGORY_KEYWORDS:
        if any(w in blob for w in words):
            return category
    return "GENERAL_MAINTENANCE"


def _compact_tool_log(tool_call_log: list[dict]) -> str:
    lines = []
    for call in tool_call_log:
        result = call.get("result") or {}
        summary = {k: result[k] for k in ("success", "severity", "status", "new_status", "recall_count", "count") if k in result}
        lines.append(f"- {call['tool']}({json.dumps(call.get('args', {}), default=str)[:300]}) -> {json.dumps(summary, default=str)}")
    return "\n".join(lines) or "(none)"


def _synthesize_analysis(incident: Incident, tool_call_log: list[dict]) -> Optional[dict]:
    """Rebuild a verdict from the model's own successful tool calls. Only possible when a
    task was created — its severity and description are the model's stated assessment."""
    def first(tool: str, ok_only: bool = True):
        for call in tool_call_log:
            if call["tool"] == tool and (not ok_only or (call.get("result") or {}).get("success")):
                return call
        return None

    task_call = first("create_maintenance_task")
    if not task_call:
        return None
    args = task_call.get("args") or {}
    status_call = first("update_vehicle_status")
    parts_call = first("create_parts_request")
    recalls_call = first("check_safety_recalls", ok_only=False)
    recall_count = (recalls_call or {}).get("result", {}).get("recall_count", 0) if recalls_call else 0

    severity = str(args.get("severity", "MEDIUM")).upper()
    summary = args.get("description") or incident.description
    recommended = [f"Execute work order: {args.get('title')}"] if args.get("title") else []
    if recall_count:
        recommended.append(f"Verify the {recall_count} open NHTSA recall campaign(s) for this model by VIN with the dealer")

    return _normalize_analysis({
        "category": _keyword_category(incident.description, args.get("title", ""), args.get("description", "")),
        "severity": severity if severity in SEVERITIES else "MEDIUM",
        "vehicle_status": ((status_call or {}).get("args") or {}).get("new_status", ""),
        "summary": summary,
        "possible_causes": [],
        "recommended_actions": recommended,
        "required_parts": ((parts_call or {}).get("args") or {}).get("parts", []),
        "related_recalls": [],
        "requires_manager_approval": severity in ("CRITICAL", "HIGH"),
    })

def _parse_analysis(text: Optional[str]) -> Optional[dict]:
    if not text:
        return None
    # Extract JSON from markdown code blocks if present
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    json_str = match.group(1) if match else text.strip()
    start = json_str.find("{")
    end = json_str.rfind("}") + 1
    if start == -1 or end == 0:
        return None
    try:
        data = json.loads(json_str[start:end])
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, dict) or "severity" not in data or "category" not in data:
        return None
    return _normalize_analysis(data)


def _normalize_analysis(data: dict) -> Optional[dict]:
    """Coerce the model's verdict into the validated IncidentAnalysis shape.
    Unknown categories become UNKNOWN; an invalid severity rejects the verdict."""
    severity = str(data.get("severity", "")).strip().upper()
    if severity not in SEVERITIES:
        return None

    category = str(data.get("category", "UNKNOWN")).strip().upper().replace(" ", "_").replace("-", "_")
    if category not in IncidentCategory.__members__:
        category = "UNKNOWN"

    vehicle_status = str(data.get("vehicle_status", "")).strip().upper()
    if vehicle_status not in VEHICLE_STATUSES:
        vehicle_status = {"CRITICAL": "OUT_OF_SERVICE", "HIGH": "MAINTENANCE_DUE"}.get(severity, "ACTIVE")

    def _str_list(value) -> list[str]:
        if isinstance(value, str):
            return [value] if value.strip() else []
        return [str(v) for v in (value or []) if str(v).strip()]

    parts = []
    for p in data.get("required_parts") or []:
        if isinstance(p, str):
            parts.append({"name": p, "quantity": 1})
        elif isinstance(p, dict) and str(p.get("name", "")).strip():
            parts.append({"name": str(p["name"]), "quantity": max(1, tool_handlers._to_int(p.get("quantity", 1), 1))})

    try:
        validated = IncidentAnalysis(
            category=category,
            severity=severity,
            vehicle_status=vehicle_status,
            summary=str(data.get("summary") or ""),
            possible_causes=_str_list(data.get("possible_causes")),
            recommended_actions=_str_list(data.get("recommended_actions")),
            required_parts=parts,
            related_recalls=_str_list(data.get("related_recalls")),
            requires_manager_approval=bool(data.get("requires_manager_approval", False)),
        )
    except Exception as e:  # pydantic ValidationError
        logger.warning("analysis_validation_failed", error=str(e)[:200])
        return None
    return validated.model_dump(mode="json")


def _apply_business_rules(analysis: dict) -> dict:
    """Enforce deterministic rules — the backend decides, not the LLM."""
    severity = analysis.get("severity", "MEDIUM").upper()

    # Rule: CRITICAL → OUT_OF_SERVICE + requires approval
    if severity == "CRITICAL":
        analysis["vehicle_status"] = "OUT_OF_SERVICE"
        analysis["requires_manager_approval"] = True

    # Rule: HIGH → at least MAINTENANCE_DUE + requires approval
    elif severity == "HIGH":
        if analysis.get("vehicle_status") == "ACTIVE":
            analysis["vehicle_status"] = "MAINTENANCE_DUE"
        analysis["requires_manager_approval"] = True

    # Rule: LOW → no approval needed
    elif severity == "LOW":
        analysis["requires_manager_approval"] = False

    return analysis


def _enforce_actions(incident: Incident, vehicle: Vehicle, analysis: dict, outcome: dict, db: Session, log_action) -> None:
    """Deterministic safety net run after the model's verdict."""
    severity = analysis["severity"]

    # 1. Every analyzed incident gets a maintenance task (with its parts).
    if not outcome["task_id"]:
        result = tool_handlers.tool_create_maintenance_task(
            vehicle_id=str(vehicle.id),
            incident_id=str(incident.id),
            title=f"MR-{vehicle.fleet_number.replace('-', '')}: {analysis['category'].replace('_', ' ').title()} — {severity.title()}",
            description=analysis.get("summary") or incident.description,
            severity=severity,
            db=db,
        )
        log_action("CREATE_MAINTENANCE_TASK", "Created maintenance task (business rule: every incident gets a task)", "create_maintenance_task", {"severity": severity}, result)
        if result.get("success"):
            outcome["task_id"] = result["task_id"]
            if analysis.get("required_parts"):
                parts_result = tool_handlers.tool_create_parts_request(result["task_id"], analysis["required_parts"], db)
                log_action("CREATE_PARTS_REQUEST", f"Created {parts_result.get('count', 0)} parts requests", "create_parts_request", {}, parts_result)

    # 2. Vehicle status may only escalate as a result of an analysis.
    db.refresh(vehicle)
    target = analysis["vehicle_status"]
    if _STATUS_RANK[target] > _STATUS_RANK[vehicle.status.value]:
        result = tool_handlers.tool_update_vehicle_status(str(vehicle.id), target, db)
        log_action("UPDATE_VEHICLE_STATUS", f"Vehicle status → {target} (business rule for {severity})", "update_vehicle_status", {"new_status": target}, result)
    else:
        analysis["vehicle_status"] = vehicle.status.value

    # 3. CRITICAL/HIGH → the fleet manager gets an email, whatever the model did.
    if severity in ("CRITICAL", "HIGH") and not outcome["email_sent"]:
        notes = NotificationService(db).notify_critical_incident(incident, vehicle, analysis)
        statuses = {n.channel.value: n.status.value for n in notes}
        outcome["email_sent"] = statuses.get("EMAIL") in ("SENT", "SIMULATED")
        log_action("SEND_NOTIFICATION", f"Fleet manager notified — email {statuses.get('EMAIL', 'n/a').lower()}, in-app sent (business rule for {severity})", "send_notification", {"channel": "EMAIL"}, statuses)


# --- demo mode -----------------------------------------------------------------------

async def _demo_mode_analysis(incident: Incident, vehicle: Vehicle, db: Session, log_action, action_log: list, reason: str = "") -> dict:
    """Keyword-based fallback when no AI provider is available. Runs the same tool
    chain so tasks, notifications and the timeline still behave end-to-end."""
    description = incident.description.lower()

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
    elif any(word in description for word in ["engine", "oil", "overheating", "coolant", "temperature"]):
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

    analysis = _apply_business_rules(_normalize_analysis(analysis))

    suffix = f" (demo mode — {reason})" if reason else " (demo mode)"
    log_action("GET_VEHICLE", f"Retrieved vehicle {vehicle.fleet_number}{suffix}", "get_vehicle", {"fleet_number": vehicle.fleet_number}, {"found": True, "fleet_number": vehicle.fleet_number})
    history = tool_handlers.tool_get_maintenance_history(str(vehicle.id), db)
    log_action("GET_MAINTENANCE_HISTORY", f"Retrieved maintenance history — {history.get('record_count', 0)} records{suffix}", "get_vehicle_maintenance_history", {"vehicle_id": str(vehicle.id)}, {"record_count": history.get("record_count", 0)})
    recalls = tool_handlers.tool_check_recalls(vehicle.make, vehicle.model, vehicle.year)
    campaigns = [r.get("campaign_number") for r in recalls.get("recalls", [])][:5]
    log_action("CHECK_RECALLS", f"NHTSA recall check — {recalls.get('recall_count', 0)} open campaign(s){suffix}", "check_safety_recalls", {"make": vehicle.make, "model": vehicle.model, "year": vehicle.year}, {"recall_count": recalls.get("recall_count", 0), "campaigns": campaigns})
    log_action("ANALYZE_INCIDENT", f"Keyword classification: {analysis['severity']} / {analysis['category']}{suffix}", "analyze_incident", {}, analysis)

    outcome = {"task_id": None, "email_sent": False}
    _enforce_actions(incident, vehicle, analysis, outcome, db, log_action)

    if analysis["severity"] not in ("CRITICAL", "HIGH"):
        notif = tool_handlers.tool_send_notification(
            recipient="Fleet Manager",
            subject=f"[{analysis['severity']}] {analysis['category'].replace('_', ' ').title()} — {vehicle.fleet_number}",
            message=analysis["summary"],
            channel="IN_APP",
            related_entity_type="incident",
            related_entity_id=str(incident.id),
            db=db,
        )
        log_action("SEND_NOTIFICATION", "In-app notification → Fleet Manager", "send_notification", {}, notif)

    incident.severity = IncidentSeverity(analysis["severity"])
    incident.category = analysis["category"]
    incident.ai_analysis = analysis
    incident.status = IncidentStatus.AWAITING_APPROVAL if analysis.get("requires_manager_approval") else IncidentStatus.APPROVED
    db.commit()

    return {
        "incident_id": str(incident.id),
        "analysis": analysis,
        "agent_actions": action_log,
        "status": incident.status.value,
        "provider": "Demo mode",
        "demo_mode": True,
        "demo_reason": reason,
    }
