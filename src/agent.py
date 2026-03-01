import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Ensure project root is on path so "db" package can be imported when running src/agent.py
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
from livekit import rtc
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    cli,
    room_io,
)
from livekit.agents.beta.tools import EndCallTool
from livekit.plugins import noise_cancellation, openai

from src.prompt import PHILO_INSTRUCTIONS
from src.tools import PhiloToolsMixin

load_dotenv(".env.local")

# Directory for per-call transcripts (session report JSON + readable transcript TXT)
TRANSCRIPTS_DIR = Path(os.getenv("TRANSCRIPTS_DIR", str(_PROJECT_ROOT / "transcripts")))

# EndCallTool: agent must call this when the conversation is finished. Goodbye is spoken by the tool, then call disconnects.
END_CALL_TOOL = EndCallTool(
    delete_room=True,
    end_instructions="Thank you so much for ordering with us. Goodbye.",
    extra_description=(
        "Call this tool (no parameters) when: (1) You have given the customer the shop number and/or pick-up address and they said they have no more questions. "
        "(2) You have said 'Our manager would be calling you in a while.' (3) The customer says goodbye or 'that's all'. "
        "You MUST call end_call at the end of every conversation. After calling, do not generate any more text."
    ),
)


def _format_chat_item_for_transcript(item) -> str:
    """Format a single chat history item as a line for the transcript."""
    if item.type == "message":
        content = (item.text_content or "").replace("\n", " ")
        text = f"{item.role}: {content}"
        if getattr(item, "interrupted", False):
            text += " (interrupted)"
        return text
    if item.type == "function_call":
        return f"[tool] {item.name}({item.arguments})"
    if item.type == "function_call_output":
        err = " (error)" if item.is_error else ""
        return f"[tool result] {item.name}: {item.output}{err}"
    if item.type == "agent_handoff":
        return f"[handoff] {getattr(item, 'old_agent_id', '')} -> {item.new_agent_id}"
    if item.type == "agent_config_update":
        return "[config update]"
    return f"[unknown item type: {item.type}]"


async def on_session_end(ctx: JobContext) -> None:
    """Generate a transcript per call: session report JSON + readable transcript TXT."""
    try:
        report = ctx.make_session_report()
    except RuntimeError as e:
        print(f"Session report skipped: {e}")
        return

    room_name = ctx.room.name or "unknown"
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    base_name = f"{room_name}_{timestamp}"

    TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)

    # Full session report (conversation history, events, config, etc.)
    report_path = TRANSCRIPTS_DIR / f"session_report_{base_name}.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report.to_dict(), f, indent=2, ensure_ascii=False)
    print(f"Session report for {room_name} saved to {report_path}")

    # Human-readable transcript (turn-by-turn)
    transcript_path = TRANSCRIPTS_DIR / f"transcript_{base_name}.txt"
    lines = []
    for item in report.chat_history.items:
        lines.append(_format_chat_item_for_transcript(item))
    with open(transcript_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Transcript for {room_name} saved to {transcript_path}")


class Assistant(PhiloToolsMixin, Agent):
    def __init__(self) -> None:
        super().__init__(instructions=PHILO_INSTRUCTIONS, tools=[END_CALL_TOOL])


server = AgentServer()


@server.rtc_session(agent_name="Philo-Coffee-Agent", on_session_end=on_session_end)
async def my_agent(ctx: JobContext):
    # Logging setup
    # Add any other context you want in all log entries here
    ctx.log_context_fields = {
        "room": ctx.room.name,
    }


    # ============================================
    # AUDIO CONFIGURATION FOR BETTER VOICE QUALITY
    # ============================================
    # Get audio configuration from environment variables with defaults
    # Optimized for telephony with 16kHz sample rate (recommended for phone calls)
    AUDIO_SAMPLE_RATE = int(os.getenv("AUDIO_SAMPLE_RATE", "16000"))  # 16kHz (recommended for telephony)
    TELEPHONY_SAMPLE_RATE = int(os.getenv("TELEPHONY_SAMPLE_RATE", "16000"))  # Telephony target rate
    AUDIO_ENCODING = os.getenv("AUDIO_ENCODING", "pcm16")  # PCM format
    AUDIO_CHANNELS = int(os.getenv("AUDIO_CHANNELS", "1"))  # Mono audio
    AUDIO_FRAME_SIZE = int(os.getenv("AUDIO_FRAME_SIZE", "320"))  # Frames per packet (20ms at 16kHz)

    print("Audio Configuration:")
    print(f"  Sample Rate: {AUDIO_SAMPLE_RATE} Hz (optimized for telephony)")
    print(f"  Telephony Rate: {TELEPHONY_SAMPLE_RATE} Hz")
    print(f"  Encoding: {AUDIO_ENCODING}")
    print(f"  Channels: {AUDIO_CHANNELS}")
    print(f"  Frame Size: {AUDIO_FRAME_SIZE}")

    # ============================================
    # TTS CONFIGURATION (OpenAI)
    # ============================================
    # High-quality OpenAI TTS for clear telephony audio
    tts_provider = openai.TTS(
        model="tts-1-hd",  # high-definition TTS model
        voice="shimmer",   # warm, barista-friendly (valid: nova, shimmer, echo, onyx, fable, alloy, ash, sage, coral)
    )

    # ============================================
    # START AGENT SESSION
    # ============================================
    # Use OpenAI Realtime model with server-side VAD
    session = AgentSession(
        llm=openai.realtime.RealtimeModel(
            model="gpt-4o-realtime-preview",
            voice="shimmer",
            # Server-side VAD configuration (OpenAI)
            turn_detection={
                "type": "server_vad",
                "silence_duration_ms": 350,
                "prefix_padding_ms": 150,
                "threshold": 0.5,
                "create_response": True,
                "interrupt_response": True,
                "idle_timeout_ms": 5000,
            },
            temperature=0.8,
        ),
        # Use OpenAI TTS with high-quality settings
        tts=tts_provider,
        # Allow the LLM to generate a response while waiting for end of turn
        preemptive_generation=True,
    )

    # Join the room first so the greeting is heard immediately.
    await ctx.connect()

    # Start the session, which initializes the voice pipeline and warms up the models
    await session.start(
        agent=Assistant(),
        room=ctx.room,
        room_options=room_io.RoomOptions(
            audio_input=room_io.AudioInputOptions(
                noise_cancellation=lambda params: (
                    noise_cancellation.BVCTelephony()
                    if params.participant.kind
                    == rtc.ParticipantKind.PARTICIPANT_KIND_SIP
                    else noise_cancellation.BVC()
                ),
            ),
        ),
    )

    # Speak a greeting immediately (don't wait for the user to speak first).
    await session.say("Hey there! Welcome to the Philo Coffee Shop. I am your Coffee barista bot, Philo.How can I help you?")


if __name__ == "__main__":
    cli.run_app(server)
