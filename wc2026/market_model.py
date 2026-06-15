"""Market-implied forecasting model independent from Dixon-Coles and Elo."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.optimize import brentq
from scipy.stats import poisson

from wc2026.models import Match
from wc2026.odds_loader import get_match_odds, odds_from_prob


TOTAL_KEYS = ("over_1.5", "under_1.5", "over_2.5", "under_2.5", "over_3.5", "under_3.5")
HANDICAP_LINES = (-1.5, -0.5, 0.5, 1.5)


@dataclass(frozen=True)
class MarketForecast:
    match: Match
    source: str
    home_prob: float
    draw_prob: float
    away_prob: float
    lambda_home: float
    lambda_away: float
    expected_total: float
    btts_yes: float
    btts_no: float
    totals: dict[str, float]
    handicaps: dict[str, float]
    top_pick: dict


def _normalize_inverse_odds(odds: dict[str, float], keys: tuple[str, ...]) -> dict[str, float]:
    inv = {key: 1.0 / float(odds[key]) for key in keys if odds.get(key)}
    total = sum(inv.values())
    if not inv or total <= 0:
        return {key: 1.0 / len(keys) for key in keys}
    return {key: inv.get(key, 0.0) / total for key in keys}


def _pair_probs(over_odds: float | None, under_odds: float | None, fallback_over: float) -> tuple[float, float]:
    if over_odds and under_odds:
        probs = _normalize_inverse_odds(
            {"over": float(over_odds), "under": float(under_odds)},
            ("over", "under"),
        )
        return probs["over"], probs["under"]
    fallback_over = min(0.96, max(0.04, fallback_over))
    return fallback_over, 1.0 - fallback_over


def _poisson_over_probability(expected_total: float, line: float) -> float:
    threshold = math.floor(line)
    return 1.0 - poisson.cdf(threshold, expected_total)


def _expected_total_from_over25(p_over25: float) -> float:
    p = min(0.94, max(0.06, p_over25))

    def objective(mu: float) -> float:
        return _poisson_over_probability(mu, 2.5) - p

    return float(brentq(objective, 0.2, 6.5))


def _goal_share(home_prob: float, away_prob: float) -> float:
    decisive = home_prob + away_prob
    if decisive <= 0:
        return 0.5
    share = home_prob / decisive
    return min(0.82, max(0.18, share))


def _score_matrix(lambda_home: float, lambda_away: float, max_goals: int = 8) -> np.ndarray:
    matrix = np.zeros((max_goals + 1, max_goals + 1))
    for h in range(max_goals + 1):
        for a in range(max_goals + 1):
            matrix[h, a] = poisson.pmf(h, lambda_home) * poisson.pmf(a, lambda_away)
    tail = 1.0 - matrix.sum()
    if tail > 1e-9:
        matrix[max_goals, max_goals] += tail
    matrix /= matrix.sum()
    return matrix


def _outcomes_from_matrix(matrix: np.ndarray) -> tuple[float, float, float]:
    n = matrix.shape[0]
    home = sum(matrix[h, a] for h in range(n) for a in range(n) if h > a)
    draw = sum(matrix[h, h] for h in range(n))
    away = sum(matrix[h, a] for h in range(n) for a in range(n) if h < a)
    return float(home), float(draw), float(away)


def _totals_from_matrix(matrix: np.ndarray) -> dict[str, float]:
    n = matrix.shape[0]

    def over(line: float) -> float:
        return float(sum(matrix[h, a] for h in range(n) for a in range(n) if h + a > line))

    return {
        "over_1.5": over(1.5),
        "under_1.5": 1.0 - over(1.5),
        "over_2.5": over(2.5),
        "under_2.5": 1.0 - over(2.5),
        "over_3.5": over(3.5),
        "under_3.5": 1.0 - over(3.5),
    }


def _btts_from_matrix(matrix: np.ndarray) -> tuple[float, float]:
    n = matrix.shape[0]
    yes = float(sum(matrix[h, a] for h in range(1, n) for a in range(1, n)))
    return yes, 1.0 - yes


def _handicaps_from_matrix(matrix: np.ndarray) -> dict[str, float]:
    n = matrix.shape[0]
    probs: dict[str, float] = {}
    for line in HANDICAP_LINES:
        label = f"{line:+.1f}"
        probs[f"home_{label}"] = float(
            sum(matrix[h, a] for h in range(n) for a in range(n) if h + line > a)
        )
        probs[f"away_{label}"] = float(
            sum(matrix[h, a] for h in range(n) for a in range(n) if a + line > h)
        )
    return probs


def _blend_market_and_goal_probs(
    market_probs: tuple[float, float, float],
    matrix_probs: tuple[float, float, float],
) -> tuple[float, float, float]:
    blended = tuple(0.72 * m + 0.28 * g for m, g in zip(market_probs, matrix_probs))
    total = sum(blended)
    return tuple(float(p / total) for p in blended)  # type: ignore[return-value]


def _top_pick(
    match: Match,
    probs_1x2: dict[str, float],
    totals: dict[str, float],
    btts: dict[str, float],
    handicaps: dict[str, float],
    odds: dict,
) -> dict:
    candidates: list[dict] = []

    labels_1x2 = {
        "home": f"П1 {match.home.name}",
        "draw": "X - ничья",
        "away": f"П2 {match.away.name}",
    }
    for key in ("home", "draw", "away"):
        odd = float(odds.get("1x2", {}).get(key) or odds_from_prob(probs_1x2[key]))
        candidates.append(
            {
                "market": "1x2",
                "selection": key,
                "selection_label": labels_1x2[key],
                "prob": probs_1x2[key],
                "odds": odd,
            }
        )

    total_odds = odds.get("total", {})
    total_labels = {
        "over_1.5": "Больше 1.5",
        "under_1.5": "Меньше 1.5",
        "over_2.5": "Больше 2.5",
        "under_2.5": "Меньше 2.5",
        "over_3.5": "Больше 3.5",
        "under_3.5": "Меньше 3.5",
    }
    for key in TOTAL_KEYS:
        odd = float(total_odds.get(key) or odds_from_prob(totals[key]))
        candidates.append(
            {
                "market": "total",
                "selection": key,
                "selection_label": total_labels[key],
                "prob": totals[key],
                "odds": odd,
            }
        )

    oz_odds = odds.get("oz", odds.get("btts", {}))
    for key, label in (("yes", "ОЗ: Да"), ("no", "ОЗ: Нет")):
        odd = float(oz_odds.get(key) or odds_from_prob(btts[key]))
        candidates.append(
            {
                "market": "oz",
                "selection": key,
                "selection_label": label,
                "prob": btts[key],
                "odds": odd,
            }
        )

    handicap_odds = odds.get("handicap", {})
    for key, prob in handicaps.items():
        side, line = key.split("_", 1)
        label = f"{'Ф1' if side == 'home' else 'Ф2'} ({line})"
        odd = float(handicap_odds.get(key) or odds_from_prob(prob))
        candidates.append(
            {
                "market": "handicap",
                "selection": key,
                "selection_label": label,
                "prob": prob,
                "odds": odd,
            }
        )

    for item in candidates:
        item["edge"] = item["prob"] - 1.0 / item["odds"]
        item["ev"] = item["prob"] * item["odds"] - 1.0

    short = [c for c in candidates if 1.45 <= c["odds"] <= 4.75]
    pool = short or candidates
    best = max(pool, key=lambda c: (c["ev"], c["prob"], -c["odds"]))
    return {
        "market": best["market"],
        "selection": best["selection"],
        "selection_label": best["selection_label"],
        "prob": round(float(best["prob"]), 4),
        "odds": round(float(best["odds"]), 2),
        "edge": round(float(best["edge"]), 4),
        "ev": round(float(best["ev"]), 4),
        "ev_pct": round(float(best["ev"]) * 100, 1),
    }


def forecast_match_market(match: Match) -> MarketForecast:
    """Build a market-consensus forecast from bookmaker prices only."""
    odds = get_match_odds(match.match_id)
    odds_1x2 = odds.get("1x2", {})
    if odds_1x2:
        market_1x2 = _normalize_inverse_odds(odds_1x2, ("home", "draw", "away"))
        source = "bookmaker-lines"
    else:
        market_1x2 = {"home": 0.38, "draw": 0.27, "away": 0.35}
        source = "synthetic-market"

    total_odds = odds.get("total", {})
    over25, under25 = _pair_probs(
        total_odds.get("over_2.5"),
        total_odds.get("under_2.5"),
        fallback_over=0.51,
    )
    expected_total = _expected_total_from_over25(over25)

    share = _goal_share(market_1x2["home"], market_1x2["away"])
    lambda_home = expected_total * share
    lambda_away = expected_total - lambda_home
    matrix = _score_matrix(lambda_home, lambda_away)
    matrix_1x2 = _outcomes_from_matrix(matrix)
    home_prob, draw_prob, away_prob = _blend_market_and_goal_probs(
        (market_1x2["home"], market_1x2["draw"], market_1x2["away"]),
        matrix_1x2,
    )

    matrix_totals = _totals_from_matrix(matrix)
    totals = dict(matrix_totals)
    for line in ("1.5", "2.5", "3.5"):
        over_key = f"over_{line}"
        under_key = f"under_{line}"
        market_over, market_under = _pair_probs(
            total_odds.get(over_key),
            total_odds.get(under_key),
            fallback_over=matrix_totals[over_key],
        )
        totals[over_key] = 0.68 * market_over + 0.32 * matrix_totals[over_key]
        totals[under_key] = 0.68 * market_under + 0.32 * matrix_totals[under_key]

    matrix_btts_yes, matrix_btts_no = _btts_from_matrix(matrix)
    handicaps = _handicaps_from_matrix(matrix)
    oz_odds = odds.get("oz", odds.get("btts", {}))
    market_btts_yes, market_btts_no = _pair_probs(
        oz_odds.get("yes"),
        oz_odds.get("no"),
        fallback_over=matrix_btts_yes,
    )
    btts_yes = 0.66 * market_btts_yes + 0.34 * matrix_btts_yes
    btts_no = 0.66 * market_btts_no + 0.34 * matrix_btts_no

    probs_1x2 = {"home": home_prob, "draw": draw_prob, "away": away_prob}
    btts = {"yes": btts_yes, "no": btts_no}

    return MarketForecast(
        match=match,
        source=source,
        home_prob=home_prob,
        draw_prob=draw_prob,
        away_prob=away_prob,
        lambda_home=lambda_home,
        lambda_away=lambda_away,
        expected_total=expected_total,
        btts_yes=btts_yes,
        btts_no=btts_no,
        totals=totals,
        handicaps=handicaps,
        top_pick=_top_pick(match, probs_1x2, totals, btts, handicaps, odds),
    )


def forecast_to_dict(forecast: MarketForecast) -> dict:
    match = forecast.match
    return {
        "match_id": match.match_id,
        "match_date": match.date,
        "group": match.group,
        "venue": match.venue,
        "home_code": match.home.code,
        "away_code": match.away.code,
        "home_name": match.home.name,
        "away_name": match.away.name,
        "source": forecast.source,
        "model": {
            "lambda_home": round(forecast.lambda_home, 3),
            "lambda_away": round(forecast.lambda_away, 3),
            "expected_total": round(forecast.expected_total, 2),
        },
        "outcome_1x2": {
            "home": round(forecast.home_prob, 4),
            "draw": round(forecast.draw_prob, 4),
            "away": round(forecast.away_prob, 4),
            "most_likely": max(
                (("home", forecast.home_prob), ("draw", forecast.draw_prob), ("away", forecast.away_prob)),
                key=lambda item: item[1],
            )[0],
        },
        "totals": {key.replace(".", "_"): round(value, 4) for key, value in forecast.totals.items()},
        "oz": {
            "yes": round(forecast.btts_yes, 4),
            "no": round(forecast.btts_no, 4),
            "most_likely": "yes" if forecast.btts_yes >= forecast.btts_no else "no",
        },
        "handicaps": {
            key.replace("+", "plus_").replace("-", "minus_").replace(".", "_"): round(value, 4)
            for key, value in forecast.handicaps.items()
        },
        "top_pick": forecast.top_pick,
    }
