"""Fast Malbolge execution engine backed by the Zig motor (zig/bolge.exe).

Drop-in for relational.execution.run_bounded with identical semantics:

- parse_source replicated exactly (skip ' ', '\\n', '\\r', '\\t'; validate
  (ord(c)+i) % 94 in OPS_VALID; max 59049 cells) -- same ValueError messages
- step loop replicated exactly (see zig/bolge.zig header): crazy-fill memory,
  8 opcodes, post-execution ENCRYPT, pointer increment, termination cases
- stop_reason parity with run_bounded: str(StopReason.X) after
  get_state(), i.e. only "StopReason.TERMINATED" / "StopReason.RUNNING"
- steps parity: counts every step() call, including the terminating one

Performance: one bolge.exe process serves a whole batch of programs, so the
per-program cost drops from ~ms (Python debugger objects) to ~ns-scale steps.
"""

from __future__ import annotations

import os
import struct
import subprocess
import tempfile
from typing import List, Optional, Tuple

from .execution import RunResult

BOLGE_EXE = os.environ.get(
    "AUTOBOLGE_BOLGE",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "zig", "bolge.exe"),
)

MAGIC_IN = b"BOLG1"
MAGIC_OUT = b"BOLG2"

OPS_VALID = (4, 5, 23, 39, 40, 62, 68, 81)
WHITESPACE = (" ", "\n", "\r", "\t")
MEM_SIZE = 59049

# str(StopReason.TERMINATED) / str(StopReason.RUNNING) from the malbolge package
REASON_TERMINATED = "StopReason.TERMINATED"
REASON_RUNNING = "StopReason.RUNNING"


class BolgeError(RuntimeError):
    """The Zig motor failed (missing binary, batch protocol violation, crash)."""


def parse_cells(program: str) -> List[int]:
    """Replicate malbolge.core.parse_source exactly (whitespace skip, validation)."""
    cells: List[int] = []
    for char in program:
        if char in WHITESPACE:
            continue
        i = len(cells)
        if (ord(char) + i) % 94 not in OPS_VALID:
            raise ValueError(f"Invalid character '{char}' at position {i}")
        if i >= MEM_SIZE:
            raise ValueError(f"Source file is too long (max {MEM_SIZE} cells)")
        cells.append(ord(char))
    return cells


def _encode_input(input_data: str) -> bytes:
    # The debugger reads ord(ch) per char; ASCII parity is exact.
    return input_data.encode("utf-8")


def _build_batch(records: List[Tuple[List[int], bytes, int]]) -> bytes:
    buf = bytearray()
    buf += MAGIC_IN
    buf += struct.pack("<Q", len(records))
    for cells, input_bytes, max_steps in records:
        buf += struct.pack("<I", len(cells))
        buf += struct.pack("<%dI" % len(cells), *cells)
        buf += struct.pack("<I", len(input_bytes))
        buf += input_bytes
        buf += struct.pack("<I", max_steps)
    return bytes(buf)


def _parse_batch_results(data: bytes, count: int) -> List[Tuple[bytes, int, bool, int, int, int]]:
    if len(data) < 5 or data[0:5] != MAGIC_OUT:
        raise BolgeError("bolge.exe returned an invalid output file")
    pos = 5
    (n,) = struct.unpack_from("<Q", data, pos)
    pos += 8
    if n != count:
        raise BolgeError(f"bolge.exe returned {n} results, expected {count}")
    results: List[Tuple[bytes, int, bool, int, int, int]] = []
    for _ in range(n):
        (olen,) = struct.unpack_from("<I", data, pos)
        pos += 4
        out = data[pos : pos + olen]
        pos += olen
        (steps,) = struct.unpack_from("<Q", data, pos)
        pos += 8
        terminated = data[pos] != 0
        pos += 1
        reason = data[pos]
        pos += 1
        (final_c, final_a, final_d) = struct.unpack_from("<III", data, pos)
        pos += 12
        if (reason == 1) != terminated:
            raise BolgeError("bolge.exe returned inconsistent termination flags")
        results.append((out, steps, terminated, final_c, final_a, final_d))
    return results


def run_batch_bounded(records, workdir: Optional[str] = None) -> List[RunResult]:
    """Execute a batch of (program, input_data, max_steps) records via bolge.exe.

    Programs are parsed Python-side (parse_cells) so validation and its
    ValueError messages are byte-identical to run_bounded. Records that fail
    validation become RunResult(stop_reason="ERROR") like run_bounded.
    """
    if not os.path.exists(BOLGE_EXE):
        raise BolgeError(f"bolge.exe not found at {BOLGE_EXE}")

    parsed: List[Optional[Tuple[List[int], bytes, int]]] = []
    errors: List[Optional[RunResult]] = []
    for program, input_data, max_steps in records:
        try:
            cells = parse_cells(program)
        except ValueError as e:
            errors.append(
                RunResult(
                    program=program,
                    output="",
                    steps=0,
                    stop_reason="ERROR",
                    terminated=False,
                    error=str(e),
                )
            )
            parsed.append(None)
            continue
        errors.append(None)
        parsed.append((cells, _encode_input(input_data), max_steps))

    valid = [p for p in parsed if p is not None]
    results: List[Optional[RunResult]] = list(errors)

    if valid:
        batch = _build_batch(valid)
        with tempfile.TemporaryDirectory(dir=workdir) as tmp:
            in_path = os.path.join(tmp, "in.bin")
            out_path = os.path.join(tmp, "out.bin")
            with open(in_path, "wb") as f:
                f.write(batch)
            proc = subprocess.run(
                [BOLGE_EXE, in_path, out_path],
                capture_output=True,
                timeout=600,
            )
            if proc.returncode != 0:
                raise BolgeError(
                    f"bolge.exe failed (rc={proc.returncode}): "
                    f"{proc.stdout.decode(errors='replace')} {proc.stderr.decode(errors='replace')}"
                )
            with open(out_path, "rb") as f:
                out_data = f.read()
        raw = _parse_batch_results(out_data, len(valid))
        v_idx = 0
        for i in range(len(records)):
            if errors[i] is not None:
                results[i] = errors[i]
            else:
                out, steps, terminated, final_c, final_a, final_d = raw[v_idx]
                v_idx += 1
                results[i] = RunResult(
                    program=records[i][0],
                    output=out.decode("latin-1"),
                    steps=steps,
                    stop_reason=REASON_TERMINATED if terminated else REASON_RUNNING,
                    terminated=terminated,
                    final_pc=final_c,
                    final_a=final_a,
                    final_d=final_d,
                )

    return [r for r in results if r is not None]


def run_bounded_fast(program: str, input_data: str = "", max_steps: int = 20000) -> RunResult:
    """Single-program convenience wrapper with run_bounded-compatible behavior."""
    return run_batch_bounded([(program, input_data, max_steps)])[0]
