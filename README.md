# Seeing, Saying, but Not Using: From Reportable Spatial Facts to Usable States in Multimodal Models

**SpaceConflict**: code, benchmark questions and public gold, training supervision, and aggregate results for a four-level spatial-conflict benchmark and structured-state fine-tuning.

The project's original code and authored documentation are MIT licensed. Dataset records and third-party dependencies are governed separately; see [DATA_TERMS.md](DATA_TERMS.md). Source images/videos and model weights are not included. MIT does not override upstream data terms or establish redistribution clearance for source-derived annotations.

This repository is hosted publicly under `changcv2021`; it is not anonymous hosting. Personal filesystem paths, private endpoints, credentials and prior Git history are excluded from this exported copy. The original research archive is not published here.

## What is included

| Location | Content |
|---|---|
| `SpaceConflict/src/spaceconflict/` | Construction, source adapters, graphs, transformations and verifiers |
| `SpaceConflict/contracts/`, `schemas/`, `operators/` | Versioned construction rules |
| `SpaceConflict/scripts/` | Existing acquisition, media preparation and multi-model evaluation implementations |
| `phase8/formal_training_v4/` | Actual five-method, two-seed, update-matched training implementation |
| `phase8/pss_full_l4_preserved_v1/` | Additive preserved-L4 training implementation and exposure audit |
| `phase8/execution_pss_v2/` | Training-target preparation, state serialization, processor and split code |
| `phase8/label_rescore_v3/` | Final held-out label parser; v2 and strict predecessors retained |
| `phase4/`–`phase7/`, `SpaceConflict/research/` | Historical behavior, representation and intervention code |
| `artifacts/model_results/full_multimodel_20260908_v1/` | Full benchmark: 24,196 requests and public gold |
| `artifacts/model_results/pss_20260922_v1/approved_v2/` | Actual frozen train/dev/test, supervision, schedules and exposure metadata |
| `results/sft/` | Base + six methods × two seeds: aggregate scores and tables only |
| `results/paper_tables/` | Existing multi-model and fine-tuning summary tables |
| `tools/` | Portable CPU validation, scoring supplied predictions, media relocation and optional result reproduction |
| `docs/` | Data, training, evaluation, privacy and portability documentation |
| `verification/` | Checks actually executed for this export |

Historical filenames `private_gold.jsonl` are retained to keep the real code compatible. **Their contents are intentionally public in this release, including the test gold.** Public gold must never be passed to an evaluated model or used to tune on test.

Per-sample model responses/scoring records and diagnostic experiment inputs/gold are intentionally omitted. Benchmark questions/gold, training supervision, code and aggregate result tables remain included. Historical diagnostic code may require separately supplied diagnostic data; it is not a bundled runnable diagnostic dataset.

## Quick start: no model, GPU, API or source images required

From this directory, with Python 3.10+:

```bash
python tools/validate_data.py
python tools/score.py --help
```

After generating your own predictions (not bundled), score them with:

```bash
python tools/score.py --gold artifacts/model_results/pss_20260922_v1/approved_v2/data/test/private_gold.jsonl --predictions outputs/my_model_predictions.jsonl
```

The optional historical reproduction tool requires `--predictions-dir` containing the original 13 runs supplied separately. Export-time verification records are retained as historical evidence; they do not imply those raw outputs are bundled in this slim package.

## Training and model evaluation

Read [TRAINING.md](docs/TRAINING.md), [EVALUATION.md](docs/EVALUATION.md) and [PORTABILITY.md](docs/PORTABILITY.md) first. Source media and model weights are not bundled. Obtain them under the upstream terms. Historical GPU runners require a new environment-specific freeze and engineering acceptance; an old successful run is not permission to forge acceptance for another system.

This package preserves historical implementations and their dependencies rather than pretending all exploratory stages are one production CLI. The new CPU validation/scoring entry points are portable. Full GPU retraining, all model adapters and source-media reconstruction have not been rerun as part of anonymization; consult the explicit validation report.

## Protocol boundaries

- Full-benchmark baseline evaluation uses 24,196 inputs; SFT methods use only the 5,608-input held-out test for final comparison.
- Freeze by underlying world and cross-source alias; never shuffle individual derived questions across splits.
- ClaimAcc includes UNKNOWN. PairAcc requires both members of a complete SUPPORTED/CONTRADICTORY pair; UNKNOWN is not in that denominator.
- Retain at most 512 generated tokens and score what was emitted. Length termination alone does not invalidate a usable label.
- The v3 label recovery is a disclosed post-hoc parser correction, not a preregistered protocol or a new model generation. It does not repair explanations or confidence.
- Aggregate Known/UNKNOWN subgroup scores and all seeds are retained. Individual responses, failures and counterexamples remain in the original research archive, not this slim package.

Website, paper citation and checkpoint download links are not yet provided. Do not infer that a checkpoint release or fresh GPU replication has been completed. See [the publication precheck](verification/PUBLICATION_PRECHECK_20260926.json) for the scope of this export; historical verification reports describe their original runs.
