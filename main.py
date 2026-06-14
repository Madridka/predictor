#!/usr/bin/env python3
"""
FIFA World Cup 2026 — математический прогнозатор исходов матчей.

Модели:
  • FIFA Elo (официальная формула We с 2018)
  • Poisson + Dixon-Coles (коррекция низких счётов 0:0, 1:0, 0:1, 1:1)
  • Ансамбль 65% Poisson / 35% Elo для 1X2

Данные: рейтинг FIFA от 11.06.2026, расписание группового этапа.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from wc2026.data_loader import filter_by_date, load_matches
from wc2026.display import render_prediction
from wc2026.models import predict_match


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Прогноз исходов матчей ЧМ-2026 (Poisson + Dixon-Coles + FIFA Elo)"
    )
    parser.add_argument(
        "--date",
        default=date.today().isoformat(),
        help="Дата матчей (YYYY-MM-DD), по умолчанию — сегодня",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Показать все матчи из расписания (не только за дату)",
    )
    parser.add_argument(
        "--match",
        type=int,
        metavar="ID",
        help="Прогноз для конкретного матча по ID",
    )
    args = parser.parse_args()

    matches = load_matches()

    if args.match is not None:
        selected = [m for m in matches if m.match_id == args.match]
        if not selected:
            print(f"Матч #{args.match} не найден.", file=sys.stderr)
            return 1
    elif args.all:
        selected = matches
    else:
        selected = filter_by_date(matches, args.date)
        if not selected:
            print(f"Нет матчей на {args.date}. Используйте --all или другую --date.")
            return 0

    print(f"\nFIFA World Cup 2026 — Прогноз ({len(selected)} матч(ей))\n")
    for match in selected:
        pred = predict_match(match)
        print(render_prediction(pred))
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
