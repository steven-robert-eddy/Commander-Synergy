import json
from pathlib import Path

import pytest

from synergy_finder import db, match

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample_cards.json"


def _load_fixture_cards():
    with open(FIXTURE_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture
def conn(tmp_path):
    cards = _load_fixture_cards()
    db_path = tmp_path / "cards.db"
    db.build_database(cards=cards, db_path=db_path)
    connection = db.connect(db_path=db_path)
    yield connection
    connection.close()


def test_find_synergies_ranks_by_weighted_overlap(conn):
    results = match.find_synergies(conn, "Korvold, Fae-Cursed King")
    names = [m.name for m in results]

    # Fable shares 3 tags with Korvold (etb_triggers, card_draw, keyword_combat);
    # Ashnod's Altar and Hardened Scales each share exactly 1 tag with Korvold.
    assert names[0] == "Fable of the Mirror-Breaker // Reflection of Kiki-Jiki"
    assert set(names[1:]) == {"Ashnod's Altar", "Hardened Scales"}

    fable_match = results[0]
    assert set(fable_match.matched_tags) == {"etb_triggers", "card_draw", "keyword_combat"}
    assert fable_match.score == pytest.approx(0.9 + 0.8 + 0.7)


def test_find_synergies_excludes_source_card(conn):
    results = match.find_synergies(conn, "Korvold, Fae-Cursed King")
    assert "Korvold, Fae-Cursed King" not in [m.name for m in results]


def test_find_synergies_respects_top_n(conn):
    results = match.find_synergies(conn, "Korvold, Fae-Cursed King", top_n=1)
    assert len(results) == 1
    assert results[0].name == "Fable of the Mirror-Breaker // Reflection of Kiki-Jiki"


def test_find_synergies_unknown_card_raises(conn):
    with pytest.raises(match.CardNotFoundError):
        match.find_synergies(conn, "Not A Real Card Name")


def test_find_synergies_same_color_identity_filter(conn):
    # Korvold is B/G/R. Hardened Scales is mono-G (fits), Ashnod's Altar is
    # colorless (fits), so the color-identity filter shouldn't drop anyone
    # in this fixture, but it exercises the code path end-to-end.
    results = match.find_synergies(
        conn, "Korvold, Fae-Cursed King", same_color_identity_only=True
    )
    assert len(results) == 3


def test_explain_mentions_tag_labels(conn):
    results = match.find_synergies(conn, "Korvold, Fae-Cursed King", top_n=1)
    explanation = results[0].explain()
    assert "ETB Triggers" in explanation
    assert "Card Draw Engine" in explanation


def test_find_synergies_no_tags_returns_empty(conn):
    # Insert a card with no oracle text at all (e.g. a vanilla creature) —
    # nothing to compare on, so it should get no matches rather than error.
    conn.execute(
        """INSERT INTO cards (id, name, name_lower, oracle_text, type_line, mana_cost, cmc,
                               colors, color_identity, keywords, rarity, set_code, legalities, raw)
           VALUES ('vanilla-id', 'Plain Bear', 'plain bear', '', 'Creature — Bear', '{2}{G}', 3.0,
                   '["G"]', '["G"]', '[]', 'common', 'tst', '{}', '{}')"""
    )
    conn.commit()
    results = match.find_synergies(conn, "Plain Bear")
    assert results == []
