"""
Database layer for Philo Coffee Shop (SQLite).

Usage:
    from db import init_db, get_connection
    from db.repository import get_all_menu, create_customer, get_all_platform

    init_db()  # create tables and seed platform + menu (idempotent)
    items = get_all_menu()
"""

from db.connection import get_connection, get_db_path, init_db
from db.repository import (
    CustomerRow,
    MenuRow,
    PlatformRow,
    create_customer,
    get_all_customers,
    get_all_menu,
    get_all_platform,
    get_customer_by_id,
    get_menu_by_id,
    get_menu_by_name,
    get_platform_by_id,
)

__all__ = [
    "init_db",
    "get_connection",
    "get_db_path",
    "PlatformRow",
    "CustomerRow",
    "MenuRow",
    "get_all_platform",
    "get_platform_by_id",
    "get_all_customers",
    "get_customer_by_id",
    "create_customer",
    "get_all_menu",
    "get_menu_by_id",
    "get_menu_by_name",
]
