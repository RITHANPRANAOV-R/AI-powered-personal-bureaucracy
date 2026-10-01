#!/usr/bin/env bash
set -e

echo "================================================================="
echo "  Starting AI-Powered Personal Bureaucracy Multi-Agent System    "
echo "================================================================="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/sih/.venv/bin/python" ]; then
    PYTHON_BIN="$SCRIPT_DIR/sih/.venv/bin/python"
elif [ -f "/home/navneeth/Projects/sih/.venv/bin/python" ]; then
    PYTHON_BIN="/home/navneeth/Projects/sih/.venv/bin/python"
else
    PYTHON_BIN="python3"
fi

# Ensure nvm node path
if [ -d "/home/navneeth/.nvm/versions/node/v24.21.0/bin" ]; then
    export PATH="/home/navneeth/.nvm/versions/node/v24.21.0/bin:$PATH"
fi

# Free any lingering processes on ports 8000 and 5173
fuser -k 8000/tcp 5173/tcp 5174/tcp 2>/dev/null || true
sleep 1

echo "1. Starting FastAPI Orchestrator Backend on http://localhost:8000..."
cd "$SCRIPT_DIR/sih"
PYTHONPATH=. $PYTHON_BIN -m uvicorn src.bureaucracy_agent.server:app --port 8000 --host 0.0.0.0 &
BACKEND_PID=$!

echo "2. Starting Vite React Frontend on http://localhost:5173..."
cd "$SCRIPT_DIR/frontend"
npm run dev -- --host 0.0.0.0 --port 5173 &
FRONTEND_PID=$!

echo ""
echo "================================================================="
echo "  ✓ Multi-Agent Backend:  http://localhost:8000                  "
echo "  ✓ Web Application UI:   http://localhost:5173                  "
echo "================================================================="
echo "Press Ctrl+C to terminate all services."

cleanup() {
    echo "Stopping servers..."
    kill $BACKEND_PID 2>/dev/null || true
    kill $FRONTEND_PID 2>/dev/null || true
    exit 0
}

trap cleanup SIGINT SIGTERM
wait
