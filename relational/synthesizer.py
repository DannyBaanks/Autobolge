"""relational/synthesizer.py - High-Performance Constructive Malbolge Synthesizer.

Synthesizes autonomous, self-contained, valid Classic Malbolge programs
for arbitrary text specifications in O(N) time with ZERO brute-force search.

Architecture (Conveyor Synthesis):
1. High-Memory Quantum Jump:
   Algebraic jump c=0 -> 98 -> 99..107 computing target 3312 via
   crazy(rot^2(80), 72) = 3312, landing on c=3315 with d=121.
2. Conveyor Invariant (Delta c == Delta d):
   - Code segment: c in [3315, ...]
   - Data segment: d in [121, ...]
   - Sterile gap: > 2000 cells. Code and data never collide.
3. Constructive Emission Matrix:
   - '\\n' (ASCII 10): 2 opcodes ('* <', V=118).
   - 94 printable ASCII characters: 3 opcodes ('* p <', V1, V2).
   - '+' (ASCII 43): 4 opcodes ('* p p <', V1, V2, V3).
4. Clean termination 'v' (opcode 81) on exit with zero stdin reads.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import struct
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

XLAT1 = (
    "+b(29e*j1VMEKLyC})8&m#~W>qxdRp0wkrUo[D7,XTcA\"lI"
    ".v%{gJh4G\\-=O@5`_3i<?Z';FNQuY]szf$!BS/|t:Pn6^Ha"
)
XLAT2 = (
    "5z]&gqtyfr$(we4{WP)H-Zn,[%\\3dL+Q;>U!pJS72FhOA1C"
    "B6v^=I_0/8|jsb9m<.TVac`uY*MK'X~xDl}REokN:#?G\"i@"
)

POW9 = 19683
_CRAZY_TRITS = (
    (1, 0, 0),
    (1, 0, 2),
    (2, 2, 1),
)

ROOT = Path(__file__).resolve().parent.parent
BOLGE_EXE = ROOT / "zig" / "bolge.exe"


def crazy_op(x: int, y: int) -> int:
    res = 0
    p = 1
    for _ in range(10):
        res += _CRAZY_TRITS[y % 3][x % 3] * p
        x //= 3
        y //= 3
        p *= 3
    return res


def rot_op(x: int) -> int:
    return (x // 3) + (x % 3) * POW9


def char_for(op_char: str, c: int) -> int:
    idx = XLAT1.index(op_char)
    return ((idx - (c % 94) + 94) % 94) + 33


# Build emission recipe dictionary for all printable ASCII + newline
RECIPES: Dict[int, Tuple] = {
    10: ("rot", 118),
    43: ("rot_crazy_crazy", 33, 54, 60),  # '+'
}

# Precompute single rotation and rot+crazy pairs
for _v1 in range(33, 127):
    _r1 = rot_op(_v1)
    _b1 = _r1 % 256
    if _b1 not in RECIPES:
        RECIPES[_b1] = ("rot", _v1)
    for _v2 in range(33, 127):
        _b2 = crazy_op(_r1, _v2) % 256
        if _b2 not in RECIPES:
            RECIPES[_b2] = ("rot_crazy", _v1, _v2)


@dataclass(frozen=True)
class SynthesisResult:
    target: str
    program: str
    program_bytes: bytes
    opcode_count: int
    data_cells: int
    steps: int
    output: str
    elapsed_ms: float
    sha256: str
    verified: bool


def run_on_engine(cells: bytes | List[int], input_data: str = "", max_steps: int = 500000) -> Tuple[bytes, int, bool, int]:
    """Runs program cells directly on the fast Zig native engine (bolge.exe)."""
    cell_list = list(cells)
    with tempfile.TemporaryDirectory() as tmp:
        in_p = Path(tmp) / "in.bin"
        out_p = Path(tmp) / "out.bin"

        payload = bytearray(b"BOLG1")
        payload.extend(struct.pack("<Q", 1))
        payload.extend(struct.pack("<I", len(cell_list)))
        for c in cell_list:
            payload.extend(struct.pack("<I", c))
        inp_bytes = input_data.encode("latin-1")
        payload.extend(struct.pack("<I", len(inp_bytes)))
        payload.extend(inp_bytes)
        payload.extend(struct.pack("<I", max_steps))

        in_p.write_bytes(payload)

        res = subprocess.run([str(BOLGE_EXE), str(in_p), str(out_p)], capture_output=True)
        if res.returncode != 0:
            raise RuntimeError(f"bolge.exe failed: {res.stderr.decode('latin-1', errors='replace')}")

        data = out_p.read_bytes()
        pos = 5 + 8
        out_len = struct.unpack_from("<I", data, pos)[0]
        pos += 4
        out_bytes = data[pos:pos + out_len]
        pos += out_len
        steps, term, reason, fc, fa, fd = struct.unpack_from("<QBBIII", data, pos)
        return out_bytes, steps, (term == 1), reason


def synthesize_text(target: str, verify: bool = True) -> SynthesisResult:
    """Synthesizes a standalone Classic Malbolge program that outputs `target`."""
    t0 = time.perf_counter()

    target_bytes = target.encode("latin-1")
    for b in target_bytes:
        if b not in RECIPES:
            raise ValueError(f"Byte {b} ({chr(b)!r}) is not in the emission recipes")

    code_ops: List[str] = []
    data_bytes: List[int] = []

    for b in target_bytes:
        rec = RECIPES[b]
        kind = rec[0]
        if kind == "rot":
            code_ops.extend(["*", "<"])
            data_bytes.extend([rec[1], ord("o")])
        elif kind == "rot_crazy":
            code_ops.extend(["*", "p", "<"])
            data_bytes.extend([rec[1], rec[2], ord("o")])
        elif kind == "rot_crazy_crazy":
            code_ops.extend(["*", "p", "p", "<"])
            data_bytes.extend([rec[1], rec[2], rec[3], ord("o")])

    code_ops.append("v")  # Clean HALT

    C_START = 3315
    D_START = 121
    TOTAL_LEN = C_START + len(code_ops)

    if TOTAL_LEN > 59049:
        raise ValueError(f"Synthesized program length {TOTAL_LEN} exceeds 59,049 Classic memory limit")

    prog = [ord("o")] * TOTAL_LEN

    # Portal jump from c=0 -> 98 (landing on 99):
    prog[0] = ord("b")
    prog[98] = ord("o")

    # Low-memory data pointers:
    prog[1] = 93
    prog[94] = ord("P")  # 80: Y1
    prog[95] = 93
    prog[96] = 73
    prog[74] = ord("H")  # 72: Y2 (crazy produces 3312)
    prog[75] = 73
    prog[76] = D_START - 1  # 120: target for j at c=3314 to initialize d=121!

    # Discriminator / jump sequence at c=99..107:
    prog[99] = char_for("j", 99)
    prog[100] = char_for("*", 100)
    prog[101] = char_for("j", 101)
    prog[102] = char_for("*", 102)
    prog[103] = char_for("o", 103)
    prog[104] = char_for("j", 104)
    prog[105] = char_for("p", 105)
    prog[106] = char_for("j", 106)
    prog[107] = char_for("i", 107)

    # Cushion and bridge at c=3312..3314:
    prog[3312] = ord("o")
    prog[3313] = char_for("o", 3313)
    prog[3314] = char_for("j", 3314)

    # Place data segment:
    for idx, db in enumerate(data_bytes):
        prog[D_START + idx] = db

    # Place code segment:
    for idx, opc in enumerate(code_ops):
        prog[C_START + idx] = char_for(opc, C_START + idx)

    prog_bytes = bytes(prog)
    prog_str = prog_bytes.decode("latin-1")

    # Verification
    actual_output = ""
    step_count = 0
    is_verified = False

    if verify:
        out_b, step_count, term, reason = run_on_engine(prog_bytes, input_data="", max_steps=500000)
        actual_output = out_b.decode("latin-1")
        assert actual_output == target, f"Verification failed: expected {target!r}, got {actual_output!r}"
        assert term and reason == 1, f"Program did not halt cleanly: term={term}, reason={reason}"
        is_verified = True

    elapsed = (time.perf_counter() - t0) * 1000.0
    sha256 = hashlib.sha256(prog_bytes).hexdigest()

    return SynthesisResult(
        target=target,
        program=prog_str,
        program_bytes=prog_bytes,
        opcode_count=len(code_ops),
        data_cells=len(data_bytes),
        steps=step_count,
        output=actual_output,
        elapsed_ms=elapsed,
        sha256=sha256,
        verified=is_verified,
    )


def main():
    parser = argparse.ArgumentParser(description="Autobolge Constructive Malbolge Synthesizer")
    parser.add_argument("--text", "-t", type=str, default="Hello, world!\n", help="Target text to synthesize")
    parser.add_argument("--out", "-o", type=str, default=None, help="Output .mal file path")
    args = parser.parse_args()

    # Unescape common sequences like \n, \t
    raw_text = args.text.encode("utf-8").decode("unicode_escape")

    print(f"=== AUTOBOLGE 2.0: CONVEYOR SYNTHESIS ===")
    print(f"Target: {raw_text!r} ({len(raw_text)} chars)")

    res = synthesize_text(raw_text, verify=True)
    print(f"Synthesis & Verification Succeeded in {res.elapsed_ms:.2f} ms!")
    print(f"  Program size: {len(res.program_bytes):,} bytes (total tape)")
    print(f"  Code opcodes: {res.opcode_count}")
    print(f"  Data cells:   {res.data_cells}")
    print(f"  VM steps:     {res.steps:,}")
    print(f"  SHA-256:      {res.sha256}")
    print(f"  Output:       {res.output!r}")

    if args.out:
        with open(args.out, "w", encoding="latin-1") as f:
            f.write(res.program)
        print(f"Saved to {args.out}")


if __name__ == "__main__":
    main()
