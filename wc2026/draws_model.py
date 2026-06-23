"""Retrospective flat-stake draw strategy model."""

from __future__ import annotations

from datetime import date as date_type

from wc2026.api import get_prediction_json
from wc2026.data_loader import load_matches
from wc2026.odds_loader import DEFAULT_STAKE
from wc2026.results_loader import load_results


def _result_text(result: dict) -> str:
    return f"{result['home']}:{result['away']}"


def _is_draw(result: dict) -> bool:
    return int(result["home"]) == int(result["away"])


def calculate_draw_strategy(
    *,
    stake: float = DEFAULT_STAKE,
    to_date: str | None = None,
) -> dict:
    """Calculate P/L if betting a fixed stake on draw in every finished match."""
    today = to_date or date_type.today().isoformat()
    matches = sorted(load_matches(), key=lambda m: (m.date, m.match_id))
    if not matches:
        return {
            "rows": [],
            "stats": {
                "matches": 0,
                "settled": 0,
                "draws": 0,
                "losses": 0,
                "stake": round(stake, 2),
                "total_staked": 0,
                "total_return": 0,
                "profit": 0,
                "roi": None,
                "bank": 0,
                "from_date": "",
                "to_date": today,
            },
        }

    first_date = matches[0].date
    results = load_results()
    rows: list[dict] = []
    bank = 0.0

    for match in matches:
        if match.date < first_date or match.date > today:
            continue

        result = results.get(str(match.match_id))
        if not result or result.get("status") != "finished":
            continue

        prediction = get_prediction_json(match)
        draw_prob = float(prediction["outcome_1x2"]["draw"]["prob"])
        draw_odds = float(prediction["odds"]["1x2"]["draw"])
        won = _is_draw(result)
        payout = round(stake * draw_odds, 2) if won else 0.0
        profit = round(stake * (draw_odds - 1.0), 2) if won else -round(stake, 2)
        bank = round(bank + profit, 2)

        rows.append(
            {
                "row_num": len(rows) + 1,
                "match_id": match.match_id,
                "match_date": match.date,
                "home_name": match.home.name,
                "away_name": match.away.name,
                "result_score": _result_text(result),
                "selection": "draw",
                "selection_label": "Ничья",
                "model_prob": round(draw_prob, 4),
                "odds": round(draw_odds, 2),
                "stake": round(stake, 2),
                "payout": payout,
                "profit": profit,
                "bank": bank,
                "status": "won" if won else "lost",
            }
        )

    wins = sum(1 for row in rows if row["status"] == "won")
    losses = len(rows) - wins
    total_staked = round(len(rows) * stake, 2)
    total_return = round(sum(row["payout"] for row in rows), 2)
    profit = round(sum(row["profit"] for row in rows), 2)
    roi = round(profit / total_staked * 100, 1) if total_staked else None

    return {
        "rows": rows,
        "stats": {
            "matches": len(rows),
            "settled": len(rows),
            "draws": wins,
            "losses": losses,
            "stake": round(stake, 2),
            "total_staked": total_staked,
            "total_return": total_return,
            "profit": profit,
            "roi": roi,
            "bank": profit,
            "from_date": first_date,
            "to_date": today,
        },
    }
