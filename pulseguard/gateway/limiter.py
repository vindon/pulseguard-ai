from slowapi import Limiter
from starlette.requests import Request


def _real_client_ip(request: Request) -> str:
    """slowapi's default key_func (get_remote_address) reads request.client.host,
    which behind a reverse proxy — Render's ingress, itself behind Cloudflare —
    is the proxy's IP, not the caller's. Every request then keys to the same
    handful of proxy IPs (or rotates between them), so per-client rate
    limiting silently does nothing. Prefer the headers the proxy chain
    actually sets, falling back to request.client.host for local/direct runs
    where neither header is present.
    """
    cf_ip = request.headers.get("cf-connecting-ip")
    if cf_ip:
        return cf_ip
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# Shared instance: main.py registers it on app.state and wires the
# exception handler; routes.py applies @limiter.limit(...) to individual
# endpoints. Split out to avoid a routes.py <-> main.py import cycle.
limiter = Limiter(key_func=_real_client_ip)
