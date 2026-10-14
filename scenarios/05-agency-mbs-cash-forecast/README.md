# mbs_cash

Daily forecast of agency MBS principal and interest (UMBS, Freddie Gold, Ginnie I / II) for Treasury.

```
positions.csv + factors.csv + fed_holidays.csv
   -> inputs          (CUSIP checks, 8-decimal factors)
   -> cashflow        (factor path with projections, P&I, payment date per program)
   -> forecast        (detail and daily totals, business-day check)
```

## Run

```bash
python data/generate.py
PYTHONPATH=src python -m mbs_cash.cli --as-of 2026-12-18 [--horizon 3] [--print]
PYTHONPATH=src python -m pytest -q tests
```
