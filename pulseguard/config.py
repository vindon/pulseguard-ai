from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Anthropic
    anthropic_api_key: str = ""

    # LangSmith
    langchain_api_key: str = ""
    langchain_project: str = "pulseguard-ai"
    # Off by default: tracing sends node/tool inputs and outputs (already
    # PII-redacted, but still real customer-issue content) to a third-party
    # service. Require an explicit opt-in rather than silently starting to
    # export data the moment someone sets an unrelated LANGCHAIN_API_KEY.
    langchain_tracing_v2: bool = False

    # X / Twitter
    x_bearer_token: str = ""
    x_api_tier: str = "basic"  # "basic" | "pro"
    x_monthly_cap: int = 15000
    x_poll_interval_seconds: int = 300

    # Reddit
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    reddit_user_agent: str = "PulseGuard/1.0"

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
    # Comma-separated origins allowed to call the API from a browser (CORS).
    # Empty means no browser origin is trusted — the intended path is always
    # the frontend's own server-side proxy, which isn't subject to CORS at all.
    allowed_origins: str = ""
    # Comma-separated IPs of the reverse-proxy hop(s) directly in front of this
    # service (e.g. Render's ingress). CF-Connecting-IP / X-Forwarded-For are
    # only trusted for rate-limiting when request.client.host matches one of
    # these — otherwise any caller could spoof those headers to bypass the
    # limiter entirely. Empty means nothing is trusted; the limiter falls back
    # to request.client.host, which is safe but keys on the shared proxy IP
    # behind a PaaS. Set this once the real ingress IP(s) are confirmed.
    trusted_proxy_ips: str = ""

    # Carriers
    monitored_carriers: str = "verizon,tmobile,att"

    # Misc
    environment: str = "development"  # "development" | "production"
    audit_log_path: str = "logs/audit.jsonl"
    enable_adapter_polling: bool = True

    @property
    def carrier_list(self) -> list[str]:
        return [c.strip() for c in self.monitored_carriers.split(",") if c.strip()]

    @property
    def allowed_origins_list(self) -> list[str]:
        configured = [o.strip() for o in self.allowed_origins.split(",") if o.strip()]
        if configured:
            return configured
        if self.environment != "production":
            return ["http://localhost:3000", "http://localhost:3100"]
        return []

    @property
    def trusted_proxy_ips_set(self) -> set[str]:
        return {ip.strip() for ip in self.trusted_proxy_ips.split(",") if ip.strip()}


settings = Settings()
