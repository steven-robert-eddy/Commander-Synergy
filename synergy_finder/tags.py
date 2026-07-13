"""Rule-based mechanical theme tagging for MTG cards.

Each `Tag` is a set of regexes matched against a card's oracle text (plus,
for a couple of tags, its structured `keywords` list). A card can carry
any number of tags. To add a new theme, append a `Tag` to `TAGS` below —
nothing else needs to change; the tagger, the CLI, and the DB population
step all just iterate `TAGS`.

`weight` is a rough prior for how *specific* (as opposed to generic) a
tag is, used later by the matching/scoring step to weight rarer, more
telling overlaps above common ones. It's a starting point, not gospel —
Phase 3 can refine it with real corpus frequency if the priors are off.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Mapping


@dataclass(frozen=True)
class Tag:
    id: str
    label: str
    patterns: tuple[re.Pattern, ...]
    weight: float = 1.0
    # Combat keywords (from Scryfall's structured `keywords` field) that
    # also count as a match for this tag, independent of oracle text.
    keyword_aliases: tuple[str, ...] = field(default_factory=tuple)


def _rx(*patterns: str) -> tuple[re.Pattern, ...]:
    return tuple(re.compile(p, re.IGNORECASE) for p in patterns)


TAGS: tuple[Tag, ...] = (
    Tag(
        id="plus1_plus1_counters",
        label="+1/+1 Counters",
        weight=1.3,
        patterns=_rx(r"\+1/\+1 counter"),
    ),
    Tag(
        id="sacrifice_synergy",
        label="Sacrifice / Aristocrats",
        weight=1.3,
        patterns=_rx(
            r"\bsacrifice(s|d)? (a|an|another|target|\d)\b",
            r"\bsacrifice this\b",
            r"whenever (a |another )?creature (you control )?dies",
            r"whenever .* you control dies",
        ),
    ),
    Tag(
        id="graveyard_recursion",
        label="Graveyard Recursion",
        weight=1.2,
        patterns=_rx(
            r"from (a|your|target opponent's) graveyard",
            r"return .* from (your|a) graveyard",
            r"put .* graveyard.{0,20}onto the battlefield",
        ),
    ),
    Tag(
        id="reanimation",
        label="Reanimation",
        weight=1.5,
        patterns=_rx(
            r"return (target |a )?creature card from (a|your|any) graveyard to the battlefield",
            r"put (a|target) creature card from (a|your|any) graveyard onto the battlefield",
        ),
    ),
    Tag(
        id="tokens",
        label="Token Generation",
        weight=1.1,
        patterns=_rx(
            r"create (a|one|two|three|four|x|\d+) .*token",
            r"\btoken creature\b",
        ),
    ),
    Tag(
        id="etb_triggers",
        label="ETB Triggers",
        weight=0.9,
        patterns=_rx(
            r"whenever [^.]* enters(?! the battlefield under)",
            r"\benters the battlefield\b",
            r"when [^.]* enters,",
        ),
    ),
    Tag(
        id="card_draw",
        label="Card Draw Engine",
        weight=0.8,
        patterns=_rx(
            r"draw (a|two|three|x|\d+|that many) cards?",
            r"whenever you draw (a|your first) card",
        ),
    ),
    Tag(
        id="artifact_matters",
        label="Artifact Matters",
        weight=1.1,
        patterns=_rx(
            r"artifact(s)? you control",
            r"whenever (an|another) artifact (you control )?enters",
            r"target artifact",
        ),
    ),
    Tag(
        id="enchantment_matters",
        label="Enchantment Matters",
        weight=1.2,
        patterns=_rx(
            r"enchantment(s)? you control",
            r"whenever (an|another) enchantment (you control )?enters",
            r"target enchantment",
        ),
    ),
    Tag(
        id="combat_tricks",
        label="Combat Tricks",
        weight=0.9,
        patterns=_rx(
            r"target creature (you control )?gets? [+\-]\d*x?/[+\-]\d*x?",
            r"until end of turn",
        ),
    ),
    Tag(
        id="keyword_combat",
        label="Evasion / Combat Keywords",
        weight=0.7,
        keyword_aliases=(
            "Flying",
            "Trample",
            "Menace",
            "Deathtouch",
            "First strike",
            "Double strike",
            "Vigilance",
            "Haste",
            "Reach",
        ),
        patterns=_rx(
            r"\b(flying|trample|menace|deathtouch|first strike|double strike|vigilance|haste|reach)\b",
        ),
    ),
    Tag(
        id="lifegain",
        label="Lifegain",
        weight=1.0,
        patterns=_rx(
            r"gain(s)? \d* ?(or more )?life",
            r"whenever you gain life",
            r"life equal to",
        ),
    ),
    Tag(
        id="ramp",
        label="Mana Ramp",
        weight=1.0,
        patterns=_rx(
            r"search your library for a( basic)? land card",
            r"add (one mana|\{[cwubrg]\})",
            r"add [a-z\s]*mana of any (one )?color",
        ),
    ),
    Tag(
        id="spellslinger",
        label="Instant/Sorcery Matters",
        weight=1.3,
        patterns=_rx(
            r"instant (and|or) sorcery spells?",
            r"whenever you cast an instant or sorcery spell",
            r"noncreature spell",
        ),
    ),
)

_TAGS_BY_ID: dict[str, Tag] = {tag.id: tag for tag in TAGS}


def _get(card: Mapping, key: str, default=None):
    """`Mapping.get`, but also works with `sqlite3.Row` (no `.get` method)."""
    try:
        value = card[key]
    except (KeyError, IndexError):
        return default
    return default if value is None else value

# Words we skip when treating a card's type line as a creature-type signal —
# these show up in type lines but aren't tribal-relevant subtypes.
_NON_TRIBAL_TYPE_WORDS = {"Legendary", "Creature", "Artifact", "Snow", "Basic", "World", "Host"}


def tag_card(card: Mapping) -> set[str]:
    """Return the set of tag ids that apply to `card`.

    `card` just needs to look like a mapping with `oracle_text` (str) and
    optionally `keywords` (list[str] or JSON-encoded list[str]) — this
    works equally well against a raw Scryfall card dict, a `sqlite3.Row`
    from `db.py`, or a hand-built dict in a test.
    """
    text = _get(card, "oracle_text", "")
    keywords = _extract_keywords(card)
    keyword_set = {kw.lower() for kw in keywords}

    matched: set[str] = set()
    for tag in TAGS:
        if any(alias.lower() in keyword_set for alias in tag.keyword_aliases):
            matched.add(tag.id)
            continue
        if any(pattern.search(text) for pattern in tag.patterns):
            matched.add(tag.id)
    return matched


def _extract_keywords(card: Mapping) -> Iterable[str]:
    keywords = _get(card, "keywords")
    if keywords is None:
        return []
    if isinstance(keywords, str):
        import json

        try:
            return json.loads(keywords)
        except json.JSONDecodeError:
            return []
    return keywords


def extract_creature_types(type_line: str | None) -> set[str]:
    """Pull out subtypes after the em dash in a type line for tribal matching.

    E.g. "Legendary Creature — Dragon Noble" -> {"Dragon", "Noble"}.
    Front/back-face type lines joined with " // " are both scanned.
    """
    if not type_line:
        return set()

    types: set[str] = set()
    for face in type_line.split(" // "):
        if "—" in face:  # em dash
            _, _, subtypes = face.partition("—")
        elif "-" in face and " - " in face:
            _, _, subtypes = face.partition(" - ")
        else:
            continue
        for word in subtypes.split():
            word = word.strip()
            if word and word not in _NON_TRIBAL_TYPE_WORDS:
                types.add(word)
    return types


def tag_label(tag_id: str) -> str:
    tag = _TAGS_BY_ID.get(tag_id)
    return tag.label if tag else tag_id


def tag_weight(tag_id: str) -> float:
    tag = _TAGS_BY_ID.get(tag_id)
    return tag.weight if tag else 1.0


def all_tag_ids() -> tuple[str, ...]:
    return tuple(tag.id for tag in TAGS)
