"""tests/test_ripple.py - Verification suite for XLAT2 Nested Ripple Counter."""
from __future__ import annotations

import pytest
from relational.ripple import (
    generate_ripple_counter_hell,
    synthesize_ripple_counter,
    RippleCounterResult,
)


def test_generate_hell_source():
    src = generate_ripple_counter_hell(3, "X")
    assert "Stages: 3, Total Outputs: 125" in src
    assert "LOOP5_1:" in src
    assert "LOOP5_2:" in src
    assert "LOOP5_3:" in src
    assert "OUT ?-" in src
    assert "Hlt" in src


def test_generate_hell_invalid_inputs():
    with pytest.raises(ValueError, match="num_stages must be >= 1"):
        generate_ripple_counter_hell(0)
    with pytest.raises(ValueError, match="single ASCII character"):
        generate_ripple_counter_hell(2, "XX")


def test_synthesize_ripple_counter_unverified():
    res = synthesize_ripple_counter(stages=2, char_to_print="B", verify=False)
    assert res.stages == 2
    assert res.expected_outputs == 25
    assert res.source_bytes > 0
    assert len(res.sha256) == 64
    assert res.exact_match


def test_synthesize_ripple_counter_stage5_verified():
    res = synthesize_ripple_counter(stages=5, char_to_print="A", verify=True)
    assert res.stages == 5
    assert res.expected_outputs == 3125
    assert res.output_bytes == 3125
    assert res.exact_match
    assert res.halted_cleanly


def test_synthesize_ripple_counter_stage6_positive_expansion():
    # Stage 6: 15,625 outputs from 4,984 bytes -> ratio > 3.0x
    res = synthesize_ripple_counter(stages=6, char_to_print="A", verify=True)
    assert res.stages == 6
    assert res.expected_outputs == 15625
    assert res.output_bytes == 15625
    assert res.exact_match
    assert res.halted_cleanly
    assert res.ratio > 3.0


def test_synthesize_ripple_counter_stage7_unverified_14x():
    # Stage 7: 78,125 outputs from 5,360 bytes -> ratio 14.58x
    res = synthesize_ripple_counter(stages=7, char_to_print="A", verify=False)
    assert res.stages == 7
    assert res.expected_outputs == 78125
    assert res.ratio > 14.0
