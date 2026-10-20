"""tests/test_novel_discoveries.py - Independent Dual-Oracle Verification of Novel Malbolge Programs.

Verifies unprecedented, previously uncataloged programs discovered and synthesized
by Autobolge 2.0 against:
  1. Autobolge Zig Native Engine (bolge.exe)
  2. Ben Olmstead 1998 Canonical C Reference Interpreter (mb_ref)
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MB_REF = Path(__file__).resolve().parents[2] / "BolgeForge" / "mb_ref"
MB_REF = Path(os.environ.get("AUTOBOLGE_MB_REF", str(DEFAULT_MB_REF)))
BOLGE_EXE = REPO_ROOT / "zig" / "bolge.exe"

from relational.fast_engine import run_batch_bounded
from relational.synthesizer import run_on_engine


def run_mb_ref(program_content: str, max_steps: int = 500_000) -> tuple[int, str]:
    if not MB_REF.exists():
        pytest.skip(f"independent oracle mb_ref not found at {MB_REF} "
                    f"(env AUTOBOLGE_MB_REF)")
    res = subprocess.run(
        [str(MB_REF), "/dev/stdin", str(max_steps)],
        input=program_content.encode("latin-1"),
        capture_output=True,
    )
    return res.returncode, res.stdout.decode("latin-1", errors="replace")


@pytest.mark.parametrize(
    "program,expected_output,expected_steps",
    [
        (">ba`M", "sss", 5),
        ("'=a`M", "hh", 5),
        ("(&a`M", "ll", 5),
        ("(=a`M", "``", 5),
        ("c=aN", "\x00r", 4),
    ],
)
def test_discovered_miniature_programs_dual_oracle(program, expected_output, expected_steps):
    """Test unsupervised frontier search discoveries."""
    # Oracle 1: Zig Engine
    batch_res = run_batch_bounded([(program, "", 1000)])
    r = batch_res[0]
    assert r.output == expected_output, f"Zig output mismatch: got {r.output!r}"
    assert str(r.stop_reason) == "StopReason.TERMINATED"
    assert r.steps == expected_steps

    # Oracle 2: Olmstead C Reference
    rc, mb_out = run_mb_ref(program, max_steps=1000)
    assert rc == 0
    assert mb_out == expected_output, f"mb_ref output mismatch: got {mb_out!r}"


@pytest.mark.parametrize(
    "artifact_name,expected_prefix",
    [
        ("fibonacci.mal", "0, 1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89\n"),
        ("primes.mal", "Primes: 2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47\n"),
        ("pi_constant.mal", "PI = 3.141592653589793238462643383279\n"),
    ],
)
def test_synthesized_novel_programs_dual_oracle(artifact_name, expected_prefix):
    """Test closed-form conveyor synthesis programs."""
    art_path = REPO_ROOT / "artifacts" / artifact_name
    assert art_path.exists(), f"Artifact {art_path} missing"

    content = art_path.read_text(encoding="latin-1")
    cells = [ord(c) for c in content if 33 <= ord(c) <= 126]
    clean_prog = "".join(chr(c) for c in cells)

    # Oracle 1: Zig Engine (bolge.exe via binary protocol)
    out_b, steps, term, reason = run_on_engine(cells, input_data="", max_steps=500_000)
    assert term and reason == 1
    assert out_b.decode("latin-1") == expected_prefix

    # Oracle 2: Olmstead C Reference
    rc, mb_out = run_mb_ref(content, max_steps=500_000)
    assert rc == 0
    assert mb_out == expected_prefix
