# Evaluation and published gold

The full frozen benchmark and the approved SFT split are distinct evaluation populations. Never compare a 24,196-input all-split baseline to a 5,608-input fine-tuned result and label that a before/after test comparison. The `base_qwen35_9b` entry in `results/sft/summary_v3.json` is the correct held-out baseline summary. Per-sample predictions and scores are not bundled.

Gold is public by explicit owner decision. `requests.jsonl` remains separate and contains no answer or reference proposition fields. Inference must open only requests and media. Scoring joins by unique `sample_id` afterward. Published test gold must not be used for prompt selection, training, checkpoint selection or hyperparameter tuning.

Final primary metrics: ClaimAcc, PairAcc, per-label recall/F1, Known accuracy, UNKNOWN recall, by L1–L4 and Overall. Missing/unparsed predictions remain wrong under fixed denominators. PairAcc requires both binary members correct. UNKNOWN is excluded from pairs, not from ClaimAcc.

The portable `tools/score.py` executes the actual v3 parser and original metric implementation on predictions supplied by the user. It never passes gold to the label parser. Original strict/v2/v3 aggregate scores remain in the summary.

Optional historical reproduction: `python tools/reproduce_sft_results.py --predictions-dir /path/to/original_predictions --output reproduced_sft_metrics.json`. This requires the original 13 JSONL files, named by model keys in the summary, supplied separately; it is not a command for comparing arbitrary new model runs to identical expected scores. The output filename must not already exist. Historical export-time verification confirms that the original runs reproduced the summary before the public package was slimmed.

All held-out inference retains the original 512-token output cap, non-thinking/greedy protocol and actual processor settings. A truncated but fully emitted label can be scored; do not complete unfinished labels or extract a different answer from the explanation.

Auxiliary explanation judging is separate from label scoring. Historical judge contracts differed: the old 160-character evidence rule is preserved history; the later active judge interface allows 1,000 non-whitespace evidence characters and 512 generated tokens per criterion. Use the recorded contract for the corresponding result rather than silently mixing versions. Public gold does not turn explanation judgments into visual-grounding proofs.

Existing model/API runners are under `SpaceConflict/scripts/`. Private endpoints and keys are removed; a user must configure their own provider credentials. No network evaluation or paid API request is triggered by the CPU reproduction commands.
