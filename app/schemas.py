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

class TransferCheckIn(BaseModel):
    id_transferencia: UUID
    id_cuenta_origen: UUID
    id_cuenta_destino: Optional[UUID] = None
    monto: float = Field(..., gt=0)


class TransferCheckOut(BaseModel):
    resultado: Literal["aprobada", "revision_manual", "bloqueada"]
    score_riesgo: float
    motivo: Optional[str] = None
    id_evaluacion: UUID


class AlertaOut(BaseModel):
    id_alerta: UUID
    id_evaluacion: UUID
    estado: str
    prioridad: str
    fecha_generacion: datetime
    motivo: Optional[str] = None
    monto: Optional[float] = None

    class Config:
        from_attributes = True

class EvaluacionOut(BaseModel):
    id_evaluacion: UUID
    id_transaccion: UUID
    id_regla: UUID
    score_riesgo: float
    resultado: str
    fecha_evaluacion: datetime
    id_cuenta_origen: Optional[UUID] = None
    monto: Optional[float] = None
    motivo: Optional[str] = None
    alertas: List[AlertaOut] = []

    class Config:
        from_attributes = True
