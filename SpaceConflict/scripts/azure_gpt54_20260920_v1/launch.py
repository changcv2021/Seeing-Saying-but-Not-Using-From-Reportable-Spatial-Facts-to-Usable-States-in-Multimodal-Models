"""One tiny connectivity check then Slurm submission; no credential on disk."""
import getpass
import json
import os
import subprocess
import urllib.request
import urllib.error
from run import ROOT,CODE,config,write,allowed_model,old

if (ROOT/'SUBMISSION.json').exists():raise SystemExit('ALREADY_SUBMITTED')
(ROOT/'logs').mkdir(parents=True,exist_ok=True)
secret=os.environ.get('SPACECONFLICT_AZURE_API_KEY') or getpass.getpass('Azure API key (hidden): ')
if not secret.strip():raise SystemExit('MISSING_CREDENTIAL')
cfg=config()
if not (ROOT/'CONNECTIVITY.json').exists():
    payload=dict(model=cfg['model'],input='Reply exactly OK.',store=False,
        reasoning={'effort':'none'},max_output_tokens=32)
    request=urllib.request.Request(cfg['endpoint'],data=json.dumps(payload).encode(),
        headers={'Content-Type':'application/json','api-key':secret,'Authorization':'Bearer '+secret})
    try:
        with urllib.request.urlopen(request,timeout=45) as http:
            response=json.load(http)
            headers={k:v for k,v in http.headers.items() if 'ratelimit' in k.lower()}
    except urllib.error.HTTPError as exc:
        message=exc.read().decode(errors='replace').replace(secret,'[REDACTED]')[:1000]
        raise SystemExit('CONNECTIVITY_FAILED:'+str(exc.code)+':'+message) from None
    assert allowed_model(response.get('model'),cfg) and response.get('status')=='completed', 'DEPLOYMENT_RESPONSE_MISMATCH'
    write(ROOT/'CONNECTIVITY.json',dict(at=old.now(),model=response.get('model'),response=response,
        usage=response.get('usage',{}),rate_limits=headers,benchmark_sample=False))
    print(json.dumps({'connectivity':'PASS','model':response.get('model'),'usage':response.get('usage'),'rate_limits':headers}),flush=True)
env=dict(os.environ,SPACECONFLICT_AZURE_API_KEY=secret.strip())
cmd=['sbatch','--parsable',str(CODE/'job.sh')]
result=subprocess.run(cmd,env=env,text=True,capture_output=True)
env.pop('SPACECONFLICT_AZURE_API_KEY',None);secret=None
if result.returncode:raise SystemExit('SBATCH_FAILED:'+result.stderr)
record=dict(job_id=result.stdout.strip(),command=cmd,
    resources=dict(partition='general',account='YOUR_ACCOUNT',qos='allocated',cpus=4,memory='8G',gpus=0,walltime='24:00:00'),
    credential_policy='HIDDEN_INPUT_SLURM_ENVIRONMENT_ONLY')
with (ROOT/'SUBMISSION.json').open('x') as f:json.dump(record,f,indent=2)
print(json.dumps(record))
