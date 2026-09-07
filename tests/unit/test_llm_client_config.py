"""Every ChatAnthropic client in the codebase must set an explicit timeout
and max_retries=1 — an unbounded client timeout is what lets a stuck LLM
call burn spend silently instead of failing fast into the retry/halt logic
in orchestrator/graph.py."""

import pulseguard.agents.escalation as escalation
import pulseguard.agents.resolver as resolver
import pulseguard.agents.sentinel as sentinel
import pulseguard.agents.triage as triage


def _assert_hardened(model) -> None:
    assert model.default_request_timeout is not None
    assert model.default_request_timeout <= 60
    assert model.max_retries == 1


class TestLlmClientHardening:
    def test_sentinel_model(self):
        _assert_hardened(sentinel._MODEL)

    def test_triage_model(self):
        _assert_hardened(triage._MODEL)

    def test_resolver_model(self):
        _assert_hardened(resolver._MODEL)

    def test_resolver_thinking_model(self):
        _assert_hardened(resolver._MODEL_THINKING)

    def test_escalation_model(self):
        _assert_hardened(escalation._MODEL)
