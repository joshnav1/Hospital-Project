from fastapi import APIRouter
from pydantic import BaseModel
from app.config import settings

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    model: str
    environment: str


@router.get("/health", response_model=HealthResponse, summary="Service health check")
async def health_check() -> HealthResponse:
    return HealthResponse(
        status="ok",
        model=settings.GEMINI_MODEL,
        environment=settings.APP_ENV,
    )