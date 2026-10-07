import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from .config import settings
from .database import Base, engine
from .routers import fraud
from .consumer import start_consumer, stop_consumer
from .rules import REGLAS_POR_DEFECTO

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(settings.service_name)

def _migrar_y_sembrar() -> None:
    """Columnas nuevas (create_all no altera tablas existentes) y reglas por defecto."""
    from sqlalchemy import text
    from .database import SessionLocal
    from .models import ReglaFraude

    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE evaluacion_fraude ADD COLUMN IF NOT EXISTS id_cuenta_origen UUID;"))
        conn.execute(text("ALTER TABLE evaluacion_fraude ADD COLUMN IF NOT EXISTS monto NUMERIC(14,2);"))
        conn.execute(text("ALTER TABLE evaluacion_fraude ADD COLUMN IF NOT EXISTS motivo VARCHAR(255);"))
    with SessionLocal() as db:
        existentes = {r.tipo for r in db.query(ReglaFraude).all()}
        for nombre, tipo, umbral in REGLAS_POR_DEFECTO:
            if tipo not in existentes:
                db.add(ReglaFraude(nombre=nombre, tipo=tipo, umbral=umbral, activa=True))
        db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    _migrar_y_sembrar()
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
