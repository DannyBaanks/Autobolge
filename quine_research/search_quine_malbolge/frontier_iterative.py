from pathlib import Path
"""Extensión iterativa con pruning: solo extiende programas de calidad.
Quality frontier = output_len>=2 | non-NUL | prefix>=1, + muestra de NULs.
También explora exhaustivamente las familias semilla (r=a, >ba, 'ba, c=a, c&a, cb, cba).
"""
import sys, os, json, time, random
os.chdir(Path(__file__).resolve().parents[2])
sys.path.insert(0, 'quine_research/search_quine_malbolge')
from search_quine_malbolge import Candidate, ExecutionResult, generate_candidates, _common_prefix_len
from zig_batch import prepare_batch_from_dicts, run_batch
from collections import Counter

ALPHABET = [chr(c) for c in range(33, 127)]

def execute_dicts(batch_dicts, chunk=50000, max_steps=100_000):
    results = []
    for i in range(0, len(batch_dicts), chunk):
        sub = batch_dicts[i:i+chunk]
        batch = prepare_batch_from_dicts(sub, max_steps=max_steps)
        res = run_batch(batch, bolge_path='zig/bolge.exe', work_dir='.')
        for rr in res:
            if 'error' in rr:
                results.append({'output': '', 'steps': 0, 'terminated': False, 'error': rr['error']})
            else:
                results.append(rr)
    return results

def run_level(level, programs, nul_sample=5000):
    """Extiende cada programa con 94 chars, ejecuta, retorna (stats, new_frontier)."""
    t0 = time.time()
    batch_dicts = []
    extended = []
    for p in programs:
        for ch in ALPHABET:
            np = p + ch
            extended.append(np)
            batch_dicts.append({'program': np, 'input_data': '', 'max_steps': 100_000})

    print(f"[L{level}] Extending {len(programs):,} programs x94 = {len(batch_dicts):,} candidates")
    results = execute_dicts(batch_dicts)
    print(f"[L{level}] Executed in {time.time()-t0:.1f}s")

    s3 = []
    for np, rr in zip(extended, results):
        output = rr.get('output', '')
        steps = rr.get('steps', 0)
        terminated = rr.get('terminated', False)
        if terminated and len(output) > 0:
            s3.append({'program': np, 'output': output, 'steps': steps,
                       'output_len': len(output),
                       'non_nul': any(b != chr(0) for b in output)})

    out_dist = Counter(r['output_len'] for r in s3)
    max_out = max(out_dist) if out_dist else 0

    pref_dist = Counter()
    top_pref = []
    for r in s3:
        src = r['program'] + '\n\n'
        pl = _common_prefix_len(r['output'], src)
        pref_dist[pl] += 1
        if pl > 0:
            top_pref.append({**r, 'prefix': pl})
    top_pref.sort(key=lambda x: -x['prefix'])

    s5 = [r for r in s3 if r['output'] == r['program'] + '\n\n']

    best = sorted(s3, key=lambda r: (-r['output_len'], -r['non_nul'], r['steps']))
    top_best = best[:10]

    stats = {
        'level': level,
        'candidates': len(batch_dicts),
        'S3': len(s3),
        'output_distribution': dict(sorted(out_dist.items())),
        'max_output_len': max_out,
        'prefix_distribution': dict(sorted(pref_dist.items())),
        'max_prefix': max(pref_dist) if pref_dist else 0,
        'S5_quines': len(s5),
        'top_prefix_matches': top_pref[:10],
        'top_by_output_len': top_best,
        'elapsed_s': round(time.time()-t0, 1),
    }
    print(f"[L{level}] S3={len(s3):,} out_dist={dict(sorted(out_dist.items()))}")
    print(f"[L{level}] prefix_dist={dict(sorted(pref_dist.items()))} quines={len(s5)}")
    for tb in top_best[:5]:
        print(f"  best: out_len={tb['output_len']} non_nul={tb['non_nul']} prog={tb['program']!r} out={tb['output']!r}")
    for tp in top_pref[:5]:
        print(f"  prefix={tp['prefix']} prog={tp['program']!r} out={tp['output']!r}")
    for q in s5:
        print(f"  *** QUINE: prog={q['program']!r} out={q['output']!r}")

    # Pruning para siguiente nivel
    quality = [r for r in s3 if r['output_len'] >= 2 or r['non_nul'] or any(
        _common_prefix_len(r['output'], r['program'] + '\n\n') > 0 for _ in [0])]
    nul_ones = [r for r in s3 if r['output_len'] == 1 and not r['non_nul']]
    sample = random.Random(42).sample(nul_ones, min(nul_sample, len(nul_ones)))
    new_frontier = [r['program'] for r in quality] + [r['program'] for r in sample]
    stats['frontier_next'] = len(new_frontier)
    print(f"[L{level}] Next frontier: {len(new_frontier):,} ({len(quality):,} quality + {len(sample):,} nul sample)")

    with open(f'quine_research/search_quine_malbolge/results/frontier_L{level}.json', 'w') as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)
    return stats, new_frontier

def seed_families(level):
    """Extiende exhaustivamente las familias semilla hasta plen=level."""
    seeds = ['r=a', '>ba', "'ba", 'c=a', 'c&a', 'cb', 'cba']
    t0 = time.time()
    all_cands = []
    for seed in seeds:
        # Extender con (level - len(seed)) chars = exhaustivo
        remaining = level - len(seed)
        for comb in __import__('itertools').product(ALPHABET, repeat=remaining):
            all_cands.append({'program': seed + ''.join(comb), 'input_data': '', 'max_steps': 100_000})
    print(f"[SEEDS] {len(all_cands):,} candidates (plen<={level})")
    results = execute_dicts(all_cands)
    print(f"[SEEDS] Executed in {time.time()-t0:.1f}s")

    s3 = []
    for c, rr in zip(all_cands, results):
        output = rr.get('output', '')
        if rr.get('terminated', False) and len(output) > 0:
            s3.append({'program': c['program'], 'output': output,
                       'steps': rr.get('steps', 0), 'output_len': len(output),
                       'non_nul': any(b != chr(0) for b in output)})

    # Prefix matches
    matches = []
    for r in s3:
        src = r['program'] + '\n\n'
        pl = _common_prefix_len(r['output'], src)
        if pl > 0:
            matches.append({**r, 'prefix': pl})
    matches.sort(key=lambda x: -x['prefix'])
    print(f"[SEEDS] S3={len(s3):,} prefix_matches={len(matches)}")
    for m in matches[:20]:
        print(f"  prefix={m['prefix']} prog={m['program']!r} out={m['output']!r} steps={m['steps']}")

    quines = [r for r in s3 if r['output'] == r['program'] + '\n\n']
    print(f"[SEEDS] Quines: {len(quines)}")
    for q in quines:
        print(f"  *** QUINE: prog={q['program']!r} out={q['output']!r}")

    stats = {
        'level': level,
        'seeds': seeds,
        'candidates': len(all_cands),
        'S3': len(s3),
        'output_distribution': dict(sorted(Counter(r['output_len'] for r in s3).items())),
        'prefix_matches': matches[:20],
        'S5_quines': len(quines),
        'elapsed_s': round(time.time()-t0, 1),
    }
    with open(f'quine_research/search_quine_malbolge/results/seeds_plen{level}.json', 'w') as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)
    print(f"[SEEDS] Saved seeds_plen{level}.json")
    return stats

if __name__ == '__main__':
    # Frontier inicial: S3 del espacio plen=3 completo
    print("Building initial frontier from full plen=3 space...")
    t0 = time.time()
    candidates = generate_candidates(mode='program', max_program_length=3,
                                      max_input_length=0, limit=None)
    batch_dicts = [{'program': c.program, 'input_data': '', 'max_steps': 100_000}
                   for c in candidates]
    results = execute_dicts(batch_dicts)
    frontier = []
    for c, rr in zip(candidates, results):
        if rr.get('terminated', False) and len(rr.get('output', '')) > 0:
            frontier.append(c.program)
    print(f"Initial frontier: {len(frontier):,} programs in {time.time()-t0:.1f}s")

    # Nivel 4 con frontier completo (ya validado: 2.4M)
    stats, frontier = run_level(4, frontier)
    # Niveles siguientes con pruning
    for level in [5, 6]:
        stats, frontier = run_level(level, frontier)

    # Familias semilla exhaustivas hasta plen=6
    seed_families(6)

    print("DONE")