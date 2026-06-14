"""Load bookmaker odds from data/odds.json."""

from __future__ import annotations

import json
from pathlib import Path

ODDS_PATH = Path(__file__).resolve().parent.parent / "data" / "odds.json"

DEFAULT_STAKE = 500.0


def _load_all() -> dict:
    if not ODDS_PATH.exists():
        return {"default_stake": DEFAULT_STAKE, "matches": {}}
    return json.loads(ODDS_PATH.read_text(encoding="utf-8"))


def get_default_stake() -> float:
    return float(_load_all().get("default_stake", DEFAULT_STAKE))


def get_match_odds(match_id: int) -> dict:
    data = _load_all()
    key = str(match_id)
    return data.get("matches", {}).get(key, {})


def odds_from_prob(prob: float, margin: float = 0.08) -> float:
    """Fair decimal odds with bookmaker margin."""
    if prob <= 0.01:
        return 15.0
    return round(max(1.01, (1.0 - margin) / prob), 2)


def enrich_prediction_with_odds(prediction: dict) -> dict:
    """Attach odds to prediction; fill missing from model probabilities."""
    match_id = prediction["match"]["id"]
    stored = get_match_odds(match_id)
    o = prediction["outcome_1x2"]
    t = prediction["totals"]
    oz = prediction["oz"]

    odds_1x2 = stored.get("1x2", {})
    odds_total = stored.get("total", {})
    odds_oz = stored.get("oz", stored.get("btts", {}))
    odds_cards = stored.get("cards", {})
    odds_red = stored.get("red_card", {})
    odds_both = stored.get("both_yellow", {})

    cards = prediction.get("cards", {})
    y = cards.get("yellows", {})
    rc = cards.get("red_card", {})
    by = cards.get("both_yellow", {})

    prediction["odds"] = {
        "1x2": {
            "home": odds_1x2.get("home") or odds_from_prob(o["home"]["prob"]),
            "draw": odds_1x2.get("draw") or odds_from_prob(o["draw"]["prob"]),
            "away": odds_1x2.get("away") or odds_from_prob(o["away"]["prob"]),
        },
        "total": {
            "over_1.5": odds_total.get("over_1.5") or odds_from_prob(t["over_1_5"]),
            "under_1.5": odds_total.get("under_1.5") or odds_from_prob(t["under_1_5"]),
            "over_2.5": odds_total.get("over_2.5") or odds_from_prob(t["over_2_5"]),
            "under_2.5": odds_total.get("under_2.5") or odds_from_prob(t["under_2_5"]),
            "over_3.5": odds_total.get("over_3.5") or odds_from_prob(t["over_3_5"]),
            "under_3.5": odds_total.get("under_3.5") or odds_from_prob(t["under_3_5"]),
        },
        "oz": {
            "yes": odds_oz.get("yes") or odds_from_prob(oz["yes"]),
            "no": odds_oz.get("no") or odds_from_prob(oz["no"]),
        },
        "cards": {
            "over_3.5": odds_cards.get("over_3.5") or odds_from_prob(y.get("over_3.5", 0.5)),
            "under_3.5": odds_cards.get("under_3.5") or odds_from_prob(y.get("under_3.5", 0.5)),
            "over_4.5": odds_cards.get("over_4.5") or odds_from_prob(y.get("over_4.5", 0.4)),
            "under_4.5": odds_cards.get("under_4.5") or odds_from_prob(y.get("under_4.5", 0.6)),
        },
        "red_card": {
            "yes": odds_red.get("yes") or odds_from_prob(rc.get("yes", 0.2)),
            "no": odds_red.get("no") or odds_from_prob(rc.get("no", 0.8)),
        },
        "both_yellow": {
            "yes": odds_both.get("yes") or odds_from_prob(by.get("yes", 0.55)),
            "no": odds_both.get("no") or odds_from_prob(by.get("no", 0.45)),
        },
    }
    prediction["default_stake"] = get_default_stake()
    from wc2026.picks_extractor import compute_best_value_pick, compute_bold_odds_pick

    prediction["best_value"] = compute_best_value_pick(prediction)
    prediction["bold_pick"] = compute_bold_odds_pick(prediction)
    return prediction
