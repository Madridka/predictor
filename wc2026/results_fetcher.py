"""Загрузка итогов матчей ЧМ-2026 с ESPN (без API-ключа)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import date

from wc2026.data_loader import load_matches
from wc2026.results_loader import RESULTS_PATH, load_results

ESPN_SCOREBOARD = (
    "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard"
)

# Редкие расхождения аббревиатур ESPN ↔ FIFA
ESPN_TO_FIFA: dict[str, str] = {}


def _parse_cards(details: list[dict], home_team_id: str | None) -> tuple[int, int, int]:
    yellow_home = yellow_away = reds = 0
    for detail in details:
        tid = detail.get("team", {}).get("id")
        if detail.get("yellowCard"):
            if tid == home_team_id:
                yellow_home += 1
            else:
                yellow_away += 1
        if detail.get("redCard"):
            reds += 1
    return yellow_home, yellow_away, reds


def _fetch_espn_events(iso_date: str) -> list[dict]:
    ymd = iso_date.replace("-", "")
    url = f"{ESPN_SCOREBOARD}?dates={ymd}"
    req = urllib.request.Request(url, headers={"User-Agent": "WC2026-Predictor/1.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data.get("events", [])


def _result_from_competition(comp: dict) -> dict | None:
    if not comp.get("status", {}).get("type", {}).get("completed"):
        return None

    home_code = away_code = None
    home_score = away_score = None
    home_team_id = None

    for team in comp.get("competitors", []):
        abbr = team.get("team", {}).get("abbreviation")
        if not abbr:
            continue
        code = ESPN_TO_FIFA.get(abbr, abbr)
        score_raw = team.get("score")
        if score_raw is None or score_raw == "":
            return None
        score = int(score_raw)
        if team.get("homeAway") == "home":
            home_code, home_score, home_team_id = code, score, team.get("team", {}).get("id")
        else:
            away_code, away_score = code, score

    if home_code is None or away_code is None:
        return None

    details = comp.get("details") or []
    yellow_home, yellow_away, reds = _parse_cards(details, home_team_id)

    entry: dict = {
        "home": home_score,
        "away": away_score,
        "status": "finished",
    }
    if yellow_home or yellow_away:
        entry["yellow_home"] = yellow_home
        entry["yellow_away"] = yellow_away
        entry["yellows"] = yellow_home + yellow_away
    if reds:
        entry["reds"] = reds
    entry["_pair"] = (home_code, away_code)
    return entry


def _dates_to_check(dates: list[str] | None) -> list[str]:
    if dates:
        return sorted(set(dates))
    today = date.today().isoformat()
    return sorted({m.date for m in load_matches() if m.date <= today})


def fetch_and_merge_results(dates: list[str] | None = None) -> dict:
    """Подтянуть завершённые матчи с ESPN в data/results.json."""
    by_pair = {(m.home.code, m.away.code): m for m in load_matches()}
    check_dates = _dates_to_check(dates)
    existing = load_results()
    fetched = 0
    errors: list[str] = []

    for iso_date in check_dates:
        try:
            events = _fetch_espn_events(iso_date)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            errors.append(f"{iso_date}: {exc}")
            continue

        for event in events:
            comp = event.get("competitions", [{}])[0]
            parsed = _result_from_competition(comp)
            if not parsed:
                continue

            pair = parsed.pop("_pair")
            match = by_pair.get(pair)
            if not match:
                continue

            mid = str(match.match_id)
            prev = existing.get(mid)
            if prev == parsed:
                continue
            existing[mid] = parsed
            fetched += 1

    payload = {"matches": existing}
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return {
        "results_fetched": fetched,
        "dates_checked": len(check_dates),
        "errors": errors,
    }
