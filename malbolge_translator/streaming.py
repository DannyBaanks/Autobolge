"""State-continuous fixed-text Malbolge generation.

This composes continuations inside one Malbolge program. It is not a fresh-VM
resume protocol: snapshots exist only while synthesizing and validating the
single final program.
"""
from __future__ import annotations

from dataclasses import dataclass

from malbolge import MalbolgeRuntimeError, ProgramGenerator

from .backend import get_backend


CLASSIC_MAX_PROGRAM_LENGTH = 59049


@dataclass
class StreamingSegment:
    index: int
    text: str
    opcodes: str
    evaluations: int


@dataclass
class StreamingResult:
    text: str
    opcodes: str
    output: str
    segments: list[StreamingSegment]


def translate_continuous(
    text: str,
    *,
    segment_chars: int = 64,
    max_program_length: int = CLASSIC_MAX_PROGRAM_LENGTH,
) -> StreamingResult:
    """Generate a single Classic program by continuing its live machine state.

    The routine keeps only the current machine snapshot and one segment's
    search cache. Each continuation is verified from that snapshot, then all
    continuations are executed together from the normal bootstrap.
    """
    if not text:
        raise ValueError("text must not be empty")
    if segment_chars <= 0:
        raise ValueError("segment_chars must be > 0")
    if max_program_length <= 100:
        raise ValueError("max_program_length must exceed the 100-op bootstrap")

    generator = ProgramGenerator()
    interpreter = generator._interpreter
    backend = get_backend(generator)
    bootstrap = "i" + "o" * 99
    initial = interpreter.execute(bootstrap, capture_machine=True)
    if initial.machine is None:
        raise MalbolgeRuntimeError("bootstrap did not produce a machine snapshot")

    machine = initial.machine
    continuations: list[str] = []
    segments: list[StreamingSegment] = []
    for index, start in enumerate(range(0, len(text), segment_chars)):
        segment = text[start : start + segment_chars]
        is_final = start + segment_chars >= len(text)
        continuation, machine, stats = backend.search_continuation(
            machine,
            segment,
            add_halt=is_final,
        )
        if len(bootstrap) + sum(map(len, continuations)) + len(continuation) > max_program_length:
            raise MalbolgeRuntimeError(
                f"Classic program would exceed {max_program_length} opcodes after segment {index}"
            )
        continuations.append(continuation)
        segments.append(
            StreamingSegment(
                index=index,
                text=segment,
                opcodes=continuation,
                evaluations=int(stats["evaluations"]),
            )
        )

    opcodes = bootstrap + "".join(continuations)
    final = interpreter.execute(opcodes, capture_machine=True)
    if final.output != text or not final.halted:
        raise MalbolgeRuntimeError("composed program did not reproduce the requested text")
    return StreamingResult(text=text, opcodes=opcodes, output=final.output, segments=segments)
