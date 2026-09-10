from datetime import datetime, timedelta
import json

from sqlalchemy.orm import Session

from app import vapi_client
from app.agents import assistant_overrides
from app.compliance import can_dial, normalize_e164
from app.config import settings
from app.models import Call, Lead


def enqueue_call(db: Session, lead: Lead) -> Call:
    ok, reason = can_dial(lead)
    if not ok:
        raise ValueError(reason)

    phone = normalize_e164(lead.phone)
    lead.phone = phone
    lead.attempts += 1
    lead.status = "dialing"
    lead.last_outcome = "initiated"

    call = Call(lead_id=lead.id, provider="vapi", dry_run=settings.dry_run, status="created")
    db.add(call)
    db.flush()

    extra = lead.extra
    try:
        extra_obj = json.loads(lead.extra or "{}")
        extra = json.dumps(extra_obj) if extra_obj else lead.notes
    except json.JSONDecodeError:
        extra = lead.notes or lead.extra

    if settings.dry_run or not settings.vapi_api_key:
        call.status = "simulated"
        call.summary = "Dry-run: compliance passed, no live telephony placed."
        lead.status = "queued"
        lead.next_attempt_at = datetime.utcnow() + timedelta(hours=settings.retry_hours)
        db.commit()
        db.refresh(call)
        return call

    server_url = settings.public_base_url.rstrip("/") + "/webhooks/vapi"
    overrides = assistant_overrides(lead.campaign.agent_key, lead.name, extra, server_url)
    result = vapi_client.create_outbound_call(
        to_number=phone,
        assistant_overrides=overrides,
        metadata={"lead_id": lead.id, "campaign_id": lead.campaign_id, "call_id": call.id},
    )
    call.provider_call_id = result.get("id", "")
    call.status = result.get("status", "queued")
    db.commit()
    db.refresh(call)
    return call


def process_due_leads(db: Session, limit: int = 10) -> list[Call]:
    leads = (
        db.query(Lead)
        .filter(Lead.status.in_(["queued", "callback", "no_answer"]))
        .order_by(Lead.id.asc())
        .limit(limit)
        .all()
    )
    placed = []
    for lead in leads:
        ok, _ = can_dial(lead)
        if not ok:
            continue
        try:
            placed.append(enqueue_call(db, lead))
        except Exception as exc:
            lead.last_outcome = f"error:{exc}"
            lead.status = "queued"
            db.commit()
    return placed
