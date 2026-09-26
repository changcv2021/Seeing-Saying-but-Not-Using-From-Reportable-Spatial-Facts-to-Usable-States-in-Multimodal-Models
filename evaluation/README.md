# Inference and evaluation

| Entry | Purpose |
|---|---|
| `score.py` | CPU-only, gold-blind label parsing and fixed-denominator metrics |
| `label_rescore_v3/` | Final disclosed parser correction; no new generation |
| `label_rescore_v2/` | Required predecessor and historical comparison policy |
| `heldout_test_v1/` | Frozen held-out inference for trained adapters |
| `heldout_test_full_pss_v1/` | Full-PSS extension to the same test |

From the repository root:

```bash
python evaluation/score.py --help
python evaluation/label_rescore_v3/test_policy_v3.py
python evaluation/score.py --gold artifacts/model_results/pss_20260922_v1/approved_v2/data/test/private_gold.jsonl --predictions outputs/my_model_predictions.jsonl
```

The last command requires your predictions; historical per-sample outputs are not bundled. The 5,608-input held-out comparison differs from the 24,196-input full benchmark. See [metric definitions](../docs/EVALUATION.md).

Shared multi-model/API implementations remain in [`dataset/scripts/`](../dataset/scripts/), because construction and historical diagnostics also import them. Held-out runners reuse those processors rather than maintaining duplicates. They require environment-specific setup and a new freeze; this cleanup does not claim a GPU rerun.

`tools/score.py` is a compatibility wrapper. `tools/reproduce_sft_results.py` checks the 13 original held-out runs when their prediction files are supplied separately.
