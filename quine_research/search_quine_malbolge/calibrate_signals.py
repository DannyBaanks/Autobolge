from pathlib import Path
"""Calibración completa del pipeline Malbolge.
Explora espacios pequeños y mide TODAS las señales disponibles.
NO implementa beam. Solo mide.
"""
import sys, os, json, time, collections
os.chdir(Path(__file__).resolve().parents[2])
sys.path.insert(0, 'quine_research/search_quine_malbolge')
from search_quine_malbolge import (Candidate, ExecutionResult, execute_stage,
                                     halt_stage, output_stage, generate_candidates,
                                     encode_candidate, TIERS)
from zig_batch import prepare_batch, run_batch

def hamming(a, b):
    n = min(len(a), len(b))
    return sum(1 for i in range(n) if a[i] != b[i])

def analyze_signals(candidates, s1_all, s2, s3):
    rows = []
    for i, rr in enumerate(s1_all):
        cand = candidates[i] if i < len(candidates) else Candidate("", "")
        src = cand.source
        out = rr.output
        halted = rr.halted

        # Señales básicas
        output_len = len(out)
        source_len = len(src)
        prefix_len = 0
        positional = 0
        byte_overlap = 0
        src_bytes = set(src)
        out_bytes = set(out)
        for a, b in zip(out, src):
            if a == b:
                positional += 1
                byte_overlap += 1
            prefix_len = positional  # same as positional since it's prefix

        ham = hamming(out, src)
        ham_trunc = ham / max(1, min(output_len, source_len))
        ratio_out_src = output_len / max(1, source_len)
        ratio_out_src_trunc = min(output_len, source_len) / max(1, max(output_len, source_len))

        rows.append({
            'program': cand.program,
            'input': cand.input_data,
            'source': src,
            'source_len': source_len,
            'output': out,
            'output_len': output_len,
            'halted': halted,
            'steps': rr.steps,
            'status': rr.status,
            'prefix_len': prefix_len,
            'positional_match': positional,
            'positional_ratio': positional / max(1, source_len),
            'byte_overlap': byte_overlap,
            'byte_overlap_ratio': byte_overlap / max(1, len(set(src) | set(out))),
            'hamming': ham,
            'hamming_trunc_ratio': ham_trunc,
            'output_source_ratio': ratio_out_src,
            'overlap_ratio_trunc': ratio_out_src_trunc,
            'first_byte_src': src[0] if src else '',
            'first_byte_out': out[0] if out else '',
            'first_byte_match': (src[0] == out[0]) if src and out else False,
            'distinct_output_bytes': len(out_bytes),
            'output_nonempty': output_len > 0,
            'output_equals_source': out == src,
        })
    return rows

def classify_signal(rows, signal_key):
    values = [r[signal_key] for r in rows]
    unique = sorted(set(values))
    n = len(values)
    dist = collections.Counter(values)
    print(f"\nSignal: {signal_key}")
    print(f"  unique_count: {len(unique)}")
    print(f"  top values: {dist.most_common(10)}")
    if len(unique) <= 1:
        classification = "FLAT"
    elif len(unique) == 2:
        classification = "WEAK"
    else:
        # Check if it correlates with exact_match
        exacts = [r for r in rows if r.get('output_equals_source', False)]
        if exacts:
            exact_vals = [r[signal_key] for r in exacts]
            non_exact = [r[signal_key] for r in rows if not r.get('output_equals_source', False)]
            # If exacts cluster at one extreme
            if min(exact_vals) > max(non_exact) or max(exact_vals) < min(non_exact):
                classification = "USEFUL"
            else:
                classification = "WEAK"
        else:
            classification = "UNKNOWN"
    print(f"  classification: {classification}")
    return classification

def run_calibration():
    configs = [
        {"plen": 1, "ilen": 0},
        {"plen": 1, "ilen": 1},
        {"plen": 2, "ilen": 0},
        {"plen": 2, "ilen": 1},
        {"plen": 3, "ilen": 0},
        {"plen": 3, "ilen": 1},
    ]

    all_results = {}
    for cfg in configs:
        key = f"plen{cfg['plen']}_ilen{cfg['ilen']}"
        print(f"\n{'='*60}")
        print(f"Config: {key}")
        print(f"{'='*60}")

        candidates = generate_candidates(
            mode='both', max_program_length=cfg['plen'],
            max_input_length=cfg['ilen'], limit=300
        )

        t0 = time.time()
        s1_all = execute_stage(candidates, tiers=TIERS)
        s1 = [r for r in s1_all if r.survived()]
        s2 = halt_stage(s1)
        s3 = output_stage(s2)
        elapsed = time.time() - t0

        print(f"S0={len(candidates)} S1={len(s1)} S2={len(s2)} S3={len(s3)} time={elapsed:.2f}s")

        rows = analyze_signals(candidates, s1_all, s2, s3)
        all_results[key] = {
            'config': cfg,
            'stats': {
                'S0': len(candidates), 'S1': len(s1), 'S2': len(s2),
                'S3': len(s3), 'time_s': round(elapsed, 2)
            },
            'rows': rows,
        }

        # Classify signals
        signals = [
            'output_len', 'prefix_len', 'positional_match', 'positional_ratio',
            'byte_overlap', 'byte_overlap_ratio', 'hamming_trunc_ratio',
            'output_source_ratio', 'overlap_ratio_trunc', 'first_byte_match',
            'distinct_output_bytes', 'halted', 'steps'
        ]
        classifications = {}
        for sig in signals:
            classifications[sig] = classify_signal(rows, sig)
        all_results[key]['classifications'] = classifications

    # Save all
    out_path = 'quine_research/search_quine_malbolge/results/calibration_signals.json'
    with open(out_path, 'w') as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False, default=str)
    print(f"\nSaved calibration: {out_path}")
    return all_results

if __name__ == '__main__':
    run_calibration()