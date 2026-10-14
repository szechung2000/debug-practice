"""Entry points:
    python -m crt_perf.cli load    --deal CAS-2024-R03 --period 2026-09
    python -m crt_perf.cli verify  --deal CAS-2024-R03 --period 2026-09
    python -m crt_perf.cli summary --deal CAS-2024-R03
    python -m crt_perf.cli runs
"""
from __future__ import annotations

import argparse
import logging
import re
import sys
from contextlib import closing

from . import loader, store
from .config import LoadConfig, configure_logging

log = logging.getLogger("crt_perf")
PERIOD_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def cmd_load(cfg: LoadConfig, deal: str, period: str) -> int:
    result = loader.load_partition(cfg, deal, period)
    if not result.ok:
        log.error("load incomplete: fix the file and rerun the same command (the partition is replaced)")
        return 1
    stats = loader.verify_partition(cfg, deal, period)
    if not stats["complete"]:
        log.error("verify failed: %d loans in store, %d in file", stats["loans"], stats["file_rows"])
        return 1
    log.info("verify ok: %d loans, UPB %.2f, 60+ DQ %.3f%%", stats["loans"], stats["upb"], stats["dq60_pct"])
    return 0


def cmd_summary(cfg: LoadConfig, deal: str) -> None:
    with closing(store.connect(cfg.store_path)) as conn:
        periods = [r[0] for r in conn.execute(
            "SELECT DISTINCT reporting_period FROM loan_performance WHERE deal_id = ? ORDER BY 1", (deal,))]
        print(f"{'period':<11} {'rows':>7} {'loans':>7} {'UPB':>18} {'60+ DQ %':>9} {'events':>7} {'est. loss':>14}")
        for p in periods:
            s = store.partition_stats(conn, deal, p)
            print(f"{p:<11} {s['rows']:>7} {s['loans']:>7} {s['upb']:>18,.2f} {s['dq60_pct']:>9.3f} "
                  f"{s['credit_events']:>7} {s['estimated_loss']:>14,.2f}")


def cmd_runs(cfg: LoadConfig) -> None:
    with closing(store.connect(cfg.store_path)) as conn:
        for row in conn.execute("SELECT run_id, deal_id, period, file_rows, loaded_rows, chunks_failed, status, "
                                "started_at FROM load_runs ORDER BY started_at"):
            print(" ", row)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="crt_perf")
    ap.add_argument("cmd", choices=["load", "verify", "summary", "runs"])
    ap.add_argument("--deal")
    ap.add_argument("--period", help="YYYY-MM")
    ap.add_argument("--inbound")
    ap.add_argument("--store")
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args(argv)
    configure_logging(args.log_level)
    cfg = LoadConfig.from_env(args.inbound, args.store)
    if args.cmd in ("load", "verify") and not (args.deal and args.period and PERIOD_RE.match(args.period)):
        ap.error("load/verify need --deal and --period YYYY-MM")
    try:
        if args.cmd == "load":
            return cmd_load(cfg, args.deal, args.period)
        if args.cmd == "verify":
            stats = loader.verify_partition(cfg, args.deal, args.period)
            print(stats)
            return 0 if stats["complete"] else 1
        if args.cmd == "summary":
            if not args.deal:
                ap.error("summary needs --deal")
            cmd_summary(cfg, args.deal)
        else:
            cmd_runs(cfg)
    except loader.LoadError as exc:
        log.error("%s", exc)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
