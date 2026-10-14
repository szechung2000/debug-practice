# INC-4471: Dec-2025 trustee recon breaks on two CMBS deals

**Severity:** SEV-3 (investor reporting at risk)
**Opened:** 2026-01-12 08:40 ET by Investor Reporting
**Service:** `cmbs_ingest` nightly job (loan periodic update ingestion)

## What the reporting team sees

The trustee reconciliation for determination period **202512** breaks on two deals:

```
WARNING cmbs_ingest.reconcile: RECON BREAK BANK5-2024-5YR8 202512: loans 44 vs 44, ending balance 2295727144.76 vs trustee 2290193163.52 (variance 5533981.24)
WARNING cmbs_ingest.reconcile: RECON BREAK BMARK-2024-V9 202512: loans 41 vs 41, ending balance 1761622691.13 vs trustee 1756652812.18 (variance 4969878.95)
```

Loan counts match. Only the balances are off. Our numbers are **higher** than the trustee's.

The investor reporting package for both deals goes out on 2026-01-15.

## What we know

- Midland and Wells sent restated 202512 files last week. Both files are in the
  landing zone and in the manifest. The collector logs show they arrived.
- On-call reran the job twice for `--period 202512`. Same breaks both times.
- WFCM-2023-C61 had a restatement for 202511 last month. That one reconciled
  with no issue and nobody touched the job.
- No code deploys to `cmbs_ingest` since 2025-11-20.

## Asks

1. Find out why the warehouse does not match the trustee for these deals.
2. Fix it, with a test, before the 15th.
3. Tell us which other deals or periods could be affected, and whether we need a backfill.

## How to reproduce

```bash
python data/generate.py               # rebuilds the landing zone (local copy of prod files)
PYTHONPATH=src python -m cmbs_ingest.cli run --period 202512
PYTHONPATH=src python -m pytest -q tests
```

The warehouse is `data/warehouse.db` (SQLite). Table: `loan_periodic`.
