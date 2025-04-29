from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    target_temp: float = 37.0
    sensor_gpio: int = 4
    heater_gpio: int = 17
    db_path: str = "/opt/incubator/data/telemetry.db"

settings = Settings()
