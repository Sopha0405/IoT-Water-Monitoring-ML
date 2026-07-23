from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = Field(..., alias="DATABASE_URL")
    jwt_secret_key: str = Field(..., alias="JWT_SECRET_KEY")

    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    admin_role_id: int = 3
    initial_admin_name: str = Field("Admin", alias="INITIAL_ADMIN_NAME")
    initial_admin_email: str = Field("admin@example.com", alias="INITIAL_ADMIN_EMAIL")
    initial_admin_password: str = Field("change_me_admin", alias="INITIAL_ADMIN_PASSWORD")
    initial_admin_floor: str = Field("PB", alias="INITIAL_ADMIN_FLOOR")
    cors_origins: str = Field("http://localhost:3000,http://127.0.0.1:3000", alias="CORS_ORIGINS")

    influx_url: str = Field("http://influxdb:8086", alias="INFLUX_URL")
    influx_token: str = Field("", alias="INFLUX_TOKEN")
    influx_org: str = Field("water-monitoring", alias="INFLUX_ORG")
    influx_bucket: str = Field("water-data", alias="INFLUX_BUCKET")
    influx_measurement: str = Field("water_telemetry", alias="INFLUX_MEASUREMENT")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
