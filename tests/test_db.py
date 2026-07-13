import json
from pathlib import Path

from synergy_finder import db

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample_cards.json"


def _load_fixture_cards():
    with open(FIXTURE_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


def test_build_database_and_lookup(tmp_path):
    cards = _load_fixture_cards()
    db_path = tmp_path / "cards.db"

    db.build_database(cards=cards, db_path=db_path)
    conn = db.connect(db_path=db_path)
    try:
        rows = list(db.iter_all_cards(conn))
        assert len(rows) == len(cards)

        korvold = db.get_card_by_name(conn, "korvold, fae-cursed king")
        assert korvold is not None
        assert korvold["name"] == "Korvold, Fae-Cursed King"
        assert "+1/+1 counter" in korvold["oracle_text"]
        assert korvold["color_identity"] == '["B", "G", "R"]'
    finally:
        conn.close()


def test_split_card_combines_face_text(tmp_path):
    cards = _load_fixture_cards()
    db_path = tmp_path / "cards.db"
    db.build_database(cards=cards, db_path=db_path)

    conn = db.connect(db_path=db_path)
    try:
        fable = db.get_card_by_name(conn, "Fable of the Mirror-Breaker // Reflection of Kiki-Jiki")
        assert fable is not None
        assert "Goblin Shaman creature token" in fable["oracle_text"]
        assert "copy of another target" in fable["oracle_text"]
    finally:
        conn.close()


def test_build_database_populates_tags_and_creature_types(tmp_path):
    cards = _load_fixture_cards()
    db_path = tmp_path / "cards.db"
    db.build_database(cards=cards, db_path=db_path)

    conn = db.connect(db_path=db_path)
    try:
        korvold = db.get_card_by_name(conn, "Korvold, Fae-Cursed King")
        korvold_tags = db.get_tags_for_card(conn, korvold["id"])
        assert "plus1_plus1_counters" in korvold_tags
        assert "sacrifice_synergy" in korvold_tags

        korvold_types = db.get_creature_types_for_card(conn, korvold["id"])
        assert korvold_types == {"Dragon", "Noble"}

        total_tags = conn.execute("SELECT COUNT(*) FROM card_tags").fetchone()[0]
        assert total_tags > 0
    finally:
        conn.close()


def test_populate_tags_is_idempotent(tmp_path):
    cards = _load_fixture_cards()
    db_path = tmp_path / "cards.db"
    db.build_database(cards=cards, db_path=db_path)

    conn = db.connect(db_path=db_path)
    try:
        before = conn.execute("SELECT COUNT(*) FROM card_tags").fetchone()[0]
        db.populate_tags(conn)
        after = conn.execute("SELECT COUNT(*) FROM card_tags").fetchone()[0]
        assert before == after
    finally:
        conn.close()


def test_prefix_lookup(tmp_path):
    cards = _load_fixture_cards()
    db_path = tmp_path / "cards.db"
    db.build_database(cards=cards, db_path=db_path)

    conn = db.connect(db_path=db_path)
    try:
        row = db.get_card_by_name(conn, "hardened")
        assert row is not None
        assert row["name"] == "Hardened Scales"
    finally:
        conn.close()
