# Portability and validation boundaries

## Immediately runnable

The standard-library CPU helpers validate request/gold IDs and split disjointness, score user-supplied predictions, and relocate legally acquired media with hash checks. These do not require a GPU, a paid API, or the original host filesystem. Reproducing the 13 historical SFT score tables additionally requires the original raw outputs supplied separately; they are not bundled. Read `verification/` for the historical export-time results and current slim-package checks.

## Historical research implementations

The relative `SpaceConflict/`, `phase4/`–`phase8/` layout is intentional: existing imports refer to sibling phases. Historical source snapshots, partial experiments, parser versions and engineering dependencies are retained where required. They are not all active experimental methods.

Absolute project paths were relocated to `.`; persistent data paths to `artifacts/`; model paths to `models/`; remaining external caches to `external/`. Run historical scripts from this package root. The benchmark dataset itself contains only relative media locators, no source images.

Site-specific job scripts are historical templates, **not ready-to-submit jobs**: supply your own scheduler account, partition, Python environment, model locations and resources. Remove/replace old node-exclusion lists for your cluster. No original scheduler account or internal service address is required by the portable CPU tools.

Private API endpoints were replaced by an invalid placeholder; credentials were excluded/redacted. Configure your own environment variables and provider endpoint. Never commit `.env`, credential files or provider response headers containing authorization.

## Hashes and refreezing

Privacy relocation changes serialized data/code bytes. `provenance/EXPORT_MANIFEST.json` records both historical source hash and exported-file hash. Historical training `PLAN.json` and freeze receipts retain their historical integrity evidence; they are not rewritten to falsely assert the modified package was the original accepted run. Training/GPU inference requires a **new local output directory and freeze**, recomputed source/code hashes, legal media resolution and a fresh processor/engineering smoke. Do not blindly run orchestration scripts expecting the original laboratory filesystem.

## Not claimed complete by this package

- GPU retraining or fresh evaluation of every model from the anonymized tree.
- A fully portable, one-command replacement for every historical scheduler controller.
- A newly executed full upstream download/media reconstruction.
- Reproduction of all behavior/internal-mechanism figures from published raw activations; activations/checkpoints are intentionally omitted.
- Legal clearance of every source-derived annotation. Code MIT and source data terms are distinct.

These are explicit limitations, not experiments marked as passed. Historical diagnostic code/configuration and aggregate result evidence are retained. Diagnostic experiment inputs/gold and per-sample model response/scoring files are intentionally omitted; those diagnostic pipelines need separately supplied data. Benchmark questions/gold and training supervision remain included.
