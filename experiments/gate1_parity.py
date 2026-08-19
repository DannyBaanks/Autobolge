from pathlib import Path
"""Gate 1: differential parity between run_bounded (malbolge package) and
the Zig motor (run_bounded_fast).

Every record must agree EXACTLY on: output, steps, terminated, stop_reason,
final_pc, final_a, final_d (and error strings for invalid programs).

Corpus:
  - known-answer programs (echo `ub`, prefix echo `ubs``, canonical
    Hello-World, single-char programs, empty program)
  - seeded random valid programs (len 1..30), random inputs, mixed max_steps
  - whitespace-skipping parity, invalid-char parity (identical ValueError
    text), long valid programs, >59049-cell too-long parity

Evidence-first: result is written to experiments/evidence/gate1_parity.json.
"""

import hashlib
import json
import os
import random
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from relational.execution import run_bounded
from relational.fast_engine import run_bounded_fast, parse_cells

OPS_VALID = (4, 5, 23, 39, 40, 62, 68, 81)
EVIDENCE_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "evidence"
)

HELLO = "(=<`#9]~6ZY327Uv4-QsqpMn&+Ij\"'E%e{Ab~w=_:]Kw%o44Uqp0/Q?xNvL:`H%c#DD2^WV>gY;dts76qKJImZkj"


def valid_char_at(pos: int, opcode: int) -> str:
    return chr(33 + (opcode - 33 - pos) % 94)


def random_program(rng: random.Random, length: int) -> str:
    return "".join(valid_char_at(i, rng.choice(OPS_VALID)) for i in range(length))


def random_input(rng: random.Random) -> str:
    if rng.random() < 0.3:
        return ""
    n = rng.randint(1, 12)
    return "".join(chr(rng.randint(32, 126)) for _ in range(n))


def summarize(r):
    return {
        "output": r.output,
        "steps": r.steps,
        "terminated": r.terminated,
        "stop_reason": r.stop_reason,
        "final_pc": r.final_pc,
        "final_a": r.final_a,
        "final_d": r.final_d,
        "error": r.error,
    }


def run_pair(program: str, input_data: str, max_steps: int):
    r_ref = run_bounded(program, input_data, max_steps)
    r_fast = run_bounded_fast(program, input_data, max_steps)
    return r_ref, r_fast, summarize(r_ref), summarize(r_fast)


def main():
    rng = random.Random(20260817)
    cases = []

    # --- known-answer programs ------------------------------------------
    known = [
        ("ub", "A", 20000),
        ("ubs`", "AB", 20000),
        ("ubs`", "HI", 20000),
        ("ubs`", "XYZ", 20000),
        (HELLO, "", 20000),
        ("(", "", 20000),
        ("ub", "", 20000),
        ("", "", 20000),
        ("", "ABC", 20000),
        ("(=<`#9]~6ZY32", "", 20000),
    ]
    for program, inp, ms in known:
        cases.append((program, inp, ms, "known"))

    # --- random valid corpus --------------------------------------------
    n_random = 400
    for _ in range(n_random):
        length = rng.randint(1, 30)
        ms = rng.choice([1, 2, 3, 7, 50, 500, 20000])
        cases.append((random_program(rng, length), random_input(rng), ms, "random"))

    # --- whitespace skip parity -----------------------------------------
    ws_prog = "ub\nx`\tu b\r"
    cases.append((ws_prog, "A", 20000, "whitespace"))
    cases.append(("ub x`", "A", 20000, "whitespace"))

    # --- invalid char parity (identical ValueError) ----------------------
    cases.append(("ub@bad", "A", 20000, "invalid"))
    cases.append(("ub\x01x", "", 20000, "invalid"))

    # --- long valid programs ---------------------------------------------
    long_prog = "".join(valid_char_at(i, 4) for i in range(300))
    cases.append((long_prog, "AB", 20000, "long_valid"))
    long_prog_50 = "".join(valid_char_at(i, 5) for i in range(50))
    cases.append((long_prog_50, "", 500, "long_valid"))

    # --- too-long parity (59049 cells) ------------------------------------
    too_long = "".join(valid_char_at(i, 4) for i in range(59049))
    cases.append((too_long, "", 10, "too_long"))

    mismatches = []
    records = []
    t0 = time.perf_counter()

    for idx, (program, inp, ms, kind) in enumerate(cases):
        if idx % 50 == 0:
            print(f"  case {idx}/{len(cases)} ...", flush=True)
        try:
            r_ref, r_fast, s_ref, s_fast = run_pair(program, inp, ms)
        except Exception as e:
            print(f"  case {idx} CRASH: {type(e).__name__}: {e}")
            print(f"    program={program!r} input={inp!r} max_steps={ms}")
            raise
        record = {
            "case": idx,
            "kind": kind,
            "program": program,
            "input": inp,
            "max_steps": ms,
            "ref": s_ref,
            "fast": s_fast,
        }
        records.append(record)
        if s_ref != s_fast:
            mismatches.append(record)

    elapsed = time.perf_counter() - t0

    result = {
        "gate": "gate1_parity",
        "engine": "run_bounded_fast (zig/bolge.exe)",
        "reference": "run_bounded (malbolge package debugger, SPARSE_CONFIG)",
        "seed": 20260817,
        "cases_total": len(cases),
        "mismatches": len(mismatches),
        "elapsed_s": round(elapsed, 2),
        "sha256": hashlib.sha256(json.dumps(records, sort_keys=True).encode()).hexdigest(),
        "mismatch_details": mismatches,
    }

    os.makedirs(EVIDENCE_DIR, exist_ok=True)
    out_path = os.path.join(EVIDENCE_DIR, "gate1_parity.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"gate1_parity: {len(cases)} cases, {len(mismatches)} mismatches, {round(elapsed,2)}s")
    print(f"sha256: {result['sha256']}")
    for m in mismatches[:5]:
        print("MISMATCH:", json.dumps(m, ensure_ascii=False)[:400])
    if mismatches:
        sys.exit(1)
    print("GATE1 PASSED - Zig motor is semantically identical to the reference")


if __name__ == "__main__":
    main()
