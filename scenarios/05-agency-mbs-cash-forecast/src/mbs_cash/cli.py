"""Entry point: python -m mbs_cash.cli --as-of YYYY-MM-DD [--horizon N]"""
from __future__ import annotations

import argparse
import logging
import sys

from . import forecast, inputs
from .calendar import BusinessCalendar, CalendarError
from .config import ForecastConfig, configure_logging

log = logging.getLogger("mbs_cash")


def run(cfg: ForecastConfig):
    cal = BusinessCalendar.from_csv(cfg.holidays_path)
    positions = inputs.load_positions(cfg.positions_path)
    factors = inputs.load_factors(cfg.factors_path)
    flows = forecast.build(positions, factors, cfg, cal)
    for problem in forecast.check_dates(flows, cal):
        log.error(problem)
    forecast.write(flows, cfg.output_dir, cfg.as_of)
    return flows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="mbs_cash")
    ap.add_argument("--as-of", required=True)
    ap.add_argument("--horizon", type=int, help="payment months to forecast (default 3)")
    ap.add_argument("--data")
    ap.add_argument("--out")
    ap.add_argument("--print", action="store_true", help="print daily totals")
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args(argv)
    configure_logging(args.log_level)
    cfg = ForecastConfig.build(args.data, args.out, args.as_of, args.horizon)
    try:
        flows = run(cfg)
    except (inputs.InputError, CalendarError) as exc:
        log.error("run failed: %s", exc)
        return 2
    if args.print:
        for row in forecast.daily_totals(flows):
            print(f"{row['payment_date']} {row['weekday']}  {row['account']:<10} {row['total']:>18}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
