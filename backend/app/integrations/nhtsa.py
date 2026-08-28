"""
NHTSA vPIC API integration for VIN decoding.
Fails gracefully — application works without NHTSA.
"""
import httpx
from typing import Optional
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_TIMEOUT = 8.0


async def decode_vin_from_nhtsa(vin: str) -> dict:
    settings = get_settings()
    url = f"{settings.nhtsa_base_url}/vehicles/DecodeVin/{vin}?format=json"

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
    except httpx.TimeoutException:
        logger.warning("nhtsa_timeout", vin=vin)
        return {"error": "NHTSA API timed out.", "vin": vin}
    except httpx.HTTPStatusError as e:
        logger.warning("nhtsa_http_error", vin=vin, status=e.response.status_code)
        return {"error": f"NHTSA returned {e.response.status_code}.", "vin": vin}
    except Exception as e:
        logger.error("nhtsa_error", vin=vin, error=str(e))
        return {"error": "NHTSA API unavailable.", "vin": vin}

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
        "drive_type": decoded.get("Drive Type"),
        "manufacturer": decoded.get("Manufacturer Name"),
        "plant_country": decoded.get("Plant Country"),
        "vehicle_type": decoded.get("Vehicle Type"),
        "error_code": decoded.get("Error Code"),
        "error_text": decoded.get("Error Text"),
    }
