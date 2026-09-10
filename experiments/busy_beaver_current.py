"""Re-run Busy Beaver under current semantic_epoch.

Generates frontier at len 1-3, filters terminated programs with output,
and reports top champions by output length.
"""
import json
import time
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from quine_research.dataflow.stages import (
    stage_frontier, stage_busy_beaver, _python_execute
)
from quine_research.dataflow.contracts import SearchResult


def run_bb():
    t0 = time.time()

    # Frontier len 1-3 via Python (avoid Zig batch for small sizes)
    all_rows = []
    for level in [1, 2, 3]:
        from itertools import product
        from string import printable
        valid_chars = [c for c in printable if c != '\x00']

        # Generate all programs of exact length `level` using valid opcodes
        from relational.transition import valid_opcode_chars
        programs = []
        if level == 1:
            for cand in valid_opcode_chars(0):
                programs.append(cand["char"])
        elif level == 2:
            for c1 in valid_opcode_chars(0):
                for c2 in valid_opcode_chars(1):
                    programs.append(c1["char"] + c2["char"])
        elif level == 3:
            for c1 in valid_opcode_chars(0):
                for c2 in valid_opcode_chars(1):
                    for c3 in valid_opcode_chars(2):
                        programs.append(c1["char"] + c2["char"] + c3["char"])

        print(f"  len-{level}: {len(programs)} programs")
        py = _python_execute(programs, 3000)
        for p, r in zip(programs, py):
            all_rows.append({
                "program": p,
                "output": r.get("output", ""),
                "steps": r.get("steps", 0),
                "terminated": r.get("terminated", False),
                "reason": 0,
                "final_pc": r.get("final_pc", 0),
                "final_a": r.get("final_a", 0),
                "final_d": r.get("final_d", 0),
            })

    sr = SearchResult(
        level=3, candidates_examined=len(all_rows),
        exhaustive=True, rows=all_rows,
    )

    # Run Busy Beaver
    sel, detail = stage_busy_beaver({}, {"top_n": 10, "non_nul_only": False}, [("f", sr)])

    elapsed = time.time() - t0
    print(f"\nBusy Beaver (semantic_epoch=autobolge-classic-dense-input-underflow/v1):")
    for line in detail:
        print(f"  {line}")
    print(f"  elapsed: {elapsed:.1f}s")

    # Save result
    out_dir = Path("runs/busy_beaver_current")
    out_dir.mkdir(parents=True, exist_ok=True)
    result = {
        "data": {
            "kind": "selection_result",
            "selected": sel.selected,
            "scores": sel.scores,
            "rule": sel.rule,
        },
        "_meta": {
            "stage_id": "bb3_current",
            "kind": "busy_beaver",
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
    run_bb()
