# research-db-test-1119 — disposable test branch (do not merge)

Orphan branch for testing the DYS Pokémon research database storage split (approved Nov 18, 2026, 10:53 PM).
It shares no history with `main` and holds only test code, a public-safe catalog and one workflow.

- `research/rdbpub.py` — public part: catalog + tcgcsv-derived daily prices (market/low/mid/high/direct low), presence and gaps, provenance.
- `research/private_schema.py`, `research/vault.py` — private part schema and encryption. **No private data or keys are in this branch.**
- `research/nightly.py` — snapshots as release assets in a **draft** release whose name starts with `research-db-test`; append-only names; pointer files.
- `research/leakscan.py` — scanner for files, logs and artifacts.
- `research/tests/` — synthetic private tests; public storage scenarios (interrupted upload, missed days, rerun, corrupt archive/extract/snapshot, unarchived day, restore, rebuild equivalence, leak scan).
- `research/catalog/catalog-2026-11-18.jsonl.gz` — 83,166 public identities (English + Japanese; the pending research identity is not here).

Nothing here is production. No schedule; it runs only when this branch is pushed.
