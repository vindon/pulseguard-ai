# Skill: add-feed-adapter

Scaffolds a new feed adapter for PulseGuard AI.

## What this skill does

1. Creates `pulseguard/adapters/{name}_adapter.py` extending `FeedAdapter` ABC
2. Implements `fetch()` and `health_check()` methods
3. Adds Pydantic fields to `adapter_metadata` for source-specific data
4. Registers the adapter in `pulseguard/orchestrator/graph.py`
5. Adds the new source literal to `RawSignal.source` in `pulseguard/models/signals.py`
6. Writes unit tests in `tests/unit/test_adapters.py` with mocked API responses
7. Documents any new env vars in `.env.example`

## Usage

```
/add-feed-adapter <name> <source_literal> <description>
```

Example: `/add-feed-adapter linkedin linkedin LinkedIn company page posts`

## Template

```python
class {Name}Adapter(FeedAdapter):
    name = "{source_literal}"
    carrier_configs: list[CarrierConfig] = list(CARRIER_CONFIGS.values())

    def __init__(self) -> None:
        self._consecutive_errors = 0
        self._last_successful_fetch: datetime | None = None

    async def fetch(self) -> list[RawSignal]:
        # TODO: implement using httpx or SDK
        # Always call self._make_signal() — never bypass PII sanitisation
        ...

    async def health_check(self) -> AdapterHealth:
        status = "DOWN" if self._consecutive_errors >= 5 else (
            "DEGRADED" if self._consecutive_errors >= 3 else "HEALTHY"
        )
        return AdapterHealth(
            adapter_name=self.name,
            status=status,
            last_successful_fetch=self._last_successful_fetch,
            consecutive_errors=self._consecutive_errors,
        )
```

## Checklist before marking done

- [ ] `fetch()` calls `self._make_signal()` for every signal (no raw author handles or un-sanitised content)
- [ ] `health_check()` returns correct status based on `_consecutive_errors`
- [ ] Circuit breaker registered in `orchestrator/circuit_breaker.py`
- [ ] Unit tests pass: `uv run pytest tests/unit/test_adapters.py -k {name}`
- [ ] New source literal added to `RawSignal.source` Literal type
- [ ] Adapter added to orchestrator polling loop
