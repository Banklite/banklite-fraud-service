"""Pruebas de INTEGRACION de fraud-service: endpoint + motor de reglas + base de datos.

/fraud/check-transfer es la llamada sincrona que hace transfer-service antes de mover
dinero. La base es SQLite en memoria con las reglas por defecto del servicio; RabbitMQ
y el proveedor de geolocalizacion se reemplazan con mocks.
"""
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from app.geoip import GeoIPError
from app.models import AlertaFraude, EvaluacionFraude, ReglaFraude
from app.rules import REGLAS_POR_DEFECTO


@pytest.fixture(autouse=True)
def reglas_y_bus(sesiones):
    """Siembra las mismas reglas que el servicio crea al arrancar y simula el bus de eventos."""
    with sesiones() as db:
        for nombre, tipo, umbral in REGLAS_POR_DEFECTO:
            db.add(ReglaFraude(nombre=nombre, tipo=tipo, umbral=umbral, activa=True))
        db.commit()
    with patch("app.routers.fraud.publish_event", return_value=True) as publicar:
        yield publicar


def _revisar(client, monto, cuenta=None):
    return client.post("/fraud/check-transfer", json={
        "id_transferencia": str(uuid.uuid4()), "id_cuenta_origen": str(cuenta or uuid.uuid4()), "monto": monto,
    })


def test_transferencia_normal_se_aprueba_sin_alerta(client, sesiones, reglas_y_bus):
    r = _revisar(client, 150_000)

    assert r.status_code == 200
    assert r.json()["resultado"] == "aprobada" and r.json()["score_riesgo"] == 5.0 and r.json()["motivo"] is None
    with sesiones() as db:
        assert db.query(EvaluacionFraude).count() == 1 and db.query(AlertaFraude).count() == 0
    reglas_y_bus.assert_not_called()


def test_monto_alto_pasa_pero_queda_en_revision_con_alerta_media(client, sesiones, reglas_y_bus):
    r = _revisar(client, 3_000_000)

    assert r.json()["resultado"] == "revision_manual" and "Monto alto" in r.json()["motivo"]
    with sesiones() as db:
        assert db.query(AlertaFraude).one().prioridad == "media"
    evento, datos = reglas_y_bus.call_args.args
    assert evento == "fraud.alert" and datos["resultado"] == "revision_manual"


def test_monto_sobre_el_maximo_se_bloquea_con_alerta_alta(client, sesiones, reglas_y_bus):
    cuenta = uuid.uuid4()
    r = _revisar(client, 6_000_000, cuenta)

    assert r.json()["resultado"] == "bloqueada" and r.json()["score_riesgo"] == 95.0
    assert "supera el maximo" in r.json()["motivo"]
    with sesiones() as db:
        assert db.query(AlertaFraude).one().prioridad == "alta"
    datos = reglas_y_bus.call_args.args[1]
    assert datos["prioridad"] == "alta"
    # El evento lleva la cuenta y el monto: con eso notification y compliance ubican al titular
    assert datos["id_cuenta"] == str(cuenta) and datos["monto"] == 6_000_000


def test_la_sexta_transferencia_en_diez_minutos_se_bloquea_por_rafaga(client):
    cuenta = uuid.uuid4()

    resultados = [_revisar(client, 10_000, cuenta).json()["resultado"] for _ in range(6)]

    assert resultados == ["aprobada"] * 5 + ["bloqueada"]


def test_la_rafaga_es_por_cuenta_y_no_afecta_a_otras(client):
    cuenta = uuid.uuid4()
    for _ in range(5):
        _revisar(client, 10_000, cuenta)

    assert _revisar(client, 10_000).json()["resultado"] == "aprobada"


def test_el_acumulado_diario_bloquea_aunque_cada_monto_sea_valido(client):
    cuenta = uuid.uuid4()
    for _ in range(2):
        assert _revisar(client, 4_500_000, cuenta).json()["resultado"] == "revision_manual"

    r = _revisar(client, 1_500_000, cuenta)  # 9.000.000 + 1.500.000 supera los 10.000.000 diarios

    assert r.json()["resultado"] == "bloqueada" and "acumulado diario" in r.json()["motivo"]


def test_lo_evaluado_hace_mas_de_un_dia_no_cuenta_para_el_acumulado(client, sesiones):
    cuenta = uuid.uuid4()
    with sesiones() as db:
        regla = db.query(ReglaFraude).first()
        db.add(EvaluacionFraude(
            id_transaccion=uuid.uuid4(), id_regla=regla.id_regla, score_riesgo=5, resultado="aprobada",
            id_cuenta_origen=cuenta, monto=9_900_000, fecha_evaluacion=datetime.utcnow() - timedelta(hours=25),
        ))
        db.commit()

    assert _revisar(client, 1_000_000, cuenta).json()["resultado"] == "aprobada"


def test_una_regla_desactivada_deja_de_aplicarse(client, sesiones):
    with sesiones() as db:
        db.query(ReglaFraude).filter(ReglaFraude.tipo.in_(["monto_maximo", "monto_alto"])).update(
            {"activa": False}, synchronize_session=False)
        db.commit()

    assert _revisar(client, 6_000_000).json()["resultado"] == "aprobada"


def test_alertas_se_listan_con_motivo_y_se_resuelven(client):
    _revisar(client, 6_000_000)
    alerta = client.get("/fraud/alerts").json()[0]
    assert alerta["estado"] == "abierta" and alerta["monto"] == 6_000_000 and "maximo" in alerta["motivo"]
    assert client.get("/stats").json() == {"total_alertas": 1, "alertas_pendientes": 1}

    resuelta = client.patch(f"/fraud/alerts/{alerta['id_alerta']}/resolve")

    assert resuelta.json()["estado"] == "resuelta"
    assert client.get("/stats").json() == {"total_alertas": 1, "alertas_pendientes": 0}
    assert client.patch(f"/fraud/alerts/{uuid.uuid4()}/resolve").status_code == 404


def test_reglas_se_crean_y_se_listan(client):
    r = client.post("/fraud/rules", json={"nombre": "Pais de alto riesgo", "tipo": "pais", "umbral": 1})

    assert r.status_code == 201 and r.json()["activa"] is True
    assert len(client.get("/fraud/rules").json()) == len(REGLAS_POR_DEFECTO) + 1
    assert client.post("/fraud/rules", json={"nombre": "Umbral negativo", "umbral": -1}).status_code == 422


@pytest.mark.parametrize("monto, resultado, alertas", [
    (1_000_000, "aprobada", 0), (4_000_000, "revision_manual", 1), (5_500_000, "sospechosa", 1),
])
def test_evaluacion_manual_por_monto(client, monto, resultado, alertas):
    r = client.post("/fraud/evaluate", json={"id_transaccion": str(uuid.uuid4()), "monto_transaccion": monto})

    assert r.status_code == 201 and r.json()["resultado"] == resultado
    assert len(client.get("/fraud/alerts").json()) == alertas
    assert len(client.get("/fraud/evaluations").json()) == 1


def test_geolocalizacion_de_ip_usa_el_proveedor_y_traduce_errores(client):
    with patch("app.routers.fraud.localizar_ip", return_value={"ip": "8.8.8.8", "pais": "Estados Unidos"}) as mock_geo:
        assert client.get("/fraud/geoip/8.8.8.8").json()["pais"] == "Estados Unidos"
        assert client.post("/fraud/geoip", json={"ip": "8.8.8.8"}).status_code == 200
    assert mock_geo.call_count == 2

    with patch("app.routers.fraud.localizar_ip", side_effect=GeoIPError("IP no valida")):
        assert client.get("/fraud/geoip/999.1.1.1").status_code == 400
        assert client.post("/fraud/geoip", json={"ip": "999.1.1.1"}).status_code == 400
