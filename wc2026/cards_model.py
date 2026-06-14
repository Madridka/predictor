"""Poisson-модель для нишевых рынков: карточки, фолы."""

from __future__ import annotations

import math

from scipy.stats import poisson

from wc2026.models import Team, effective_ratings

# Средние по последним ЧМ (≈3.4–3.8 ЖК, ~0.15–0.22 КК за матч)
WC_AVG_YELLOW = 3.55
WC_AVG_RED = 0.19

# «Агрессивные» стили — эвристика по кодам (физический футбол)
AGGRESSIVE_BONUS = {
    "URU": 0.08,
    "COL": 0.07,
    "ECU": 0.06,
    "MEX": 0.05,
    "TUR": 0.08,
    "SRB": 0.06,
    "BIH": 0.05,
    "CIV": 0.05,
    "GHA": 0.05,
    "CMR": 0.05,
    "SEN": 0.04,
    "MAR": 0.06,
    "IRN": 0.07,
    "KSA": 0.05,
    "QAT": 0.04,
    "HAI": 0.06,
    "PAN": 0.05,
}


def _team_aggression(team: Team) -> float:
    base = AGGRESSIVE_BONUS.get(team.code, 0.0)
    if team.rank > 50:
        base += 0.04
    return base


def _yellow_over_prob(lam: float, line: float) -> float:
    threshold = int(line)
    if line == threshold:
        return float(1.0 - sum(poisson.pmf(k, lam) for k in range(threshold + 1)))
    return float(1.0 - sum(poisson.pmf(k, lam) for k in range(int(math.ceil(line)))))


def predict_cards(home: Team, away: Team) -> dict:
    """Вероятности рынков ЖК/КК на основе интенсивности матча."""
    r_home, r_away = effective_ratings(home, away)
    gap = abs(r_home - r_away)

    intensity = 1.0 + 0.14 * math.exp(-gap / 220.0)
    aggression = 1.0 + _team_aggression(home) + _team_aggression(away)
    underdog = 1.0 + max(0.0, (1650 - min(home.fifa_points, away.fifa_points)) / 2200)

    lambda_y = WC_AVG_YELLOW * intensity * aggression * underdog
    lambda_r = WC_AVG_RED * intensity * aggression * 1.12

    lam_h = lambda_y * 0.52
    lam_a = lambda_y * 0.48

    p_over_35 = _yellow_over_prob(lambda_y, 3.5)
    p_over_45 = _yellow_over_prob(lambda_y, 4.5)
    p_red_yes = float(1.0 - poisson.pmf(0, lambda_r))
    p_both_yellow = float((1 - poisson.pmf(0, lam_h)) * (1 - poisson.pmf(0, lam_a)))

    yellows = {
        "over_3.5": round(p_over_35, 4),
        "under_3.5": round(1.0 - p_over_35, 4),
        "over_4.5": round(p_over_45, 4),
        "under_4.5": round(1.0 - p_over_45, 4),
        "most_likely": "over_3.5" if p_over_35 >= 0.5 else "under_3.5",
    }
    red_card = {
        "yes": round(p_red_yes, 4),
        "no": round(1.0 - p_red_yes, 4),
        "most_likely": "yes" if p_red_yes >= 0.5 else "no",
    }
    both_yellow = {
        "yes": round(p_both_yellow, 4),
        "no": round(1.0 - p_both_yellow, 4),
        "most_likely": "yes" if p_both_yellow >= 0.5 else "no",
    }

    niche_options = [
        ("cards", yellows["most_likely"], f"ЖК {yellows['most_likely'].replace('_', ' ')}", max(p_over_35, 1 - p_over_35)),
        ("red_card", red_card["most_likely"], f"КК: {'да' if red_card['most_likely'] == 'yes' else 'нет'}", max(p_red_yes, 1 - p_red_yes)),
        ("both_yellow", both_yellow["most_likely"], f"Обе с ЖК: {'да' if both_yellow['most_likely'] == 'yes' else 'нет'}", max(p_both_yellow, 1 - p_both_yellow)),
    ]
    best = max(niche_options, key=lambda x: x[3])

    return {
        "expected_yellow": round(lambda_y, 2),
        "expected_red": round(lambda_r, 3),
        "yellows": yellows,
        "red_card": red_card,
        "both_yellow": both_yellow,
        "guess_note": f"≈{round(lambda_y)} ЖК",
        "niche_highlight": {
            "market": best[0],
            "selection": best[1],
            "label": best[2],
            "prob": round(best[3], 4),
        },
    }
