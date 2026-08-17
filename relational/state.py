from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass(frozen=True)
class MalbolgeSnapshot:
    """A snapshot of Malbolge VM state (pc, registers, memory hash, buffers)."""

    pc: int
    a: int
    d: int
    memory_hash: str
    step_count: int
    stop_reason: str
    output_buffer: bytes
    input_buffer: bytes

    def __hash__(self):
        return hash(
            (
                self.pc,
                self.a,
                self.d,
                self.memory_hash,
                self.step_count,
                self.stop_reason,
                self.output_buffer,
                self.input_buffer,
            )
        )


class MalbolgeStateWrapper:
    """Mutable wrapper around Malbolge state used during searches."""

    def __init__(
        self,
        program: str,
        pc: int = 0,
        a: int = 0,
        d: int = 0,
        step_count: int = 0,
        input_buffer: bytes = b"",
        output_buffer: bytes = b"",
    ):
        self.program = program
        self.pc = pc
        self.a = a
        self.d = d
        self.step_count = step_count
        self.input_buffer = input_buffer
        self.output_buffer = output_buffer
        self._mem = {
            i: ord(c) for i, c in enumerate(program) if 33 <= ord(c) <= 126
        }
        self._mem_hash = None

    def _compute_mem_hash(self):
        relevant = {k: v for k, v in self._mem.items() if k < 1000}
        return hashlib.sha256(str(sorted(relevant.items())).encode()).hexdigest()[:16]

    @property
    def memory_hash(self):
        if self._mem_hash is None:
            self._mem_hash = self._compute_mem_hash()
        return self._mem_hash

    def __hash__(self):
        return hash((self.program, self.pc, self.a, self.d, self.memory_hash))

    def __eq__(self, other):
        return (
            isinstance(other, MalbolgeStateWrapper)
            and self.program == other.program
            and self.pc == other.pc
            and self.a == other.a
            and self.d == other.d
        )

    def to_dict(self):
        return {
            "program": self.program,
            "pc": self.pc,
            "a": self.a,
            "d": self.d,
            "memory_hash": self.memory_hash,
        }

    @classmethod
    def from_program(cls, program: str, input_data: bytes = b""):
        return cls(program=program, input_buffer=input_data)


def are_equivalent_states(s1, s2, ignore_output=False):
    return (
        s1.pc == s2.pc
        and s1.a == s2.a
        and s1.d == s2.d
        and s1.memory_hash == s2.memory_hash
    )


def state_distance(s1, s2):
    dist = 0.0
    if s1.pc != s2.pc:
        dist += abs(s1.pc - s2.pc) * 0.1
    if s1.a != s2.a:
        dist += abs(s1.a - s2.a) * 0.01
    if s1.d != s2.d:
        dist += abs(s1.d - s2.d) * 0.01
    if s1.memory_hash != s2.memory_hash:
        dist += 1.0
    return dist