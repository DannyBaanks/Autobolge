"""Materialized, immutable Classic continuation anchors."""

from __future__ import annotations

import hashlib
import json
import struct
from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple

from .classic import ClassicDebugger, TraceEvent
from .trace import serialize_trace


def memory_root(memory: Iterable[int]) -> str:
    digest = hashlib.sha256()
    for cell in memory:
        digest.update(struct.pack("<H", cell))
    return digest.hexdigest()


@dataclass(frozen=True)
class EpochAnchorV1:
    """Complete continuation state; registers alone are intentionally insufficient."""

    schema: str
    program: str
    input_data: bytes
    input_cursor: int
    output: bytes
    output_cursor: int
    step: int
    pc: int
    a: int
    d: int
    stop_reason: str
    trace_hash: str
    memory_root: str
    memory: Tuple[int, ...]
    parent_hash: Optional[str] = None

    @classmethod
    def from_debugger(
        cls,
        debugger: ClassicDebugger,
        trace: Iterable[TraceEvent] = (),
        parent_hash: Optional[str] = None,
    ) -> "EpochAnchorV1":
        raw_memory = tuple(debugger.memory)
        trace_hash = hashlib.sha256(serialize_trace(trace).encode("ascii")).hexdigest()
        return cls(
            schema="autobolge-epoch-anchor/v1",
            program=debugger.program,
            input_data=debugger._input,
            input_cursor=debugger._input_pos,
            output=bytes(debugger._out),
            output_cursor=len(debugger._out),
            step=debugger.step_count,
            pc=debugger.c,
            a=debugger.a,
            d=debugger.d,
            stop_reason=debugger.get_state().stop_reason,
            trace_hash=trace_hash,
            memory_root=memory_root(raw_memory),
            memory=raw_memory,
            parent_hash=parent_hash,
        )

    def digest(self) -> str:
        payload = "|".join((self.schema, self.program, self.memory_root, str(self.step), str(self.pc), str(self.a), str(self.d), self.trace_hash, self.parent_hash or ""))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def delta(self, parent: Optional["EpochAnchorV1"]) -> List[Tuple[int, int]]:
        if parent is None:
            return list(enumerate(self.memory))
        if len(parent.memory) != len(self.memory):
            raise ValueError("anchor memory sizes differ")
        return [(index, value) for index, value in enumerate(self.memory) if value != parent.memory[index]]

    def restore(self, trace: Optional[List[TraceEvent]] = None) -> ClassicDebugger:
        debugger = ClassicDebugger(self.program, self.input_data.decode("utf-8"), trace=trace)
        debugger._mem = list(self.memory)
        debugger._input_pos = self.input_cursor
        debugger._out = list(self.output)
        debugger._step_count = self.step
        debugger._c, debugger._a, debugger._d = self.pc, self.a, self.d
        debugger._halted = self.stop_reason in ("StopReason.TERMINATED", "StopReason.INPUT_UNDERFLOW")
        debugger._stopped = self.stop_reason == "StopReason.OUTPUT_LIMIT"
        return debugger

    def to_json(self) -> str:
        return json.dumps({
            "schema": self.schema,
            "program": self.program,
            "input_data": list(self.input_data),
            "input_cursor": self.input_cursor,
            "output": list(self.output),
            "output_cursor": self.output_cursor,
            "step": self.step,
            "pc": self.pc,
            "a": self.a,
            "d": self.d,
            "stop_reason": self.stop_reason,
            "trace_hash": self.trace_hash,
            "memory_root": self.memory_root,
            "memory": self.memory,
            "parent_hash": self.parent_hash,
            "digest": self.digest(),
        }, ensure_ascii=True, sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_json(cls, text: str) -> "EpochAnchorV1":
        data = json.loads(text)
        if data.get("schema") != "autobolge-epoch-anchor/v1":
            raise ValueError("unsupported anchor schema")
        anchor = cls(
            schema=data["schema"],
            program=data["program"],
            input_data=bytes(data["input_data"]),
            input_cursor=data["input_cursor"],
            output=bytes(data["output"]),
            output_cursor=data["output_cursor"],
            step=data["step"],
            pc=data["pc"],
            a=data["a"],
            d=data["d"],
            stop_reason=data["stop_reason"],
            trace_hash=data["trace_hash"],
            memory_root=data["memory_root"],
            memory=tuple(data["memory"]),
            parent_hash=data.get("parent_hash"),
        )
        if anchor.digest() != data.get("digest"):
            raise ValueError("anchor digest mismatch")
        return anchor
