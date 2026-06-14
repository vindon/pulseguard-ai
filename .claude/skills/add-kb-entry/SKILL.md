# Skill: add-kb-entry

Adds a new resolution script to the telecom KB and reseeds the ChromaDB vector store.

## What this skill does

1. Validates the category exists in the taxonomy (`pulseguard/mcp_servers/classify_mcp.py` `_TIER_MAP`)
2. Adds a new entry to `pulseguard/kb/telecom_resolutions.json`
3. Deletes and reseeds the ChromaDB collection (run `_seed_collection`)
4. Writes a unit test in `tests/unit/test_mcp_tools.py` asserting `get_resolution_script(category, carrier)` returns the new entry

## Usage

```
/add-kb-entry <category> <carrier> [--tier <0|1|2>]
```

Example: `/add-kb-entry "5G Home Internet" verizon --tier 1`

## Required fields for each KB entry

```json
{
  "category": "<must match taxonomy or add to _TIER_MAP>",
  "carrier": "verizon|tmobile|att",
  "tier": 0|1|2,
  "title": "<short title>",
  "steps": ["Step 1...", "Step 2...", "..."],
  "escalation_triggers": ["trigger 1", "trigger 2"],
  "expected_resolution_minutes": null|<integer>,
  "platform_responses": {
    "x": "<≤280 chars, end with ^PG>",
    "reddit": "<markdown, use **bold** for steps>",
    "review": "<prose, polite, ≤500 chars>"
  }
}
```

## Checklist

- [ ] Category exists in `_TIER_MAP` in `classify_mcp.py` (add if new)
- [ ] All three platform responses provided (x, reddit, review)
- [ ] X response ≤280 chars and ends with `^PG`
- [ ] ChromaDB reseeded: `uv run python -c "from pulseguard.mcp_servers.kb_mcp import _seed_collection, _get_collection; _seed_collection(_get_collection())"`
- [ ] Unit test passes: `uv run pytest tests/unit/test_mcp_tools.py -k kb`
