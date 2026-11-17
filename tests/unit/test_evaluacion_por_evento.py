"""Pruebas UNITARIAS de la evaluacion de riesgo por monto (consumidor de eventos).

La base de datos y RabbitMQ se reemplazan con mocks (unittest.mock): solo se prueba
la regla "score y prioridad segun cuanto supera el monto al umbral".
"""
import uuid
from unittest.mock import MagicMock, patch

import pytest

from app import consumer
from app.models import AlertaFraude, EvaluacionFraude


def _evaluar(monto: float, umbral: float = 1_000_000):
    """Ejecuta _evaluar_monto con una sesion falsa cuya regla activa tiene el umbral dado."""
    sesion = MagicMock()
    regla = MagicMock(umbral=umbral, id_regla=uuid.uuid4())
    sesion.query.return_value.filter.return_value.first.return_value = regla
    with (
        patch("app.consumer.SessionLocal", return_value=sesion),
        patch("app.consumer.publish_event", return_value=True) as publicar,
    ):
        consumer._evaluar_monto(uuid.uuid4(), monto, uuid.uuid4())
    guardados = [llamada.args[0] for llamada in sesion.add.call_args_list]
    return guardados, publicar, sesion


@pytest.mark.parametrize("monto, score, resultado", [
    (500_000, 10.0, "aprobada"),            # por debajo del 70 % del umbral
    (700_000, 10.0, "aprobada"),            # exactamente el 70 %: todavia pasa
    (700_001, 60.0, "revision_manual"),     # entre el 70 % y el umbral
    (1_000_000, 60.0, "revision_manual"),   # igual al umbral: no lo supera
    (1_000_001, 90.0, "sospechosa"),        # supera el umbral
])
def test_score_y_resultado_segun_el_monto(monto, score, resultado):
    guardados, _, _ = _evaluar(monto)

    evaluacion = next(g for g in guardados if isinstance(g, EvaluacionFraude))
    assert (float(evaluacion.score_riesgo), evaluacion.resultado) == (score, resultado)


def test_monto_normal_no_genera_alerta_ni_evento():
    guardados, publicar, _ = _evaluar(100_000)

    assert not any(isinstance(g, AlertaFraude) for g in guardados)
    publicar.assert_not_called()


def test_monto_sospechoso_genera_alerta_alta_y_publica_fraud_alert():
    guardados, publicar, _ = _evaluar(5_000_000)

    alerta = next(g for g in guardados if isinstance(g, AlertaFraude))
    assert alerta.prioridad == "alta" and alerta.estado == "abierta"
    evento, datos = publicar.call_args.args
    assert evento == "fraud.alert"
    assert datos["prioridad"] == "alta" and datos["resultado"] == "sospechosa" and datos["monto"] == 5_000_000


def test_la_sesion_siempre_se_cierra_aunque_falle_el_guardado():
    sesion = MagicMock()
    sesion.query.return_value.filter.return_value.first.return_value = MagicMock(umbral=1000, id_regla=uuid.uuid4())
    sesion.commit.side_effect = RuntimeError("base de datos caida")
    with patch("app.consumer.SessionLocal", return_value=sesion), patch("app.consumer.publish_event"):
        with pytest.raises(RuntimeError):
            consumer._evaluar_monto(uuid.uuid4(), 50.0)
    sesion.close.assert_called_once()
