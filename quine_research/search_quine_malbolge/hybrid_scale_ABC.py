"""Fusión Translator + Zig batch para generar bank de programas ABC.

Flags:
  --memo         comparte el state_cache del solver entre los 676 targets (H3).
  --workers N    paraleliza la generación con ProcessPoolExecutor (H4).

Instrumentación por target (se guarda en results/gen_instrumentation_*.json):
  target, nodes_expanded (evaluations), states_revisited (repeated_state_pruned),
  cache_hits, solution_length, generation_ms.
"""
import sys, json, time
sys.path.insert(0, 'quine_research/search_quine_malbolge')
from translator_hybrid import (
    TranslatorCandidateFactory,
    TranslatorVerifier,
    generate_chunk_worker,
)
from zig_batch import prepare_batch_from_dicts, run_batch


def main() -> None:
    memo = '--memo' in sys.argv
    workers = 0
    if '--workers' in sys.argv:
        workers = int(sys.argv[sys.argv.index('--workers') + 1])
    mode = 'memo' if memo else (f'par_w{workers}' if workers > 1 else 'baseline')
    print(f'Mode: {mode}')

    factory = TranslatorCandidateFactory(max_search_depth=5)
    verifier = TranslatorVerifier(max_steps=5_000_000)

    alphabet = [chr(c) for c in range(ord('A'), ord('Z')+1)]
    targets = [a+b for a in alphabet for b in alphabet]
    print(f'Targets: {len(targets)}')

    shared_cache: dict = {} if memo else None
    gen_meta: dict = {}

    t0 = time.time()
    if workers > 1:
        import math
        from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED

        import psutil

        items = list(enumerate(targets))
        n_chunks = workers * 4
        chunk_size = math.ceil(len(items) / n_chunks)
        chunks = [items[i:i + chunk_size] for i in range(0, len(items), chunk_size)]

        pool_start = time.time()
        first_result_s = None
        results = []
        with ProcessPoolExecutor(max_workers=workers) as pool:
            parent = psutil.Process()
            futures = [
                pool.submit(generate_chunk_worker, (chunk, 5))
                for chunk in chunks
            ]
            pending = set(futures)
            peak_rss_mb = 0.0
            while pending:
                done, pending = wait(pending, timeout=0.5, return_when=FIRST_COMPLETED)
                rss = 0
                for child in parent.children(recursive=True):
                    try:
                        rss += child.memory_info().rss
                    except psutil.Error:
                        pass
                peak_rss_mb = max(peak_rss_mb, rss / 1e6)
                for fut in done:
                    if first_result_s is None:
                        first_result_s = round(time.time() - pool_start, 2)
                    results.extend(fut.result())
        results.sort(key=lambda c: c['_index'])
        raw = results
        gen_meta = {
            'workers': workers,
            'chunks': len(chunks),
            'startup_overhead_s': first_result_s,
            'peak_worker_rss_mb': round(peak_rss_mb, 1),
        }
    else:
        raw = factory.batch(targets, shared_state_cache=shared_cache)
    gen_time = time.time() - t0
    print(f'Generated: {len(raw)} in {gen_time:.1f}s')
    if shared_cache is not None:
        print(f'Shared cache entries: {len(shared_cache)}')
    if gen_meta:
        print(f'Workers: {gen_meta}')

    instrumentation = [
        {
            'target': c['target'],
            'nodes_expanded': c['stats']['evaluations'],
            'states_revisited': c['stats']['repeated_state_pruned'],
            'cache_hits': c['stats']['cache_hits'],
            'solution_length': len(c['opcodes']),
            'generation_ms': round(c['stats']['duration_ns'] / 1e6, 3),
        }
        for c in raw
    ]

    # Zig batch batch verification
    batch_dicts = [{'program': c['program_source'], 'input_data': '', 'max_steps': 5000000} for c in raw]
    batch = prepare_batch_from_dicts(batch_dicts)

    t1 = time.time()
    zig_results = run_batch(batch, bolge_path='zig/bolge.exe', work_dir='.')
    zig_time = time.time() - t1
    print(f'Zig batch: {zig_time:.2f}s ({len(batch_dicts)/max(0.001,zig_time):.0f} cand/s)')

    matched = 0
    mismatched = 0
    quine_candidates = []
    for i, (c, zr) in enumerate(zip(raw, zig_results)):
        zig_out = zr.get('output', '')
        tgt = c['target']
        source = c['program_source'] + chr(10) + tgt + chr(10)
        if zig_out == tgt:
            matched += 1
        else:
            mismatched += 1
            if mismatched <= 3:
                print(f'  Mismatch target={tgt!r} zig={zig_out!r}')
        if zig_out == source:
            quine_candidates.append({
                'program': c['program_source'],
                'opcodes': c['opcodes'],
                'target': tgt,
                'source': source,
                'output': zig_out,
                'steps': zr.get('steps', 0),
            })

    print(f'Matched: {matched}/{len(raw)} | Mismatched: {mismatched}')
    print(f'Quine candidates: {len(quine_candidates)}')
    for q in quine_candidates:
        print(f'  QUINE: prog={q["program"][:50]!r} src={q["source"][:50]!r}')

    bank = {
        'alphabet': 'A-Z',
        'target_count': len(targets),
        'candidates': [
            {
                'program': c['program_source'],
                'opcodes': c['opcodes'],
                'target': c['target'],
                'zig_output': zig_results[i].get('output', ''),
                'zig_steps': zig_results[i].get('steps', 0),
                'zig_terminated': zig_results[i].get('terminated', False),
                'zig_match': zig_results[i].get('output', '') == c['target'],
            }
            for i, c in enumerate(raw)
        ],
        'stats': {
            'mode': mode,
            'total': len(raw),
            'matched': matched,
            'mismatched': mismatched,
            'quine_candidates': len(quine_candidates),
            'gen_time_s': round(gen_time, 2),
            **gen_meta,
            'zig_time_s': round(zig_time, 2),
            'zig_throughput': round(len(raw)/max(0.001, zig_time), 1),
        }
    }
    bank_name = ('program_bank_ABC_zig_memo.json' if memo
                 else f'program_bank_ABC_zig_w{workers}.json' if workers > 1
                 else 'program_bank_ABC_zig.json')
    with open(f'quine_research/search_quine_malbolge/results/{bank_name}', 'w') as f:
        json.dump(bank, f, indent=2, ensure_ascii=False)
    print(f'Saved: {bank_name}')

    instr = {
        'mode': mode,
        'gen_time_s': round(gen_time, 2),
        **gen_meta,
        'per_target': instrumentation,
        'totals': {
            'nodes_expanded': sum(m['nodes_expanded'] for m in instrumentation),
            'cache_hits': sum(m['cache_hits'] for m in instrumentation),
            'states_revisited': sum(m['states_revisited'] for m in instrumentation),
            'generation_ms': round(sum(m['generation_ms'] for m in instrumentation), 1),
        },
    }
    instr_name = f'quine_research/search_quine_malbolge/results/gen_instrumentation_{mode}.json'
    with open(instr_name, 'w') as f:
        json.dump(instr, f, indent=2, ensure_ascii=False)
    print(f'Saved: gen_instrumentation_{mode}.json')


if __name__ == '__main__':
    main()
