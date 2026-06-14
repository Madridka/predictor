"""Match results for auto-resolving bets."""

from __future__ import annotations

import json
from pathlib import Path

RESULTS_PATH = Path(__file__).resolve().parent.parent / "data" / "results.json"


def load_results() -> dict[str, dict]:
    if not RESULTS_PATH.exists():
        return {}
    raw = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    return raw.get("matches", {})


def get_result(match_id: int) -> dict | None:
    return load_results().get(str(match_id))


def save_result(match_id: int, home: int, away: int, status: str = "finished") -> dict:
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    if RESULTS_PATH.exists():
        data = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    else:
        data = {"matches": {}}

    entry = {"home": home, "away": away, "status": status}
    data.setdefault("matches", {})[str(match_id)] = entry
    RESULTS_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return entry
