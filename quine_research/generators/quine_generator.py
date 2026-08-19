"""
quine_generator.py - Generador paramétrico de candidatos Quine.

Genera variantes paramétricas sobre la familia de reconstrucción (Family B)
para explorar el espacio de quines de Malbolge que NO requieren CODE==DATA.

Familias soportadas:
  FAMILY_B_1:  rotate(S)  +  offset fijo en la lectura
  FAMILY_B_2:  S XOR k   +  compensación XOR en out
  FAMILY_B_3:  permute(S, π)  +  permutación inversa en lectura
  FAMILY_B_4:  S[k:]     +  rotación circular (eliminar sufijo repetido)

Uso:
    python quine_generator.py --family B1 --offset 0 --save
    python quine_generator.py --family B2 --key 0x42 --verify
    python quine_generator.py --family B3 --perm-seed 12345 --verify
"""

import sys
import os
import hashlib
import random
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))
from malbolge import malbolge  # si está disponible, si no usamos python puro

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


def load_baseline_mem():
    with open('quine_research/baseline_quine.mal', 'r', encoding='latin1') as f:
        raw = f.read()
    clean = ''.join(c for c in raw if 33 <= ord(c) <= 126)
    mem = [0] * POW10
    for i, c in enumerate(clean):
        mem[i] = ord(c)
    for i in range(len(clean), POW10):
        mem[i] = crazy(mem[i - 1], mem[i - 2])
    return raw, clean, mem


# ----------- Family B1: rotate(S) -----------

def generate_b1(offset=0):
    """
    Reemplaza DATA con rotate(CODE) aplicado carácter a carácter.
    
    Para deshacer la rotación al leer, insertamos rotr antes de out.
    offset: un offset fijo que se suma al byte leído antes de out (para compensar rotate)
    """
    raw, clean, base_mem = load_baseline_mem()
    code_region = clean[:29516]
    data_region = clean[29516:59032]

    # Transformación: cada byte de DATA es el byte CODE rotado
    rotated_data = ''.join(chr(rotate(ord(c))) for c in code_region)

    # Reconstruir mem con DATA modificada
    mem = list(base_mem)
    for i, c in enumerate(rotated_data):
        mem[29516 + i] = ord(c)

    # Reconstruir raw: hay que reemplazar DATA por rotated_data
    # Manteniendo los newlines originales
    new_raw = code_region + rotated_data  # sin newlines por ahora (simplificación)
    
    return {
        "family": "B1",
        "params": {"offset": offset},
        "code": code_region,
        "data": rotated_data,
        "mem": mem,
        "sha256_code": hashlib.sha256(code_region.encode('latin1')).hexdigest(),
        "sha256_data": hashlib.sha256(rotated_data.encode('latin1')).hexdigest(),
    }


# ----------- Family B2: XOR -----------

def generate_b2(key=0x40):
    """
    Reemplaza DATA por CODE XOR key.
    Necesita compensación XOR antes de cada out.
    """
    raw, clean, base_mem = load_baseline_mem()
    code_region = clean[:29516]
    data_region = clean[29516:59032]
    
    xor_data = ''.join(chr(ord(c) ^ key) for c in code_region)
    
    mem = list(base_mem)
    for i, c in enumerate(xor_data):
        mem[29516 + i] = ord(c)
    
    new_raw = code_region + xor_data
    
    return {
        "family": "B2",
        "params": {"key": key},
        "code": code_region,
        "data": xor_data,
        "mem": mem,
        "sha256_code": hashlib.sha256(code_region.encode('latin1')).hexdigest(),
        "sha256_data": hashlib.sha256(xor_data.encode('latin1')).hexdigest(),
    }


# ----------- Family B3: bytes complement -----------

def generate_b3(mask=0x7F):
    """
    Reemplaza DATA por CODE con máscara AND.
    """
    raw, clean, base_mem = load_baseline_mem()
    code_region = clean[:29516]
    
    masked_data = ''.join(chr(ord(c) & mask) for c in code_region)
    
    mem = list(base_mem)
    for i, c in enumerate(masked_data):
        mem[29516 + i] = ord(c)
    
    return {
        "family": "B3",
        "params": {"mask": mask},
        "code": code_region,
        "data": masked_data,
        "mem": mem,
    }


# ----------- Family B4: reducción circular (trozo + repetición) -----------

def generate_b4(chunk_size=1024):
    """
    DATA consta de un chunk_size bytes significativos + repetición.
    Permite demostrar que no necesitamos 29516 bytes únicos en DATA.
    """
    raw, clean, base_mem = load_baseline_mem()
    code_region = clean[:29516]
    
    # Tomar un chunk aleatorio de CODE como semilla
    seed = code_region[:chunk_size]
    
    # DATA = seed * (29516 // chunk_size) + seed[:29516 % chunk_size]
    repeats = 29516 // chunk_size
    remainder = 29516 % chunk_size
    data_reconstructed = (seed * repeats) + seed[:remainder]
    
    mem = list(base_mem)
    for i, c in enumerate(data_reconstructed):
        mem[29516 + i] = ord(c)
    
    # RAW = code + compact_data
    new_raw = code_region + data_reconstructed
    
    return {
        "family": "B4",
        "params": {"chunk_size": chunk_size, "seed": seed},
        "code": code_region,
        "data": data_reconstructed,
        "mem": mem,
        "sha256_code": hashlib.sha256(code_region.encode('latin1')).hexdigest(),
        "sha256_data": hashlib.sha256(data_reconstructed.encode('latin1')).hexdigest(),
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--family', choices=['B1', 'B2', 'B3', 'B4'], required=True)
    parser.add_argument('--offset', type=int, default=0)
    parser.add_argument('--key', type=int, default=0x40)
    parser.add_argument('--mask', type=int, default=0x7F)
    parser.add_argument('--chunk-size', type=int, default=1024)
    parser.add_argument('--save', action='store_true', help='Save generated candidate')
    parser.add_argument('--verify', action='store_true', help='Verify quine property')
    args = parser.parse_args()
    
    gen = None
    if args.family == 'B1':
        gen = generate_b1(args.offset)
    elif args.family == 'B2':
        gen = generate_b2(args.key)
    elif args.family == 'B3':
        gen = generate_b3(args.mask)
    elif args.family == 'B4':
        gen = generate_b4(args.chunk_size)
    
    if gen is None:
        sys.exit(1)
    
    outdir = 'quine_research/generated'
    os.makedirs(outdir, exist_ok=True)
    fname = f'candidate_{gen["family"]}.mal'
    fpath = os.path.join(outdir, fname)
    with open(fpath, 'w', encoding='latin1') as f:
        f.write(gen['code'] + '\n' + gen['data'] + '\n')
    
    print(f"[*] Generated {fname}")
    print(f"[*] Code SHA256:  {gen.get('sha256_code', 'N/A')}")
    print(f"[*] Data SHA256: {gen.get('sha256_data', 'N/A')}")
    print(f"[*] Raw size: {os.path.getsize(fpath)}")
    
    if args.save:
        print(f"[*] Saved to {fpath}")
    
    if args.verify:
        print("[!] Verify not yet implemented -- use loop_analyzer.py")
        print("[!] Full verification requires matching output to source")