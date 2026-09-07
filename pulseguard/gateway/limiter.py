from slowapi import Limiter
from starlette.requests import Request

from pulseguard.config import settings


def _real_client_ip(request: Request) -> str:
    """slowapi's default key_func (get_remote_address) reads request.client.host,
    which behind a reverse proxy — Render's ingress, itself behind Cloudflare —
    is the proxy's IP, not the caller's. Every request then keys to the same
    handful of proxy IPs (or rotates between them), so per-client rate
    limiting silently does nothing.

    CF-Connecting-IP / X-Forwarded-For are attacker-controlled on any request
    that doesn't actually transit the trusted proxy chain, so they are only
    trusted when the immediate TCP peer (request.client.host) is itself a
    configured trusted hop (settings.trusted_proxy_ips_set) — otherwise a
    caller could set either header to an arbitrary value per request and
    bypass the limiter entirely. With nothing configured, this falls back to
    request.client.host: safe (unspoofable), just imprecise behind a PaaS
    until the real ingress IP(s) are set.
    """
    direct_peer = request.client.host if request.client else None
    trusted = bool(direct_peer) and direct_peer in settings.trusted_proxy_ips_set

    if trusted:
        cf_ip = request.headers.get("cf-connecting-ip")
        if cf_ip:
            return cf_ip
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()

    return direct_peer or "unknown"


# Shared instance: main.py registers it on app.state and wires the
# exception handler; routes.py applies @limiter.limit(...) to individual
# endpoints. Split out to avoid a routes.py <-> main.py import cycle.
limiter = Limiter(key_func=_real_client_ip)
