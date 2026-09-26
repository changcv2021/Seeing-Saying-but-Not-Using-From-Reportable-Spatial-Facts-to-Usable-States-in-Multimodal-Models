"""Bounded deployment compatibility diagnosis; no benchmark or image inputs."""
import getpass
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from datetime import datetime,timezone

root=Path('artifacts/model_results/azure_gpt54_20260920_v1')
secret=os.environ.get('SPACECONFLICT_AZURE_API_KEY') or getpass.getpass('Azure API key (hidden): ')
base='https://YOUR_ENDPOINT.invalid'
cases=[('responses_minimal','/responses',{'model':'gpt-5.4','input':'Reply exactly OK.','max_output_tokens':32}),
       ('chat_completions','/chat/completions',{'model':'gpt-5.4','messages':[{'role':'user','content':'Reply exactly OK.'}],
          'max_completion_tokens':32,'reasoning_effort':'none'})]
records=[]
for name,route,body in cases:
    req=urllib.request.Request(base+route,data=json.dumps(body).encode(),
        headers={'Content-Type':'application/json','api-key':secret,'Authorization':'Bearer '+secret})
    row={'test':name,'at':datetime.now(timezone.utc).isoformat(),'benchmark_inputs_sent':0}
    try:
        with urllib.request.urlopen(req,timeout=30) as response:
            data=json.load(response)
            row.update(status=response.status,response=data)
    except urllib.error.HTTPError as exc:
        row.update(status=exc.code,error=exc.read().decode(errors='replace').replace(secret,'[REDACTED]')[:1000])
    except Exception as exc:
        row.update(error=type(exc).__name__+':'+str(exc).replace(secret,'[REDACTED]')[:300])
    records.append(row);print(json.dumps(row),flush=True)
    if row.get('status') in (401,403):break
with (root/'DEPLOYMENT_DIAGNOSTIC.json').open('x') as f:json.dump(records,f,indent=2)
