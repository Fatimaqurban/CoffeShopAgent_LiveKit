"""Philo Coffee Shop agent tools (menu check, list menu, save order, manager call, end call)."""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from livekit.agents import RunContext, function_tool, get_job_context

logger = logging.getLogger("agent")

GOODBYE_MESSAGE = "Thank you so much for ordering with us. Goodbye."


async def hangup_call() -> None:
    """Delete the room so all participants (SIP, browser) disconnect, then shut down the job."""
    ctx = get_job_context()
    if ctx is None:
        return
    try:
        task = ctx.delete_room(room_name=ctx.room.name)
        await task
        logger.info("Room deleted, call ended.")
    except Exception as e:
        logger.warning("hangup_call delete_room: %s", e)
    try:
        ctx.shutdown(reason="agent_ended_call")
    except Exception as e:
        logger.warning("hangup_call shutdown: %s", e)


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
            return f"Order saved successfully. Customer id {customer_id}.{total_msg} Thank them and remind them: for queries they can call the shop; if pick up, tell them the pick-up address (it is in your instructions)."
        except Exception:
            logger.exception("Failed to save customer order")
            return "Failed to save the order. Apologize and ask the user to try again or call back."

    @function_tool()
    async def request_manager_call(
        self,
        context: RunContext,
        customer_name: str = "",
        customer_phone: str = "",
    ) -> str:
        """Trigger an outbound call to the manager (using the phone number stored in the database). Use when the user says they want to talk to the manager or speak to the manager. The backend will call the manager and record the request with is_outbound_call=true. Pass the customer's name and phone if you have them from the conversation.

        Args:
            customer_name: The customer's name if known; otherwise leave empty.
            customer_phone: The customer's phone number if known; otherwise leave empty.
        """
        backend_url = (os.environ.get("BACKEND_URL") or "http://localhost:8000").rstrip("/")
        url = f"{backend_url}/api/telephony/outbound-manager"
        data = json.dumps({
            "customer_name": (customer_name or "").strip(),
            "customer_phone": (customer_phone or "").strip(),
        }).encode("utf-8")
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

    @function_tool()
    async def end_call(self, context: RunContext) -> str:
        """End the call and hang up. Call this tool (no arguments) when: (1) After save_customer_order when user said no to 'anything else?'—say only the shop number and pick-up address if pickup, then call end_call. (2) After saying 'Our manager would be calling you in a while.' (3) When the user says goodbye. Do NOT say 'Thank you for ordering' or 'Goodbye' in your own message—this tool will say it once. If you say it too, the customer hears it twice."""
        session = context.session
        # Speak the goodbye ourselves so we control the exact message and no extra LLM speech follows
        handle = session.say(GOODBYE_MESSAGE, add_to_chat_ctx=False)
        try:
            await asyncio.wait_for(asyncio.shield(handle.wait_for_playout()), timeout=12.0)
        except asyncio.TimeoutError:
            logger.warning("end_call: goodbye playout timed out")
        except Exception as e:
            logger.warning("end_call wait: %s", e)
        await hangup_call()
        return "Call ended."
