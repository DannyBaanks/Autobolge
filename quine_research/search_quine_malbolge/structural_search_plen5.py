from pathlib import Path
"""Structural search plen=5: busca frontier output_len >= 2."""
import sys, os, json, time
os.chdir(Path(__file__).resolve().parents[2])
sys.path.insert(0, 'quine_research/search_quine_malbolge')
from search_quine_malbolge import (Candidate, ExecutionResult, execute_stage,
                                     halt_stage, output_stage, prefix_stage, exact_stage,
                                     generate_candidates as gen_std, TIERS, encode_candidate)
from zig_batch import prepare_batch, run_batch
from structural_generator import generate_structural
from collections import Counter

def run_family(mode, max_len=5, max_input_len=1, limit=500, max_steps=100000):
    print(f"\n=== {mode} | plen={max_len} ilen={max_input_len} limit={limit} ===")
    t0 = time.time()
    programs = generate_structural(mode=mode, max_len=max_len, limit=limit)
    candidates = [Candidate(p, "") for p in programs]
    # Añadir pocas variantes de input
    if max_input_len > 0:
        for c in candidates[:50]:
            for ch in ['A', 'B', 'C']:
                candidates.append(Candidate(c.program, ch))
                if len(candidates) >= limit:
                    break
            if len(candidates) >= limit:
                break
    gen_time = time.time() - t0
    print(f"Generated: {len(candidates):,} in {gen_time:.2f}s")
    stats = {'mode': mode, 'plen': max_len, 'ilen': max_input_len, 'limit': limit}

    t1 = time.time()
    s1_all = execute_stage(candidates, tiers=TIERS)
    s1 = [r for r in s1_all if r.survived()]
    stats['S1'] = len(s1)
    stats['S1_status'] = dict(Counter(r.status for r in s1_all))

    s2 = halt_stage(s1)
    stats['S2'] = len(s2)

    s3 = output_stage(s2)
    stats['S3'] = len(s3)
    out_lens = [len(r.output) for r in s3]
    out_dist = Counter(out_lens)
    stats['output_distribution'] = dict(sorted(out_dist.items()))
    stats['max_output_len'] = max(out_lens) if out_lens else 0

    s4 = prefix_stage(s3)
    stats['S4'] = len(s4)
    prefix_dist = Counter(r['prefix_length'] for r in s4)
    stats['prefix_distribution'] = dict(sorted(prefix_dist.items()))

    s5 = exact_stage(s4)
    stats['S5'] = len(s5)

    total = time.time() - t0
    stats['total_time_s'] = round(total, 3)
    stats['candidates_per_sec'] = round(len(candidates) / max(0.001, total), 1)

    print(f"S0={len(candidates)} S1={stats['S1']} S2={stats['S2']} S3={stats['S3']} S4={stats['S4']} S5={stats['S5']}")
    print(f"Output dist: {dict(out_dist)} max={stats['max_output_len']}")
    print(f"Prefix dist: {dict(prefix_dist)}")
    if s5:
        for q in s5:
            print(f"  QUINE: {q['candidate'].program!r} + {q['candidate'].input_data!r}")
    print(f"Time: {total:.2f}s | {stats['candidates_per_sec']} cand/s")
    return stats

if __name__ == '__main__':
    modes = ['multi_out', 'modify_out', 'loop_seed']
    all_stats = {}
    for mode in modes:
        all_stats[mode] = run_family(mode, max_len=5, max_input_len=1, limit=500)
    
    out_path = 'quine_research/search_quine_malbolge/results/structural_plen5_search.json'
    with open(out_path, 'w') as f:
        json.dump(all_stats, f, indent=2, ensure_ascii=False)
    print(f"\nSaved: {out_path}")