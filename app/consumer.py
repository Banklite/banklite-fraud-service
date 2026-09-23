import json
import logging
import threading
import time
import uuid
import pika
from .config import settings
from .database import SessionLocal
from .models import ReglaFraude, EvaluacionFraude, AlertaFraude
from .events import publish_event, EVENT_FRAUD_ALERT

logger = logging.getLogger(__name__)

EVENT_CARD_AUTHORIZED = "card.transaction.authorized"
EVENT_TRANSFER_COMPLETED = "transfer.completed"
_stop = threading.Event()

def _evaluar_monto(id_transaccion: uuid.UUID, monto: float):
    db = SessionLocal()
    try:
        regla = db.query(ReglaFraude).filter(ReglaFraude.activa == True).first()
        if not regla:
            regla = ReglaFraude(nombre="Regla Base Antifraude", tipo="monto_maximo", umbral=2500.00, activa=True)
            db.add(regla)
            db.commit()
            db.refresh(regla)

        umbral = float(regla.umbral)
        if monto > umbral:
            score = 90.0
            resultado = "sospechosa"
            prioridad = "alta"
        elif monto > (umbral * 0.7):
            score = 60.0
            resultado = "revision_manual"
            prioridad = "media"
        else:
            score = 10.0
            resultado = "aprobada"
            prioridad = "baja"

        evaluacion = EvaluacionFraude(
            id_transaccion=id_transaccion,
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
            db.refresh(alerta)

            publish_event(EVENT_FRAUD_ALERT, {
                "id_alerta": str(alerta.id_alerta),
                "id_evaluacion": str(evaluacion.id_evaluacion),
                "id_transaccion": str(id_transaccion),
                "prioridad": prioridad,
                "score_riesgo": score,
                "resultado": resultado
            })
            logger.warning("ALERTA DE FRAUDE GENERADA: transaccion %s (Score: %f, Prioridad: %s)", id_transaccion, score, prioridad)
        else:
            logger.info("Transaccion %s evaluada OK (Score: %f)", id_transaccion, score)
    finally:
        db.close()

def _worker():
    while not _stop.is_set():
        connection = None
        try:
            logger.info("Fraud consumer conectando a %s", settings.rabbitmq_url)
            connection = pika.BlockingConnection(pika.URLParameters(settings.rabbitmq_url))
            channel = connection.channel()
            channel.exchange_declare(exchange=settings.events_exchange, exchange_type="topic", durable=True)
            channel.queue_declare(queue=settings.events_queue, durable=True)

            channel.queue_bind(queue=settings.events_queue, exchange=settings.events_exchange, routing_key=EVENT_CARD_AUTHORIZED)
            channel.queue_bind(queue=settings.events_queue, exchange=settings.events_exchange, routing_key=EVENT_TRANSFER_COMPLETED)

            def callback(ch, method, properties, body):
                try:
                    payload = json.loads(body.decode("utf-8"))
                    if method.routing_key == EVENT_CARD_AUTHORIZED:
                        _evaluar_monto(uuid.UUID(payload["id_autorizacion"]), float(payload["monto"]))
                    elif method.routing_key == EVENT_TRANSFER_COMPLETED:
                        _evaluar_monto(uuid.UUID(payload["id_transferencia"]), float(payload["monto"]))
                    ch.basic_ack(delivery_tag=method.delivery_tag)
                except Exception as exc:
                    logger.exception("Error procesando mensaje %s: %s", method.routing_key, exc)
                    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

            channel.basic_qos(prefetch_count=10)
            channel.basic_consume(queue=settings.events_queue, on_message_callback=callback)
            logger.info("Fraud consumer listo y escuchando eventos")

            while not _stop.is_set() and channel.is_open:
                connection.process_data_events(time_limit=1)

        except Exception as exc:
            logger.warning("Fraud consumer error de conexion: %s. Reintentando en 5s...", exc)
            time.sleep(5)
        finally:
            if connection and connection.is_open:
                connection.close()

def start_consumer():
    if not settings.enable_consumer:
        return
    _stop.clear()
    t = threading.Thread(target=_worker, daemon=True, name="fraud-consumer")
    t.start()

def stop_consumer():
    _stop.set()
