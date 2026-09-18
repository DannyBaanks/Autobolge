"""Shape families gate: positional-arithmetic predictions vs the Zig batch engine.

Every member of every family carries a prediction computed before execution
(output, steps, final_pc, stop_reason). One Zig batch runs all members; a
member passes only if all four fields match. Controls are loadable mutants
that keep the original prediction and must be rejected.

Also measured: how many mutants an OUTPUT-ONLY check would have accepted.

Run:  py experiments/shape_families.py
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from relational.fast_engine import BOLGE_EXE, run_batch_bounded  # noqa: E402
from relational import shapes  # noqa: E402

EVIDENCE = ROOT / "experiments" / "evidence" / "shape_families.json"
MAX_STEPS = 10_000
FIELDS = ("output", "steps", "final_pc", "stop_reason")

# Optional interoperability anchors produced elsewhere, by other means.
CALCBOLGE_CALL_RETURN = Path(r"C:\Development\ISyCo Git\Calcbolge\ejemplos\llamada_y_retorno\llamada_y_retorno.mal")
STAIRCASE_TOY = Path(r"C:\Development\ISyCo\experiments0000\MALBOLGE_STAIRCASE_TOY_V0\toys\stairprinter.malbolge")


def observed(r) -> dict:
    return {"output": r.output, "steps": r.steps, "final_pc": r.final_pc,
            "stop_reason": r.stop_reason, "error": r.error}


def run(instances):
    results = run_batch_bounded([(i.program, i.input_data, MAX_STEPS) for i in instances])
    return [observed(r) for r in results]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    t0 = time.time()
    families = {"call_return": shapes.call_return("AB"), "rot_sequence": shapes.rot_printer_family()}
    report = {"format": "autobolge-shape-families/1",
              "engine": {"bolge_exe": str(Path(BOLGE_EXE).name), "bolge_sha256": sha256(Path(BOLGE_EXE).read_bytes())},
              "shapes_sha256": sha256((ROOT / "relational" / "shapes.py").read_bytes()),
              "semantic_contract": "classic-dense, input underflow terminates",
              "families": {}}
    all_ok = True
    for name, members in families.items():
        obs = run(members)
        mismatches = []
        for inst, o in zip(members, obs):
            diff = [f for f in FIELDS if o[f] != inst.expect[f]]
            if diff or o["error"]:
                mismatches.append({"params": inst.params, "fields": diff, "error": o["error"],
                                   "expected": inst.expect, "observed": o})

        mutants = [m for inst in members for m in shapes.controls(inst)]
        mobs = run(mutants)
        rejected = output_only_accepts = load_errors = 0
        for m, o in zip(mutants, mobs):
            if o["error"]:
                load_errors += 1
                rejected += 1
                continue
            full_match = all(o[f] == m.expect[f] for f in FIELDS)
            rejected += not full_match
            output_only_accepts += (o["output"] == m.expect["output"])

        lengths = [len(i.program) for i in members]
        fam = {"members": len(members), "matched": len(members) - len(mismatches),
               "mismatched": len(mismatches), "mismatch_samples": mismatches[:5],
               "program_length_min": min(lengths), "program_length_max": max(lengths),
               "exhaustive_space_at_max_length": f"8^{max(lengths)}",
               "controls": {"mutants": len(mutants), "rejected_by_full_prediction": rejected,
                            "load_errors": load_errors,
                            "accepted_by_output_only_check": output_only_accepts}}
        report["families"][name] = fam
        all_ok &= fam["mismatched"] == 0 and rejected == len(mutants)
        print(f"{name:<13} members={fam['members']:>4} matched={fam['matched']:>4} "
              f"mismatched={fam['mismatched']} lengths={fam['program_length_min']}..{fam['program_length_max']} | "
              f"controls {rejected}/{len(mutants)} rejected, output-only check would accept {output_only_accepts}")

    interop = {}
    cr = next(i for i in families["call_return"] if i.params["call"] == 40 and i.params["return_to"] == 56)
    if CALCBOLGE_CALL_RETURN.exists():
        interop["call_return_k40_r56_equals_calcbolge_example"] = cr.program == CALCBOLGE_CALL_RETURN.read_text(encoding="ascii")
    else:
        interop["call_return_k40_r56_equals_calcbolge_example"] = "NOT_RUN"
    stair = next(i for i in families["rot_sequence"] if i.params["bytes"] == list(range(33, 43)))
    if STAIRCASE_TOY.exists():
        toy = "".join(ch for ch in STAIRCASE_TOY.read_text(encoding="latin-1") if not ch.isspace())
        interop["ascending_staircase_equals_staircase_toy"] = stair.program == toy
        interop["ascending_staircase_rot_positions"] = stair.params["rot_positions"]
    else:
        interop["ascending_staircase_equals_staircase_toy"] = "NOT_RUN"
    report["interop"] = interop
    for k, v in interop.items():
        print(f"{k}={v}")
    all_ok &= all(v is True for k, v in interop.items() if k.endswith("equals_calcbolge_example") or k.endswith("equals_staircase_toy"))

    report["verdict"] = "SHAPE_FAMILIES=PASS" if all_ok else "SHAPE_FAMILIES=FAIL"
    report["seconds"] = round(time.time() - t0, 2)
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(report["verdict"], f"({report['seconds']} s)")
    print(f"evidence: {EVIDENCE.relative_to(ROOT)}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
