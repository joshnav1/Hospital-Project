from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class TriageLevel(str, Enum):
    EMERGENCY = "EMERGENCY"   # Immediate — life threatening
    URGENT    = "URGENT"      # Within 30 min
    STANDARD  = "STANDARD"    # Within 2 hours
    SELF_CARE = "SELF_CARE"   # Home care / scheduled


class VitalSigns(BaseModel):
    heart_rate_bpm:           Optional[int]   = Field(None, ge=0,    le=300,  description="Heart rate (bpm)")
    blood_pressure_systolic:  Optional[int]   = Field(None, ge=0,    le=300,  description="Systolic BP (mmHg)")
    blood_pressure_diastolic: Optional[int]   = Field(None, ge=0,    le=200,  description="Diastolic BP (mmHg)")
    temperature_celsius:      Optional[float] = Field(None, ge=30.0, le=45.0, description="Body temp (°C)")
    oxygen_saturation_pct:    Optional[float] = Field(None, ge=0.0,  le=100.0, description="SpO₂ (%)")
    respiratory_rate_bpm:     Optional[int]   = Field(None, ge=0,    le=100,  description="Respiratory rate (bpm)")


class TriageRequest(BaseModel):
    patient_name:           str             = Field(..., min_length=2, max_length=120)
    age:                    int             = Field(..., ge=0, le=130)
    gender:                 str             = Field(..., pattern="^(male|female|other)$")
    symptoms:               List[str]       = Field(..., min_length=1, description="List of reported symptoms")
    symptom_duration_hours: Optional[float] = Field(None, ge=0, description="Duration symptoms present (hours)")
    medical_history:        Optional[List[str]] = None
    current_medications:    Optional[List[str]] = None
    allergies:              Optional[List[str]] = None
    vitals:                 Optional[VitalSigns] = None
    notes:                  Optional[str]   = Field(None, max_length=1000)

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "patient_name": "Ravi Kumar",
                    "age": 54,
                    "gender": "male",
                    "symptoms": ["severe chest pain", "shortness of breath", "left arm numbness"],
                    "symptom_duration_hours": 1.5,
                    "medical_history": ["hypertension", "type 2 diabetes"],
                    "current_medications": ["metformin", "amlodipine"],
                    "vitals": {
                        "heart_rate_bpm": 108,
                        "blood_pressure_systolic": 158,
                        "blood_pressure_diastolic": 96,
                        "temperature_celsius": 37.2,
                        "oxygen_saturation_pct": 94.0,
                    },
                }
            ]
        }
    }


class TriageReport(BaseModel):
    patient_id:               str
    patient_name:             str
    age:                      int
    gender:                   str
    triage_level:             TriageLevel
    triage_score:             int = Field(..., ge=1, le=10, description="1=most critical, 10=least critical")
    matched_department:       str
    matched_department_id:    str
    available_slots:          int
    capacity_flag:            bool = Field(..., description="True when matched dept has 0 available slots")
    next_best_department:     Optional[str] = None
    next_best_department_id:  Optional[str] = None
    estimated_wait_minutes:   int
    chief_complaint:          str
    clinical_summary:         str
    recommended_actions:      List[str]
    red_flags:                List[str] = Field(default_factory=list)
    escalated:                bool = False
    escalation_reason:        Optional[str] = None
    escalated_at:             Optional[datetime] = None
    created_at:               datetime
    updated_at:               datetime
    llm_model_used:           str
    raw_symptoms:             List[str]
    vitals:                   Optional[VitalSigns] = None


class LLMTriageResult(BaseModel):
    """Validates the JSON object returned by the LLM triage prompt."""
    triage_level:            TriageLevel
    triage_score:            int        = Field(..., ge=1, le=10)
    suggested_department_id: str
    chief_complaint:         str
    clinical_summary:        str
    recommended_actions:     List[str]  = Field(default_factory=list)
    red_flags:               List[str]  = Field(default_factory=list)


class EscalateRequest(BaseModel):
    patient_id: str
    reason: str = "Manual escalation by clinical staff"


class EscalateResponse(BaseModel):
    patient_id:             str
    previous_triage_level:  TriageLevel
    new_triage_level:       TriageLevel = TriageLevel.EMERGENCY
    matched_department:     str
    matched_department_id:  str
    available_slots:        int
    estimated_wait_minutes: int = 0
    escalated_at:           datetime
    message:                str


class EscalationStatus(BaseModel):
    patient_id:        str
    escalated:         bool
    triage_level:      TriageLevel
    escalation_reason: Optional[str]
    escalated_at:      Optional[datetime]