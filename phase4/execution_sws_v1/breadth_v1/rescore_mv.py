"""Separate gold-blind canonicalization from multiview scoring."""
import subprocess
import sys
from pathlib import Path
if __name__=='__main__':
    for stage in ('canonicalize','score'):
        subprocess.run([sys.executable,'-B',str(Path(__file__).with_name('runner_mv.py')),'--stage',stage,*sys.argv[1:]],check=True)
