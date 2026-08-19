"""
structural_generator.py — Generación estructural de candidatos Malbolge
para buscar OUTPUT_LEN >= 2.

Familias (sin ejecución previa):
  A. MULTI_OUT: >=2 caracteres en OUTPUT_PRONE_CHARS
  B. MODIFY_OUT: >=1 STATE_MODIFIER + >=1 OUTPUT_PRONE
  C. LOOP_SEED: subsecuenciasjmov_d o rotr/crz cerca de out

NO garantiza output_len>=2. Solo aumenta la densidad estructural.
"""
import itertools

# Caracteres que en ALGUNA posición pc podrían decodificar a v=5 (OUT)
# Criterio amplío: cualquier char ASCII imprimible podría ser OUT en alguna posición
OUTPUT_PRONE_CHARS = set(chr(c) for c in range(33, 127))

# Caracteres asociados a modificación de estado (crz, rotr, mov_d, jmp)
# Basado en opcodes Malbolge que alteran A, D, o C
STATE_MODIFIER_CHARS = {
    '4',   # jmp
    '6',   # potential opcodes
    '7', '8', '9',
    ':', ';', '<', '=', '>', '?',
    '@', 'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J',
    'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U',
    'V', 'W', 'X', 'Y', 'Z', '[', '\\', ']', '^', '_', '`',
    'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k',
    'l', 'm', 'n', 'o', 'p', 'q', 'r', 's', 't', 'u', 'v',
    'w', 'x', 'y', 'z', '{', '|', '}', '~'
}

# Subsecuencias estructurales clave (strings que contienen patrones del baseline)
LOOP_PATTERNS = ['54', '45', '46', '64', '65', '56']  # out+jmp, jmp+out, etc.

def gen_multi_out(max_len, alphabet=None, min_out_chars=2):
    """Programas con >= min_out_chars caracteres OUTPUT_PRONE."""
    if alphabet is None:
        alphabet = [chr(c) for c in range(33, 127)]
    out_prone = sorted(OUTPUT_PRONE_CHARS & set(alphabet))
    others = sorted(set(alphabet) - set(out_prone))
    # Garantizar al menos min_out_chars de out_prone
    for positions in itertools.combinations(range(max_len), min_out_chars):
        # Elegir chars para esas posiciones
        for combo in itertools.product(out_prone, repeat=min_out_chars):
            # Rellenar resto con alphabet completo
            rest_positions = [i for i in range(max_len) if i not in positions]
            for rest in itertools.product(alphabet, repeat=len(rest_positions)):
                prog = [''] * max_len
                for pos, ch in zip(positions, combo):
                    prog[pos] = ch
                for pos, ch in zip(rest_positions, rest):
                    prog[pos] = ch
                yield ''.join(prog)

def gen_modify_out(max_len, alphabet=None):
    """Programas con >=1 state modifier y >=1 output-prone."""
    if alphabet is None:
        alphabet = [chr(c) for c in range(33, 127)]
    modifiers = sorted(STATE_MODIFIER_CHARS & set(alphabet))
    out_chars = sorted(OUTPUT_PRONE_CHARS & set(alphabet))
    for m in modifiers:
        for o in out_chars:
            # Colocar m y o en diferentes posiciones
            remaining = [ch for ch in alphabet if ch not in (m, o)]
            for others in itertools.product(remaining, repeat=max(0, max_len-2)):
                prog = [m, o] + list(others)
                yield ''.join(prog[:max_len])

def gen_loop_seed(max_len, alphabet=None):
    """Programas que contienen patrones de loop (jmp/mov_d cerca de out)."""
    if alphabet is None:
        alphabet = [chr(c) for c in range(33, 127)]
    patterns = LOOP_PATTERNS
    for pat in patterns:
        if len(pat) > max_len:
            continue
        # Colocar patrón en posiciones 0..len(pat)-1
        rest_len = max_len - len(pat)
        for rest in itertools.product(alphabet, repeat=rest_len):
            yield pat + ''.join(rest)

def generate_structural(mode='multi_out', max_len=4, max_input_len=1,
                        alphabet=None, limit=None):
    """
    Generador principal. Retorna lista de strings (programas).
    Para modo 'both', también genera variantes de input.
    """
    if alphabet is None:
        alphabet = [chr(c) for c in range(33, 127)]
    
    programs = []
    seen = set()
    count = 0
    
    if mode == 'multi_out':
        gen_fn = lambda: gen_multi_out(max_len, alphabet)
    elif mode == 'modify_out':
        gen_fn = lambda: gen_modify_out(max_len, alphabet)
    elif mode == 'loop_seed':
        gen_fn = lambda: gen_loop_seed(max_len, alphabet)
    elif mode == 'all':
        gens = [
            gen_multi_out(max_len, alphabet),
            gen_modify_out(max_len, alphabet),
            gen_loop_seed(max_len, alphabet),
        ]
        def gen_fn():
            for g in gens:
                yield from g
    else:
        raise ValueError(f"Unknown mode: {mode}")
    
    for prog in gen_fn():
        if prog not in seen:
            seen.add(prog)
            programs.append(prog)
            count += 1
            if limit and count >= limit:
                break
    
    return programs

if __name__ == '__main__':
    # Test: generar algunos candidatos
    for mode in ['multi_out', 'modify_out', 'loop_seed']:
        progs = generate_structural(mode=mode, max_len=4, limit=20)
        print(f"Mode {mode}: {len(progs)} progs")
        for p in progs[:5]:
            print(f"  {p!r}")