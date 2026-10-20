"""tests/test_synthesizer.py - Verification suite for Autobolge 2.0 Conveyor Synthesis."""
from __future__ import annotations

import pytest
from relational.synthesizer import synthesize_text, run_on_engine


def test_synthesize_single_newline():
    res = synthesize_text("\n", verify=True)
    assert res.output == "\n"
    assert res.verified
    assert res.steps > 0
    assert all(33 <= b <= 126 for b in res.program_bytes)


def test_synthesize_single_character():
    res = synthesize_text("Z", verify=True)
    assert res.output == "Z"
    assert res.verified
    assert all(33 <= b <= 126 for b in res.program_bytes)


def test_synthesize_hello_world():
    target = "Hello, world!\n"
    res = synthesize_text(target, verify=True)
    assert res.output == target
    assert res.verified
    assert res.steps == 52
    assert all(33 <= b <= 126 for b in res.program_bytes)


def test_synthesize_special_characters_and_plus():
    # '+' requires the 3-step crazy composition
    target = "1 + 2 = 3; [OK]!\n"
    res = synthesize_text(target, verify=True)
    assert res.output == target
    assert res.verified
    assert all(33 <= b <= 126 for b in res.program_bytes)


def test_synthesis_determinism():
    res1 = synthesize_text("Deterministic test", verify=False)
    res2 = synthesize_text("Deterministic test", verify=False)
    assert res1.sha256 == res2.sha256
    assert res1.program_bytes == res2.program_bytes


def test_synthesis_performance():
    # Synthesis of 50 chars must complete in under 50 ms
    target = "Autobolge 2.0: High-Performance Conveyor Synthesizer"
    res = synthesize_text(target, verify=True)
    assert res.output == target
    assert res.elapsed_ms < 50.0, f"Synthesis too slow: {res.elapsed_ms} ms"
