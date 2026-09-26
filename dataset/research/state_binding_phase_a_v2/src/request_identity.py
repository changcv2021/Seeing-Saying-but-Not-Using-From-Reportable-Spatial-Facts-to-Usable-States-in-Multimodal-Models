"""Full execution identity, independent of gold and model correctness."""
from base import digest


def execution_identity(revision, request, cfg, presentation_hash, rendered_prompt_hash):
    if not presentation_hash or not rendered_prompt_hash:
        raise ValueError('ACTUAL_INPUT_HASH_REQUIRED')
    return digest(dict(version='actual_input_identity_v1',model_revision=revision,request=request,
        presentation_hash=presentation_hash,rendered_prompt_hash=rendered_prompt_hash,
        seed=cfg['seed'],mode=dict(enable_thinking=False,do_sample=False,max_new_tokens=cfg['max_new_tokens'],use_cache=True)))
