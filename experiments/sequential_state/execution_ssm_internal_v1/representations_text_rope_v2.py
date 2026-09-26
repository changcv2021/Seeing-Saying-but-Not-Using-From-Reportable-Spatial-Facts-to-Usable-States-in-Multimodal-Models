"""Versioned pure-text RoPE fix; original frozen implementation and failures retained."""
from internal_common import *
def main():
    lock=load(OUT/'manifest/TEXT_ROPE_REPAIR_V2.json')
    for ref in lock['code']:check(ref)
    src=WAVE_CODE/'representations.py';text=src.read_text()
    replacements={
        "dest=out/'representations'/a.model":"dest=out/'representations_v2'/a.model",
        'delta=model.model.rope_deltas.detach().clone()':'delta=model.model.rope_deltas.detach().clone() if model.model.rope_deltas is not None else None',
        'model.model.rope_deltas=delta.clone()':'model.model.rope_deltas=delta.clone() if delta is not None else None',
        'position=torch.tensor([[[length+j]]],device=model.device).expand(3,1,1)+delta.to(model.device).view(1,1,1)':'position=(torch.tensor([[[length+j]]],device=model.device).expand(3,1,1)+delta.to(model.device).view(1,1,1)) if delta is not None else None',
        'rope_deltas=model.model.rope_deltas.tolist()':'rope_deltas=model.model.rope_deltas.tolist() if model.model.rope_deltas is not None else None',
    }
    for old,new in replacements.items():
        if text.count(old)!=1:raise ValueError('UNEXPECTED_FROZEN_SOURCE_FOR_REPAIR:'+old)
        text=text.replace(old,new)
    namespace={'__name__':'ssm_repr_text_rope_v2','__file__':str(src)}
    exec(compile(text,str(src),'exec'),namespace);namespace['main']()
if __name__=='__main__':main()
