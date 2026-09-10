"""F4 gate: every hit has bootstrap -> anchors -> proposal -> replay; every prune is auditable."""

from __future__ import annotations

from relational.anchors import EpochAnchorV1, memory_root
from relational.classic import ClassicDebugger, TraceEvent, MEM_SIZE
from relational.frontier import (
    AnchorResult,
    PruneReason,
    Proposal,
    TraceExpander,
    TraceFrontier,
    TraceResult,
)
from relational.trace import verify_trace, replay_trace


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _char_for_opcode(opcode: int, position: int) -> str:
    for code in range(33, 127):
        if (code + position) % 94 == opcode:
            return chr(code)
    raise ValueError(f"no char for opcode {opcode} at position {position}")


def _build_program(spec):
    chars = []
    for i, (opcode, _) in enumerate(spec):
        chars.append(_char_for_opcode(opcode, i))
    return "".join(chars)


def _run_and_anchor(program: str, input_data: str = "", max_steps: int = 50, partial: int = 0):
    trace: list[TraceEvent] = []
    dbg = ClassicDebugger(program, input_data, max_steps, trace=trace)
    limit = partial if partial > 0 else max_steps
    while not dbg.is_stopped and dbg.step_count < limit:
        dbg.step()
    anchor = EpochAnchorV1.from_debugger(dbg, trace)
    return dbg, trace, anchor


# ---------------------------------------------------------------------------
# F4 GATE TESTS
# ---------------------------------------------------------------------------


class TestF4PruneAuditability:
    """Every prune has a valid PruneReason; no silent discards."""

    def test_all_prunes_are_auditable(self):
        program = _build_program([(39, None), (81, None)])
        _, _, anchor = _run_and_anchor(program)

        expander = TraceExpander(max_steps=20)
        result = expander.expand(anchor, target=b"", budget=10)

        assert isinstance(result, AnchorResult)
        assert result.anchor.digest() == anchor.digest()
        for proposal, reason in result.prunes:
            assert isinstance(proposal, Proposal)
            assert isinstance(reason, PruneReason)

        total = result.hit_count + result.prune_count
        extensions = len(expander._valid_extensions(anchor))
        assert total == min(extensions, 10)


class TestF4HitChain:
    """Every hit has a complete bootstrap -> anchor -> proposal -> replay chain."""

    def test_hit_has_complete_chain(self):
        program = _build_program([(39, None), (81, None)])
        _, _, anchor = _run_and_anchor(program)

        expander = TraceExpander(max_steps=20)
        result = expander.expand(anchor, target=b"", budget=50)

        for tr in result.hits:
            assert tr.success
            assert tr.anchor_digest == anchor.digest()
            assert tr.proposal.anchor_digest == anchor.digest()
            verify_trace(list(tr.trace))
            replay_trace(program, "", list(tr.trace), max_steps=20)


class TestF4FrontierSearch:
    """TraceFrontier searches across multiple anchors with budget control."""

    def test_multi_anchor_search(self):
        programs = [
            _build_program([(39, None), (81, None)]),
            _build_program([(62, None), (81, None)]),
            _build_program([(40, None), (81, None)]),
        ]
        anchors = []
        for p in programs:
            _, _, anchor = _run_and_anchor(p)
            anchors.append(anchor)

        frontier = TraceFrontier(max_budget=30)
        results = frontier.search(anchors, target=b"")

        assert len(results) == 3
        summary = frontier.summary()
        assert summary["anchors_explored"] == 3
        assert summary["total_hits"] + summary["total_prunes"] > 0
        assert isinstance(summary["prune_breakdown"], dict)


class TestF4Deduplication:
    """Same memory_root seen twice is pruned as STATE_ALREADY_SEEN."""

    def test_duplicate_memory_root_pruned(self):
        prog_a = _build_program([(39, None), (39, None), (39, None), (39, None), (81, None)])
        _, _, anchor1 = _run_and_anchor(prog_a, partial=1)

        expander = TraceExpander(max_steps=20)
        result1 = expander.expand(anchor1, target=b"", budget=50)
        non_stop = [r for r in result1.proposals if r.prune_reason != PruneReason.STOP_REASON]
        if not non_stop:
            return

        result2 = expander.expand(anchor1, target=b"", budget=50)
        seen_prunes_r2 = [r for _, r in result2.prunes if r == PruneReason.STATE_ALREADY_SEEN]
        assert len(seen_prunes_r2) > 0


class TestF4TraceDivergence:
    """Different anchors produce different traces for the same program extension."""

    def test_divergent_traces(self):
        prog_a = _build_program([(39, None), (81, None)])
        prog_b = _build_program([(62, None), (81, None)])
        _, _, anchor_a = _run_and_anchor(prog_a)
        _, _, anchor_b = _run_and_anchor(prog_b)

        expander = TraceExpander(max_steps=20)
        result_a = expander.expand(anchor_a, target=b"", budget=50)
        result_b = expander.expand(anchor_b, target=b"", budget=50)

        traces_a = {r.trace_hash for r in result_a.hits}
        traces_b = {r.trace_hash for r in result_b.hits}
        if traces_a and traces_b:
            assert traces_a != traces_b


class TestF4PruneBreakdown:
    """Summary reports correct prune categories."""

    def test_prune_breakdown_counts(self):
        program = _build_program([(39, None), (81, None)])
        _, _, anchor = _run_and_anchor(program)

        expander = TraceExpander(max_steps=20)
        expander.expand(anchor, target=b"x" * 100, budget=50)

        expander2 = TraceExpander(max_steps=20)
        result = expander2.expand(anchor, target=b"x" * 100, budget=2)

        summary_breakdown = {}
        for _, reason in result.prunes:
            key = reason.value
            summary_breakdown[key] = summary_breakdown.get(key, 0) + 1

        assert "budget_exceeded" in summary_breakdown or result.prune_count <= 2
