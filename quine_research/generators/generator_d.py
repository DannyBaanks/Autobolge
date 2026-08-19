"""
generator_d.py - Family D: Memoria derivada (crazy/rotr runtime derivation).

Strategy:
  - Short prefix (e.g. 512 bytes) contains boot code
  - Boot code uses 'crz' and 'rotr' to DERIVE remaining bytes during execution
  - Each DATA cell[i] = crazy(X, code[i % prefix_len]) for fixed X
  - During output: read DATA[i], apply rotr (inverse of crazy) to recover code[i]
"""

import hashlib
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

ENCRYPT = "5z]&gqtyfr$(we4{WP)H-Zn,[%\\3dL+Q;>U!pJS72FhOA1CB6v^=I_0/8|jsb9m<.TVac`uY*MK'X~xDl}REokN:#?G\"i@"
CRAZY_TBL = [[1, 0, 0], [1, 0, 2], [2, 2, 1]]
POW10 = 59049


def crazy(a, b):
    res, p = 0, 1
    for _ in range(10):
        res += CRAZY_TBL[b % 3][a % 3] * p
        a, b, p = a // 3, b // 3, p * 3
    return res


def rotate(n):
    return (n % 3) * 19683 + (n // 3)


def load_baseline_clean():
    with open('quine_research/baseline_quine.mal', 'r', encoding='latin1') as f:
        raw = f.read()
    clean = ''.join(c for c in raw if 33 <= ord(c) <= 126)
    return raw, clean


def make_raw_preserving_structure(clean_source, new_clean):
    """Preserva newlines del baseline, solo reemplaza chars imprimibles."""
    raw_base, _ = load_baseline_clean()
    assert len(new_clean) == len(clean_source)
    new_raw = []
    ci = 0
    for ch in raw_base:
        if 33 <= ord(ch) <= 126:
            new_raw.append(new_clean[ci])
            ci += 1
        else:
            new_raw.append(ch)
    return ''.join(new_raw)


def generate_d_fixed_operand(operand, data_region_size=29516):
    """
    Family D: DATA[i] = crazy(operand, src[i])
    donde src es el source_code completo.
    Boot code debe deshacer con rotr antes de out.
    
    operand: valor fijo A usado en todas las celdas DATA
    """
    raw_base, clean_base = load_baseline_clean()
    src = clean_base  # todo el source (29532 = 29516 CODE + 29516 DATA, pero aqui es 59032)
    code_region = src[:29516]
    full_data = src[29516:59032]  # original DATA region
    
    # Generamos NUEVO DATA: cada celda = crazy(operand, src[i])
    # Pero usamos src como la fuente verdadera
    new_data = ''.join(chr(crazy(operand, ord(full_data[i]))) for i in range(len(full_data)))
    
    new_clean = code_region + new_data
    new_raw = make_raw_preserving_structure(clean_base, new_clean)
    
    return {
        'family': 'D',
        'params': {'operand': operand, 'data_size': data_region_size},
        'code': code_region,
        'data': new_data,
        'raw': new_raw,
        'source_size': len(new_raw),
        'code_size': len(code_region),
        'data_size': len(new_data),
        'note': f'DATA = crazy({operand}, src[i])',
    }


def generate_d_alternating_operand(op_even, op_odd, data_region_size=29516):
    """
    Family D variant: alternating operands even/odd positions.
    DATA[i] = crazy(op_even, src[i]) if i%2==0 else crazy(op_odd, src[i])
    """
    raw_base, clean_base = load_baseline_clean()
    code_region = clean_base[:29516]
    full_data = clean_base[29516:59032]
    
    new_data = ''.join(
        chr(crazy(op_even if i % 2 == 0 else op_odd, ord(full_data[i])))
        for i in range(len(full_data))
    )
    
    new_clean = code_region + new_data
    new_raw = make_raw_preserving_structure(clean_base, new_clean)
    
    return {
        'family': 'D',
        'params': {'op_even': op_even, 'op_odd': op_odd, 'data_size': data_region_size},
        'code': code_region,
        'data': new_data,
        'raw': new_raw,
        'source_size': len(new_raw),
        'code_size': len(code_region),
        'data_size': len(new_data),
        'note': f'DATA alternada: even=crz({op_even}), odd=crz({op_odd})',
    }


def generate_all_family_d():
    """Genera todos los candidatos D con varios operandos."""
    candidates = []
    
    # Fixed single operand: probar 59048 (EOF_A), 9841 (0*3^0 + 1*3^1 + ...), otros "interesantes"
    for operand in [59048, 1, 2, 3, 9, 27, 81, 59047, 29524, 14762, 7381]:
        try:
            gen = generate_d_fixed_operand(operand)
            candidates.append(gen)
        except Exception as e:
            print(f'  [WARN] D operand {operand} failed: {e}')
    
    # Alternating pairs
    for op_even, op_odd in [(59048, 1), (1, 2), (59048, 9841), (2, 3)]:
        try:
            gen = generate_d_alternating_operand(op_even, op_odd)
            candidates.append(gen)
        except Exception as e:
            print(f'  [WARN] D alt {op_even},{op_odd} failed: {e}')
    
    return candidates


if __name__ == '__main__':
    import json
    candidates = generate_all_family_d()
    os.makedirs('quine_research/generated', exist_ok=True)
    for c in candidates:
        cid = f'D_op{c[\"params\"][\"operand\"]}'
        if 'op_even' in c['params']:
            cid = f'D_alt{c[\"params\"][\"op_even\"]}_{c[\"params\"][\"op_odd\"]}'
        path = f'quine_research/generated/{cid}.mal'
        with open(path, 'w', encoding='latin1') as f:
            f.write(c['raw'])
        print(f'  Generated {cid}: size={c[\"source_size\"]}')
    
    print(f'\nTotal D candidates: {len(candidates)}')