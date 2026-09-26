"""Gold-blind normalization and subsequent scoring in separate processes."""
import subprocess
import sys
from pathlib import Path
if __name__=='__main__':
    runner=Path(__file__).with_name('runner.py')
    for stage in ('canonicalize','score'):
        subprocess.run([sys.executable,'-B',str(runner),'--stage',stage,*sys.argv[1:]],check=True)
