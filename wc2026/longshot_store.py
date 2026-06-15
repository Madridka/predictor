"""Separate SQLite storage for longshot forecasts."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from wc2026.data_loader import load_matches
from wc2026.longshot_model import longshot_forecast, longshot_to_dict

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "longshot_predictions.db"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@contextmanager
def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_longshot_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS longshot_forecasts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_id INTEGER NOT NULL UNIQUE,
                match_date TEXT NOT NULL,
                home_code TEXT NOT NULL,
                away_code TEXT NOT NULL,
                home_name TEXT NOT NULL,
                away_name TEXT NOT NULL,
                source TEXT NOT NULL,
                top_market TEXT,
                top_selection TEXT,
                top_label TEXT,
                top_prob REAL,
                top_odds REAL,
                top_score REAL,
                snapshot_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_longshot_forecasts_date ON longshot_forecasts(match_date)"
        )
        conn.commit()


def upsert_forecast(snapshot: dict) -> dict:
    now = _utc_now()
    top = snapshot.get("top_pick")
    payload = json.dumps(snapshot, ensure_ascii=False, sort_keys=True)
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO longshot_forecasts (
                match_id, match_date, home_code, away_code, home_name, away_name,
                source, top_market, top_selection, top_label, top_prob, top_odds,
                top_score, snapshot_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(match_id) DO UPDATE SET
                match_date = excluded.match_date,
                home_code = excluded.home_code,
                away_code = excluded.away_code,
                home_name = excluded.home_name,
                away_name = excluded.away_name,
                source = excluded.source,
                top_market = excluded.top_market,
                top_selection = excluded.top_selection,
                top_label = excluded.top_label,
                top_prob = excluded.top_prob,
                top_odds = excluded.top_odds,
                top_score = excluded.top_score,
                snapshot_json = excluded.snapshot_json,
                updated_at = excluded.updated_at
            """,
            (
                snapshot["match_id"],
                snapshot["match_date"],
                snapshot["home_code"],
                snapshot["away_code"],
                snapshot["home_name"],
                snapshot["away_name"],
                snapshot["source"],
                top["market"] if top else None,
                top["selection"] if top else None,
                top["selection_label"] if top else None,
                float(top["model_prob"]) if top else None,
                float(top["odds"]) if top else None,
                float(top["score"]) if top else None,
                payload,
                now,
                now,
            ),
        )
        conn.commit()
    return get_forecast(snapshot["match_id"])  # type: ignore[return-value]


def refresh_longshot_forecasts() -> list[dict]:
    init_longshot_db()
    rows = []
    for match in load_matches():
        snapshot = longshot_to_dict(longshot_forecast(match))
        rows.append(upsert_forecast(snapshot))
    return rows


def _row_to_dict(row: sqlite3.Row) -> dict:
    data = dict(row)
    data["snapshot"] = json.loads(data.pop("snapshot_json"))
    return data


def get_forecast(match_id: int) -> dict | None:
    init_longshot_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM longshot_forecasts WHERE match_id = ?",
            (match_id,),
        ).fetchone()
    return _row_to_dict(row) if row else None


def list_forecasts(date: str | None = None) -> list[dict]:
    init_longshot_db()
    with _connect() as conn:
        if date:
            rows = conn.execute(
                "SELECT * FROM longshot_forecasts WHERE match_date = ? ORDER BY match_id ASC",
                (date,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM longshot_forecasts ORDER BY match_date ASC, match_id ASC"
            ).fetchall()
    return [_row_to_dict(row) for row in rows]
