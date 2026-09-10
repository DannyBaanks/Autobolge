"""F5: Substitution benchmark — measure that guided search reduces work without hiding failures."""

from __future__ import annotations

import hashlib
import random
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .anchors import EpochAnchorV1
from .classic import ClassicDebugger, TraceEvent, MEM_SIZE
from .transition import valid_opcode_chars as _valid_opcode_chars
from .frontier import PruneReason, Proposal, TraceExpander, TraceFrontier, TraceResult
from .oracles_v2 import CatalogOracleV2, CatalogEntry
from .materialization import Materialization


# ---------------------------------------------------------------------------
# Workload definition
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Workload:
    """A benchmark workload with explicit oracle horizon."""

    name: str
    programs: Tuple[str, ...]
    input_data: str
    max_steps: int
    horizon: int  # max catalog length for exhaustive v1
    target: bytes  # byte-level target for guided search


# ---------------------------------------------------------------------------
# Method results
# ---------------------------------------------------------------------------

@dataclass
class MethodResult:
    """Outcome of one method on one workload."""

    method: str
    hits: int
    total_proposals: int
    elapsed_s: float
    prune_breakdown: Dict[str, int] = field(default_factory=dict)
    hit_programs: List[str] = field(default_factory=list)
    hit_outputs: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Benchmark harness
# ---------------------------------------------------------------------------

@dataclass
class SubstitutionBenchmark:
    """Runs v1 exhaustive, v2 guided, and random control on a workload."""

    def run_v1_exhaustive(self, wl: Workload) -> MethodResult:
        t0 = time.perf_counter()
        programs: List[str] = []
        level: List[str] = list(wl.programs)
        for length in range(0, wl.horizon + 1):
            programs.extend(level)
            if length < wl.horizon:
                nxt: List[str] = []
                for prog in level:
                    for cand in _valid_opcode_chars(len(prog)):
                        nxt.append(prog + cand["char"])
                level = nxt

        hits = 0
        hit_programs: List[str] = []
        for prog in programs:
            dbg = ClassicDebugger(prog, wl.input_data, wl.max_steps)
            while not dbg.is_stopped and dbg.step_count < wl.max_steps:
                dbg.step()
            if dbg.output.encode() == wl.target:
                hits += 1
                hit_programs.append(prog)

        elapsed = time.perf_counter() - t0
        return MethodResult(
            method="v1_exhaustive",
            hits=hits,
            total_proposals=len(programs),
            elapsed_s=elapsed,
            hit_programs=hit_programs,
        )

    def run_v2_guided(self, wl: Workload) -> MethodResult:
        t0 = time.perf_counter()
        hits = 0
        hit_programs: List[str] = []
        total_proposals = 0
        seen_memory: set = set()
        prune_breakdown: Dict[str, int] = {}

        level: List[str] = list(wl.programs)
        for length in range(0, wl.horizon + 1):
            next_level: List[str] = []
            for prog in level:
                trace: List[TraceEvent] = []
                dbg = ClassicDebugger(prog, wl.input_data, wl.max_steps, trace=trace)
                while not dbg.is_stopped and dbg.step_count < wl.max_steps:
                    dbg.step()
                total_proposals += 1

                from .anchors import memory_root as _mr
                mem_root = _mr(dbg.memory)
                if mem_root in seen_memory:
                    prune_breakdown["state_already_seen"] = prune_breakdown.get("state_already_seen", 0) + 1
                    continue
                seen_memory.add(mem_root)

                if dbg.output.encode() == wl.target:
                    hits += 1
                    hit_programs.append(prog)

                if length < wl.horizon:
                    for cand in _valid_opcode_chars(len(prog)):
                        next_level.append(prog + cand["char"])
            level = next_level

        elapsed = time.perf_counter() - t0
        return MethodResult(
            method="v2_guided",
            hits=hits,
            total_proposals=total_proposals,
            elapsed_s=elapsed,
            prune_breakdown=prune_breakdown,
            hit_programs=hit_programs,
        )

    def run_random_control(self, wl: Workload, seed: int = 42) -> MethodResult:
        t0 = time.perf_counter()
        rng = random.Random(seed)
        programs = []
        for prog in wl.programs:
            position = len(prog)
            for _ in range(4):
                candidates = []
                for code in range(33, 127):
                    if (code + position) % 94 in (4, 5, 23, 39, 40, 62, 68, 81):
                        candidates.append(chr(code))
                if candidates:
                    prog += rng.choice(candidates)
                    position += 1
            programs.append(prog)

        hits = 0
        hit_programs = []
        for prog in programs:
            dbg = ClassicDebugger(prog, wl.input_data, wl.max_steps)
            while not dbg.is_stopped and dbg.step_count < wl.max_steps:
                dbg.step()
            if dbg.output.encode() == wl.target:
                hits += 1
                hit_programs.append(prog)

        elapsed = time.perf_counter() - t0
        return MethodResult(
            method="random_control",
            hits=hits,
            total_proposals=len(programs),
            elapsed_s=elapsed,
            hit_programs=hit_programs,
        )

    def compare(self, wl: Workload) -> Dict[str, MethodResult]:
        v1 = self.run_v1_exhaustive(wl)
        v2 = self.run_v2_guided(wl)
        rnd = self.run_random_control(wl)
        return {"v1_exhaustive": v1, "v2_guided": v2, "random_control": rnd}


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

@dataclass
class SubstitutionReport:
    """Aggregate results across workloads."""

    workload_results: Dict[str, Dict[str, MethodResult]] = field(default_factory=dict)

    def add(self, wl_name: str, results: Dict[str, MethodResult]) -> None:
        self.workload_results[wl_name] = results

    def summary(self) -> Dict[str, object]:
        totals: Dict[str, Dict[str, int]] = {}
        for wl_name, methods in self.workload_results.items():
            for method_name, result in methods.items():
                if method_name not in totals:
                    totals[method_name] = {"hits": 0, "proposals": 0}
                totals[method_name]["hits"] += result.hits
                totals[method_name]["proposals"] += result.total_proposals

        v1_hits = totals.get("v1_exhaustive", {}).get("hits", 0)
        v2_hits = totals.get("v2_guided", {}).get("hits", 0)
        v1_proposals = totals.get("v1_exhaustive", {}).get("proposals", 0)
        v2_proposals = totals.get("v2_guided", {}).get("proposals", 0)

        if v1_hits > 0:
            coverage = v2_hits / v1_hits
        else:
            coverage = 1.0 if v2_hits == 0 else 0.0

        if v1_proposals > 0:
            work_reduction = 1.0 - (v2_proposals / v1_proposals)
        else:
            work_reduction = 0.0

        verdict = "PASS" if v2_hits >= v1_hits else "NOT_DEMONSTRATED"

        return {
            "workloads": len(self.workload_results),
            "v1_total_hits": v1_hits,
            "v2_total_hits": v2_hits,
            "v1_total_proposals": v1_proposals,
            "v2_total_proposals": v2_proposals,
            "coverage": round(coverage, 4),
            "work_reduction": round(work_reduction, 4),
            "verdict": verdict,
        }

    def details(self) -> List[Dict[str, object]]:
        rows = []
        for wl_name, methods in self.workload_results.items():
            row: Dict[str, object] = {"workload": wl_name}
            for method_name, result in methods.items():
                row[f"{method_name}_hits"] = result.hits
                row[f"{method_name}_proposals"] = result.total_proposals
                row[f"{method_name}_elapsed_s"] = round(result.elapsed_s, 3)
            v1 = methods.get("v1_exhaustive")
            v2 = methods.get("v2_guided")
            if v1 and v2:
                row["coverage"] = v2.hits / v1.hits if v1.hits > 0 else 1.0
                row["work_reduction"] = 1.0 - (v2.total_proposals / v1.total_proposals) if v1.total_proposals > 0 else 0.0
            rows.append(row)
        return rows
