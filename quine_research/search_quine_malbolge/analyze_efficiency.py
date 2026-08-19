"""Analiza eficiencia del program bank ABC para informar diseño de quine."""
import sys, json
from collections import defaultdict

with open('quine_research/search_quine_malbolge/results/program_bank_ABC_zig.json', 'r') as f:
    bank = json.load(f)

candidates = bank['candidates']

# Efficiency: program_len / output_len
# For 2-char targets, output_len=2, program_len varies
efficiency = [(c['program'], c['target'], len(c['program']), len(c['target']), c['zig_steps'])
              for c in candidates]

# Sort by program_len ascending
efficiency.sort(key=lambda x: x[2])

print('Top 10 shortest programs (2-char targets):')
for prog, tgt, plen, tlen, steps in efficiency[:10]:
    ratio = plen / max(1, tlen)
    print(f'  target={tgt!r} prog_len={plen} ratio={ratio:.1f} steps={steps}')
    print(f'    prog={prog[:70]!r}')

# Distribution of program lengths
plens = [x[2] for x in efficiency]
print(f'\nProgram len distribution:')
print(f'  min: {min(plens)}')
print(f'  max: {max(plens)}')
print(f'  avg: {sum(plens)/len(plens):.1f}')
print(f'  median: {sorted(plens)[len(plens)//2]}')

# Check if the common bootstrap is identifiable
# The prefix `bCBA@?>=<;:9876543210/.-,+*)(...` appears in all programs
bootstrap = candidates[0]['program'][:118]
print(f'\nCommon bootstrap (first 118 chars):')
print(f'  {bootstrap!r}')
print(f'  Bootstrap length: {len(bootstrap)}')

# Continuation length after bootstrap
continuation_lens = [len(c['program']) - len(bootstrap) for c in candidates]
print(f'\nContinuation len: min={min(continuation_lens)} max={max(continuation_lens)} avg={sum(continuation_lens)/len(continuation_lens):.1f}')

# Efficiency of just the continuation
print(f'\nFor a quine using this bootstrap:')
print(f'  Bootstrap overhead: {len(bootstrap)} chars (no output)')
print(f'  Continuation per output byte: ~{sum(continuation_lens)/len(continuation_lens)/2:.1f} chars')

# Save analysis
analysis = {
    'shortest_programs': [
        {'target': tgt, 'prog_len': plen, 'steps': st, 'ratio': round(plen/max(1,tlen),1)}
        for prog, tgt, plen, tlen, st in efficiency[:20]
    ],
    'bootstrap_prefix': bootstrap,
    'bootstrap_len': len(bootstrap),
    'avg_continuation_len': round(sum(continuation_lens)/len(continuation_lens), 1),
}
with open('quine_research/search_quine_malbolge/results/efficiency_ABC_bank.json', 'w') as f:
    json.dump(analysis, f, indent=2, ensure_ascii=False)
print('\nSaved efficiency_ABC_bank.json')