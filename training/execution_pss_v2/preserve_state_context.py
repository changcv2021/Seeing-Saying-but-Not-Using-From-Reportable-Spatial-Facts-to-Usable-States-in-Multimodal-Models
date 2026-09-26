"""Retain parent public bounding-box/frame conventions in derived state queries."""
from collections import Counter
from common import *

def main():
    a=cli(__doc__).parse_args();root=a.run_root;out=root/'grounded_state_v4'
    if a.dry_run:print(out);return
    compute()
    if (out/'MANIFEST.json').exists() and a.resume:return
    result={};hashes={}
    for split in ('train','dev'):
        source=root/'supervision_v3'/split/'state.jsonl';original=list(rows(source));new=[];changed=0
        for row in original:
            ctx=row['request'].get('media_context','')
            if ctx and not row['task_prompt'].startswith(ctx+'\n'):
                row=dict(row,task_prompt=ctx+'\n'+row['task_prompt'],public_context_preserved=True);changed+=1
            new.append(row)
        path=out/split/'state.jsonl';write(path,new,True);hashes[str(path)]=sha(path)
        result[split]=dict(states=len(new),public_context_prepended=changed,source_sha256=sha(source))
    manifest=dict(status='PASS_CONTEXT_PRESERVED',counts=result,output_hashes=hashes,
        only_change='Prepend existing parent public media_context. No media, gold, target, split or sample changes.',
        test_opened=False,job_id=os.environ['SLURM_JOB_ID'],code_sha256=sha(__file__))
    write(out/'MANIFEST.json',manifest);print(json.dumps(manifest),flush=True)

if __name__=='__main__':main()
