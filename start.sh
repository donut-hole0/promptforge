#!/bin/bash
set -e

echo "🚀 PromptForge — Starting full stack"

# Ensure .env exists
if [ ! -f .env ]; then
  echo "⚠️  .env file not found. Using .env.example as template."
  cp .env.example .env
  echo "📝 Please fill in your API keys in .env file"
fi

# Start backend
echo "📡 Starting backend (http://localhost:8000)..."
python server.py &
BACKEND_PID=$!

# Wait for backend to start
sleep 2

# Start frontend
echo "🎨 Starting dashboard (http://localhost:3000)..."
cd dashboard
npm install
npm run dev &
FRONTEND_PID=$!

echo ""
echo "✅ PromptForge running:"
echo "   Backend:  http://localhost:8000"
echo "   Dashboard: http://localhost:3000"
echo "   API Docs: http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop"

# Wait for both processes
wait $BACKEND_PID $FRONTEND_PID
