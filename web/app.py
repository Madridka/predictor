"""Flask web interface for World Cup 2026 +EV bets."""

from __future__ import annotations

import sys
from datetime import date as date_type
from pathlib import Path

from flask import Flask, jsonify, render_template, request

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wc2026.bets_store import (
    VALID_MARKETS,
    create_bet,
    delete_bet,
    get_bet_stats,
    init_bets_db,
    list_bets,
    sync_results_from_file,
    update_guess,
)
from wc2026.data_loader import load_matches
from wc2026.draws_model import calculate_draw_strategy
from wc2026.odds_loader import get_default_stake
from wc2026.results_fetcher import fetch_and_merge_results
from wc2026.risky_scan import scan_positive_ev_picks, scan_retrospective_risky
from wc2026.market_section import (
    ensure_market_forecasts,
    list_market_forecast_cards,
    market_retrospective,
)
from wc2026.market_store import init_market_db
from wc2026.longshot_section import (
    ensure_longshot_forecasts,
    list_longshot_cards,
    longshot_retrospective,
)
from wc2026.longshot_store import init_longshot_db

app = Flask(
    __name__,
    template_folder=str(Path(__file__).parent / "templates"),
    static_folder=str(Path(__file__).parent / "static"),
)


@app.before_request
def _init_once():
    init_bets_db()
    init_market_db()
    init_longshot_db()


@app.get("/")
def index():
    from wc2026.data_loader import load_matches as _load

    dates = sorted({m.date for m in _load()})
    today = date_type.today().isoformat()
    default_date = today if today in dates else (dates[0] if dates else "")

    risky_boot = scan_positive_ev_picks(date=default_date or None)
    risky_retro = scan_retrospective_risky()
    draws_boot = calculate_draw_strategy(stake=get_default_stake())

    return render_template(
        "index.html",
        dates=dates,
        default_date=default_date,
        default_stake=get_default_stake(),
        risky_boot=risky_boot,
        risky_retro=risky_retro,
        draws_boot=draws_boot,
    )


@app.get("/market")
def market_index():
    from wc2026.data_loader import load_matches as _load

    ensure_market_forecasts()
    dates = sorted({m.date for m in _load()})
    today = date_type.today().isoformat()
    default_date = today if today in dates else (dates[0] if dates else "")

    market_boot = list_market_forecast_cards(date=default_date or None)
    market_retro = market_retrospective()

    return render_template(
        "market.html",
        dates=dates,
        default_date=default_date,
        market_boot=market_boot,
        market_retro=market_retro,
    )


@app.get("/longshot")
def longshot_index():
    from wc2026.data_loader import load_matches as _load

    ensure_longshot_forecasts()
    dates = sorted({m.date for m in _load()})
    today = date_type.today().isoformat()
    default_date = today if today in dates else (dates[0] if dates else "")

    longshot_boot = list_longshot_cards(date=default_date or None)
    longshot_retro = longshot_retrospective()

    return render_template(
        "longshot.html",
        dates=dates,
        default_date=default_date,
        longshot_boot=longshot_boot,
        longshot_retro=longshot_retro,
    )


@app.get("/longshot/data/forecasts")
def api_longshot_forecasts():
    ensure_longshot_forecasts()
    date = request.args.get("date") or None
    include_finished = request.args.get("include_finished", "0") == "1"
    return jsonify(
        list_longshot_cards(
            date=date,
            include_finished=include_finished,
        )
    )


@app.get("/longshot/data/retrospective")
def api_longshot_retrospective():
    ensure_longshot_forecasts()
    return jsonify(longshot_retrospective())


@app.post("/longshot/data/sync")
def api_longshot_sync():
    ensure_longshot_forecasts()
    return jsonify(
        {
            "forecasts": list_longshot_cards(include_finished=True),
            "retrospective": longshot_retrospective(),
        }
    )


@app.get("/market/data/forecasts")
def api_market_forecasts():
    ensure_market_forecasts()
    date = request.args.get("date") or None
    include_finished = request.args.get("include_finished", "0") == "1"
    return jsonify(
        list_market_forecast_cards(
            date=date,
            include_finished=include_finished,
        )
    )


@app.get("/market/data/retrospective")
def api_market_retrospective():
    ensure_market_forecasts()
    return jsonify(market_retrospective())


@app.post("/market/data/sync")
def api_market_sync():
    ensure_market_forecasts()
    return jsonify(
        {
            "forecasts": list_market_forecast_cards(include_finished=True),
            "retrospective": market_retrospective(),
        }
    )


@app.get("/data/bets")
def api_bets_list():
    return jsonify(
        {
            "bets": list_bets(is_risky=True),
            "stats": get_bet_stats(is_risky=True),
        }
    )


@app.get("/data/draws")
def api_draws_list():
    stake = request.args.get("stake", type=float, default=get_default_stake())
    if stake <= 0:
        stake = get_default_stake()
    return jsonify(calculate_draw_strategy(stake=stake))


@app.post("/data/bets")
def api_bets_create():
    data = request.get_json(silent=True) or {}
    record, err = _create_bet_from_request(data)
    if err:
        code = 400 if "Обязательные" in err or "market" in err else 404
        return jsonify({"error": err}), code
    return jsonify(record), 201


def _create_bet_from_request(data: dict) -> tuple[dict | None, str | None]:
    required = ["match_id", "market", "selection", "selection_label", "model_prob", "odds"]
    missing = [f for f in required if f not in data]
    if missing:
        return None, f"Обязательные поля: {', '.join(missing)}"

    matches = load_matches()
    match = next((m for m in matches if m.match_id == data["match_id"]), None)
    if not match:
        return None, "Матч не найден"
    if data["market"] not in VALID_MARKETS:
        return None, f"market: {' | '.join(VALID_MARKETS)}"

    record = create_bet(
        {
            "match_id": match.match_id,
            "match_date": match.date,
            "home_code": match.home.code,
            "away_code": match.away.code,
            "home_name": match.home.name,
            "away_name": match.away.name,
            "market": data["market"],
            "selection": data["selection"],
            "selection_label": data["selection_label"],
            "model_prob": data["model_prob"],
            "odds": data["odds"],
            "stake": data.get("stake", get_default_stake()),
            "guess_home": data.get("guess_home"),
            "guess_away": data.get("guess_away"),
            "guess_note": data.get("guess_note"),
            "is_risky": 1,
        }
    )
    return record, None


@app.post("/data/bets/sync")
def api_bets_sync():
    fetch_stats = fetch_and_merge_results()
    synced = sync_results_from_file()
    return jsonify(
        {
            **fetch_stats,
            "synced": synced,
            "bets": list_bets(is_risky=True),
            "stats": get_bet_stats(is_risky=True),
        }
    )


@app.patch("/data/bets/<int:bet_id>")
def api_bets_guess(bet_id: int):
    data = request.get_json(silent=True) or {}
    gh = data.get("guess_home")
    ga = data.get("guess_away")
    if gh is None and ga is None:
        return jsonify({"error": "Укажите guess_home и guess_away"}), 400
    bet = update_guess(
        bet_id,
        int(gh) if gh is not None and gh != "" else None,
        int(ga) if ga is not None and ga != "" else None,
    )
    if not bet:
        return jsonify({"error": "Ставка не найдена"}), 404
    return jsonify(bet)


@app.delete("/data/bets/<int:bet_id>")
def api_bets_delete(bet_id: int):
    if delete_bet(bet_id):
        return jsonify({"ok": True})
    return jsonify({"error": "Ставка не найдена"}), 404


@app.get("/data/risky")
def api_risky_list():
    date = request.args.get("date")
    min_odds = request.args.get("min_odds", type=float, default=1.65)
    min_ev = request.args.get("min_ev", type=float, default=0.0)
    if min_odds < 1.65:
        min_odds = 1.65
    return jsonify(
        scan_positive_ev_picks(
            date=date or None,
            min_odds=min_odds,
            min_ev=min_ev,
        )
    )


@app.get("/data/risky/retrospective")
def api_risky_retrospective():
    min_odds = request.args.get("min_odds", type=float, default=1.65)
    min_ev = request.args.get("min_ev", type=float, default=0.0)
    if min_odds < 1.65:
        min_odds = 1.65
    return jsonify(scan_retrospective_risky(min_odds=min_odds, min_ev=min_ev))


if __name__ == "__main__":
    init_bets_db()
    init_market_db()
    init_longshot_db()
    print("WC2026 +EV: http://127.0.0.1:5000")
    app.run(debug=True, host="127.0.0.1", port=5000)
