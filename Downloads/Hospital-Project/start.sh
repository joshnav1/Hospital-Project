#!/usr/bin/env bash
# start.sh — launches the full Patient Triage application
# Usage: ./start.sh

set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"

# ── Colours ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

log()  { echo -e "${CYAN}[triage]${NC} $*"; }
ok()   { echo -e "${GREEN}[triage]${NC} $*"; }
warn() { echo -e "${YELLOW}[triage]${NC} $*"; }
die()  { echo -e "${RED}[triage] ERROR:${NC} $*"; exit 1; }

# ── Trap: kill background processes on exit ───────────────────────────────────
cleanup() {
  echo ""
  log "Shutting down..."
  [ -n "$BACKEND_PID" ] && kill "$BACKEND_PID" 2>/dev/null
  [ -n "$FRONTEND_PID" ] && kill "$FRONTEND_PID" 2>/dev/null
  ok "Done."
}
trap cleanup EXIT INT TERM

# ── 1. Check .env ─────────────────────────────────────────────────────────────
if [ ! -f "$ROOT/.env" ]; then
  warn ".env not found — copying from .env.example"
  cp "$ROOT/.env.example" "$ROOT/.env"
  die "Please set GEMINI_API_KEY in .env and re-run."
fi

# shellcheck source=/dev/null
source "$ROOT/.env"
if [ -z "$GEMINI_API_KEY" ] || [ "$GEMINI_API_KEY" = "your_gemini_api_key_here" ]; then
  die "GEMINI_API_KEY is not set in .env"
fi
ok "API key found."

# ── 2. Python venv ────────────────────────────────────────────────────────────
VENV="$ROOT/.venv"
if [ ! -d "$VENV" ]; then
  log "Creating Python virtual environment..."
  python3 -m venv "$VENV"
fi

# shellcheck source=/dev/null
source "$VENV/bin/activate"

log "Installing/verifying Python dependencies..."
pip install -q -r "$ROOT/requirements.txt"
ok "Python dependencies ready."

# ── 3. Node dependencies ──────────────────────────────────────────────────────
FRONTEND="$ROOT/frontend"
if [ ! -d "$FRONTEND/node_modules" ]; then
  log "Installing frontend dependencies (npm install)..."
  cd "$FRONTEND" && npm install --silent
  cd "$ROOT"
fi
ok "Frontend dependencies ready."

# ── 4. Start FastAPI backend ──────────────────────────────────────────────────
log "Starting FastAPI backend on http://localhost:8000 ..."
cd "$ROOT"
uvicorn app.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

# Wait for backend to be ready
for i in $(seq 1 20); do
  if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
    ok "Backend is up."
    break
  fi
  sleep 0.5
  if [ "$i" -eq 20 ]; then
    die "Backend failed to start. Check logs above."
  fi
done

# ── 5. Start React frontend ───────────────────────────────────────────────────
log "Starting React frontend on http://localhost:5173 ..."
cd "$FRONTEND"
npm run dev &
FRONTEND_PID=$!
cd "$ROOT"

# Wait for frontend to be ready
for i in $(seq 1 20); do
  if curl -sf http://localhost:5173 > /dev/null 2>&1; then
    break
  fi
  sleep 0.5
done

# ── 6. Ready ──────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${GREEN}========================================${NC}"
echo -e "${BOLD}  Patient Triage Agent is running${NC}"
echo -e "${BOLD}${GREEN}========================================${NC}"
echo -e "  ${BOLD}UI      ${NC}→  http://localhost:5173"
echo -e "  ${BOLD}API     ${NC}→  http://localhost:8000"
echo -e "  ${BOLD}Docs    ${NC}→  http://localhost:8000/docs"
echo -e "  ${BOLD}Health  ${NC}→  http://localhost:8000/health"
echo -e "${BOLD}${GREEN}========================================${NC}"
echo -e "  Press ${BOLD}Ctrl+C${NC} to stop all services."
echo ""

# Keep script alive until Ctrl+C
wait