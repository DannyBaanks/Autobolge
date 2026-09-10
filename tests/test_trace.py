import json
import subprocess
from pathlib import Path

from relational.classic import ClassicDebugger, TraceEvent
from relational.trace import checkpoint_digests, deserialize_trace, replay_trace, serialize_trace, verify_trace


ROOT = Path(__file__).resolve().parents[1]
TRACE_PROBE = ROOT / "zig" / "trace_probe.exe"


def test_classic_trace_is_deterministic_and_replayable():
    first = []
    second = []
    first_debugger = ClassicDebugger("ub", "A", trace=first)
    second_debugger = ClassicDebugger("ub", "A", trace=second)

    first_debugger.step()
    second_debugger.step()

    assert first == second
    assert len(first) == 1
    assert isinstance(first[0], TraceEvent)
    assert first[0].opcode == 23
    assert first[0].reason == "StopReason.RUNNING"

    decoded = deserialize_trace(serialize_trace(first))
    assert decoded == first
    verify_trace(decoded)
    replay_trace("ub", "A", decoded)
    assert checkpoint_digests(decoded, 1) == checkpoint_digests(first, 1)


def test_trace_records_terminal_reason():
    events = []
    debugger = ClassicDebugger("Q", trace=events)
    debugger.step()

    assert len(events) == 1
    assert events[0].opcode == 81
    assert events[0].reason == "StopReason.TERMINATED"


def test_zig_and_python_trace_parity():
    assert TRACE_PROBE.exists()
    for program, input_data, steps in (("ub", "A", 1), ("Q", "", 1)):
        expected = []
        debugger = ClassicDebugger(program, input_data, steps, trace=expected)
        while not debugger.is_stopped and debugger.step_count < steps:
            debugger.step()
        completed = subprocess.run(
            [str(TRACE_PROBE), program, input_data, str(steps)],
            cwd=ROOT / "zig",
            capture_output=True,
            text=True,
            check=True,
        )
        actual = json.loads(completed.stderr)
        assert [event.__dict__ for event in expected] == actual["events"]
        assert actual["outcome"]["steps"] == len(expected)
