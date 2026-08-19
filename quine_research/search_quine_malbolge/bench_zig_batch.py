from pathlib import Path
"""Benchmark: Zig batch vs Python inline throughput."""
import sys, os, time
os.chdir(Path(__file__).resolve().parents[2])
sys.path.insert(0, 'quine_research/search_quine_malbolge')
from search_quine_malbolge import Candidate, execute_stage, generate_candidates, run_malbolge_inline, prepare_batch, run_zig_batch

N = 100  # candidates per batch

# Generate diverse candidates
candidates = generate_candidates(mode="both", max_program_length=2, max_input_length=1, limit=N)
print(f"Benchmarking {N} candidates...")

# Python inline
t0 = time.time()
py_results = []
for c in candidates:
    out, hlt, st = run_malbolge_inline(c.program, c.input_data, max_steps=100_000)
    py_results.append((out, hlt, st))
py_time = time.time() - t0
py_throughput = N / py_time
print(f"Python inline: {py_time:.2f}s = {py_throughput:.1f} cand/s")

# Zig batch
batch = prepare_batch(candidates, max_steps=100_000)
t0 = time.time()
zig_results = run_zig_batch(batch, bolge_path='zig/bolge.exe', work_dir='.')
zig_time = time.time() - t0
zig_throughput = N / zig_time
print(f"Zig batch:     {zig_time:.2f}s = {zig_throughput:.1f} cand/s")
print(f"Speedup:       {zig_throughput / py_throughput:.1f}x")

# Parity check
mismatches = 0
for i, (c, (py_out, py_hlt, py_st), zr) in enumerate(zip(candidates, py_results, zig_results)):
    z_out = zr.get('output', '')
    z_hlt = zr.get('terminated', False)
    z_st = zr.get('steps', 0)
    if py_hlt != z_hlt:
        mismatches += 1
        if mismatches <= 3:
            print(f"  HALT mismatch [{i}] prog={c.program!r} inp={c.input_data!r}: py={py_hlt} zig={z_hlt}")
    if py_out != z_out:
        mismatches += 1
        if mismatches <= 3:
            print(f"  OUT mismatch [{i}] prog={c.program!r} inp={c.input_data!r}: py={py_out!r} zig={z_out!r}")

print(f"Mismatches: {mismatches}")