"""
run_search.py - Ejecuta la búsqueda completa de candidatos y verificación.
Fases 6-9: execution, verification, comparison, report.
"""

import sys
import os
import time
import json
import hashlib

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

ENCRYPT = "5z]&gqtyfr$(we4{WP)H-Zn,[%\\3dL+Q;>U!pJS72FhOA1CB6v^=I_0/8|jsb9m<.TVac`uY*MK'X~xDl}REokN:#?G\"i@"
CRAZY_TBL = [[1, 0, 0], [1, 0, 2], [2, 2, 1]]
POW10 = 59049
EOF_A = 59048


def crazy(a, b):
    res, p = 0, 1
    for _ in range(10):
        res += CRAZY_TBL[b % 3][a % 3] * p
        a, b, p = a // 3, b // 3, p * 3
    return res


def rotate(n):
    return (n % 3) * 19683 + (n // 3)


def load_baseline():
    with open('quine_research/baseline_quine.mal', 'r', encoding='latin1') as f:
        raw = f.read()
    clean = ''.join(c for c in raw if 33 <= ord(c) <= 126)
    return raw, clean


def make_raw_preserving_structure(clean_source, new_clean):
    """
    Reconstruye raw manteniendo la estructura de newlines del baseline.
    Cada caracter imprimible en raw se reemplaza por el siguiente de new_clean.
    Los newlines (\n, chr 10) se mantienen en sus posiciones originales.
    """
    assert len(new_clean) == len(clean_source), "new_clean must match clean_source length"
    
    raw_base, _ = load_baseline()
    new_raw = []
    clean_idx = 0
    
    for ch in raw_base:
        if 33 <= ord(ch) <= 126:
            new_raw.append(new_clean[clean_idx])
            clean_idx += 1
        else:
            new_raw.append(ch)  # keep newlines and other non-printable as-is
    
    return ''.join(new_raw)


def verify_candidate(path, max_steps=200_000_000):
    """Ejecuta un candidato y verifica propiedad quine."""
    with open(path, 'r', encoding='latin1') as f:
        raw = f.read()
    
    clean = ''.join(c for c in raw if 33 <= ord(c) <= 126)
    src_len = len(clean)
    
    mem = [0] * POW10
    for i, c in enumerate(clean):
        mem[i] = ord(c)
    for i in range(src_len, POW10):
        mem[i] = crazy(mem[i - 1], mem[i - 2])
    
    a, c, d = 0, 0, 0
    output_chars = []
    steps = 0
    
    t0 = time.time()
    while True:
        val = mem[c]
        if val < 33 or val > 126:
            break
        v = (val + c) % 94
        steps += 1
        if steps > max_steps:
            break
        
        if v == 4:
            c = mem[d]
        elif v == 5:
            output_chars.append(chr(a % 256))
        elif v == 23:
            a = EOF_A
        elif v == 39:
            v_rot = rotate(mem[d])
            mem[d] = v_rot
            a = v_rot
        elif v == 40:
            d = mem[d]
        elif v == 62:
            res = crazy(a, mem[d])
            mem[d] = res
            a = res
        elif v == 81:
            break
        
        if 33 <= mem[c] <= 126:
            mem[c] = ord(ENCRYPT[mem[c] - 33])
        c = 0 if c == POW10 - 1 else c + 1
        d = 0 if d == POW10 - 1 else d + 1
    
    elapsed = time.time() - t0
    output = ''.join(output_chars)
    
    return {
        'file': os.path.basename(path),
        'raw_size': len(raw),
        'output_size': len(output),
        'total_steps': steps,
        'elapsed_s': round(elapsed, 2),
        'steps_per_sec': round(steps / max(0.001, elapsed)),
        'quine_match': output == raw,
        'quine_clean_match': output == clean,
        'halt_reason': 'end_opcode' if steps < max_steps else 'max_steps',
        'sha256_output': hashlib.sha256(output.encode('latin1')).hexdigest()[:16],
        'sha256_source': hashlib.sha256(raw.encode('latin1')).hexdigest()[:16],
    }


def generate_all_candidates():
    """Genera candidatos de familias B1-B4 con estructura de raw preservada."""
    raw_base, clean_base = load_baseline()
    code_region = clean_base[:29516]
    data_region = clean_base[29516:59032]
    candidates = []
    
    # B1: rotate modulo 94 mapped to printable
    for offset in [0, 33, 66]:
        transformed_data = ''.join(
            chr(((rotate(ord(c)) % 94) + 33 + offset) % 94 + 33) for c in code_region
        )
        new_clean = code_region + transformed_data
        raw = make_raw_preserving_structure(clean_base, new_clean)
        candidates.append({
            'candidate_id': f'B1_off{offset}',
            'family': 'B1',
            'params': {'offset': offset},
            'code': code_region,
            'data': transformed_data,
            'raw': raw,
            'source_size': len(raw),
            'code_size': len(code_region),
            'data_size': len(transformed_data),
        })
    
    # B2: XOR
    for key in [0x00, 0x20, 0x40, 0x7F]:
        xor_data = ''.join(chr(ord(c) ^ key) for c in code_region)
        new_clean = code_region + xor_data
        raw = make_raw_preserving_structure(clean_base, new_clean)
        candidates.append({
            'candidate_id': f'B2_key{key}',
            'family': 'B2',
            'params': {'key': key},
            'code': code_region,
            'data': xor_data,
            'raw': raw,
            'source_size': len(raw),
            'code_size': len(code_region),
            'data_size': len(xor_data),
        })
    
    # B3: mask AND (only masks that preserve printable range)
    for mask in [0x7F, 0x3F]:
        masked_data = ''.join(chr(ord(c) & mask) for c in code_region)
        new_clean = code_region + masked_data
        raw = make_raw_preserving_structure(clean_base, new_clean)
        candidates.append({
            'candidate_id': f'B3_mask{mask}',
            'family': 'B3',
            'params': {'mask': mask},
            'code': code_region,
            'data': masked_data,
            'raw': raw,
            'source_size': len(raw),
            'code_size': len(code_region),
            'data_size': len(masked_data),
        })
    
    # B4: chunk + repetición
    for chunk_size in [512, 1024, 2048, 4096]:
        seed = code_region[:chunk_size]
        repeats = 29516 // chunk_size
        remainder = 29516 % chunk_size
        data_reconstructed = (seed * repeats) + seed[:remainder]
        new_clean = code_region + data_reconstructed
        raw = make_raw_preserving_structure(clean_base, new_clean)
        candidates.append({
            'candidate_id': f'B4_chunk{chunk_size}',
            'family': 'B4',
            'params': {'chunk_size': chunk_size},
            'code': code_region,
            'data': data_reconstructed,
            'raw': raw,
            'source_size': len(raw),
            'code_size': len(code_region),
            'data_size': len(data_reconstructed),
        })
    
    return candidates


def main():
    print("=" * 60)
    print("PHASE 6-9: FULL SEARCH + VERIFICATION + REPORT")
    print("=" * 60)
    
    # Phase 6: Generate
    print("\n[*] PHASE 6: Generating candidates...")
    t0 = time.time()
    candidates = generate_all_candidates()
    gen_time = time.time() - t0
    print(f"  Generated {len(candidates)} candidates in {gen_time:.2f}s")
    
    # Phase 7: Verify
    print("\n[*] PHASE 7: Verification pipeline...")
    results = []
    os.makedirs('quine_research/generated', exist_ok=True)
    
    baseline_path = 'quine_research/baseline_quine.mal'
    with open(baseline_path, 'r', encoding='latin1') as f:
        baseline_raw = f.read()
    baseline_result = verify_candidate(baseline_path)
    
    for i, c in enumerate(candidates):
        cid = c['candidate_id']
        fpath = os.path.join('quine_research', 'generated', f'{cid}.mal')
        with open(fpath, 'w', encoding='latin1') as f:
            f.write(c['raw'])
        
        print(f"  [{i+1}/{len(candidates)}] {cid}...")
        r = verify_candidate(fpath)
        
        result_entry = {
            'candidate_id': cid,
            'family': c['family'],
            'params': c['params'],
            'source_size': c['source_size'],
            'code_size': c['code_size'],
            'data_size': c['data_size'],
            'execution_steps': r['total_steps'],
            'elapsed_s': r['elapsed_s'],
            'valid': r['quine_match'],
            'halted': r['halt_reason'] == 'end_opcode',
            'output_matches_source': r['quine_match'],
            'output_hash': r['sha256_output'],
            'source_hash': r['sha256_source'],
            'rejection_reason': '' if r['quine_match'] else 'output_mismatch',
            'steps_per_sec': r['steps_per_sec'],
        }
        results.append(result_entry)
        
        status = "QUINE" if r['quine_match'] else "not-quine"
        print(f"    [{status}] steps={r['total_steps']:,} size={c['source_size']} valid={r['quine_match']}")
    
    # Phase 8: Comparison
    print("\n[*] PHASE 8: Comparison...")
    best_valid = [r for r in results if r['valid']]
    baseline_size = baseline_result['raw_size']
    
    # Among valid quines, find smallest
    best_valid_entry = min(best_valid, key=lambda r: r['source_size']) if best_valid else None
    
    # Overall smallest candidate (may not be valid)
    best_overall = min(results, key=lambda r: r['source_size']) if results else None
    
    has_reduction = best_valid_entry and best_valid_entry['source_size'] < baseline_size
    
    comparison = {
        'baseline_size': baseline_size,
        'baseline_steps': baseline_result['total_steps'],
        'best_candidate_size': best_valid_entry['source_size'] if best_valid_entry else None,
        'best_valid_size': best_valid_entry['source_size'] if best_valid_entry else None,
        'best_valid_id': best_valid_entry['candidate_id'] if best_valid_entry else None,
        'smallest_overall_size': best_overall['source_size'] if best_overall else None,
        'smallest_overall_id': best_overall['candidate_id'] if best_overall else None,
        'reduction_absolute': (baseline_size - best_valid_entry['source_size']) if best_valid_entry else 0,
        'reduction_percent': ((baseline_size - best_valid_entry['source_size']) / baseline_size * 100) if best_valid_entry else 0,
        'valid_count': len(best_valid),
        'has_reduction': has_reduction,
    }
    
    print(f"  Baseline: {baseline_size} bytes, {baseline_result['total_steps']:,} steps")
    if best_valid_entry:
        print(f"  Best valid: {best_valid_entry['source_size']} bytes ({best_valid_entry['candidate_id']})")
    else:
        print(f"  Best valid: N/A")
    if has_reduction:
        print(f"  REDUCTION: {comparison['reduction_absolute']} bytes ({comparison['reduction_percent']:.2f}%)")
    else:
        print(f"  Reduction: 0 bytes (0.00%)")
    print(f"  Valid quines: {len(best_valid)}")
    
    # Phase 9: Report
    print("\n[*] PHASE 9: Report...")
    os.makedirs('quine_research/results', exist_ok=True)
    
    evidence = {
        'baseline': {
            'source_size': baseline_size,
            'execution_steps': baseline_result['total_steps'],
            'hash': baseline_result['sha256_source'],
        },
        'candidates': results,
        'comparison': comparison,
        'summary': {
            'total': len(candidates),
            'valid': len(best_valid),
            'best_valid_id': best_valid_entry['candidate_id'] if best_valid_entry else None,
            'best_valid_size': best_valid_entry['source_size'] if best_valid_entry else None,
            'generation_time_s': gen_time,
            'total_verify_time_s': sum(r['elapsed_s'] for r in results),
        }
    }
    
    with open('quine_research/results/candidates.jsonl', 'w') as f:
        for r in results:
            f.write(json.dumps(r) + '\n')
    
    with open('quine_research/results/search_manifest.json', 'w') as f:
        json.dump(evidence, f, indent=2)
    
    if best_valid_entry:
        with open('quine_research/results/best_candidate.json', 'w') as f:
            json.dump(best_valid_entry, f, indent=2)
    
    # Final
    print("\n" + "=" * 60)
    print("STATUS")
    print("=" * 60)
    status_str = 'FOUND' if has_reduction else 'NOT_FOUND_WITHIN_EXPLORED_BOUNDS'
    print(f"  STATUS: {status_str}")
    print(f"  baseline_size: {baseline_size}")
    print(f"  best_size: {best_valid_entry['source_size'] if best_valid_entry else 'N/A'}")
    print(f"  reduction: {comparison['reduction_absolute']} bytes ({comparison['reduction_percent']:.2f}%)")
    print(f"  family: {best_valid_entry['family'] if best_valid_entry else 'N/A'}")
    print(f"  candidates_explored: {len(candidates)}")
    print(f"  verification: {'PASSED' if best_valid else 'FAILED'}")
    print(f"  evidence_hash: {hashlib.sha256(json.dumps(results).encode()).hexdigest()[:16]}")
    print(f"  tests: {len(best_valid)} valid, {len(results) - len(best_valid)} failed")
    print(f"  conclusion: {'Smaller quine found!' if has_reduction else 'No smaller quine in explored space.'}")
    
    if best_valid_entry:
        print(f"\n  WINNER: {best_valid_entry['candidate_id']}")
        print(f"  Frozen at: quine_research/results/best_candidate.json")


if __name__ == '__main__':
    main()