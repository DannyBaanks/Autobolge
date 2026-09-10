"""F4b gate: v2 adapters preserve v1 results and emit valid anchors/replay."""

from __future__ import annotations

from relational.anchors import EpochAnchorV1
from relational.classic import ClassicDebugger, TraceEvent
from relational.materialization import Materialization
from relational.oracles_v2 import CatalogOracleV2, CatalogEntry, PrefixFamilyOracleV2, GuidedFrontierV2
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
    return "".join(_char_for_opcode(op, i) for i, (op, _) in enumerate(spec))


# ---------------------------------------------------------------------------
# F4b GATE TESTS
# ---------------------------------------------------------------------------


class TestF4bCatalogOracleV2:
    """CatalogOracleV2 preserves v1 catalog results and adds valid anchors."""

    def test_v2_matches_v1_exactly(self):
        mat = Materialization()
        v1_catalog = mat.build_catalog(max_len=3, max_steps=100, input_data="")

        oracle = CatalogOracleV2()
        v2_entries = oracle.scan(max_len=3, max_steps=100, input_data="")

        assert len(v2_entries) == len(v1_catalog)
        for v2, v1 in zip(v2_entries, v1_catalog):
            assert v2.program == v1["program"]
            assert v2.output == v1["output"]
            assert v2.steps == v1["steps"]
            assert v2.terminated == v1["terminated"]

    def test_every_entry_has_valid_anchor(self):
        oracle = CatalogOracleV2()
        entries = oracle.scan(max_len=3, max_steps=100, input_data="")
        assert len(entries) > 0

        for entry in entries:
            assert len(entry.anchor_digest) == 64
            assert len(entry.memory_root) == 64

    def test_anchor_replay_matches_v1_output(self):
        oracle = CatalogOracleV2()
        entries = oracle.scan(max_len=3, max_steps=100, input_data="")

        for entry in entries[:10]:
            trace: list[TraceEvent] = []
            dbg = ClassicDebugger(entry.program, "", 100, trace=trace)
            while not dbg.is_stopped and dbg.step_count < entry.steps:
                dbg.step()
            assert dbg.output == entry.output

    def test_matches_returns_only_exact(self):
        oracle = CatalogOracleV2()
        entries = oracle.scan(max_len=3, max_steps=100, input_data="")
        if entries:
            target = entries[0].output
            matched = oracle.matches(target, max_len=3, input_data="")
            assert all(e.output == target for e in matched)
            assert len(matched) >= 1


class TestF4bPrefixFamilyOracleV2:
    """PrefixFamilyOracleV2 preserves v1 prefix scan results."""

    def test_v2_matches_v1_prefix_scan(self):
        mat = Materialization()
        prefix = _build_program([(39, None)])
        v1_results = mat.scan_prefix_family(prefix, 1, "", 100)

        oracle = PrefixFamilyOracleV2()
        v2_entries = oracle.scan(prefix, 1, input_data="", max_steps=100)

        assert len(v2_entries) == len(v1_results)
        for v2, v1 in zip(v2_entries, v1_results):
            assert v2.program == v1["program"]
            assert v2.output == v1["output"]

    def test_v2_with_target_filter(self):
        oracle = PrefixFamilyOracleV2()
        prefix = _build_program([(39, None)])
        entries = oracle.scan(prefix, 1, input_data="", max_steps=100)
        if entries:
            target = entries[0].output
            filtered = oracle.scan(prefix, 1, input_data="", max_steps=100, target_output=target)
            assert all(e.output == target for e in filtered)


class TestF4bGuidedFrontierV2:
    """GuidedFrontierV2 produces proposals with complete chains."""

    def test_guided_search_produces_results(self):
        seeds = [_build_program([(39, None), (39, None), (81, None)])]
        oracle = GuidedFrontierV2(max_budget=20)
        hits, prunes = oracle.search(seeds, target=b"", max_steps=100)

        total = len(hits) + len(prunes)
        assert total > 0

        for hit in hits:
            assert hit.anchor_digest
            assert len(hit.trace) > 0
            verify_trace(list(hit.trace))

    def test_prunes_are_auditable(self):
        seeds = [_build_program([(39, None), (39, None), (81, None)])]
        oracle = GuidedFrontierV2(max_budget=10)
        hits, prunes = oracle.search(seeds, target=b"x" * 100, max_steps=100)

        for proposal, reason in prunes:
            assert proposal.anchor_digest
            assert reason.value
