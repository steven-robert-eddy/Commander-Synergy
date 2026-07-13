"""FastAPI app: a small JSON API plus a static vanilla-JS frontend.

Run with `synergy-finder serve` (see cli.py) or directly:

    uvicorn synergy_finder.web.app:app --reload
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .. import db, match

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="Commander Synergy Finder")


def _get_conn() -> sqlite3.Connection:
    try:
        return db.connect()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/cards/search")
def search_cards(q: str = Query(..., min_length=1), limit: int = Query(10, ge=1, le=50)):
    conn = _get_conn()
    try:
        return {"results": db.search_card_names(conn, q, limit=limit)}
    finally:
        conn.close()


@app.get("/api/synergy")
def synergy(
    name: str = Query(..., min_length=1),
    top: int = Query(20, ge=1, le=100),
    same_color_identity: bool = Query(False),
):
    conn = _get_conn()
    try:
        source = db.get_card_by_name(conn, name)
        if source is None:
            raise HTTPException(status_code=404, detail=f"No card found matching {name!r}")
        matches = match.find_synergies(
            conn, name, top_n=top, same_color_identity_only=same_color_identity
        )
    finally:
        conn.close()

    return {
        "source": {"name": source["name"], "type_line": source["type_line"]},
        "matches": [
            {
                "name": m.name,
                "type_line": m.type_line,
                "score": m.score,
                "explanation": m.explain(),
                "matched_tags": list(m.matched_tags),
                "shared_creature_types": list(m.shared_creature_types),
            }
            for m in matches
        ],
    }


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")
