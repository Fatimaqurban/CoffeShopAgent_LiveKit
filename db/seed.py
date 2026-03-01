"""Seed data for platform and menu tables."""

# platform: id, name, phone_number
PLATFORM_ROWS = [
    (1, "Manager", "+923337136983"),
    (2, "Admin", "+92876544321"),
]

# menu: item_name, price (id is AUTOINCREMENT; we use explicit ids for clarity)
MENU_ROWS = [
    (1, "Espresso", 3.50),
    (2, "Americano", 4.00),
    (3, "Latte", 4.50),
    (4, "Cappuccino", 4.50),
    (5, "Mocha", 5.00),
    (6, "Cold Brew", 4.25),
    (7, "Croissant", 3.00),
    (8, "Muffin", 3.25),
]
