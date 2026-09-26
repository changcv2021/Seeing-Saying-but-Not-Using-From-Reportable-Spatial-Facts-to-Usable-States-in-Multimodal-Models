"""Read the credential without echo; forward to Slurm, never to a source file."""
import getpass
import json
import os
from pathlib import Path
import subprocess

code = Path(__file__).resolve().parent
cfg = json.loads((code / 'config.json').read_text())
root = Path(cfg['output_root'])
(root / 'logs').mkdir(parents=True, exist_ok=True)
if (root / 'SUBMISSION.json').exists():
    raise SystemExit('Existing submission; inspect it before creating another paid run.')
secret = getpass.getpass('Azure API key (hidden, environment only): ')
if not secret.strip():
    raise SystemExit('Missing key')
env = dict(os.environ, SPACECONFLICT_AZURE_API_KEY=secret.strip())
result = subprocess.run(['sbatch', '--parsable', str(code / 'job.sh')], env=env, capture_output=True, text=True)
secret = None
env.pop('SPACECONFLICT_AZURE_API_KEY', None)
if result.returncode:
    raise SystemExit('SBATCH_FAILED:' + result.stderr)
job_id = result.stdout.strip()
record = dict(job_id=job_id, command=['sbatch', '--parsable', str(code / 'job.sh')],
              resources=dict(partition='general', account='YOUR_ACCOUNT', qos='allocated', cpus=2, memory='8G', gpus=0, walltime='24:00:00'),
              credential_policy='USER_SUPPLIED_KEY_VIA_HIDDEN_STDIN_AND_SLURM_ENVIRONMENT_ONLY')
fd = os.open(root / 'SUBMISSION.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, 'w') as f:
    json.dump(record, f, indent=2)
print(json.dumps(record))
