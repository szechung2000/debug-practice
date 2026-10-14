"""Entry point: python -m cmbs_ingest.cli run [--period YYYYMM ...]"""
from __future__ import annotations

import argparse
import logging
import sys
import uuid
from contextlib import closing

from . import loader, manifest, parser, reconcile, transform
from .config import IngestConfig, configure_logging

log = logging.getLogger("cmbs_ingest")


def run(cfg: IngestConfig, periods: set[str] | None) -> int:
    run_id = uuid.uuid4().hex[:12]
    log.info("run %s: landing=%s warehouse=%s periods=%s",
             run_id, cfg.landing_dir, cfg.warehouse_path, sorted(periods) if periods else "all")
    entries = manifest.filter_periods(manifest.read_manifest(cfg.manifest_path, cfg.accepted_servicers), periods)
    if not entries:
        log.warning("nothing to load")
        return 0

    # Restatements only make sense next to the original copy: always parse
    # every file for a (deal, period) that is in scope.
    records: list[parser.LoanPeriodic] = []
    for entry in sorted(entries, key=lambda e: e.file_name):
        records.extend(parser.parse_file(entry, cfg.required_columns))
    log.info("parsed %d records from %d files", len(records), len(entries))

    rows, stats = transform.run_transform(records)
    with closing(loader.connect(cfg.warehouse_path)) as conn:
        loader.upsert(conn, rows, run_id)

    results = reconcile.reconcile(rows, reconcile.read_trustee(cfg.trustee_path))
    breaks = reconcile.report(results, cfg.recon_tolerance)
    log.info("run %s finished: %d rows, %d recon checks, %d breaks", run_id, len(rows), len(results), breaks)
    if breaks and cfg.fail_on_recon_break:
        log.error("failing the run: %d recon breaks and CMBS_FAIL_ON_BREAK=1", breaks)
        return 3
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="cmbs_ingest")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="ingest landing-zone files into the warehouse")
    r.add_argument("--landing", help="landing directory (default: $CMBS_LANDING_DIR or data/landing)")
    r.add_argument("--warehouse", help="SQLite path (default: $CMBS_WAREHOUSE or data/warehouse.db)")
    r.add_argument("--period", action="append", help="YYYYMM determination period; repeatable")
    r.add_argument("--log-level", default="INFO")
    args = ap.parse_args(argv)
    configure_logging(args.log_level)
    cfg = IngestConfig.from_env(args.landing, args.warehouse)
    try:
        return run(cfg, set(args.period) if args.period else None)
    except (manifest.ManifestError, parser.ParseError) as exc:
        log.error("run aborted: %s", exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
