import json
import logging
import pika
from .config import settings

logger = logging.getLogger(__name__)

EVENT_FRAUD_ALERT = "fraud.alert"

def publish_event(routing_key: str, payload: dict) -> bool:
    if not settings.enable_events:
        logger.warning("Eventos deshabilitados: %s no publicado", routing_key)
        return False

    connection = None
    try:
        connection = pika.BlockingConnection(pika.URLParameters(settings.rabbitmq_url))
        channel = connection.channel()
        channel.exchange_declare(exchange=settings.events_exchange, exchange_type="topic", durable=True)
        channel.confirm_delivery()
        channel.basic_publish(
            exchange=settings.events_exchange,
            routing_key=routing_key,
            body=json.dumps(payload, default=str).encode("utf-8"),
            properties=pika.BasicProperties(
                delivery_mode=2,
                content_type="application/json",
                type=routing_key,
            ),
            mandatory=True,
        )
        logger.info("Evento publicado y confirmado: %s -> %s", routing_key, payload)
        return True
    except Exception as exc:
        logger.error("Error publicando %s en RabbitMQ: %s", routing_key, exc)
        return False
    finally:
        if connection is not None and connection.is_open:
            connection.close()
