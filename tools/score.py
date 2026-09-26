"""Compatibility entry point; the scoring implementation lives in evaluation/."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation.score import ROOT, load, score, main

if __name__ == '__main__':
    main()
