# main.py - Production-ready FastAPI token API with optional JWT auth
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Optional, Dict, Any

# Ensure project root is on path so "db" and "telephony" packages can be imported
_BACKEND_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _BACKEND_DIR.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.responses import Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from livekit.api import AccessToken, VideoGrants, LiveKitAPI
from livekit.protocol.agent_dispatch import CreateAgentDispatchRequest
from livekit.protocol.room import RoomConfiguration
from google.protobuf.json_format import ParseDict
from dotenv import load_dotenv
import jwt

load_dotenv(".env.local")

app = FastAPI(title="Philo Coffee Shop Token API", version="1.0.0")


@app.on_event("startup")
def startup():
    """Ensure SQLite DB exists and is seeded (idempotent)."""
    try:
        from db import init_db
        init_db()
    except Exception as e:
        print(f"[STARTUP] DB init warning: {e}")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET")
LIVEKIT_URL = os.getenv("LIVEKIT_URL")
JWT_SECRET = os.getenv("JWT_SECRET")  # If set, require Authorization: Bearer <jwt>
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

AGENT_NAME = "Philo-Coffee-Agent"

if not LIVEKIT_API_KEY or not LIVEKIT_API_SECRET:
    raise RuntimeError("LIVEKIT_API_KEY and LIVEKIT_API_SECRET must be set")

# ---------------------------------------------------------------------------
# JWT auth layer (optional: only when JWT_SECRET is set)
# ---------------------------------------------------------------------------
security = HTTPBearer(auto_error=False)


async def verify_jwt(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[Dict[str, Any]]:
    """Verify Bearer JWT. If JWT_SECRET is set, token is required; else allowed without auth."""
    if not JWT_SECRET:
        return {}
    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Missing Authorization header (Bearer token required when JWT_SECRET is set)",
        )
    try:
        payload = jwt.decode(
            credentials.credentials,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM],
            options={"verify_exp": True},
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


# ---------------------------------------------------------------------------
# Request / Response models 
# ---------------------------------------------------------------------------
class TokenRequest(BaseModel):
    room_name: Optional[str] = None
    participant_identity: Optional[str] = None
    participant_name: Optional[str] = None
    participant_metadata: Optional[str] = None
    participant_attributes: Optional[Dict[str, str]] = None
    room_config: Optional[dict] = None


# ---------------------------------------------------------------------------
# Token endpoint (production: POST /api/token, 201)
# ---------------------------------------------------------------------------
@app.post("/api/token", status_code=201)
async def get_token(
    request: TokenRequest,
    token_payload: Optional[Dict[str, Any]] = Depends(verify_jwt),
):
    """Create a LiveKit room token and explicit agent dispatch. Optional JWT auth when JWT_SECRET is set."""
    try:
        if not LIVEKIT_URL:
            raise HTTPException(
                status_code=500,
                detail="Server configuration error: LIVEKIT_URL not set",
            )

        # Unique room per session when not provided
        room_name = request.room_name or f"philo-coffee-{uuid.uuid4().hex[:12]}"
        participant_identity = (
            request.participant_identity or f"user-{uuid.uuid4().hex[:8]}"
        )
        participant_name = request.participant_name or "User"

        # 1) Explicit dispatch so PhiloCoffeeAgent joins this room
        api_url = (LIVEKIT_URL or "").replace("wss://", "https://", 1).replace(
            "ws://", "http://", 1
        )
        lkapi = LiveKitAPI(
            url=api_url,
            api_key=LIVEKIT_API_KEY,
            api_secret=LIVEKIT_API_SECRET,
        )
        try:
            dispatch = await lkapi.agent_dispatch.create_dispatch(
                CreateAgentDispatchRequest(
                    agent_name=AGENT_NAME,
                    room=room_name,
                )
            )
            print(
                f"[DISPATCH] created id={getattr(dispatch, 'id', '')} room={room_name} agent={AGENT_NAME}"
            )
        except Exception as e:
            print(f"[DISPATCH] warning: failed for room={room_name}: {e}")
        finally:
            await lkapi.aclose()

        # 2) Build LiveKit access token
        at = (
            AccessToken(
                api_key=LIVEKIT_API_KEY,
                api_secret=LIVEKIT_API_SECRET,
            )
            .with_identity(participant_identity)
            .with_name(participant_name)
            .with_grants(
                VideoGrants(
                    room_join=True,
                    room=room_name,
                    can_publish=True,
                    can_subscribe=True,
                    can_publish_data=True,
                )
            )
        )
        if request.participant_metadata:
            at = at.with_metadata(request.participant_metadata)
        if request.participant_attributes:
            at = at.with_attributes(request.participant_attributes)
        if request.room_config:
            try:
                room_config = RoomConfiguration()
                ParseDict(request.room_config, room_config)
                at = at.with_room_config(room_config)
            except Exception as e:
                print(f"[TOKEN] warning: invalid room_config ignored: {e}")

        participant_token = at.to_jwt()
        print(
            f"[TOKEN] room={room_name} identity={participant_identity} len={len(participant_token)}"
        )

        return {
            "server_url": LIVEKIT_URL,
            "participant_token": participant_token,
            "room_name": room_name,
            "identity": participant_identity,
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"Token generation error: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to generate token",
        )


# ---------------------------------------------------------------------------
# Session JWT for frontend (so Streamlit can call /api/token with Bearer when JWT_SECRET is set)
# ---------------------------------------------------------------------------
@app.post("/auth/session", status_code=200)
def create_session_token():
    """Issue a short-lived JWT for the frontend. No auth required. Use when JWT_SECRET is set."""
    if not JWT_SECRET:
        raise HTTPException(
            status_code=503,
            detail="JWT auth not configured (JWT_SECRET not set)",
        )
    exp_seconds = 3600  # 1 hour
    payload = {
        "sub": "streamlit",
        "exp": int(time.time()) + exp_seconds,
        "iat": int(time.time()),
    }
    token = jwt.encode(
        payload,
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )
    if hasattr(token, "decode"):
        token = token.decode("utf-8")
    return {"access_token": token, "expires_in": exp_seconds}


# ---------------------------------------------------------------------------
# Telephony: outbound call to manager (Twilio)
# ---------------------------------------------------------------------------
class OutboundManagerRequest(BaseModel):
    customer_name: str = ""
    customer_phone: str = ""


@app.post("/api/telephony/outbound-manager", status_code=200)
def outbound_manager(request: OutboundManagerRequest):
    """Trigger outbound Twilio call to manager; record in DB with is_outbound_call=true."""
    try:
        from telephony import trigger_manager_call
        ok, msg = trigger_manager_call(
            customer_name=(request.customer_name or "").strip(),
            customer_phone=(request.customer_phone or "").strip(),
        )
        if not ok:
            raise HTTPException(status_code=400, detail=msg)
        return {"ok": True, "message": msg}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[TELEPHONY] outbound-manager error: {e}")
        raise HTTPException(status_code=500, detail="Failed to trigger manager call")


def _escape_twiml(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


@app.get("/api/telephony/voice")
def telephony_voice(
    type: str = Query(default="", alias="type"),
    customer_name: str = Query(default="A customer"),
    customer_phone: str = Query(default="Not provided"),
):
    """TwiML webhook for when manager answers the outbound call."""
    if type == "manager_notify":
        message = (
            "You have a customer who asked to speak with the manager. "
            f"Customer name: {customer_name or 'A customer'}. "
            f"Customer phone: {customer_phone or 'Not provided'}. "
            "Please call them back when you can."
        )
    else:
        message = "You have a call from Philo Coffee Shop."
    twiml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response><Say>" + _escape_twiml(message) + "</Say></Response>"
    )
    return Response(content=twiml, media_type="application/xml")


@app.get("/health")
def health():
    return {"status": "ok"}
