<a href="https://livekit.io/">
  <img src="./.github/assets/livekit-mark.png" alt="LiveKit logo" width="100" height="100">
</a>

# Philo Coffee Shop Voice Agent

A voice AI assistant for Philo Coffee Shop built with [LiveKit Agents for Python](https://github.com/livekit/agents) and [LiveKit Cloud](https://cloud.livekit.io/). The agent helps customers check the menu, place orders, and request to speak with the manager. When a customer asks to talk to the manager, the system places an **outbound call** to the manager via Twilio and records the request in the database.

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [What It Does](#what-it-does)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Environment Variables](#environment-variables)
- [How to Run](#how-to-run)
- [Run with Docker](#run-with-docker)
- [How It Works](#how-it-works)
- [Updating the Manager Phone Number](#updating-the-manager-phone-number)
- [Twilio Trial Account Notes](#twilio-trial-account-notes)
- [Testing](#testing)
- [Production Deployment](#production-deployment)
- [License](#license)

---

## Architecture Overview

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Streamlit     │     │   FastAPI         │     │  LiveKit Agent   │
│   (Web UI)      │────▶│   Backend         │────▶│  (src/agent.py)  │
│                 │     │   (backend/)      │     │                  │
│  - Start Session│     │  - Token API      │     │  - Voice pipeline │
│  - Connect to   │     │  - Telephony API  │     │  - Tools (menu,   │
│    LiveKit room │     │  - TwiML webhook  │     │    order, manager)│
└─────────────────┘     └────────┬─────────┘     └─────────────────┘
                                  │
                                  │ Outbound call
                                  ▼
                          ┌──────────────┐
                          │   Twilio     │
                          │   (REST API) │
                          │              │
                          │  - Call mgr  │
                          │  - TwiML URL │
                          └──────────────┘
```

- **Streamlit**: Web frontend that connects users to a LiveKit room via microphone.
- **FastAPI backend**: Issues LiveKit tokens, triggers outbound calls, serves TwiML for Twilio.
- **LiveKit Agent**: Voice AI that speaks with customers, uses tools (menu, orders, manager call).
- **Twilio**: Places outbound calls to the manager when requested; plays a TwiML message when the manager answers.
- **SQLite database**: Stores menu, platform (manager phone), and customer orders.

---

## What It Does

### Voice Agent Capabilities

| Feature | Description |
|---------|-------------|
| **Greeting** | Welcomes the customer and asks how to help |
| **Menu** | Lists all items and prices (`list_menu`), checks specific items (`check_menu_item`) |
| **Orders** | Collects name, phone, order details → confirms total → asks delivery (home/pickup) → if delivery, asks address → saves to DB |
| **Manager request** | When the user says "I want to talk to your manager", the agent triggers an outbound call to the manager's phone (from DB). Creates a customer record with `is_outbound_call=true` |
| **Closing** | Tells the customer the shop phone and pick-up address |

### Default Menu

| Item | Price |
|------|-------|
| Espresso | $3.50 |
| Americano | $4.00 |
| Latte | $4.50 |
| Cappuccino | $4.50 |
| Mocha | $5.00 |
| Cold Brew | $4.25 |
| Croissant | $3.00 |
| Muffin | $3.25 |

---

## Project Structure

```
CoffeeShopAgent-LK/
├── backend/
│   └── main.py              # FastAPI: token, telephony, TwiML
├── db/
│   ├── __init__.py          # init_db, repository functions
│   ├── connection.py       # DB setup and seeding
│   ├── repository.py       # platform, customer, menu queries
│   ├── schema.py           # SQL schema
│   ├── seed.py             # Seed data (platform, menu)
│   └── update_manager_phone.py  # Script to update manager phone
├── data/
│   └── coffeepho.db        # SQLite database
├── src/
│   ├── agent.py            # LiveKit agent entry point
│   ├── prompt.py           # Philo instructions
│   └── tools.py            # Agent tools (menu, order, manager call)
├── telephony/
│   ├── __init__.py         # Exports trigger_manager_call
│   ├── manager_call.py     # Orchestrates manager outbound call
│   └── twilio_client.py   # Twilio REST API calls
├── streamlit_app.py        # Web UI to connect to agent
├── .env.example            # Environment template
├── .env.local              # Your secrets (not committed)
└── pyproject.toml          # Dependencies
```

---

## Prerequisites

1. **Python 3.10+** (recommend [uv](https://docs.astral.sh/uv/) for package management)
2. **LiveKit Cloud account** – [Sign up](https://cloud.livekit.io/)
3. **Twilio account** (for manager outbound calls) – [Sign up](https://www.twilio.com/)
4. **OpenAI API key** (for LLM and TTS) – set via LiveKit Cloud or in agent config

---

## Environment Variables

Copy `.env.example` to `.env.local` and fill in the values:

```bash
cp .env.example .env.local
```

### Required (LiveKit)

| Variable | Description | Example |
|----------|-------------|---------|
| `LIVEKIT_URL` | LiveKit server WebSocket URL | `wss://your-project.livekit.cloud` |
| `LIVEKIT_API_KEY` | LiveKit API key | `APIxxxx...` |
| `LIVEKIT_API_SECRET` | LiveKit API secret | `secret...` |

### Required for Manager Outbound Calls (Twilio)

| Variable | Description | Example |
|----------|-------------|---------|
| `TWILIO_ACCOUNT_SID` | Twilio Account SID | `ACxxxxxxxx...` |
| `TWILIO_AUTH_TOKEN` | Twilio Auth Token | `your-auth-token` |
| `TWILIO_PHONE_NUMBER` | Twilio number for outbound calls (E.164) | `+1234567890` |
| `BASE_URL` | **Public** URL of your backend (Twilio fetches TwiML from here) | `https://your-ngrok.ngrok.io` |

For local development, use [ngrok](https://ngrok.com/) to expose your backend. Twilio must reach `BASE_URL/api/telephony/voice` when the manager answers.

### Optional

| Variable | Description | Default |
|----------|-------------|---------|
| `BACKEND_URL` | URL the agent uses to call the backend (manager-call API) | `http://localhost:8000` |
| `DATABASE_PATH` | Path to SQLite DB | `./data/coffeepho.db` |
| `PHILO_SHOP_ADDRESS` | Pick-up address told to customers | (hardcoded in prompt) |
| `JWT_SECRET` | If set, token API requires Bearer JWT | (disabled) |

---

## How to Run

> **Using Docker?** See [Run with Docker](#run-with-docker) for a single `docker compose up` setup (backend + agent + Streamlit together).

### Step 1: Install Dependencies

```bash
cd CoffeeShopAgent-LK
uv sync
```

### Step 2: Configure Environment

1. Copy `.env.example` to `.env.local`.
2. Fill in LiveKit credentials. You can use the LiveKit CLI:

   ```bash
   lk cloud auth
   lk app env -w -d .env.local
   ```

3. Add Twilio credentials and `BASE_URL` (see [Environment Variables](#environment-variables)).
4. For local dev with Twilio: run ngrok (see below) and set `BASE_URL` to the ngrok URL.

### Step 3: Download Agent Models

```bash
uv run python src/agent.py download-files
```

This downloads Silero VAD and LiveKit turn detector models used for voice activity detection.

### Step 4: Start the Backend

**Important:** Run from the **project root** (`CoffeeShopAgent-LK/`) so the `db` and `telephony` packages resolve correctly.

```bash
uv run uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

The backend will:

- Create the SQLite database and seed platform + menu if empty
- Expose `/api/token`, `/api/telephony/outbound-manager`, `/api/telephony/voice` (TwiML), `/health`

### Step 5: Expose Backend for Twilio (Local Dev)

If your backend runs on `localhost`, Twilio cannot reach it. Use ngrok:

```bash
ngrok http 8000
```

Copy the `https://xxxx.ngrok-free.app` URL and set `BASE_URL` in `.env.local`. Restart the backend.

> **Note:** Free ngrok gives a new URL each run. Paid plans allow a fixed domain.

### Step 6: Start the Agent

In a **second terminal** (from project root):

```bash
uv run python src/agent.py dev
```

This starts the LiveKit agent so it can join rooms when the backend dispatches it.

### Step 7: Start the Web Frontend

In a **third terminal**:

```bash
uv run streamlit run streamlit_app.py
```

Open http://localhost:8501 in your browser. Click **Start Session** to connect to the agent and talk via microphone.

### Run Modes

| Command | Use Case |
|---------|----------|
| `uv run python src/agent.py console` | Talk to the agent in the terminal (no web UI) |
| `uv run python src/agent.py dev` | Agent for frontend/telephony (with auto-reconnect) |
| `uv run python src/agent.py start` | Production mode |

---

## Run with Docker

Run the entire project (backend, agent, Streamlit) with Docker. You only need **2 terminals** when using the manager-call feature (ngrok required for Twilio).

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/)
- Create `.env.local` with your LiveKit and Twilio credentials (see [Environment Variables](#environment-variables))

### Step 1: Configure environment

```bash
cd CoffeeShopAgent-LK
cp .env.example .env.local
# Edit .env.local with LIVEKIT_*, TWILIO_*, BASE_URL (set BASE_URL after Step 2)
```

### Step 2: Start all services (Terminal 1)

```bash
docker compose up --build
```

This starts:

| Service   | Port | Purpose                                                |
|-----------|------|--------------------------------------------------------|
| Backend   | 8000 | Token API, telephony, TwiML webhook                    |
| Agent     | -    | LiveKit voice agent (connects to LiveKit Cloud)        |
| Streamlit | 8501 | Web UI for talking to the agent                        |

- Open **http://localhost:8501** for the Streamlit UI.
- Open **http://localhost:8000/health** to check the backend.

### Step 3: Expose backend for Twilio (Terminal 2, optional for manager calls)

If you want to test the "talk to manager" flow, Twilio must reach your backend at a public URL. Run ngrok in a **second terminal**:

```bash
ngrok http 8000
```

Copy the `https://xxxx.ngrok-free.app` URL, set `BASE_URL` in `.env.local`, then restart the backend:

```bash
docker compose restart backend
```

> **Skip this step** if you only test menu/orders and do not need manager outbound calls.

### Summary: terminals when using Docker

| Terminal | Command | Purpose |
|----------|---------|---------|
| **1** | `docker compose up --build` | Runs backend, agent, Streamlit together |
| **2** | `ngrok http 8000` | Exposes backend to Twilio for manager calls |

### Run in background

```bash
docker compose up --build -d
```

View logs: `docker compose logs -f`

### Database

The SQLite database is stored in a Docker volume (`app-data`), so it persists across restarts. To update the manager phone in the container:

```bash
docker compose exec backend uv run python db/update_manager_phone.py +923337136983
```

Replace the number with your verified Twilio number.

### Stop

```bash
docker compose down
```

---

## How It Works

### 1. User Connects to the Agent

1. User clicks **Start Session** in Streamlit.
2. Streamlit calls `POST /api/token` on the backend.
3. Backend creates a LiveKit room, dispatches the Philo agent to that room, and returns a participant token.
4. Streamlit connects to the room with the LiveKit Web SDK and publishes the user's microphone.
5. The agent joins, says the greeting, and listens.

### 2. Order Flow

1. User says what they want (e.g. "I'd like a latte and a muffin").
2. Agent uses `check_menu_item` / `list_menu` to verify items and prices.
3. Agent asks for name, phone, delivery type (home/pickup), and address (if delivery).
4. Agent calls `save_customer_order` with all details.
5. Backend saves to SQLite in the `customer` table.
6. Agent confirms the order, total price, and gives the shop phone + pick-up address.

### 3. Manager Call Flow

1. User says "I want to talk to your manager" (or similar).
2. Agent calls `request_manager_call(customer_name, customer_phone)` (passes values if known).
3. The tool `POST`s to `BACKEND_URL/api/telephony/outbound-manager` with `{customer_name, customer_phone}`.
4. Backend (`telephony/manager_call.py`):
   - Reads the Manager phone from `platform` table (id=1)
   - Builds a TwiML URL: `BASE_URL/api/telephony/voice?type=manager_notify&customer_name=...&customer_phone=...`
   - Calls Twilio REST API: `client.calls.create(to=manager_phone, from_=TWILIO_PHONE_NUMBER, url=voice_url)`
   - Creates a `customer` row with `order="Manager transfer requested"`, `is_outbound_call=true`
5. When the manager answers, Twilio requests the TwiML URL from your backend.
6. Backend returns XML with `<Say>` containing: "You have a customer who asked to speak with the manager. Customer name: X. Customer phone: Y. Please call them back when you can."
7. Twilio plays that message to the manager.

### 4. Database

- **platform**: Manager and Admin phone numbers (id=1 = Manager, used for outbound calls).
- **menu**: Items and prices.
- **customer**: Orders with `customer_name`, `phone_number`, `order`, `delivery_type`, `address`, `total_price`, `is_outbound_call`.

---

## Updating the Manager Phone Number

The manager's phone is stored in the `platform` table (row `id=1`). This is the number Twilio calls when a customer requests the manager.

### Option 1: Use the Update Script

From the project root:

```bash
uv run python db/update_manager_phone.py +923337136983
```

Replace `+923337136983` with your **verified** Twilio number (E.164 format, e.g. `+923001234567`).

### Option 2: Update the Seed and Re-run

Edit `db/seed.py` and change the Manager phone in `PLATFORM_ROWS`:

```python
PLATFORM_ROWS = [
    (1, "Manager", "+923337136983"),  # Your verified number
    ...
]
```

Then either:

- Delete `data/coffeepho.db` and restart the backend (it will re-seed), or
- Run a one-time script to update only the platform row without losing customer data.

### Option 3: Direct SQL

If you have SQLite access:

```sql
UPDATE platform SET phone_number = '+923337136983' WHERE id = 1;
```

### Twilio Trial Restriction

**Twilio trial accounts can only call verified numbers.** Add your phone in [Twilio Console → Verified Caller IDs](https://console.twilio.com/) and use that exact number as the Manager phone for testing. After upgrading Twilio, you can use any valid number.

---

## Twilio Trial Account Notes

| Limitation | What to do |
|------------|------------|
| Can only call **verified** numbers | Add your number in Verified Caller IDs; use it as Manager in DB |
| Need public URL for TwiML | Use ngrok or deploy backend to a public host; set `BASE_URL` |
| New ngrok URL each run (free) | Update `BASE_URL` in `.env.local` and restart backend when ngrok restarts |

---

## Testing

### Run Tests

```bash
uv run pytest
```

### Manual Test: Manager Call

1. Ensure Manager phone in DB is your **verified** Twilio number.
2. Start backend, agent, Streamlit, and ngrok (if local).
3. Connect via Streamlit, say "I want to talk to your manager."
4. Your phone (Manager) should ring; when you answer, you hear the TwiML message.
5. Check `customer` table for a row with `is_outbound_call=1`.

---

## Production Deployment

1. **Deploy backend** to a host with a public HTTPS URL (e.g. Railway, Render, Fly.io). Set `BASE_URL` to that URL.
2. **Deploy agent** to LiveKit Cloud or your own infrastructure. See [LiveKit deployment guide](https://docs.livekit.io/agents/ops/deployment/).
3. **Environment**: Set all env vars in your hosting platform; do not commit `.env.local`.
4. **Database**: For production, consider PostgreSQL instead of SQLite; the current code uses SQLite for simplicity.

---

## Coding Agents and MCP

This project works with coding agents like [Cursor](https://www.cursor.com/) and [Claude Code](https://www.anthropic.com/claude-code). Install the [LiveKit Docs MCP server](https://docs.livekit.io/mcp) for API documentation.

**Cursor:** [Install MCP Server](https://cursor.com/en-US/install-mcp?name=livekit-docs&config=eyJ1cmwiOiJodHRwczovL2RvY3MubGl2ZWtpdC5pby9tY3AifQ%3D%3D)

**Claude Code:**
```
claude mcp add --transport http livekit-docs https://docs.livekit.io/mcp
```

---

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
