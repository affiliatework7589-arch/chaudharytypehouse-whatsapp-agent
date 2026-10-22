# -*- coding: utf-8 -*-
"""whatsapp_ai.py — CLI bridge for the WhatsApp AI agent.

Reads a JSON object from stdin: {"message": "...", "state": {...}}
Prints a single JSON object to stdout: the smart_reply result.
Used by whatsapp_bridge.js (Node) to query the Python AI engine.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from core.ai_engine import smart_reply


def main():
    raw = sys.stdin.read()
    try:
        data = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        data = {}
    message = (data.get("message") or "").strip()
    state = data.get("state") or {}
    out = smart_reply(message, state=state, channel="whatsapp")
    # Ensure JSON-serialisable
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()