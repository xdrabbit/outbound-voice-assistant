from datetime import datetime, timedelta
import json

from fastapi import APIRouter, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.models import Call, Lead

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _db() -> Session:
    return SessionLocal()


def _find_call(db: Session, message: dict) -> Call | None:
    call_obj = message.get("call") or {}
    provider_id = call_obj.get("id") or ""
    metadata = call_obj.get("metadata") or message.get("metadata") or {}
    local_id = metadata.get("call_id")
    if provider_id:
        found = db.query(Call).filter(Call.provider_call_id == provider_id).first()
        if found:
            return found
    if local_id:
        return db.query(Call).filter(Call.id == int(local_id)).first()
    return None


@router.post("/vapi")
async def vapi_webhook(
    request: Request,
    x_vapi_secret: str | None = Header(default=None, alias="X-Vapi-Secret"),
):
    if settings.webhook_secret and x_vapi_secret and x_vapi_secret != settings.webhook_secret:
        raise HTTPException(status_code=401, detail="bad webhook secret")

    body = await request.json()
    message = body.get("message", body)
    msg_type = message.get("type")

    db = _db()
    try:
        if msg_type in {"tool-calls", "function-call"}:
            return handle_tools(db, message)
        if msg_type == "status-update":
            handle_status(db, message)
        elif msg_type == "end-of-call-report":
            handle_end(db, message)
        db.commit()
        return {"ok": True}
    finally:
        db.close()


def handle_status(db: Session, message: dict) -> None:
    call = _find_call(db, message)
    if not call:
        return
    call.status = message.get("status") or call.status
    if call.lead and call.status in {"ringing", "in-progress"}:
        call.lead.status = "in_progress"


def handle_end(db: Session, message: dict) -> None:
    call = _find_call(db, message)
    if not call:
        return
    artifact = message.get("artifact") or {}
    call.status = "ended"
    call.ended_reason = message.get("endedReason") or ""
    call.transcript = artifact.get("transcript") or ""
    recording = artifact.get("recording") or {}
    call.recording_url = recording.get("url") or recording.get("stereoUrl") or ""
    analysis = message.get("analysis") or {}
    call.summary = analysis.get("summary") or call.summary
    call.ended_at = datetime.utcnow()

    lead = call.lead
    if not lead:
        return
    reason = (call.ended_reason or "").lower()
    if lead.status in {"booked", "not_interested", "do_not_call"}:
        return
    if "voicemail" in reason:
        lead.status = "no_answer"
        lead.last_outcome = "voicemail"
        lead.next_attempt_at = datetime.utcnow() + timedelta(hours=settings.retry_hours)
    elif "no-answer" in reason or "customer-did-not-answer" in reason:
        lead.status = "no_answer"
        lead.last_outcome = "no_answer"
        lead.next_attempt_at = datetime.utcnow() + timedelta(hours=settings.retry_hours)
    else:
        lead.status = "completed"
        lead.last_outcome = call.ended_reason or "ended"


def handle_tools(db: Session, message: dict) -> dict:
    call = _find_call(db, message)
    results = []
    tool_calls = message.get("toolCallList") or []
    if not tool_calls and message.get("functionCall"):
        fc = message["functionCall"]
        tool_calls = [{"id": fc.get("id", "fn"), "name": fc.get("name"), "parameters": fc.get("parameters", {})}]

    for tool in tool_calls:
        name = tool.get("name")
        params = tool.get("parameters") or {}
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except json.JSONDecodeError:
                params = {"raw": params}
        result = apply_tool(db, call, name, params)
        results.append({"toolCallId": tool.get("id"), "result": result})

    return {"results": results}


def apply_tool(db: Session, call: Call | None, name: str, params: dict) -> str:
    lead = call.lead if call else None
    if name == "book_appointment" and lead:
        lead.status = "booked"
        lead.last_outcome = "booked"
        note = params.get("when", "")
        lead.notes = (lead.notes + f"\nBOOKED: {note} {params.get('notes','')}").strip()
        if call:
            call.summary = f"Booked for {note}"
        return f"Appointment recorded for {note}."
    if name == "schedule_callback" and lead:
        lead.status = "callback"
        lead.last_outcome = "callback"
        lead.next_attempt_at = datetime.utcnow() + timedelta(hours=settings.retry_hours)
        lead.notes = (lead.notes + f"\nCALLBACK: {params}").strip()
        return "Callback scheduled."
    if name == "mark_not_interested" and lead:
        lead.status = "not_interested"
        lead.dnc = True
        lead.last_outcome = params.get("reason", "not_interested")
        return "Contact suppressed. Do not call again."
    return f"Unhandled tool {name}"
