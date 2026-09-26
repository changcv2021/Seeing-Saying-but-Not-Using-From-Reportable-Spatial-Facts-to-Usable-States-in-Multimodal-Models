"""Reuse verified Qwen2.5-VL media handling; preserve L4 intervention prompts."""
import sys
from pathlib import Path
from common import parse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_qwen25vl7b_spaceconflict_v10 as runner
from spaceconflict.mllm_l4 import user_prompt as l4_prompt

l13_prompt = runner.user_prompt
runner.user_prompt = lambda sample: l4_prompt(sample) if sample.get('level') == 'L4' else (
    (sample.get('media_context','')+'\n\n' if sample.get('media_context') else '')+l13_prompt(sample))
runner.parse_model_response = parse

if __name__ == '__main__':
    raise SystemExit(runner.main())
