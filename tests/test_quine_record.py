"""tests/test_quine_record.py - Verification of the 53,562 B Classic Malbolge quine (m=281)."""
from __future__ import annotations

import hashlib
import os
import subprocess
import time
from pathlib import Path

import pytest

from relational.synthesizer import run_on_engine

REPO_ROOT = Path(__file__).resolve().parent.parent
QUINE_PATH = REPO_ROOT / "artifacts" / "candidate_m281_53562b.mal"
EXPECTED_SHA256 = "96b670b825372a0f41fa3b574d47457f92654b76411e5d5be4c438003087610e"
DEFAULT_MB_REF = Path(__file__).resolve().parents[2] / "BolgeForge" / "mb_ref"
MB_REF = Path(os.environ.get("AUTOBOLGE_MB_REF", str(DEFAULT_MB_REF)))
HALT_STEP = 62_239_852


def _require_mb_ref() -> None:
    if not MB_REF.exists():
        pytest.skip(
            f"independent oracle mb_ref not found at {MB_REF} (env AUTOBOLGE_MB_REF)"
        )


def _run_mb_ref(program_content: str, max_steps: int) -> tuple[int, bytes, str]:
    _require_mb_ref()
    res = subprocess.run(
        [str(MB_REF), "/dev/stdin", str(max_steps)],
        input=program_content.encode("latin-1"),
        capture_output=True,
    )
    return (
        res.returncode,
        res.stdout,
        res.stderr.decode("latin-1", errors="replace"),
    )


def _quine_bytes() -> bytes:
    assert QUINE_PATH.exists(), f"Quine file {QUINE_PATH} must exist"
    return QUINE_PATH.read_bytes()


def test_record_quine_invariants_and_execution():
    raw_bytes = _quine_bytes()
    assert len(raw_bytes) == 53562, f"Expected 53,562 bytes, got {len(raw_bytes)}"
    digest = hashlib.sha256(raw_bytes).hexdigest()
    assert digest == EXPECTED_SHA256, f"Hash mismatch: expected {EXPECTED_SHA256}, got {digest}"

    cells = [b for b in raw_bytes if 33 <= b <= 126]
    assert len(cells) == 52828, f"Expected 52,828 code cells, got {len(cells)}"
    assert all(33 <= b <= 126 for b in cells), "All cells must satisfy ASCII [33, 126]"

    t0 = time.perf_counter()
    out_bytes, steps, term, reason = run_on_engine(cells, input_data="", max_steps=100_000_000)
    elapsed = time.perf_counter() - t0

    assert term, "Quine must terminate"
    assert reason == 1, f"Expected clean halt (reason=1), got {reason}"
    assert steps == HALT_STEP, f"Expected exactly {HALT_STEP:,} steps, got {steps}"
    assert out_bytes == raw_bytes, "Quine output must match its source file bit-for-bit!"
    assert elapsed < 1.0, f"Execution took too long: {elapsed:.2f}s"


def test_record_quine_matches_canonical_c_oracle():
    raw_bytes = _quine_bytes()
    rc, out, err = _run_mb_ref(raw_bytes.decode("latin-1"), max_steps=100_000_000)
    assert rc == 0, f"mb_ref failed: {err}"
    assert out == raw_bytes, "mb_ref output must match the source file bit-for-bit"


def test_record_quine_exact_halt_budget():
    raw_bytes = _quine_bytes()
    before_rc, before_out, _ = _run_mb_ref(
        raw_bytes.decode("latin-1"), max_steps=HALT_STEP - 1
    )
    assert before_rc == 2  # MAX_STEPS: output complete, HALT not reached
    assert before_out == raw_bytes

    at_rc, at_out, at_err = _run_mb_ref(
        raw_bytes.decode("latin-1"), max_steps=HALT_STEP
    )
    assert at_rc == 0, f"mb_ref did not halt at {HALT_STEP:,}: {at_err}"
    assert at_out == raw_bytes
