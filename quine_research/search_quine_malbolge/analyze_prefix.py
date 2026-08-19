from pathlib import Path
"""Analiza la señal PREFIX del pipeline Malbolge."""
import sys, os, json
os.chdir(Path(__file__).resolve().parents[2])
sys.path.insert(0, 'quine_research/search_quine_malbolge')
from search_quine_malbolge import (Candidate, ExecutionResult, execute_stage,
                                     halt_stage, output_stage, prefix_stage, exact_stage,
                                     generate_candidates, TIERS)
from zig_batch import prepare_batch, run_batch
from collections import Counter

# Re-ejecutar plen=3 ilen=1 con 839,610 candidatos real
print("Generating candidates...")
candidates = generate_candidates(mode='both', max_program_length=3, max_input_length=1)
print(f"Total: {len(candidates):,}")

print("Running EXECUTE/HALT/OUTPUT...")
s1_all = execute_stage(candidates, tiers=TIERS)
s1 = [r for r in s1_all if r.survived()]
s2 = halt_stage(s1)
s3 = output_stage(s2)

print(f"S3 OUTPUT survivors: {len(s3)}")

# PREFIX analysis
s4 = prefix_stage(s3)
print(f"S4 PREFIX survivors: {len(s4)}")

# Distribution of prefix lengths
prefix_dist = Counter(r['prefix_length'] for r in s4)
print(f"\nPrefix length distribution:")
for k in sorted(prefix_dist.keys()):
    v = prefix_dist[k]
    print(f"  prefix_len={k}: {v} ({v/len(s4)*100:.1f}%)")

# Stats by prefix length
print(f"\n--- Detailed stats by prefix_len ---")
for plen in sorted(set(r['prefix_length'] for r in s4)):
    subset = [r for r in s4 if r['prefix_length'] == plen]
    steps_list = [r['result'].steps for r in subset]
    out_lens = [r['output_length'] for r in subset]
    src_lens = [r['source_length'] for r in subset]
    print(f"\nprefix_len={plen} (n={len(subset)}):")
    print(f"  avg_steps: {sum(steps_list)/len(steps_list):.1f}")
    print(f"  min_steps: {min(steps_list)} max_steps: {max(steps_list)}")
    print(f"  avg_output_len: {sum(out_lens)/len(out_lens):.1f}")
    print(f"  source_len: {src_lens[0]} (constante)")
    # Show first 3 examples
    for r in subset[:3]:
        print(f"    prog={r['candidate'].program!r} inp={r['candidate'].input_data!r} "
              f"out={r['result'].output[:20]!r} src={r['candidate'].source[:20]!r}")

# Best prefix candidates
print(f"\n--- Top 10 by prefix_len ---")
for r in s4[:10]:
    print(f"  prefix={r['prefix_length']} ratio={r['prefix_ratio']:.3f} "
          f"prog={r['candidate'].program!r} out={r['result'].output[:20]!r}")

# Check if any exact match
s5 = exact_stage(s4)
print(f"\nS5 EXACT: {len(s5)}")

# Correlation: prefix_len vs steps
print(f"\n--- Correlation: prefix_len vs steps ---")
from statistics import mean
for plen in sorted(set(r['prefix_length'] for r in s4)):
    subset = [r for r in s4 if r['prefix_length'] == plen]
    avg_steps = mean(r['result'].steps for r in subset)
    avg_out = mean(r['output_length'] for r in subset)
    print(f"  prefix={plen}: avg_steps={avg_steps:.1f} avg_out_len={avg_out:.1f} n={len(subset)}")

# Save full analysis
analysis = {
    'prefix_dist': dict(prefix_dist),
    'total_s4': len(s4),
    'best_prefix': s4[0]['prefix_length'] if s4 else 0,
    'top10': [{'prefix': r['prefix_length'], 'ratio': r['prefix_ratio'],
               'program': r['candidate'].program, 'input': r['candidate'].input_data,
               'output': r['result'].output[:50], 'source': r['candidate'].source[:50],
               'steps': r['result'].steps} for r in s4[:10]],
}
out_path = 'quine_research/search_quine_malbolge/results/prefix_analysis_plen3.json'
with open(out_path, 'w') as f:
    json.dump(analysis, f, indent=2, ensure_ascii=False)
print(f"\nSaved: {out_path}")