"""Validate explicitly pinned development Transformers with PEP440 prereleases enabled."""
import importlib.metadata,sys
from common import *

def main():
    a=cli(__doc__).parse_args();out=a.run_root/'environment'
    if a.dry_run:print(str(out));return
    compute()
    if (out/'ENVIRONMENT.json').exists():
        if a.resume:print((out/'ENVIRONMENT.json').read_text());return
        raise FileExistsError(out/'ENVIRONMENT.json')
    sys.path.insert(0,str(out/'peft_overlay'))
    import torch,transformers,peft
    from packaging.requirements import Requirement
    from packaging.version import Version
    dependencies={}
    for spec in importlib.metadata.requires('peft') or []:
        r=Requirement(spec)
        if r.marker and not r.marker.evaluate({'extra':''}):continue
        v=importlib.metadata.version(r.name);dependencies[r.name]=v
        if not r.specifier.contains(Version(v),prereleases=True):raise ValueError('DEPENDENCY_MISMATCH:'+spec)
    wheels=list(out.glob('peft-*.whl'))
    if len(wheels)!=1:raise ValueError('AMBIGUOUS_WHEEL')
    result=dict(status='PASS_CPU_IMPORT_ONLY',peft=peft.__version__,torch=torch.__version__,transformers=transformers.__version__,
        overlay=str(out/'peft_overlay'),wheel=str(wheels[0]),wheel_sha256=sha(wheels[0]),dependencies=dependencies,
        prerelease_policy='Existing explicitly pinned transformers 5.16.0.dev0; PEP440 contains(prereleases=True)',
        python=sys.executable,shared_environment_modified=False,gpu_smoke_complete=False,job_id=os.environ['SLURM_JOB_ID'])
    write(out/'ENVIRONMENT.json',result);print(json.dumps(result),flush=True)
if __name__=='__main__':main()
