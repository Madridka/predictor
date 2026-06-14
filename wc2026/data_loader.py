"""Data loading and tournament simulation utilities."""

from __future__ import annotations

import json
from pathlib import Path

from wc2026.models import Match, Team

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def load_teams() -> dict[str, Team]:
    raw = json.loads((DATA_DIR / "teams.json").read_text(encoding="utf-8"))
    teams: dict[str, Team] = {}
    for code, info in raw["teams"].items():
        teams[code] = Team(
            code=code,
            name=info["name"],
            fifa_points=float(info["fifa_points"]),
            rank=int(info["rank"]),
            host=bool(info.get("host", False)),
        )
    return teams


def load_matches(teams: dict[str, Team] | None = None) -> list[Match]:
    if teams is None:
        teams = load_teams()
    raw = json.loads((DATA_DIR / "schedule.json").read_text(encoding="utf-8"))
    matches: list[Match] = []
    for m in raw["matches"]:
        matches.append(
            Match(
                match_id=int(m["id"]),
                date=m["date"],
                home=teams[m["home"]],
                away=teams[m["away"]],
                group=m["group"],
                venue=m["venue"],
            )
        )
    return matches


def filter_by_date(matches: list[Match], date: str) -> list[Match]:
    return [m for m in matches if m.date == date]
