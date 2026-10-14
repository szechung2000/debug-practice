# INC-5617: CAS-2024-R03 September UPB almost doubled after the rerun

**Severity:** SEV-2 (credit risk transfer surveillance and loss reporting)
**Opened:** 2026-10-07 10:20 ET by CRT Surveillance
**Service:** `crt_perf` monthly loan-level performance load

## What surveillance sees

The September dashboard for CAS-2024-R03 shows a total UPB of about
**$25.3bn**. August was about $13.9bn. The deal cannot grow. The 60+
delinquency rate and the loss numbers also moved in ways that make no sense.
STACR-2025-DNA2 looks normal.

## What happened

1. 2026-10-06 06:00: the September load for CAS-2024-R03 failed. The log said
   one chunk had a bad record (zero balance code `0l`). The run is `FAILED` in
   `load_runs`.
2. The vendor sent a corrected file at 09:10.
3. On-call reran the documented command:
   `python -m crt_perf.cli load --deal CAS-2024-R03 --period 2026-09`
4. The rerun finished `OK` and the post-load verify passed:
   ```
   INFO crt_perf: verify ok: 30917 loans, UPB 25293354291.21, 60+ DQ 3.449%
   ```

The runbook says a rerun is safe because the job replaces the partition.

## Asks

1. Find out why the rerun produced these numbers, and why the verify passed.
2. Fix the job, with tests.
3. Repair the September partition and tell us whether any other partition
   needs repair.

## How to reproduce

```bash
python data/generate.py     # store as of the failed run + the corrected vendor file
PYTHONPATH=src python -m crt_perf.cli runs
PYTHONPATH=src python -m crt_perf.cli load --deal CAS-2024-R03 --period 2026-09
PYTHONPATH=src python -m crt_perf.cli summary --deal CAS-2024-R03
PYTHONPATH=src python -m pytest -q tests
```

The store is `data/crt_store.db` (SQLite). Vendor files are in `data/inbound/`.
