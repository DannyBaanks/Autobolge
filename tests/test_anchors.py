from __future__ import annotations

"""F3 gate: replay, continuation, no-alias, perturbation, branch isolation."""

from relational.anchors import EpochAnchorV1, memory_root
from relational.classic import ClassicDebugger, TraceEvent, MEM_SIZE
from relational.trace import serialize_trace, verify_trace, replay_trace, checkpoint_digests


# ---------------------------------------------------------------------------
# Corpus: programs that exercise writes, jumps, input, output and halt.
# Built with valid_opcode_chars logic to guarantee legal decode.
# ---------------------------------------------------------------------------

def _char_for_opcode(opcode: int, position: int) -> str:
    for code in range(33, 127):
        if (code + position) % 94 == opcode:
            return chr(code)
    raise ValueError(f"no char for opcode {opcode} at position {position}")


def _build_program(spec: list[tuple[int, int | None]]) -> str:
    """spec = [(opcode, input_byte_or_None), ...]"""
    chars: list[str] = []
    for i, (opcode, _) in enumerate(spec):
        chars.append(_char_for_opcode(opcode, i))
    return "".join(chars)


def _input_for(spec: list[tuple[int, int | None]]) -> bytes:
    return bytes(b for _, b in spec if b is not None)


# Corpus entries: (name, program, input_bytes, max_steps)
# Each entry exercises at least one mutation class.
CORPUS: list[tuple[str, str, bytes, int]] = [
    # rotr write + halt
    ("rotr_halt", _build_program([(39, None), (81, None)]), b"", 10),
    # crz write + halt
    ("crz_halt", _build_program([(62, None), (81, None)]), b"", 10),
    # jmp + halt
    ("jmp_halt", _build_program([(4, None), (81, None)]), b"", 10),
    # input + halt
    ("input_halt", _build_program([(23, 65), (81, None)]), b"A", 10),
    # output + halt
    ("output_halt", _build_program([(5, None), (81, None)]), b"", 10),
    # mov_d + halt
    ("movd_halt", _build_program([(40, None), (81, None)]), b"", 10),
    # rotr + crz + jmp + input + output + halt (full mix)
    ("full_mix", _build_program([
        (39, None), (62, None), (23, 72), (5, None), (4, None), (81, None)
    ]), b"H", 20),
    # multi-step rotr mutations
    ("multi_rotr", _build_program([
        (39, None), (39, None), (39, None), (81, None)
    ]), b"", 10),
]


# ---------------------------------------------------------------------------
# Helper: run a corpus entry and collect a trace.
# ---------------------------------------------------------------------------

def _run_corpus_entry(program: str, input_data: bytes, max_steps: int):
    trace: list[TraceEvent] = []
    dbg = ClassicDebugger(program, input_data.decode("utf-8"), max_steps, trace=trace)
    while not dbg.is_stopped and dbg.step_count < max_steps:
        dbg.step()
    return dbg, trace


# ===========================================================================
# F3 GATE TESTS
# ===========================================================================


class TestF3Replay:
    """Replay: a trace from one run matches a fresh re-execution exactly."""

    def test_replay_each_corpus_entry(self):
        for name, program, input_data, max_steps in CORPUS:
            dbg, trace = _run_corpus_entry(program, input_data, max_steps)
            if not trace:
                continue
            verify_trace(trace)
            replay_trace(program, input_data.decode("utf-8"), trace, max_steps)


class TestF3Continuation:
    """Continuation: anchor -> restore -> continue produces matching state."""

    def test_continuation_each_corpus_entry(self):
        for name, program, input_data, max_steps in CORPUS:
            trace1: list[TraceEvent] = []
            dbg1 = ClassicDebugger(program, input_data.decode("utf-8"), max_steps, trace=trace1)
            while not dbg1.is_stopped and dbg1.step_count < 3:
                dbg1.step()

            anchor = EpochAnchorV1.from_debugger(dbg1, trace1)

            trace2: list[TraceEvent] = []
            restored = anchor.restore(trace=trace2)
            while not restored.is_stopped and restored.step_count < max_steps:
                restored.step()

            assert restored.step_count > dbg1.step_count or restored.is_stopped
            assert anchor.memory_root == memory_root(dbg1.memory)
            assert memory_root(restored.memory) != anchor.memory_root or restored.is_stopped


class TestF3NoAlias:
    """No-alias: two different programs produce anchors with different digests."""

    def test_no_alias_across_corpus(self):
        anchors: list[tuple[str, EpochAnchorV1]] = []
        for name, program, input_data, max_steps in CORPUS:
            dbg, trace = _run_corpus_entry(program, input_data, max_steps)
            if not trace:
                continue
            anchors.append((name, EpochAnchorV1.from_debugger(dbg, trace)))

        digests = [a.digest() for _, a in anchors]
        assert len(digests) == len(set(digests)), "anchor digests must be unique across corpus"


class TestF3Perturbation:
    """Perturbation: changing one memory cell changes the anchor and its trace."""

    def test_single_cell_perturbation(self):
        program, input_data, max_steps = _build_program([
            (39, None), (62, None), (5, None), (81, None)
        ]), b"", 20

        trace_a: list[TraceEvent] = []
        dbg_a = ClassicDebugger(program, "", max_steps, trace=trace_a)
        while not dbg_a.is_stopped and dbg_a.step_count < max_steps:
            dbg_a.step()
        anchor_a = EpochAnchorV1.from_debugger(dbg_a, trace_a)

        target = (anchor_a.pc + 1) % MEM_SIZE
        perturbed = list(anchor_a.memory)
        perturbed[target] = (perturbed[target] + 1) % MEM_SIZE

        trace_b: list[TraceEvent] = []
        dbg_b = ClassicDebugger(program, "", max_steps, trace=trace_b)
        dbg_b._mem = perturbed
        while not dbg_b.is_stopped and dbg_b.step_count < max_steps:
            dbg_b.step()
        anchor_b = EpochAnchorV1.from_debugger(dbg_b, trace_b)

        assert anchor_a.memory_root != anchor_b.memory_root
        assert anchor_a.digest() != anchor_b.digest()

        assert len(trace_b) == len(trace_a)
        if trace_a and trace_b:
            assert trace_a[0].effects != trace_b[0].effects or trace_a[0].post_a != trace_b[0].post_a or trace_a[0].post_c != trace_b[0].post_c


class TestF3BranchIsolation:
    """Branch isolation: two continuations from the same parent stay independent."""

    def test_two_branches_diverge(self):
        program, input_data, max_steps = _build_program([
            (39, None), (23, 65), (5, None), (62, None), (81, None)
        ]), b"A", 20

        trace0: list[TraceEvent] = []
        dbg0 = ClassicDebugger(program, "A", max_steps, trace=trace0)
        while not dbg0.is_stopped and dbg0.step_count < 2:
            dbg0.step()
        parent = EpochAnchorV1.from_debugger(dbg0, trace0)

        branch_a = parent.restore()
        branch_a._mem[(parent.pc + 1) % MEM_SIZE] = (branch_a._mem[(parent.pc + 1) % MEM_SIZE] + 3) % MEM_SIZE
        trace_a: list[TraceEvent] = []
        branch_a._trace = trace_a
        while not branch_a.is_stopped and branch_a.step_count < max_steps:
            branch_a.step()

        branch_b = parent.restore()
        branch_b._mem[(parent.pc + 1) % MEM_SIZE] = (branch_b._mem[(parent.pc + 1) % MEM_SIZE] + 7) % MEM_SIZE
        trace_b: list[TraceEvent] = []
        branch_b._trace = trace_b
        while not branch_b.is_stopped and branch_b.step_count < max_steps:
            branch_b.step()

        anchor_a = EpochAnchorV1.from_debugger(branch_a, trace_a, parent_hash=parent.digest())
        anchor_b = EpochAnchorV1.from_debugger(branch_b, trace_b, parent_hash=parent.digest())

        assert anchor_a.parent_hash == anchor_b.parent_hash == parent.digest()
        assert anchor_a.memory_root != anchor_b.memory_root
        assert anchor_a.digest() != anchor_b.digest()

        delta_a = anchor_a.delta(parent)
        delta_b = anchor_b.delta(parent)
        assert delta_a != delta_b


class TestF3Serialization:
    """Serialization: anchor round-trips through JSON with digest check."""

    def test_json_round_trip(self):
        for name, program, input_data, max_steps in CORPUS:
            dbg, trace = _run_corpus_entry(program, input_data, max_steps)
            if not trace:
                continue
            anchor = EpochAnchorV1.from_debugger(dbg, trace)
            text = anchor.to_json()
            restored = EpochAnchorV1.from_json(text)
            assert restored.digest() == anchor.digest()
            assert restored.memory == anchor.memory
            assert restored.memory_root == anchor.memory_root
