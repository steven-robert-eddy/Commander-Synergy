# Commander Synergy Finder — Plan & Progress

Given a commander (or any MTG card) name, find and rank other cards that
are mechanically synergistic with it, using rule-based oracle text
analysis — no LLM calls, no per-card API requests.

Stack: Python, SQLite (local cache + queryable card DB), Scryfall bulk
data as the data source.

## Phase 1 — Setup ✅ done

- Project structure: `synergy_finder/` package, `pyproject.toml`,
  `tests/`.
- `synergy_finder/bulk_data.py` downloads Scryfall's `oracle_cards` bulk
  file (https://scryfall.com/docs/api/bulk-data), caching it at
  `data/oracle_cards.json` with a 24h freshness check (`--force` to
  override) instead of hitting the API per card.
- `synergy_finder/db.py` loads the cached JSON into `data/cards.db`
  (SQLite), flattening multi-face cards (DFCs/split cards) into one
  combined `oracle_text`/`type_line`/`mana_cost` per row. Name lookup is
  case-insensitive with prefix fallback.
- `synergy-finder update-data` CLI command runs the full pipeline.
- `data/oracle_cards.json` and `data/cards.db` are gitignored —
  regenerated locally, not committed.

**Known gap:** this dev sandbox's egress policy blocks
`api.scryfall.com` (403), so `update-data` has never actually been run
against live data in this environment — only verified against the
offline test fixture. Whoever runs this with real network access should
run `synergy-finder update-data` once and sanity-check the resulting
`data/cards.db` (row count, spot-check a few cards).

## Phase 2 — Tagging ✅ done

- `synergy_finder/tags.py`: ~14 regex-based mechanical theme tags, each
  a `Tag(id, label, patterns, weight, keyword_aliases)`. Adding a tag is
  just appending to the `TAGS` tuple — the tagger, CLI, and DB
  population all pick it up automatically.
- Current tags: `plus1_plus1_counters`, `sacrifice_synergy`,
  `graveyard_recursion`, `reanimation`, `tokens`, `etb_triggers`,
  `card_draw`, `artifact_matters`, `enchantment_matters`,
  `combat_tricks`, `keyword_combat`, `lifegain`, `ramp`, `spellslinger`.
- Each tag carries a `weight` — a rough manually-assigned "specificity"
  prior (e.g. `reanimation` 1.5 vs. generic `card_draw` 0.8), meant for
  Phase 3 scoring. Not validated against a real corpus yet.
- Creature types (for tribal synergy) are extracted separately via
  `extract_creature_types(type_line)` rather than as a boolean tag —
  tribal matching should compare these sets directly, not go through the
  tag-overlap scorer.
- `db.py::populate_tags()` computes tags/creature-types for every card
  and stores them in `card_tags` / `card_creature_types` tables (indexed
  on both `card_id` and `tag`), so Phase 3 can do SQL-level overlap
  queries instead of re-scanning oracle text per lookup. Runs
  automatically inside `build_database()`.
- CLI: `synergy-finder tag <name>` (debug one card's tags),
  `synergy-finder retag` (recompute tags without re-downloading — use
  this after editing `tags.py`).
- Tests: `tests/test_tags.py`, plus tag/creature-type assertions in
  `tests/test_db.py`. All run offline against
  `tests/fixtures/sample_cards.json`.

**Known gap:** tag patterns are hand-written and only validated against
4 fixture cards. Once real bulk data is loaded, spot-check tag
distributions (`SELECT tag, COUNT(*) FROM card_tags GROUP BY tag`) for
obviously wrong hit rates (a tag matching almost everything, or almost
nothing, usually means a regex bug — see the `sacrifice_synergy` "a" vs
"after" false-positive caught and fixed during Phase 2 for the kind of
thing to watch for).

## Phase 3 — Matching (not started)

Plan: given an input card name, look up its tags + creature types, then
score every other card in `cards` by:

- Tag overlap, weighted by each tag's `weight` (rarer/more specific tags
  should count for more — current weights are a starting guess, may
  want to replace with real inverse-document-frequency from the corpus
  once it's loaded).
- Creature type overlap (tribal) as a separate signal/bonus, since it's
  not part of the tag-weight scheme.
- Return top N ranked matches with a short "why" explanation (which
  tags/types overlapped and their weights) — this is a stated
  requirement, not optional polish.

Open questions to resolve when starting this phase:
- Exact scoring formula (sum of overlapping tag weights? Jaccard-style
  normalization by total tag count so verbose cards don't win by sheer
  tag count?).
- Whether to exclude the input card's own color identity mismatches, or
  leave color-identity filtering to the caller/CLI flag.
- Where this logic lives: likely `synergy_finder/match.py` with a
  `find_synergies(conn, card_name, top_n=20) -> list[Match]`-shaped API,
  consumed by both the CLI and (later) a web UI.

## Phase 4 — Interface (not started)

- CLI: `synergy-finder find "Korvold, Fae-Cursed King"` prints ranked
  matches with reasons (builds on Phase 3's `find_synergies`).
- Web UI: deferred, no design decisions made yet.

## Project layout (current)

```
synergy_finder/
  bulk_data.py   # download + cache Scryfall's oracle_cards bulk file
  db.py          # load cached JSON into SQLite, run tagging (Phase 1 + 2)
  tags.py        # regex-based mechanical theme tag definitions + tagger (Phase 2)
  cli.py         # `synergy-finder` command-line entry point
tests/
  fixtures/sample_cards.json  # small hand-written card sample for offline tests
  test_db.py
  test_tags.py
PLAN.md          # this file
README.md        # setup + usage instructions
```

## Repo/branch notes

- Working repo: `steven-robert-eddy/commander-synergy` (renamed to
  `Commander-Synergy` on GitHub; old remote URL still redirects).
- All work happens on branch `claude/mtg-synergy-finder-tnfmks`.
- A sibling repo, `steven-robert-eddy/commander-companion`, also exists
  and is currently empty/unused — this project intentionally was not
  duplicated there (see decision in conversation history).
