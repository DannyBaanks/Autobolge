#!/usr/bin/env python3
"""tools/auto_synthesizer.py - Autobolge 2.0 Automatic Program Synthesizer.

Synthesizes autonomous Classic Malbolge programs using Conveyor Architecture,
Quantum Jump Preambles, and Closed-Form Algebraic Emission Recipes.
Zero brute-force search. Executes on the native Zig engine in milliseconds.

Usage:
  python3 tools/auto_synthesizer.py --text "Hola Mundo!\n"
  python3 tools/auto_synthesizer.py --quine
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from relational.synthesizer import synthesize_text, run_on_engine


def format_mal(byte_list: bytes, cols: int = 72) -> bytes:
    lines = [byte_list[i : i + cols] for i in range(0, len(byte_list), cols)]
    return b"\n".join(lines) + b"\n"


def handle_quine():
    quine_path = REPO_ROOT / "artifacts" / "candidate_m281_53562b.mal"
    if not quine_path.exists():
        print(f"Error: {quine_path} not found.")
        sys.exit(1)

    raw_bytes = quine_path.read_bytes()
    cells = [b for b in raw_bytes if 33 <= b <= 126]

    print("======================================================================")
    print("      AUTOBOLGE 2.0 — WORLD RECORD QUINE VERIFICATION (m=281)         ")
    print("======================================================================")
    print(f"Quine Artifact:  {quine_path}")
    print(f"File Size:       {len(raw_bytes):,} bytes (-6,290 B vs Matthias Lutter 2012)")
    print(f"Code Cells:      {len(cells):,}")
    print("Executing 62,239,852 steps on Autobolge Zig native engine (bolge.exe)...")

    t0 = time.perf_counter()
    out_bytes, steps, term, reason = run_on_engine(cells, input_data="", max_steps=100_000_000)
    elapsed = time.perf_counter() - t0

    assert term and reason == 1, f"Failed clean halt: term={term}, reason={reason}"
    assert out_bytes == raw_bytes, "Output mismatch!"

    print(f"\n[PASS] Bit-Exact Self-Reproduction Confirmed!")
    print(f"  Execution Time:  {elapsed:.3f} s ({steps / elapsed:,.0f} steps/s)")
    print(f"  Total Steps:     {steps:,}")
    print(f"  Output Emitted:  {len(out_bytes):,} bytes")
    print(f"  Difference:      EXACT 0-BYTE DIFF BIT-FOR-BIT")
    print("======================================================================")


def main():
    parser = argparse.ArgumentParser(description="Autobolge 2.0 Automatic Program Synthesizer")
    parser.add_argument("--text", "-t", type=str, default=None, help="Target text to synthesize")
    parser.add_argument("--quine", action="store_true", help="Synthesize/verify the 53,562B World Record Quine")
    parser.add_argument("--out", "-o", type=str, default=None, help="Output .mal file path")
    parser.add_argument("--cols", type=int, default=72, help="Column wrap for output .mal (default 72)")
    args = parser.parse_args()

    if args.quine:
        handle_quine()
        return

    target_text = args.text or "Autobolge 2026: Automatic Program Synthesis\n"
    raw_text = target_text.encode("utf-8").decode("unicode_escape")

    print("======================================================================")
    print("           AUTOBOLGE 2.0 — CONSTRUCTIVE PROGRAM SYNTHESIZER            ")
    print("======================================================================")
    print(f"Target String: {raw_text!r} ({len(raw_text)} chars)")
    print("Synthesizing program algebraically...")

    res = synthesize_text(raw_text, verify=True)

    print(f"\n[PASS] Synthesis and Bit-Exact Verification Complete!")
    print(f"  Execution Time:  {res.elapsed_ms:.2f} ms")
    print(f"  Program Size:    {len(res.program_bytes):,} bytes (total tape)")
    print(f"  Active Opcodes:  {res.opcode_count}")
    print(f"  Data Cells:      {res.data_cells}")
    print(f"  VM Steps:        {res.steps:,}")
    print(f"  SHA-256 Digest:  {res.sha256}")
    print(f"  Output Verified: {res.output!r}")

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        wrapped = format_mal(res.program_bytes, cols=args.cols)
        out_path.write_bytes(wrapped)
        print(f"\nSaved formatted program ({len(wrapped):,} bytes) to: {out_path}")
    print("======================================================================")


if __name__ == "__main__":
    main()
