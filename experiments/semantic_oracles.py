#!/usr/bin/env python3
"""experiments/semantic_oracles.py - Separate canonical and toolkit oracles.

This experiment records the real result of the two semantic classes used by
Autobolge. It deliberately does not claim parity between them:

  * canonical strict: BolgeForge/mb_ref (Olmstead runtime + strict initial-cell
    validation);
  * toolkit Classic-dense: zig/bolge.exe (invalid decoded opcodes -> NOP,
    post-step encryption guarded by 33..126).

Output: experiments/evidence/semantic_oracles_current.json
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from relational.synthesizer import run_on_engine

DEFAULT_MB_REF = REPO_ROOT.parent / "BolgeForge" / "mb_ref"
MB_REF = Path(os.environ.get("AUTOBOLGE_MB_REF", str(DEFAULT_MB_REF)))
OUT = REPO_ROOT / "experiments" / "evidence" / "semantic_oracles_current.json"
HALT_STEP = 62_239_852

CANONICAL_MINIS = [("(&a`M", "ll", 5), ("(=a`M", "``", 5)]
TOOLKIT_ONLY_MINIS = [(">ba`M", "sss", 5), ("'=a`M", "hh", 5), ("c=aN", "\x00r", 4)]
PRINT_PROGRAMS = [
    ("fibonacci.mal", "0, 1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89\n"),
    (
        "primes.mal",
        "Primes: 2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47\n",
    ),
    ("pi_constant.mal", "PI = 3.141592653589793238462643383279\n"),
]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def run_zig(program: str, max_steps: int = 1000) -> dict:
    cells = [ord(c) for c in program]
    out_b, steps, term, reason = run_on_engine(
        cells, input_data="", max_steps=max_steps
    )
    return {
        "output": out_b.decode("latin-1"),
        "output_sha256": sha256_bytes(out_b),
        "steps": steps,
        "terminated": bool(term),
        "reason": reason,
    }


def run_mb_ref(content: str, max_steps: int) -> dict | None:
    if not MB_REF.exists():
        return None
    res = subprocess.run(
        [str(MB_REF), "/dev/stdin", str(max_steps)],
        input=content.encode("latin-1"),
        capture_output=True,
    )
    return {
        "rc": res.returncode,
        "stdout_sha256": sha256_bytes(res.stdout),
        "stdout_len": len(res.stdout),
        "stderr": res.stderr.decode("latin-1", errors="replace").strip(),
        "stdout": res.stdout,
    }


def zig_version() -> str:
    try:
        return subprocess.run(
            ["zig", "version"], capture_output=True, text=True
        ).stdout.strip()
    except FileNotFoundError:
        return "not found"


def main() -> int:
    started = time.perf_counter()
    mb_available = MB_REF.exists()
    evidence = {
        "format": "autobolge-semantic-oracles/1",
        "label": "CURRENT",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "generated_by": "python3 experiments/semantic_oracles.py",
        "environment": {
            "platform": platform.platform(),
            "python": sys.version.split()[0],
            "zig": zig_version(),
        },
        "oracles": {
            "toolkit": "zig/bolge.exe (Classic dense: NOP invalid, encryption guarded 33..126, input underflow terminates)",
            "canonical_strict": f"BolgeForge/mb_ref ({MB_REF})"
            if mb_available
            else None,
        },
        "mb_ref_available": mb_available,
        "canonical_minis": [],
        "toolkit_only_minis": [],
        "print_programs": [],
        "quine": {},
        "claims": {
            "dual_oracle_8_8": "RETIRED: the old 8/8 claim is not reproducible; cases are split by semantics",
            "canonical_parity_zig_vs_mb_ref": "NOT_DEMONSTRATED: different semantics",
            "absolute_world_record": "NOT_DEMONSTRATED",
        },
    }
    ok = True

    for program, expected, expected_steps in CANONICAL_MINIS:
        z = run_zig(program, 1000)
        c = run_mb_ref(program, 1000)
        entry = {
            "program": program,
            "program_sha256": sha256_bytes(program.encode("latin-1")),
            "expected": expected,
            "zig": z,
            "mb_ref": None if c is None else {k: v for k, v in c.items() if k != "stdout"},
            "zig_pass": z["output"] == expected
            and z["steps"] == expected_steps
            and z["terminated"],
            "mb_ref_pass": bool(
                c and c["rc"] == 0 and c["stdout"].decode("latin-1") == expected
            ),
        }
        ok = ok and entry["zig_pass"] and (entry["mb_ref_pass"] if c else True)
        evidence["canonical_minis"].append(entry)

    for program, expected, expected_steps in TOOLKIT_ONLY_MINIS:
        z = run_zig(program, 1000)
        c = run_mb_ref(program, 1000)
        entry = {
            "program": program,
            "program_sha256": sha256_bytes(program.encode("latin-1")),
            "expected": expected,
            "zig": z,
            "mb_ref": None if c is None else {k: v for k, v in c.items() if k != "stdout"},
            "zig_pass": z["output"] == expected
            and z["steps"] == expected_steps
            and z["terminated"],
            "mb_ref_rejects": bool(
                c and c["rc"] != 0 and "INVALID_ENCRYPTION" in c["stderr"]
            ),
        }
        ok = ok and entry["zig_pass"] and (entry["mb_ref_rejects"] if c else True)
        evidence["toolkit_only_minis"].append(entry)

    for artifact_name, expected_output in PRINT_PROGRAMS:
        path = REPO_ROOT / "artifacts" / artifact_name
        content = path.read_text(encoding="latin-1")
        cells = [ord(c) for c in content if 33 <= ord(c) <= 126]
        out_b, steps, term, reason = run_on_engine(
            cells, input_data="", max_steps=500_000
        )
        c = run_mb_ref(content, 500_000)
        entry = {
            "artifact": artifact_name,
            "artifact_sha256": sha256_file(path),
            "expected_output": expected_output,
            "zig": {
                "output": out_b.decode("latin-1"),
                "output_sha256": sha256_bytes(out_b),
                "steps": steps,
                "terminated": bool(term),
                "reason": reason,
            },
            "mb_ref": None if c is None else {k: v for k, v in c.items() if k != "stdout"},
            "zig_pass": bool(
                term
                and reason == 1
                and out_b.decode("latin-1") == expected_output
            ),
            "strict_mb_ref_rejects": bool(
                c and c["rc"] != 0 and "INVALID_OPCODE" in c["stderr"]
            ),
        }
        ok = ok and entry["zig_pass"] and (
            entry["strict_mb_ref_rejects"] if c else True
        )
        evidence["print_programs"].append(entry)

    quine_path = REPO_ROOT / "artifacts" / "candidate_m281_53562b.mal"
    raw = quine_path.read_bytes()
    cells = [b for b in raw if 33 <= b <= 126]
    t0 = time.perf_counter()
    out_b, steps, term, reason = run_on_engine(
        cells, input_data="", max_steps=100_000_000
    )
    elapsed = time.perf_counter() - t0
    c = run_mb_ref(raw.decode("latin-1"), 100_000_000)
    q = {
        "artifact": "artifacts/candidate_m281_53562b.mal",
        "artifact_sha256": sha256_bytes(raw),
        "bytes": len(raw),
        "cells": len(cells),
        "zig": {
            "output_sha256": sha256_bytes(out_b),
            "identical": out_b == raw,
            "steps": steps,
            "terminated": bool(term),
            "reason": reason,
            "elapsed_s": round(elapsed, 6),
        },
        "mb_ref": None if c is None else {k: v for k, v in c.items() if k != "stdout"},
        "mb_ref_identical": bool(c and c["rc"] == 0 and c["stdout"] == raw),
        "halt_budget": {},
    }
    if c:
        before = run_mb_ref(raw.decode("latin-1"), HALT_STEP - 1)
        at = run_mb_ref(raw.decode("latin-1"), HALT_STEP)
        q["halt_budget"] = {
            "below_halt_rc": before["rc"],
            "below_halt_output_identical": before["stdout"] == raw,
            "at_halt_rc": at["rc"],
            "at_halt_output_identical": at["stdout"] == raw,
        }
        ok = ok and q["mb_ref_identical"] and before["rc"] == 2 and at["rc"] == 0
    ok = ok and q["zig"]["identical"] and q["zig"]["terminated"] and q["zig"]["reason"] == 1
    evidence["quine"] = q

    evidence["verdict"] = (
        "SEMANTIC_ORACLES=PASS"
        if (ok and mb_available)
        else (
            "SEMANTIC_ORACLES=NOT_DEMONSTRATED"
            if not mb_available
            else "SEMANTIC_ORACLES=FAIL"
        )
    )
    evidence["elapsed_s"] = round(time.perf_counter() - started, 3)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(evidence["verdict"])
    print(f"evidence: {OUT.relative_to(REPO_ROOT)}")
    return 0 if evidence["verdict"] == "SEMANTIC_ORACLES=PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
