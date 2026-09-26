# Functional repository layout

Use `dataset/` for construction, `training/` for SFT, `evaluation/` for held-out inference/scoring, `experiments/` for diagnostic research, `docs/` for protocols, and `results/` for aggregate tables. `artifacts/` contains frozen benchmark/training records; `tools/` contains portable utilities.

## Migration map

| Former code location | Current location |
|---|---|
| `SpaceConflict/` | `dataset/` |
| `phase4/` | `experiments/spatial_world_state/` |
| `phase5/` | `experiments/behavioral_closure/` |
| `phase6/` | `experiments/sequential_state/` |
| `phase7/` | `experiments/state_interventions/` |
| `phase8/` training/preparation code | `training/` |
| `phase8/heldout_test_v1/` | `evaluation/heldout_test_v1/` |
| `phase8/heldout_test_full_pss_v1/` | `evaluation/heldout_test_full_pss_v1/` |
| `phase8/label_rescore_v2/` | `evaluation/label_rescore_v2/` |
| `phase8/label_rescore_v3/` | `evaluation/label_rescore_v3/` |
| `tools/score.py` implementation | `evaluation/score.py`; old command remains a wrapper |

## What did not change

Requests/gold, train/dev/test records, supervision targets, frozen schedules/exposure records, aggregate results and prior verification JSON files retain their original bytes. Construction release files moved with their directory without content changes. No model outputs were regenerated; metric definitions and parser decisions are unchanged.

Historical records can still contain old paths, run IDs, hashes or internal stage names. They are evidence of original runs, not instructions for the new layout. They are not rewritten to pretend that a past freeze applies to relocated code. Resolve code paths using the map, then create a separate new local freeze before fresh GPU work.

`provenance/EXPORT_MANIFEST.json` tracks current locations/export hashes while retaining source hashes. `provenance/LAYOUT_MIGRATION.json` records the mapping. `verification/LAYOUT_ACCEPTANCE.json` records actual CPU checks and scoring equivalence. Original research directories and earlier public commits are preserved; history is not force-rewritten.

## Reproduction boundaries

CPU data validation, label scoring and sampler/parser regression tests are supported. Some legacy construction tests and diagnostic runs require intentionally unbundled discovery reports or diagnostic data. GPU training, every model adapter and all historical experiments have not been rerun during cleanup. See [PORTABILITY.md](PORTABILITY.md).
