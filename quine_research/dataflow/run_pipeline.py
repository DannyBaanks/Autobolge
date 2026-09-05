"""CLI del dataflow: py quine_research/dataflow/run_pipeline.py <pipeline.json> [--force]"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
sys.path.insert(0, "quine_research/search_quine_malbolge")

from quine_research.dataflow.engine import run_pipeline


def main() -> None:
    if len(sys.argv) < 2:
        print("uso: py quine_research/dataflow/run_pipeline.py <pipeline.json> [--force]")
        raise SystemExit(2)
    force = "--force" in sys.argv
    spec = sys.argv[1]
    statuses = run_pipeline(spec, force=force)
    print(f"[dataflow] done: {statuses}")


if __name__ == "__main__":
    main()
