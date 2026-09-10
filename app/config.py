from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    vapi_api_key: str = ""
    vapi_phone_number_id: str = ""
    vapi_assistant_id: str = ""
    public_base_url: str = "http://localhost:8000"
    webhook_secret: str = "change-me"
    transfer_number: str = ""

    app_host: str = "0.0.0.0"
    app_port: int = 8000
    database_url: str = "sqlite:///./data/outbound.db"
    dry_run: bool = True

    default_tz: str = "America/Denver"
    call_window_start: str = "09:00"
    call_window_end: str = "20:00"
    max_attempts: int = 3
    retry_hours: int = 4


settings = Settings()
