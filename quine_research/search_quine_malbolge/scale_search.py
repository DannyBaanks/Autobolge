from pathlib import Path
"""Structural search: espacio COMPLETO plen=3, ilen=0, modo program-only."""
import sys, os, json, time
os.chdir(Path(__file__).resolve().parents[2])
sys.path.insert(0, 'quine_research/search_quine_malbolge')
from search_quine_malbolge import (Candidate, execute_stage, halt_stage,
                                     output_stage, prefix_stage, exact_stage,
                                     generate_candidates, encode_candidate)
from zig_batch import prepare_batch_from_dicts, run_batch
from collections import Counter

def run_full_plen3():
    print("=== FULL plen=3, ilen=0, mode=program ===")
    t0 = time.time()
    candidates = generate_candidates(mode='program', max_program_length=3,
                                      max_input_length=0, limit=None)
    gen_time = time.time() - t0
    print(f"Generated: {len(candidates):,} in {gen_time:.2f}s")

    # Ejecutar en chunks de 50K via Zig batch directo
    chunk = 50000
    all_results = []
    t1 = time.time()
    for i in range(0, len(candidates), chunk):
        sub = candidates[i:i+chunk]
        batch_dicts = [{'program': c.program, 'input_data': c.input_data,
                        'max_steps': 100_000} for c in sub]
        batch = prepare_batch_from_dicts(batch_dicts, max_steps=100_000)
        results = run_batch(batch, bolge_path='zig/bolge.exe', work_dir='.')
        for j, rr in enumerate(results):
            if 'error' in rr:
                all_results.append({'output': '', 'steps': 0, 'terminated': False, 'error': rr['error']})
            else:
                all_results.append(rr)
    exec_time = time.time() - t1
    print(f"Executed {len(all_results):,} in {exec_time:.2f}s ({len(all_results)/max(0.001,exec_time):.0f} cand/s)")

    # Reconstruir ExecutionResults
    from search_quine_malbolge import ExecutionResult
    s1_all = []
    for cand, rr in zip(candidates, all_results):
        output = rr.get('output', '')
        steps = rr.get('steps', 0)
        terminated = rr.get('terminated', False)
        status = 'executed' if terminated else ('budget_exhausted' if len(output) > 0 else 'non_productive')
        s1_all.append(ExecutionResult(cand, output, terminated, steps, status, tier=0))

    s1 = [r for r in s1_all if r.survived()]
    s2 = halt_stage(s1)
    s3 = output_stage(s2)

    out_dist = Counter(len(r.output) for r in s3)
    print(f"S1={len(s1):,} S2={len(s2):,} S3={len(s3):,}")
    print(f"Output len dist: {dict(sorted(out_dist.items()))} max={max(out_dist) if out_dist else 0}")

    s4 = prefix_stage(s3)
    pref_dist = Counter(r['prefix_length'] for r in s4)
    print(f"S4 prefix dist: {dict(sorted(pref_dist.items()))} best={max(pref_dist) if pref_dist else 0}")

    print("\nTop 10 S4 (by prefix_len):")
    for r in s4[:10]:
        c = r['candidate']
        print(f"  prefix={r['prefix_length']} ratio={r['prefix_ratio']:.2f} "
              f"steps={r['result'].steps} prog={c.program!r} out={r['result'].output!r} "
              f"src={c.source!r}")

    s5 = exact_stage(s4)
    print(f"\nS5 EXACT quines: {len(s5)}")
    for q in s5:
        c = q['candidate']
        print(f"  QUINE: prog={c.program!r} input={c.input_data!r} steps={q['result'].steps}")

    stats = {
        'mode': 'full_plen3_program', 'plen': 3, 'ilen': 0,
        'S0': len(candidates), 'S1': len(s1), 'S2': len(s2), 'S3': len(s3),
        'output_distribution': dict(sorted(out_dist.items())),
        'max_output_len': max(out_dist) if out_dist else 0,
        'S4': len(s4),
        'prefix_distribution': dict(sorted(pref_dist.items())),
        'best_prefix': max(pref_dist) if pref_dist else 0,
        'S5': len(s5),
        'gen_time_s': round(gen_time, 2),
        'exec_time_s': round(exec_time, 2),
        'throughput': round(len(candidates)/max(0.001, time.time()-t0), 1),
        'top10': [{
            'program': r['candidate'].program,
            'input': r['candidate'].input_data,
            'output': r['result'].output,
            'prefix': r['prefix_length'],
            'ratio': r['prefix_ratio'],
            'steps': r['result'].steps,
        } for r in s4[:10]],
    }
    out_path = 'quine_research/search_quine_malbolge/results/full_plen3_search.json'
    with open(out_path, 'w') as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)
    print(f"\nSaved {out_path}")

if __name__ == '__main__':
    run_full_plen3()