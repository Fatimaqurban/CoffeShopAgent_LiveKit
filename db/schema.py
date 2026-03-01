"""SQLite schema definitions for Philo Coffee Shop."""

CREATE_PLATFORM = """
CREATE TABLE IF NOT EXISTS platform (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    phone_number TEXT NOT NULL
);
"""

CREATE_CUSTOMER = """
CREATE TABLE IF NOT EXISTS customer (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_name TEXT NOT NULL,
    phone_number TEXT NOT NULL,
    "order" TEXT NOT NULL,
    order_date TEXT NOT NULL,
    is_outbound_call INTEGER NOT NULL DEFAULT 0,
    delivery_type TEXT,
    address TEXT,
    total_price REAL
);
"""

# Migration: add new columns to existing customer table (no-op if already present)
CUSTOMER_ADD_DELIVERY_TYPE = "ALTER TABLE customer ADD COLUMN delivery_type TEXT;"
CUSTOMER_ADD_ADDRESS = "ALTER TABLE customer ADD COLUMN address TEXT;"
CUSTOMER_ADD_TOTAL_PRICE = "ALTER TABLE customer ADD COLUMN total_price REAL;"

CREATE_MENU = """
CREATE TABLE IF NOT EXISTS menu (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_name TEXT NOT NULL,
    price REAL NOT NULL
);
"""

ALL_CREATE = [CREATE_PLATFORM, CREATE_CUSTOMER, CREATE_MENU]
