"""
Business logic for the Patient Triage & Care Routing Agent.

Public surface:
  submit_triage(req)          → TriageReport
  get_report(patient_id)      → TriageReport   (raises 404 if missing)
  escalate_patient(req)       → EscalateResponse
  get_escalation_status(id)   → EscalationStatus
"""

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncGenerator, Dict, List, Optional, Tuple

import httpx
from fastapi import HTTPException

from app.config import settings
from app.schemas import (
    EscalateRequest,
    EscalateResponse,
    EscalationStatus,
    TriageLevel,
    TriageReport,
    TriageRequest,
    VitalSigns,
)

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# DEPARTMENT CATALOGUE  (seed data from department_data.json)
# ─────────────────────────────────────────────────────────────────────────────

_DEPT_FILE = Path(__file__).parent.parent / "department_data.json"


def _load_departments() -> List[Dict]:
    with open(_DEPT_FILE) as f:
        return json.load(f)["departments"]


DEPARTMENTS: List[Dict] = _load_departments()
DEPARTMENT_MAP: Dict[str, Dict] = {d["department_id"]: d for d in DEPARTMENTS}


# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

_TRIAGE_PRIORITY: Dict[str, int] = {
    "EMERGENCY": 1,
    "URGENT":    2,
    "STANDARD":  3,
    "SELF_CARE": 4,
}

_WAIT_FALLBACK: Dict[TriageLevel, int] = {
    TriageLevel.EMERGENCY: 0,
    TriageLevel.URGENT:    15,
    TriageLevel.STANDARD:  45,
    TriageLevel.SELF_CARE: 60,
}


# ─────────────────────────────────────────────────────────────────────────────
# IN-MEMORY STORE  (replace with Redis/Postgres for production)
# ─────────────────────────────────────────────────────────────────────────────

_reports: Dict[str, TriageReport] = {}

# Daily counter for patient ID generation — resets automatically each new day
_id_daily_count: Dict[str, int] = {}


def _generate_patient_id() -> str:
    """Generate a patient ID in the format RM{YYYYMMDD}{count:04d}, e.g. RM202605180003."""
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    _id_daily_count[today] = _id_daily_count.get(today, 0) + 1
    return f"RM{today}{_id_daily_count[today]:04d}"


def _decrement_slots(dept_id: str) -> None:
    dept = DEPARTMENT_MAP.get(dept_id)
    if dept and dept["available_slots"] > 0:
        dept["available_slots"] -= 1
        logger.info("SLOT_TAKEN | dept=%s | remaining=%d", dept_id, dept["available_slots"])


def _increment_slots(dept_id: str) -> None:
    dept = DEPARTMENT_MAP.get(dept_id)
    if dept:
        dept["available_slots"] += 1
        logger.info("SLOT_RELEASED | dept=%s | available=%d", dept_id, dept["available_slots"])


# ─────────────────────────────────────────────────────────────────────────────
# RED-FLAG DETECTION ENGINE  (safety overrides — always run before LLM)
# ─────────────────────────────────────────────────────────────────────────────

def _detect_red_flags(
    symptoms: List[str],
    age: int,
    vitals: Optional[VitalSigns],
) -> Tuple[List[str], Optional[TriageLevel], Optional[str]]:
    """
    Rule-based safety detector.
    Returns (flags, override_level, override_dept_id).
    STROKE_RISK and CARDIAC_EVENT_RISK force EMERGENCY regardless of LLM output.
    """
    flags: List[str] = []
    override_level: Optional[TriageLevel] = None
    override_dept_id: Optional[str] = None

    s_lower = [s.lower() for s in symptoms]
    combined = " ".join(s_lower)

    # CARDIAC_EVENT_RISK: chest pain + shortness of breath
    has_chest_pain = any("chest pain" in s for s in s_lower)
    has_sob = any(
        kw in combined
        for kw in ("shortness of breath", "short of breath", "difficulty breathing", "can't breathe")
    )
    if has_chest_pain and has_sob:
        flags.append("CARDIAC_EVENT_RISK")
        override_level = TriageLevel.EMERGENCY
        override_dept_id = "DEPT-002"  # Cardiology; falls back to Emergency if full

    # STROKE_RISK: face drooping + arm weakness + speech difficulty (FAST triad)
    has_face_droop  = any(kw in combined for kw in ("face drooping", "facial droop", "face droop", "face numb"))
    has_arm_weak    = any(kw in combined for kw in ("arm weakness", "arm weak", "arm numb", "one-sided weakness"))
    has_speech_diff = any(kw in combined for kw in ("speech difficulty", "slurred speech", "can't speak", "speech problem"))
    if has_face_droop and has_arm_weak and has_speech_diff:
        flags.append("STROKE_RISK")
        override_level = TriageLevel.EMERGENCY  # hard override — always EMERGENCY
        override_dept_id = "DEPT-001"

    # PEDIATRIC_HIGH_FEVER: age ≤ 12 with fever > 39°C (vitals) or "fever" in symptoms
    if age <= 12:
        fever_from_vitals = (
            vitals is not None
            and vitals.temperature_celsius is not None
            and vitals.temperature_celsius > 39.0
        )
        fever_in_symptoms = "fever" in combined
        if fever_from_vitals or fever_in_symptoms:
            flags.append("PEDIATRIC_HIGH_FEVER")
            if override_level is None:
                override_level = TriageLevel.URGENT
                override_dept_id = "DEPT-004"  # Pediatrics

    return flags, override_level, override_dept_id


# ─────────────────────────────────────────────────────────────────────────────
# DEPARTMENT MATCHER
# ─────────────────────────────────────────────────────────────────────────────

def _match_department(
    triage_level: TriageLevel,
    suggested_dept_id: Optional[str] = None,
    override_dept_id: Optional[str] = None,
) -> Tuple[Dict, bool, Optional[Dict]]:
    """
    Returns (matched_dept, capacity_flag, next_best_dept).
    override_dept_id (from red-flag engine) takes precedence over LLM suggestion.
    """
    def _eligible(d: Dict) -> bool:
        return triage_level.value in d["accepts_triage_level"]

    def _has_slots(d: Dict) -> bool:
        return d["available_slots"] > 0

    primary_id = override_dept_id or suggested_dept_id
    best: Optional[Dict] = None

    if primary_id and primary_id in DEPARTMENT_MAP:
        candidate = DEPARTMENT_MAP[primary_id]
        if _eligible(candidate):
            best = candidate

    if best is None:
        eligible = [d for d in DEPARTMENTS if _eligible(d)]
        best = max(eligible, key=lambda d: d["available_slots"]) if eligible else DEPARTMENT_MAP["DEPT-001"]

    capacity_flag = not _has_slots(best)
    next_best: Optional[Dict] = None
    if capacity_flag:
        for d in DEPARTMENTS:
            if d["department_id"] != best["department_id"] and _eligible(d) and _has_slots(d):
                next_best = d
                break

    return best, capacity_flag, next_best


def _estimate_wait(dept: Dict, triage_level: TriageLevel) -> int:
    return dept.get("avg_wait_minutes", _WAIT_FALLBACK[triage_level])


# ─────────────────────────────────────────────────────────────────────────────
# LLM INTEGRATION  (Google Gemini)
# ─────────────────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """
You are a senior emergency-medicine physician performing an initial triage assessment.
Respond with a single valid JSON object — no markdown fences, no extra text.

Schema:
{
  "triage_level": "<EMERGENCY|URGENT|STANDARD|SELF_CARE>",
  "triage_score": <integer 1-10, 1=most critical>,
  "suggested_department_id": "<one department_id from the provided list>",
  "chief_complaint": "<one concise sentence>",
  "clinical_summary": "<2-4 sentence clinical narrative>",
  "recommended_actions": ["...", "..."],
  "red_flags": ["..."]
}

Scoring guide:
  1-2  → EMERGENCY   (immediate life threat)
  3-4  → URGENT      (within 30 min)
  5-7  → STANDARD    (within 2 hours)
  8-10 → SELF_CARE   (home care / scheduled)

Rules:
- suggested_department_id MUST be exactly one department_id from the list provided.
- red_flags is an empty list [] when no dangerous findings exist.
- Be medically accurate; err on the side of caution for ambiguous presentations.
- NEVER return a silent failure — always return valid JSON.
""".strip()


def _build_triage_prompt(req: TriageRequest) -> str:
    vitals_str = "Not provided"
    if req.vitals:
        vitals_str = json.dumps(req.vitals.model_dump(exclude_none=True), indent=2)

    dept_summary = [
        {
            "department_id": d["department_id"],
            "name": d["name"],
            "specialty": d["specialty"],
            "accepts_triage_level": d["accepts_triage_level"],
        }
        for d in DEPARTMENTS
    ]

    return (
        f"AVAILABLE DEPARTMENTS:\n{json.dumps(dept_summary, indent=2)}\n\n"
        f"PATIENT:\n"
        f"- Name          : {req.patient_name}\n"
        f"- Age           : {req.age}\n"
        f"- Gender        : {req.gender}\n"
        f"- Symptoms      : {', '.join(req.symptoms)}\n"
        f"- Duration (h)  : {req.symptom_duration_hours or 'few'}\n"
        f"- Medical Hx    : {', '.join(req.medical_history or []) or 'none'}\n"
        f"- Medications   : {', '.join(req.current_medications or []) or 'none'}\n"
        f"- Allergies     : {', '.join(req.allergies or []) or 'none'}\n"
        f"- Vitals        :\n{vitals_str}\n"
        f"- Notes         : {req.notes or 'none'}\n\n"
        "Perform a triage assessment and return the JSON object described in the system prompt."
    )


def _strip_markdown_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


async def _call_gemini(prompt: str) -> dict:
    url = (
        f"{settings.GEMINI_BASE_URL}/models/{settings.GEMINI_MODEL}"
        f":generateContent?key={settings.GEMINI_API_KEY}"
    )
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "systemInstruction": {"parts": [{"text": _SYSTEM_PROMPT}]},
        "generationConfig": {"maxOutputTokens": 1024, "temperature": 0.2, "topP": 0.9},
    }
    async with httpx.AsyncClient(timeout=25.0) as client:
        resp = await client.post(url, json=payload)

    if resp.status_code != 200:
        raise RuntimeError(f"Gemini API error {resp.status_code}: {resp.text[:200]}")

    candidates = resp.json().get("candidates", [])
    if not candidates:
        raise RuntimeError("Gemini returned no candidates")

    text = "".join(
        part.get("text", "")
        for part in candidates[0].get("content", {}).get("parts", [])
    )
    try:
        return json.loads(_strip_markdown_fences(text))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"LLM returned non-JSON: {exc}. Raw: {text[:300]}")


def _rule_based_fallback(req: TriageRequest) -> dict:
    """Deterministic triage used when the LLM is unavailable."""
    combined = " ".join(req.symptoms).lower()

    critical = ["chest pain", "unconscious", "cardiac", "stroke", "seizure", "not breathing"]
    urgent   = ["fever", "severe pain", "vomiting blood", "head injury", "fracture", "difficulty breathing"]

    if any(kw in combined for kw in critical):
        level, score, dept = "EMERGENCY", 2, "DEPT-001"
    elif any(kw in combined for kw in urgent) or req.age <= 12:
        level, score, dept = "URGENT", 4, ("DEPT-004" if req.age <= 12 else "DEPT-001")
    else:
        level, score, dept = "STANDARD", 6, "DEPT-003"

    return {
        "triage_level": level,
        "triage_score": score,
        "suggested_department_id": dept,
        "chief_complaint": "Rule-based assessment (LLM unavailable)",
        "clinical_summary": "Automated rule-based triage performed; LLM service was unreachable.",
        "recommended_actions": ["Assess vital signs", "Assign to department", "Re-evaluate if condition changes"],
        "red_flags": [],
    }


# ─────────────────────────────────────────────────────────────────────────────
# GEMINI STREAMING
# ─────────────────────────────────────────────────────────────────────────────

async def _call_gemini_stream(prompt: str) -> AsyncGenerator[str, None]:
    """Yields raw text chunks from Gemini's streamGenerateContent SSE endpoint."""
    url = (
        f"{settings.GEMINI_BASE_URL}/models/{settings.GEMINI_MODEL}"
        f":streamGenerateContent?key={settings.GEMINI_API_KEY}&alt=sse"
    )
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "systemInstruction": {"parts": [{"text": _SYSTEM_PROMPT}]},
        "generationConfig": {"maxOutputTokens": 1024, "temperature": 0.2, "topP": 0.9},
    }
    async with httpx.AsyncClient(timeout=25.0) as client:
        async with client.stream("POST", url, json=payload) as resp:
            if resp.status_code != 200:
                raise RuntimeError(f"Gemini streaming error {resp.status_code}")
            async for line in resp.aiter_lines():
                if not line.startswith("data: ") or "[DONE]" in line:
                    continue
                try:
                    chunk = json.loads(line[6:])
                    for candidate in chunk.get("candidates", []):
                        for part in candidate.get("content", {}).get("parts", []):
                            text = part.get("text", "")
                            if text:
                                yield text
                except json.JSONDecodeError:
                    continue


def _build_report(
    patient_id: str,
    now: "datetime",
    req: TriageRequest,
    llm_data: dict,
    llm_model_used: str,
    rule_flags: List[str],
    rule_override_level: Optional[TriageLevel],
    rule_override_dept: Optional[str],
) -> TriageReport:
    """Shared report assembly used by both submit_triage and stream_triage."""
    try:
        llm_level = TriageLevel(llm_data.get("triage_level", "STANDARD"))
    except ValueError:
        llm_level = TriageLevel.STANDARD

    if rule_override_level is not None and (
        _TRIAGE_PRIORITY[rule_override_level.value] <= _TRIAGE_PRIORITY[llm_level.value]
    ):
        triage_level = rule_override_level
    else:
        triage_level = llm_level

    llm_flags = llm_data.get("red_flags", [])
    all_flags = list(dict.fromkeys(rule_flags + [f for f in llm_flags if f not in rule_flags]))

    override_dept = rule_override_dept if rule_override_level else None
    dept, capacity_flag, next_best = _match_department(
        triage_level, llm_data.get("suggested_department_id"), override_dept
    )

    return TriageReport(
        patient_id=patient_id,
        patient_name=req.patient_name,
        age=req.age,
        gender=req.gender,
        triage_level=triage_level,
        triage_score=max(1, min(10, int(llm_data.get("triage_score", 5)))),
        matched_department=dept["name"],
        matched_department_id=dept["department_id"],
        available_slots=dept["available_slots"],
        capacity_flag=capacity_flag,
        next_best_department=next_best["name"] if next_best else None,
        next_best_department_id=next_best["department_id"] if next_best else None,
        estimated_wait_minutes=_estimate_wait(dept, triage_level),
        chief_complaint=llm_data.get("chief_complaint", "Not determined"),
        clinical_summary=llm_data.get("clinical_summary", ""),
        recommended_actions=llm_data.get("recommended_actions", []),
        red_flags=all_flags,
        created_at=now,
        updated_at=now,
        llm_model_used=llm_model_used,
        raw_symptoms=req.symptoms,
        vitals=req.vitals,
    )


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC SERVICE FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

async def submit_triage(req: TriageRequest) -> TriageReport:
    patient_id = _generate_patient_id()
    now = datetime.now(timezone.utc)
    logger.info("TRIAGE_REQUEST | patient_id=%s | age=%d | ts=%s", patient_id, req.age, now.isoformat())

    rule_flags, rule_override_level, rule_override_dept = _detect_red_flags(req.symptoms, req.age, req.vitals)

    try:
        llm_data = await _call_gemini(_build_triage_prompt(req))
        llm_model_used = settings.GEMINI_MODEL
    except Exception as exc:
        logger.warning("LLM unavailable — using rule-based fallback | error=%s", exc)
        llm_data = _rule_based_fallback(req)
        llm_model_used = "rule-based-fallback"

    report = _build_report(patient_id, now, req, llm_data, llm_model_used,
                           rule_flags, rule_override_level, rule_override_dept)
    _reports[patient_id] = report
    _decrement_slots(report.matched_department_id)
    logger.info("TRIAGE_COMPLETE | patient_id=%s | level=%s | dept=%s | ts=%s",
                patient_id, report.triage_level.value, report.matched_department_id,
                datetime.now(timezone.utc).isoformat())
    return report


async def stream_triage(req: TriageRequest) -> AsyncGenerator[str, None]:
    """
    Async generator yielding SSE events for POST /triage/stream.

    Events emitted in order:
      event: start       data: {patient_id}
      event: red_flags   data: {flags, override_level}   (only if flags detected)
      event: reasoning   data: {text}                    (one per LLM token chunk)
      event: complete    data: <full TriageReport JSON>
    """
    patient_id = _generate_patient_id()
    now = datetime.now(timezone.utc)
    logger.info("TRIAGE_STREAM | patient_id=%s | age=%d | ts=%s", patient_id, req.age, now.isoformat())

    yield f"event: start\ndata: {json.dumps({'patient_id': patient_id})}\n\n"

    # Red-flag detection fires immediately — before any LLM latency
    rule_flags, rule_override_level, rule_override_dept = _detect_red_flags(req.symptoms, req.age, req.vitals)
    if rule_flags:
        yield (
            f"event: red_flags\ndata: {json.dumps({'flags': rule_flags, 'override_level': rule_override_level.value if rule_override_level else None})}\n\n"
        )

    # Stream LLM tokens
    full_text = ""
    llm_model_used = settings.GEMINI_MODEL
    try:
        async for chunk in _call_gemini_stream(_build_triage_prompt(req)):
            full_text += chunk
            yield f"event: reasoning\ndata: {json.dumps({'text': chunk})}\n\n"
        llm_data = json.loads(_strip_markdown_fences(full_text))
    except Exception as exc:
        logger.warning("LLM stream failed — using fallback | error=%s", exc)
        llm_data = _rule_based_fallback(req)
        llm_model_used = "rule-based-fallback"

    report = _build_report(patient_id, now, req, llm_data, llm_model_used,
                           rule_flags, rule_override_level, rule_override_dept)
    _reports[patient_id] = report
    _decrement_slots(report.matched_department_id)
    logger.info("TRIAGE_STREAM_COMPLETE | patient_id=%s | level=%s | dept=%s | ts=%s",
                patient_id, report.triage_level.value, report.matched_department_id,
                datetime.now(timezone.utc).isoformat())

    yield f"event: complete\ndata: {json.dumps(report.model_dump(mode='json'), default=str)}\n\n"


def get_report(patient_id: str) -> TriageReport:
    report = _reports.get(patient_id)
    if not report:
        raise HTTPException(
            status_code=404,
            detail=f"No triage report found for patient_id '{patient_id}'.",
        )
    return report


def escalate_patient(req: EscalateRequest) -> EscalateResponse:
    report = _reports.get(req.patient_id)
    if not report:
        raise HTTPException(
            status_code=404,
            detail=f"No triage report found for patient_id '{req.patient_id}'.",
        )

    previous_level = report.triage_level
    previous_dept_id = report.matched_department_id
    now = datetime.now(timezone.utc)
    emergency_dept = DEPARTMENT_MAP["DEPT-001"]

    # Release slot from the old department; claim one in Emergency
    if previous_dept_id != "DEPT-001":
        _increment_slots(previous_dept_id)
        _decrement_slots("DEPT-001")

    report.triage_level           = TriageLevel.EMERGENCY
    report.triage_score           = 1
    report.matched_department     = emergency_dept["name"]
    report.matched_department_id  = "DEPT-001"
    report.available_slots        = emergency_dept["available_slots"]
    report.capacity_flag          = emergency_dept["available_slots"] == 0
    report.estimated_wait_minutes = 0
    report.escalated              = True
    report.escalation_reason      = req.reason
    report.escalated_at           = now
    report.updated_at             = now

    escalation_flag = f"MANUALLY_ESCALATED: {req.reason}"
    if escalation_flag not in report.red_flags:
        report.red_flags.insert(0, escalation_flag)

    logger.warning(
        "ESCALATION | patient_id=%s | prev_level=%s | reason=%s | ts=%s",
        req.patient_id, previous_level.value, req.reason, now.isoformat(),
    )

    already_emergency = previous_level == TriageLevel.EMERGENCY
    message = (
        f"Patient '{report.patient_name}' was already at EMERGENCY level. Record updated."
        if already_emergency else
        f"Patient '{report.patient_name}' escalated from {previous_level.value} to EMERGENCY. Immediate attention required."
    )

    return EscalateResponse(
        patient_id=req.patient_id,
        previous_triage_level=previous_level,
        matched_department=emergency_dept["name"],
        matched_department_id="DEPT-001",
        available_slots=emergency_dept["available_slots"],
        escalated_at=now,
        message=message,
    )


def get_escalation_status(patient_id: str) -> EscalationStatus:
    report = _reports.get(patient_id)
    if not report:
        raise HTTPException(
            status_code=404,
            detail=f"No triage report found for patient_id '{patient_id}'.",
        )
    return EscalationStatus(
        patient_id=patient_id,
        escalated=report.escalated,
        triage_level=report.triage_level,
        escalation_reason=report.escalation_reason,
        escalated_at=report.escalated_at,
    )