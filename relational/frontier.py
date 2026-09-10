"""F4: Trace-guided frontier — proposals from anchors, not brute-force."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

from .anchors import EpochAnchorV1, memory_root
from .classic import (
    MEM_SIZE,
    OPS_VALID,
    ClassicDebugger,
    OPCODE_NAMES,
    TraceEvent,
)
from .transition import valid_opcode_chars
from .trace import serialize_trace, verify_trace


class PruneReason(Enum):
    BUDGET_EXCEEDED = "budget_exceeded"
    CAUSAL_INCOMPAT = "causal_incompat"
    STATE_ALREADY_SEEN = "state_already_seen"
    TRACE_DIVERGENCE = "trace_divergence"
    OUTPUT_LIMIT = "output_limit"
    STOP_REASON = "stop_reason"
    MEMORY_ROOT_COLLISION = "memory_root_collision"


@dataclass(frozen=True)
class Proposal:
    """A candidate single-instruction extension from an anchor."""

    anchor_digest: str
    char: str
    opcode: str
    position: int


@dataclass(frozen=True)
class TraceResult:
    """Outcome of evaluating a proposal against a target."""

    proposal: Proposal
    success: bool
    trace: Tuple[TraceEvent, ...]
    output: bytes
    steps: int
    stop_reason: str
    trace_hash: str
    memory_root: str
    anchor_digest: str
    prune_reason: Optional[PruneReason] = None

    def to_dict(self) -> dict:
        return {
            "proposal": {
                "anchor_digest": self.proposal.anchor_digest,
                "char": self.proposal.char,
                "opcode": self.proposal.opcode,
                "position": self.proposal.position,
            },
            "success": self.success,
            "steps": self.steps,
            "stop_reason": self.stop_reason,
            "trace_hash": self.trace_hash,
            "memory_root": self.memory_root,
            "output_len": len(self.output),
            "prune_reason": self.prune_reason.value if self.prune_reason else None,
        }


@dataclass
class AnchorResult:
    """Full result set for one anchor: proposals evaluated, prunes logged."""

    anchor: EpochAnchorV1
    proposals: List[TraceResult] = field(default_factory=list)
    prunes: List[Tuple[Proposal, PruneReason]] = field(default_factory=list)

    @property
    def hits(self) -> List[TraceResult]:
        return [r for r in self.proposals if r.success]

    @property
    def hit_count(self) -> int:
        return len(self.hits)

    @property
    def prune_count(self) -> int:
        return len(self.prunes)

    def to_dict(self) -> dict:
        return {
            "anchor_digest": self.anchor.digest(),
            "proposals": [r.to_dict() for r in self.proposals],
            "prunes": [{"proposal": p.__dict__, "reason": r.value} for p, r in self.prunes],
            "hit_count": self.hit_count,
            "prune_count": self.prune_count,
        }


@dataclass
class TraceExpander:
    """Generates proposals from an anchor, compatible with its state."""

    max_steps: int = 200
    seen_memory_roots: set = field(default_factory=set)

    def _valid_extensions(self, anchor: EpochAnchorV1) -> List[Tuple[str, str, int]]:
        position = len(anchor.program)
        result = []
        for opcode in OPS_VALID:
            for code in range(33, 127):
                if (code + position) % 94 == opcode:
                    result.append((chr(code), OPCODE_NAMES.get(opcode, "?"), opcode))
                    break
        return result

    def expand(self, anchor: EpochAnchorV1, target: bytes, budget: int = 200) -> AnchorResult:
        result = AnchorResult(anchor=anchor)
        extensions = self._valid_extensions(anchor)

        for char, opcode_name, opcode in extensions:
            if len(result.proposals) + len(result.prunes) >= budget:
                result.prunes.append((
                    Proposal(anchor.digest(), char, opcode_name, len(anchor.program)),
                    PruneReason.BUDGET_EXCEEDED,
                ))
                break

            proposal = Proposal(anchor.digest(), char, opcode_name, len(anchor.program))
            trace: List[TraceEvent] = []
            dbg = anchor.restore(trace=trace)
            dbg.step()

            if dbg.is_stopped and dbg.get_state().stop_reason == "StopReason.OUTPUT_LIMIT":
                result.prunes.append((proposal, PruneReason.OUTPUT_LIMIT))
                continue

            if trace and trace[-1].reason not in ("StopReason.RUNNING",):
                result.prunes.append((proposal, PruneReason.STOP_REASON))
                continue

            new_mem_root = memory_root(dbg.memory)
            if new_mem_root in self.seen_memory_roots:
                result.prunes.append((proposal, PruneReason.STATE_ALREADY_SEEN))
                continue

            child_anchor = EpochAnchorV1.from_debugger(dbg, trace, parent_hash=anchor.digest())

            trace_hash = hashlib.sha256(
                serialize_trace(trace).encode("ascii")
            ).hexdigest()

            if child_anchor.memory_root == anchor.memory_root:
                result.prunes.append((proposal, PruneReason.MEMORY_ROOT_COLLISION))
                continue

            output = bytes(dbg._out)
            success = output == target

            result.proposals.append(TraceResult(
                proposal=proposal,
                success=success,
                trace=tuple(trace),
                output=output,
                steps=dbg.step_count,
                stop_reason=dbg.get_state().stop_reason,
                trace_hash=trace_hash,
                memory_root=new_mem_root,
                anchor_digest=child_anchor.digest(),
            ))

            self.seen_memory_roots.add(new_mem_root)

        return result


@dataclass
class TraceFrontier:
    """Orchestrates trace-guided search over a list of anchors."""

    expander: TraceExpander = field(default_factory=TraceExpander)
    max_budget: int = 500
    results: List[AnchorResult] = field(default_factory=list)

    def search(self, anchors: List[EpochAnchorV1], target: bytes) -> List[AnchorResult]:
        self.results.clear()
        budget_remaining = self.max_budget

        for anchor in anchors:
            if budget_remaining <= 0:
                break
            anchor_result = self.expander.expand(anchor, target, budget=min(budget_remaining, 200))
            self.results.append(anchor_result)
            budget_remaining -= (anchor_result.hit_count + anchor_result.prune_count)

        return self.results

    def all_hits(self) -> List[TraceResult]:
        return [r for ar in self.results for r in ar.hits]

    def all_prunes(self) -> List[Tuple[Proposal, PruneReason]]:
        return [p for ar in self.results for p in ar.prunes]

    def summary(self) -> dict:
        total_hits = sum(ar.hit_count for ar in self.results)
        total_prunes = sum(ar.prune_count for ar in self.results)
        return {
            "anchors_explored": len(self.results),
            "total_hits": total_hits,
            "total_prunes": total_prunes,
            "prune_breakdown": self._prune_breakdown(),
        }

    def _prune_breakdown(self) -> Dict[str, int]:
        breakdown: Dict[str, int] = {}
        for _, reason in self.all_prunes():
            key = reason.value
            breakdown[key] = breakdown.get(key, 0) + 1
        return breakdown
