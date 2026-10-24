"""Semantic-oracle checks for minimal programs and synthesized print programs.

Two semantics are tested separately and must not be conflated:
  * canonical strict: BolgeForge mb_ref (Olmstead runtime + strict initial-cell
    validation). Only programs whose initial cells all decode to valid
    instructions are accepted.
  * toolkit Classic-dense: zig/bolge.exe (invalid decoded opcodes are NOP and
    post-step encryption is guarded by 33..126).

The five mini programs are already in the exhaustive catalog (len <= 6); this
file does not claim novelty. Three of them depend on the toolkit guard and are
therefore toolkit-only.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from relational.synthesizer import run_on_engine

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MB_REF = Path(__file__).resolve().parents[2] / "BolgeForge" / "mb_ref"
MB_REF = Path(os.environ.get("AUTOBOLGE_MB_REF", str(DEFAULT_MB_REF)))


def _require_mb_ref() -> None:
    if not MB_REF.exists():
        pytest.skip(
            f"independent oracle mb_ref not found at {MB_REF} (env AUTOBOLGE_MB_REF)"
        )


def run_mb_ref(program_content: str, max_steps: int = 500_000) -> tuple[int, bytes, str]:
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


CANONICAL_MINIS = [
    ("(&a`M", "ll", 5),
    ("(=a`M", "``", 5),
]

TOOLKIT_ONLY_MINIS = [
    (">ba`M", "sss", 5),
    ("'=a`M", "hh", 5),
    ("c=aN", "\x00r", 4),
]

PRINT_PROGRAMS = [
    ("fibonacci.mal", "0, 1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89\n"),
    (
        "primes.mal",
        "Primes: 2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47\n",
    ),
    ("pi_constant.mal", "PI = 3.141592653589793238462643383279\n"),
]


def _run_zig(program: str, max_steps: int = 1000):
    cells = [ord(c) for c in program]
    out_b, steps, term, reason = run_on_engine(
        cells, input_data="", max_steps=max_steps
    )
    return out_b, steps, term, reason


@pytest.mark.parametrize("program,expected_output,expected_steps", CANONICAL_MINIS)
def test_canonical_miniatures_dual_oracle(program, expected_output, expected_steps):
    out_b, steps, term, reason = _run_zig(program, 1000)
    assert out_b.decode("latin-1") == expected_output
    assert term and reason == 1
    assert steps == expected_steps

    rc, mb_out, mb_err = run_mb_ref(program, max_steps=1000)
    assert rc == 0, mb_err
    assert mb_out.decode("latin-1") == expected_output


@pytest.mark.parametrize("program,expected_output,expected_steps", TOOLKIT_ONLY_MINIS)
def test_toolkit_only_miniatures(program, expected_output, expected_steps):
    out_b, steps, term, reason = _run_zig(program, 1000)
    assert out_b.decode("latin-1") == expected_output
    assert term and reason == 1
    assert steps == expected_steps

    rc, _mb_out, mb_err = run_mb_ref(program, max_steps=1000)
    assert rc != 0
    assert "INVALID_ENCRYPTION" in mb_err


@pytest.mark.parametrize("artifact_name,expected_output", PRINT_PROGRAMS)
def test_synthesized_print_programs_zig(artifact_name, expected_output):
    art_path = REPO_ROOT / "artifacts" / artifact_name
    assert art_path.exists(), f"Artifact {art_path} missing"

    content = art_path.read_text(encoding="latin-1")
    cells = [ord(c) for c in content if 33 <= ord(c) <= 126]
    out_b, _steps, term, reason = run_on_engine(
        cells, input_data="", max_steps=500_000
    )
    assert term and reason == 1
    assert out_b.decode("latin-1") == expected_output

    rc, _mb_out, mb_err = run_mb_ref(content, max_steps=500_000)
    assert rc != 0
    assert "INVALID_OPCODE" in mb_err
