"""Entry point: python -m rmbs_speeds.cli [--strict]"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from . import calc, history, loader, publish
from .config import SpeedsConfig, configure_logging

log = logging.getLogger("rmbs_speeds")


def build_speeds(cfg: SpeedsConfig):
    remits = loader.load_remittances(cfg.remit_dir)
    corrections = loader.load_corrections(cfg.corrections_dir)
    data = loader.apply_corrections(remits, corrections)
    return calc.compute_speeds(data, cfg.windows, cfg.min_balance, cfg.roll_tolerance)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="rmbs_speeds")
    ap.add_argument("--data", help="data dir with remits/ and corrections/ (default: $RMBS_DATA_DIR or data)")
    ap.add_argument("--out", help="output CSV path")
    ap.add_argument("--strict", action="store_true", help="fail if any speed is out of range")
    ap.add_argument("--summary", action="store_true", help="print the latest-period deal summary")
    ap.add_argument("--compare-to", help="snapshot CSV to compare with (default: latest snapshot)")
    ap.add_argument("--no-snapshot", action="store_true", help="do not keep a snapshot of this run")
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args(argv)
    configure_logging(args.log_level)
    cfg = SpeedsConfig.build(args.data, args.out)
    try:
        speeds = build_speeds(cfg)
        previous = Path(args.compare_to) if args.compare_to else history.latest_snapshot(cfg.output_path)
        publish.publish(speeds, cfg.output_path, strict=args.strict)
        history.restatement_report(cfg.output_path, previous)
        if not args.no_snapshot:
            history.save_snapshot(cfg.output_path)
    except (loader.LoadError, publish.PublishError) as exc:
        log.error("run failed: %s", exc)
        return 2
    if args.summary:
        print(publish.latest_period_summary(speeds).to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
