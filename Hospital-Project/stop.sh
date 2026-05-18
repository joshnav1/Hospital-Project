#!/usr/bin/env bash
# stop.sh — stops the Patient Triage application (backend + frontend)
# Usage: ./stop.sh

RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; NC='\033[0m'

log()  { echo -e "${CYAN}[triage]${NC} $*"; }
ok()   { echo -e "${GREEN}[triage]${NC} $*"; }
warn() { echo -e "${RED}[triage]${NC} $*"; }

stopped=0

# Kill uvicorn (FastAPI backend on port 8000)
BACKEND_PIDS=$(lsof -ti tcp:8000 2>/dev/null)
if [ -n "$BACKEND_PIDS" ]; then
  log "Stopping FastAPI backend (port 8000)..."
  echo "$BACKEND_PIDS" | xargs kill 2>/dev/null
  ok "Backend stopped."
  stopped=1
else
  warn "No process found on port 8000."
fi

# Kill vite dev server (frontend on port 5173)
FRONTEND_PIDS=$(lsof -ti tcp:5173 2>/dev/null)
if [ -n "$FRONTEND_PIDS" ]; then
  log "Stopping React frontend (port 5173)..."
  echo "$FRONTEND_PIDS" | xargs kill 2>/dev/null
  ok "Frontend stopped."
  stopped=1
else
  warn "No process found on port 5173."
fi

if [ "$stopped" -eq 1 ]; then
  ok "All services stopped."
else
  warn "Nothing was running."
fi