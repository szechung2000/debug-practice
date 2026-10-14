# INC-5233: January prepayment speeds look wrong on several non-QM pools

**Severity:** SEV-3 (desk is pricing off these speeds)
**Opened:** 2026-03-03 09:15 ET by the non-agency trading desk
**Service:** `rmbs_speeds` monthly job (pool-level CPR / CDR)

## What the desk sees

After the March 2 run (February remittances), the desk compared our pool speeds
with the trustee's factor-implied speeds:

- About 7 pools show a **January** 1-month CPR that is much higher than the
  number we published last month. Example: SEMT-2023-4-G4 went from 11.8%
  (published in February) to 23.2%.
- The same pools show **February** speeds below the trustee's figures. For
  SEMT-2023-4-G4 our February 3-month CPR is 8.4%; the trustee's factor-implied
  3-month CPR is about 11.5%.
- Other pools look fine.

The job log shows warnings like this:

```
WARNING rmbs_speeds.calc: balance roll break SEMT-2023-4-G4 2026-01: gap 9350371.58
WARNING rmbs_speeds.calc: balance roll break SEMT-2023-4-G4 2026-02: gap 6708750.86
```

## What changed

- On 2026-02-18 the trustee sent a correction file for period 2026-01 (a
  servicer reported payoffs late). This is the first correction file we have
  received since the trustee started to send them. It is in `data/corrections/`.
- The job code has not changed since October.

## Asks

1. Find out why the speeds for these pools are wrong.
2. Fix it with a test. The desk needs correct January and February numbers.
3. Tell us how to make sure the next correction file does not do this again.

## How to reproduce

```bash
python data/generate.py
PYTHONPATH=src python -m rmbs_speeds.cli --summary
PYTHONPATH=src python -m pytest -q tests
```

Output: `data/output/pool_speeds.csv`.
