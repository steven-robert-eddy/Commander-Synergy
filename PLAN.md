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

## Phase 3 — Matching ✅ done

- `synergy_finder/match.py::find_synergies(conn, card_name, top_n=20,
  same_color_identity_only=False) -> list[Match]`.
- Scoring: sum of `tags.tag_weight()` for every tag shared with the
  source card, plus `TRIBAL_TYPE_WEIGHT` (1.5, a flat bonus, not
  normalized against tag weights yet) per shared creature type.
  No Jaccard-style normalization by total tag count — a card with many
  overlapping tags currently outranks one with fewer regardless of how
  "tag-heavy" either card's oracle text is. Revisit if this over/under-
  ranks verbose cards once real data is loaded.
- `same_color_identity_only` flag filters candidates to those whose
  color identity is a subset of the source's — applied before ranking/
  truncation (not after), so `top_n` results are always filled from the
  filtered set, not shrunk by post-hoc filtering.
- Excludes the source card itself from results. Returns `[]` (not an
  error) for a card with no tags and no creature types — nothing to
  compare on.
- `Match.explain()` renders which tags (by label) and which creature
  types drove the score — satisfies the "short explanation of why"
  requirement.
- Raises `match.CardNotFoundError` for an unknown card name; CLI catches
  it and prints a clean message.
- CLI: `synergy-finder find "<name>" [--top N] [--same-color-identity]`.
- Tests: `tests/test_match.py`, verified against the same 4-card
  fixture — Fable (3 shared tags, score 2.4) correctly outranks Ashnod's
  Altar and Hardened Scales (1 shared tag each, score 1.3) for a Korvold
  query.

**Known gap:** tag weights and `TRIBAL_TYPE_WEIGHT` are still hand-picked
priors, not validated against real card data (see Phase 2's known gap —
same underlying issue). Worth sanity-checking top matches for a handful
of well-known commanders once `update-data` has actually run.

## Phase 4 — Interface ✅ done

User decided this should be more of an app than a bare CLI. Stack
decision (asked, not assumed): **FastAPI + plain HTML/JS**, local-only
for now — no separate frontend build step, no deployment/hosting setup.

- `synergy_finder/web/app.py` — FastAPI app exposing:
  - `GET /api/cards/search?q=&limit=` — substring name search for
    autocomplete (`db.search_card_names`, new in this phase).
  - `GET /api/synergy?name=&top=&same_color_identity=` — same ranking
    `match.find_synergies` produces, as JSON (source card + list of
    matches with name/type_line/score/explanation/matched_tags/shared
    creature types).
  - `GET /` — serves the static frontend's `index.html`.
  - 503 (not 500) if `data/cards.db` doesn't exist yet — tells the user
    to run `update-data` rather than a bare stack trace.
- `synergy_finder/web/static/` — one HTML page, vanilla JS
  (`app.js`, debounced autocomplete with keyboard nav, no framework),
  and CSS with light/dark support via `prefers-color-scheme`. Served
  directly by FastAPI's `StaticFiles`; no Node/npm anywhere in this repo.
- CLI: `synergy-finder serve [--host] [--port] [--reload]` launches it
  via `uvicorn.run("synergy_finder.web.app:app", ...)`. Refuses to start
  with a clear error if `data/cards.db` is missing.
- `synergy-finder find` (Phase 3) is untouched and still works
  standalone — the web app is a second, independent consumer of
  `match.find_synergies`, not a replacement.
- Verified with Playwright against a screenshot of the running app
  (search → autocomplete → ranked results with explanations) — this was
  an actual rendered-browser check, not just curling the API.
- Tests: `tests/test_web.py` uses FastAPI's `TestClient` +
  `monkeypatch` on `db.connect` to point at a temp DB built from the
  same offline fixture used elsewhere. New dev-only extras group in
  `pyproject.toml` (`pip install -e ".[dev]"`) adds `httpx` (required by
  `TestClient`) alongside `pytest`.

**Known gaps / deliberately deferred:**
- No deployment/hosting story yet — user explicitly said local-only for
  now. Revisit if/when that changes (containerizing is easy since it's
  just `uvicorn` + a SQLite file, but nothing's been set up).
- No auth, no rate limiting, no pagination beyond `top`/`limit` query
  params — fine for a local single-user tool, would need attention
  before exposing this beyond localhost.
- The `StarletteDeprecationWarning` about `httpx` vs `httpx2` in test
  output comes from FastAPI's `TestClient` internals, not our code —
  harmless for now, but if a future FastAPI/Starlette upgrade removes
  the old `httpx` code path, `test_web.py`'s import will need updating.

## Project layout (current)

```
synergy_finder/
  bulk_data.py   # download + cache Scryfall's oracle_cards bulk file
  db.py          # load cached JSON into SQLite, run tagging (Phase 1 + 2)
  tags.py        # regex-based mechanical theme tag definitions + tagger (Phase 2)
  match.py       # rank cards by weighted tag/creature-type overlap (Phase 3)
  cli.py         # `synergy-finder` command-line entry point
  web/
    app.py       # FastAPI app: JSON API + serves the static frontend (Phase 4)
    static/      # index.html / app.js / style.css — no build step
tests/
  fixtures/sample_cards.json  # small hand-written card sample for offline tests
  test_db.py
  test_tags.py
  test_match.py
  test_web.py
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
