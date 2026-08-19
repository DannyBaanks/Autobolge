"""Analiza el program bank ABC para extraer patrones estructurales."""
import sys, json
from collections import Counter

with open('quine_research/search_quine_malbolge/results/program_bank_ABC_zig.json', 'r') as f:
    bank = json.load(f)

candidates = bank['candidates']
print(f'Total candidates: {len(candidates)}')

# Length distributions
prog_lens = [len(c['program']) for c in candidates]
opcode_lens = [len(c['opcodes']) for c in candidates]
print(f'Program len: min={min(prog_lens)} max={max(prog_lens)} avg={sum(prog_lens)/len(prog_lens):.1f}')
print(f'Opcode len: min={min(opcode_lens)} max={max(opcode_lens)} avg={sum(opcode_lens)/len(opcode_lens):.1f}')

# Steps distribution
steps = [c['zig_steps'] for c in candidates if c['zig_terminated']]
print(f'Steps: min={min(steps)} max={max(steps)} avg={sum(steps)/len(steps):.1f}')

# Shortest programs
shortest = sorted(candidates, key=lambda c: len(c['program']))[:10]
print('\nShortest programs (top 3):')
for c in shortest[:3]:
    tgt = c['target']
    prog = c['program'][:60]
    plen = len(c['program'])
    olen = len(c['opcodes'])
    st = c['zig_steps']
    print(f'  target={tgt!r} prog={prog!r} prog_len={plen} opcode_len={olen} steps={st}')

# Interesting targets
interesting_targets = ['AA', 'AB', 'HI', 'NO', 'QU', 'ZZ']
print('\nInteresting targets:')
for tgt in interesting_targets:
    c = next((x for x in candidates if x['target'] == tgt), None)
    if c:
        print(f'  {tgt!r}: prog={c["program"][:80]!r} steps={c["zig_steps"]}')

# Opcodes diversity (count unique opcodes used per program, rough via program_source)
# In printable source, character codes 33-126 map to opcodes via (char + pc) % 94
# We can't derive exact opcodes without knowing pc, but we can look for opcode indicators
# The translator uses opcode_choices="op*" where op = operations (not nops)
# op* means any opcode including nops

# Save analysis
analysis = {
    'total': len(candidates),
    'prog_len': {'min': min(prog_lens), 'max': max(prog_lens), 'avg': round(sum(prog_lens)/len(prog_lens), 1)},
    'steps': {'min': min(steps), 'max': max(steps), 'avg': round(sum(steps)/len(steps), 1)},
    'shortest': [
        {'target': c['target'], 'prog_len': len(c['program']), 'steps': c['zig_steps']}
        for c in shortest[:10]
    ],
}
with open('quine_research/search_quine_malbolge/results/analysis_ABC_bank.json', 'w') as f:
    json.dump(analysis, f, indent=2)
print('\nSaved analysis_ABC_bank.json')