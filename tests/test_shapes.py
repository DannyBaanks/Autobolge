from __future__ import annotations

"""Shape families: positional arithmetic without and with the Zig engine."""

import os

import pytest

from relational import shapes
from relational.execution import OPS_VALID


def test_valid_char_matches_frontier_formula():
    for pos in range(0, 300, 7):
        for op in shapes.VALID:
            ch = shapes.valid_char(op, pos)
            assert 33 <= ord(ch) <= 126
            assert (ord(ch) + pos) % 94 == op


def test_call_return_family_is_exactly_the_forced_layouts():
    family = shapes.call_return("AB")
    assert len(family) == 396
    assert sum(1 for i in family if i.params["return_to"] < i.params["subroutine"]) == 213
    assert min(len(i.program) for i in family) == 56
    for inst in family:
        k, data = inst.params["call"], inst.params["data_cell"]
        assert data == k + 3
        assert inst.expect["steps"] == k + 6
        assert inst.expect["final_pc"] == inst.params["return_to"] + 1
        assert all((ord(ch) + i) % 94 in OPS_VALID for i, ch in enumerate(inst.program))


def test_rot_positions_reproduce_the_published_staircase():
    stair = shapes.rot_sequence(bytes(range(33, 43)))
    assert stair.params["rot_positions"] == [34, 125, 216, 307, 398, 489, 580, 671, 762, 853]
    assert len(stair.program) == 856
    assert stair.expect == {"output": "!\"#$%&'()*", "steps": 856, "final_pc": 855,
                            "stop_reason": shapes.TERMINATED}


def test_rot_sequence_rejects_unreachable_bytes():
    with pytest.raises(ValueError):
        shapes.rot_sequence(b"A")          # 3*65 = 195 is not printable


def test_controls_keep_the_original_prediction():
    inst = shapes.call_return("AB")[0]
    mutants = shapes.controls(inst)
    assert len(mutants) == 7
    assert all(m.expect == inst.expect and m.program != inst.program for m in mutants)
    single = shapes.rot_sequence(b"!")
    (m,) = shapes.controls(single)
    assert m.plan[-1] == shapes.HALT


@pytest.mark.skipif(not os.path.exists(os.path.join(os.path.dirname(os.path.dirname(__file__)), "zig", "bolge.exe")),
                    reason="zig/bolge.exe not built")
def test_zig_engine_confirms_predictions_and_rejects_controls():
    from relational.fast_engine import run_batch_bounded

    members = shapes.call_return("AB")[:40] + shapes.rot_printer_family()
    results = run_batch_bounded([(i.program, i.input_data, 10_000) for i in members])
    for inst, r in zip(members, results):
        assert (r.output, r.steps, r.final_pc, r.stop_reason) == (
            inst.expect["output"], inst.expect["steps"], inst.expect["final_pc"], inst.expect["stop_reason"])
    mutants = [m for inst in members for m in shapes.controls(inst)]
    mres = run_batch_bounded([(m.program, m.input_data, 10_000) for m in mutants])
    for m, r in zip(mutants, mres):
        assert r.error or (r.output, r.steps, r.final_pc, r.stop_reason) != (
            m.expect["output"], m.expect["steps"], m.expect["final_pc"], m.expect["stop_reason"])
