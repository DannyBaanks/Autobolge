"""Sister implementation of the Zig Malbolge VM.

Both this module and zig/vm.zig implement autobolge-classic-dense-input-underflow/v1.
Gate1 (417/417) validates semantic equivalence. The difftest detects divergences
between implementations, not against an independent authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .classic import (
    MEM_SIZE,
    OPS_VALID,
    OUT_CAP,
    REASON_RUNNING,
    REASON_TERMINATED,
    REASON_INPUT_UNDERFLOW,
    REASON_OUTPUT_LIMIT,
    WHITESPACE,
    ClassicDebugger,
    _compute_tail,
    _fill_memory,
    parse_cells,
)

__all__ = [
    "MEM_SIZE",
    "OPS_VALID",
    "OUT_CAP",
    "REASON_RUNNING",
    "REASON_TERMINATED",
    "WHITESPACE",
    "ClassicDebugger",
    "parse_cells",
    "RunResult",
    "run_bounded",
    "run_bounded_many",
    "prefix_score",
    "fitness",
    "guided_fitness",
    "evaluate_io",
]


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
    reason_code: int = 0

    @property
    def ok(self) -> bool:
        return self.error is None


def _run_one(
    program: str,
    mem: Optional[List[int]],
    input_data: str,
    max_steps: int,
) -> RunResult:
    """Loop canonico de la referencia Classic densa (un solo programa).

    `mem` pre-llenado = None: ClassicDebugger hace el relleno estandar.
    Es la UNICA implementacion del loop de pasos; run_bounded y
    run_bounded_many lo comparten, asi que no hay deriva entre rutas.
    """
    try:
        dbg = ClassicDebugger(program, input_data, max_steps, mem=mem)
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
        while not dbg.is_stopped and steps < max_steps:
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
        stop_reason=state.stop_reason,
        terminated=dbg.is_terminated,
        final_pc=state.c,
        final_a=state.a,
        final_d=state.d,
        reason_code=state.reason_code,
    )


def run_bounded(program: str, input_data: str = "", max_steps: int = 20000) -> RunResult:
    """Run a Malbolge program with a hard step budget.

    Referencia CLASSIC densa: cinta 59049 celdas rellenada por la recurrencia
    crazy, decode (cell+pc)%94 con NOP para invalidas, input real con
    terminacion por bajoflujo -- exactamente la misma maquina que implementa
    el motor Zig (zig/vm.zig). Anclada en primitivas de la toolkit malbolge
    (crazy_operation, ENCRYPTION_TRANSLATE), NO en MalbolgeInterpreter del
    paquete malbolge (ausente de la toolkit y con semantica distinta).
    """
    return _run_one(program, None, input_data, max_steps)


def run_bounded_many(
    programs: List[str],
    input_data: str = "",
    max_steps: int = 20000,
) -> List[RunResult]:
    """Bulk de la referencia Classic densa para catalogos exhaustivos.

    Semantica identica a run_bounded (mismo _run_one / ClassicDebugger.step).
    Solo cambia el relleno: la cola de la cinta a partir de la posicion n
    depende unicamente de las dos ultimas celdas, asi que se computa UNA vez
    por par (prev2, prev1) con _compute_tail y se copia por programa con
    `cells + tail[:59049-n]`. Cada programa recibe su propia copia, luego los
    writes de op39/op62 mutan solo la cinta local (fidelidad densa exacta).
    """
    # Parse de todos (mismo contrato de error que run_bounded: ValueError -> ERROR)
    items: List[Optional[Tuple[str, List[int]]]] = [None] * len(programs)
    parts: List[Optional[RunResult]] = [None] * len(programs)
    for i, program in enumerate(programs):
        try:
            cells = parse_cells(program)
        except Exception as e:
            parts[i] = RunResult(
                program=program,
                output="",
                steps=0,
                stop_reason="ERROR",
                terminated=False,
                error=str(e),
            )
            continue
        items[i] = (program, cells)

    # Agrupar por par (prev2, prev1) de las dos ultimas celdas (n>=2).
    groups: Dict[Tuple[int, int], List[Tuple[int, List[int]]]] = {}
    direct: List[Tuple[int, List[int]]] = []
    for i, item in enumerate(items):
        if item is None:
            continue
        cells = item[1]
        if len(cells) >= 2:
            groups.setdefault((cells[-2], cells[-1]), []).append((i, cells))
        else:
            direct.append((i, cells))

    # n = 0/1: irrelevantes en volumen (<= 9 programas); relleno estandar.
    for i, cells in direct:
        program = items[i][0]
        parts[i] = _run_one(program, _fill_memory(cells), input_data, max_steps)

    # n >= 2: cola compartida por par (una vez), copia list(tail) por programa.
    for (p2, p1), entries in groups.items():
        tail = _compute_tail(p1, p2, MEM_SIZE - 2)
        for i, cells in entries:
            n = len(cells)
            program = items[i][0]
            mem = cells + list(tail[: MEM_SIZE - n])
            parts[i] = _run_one(program, mem, input_data, max_steps)

    assert all(part is not None for part in parts)
    return [part for part in parts if part is not None]


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
