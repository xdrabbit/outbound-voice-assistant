from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request
from sqlalchemy.orm import Session

from app.config import settings
from app.db import Base, engine, get_db
from app.dialer import enqueue_call, process_due_leads
from app.models import Call, Campaign, Lead
from app.webhooks import router as webhook_router

app = FastAPI(title="Outbound Voice Assistant", version="1.0.0")
app.include_router(webhook_router)

BASE = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE / "templates"))
static_dir = BASE / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.on_event("startup")
def startup() -> None:
    (BASE / "data").mkdir(exist_ok=True)
    Base.metadata.create_all(bind=engine)


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    campaigns = db.query(Campaign).order_by(Campaign.id.desc()).all()
    leads = db.query(Lead).order_by(Lead.id.desc()).limit(100).all()
    calls = db.query(Call).order_by(Call.id.desc()).limit(50).all()
    stats = {
        "leads": db.query(Lead).count(),
        "queued": db.query(Lead).filter(Lead.status.in_(["queued", "callback", "no_answer"])).count(),
        "booked": db.query(Lead).filter(Lead.status == "booked").count(),
        "calls": db.query(Call).count(),
        "dry_run": settings.dry_run,
    }
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "campaigns": campaigns,
            "leads": leads,
            "calls": calls,
            "stats": stats,
        },
    )


@app.post("/campaigns")
def create_campaign(
    name: str = Form(...),
    agent_key: str = Form("qualifier"),
    db: Session = Depends(get_db),
):
    campaign = Campaign(name=name, agent_key=agent_key, status="active")
    db.add(campaign)
    db.commit()
    return {"id": campaign.id, "name": campaign.name}


@app.post("/leads")
def add_lead(
    campaign_id: int = Form(...),
    name: str = Form(...),
    phone: str = Form(...),
    timezone: str = Form(settings.default_tz),
    consent: bool = Form(False),
    notes: str = Form(""),
    db: Session = Depends(get_db),
):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(404, "campaign not found")
    lead = Lead(
        campaign_id=campaign.id,
        name=name,
        phone=phone,
        timezone=timezone,
        consent=consent,
        notes=notes,
        status="queued",
    )
    db.add(lead)
    db.commit()
    return {"id": lead.id}


@app.post("/leads/csv")
async def import_csv(
    campaign_id: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    import csv
    import io

    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(404, "campaign not found")
    raw = (await file.read()).decode("utf-8")
    reader = csv.DictReader(io.StringIO(raw))
    count = 0
    for row in reader:
        db.add(
            Lead(
                campaign_id=campaign.id,
                name=row.get("name") or row.get("Name") or "Unknown",
                phone=row.get("phone") or row.get("Phone") or "",
                timezone=row.get("timezone") or settings.default_tz,
                consent=str(row.get("consent", "true")).lower() in {"1", "true", "yes", "y"},
                notes=row.get("notes") or "",
                extra=str({k: v for k, v in row.items()}),
                status="queued",
            )
        )
        count += 1
    db.commit()
    return {"imported": count}


@app.post("/calls/dial/{lead_id}")
def dial_one(lead_id: int, db: Session = Depends(get_db)):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(404, "lead not found")
    try:
        call = enqueue_call(db, lead)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, str(exc)) from exc
    return {"call_id": call.id, "status": call.status, "provider_call_id": call.provider_call_id}


@app.post("/campaigns/{campaign_id}/run")
def run_campaign(campaign_id: int, limit: int = 10, db: Session = Depends(get_db)):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(404, "campaign not found")
    placed = process_due_leads(db, limit=limit)
    return {"placed": len(placed), "call_ids": [c.id for c in placed]}


@app.get("/health")
def health():
    return {
        "ok": True,
        "dry_run": settings.dry_run,
        "vapi_configured": bool(settings.vapi_api_key and settings.vapi_phone_number_id),
    }
