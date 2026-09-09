"""
When the system-wide halt flag (pulseguard.orchestrator.halt) is set, the
orchestrator's 5 continuously-running loops must actually stop pulling and
dispatching new work — not just the manual-ingest gateway endpoint. Before
this fix, is_halted() was checked nowhere in the orchestrator itself, so
after 3 consecutive dispatch failures tripped the halt, the polling loops
kept fetching and the stream consumers kept consuming and re-dispatching
into the same broken agent forever, silently re-writing the halt key on
every subsequent failure with zero reduction in work. This directly
contradicted halt.py's own docstring claim that "every signal-processing
entrypoint returns early" once halted.

Each test below forces is_halted() to return True, lets the loop run for
exactly one iteration (via a patched asyncio.sleep that flips `_running`
off), and asserts the loop's fetch/consume call was never made for that
iteration.
"""

from unittest.mock import AsyncMock, patch

import pytest

from pulseguard.orchestrator.graph import PulseGuardOrchestrator


def _orchestrator() -> PulseGuardOrchestrator:
    return PulseGuardOrchestrator()


class TestPollingLoopsRespectHalt:
    @pytest.mark.asyncio
    async def test_poll_x_skips_fetch_when_halted(self):
        orch = _orchestrator()
        orch._running = True
        orch._adapters["x"].fetch = AsyncMock(return_value=[])

        async def fake_sleep(_seconds: float) -> None:
            orch._running = False

        with (
            patch("pulseguard.orchestrator.halt.is_halted", AsyncMock(return_value=True)),
            patch("pulseguard.orchestrator.graph.asyncio.sleep", side_effect=fake_sleep),
        ):
            await orch._poll_x()

        orch._adapters["x"].fetch.assert_not_called()

    @pytest.mark.asyncio
    async def test_poll_reddit_skips_fetch_when_halted(self):
        orch = _orchestrator()
        orch._running = True
        orch._adapters["reddit"].fetch = AsyncMock(return_value=[])

        async def fake_sleep(_seconds: float) -> None:
            orch._running = False

        with (
            patch("pulseguard.orchestrator.halt.is_halted", AsyncMock(return_value=True)),
            patch("pulseguard.orchestrator.graph.asyncio.sleep", side_effect=fake_sleep),
        ):
            await orch._poll_reddit()

        orch._adapters["reddit"].fetch.assert_not_called()


class TestStreamConsumersRespectHalt:
    @pytest.mark.asyncio
    async def test_consume_validated_signals_skips_consume_when_halted(self):
        orch = _orchestrator()
        orch._running = True

        async def fake_sleep(_seconds: float) -> None:
            orch._running = False

        with (
            patch("pulseguard.orchestrator.halt.is_halted", AsyncMock(return_value=True)),
            patch(
                "pulseguard.orchestrator.graph.consume_stream", AsyncMock(return_value=[])
            ) as mock_consume,
            patch("pulseguard.orchestrator.graph.asyncio.sleep", side_effect=fake_sleep),
        ):
            await orch._consume_validated_signals()

        mock_consume.assert_not_called()

    @pytest.mark.asyncio
    async def test_consume_triage_reports_skips_consume_when_halted(self):
        orch = _orchestrator()
        orch._running = True

        async def fake_sleep(_seconds: float) -> None:
            orch._running = False

        with (
            patch("pulseguard.orchestrator.halt.is_halted", AsyncMock(return_value=True)),
            patch(
                "pulseguard.orchestrator.graph.consume_stream", AsyncMock(return_value=[])
            ) as mock_consume,
            patch("pulseguard.orchestrator.graph.asyncio.sleep", side_effect=fake_sleep),
        ):
            await orch._consume_triage_reports()

        mock_consume.assert_not_called()

    @pytest.mark.asyncio
    async def test_consume_escalation_needed_skips_consume_when_halted(self):
        orch = _orchestrator()
        orch._running = True

        async def fake_sleep(_seconds: float) -> None:
            orch._running = False

        with (
            patch("pulseguard.orchestrator.halt.is_halted", AsyncMock(return_value=True)),
            patch(
                "pulseguard.orchestrator.graph.consume_stream", AsyncMock(return_value=[])
            ) as mock_consume,
            patch("pulseguard.orchestrator.graph.asyncio.sleep", side_effect=fake_sleep),
        ):
            await orch._consume_escalation_needed()

        mock_consume.assert_not_called()


class TestLoopsProceedNormallyWhenNotHalted:
    @pytest.mark.asyncio
    async def test_poll_x_still_fetches_when_not_halted(self):
        """Guards against a check so eager it also skips work when healthy."""
        orch = _orchestrator()
        orch._running = True
        orch._adapters["x"].fetch = AsyncMock(return_value=[])

        async def fake_sleep(_seconds: float) -> None:
            orch._running = False

        with (
            patch("pulseguard.orchestrator.halt.is_halted", AsyncMock(return_value=False)),
            patch("pulseguard.orchestrator.graph.asyncio.sleep", side_effect=fake_sleep),
        ):
            await orch._poll_x()

        orch._adapters["x"].fetch.assert_called_once()

    @pytest.mark.asyncio
    async def test_consume_validated_signals_still_consumes_when_not_halted(self):
        """consume_stream returning no events doesn't sleep on the success
        path, so the loop would spin forever in a test — stop it by having
        the mocked consume_stream itself flip `_running` off after the
        first call, rather than relying on a patched sleep."""
        orch = _orchestrator()
        orch._running = True

        async def fake_consume(*_args, **_kwargs) -> list:
            orch._running = False
            return []

        with (
            patch("pulseguard.orchestrator.halt.is_halted", AsyncMock(return_value=False)),
            patch(
                "pulseguard.orchestrator.graph.consume_stream", AsyncMock(side_effect=fake_consume)
            ) as mock_consume,
        ):
            await orch._consume_validated_signals()

        mock_consume.assert_called_once()
