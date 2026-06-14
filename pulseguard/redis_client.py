from functools import lru_cache

import redis as syncredis
import redis.asyncio as aioredis

from pulseguard.config import settings


@lru_cache(maxsize=1)
def get_async_redis() -> aioredis.Redis:
    return aioredis.from_url(settings.redis_url, decode_responses=True)


@lru_cache(maxsize=1)
def get_sync_redis() -> syncredis.Redis:
    return syncredis.from_url(settings.redis_url, decode_responses=True)


async def close_redis() -> None:
    client = get_async_redis()
    await client.aclose()
