"""
Fleet agent tool definitions (JSON-Schema style).

Consumed by both the Gemini function-calling adapter and the Groq/OpenAI-compatible
adapter. Every array of objects declares its item properties explicitly — Gemini
rejects OBJECT schemas with no properties.
"""

PART_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "Part name, e.g. 'Brake pads (front)'."},
        "quantity": {"type": "integer", "description": "Quantity required (default 1)."},
    },
    "required": ["name"],
}

AGENT_TOOL_DEFINITIONS = [
    {
        "name": "get_vehicle",
        "description": "Retrieve vehicle information from the fleet database using the fleet number (e.g. ET-042).",
        "parameters": {
            "type": "object",
            "properties": {
                "fleet_number": {"type": "string", "description": "The vehicle fleet number, e.g. ET-042"},
            },
            "required": ["fleet_number"],
        },
    },
    {
        "name": "get_vehicle_maintenance_history",
        "description": "Retrieve the maintenance history for a vehicle using its internal vehicle_id UUID.",
        "parameters": {
            "type": "object",
            "properties": {
                "vehicle_id": {"type": "string", "description": "The vehicle UUID returned by get_vehicle."},
            },
            "required": ["vehicle_id"],
        },
    },
    {
        "name": "decode_vin",
        "description": (
            "Decode a 17-character VIN with the NHTSA vPIC API to get manufacturer specifications "
            "(body class, engine displacement, drive type, fuel type, GVWR class). Use it to confirm "
            "the vehicle's identity or when the fleet record lacks technical detail."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "vin": {"type": "string", "description": "17-character VIN from the vehicle record."},
            },
            "required": ["vin"],
        },
    },
    {
        "name": "check_safety_recalls",
        "description": (
            "Look up open NHTSA safety recall campaigns for a make/model/year. Use it to check whether "
            "the reported symptom matches a known manufacturer defect (e.g. a brake complaint on a "
            "vehicle with an open brake recall)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "make": {"type": "string", "description": "Manufacturer, e.g. Ford"},
                "model": {"type": "string", "description": "Model, e.g. Transit"},
                "year": {"type": "integer", "description": "Model year, e.g. 2020"},
            },
            "required": ["make", "model", "year"],
        },
    },
    {
        "name": "create_maintenance_task",
        "description": "Create a new maintenance task for a vehicle based on the incident analysis.",
        "parameters": {
            "type": "object",
            "properties": {
                "vehicle_id": {"type": "string", "description": "Vehicle UUID."},
                "incident_id": {"type": "string", "description": "Incident UUID (optional)."},
                "title": {"type": "string", "description": "Short task title, e.g. 'MR-1042: Critical Brake System Inspection'."},
                "description": {"type": "string", "description": "Detailed description of the required work."},
                "severity": {"type": "string", "description": "LOW | MEDIUM | HIGH | CRITICAL"},
            },
            "required": ["vehicle_id", "title", "description", "severity"],
        },
    },
    {
        "name": "update_vehicle_status",
        "description": "Update the operational status of a vehicle.",
        "parameters": {
            "type": "object",
            "properties": {
                "vehicle_id": {"type": "string", "description": "Vehicle UUID."},
                "new_status": {"type": "string", "description": "ACTIVE | MAINTENANCE_DUE | OUT_OF_SERVICE"},
            },
            "required": ["vehicle_id", "new_status"],
        },
    },
    {
        "name": "create_parts_request",
        "description": "Create parts requests for a maintenance task.",
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Maintenance task UUID."},
                "parts": {
                    "type": "array",
                    "description": "List of parts needed.",
                    "items": PART_ITEM_SCHEMA,
                },
            },
            "required": ["task_id", "parts"],
        },
    },
    {
        "name": "send_notification",
        "description": (
            "Notify a stakeholder. Use channel EMAIL with recipient 'Fleet Manager' for CRITICAL and HIGH "
            "incidents — the backend resolves the manager's address. Use IN_APP for informational updates."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "recipient": {"type": "string", "description": "Recipient role or email, e.g. 'Fleet Manager'."},
                "subject": {"type": "string", "description": "Notification subject."},
                "message": {"type": "string", "description": "Notification message body."},
                "channel": {"type": "string", "description": "EMAIL | IN_APP"},
                "related_entity_type": {"type": "string", "description": "e.g. 'incident' or 'maintenance_task'"},
                "related_entity_id": {"type": "string", "description": "UUID of the related entity."},
            },
            "required": ["recipient", "subject", "message"],
        },
    },
    {
        "name": "submit_analysis",
        "description": (
            "Submit the final structured analysis for the incident. Call this exactly once, as your "
            "LAST action, after every other tool call is complete. Calling it ends the analysis."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "BRAKE_SYSTEM | ENGINE | TRANSMISSION | ELECTRICAL | SUSPENSION | COOLING_SYSTEM | FUEL_SYSTEM | EXHAUST | TIRES | BODY_DAMAGE | GENERAL_MAINTENANCE | UNKNOWN",
                },
                "severity": {"type": "string", "description": "LOW | MEDIUM | HIGH | CRITICAL"},
                "vehicle_status": {"type": "string", "description": "ACTIVE | MAINTENANCE_DUE | OUT_OF_SERVICE"},
                "summary": {"type": "string", "description": "Clear summary of the assessment."},
                "possible_causes": {"type": "array", "items": {"type": "string"}, "description": "Likely causes of the reported symptoms."},
                "recommended_actions": {"type": "array", "items": {"type": "string"}, "description": "Actions the workshop should take."},
                "required_parts": {"type": "array", "description": "Parts needed for the repair.", "items": PART_ITEM_SCHEMA},
                "related_recalls": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "NHTSA campaign numbers from check_safety_recalls that plausibly relate to the reported symptom.",
                },
                "requires_manager_approval": {"type": "boolean", "description": "Whether a fleet manager must approve before work proceeds."},
            },
            "required": ["category", "severity", "summary"],
        },
    },
]
