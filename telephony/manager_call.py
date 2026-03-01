"""Trigger outbound call to manager and record in DB (is_outbound_call=true)."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from urllib.parse import urlencode

from telephony.twilio_client import place_outbound_call


def trigger_manager_call(
    customer_name: str = "",
    customer_phone: str = "",
    order: str | None = None,
    delivery_type: str | None = None,
    address: str | None = None,
    total_price: float | None = None,
) -> tuple[bool, str]:
    """
    Get manager phone from DB, place Twilio outbound call to manager.
    Creates a customer row with is_outbound_call=True only when this is a transfer-without-order
    (no order details). If the customer already placed an order, the agent will have saved it via
    save_customer_order; we do not create a duplicate row here.
    Returns (success, message).
    """
    from db import init_db, get_platform_by_id, create_customer

    init_db()
    manager = get_platform_by_id(1)  # Manager
    if not manager or not (manager.phone_number or "").strip():
        return False, "Manager phone number not found in database"

    base_url = (os.environ.get("BASE_URL") or os.environ.get("BACKEND_URL") or "").rstrip("/")
    if not base_url:
        return False, "BASE_URL or BACKEND_URL not set (required for Twilio webhook)"

    params = {"type": "manager_notify", "customer_name": customer_name or "A customer", "customer_phone": customer_phone or "Not provided"}
    voice_url = f"{base_url}/api/telephony/voice?{urlencode(params)}"

    ok, msg = place_outbound_call(to_number=manager.phone_number, voice_url=voice_url)
    if not ok:
        return False, msg

    # Only create a new customer row when there was no prior order (transfer without order).
    # If the agent already saved the order via save_customer_order, we must not duplicate it
    # with is_outbound_call=True.
    order_text = (order or "").strip()
    is_transfer_only = not order_text or order_text.lower() == "manager transfer requested"
    if is_transfer_only:
        order_date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        create_customer(
            customer_name=customer_name or "N/A",
            phone_number=customer_phone or "N/A",
            order="Manager transfer requested",
            order_date=order_date,
            is_outbound_call=True,
            delivery_type=delivery_type or "N/A",
            address=address or "N/A",
            total_price=total_price,
        )
    return True, "Outbound call to manager initiated and recorded."
