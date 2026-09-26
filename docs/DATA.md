# Data organization

Full benchmark requests and gold: `artifacts/model_results/full_multimodel_20260908_v1/` (24,196 inputs). Actual SFT split: `artifacts/model_results/pss_20260922_v1/approved_v2/data/{train,dev,test}/`. The train/test sizes are 13,476/5,608; the verifier reports the actual dev size and exclusions without assuming the approved split is the full benchmark.

Each request retains its sample and pair IDs, level, claim, hypothetical intervention when present, media order/roles, processor presentation settings and hash. Gold is in a separate published file with labels, world IDs and available provenance. Construction-level pairs and local-generation artifacts remain in `dataset/release/production_available_v10/` and `dataset/l4/v3_3/release/`.

L1–L3 and L4 were constructed through different versioned pipelines. Do not retrofit a new rule or infer missing gold from images. Construction code/contracts specify accepted source facts, transformations, verifier checks and UNKNOWN evidence gaps.

The upstream raw datasets and 25+ GiB media evaluation bundle are **not** included in this code/annotation package. Source references, hashes and existing reconstruction scripts are included. Obtain images under the appropriate upstream terms; provide a mapping from exported media locator to local file, then use `tools/resolve_media.py`. Reconstruction provenance may refer to external upstream annotations that are likewise not bundled.

`world_groups.jsonl` records the existing grouping; `exclusions.jsonl` preserves excluded cases. Do not generate a new item-random split. Public test answers do not authorize using test worlds or cross-source aliases in training.

## Human annotation verification

The SpaceConflict benchmark has completed human annotation verification, as confirmed by the researcher. This public documentation update is dated 2026-09-26. Historical `AUTO_ACCEPTED` fields record automated construction checks; they do not mean that human verification was absent. Review or waiver records for later diagnostic derivatives apply to those experiments, not to the original benchmark. No independent double-annotation protocol, reviewer count or inter-annotator agreement is claimed here without supporting records. This documentation update does not alter gold, data splits, model results or historical audit records.
