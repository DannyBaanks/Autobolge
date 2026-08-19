from pathlib import Path
"""Pipeline estructural: busca output_len >= 2 en familias dirigidas."""
import sys, os, json, time
os.chdir(Path(__file__).resolve().parents[2])
sys.path.insert(0, 'quine_research/search_quine_malbolge')
from search_quine_malbolge import (Candidate, ExecutionResult, execute_stage,
                                     halt_stage, output_stage, prefix_stage, exact_stage,
                                     generate_candidates, TIERS, encode_candidate)
from zig_batch import prepare_batch, run_batch
from structural_generator import generate_structural
from collections import Counter

def pipeline_structural(mode='multi_out', max_len=4, max_input_len=1,
                        limit=1000, max_steps=100000):
    print(f"\n=== Structural family: {mode} | plen={max_len} ilen={max_input_len} limit={limit} ===")
    
    t0 = time.time()
    programs = generate_structural(mode=mode, max_len=max_len, limit=limit)
    candidates = [Candidate(p, "") for p in programs]
    
    # Añadir variantes de input si ilen > 0 (limitadas para no explotar espacio)
    if max_input_len > 0 and limit > 0:
        input_variants = [chr(c) for c in range(33, 43)]  # solo 10 chars para prueba
        extra = []
        for c in candidates[:min(100, len(candidates))]:
            for inp_char in input_variants:
                extra.append(Candidate(c.program, inp_char))
        candidates.extend(extra[:limit - len(candidates)])
    
    gen_time = time.time() - t0
    print(f"Generated: {len(candidates):,} in {gen_time:.2f}s")
    stats = {'mode': mode, 'plen': max_len, 'ilen': max_input_len, 'limit': limit}
    stats['S0'] = len(candidates)
    stats['gen_time_s'] = round(gen_time, 3)

    t1 = time.time()
    s1_all = execute_stage(candidates, tiers=TIERS)
    s1 = [r for r in s1_all if r.survived()]
    stats['S1'] = len(s1)
    stats['S1_reduction'] = 1.0 - len(s1)/max(1, stats['S0'])
    stats['S1_time_s'] = round(time.time()-t1, 3)
    stats['S1_status'] = dict(Counter(r.status for r in s1_all))

    t2 = time.time()
    s2 = halt_stage(s1)
    stats['S2'] = len(s2)
    stats['S2_reduction'] = 1.0 - len(s2)/max(1, len(s1))
    stats['S2_time_s'] = round(time.time()-t2, 3)

    t3 = time.time()
    s3 = output_stage(s2)
    stats['S3'] = len(s3)
    stats['S3_reduction'] = 1.0 - len(s3)/max(1, len(s2))
    stats['S3_time_s'] = round(time.time()-t3, 3)

    # Output distribution
    out_lens = [len(r.output) for r in s3]
    out_dist = Counter(out_lens)
    stats['output_distribution'] = dict(sorted(out_dist.items()))
    stats['max_output_len'] = max(out_lens) if out_lens else 0
    stats['avg_output_len'] = round(sum(out_lens)/len(out_lens), 2) if out_lens else 0
    
    # PREFIX analysis
    t4 = time.time()
    s4 = prefix_stage(s3)
    stats['S4'] = len(s4)
    prefix_dist = Counter(r['prefix_length'] for r in s4)
    stats['prefix_distribution'] = dict(sorted(prefix_dist.items()))
    stats['S4_time_s'] = round(time.time()-t4, 3)

    # EXACT
    t5 = time.time()
    s5 = exact_stage(s4)
    stats['S5'] = len(s5)
    stats['S5_time_s'] = round(time.time()-t5, 3)

    # Best candidates (top by prefix_len)
    best = []
    for r in s4[:20]:
        best.append({
            'program': r['candidate'].program,
            'input': r['candidate'].input_data,
            'source': r['candidate'].source,
            'output': r['result'].output,
            'steps': r['result'].steps,
            'output_len': r['output_length'],
            'prefix_len': r['prefix_length'],
            'prefix_ratio': round(r['prefix_ratio'], 4),
        })
    stats['best_candidates'] = best
    stats['total_time_s'] = round(time.time()-t0, 3)
    stats['candidates_per_sec'] = round(stats['S0'] / max(0.001, stats['total_time_s']), 1)

    # Report
    print(f"S0={stats['S0']} S1={stats['S1']} S2={stats['S2']} S3={stats['S3']} S4={stats['S4']} S5={stats['S5']}")
    print(f"Output dist: {dict(out_dist)}")
    print(f"Max output_len: {stats['max_output_len']}")
    print(f"Prefix dist: {dict(prefix_dist)}")
    if s5:
        print(f"EXACT QUINES FOUND: {len(s5)}")
        for q in s5:
            print(f"  {q['candidate'].program!r} + {q['candidate'].input_data!r}")
    print(f"Total: {stats['total_time_s']}s | {stats['candidates_per_sec']} cand/s")
    
    return stats

if __name__ == '__main__':
    modes = ['multi_out', 'modify_out', 'loop_seed']
    all_stats = {}
    for mode in modes:
        all_stats[mode] = pipeline_structural(mode=mode, max_len=4, max_input_len=1, limit=1000)
    
    out_path = 'quine_research/search_quine_malbolge/results/structural_output_search.json'
    with open(out_path, 'w') as f:
        json.dump(all_stats, f, indent=2, ensure_ascii=False)
    print(f"\nSaved evidence: {out_path}")