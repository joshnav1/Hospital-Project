"""
Unit tests for the Patient Triage & Care Routing Agent.
Run with: pytest test_gemini.py -v
"""
import pytest
from unittest.mock import AsyncMock, patch

from app.services.triage_service import (
    _detect_red_flags,
    _match_department,
    _rule_based_fallback,
    TriageLevel,
    TriageRequest,
    VitalSigns,
    DEPARTMENT_MAP,
)


# ── Red-flag detection ────────────────────────────────────────────────────────

def test_cardiac_event_risk_detected():
    flags, level, dept = _detect_red_flags(
        ["severe chest pain", "shortness of breath"], age=54, vitals=None
    )
    assert "CARDIAC_EVENT_RISK" in flags
    assert level == TriageLevel.EMERGENCY
    assert dept == "DEPT-002"  # Cardiology


def test_stroke_risk_detected():
    flags, level, dept = _detect_red_flags(
        ["face drooping", "arm weakness", "speech difficulty"], age=65, vitals=None
    )
    assert "STROKE_RISK" in flags
    assert level == TriageLevel.EMERGENCY


def test_stroke_risk_always_overrides_to_emergency():
    # Even if only stroke flags exist (no cardiac), level must be EMERGENCY
    flags, level, _ = _detect_red_flags(
        ["face drooping", "arm weakness", "speech difficulty"], age=40, vitals=None
    )
    assert level == TriageLevel.EMERGENCY


def test_pediatric_high_fever_from_vitals():
    vitals = VitalSigns(temperature_celsius=39.5)
    flags, level, dept = _detect_red_flags(["body aches"], age=8, vitals=vitals)
    assert "PEDIATRIC_HIGH_FEVER" in flags
    assert level == TriageLevel.URGENT
    assert dept == "DEPT-004"


def test_pediatric_high_fever_from_symptom_text():
    flags, level, dept = _detect_red_flags(["fever", "cough"], age=6, vitals=None)
    assert "PEDIATRIC_HIGH_FEVER" in flags
    assert level == TriageLevel.URGENT
    assert dept == "DEPT-004"


def test_no_flags_for_adult_fever():
    flags, level, dept = _detect_red_flags(["fever", "cough"], age=30, vitals=None)
    assert "PEDIATRIC_HIGH_FEVER" not in flags
    assert level is None


def test_no_flags_for_benign_symptoms():
    flags, level, dept = _detect_red_flags(["runny nose", "mild headache"], age=25, vitals=None)
    assert flags == []
    assert level is None


def test_cardiac_risk_requires_both_symptoms():
    # Only chest pain — not enough for CARDIAC_EVENT_RISK
    flags, level, _ = _detect_red_flags(["chest pain"], age=50, vitals=None)
    assert "CARDIAC_EVENT_RISK" not in flags

    # Only shortness of breath — not enough
    flags, level, _ = _detect_red_flags(["shortness of breath"], age=50, vitals=None)
    assert "CARDIAC_EVENT_RISK" not in flags


# ── Department matching ───────────────────────────────────────────────────────

def test_emergency_routes_to_emergency_dept():
    dept, capacity_flag, next_best = _match_department(TriageLevel.EMERGENCY)
    assert dept["department_id"] in ("DEPT-001", "DEPT-002", "DEPT-004")
    # All emergency-capable depts have slots in seed data except DEPT-005 (no emergency)


def test_capacity_flag_set_when_dept_full():
    # DEPT-005 (Mental Health) has 0 slots — force it as override
    dept, capacity_flag, next_best = _match_department(
        TriageLevel.URGENT, override_dept_id="DEPT-005"
    )
    assert dept["department_id"] == "DEPT-005"
    assert capacity_flag is True
    assert next_best is not None  # Should find an alternative


def test_standard_routes_to_general_practice():
    dept, capacity_flag, next_best = _match_department(
        TriageLevel.STANDARD, suggested_dept_id="DEPT-003"
    )
    assert dept["department_id"] == "DEPT-003"
    assert capacity_flag is False  # DEPT-003 has 5 slots


def test_pediatric_override_routes_to_pediatrics():
    dept, capacity_flag, next_best = _match_department(
        TriageLevel.URGENT, override_dept_id="DEPT-004"
    )
    assert dept["department_id"] == "DEPT-004"


# ── Rule-based fallback ───────────────────────────────────────────────────────

def test_rule_based_chest_pain_is_emergency():
    req = TriageRequest(
        patient_name="Test Patient",
        age=50,
        gender="male",
        symptoms=["chest pain", "shortness of breath"],
    )
    result = _rule_based_fallback(req)
    assert result["triage_level"] == "EMERGENCY"


def test_rule_based_pediatric_defaults_to_pediatrics():
    req = TriageRequest(
        patient_name="Child Patient",
        age=5,
        gender="female",
        symptoms=["fever", "cough"],
    )
    result = _rule_based_fallback(req)
    assert result["triage_level"] == "URGENT"
    assert result["suggested_department_id"] == "DEPT-004"


def test_rule_based_minor_symptoms_standard():
    req = TriageRequest(
        patient_name="Mild Patient",
        age=30,
        gender="other",
        symptoms=["runny nose", "mild headache"],
    )
    result = _rule_based_fallback(req)
    assert result["triage_level"] == "STANDARD"


# ── Input validation ──────────────────────────────────────────────────────────

def test_triage_request_requires_symptoms():
    with pytest.raises(Exception):
        TriageRequest(patient_name="Test", age=25, gender="male", symptoms=[])


def test_triage_request_rejects_invalid_gender():
    with pytest.raises(Exception):
        TriageRequest(patient_name="Test", age=25, gender="unknown", symptoms=["headache"])


def test_triage_request_rejects_extreme_age():
    with pytest.raises(Exception):
        TriageRequest(patient_name="Test", age=200, gender="male", symptoms=["headache"])