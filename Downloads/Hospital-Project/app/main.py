import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import triage
from app.routers.health import router as health_router
from app.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting AI-Powered Patient Triage & Care Routing Agent...")
    logger.info(f"LLM model: {settings.GEMINI_MODEL}")
    yield
    logger.info("Shutting down Patient Triage service...")


app = FastAPI(
    title="AI-Powered Patient Triage & Care Routing Agent",
    description=(
        "LLM-backed triage assessment with rule-based red-flag detection, "
        "department routing, and capacity management. Powered by Google Gemini."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, tags=["Health"])
app.include_router(triage.router, tags=["Triage"])