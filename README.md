# Fraud Service — BankLite

Evaluacion de riesgo, scoring y reglas antifraude; marca transacciones sospechosas y genera alertas. Geolocalizacion por IP.

Parte del proyecto **BankLite** (banca digital con microservicios) de *Arquitectura y Modelamiento de Software*, Universidad Cooperativa de Colombia. Cada microservicio tiene su propio repositorio y su propia base de datos (`fraud_db`).

## Responsabilidad en la arquitectura

Evaluacion de riesgo, scoring y reglas antifraude; marca transacciones sospechosas y genera alertas. Geolocalizacion por IP. Se comunica con los demas servicios por **REST** (operaciones que necesitan respuesta inmediata) y por **eventos** en RabbitMQ (exchange `banklite.events`, tipo topic).

| Eventos publicados | Eventos consumidos |
|---|---|
| `fraud.alert` | `transfer.completed`, `card.transaction.authorized` |

## Tecnologias

FastAPI, SQLAlchemy, PostgreSQL, RabbitMQ (pika). Externo: servicio de GeoIP. Python 3.12, Docker.

## Despliegue

- URL publica: <https://banklite-fraud-service.onrender.com>
- Salud: <https://banklite-fraud-service.onrender.com/health>
- Documentacion interactiva (Swagger): <https://banklite-fraud-service.onrender.com/docs>

Desplegado en Render (plan gratuito: tarda hasta ~1 minuto en responder si estuvo inactivo). Las credenciales se configuran como variables de entorno en la plataforma, no en el codigo.

## Endpoints principales

| Metodo | Ruta | Descripcion |
|---|---|---|
| `POST` | `/rules` | Crea una regla antifraude |
| `GET` | `/rules` | Lista reglas |
| `POST` | `/evaluate` | Evalua una transaccion |
| `POST` | `/check-transfer` | Evaluacion previa de una transferencia (REST sincrono) |
| `GET` | `/evaluations` | Evaluaciones realizadas |
| `GET` | `/alerts` | Alertas generadas |
| `PATCH` | `/alerts/{id}/resolve` | Resuelve una alerta |
| `GET` | `/geoip/{ip}` | Geolocalizacion de una IP |
| `GET` | `/health` | Estado del servicio |
| `GET` | `/stats` | Contadores del servicio |

La lista completa esta en `/docs`.

## Variables de entorno

Copia `.env.example` a `.env` y completa los valores.

| Variable | Descripcion |
|---|---|
| `DATABASE_URL` | Conexion PostgreSQL |
| `RABBITMQ_URL` | URL del bus de eventos |
| `EVENTS_EXCHANGE` | Exchange de eventos |
| `EVENTS_QUEUE` | Cola propia |
| `ENABLE_EVENTS` | Publicar eventos |
| `ENABLE_CONSUMER` | Consumir eventos |

## Base de datos

Motor: PostgreSQL. Base: `fraud_db`.

- `db/schema.sql`: creacion de tablas, indices y restricciones.
- `db/seed.sql`: datos de ejemplo.

El servicio tambien crea las tablas solo al arrancar (`create_all`). Para restaurar a mano:

```bash
createdb fraud_db
psql -d fraud_db -f db/schema.sql
psql -d fraud_db -f db/seed.sql
```

Respaldo completo (para entregar o restaurar): `pg_dump -Fc fraud_db > fraud_db.dump` y `pg_restore -d fraud_db fraud_db.dump`.

## Instalacion y ejecucion

Con Docker:

```bash
docker build -t banklite-fraud-service .
docker run --env-file .env -p 8006:8006 -e PORT=8006 banklite-fraud-service
```

Sin Docker:

```bash
python -m venv .venv && source .venv/bin/activate   # en Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8006
```

Prueba: abre <http://localhost:8006/docs>.

## Repositorios del proyecto

`banklite-identity-service`, `banklite-account-service`, `banklite-ledger-service`, `banklite-transfer-service`, `banklite-card-service`, `banklite-fraud-service`, `banklite-notification-service`, `banklite-compliance-service`. Panel web: `services/web-panel` en el repositorio `banklite-microservicios`.
