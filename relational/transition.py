from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from malbolge import MalbolgeDebugger, OPS_VALID, StopReason

from .execution import SPARSE_CONFIG
from .state import MalbolgeSnapshot, MalbolgeStateWrapper

OPCODE_NAMES = {
    4: "jmp",
    5: "out",
    23: "in",
    39: "rotr",
    40: "mov_d",
    62: "crz",
    68: "nop",
    81: "end",
}


@dataclass(frozen=True)
class Transition:
    """Represents a single state transition in Malbolge."""

    from_state: MalbolgeSnapshot
    to_state: MalbolgeSnapshot
    opcode: str
    input_consumed: bytes
    output_produced: bytes
    step_cost: int = 1
    char: str = ""

    def __hash__(self):
        return hash(
            (
                self.from_state,
                self.to_state,
                self.opcode,
                self.input_consumed,
                self.output_produced,
            )
        )

    def __eq__(self, other):
        if not isinstance(other, Transition):
            return False
        return (
            self.from_state == other.from_state
            and self.to_state == other.to_state
            and self.opcode == other.opcode
            and self.input_consumed == other.input_consumed
            and self.output_produced == other.output_produced
        )


def snapshot_from_state(state, program: str) -> MalbolgeSnapshot:
    """Convert a MalbolgeState from the debugger into a MalbolgeSnapshot."""
    mem_hash = hashlib.sha256(
        (program + f"|{state.c}").encode()
    ).hexdigest()[:16]
    return MalbolgeSnapshot(
        pc=state.c,
        a=state.a,
        d=state.d,
        memory_hash=mem_hash,
        step_count=state.step_count,
        stop_reason=str(state.stop_reason),
        output_buffer=state.output.encode(),
        input_buffer=b"",
    )


def valid_opcode_chars(position: int) -> List[Dict[str, object]]:
    """Return chars that decode to a valid opcode at a given position."""
    candidates = []
    for opcode in OPS_VALID:
        for code in range(33, 127):
            if (code + position) % 94 == opcode:
                candidates.append(
                    {"char": chr(code), "code": code, "opcode": opcode}
                )
                break
    return candidates


class TransitionSystem:
    """Manages transitions between Malbolge states."""

    def __init__(self):
        self._transitions: Dict[MalbolgeSnapshot, list] = {}
        self._reverse_transitions: Dict[MalbolgeSnapshot, list] = {}

    def add_transition(self, transition):
        from_snap = transition.from_state
        to_snap = transition.to_state
        if from_snap not in self._transitions:
            self._transitions[from_snap] = []
        self._transitions[from_snap].append(transition)
        if to_snap not in self._reverse_transitions:
            self._reverse_transitions[to_snap] = []
        self._reverse_transitions[to_snap].append(transition)

    def get_transitions_from(self, state):
        return self._transitions.get(state, [])

    def get_transitions_to(self, state):
        return self._reverse_transitions.get(state, [])

    def has_path(self, from_state, to_state, max_depth=100):
        """Check if there is a path from from_state to to_state."""
        visited = set()
        queue = [(from_state, 0)]
        while queue:
            current, depth = queue.pop(0)
            if current == to_state:
                return True
            if depth >= max_depth or current in visited:
                continue
            visited.add(current)
            for t in self.get_transitions_from(current):
                queue.append((t.to_state, depth + 1))
        return False

    def find_path(self, from_state, to_state, max_depth=100):
        """Find a path from from_state to to_state."""
        visited = set()
        queue = [(from_state, [])]
        while queue:
            current, path = queue.pop(0)
            if current == to_state:
                return path
            if len(path) >= max_depth or current in visited:
                continue
            visited.add(current)
            for t in self.get_transitions_from(current):
                queue.append((t.to_state, path + [t]))
        return None


def discover_transitions(program: str, input_data: str = "", max_steps: int = 1000) -> List[Transition]:
    """Discover the single-step transitions reachable from a program."""
    transitions: List[Transition] = []
    dbg = MalbolgeDebugger(program, input_data, config=SPARSE_CONFIG)
    initial = dbg.get_state()
    initial_snap = snapshot_from_state(initial, program)

    if dbg.is_terminated:
        return transitions

    next_pos = len(program)
    for candidate in valid_opcode_chars(next_pos):
        test_prog = program + candidate["char"]
        test_dbg = MalbolgeDebugger(test_prog, input_data, config=SPARSE_CONFIG)
        next_state = test_dbg.step()
        to_snap = snapshot_from_state(next_state, test_prog)
        transitions.append(
            Transition(
                from_state=initial_snap,
                to_state=to_snap,
                opcode=OPCODE_NAMES.get(candidate["opcode"], "?"),
                input_consumed=b"",
                output_produced=next_state.output.encode(),
                step_cost=1,
                char=candidate["char"],
            )
        )
    return transitions