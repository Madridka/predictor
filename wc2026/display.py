"""CLI output formatting for match predictions."""

from __future__ import annotations

from wc2026.models import MatchPrediction, ensemble_1x2, format_pct


def render_prediction(pred: MatchPrediction) -> str:
    m = pred.match
    eh, ed, ea = ensemble_1x2(
        pred.prob_home_win,
        pred.prob_draw,
        pred.prob_away_win,
        m.home,
        m.away,
    )

    lines = [
        f"{'=' * 64}",
        f"Матч #{m.match_id} | Группа {m.group} | {m.date} | {m.venue}",
        f"{m.home.name} vs {m.away.name}",
        f"FIFA: {m.home.fifa_points:.0f} (#{m.home.rank}) — {m.away.fifa_points:.0f} (#{m.away.rank})",
        f"{'-' * 64}",
        "МОДЕЛЬ: Dixon-Coles Poisson + FIFA Elo (ансамбль 65/35)",
        f"  λ дома: {pred.lambda_home:.2f}  |  λ гостей: {pred.lambda_away:.2f}  |  E[тотал]: {pred.expected_total:.2f}",
        "",
        "ИСХОД МАТЧА (1X2):",
        f"  П1 ({m.home.code}): {format_pct(eh)}",
        f"  X  (ничья):       {format_pct(ed)}",
        f"  П2 ({m.away.code}): {format_pct(ea)}",
        "",
        "ТОТАЛ ГОЛОВ:",
        f"  Больше 1.5: {format_pct(pred.totals['over_1.5'])}  |  Меньше 1.5: {format_pct(pred.totals['under_1.5'])}",
        f"  Больше 2.5: {format_pct(pred.totals['over_2.5'])}  |  Меньше 2.5: {format_pct(pred.totals['under_2.5'])}",
        f"  Больше 3.5: {format_pct(pred.totals['over_3.5'])}  |  Меньше 3.5: {format_pct(pred.totals['under_3.5'])}",
        "",
        "ОБЕ ЗАБЬЮТ (ОЗ):",
        f"  Да: {format_pct(pred.oz['yes'])}  |  Нет: {format_pct(pred.oz['no'])}",
        "",
        "ТОП-5 ТОЧНЫХ СЧЁТОВ:",
    ]
    for h, a, p in pred.top_scores:
        lines.append(f"  {h}:{a} — {format_pct(p)}")
    lines.append(f"{'=' * 64}")
    return "\n".join(lines)
