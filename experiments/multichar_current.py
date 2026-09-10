"""Re-run multi-char synthesis under current semantic_epoch.

Solves a small set of 2-char targets via the hybrid translator + Zig verification.
"""
import json
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "quine_research" / "search_quine_malbolge"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from quine_research.dataflow.stages import (
    stage_solve, stage_catalog, _python_execute
)
from quine_research.dataflow.contracts import TransformResult


def run_multichar():
    t0 = time.time()

    # Small target set for verification
    targets = ["AB", "HI", "OK", "NO", "GO"]

    print(f"Solving {len(targets)} targets...")
    tr = TransformResult(op="seed_solver", derived=targets)
    sol, sol_detail = stage_solve(
        {}, {"workers": 1, "max_search_depth": 5, "max_steps": 5_000_000},
        [("t", tr)]
    )
    for line in sol_detail:
        print(f"  {line}")

    # Build catalog from solver results
    tc, cat_detail = stage_catalog({}, {}, [("s", sol)])
    for line in cat_detail:
        print(f"  {line}")

    elapsed = time.time() - t0
    print(f"\nMulti-char synthesis (semantic_epoch=autobolge-classic-dense-input-underflow/v1):")
    print(f"  matched: {sol.matched}/{len(targets)}")
    print(f"  errors: {len(sol.errors)}")
    print(f"  catalog blocks: {len(tc.blocks)}")
    print(f"  elapsed: {elapsed:.1f}s")

    for block in tc.blocks:
        print(f"  block: target={block['name']} program={block['program']!r} "
              f"output={block['behavior']!r} zig_verified={block['zig_verified']}")

    # Save result
    out_dir = Path("runs/multichar_synthesis_current")
    out_dir.mkdir(parents=True, exist_ok=True)
    result = {
        "data": {
            "kind": "solver_result",
            "matched": sol.matched,
            "mismatched": sol.mismatched,
            "errors": sol.errors,
            "total_nodes": sol.total_nodes,
        },
        "_meta": {
            "stage_id": "solve_current",
            "kind": "multichar_synthesis",
            "semantic_epoch": "autobolge-classic-dense-input-underflow/v1",
            "label": "CURRENT",
            "elapsed_s": round(elapsed, 2),
            "status": "ok",
        },
    }
    out_path = out_dir / "artifact.json"
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  saved: {out_path}")


if __name__ == "__main__":
    run_multichar()
