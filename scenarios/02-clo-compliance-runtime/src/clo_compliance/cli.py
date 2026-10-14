"""Entry point: python -m clo_compliance.cli --as-of YYYY-MM-DD"""
from __future__ import annotations

import argparse
import logging
import sys
import time

from . import loaders, metrics, report
from .config import JobConfig, configure_logging
from .ratings import RatingsStore

log = logging.getLogger("clo_compliance")


def run(cfg: JobConfig, deal_filter: set[str] | None = None) -> list[metrics.DealResult]:
    t0 = time.perf_counter()
    holdings = loaders.load_holdings(cfg.holdings_path, cfg.as_of)
    ratings = loaders.load_ratings(cfg.ratings_path)
    deals = loaders.load_deals(cfg.deals_path)
    store = RatingsStore(ratings, cfg.as_of)
    log.info("inputs loaded in %.1fs", time.perf_counter() - t0)

    results = []
    for deal_id, positions in holdings.groupby("deal_id", sort=True):
        if deal_filter and deal_id not in deal_filter:
            continue
        if deal_id not in deals.index:
            log.error("deal %s has holdings but no capital structure; skipped", deal_id)
            continue
        t_deal = time.perf_counter()
        cap = deals.loc[deal_id]
        res = metrics.run_deal(str(deal_id), positions, store, float(cap["senior_notes"]),
                               float(cap["oc_trigger"]), cfg.limits)
        results.append(res)
        log.info("deal %s: %d positions, OC %.2f%%, CCC %.2f%%, WARF %.0f (%.1fs)",
                 deal_id, res.positions, res.oc_ratio, res.ccc_pct, res.warf, time.perf_counter() - t_deal)

    report.write_results(results, cfg.output_dir, cfg.as_of)
    report.write_exceptions(results, cfg.output_dir, cfg.as_of)
    log.info("done: %d deals, %d rating lookups, %.1fs total",
             len(results), store.lookups, time.perf_counter() - t0)
    return results


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="clo_compliance")
    ap.add_argument("--as-of", required=True, help="run date, YYYY-MM-DD")
    ap.add_argument("--data", help="input dir (default: $CLO_DATA_DIR or data/input)")
    ap.add_argument("--out", help="output dir (default: $CLO_OUTPUT_DIR or data/output)")
    ap.add_argument("--deal", action="append", help="limit to one deal; repeatable")
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args(argv)
    configure_logging(args.log_level)
    cfg = JobConfig.build(args.data, args.out, args.as_of)
    try:
        run(cfg, set(args.deal) if args.deal else None)
    except loaders.InputError as exc:
        log.error("run aborted: %s", exc)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
