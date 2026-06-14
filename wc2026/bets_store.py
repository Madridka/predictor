"""Bet slip storage with P/L tracking."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from wc2026.odds_loader import DEFAULT_STAKE
from wc2026.results_loader import load_results

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "predictions.db"

VALID_MARKETS = ("1x2", "total", "oz", "cards", "red_card", "both_yellow")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _migrate_columns(conn: sqlite3.Connection) -> None:
    cols = {row[1] for row in conn.execute("PRAGMA table_info(bets)")}
    if "guess_home" not in cols:
        conn.execute("ALTER TABLE bets ADD COLUMN guess_home INTEGER")
        conn.execute("ALTER TABLE bets ADD COLUMN guess_away INTEGER")
    if "guess_note" not in cols:
        conn.execute("ALTER TABLE bets ADD COLUMN guess_note TEXT")


def _migrate_markets(conn: sqlite3.Connection) -> None:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='bets'"
    ).fetchone()
    ddl = row[0] if row else ""
    if "red_card" in ddl:
        return

    conn.execute(
        """
        CREATE TABLE bets_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            match_id INTEGER NOT NULL,
            match_date TEXT NOT NULL,
            home_code TEXT NOT NULL,
            away_code TEXT NOT NULL,
            home_name TEXT NOT NULL,
            away_name TEXT NOT NULL,
            market TEXT NOT NULL CHECK(market IN (
                '1x2', 'total', 'oz', 'cards', 'red_card', 'both_yellow'
            )),
            selection TEXT NOT NULL,
            selection_label TEXT NOT NULL,
            model_prob REAL NOT NULL,
            odds REAL NOT NULL,
            stake REAL NOT NULL DEFAULT 500,
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK(status IN ('pending', 'won', 'lost')),
            profit REAL,
            guess_home INTEGER,
            guess_away INTEGER,
            guess_note TEXT,
            actual_home INTEGER,
            actual_away INTEGER,
            created_at TEXT NOT NULL,
            resolved_at TEXT
        )
        """
    )
    conn.execute(
        """
        INSERT INTO bets_new (
            id, match_id, match_date, home_code, away_code, home_name, away_name,
            market, selection, selection_label, model_prob, odds, stake, status,
            profit, guess_home, guess_away, guess_note, actual_home, actual_away,
            created_at, resolved_at
        )
        SELECT
            id, match_id, match_date, home_code, away_code, home_name, away_name,
            market, selection, selection_label, model_prob, odds, stake, status,
            profit, guess_home, guess_away, NULL, actual_home, actual_away,
            created_at, resolved_at
        FROM bets
        """
    )
    conn.execute("DROP TABLE bets")
    conn.execute("ALTER TABLE bets_new RENAME TO bets")


def _migrate_btts_to_oz(conn: sqlite3.Connection) -> None:
    conn.execute("UPDATE bets SET market = 'oz' WHERE market = 'btts'")
    conn.execute(
        "UPDATE bets SET selection_label = REPLACE(selection_label, 'BTTS:', 'ОЗ:') "
        "WHERE selection_label LIKE 'BTTS:%'"
    )
    conn.execute("UPDATE archive_picks SET market = 'oz' WHERE market = 'btts'")

    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='bets'"
    ).fetchone()
    ddl = row[0] if row else ""
    if "'btts'" not in ddl:
        return

    conn.execute(
        """
        CREATE TABLE bets_oz (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            match_id INTEGER NOT NULL,
            match_date TEXT NOT NULL,
            home_code TEXT NOT NULL,
            away_code TEXT NOT NULL,
            home_name TEXT NOT NULL,
            away_name TEXT NOT NULL,
            market TEXT NOT NULL CHECK(market IN (
                '1x2', 'total', 'oz', 'cards', 'red_card', 'both_yellow'
            )),
            selection TEXT NOT NULL,
            selection_label TEXT NOT NULL,
            model_prob REAL NOT NULL,
            odds REAL NOT NULL,
            stake REAL NOT NULL DEFAULT 500,
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK(status IN ('pending', 'won', 'lost')),
            profit REAL,
            guess_home INTEGER,
            guess_away INTEGER,
            guess_note TEXT,
            actual_home INTEGER,
            actual_away INTEGER,
            created_at TEXT NOT NULL,
            resolved_at TEXT
        )
        """
    )
    conn.execute(
        """
        INSERT INTO bets_oz (
            id, match_id, match_date, home_code, away_code, home_name, away_name,
            market, selection, selection_label, model_prob, odds, stake, status,
            profit, guess_home, guess_away, guess_note, actual_home, actual_away,
            created_at, resolved_at
        )
        SELECT
            id, match_id, match_date, home_code, away_code, home_name, away_name,
            market, selection, selection_label, model_prob, odds, stake, status,
            profit, guess_home, guess_away, guess_note, actual_home, actual_away,
            created_at, resolved_at
        FROM bets
        """
    )
    conn.execute("DROP TABLE bets")
    conn.execute("ALTER TABLE bets_oz RENAME TO bets")


def _migrate_is_risky(conn: sqlite3.Connection) -> None:
    cols = {row[1] for row in conn.execute("PRAGMA table_info(bets)")}
    if "is_risky" not in cols:
        conn.execute(
            "ALTER TABLE bets ADD COLUMN is_risky INTEGER NOT NULL DEFAULT 0"
        )


def init_bets_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_id INTEGER NOT NULL,
                match_date TEXT NOT NULL,
                home_code TEXT NOT NULL,
                away_code TEXT NOT NULL,
                home_name TEXT NOT NULL,
                away_name TEXT NOT NULL,
                market TEXT NOT NULL CHECK(market IN ('1x2', 'total', 'btts')),
                selection TEXT NOT NULL,
                selection_label TEXT NOT NULL,
                model_prob REAL NOT NULL,
                odds REAL NOT NULL,
                stake REAL NOT NULL DEFAULT 500,
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK(status IN ('pending', 'won', 'lost')),
                profit REAL,
                guess_home INTEGER,
                guess_away INTEGER,
                actual_home INTEGER,
                actual_away INTEGER,
                created_at TEXT NOT NULL,
                resolved_at TEXT
            )
            """
        )
        _migrate_columns(conn)
        _migrate_markets(conn)
        _migrate_btts_to_oz(conn)
        _migrate_is_risky(conn)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bets_match ON bets(match_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bets_status ON bets(status)")
        conn.commit()


@contextmanager
def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def _actual_outcome(home: int, away: int) -> str:
    if home > away:
        return "home"
    if home < away:
        return "away"
    return "draw"


def _evaluate_bet(row: dict, result: dict) -> bool:
    market = row["market"]
    sel = row["selection"]
    home = int(result["home"])
    away = int(result["away"])
    total = home + away

    if market == "1x2":
        return _actual_outcome(home, away) == sel

    if market == "total":
        threshold = float(sel.split("_")[1])
        is_over = total > threshold
        return (sel.startswith("over") and is_over) or (sel.startswith("under") and not is_over)

    if market in ("oz", "btts"):
        both = home > 0 and away > 0
        return (sel == "yes" and both) or (sel == "no" and not both)

    if market == "cards":
        yellows = result.get("yellows")
        if yellows is None:
            return False
        threshold = float(sel.split("_")[1])
        is_over = float(yellows) > threshold
        return (sel.startswith("over") and is_over) or (sel.startswith("under") and not is_over)

    if market == "red_card":
        reds = result.get("reds")
        if reds is None:
            return False
        has_red = int(reds) > 0
        return (sel == "yes" and has_red) or (sel == "no" and not has_red)

    if market == "both_yellow":
        yh = result.get("yellow_home")
        ya = result.get("yellow_away")
        if yh is None or ya is None:
            return False
        both = int(yh) > 0 and int(ya) > 0
        return (sel == "yes" and both) or (sel == "no" and not both)

    return False


def _can_evaluate(row: dict, result: dict) -> bool:
    market = row["market"]
    if market in ("1x2", "total", "oz", "btts"):
        return "home" in result and "away" in result
    if market == "cards":
        return result.get("yellows") is not None
    if market == "red_card":
        return result.get("reds") is not None
    if market == "both_yellow":
        return result.get("yellow_home") is not None and result.get("yellow_away") is not None
    return False


def _calc_profit(stake: float, odds: float, won: bool) -> float:
    if won:
        return round(stake * (odds - 1.0), 2)
    return round(-stake, 2)


def _apply_result(row: dict, result: dict) -> dict:
    won = _evaluate_bet(row, result)
    return {
        "status": "won" if won else "lost",
        "profit": _calc_profit(row["stake"], row["odds"], won),
        "actual_home": int(result["home"]),
        "actual_away": int(result["away"]),
        "resolved_at": _utc_now(),
    }


def sync_results_from_file() -> int:
    """Подтянуть реальные счета из data/results.json и пересчитать P/L."""
    results = load_results()
    if not results:
        return 0

    updated = 0
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM bets").fetchall()
        for row in rows:
            result = results.get(str(row["match_id"]))
            if not result or result.get("status") != "finished":
                continue
            if not _can_evaluate(dict(row), result):
                continue
            home, away = int(result["home"]), int(result["away"])
            data = dict(row)
            if (
                row["actual_home"] == home
                and row["actual_away"] == away
                and row["status"] != "pending"
            ):
                continue
            outcome = _apply_result(data, result)
            conn.execute(
                """
                UPDATE bets SET status = ?, profit = ?, actual_home = ?, actual_away = ?,
                                resolved_at = ?
                WHERE id = ?
                """,
                (
                    outcome["status"],
                    outcome["profit"],
                    outcome["actual_home"],
                    outcome["actual_away"],
                    outcome["resolved_at"],
                    row["id"],
                ),
            )
            updated += 1
        conn.commit()
    return updated


def update_guess(bet_id: int, guess_home: int | None, guess_away: int | None) -> dict | None:
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE bets SET guess_home = ?, guess_away = ? WHERE id = ?",
            (guess_home, guess_away, bet_id),
        )
        conn.commit()
        if cur.rowcount == 0:
            return None
    return get_bet(bet_id)


def create_bet(data: dict) -> dict:
    created_at = _utc_now()
    stake = float(data.get("stake", DEFAULT_STAKE))
    is_risky = int(data.get("is_risky", 0))
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO bets (
                match_id, match_date, home_code, away_code, home_name, away_name,
                market, selection, selection_label, model_prob, odds, stake,
                guess_home, guess_away, guess_note, is_risky, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["match_id"],
                data["match_date"],
                data["home_code"],
                data["away_code"],
                data["home_name"],
                data["away_name"],
                data["market"],
                data["selection"],
                data["selection_label"],
                float(data["model_prob"]),
                float(data["odds"]),
                stake,
                data.get("guess_home"),
                data.get("guess_away"),
                data.get("guess_note"),
                is_risky,
                created_at,
            ),
        )
        conn.commit()
        bet_id = cur.lastrowid
    return get_bet(bet_id)  # type: ignore[return-value]


def get_bet(bet_id: int) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM bets WHERE id = ?", (bet_id,)).fetchone()
    return _enrich_bet(dict(row)) if row else None


def _enrich_bet(d: dict) -> dict:
    """Добавить подсказку: есть ли результат в файле, но ещё не применён."""
    results = load_results()
    r = results.get(str(d["match_id"]))
    if r and r.get("status") == "finished":
        d["file_result"] = {
            "home": r["home"],
            "away": r["away"],
            "yellows": r.get("yellows"),
            "reds": r.get("reds"),
            "yellow_home": r.get("yellow_home"),
            "yellow_away": r.get("yellow_away"),
        }
    else:
        d["file_result"] = None
    return d


def list_bets(is_risky: bool | None = None) -> list[dict]:
    with _connect() as conn:
        if is_risky is None:
            rows = conn.execute("SELECT * FROM bets ORDER BY id ASC").fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM bets WHERE is_risky = ? ORDER BY id ASC",
                (int(is_risky),),
            ).fetchall()
    result = []
    for i, row in enumerate(rows):
        d = _enrich_bet(dict(row))
        d["row_num"] = i + 1
        result.append(d)
    return result


def delete_bet(bet_id: int) -> bool:
    with _connect() as conn:
        cur = conn.execute("DELETE FROM bets WHERE id = ?", (bet_id,))
        conn.commit()
        return cur.rowcount > 0


def get_bet_stats(is_risky: bool | None = None) -> dict:
    bets = list_bets(is_risky=is_risky)
    resolved = [b for b in bets if b["status"] != "pending"]
    pending = [b for b in bets if b["status"] == "pending"]

    total_staked = sum(b["stake"] for b in bets)
    total_profit = sum(b["profit"] or 0 for b in resolved)
    wins = sum(1 for b in resolved if b["status"] == "won")
    losses = sum(1 for b in resolved if b["status"] == "lost")

    roi = None
    staked_resolved = sum(b["stake"] for b in resolved)
    if staked_resolved > 0:
        roi = round(total_profit / staked_resolved * 100, 1)

    return {
        "total": len(bets),
        "pending": len(pending),
        "resolved": len(resolved),
        "wins": wins,
        "losses": losses,
        "total_staked": round(total_staked, 2),
        "total_profit": round(total_profit, 2),
        "roi": roi,
        "default_stake": DEFAULT_STAKE,
    }
