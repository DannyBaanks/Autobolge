#!/usr/bin/env python3
"""experiments/indep_frontier_v1.py - Independent frontier campaign (A + D).

Compiles tools/indep_scan/frontier_indep.c (written from the Malbolge spec, not
from vm.zig/classic.py), then:

  CONTROL  For L=2..6 compares, length by length, the scanner against the
           exhaustive catalog experiments/catalog_cache/catalog_e6dfb345.json
           (built by Autobolge's own engine): stop-reason counts, the full set
           of exact 1-byte and 2-byte outputs, and the witness program of every
           2-byte output must reproduce under the catalog. Any mismatch => FAIL.
  A        Exhaustive 'HI' (no input, MAX_STEPS 3000) negative/positive scan
           for L=7..LMAX.
  D        For every 2-byte output, the minimal program length (2..LMAX) at
           which it first appears, with a witness program; list of printable
           pairs still unreached at LMAX.

Evidence: experiments/evidence/indep_frontier_v1/ (new path, never reused).
Usage:   python3 experiments/indep_frontier_v1.py [--lmax 11] [--threads N]
"""
from __future__ import annotations

import argparse
import collections
import datetime
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "tools" / "indep_scan" / "frontier_indep.c"
BIN = ROOT / "tools" / "indep_scan" / "frontier_indep"
CATALOG = ROOT / "experiments" / "catalog_cache" / "catalog_e6dfb345.json"
OUT = ROOT / "experiments" / "evidence" / "indep_frontier_v1"
MAX_STEPS = 3000
TARGET = "HI"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def scan(length: int, threads: int, target_hex: str = "-") -> dict:
    cmd = [str(BIN), str(length), str(MAX_STEPS), target_hex, str(threads)]
    proc = subprocess.run(cmd, capture_output=True, check=True)
    data = json.loads(proc.stdout)
    data["command"] = " ".join(cmd[1:])
    return data


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lmax", type=int, default=11)
    ap.add_argument("--threads", type=int, default=os.cpu_count() or 1)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    cc = subprocess.run(["gcc", "-O2", "-Wall", "-pthread", "-o", str(BIN), str(SRC)], capture_output=True, text=True)
    if cc.returncode != 0:
        print(cc.stderr)
        return 1
    gcc_version = subprocess.run(["gcc", "--version"], capture_output=True, text=True).stdout.splitlines()[0]

    target_hex = TARGET.encode().hex()
    per_length = {}
    t_start = time.perf_counter()
    for length in range(2, args.lmax + 1):
        data = scan(length, args.threads, target_hex)
        (OUT / f"scan_len{length:02d}.json").write_text(json.dumps(data, sort_keys=True) + "\n", encoding="utf-8")
        per_length[length] = data
        print(f"L={length:2d} programs={data['total_programs']:>12,} HI_hits={data['hits']} "
              f"distinct2={data['distinct_two_byte_outputs']:>6} {data['elapsed_s']:.2f}s", flush=True)

    # ---------------- CONTROL vs Autobolge catalog (L=2..6) ----------------
    control = {"catalog": str(CATALOG.relative_to(ROOT)), "available": CATALOG.exists(), "lengths": {}}
    control_pass = None
    if CATALOG.exists():
        control["catalog_sha256"] = sha256(CATALOG)
        cat = json.loads(CATALOG.read_text(encoding="utf-8"))
        by_len = collections.defaultdict(list)
        for e in cat:
            by_len[len(e["program"])].append(e)
        control_pass = True
        for length in range(2, min(6, args.lmax) + 1):
            entries = by_len[length]
            mine = per_length[length]
            reasons = collections.Counter(e["stop_reason"].split(".")[-1] for e in entries)
            one = {e["output"] for e in entries if len(e["output"]) == 1}
            two = {e["output"] for e in entries if len(e["output"]) == 2}
            prog_out = {e["program"]: e["output"] for e in entries}
            my_one = {bytes.fromhex(k).decode("latin-1") for k in mine["one_byte_outputs"]}
            my_two = {bytes.fromhex(k).decode("latin-1") for k in mine["two_byte_outputs"]}
            witness_ok = all(prog_out.get(p) == bytes.fromhex(k).decode("latin-1")
                             for k, p in mine["two_byte_outputs"].items())
            hi_cat = sorted(e["program"] for e in entries if e["output"] == TARGET)
            row = {
                "programs": [len(entries), mine["total_programs"]],
                "stop_reasons_equal": dict(reasons) == {k: v for k, v in mine["stop_reasons"].items() if v},
                "one_byte_sets_equal": one == my_one,
                "two_byte_sets_equal": two == my_two,
                "two_byte_witnesses_reproduce_in_catalog": witness_ok,
                "hi_hits_equal": hi_cat == sorted(mine["hit_programs"]),
            }
            row["pass"] = (len(entries) == mine["total_programs"]) and all(
                v for k, v in row.items() if k != "programs")
            control["lengths"][length] = row
            control_pass = control_pass and row["pass"]
    control["pass"] = control_pass

    # ---------------- D: minimal length per 2-byte output ----------------
    first_len = {}
    for length in range(2, args.lmax + 1):
        for k, prog in per_length[length]["two_byte_outputs"].items():
            if k not in first_len:
                first_len[k] = (length, prog)
    printable = [chr(a) + chr(b) for a in range(32, 127) for b in range(32, 127)]
    reached = {bytes.fromhex(k).decode("latin-1"): v for k, v in first_len.items()}
    printable_reached = {p: reached[p] for p in printable if p in reached}
    unreached = [p for p in printable if p not in reached]
    new_at = collections.Counter(v[0] for v in first_len.values())
    printable_new_at = collections.Counter(v[0] for v in printable_reached.values())
    alnum = [p for p in printable if p.isalnum() and len(p) == 2]
    shortest_alpha = sorted(
        ((v[0], p, v[1]) for p, v in printable_reached.items() if p.isalpha()), key=lambda t: (t[0], t[1]))
    d_result = {
        "pairs_total_256x256": 65536,
        "pairs_reached": len(first_len),
        "printable_pairs_total": len(printable),
        "printable_pairs_reached": len(printable_reached),
        "printable_pairs_unreached": len(unreached),
        "new_pairs_by_length": dict(sorted(new_at.items())),
        "new_printable_pairs_by_length": dict(sorted(printable_new_at.items())),
        "alnum_pairs_reached": sum(1 for p in alnum if p in printable_reached),
        "alnum_pairs_total": len(alnum),
        "alpha_pairs_reached_first_50": [
            {"output": p, "min_length": l, "witness": w} for l, p, w in shortest_alpha[:50]],
        "longest_min_length_printable": sorted(
            ({"output": p, "min_length": v[0], "witness": v[1]} for p, v in printable_reached.items()),
            key=lambda r: (-r["min_length"], r["output"]))[:25],
    }
    (OUT / "two_byte_min_length.json").write_text(json.dumps({
        "min_length_and_witness": {k: {"min_length": v[0], "witness": v[1]} for k, v in sorted(first_len.items())},
        "printable_unreached": unreached,
    }, sort_keys=True) + "\n", encoding="utf-8")

    hi = {str(L): {"programs": per_length[L]["total_programs"], "hits": per_length[L]["hits"],
                   "hit_programs": per_length[L]["hit_programs"]} for L in range(2, args.lmax + 1)}
    summary = {
        "experiment": "INDEP_FRONTIER_V1",
        "timestamp": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "environment": {"host": platform.platform(), "python": sys.version.split()[0], "gcc": gcc_version,
                        "threads": args.threads},
        "command": f"python3 experiments/indep_frontier_v1.py --lmax {args.lmax} --threads {args.threads}",
        "semantic_epoch": "autobolge-classic-dense-input-underflow/v1",
        "max_steps": MAX_STEPS,
        "input": "",
        "tool_sha256": sha256(SRC),
        "control_vs_catalog": control,
        "A_HI_frontier": hi,
        "D_two_byte_frontier": d_result,
        "elapsed_total_s": round(time.perf_counter() - t_start, 2),
        "scope": "Exhaustive over all 8^L valid-decoding programs, L=2..LMAX, empty stdin, "
                 "MAX_STEPS=3000, toolkit (lenient) semantics. Programs that do not halt within "
                 "3000 steps are counted with their output so far (RUNNING); exact-output matching only.",
        "not_demonstrated": [
            "Anything about programs longer than LMAX or with more than 3000 steps.",
            "Anything under the strict canonical loader (mb_ref): toolkit semantics only.",
            "Programs that read input.",
        ],
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    hashes = {p.name: sha256(p) for p in sorted(OUT.glob("*.json")) if p.name != "hashes.json"}
    hashes["tools/indep_scan/frontier_indep.c"] = sha256(SRC)
    (OUT / "hashes.json").write_text(json.dumps(hashes, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"control_pass": control_pass, "D": {k: d_result[k] for k in (
        "pairs_reached", "printable_pairs_reached", "printable_pairs_unreached", "new_printable_pairs_by_length")}}, indent=1))
    return 0 if control_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
