import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pulseguard.security.output_screen import screen_draft


class TestScreenDraft:
    @pytest.mark.asyncio
    async def test_clean_draft_passes(self):
        mock_response = MagicMock()
        mock_response.content = json.dumps({"passed": True, "reasons": []})
        mock_response.usage_metadata = {"input_tokens": 50, "output_tokens": 20}
        mock_model = MagicMock()
        mock_model.ainvoke = AsyncMock(return_value=mock_response)
        with patch("pulseguard.security.output_screen._MODEL", mock_model):
            result = await screen_draft(
                "Sorry about the delay — I've issued a credit.", "Billing dispute"
            )
        assert result.passed is True
        assert result.reasons == []

    @pytest.mark.asyncio
    async def test_flagged_draft_carries_reasons(self):
        mock_response = MagicMock()
        mock_response.content = json.dumps(
            {
                "passed": False,
                "reasons": ["Promises a specific refund amount the KB does not authorize"],
            }
        )
        mock_response.usage_metadata = {"input_tokens": 50, "output_tokens": 20}
        mock_model = MagicMock()
        mock_model.ainvoke = AsyncMock(return_value=mock_response)
        with patch("pulseguard.security.output_screen._MODEL", mock_model):
            result = await screen_draft("I'll refund you $500 right now!", "Billing dispute")
        assert result.passed is False
        assert "refund" in result.reasons[0]

    @pytest.mark.asyncio
    async def test_screening_failure_fails_open_with_a_flag(self):
        """If the screening call itself errors, the draft still reaches the
        queue (never silently dropped) but is flagged for extra scrutiny —
        the one place a screen failure is a signal, not a blocker."""
        mock_model = MagicMock()
        mock_model.ainvoke = AsyncMock(side_effect=RuntimeError("model unavailable"))
        with patch("pulseguard.security.output_screen._MODEL", mock_model):
            result = await screen_draft("Some draft text.", "General complaint / NPS risk")
        assert result.passed is False
        assert "screening unavailable" in result.reasons[0].lower()

    @pytest.mark.asyncio
    async def test_budget_exceeded_fails_open_with_a_flag(self):
        """screen_draft is routed through invoke_with_budget_guard like every
        other LLM call site, but unlike the production agents it must NOT
        propagate BudgetExceededError -- it fails open (flags the draft)
        instead of halting the resolver pipeline."""
        from pulseguard.security.budget_guard import BudgetExceededError

        mock_model = MagicMock()
        mock_model.ainvoke = AsyncMock()
        with (
            patch("pulseguard.security.output_screen._MODEL", mock_model),
            patch(
                "pulseguard.security.output_screen.invoke_with_budget_guard",
                AsyncMock(side_effect=BudgetExceededError("daily spend $1.00 exceeds cap $0.50")),
            ),
        ):
            result = await screen_draft("Some draft text.", "General complaint / NPS risk")
        assert result.passed is False
        assert "spend cap" in result.reasons[0].lower()
        mock_model.ainvoke.assert_not_awaited()
