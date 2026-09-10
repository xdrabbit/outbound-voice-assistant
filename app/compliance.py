from datetime import datetime, time
from zoneinfo import ZoneInfo

import phonenumbers

from app.config import settings


ALLOWED_COUNTRY = "US"
DEFAULT_START = time.fromisoformat(settings.call_window_start)
DEFAULT_END = time.fromisoformat(settings.call_window_end)


def normalize_e164(raw: str, region: str = "US") -> str | None:
    try:
        parsed = phonenumbers.parse(raw, region)
        if not phonenumbers.is_valid_number(parsed):
            return None
        return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    except phonenumbers.NumberParseException:
        return None


def in_calling_window(tz_name: str | None) -> bool:
    tz = ZoneInfo(tz_name or settings.default_tz)
    now = datetime.now(tz)
    if now.weekday() >= 5:
        return False
    current = now.time()
    return DEFAULT_START <= current <= DEFAULT_END


def can_dial(lead) -> tuple[bool, str]:
    if lead.dnc:
        return False, "on_dnc"
    if not lead.consent:
        return False, "missing_consent"
    phone = normalize_e164(lead.phone)
    if not phone:
        return False, "invalid_phone"
    if lead.attempts >= settings.max_attempts:
        return False, "max_attempts"
    if lead.status in {"completed", "do_not_call", "not_interested", "booked"}:
        return False, f"terminal_status:{lead.status}"
    if lead.next_attempt_at and lead.next_attempt_at > datetime.utcnow():
        return False, "retry_not_due"
    if not in_calling_window(lead.timezone):
        return False, "outside_calling_hours"
    return True, "ok"
