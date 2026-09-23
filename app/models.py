import uuid
from datetime import datetime
from sqlalchemy import Column, String, Numeric, Boolean, DateTime, ForeignKey, CheckConstraint, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from .database import Base

class ReglaFraude(Base):
    __tablename__ = "regla_fraude"

    id_regla = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nombre = Column(String(150), nullable=False)
    tipo = Column(String(50), nullable=False)
    umbral = Column(Numeric(12, 2), nullable=False)
    activa = Column(Boolean, default=True, nullable=False)

    __table_args__ = (
        CheckConstraint("umbral >= 0", name="chk_regla_umbral_positivo"),
    )

    evaluaciones = relationship("EvaluacionFraude", back_populates="regla", cascade="all, delete-orphan")


class EvaluacionFraude(Base):
    __tablename__ = "evaluacion_fraude"

    id_evaluacion = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    id_transaccion = Column(UUID(as_uuid=True), nullable=False)
    id_regla = Column(UUID(as_uuid=True), ForeignKey("regla_fraude.id_regla"), nullable=False)
    score_riesgo = Column(Numeric(5, 2), nullable=False)
    resultado = Column(String(50), nullable=False)
    fecha_evaluacion = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint("score_riesgo >= 0", name="chk_evaluacion_score_positivo"),
        Index("idx_evaluacion_transaccion", "id_transaccion"),
        Index("idx_evaluacion_regla", "id_regla"),
    )

    regla = relationship("ReglaFraude", back_populates="evaluaciones")
    alertas = relationship("AlertaFraude", back_populates="evaluacion", cascade="all, delete-orphan")


class AlertaFraude(Base):
    __tablename__ = "alerta_fraude"

    id_alerta = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    id_evaluacion = Column(UUID(as_uuid=True), ForeignKey("evaluacion_fraude.id_evaluacion"), nullable=False)
    estado = Column(String(30), nullable=False, default="abierta")
    prioridad = Column(String(20), nullable=False)
    fecha_generacion = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint("prioridad IN ('baja', 'media', 'alta')", name="chk_alerta_prioridad"),
        Index("idx_alerta_evaluacion", "id_evaluacion"),
    )

    evaluacion = relationship("EvaluacionFraude", back_populates="alertas")
