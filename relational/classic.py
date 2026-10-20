from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

ENCRYPTION_TRANSLATE = (
    "5z]&gqtyfr$(we4{WP)H-Zn,[%\\3dL+Q;>U!pJS72FhOA1C"
    "B6v^=I_0/8|jsb9m<.TVac`uY*MK'X~xDl}REokN:#?G\"i@"
)

_CRAZY_TRITS = (
    (1, 0, 0),
    (1, 0, 2),
    (2, 2, 1),
)

def crazy_operation(x: int, y: int) -> int:
    res = 0
    p = 1
    for _ in range(10):
        res += _CRAZY_TRITS[y % 3][x % 3] * p
        x //= 3
        y //= 3
        p *= 3
    return res

MEM_SIZE = 59049
OUT_CAP = 65536
LAST = MEM_SIZE - 1
POW9 = 19683
HALF = 243

OPS_VALID = (4, 5, 23, 39, 40, 62, 68, 81)
WHITESPACE = (" ", "\n", "\r", "\t")

REASON_TERMINATED = "StopReason.TERMINATED"
REASON_RUNNING = "StopReason.RUNNING"
REASON_INPUT_UNDERFLOW = "StopReason.INPUT_UNDERFLOW"
REASON_OUTPUT_LIMIT = "StopReason.OUTPUT_LIMIT"

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

# ---------------------------------------------------------------------------
# Referencia CLASSIC densa (semantica de Malbolge-Translator zig/src/engine.zig)
# en Python puro, anclada en primitivas de la toolkit malbolge
# (malbolge_toolkit): crazy_operation / ENCRYPTION_TRANSLATE.
#
# El Zig motor (zig/vm.zig) Y esta referencia implementan la misma maquina:
#   - cinta [59049]u16 cero-inicializada y rellenada al completo por la
#     recurrencia crazy (wrap de las semillas a mem[MEM_SIZE-1] == 0)
#   - decode con widening: op = (cell + c) % 94 ; invalidas -> NOP
#   - opcodes 4/5/23/39/40/62/68/81 ; post-exec encrypt + c++/d++ con wrap
#   - input REAL; bajoflujo de input TERMINA la ejecucion
#   - steps cuenta toda instruccion ejecutada, incluida la que termina
#
# NO usa MalbolgeInterpreter (opcode-level, c/d sin wrap, HALT en program_end):
# seria una maquina distinta y la paridad con el motor fallaria.
# ---------------------------------------------------------------------------


def parse_cells(program: str) -> List[int]:
    """Replicate malbolge.core.parse_source exactly (whitespace skip, validation)."""
    cells: List[int] = []
    for char in program:
        if char in WHITESPACE:
            continue
        i = len(cells)
        if ord(char) > 0xFFFF:
            raise ValueError(f"Cell value for '{char}' exceeds u16 at position {i}")
        if (ord(char) + i) % 94 not in OPS_VALID:
            raise ValueError(f"Invalid character '{char}' at position {i}")
        if i >= MEM_SIZE:
            raise ValueError(f"Source file is too long (max {MEM_SIZE} cells)")
        cells.append(ord(char))
    return cells


_CRAZY5: Optional[List[List[int]]] = None


def _build_crazy5() -> List[List[int]]:
    # tabla 243x243 = crazy de 5 trits. Se deriva de crazy_operation de la
    # toolkit: para a, b < 243 los trits altos de ambos inputs son 0 y su
    # contribucion es multiplo de 243, asi que crazy_operation(a, b) % 243
    # es exactamente el crazy de 5 trits (verificado valor a valor).
    t = [[0] * HALF for _ in range(HALF)]
    for i in range(HALF):
        for j in range(HALF):
            t[i][j] = crazy_operation(i, j) % HALF
    return t


def _crazy(a: int, b: int) -> int:
    global _CRAZY5
    if _CRAZY5 is None:
        _CRAZY5 = _build_crazy5()
    return _CRAZY5[a % HALF][b % HALF] + HALF * _CRAZY5[a // HALF][b // HALF]


def _fill_memory(cells: List[int]) -> List[int]:
    mem = [0] * MEM_SIZE
    n = min(len(cells), MEM_SIZE)
    mem[:n] = cells[:n]
    for i in range(n, MEM_SIZE):
        prev1 = mem[i - 1] if i >= 1 else mem[MEM_SIZE - 1]
        prev2 = mem[i - 2] if i >= 2 else mem[MEM_SIZE - 1]
        mem[i] = _crazy(prev1, prev2)
    return mem


def _compute_tail(prev1: int, prev2: int, length: int) -> List[int]:
    """mem[n..] de la cinta para programas de >=2 celdas.

    La recurrencia del relleno es de orden 2: a partir de la posicion n todo
    queda determinado por las dos ultimas celdas (prev1, prev2). Asi:

      tail[0] = crazy(prev1, prev2)        (= mem[n])
      tail[1] = crazy(tail[0], prev1)      (= mem[n+1])
      tail[i] = crazy(tail[i-1], tail[i-2])  para i >= 2

    (verificado == _fill_memory para programas >=2 celdas). Permite construir
    catalogos exhaustivos compartiendo una sola cola por par en lugar de
    re-llenar 59049 celdas por programa.
    """
    tail = [0] * length
    if length == 0:
        return tail
    tail[0] = _crazy(prev1, prev2)
    for i in range(1, length):
        if i == 1:
            tail[i] = _crazy(tail[0], prev1)
        else:
            tail[i] = _crazy(tail[i - 1], tail[i - 2])
    return tail


@dataclass
class ClassicState:
    """Estado de la maquina Classic (compatible con lo que consumers esperan)."""

    c: int
    a: int
    d: int
    step_count: int
    stop_reason: str
    output: str
    opcode_name: str = ""
    raw_instruction: str = ""
    reason_code: int = 0


@dataclass(frozen=True)
class TraceEvent:
    """Canonical per-instruction event used by replay/checkpoint tooling."""

    step: int
    pre_c: int
    pre_a: int
    pre_d: int
    opcode: int
    effects: int
    post_c: int
    post_a: int
    post_d: int
    reason: str


class ClassicDebugger:
    """Debugger paso a paso de la maquina Classic densa.

    Sustituye al MalbolgeDebugger del paquete malbolge (ausente en la
    toolkit): misma interfaz util (get_state/step/is_terminated/output) y
    semantica de motor COMPARTIDA con run_bounded.
    """

    def __init__(
        self,
        program: str,
        input_data: str = "",
        max_steps: int = 20000,
        mem: Optional[List[int]] = None,
        trace: Optional[List[TraceEvent]] = None,
    ):
        self.program = program
        self.input_data = input_data
        self.max_steps = max_steps
        self._trace = trace
        self._cells = parse_cells(program)
        self._reset(mem)

    def _reset(self, mem: Optional[List[int]] = None) -> None:
        # mem pre-llenado: ruta bulk (run_bounded_many) compartiendo colas
        # por par; la semantica de step() es identica, cada programa tiene su
        # propia copia de la cinta para los writes de op39/op62.
        self._mem = mem if mem is not None else _fill_memory(self._cells)
        self._a = 0
        self._c = 0
        self._d = 0
        self._step_count = 0
        self._halted = False
        self._stopped = False
        self._reason_code = 0  # 0=step_limit/running, 1=halt, 2=input_underflow
        self._input = self.input_data.encode("utf-8")
        self._input_pos = 0
        self._out: List[int] = []
        self._last_op_name = ""
        self._last_raw = ""
        if self._trace is not None:
            self._trace.clear()

    def _record_trace(self, pre_c: int, pre_a: int, pre_d: int, op: int, effects: int) -> None:
        if self._trace is not None:
            self._trace.append(TraceEvent(
                step=self._step_count,
                pre_c=pre_c,
                pre_a=pre_a,
                pre_d=pre_d,
                opcode=op,
                effects=effects,
                post_c=self._c,
                post_a=self._a,
                post_d=self._d,
                reason=self.get_state().stop_reason,
            ))

    # -- public machine view -------------------------------------------------

    @property
    def is_terminated(self) -> bool:
        return self._halted

    @property
    def is_stopped(self) -> bool:
        return self._halted or self._stopped

    @property
    def a(self) -> int:
        return self._a

    @property
    def c(self) -> int:
        return self._c

    @property
    def d(self) -> int:
        return self._d

    @property
    def step_count(self) -> int:
        return self._step_count

    @property
    def output(self) -> str:
        return "".join(chr(b) for b in self._out)

    @property
    def memory(self) -> List[int]:
        return self._mem

    def _compose(self) -> ClassicState:
        return ClassicState(
            c=self._c,
            a=self._a,
            d=self._d,
            step_count=self._step_count,
            stop_reason=(REASON_INPUT_UNDERFLOW if self._reason_code == 2 else
                         REASON_TERMINATED if self._halted else
                         REASON_OUTPUT_LIMIT if self._stopped else REASON_RUNNING),
            output=self.output,
            opcode_name=self._last_op_name,
            raw_instruction=self._last_raw,
            reason_code=self._reason_code,
        )

    def _instruction_at(self, c: int) -> tuple:
        cell = self._mem[c]
        op = (cell + c) % 94
        raw = chr(cell) if 33 <= cell <= 126 else f"<{cell}>"
        return op, raw

    def get_state(self) -> ClassicState:
        """Estado actual; opcode_name/raw_instruction = proxima instruccion (pc)."""
        op, raw = self._instruction_at(self._c)
        return ClassicState(
            c=self._c,
            a=self._a,
            d=self._d,
            step_count=self._step_count,
            stop_reason=(REASON_INPUT_UNDERFLOW if self._reason_code == 2 else
                         REASON_TERMINATED if self._halted else
                         REASON_OUTPUT_LIMIT if self._stopped else REASON_RUNNING),
            output=self.output,
            opcode_name=OPCODE_NAMES.get(op, "?"),
            raw_instruction=raw,
            reason_code=self._reason_code,
        )

    def step(self) -> ClassicState:
        """Ejecuta UNA instruccion; opcode_name/raw_instruction = la ejecutada."""
        if self._halted:
            return self.get_state()
        if self._stopped:
            return self.get_state()
        self._step_count += 1
        pre_c, pre_a, pre_d = self._c, self._a, self._d
        cell = self._mem[self._c]
        op = (cell + self._c) % 94
        effects = 0
        self._last_op_name = OPCODE_NAMES.get(op, "?")
        self._last_raw = chr(cell) if 33 <= cell <= 126 else f"<{cell}>"

        if op == 4:  # jmp [d]
            self._c = self._mem[self._d]
            effects |= 1
        elif op == 5:  # out a%256
            if len(self._out) < OUT_CAP:
                self._out.append(self._a % 256)
                effects |= 2
            else:
                self._stopped = True
                self._reason_code = 3
                self._record_trace(pre_c, pre_a, pre_d, op, effects)
                return self._compose()
        elif op == 23:  # in
            if self._input_pos < len(self._input):
                self._a = self._input[self._input_pos]
                self._input_pos += 1
                effects |= 4
            else:
                self._halted = True
                self._reason_code = 2
                self._record_trace(pre_c, pre_a, pre_d, op, effects)
                return self._compose()
        elif op == 39:  # rotr [d]
            v = self._mem[self._d]
            self._mem[self._d] = (v // 3) + (v % 3) * POW9
            self._a = self._mem[self._d]
            effects |= 8
        elif op == 40:  # mov d
            self._d = self._mem[self._d]
        elif op == 62:  # crz
            r = _crazy(self._a, self._mem[self._d])
            self._mem[self._d] = r
            self._a = r
            effects |= 8
        elif op == 81:  # end
            self._halted = True
            self._reason_code = 1
            self._record_trace(pre_c, pre_a, pre_d, op, effects)
            return self._compose()
        # else: NOP

        enc = self._mem[self._c]
        if 33 <= enc <= 126:
            # ENCRYPTION_TRANSLATE es un str: indizar da el caracter; la cinta
            # guarda codigos ASCII (como el motor: ENCRYPT[...] devuelve u8).
            self._mem[self._c] = ord(ENCRYPTION_TRANSLATE[enc - 33])
            effects |= 16
        self._c = (self._c + 1) % MEM_SIZE
        self._d = (self._d + 1) % MEM_SIZE
        self._record_trace(pre_c, pre_a, pre_d, op, effects)
        return self._compose()


def run_reference(program: str, input_data: str = "", max_steps: int = 20000):
    """Corre una programa con la maquina Classic densa (para extensiones)."""
    dbg = ClassicDebugger(program, input_data, max_steps)
    steps = 0
    while not dbg.is_stopped and steps < max_steps:
        dbg.step()
        steps += 1
    state = dbg.get_state()
    return dbg.output, steps, dbg.is_terminated, state
