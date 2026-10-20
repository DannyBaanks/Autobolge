"""tests/test_quine_record.py - Verification of the 53,562B World Record Classic Malbolge Quine."""
from __future__ import annotations

import hashlib
import time
from pathlib import Path
import pytest

from relational.synthesizer import run_on_engine

REPO_ROOT = Path(__file__).resolve().parent.parent
QUINE_PATH = REPO_ROOT / "artifacts" / "candidate_m281_53562b.mal"
EXPECTED_SHA256 = "96b670b825372a0f41fa3b574d47457f92654b76411e5d5be4c438003087610e"


def test_record_quine_invariants_and_execution():
    assert QUINE_PATH.exists(), f"Quine file {QUINE_PATH} must exist"

    raw_bytes = QUINE_PATH.read_bytes()
    assert len(raw_bytes) == 53562, f"Expected 53,562 bytes, got {len(raw_bytes)}"

    # Check SHA-256
    digest = hashlib.sha256(raw_bytes).hexdigest()
    assert digest == EXPECTED_SHA256, f"Hash mismatch: expected {EXPECTED_SHA256}, got {digest}"

    # Filter opcodes (strip whitespace)
    cells = [b for b in raw_bytes if 33 <= b <= 126]
    assert len(cells) == 52828, f"Expected 52,828 code cells, got {len(cells)}"
    assert all(33 <= b <= 126 for b in cells), "All cells must satisfy ASCII [33, 126]"

    # Execute on the fast native Zig motor (bolge.exe)
    t0 = time.perf_counter()
    out_bytes, steps, term, reason = run_on_engine(cells, input_data="", max_steps=100_000_000)
    elapsed = time.perf_counter() - t0

    assert term, "Quine must terminate"
    assert reason == 1, f"Expected clean halt (reason=1), got {reason}"
    assert steps == 62239852, f"Expected exactly 62,239,852 steps, got {steps}"
    assert len(out_bytes) == len(raw_bytes), f"Output length mismatch: {len(out_bytes)} vs {len(raw_bytes)}"
    assert out_bytes == raw_bytes, "Quine output must match its source file bit-for-bit!"

    # Must execute in under 0.5s on native engine
    assert elapsed < 1.0, f"Execution took too long: {elapsed:.2f}s"
