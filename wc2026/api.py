"""JSON API helpers for web and external consumers."""

from __future__ import annotations

from wc2026.models import Match, MatchPrediction, ensemble_1x2, predict_match
from wc2026.odds_loader import enrich_prediction_with_odds


def team_to_dict(team) -> dict:
    return {
        "code": team.code,
        "name": team.name,
        "fifa_points": round(team.fifa_points, 2),
        "rank": team.rank,
        "host": team.host,
    }


def match_to_dict(match: Match) -> dict:
    return {
        "id": match.match_id,
        "date": match.date,
        "group": match.group,
        "venue": match.venue,
        "home": team_to_dict(match.home),
        "away": team_to_dict(match.away),
        "label": f"{match.home.name} — {match.away.name}",
    }


def prediction_to_dict(pred: MatchPrediction) -> dict:
    m = pred.match
    eh, ed, ea = ensemble_1x2(
        pred.prob_home_win,
        pred.prob_draw,
        pred.prob_away_win,
        m.home,
        m.away,
    )

    best_outcome = max(
        [("home", eh, m.home.code), ("draw", ed, "X"), ("away", ea, m.away.code)],
        key=lambda x: x[1],
    )

    best_total = max(
        [
            ("over_2_5", pred.totals["over_2.5"]),
            ("under_2_5", pred.totals["under_2.5"]),
        ],
        key=lambda x: x[1],
    )

    best_oz = "yes" if pred.oz["yes"] >= pred.oz["no"] else "no"
    top_score = pred.top_scores[0] if pred.top_scores else (0, 0, 0.0)

    return {
        "match": match_to_dict(m),
        "model": {
            "lambda_home": round(pred.lambda_home, 3),
            "lambda_away": round(pred.lambda_away, 3),
            "expected_total": round(pred.expected_total, 2),
        },
        "outcome_1x2": {
            "home": {"code": m.home.code, "prob": round(eh, 4)},
            "draw": {"prob": round(ed, 4)},
            "away": {"code": m.away.code, "prob": round(ea, 4)},
            "most_likely": best_outcome[0],
        },
        "totals": {
            "over_1_5": round(pred.totals["over_1.5"], 4),
            "under_1_5": round(pred.totals["under_1.5"], 4),
            "over_2_5": round(pred.totals["over_2.5"], 4),
            "under_2_5": round(pred.totals["under_2.5"], 4),
            "over_3_5": round(pred.totals["over_3.5"], 4),
            "under_3_5": round(pred.totals["under_3.5"], 4),
            "most_likely": best_total[0],
        },
        "oz": {
            "yes": round(pred.oz["yes"], 4),
            "no": round(pred.oz["no"], 4),
            "most_likely": best_oz,
        },
        "top_scores": [
            {"home": h, "away": a, "prob": round(p, 4)} for h, a, p in pred.top_scores
        ],
        "suggested": {
            "outcome": best_outcome[0],
            "outcome_label": best_outcome[2],
            "score_home": top_score[0],
            "score_away": top_score[1],
            "total": best_total[0].replace("_", "."),
            "oz": best_oz,
        },
    }


def prediction_to_dict_full(match) -> dict:
    """Полный прогноз включая нишевые рынки (карточки)."""
    from wc2026.cards_model import predict_cards

    pred = prediction_to_dict(predict_match(match))
    pred["cards"] = predict_cards(match.home, match.away)
    return pred


def get_prediction_json(match: Match) -> dict:
    pred = prediction_to_dict_full(match)
    return enrich_prediction_with_odds(pred)
