"""Update manager phone in platform table. Run: uv run python scripts/update_manager_phone.py +923337136983"""
import sys
from pathlib import Path

if len(sys.argv) < 2:
    print("Usage: uv run python scripts/update_manager_phone.py +923337136983")
    print("Replace with YOUR verified Twilio number (E.164 format).")
    sys.exit(1)

phone = sys.argv[1].strip()
if not phone.startswith("+"):
    print("Use E.164 format, e.g. +923337136983")
    sys.exit(1)

root = Path(__file__).resolve().parent.parent
db_path = root / "data" / "coffeepho.db"
import sqlite3
conn = sqlite3.connect(db_path)
conn.execute("UPDATE platform SET phone_number = ? WHERE id = 1", (phone,))
conn.commit()
print(f"Updated Manager phone to {phone}")
conn.close()
