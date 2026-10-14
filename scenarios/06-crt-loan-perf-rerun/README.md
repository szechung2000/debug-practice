# crt_perf

Monthly loan-level performance load for credit risk transfer deals (Fannie Mae CAS, Freddie Mac STACR).

```
inbound/<deal>_<YYYYMM>.txt (pipe-delimited)
   -> loader.load_partition   (replace the (deal, period) partition; chunks parsed and inserted in parallel)
      -> reader.parse_line    (vendor layout, validation)
      -> transform.enrich     (DQ bucket, events, estimated loss vs prior UPB)
   -> loader.verify_partition (post-load completeness check)
```

## Run

```bash
python data/generate.py
PYTHONPATH=src python -m crt_perf.cli load|verify --deal CAS-2024-R03 --period 2026-09
PYTHONPATH=src python -m crt_perf.cli summary --deal CAS-2024-R03
PYTHONPATH=src python -m pytest -q tests
```

Environment: `CRT_INBOUND_DIR`, `CRT_STORE`, `CRT_CHUNK_SIZE`, `CRT_WORKERS`.
