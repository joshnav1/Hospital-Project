# AI-Powered Patient Triage & Care Routing Agent

FastAPI + React application that triages patients using Google Gemini, applies rule-based safety overrides, routes to the best available department, and streams the assessment in real-time via SSE.

---

## Quick Start

```bash
# 1. Clone / enter the project
cd mini_project

# 2. Add your Gemini API key
cp .env.example .env
# Edit .env → set GEMINI_API_KEY=<your-key>
# Get a key at: https://aistudio.google.com/apikey

# 3. Run everything with one command
./start.sh
```

To stop all services:

```bash
./stop.sh
```

`start.sh` will:
- Check that `GEMINI_API_KEY` is set in `.env`
- Create the Python `.venv` and install dependencies if needed
- Install frontend `node_modules` if needed
- Start the FastAPI backend on **http://localhost:8000**
- Start the React UI on **http://localhost:5173**
- Print a ready banner and shut both down cleanly on `Ctrl+C`

`stop.sh` kills any process bound to port 8000 (uvicorn) and port 5173 (Vite).

---

## Project Layout

```
mini_project/
├── app/
│   ├── main.py                    # FastAPI app + CORS + lifespan
│   ├── config.py                  # Pydantic-settings (reads .env)
│   ├── schemas.py                 # All Pydantic models + TriageLevel enum
│   ├── department_data.json       # Seed provider/department store
│   ├── routers/
│   │   ├── health.py              # GET /health
│   │   └── triage.py              # API endpoints only (thin layer)
│   └── services/
│       └── triage_service.py      # All business logic
├── frontend/
│   ├── src/
│   │   ├── api.js                 # fetch wrappers for all endpoints
│   │   ├── App.jsx                # Tab layout (New Triage / Reports / Lookup)
│   │   ├── App.css                # All styles
│   │   └── components/
│   │       ├── TriageForm.jsx     # Patient intake form (SSE streaming submit)
│   │       ├── TriageReport.jsx   # Result card with escalation action
│   │       └── ReportLookup.jsx   # Fetch report by patient ID
│   └── vite.config.js             # Proxy: /triage /report /escalate /health → :8000
├── test_gemini.py                 # 18 unit tests
├── Dockerfile
├── docker-compose.yml
├── start.sh                       # Start backend + frontend
├── stop.sh                        # Stop backend + frontend
├── requirements.txt
└── .env.example
```

---

## Architecture

```
POST /triage  (or /triage/stream for SSE)
  │
  ├─► Red-Flag Detection Engine        (runs before LLM — safety overrides)
  │     CARDIAC_EVENT_RISK   → chest pain + shortness of breath
  │                            → EMERGENCY, routes to Cardiology (DEPT-002)
  │                              falls back to Emergency Medicine if Cardiology full
  │     STROKE_RISK          → face drooping + arm weakness + speech difficulty
  │                            → EMERGENCY, routes to Emergency Medicine (DEPT-001)
  │     PEDIATRIC_HIGH_FEVER → age ≤ 12 + fever > 39°C (vitals) or "fever" in symptoms
  │                            → URGENT, routes to Pediatrics (DEPT-004)
  │
  ├─► Gemini LLM Assessment            (gemini-2.5-flash, falls back to rule-based)
  │     Streams via streamGenerateContent?alt=sse
  │     Returns: triage_level, score, suggested_dept, red_flags, clinical_summary
  │
  └─► Department Matcher
        Filters by accepts_triage_level
        Checks available_slots → sets capacity_flag + next_best_department
```

Red-flag rules are evaluated **before** the LLM. If a rule fires, its `triage_level` and `department` override whatever the LLM returns. The LLM assessment still runs and its clinical summary is included in the report.

### SSE Stream Events

When using `POST /triage/stream`, events arrive in this order:

| Event | Timing | Payload |
|-------|--------|---------|
| `start` | ~0 ms | `{ patient_id }` |
| `red_flags` | ~1 ms | `{ flags[], override_level }` |
| `reasoning` | ~300 ms+ | `{ text }` — one per LLM token chunk |
| `complete` | ~1–2 s | Full `TriageReport` JSON |

The React UI consumes the stream using `fetch` + `ReadableStream` (not `EventSource`, which only supports GET).

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Service health + model info |
| POST | `/triage` | Submit patient → full triage report (blocking) |
| POST | `/triage/stream` | Submit patient → SSE streaming response |
| GET | `/report/{patient_id}` | Retrieve stored triage report |
| POST | `/escalate` | Manually escalate patient to EMERGENCY |
| GET | `/escalate/{patient_id}` | Get escalation status |
| GET | `/docs` | Swagger UI |

---

## Example curl Requests

### Standard triage
```bash
curl -X POST http://localhost:8000/triage \
  -H "Content-Type: application/json" \
  -d '{
    "patient_name": "Ravi Kumar",
    "age": 54,
    "gender": "male",
    "symptoms": ["severe chest pain", "shortness of breath"],
    "vitals": { "heart_rate_bpm": 108, "temperature_celsius": 37.2 }
  }'
```
Expected: `triage_level: EMERGENCY`, `matched_department: Cardiology`, `red_flags: ["CARDIAC_EVENT_RISK"]`

### Streaming triage
```bash
curl -N -X POST http://localhost:8000/triage/stream \
  -H "Content-Type: application/json" \
  -d '{
    "patient_name": "Arjun Singh",
    "age": 8,
    "gender": "male",
    "symptoms": ["fever", "headache"],
    "vitals": { "temperature_celsius": 39.9 }
  }'
```
Expected events: `start` → `red_flags: PEDIATRIC_HIGH_FEVER` → `reasoning` chunks → `complete`

### Retrieve report
```bash
curl http://localhost:8000/report/<patient_id>
```

### Escalate a patient
```bash
curl -X POST http://localhost:8000/escalate \
  -H "Content-Type: application/json" \
  -d '{ "patient_id": "<patient_id>", "reason": "Rapid deterioration" }'
```

### Check escalation status
```bash
curl http://localhost:8000/escalate/<patient_id>
```

---

## Configuration

All settings are read from `.env` (never hard-coded):

| Variable | Default | Description |
|----------|---------|-------------|
| `GEMINI_API_KEY` | **required** | Google AI Studio API key |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Gemini model ID |
| `APP_ENV` | `development` | Environment label |
| `LOG_LEVEL` | `INFO` | Logging level |

> After changing `.env`, restart the server — settings are LRU-cached and won't reload on the fly.

---

## Running Tests

```bash
source .venv/bin/activate
pytest test_gemini.py -v
```

18 tests covering:
- Red-flag detection (cardiac, stroke, pediatric fever — from vitals and symptom text)
- Edge cases (adult fever no-flag, benign symptoms, cardiac requires both symptoms)
- Department routing and capacity fallback
- Rule-based fallback triage
- Input validation (empty symptoms, invalid gender, out-of-range age)

---

## Docker

Both services are containerised and wired together via `docker-compose.yml`.

```bash
docker compose up --build
```

| Service | Container | Port | Description |
|---------|-----------|------|-------------|
| `backend` | `triage-backend` | 8000 | FastAPI + uvicorn |
| `frontend` | `triage-frontend` | 80 | React app served by nginx |

- The frontend nginx config proxies `/triage`, `/report`, `/escalate`, and `/health` to the backend container — no CORS issues.
- SSE streaming is supported: nginx buffering is disabled for those routes.
- The frontend container waits for the backend health check to pass before starting (`depends_on: condition: service_healthy`).

To build images individually:

```bash
# Backend
docker build -t triage-backend .

# Frontend
docker build -t triage-frontend ./frontend
```

Open **http://localhost** (port 80) for the UI, or **http://localhost:8000** for the API directly.

---

## Triage Levels

| Level | Priority | Target Time |
|-------|----------|-------------|
| EMERGENCY | 1 | Immediate |
| URGENT | 2 | Within 30 min |
| STANDARD | 3 | Within 2 hours |
| SELF_CARE | 4 | Home care / scheduled |

---

## Department Seed Data

| ID | Department | Accepts | Slots | Hours |
|----|-----------|---------|-------|-------|
| DEPT-001 | Emergency Medicine | EMERGENCY, URGENT | 3 | 24/7 |
| DEPT-002 | Cardiology | EMERGENCY, URGENT | 1 | 24/7 |
| DEPT-003 | General Practice | STANDARD, SELF_CARE | 5 | 08:00–20:00 |
| DEPT-004 | Pediatrics | EMERGENCY, URGENT, STANDARD | 2 | 24/7 |
| DEPT-005 | Mental Health Unit | URGENT, STANDARD | 0 | 09:00–21:00 |

**Routing rules:**
- Chest pain + shortness of breath → **Cardiology** (DEPT-002) primary, Emergency Medicine fallback if full
- Stroke triad (face droop + arm weakness + speech difficulty) → **Emergency Medicine** (DEPT-001)
- Child (age ≤ 12) + fever → **Pediatrics** (DEPT-004)