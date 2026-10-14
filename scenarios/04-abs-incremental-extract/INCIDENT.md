# INC-5390: Auto ABS delinquency buckets do not tie to the servicer after month-end

**Severity:** SEV-2 (monthly servicer report and the trigger tests use these buckets)
**Opened:** 2026-05-02 08:05 ET by Securitization Reporting
**Service:** `abs_cdc` nightly incremental extract (servicer replica -> warehouse)

## What reporting sees

The nightly recon after the 1 May run breaks in almost every delinquency bucket:

```
WARNING abs_cdc.recon: 1-29        source    5796 loans     170505658.14 | warehouse    5481 loans     161141397.52 <-- BREAK
WARNING abs_cdc.recon: CURRENT     source   19646 loans     578115681.99 | warehouse   20017 loans     588999844.46 <-- BREAK
WARNING abs_cdc.recon: REPO        source     107 loans       3151069.43 | warehouse      96 loans       2786309.05 <-- BREAK
INFO    abs_cdc: recon: 8 buckets, 7 breaks
```

The total loan count matches. Loans sit in the wrong bucket: the warehouse
shows them as current when the servicer shows them as delinquent.

## What we know

- The job finished with status OK. No errors, no rejected rows.
- On-call reran the job. The rerun read 0 rows and the breaks stayed.
- Ops says small recon breaks have shown up on the first business day of the
  month before, and that they "fix themselves" within a few days. Nobody
  investigated.
- On 28 April the servicer moved its month-end delinquency roll to a new bulk
  job.

## Asks

1. Find out why the warehouse missed these changes.
2. Fix the extract, with a test.
3. Repair the warehouse for 1 May, and tell us if earlier months need repair.

## How to reproduce

```bash
python data/generate.py        # replica + warehouse as of 30 April, then 1 May activity
PYTHONPATH=src python -m abs_cdc.cli run
PYTHONPATH=src python -m abs_cdc.cli recon
PYTHONPATH=src python -m abs_cdc.cli status
PYTHONPATH=src python -m pytest -q tests
```

`data/source.db` is a copy of the servicer replica (read-only in prod).
`data/warehouse.db` is the warehouse. `python data/generate.py` resets both.
