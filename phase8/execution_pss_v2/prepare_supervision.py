"""Isolated proof-verifier dependencies, then deterministic supervision builder."""
import importlib.metadata,subprocess,sys
from common import *

def main():
    a=cli(__doc__).parse_args();env=a.run_root/'environment/proof_overlay'
    if a.dry_run:print(env);return
    compute();manifest=env.parent/'PROOF_ENVIRONMENT.json'
    if not manifest.exists():
        wheel_dir=env.parent/'proof_wheels';wheel_dir.mkdir(exist_ok=True)
        subprocess.run([sys.executable,'-m','pip','download','--only-binary=:all:',
            '--dest',str(wheel_dir),'jsonschema==4.23.0'],check=True)
        subprocess.run([sys.executable,'-m','pip','install','--no-index','--no-compile',
            '--find-links',str(wheel_dir),'--target',str(env),'jsonschema==4.23.0'],check=True)
        sys.path.insert(0,str(env));import jsonschema
        write(manifest,dict(status='PASS',overlay=str(env),shared_environment_modified=False,
            wheels=[dict(path=str(p),sha256=sha(p)) for p in sorted(wheel_dir.glob('*.whl'))],
            versions={d.metadata['Name']:d.version for d in importlib.metadata.distributions(path=[str(env)])},
            job_id=os.environ['SLURM_JOB_ID']))
    sys.path.insert(0,str(env))
    import build_supervision
    build_supervision.main()

if __name__=='__main__':main()
