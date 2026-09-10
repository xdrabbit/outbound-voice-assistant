#!/usr/bin/env python3
"""Create or update the reusable Vapi assistant from local agent config."""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv()

from app.agents import assistant_payload
from app.config import settings
from app.vapi_client import upsert_assistant


def main() -> None:
    agent_key = sys.argv[1] if len(sys.argv) > 1 else "qualifier"
    server_url = settings.public_base_url.rstrip("/") + "/webhooks/vapi"
    payload = assistant_payload(agent_key, "{{lead_name}}", "", server_url)
    assistant_id = settings.vapi_assistant_id or None
    result = upsert_assistant(payload, assistant_id)
    print(json.dumps({"id": result.get("id"), "name": result.get("name")}, indent=2))
    if not assistant_id:
        print("\nAdd this to .env:\nVAPI_ASSISTANT_ID=" + result["id"])


if __name__ == "__main__":
    if not os.getenv("VAPI_API_KEY"):
        sys.exit("Set VAPI_API_KEY first")
    main()
