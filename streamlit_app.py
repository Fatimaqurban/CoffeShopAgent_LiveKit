import os
import requests
import streamlit as st

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

st.set_page_config(page_title="Philo Coffee Shop Voice Agent", layout="centered")

st.title("Philo Coffee Shop Voice Agent")
st.write("Click **Start Session** to connect to the LiveKit room and talk to the agent.")

if "session" not in st.session_state:
    st.session_state["session"] = None

# Button: Start session → get JWT if needed, then call FastAPI → get LiveKit token
if st.button("Start Session"):
    try:
        headers = {}
        # When backend has JWT_SECRET set, get a session JWT first
        session_resp = requests.post(f"{BACKEND_URL}/auth/session", timeout=10)
        if session_resp.status_code == 200:
            session_data = session_resp.json()
            access_token = session_data.get("access_token")
            if access_token:
                headers["Authorization"] = f"Bearer {access_token}"
        # Request LiveKit token from POST /api/token (with or without Bearer)
        resp = requests.post(
            f"{BACKEND_URL}/api/token",
            json={},
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        st.session_state["session"] = data
        st.success(f"Session started in room `{data['room_name']}` as `{data['identity']}`.")
    except requests.exceptions.HTTPError as e:
        if e.response is not None and e.response.status_code == 401:
            st.error("Unauthorized. Backend requires JWT; ensure /auth/session is available and JWT_SECRET is set.")
        else:
            st.error(f"Failed to start session: {e}")
    except Exception as e:
        st.error(f"Failed to start session: {e}")

session = st.session_state["session"]

if session:
    # POST /api/token returns participant_token and server_url
    token = session.get("participant_token") or session.get("token")
    livekit_url = session.get("server_url") or session.get("url") or ""

    if not livekit_url:
        st.error("LIVEKIT_URL is not set in the backend response.")
    else:
        st.info("Your microphone will be used to talk to the agent. "
                "Keep this tab open while speaking.")

        # Simple HTML + JS embedding LiveKit Web SDK, with hold music until agent speaks
        html = f"""
<!DOCTYPE html>
<html>
  <head>
    <meta charset="UTF-8" />
    <script src="https://unpkg.com/livekit-client@latest/dist/livekit-client.umd.js"></script>
  </head>
  <body>
    <button id="end-call-button">End Call</button>
    <button id="unmute-button" style="display:none;">Click if you don't hear the agent</button>
    <div id="audio-container"></div>
    <script>
      (async () => {{
        const {{ Room, createLocalTracks, RoomEvent }} = LivekitClient;

        let room = new Room({{
          adaptiveStream: true,
          dynacast: true,
        }});

        // Hold music: soft looping tone until agent speaks (no external file, works offline)
        let holdMusicOsc = null;
        let holdMusicGain = null;
        let holdMusicCtx = null;

        function startHoldMusic() {{
          try {{
            holdMusicCtx = new (window.AudioContext || window.webkitAudioContext)();
            holdMusicOsc = holdMusicCtx.createOscillator();
            holdMusicGain = holdMusicCtx.createGain();
            holdMusicOsc.type = "sine";
            holdMusicOsc.frequency.setValueAtTime(220, holdMusicCtx.currentTime);
            holdMusicGain.gain.setValueAtTime(0.08, holdMusicCtx.currentTime);
            holdMusicOsc.connect(holdMusicGain);
            holdMusicGain.connect(holdMusicCtx.destination);
            holdMusicOsc.start(holdMusicCtx.currentTime);
          }} catch (e) {{
            console.warn("Hold music not started:", e);
          }}
        }}

        function stopHoldMusic() {{
          if (holdMusicOsc && holdMusicCtx) {{
            try {{
              holdMusicGain.gain.linearRampToValueAtTime(0, holdMusicCtx.currentTime + 0.2);
              holdMusicOsc.stop(holdMusicCtx.currentTime + 0.25);
            }} catch (e) {{}}
            holdMusicOsc = null;
            holdMusicGain = null;
            holdMusicCtx = null;
          }}
        }}

        // Expose a function to end the call from the button
        window.endLiveKitCall = async () => {{
          stopHoldMusic();
          if (room) {{
            try {{
              await room.disconnect();
            }} catch (err) {{
              console.error("Error disconnecting from LiveKit:", err);
            }} finally {{
              room = null;
            }}
          }}
        }};

        const btn = document.getElementById("end-call-button");
        if (btn) {{
          btn.addEventListener("click", () => {{
            window.endLiveKitCall();
          }});
        }}

        const audioContainer = document.getElementById("audio-container");
        const unmuteBtn = document.getElementById("unmute-button");
        const audioElements = [];

        unmuteBtn.onclick = () => {{
          audioElements.forEach(el => el.play().catch(() => {{}}));
          unmuteBtn.style.display = "none";
        }};

        function playAgentAudio(audioEl) {{
          if (!audioEl) return;
          stopHoldMusic();
          audioElements.push(audioEl);
          audioContainer.appendChild(audioEl);
          audioEl.play().then(() => {{
            unmuteBtn.style.display = "none";
          }}).catch(() => {{
            unmuteBtn.style.display = "inline-block";
          }});
        }}

        room.on(RoomEvent.TrackSubscribed, (track, publication, participant) => {{
          if (track.kind === "audio") {{
            const audioEl = track.attach();
            audioEl.autoplay = true;
            playAgentAudio(audioEl);
          }}
        }});

        try {{
          startHoldMusic();
          await room.connect("{livekit_url}", "{token}");

          const tracks = await createLocalTracks({{ audio: true }});
          await room.localParticipant.publishTrack(tracks[0]);

          room.remoteParticipants.forEach((p) => {{
            p.trackPublications.forEach((pub) => {{
              if (pub.track && pub.kind === "audio") {{
                const audioEl = pub.track.attach();
                audioEl.autoplay = true;
                playAgentAudio(audioEl);
              }}
            }});
          }});
        }} catch (err) {{
          stopHoldMusic();
          console.error("Error connecting to LiveKit:", err);
        }}
      }})();
    </script>
  </body>
</html>
"""
        # Render the HTML/JS in the Streamlit app (height allows buttons + audio fallback)
        st.components.v1.html(html, height=120, width=400)