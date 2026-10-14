# clo_compliance

Daily collateral quality and concentration tests for broadly syndicated CLOs.

```
holdings.csv + ratings_history.csv + deals.csv
   -> loaders          (settled positions only, input checks)
   -> RatingsStore     (point-in-time Moody's / S&P ratings, derived ratings)
   -> metrics.run_deal (obligor, industry, CCC excess, defaulted haircut, OC, WARF, WAS)
   -> report           (compliance_YYYYMMDD.csv, exceptions_YYYYMMDD.json)
```

## Run

```bash
python data/generate.py
PYTHONPATH=src python -m clo_compliance.cli --as-of 2026-03-31 [--deal CLO-2019-01]
PYTHONPATH=src python -m pytest -q tests
```
