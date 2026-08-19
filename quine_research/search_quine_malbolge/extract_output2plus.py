from pathlib import Path
"""Extrae los candidatos con output_len >= 2 del espacio plen=3 completo."""
import sys, os, json, time
os.chdir(Path(__file__).resolve().parents[2])
sys.path.insert(0, 'quine_research/search_quine_malbolge')
from search_quine_malbolge import (Candidate, ExecutionResult,
                                     output_stage, halt_stage, prefix_stage,
                                     generate_candidates)
from zig_batch import prepare_batch_from_dicts, run_batch

candidates = generate_candidates(mode='program', max_program_length=3,
                                  max_input_length=0, limit=None)
print(f"Total: {len(candidates):,}")

chunk = 50000
all_results = []
t0 = time.time()
for i in range(0, len(candidates), chunk):
    sub = candidates[i:i+chunk]
    batch_dicts = [{'program': c.program, 'input_data': c.input_data,
                    'max_steps': 100_000} for c in sub]
    batch = prepare_batch_from_dicts(batch_dicts, max_steps=100_000)
    results = run_batch(batch, bolge_path='zig/bolge.exe', work_dir='.')
    for rr in results:
        all_results.append(rr)
print(f"Executed {len(all_results):,} in {time.time()-t0:.2f}s")

s1_all = []
for cand, rr in zip(candidates, all_results):
    output = rr.get('output', '')
    steps = rr.get('steps', 0)
    terminated = rr.get('terminated', False)
    status = 'executed' if terminated else ('budget_exhausted' if len(output) > 0 else 'non_productive')
    s1_all.append(ExecutionResult(cand, output, terminated, steps, status, tier=0))

s3 = output_stage(halt_stage(s1_all))
interesting = [r for r in s3 if len(r.output) >= 2]
print(f"S3={len(s3)} | output_len>=2: {len(interesting)}")

interesting.sort(key=lambda r: (-len(r.output), r.steps))

print(f"\n--- Candidates with output_len >= 2 ({len(interesting)}) ---")
for r in interesting[:50]:
    print(f"  out_len={len(r.output)} steps={r.steps} prog={r.candidate.program!r} "
          f"out={r.output!r}")

data = [{
    'program': r.candidate.program,
    'output': r.output,
    'output_len': len(r.output),
    'steps': r.steps,
    'terminated': r.halted,
    'source': r.candidate.source,
} for r in interesting]

out_path = 'quine_research/search_quine_malbolge/results/plen3_output2plus.json'
with open(out_path, 'w') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
print(f"\nSaved {len(data)} candidates to {out_path}")