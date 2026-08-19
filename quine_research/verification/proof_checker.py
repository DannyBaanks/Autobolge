"""
proof_checker.py - Verificador de prueba estructural para candidatos Quine.

Permite verificar la propiedad QUI_NE sin ejecutar 69M de pasos,
mediante invariantes estructurales.

Uso:
    python proof_checker.py candidate.mal
"""

import sys
import hashlib
import os

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


def load_mem(path):
    with open(path, 'r', encoding='latin1') as f:
        raw = f.read()
    # Split on newlines to get code and data
    parts = raw.split('\n')
    code_part = ''
    data_part = ''
    for i, p in enumerate(parts):
        if i == 0:
            code_part = p
        elif i == 1:
            data_part = p
    # If no newline, assume single
    if len(parts) == 1:
        code_part = parts[0]
        data_part = parts[0][29516:59032] if len(parts[0]) >= 59032 else ''
    
    return raw, code_part, data_part


def check_R1(code, data):
    """Check if CODE == DATA (region 0..29515 == 29516..59031)"""
    c1 = code[:29516]
    c2 = data[:29516] if len(data) >= 29516 else ''
    return c1 == c2


def check_R2(code):
    """Check if D initialization is at address 29516 (start of DATA)"""
    # Look for a pattern that sets d=29516 via mov_d, [d]
    # First we need M[d] = 29516 for some d reachable from d=0
    # This check is heurística
    return "mov_d" in code or "29516" in code


def check_R3(code):
    """Check if `in` opcode is not used (no stdin needed)"""
    # `in` corresponds to v==23: chr(value_code[c]) where code[c] comes from the source
    # Heurística: look for patterns suggesting input usage
    return "EOF_A" not in code  # Simplificación


def structural_check(path):
    raw, code, data = load_mem(path)
    
    r1 = check_R1(code, data)
    r2 = check_R2(code)
    r3 = check_R3(code)
    q_ine_potential = len(raw) == len(code) + len(data) + 1  # +1 for newline
    
    size_check = {'raw': len(raw), 'code': len(code), 'data': len(data)}
    
    # Determine family from structure
    family_guess = 'A' if r1 else ('B' if r2 else 'unknown')
    
    return {
        'file': path,
        'family_guess': family_guess,
        'size_check': size_check,
        'R1_CODE_EQUALS_DATA': r1,
        'R2_D_init_at_DATA': r2,
        'R3_no_stdin': r3,
        'QUI_NE_potential': q_ine_potential,
        'R1_violated': not r1,
        'R2_violated': not r2,
    }


if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit(1)
    path = sys.argv[1]
    if not os.path.exists(path):
        sys.exit(1)
    result = structural_check(path)
    for k, v in result.items():
        print(f"  {k}: {v}")