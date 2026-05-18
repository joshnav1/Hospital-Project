"""
Triage router — API endpoints only.
All business logic lives in app.services.triage_service.
"""

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from ..services.triage_service import (
    EscalateRequest,
    EscalateResponse,
    EscalationStatus,
    TriageReport,
    TriageRequest,
    escalate_patient,
    get_escalation_status,
    get_report,
    stream_triage,
    submit_triage,
)

router = APIRouter()


@router.post(
    "/triage",
    response_model=TriageReport,
    status_code=200,
    summary="Submit patient symptoms → LLM triage assessment + department routing",
)
async def triage_endpoint(req: TriageRequest) -> TriageReport:
    return await submit_triage(req)


@router.post(
    "/triage/stream",
    summary="Submit patient triage — streaming SSE response (red flags + LLM reasoning + complete report)",
)
async def triage_stream_endpoint(req: TriageRequest) -> StreamingResponse:
    return StreamingResponse(
        stream_triage(req),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get(
    "/report/{patient_id}",
    response_model=TriageReport,
    summary="Retrieve a triage report by patient ID",
)
def report_endpoint(patient_id: str) -> TriageReport:
    return get_report(patient_id)


@router.post(
    "/escalate",
    response_model=EscalateResponse,
    summary="Manually escalate a patient to EMERGENCY level",
)
def escalate_endpoint(req: EscalateRequest) -> EscalateResponse:
    return escalate_patient(req)


@router.get(
    "/escalate/{patient_id}",
    response_model=EscalationStatus,
    summary="Get escalation status for a patient",
)
def escalation_status_endpoint(patient_id: str) -> EscalationStatus:
    return get_escalation_status(patient_id)