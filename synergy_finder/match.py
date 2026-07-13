"""Rank cards by mechanical synergy with a given card.

Scoring is a simple weighted overlap: for each other card, sum the
`tags.tag_weight()` of every tag it shares with the source card, plus a
flat bonus per shared creature type (tribal synergy is tracked
separately from tags — see `tags.extract_creature_types`). This is a
starting heuristic, not a tuned model; `TRIBAL_TYPE_WEIGHT` and the tag
weights in `tags.py` are the knobs to revisit once this has been run
against real data.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field

from . import tags as tags_module
from . import db as db_module

# Weight applied per shared creature type. Tribal overlap is a strong,
# unambiguous synergy signal in Commander, so this sits above most tag
# weights (see synergy_finder/tags.py) by design.
TRIBAL_TYPE_WEIGHT = 1.5


@dataclass
class Match:
    card_id: str
    name: str
    type_line: str
    score: float
    matched_tags: tuple[str, ...] = field(default_factory=tuple)
    shared_creature_types: tuple[str, ...] = field(default_factory=tuple)

    def explain(self) -> str:
        parts = []
        if self.matched_tags:
            labels = ", ".join(tags_module.tag_label(t) for t in self.matched_tags)
            parts.append(f"tags: {labels}")
        if self.shared_creature_types:
            parts.append(f"creature types: {', '.join(self.shared_creature_types)}")
        return "; ".join(parts) if parts else "(no overlap)"


class CardNotFoundError(LookupError):
    pass


def find_synergies(
    conn: sqlite3.Connection,
    card_name: str,
    top_n: int = 20,
    same_color_identity_only: bool = False,
) -> list[Match]:
    """Rank other cards in the DB by mechanical synergy with `card_name`.

    `same_color_identity_only` restricts results to cards whose color
    identity is a subset of the source card's — useful when the source
    is a commander and you only want castable-in-that-deck suggestions.
    Off by default since the source can be any card, not just a
    commander.
    """
    source = db_module.get_card_by_name(conn, card_name)
    if source is None:
        raise CardNotFoundError(f"No card found matching {card_name!r}")

    source_tags = db_module.get_tags_for_card(conn, source["id"])
    source_types = db_module.get_creature_types_for_card(conn, source["id"])

    if not source_tags and not source_types:
        return []

    overlap: dict[str, dict[str, set[str]]] = defaultdict(lambda: {"tags": set(), "types": set()})

    if source_tags:
        placeholders = ",".join("?" for _ in source_tags)
        rows = conn.execute(
            f"SELECT card_id, tag FROM card_tags WHERE tag IN ({placeholders}) AND card_id != ?",
            (*source_tags, source["id"]),
        )
        for row in rows:
            overlap[row["card_id"]]["tags"].add(row["tag"])

    if source_types:
        placeholders = ",".join("?" for _ in source_types)
        rows = conn.execute(
            f"""SELECT card_id, creature_type FROM card_creature_types
                WHERE creature_type IN ({placeholders}) AND card_id != ?""",
            (*source_types, source["id"]),
        )
        for row in rows:
            overlap[row["card_id"]]["types"].add(row["creature_type"])

    if not overlap:
        return []

    id_placeholders = ",".join("?" for _ in overlap)
    candidate_rows = {
        row["id"]: row
        for row in conn.execute(
            f"SELECT * FROM cards WHERE id IN ({id_placeholders})", tuple(overlap.keys())
        )
    }

    scored: list[tuple[str, float, set[str], set[str]]] = []
    for card_id, hit in overlap.items():
        if card_id not in candidate_rows:
            continue
        score = sum(tags_module.tag_weight(t) for t in hit["tags"])
        score += TRIBAL_TYPE_WEIGHT * len(hit["types"])
        scored.append((card_id, score, hit["tags"], hit["types"]))

    if same_color_identity_only:
        import json

        source_ci = set(json.loads(source["color_identity"]))
        scored = [
            item
            for item in scored
            if set(json.loads(candidate_rows[item[0]]["color_identity"])).issubset(source_ci)
        ]

    scored.sort(key=lambda item: item[1], reverse=True)
    top = scored[:top_n]

    matches = []
    for card_id, score, matched_tags, shared_types in top:
        row = candidate_rows[card_id]
        matches.append(
            Match(
                card_id=card_id,
                name=row["name"],
                type_line=row["type_line"],
                score=round(score, 2),
                matched_tags=tuple(sorted(matched_tags, key=tags_module.tag_weight, reverse=True)),
                shared_creature_types=tuple(sorted(shared_types)),
            )
        )
    return matches
