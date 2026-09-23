from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "fraud-service"
    api_port: int = 8006

    database_url: str = (
        "postgresql+psycopg2://banklite:banklite@fraud-db:5432/fraud_db"
    )

    rabbitmq_url: str = "amqp://banklite:banklite@rabbitmq:5672/"
    events_exchange: str = "banklite.events"
    events_queue: str = "fraud.events"
    enable_events: bool = True
    enable_consumer: bool = True

settings = Settings()
