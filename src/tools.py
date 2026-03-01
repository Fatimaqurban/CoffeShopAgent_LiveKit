"""Philo Coffee Shop agent tools (menu check, list menu, save order, manager call). end_call is provided by EndCallTool in agent.py."""

import json
import logging
import os
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from livekit.agents import RunContext, function_tool

logger = logging.getLogger("agent")


class PhiloToolsMixin:
    """Mixin that adds Philo voice agent tools. Use with: class Assistant(PhiloToolsMixin, Agent)."""

    @function_tool()
    async def check_menu_item(self, context: RunContext, item_name: str) -> str:
        """Check if we have this item on the menu and get its price. Use this when the user mentions an item they want to order or asks for the price of an item. Use the item name as the user said it (e.g. latte, Latte, Espresso). If not found, the tool returns that the item is not on the menu.

        Args:
            item_name: The menu item name to look up (e.g. Latte, Espresso, Muffin).
        """
        from db import init_db, get_all_menu

        init_db()
        menu = get_all_menu()
        item_name_clean = (item_name or "").strip()
        if not item_name_clean:
            return "No item name provided."
        for m in menu:
            if m.item_name.lower() == item_name_clean.lower():
                return f"Item found: {m.item_name}, price {m.price} dollars."
        return "Item not on the menu."

    @function_tool()
    async def list_menu(self, context: RunContext) -> str:
        """Get the full list of items we offer and their prices. Use this when the user asks what we have, what we offer, or when an item they asked for was not found so you can suggest our menu.
        """
        from db import init_db, get_all_menu

        init_db()
        menu = get_all_menu()
        if not menu:
            return "The menu is currently empty."
        lines = [f"{m.item_name}: {m.price} dollars" for m in menu]
        return "Menu: " + "; ".join(lines)

    @function_tool()
    async def save_customer_order(
        self,
        context: RunContext,
        customer_name: str,
        phone_number: str,
        order: str,
        delivery_type: str,
        address: str = "",
    ) -> str:
        """Save a new customer order. Call only after you have name, phone, order, delivery_type ("home" or "pickup"), and address if delivery_type is "home". Order date and total price are set automatically. For multiple items, pass them comma-separated (e.g. "Muffin, Cold Brew"); the total will be the sum of all items.

        Args:
            customer_name: The customer's full name.
            phone_number: The customer's phone number.
            order: The menu item(s) they ordered. One item: e.g. "Latte", "Espresso". Multiple items: comma-separated, e.g. "Muffin, Cold Brew" or "Latte, Croissant, Muffin".
            delivery_type: Either "home" for delivery or "pickup" for pick up from shop.
            address: Required if delivery_type is "home"; leave empty for pickup.
        """
        from db import init_db, create_customer, get_all_menu

        init_db()
        menu = get_all_menu()

        # Split order into multiple items: by comma, " and ", or " & "
        order_raw = (order or "").strip()
        for sep in (" and ", " & "):
            order_raw = order_raw.replace(sep, ",")
        parts = [p.strip() for p in order_raw.split(",") if p.strip()]

        def normalize(s: str) -> str:
            out = s.strip()
            for prefix in ("a ", "one ", "two ", "the ", "an "):
                if out.lower().startswith(prefix):
                    out = out[len(prefix) :].strip()
                    break
            return out.strip() or s.strip()

        def match_item(text: str) -> tuple[str | None, float | None]:
            """Return (canonical_menu_name, price) or (None, None)."""
            clean = normalize(text)
            for m in menu:
                if m.item_name.lower() == clean.lower():
                    return m.item_name, m.price
            clean_lower = clean.lower()
            for m in menu:
                if m.item_name.lower() in clean_lower or clean_lower in m.item_name.lower():
                    return m.item_name, m.price
            return None, None

        matched_names: list[str] = []
        total_price = 0.0
        for part in parts:
            name, price = match_item(part)
            if name and price is not None:
                matched_names.append(name)
                total_price += price

        order_to_save = ", ".join(matched_names) if matched_names else order_raw
        if not matched_names:
            total_price = None  # so we don't save 0.0 when nothing matched

        order_date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        delivery = (delivery_type or "").strip().lower() if delivery_type else ""
        if delivery not in ("home", "pickup"):
            delivery = "pickup"
        addr = (address or "").strip() if delivery == "home" else None
        try:
            customer_id = create_customer(
                customer_name=customer_name.strip(),
                phone_number=phone_number.strip(),
                order=order_to_save,
                order_date=order_date,
                is_outbound_call=False,
                delivery_type=delivery,
                address=addr,
                total_price=total_price if total_price else None,
            )
            total_msg = f" Total is {total_price} dollars." if total_price else ""
            return f"Order saved successfully. Customer id {customer_id}.{total_msg} Confirm the order to the customer, then ask 'Is there anything else you'd like to ask?' and wait for their response. Do NOT end the call yet—only when they say no or goodbye should you give the shop number and pick-up address, then call end_call."
        except Exception:
            logger.exception("Failed to save customer order")
            return "Failed to save the order. Apologize and ask the user to try again or call back."

    @function_tool()
    async def request_manager_call(
        self,
        context: RunContext,
        customer_name: str = "",
        customer_phone: str = "",
        order: str = "",
        delivery_type: str = "",
        address: str = "",
        total_price: float | None = None,
    ) -> str:
        """Trigger an outbound call to the manager. Use when the user says they want to talk to the manager. Pass any customer details you have from the conversation so the manager has context: name, phone, and if they placed an order also pass order (items), delivery_type (home/pickup), address (if delivery), total_price.

        Args:
            customer_name: The customer's name if known; otherwise leave empty.
            customer_phone: The customer's phone number if known; otherwise leave empty.
            order: If they placed an order, pass the items (e.g. "Latte, Muffin"); otherwise leave empty.
            delivery_type: "home" or "pickup" if known; otherwise leave empty.
            address: Delivery address if delivery_type is home; otherwise leave empty.
            total_price: Total order price in dollars if they ordered; otherwise leave unset.
        """
        backend_url = (os.environ.get("BACKEND_URL") or "http://localhost:8000").rstrip("/")
        url = f"{backend_url}/api/telephony/outbound-manager"
        payload = {
            "customer_name": (customer_name or "").strip(),
            "customer_phone": (customer_phone or "").strip(),
            "order": (order or "").strip(),
            "delivery_type": (delivery_type or "").strip(),
            "address": (address or "").strip(),
        }
        if total_price is not None:
            payload["total_price"] = total_price
        data = json.dumps(payload).encode("utf-8")
        req = Request(url, data=data, method="POST", headers={"Content-Type": "application/json"})
        try:
            with urlopen(req, timeout=10) as resp:
                body = resp.read().decode("utf-8")
                out = json.loads(body) if body else {}
                if out.get("ok"):
                    return "Manager call requested successfully. Tell the customer that the manager will be notified and will call them back."
                return out.get("message", "Request failed. Apologize and ask the customer to call the shop number later.")
        except HTTPError as e:
            try:
                err_body = e.read().decode("utf-8")
                detail = json.loads(err_body).get("detail", err_body)
            except Exception:
                detail = str(e)
            logger.warning("request_manager_call HTTP error: %s", detail)
            return f"Could not reach the manager right now. Apologize and suggest the customer call the shop at 051 23445726 to speak with the manager."
        except (URLError, TimeoutError, OSError) as e:
            logger.warning("request_manager_call request error: %s", e)
            return "Could not connect to the phone system. Apologize and suggest the customer call the shop at 051 23445726 to speak with the manager."

