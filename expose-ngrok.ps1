# Expose backend (port 8000) with ngrok for Twilio webhooks / public access.
# Prereq: Install ngrok (https://ngrok.com/download) and sign in: ngrok config add-authtoken <token>
# Start backend first: uv run uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

$port = 8000
Write-Host "Exposing localhost:$port with ngrok. Copy the https URL and set BASE_URL in .env.local" -ForegroundColor Cyan
ngrok http $port
