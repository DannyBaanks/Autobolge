from __future__ import annotations

import sys
from pathlib import Path
from typing import Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from relational.classic import ClassicDebugger  # noqa: E402
from relational.execution import run_bounded  # noqa: E402


class MalbolgeInterpreter:
    """Wrapper around the Classic reference engine (relational) for Autobolge."""

    def __init__(self, max_steps=100000):
        self.max_steps = max_steps

    def execute(self, program: str, input_data: str = "") -> Tuple[str, str, int]:
        """Execute a Classic Malbolge program with given input.

        Returns (output, status, steps); status is one of
        "StopReason.TERMINATED", "StopReason.RUNNING", "StopReason.ERROR".
        """
        r = run_bounded(program, input_data, self.max_steps)
        if r.error is not None:
            return str(r.error), "StopReason.ERROR", r.steps
        status = "StopReason.TERMINATED" if r.terminated else "StopReason.RUNNING"
        return r.output, status, r.steps

    def step(self, program: str, input_data: str = ""):
        """Execute one instruction via the Classic debugger, returning the state."""
        return ClassicDebugger(program, input_data).step()

    def get_state(self, program: str, input_data: str = ""):
        """Get the current state of a program via the Classic debugger."""
        return ClassicDebugger(program, input_data).get_state()


def run_malbolge(program: str, input_data: str = "", max_steps=100000):
    """Convenience function to run a Malbolge program."""
    interpreter = MalbolgeInterpreter(max_steps=max_steps)
    return interpreter.execute(program, input_data)


def test_program(program: str, test_cases: list) -> dict:
    """Test a program against multiple input/output cases."""
    results = {}
    for inp, expected in test_cases:
        output, status, steps = run_malbolge(program, input_data=inp)
        results[inp] = {
            "output": output,
            "expected": expected,
            "match": output == expected,
            "status": status,
        }
    return results