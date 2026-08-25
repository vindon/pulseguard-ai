"""
get_remote_address (slowapi's default key_func) reads request.client.host,
which behind Render's ingress (itself behind Cloudflare) is the proxy's IP,
not the caller's — a real deployment gap found by testing the rate limiter
against production and seeing it silently never trigger. _real_client_ip
fixes that by preferring the headers the proxy chain actually sets.
"""

from unittest.mock import MagicMock

from pulseguard.gateway.limiter import _real_client_ip


def _request(headers: dict[str, str], client_host: str | None = "10.0.0.1") -> MagicMock:
    req = MagicMock()
    req.headers = headers
    req.client = MagicMock(host=client_host) if client_host else None
    return req


class TestRealClientIp:
    def test_prefers_cf_connecting_ip(self):
        req = _request({"cf-connecting-ip": "203.0.113.5", "x-forwarded-for": "10.1.1.1"})
        assert _real_client_ip(req) == "203.0.113.5"

    def test_falls_back_to_x_forwarded_for(self):
        req = _request({"x-forwarded-for": "203.0.113.9, 10.1.1.1"})
        assert _real_client_ip(req) == "203.0.113.9"

    def test_falls_back_to_client_host_when_no_proxy_headers(self):
        req = _request({}, client_host="127.0.0.1")
        assert _real_client_ip(req) == "127.0.0.1"

    def test_handles_missing_client(self):
        req = _request({}, client_host=None)
        assert _real_client_ip(req) == "unknown"
