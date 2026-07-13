import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from synergy_finder import db
from synergy_finder.web.app import app

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample_cards.json"


def _load_fixture_cards():
    with open(FIXTURE_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture
def client(tmp_path, monkeypatch):
    cards = _load_fixture_cards()
    db_path = tmp_path / "cards.db"
    db.build_database(cards=cards, db_path=db_path)

    original_connect = db.connect
    monkeypatch.setattr(db, "connect", lambda: original_connect(db_path=db_path))

    return TestClient(app)


def test_index_serves_html(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Commander Synergy Finder" in resp.text


def test_search_cards_returns_matches(client):
    resp = client.get("/api/cards/search", params={"q": "korv"})
    assert resp.status_code == 200
    assert "Korvold, Fae-Cursed King" in resp.json()["results"]


def test_search_cards_requires_query(client):
    resp = client.get("/api/cards/search")
    assert resp.status_code == 422


def test_synergy_returns_ranked_matches(client):
    resp = client.get("/api/synergy", params={"name": "Korvold, Fae-Cursed King"})
    assert resp.status_code == 200
    data = resp.json()

    assert data["source"]["name"] == "Korvold, Fae-Cursed King"
    names = [m["name"] for m in data["matches"]]
    assert names[0] == "Fable of the Mirror-Breaker // Reflection of Kiki-Jiki"
    assert data["matches"][0]["explanation"]


def test_synergy_respects_top_param(client):
    resp = client.get(
        "/api/synergy", params={"name": "Korvold, Fae-Cursed King", "top": 1}
    )
    assert resp.status_code == 200
    assert len(resp.json()["matches"]) == 1


def test_synergy_unknown_card_returns_404(client):
    resp = client.get("/api/synergy", params={"name": "Not A Real Card"})
    assert resp.status_code == 404


def test_synergy_same_color_identity_param(client):
    resp = client.get(
        "/api/synergy",
        params={"name": "Korvold, Fae-Cursed King", "same_color_identity": "true"},
    )
    assert resp.status_code == 200
