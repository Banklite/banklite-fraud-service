from uuid import UUID
from datetime import datetime
from typing import Optional, Literal, List
from pydantic import BaseModel, Field

class ReglaFraudeCreate(BaseModel):
    nombre: str = Field(..., min_length=3, max_length=150)
    tipo: str = Field(default="monto_maximo", max_length=50)
    umbral: float = Field(..., ge=0)
    activa: bool = True

class ReglaFraudeOut(BaseModel):
    id_regla: UUID
    nombre: str
    tipo: str
    umbral: float
    activa: bool

    class Config:
        from_attributes = True

class EvaluacionCreate(BaseModel):
    id_transaccion: UUID
    monto_transaccion: float = Field(..., gt=0)

class AlertaOut(BaseModel):
    id_alerta: UUID
    id_evaluacion: UUID
    estado: str
    prioridad: str
    fecha_generacion: datetime

    class Config:
        from_attributes = True

class EvaluacionOut(BaseModel):
    id_evaluacion: UUID
    id_transaccion: UUID
    id_regla: UUID
    score_riesgo: float
    resultado: str
    fecha_evaluacion: datetime
    alertas: List[AlertaOut] = []

    class Config:
        from_attributes = True
