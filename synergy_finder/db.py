"""Load cached Scryfall oracle card data into a local SQLite database."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterable, Iterator

from . import tags as tags_module
from .bulk_data import CARDS_PATH, DATA_DIR

DB_PATH = DATA_DIR / "cards.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS cards (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    name_lower TEXT NOT NULL,
    oracle_text TEXT NOT NULL DEFAULT '',
    type_line TEXT NOT NULL DEFAULT '',
    mana_cost TEXT NOT NULL DEFAULT '',
    cmc REAL NOT NULL DEFAULT 0,
    colors TEXT NOT NULL DEFAULT '[]',
    color_identity TEXT NOT NULL DEFAULT '[]',
    keywords TEXT NOT NULL DEFAULT '[]',
    power TEXT,
    toughness TEXT,
    rarity TEXT NOT NULL DEFAULT '',
    set_code TEXT NOT NULL DEFAULT '',
    legalities TEXT NOT NULL DEFAULT '{}',
    raw TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cards_name_lower ON cards (name_lower);

CREATE TABLE IF NOT EXISTS card_tags (
    card_id TEXT NOT NULL REFERENCES cards (id),
    tag TEXT NOT NULL,
    PRIMARY KEY (card_id, tag)
);
CREATE INDEX IF NOT EXISTS idx_card_tags_tag ON card_tags (tag);
CREATE INDEX IF NOT EXISTS idx_card_tags_card_id ON card_tags (card_id);

CREATE TABLE IF NOT EXISTS card_creature_types (
    card_id TEXT NOT NULL REFERENCES cards (id),
    creature_type TEXT NOT NULL,
    PRIMARY KEY (card_id, creature_type)
);
CREATE INDEX IF NOT EXISTS idx_card_creature_types_type ON card_creature_types (creature_type);
"""


def _combined_oracle_text(card: dict) -> str:
    """Scryfall splits double-faced/split cards into `card_faces`; flatten them."""
    if card.get("oracle_text"):
        return card["oracle_text"]
    faces = card.get("card_faces") or []
    return "\n//\n".join(face.get("oracle_text", "") for face in faces if face.get("oracle_text"))


def _combined_type_line(card: dict) -> str:
    return card.get("type_line", "")


def _combined_mana_cost(card: dict) -> str:
    if card.get("mana_cost"):
        return card["mana_cost"]
    faces = card.get("card_faces") or []
    return " // ".join(face.get("mana_cost", "") for face in faces if face.get("mana_cost"))


def _card_row(card: dict) -> tuple:
    name = card.get("name", "")
    return (
        card.get("id", ""),
        name,
        name.lower(),
        _combined_oracle_text(card),
        _combined_type_line(card),
        _combined_mana_cost(card),
        card.get("cmc", 0.0),
        json.dumps(card.get("colors", [])),
        json.dumps(card.get("color_identity", [])),
        json.dumps(card.get("keywords", [])),
        card.get("power"),
        card.get("toughness"),
        card.get("rarity", ""),
        card.get("set", ""),
        json.dumps(card.get("legalities", {})),
        json.dumps(card),
    )


def build_database(
    cards: Iterable[dict] | None = None,
    json_path: Path = CARDS_PATH,
    db_path: Path = DB_PATH,
) -> Path:
    """Load oracle card JSON into a fresh SQLite database at `db_path`.

    Pass `cards` directly to skip re-reading the JSON file (e.g. when the
    caller already loaded it via `bulk_data.load_cards`).
    """
    if cards is None:
        from .bulk_data import load_cards

        cards = load_cards(json_path)

    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(SCHEMA)
        conn.executemany(
            """
            INSERT INTO cards (
                id, name, name_lower, oracle_text, type_line, mana_cost, cmc,
                colors, color_identity, keywords, power, toughness, rarity,
                set_code, legalities, raw
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (_card_row(card) for card in cards),
        )
        conn.commit()
        populate_tags(conn)
    finally:
        conn.close()

    return db_path


def populate_tags(conn: sqlite3.Connection) -> None:
    """(Re)compute mechanical theme tags and creature types for every card.

    Safe to call on an already-populated DB — clears and rebuilds both
    derived tables from the current `cards` rows.
    """
    conn.execute("DELETE FROM card_tags")
    conn.execute("DELETE FROM card_creature_types")

    tag_rows: list[tuple[str, str]] = []
    type_rows: list[tuple[str, str]] = []
    for row in conn.execute("SELECT id, oracle_text, keywords, type_line FROM cards"):
        card_id = row["id"]
        card = {
            "oracle_text": row["oracle_text"],
            "keywords": row["keywords"],
        }
        for tag_id in tags_module.tag_card(card):
            tag_rows.append((card_id, tag_id))
        for creature_type in tags_module.extract_creature_types(row["type_line"]):
            type_rows.append((card_id, creature_type))

    conn.executemany("INSERT INTO card_tags (card_id, tag) VALUES (?, ?)", tag_rows)
    conn.executemany(
        "INSERT INTO card_creature_types (card_id, creature_type) VALUES (?, ?)", type_rows
    )
    conn.commit()


def get_tags_for_card(conn: sqlite3.Connection, card_id: str) -> set[str]:
    rows = conn.execute("SELECT tag FROM card_tags WHERE card_id = ?", (card_id,)).fetchall()
    return {row["tag"] for row in rows}


def get_creature_types_for_card(conn: sqlite3.Connection, card_id: str) -> set[str]:
    rows = conn.execute(
        "SELECT creature_type FROM card_creature_types WHERE card_id = ?", (card_id,)
    ).fetchall()
    return {row["creature_type"] for row in rows}


def connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    if not db_path.exists():
        raise FileNotFoundError(
            f"{db_path} does not exist yet. Run `synergy-finder update-data` first."
        )
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def get_card_by_name(conn: sqlite3.Connection, name: str) -> sqlite3.Row | None:
    """Exact (case-insensitive) name lookup, falling back to a prefix match."""
    row = conn.execute(
        "SELECT * FROM cards WHERE name_lower = ? LIMIT 1", (name.lower(),)
    ).fetchone()
    if row is not None:
        return row
    row = conn.execute(
        "SELECT * FROM cards WHERE name_lower LIKE ? ORDER BY length(name) ASC LIMIT 1",
        (f"{name.lower()}%",),
    ).fetchone()
    return row


def iter_all_cards(conn: sqlite3.Connection) -> Iterator[sqlite3.Row]:
    cursor = conn.execute("SELECT * FROM cards")
    yield from cursor
