"""View data builders for the isolated market-implied forecast section."""

from __future__ import annotations

from wc2026.bets_store import _evaluate_bet
from wc2026.market_store import list_forecasts, refresh_market_forecasts
from wc2026.results_loader import load_results


def ensure_market_forecasts() -> None:
    refresh_market_forecasts()


def _is_finished(match_id: int, results: dict) -> bool:
    entry = results.get(str(match_id))
    return bool(entry and entry.get("status") == "finished")


def _forecast_public(row: dict, results: dict) -> dict:
    snap = row["snapshot"]
    top = snap["top_pick"]
    return {
        "match_id": row["match_id"],
        "match_date": row["match_date"],
        "home_name": row["home_name"],
        "away_name": row["away_name"],
        "group": snap["group"],
        "venue": snap["venue"],
        "source": row["source"],
        "is_finished": _is_finished(row["match_id"], results),
        "top_pick": top,
        "model": snap["model"],
        "outcome_1x2": snap["outcome_1x2"],
        "totals": snap["totals"],
        "oz": snap["oz"],
        "handicaps": snap["handicaps"],
    }


def list_market_forecast_cards(
    date: str | None = None,
    include_finished: bool = False,
) -> dict:
    results = load_results()
    rows = list_forecasts(date=date)
    if not include_finished:
        rows = [row for row in rows if not _is_finished(row["match_id"], results)]

    cards = [_forecast_public(row, results) for row in rows]
    ev_values = [card["top_pick"]["ev"] for card in cards]
    stats = {
        "total": len(cards),
        "matches": len({card["match_id"] for card in cards}),
        "avg_ev_pct": round(sum(ev_values) / len(ev_values) * 100, 1) if ev_values else None,
        "top_ev_pct": round(max(ev_values) * 100, 1) if ev_values else None,
        "date": date or "",
        "finished_hidden": sum(
            1 for row in list_forecasts(date=date) if _is_finished(row["match_id"], results)
        )
        if not include_finished
        else 0,
    }
    return {"cards": cards, "stats": stats}


def _result_text(result: dict) -> str:
    parts = [f"{result['home']}:{result['away']}"]
    if result.get("yellows") is not None:
        parts.append(f"{result['yellows']} ЖК")
    if result.get("reds") is not None:
        parts.append(f"{result['reds']} КК")
    return " · ".join(parts)


def _evaluate_market_pick(pick: dict, result: dict) -> bool:
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


def market_retrospective() -> dict:
    results = load_results()
    rows = list_forecasts()
    groups: list[dict] = []

    for row in rows:
        result = results.get(str(row["match_id"]))
        if not result or result.get("status") != "finished":
            continue

        snap = row["snapshot"]
        top = snap["top_pick"]
        won = _evaluate_market_pick(top, result)
        groups.append(
            {
                "match_id": row["match_id"],
                "match_date": row["match_date"],
                "home_name": row["home_name"],
                "away_name": row["away_name"],
                "result_score": _result_text(result),
                "top_pick": {
                    **top,
                    "outcome": "won" if won else "lost",
                },
                "expected_total": row["expected_total"],
                "snapshot": snap,
            }
        )

    groups.sort(key=lambda item: (item["match_date"], item["match_id"]), reverse=True)
    wins = sum(1 for group in groups if group["top_pick"]["outcome"] == "won")
    losses = sum(1 for group in groups if group["top_pick"]["outcome"] == "lost")
    total = wins + losses
    return {
        "groups": groups,
        "stats": {
            "matches": len(groups),
            "wins": wins,
            "losses": losses,
            "hit_rate": round(wins / total * 100, 1) if total else None,
            "avg_ev_pct": round(
                sum(group["top_pick"]["ev"] for group in groups) / len(groups) * 100,
                1,
            )
            if groups
            else None,
        },
    }
