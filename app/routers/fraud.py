import logging
import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import ReglaFraude, EvaluacionFraude, AlertaFraude
from ..schemas import (
    ReglaFraudeCreate, ReglaFraudeOut,
    EvaluacionCreate, EvaluacionOut,
    AlertaOut
)
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
    regla = db.query(ReglaFraude).filter(ReglaFraude.activa == True).first()
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
