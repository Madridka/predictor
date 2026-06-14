"""Mathematical models for FIFA World Cup 2026 match prediction."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.stats import poisson


@dataclass(frozen=True)
class Team:
    code: str
    name: str
    fifa_points: float
    rank: int
    host: bool = False


@dataclass(frozen=True)
class Match:
    match_id: int
    date: str
    home: Team
    away: Team
    group: str
    venue: str


@dataclass
class MatchPrediction:
    match: Match
    lambda_home: float
    lambda_away: float
    prob_home_win: float
    prob_draw: float
    prob_away_win: float
    score_matrix: np.ndarray
    top_scores: list[tuple[int, int, float]]
    totals: dict[str, float]
    oz: dict[str, float]
    expected_total: float


# FIFA official Elo divisor (since 2018)
FIFA_ELO_DIVISOR = 600.0

# Dixon-Coles low-score correlation (typical WC calibration)
DIXON_COLES_RHO = -0.13

# Historical World Cup group-stage average (~2.65 goals/match, 2022: 2.69)
WC_AVG_GOALS_PER_MATCH = 2.65
WC_AVG_GOALS_PER_TEAM = WC_AVG_GOALS_PER_MATCH / 2.0

# Host/co-host home advantage in rating points (literature: ~50-100 Elo)
HOST_HOME_ADVANTAGE = 75.0
GENERAL_HOME_ADVANTAGE = 35.0


def fifa_expected_score(rating_home: float, rating_away: float) -> float:
    """FIFA official expected result We for the home team."""
    diff = rating_home - rating_away
    return 1.0 / (10.0 ** (-diff / FIFA_ELO_DIVISOR) + 1.0)


def effective_ratings(home: Team, away: Team) -> tuple[float, float]:
    """Apply home-field advantage on top of FIFA points."""
    bonus = HOST_HOME_ADVANTAGE if home.host else GENERAL_HOME_ADVANTAGE
    return home.fifa_points + bonus, away.fifa_points


def estimate_lambdas(home: Team, away: Team) -> tuple[float, float]:
    """
    Derive Poisson intensities from FIFA ratings.

    Uses log-linear model calibrated to World Cup scoring rates:
    λ_home = μ * exp((R_h - R_a) / (2 * scale))
    λ_away = μ * exp((R_a - R_h) / (2 * scale))
    where μ = average goals per team per match.
    """
    r_home, r_away = effective_ratings(home, away)
    scale = 400.0  # standard Elo goal-scoring sensitivity
    delta = (r_home - r_away) / scale
    lambda_home = WC_AVG_GOALS_PER_TEAM * math.exp(delta / 2.0)
    lambda_away = WC_AVG_GOALS_PER_TEAM * math.exp(-delta / 2.0)
    return lambda_home, lambda_away


def dixon_coles_tau(home_goals: int, away_goals: int, lambda_h: float, lambda_a: float, rho: float) -> float:
    """Dixon-Coles adjustment factor τ for low-score outcomes."""
    if home_goals == 0 and away_goals == 0:
        return 1.0 - lambda_h * lambda_a * rho
    if home_goals == 0 and away_goals == 1:
        return 1.0 + lambda_h * rho
    if home_goals == 1 and away_goals == 0:
        return 1.0 + lambda_a * rho
    if home_goals == 1 and away_goals == 1:
        return 1.0 - rho
    return 1.0


def build_score_matrix(
    lambda_home: float,
    lambda_away: float,
    max_goals: int = 8,
    rho: float = DIXON_COLES_RHO,
) -> np.ndarray:
    """Full joint score probability matrix with Dixon-Coles correction."""
    matrix = np.zeros((max_goals + 1, max_goals + 1))
    for h in range(max_goals + 1):
        for a in range(max_goals + 1):
            base = poisson.pmf(h, lambda_home) * poisson.pmf(a, lambda_away)
            matrix[h, a] = base * dixon_coles_tau(h, a, lambda_home, lambda_away, rho)
    tail = 1.0 - matrix.sum()
    if tail > 1e-9:
        matrix[max_goals, max_goals] += tail
    matrix /= matrix.sum()
    return matrix


def outcome_probabilities(matrix: np.ndarray) -> tuple[float, float, float]:
    """P(home win), P(draw), P(away win) from score matrix."""
    n = matrix.shape[0]
    p_home = sum(matrix[h, a] for h in range(n) for a in range(n) if h > a)
    p_draw = sum(matrix[h, h] for h in range(n))
    p_away = sum(matrix[h, a] for h in range(n) for a in range(n) if h < a)
    return float(p_home), float(p_draw), float(p_away)


def total_goals_probs(matrix: np.ndarray, max_total: int = 10) -> dict[str, float]:
    """Over/under probabilities for common lines."""
    n = matrix.shape[0]
    totals = np.zeros(max_total + 1)
    for h in range(n):
        for a in range(n):
            t = min(h + a, max_total)
            totals[t] += matrix[h, a]

    def over(line: float) -> float:
        threshold = int(line)
        if line == threshold:
            return float(sum(totals[threshold + 1 :]))
        return float(sum(totals[int(math.ceil(line)) :]))

    def under(line: float) -> float:
        return 1.0 - over(line)

    return {
        "over_1.5": over(1.5),
        "under_1.5": under(1.5),
        "over_2.5": over(2.5),
        "under_2.5": under(2.5),
        "over_3.5": over(3.5),
        "under_3.5": under(3.5),
        "exact_distribution": {str(i): float(totals[i]) for i in range(max_total + 1)},
    }


def oz_probs(matrix: np.ndarray) -> dict[str, float]:
    """Обе забьют (ОЗ) — вероятности."""
    n = matrix.shape[0]
    yes = sum(matrix[h, a] for h in range(1, n) for a in range(1, n))
    return {"yes": float(yes), "no": float(1.0 - yes)}


def top_correct_scores(matrix: np.ndarray, n: int = 5) -> list[tuple[int, int, float]]:
    """Most likely exact scores."""
    flat = []
    rows, cols = matrix.shape
    for h in range(rows):
        for a in range(cols):
            flat.append((h, a, float(matrix[h, a])))
    flat.sort(key=lambda x: x[2], reverse=True)
    return flat[:n]


def predict_match(match: Match) -> MatchPrediction:
    """Full prediction pipeline for a single match."""
    lambda_h, lambda_a = estimate_lambdas(match.home, match.away)
    matrix = build_score_matrix(lambda_h, lambda_a)
    p_home, p_draw, p_away = outcome_probabilities(matrix)

    return MatchPrediction(
        match=match,
        lambda_home=lambda_h,
        lambda_away=lambda_a,
        prob_home_win=p_home,
        prob_draw=p_draw,
        prob_away_win=p_away,
        score_matrix=matrix,
        top_scores=top_correct_scores(matrix),
        totals=total_goals_probs(matrix),
        oz=oz_probs(matrix),
        expected_total=lambda_h + lambda_a,
    )


def ensemble_1x2(
    poisson_home: float,
    poisson_draw: float,
    poisson_away: float,
    home: Team,
    away: Team,
    poisson_weight: float = 0.65,
) -> tuple[float, float, float]:
    """
    Blend Poisson/Dixon-Coles 1X2 with FIFA Elo expected result.

    Elo alone ignores draws; we map We to (W, D, L) using empirical WC draw rate (~25%).
    """
    r_home, r_away = effective_ratings(home, away)
    we = fifa_expected_score(r_home, r_away)
    draw_rate = 0.25
    elo_home = we * (1.0 - draw_rate)
    elo_draw = draw_rate
    elo_away = (1.0 - we) * (1.0 - draw_rate)

    w = poisson_weight
    return (
        w * poisson_home + (1 - w) * elo_home,
        w * poisson_draw + (1 - w) * elo_draw,
        w * poisson_away + (1 - w) * elo_away,
    )


def format_pct(value: float) -> str:
    return f"{value * 100:.1f}%"
