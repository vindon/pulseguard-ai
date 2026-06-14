# Skill: check-x-cap

Reports current X API monthly read usage, cap percentage, and projected end-of-month usage.

## What this skill does

Reads `pulseguard:x:monthly_reads` from Redis and computes:
- Current reads used
- Percentage of 15,000 monthly cap
- Days remaining in the current billing cycle (assumes calendar month)
- Projected end-of-month reads at current daily rate
- Warning if >80% used

## Usage

```
/check-x-cap
```

## Output format

```
X API Monthly Read Usage
========================
Used:      8,432 / 15,000  (56.2%)
Remaining: 6,568 reads
Days left in cycle: 12
Daily average: 703 reads/day
Projected EOM usage: ~8,436 + (12 × 703) = 16,872 ⚠️ OVER CAP
Status: ON TRACK / AT RISK / OVER CAP
```

## To run manually

```bash
uv run python -c "
import asyncio
from pulseguard.redis_client import get_async_redis

async def check():
    redis = get_async_redis()
    used = int(await redis.get('pulseguard:x:monthly_reads') or 0)
    cap = 15000
    pct = used / cap * 100
    print(f'X API reads: {used:,} / {cap:,} ({pct:.1f}%)')
    if pct >= 80:
        print('⚠️  WARNING: At or above 80% of monthly cap')

asyncio.run(check())
"
```

## To reset cap counter (new billing cycle)

```bash
redis-cli SET pulseguard:x:monthly_reads 0
```
