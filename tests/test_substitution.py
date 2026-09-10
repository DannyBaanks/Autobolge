"""F5 gate: substitution benchmark — measure guided vs exhaustive vs random."""

from __future__ import annotations

from relational.classic import ClassicDebugger
from relational.substitution import SubstitutionBenchmark, SubstitutionReport, Workload


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
# Workloads: each has an explicit horizon (v1 exhaustive catalog max_len)
# ---------------------------------------------------------------------------

def _make_workloads():
    wl_empty = Workload(
        name="empty_target",
        programs=(
            _build_program([(39, None), (39, None), (81, None)]),
            _build_program([(62, None), (39, None), (81, None)]),
            _build_program([(40, None), (39, None), (81, None)]),
            _build_program([(39, None), (62, None), (81, None)]),
            _build_program([(62, None), (62, None), (81, None)]),
            _build_program([(40, None), (62, None), (81, None)]),
        ),
        input_data="",
        max_steps=100,
        horizon=2,
        target=b"",
    )

    wl_short = Workload(
        name="short_output",
        programs=(
            _build_program([(39, None), (5, None), (81, None)]),
            _build_program([(62, None), (5, None), (81, None)]),
            _build_program([(39, None), (39, None), (5, None), (81, None)]),
            _build_program([(62, None), (62, None), (5, None), (81, None)]),
        ),
        input_data="",
        max_steps=100,
        horizon=2,
        target=b"\x00",
    )

    return [wl_empty, wl_short]


# ---------------------------------------------------------------------------
# F5 GATE TESTS
# ---------------------------------------------------------------------------


class TestF5Substitution:
    """F5: guided search must preserve v1 hits within horizon and reduce work."""

    def test_v2_preserves_v1_hits_within_horizon(self):
        for wl in _make_workloads():
            benchmark = SubstitutionBenchmark()
            results = benchmark.compare(wl)

            v1 = results["v1_exhaustive"]
            v2 = results["v2_guided"]

            assert v2.hits >= v1.hits, (
                f"[{wl.name}] v2 lost hits: v1={v1.hits} v2={v2.hits}"
            )

    def test_v2_same_or_fewer_proposals(self):
        for wl in _make_workloads():
            benchmark = SubstitutionBenchmark()
            results = benchmark.compare(wl)

            v1 = results["v1_exhaustive"]
            v2 = results["v2_guided"]

            assert v2.total_proposals <= v1.total_proposals, (
                f"[{wl.name}] v2 proposed more: v1={v1.total_proposals} v2={v2.total_proposals}"
            )

    def test_random_control_finds_fewer_hits(self):
        for wl in _make_workloads():
            benchmark = SubstitutionBenchmark()
            results = benchmark.compare(wl)

            v1 = results["v1_exhaustive"]
            rnd = results["random_control"]

            assert v1.hits >= rnd.hits, (
                f"[{wl.name}] random beat v1: random={rnd.hits} v1={v1.hits}"
            )

    def test_report_verdict(self):
        report = SubstitutionReport()
        benchmark = SubstitutionBenchmark()
        for wl in _make_workloads():
            results = benchmark.compare(wl)
            report.add(wl.name, results)

        summary = report.summary()
        assert summary["workloads"] == 2
        assert summary["v1_total_hits"] >= summary["v2_total_hits"]
        assert summary["verdict"] in ("PASS", "NOT_DEMONSTRATED")

    def test_details_has_all_workloads(self):
        report = SubstitutionReport()
        benchmark = SubstitutionBenchmark()
        for wl in _make_workloads():
            results = benchmark.compare(wl)
            report.add(wl.name, results)

        details = report.details()
        assert len(details) == 2
        for row in details:
            assert "workload" in row
            assert "v1_exhaustive_hits" in row
            assert "v2_guided_hits" in row
            assert "coverage" in row
            assert "work_reduction" in row
