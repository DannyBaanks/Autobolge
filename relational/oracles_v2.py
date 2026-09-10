"""F4b: v2 adapters that wrap v1 oracles, emitting anchors and traces."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .anchors import EpochAnchorV1, memory_root
from .classic import ClassicDebugger, TraceEvent, MEM_SIZE
from .transition import valid_opcode_chars as _valid_opcode_chars
from .frontier import AnchorResult, PruneReason, Proposal, TraceExpander, TraceFrontier, TraceResult
from .trace import serialize_trace
from .materialization import Materialization, RunResult, fitness


# ---------------------------------------------------------------------------
# CatalogOracleV2: wraps build_catalog, emits anchors per result
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CatalogEntry:
    """A single catalog result with its anchor."""

    program: str
    output: str
    steps: int
    terminated: bool
    stop_reason: str
    final_a: int
    final_pc: int
    final_d: int
    anchor_digest: str
    memory_root: str


@dataclass
class CatalogOracleV2:
    """Wraps Materialization.build_catalog, emitting CatalogEntry with anchors."""

    inner: Materialization = field(default_factory=Materialization)

    def scan(
        self,
        max_len: int = 4,
        max_steps: int = 3000,
        input_data: str = "",
        engine: str = "reference",
    ) -> List[CatalogEntry]:
        v1_catalog = self.inner.build_catalog(max_len, max_steps, input_data, engine)
        entries: List[CatalogEntry] = []
        for item in v1_catalog:
            trace: List[TraceEvent] = []
            dbg = ClassicDebugger(item["program"], input_data, max_steps, trace=trace)
            while not dbg.is_stopped and dbg.step_count < max_steps:
                dbg.step()
            anchor = EpochAnchorV1.from_debugger(dbg, trace)
            entries.append(CatalogEntry(
                program=item["program"],
                output=item["output"],
                steps=item["steps"],
                terminated=item["terminated"],
                stop_reason=item["stop_reason"],
                final_a=item["final_a"],
                final_pc=item["final_pc"],
                final_d=item["final_d"],
                anchor_digest=anchor.digest(),
                memory_root=anchor.memory_root,
            ))
        return entries

    def matches(self, target: str, max_len: int = 4, input_data: str = "") -> List[CatalogEntry]:
        return [e for e in self.scan(max_len=max_len, input_data=input_data) if e.output == target]


# ---------------------------------------------------------------------------
# PrefixFamilyOracleV2: wraps scan_prefix_family, emits anchors per result
# ---------------------------------------------------------------------------

@dataclass
class PrefixFamilyOracleV2:
    """Wraps Materialization.scan_prefix_family with anchor provenance."""

    inner: Materialization = field(default_factory=Materialization)

    def scan(
        self,
        prefix: str,
        suffix_len: int,
        input_data: str = "",
        max_steps: int = 3000,
        target_output: Optional[str] = None,
        engine: str = "reference",
    ) -> List[CatalogEntry]:
        v1_results = self.inner.scan_prefix_family(
            prefix, suffix_len, input_data, max_steps, target_output, engine
        )
        entries: List[CatalogEntry] = []
        for item in v1_results:
            trace: List[TraceEvent] = []
            dbg = ClassicDebugger(item["program"], input_data, max_steps, trace=trace)
            while not dbg.is_stopped and dbg.step_count < max_steps:
                dbg.step()
            anchor = EpochAnchorV1.from_debugger(dbg, trace)
            entries.append(CatalogEntry(
                program=item["program"],
                output=item["output"],
                steps=item["steps"],
                terminated=item["terminated"],
                stop_reason=item["stop_reason"],
                final_a=item["final_a"],
                final_pc=item["final_pc"],
                final_d=item["final_d"],
                anchor_digest=anchor.digest(),
                memory_root=anchor.memory_root,
            ))
        return entries


# ---------------------------------------------------------------------------
# GuidedFrontierV2: TraceFrontier wrapped as a catalog-compatible oracle
# ---------------------------------------------------------------------------

@dataclass
class GuidedFrontierV2:
    """Search that expands anchors like the v1 catalog but guided by traces."""

    expander: TraceExpander = field(default_factory=TraceExpander)
    max_budget: int = 500
    max_depth: int = 4

    def search(
        self,
        seed_programs: List[str],
        target: bytes,
        input_data: str = "",
        max_steps: int = 3000,
    ) -> Tuple[List[TraceResult], List[Tuple[Proposal, PruneReason]]]:
        anchors: List[EpochAnchorV1] = []
        for prog in seed_programs:
            trace: List[TraceEvent] = []
            dbg = ClassicDebugger(prog, input_data, max_steps, trace=trace)
            while not dbg.is_stopped and dbg.step_count < max_steps:
                dbg.step()
            anchors.append(EpochAnchorV1.from_debugger(dbg, trace))

        frontier = TraceFrontier(expander=self.expander, max_budget=self.max_budget)
        frontier.search(anchors, target)
        return frontier.all_hits(), frontier.all_prunes()
