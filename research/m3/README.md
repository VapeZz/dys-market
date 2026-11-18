# DYS Edge M3 research archive (preserved Nov 18, 2026)
Phase 0 of the research preservation plan (Keo approved Nov 18, 2026, 3:32 PM). Read-only copies of research code,
methods and results. Nothing here runs on its own, changes the site, or calls a paid API. Branch built from commit
0f4b3f06 so the Step 3 file holding TCGplayer website numbers (`tools/m3/step3_scored.json`) is not included.

## What is here
| Item | Where | Rule version / date |
|---|---|---|
| Step 1 Quick Flip backtest code | `tools/m3/pull_days.py`, `quickflip.py`, `recheck.py` | Nov 17, 2026 (approved 8:14 PM) |
| Step 1 results (TCGplayer market prices via tcgcsv) | `research/m3/results/step1_quickflip_result.json` | 89 decision days, 2025-01-01 – 2026-09-09 |
| Step 2 frozen plan + amendment | `tools/m3/STEP2_PLAN.md` | frozen before results; amendment before the 2026 holdout |
| Step 2 replay code, look-ahead test, recheck, audit | `tools/m3/pull_full.py`, `scout_replay.py`, `lookahead_test.py`, `step2_recheck.py`, `step2_audit.py` | Nov 17, 2026 |
| Step 2 results | `tools/m3/step2_dev2025.txt`, `step2_holdout2026.txt`, `step2_audit_result.txt`, `research/m3/results/step2_result_2025_2026.json`, `step2_cases_2025_2026.json.gz` (18,556 list entries, tcgcsv values only) | 2025 dev / 2026 holdout |
| Step 3 method and code (no data) | `tools/m3/STEP3_METHOD.md`, `step3_select.py`, `step3_score.py` | Nov 18, 2026 |
| Step 3 sample (Edge's own Nov 17 lists) | `research/m3/results/step3_sample_edge_lists_2026-11-17.json` | seeded draw 20261118 |
| Near Mint finder code, dry runs 1 and 2 | `research/m3/finder/nm_runner_v1.py`, `nm_runner_v2.py` | v1 Nov 18 12:19 PM; v2 Nov 18 1:45 PM |
| Dry-run summaries (counts only) | `research/m3/results/dryrun1_summary.json`, `dryrun2_summary.json` | runs 44389760899, 44403424361 |
| Price-archive manifest (names, sizes, SHA-256 digests) | `research/m3/results/archive_manifest_2026-11-18.json` | releases as of Nov 18 |

The dispatch-only workflows used for the PkmnPrices test and the dry runs stay on their own branches
(`pkmn-verify-1118`, `nm-finder-dryrun-1118`, `nm-finder-dryrun2-1118`), unchanged.

## Not included on purpose
- PkmnPrices responses of any kind (memory-only rule): no listings, prices, sales or population values.
- TCGplayer website data (its terms forbid automated collection): `step3_scored.json` and the Step 3 CSV stay out.
- Credentials, keys and device hashes (scanned before pushing: none present).

## Could not be recovered
- Dry runs 1 and 2: the per-listing details (which of the 104 / 146 cards hit, listing prices, titles) were deleted
  under the memory-only rule after the reports. Only counts and the cards named in project doc 14 survive.
- PkmnPrices verification test (10 cards): only the derived checks printed in its public log (run 44263625841) survive.
- Step 3 exact TCGplayer page numbers: kept out on purpose; the decisions and reasons are in the private research records.
- Full tcgcsv daily files (lowest / median / direct-low listing) for Oct 12 – Nov 17, 2026 (37 days): our own daily file
  for those days holds market prices only. Recoverable only if tcgcsv still offers those archive days (not checked;
  their site isn't reachable from Claude's workspace).

Card-level research records (decisions, reasons, recheck dates) are kept in the private project doc
`claude/17-research-records.jsonl`, not in this public repository.
