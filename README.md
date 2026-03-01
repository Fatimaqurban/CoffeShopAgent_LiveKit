# Philo Coffee Shop Voice Agent

Voice AI assistant for a coffee shop: menu, orders, and outbound call to manager. Built with [LiveKit Agents](https://github.com/livekit/agents), [LiveKit Cloud](https://cloud.livekit.io/), FastAPI, and Twilio.

---

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Streamlit      │     │   FastAPI         │     │  LiveKit Agent   │
│   (Web UI)       │────▶│   Backend         │────▶│  (src/agent.py)  │
│  Start Session   │     │  Token, Telephony  │     │  Voice + tools   │
│  Mic → LiveKit   │     │  TwiML webhook    │     │  (menu, order,   │
└─────────────────┘     └────────┬─────────┘     │   manager call)  │
                                 │               └─────────────────┘
                                 │ Outbound call
                                 ▼
                         ┌──────────────┐
                         │   Twilio     │  → Manager phone
                         │   TwiML      │
                         └──────────────┘
```

- **Streamlit** — Web UI; user clicks Start Session, talks via mic.
- **Backend** — Issues LiveKit tokens, creates rooms, dispatches agent; handles manager outbound calls and TwiML for Twilio.
- **Agent** — Joins room, speaks (OpenAI Realtime), uses tools: menu check, list menu, save order, request manager call.
- **Twilio** — Calls manager when requested; plays message when manager answers.
- **SQLite** — Menu, platform (manager phone), customer orders. Stored in `./data/` (bind mount in Docker).

---

## Why OpenAI Realtime + OpenAI TTS

- **Low latency** — OpenAI Realtime API streams audio and text over a single WebSocket, with sub-second response times that suit live voice; separate STT → LLM → TTS pipelines add round-trips.
- **Single provider** — One API handles speech-to-text, reasoning, and text-to-speech, simplifying integration with LiveKit Agents and reducing sync/format issues.
- **Voice quality** — OpenAI’s native TTS (e.g. `shimmer`) is clear and natural for a customer-facing barista; [Realtime API docs](https://platform.openai.com/docs/guides/realtime) document supported models and best practices.

---

## System requirements

- **Python 3.10+** (recommend [uv](https://docs.astral.sh/uv/))
- **Docker & Docker Compose** (for one-command run)
- **Accounts**: [LiveKit Cloud](https://cloud.livekit.io/), [Twilio](https://www.twilio.com/) (manager calls), OpenAI API key

---

## How to run

### 1. Configure

```bash
cp .env.example .env.local
```

Edit `.env.local`: set `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, and (for manager calls) `TWILIO_*`, `BASE_URL`.

**Deployed backend:** The FastAPI backend is deployed on [Render](https://render.com/) at `https://coffeshopagent-livekit.onrender.com`. Set `BASE_URL` to that URL so Twilio can reach the TwiML webhook for manager calls. For local-only runs, use [ngrok](https://ngrok.com/) and set `BASE_URL` to the ngrok URL.

### 2. Start (Docker)

```bash
docker compose up --build
```

- **Streamlit**: http://localhost:8501 — click **Start Session** to talk to the agent.
- **Backend health**: http://localhost:8000/health

| Service   | Port | Role                |
|-----------|------|---------------------|
| Backend   | 8000 | Token, telephony    |
| Agent     | -    | LiveKit voice agent |
| Streamlit | 8501 | Web UI              |

Data: DB in `./data/coffeepho.db`, transcripts in `./transcripts/` (bind mounts).

### 3. Optional — Manager calls (local)

If backend is local, expose it for Twilio:

```bash
ngrok http 8000
```

Set `BASE_URL` in `.env.local` to the ngrok URL, then `docker compose restart backend`.

### Run without Docker

From project root:

```bash
uv sync
uv run python src/agent.py download-files   # one-time
uv run uvicorn backend.main:app --host 0.0.0.0 --port 8000   # terminal 1
uv run python src/agent.py dev                               # terminal 2
uv run streamlit run streamlit_app.py                        # terminal 3
```

Open http://localhost:8501.

---

## Project structure

```
├── backend/main.py     # FastAPI: token, telephony, TwiML
├── db/                 # SQLite: schema, repository, seed
├── src/                # Agent: agent.py, prompt.py, tools.py
├── telephony/          # Twilio outbound manager call
├── streamlit_app.py    # Web UI
├── data/               # coffeepho.db (bind mount)
├── transcripts/        # Per-call transcripts (bind mount)
└── pyproject.toml
```

---

## Main flows

1. **Order** — User speaks order → agent checks menu, collects name/phone/delivery → `save_customer_order` → confirms, asks “Anything else?” → when user says no, gives shop number/pick-up address → `end_call`.
2. **Manager** — User says “talk to manager” → `request_manager_call` (with any known details) → backend calls Twilio → manager’s phone rings → TwiML message played; customer row saved with `is_outbound_call=true`.

---

## Assumptions

- Manager phone number in the `platform` table is **Twilio-verified** (required for trial accounts when placing outbound calls). And since its a free number so when the call is picked up there is an auto generated audio of a bot since its a free number
- **Backend is reachable at `BASE_URL`** so Twilio can hit the TwiML webhook for manager calls; use the deployed Render URL or an ngrok URL when running locally.
- LiveKit Cloud is used for rooms and agent dispatch; OpenAI and Twilio API keys are provided via environment variables.

---

## Other

- **Manager phone**: `docker compose exec backend uv run python db/update_manager_phone.py +1234567890` (use a Twilio-verified number for trials).
- **Transcripts**: One `.txt` per call in `./transcripts/` (room + timestamp).
- **Troubleshooting**: If agent fails to connect (e.g. “wait_pc_connection timed out”), try running the agent locally (`uv run python src/agent.py dev`) or enable host networking in Docker Desktop (Windows).

---

## License

MIT. See [LICENSE](LICENSE).
