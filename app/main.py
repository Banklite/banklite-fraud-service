import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from .config import settings
from .database import Base, engine
from .routers import fraud
from .consumer import start_consumer, stop_consumer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(settings.service_name)

@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    start_consumer()
    logger.info("%s iniciado en puerto %d", settings.service_name, settings.api_port)
    yield
    stop_consumer()

app = FastAPI(
    title="BankLite - Fraud Detection Service",
    description="Microservicio de Detección de Fraude, Evaluación de Riesgo y Scoring Antifraude.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(fraud.router)

@app.get("/health", tags=["infra"])
def health():
    return {"status": "ok", "service": settings.service_name}

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Error no controlado en %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Error interno en Fraud Service"},
    )
