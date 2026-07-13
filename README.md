# Commander Synergy Finder

Given a commander (or any Magic: The Gathering card) name, find and rank
other cards that are mechanically synergistic with it, using rule-based
analysis of Scryfall oracle text (no LLM calls, no per-card API requests).

## Status

All four phases are done: data setup, tagging, matching, and a web app
(FastAPI + vanilla JS) on top of the same matching engine the CLI uses.

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

## Tagging

Every card is scanned against a set of regex-based rules
(`synergy_finder/tags.py`) that assign mechanical theme tags — e.g.
`plus1_plus1_counters`, `sacrifice_synergy`, `graveyard_recursion`,
`tokens`, `etb_triggers`, `card_draw`, `artifact_matters`,
`enchantment_matters`, `combat_tricks`, `keyword_combat`, `lifegain`,
`ramp`, `spellslinger`, `reanimation`. Each tag also carries a rough
"specificity" weight, used later to weight rarer, more telling overlaps
above generic ones when scoring matches.

Creature types (for tribal synergy) are extracted separately from each
card's type line rather than tagged as a single boolean.

Tags run automatically as part of `update-data` / `build_database`, and
are stored in a `card_tags` table (plus `card_creature_types`) so matching
can query them with plain SQL instead of re-scanning oracle text. To
recompute tags without re-downloading data (e.g. after editing
`tags.py`):

```bash
synergy-finder retag
```

To debug what a single card tags as:

```bash
synergy-finder tag "Korvold, Fae-Cursed King"
```

Adding a new tag just means adding a new `Tag(...)` entry to the `TAGS`
tuple in `synergy_finder/tags.py` — the tagger, CLI, and DB population
all pick it up automatically.

## Matching

`synergy_finder/match.py` ranks every other card in the DB against a
given card by weighted tag overlap: for each shared tag, add that tag's
`weight` (from `tags.py`); for each shared creature type (tribal
synergy, tracked separately from tags), add a flat `TRIBAL_TYPE_WEIGHT`
bonus. Results are returned as `Match` objects with a `.explain()`
string listing which tags/types drove the score.

```bash
synergy-finder find "Korvold, Fae-Cursed King"
synergy-finder find "Korvold, Fae-Cursed King" --top 10 --same-color-identity
```

`--same-color-identity` restricts results to cards whose color identity
fits within the source card's — handy when the source is a commander and
you only want suggestions that are actually castable in that deck.

## Web app

A small FastAPI backend (`synergy_finder/web/app.py`) serves a JSON API
plus a single-page vanilla-JS frontend (`synergy_finder/web/static/`) —
a search box with autocomplete, a "same color identity" toggle, and a
ranked results list with per-match explanations. No Node/build step; the
frontend is plain HTML/CSS/JS served directly by the backend.

```bash
synergy-finder serve
```

Then open http://127.0.0.1:8000. Flags: `--host`, `--port`, `--reload`
(auto-restart on code changes, for development).

API endpoints, if you want to hit them directly or build another client:

- `GET /api/cards/search?q=<partial name>&limit=10` — autocomplete.
- `GET /api/synergy?name=<card name>&top=20&same_color_identity=false` —
  same ranking `synergy-finder find` produces, as JSON.

## Project layout

```
synergy_finder/
  bulk_data.py   # download + cache Scryfall's oracle_cards bulk file
  db.py          # load cached JSON into a queryable SQLite database, run tagging
  tags.py        # regex-based mechanical theme tag definitions + tagger
  match.py       # rank cards by weighted tag/creature-type overlap
  cli.py         # `synergy-finder` command-line entry point
  web/
    app.py       # FastAPI app (JSON API + serves the static frontend)
    static/      # index.html / app.js / style.css — no build step
tests/
  fixtures/sample_cards.json  # small hand-written card sample for offline tests
  test_db.py
  test_tags.py
  test_match.py
  test_web.py
```

## Running tests

```bash
pip install -e ".[dev]"
pytest
```

Tests run entirely offline against `tests/fixtures/sample_cards.json`, so
they don't require network access to Scryfall.
