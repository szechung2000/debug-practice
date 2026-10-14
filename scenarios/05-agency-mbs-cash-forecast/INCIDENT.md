# INC-5502: MBS cash forecast puts P&I on days when Fedwire is closed

**Severity:** SEV-2 (Treasury funds overnight positions from this forecast)
**Opened:** 2026-12-18 07:50 ET by Treasury Operations
**Service:** `mbs_cash` daily forecast (agency MBS principal and interest)

## What Treasury sees

The forecast that ran this morning (`--as-of 2026-12-18`) expects UMBS P&I of
about $13.8m across the four accounts on **Friday 25 December** (Christmas). Fedwire is
closed. The money will arrive on Monday 28 December. Treasury had planned to
use it to cover a repo maturity on the 28th and almost moved funds early.

The forecast for February also shows Ginnie Mae I and Freddie Gold cash on
**Monday 15 February 2027** (Washington's Birthday).

The job log has these lines, but the job does not fail:

```
ERROR   mbs_cash: payment date 2026-12-25 (Fri) is not a business day
ERROR   mbs_cash: payment date 2027-02-15 (Mon) is not a business day
```

## What we know

- Weekend dates roll correctly (for example GNMA II 20 Dec 2026 -> Monday 21 Dec).
- The Fed holiday file for 2026-2027 was loaded last month. On-call checked:
  25 Dec 2026 and 15 Feb 2027 are in it.
- Last year nobody noticed, because 25 December 2025 was a Thursday and the
  forecast was reviewed by hand over the holidays.

## Asks

1. Find out why holidays are ignored.
2. Fix it with a test.
3. Tell us if any other output or other job could have the same problem.

## How to reproduce

```bash
python data/generate.py
PYTHONPATH=src python -m mbs_cash.cli --as-of 2026-12-18 --print
PYTHONPATH=src python -m pytest -q tests
```

Outputs: `data/output/mbs_cash_detail_*.csv`, `data/output/mbs_cash_daily_*.csv`.
