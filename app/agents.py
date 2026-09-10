from app.config import settings


def qualifier_prompt(lead_name: str, extra: str = "") -> str:
    return f"""You are Maya, an outbound voice assistant calling on behalf of a licensed business.
You are speaking with {lead_name or "the customer"}.

Purpose: briefly introduce yourself, confirm you have the right person, qualify interest, and either
book a follow-up, take a callback time, or mark them not interested.

Hard rules:
- Disclose immediately that this is an automated AI assistant.
- If they ask to stop receiving calls, confirm, use mark_not_interested, and end the call.
- Never argue, never pressure, never invent prices, availability, or legal claims.
- Keep turns short. One question at a time.
- If they ask for a human, use transfer_to_human.
- If you reach voicemail, leave a 12-second message and hang up.
- Do not collect full SSN, card numbers, or passwords.

Context: {extra or "General qualification call."}
"""


def reminder_prompt(lead_name: str, extra: str = "") -> str:
    return f"""You are Maya, an outbound reminder assistant.
You are speaking with {lead_name or "the customer"}.

Purpose: confirm or reschedule an existing appointment.

Hard rules:
- Disclose that this is an automated AI assistant.
- Confirm identity before discussing appointment details.
- If they confirm, use book_appointment with status confirmed.
- If they want another time, collect a window and use schedule_callback.
- If they cancel, use mark_not_interested with reason cancelled.
- Never invent appointment times that were not provided in context.

Appointment context: {extra or "No extra details provided."}
"""


AGENTS = {
    "qualifier": {
        "name": "Outbound Qualifier",
        "first_message": "Hi, this is Maya, an automated assistant. Do you have a quick moment?",
        "prompt": qualifier_prompt,
    },
    "reminder": {
        "name": "Appointment Reminder",
        "first_message": "Hi, this is Maya, an automated assistant calling with a short appointment reminder. Is this a good time?",
        "prompt": reminder_prompt,
    },
}


def assistant_payload(agent_key: str, lead_name: str, extra: str, server_url: str) -> dict:
    agent = AGENTS[agent_key]
    tools = [
        {"type": "endCall"},
        {
            "type": "function",
            "function": {
                "name": "book_appointment",
                "description": "Book or confirm an appointment after the caller agrees.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "when": {"type": "string", "description": "ISO datetime or human window"},
                        "notes": {"type": "string"},
                    },
                    "required": ["when"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "schedule_callback",
                "description": "Schedule another outbound attempt at a requested time.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "when": {"type": "string"},
                        "reason": {"type": "string"},
                    },
                    "required": ["when"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "mark_not_interested",
                "description": "Caller asked to stop, is not interested, or cancelled.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "reason": {"type": "string"},
                    },
                    "required": ["reason"],
                },
            },
        },
    ]
    if settings.transfer_number:
        tools.append(
            {
                "type": "transferCall",
                "destinations": [{"type": "number", "number": settings.transfer_number}],
            }
        )

    return {
        "name": agent["name"][:40],
        "firstMessage": agent["first_message"],
        "endCallMessage": "Thanks for your time. Goodbye.",
        "maxDurationSeconds": 360,
        "voicemailMessage": "Hi, this is Maya with a quick automated follow-up. Please call us back when you have a moment. Goodbye.",
        "serverUrl": server_url,
        "serverUrlSecret": settings.webhook_secret,
        "model": {
            "provider": "openai",
            "model": "gpt-4o",
            "temperature": 0.3,
            "messages": [{"role": "system", "content": agent["prompt"](lead_name, extra)}],
            "tools": tools,
        },
        "voice": {"provider": "vapi", "voiceId": "Elliot"},
        "transcriber": {"provider": "deepgram", "model": "nova-2", "language": "en"},
    }


def assistant_overrides(agent_key: str, lead_name: str, extra: str, server_url: str) -> dict:
    payload = assistant_payload(agent_key, lead_name, extra, server_url)
    return {
        "firstMessage": payload["firstMessage"],
        "variableValues": {"lead_name": lead_name},
        "model": payload["model"],
        "serverUrl": server_url,
    }
