"""Автозаполнение архива по всему расписанию."""

from __future__ import annotations

from wc2026.api import get_prediction_json
from wc2026.archive_store import (
    add_picks,
    cleanup_archive_below_odds,
    get_archived_match_ids,
    upsert_best_value_pick,
)
from wc2026.data_loader import filter_by_date, load_matches
from wc2026.picks_extractor import (
    DEFAULT_MIN_ODDS,
    best_value_as_archive_pick,
    extract_top_picks,
)


def sync_best_value_picks(date: str | None = None) -> dict:
    """Сохранить «наиболее вероятный прогноз» для каждого матча."""
    matches = load_matches()
    if date:
        matches = filter_by_date(matches, date)

    updated = 0
    for match in matches:
        pred = get_prediction_json(match)
        pick = best_value_as_archive_pick(pred)
        if upsert_best_value_pick(pick, match.match_id):
            updated += 1

    return {"best_value_updated": updated}


def sync_schedule_to_archive(
    min_odds: float = DEFAULT_MIN_ODDS,
    *,
    only_missing: bool = True,
    date: str | None = None,
) -> dict:
    """Добавить в архив лидеров по каждому рынку для матчей расписания."""
    matches = load_matches()
    if date:
        matches = filter_by_date(matches, date)

    cleanup_archive_below_odds(min_odds)

    if only_missing:
        archived = get_archived_match_ids()
        matches = [m for m in matches if m.match_id not in archived]

    all_picks: list[dict] = []
    for match in matches:
        pred = get_prediction_json(match)
        all_picks.extend(extract_top_picks(pred, min_odds=min_odds))

    result = add_picks(all_picks)
    bv = sync_best_value_picks(date=date)
    return {
        **result,
        **bv,
        "matches_scanned": len(matches),
        "picks_found": len(all_picks),
    }
