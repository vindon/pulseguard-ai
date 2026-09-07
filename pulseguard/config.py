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

    # Enterprise integrations — each is independently optional; unset means
    # that channel is skipped, matching Slack/email above. These exist so a
    # telecom's existing CX stack can receive escalations directly, instead
    # of PulseGuard being a parallel, non-integrated alert tool.
    #
    # Generic outbound webhook — the universal "plug into anything" adapter
    # (Zapier, Make, n8n, ServiceNow inbound actions, or a custom internal
    # system). Payload is signed so receivers can verify authenticity.
    webhook_url: str = ""
    webhook_secret: str = ""
    # Microsoft Teams — incoming webhook *connectors* were retired by
    # Microsoft in 2026; this must be a channel Workflow's webhook URL
    # (Teams channel -> Workflows -> "Post to a channel when a webhook
    # request is received"), not a legacy connector URL.
    teams_webhook_url: str = ""
    # Zendesk — creates a ticket via the Ticketing API.
    zendesk_subdomain: str = ""
    zendesk_email: str = ""
    zendesk_api_token: str = ""
    # Freshdesk — creates a ticket via the same-shaped Tickets API.
    freshdesk_domain: str = ""
    freshdesk_api_key: str = ""

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

    # Spend guard — hard caps on LLM spend, checked before every call.
    # 0 means "no cap" (useful for local dev); set real values before any
    # pilot deployment. Pricing is per-million-tokens, "model:input,output"
    # pairs comma-separated, e.g. "claude-haiku-4-5:1.00,5.00" — set from
    # Anthropic's current published pricing at deploy time, not hardcoded
    # here, since pricing changes independently of this codebase.
    daily_budget_usd_cap: float = 0.0
    monthly_budget_usd_cap: float = 0.0
    model_pricing_per_million_tokens: str = ""

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

    @property
    def model_pricing_map(self) -> dict[str, tuple[float, float]]:
        """Parses MODEL_PRICING_PER_MILLION_TOKENS into {model: (input_$/M, output_$/M)}.

        The format is "model:input,output" pairs, comma-separated for
        multiple models. A naive split on "," alone is ambiguous, since the
        input/output rate pair inside one entry is itself comma-separated
        (e.g. "claude-haiku-4-5:1.00,5.00" has two commas' worth of meaning
        packed differently than a plain CSV list). So this walks the
        comma-split tokens instead: a token containing ":" starts a new
        model entry, and the token immediately after it is that model's
        output rate.
        """
        pricing: dict[str, tuple[float, float]] = {}
        tokens = [t.strip() for t in self.model_pricing_per_million_tokens.split(",") if t.strip()]
        i = 0
        while i < len(tokens):
            token = tokens[i]
            if ":" not in token or i + 1 >= len(tokens):
                i += 1
                continue
            model, input_rate = token.split(":", 1)
            output_rate = tokens[i + 1]
            pricing[model.strip()] = (float(input_rate), float(output_rate))
            i += 2
        return pricing


settings = Settings()
