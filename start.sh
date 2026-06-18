#!/bin/bash
set -e

echo "🚀 PromptForge — Starting full stack"

# Ensure .env exists
if [ ! -f .env ]; then
  echo "⚠️  .env file not found. Using .env.example as template."
  cp .env.example .env
  echo "📝 Please fill in your API keys in .env file"
fi

# Start engine (FastAPI) on :8000
echo "📡 Starting engine (http://localhost:8000)..."
python3 server.py &
ENGINE_PID=$!

# Wait for the engine to come up
sleep 2

# Start dashboard (FastAPI + static UI) on :8050 — proxies to the engine,
# falls back to a local mock when the engine is offline.
echo "🎨 Starting dashboard (http://localhost:8050)..."
python3 -m uvicorn dashboard.app:app --port 8050 &
DASHBOARD_PID=$!

echo ""
echo "✅ PromptForge running:"
echo "   Engine:    http://localhost:8000"
echo "   Dashboard: http://localhost:8050"
echo "   API Docs:  http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop"

# Stop both children on Ctrl+C
trap 'kill $ENGINE_PID $DASHBOARD_PID 2>/dev/null' INT TERM

# Wait for both processes
wait $ENGINE_PID $DASHBOARD_PID
