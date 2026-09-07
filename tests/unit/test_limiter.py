"""
get_remote_address (slowapi's default key_func) reads request.client.host,
which behind Render's ingress (itself behind Cloudflare) is the proxy's IP,
not the caller's — a real deployment gap found by testing the rate limiter
against production and seeing it silently never trigger. _real_client_ip
fixes that by preferring the headers the proxy chain actually sets — but
only when the direct TCP peer is a configured trusted proxy hop. Without
that gate, CF-Connecting-IP / X-Forwarded-For are attacker-controlled on
any request that doesn't actually transit the trusted chain, and trusting
them unconditionally lets any caller spoof a fresh IP per request to bypass
the limiter entirely (the bug this file's earlier version shipped).
"""

from unittest.mock import MagicMock

import pytest

from pulseguard.config import settings
from pulseguard.gateway.limiter import _real_client_ip


def _request(headers: dict[str, str], client_host: str | None = "10.0.0.1") -> MagicMock:
    req = MagicMock()
    req.headers = headers
    req.client = MagicMock(host=client_host) if client_host else None
    return req


@pytest.fixture(autouse=True)
def _clear_trusted_proxies(monkeypatch):
    # Default posture: nothing trusted, matching production until an operator
    # explicitly configures the real ingress IP(s).
    monkeypatch.setattr(settings, "trusted_proxy_ips", "")


class TestRealClientIp:
    def test_prefers_cf_connecting_ip_when_peer_is_trusted(self, monkeypatch):
        monkeypatch.setattr(settings, "trusted_proxy_ips", "10.0.0.1")
        req = _request(
            {"cf-connecting-ip": "203.0.113.5", "x-forwarded-for": "10.1.1.1"},
            client_host="10.0.0.1",
        )
        assert _real_client_ip(req) == "203.0.113.5"

    def test_falls_back_to_x_forwarded_for_when_peer_is_trusted(self, monkeypatch):
        monkeypatch.setattr(settings, "trusted_proxy_ips", "10.0.0.1")
        req = _request({"x-forwarded-for": "203.0.113.9, 10.1.1.1"}, client_host="10.0.0.1")
        assert _real_client_ip(req) == "203.0.113.9"

    def test_ignores_spoofed_headers_when_peer_is_not_trusted(self):
        """The regression test for the actual vulnerability: an untrusted
        caller sets CF-Connecting-IP itself. With no trusted_proxy_ips
        configured, that header must be ignored — the limiter must key on
        the real, unspoofable TCP peer instead."""
        req = _request(
            {"cf-connecting-ip": "1.2.3.4", "x-forwarded-for": "5.6.7.8"},
            client_host="198.51.100.7",
        )
        assert _real_client_ip(req) == "198.51.100.7"

    def test_ignores_headers_from_a_peer_outside_the_trusted_set(self, monkeypatch):
        monkeypatch.setattr(settings, "trusted_proxy_ips", "10.0.0.1")
        req = _request({"cf-connecting-ip": "1.2.3.4"}, client_host="192.0.2.99")
        assert _real_client_ip(req) == "192.0.2.99"

    def test_falls_back_to_client_host_when_no_proxy_headers(self):
        req = _request({}, client_host="127.0.0.1")
        assert _real_client_ip(req) == "127.0.0.1"

    def test_handles_missing_client(self):
        req = _request({}, client_host=None)
        assert _real_client_ip(req) == "unknown"
