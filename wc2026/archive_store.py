"""Архив наиболее вероятных прогнозов модели."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "predictions.db"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def init_archive_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS archive_picks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_id INTEGER NOT NULL,
                match_date TEXT NOT NULL,
                home_name TEXT NOT NULL,
                away_name TEXT NOT NULL,
                market TEXT NOT NULL,
                selection TEXT NOT NULL,
                selection_label TEXT NOT NULL,
                model_prob REAL NOT NULL,
                odds REAL NOT NULL,
                guess_note TEXT,
                rank_in_match INTEGER,
                created_at TEXT NOT NULL,
                UNIQUE(match_id, market, selection)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_archive_date ON archive_picks(match_date)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_archive_prob ON archive_picks(model_prob DESC)"
        )
        _migrate_archive_columns(conn)
        conn.commit()


def _migrate_archive_columns(conn: sqlite3.Connection) -> None:
    cols = {row[1] for row in conn.execute("PRAGMA table_info(archive_picks)")}
    if "is_best_value" not in cols:
        conn.execute(
            "ALTER TABLE archive_picks ADD COLUMN is_best_value INTEGER NOT NULL DEFAULT 0"
        )


@contextmanager
def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def add_picks(picks: list[dict]) -> dict:
    """Добавить прогнозы; дубликаты (match+market+selection) пропускаются."""
    added = 0
    skipped = 0
    created_at = _utc_now()

    with _connect() as conn:
        for pick in picks:
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO archive_picks (
                    match_id, match_date, home_name, away_name,
                    market, selection, selection_label,
                    model_prob, odds, guess_note, rank_in_match,
                    is_best_value, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pick["match_id"],
                    pick["match_date"],
                    pick["home_name"],
                    pick["away_name"],
                    pick["market"],
                    pick["selection"],
                    pick["selection_label"],
                    float(pick["model_prob"]),
                    float(pick["odds"]),
                    pick.get("guess_note"),
                    pick.get("rank_in_match"),
                    int(pick.get("is_best_value", 0)),
                    created_at,
                ),
            )
            if cur.rowcount:
                added += 1
            else:
                skipped += 1
        conn.commit()

    return {"added": added, "skipped": skipped}


def get_archived_match_ids() -> set[int]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT DISTINCT match_id FROM archive_picks"
        ).fetchall()
    return {int(row[0]) for row in rows}


def cleanup_archive_below_odds(min_odds: float) -> int:
    with _connect() as conn:
        cur = conn.execute(
            """
            DELETE FROM archive_picks
            WHERE odds < ? AND COALESCE(is_best_value, 0) = 0
            """,
            (min_odds,),
        )
        conn.commit()
        return cur.rowcount


def upsert_best_value_pick(pick: dict | None, match_id: int) -> bool:
    """Обновить отметку «наиболее вероятный прогноз» для матча."""
    with _connect() as conn:
        conn.execute(
            "DELETE FROM archive_picks WHERE match_id = ? AND is_best_value = 1",
            (match_id,),
        )
        if not pick:
            conn.commit()
            return False

        existing = conn.execute(
            """
            SELECT id FROM archive_picks
            WHERE match_id = ? AND market = ? AND selection = ?
            """,
            (match_id, pick["market"], pick["selection"]),
        ).fetchone()

        if existing:
            conn.execute(
                """
                UPDATE archive_picks SET
                    is_best_value = 1,
                    model_prob = ?,
                    odds = ?,
                    guess_note = ?,
                    selection_label = ?
                WHERE id = ?
                """,
                (
                    float(pick["model_prob"]),
                    float(pick["odds"]),
                    pick.get("guess_note"),
                    pick["selection_label"],
                    existing[0],
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO archive_picks (
                    match_id, match_date, home_name, away_name,
                    market, selection, selection_label,
                    model_prob, odds, guess_note, rank_in_match,
                    is_best_value, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pick["match_id"],
                    pick["match_date"],
                    pick["home_name"],
                    pick["away_name"],
                    pick["market"],
                    pick["selection"],
                    pick["selection_label"],
                    float(pick["model_prob"]),
                    float(pick["odds"]),
                    pick.get("guess_note"),
                    pick.get("rank_in_match", 1),
                    1,
                    _utc_now(),
                ),
            )
        conn.commit()
    return True


def list_archive(
    min_odds: float | None = None,
    date: str | None = None,
) -> list[dict]:
    query = "SELECT * FROM archive_picks WHERE 1=1"
    params: list = []

    if min_odds is not None:
        query += " AND odds >= ?"
        params.append(min_odds)
    if date:
        query += " AND match_date = ?"
        params.append(date)

    query += " ORDER BY model_prob DESC, match_date ASC, match_id ASC"

    with _connect() as conn:
        rows = conn.execute(query, params).fetchall()

    result = []
    for i, row in enumerate(rows):
        d = dict(row)
        d["row_num"] = i + 1
        result.append(d)
    return result


def delete_pick(pick_id: int) -> bool:
    with _connect() as conn:
        cur = conn.execute("DELETE FROM archive_picks WHERE id = ?", (pick_id,))
        conn.commit()
        return cur.rowcount > 0


def clear_archive(date: str | None = None) -> int:
    with _connect() as conn:
        if date:
            cur = conn.execute(
                "DELETE FROM archive_picks WHERE match_date = ?", (date,)
            )
        else:
            cur = conn.execute("DELETE FROM archive_picks")
        conn.commit()
        return cur.rowcount


def get_archive_stats() -> dict:
    with _connect() as conn:
        total = conn.execute("SELECT COUNT(*) FROM archive_picks").fetchone()[0]
        avg_prob = conn.execute(
            "SELECT AVG(model_prob) FROM archive_picks"
        ).fetchone()[0]
        top = conn.execute(
            "SELECT MAX(model_prob) FROM archive_picks"
        ).fetchone()[0]
        dates = conn.execute(
            "SELECT COUNT(DISTINCT match_date) FROM archive_picks"
        ).fetchone()[0]

    return {
        "total": total,
        "avg_prob": round(avg_prob, 3) if avg_prob else None,
        "top_prob": round(top, 3) if top else None,
        "dates": dates,
        "default_min_odds": 1.65,
    }
