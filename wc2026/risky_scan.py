"""Сканирование рискованных ставок с положительным мат. ожиданием."""

from __future__ import annotations

from wc2026.api import get_prediction_json
from wc2026.data_loader import filter_by_date, load_matches
from wc2026.picks_extractor import (
    RISKY_MIN_EV,
    RISKY_MIN_ODDS,
    compute_bold_odds_pick,
    extract_match_risky_picks,
    extract_positive_ev_picks,
)
from wc2026.results_loader import load_results


def _is_finished(match_id: int, results: dict) -> bool:
    entry = results.get(str(match_id))
    return bool(entry and entry.get("status") == "finished")


def scan_positive_ev_picks(
    *,
    date: str | None = None,
    min_odds: float = RISKY_MIN_ODDS,
    min_ev: float = RISKY_MIN_EV,
    include_finished: bool = False,
) -> dict:
    """Найти +EV ставки (коэф ≥ min_odds) по расписанию."""
    matches = load_matches()
    if date:
        matches = filter_by_date(matches, date)

    results = load_results()
    scheduled = load_matches()
    if date:
        scheduled = filter_by_date(scheduled, date)
    finished_count = sum(1 for m in scheduled if _is_finished(m.match_id, results))

    if not include_finished:
        matches = [m for m in matches if not _is_finished(m.match_id, results)]

    all_picks: list[dict] = []
    for match in matches:
        pred = get_prediction_json(match)
        all_picks.extend(
            extract_match_risky_picks(pred, min_odds=min_odds, min_ev=min_ev)
        )

    all_picks.sort(key=lambda p: (-p["ev"], p["match_date"], p["match_id"]))

    ev_values = [p["ev"] for p in all_picks]
    match_ids = {p["match_id"] for p in all_picks}

    stats = {
        "total": len(all_picks),
        "matches": len(match_ids),
        "avg_ev_pct": round(sum(ev_values) / len(ev_values) * 100, 1) if ev_values else None,
        "top_ev_pct": round(max(ev_values) * 100, 1) if ev_values else None,
        "min_odds": min_odds,
        "min_ev_pct": round(min_ev * 100, 1),
        "date": date or "",
        "scheduled_matches": len(scheduled),
        "finished_matches": finished_count,
    }
    return {"picks": all_picks, "stats": stats}


def _pick_row_for_eval(p: dict) -> dict:
    return {"market": p["market"], "selection": p["selection"]}


def scan_retrospective_risky(
    min_odds: float = RISKY_MIN_ODDS,
    min_ev: float = RISKY_MIN_EV,
) -> dict:
    """+EV ставки по сыгранным матчам с итогом (win/loss)."""
    from wc2026.bets_store import _evaluate_bet

    results = load_results()
    groups: list[dict] = []

    for match in load_matches():
        r = results.get(str(match.match_id))
        if not r or r.get("status") != "finished":
            continue

        pred = get_prediction_json(match)
        ev_picks = extract_positive_ev_picks(pred, min_odds=min_odds, min_ev=min_ev)
        if not ev_picks:
            fb = extract_match_risky_picks(pred, min_odds=min_odds, min_ev=min_ev)[0:1]
            ev_picks = fb
        bold = compute_bold_odds_pick(pred)

        evaluated: list[dict] = []
        for p in ev_picks:
            evaluated.append(
                {
                    **p,
                    "pick_type": "ev",
                    "outcome": "won" if _evaluate_bet(_pick_row_for_eval(p), r) else "lost",
                }
            )

        bold_eval = None
        if bold:
            ev = bold["prob"] * bold["odds"] - 1.0
            bold_eval = {
                "market": bold["market"],
                "selection": bold["selection"],
                "selection_label": bold["selection_label"],
                "model_prob": bold["prob"],
                "odds": bold["odds"],
                "ev": round(ev, 4),
                "ev_pct": round(ev * 100, 1),
                "pick_type": "bold",
                "outcome": "won"
                if _evaluate_bet(_pick_row_for_eval(bold), r)
                else "lost",
            }

        if not evaluated and not bold_eval:
            continue

        extras = []
        if r.get("yellows") is not None:
            extras.append(f"{r['yellows']} ЖК")
        if r.get("reds"):
            extras.append(f"{r['reds']} КК")

        groups.append(
            {
                "match_id": match.match_id,
                "match_date": match.date,
                "home_name": match.home.name,
                "away_name": match.away.name,
                "result_score": f"{r['home']}:{r['away']}",
                "result_extras": " · ".join(extras) if extras else None,
                "ev_picks": evaluated,
                "bold_pick": bold_eval,
            }
        )

    groups.sort(key=lambda g: g["match_date"], reverse=True)
    wins = sum(1 for g in groups for p in g["ev_picks"] if p["outcome"] == "won")
    losses = sum(1 for g in groups for p in g["ev_picks"] if p["outcome"] == "lost")

    return {
        "groups": groups,
        "stats": {
            "matches": len(groups),
            "ev_picks": sum(len(g["ev_picks"]) for g in groups),
            "wins": wins,
            "losses": losses,
        },
    }
