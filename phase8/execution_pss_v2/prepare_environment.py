"""Isolate the small official PEFT wheel without upgrading any shared packages."""
import importlib.metadata,sys,subprocess,urllib.request
from common import *

def main():
    a=cli(__doc__).parse_args();root=a.run_root;out=root/'environment'
    if a.dry_run:print(str(out));return
    compute()
    if (out/'ENVIRONMENT.json').exists():
        if a.resume:print((out/'ENVIRONMENT.json').read_text());return
        raise FileExistsError(out/'ENVIRONMENT.json')
    with urllib.request.urlopen('https://pypi.org/pypi/peft/json',timeout=60) as f:metadata=json.load(f)
    ent=next(r for r in metadata['urls'] if r['filename'].endswith('py3-none-any.whl'))
    if not ent['url'].startswith('https://files.pythonhosted.org/'):raise ValueError('UNTRUSTED_WHEEL_HOST')
    with urllib.request.urlopen(ent['url'],timeout=60) as f:data=f.read(10*1024**2+1)
    if len(data)>10*1024**2 or hashlib.sha256(data).hexdigest()!=ent['digests']['sha256']:raise ValueError('WHEEL_HASH_OR_SIZE')
    out.mkdir(parents=True,exist_ok=True);wheel=out/ent['filename']
    with wheel.open('xb') as f:f.write(data)
    overlay=out/'peft_overlay'
    subprocess.run([sys.executable,'-m','pip','install','--no-index','--no-deps','--no-compile','--target',str(overlay),str(wheel)],check=True)
    sys.path.insert(0,str(overlay))
    import torch,transformers,peft
    from packaging.requirements import Requirement
    from packaging.version import Version
    dependencies={}
    for spec in importlib.metadata.requires('peft') or []:
        r=Requirement(spec)
        if r.marker and not r.marker.evaluate({'extra':''}):continue
        v=importlib.metadata.version(r.name);dependencies[r.name]=v
        if Version(v) not in r.specifier:raise ValueError('DEPENDENCY_MISMATCH:'+spec)
    result=dict(status='PASS_CPU_IMPORT_ONLY',peft=peft.__version__,torch=torch.__version__,transformers=transformers.__version__,
        overlay=str(overlay),wheel=str(wheel),wheel_sha256=sha(wheel),official_url=ent['url'],dependencies=dependencies,
        python=sys.executable,shared_environment_modified=False,gpu_smoke_complete=False,job_id=os.environ['SLURM_JOB_ID'])
    write(out/'ENVIRONMENT.json',result);print(json.dumps(result),flush=True)

if __name__=='__main__':main()
