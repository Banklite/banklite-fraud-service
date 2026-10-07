import logging
import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from datetime import datetime, timedelta
from sqlalchemy import func
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import ReglaFraude, EvaluacionFraude, AlertaFraude
from ..schemas import (
    ReglaFraudeCreate, ReglaFraudeOut,
    EvaluacionCreate, EvaluacionOut,
    AlertaOut,
    TransferCheckIn, TransferCheckOut,
)
from ..rules import VENTANA_RAFAGA_MIN
from ..events import publish_event, EVENT_FRAUD_ALERT

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/fraud", tags=["Fraud"])

@router.post("/rules", response_model=ReglaFraudeOut, status_code=status.HTTP_201_CREATED)
def crear_regla(payload: ReglaFraudeCreate, db: Session = Depends(get_db)):
    regla = ReglaFraude(
        nombre=payload.nombre,
        tipo=payload.tipo,
        umbral=payload.umbral,
        activa=payload.activa
    )
    db.add(regla)
    db.commit()
    db.refresh(regla)
    return regla

@router.get("/rules", response_model=List[ReglaFraudeOut])
def listar_reglas(db: Session = Depends(get_db)):
    return db.query(ReglaFraude).all()

@router.post("/evaluate", response_model=EvaluacionOut, status_code=status.HTTP_201_CREATED)
def evaluar_transaccion_manual(payload: EvaluacionCreate, db: Session = Depends(get_db)):
    regla = db.query(ReglaFraude).filter(ReglaFraude.activa == True, ReglaFraude.tipo == "monto_maximo").first()
    if not regla:
        regla = ReglaFraude(nombre="Regla Antifraude General", tipo="monto_maximo", umbral=2000.0, activa=True)
        db.add(regla)
        db.commit()
        db.refresh(regla)

    umbral = float(regla.umbral)
    if payload.monto_transaccion > umbral:
        score = 88.0
        resultado = "sospechosa"
        prioridad = "alta"
    elif payload.monto_transaccion > (umbral * 0.7):
        score = 55.0
        resultado = "revision_manual"
        prioridad = "media"
    else:
        score = 8.0
        resultado = "aprobada"
        prioridad = "baja"

    evaluacion = EvaluacionFraude(
        id_transaccion=payload.id_transaccion,
        id_regla=regla.id_regla,
        score_riesgo=score,
        resultado=resultado
    )
    db.add(evaluacion)
    db.commit()
    db.refresh(evaluacion)

    if resultado in ["sospechosa", "revision_manual"]:
        alerta = AlertaFraude(
            id_evaluacion=evaluacion.id_evaluacion,
            estado="abierta",
            prioridad=prioridad
        )
        db.add(alerta)
        db.commit()

        publish_event(EVENT_FRAUD_ALERT, {
            "id_alerta": str(alerta.id_alerta),
            "id_evaluacion": str(evaluacion.id_evaluacion),
            "id_transaccion": str(payload.id_transaccion),
            "prioridad": priority_val if (priority_val := prioridad) else "media",
            "score_riesgo": score,
            "resultado": resultado
        })

    return evaluacion

def _regla(db: Session, tipo: str):
    return db.query(ReglaFraude).filter(ReglaFraude.tipo == tipo, ReglaFraude.activa == True).first()  # noqa: E712


@router.post("/check-transfer", response_model=TransferCheckOut)
def evaluar_transferencia(payload: TransferCheckIn, db: Session = Depends(get_db)):
    """Evalua una transferencia ANTES de ejecutarla (llamada sincrona desde transfer-service).

    Reglas: monto maximo, monto alto, rafaga de transferencias y acumulado diario.
    Devuelve aprobada / revision_manual (pasa pero queda alerta) / bloqueada.
    """
    monto = float(payload.monto)
    ahora = datetime.utcnow()
    bloqueos: list[tuple[ReglaFraude, str]] = []
    revisiones: list[tuple[ReglaFraude, str]] = []

    r = _regla(db, "monto_maximo")
    if r and monto > float(r.umbral):
        bloqueos.append((r, f"El monto supera el maximo permitido por transferencia (${float(r.umbral):,.0f})"))

    r = _regla(db, "monto_alto")
    if r and monto > float(r.umbral):
        revisiones.append((r, f"Monto alto (mayor a ${float(r.umbral):,.0f}): queda en revision"))

    base = db.query(EvaluacionFraude).filter(
        EvaluacionFraude.id_cuenta_origen == payload.id_cuenta_origen,
        EvaluacionFraude.resultado != "bloqueada",
    )

    r = _regla(db, "rafaga")
    if r:
        desde = ahora - timedelta(minutes=VENTANA_RAFAGA_MIN)
        recientes = base.filter(EvaluacionFraude.fecha_evaluacion >= desde).count()
        if recientes + 1 > int(r.umbral):
            bloqueos.append((r, f"Demasiadas transferencias en {VENTANA_RAFAGA_MIN} minutos (limite {int(r.umbral)})"))

    r = _regla(db, "acumulado_diario")
    if r:
        desde = ahora - timedelta(hours=24)
        acumulado = (
            base.filter(EvaluacionFraude.fecha_evaluacion >= desde)
            .with_entities(func.coalesce(func.sum(EvaluacionFraude.monto), 0))
            .scalar()
        )
        if float(acumulado) + monto > float(r.umbral):
            bloqueos.append((r, f"Supera el acumulado diario permitido (${float(r.umbral):,.0f})"))

    if bloqueos:
        regla, motivo = bloqueos[0]
        resultado, score, prioridad = "bloqueada", 95.0, "alta"
        motivo = "; ".join(m for _, m in bloqueos)
    elif revisiones:
        regla, motivo = revisiones[0]
        resultado, score, prioridad = "revision_manual", 60.0, "media"
    else:
        regla = _regla(db, "monto_maximo") or db.query(ReglaFraude).first()
        resultado, score, prioridad, motivo = "aprobada", 5.0, "baja", None

    evaluacion = EvaluacionFraude(
        id_transaccion=payload.id_transferencia,
        id_regla=regla.id_regla,
        score_riesgo=score,
        resultado=resultado,
        id_cuenta_origen=payload.id_cuenta_origen,
        monto=monto,
        motivo=motivo,
    )
    db.add(evaluacion)
    db.commit()
    db.refresh(evaluacion)

    if resultado != "aprobada":
        alerta = AlertaFraude(id_evaluacion=evaluacion.id_evaluacion, estado="abierta", prioridad=prioridad)
        db.add(alerta)
        db.commit()
        publish_event(EVENT_FRAUD_ALERT, {
            "id_alerta": str(alerta.id_alerta),
            "id_evaluacion": str(evaluacion.id_evaluacion),
            "id_transaccion": str(payload.id_transferencia),
            "prioridad": prioridad,
            "score_riesgo": score,
            "resultado": resultado,
        })
    logger.info("Fraude %s: %s monto=%s cuenta=%s", resultado, motivo or "ok", monto, payload.id_cuenta_origen)
    return TransferCheckOut(resultado=resultado, score_riesgo=score, motivo=motivo, id_evaluacion=evaluacion.id_evaluacion)


@router.get("/evaluations", response_model=List[EvaluacionOut])
def listar_evaluaciones(db: Session = Depends(get_db)):
    return db.query(EvaluacionFraude).order_by(EvaluacionFraude.fecha_evaluacion.desc()).limit(50).all()

@router.get("/alerts", response_model=List[AlertaOut])
def listar_alertas(db: Session = Depends(get_db)):
    return db.query(AlertaFraude).order_by(AlertaFraude.fecha_generacion.desc()).all()

@router.patch("/alerts/{id_alerta}/resolve", response_model=AlertaOut)
def resolver_alerta(id_alerta: uuid.UUID, db: Session = Depends(get_db)):
    alerta = db.query(AlertaFraude).filter(AlertaFraude.id_alerta == id_alerta).first()
    if not alerta:
        raise HTTPException(status_code=404, detail="Alerta no encontrada")
    alerta.estado = "resuelta"
    db.commit()
    db.refresh(alerta)
    return alerta
