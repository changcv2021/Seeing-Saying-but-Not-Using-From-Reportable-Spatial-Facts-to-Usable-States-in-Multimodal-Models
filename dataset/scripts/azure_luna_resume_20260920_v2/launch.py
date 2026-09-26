"""Forward user credential through hidden input and Slurm environment only."""
import getpass
import json
import os
import subprocess
from pathlib import Path
code=Path(__file__).resolve().parent
root=Path('artifacts/model_results/azure_luna_resume_20260920_v2')
record=root/'SUBMISSION.json'
if record.exists():raise SystemExit('ALREADY_SUBMITTED_INSPECT_EXISTING_JOB')
(root/'logs').mkdir(parents=True,exist_ok=True)
secret=os.environ.get('SPACECONFLICT_AZURE_API_KEY') or getpass.getpass('Azure API key (hidden): ')
if not secret.strip():raise SystemExit('CREDENTIAL_MISSING')
env=dict(os.environ,SPACECONFLICT_AZURE_API_KEY=secret.strip())
result=subprocess.run(['sbatch','--parsable',str(code/'job.sh')],env=env,capture_output=True,text=True)
env.pop('SPACECONFLICT_AZURE_API_KEY',None);secret=None
if result.returncode:raise SystemExit('SBATCH_FAILED:'+result.stderr)
obj=dict(job_id=result.stdout.strip(),command=['sbatch','--parsable',str(code/'job.sh')],
    resources=dict(partition='general',account='YOUR_ACCOUNT',qos='allocated',cpus=4,memory='8G',gpus=0,walltime='24:00:00'),
    credential_policy='HIDDEN_STDIN_AND_SLURM_ENVIRONMENT_ONLY')
with record.open('x') as f:json.dump(obj,f,indent=2)
print(json.dumps(obj))
