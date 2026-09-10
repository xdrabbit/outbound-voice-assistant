from typing import Any

import httpx

from app.config import settings


VAPI_BASE = "https://api.vapi.ai"


class VapiError(RuntimeError):
    pass


def _headers() -> dict[str, str]:
    if not settings.vapi_api_key:
        raise VapiError("VAPI_API_KEY is not set")
    return {
        "Authorization": f"Bearer {settings.vapi_api_key}",
        "Content-Type": "application/json",
    }


def create_outbound_call(
    *,
    to_number: str,
    assistant_id: str | None = None,
    assistant_overrides: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "phoneNumberId": settings.vapi_phone_number_id,
        "customer": {"number": to_number},
        "assistantId": assistant_id or settings.vapi_assistant_id,
    }
    if assistant_overrides:
        payload["assistantOverrides"] = assistant_overrides
    if metadata:
        payload["metadata"] = metadata

    with httpx.Client(timeout=30) as client:
        res = client.post(f"{VAPI_BASE}/call", headers=_headers(), json=payload)
        if res.status_code >= 400:
            raise VapiError(f"{res.status_code}: {res.text}")
        return res.json()


def upsert_assistant(payload: dict[str, Any], assistant_id: str | None = None) -> dict[str, Any]:
    with httpx.Client(timeout=30) as client:
        if assistant_id:
            res = client.patch(
                f"{VAPI_BASE}/assistant/{assistant_id}",
                headers=_headers(),
                json=payload,
            )
        else:
            res = client.post(f"{VAPI_BASE}/assistant", headers=_headers(), json=payload)
        if res.status_code >= 400:
            raise VapiError(f"{res.status_code}: {res.text}")
        return res.json()
