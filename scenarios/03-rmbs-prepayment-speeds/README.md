# rmbs_speeds

Pool-level prepayment (SMM / CPR) and default (MDR / CDR) speeds for non-agency RMBS.

```
remits/<deal>_<YYYYMM>.csv + corrections/correction_<YYYYMM>_<sent>.csv
   -> loader.load_remittances / load_corrections / apply_corrections
   -> calc.compute_speeds   (beginning balance, monthly rates, trailing windows, roll check)
   -> publish.publish       (range checks, data/output/pool_speeds.csv)
```

## Run

```bash
python data/generate.py
PYTHONPATH=src python -m rmbs_speeds.cli [--strict] [--summary]
PYTHONPATH=src python -m pytest -q tests
```
