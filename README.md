# Outbound Voice Assistant

Campaign engine + AI voice agent for outbound phone calls.

The app owns compliance, lead state, retries, and CRM-like outcomes.  
[Vapi](https://docs.vapi.ai/calls/outbound-calling) owns telephony, turn-taking, STT, LLM, and TTS.

```
CSV / API  →  compliance gate  →  Vapi outbound call  →  webhook tools
                 (consent, DNC,     (voice agent)         (book / DNC /
                  hours, retries)                          callback)
```

## What you get

- FastAPI dashboard to create campaigns, import leads, and place calls
- Two stock agents: **lead qualifier** and **appointment reminder**
- Live tool calling: book, schedule callback, suppress, transfer to a human
- TCPA-oriented gates: prior consent, DNC flag, weekday calling window, max attempts
- Dry-run mode so you can test the workflow before buying minutes
- Vapi webhooks for status, transcripts, and end-of-call reports

This is a starter you wire to a real Vapi number. It does not place calls by itself.

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

Open http://localhost:8000

With `DRY_RUN=true` (default), Dial and Run batch simulate calls and write rows. No telephony is used.

## Go live with Vapi

1. Create an account at [dashboard.vapi.ai](https://dashboard.vapi.ai)
2. Create a private API key
3. Import a Twilio / Telnyx / Vonage number (free Vapi numbers are weak for outbound)
4. Expose this app with a public HTTPS URL (`ngrok http 8000` or Cloudflare Tunnel)
5. Fill `.env`:

```env
VAPI_API_KEY=...
VAPI_PHONE_NUMBER_ID=...
PUBLIC_BASE_URL=https://your-tunnel.example.com
WEBHOOK_SECRET=a-long-random-string
DRY_RUN=false
TRANSFER_NUMBER=+18015550199
```

6. Provision the reusable assistant:

```bash
python scripts/provision_assistant.py qualifier
```

Paste the printed `VAPI_ASSISTANT_ID` into `.env`.

7. Import `scripts/sample_leads.csv`, confirm consent, then Dial.

Webhook path expected by Vapi: `POST {PUBLIC_BASE_URL}/webhooks/vapi`

## Agents

| Key | Job | Tools |
|---|---|---|
| `qualifier` | Introduce, qualify, book or suppress | book, callback, not-interested, end, transfer |
| `reminder` | Confirm / reschedule an appointment | same |

Prompts live in `app/agents.py`. Edit copy there, then re-run `provision_assistant.py`.

Each live dial also sends per-lead `assistantOverrides` so the model sees the contact name and notes.

## Compliance (you still own this)

US outbound AI audio is regulated. The app encodes the operational basics:

- Do not dial without `consent=true`
- Honor `dnc=true` and “not interested”
- Weekday window only, default 09:00–20:00 in the lead’s timezone
- Cap attempts (`MAX_ATTEMPTS`) and space retries (`RETRY_HOURS`)

That is not legal advice. You still need:

- Prior express consent appropriate to the campaign (TCPA / state mini-TCPA)
- National and internal DNC scrub before import
- AI disclosure on the call (already in the system prompt)
- STIR/SHAKEN + CNAM on the outbound number
- Recording disclosure where required

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Dashboard |
| POST | `/campaigns` | Create campaign |
| POST | `/leads` | Add one lead |
| POST | `/leads/csv` | Import CSV |
| POST | `/calls/dial/{lead_id}` | Place one call |
| POST | `/campaigns/{id}/run` | Dial the next eligible batch |
| POST | `/webhooks/vapi` | Vapi server URL |
| GET | `/health` | Config check |

## Docker

```bash
docker compose up --build
```

## Swap the voice layer

`app/vapi_client.py` is the only telephony adapter. Bland, Retell, or Twilio ConversationRelay can replace it if you keep the same `Call` / webhook contract:

- create outbound call
- map provider status onto `Call.status`
- resolve tool names onto `apply_tool()`
