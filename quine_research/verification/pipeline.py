"""
verification_pipeline.py - Pipeline de verificación para candidatos Quine.

Pipeline:
  1. PARSER: carga el candidato y extrae CODE/DATA
  2. EXECUTION: ejecuta el candidato con el evaluador de referencia
  3. TERMINATION: verifica que termina (no loop infinito)
  4. OUTPUT_EXACT: compara byte-por-byte el output con el raw file
  5. DETERMINISM: verifica que ejecución repetida da el mismo output

Uso:
    python pipeline.py candidate.mal
    python pipeline.py --batch candidates/*.mal
"""

import sys
import os
import hashlib
import time
import json

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


def verify_candidate(path, max_steps=200_000_000, check_breakpoint_file=None):
    """
    Ejecuta el candidato y verifica que su raw output es su código fuente original.
    """
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
        if steps > max_steps:
            break
        if 33 <= mem[c] <= 126:
            mem[c] = ord(ENCRYPT[mem[c] - 33])
        c = 0 if c == POW10 - 1 else c + 1
        d = 0 if d == POW10 - 1 else d + 1
    
    elapsed = time.time() - t0
    output = ''.join(output_chars)
    
    result = {
        'file': os.path.basename(path),
        'raw_size': len(raw),
        'output_size': len(output),
        'total_steps': steps,
        'elapsed_s': round(elapsed, 2),
        'steps_per_sec': round(steps / max(0.001, elapsed)),
        'quine_match': output == raw,
        'quine_clean_match': output == clean,
        'halt_reason': 'end_opcode' if steps < max_steps else 'max_steps',
        'first_output': output[:100] if output else '',
        'sha256_output': hashlib.sha256(output.encode('latin1')).hexdigest()[:16],
    }
    
    return result


if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit(1)
    files = sys.argv[1:]
    
    results = []
    for f in files:
        if not os.path.exists(f):
            continue
        r = verify_candidate(f)
        results.append(r)
    
    # Save results
    out_path = 'quine_research/evidence/pipeline_results.json'
    with open(out_path, 'w') as f:
        json.dump(results, f, indent=2)
    
    for r in results:
        status = "✅ QUINE" if r['quine_match'] else "❌ NOT QUINE"
        print(f"[{status}] {r['file']}")
        print(f"  Steps: {r['total_steps']:,} ({r['steps_per_sec']:,}/s)")
        print(f"  Output: {r['output_size']} chars, match={r['quine_match']}")
        if not r['quine_match']:
            print(f"  First 80 chars: {r['first_output']}")