"""Repository layer for platform, customer, and menu tables."""

from __future__ import annotations

from dataclasses import dataclass
from db.connection import get_connection

# ---------------------------------------------------------------------------
# Simple row types 
# ---------------------------------------------------------------------------

@dataclass
class PlatformRow:
    id: int
    name: str
    phone_number: str


@dataclass
class CustomerRow:
    id: int
    customer_name: str
    phone_number: str
    order: str
    order_date: str
    is_outbound_call: bool
    delivery_type: str | None
    address: str | None
    total_price: float | None


@dataclass
class MenuRow:
    id: int
    item_name: str
    price: float


# ---------------------------------------------------------------------------
# Platform
# ---------------------------------------------------------------------------


def get_all_platform(db_path: str | None = None) -> list[PlatformRow]:
    with get_connection(db_path) as conn:
        cur = conn.execute("SELECT id, name, phone_number FROM platform ORDER BY id")
        return [_row_to_platform(r) for r in cur.fetchall()]


def get_platform_by_id(platform_id: int, db_path: str | None = None) -> PlatformRow | None:
    with get_connection(db_path) as conn:
        cur = conn.execute(
            "SELECT id, name, phone_number FROM platform WHERE id = ?",
            (platform_id,),
        )
        row = cur.fetchone()
        return _row_to_platform(row) if row else None


def _row_to_platform(r) -> PlatformRow:
    return PlatformRow(id=r["id"], name=r["name"], phone_number=r["phone_number"])


# ---------------------------------------------------------------------------
# Customer
# ---------------------------------------------------------------------------


def get_all_customers(db_path: str | None = None) -> list[CustomerRow]:
    with get_connection(db_path) as conn:
        cur = conn.execute(
            'SELECT id, customer_name, phone_number, "order", order_date, is_outbound_call, delivery_type, address, total_price FROM customer ORDER BY order_date DESC, id DESC'
        )
        return [_row_to_customer(r) for r in cur.fetchall()]


def get_customer_by_id(customer_id: int, db_path: str | None = None) -> CustomerRow | None:
    with get_connection(db_path) as conn:
        cur = conn.execute(
            'SELECT id, customer_name, phone_number, "order", order_date, is_outbound_call, delivery_type, address, total_price FROM customer WHERE id = ?',
            (customer_id,),
        )
        row = cur.fetchone()
        return _row_to_customer(row) if row else None


def create_customer(
    customer_name: str,
    phone_number: str,
    order: str,
    order_date: str,
    is_outbound_call: bool = False,
    delivery_type: str | None = None,
    address: str | None = None,
    total_price: float | None = None,
    db_path: str | None = None,
) -> int:
    with get_connection(db_path) as conn:
        cur = conn.execute(
            """INSERT INTO customer (customer_name, phone_number, "order", order_date, is_outbound_call, delivery_type, address, total_price)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                customer_name,
                phone_number,
                order,
                order_date,
                1 if is_outbound_call else 0,
                delivery_type,
                address,
                total_price,
            ),
        )
        return cur.lastrowid


def _row_to_customer(r) -> CustomerRow:
    return CustomerRow(
        id=r["id"],
        customer_name=r["customer_name"],
        phone_number=r["phone_number"],
        order=r["order"],
        order_date=r["order_date"],
        is_outbound_call=bool(r["is_outbound_call"]),
        delivery_type=r["delivery_type"] if r["delivery_type"] is not None else None,
        address=r["address"] if r["address"] is not None else None,
        total_price=float(r["total_price"]) if r["total_price"] is not None else None,
    )


# ---------------------------------------------------------------------------
# Menu
# ---------------------------------------------------------------------------


def get_all_menu(db_path: str | None = None) -> list[MenuRow]:
    with get_connection(db_path) as conn:
        cur = conn.execute("SELECT id, item_name, price FROM menu ORDER BY id")
        return [_row_to_menu(r) for r in cur.fetchall()]


def get_menu_by_id(menu_id: int, db_path: str | None = None) -> MenuRow | None:
    with get_connection(db_path) as conn:
        cur = conn.execute("SELECT id, item_name, price FROM menu WHERE id = ?", (menu_id,))
        row = cur.fetchone()
        return _row_to_menu(row) if row else None


def get_menu_by_name(item_name: str, db_path: str | None = None) -> MenuRow | None:
    with get_connection(db_path) as conn:
        cur = conn.execute("SELECT id, item_name, price FROM menu WHERE item_name = ?", (item_name,))
        row = cur.fetchone()
        return _row_to_menu(row) if row else None


def _row_to_menu(r) -> MenuRow:
    return MenuRow(id=r["id"], item_name=r["item_name"], price=float(r["price"]))
