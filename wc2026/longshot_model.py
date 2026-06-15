"""Longshot forecasting strategy for high-odds World Cup picks."""

from __future__ import annotations

from dataclasses import dataclass

from wc2026.market_model import forecast_match_market, forecast_to_dict
from wc2026.models import Match
from wc2026.odds_loader import get_match_odds

LONGSHOT_MIN_ODDS = 4.0
LONGSHOT_MAX_ODDS = 18.0
LONGSHOT_TARGET_ODDS = 4.5
LONGSHOT_MIN_EDGE = -0.035
LONGSHOT_MIN_PROB = 0.135
LONGSHOT_MIN_SCORE = 0.72

TOTAL_LABELS = {
    "over_1.5": "Больше 1.5",
    "under_1.5": "Меньше 1.5",
    "over_2.5": "Больше 2.5",
    "under_2.5": "Меньше 2.5",
    "over_3.5": "Больше 3.5",
    "under_3.5": "Меньше 3.5",
}


@dataclass(frozen=True)
class LongshotForecast:
    match: Match
    base: dict
    picks: list[dict]


def _raw_handicap_key(safe_key: str) -> str:
    side, line = safe_key.split("_", 1)
    line = line.replace("plus_", "+").replace("minus_", "-").replace("_", ".")
    return f"{side}_{line}"


def _handicap_label(raw_key: str) -> str:
    side, line = raw_key.split("_", 1)
    return f"{'Ф1' if side == 'home' else 'Ф2'} ({line})"


def _stored_handicap_odd(handicap_odds: dict, raw_key: str, safe_key: str) -> float | None:
    odd = handicap_odds.get(raw_key) or handicap_odds.get(safe_key)
    return float(odd) if odd else None


def _adjust_longshot_probability(candidate: dict, base: dict) -> tuple[float, list[str]]:
    market = candidate["market"]
    selection = candidate["selection"]
    prob = float(candidate["base_prob"])
    o = base["outcome_1x2"]
    expected_total = float(base["model"]["expected_total"])
    imbalance = abs(float(o["home"]) - float(o["away"]))
    close_factor = max(0.0, 1.0 - imbalance / 0.35)
    reasons: list[str] = []
    multiplier = 1.0

    if market == "1x2" and selection == "draw":
        multiplier += 0.18 * close_factor
        reasons.append("близкие силы повышают шанс ничьей")
        if expected_total <= 2.45:
            multiplier += 0.12
            reasons.append("низкий ожидаемый тотал")

    if market == "1x2" and selection in ("home", "away"):
        selected_prob = float(o[selection])
        opponent = "away" if selection == "home" else "home"
        if selected_prob < float(o[opponent]):
            multiplier += 0.16 * close_factor
            reasons.append("апсет при неразорванной паре")
        if expected_total >= 2.65:
            multiplier += 0.08
            reasons.append("высокая дисперсия голов")

    if market == "total" and selection == "under_1.5":
        if expected_total <= 2.45:
            multiplier += 0.22
            reasons.append("сжатый тотал матча")
        if float(o["draw"]) >= 0.26:
            multiplier += 0.08
            reasons.append("ничейный профиль")

    if market == "total" and selection == "over_3.5":
        if expected_total >= 2.75:
            multiplier += 0.18
            reasons.append("высокий ожидаемый тотал")
        if imbalance >= 0.22:
            multiplier += 0.08
            reasons.append("сценарий разгрома")

    if market == "handicap":
        side, line_raw = selection.split("_", 1)
        line = float(line_raw)
        side_prob = float(o["home"] if side == "home" else o["away"])
        other_prob = float(o["away"] if side == "home" else o["home"])
        if line > 0:
            multiplier += 0.14 * close_factor
            reasons.append("плюсовая фора в близком матче")
        if line < 0 and side_prob > other_prob:
            multiplier += 0.10 + 0.10 * imbalance
            reasons.append("минусовая фора фаворита")

    adjusted = min(0.72, prob * multiplier)
    if not reasons:
        reasons.append("коэффициент выше порога longshot")
    return adjusted, reasons


def _candidate_score(prob: float, odds: float) -> float:
    implied = 1.0 / odds
    edge = prob - implied
    edge_bonus = 1.0 + max(-0.18, min(0.35, edge)) * 1.45
    odds_bonus = 1.0 + min(0.45, max(0.0, odds - LONGSHOT_TARGET_ODDS) * 0.04)
    return prob * odds * edge_bonus * odds_bonus


def _scenario_quality(candidate: dict, adjusted_prob: float, base: dict) -> float:
    odds = float(candidate["odds"])
    market = candidate["market"]
    selection = candidate["selection"]
    o = base["outcome_1x2"]
    expected_total = float(base["model"]["expected_total"])
    imbalance = abs(float(o["home"]) - float(o["away"]))
    quality = adjusted_prob * odds

    if market == "1x2" and selection == "draw":
        if imbalance <= 0.12:
            quality += 0.18
        if expected_total <= 2.55:
            quality += 0.12

    if market == "1x2" and selection in ("home", "away"):
        side_prob = float(o[selection])
        if side_prob >= 0.18:
            quality += 0.12
        if imbalance <= 0.18:
            quality += 0.08

    if market == "total" and selection == "under_1.5":
        if expected_total <= 2.55:
            quality += 0.16
        if float(o["draw"]) >= 0.25:
            quality += 0.08

    if market == "total" and selection == "over_3.5":
        if expected_total >= 2.65:
            quality += 0.14

    if market == "handicap":
        if selection.endswith("+0.5") or selection.endswith("+1.5"):
            quality += max(0.0, 0.14 - imbalance * 0.2)

    return quality


def longshot_forecast(match: Match, min_odds: float = LONGSHOT_MIN_ODDS) -> LongshotForecast:
    base = forecast_to_dict(forecast_match_market(match))
    stored_odds = get_match_odds(match.match_id)
    candidates: list[dict] = []

    labels_1x2 = {
        "home": f"П1 {match.home.name}",
        "draw": "X - ничья",
        "away": f"П2 {match.away.name}",
    }
    for selection, label in labels_1x2.items():
        prob = float(base["outcome_1x2"][selection])
        odd = stored_odds.get("1x2", {}).get(selection)
        if not odd:
            continue
        candidates.append(
            {
                "market": "1x2",
                "selection": selection,
                "selection_label": label,
                "base_prob": prob,
                "odds": float(odd),
            }
        )

    for selection, label in TOTAL_LABELS.items():
        prob_key = selection.replace(".", "_")
        prob = float(base["totals"][prob_key])
        odd = stored_odds.get("total", {}).get(selection)
        if not odd:
            continue
        candidates.append(
            {
                "market": "total",
                "selection": selection,
                "selection_label": label,
                "base_prob": prob,
                "odds": float(odd),
            }
        )

    handicap_odds = stored_odds.get("handicap", {})
    if handicap_odds:
        for safe_key, prob in base["handicaps"].items():
            raw_key = _raw_handicap_key(safe_key)
            odd = _stored_handicap_odd(handicap_odds, raw_key, safe_key)
            if not odd:
                continue
            candidates.append(
                {
                    "market": "handicap",
                    "selection": raw_key,
                    "selection_label": _handicap_label(raw_key),
                    "base_prob": float(prob),
                    "odds": odd,
                }
            )

    picks: list[dict] = []
    for candidate in candidates:
        odds = float(candidate["odds"])
        if odds < min_odds or odds > LONGSHOT_MAX_ODDS:
            continue
        adjusted_prob, reasons = _adjust_longshot_probability(candidate, base)
        score = _candidate_score(adjusted_prob, odds)
        edge = adjusted_prob - 1.0 / odds
        scenario_quality = _scenario_quality(candidate, adjusted_prob, base)
        if (
            adjusted_prob < LONGSHOT_MIN_PROB
            or edge < LONGSHOT_MIN_EDGE
            or (score < LONGSHOT_MIN_SCORE and scenario_quality < 0.88)
        ):
            continue
        picks.append(
            {
                "match_id": match.match_id,
                "match_date": match.date,
                "home_name": match.home.name,
                "away_name": match.away.name,
                "market": candidate["market"],
                "selection": candidate["selection"],
                "selection_label": candidate["selection_label"],
                "base_prob": round(float(candidate["base_prob"]), 4),
                "model_prob": round(adjusted_prob, 4),
                "odds": round(odds, 2),
                "implied_prob": round(1.0 / odds, 4),
                "edge": round(edge, 4),
                "score": round(score, 4),
                "scenario_quality": round(scenario_quality, 4),
                "reasons": reasons,
            }
        )

    picks.sort(key=lambda item: (item["score"], item["scenario_quality"], item["odds"]), reverse=True)
    return LongshotForecast(match=match, base=base, picks=picks[:1])


def longshot_to_dict(forecast: LongshotForecast) -> dict:
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
        "source": "longshot-overlay",
        "min_odds": LONGSHOT_MIN_ODDS,
        "model": forecast.base["model"],
        "picks": forecast.picks,
        "top_pick": forecast.picks[0] if forecast.picks else None,
    }
