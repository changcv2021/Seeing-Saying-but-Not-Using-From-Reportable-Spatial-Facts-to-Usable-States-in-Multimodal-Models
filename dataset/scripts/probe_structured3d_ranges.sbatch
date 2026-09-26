#!/usr/bin/env bash
#SBATCH --job-name=sc_s3d_range_probe
#SBATCH --partition=general
#SBATCH --account=YOUR_ACCOUNT
#SBATCH --qos=allocated
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=00:20:00
#SBATCH --output=artifacts/upstream_media/spar7m_acquisition/slurm/structured3d_probe_%j.out
#SBATCH --error=artifacts/upstream_media/spar7m_acquisition/slurm/structured3d_probe_%j.err
set -euo pipefail
umask 0007
module load python/3.12.11
python -u - <<'PY'
import concurrent.futures, hashlib, json, os, subprocess
from pathlib import Path
root = Path('artifacts/upstream_media/spar7m_acquisition/alternative_sources') / ('range_probe_' + os.environ['SLURM_JOB_ID'])
root.mkdir(exist_ok=True)
url = 'https://zju-kjl-jointlab-azure.kujiale.com/Structured3D/Structured3D_perspective_full_04.zip'
size = 13041186798
def probe(task):
    name, byte_range, query = task
    body, headers = root / (name + '.bin'), root / (name + '.headers')
    result = subprocess.run(['curl', '--http1.1', '-sS', '-fL', '--connect-timeout', '15', '--max-time', '60', '--max-filesize', '65536', '-H', 'Accept-Encoding: identity', '--range', byte_range, '-D', str(headers), '-o', str(body), url + query], capture_output=True, text=True)
    data = body.read_bytes() if body.exists() else b''
    report = dict(name=name, range=byte_range, code=result.returncode, error=result.stderr, bytes=len(data), tail=data[-128:].hex(), sha256=hashlib.sha256(data).hexdigest(), headers=headers.read_text() if headers.exists() else '')
    print(json.dumps(report), flush=True)
    return report
tasks = [('exact64k', f'{size-65536}-{size-1}', ''), ('suffix64k', '-65536', ''), ('suffix128', '-128', ''), ('bust64k', f'{size-65536}-{size-1}', '?spaceconflict_probe=' + os.environ['SLURM_JOB_ID'])]
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    results = list(pool.map(probe, tasks))
(root / 'report.json').write_text(json.dumps(results, indent=2) + '\n')
PY
