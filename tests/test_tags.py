import json
from pathlib import Path

from synergy_finder import tags

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample_cards.json"


def _fixture_by_name(name: str) -> dict:
    with open(FIXTURE_PATH, "r", encoding="utf-8") as fh:
        cards = json.load(fh)
    for card in cards:
        if card["name"] == name:
            return card
    raise KeyError(name)


def test_korvold_tags():
    korvold = _fixture_by_name("Korvold, Fae-Cursed King")
    matched = tags.tag_card(korvold)

    assert "plus1_plus1_counters" in matched
    assert "sacrifice_synergy" in matched
    assert "etb_triggers" in matched
    assert "card_draw" in matched
    assert "keyword_combat" in matched  # Flying/Trample keywords
    assert "lifegain" not in matched


def test_ashnods_altar_tags():
    altar = _fixture_by_name("Ashnod's Altar")
    matched = tags.tag_card(altar)

    assert "sacrifice_synergy" in matched
    assert "ramp" in matched
    assert "plus1_plus1_counters" not in matched


def test_fable_tags_combine_both_faces():
    fable = _fixture_by_name("Fable of the Mirror-Breaker // Reflection of Kiki-Jiki")
    # Simulate the flattened oracle text db.py would produce for a DFC.
    faces_text = "\n//\n".join(f["oracle_text"] for f in fable["card_faces"])
    matched = tags.tag_card({"oracle_text": faces_text, "keywords": fable["keywords"]})

    assert "tokens" in matched
    assert "etb_triggers" in matched
    assert "card_draw" in matched  # "discard a card, then draw a card"


def test_hardened_scales_tags():
    scales = _fixture_by_name("Hardened Scales")
    matched = tags.tag_card(scales)

    assert matched == {"plus1_plus1_counters"}


def test_extract_creature_types_single_face():
    korvold = _fixture_by_name("Korvold, Fae-Cursed King")
    assert tags.extract_creature_types(korvold["type_line"]) == {"Dragon", "Noble"}


def test_extract_creature_types_double_faced():
    fable = _fixture_by_name("Fable of the Mirror-Breaker // Reflection of Kiki-Jiki")
    assert tags.extract_creature_types(fable["type_line"]) == {"Goblin", "Shaman"}


def test_extract_creature_types_noncreature():
    altar = _fixture_by_name("Ashnod's Altar")
    assert tags.extract_creature_types(altar["type_line"]) == set()


def test_tag_card_accepts_json_encoded_keywords():
    card = {"oracle_text": "", "keywords": json.dumps(["Flying"])}
    assert "keyword_combat" in tags.tag_card(card)


def test_unknown_tag_helpers_fall_back_gracefully():
    assert tags.tag_label("not_a_real_tag") == "not_a_real_tag"
    assert tags.tag_weight("not_a_real_tag") == 1.0
