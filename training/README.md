# SFT training

Start with [the training protocol](../docs/TRAINING.md) and [portability requirements](../docs/PORTABILITY.md).

| Directory | Role |
|---|---|
| `formal_training_v4/` | Main two-GPU, update-matched implementation: Natural, Balanced, partial CoT, PSS-L4 and Full PSS |
| `pss_full_l4_preserved_v1/` | Additive Full PSS experiment preserving original L4 exposure |
| `execution_pss_v2/` | Target construction, canonical serialization and processor support |
| `formal_training_v2/`, `formal_training_v3/` | Versioned dependencies used by the final trainer |
| Other versioned directories | Earlier preparation, resource and acceptance tools; not additional final methods |

Targets, schedules and exposure metadata remain in `artifacts/model_results/pss_20260922_v1/approved_v2/`. Train worlds, methods and seeds are unchanged. Output-token totals are not a matching constraint for the update-matched comparison.

Adapter inference is under [`evaluation/`](../evaluation/README.md); the preserved-L4 `evaluate.py` calls the shared evaluation modules. GPU templates need your own environment, source media, weights, output directory and a new freeze. File presence does not establish acceptance for a new experiment.

CPU regression checks from the repository root:

```bash
python training/formal_training_v4/test_plan.py
python training/pss_full_l4_preserved_v1/test_preserved.py
```
