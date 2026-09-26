# Training methods and immutable exposure

Actual training code: `phase8/formal_training_v4/`; actual supervision targets: the four files named in its exported `PLAN.json.source_hashes`. State serialization and processor logic: `phase8/execution_pss_v2/`. Preserved-L4 extension: `phase8/pss_full_l4_preserved_v1/`.

| Setting | Five original methods |
|---|---|
| Backbone | Qwen3.5-9B |
| Seeds | 20260922, 20260923 |
| Train input pool | 13,476 original answer samples, frozen approved_v2 worlds |
| Updates | 2,237 |
| Effective batch | 16 original units, two DDP ranks |
| Microbatch | up to two forward sequences per rank |
| LoRA | language-attention modules only, rank 16, alpha 32, dropout 0.05 |
| Optimizer | AdamW, LR 2e-5, weight decay 0.01, gradient clip 1.0 |
| Schedule | ceil(3% updates) warmup, linear decay |
| Precision/attention | BF16, accelerated SDPA allowed, math fallback |
| Checkpoint selection | fixed final step; no test-based selection |

Natural keeps the original sample-frequency control. Balanced, Partial CoT, PSS-L4 and Full PSS share the same seed-specific level→world→sample schedule. PSS units have original answer and same-world auxiliary state each weighted 0.5 when an auxiliary exists; otherwise answer-only weight 1. Per-sequence target-token mean is combined by original unit, not by concatenating all tokens into an implicitly length-weighted objective.

Partial CoT retains the entire pool: 13,188 examples have verified rationales and 288 use answer-only fallback. Targets, fallback flags and source evidence are retained. No missing reasoning chain was invented.

Answer-only training uses the original partial assistant target prefix, without fabricated confidence or reason. Do not silently replace it with a different complete-JSON target and claim the same experiment. Output-interface limitations and the later parser correction are disclosed.

The preserved-L4 experiment retains every original PSS-L4 unit/weight and adds the frozen Full-PSS L1/L3 auxiliary units in full batches. Its `units.json`, plans and exposure audit are included for each seed. Updates and LR schedule therefore differ in length. It is not total-compute matched and adds some answer exposure as well as state supervision.

Training data files are relocated but their sample IDs, targets, underlying worlds, level distribution and schedule are not redesigned. Historical hash fields correspond to historical bytes; generate a separate local freeze after relocation. Do not overwrite the exported historical plan, fake a GPU acceptance receipt, or reuse test gold during training.

The historical trainer is a two-GPU Slurm runner with fresh-process checkpoint/processor checks. It is provided with its original engineering dependencies. Model weights, prepared source images and GPU runtime are external prerequisites. Portability work that is still needed is explicitly listed in `PORTABILITY.md`; no new training has been launched by this export.

Important distribution note: the frozen approved training split contains 130 UNKNOWN inputs out of 13,476, whereas the held-out test contains 2,066 UNKNOWN inputs out of 5,608. These original distributions have not been altered for release. See `verification/EXPORT_ACCEPTANCE.json` for the actual train/dev/test label counts. Do not claim label-distribution matching across splits.
