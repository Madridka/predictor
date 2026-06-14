"""SQLite storage for user prediction journal."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "predictions.db"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_id INTEGER NOT NULL,
                match_date TEXT NOT NULL,
                home_code TEXT NOT NULL,
                away_code TEXT NOT NULL,
                home_name TEXT NOT NULL,
                away_name TEXT NOT NULL,
                outcome TEXT NOT NULL CHECK(outcome IN ('home', 'draw', 'away')),
                score_home INTEGER,
                score_away INTEGER,
                total_line TEXT CHECK(total_line IN ('over_1.5', 'under_1.5', 'over_2.5', 'under_2.5', 'over_3.5', 'under_3.5')),
                btts TEXT CHECK(btts IN ('yes', 'no')),
                notes TEXT,
                model_snapshot TEXT,
                created_at TEXT NOT NULL,
                actual_home INTEGER,
                actual_away INTEGER,
                resolved_at TEXT
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_predictions_match ON user_predictions(match_id)"
        )
        conn.commit()


@contextmanager
def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["resolved"] = d["actual_home"] is not None and d["actual_away"] is not None
    if d["resolved"]:
        d["accuracy"] = _evaluate_accuracy(d)
    return d


def _evaluate_accuracy(row: dict) -> dict:
    ah, aa = row["actual_home"], row["actual_away"]
    total_goals = ah + aa

    if ah > aa:
        actual_outcome = "home"
    elif ah < aa:
        actual_outcome = "away"
    else:
        actual_outcome = "draw"

    outcome_hit = row["outcome"] == actual_outcome

    score_hit = (
        row["score_home"] is not None
        and row["score_away"] is not None
        and row["score_home"] == ah
        and row["score_away"] == aa
    )

    total_hit = None
    if row["total_line"]:
        line = row["total_line"]
        threshold = float(line.split("_")[1])
        is_over = total_goals > threshold
        total_hit = (line.startswith("over") and is_over) or (line.startswith("under") and not is_over)

    btts_hit = None
    if row["btts"]:
        both_scored = ah > 0 and aa > 0
        btts_hit = (row["btts"] == "yes" and both_scored) or (row["btts"] == "no" and not both_scored)

    return {
        "outcome": outcome_hit,
        "exact_score": score_hit,
        "total": total_hit,
        "btts": btts_hit,
    }


def list_predictions() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM user_predictions ORDER BY match_date DESC, created_at DESC"
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_prediction(prediction_id: int) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM user_predictions WHERE id = ?", (prediction_id,)
        ).fetchone()
    return _row_to_dict(row) if row else None


def create_prediction(data: dict) -> dict:
    created_at = _utc_now()
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO user_predictions (
                match_id, match_date, home_code, away_code, home_name, away_name,
                outcome, score_home, score_away, total_line, btts, notes,
                model_snapshot, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["match_id"],
                data["match_date"],
                data["home_code"],
                data["away_code"],
                data["home_name"],
                data["away_name"],
                data["outcome"],
                data.get("score_home"),
                data.get("score_away"),
                data.get("total_line"),
                data.get("btts"),
                data.get("notes"),
                data.get("model_snapshot"),
                created_at,
            ),
        )
        conn.commit()
        pid = cur.lastrowid
    return get_prediction(pid)  # type: ignore[return-value]


def resolve_prediction(prediction_id: int, actual_home: int, actual_away: int) -> dict | None:
    resolved_at = _utc_now()
    with _connect() as conn:
        conn.execute(
            """
            UPDATE user_predictions
            SET actual_home = ?, actual_away = ?, resolved_at = ?
            WHERE id = ?
            """,
            (actual_home, actual_away, resolved_at, prediction_id),
        )
        conn.commit()
    return get_prediction(prediction_id)


def delete_prediction(prediction_id: int) -> bool:
    with _connect() as conn:
        cur = conn.execute("DELETE FROM user_predictions WHERE id = ?", (prediction_id,))
        conn.commit()
        return cur.rowcount > 0


def get_stats() -> dict:
    preds = list_predictions()
    resolved = [p for p in preds if p["resolved"]]
    if not resolved:
        return {
            "total": len(preds),
            "resolved": 0,
            "outcome_accuracy": None,
            "score_accuracy": None,
            "total_accuracy": None,
            "btts_accuracy": None,
        }

    def rate(key: str) -> float | None:
        hits = [p["accuracy"][key] for p in resolved if p["accuracy"].get(key) is not None]
        if not hits:
            return None
        return round(sum(1 for h in hits if h) / len(hits) * 100, 1)

    return {
        "total": len(preds),
        "resolved": len(resolved),
        "outcome_accuracy": rate("outcome"),
        "score_accuracy": rate("exact_score"),
        "total_accuracy": rate("total"),
        "btts_accuracy": rate("btts"),
    }
