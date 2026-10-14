# abs_cdc

Nightly incremental extract of auto ABS loans from the servicer replica into the warehouse.

```
source.db (loans, updated_at)
   -> SourceClient.iter_changes   (pages of changed rows after the watermark)
   -> transform.transform_page    (amounts, delinquency bucket, validation)
   -> warehouse.merge_rows        (upsert current state, status history; watermark per page)
   -> recon                       (counts and balances by bucket vs the replica)
```

## Run

```bash
python data/generate.py
PYTHONPATH=src python -m abs_cdc.cli run | recon | status
PYTHONPATH=src python -m pytest -q tests
```

Environment: `ABS_SOURCE_DB`, `ABS_WAREHOUSE_DB`, `ABS_PAGE_SIZE` (default 5000).
