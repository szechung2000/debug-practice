# cmbs_ingest

Nightly ingestion of CREFC-style loan periodic update (LPU) files for CMBS deals.

```
landing/*.csv + manifest.csv
   -> manifest.read_manifest   (checksums, servicer allow-list)
   -> parser.parse_file        (typed LoanPeriodic records)
   -> transform.run_transform  (current version per loan, rollforward check)
   -> loader.upsert            (replace (deal, period) partitions in the warehouse)
   -> reconcile                (compare to trustee remittance totals)
```

## Run

```bash
python data/generate.py
PYTHONPATH=src python -m cmbs_ingest.cli run [--period YYYYMM ...]
PYTHONPATH=src python -m pytest -q tests
```

Environment: `CMBS_LANDING_DIR`, `CMBS_WAREHOUSE`, `CMBS_RECON_TOLERANCE`, `CMBS_FAIL_ON_BREAK=1`.
