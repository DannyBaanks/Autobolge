"""Shape families: Malbolge programs derived by positional arithmetic.

Brute force enumerates cells (8^length). A shape fixes WHAT the program does
and lets position arithmetic force WHERE each instruction must sit, so a family
of long, sparse programs can be listed exactly and every member carries a
prediction computed before execution.

Pure arithmetic: nothing here executes Malbolge. Predictions use Autobolge's
semantic contract (classic-dense, input underflow terminates) and are checked
by `experiments/shape_families.py` against the Zig batch engine.

Families
--------
call_return   main calls a subroutine that returns into the caller's region.
              After a jmp, c moves but d keeps stepping from the call site, so
              the subroutine reads its return address from a cell the main
              program skipped.  (Designed by hand, Calcbolge example.)
rot_sequence  a rot whose data register equals its own cell reads its own
              character v; when v = 3t it leaves a = t, so printing byte t
              forces the rot to cell c = (39 - 3t) mod 94.  (INV1 of
              MALBOLGE_STAIRCASE_TOY_V0.)
"""
from __future__ import annotations

from dataclasses import dataclass, field

JMP, OUT, IN, ROT, MOVD, OPR, NOP, HALT = 4, 5, 23, 39, 40, 62, 68, 81
VALID = (JMP, OUT, IN, ROT, MOVD, OPR, NOP, HALT)
TERMINATED = "StopReason.TERMINATED"


def valid_char(opcode: int, position: int) -> str:
    """The one printable character decoding to `opcode` at `position`.

    Same formula as zig/frontier_scan.zig: chr(33 + (opcode - 33 - pos) % 94).
    """
    return chr(33 + (opcode - 33 - position) % 94)


def lower(plan: list[int]) -> str:
    return "".join(valid_char(op, i) for i, op in enumerate(plan))


@dataclass(frozen=True)
class ShapeInstance:
    family: str
    params: dict
    plan: tuple[int, ...]
    program: str
    input_data: str
    expect: dict = field(default_factory=dict)   # output, steps, final_pc, stop_reason

    @property
    def plan_text(self) -> str:
        """MBIR-Classic compatible plan (space-separated opcode numbers)."""
        return " ".join(str(op) for op in self.plan)


# --- call_return ----------------------------------------------------------------

def _call_return_layouts():
    for k in range(2, 94):
        s = ord(valid_char(JMP, k)) + 1          # call lands on its own char, resumes after
        if s <= k + 4:
            continue
        data = k + 3                             # d when the subroutine reaches its jmp
        if not (k < data < s - 1):
            continue
        for op in VALID:                         # the data cell holds one of 8 legal chars
            ret = ord(valid_char(op, data)) + 1  # the return resumes after that value
            used = set(range(0, k + 1)) | {s - 1, s, s + 1, s + 2, data}
            if ret in used or ret + 1 in used or ret - 1 in (s, s + 1, s + 2):
                continue
            yield k, s, data, op, ret


def call_return(input_data: str = "AB") -> list[ShapeInstance]:
    if len(input_data) != 2:
        raise ValueError("call_return reads exactly two input bytes")
    out: list[ShapeInstance] = []
    for k, s, data, data_op, ret in _call_return_layouts():
        n = max(s + 2, ret + 1) + 1
        plan = [NOP] * n
        plan[0], plan[1], plan[k] = IN, OUT, JMP
        plan[data] = data_op
        plan[ret], plan[ret + 1] = OUT, HALT
        plan[s], plan[s + 1], plan[s + 2] = IN, OUT, JMP
        out.append(ShapeInstance(
            family="call_return",
            params={"call": k, "subroutine": s, "data_cell": data, "return_to": ret},
            plan=tuple(plan), program=lower(plan), input_data=input_data,
            expect={"output": input_data[0] + input_data[1] + input_data[1],
                    "steps": k + 6, "final_pc": ret + 1, "stop_reason": TERMINATED},
        ))
    return out


# --- rot_sequence ---------------------------------------------------------------

def rot_position(byte: int, at_least: int) -> int:
    """Smallest cell >= at_least where a self-reading rot leaves a = byte."""
    if not 33 <= 3 * byte <= 126:
        raise ValueError(f"byte {byte} not printable by a self-reading rot (needs 3*byte in 33..126)")
    base = (39 - 3 * byte) % 94
    return at_least + (base - at_least) % 94


def rot_sequence(data: bytes) -> ShapeInstance:
    if not data:
        raise ValueError("rot_sequence needs at least one byte")
    positions, pos = [], 0
    for byte in data:
        c = rot_position(byte, pos)
        positions.append(c)
        pos = c + 2
    plan = [NOP] * (pos + 1)
    for c in positions:
        plan[c], plan[c + 1] = ROT, OUT
    plan[pos] = HALT
    return ShapeInstance(
        family="rot_sequence",
        params={"bytes": list(data), "rot_positions": positions},
        plan=tuple(plan), program=lower(plan), input_data="",
        expect={"output": data.decode("latin-1"), "steps": pos + 1,
                "final_pc": pos, "stop_reason": TERMINATED},
    )


def rot_printer_family() -> list[ShapeInstance]:
    singles = [rot_sequence(bytes([b])) for b in range(11, 43)]
    ascending = rot_sequence(bytes(range(33, 43)))            # the published staircase
    descending = rot_sequence(bytes(range(42, 32, -1)))
    return singles + [ascending, descending]


# --- controls -------------------------------------------------------------------

def controls(instance: ShapeInstance) -> list[ShapeInstance]:
    """Minimal mutants that break the shape while staying loadable.

    Each keeps the ORIGINAL expectation, so a correct checker must reject it.
    call_return: the data cell holds each of the other seven legal values.
    rot_sequence: the first rot moves one cell later.
    """
    plan = list(instance.plan)
    mutants = []
    if instance.family == "call_return":
        data = instance.params["data_cell"]
        for op in VALID:
            if op == plan[data]:
                continue
            m = plan.copy()
            m[data] = op
            mutants.append(ShapeInstance(instance.family, {**instance.params, "mutant": f"data_cell={op}"},
                                         tuple(m), lower(m), instance.input_data, instance.expect))
    elif instance.family == "rot_sequence":
        c = instance.params["rot_positions"][0]
        tail = plan[c + 2]                      # what the shifted pair would overwrite
        if tail in (NOP, HALT):
            m = plan.copy()
            m[c], m[c + 1], m[c + 2] = NOP, ROT, OUT
            if tail == HALT:
                m.append(HALT)                  # keep the mutant terminating
            mutants.append(ShapeInstance(instance.family, {**instance.params, "mutant": f"rot_shift={c}->{c + 1}"},
                                         tuple(m), lower(m), instance.input_data, instance.expect))
    return mutants
