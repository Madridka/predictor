"""Извлечение наиболее вероятных прогнозов из расчёта матча."""

from __future__ import annotations

CARD_LABELS = {
    "over_3.5": "ЖК больше 3.5",
    "under_3.5": "ЖК меньше 3.5",
    "over_4.5": "ЖК больше 4.5",
    "under_4.5": "ЖК меньше 4.5",
}

TOTAL_LINES = [
    ("over_1.5", "over_1_5", "Больше 1.5"),
    ("under_1.5", "under_1_5", "Меньше 1.5"),
    ("over_2.5", "over_2_5", "Больше 2.5"),
    ("under_2.5", "under_2_5", "Меньше 2.5"),
    ("over_3.5", "over_3_5", "Больше 3.5"),
    ("under_3.5", "under_3_5", "Меньше 3.5"),
]

DEFAULT_MIN_ODDS = 1.65

# «Сбалансированный» прогноз: основные рынки, коэф 1.65–3.0, prob ≥ 42%
BALANCED_MIN_ODDS = 1.65
BALANCED_MAX_ODDS = 3.0
BALANCED_MIN_PROB = 0.42
BALANCED_TIE_EPS = 0.003
BALANCED_MARKETS = frozenset({"1x2", "total", "oz"})
BALANCED_MARKET_PRIORITY = {"oz": 0, "total": 1, "1x2": 2}

# «Риск ≈ коэф» — ставки с высоким кефом, где prob близка к implied (1/odds)
BOLD_MIN_ODDS = 1.80
BOLD_MAX_ODDS = 6.0
BOLD_MIN_PROB = 0.38
BOLD_ODDS_WEIGHT = 0.28  # бонус за высокий кеф

# «Рискованные / +EV» — мат. ожидание, кеф ≥ 1.65; fallback если нет +EV
RISKY_MIN_ODDS = 1.65
RISKY_MAX_ODDS = 15.0
RISKY_MIN_EV = 0.0  # prob × odds − 1 > 0
RISKY_FALLBACK_MIN_ODDS = 1.65
RISKY_FALLBACK_MIN_EV = -0.12  # до −12% EV для единственной ставки на матч


def _append_candidate(
    candidates: list[dict],
    market: str,
    selection: str,
    label: str,
    prob: float,
    odd: float,
    score: float,
) -> None:
    candidates.append(
        {
            "market": market,
            "selection": selection,
            "selection_label": label,
            "prob": round(float(prob), 4),
            "odds": round(float(odd), 2),
            "score": round(float(score), 4),
            "implied_prob": round(1.0 / float(odd), 4),
        }
    )


def _consider_main_markets(
    pred: dict,
    consider_fn,
) -> None:
    m = pred["match"]
    odds = pred["odds"]
    o = pred["outcome_1x2"]
    labels_1x2 = {
        "home": f"П1 {m['home']['name']}",
        "draw": "X — ничья",
        "away": f"П2 {m['away']['name']}",
    }
    for key in ("home", "draw", "away"):
        prob = o[key]["prob"] if key != "draw" else o["draw"]["prob"]
        consider_fn("1x2", key, labels_1x2[key], prob, odds["1x2"][key])

    for sel, prob_key, label in TOTAL_LINES:
        consider_fn("total", sel, label, pred["totals"][prob_key], odds["total"][sel])

    oz = pred["oz"]
    consider_fn("oz", "yes", "ОЗ: Да", oz["yes"], odds["oz"]["yes"])
    consider_fn("oz", "no", "ОЗ: Нет", oz["no"], odds["oz"]["no"])


def _consider_card_markets(pred: dict, consider_fn) -> None:
    cards = pred.get("cards", {})
    if not cards:
        return
    odds = pred["odds"]
    y = cards.get("yellows", {})
    for sel, label in CARD_LABELS.items():
        if sel in y:
            consider_fn("cards", sel, label, y[sel], odds["cards"][sel])
    rc = cards.get("red_card", {})
    for sel, label in (("yes", "КК: да"), ("no", "КК: нет")):
        if sel in rc:
            consider_fn("red_card", sel, label, rc[sel], odds["red_card"][sel])
    by = cards.get("both_yellow", {})
    for sel, label in (("yes", "Обе с ЖК: да"), ("no", "Обе с ЖК: нет")):
        if sel in by:
            consider_fn("both_yellow", sel, label, by[sel], odds["both_yellow"][sel])


def extract_top_picks(pred: dict, min_odds: float = DEFAULT_MIN_ODDS) -> list[dict]:
    """Собрать лидирующий прогноз по каждому рынку, если коэффициент >= min_odds."""
    picks: list[dict] = []
    m = pred["match"]
    odds = pred["odds"]
    suggested = pred.get("suggested", {})
    cards = pred.get("cards", {})

    base = {
        "match_id": m["id"],
        "match_date": m["date"],
        "home_name": m["home"]["name"],
        "away_name": m["away"]["name"],
    }

    def score_guess() -> str | None:
        sh, sa = suggested.get("score_home"), suggested.get("score_away")
        if sh is not None and sa is not None:
            return f"{sh}:{sa}"
        return None

    def add(
        market: str,
        selection: str,
        label: str,
        prob: float,
        odd: float,
        guess_note: str | None = None,
    ) -> None:
        if odd is None or float(odd) < min_odds:
            return
        picks.append(
            {
                **base,
                "market": market,
                "selection": selection,
                "selection_label": label,
                "model_prob": round(prob, 4),
                "odds": round(float(odd), 2),
                "guess_note": guess_note,
            }
        )

    o = pred["outcome_1x2"]
    labels_1x2 = {
        "home": f"П1 {m['home']['name']}",
        "draw": "X — ничья",
        "away": f"П2 {m['away']['name']}",
    }
    key = o["most_likely"]
    prob = o[key]["prob"] if key != "draw" else o["draw"]["prob"]
    add("1x2", key, labels_1x2[key], prob, odds["1x2"][key], score_guess())

    t = pred["totals"]
    ml = t["most_likely"]
    for sel, prob_key, label in TOTAL_LINES:
        if prob_key == ml:
            add("total", sel, label, t[prob_key], odds["total"][sel], score_guess())
            break

    oz = pred["oz"]
    ozsel = oz["most_likely"]
    add(
        "oz",
        ozsel,
        f"ОЗ: {'Да' if ozsel == 'yes' else 'Нет'}",
        oz[ozsel],
        odds["oz"][ozsel],
        score_guess(),
    )

    if cards:
        note = cards.get("guess_note")
        y = cards.get("yellows", {})
        ysel = y.get("most_likely")
        if ysel:
            add(
                "cards",
                ysel,
                CARD_LABELS.get(ysel, ysel),
                y[ysel],
                odds["cards"][ysel],
                note,
            )

        rc = cards.get("red_card", {})
        rsel = rc.get("most_likely")
        if rsel:
            add(
                "red_card",
                rsel,
                f"КК: {'да' if rsel == 'yes' else 'нет'}",
                rc[rsel],
                odds["red_card"][rsel],
                note,
            )

        by = cards.get("both_yellow", {})
        bysel = by.get("most_likely")
        if bysel:
            add(
                "both_yellow",
                bysel,
                f"Обе с ЖК: {'да' if bysel == 'yes' else 'нет'}",
                by[bysel],
                odds["both_yellow"][bysel],
                note,
            )

    picks.sort(key=lambda x: x["model_prob"], reverse=True)
    for i, pick in enumerate(picks, start=1):
        pick["rank_in_match"] = i

    return picks


def compute_best_value_pick(pred: dict) -> dict | None:
    """Сбалансированный исход: max(prob × коэф) среди 1X2/тотал/ОЗ с разумным кефом."""
    candidates: list[dict] = []

    def consider(
        market: str, selection: str, label: str, prob: float, odd: float
    ) -> None:
        if market not in BALANCED_MARKETS:
            return
        if prob is None or odd is None:
            return
        p, o = float(prob), float(odd)
        if o < BALANCED_MIN_ODDS or o > BALANCED_MAX_ODDS or p < BALANCED_MIN_PROB:
            return
        _append_candidate(candidates, market, selection, label, p, o, p * o)

    def consider_balanced(market, selection, label, prob, odd):
        if market == "oz" and selection != "yes":
            return
        consider(market, selection, label, prob, odd)

    _consider_main_markets(pred, consider_balanced)

    if not candidates:
        return None

    top_score = max(c["score"] for c in candidates)
    tier = [c for c in candidates if c["score"] >= top_score - BALANCED_TIE_EPS]
    return min(
        tier,
        key=lambda c: (BALANCED_MARKET_PRIORITY.get(c["market"], 9), -c["score"]),
    )


def compute_bold_odds_pick(pred: dict) -> dict | None:
    """Высокий кеф: prob × odds с бонусом; нишевые рынки (ЖК 4.5 и т.п.)."""
    candidates: list[dict] = []

    def consider(
        market: str, selection: str, label: str, prob: float, odd: float
    ) -> None:
        if prob is None or odd is None:
            return
        p, o = float(prob), float(odd)
        if o < BOLD_MIN_ODDS or o > BOLD_MAX_ODDS or p < BOLD_MIN_PROB:
            return
        implied = 1.0 / o
        fairness = 1.0 - min(1.0, abs(p - implied) / 0.22)
        odds_boost = 1.0 + max(0.0, o - BOLD_MIN_ODDS) * BOLD_ODDS_WEIGHT
        score = p * o * odds_boost * (0.55 + 0.45 * fairness)
        _append_candidate(candidates, market, selection, label, p, o, score)

    _consider_main_markets(pred, consider)
    _consider_card_markets(pred, consider)

    if not candidates:
        return None

    best = max(candidates, key=lambda c: c["score"])
    balanced = compute_best_value_pick(pred)
    if balanced and (
        best["market"] == balanced["market"]
        and best["selection"] == balanced["selection"]
    ):
        rest = [c for c in candidates if c is not best]
        if rest:
            best = max(rest, key=lambda c: c["score"])
    return best


def _guess_note_for_pred(pred: dict) -> str | None:
    suggested = pred.get("suggested", {})
    sh, sa = suggested.get("score_home"), suggested.get("score_away")
    if sh is not None and sa is not None:
        return f"{sh}:{sa}"
    cards = pred.get("cards", {})
    return cards.get("guess_note")


def extract_positive_ev_picks(
    pred: dict,
    min_odds: float = RISKY_MIN_ODDS,
    min_ev: float = RISKY_MIN_EV,
    max_odds: float = RISKY_MAX_ODDS,
) -> list[dict]:
    """Все исходы с +EV (prob × odds > 1) и коэфом ≥ min_odds."""
    picks: list[dict] = []
    m = pred["match"]
    guess_note = _guess_note_for_pred(pred)

    base = {
        "match_id": m["id"],
        "match_date": m["date"],
        "home_name": m["home"]["name"],
        "away_name": m["away"]["name"],
    }

    def consider(
        market: str, selection: str, label: str, prob: float, odd: float
    ) -> None:
        if prob is None or odd is None:
            return
        p, o = float(prob), float(odd)
        if o < min_odds or o > max_odds:
            return
        ev = p * o - 1.0
        if ev <= min_ev:
            return
        picks.append(
            {
                **base,
                "market": market,
                "selection": selection,
                "selection_label": label,
                "model_prob": round(p, 4),
                "odds": round(o, 2),
                "ev": round(ev, 4),
                "ev_pct": round(ev * 100, 1),
                "edge": round(p - 1.0 / o, 4),
                "implied_prob": round(1.0 / o, 4),
                "guess_note": guess_note,
            }
        )

    _consider_main_markets(pred, consider)
    _consider_card_markets(pred, consider)

    picks.sort(key=lambda x: (-x["ev"], -x["odds"]))
    for i, pick in enumerate(picks, start=1):
        pick["rank_in_match"] = i
        pick.setdefault("pick_kind", "ev")
    return picks


def _collect_risky_candidates(
    pred: dict,
    min_odds: float,
    max_odds: float,
) -> list[dict]:
    """Все исходы с коэфом в диапазоне (без фильтра EV)."""
    rows: list[dict] = []
    m = pred["match"]
    guess_note = _guess_note_for_pred(pred)
    base = {
        "match_id": m["id"],
        "match_date": m["date"],
        "home_name": m["home"]["name"],
        "away_name": m["away"]["name"],
        "guess_note": guess_note,
    }

    def consider(
        market: str, selection: str, label: str, prob: float, odd: float
    ) -> None:
        if prob is None or odd is None:
            return
        p, o = float(prob), float(odd)
        if o < min_odds or o > max_odds:
            return
        ev = p * o - 1.0
        rows.append(
            {
                **base,
                "market": market,
                "selection": selection,
                "selection_label": label,
                "model_prob": round(p, 4),
                "odds": round(o, 2),
                "ev": round(ev, 4),
                "ev_pct": round(ev * 100, 1),
                "edge": round(p - 1.0 / o, 4),
                "implied_prob": round(1.0 / o, 4),
            }
        )

    _consider_main_markets(pred, consider)
    _consider_card_markets(pred, consider)
    return rows


def extract_best_fallback_pick(
    pred: dict,
    min_odds: float = RISKY_FALLBACK_MIN_ODDS,
    min_ev: float = RISKY_FALLBACK_MIN_EV,
    max_odds: float = RISKY_MAX_ODDS,
) -> dict | None:
    """Лучший исход на матч, если +EV нет (prob×коэф, EV не хуже min_ev)."""
    candidates = _collect_risky_candidates(pred, min_odds, max_odds)
    if not candidates:
        return None

    viable = [c for c in candidates if c["ev"] >= min_ev]
    if not viable:
        viable = candidates

    best = max(viable, key=lambda c: (c["ev"], c["model_prob"] * c["odds"]))
    best = {**best, "pick_kind": "fallback", "rank_in_match": 1}
    return best


def extract_match_risky_picks(
    pred: dict,
    min_odds: float = RISKY_MIN_ODDS,
    min_ev: float = RISKY_MIN_EV,
    max_odds: float = RISKY_MAX_ODDS,
    *,
    ensure_one: bool = True,
) -> list[dict]:
    """+EV ставки; если нет — одна fallback-ставка на матч."""
    picks = extract_positive_ev_picks(pred, min_odds=min_odds, min_ev=min_ev, max_odds=max_odds)
    if picks:
        return picks
    if not ensure_one:
        return []
    fallback = extract_best_fallback_pick(
        pred, min_odds=min_odds, min_ev=RISKY_FALLBACK_MIN_EV, max_odds=max_odds
    )
    return [fallback] if fallback else []


def best_value_as_archive_pick(pred: dict) -> dict | None:
    """Прогноз prob÷коэф в формате записи архива."""
    bv = compute_best_value_pick(pred)
    if not bv:
        return None

    m = pred["match"]
    suggested = pred.get("suggested", {})
    sh, sa = suggested.get("score_home"), suggested.get("score_away")
    guess_note = f"{sh}:{sa}" if sh is not None and sa is not None else None
    cards = pred.get("cards", {})
    if not guess_note and cards.get("guess_note"):
        guess_note = cards["guess_note"]

    return {
        "match_id": m["id"],
        "match_date": m["date"],
        "home_name": m["home"]["name"],
        "away_name": m["away"]["name"],
        "market": bv["market"],
        "selection": bv["selection"],
        "selection_label": bv["selection_label"],
        "model_prob": bv["prob"],
        "odds": bv["odds"],
        "guess_note": guess_note,
        "rank_in_match": 1,
        "is_best_value": 1,
    }
