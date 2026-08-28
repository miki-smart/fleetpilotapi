"""
NHTSA integrations (free, no API key):
  - vPIC DecodeVin       → manufacturer specifications for a VIN
  - Recalls by vehicle   → open safety recall campaigns for a make/model/year

Both fail gracefully — the application keeps working without NHTSA. Synchronous
variants exist because the agent tool executor is synchronous; the async wrappers
run them off the event loop for the HTTP routes.
"""
import asyncio
import httpx
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_TIMEOUT = 8.0


def _get_json(url: str, params: dict | None, label: str) -> dict | None:
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            response = client.get(url, params=params)
            response.raise_for_status()
            return response.json()
    except httpx.TimeoutException:
        logger.warning(f"{label}_timeout", url=url)
        return {"error": "NHTSA API timed out."}
    except httpx.HTTPStatusError as e:
        logger.warning(f"{label}_http_error", status=e.response.status_code)
        return {"error": f"NHTSA returned {e.response.status_code}."}
    except Exception as e:
        logger.error(f"{label}_error", error=str(e))
        return {"error": "NHTSA API unavailable."}


def decode_vin_sync(vin: str) -> dict:
    settings = get_settings()
    vin = (vin or "").strip().upper()
    if len(vin) != 17:
        return {"error": "VIN must be exactly 17 characters.", "vin": vin}

    data = _get_json(f"{settings.nhtsa_base_url}/vehicles/DecodeVin/{vin}", {"format": "json"}, "nhtsa_vpic")
    if not data or "error" in data:
        return {**(data or {"error": "NHTSA API unavailable."}), "vin": vin}

    results = data.get("Results", [])
    decoded = {r["Variable"]: r["Value"] for r in results if r.get("Value") and r["Value"] != "Not Applicable"}

    return {
        "vin": vin,
        "make": decoded.get("Make"),
        "model": decoded.get("Model"),
        "year": decoded.get("Model Year"),
        "body_class": decoded.get("Body Class"),
        "fuel_type": decoded.get("Fuel Type - Primary"),
        "engine_displacement": decoded.get("Displacement (L)"),
        "engine_cylinders": decoded.get("Engine Number of Cylinders"),
        "drive_type": decoded.get("Drive Type"),
        "gvwr_class": decoded.get("Gross Vehicle Weight Rating From"),
        "brake_system": decoded.get("Brake System Type"),
        "manufacturer": decoded.get("Manufacturer Name"),
        "plant_country": decoded.get("Plant Country"),
        "vehicle_type": decoded.get("Vehicle Type"),
        "error_code": decoded.get("Error Code"),
        "error_text": decoded.get("Error Text"),
    }


def get_recalls_sync(make: str, model: str, year: int | str) -> dict:
    settings = get_settings()
    params = {"make": (make or "").strip(), "model": (model or "").strip(), "modelYear": str(year).strip()}
    base = {"make": params["make"], "model": params["model"], "year": params["modelYear"], "source": "nhtsa"}

    data = _get_json(f"{settings.nhtsa_recalls_base_url}/recalls/recallsByVehicle", params, "nhtsa_recalls")
    if not data or "error" in data:
        return {**base, **(data or {"error": "NHTSA API unavailable."}), "recall_count": 0, "recalls": []}

    results = data.get("results", []) or []
    recalls = [
        {
            "campaign_number": r.get("NHTSACampaignNumber"),
            "component": r.get("Component"),
            "summary": (r.get("Summary") or "")[:400],
            "consequence": (r.get("Consequence") or "")[:300],
            "remedy": (r.get("Remedy") or "")[:300],
            "report_date": r.get("ReportReceivedDate"),
            "park_outside": bool(r.get("parkOutSide") or r.get("ParkOutSide")),
            "do_not_drive": bool(r.get("overTheAirUpdate") is False and r.get("doNotDrive")) if "doNotDrive" in r else False,
        }
        for r in results[:10]
    ]
    return {**base, "recall_count": len(results), "recalls": recalls}


async def decode_vin_from_nhtsa(vin: str) -> dict:
    return await asyncio.to_thread(decode_vin_sync, vin)


async def get_recalls(make: str, model: str, year: int | str) -> dict:
    return await asyncio.to_thread(get_recalls_sync, make, model, year)
