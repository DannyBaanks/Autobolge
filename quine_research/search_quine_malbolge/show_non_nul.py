"""Muestra candidatos plen=3 con output no-NUL."""
import json

data = json.load(open('quine_research/search_quine_malbolge/results/plen3_output2plus.json'))
print('Total:', len(data))
non_nul = [d for d in data if any(b != chr(0) for b in d['output'])]
print('Non-NUL outputs:', len(non_nul))
for d in non_nul[:40]:
    print(f'  prog={d["program"]!r} out={d["output"]!r} steps={d["steps"]}')
print(f'... ({len(non_nul)} total)')