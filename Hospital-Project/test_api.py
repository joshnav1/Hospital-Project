"""
API scenario tests for the Patient Triage & Care Routing Agent.

Requires the server to be running:
    ./start.sh   OR   uvicorn app.main:app --port 8000

Run:
    python test_api.py
    python test_api.py http://localhost:8000   # custom base URL

Results are written to: test_results.json
"""

import json
import sys
import httpx
from datetime import datetime, timezone

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
RESULTS_FILE = "test_results.json"

# ─────────────────────────────────────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────────────────────────────────────

scenarios = []   # accumulated results
_ids = {}        # patient IDs shared across scenarios


def run(name, method, path, payload=None, assertions=None, sse=False):
    """Execute one API call, check assertions, store full request+response."""
    url = BASE + path
    request_record = {"method": method, "url": url, "payload": payload}
    response_record = {}
    assertion_results = []
    passed = True

    try:
        if sse:
            # Consume full SSE stream
            with httpx.Client(timeout=30.0) as client:
                with client.stream(method, url, json=payload) as r:
                    raw = r.read().decode()
            response_record["status"] = r.status_code
            response_record["body_raw"] = raw
            response_record["events"] = _parse_sse(raw)
            check_target = raw
            actual_status = r.status_code
        else:
            with httpx.Client(timeout=30.0) as client:
                r = client.request(method, url, json=payload)
            try:
                body = r.json()
            except Exception:
                body = r.text
            response_record["status"] = r.status_code
            response_record["body"] = body
            check_target = json.dumps(body)
            actual_status = r.status_code

    except Exception as exc:
        response_record["error"] = str(exc)
        actual_status = None
        check_target = ""
        passed = False

    for label, check_fn in (assertions or []):
        try:
            ok = check_fn(actual_status, check_target, response_record)
        except Exception as e:
            ok = False
            label = f"{label} [exception: {e}]"
        assertion_results.append({"check": label, "passed": bool(ok)})
        if not ok:
            passed = False

    scenarios.append({
        "name": name,
        "request": request_record,
        "response": response_record,
        "assertions": assertion_results,
        "passed": passed,
    })

    status_icon = "\033[32m✔\033[0m" if passed else "\033[31m✘\033[0m"
    print(f"  {status_icon}  {name}")
    if not passed:
        for a in assertion_results:
            if not a["passed"]:
                print(f"       \033[31m→ FAIL: {a['check']}\033[0m")

    return passed, response_record


def _parse_sse(raw):
    events = []
    current_event = None
    for line in raw.splitlines():
        if line.startswith("event: "):
            current_event = line[7:].strip()
        elif line.startswith("data: ") and current_event:
            try:
                events.append({"event": current_event, "data": json.loads(line[6:])})
            except json.JSONDecodeError:
                events.append({"event": current_event, "data": line[6:]})
            current_event = None
    return events


def status_is(expected):
    return f"HTTP {expected}", lambda s, *_: s == expected


def body_contains(substring):
    return f"body contains '{substring}'", lambda s, b, *_: substring in b


def body_not_contains(substring):
    return f"body does not contain '{substring}'", lambda s, b, *_: substring not in b


def event_exists(event_type):
    return (
        f"SSE event '{event_type}' present",
        lambda s, b, r: any(e["event"] == event_type for e in r.get("events", [])),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Pre-flight
# ─────────────────────────────────────────────────────────────────────────────

print(f"\n\033[1mPatient Triage API — Scenario Tests\033[0m")
print(f"Base URL : {BASE}")
print(f"Results  : {RESULTS_FILE}\n")

try:
    httpx.get(f"{BASE}/health", timeout=5).raise_for_status()
except Exception:
    print(f"\033[31mERROR: Server not reachable at {BASE}\033[0m")
    print("Start the server first:  ./start.sh")
    sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# 1. HEALTH
# ─────────────────────────────────────────────────────────────────────────────
print("\033[1;36m── 1. Health ──────────────────────────────────────────\033[0m")

run("Health check", "GET", "/health", assertions=[
    status_is(200),
    body_contains('"status":"ok"'),
    body_contains('"model"'),
    body_contains('"environment"'),
])


# ─────────────────────────────────────────────────────────────────────────────
# 2. TRIAGE — BLOCKING
# ─────────────────────────────────────────────────────────────────────────────
print("\033[1;36m── 2. Triage (blocking) ───────────────────────────────\033[0m")

ok, resp = run("Cardiac emergency → Cardiology", "POST", "/triage", payload={
    "patient_name": "Ravi Kumar",
    "age": 54,
    "gender": "male",
    "symptoms": ["severe chest pain", "shortness of breath"],
    "vitals": {"heart_rate_bpm": 108, "temperature_celsius": 37.2},
}, assertions=[
    status_is(200),
    body_contains('"triage_level":"EMERGENCY"'),
    body_contains("CARDIAC_EVENT_RISK"),
    body_contains('"matched_department_id":"DEPT-002"'),
])
if ok:
    _ids["cardiac"] = resp["body"]["patient_id"]

ok, resp = run("Stroke risk (FAST triad) → Emergency Medicine", "POST", "/triage", payload={
    "patient_name": "Sunil Mehta",
    "age": 65,
    "gender": "male",
    "symptoms": ["face drooping", "arm weakness", "speech difficulty"],
}, assertions=[
    status_is(200),
    body_contains('"triage_level":"EMERGENCY"'),
    body_contains("STROKE_RISK"),
    body_contains('"matched_department_id":"DEPT-001"'),
])
if ok:
    _ids["stroke"] = resp["body"]["patient_id"]

ok, resp = run("Pediatric high fever → Pediatrics", "POST", "/triage", payload={
    "patient_name": "Arjun Singh",
    "age": 8,
    "gender": "male",
    "symptoms": ["fever", "headache"],
    "vitals": {"temperature_celsius": 39.9},
}, assertions=[
    status_is(200),
    body_contains('"triage_level":"URGENT"'),
    body_contains("PEDIATRIC_HIGH_FEVER"),
    body_contains('"matched_department_id":"DEPT-004"'),
])
if ok:
    _ids["pediatric"] = resp["body"]["patient_id"]

ok, resp = run("Standard presentation — mild symptoms", "POST", "/triage", payload={
    "patient_name": "Priya Sharma",
    "age": 35,
    "gender": "female",
    "symptoms": ["mild headache", "fatigue"],
    "symptom_duration_hours": 4,
}, assertions=[
    status_is(200),
    body_contains('"patient_id"'),
    body_contains('"triage_level"'),
    body_contains('"matched_department"'),
    body_contains('"clinical_summary"'),
    body_contains('"recommended_actions"'),
])
if ok:
    _ids["standard"] = resp["body"]["patient_id"]

run("Full payload — vitals + history + medications + notes", "POST", "/triage", payload={
    "patient_name": "Meena Patel",
    "age": 48,
    "gender": "female",
    "symptoms": ["chest tightness", "dizziness"],
    "symptom_duration_hours": 1,
    "medical_history": ["hypertension", "type 2 diabetes"],
    "current_medications": ["metformin", "amlodipine"],
    "allergies": ["penicillin"],
    "vitals": {
        "temperature_celsius": 37.0,
        "heart_rate_bpm": 95,
        "blood_pressure_systolic": 158,
        "oxygen_saturation_pct": 96.0,
    },
    "notes": "Patient appears anxious, symptoms started after climbing stairs",
}, assertions=[
    status_is(200),
    body_contains('"triage_score"'),
    body_contains('"estimated_wait_minutes"'),
])

run("Self-care — minor cold symptoms", "POST", "/triage", payload={
    "patient_name": "Karan Desai",
    "age": 28,
    "gender": "male",
    "symptoms": ["runny nose", "sore throat"],
    "symptom_duration_hours": 24,
}, assertions=[
    status_is(200),
    body_contains('"triage_level"'),
])


# ─────────────────────────────────────────────────────────────────────────────
# 3. TRIAGE — VALIDATION ERRORS
# ─────────────────────────────────────────────────────────────────────────────
print("\033[1;36m── 3. Validation errors (422) ─────────────────────────\033[0m")

run("Empty symptoms list", "POST", "/triage", payload={
    "patient_name": "Test", "age": 25, "gender": "male", "symptoms": [],
}, assertions=[status_is(422), body_contains('"detail"')])

run("Missing symptoms field", "POST", "/triage", payload={
    "patient_name": "Test", "age": 25, "gender": "male",
}, assertions=[status_is(422)])

run("Missing patient_name", "POST", "/triage", payload={
    "age": 25, "gender": "male", "symptoms": ["headache"],
}, assertions=[status_is(422)])

run("Invalid gender value", "POST", "/triage", payload={
    "patient_name": "Test", "age": 25, "gender": "robot", "symptoms": ["headache"],
}, assertions=[status_is(422)])

run("Age out of range (200)", "POST", "/triage", payload={
    "patient_name": "Test", "age": 200, "gender": "male", "symptoms": ["headache"],
}, assertions=[status_is(422)])

run("Negative age (-1)", "POST", "/triage", payload={
    "patient_name": "Test", "age": -1, "gender": "male", "symptoms": ["headache"],
}, assertions=[status_is(422)])

run("Empty request body", "POST", "/triage", payload={},
    assertions=[status_is(422)])


# ─────────────────────────────────────────────────────────────────────────────
# 4. TRIAGE STREAM (SSE)
# ─────────────────────────────────────────────────────────────────────────────
print("\033[1;36m── 4. Streaming /triage/stream ────────────────────────\033[0m")

ok, resp = run("Cardiac — all 4 SSE event types", "POST", "/triage/stream", payload={
    "patient_name": "Stream Cardiac",
    "age": 60,
    "gender": "male",
    "symptoms": ["chest pain", "shortness of breath"],
}, sse=True, assertions=[
    status_is(200),
    event_exists("start"),
    event_exists("red_flags"),
    event_exists("reasoning"),
    event_exists("complete"),
    body_contains("CARDIAC_EVENT_RISK"),
])
if ok:
    complete = next((e for e in resp.get("events", []) if e["event"] == "complete"), None)
    if complete:
        _ids["streamed"] = complete["data"]["patient_id"]

run("Standard — start + reasoning + complete (no red_flags)", "POST", "/triage/stream", payload={
    "patient_name": "Stream Standard",
    "age": 30,
    "gender": "female",
    "symptoms": ["mild back pain"],
}, sse=True, assertions=[
    status_is(200),
    event_exists("start"),
    event_exists("complete"),
    body_not_contains("event: red_flags"),
])

run("Pediatric stream — red_flags event fired", "POST", "/triage/stream", payload={
    "patient_name": "Stream Child",
    "age": 6,
    "gender": "male",
    "symptoms": ["fever", "cough"],
    "vitals": {"temperature_celsius": 39.5},
}, sse=True, assertions=[
    status_is(200),
    event_exists("red_flags"),
    body_contains("PEDIATRIC_HIGH_FEVER"),
])

run("Stream — 422 on empty symptoms", "POST", "/triage/stream", payload={
    "patient_name": "Bad", "age": 25, "gender": "male", "symptoms": [],
}, assertions=[status_is(422)])

run("Stream — 422 on invalid gender", "POST", "/triage/stream", payload={
    "patient_name": "Bad", "age": 25, "gender": "robot", "symptoms": ["headache"],
}, assertions=[status_is(422)])


# ─────────────────────────────────────────────────────────────────────────────
# 5. REPORT RETRIEVAL
# ─────────────────────────────────────────────────────────────────────────────
print("\033[1;36m── 5. Report retrieval ────────────────────────────────\033[0m")

if _ids.get("standard"):
    run("Get existing report (blocking)", "GET", f"/report/{_ids['standard']}", assertions=[
        status_is(200),
        body_contains(_ids["standard"]),
    ])

if _ids.get("streamed"):
    run("Get streamed report (stored after SSE)", "GET", f"/report/{_ids['streamed']}", assertions=[
        status_is(200),
        body_contains(_ids["streamed"]),
    ])

run("Get report — unknown ID → 404", "GET", "/report/00000000-0000-0000-0000-000000000000",
    assertions=[status_is(404)])

run("Get report — malformed ID → 404", "GET", "/report/not-a-real-id",
    assertions=[status_is(404)])


# ─────────────────────────────────────────────────────────────────────────────
# 6. ESCALATION
# ─────────────────────────────────────────────────────────────────────────────
print("\033[1;36m── 6. Escalation ──────────────────────────────────────\033[0m")

if _ids.get("standard"):
    run("Escalate standard patient → EMERGENCY", "POST", "/escalate", payload={
        "patient_id": _ids["standard"],
        "reason": "Rapid deterioration observed by staff",
    }, assertions=[
        status_is(200),
        body_contains('"matched_department_id":"DEPT-001"'),
        body_contains(_ids["standard"]),
    ])

    run("Escalated report now shows EMERGENCY + escalated=true", "GET",
        f"/report/{_ids['standard']}", assertions=[
        status_is(200),
        body_contains('"triage_level":"EMERGENCY"'),
        body_contains('"escalated":true'),
    ])

if _ids.get("cardiac"):
    run("Escalate already-EMERGENCY patient — idempotent", "POST", "/escalate", payload={
        "patient_id": _ids["cardiac"],
        "reason": "Re-escalation test",
    }, assertions=[
        status_is(200),
        body_contains("already"),
    ])

run("Escalate unknown patient → 404", "POST", "/escalate", payload={
    "patient_id": "00000000-0000-0000-0000-000000000000",
    "reason": "Test",
}, assertions=[status_is(404)])

if _ids.get("standard"):
    run("Get escalation status — escalated patient", "GET",
        f"/escalate/{_ids['standard']}", assertions=[
        status_is(200),
        body_contains('"escalated":true'),
        body_contains('"triage_level":"EMERGENCY"'),
    ])

if _ids.get("pediatric"):
    run("Get escalation status — non-escalated patient", "GET",
        f"/escalate/{_ids['pediatric']}", assertions=[
        status_is(200),
        body_contains('"escalated":false'),
    ])

run("Get escalation status — unknown ID → 404", "GET",
    "/escalate/00000000-0000-0000-0000-000000000000",
    assertions=[status_is(404)])


# ─────────────────────────────────────────────────────────────────────────────
# Write results file
# ─────────────────────────────────────────────────────────────────────────────

total  = len(scenarios)
passed = sum(1 for s in scenarios if s["passed"])
failed = total - passed

output = {
    "run_at": datetime.now(timezone.utc).isoformat(),
    "base_url": BASE,
    "summary": {"total": total, "passed": passed, "failed": failed},
    "scenarios": scenarios,
}

with open(RESULTS_FILE, "w") as f:
    json.dump(output, f, indent=2, default=str)

# ─────────────────────────────────────────────────────────────────────────────
# Console summary
# ─────────────────────────────────────────────────────────────────────────────
print()
print("\033[1m══════════════════════════════════\033[0m")
print(f"\033[1m  Results  {passed}/{total} passed\033[0m")
if failed:
    print(f"  \033[31mFailed : {failed}\033[0m")
else:
    print(f"  \033[32mAll tests passed\033[0m")
print(f"  Saved  : {RESULTS_FILE}")
print("\033[1m══════════════════════════════════\033[0m\n")

sys.exit(0 if failed == 0 else 1)