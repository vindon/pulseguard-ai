import os

# Disable LangSmith tracing in tests — no API key in CI, avoids 401 noise
os.environ.setdefault("LANGCHAIN_TRACING_V2", "false")
os.environ.setdefault("LANGCHAIN_API_KEY", "test-key-not-real")

import pytest

from pulseguard.redis_client import get_async_redis, get_sync_redis


@pytest.fixture(autouse=True)
def _fresh_redis_client_cache():
    """get_async_redis()/get_sync_redis() are process-wide lru_cache singletons
    whose connections bind to whichever event loop first uses them.
    pytest-asyncio gives each test function its own event loop, so a client
    cached by a previous test raises "Task ... attached to a different loop"
    when reused here. Clear the cache so any test that touches real Redis
    (i.e. doesn't patch get_async_redis) gets a client bound to its own loop.
    """
    get_async_redis.cache_clear()
    get_sync_redis.cache_clear()
    yield
