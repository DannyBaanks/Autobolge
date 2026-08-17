from __future__ import annotations

import time
from typing import Tuple

from malbolge import MalbolgeDebugger, StopReason
from malbolge.malbolge import eval as eval_classic


class MalbolgeInterpreter:
    """Wrapper around the malbolge interpreter for Autobolge."""

    def __init__(self, max_steps=100000):
        self.max_steps = max_steps

    def execute(self, program: str, input_data: str = "") -> Tuple[str, StopReason, int]:
        """Execute a classic Malbolge program with given input."""
        start = time.perf_counter()
        try:
            output = eval_classic(program, input=input_data, eof="stop")
            elapsed = time.perf_counter() - start
            steps = int(elapsed * 1e6)
            return output, StopReason.TERMINATED, steps
        except Exception as e:
            elapsed = time.perf_counter() - start
            steps = int(elapsed * 1e6)
            return str(e), StopReason.ERROR, steps

    def step(self, program: str, input_data: str = ""):
        """Execute one instruction via the debugger, returning the state."""
        dbg = MalbolgeDebugger(program, input_data)
        return dbg.step()

    def get_state(self, program: str, input_data: str = ""):
        """Get the current state of a program via the debugger."""
        dbg = MalbolgeDebugger(program, input_data)
        return dbg.get_state()


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