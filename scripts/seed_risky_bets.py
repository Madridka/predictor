"""Очистить ставки и добавить 2 риск-ставки за матчи 11.06."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from wc2026.api import get_prediction_json
from wc2026.bets_store import create_bet, init_bets_db, sync_results_from_file
from wc2026.data_loader import load_matches
from wc2026.picks_extractor import compute_bold_odds_pick, extract_positive_ev_picks
from wc2026.bets_store import _connect

init_bets_db()

with _connect() as conn:
    conn.execute("DELETE FROM bets")
    conn.commit()

matches = {m.match_id: m for m in load_matches()}

# Мексика — ЮАР: лучший +EV
m1 = matches[1]
pred1 = get_prediction_json(m1)
top1 = extract_positive_ev_picks(pred1)[0]

create_bet(
    {
        "match_id": m1.match_id,
        "match_date": m1.date,
        "home_code": m1.home.code,
        "away_code": m1.away.code,
        "home_name": m1.home.name,
        "away_name": m1.away.name,
        "market": top1["market"],
        "selection": top1["selection"],
        "selection_label": top1["selection_label"],
        "model_prob": top1["model_prob"],
        "odds": top1["odds"],
        "stake": 500,
        "guess_note": top1.get("guess_note"),
        "is_risky": 1,
    }
)

# Корея — Чехия: +EV нет при кеф≥2, берём «риск ≈ коэф»
m2 = matches[2]
pred2 = get_prediction_json(m2)
bold2 = compute_bold_odds_pick(pred2)
if not bold2:
    raise SystemExit("Нет риск-ставки для матча 2")

create_bet(
    {
        "match_id": m2.match_id,
        "match_date": m2.date,
        "home_code": m2.home.code,
        "away_code": m2.away.code,
        "home_name": m2.home.name,
        "away_name": m2.away.name,
        "market": bold2["market"],
        "selection": bold2["selection"],
        "selection_label": bold2["selection_label"],
        "model_prob": bold2["prob"],
        "odds": bold2["odds"],
        "stake": 500,
        "guess_note": pred2.get("cards", {}).get("guess_note"),
        "is_risky": 1,
    }
)

synced = sync_results_from_file()
print(f"Готово: 2 ставки, пересчитано по итогам: {synced}")

from wc2026.bets_store import list_bets

for b in list_bets(is_risky=True):
    print(
        f"  {b['selection_label']} @ {b['odds']} · "
        f"{b['actual_home']}:{b['actual_away']} · {b['status']} · P/L {b['profit']}"
    )
