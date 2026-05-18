#!/usr/bin/env bash
# test_scenarios.sh — curl-based API scenario tests
# Usage: ./test_scenarios.sh [BASE_URL]
# Default BASE_URL: http://localhost:8000

set -euo pipefail

BASE="${1:-http://localhost:8000}"

# ── Colours ───────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; DIM='\033[2m'; NC='\033[0m'

PASS=0; FAIL=0

# ── Helpers ───────────────────────────────────────────────────────────────────
header()  { echo -e "\n${BOLD}${CYAN}══ $* ══${NC}"; }
info()    { echo -e "  ${DIM}$*${NC}"; }

pass() {
  PASS=$((PASS + 1))
  echo -e "  ${GREEN}✔ PASS${NC}  $*"
}

fail() {
  FAIL=$((FAIL + 1))
  echo -e "  ${RED}✘ FAIL${NC}  $*"
}

# assert_contains LABEL response expected_substring
assert_contains() {
  local label="$1" body="$2" needle="$3"
  if echo "$body" | grep -q "$needle"; then
    pass "$label"
  else
    fail "$label — expected to find: $needle"
    echo -e "    ${DIM}Response: ${body:0:300}${NC}"
  fi
}

# assert_status LABEL actual expected
assert_status() {
  local label="$1" actual="$2" expected="$3"
  if [ "$actual" = "$expected" ]; then
    pass "$label (HTTP $actual)"
  else
    fail "$label — expected HTTP $expected, got $actual"
  fi
}

# post ENDPOINT BODY  →  sets $RESPONSE and $STATUS
post() {
  local endpoint="$1" body="$2"
  RESPONSE=$(curl -s -w '\n__STATUS__%{http_code}' -X POST "$BASE$endpoint" \
    -H "Content-Type: application/json" -d "$body")
  STATUS=$(echo "$RESPONSE" | tail -1 | sed 's/__STATUS__//')
  RESPONSE=$(echo "$RESPONSE" | sed '$d')
}

# get ENDPOINT  →  sets $RESPONSE and $STATUS
get() {
  local endpoint="$1"
  RESPONSE=$(curl -s -w '\n__STATUS__%{http_code}' "$BASE$endpoint")
  STATUS=$(echo "$RESPONSE" | tail -1 | sed 's/__STATUS__//')
  RESPONSE=$(echo "$RESPONSE" | sed '$d')
}

# extract JSON field value (simple grep-based, no jq required)
field() { echo "$1" | grep -o "\"$2\":[^,}]*" | head -1 | sed "s/\"$2\"://;s/\"//g;s/ //g"; }

# ── Server reachability ───────────────────────────────────────────────────────
header "Pre-flight check"
if ! curl -sf "$BASE/health" > /dev/null 2>&1; then
  echo -e "${RED}ERROR: Server not reachable at $BASE${NC}"
  echo -e "  Start the server first:  ${BOLD}./start.sh${NC}"
  exit 1
fi
pass "Server is reachable at $BASE"

# ─────────────────────────────────────────────────────────────────────────────
# 1. HEALTH
# ─────────────────────────────────────────────────────────────────────────────
header "1. Health check"

get "/health"
assert_status "GET /health" "$STATUS" "200"
assert_contains "status=ok" "$RESPONSE" '"status":"ok"'
assert_contains "model field present" "$RESPONSE" '"model"'

# ─────────────────────────────────────────────────────────────────────────────
# 2. TRIAGE — RED-FLAG SCENARIOS
# ─────────────────────────────────────────────────────────────────────────────
header "2a. Cardiac emergency — chest pain + shortness of breath → Cardiology"

post "/triage" '{
  "patient_name": "Ravi Kumar",
  "age": 54,
  "gender": "male",
  "symptoms": ["severe chest pain", "shortness of breath"],
  "vitals": {"heart_rate_bpm": 108, "temperature_celsius": 37.2}
}'
assert_status "POST /triage cardiac" "$STATUS" "200"
assert_contains "triage_level = EMERGENCY" "$RESPONSE" '"triage_level":"EMERGENCY"'
assert_contains "red_flag = CARDIAC_EVENT_RISK" "$RESPONSE" "CARDIAC_EVENT_RISK"
assert_contains "routed to Cardiology (DEPT-002)" "$RESPONSE" '"matched_department_id":"DEPT-002"'
CARDIAC_ID=$(field "$RESPONSE" "patient_id")
info "patient_id: $CARDIAC_ID"


header "2b. Stroke risk — FAST triad → Emergency Medicine"

post "/triage" '{
  "patient_name": "Sunil Mehta",
  "age": 65,
  "gender": "male",
  "symptoms": ["face drooping", "arm weakness", "speech difficulty"]
}'
assert_status "POST /triage stroke" "$STATUS" "200"
assert_contains "triage_level = EMERGENCY" "$RESPONSE" '"triage_level":"EMERGENCY"'
assert_contains "red_flag = STROKE_RISK" "$RESPONSE" "STROKE_RISK"
assert_contains "routed to Emergency Medicine (DEPT-001)" "$RESPONSE" '"matched_department_id":"DEPT-001"'
STROKE_ID=$(field "$RESPONSE" "patient_id")
info "patient_id: $STROKE_ID"


header "2c. Pediatric high fever — age 8 + fever → Pediatrics"

post "/triage" '{
  "patient_name": "Arjun Singh",
  "age": 8,
  "gender": "male",
  "symptoms": ["fever", "headache"],
  "vitals": {"temperature_celsius": 39.9}
}'
assert_status "POST /triage pediatric" "$STATUS" "200"
assert_contains "triage_level = URGENT" "$RESPONSE" '"triage_level":"URGENT"'
assert_contains "red_flag = PEDIATRIC_HIGH_FEVER" "$RESPONSE" "PEDIATRIC_HIGH_FEVER"
assert_contains "routed to Pediatrics (DEPT-004)" "$RESPONSE" '"matched_department_id":"DEPT-004"'
PEDIATRIC_ID=$(field "$RESPONSE" "patient_id")
info "patient_id: $PEDIATRIC_ID"


header "2d. Standard presentation — mild symptoms"

post "/triage" '{
  "patient_name": "Priya Sharma",
  "age": 35,
  "gender": "female",
  "symptoms": ["mild headache", "fatigue"],
  "symptom_duration_hours": 4
}'
assert_status "POST /triage standard" "$STATUS" "200"
assert_contains "has patient_id" "$RESPONSE" '"patient_id"'
assert_contains "has triage_level" "$RESPONSE" '"triage_level"'
assert_contains "has matched_department" "$RESPONSE" '"matched_department"'
STANDARD_ID=$(field "$RESPONSE" "patient_id")
info "patient_id: $STANDARD_ID"


header "2e. With full vitals and history"

post "/triage" '{
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
    "oxygen_saturation_pct": 96
  },
  "notes": "Patient appears anxious, reports symptoms started after climbing stairs"
}'
assert_status "POST /triage with full payload" "$STATUS" "200"
assert_contains "has clinical_summary" "$RESPONSE" '"clinical_summary"'
assert_contains "has recommended_actions" "$RESPONSE" '"recommended_actions"'


# ─────────────────────────────────────────────────────────────────────────────
# 3. TRIAGE — VALIDATION ERRORS (422)
# ─────────────────────────────────────────────────────────────────────────────
header "3a. Validation — empty symptoms"

post "/triage" '{"patient_name":"Test","age":25,"gender":"male","symptoms":[]}'
assert_status "422 on empty symptoms" "$STATUS" "422"
assert_contains "detail array in response" "$RESPONSE" '"detail"'


header "3b. Validation — missing symptoms field"

post "/triage" '{"patient_name":"Test","age":25,"gender":"male"}'
assert_status "422 on missing symptoms" "$STATUS" "422"


header "3c. Validation — missing patient name"

post "/triage" '{"age":25,"gender":"male","symptoms":["headache"]}'
assert_status "422 on missing patient_name" "$STATUS" "422"


header "3d. Validation — invalid gender value"

post "/triage" '{"patient_name":"Test","age":25,"gender":"robot","symptoms":["headache"]}'
assert_status "422 on invalid gender" "$STATUS" "422"


header "3e. Validation — age out of range (200)"

post "/triage" '{"patient_name":"Test","age":200,"gender":"male","symptoms":["headache"]}'
assert_status "422 on age=200" "$STATUS" "422"


header "3f. Validation — negative age"

post "/triage" '{"patient_name":"Test","age":-1,"gender":"male","symptoms":["headache"]}'
assert_status "422 on age=-1" "$STATUS" "422"


# ─────────────────────────────────────────────────────────────────────────────
# 4. STREAMING  /triage/stream
# ─────────────────────────────────────────────────────────────────────────────
header "4a. Streaming — cardiac case emits all SSE event types"

STREAM=$(curl -s -N -X POST "$BASE/triage/stream" \
  -H "Content-Type: application/json" \
  -d '{
    "patient_name": "Stream Cardiac",
    "age": 60,
    "gender": "male",
    "symptoms": ["chest pain", "shortness of breath"]
  }')

assert_contains "SSE: start event" "$STREAM" 'event: start'
assert_contains "SSE: red_flags event" "$STREAM" 'event: red_flags'
assert_contains "SSE: reasoning event" "$STREAM" 'event: reasoning'
assert_contains "SSE: complete event" "$STREAM" 'event: complete'
assert_contains "SSE: CARDIAC_EVENT_RISK in red_flags" "$STREAM" 'CARDIAC_EVENT_RISK'
assert_contains "SSE: complete has triage_level" "$STREAM" 'triage_level'
STREAM_ID=$(echo "$STREAM" | grep -o '"patient_id":"[^"]*"' | head -1 | sed 's/"patient_id":"//;s/"//')
info "streamed patient_id: $STREAM_ID"


header "4b. Streaming — standard case emits start + complete (no red_flags)"

STREAM2=$(curl -s -N -X POST "$BASE/triage/stream" \
  -H "Content-Type: application/json" \
  -d '{
    "patient_name": "Stream Standard",
    "age": 30,
    "gender": "female",
    "symptoms": ["mild back pain"]
  }')

assert_contains "SSE: start event" "$STREAM2" 'event: start'
assert_contains "SSE: complete event" "$STREAM2" 'event: complete'


header "4c. Streaming — 422 on empty symptoms"

STATUS_STREAM=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE/triage/stream" \
  -H "Content-Type: application/json" \
  -d '{"patient_name":"Bad","age":25,"gender":"male","symptoms":[]}')
assert_status "422 on empty symptoms (stream)" "$STATUS_STREAM" "422"


# ─────────────────────────────────────────────────────────────────────────────
# 5. REPORT RETRIEVAL
# ─────────────────────────────────────────────────────────────────────────────
header "5a. Get report — existing patient"

get "/report/$STANDARD_ID"
assert_status "GET /report/{id} existing" "$STATUS" "200"
assert_contains "patient_id matches" "$RESPONSE" "$STANDARD_ID"


header "5b. Get report — streamed patient stored"

if [ -n "$STREAM_ID" ]; then
  get "/report/$STREAM_ID"
  assert_status "GET /report streamed patient" "$STATUS" "200"
else
  fail "GET /report streamed patient — could not extract stream patient_id"
fi


header "5c. Get report — non-existent ID returns 404"

get "/report/00000000-0000-0000-0000-000000000000"
assert_status "GET /report unknown id" "$STATUS" "404"


# ─────────────────────────────────────────────────────────────────────────────
# 6. ESCALATION
# ─────────────────────────────────────────────────────────────────────────────
header "6a. Escalate standard patient → EMERGENCY"

post "/escalate" "{\"patient_id\":\"$STANDARD_ID\",\"reason\":\"Rapid deterioration observed\"}"
assert_status "POST /escalate" "$STATUS" "200"
assert_contains "matched to DEPT-001" "$RESPONSE" '"matched_department_id":"DEPT-001"'
assert_contains "response has patient_id" "$RESPONSE" "$STANDARD_ID"


header "6b. Verify escalated report reflects EMERGENCY"

get "/report/$STANDARD_ID"
assert_contains "triage_level is EMERGENCY" "$RESPONSE" '"triage_level":"EMERGENCY"'
assert_contains "escalated=true" "$RESPONSE" '"escalated":true'


header "6c. Escalate already-EMERGENCY patient — idempotent message"

post "/escalate" "{\"patient_id\":\"$CARDIAC_ID\",\"reason\":\"Re-escalation test\"}"
assert_status "POST /escalate already-emergency" "$STATUS" "200"
assert_contains "message mentions already" "$RESPONSE" "already"


header "6d. Escalation — non-existent patient returns 404"

post "/escalate" '{"patient_id":"00000000-0000-0000-0000-000000000000","reason":"Test"}'
assert_status "POST /escalate unknown id" "$STATUS" "404"


header "6e. Get escalation status — escalated patient"

get "/escalate/$STANDARD_ID"
assert_status "GET /escalate/{id} escalated" "$STATUS" "200"
assert_contains "escalated=true" "$RESPONSE" '"escalated":true'
assert_contains "triage_level=EMERGENCY" "$RESPONSE" '"triage_level":"EMERGENCY"'


header "6f. Get escalation status — non-escalated patient"

get "/escalate/$PEDIATRIC_ID"
assert_status "GET /escalate/{id} not escalated" "$STATUS" "200"
assert_contains "escalated=false" "$RESPONSE" '"escalated":false'


header "6g. Get escalation status — non-existent returns 404"

get "/escalate/00000000-0000-0000-0000-000000000000"
assert_status "GET /escalate unknown id" "$STATUS" "404"


# ─────────────────────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────────────────────
TOTAL=$((PASS + FAIL))
echo ""
echo -e "${BOLD}════════════════════════════════${NC}"
echo -e "${BOLD}  Results: $TOTAL tests${NC}"
echo -e "  ${GREEN}Passed: $PASS${NC}"
[ "$FAIL" -gt 0 ] && echo -e "  ${RED}Failed: $FAIL${NC}" || echo -e "  ${GREEN}Failed: $FAIL${NC}"
echo -e "${BOLD}════════════════════════════════${NC}"
echo ""

[ "$FAIL" -eq 0 ] && exit 0 || exit 1