from pathlib import Path
"""Gate 2: catalog parity + performance of the Zig engine.

Part A (parity): rebuild the exhaustive len-6 catalog (299,593 programs,
empty input, max_steps=3000) with the Zig motor and compare EVERY entry
against the cached reference catalog (built with the malbolge package):
program, output, steps, terminated, stop_reason, final_a, final_pc, final_d
must be identical.

Part B (performance): wall-clock of the same len-6 rebuild (fast engine) and
an apples-to-apples len-5 rebuild on both engines; per-program rates and
projections for len-7/len-8 exhaustive scans.

Evidence: experiments/evidence/gate2_catalog.json
"""

import hashlib
import json
import os
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from relational import Materialization
from relational.materialization import DEFAULT_CATALOG_PATH

EVIDENCE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "evidence")
REFERENCE_CACHE = os.path.join(DEFAULT_CATALOG_PATH, "catalog_e6dfb345.json")
FIELDS = ("program", "output", "steps", "terminated", "stop_reason",
          "final_a", "final_pc", "final_d")


def main():
    os.makedirs(EVIDENCE_DIR, exist_ok=True)

    # ---------------------------------------------------------------
    print("[A] Parity: rebuild len-6 catalog (fast engine) vs cached reference")
    with open(REFERENCE_CACHE, "r", encoding="utf-8") as f:
        reference = json.load(f)
    print(f"    reference catalog: {len(reference)} entries, "
          f"sha256={hashlib.sha256(json.dumps(reference, sort_keys=True).encode()).hexdigest()[:16]}")

    mat = Materialization(relations=[], catalog_path=None)
    t0 = time.perf_counter()
    rebuilt = mat.build_catalog(max_len=6, max_steps=3000, input_data="", engine="fast")
    fast_len6_s = time.perf_counter() - t0
    print(f"    fast rebuild: {len(rebuilt)} entries in {round(fast_len6_s, 2)}s")

    mismatches = []
    for i, (a, b) in enumerate(zip(rebuilt, reference)):
        if a != b:
            mismatches.append({"index": i, "fast": a, "reference": b})
            if len(mismatches) >= 5:
                break
    print(f"    mismatches: {len(mismatches)}")
    for m in mismatches:
        print("      ", json.dumps(m, ensure_ascii=False)[:300])

    # ---------------------------------------------------------------
    print("\n[B] Performance")
    # apples-to-apples len-5: reference vs fast (fresh instances, no cache)
    mat_ref = Materialization(relations=[], catalog_path=None)
    t0 = time.perf_counter()
    mat_ref.build_catalog(max_len=5, max_steps=3000, input_data="", engine="reference")
    ref_len5_s = time.perf_counter() - t0

    mat_fast5 = Materialization(relations=[], catalog_path=None)
    t0 = time.perf_counter()
    mat_fast5.build_catalog(max_len=5, max_steps=3000, input_data="", engine="fast")
    fast_len5_s = time.perf_counter() - t0

    counts = {0: 1, 1: 8, 2: 64, 3: 512, 4: 4096, 5: 32768, 6: 262144}
    n5 = sum(counts[l] for l in range(6))
    n6 = sum(counts[l] for l in range(7))
    print(f"    len<=5 ({n5} programs): reference {round(ref_len5_s, 2)}s, "
          f"fast {round(fast_len5_s, 2)}s -> {round(ref_len5_s / fast_len5_s, 1)}x")
    print(f"    len<=6 ({n6} programs): fast {round(fast_len6_s, 2)}s "
          f"({n6 / fast_len6_s:,.0f} prog/s)")

    rate_ref = n5 / ref_len5_s
    rate_fast = n6 / fast_len6_s
    n7 = 2097152
    n8 = 16777216
    n9 = 134217728
    print(f"    projection len-7 scan ({n7} programs): "
          f"ref ~{n7 / rate_ref / 60:.0f} min, fast ~{n7 / rate_fast / 60:.1f} min")
    print(f"    projection len-8 scan ({n8} programs): "
          f"ref ~{n8 / rate_ref / 3600:.1f} h, fast ~{n8 / rate_fast / 60:.1f} min")
    print(f"    projection len-9 scan ({n9} programs): "
          f"ref ~{n9 / rate_ref / 3600:.0f} h, fast ~{n9 / rate_fast / 3600:.1f} h")

    result = {
        "gate": "gate2_catalog",
        "part_a": {
            "catalog": REFERENCE_CACHE,
            "entries": len(reference),
            "config": {"max_len": 6, "max_steps": 3000, "input_data": ""},
            "rebuilt_entries": len(rebuilt),
            "mismatches": len(mismatches),
            "mismatch_details": mismatches,
            "reference_sha256": hashlib.sha256(
                json.dumps(reference, sort_keys=True).encode()).hexdigest(),
            "rebuilt_sha256": hashlib.sha256(
                json.dumps(rebuilt, sort_keys=True).encode()).hexdigest(),
        },
        "part_b": {
            "len5_reference_s": round(ref_len5_s, 3),
            "len5_fast_s": round(fast_len5_s, 3),
            "len6_fast_s": round(fast_len6_s, 3),
            "speedup_len5": round(ref_len5_s / fast_len5_s, 1),
            "rate_reference_prog_per_s": round(rate_ref, 1),
            "rate_fast_prog_per_s": round(rate_fast, 1),
        },
    }

    out_path = os.path.join(EVIDENCE_DIR, "gate2_catalog.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    if mismatches:
        print("\nGATE2 FAILED - catalog parity broken")
        sys.exit(1)
    print("\nGATE2 PASSED - 299,593 catalog entries identical, "
          f"len-6 rebuild in {round(fast_len6_s, 2)}s")


if __name__ == "__main__":
    main()