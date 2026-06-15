"""View data builders for the high-odds longshot section."""

from __future__ import annotations

from wc2026.bets_store import _evaluate_bet
from wc2026.longshot_store import list_forecasts, refresh_longshot_forecasts
from wc2026.results_loader import load_results


def ensure_longshot_forecasts() -> None:
    refresh_longshot_forecasts()


def _is_finished(match_id: int, results: dict) -> bool:
    entry = results.get(str(match_id))
    return bool(entry and entry.get("status") == "finished")


def _forecast_public(row: dict, results: dict) -> dict:
    snap = row["snapshot"]
    return {
        "match_id": row["match_id"],
        "match_date": row["match_date"],
        "home_name": row["home_name"],
        "away_name": row["away_name"],
        "group": snap["group"],
        "venue": snap["venue"],
        "source": row["source"],
        "is_finished": _is_finished(row["match_id"], results),
        "model": snap["model"],
        "picks": snap["picks"],
        "top_pick": snap["top_pick"],
    }


def list_longshot_cards(
    date: str | None = None,
    include_finished: bool = False,
) -> dict:
    results = load_results()
    rows = list_forecasts(date=date)
    if not include_finished:
        rows = [row for row in rows if not _is_finished(row["match_id"], results)]

    cards = [_forecast_public(row, results) for row in rows if row["snapshot"].get("picks")]
    scores = [card["top_pick"]["score"] for card in cards if card["top_pick"]]
    odds = [card["top_pick"]["odds"] for card in cards if card["top_pick"]]
    stats = {
        "total": sum(len(card["picks"]) for card in cards),
        "matches": len(cards),
        "avg_score": round(sum(scores) / len(scores), 2) if scores else None,
        "avg_odds": round(sum(odds) / len(odds), 2) if odds else None,
        "date": date or "",
        "finished_hidden": sum(
            1 for row in list_forecasts(date=date) if _is_finished(row["match_id"], results)
        )
        if not include_finished
        else 0,
    }
    return {"cards": cards, "stats": stats}


def _result_text(result: dict) -> str:
    return f"{result['home']}:{result['away']}"


def _evaluate_longshot_pick(pick: dict, result: dict) -> bool:
    if pick["market"] != "handicap":
        return _evaluate_bet(
            {"market": pick["market"], "selection": pick["selection"]},
            result,
        )

    side, line_raw = pick["selection"].split("_", 1)
    line = float(line_raw)
    home = int(result["home"])
    away = int(result["away"])
    if side == "home":
        return home + line > away
    return away + line > home


def longshot_retrospective() -> dict:
    results = load_results()
    groups: list[dict] = []
    finished_matches = 0
    skipped_matches = 0

    for row in list_forecasts():
        result = results.get(str(row["match_id"]))
        if not result or result.get("status") != "finished":
            continue
        finished_matches += 1

        picks = []
        for pick in row["snapshot"].get("picks", []):
            won = _evaluate_longshot_pick(pick, result)
            picks.append({**pick, "outcome": "won" if won else "lost"})

        if not picks:
            skipped_matches += 1
            continue

        groups.append(
            {
                "match_id": row["match_id"],
                "match_date": row["match_date"],
                "home_name": row["home_name"],
                "away_name": row["away_name"],
                "result_score": _result_text(result),
                "picks": picks,
            }
        )

    groups.sort(key=lambda item: (item["match_date"], item["match_id"]), reverse=True)
    wins = sum(1 for group in groups for pick in group["picks"] if pick["outcome"] == "won")
    losses = sum(1 for group in groups for pick in group["picks"] if pick["outcome"] == "lost")
    total = wins + losses
    return {
        "groups": groups,
        "stats": {
            "matches": len(groups),
            "finished_matches": finished_matches,
            "skipped_matches": skipped_matches,
            "picks": total,
            "wins": wins,
            "losses": losses,
            "hit_rate": round(wins / total * 100, 1) if total else None,
        },
    }
