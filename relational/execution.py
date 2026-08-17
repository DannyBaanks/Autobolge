from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from malbolge import MalbolgeConfig, MalbolgeDebugger, MalbolgeVariant

SPARSE_CONFIG = MalbolgeConfig(
    variant=MalbolgeVariant.ORIGINAL,
    trit_width=10,
    memory_size=3**10,
    rotate_multiplier=3**9,
    use_sparse_memory=True,
)


@dataclass
class RunResult:
    """Result of a bounded Malbolge execution."""

    program: str
    output: str
    steps: int
    stop_reason: str
    terminated: bool
    error: Optional[str] = None
    final_pc: int = 0
    final_a: int = 0
    final_d: int = 0

    @property
    def ok(self) -> bool:
        return self.error is None


def run_bounded(program: str, input_data: str = "", max_steps: int = 20000) -> RunResult:
    """Run a Malbolge program with a hard step budget.

    Uses the step-level debugger (sparse memory, ~instant init) so runaway
    programs cannot hang the synthesizer and thousands of candidates can be
    evaluated quickly. Returns a RunResult with output, step count, and reason.
    """
    try:
        dbg = MalbolgeDebugger(program, input_data, config=SPARSE_CONFIG)
    except Exception as e:
        return RunResult(
            program=program,
            output="",
            steps=0,
            stop_reason="ERROR",
            terminated=False,
            error=str(e),
        )

    steps = 0
    try:
        while not dbg.is_terminated and steps < max_steps:
            dbg.step()
            steps += 1
        state = dbg.get_state()
    except Exception as e:
        try:
            output = dbg.output
        except Exception:
            output = ""
        return RunResult(
            program=program,
            output=output,
            steps=steps,
            stop_reason="ERROR",
            terminated=False,
            error=str(e),
        )

    return RunResult(
        program=program,
        output=dbg.output,
        steps=steps,
        stop_reason=str(state.stop_reason),
        terminated=dbg.is_terminated,
        final_pc=state.c,
        final_a=state.a,
        final_d=state.d,
    )


def prefix_score(output: str, target: str) -> int:
    """Length of the longest exact prefix of `target` present in `output`."""
    n = 0
    for a, b in zip(output, target):
        if a == b:
            n += 1
        else:
            break
    return n


def fitness(result: RunResult, target: str) -> int:
    """Fitness used to rank candidate programs.

    Primary signal: matched prefix length (Malbolge prints incrementally,
    so prefix match is the classic guiding heuristic).
    Then: a bonus if the program's final `a` register already holds the next
    target char (the build-then-print idiom -- the candidate just needs an
    appended `out` instruction to emit it).
    Then: having produced non-NUL output; terminating; shorter execution.
    """
    m = prefix_score(result.output, target)
    bonus = 0
    if m < len(target):
        want = ord(target[m]) % 256
        if (result.final_a % 256) == want:
            bonus = 100_000
    has_non_nul = any(ch != "\x00" for ch in result.output)
    return (
        m * 1_000_000
        + bonus
        + (10_000 if has_non_nul else 0)
        + (1000 if result.terminated else 0)
        - min(result.steps, 10000)
    )


def guided_fitness(result: RunResult, target: str) -> int:
    """Fitness with a soft signal for the next output byte.

    Malbolge often reaches a useful register value before it emits it. The
    ordinary fitness only rewards an exact ``a`` match; this optional variant
    also preserves nearby register states for exploratory searches.
    """
    score = fitness(result, target)
    matched = prefix_score(result.output, target)
    if matched < len(target):
        want = ord(target[matched]) % 256
        actual = result.final_a % 256
        distance = min((actual - want) % 256, (want - actual) % 256)
        score += max(0, 128 - distance) * 1000
    return score


def evaluate_io(program: str, test_cases: List[Tuple[str, str]], max_steps: int = 20000) -> Dict[str, dict]:
    """Run a program against (input, expected_output) pairs and report per-case evidence."""
    results: Dict[str, dict] = {}
    for inp, expected in test_cases:
        r = run_bounded(program, inp, max_steps)
        results[repr(inp)] = {
            "input": inp,
            "expected": expected,
            "output": r.output,
            "match": r.output == expected,
            "steps": r.steps,
            "stop_reason": r.stop_reason,
            "error": r.error,
        }
    return results
