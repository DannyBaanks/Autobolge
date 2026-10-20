"""State-continuous fixed-text Malbolge generation.

Synthesizes autonomous programs by segment composition using Autobolge 2.0
Conveyor Synthesis.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from relational.synthesizer import synthesize_text


CLASSIC_MAX_PROGRAM_LENGTH = 59049


class MalbolgeRuntimeError(RuntimeError):
    pass


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
    """Generate a single Classic program by continuing its live machine state."""
    if not text:
        raise ValueError("text must not be empty")
    if segment_chars <= 0:
        raise ValueError("segment_chars must be > 0")
    if max_program_length <= 100:
        raise ValueError("max_program_length must exceed the 100-op bootstrap")

    res = synthesize_text(text, verify=True)
    if len(res.program_bytes) > max_program_length:
        raise MalbolgeRuntimeError(
            f"Classic program would exceed {max_program_length} opcodes ({len(res.program_bytes)} bytes)"
        )

    segments: List[StreamingSegment] = []
    for index, start in enumerate(range(0, len(text), segment_chars)):
        segment = text[start : start + segment_chars]
        segments.append(
            StreamingSegment(
                index=index,
                text=segment,
                opcodes="conveyor",
                evaluations=len(segment),
            )
        )

    return StreamingResult(
        text=text,
        opcodes=res.program,
        output=res.output,
        segments=segments,
    )
