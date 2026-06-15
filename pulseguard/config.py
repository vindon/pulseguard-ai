from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Anthropic
    anthropic_api_key: str = ""

    # LangSmith
    langchain_api_key: str = ""
    langchain_project: str = "pulseguard-ai"
    langchain_tracing_v2: bool = True

    # X / Twitter
    x_bearer_token: str = ""
    x_api_tier: str = "basic"  # "basic" | "pro"
    x_monthly_cap: int = 15000
    x_poll_interval_seconds: int = 300

    # Reddit
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    reddit_user_agent: str = "PulseGuard/1.0"

    # Trustpilot
    trustpilot_poll_interval_seconds: int = 86400
    trustpilot_request_delay_seconds: float = 1.0

    # Notifications
    slack_webhook_url: str = ""
    notification_email: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    sendgrid_api_key: str = ""

    # Redis
    redis_url: str = "redis://localhost:6379"

    # FastAPI
    pulseguard_api_key: str = ""

    # Carriers
    monitored_carriers: str = "verizon,tmobile,att"

    # Misc
    environment: str = "development"  # "development" | "production"
    audit_log_path: str = "logs/audit.jsonl"
    enable_adapter_polling: bool = True

    @property
    def carrier_list(self) -> list[str]:
        return [c.strip() for c in self.monitored_carriers.split(",") if c.strip()]


settings = Settings()
