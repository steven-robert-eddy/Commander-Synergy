# Commander Synergy Finder

Given a commander (or any Magic: The Gathering card) name, find and rank
other cards that are mechanically synergistic with it, using rule-based
analysis of Scryfall oracle text (no LLM calls, no per-card API requests).

## Status

Phase 1 (data setup) is done. Tagging, matching, and the CLI lookup
command are next.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Fetching card data

Card data comes from Scryfall's `oracle_cards` bulk export
(https://scryfall.com/docs/api/bulk-data) — one JSON file with the latest
printing of every card, updated roughly daily. We download it once and
cache it locally instead of hitting Scryfall per card.

```bash
synergy-finder update-data
```

This:

1. Queries `https://api.scryfall.com/bulk-data` for the current
   `oracle_cards` download URL.
2. Downloads it to `data/oracle_cards.json` (skipped if the local cache is
   less than 24h old — pass `--force` to override).
3. Loads it into a local SQLite database at `data/cards.db` for fast
   querying (name lookup, oracle text search, etc.).

Both `data/oracle_cards.json` and `data/cards.db` are gitignored — they're
regenerated locally rather than committed.

## Project layout

```
synergy_finder/
  bulk_data.py   # download + cache Scryfall's oracle_cards bulk file
  db.py          # load cached JSON into a queryable SQLite database
  cli.py         # `synergy-finder` command-line entry point
tests/
  fixtures/sample_cards.json  # small hand-written card sample for offline tests
  test_db.py
```

## Running tests

```bash
pip install -e . pytest
pytest
```

Tests run entirely offline against `tests/fixtures/sample_cards.json`, so
they don't require network access to Scryfall.
