# INC-5108: CLO compliance job misses the 06:30 SLA

**Severity:** SEV-2 (portfolio managers trade without compliance numbers)
**Opened:** 2026-04-01 06:45 ET by the CLO portfolio management desk
**Service:** `clo_compliance` daily job

## What the desk sees

The daily compliance file (`compliance_YYYYMMDD.csv`) and the exceptions list
were not ready at 06:30. The job finished at 10:12.

Run time history (production, same 16-core box):

| Run date | Deals | Positions | Ratings history rows | Run time |
|---|---|---|---|---|
| 2026-01-30 | 9 | 3,900 | 6,800 | 6 min |
| 2026-02-27 | 14 | 6,800 | 11,500 | 21 min |
| 2026-03-31 | 22 | 11,200 | 20,500 | 3 h 52 min |

The book grew because we onboarded new deals. The ratings vendor also moved us
from a monthly delta to the full rating-action history.

## Constraints

- The numbers must not change. Trustees reconcile against this logic every
  month. Any change in OC ratio, CCC %, WARF or the exceptions list is a defect.
- The job reruns earlier dates for corrections (`--as-of` in the past). The
  rating used must be the one in force on the run date.
- The platform team says "just run the deals in parallel on a bigger box".
  The desk wants to know if that is the right fix.

## Asks

1. Find where the time goes.
2. Bring the run time down so that it scales with the book. Target: under 10 s
   locally on the production-sized data in this folder.
3. Prove that the output is identical before and after.

## How to reproduce

```bash
python data/generate.py                      # production-sized inputs (22 deals)
python data/generate.py --small --out data/small   # 3 deals, quick loop
PYTHONPATH=src python -m clo_compliance.cli --as-of 2026-03-31
PYTHONPATH=src python -m pytest -q tests
```

Locally the full run takes about 2 minutes. Output goes to `data/output/`.
