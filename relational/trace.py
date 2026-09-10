"""Canonical JSON transport for Classic instruction traces."""

from __future__ import annotations

import json
import hashlib
from typing import Iterable, List

from .classic import ClassicDebugger, TraceEvent

TRACE_SCHEMA = "autobolge-trace/v1"


def serialize_trace(events: Iterable[TraceEvent]) -> str:
    payload = {
        "schema": TRACE_SCHEMA,
        "events": [event.__dict__ for event in events],
    }
    return json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def deserialize_trace(text: str) -> List[TraceEvent]:
    payload = json.loads(text)
    if payload.get("schema") != TRACE_SCHEMA:
        raise ValueError("unsupported trace schema")
    return [TraceEvent(**event) for event in payload["events"]]


def verify_trace(events: Iterable[TraceEvent]) -> None:
    """Validate ordering and state continuity without executing the program."""
    items = list(events)
    for index, event in enumerate(items):
        if event.step != index + 1:
            raise ValueError("trace step sequence is not contiguous")
        if index and (
            event.pre_c != items[index - 1].post_c
            or event.pre_a != items[index - 1].post_a
            or event.pre_d != items[index - 1].post_d
        ):
            raise ValueError("trace register state is discontinuous")
        if event.reason != "StopReason.RUNNING" and index != len(items) - 1:
            raise ValueError("terminal reason appears before the final event")


def replay_trace(program: str, input_data: str, expected: Iterable[TraceEvent], max_steps: int = 20000) -> None:
    """Execute Classic and require byte-for-byte equality with an expected trace."""
    expected_items = list(expected)
    verify_trace(expected_items)
    actual: List[TraceEvent] = []
    debugger = ClassicDebugger(program, input_data, max_steps, trace=actual)
    while len(actual) < len(expected_items) and not debugger.is_stopped and debugger.step_count < max_steps:
        debugger.step()
    if actual != expected_items:
        raise ValueError("replayed trace differs from expected trace")


def checkpoint_digests(events: Iterable[TraceEvent], interval: int) -> List[str]:
    """Hash canonical trace prefixes at deterministic event boundaries."""
    if interval <= 0:
        raise ValueError("checkpoint interval must be positive")
    items = list(events)
    return [
        hashlib.sha256(serialize_trace(items[:end]).encode("ascii")).hexdigest()
        for end in range(interval, len(items) + 1, interval)
    ]
