"""Regression gate for Resolver's drafted output quality — required,
blocking CI per spec §12/§13, not an optional nightly check. Uses an
LLM-as-judge (Haiku, cheap and fast) to score each eval case's actual
draft against its rubric, and fails the build if the average score
drops below threshold. This is intentionally a real assertion, not a
report — a build that regresses draft quality should not merge, the
same way a build that fails a unit test should not merge."""

import json
from pathlib import Path

import pytest
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from pulseguard.config import settings
from pulseguard.models.signals import RawSignal, ValidatedSignal
from pulseguard.models.triage import TriageReport
from pulseguard.security.budget_guard import check_budget, record_spend

_FIXTURES = Path(__file__).parent.parent / "fixtures" / "evals" / "eval_cases.json"
# api_key is passed explicitly (not left to ChatAnthropic's default env-var
# lookup) because this module is imported at pytest collection time, before
# any pulseguard.agents.* module has run — those modules set
# os.environ["ANTHROPIC_API_KEY"] as an import side effect (see
# pulseguard/tracing.py), but this file has no reason to depend on that
# import ordering just to construct its own judge model.
_JUDGE = ChatAnthropic(
    model="claude-haiku-4-5",
    api_key=settings.anthropic_api_key,
    temperature=0,
    timeout=30,
    max_retries=1,
)
_SCORE_THRESHOLD = 3.5  # out of 5 — a build failing below this blocks merge


def _load_cases() -> list[dict]:
    return json.loads(_FIXTURES.read_text())


async def _judge_score(draft: str, rubric: str) -> float:
    prompt = (
        f"Rubric: {rubric}\n\nDraft reply to score:\n{draft}\n\n"
        "Score this draft 1-5 against the rubric (5 = fully satisfies it, "
        "1 = violates it). Return ONLY the number."
    )
    await check_budget()
    response = await _JUDGE.ainvoke(
        [
            SystemMessage(content="You score customer-support drafts against a rubric."),
            HumanMessage(content=prompt),
        ]
    )
    usage = getattr(response, "usage_metadata", None) or {}
    details = usage.get("input_token_details", {}) or {}
    await record_spend(
        "claude-haiku-4-5",
        input_tokens=usage.get("input_tokens", 0),
        output_tokens=usage.get("output_tokens", 0),
        cache_creation_tokens=details.get("cache_creation", 0),
        cache_read_tokens=details.get("cache_read", 0),
    )
    raw = str(response.content).strip()
    try:
        return float(raw)
    except ValueError as exc:
        raise AssertionError(
            f"Judge did not return a bare number as instructed (got: {raw!r})"
        ) from exc


@pytest.mark.asyncio
async def test_resolver_draft_quality_meets_threshold():
    """This test makes real Anthropic API calls (both to draft and to judge)
    — it is deliberately excluded from the fast local loop and run as its
    own required CI job (see ci.yml) so PR authors aren't blocked by API
    latency on every local test run, but merges are still blocked on it."""
    from pulseguard.agents.resolver import draft_response

    cases = _load_cases()
    scores = []
    for case in cases:
        vs = ValidatedSignal(
            signal_id=case["id"],
            raw=RawSignal(
                signal_id=case["id"],
                source="x",
                source_id=case["id"],
                author_handle="hash-placeholder",
                content=case["content"],
                url=f"https://x.com/i/web/status/{case['id']}",
                posted_at="2026-01-01T00:00:00+00:00",
                ingested_at="2026-01-01T00:00:00+00:00",
            ),
            detected_carrier=case["carrier"],
            is_valid=True,
            validity_reason="eval fixture",
            content_hash="eval-hash",
            sentinel_trace_id="eval-trace",
            validated_at="2026-01-01T00:00:00+00:00",
        )
        tr = TriageReport(
            signal_id=case["id"],
            category=case["category"],
            resolution_tier=0,
            severity_score=2,
            sentiment_score=-0.5,
            churn_risk=False,
            routing_decision="RESOLVER",
            routing_rationale="eval fixture",
            triage_trace_id="eval-trace",
            triaged_at="2026-01-01T00:00:00+00:00",
        )
        state = {
            "triage_report": tr.model_dump(),
            "validated_signal": vs.model_dump(),
            "kb_script": None,
            "draft_response": "",
            "trace_id": "eval-trace",
        }
        result = await draft_response(state)
        score = await _judge_score(result["draft_response"], case["rubric"])
        scores.append(score)

    average = sum(scores) / len(scores)
    assert (
        average >= _SCORE_THRESHOLD
    ), f"Resolver draft quality regressed: {average:.2f} < {_SCORE_THRESHOLD}"


@pytest.mark.asyncio
async def test_judge_correctly_penalizes_a_deliberately_bad_draft():
    """Sanity-checks the judge itself: if it can't tell a bad draft from a
    good one, the threshold assertion above is meaningless."""
    bad_draft = "idk, not my problem, figure it out yourself"
    rubric = "Draft must acknowledge the specific complaint and offer a concrete next step, professionally."
    score = await _judge_score(bad_draft, rubric)
    assert score <= 2.0, f"Judge failed to penalize an obviously bad draft (scored {score})"
