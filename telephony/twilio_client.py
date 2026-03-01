"""Twilio client for placing outbound calls."""

from __future__ import annotations

import os
from typing import Optional

# Optional: only used when Twilio credentials are set
try:
    from twilio.rest import Client
except ImportError:
    Client = None  # type: ignore


def get_twilio_client() -> Optional["Client"]:
    """Return Twilio client if credentials are set, else None."""
    if Client is None:
        return None
    sid = os.environ.get("TWILIO_ACCOUNT_SID")
    token = os.environ.get("TWILIO_AUTH_TOKEN")
    if not sid or not token:
        return None
    return Client(sid, token)


def place_outbound_call(
    to_number: str,
    voice_url: str,
    from_number: Optional[str] = None,
) -> tuple[bool, str]:
    """
    Place an outbound call via Twilio.
    Returns (success, message). When manager answers, Twilio will request voice_url for TwiML.
    """
    client = get_twilio_client()
    if not client:
        return False, "Twilio not configured (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)"
    from_num = from_number or os.environ.get("TWILIO_PHONE_NUMBER")
    if not from_num:
        return False, "TWILIO_PHONE_NUMBER not set"
    to_number = (to_number or "").strip()
    if not to_number:
        return False, "to_number is empty"
    if to_number.startswith("0") and len(to_number) >= 10:
        to_number = "+92" + to_number[1:]
    try:
        call = client.calls.create(to=to_number, from_=from_num, url=voice_url)
        return True, f"Call initiated: {call.sid}"
    except Exception as e:
        return False, str(e)
