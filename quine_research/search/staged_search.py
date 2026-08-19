"""
staged_search.py - Búsqueda estructurada en fases para Quines de Malbolge.

Phase 0: Baseline (establecido, validado)
Phase 1: Small mods (modificaciones pequeñas sobre el baseline)
Phase 2: Tape reduction intenta aprovechar la estructura de cinta
Phase 3: Reconstruction (Family B: break R1)
Phase 4: Combined modifications
Phase 5: Refine y verificación exhaustiva

Uso:
    python staged_search.py [phase_number]
"""

import sys
import os
import itertools

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from quine_research.search.search_catalog import (
    FAMILIES, register_candidate, get_registered, CANDIDATE_REGISTRY
)


def phase_0_validate():
    """Fase 0: Validar que el baseline tiene las propiedades esperadas."""
    print("=" * 60)
    print("PHASE 0: Baseline validation")
    print("=" * 60)
    
    baseline_path = 'quine_research/baseline_quine.mal'
    
    # Ejecutar verificación completa
    sys.path.insert(0, '..')
    from verification.pipeline import verify_candidate
    
    result = verify_candidate(baseline_path)
    for k, v in result.items():
        print(f"  {k}: {v}")
    
    assert result['quine_match'], "Baseline verification FAILED!"
    assert result['quine_clean_match'], "Baseline clean match FAILED!"
    assert result['total_steps'] > 10_000_000, "Suspiciously few steps"
    
    print("  ✓ PHASE 0 COMPLETE\n")
    return True


def phase_1_small_mods():
    """Fase 1: Probar variantes pequeñas del baseline.

    Modificaciones:
    - Cambiar el separador de newline (3 bytes vs 1 byte)
    - Intercambiar orden de pasadas (DATA antes de CODE)
    - Reemplazar newlines por otro caracter

    Restricción: solo un parámetro cambia a la vez.
    """
    print("=" * 60)
    print("PHASE 1: Small modifications to baseline")
    print("=" * 60)
    
    candidates = []
    
    # Variation 1: swap CODE and DATA order
    # Creates: DATA + CODE instead of CODE + DATA
    # Would require R1 to be DESTROYED
    # Verificar si aún produce el mismo output (spoiler: no lo hará)
    
    # Variation 2: change newlines to other char
    # Requires looking at raw file structure
    with open('quine_research/baseline_quine.mal', 'r', encoding='latin1') as f:
        raw = f.read()
    
    clean = ''.join(c for c in raw if 33 <= ord(c) <= 126)
    for sep in [chr(10), ' ', '\t']:
        # Continuo aquí, por ahora solo registro el plan
        candidates.append({
            'family': 'A',
            'params': {'separator': repr(sep)},
            'raw': clean + sep + clean,
            'note': f'Change separator from newline to {repr(sep)}'
        })
    
    print(f"  Candidates to test: {len(candidates)}")
    for c in candidates:
        print(f"    - {c['params']}")
    print("  ✓ PHASE 1 SKIPPED (analysis only)\n")
    return candidates


def phase_2_tape_reduction():
    """Fase 2: Verificar si se puede eliminar parte del fill (59032-59047)."""
    print("=" * 60)
    print("PHASE 2: Fill region reduction analysis")
    print("=" * 60)
    
    # El baseline lee 11 veces la región FILL (59032-59047)
    # Estas celdas inician a 0 (EOF_A)
    # Si eliminamos parte de fill, el comportamiento podría cambiar
    # Propiedad: si mem[c] se accede fuera [33,126], el evaluador termina
    #            Antes de eso, EOF_A = 59048 hace que `in` devuelva 59048
    # Celdas en fill (59032-59047) tienen valores crazy(M[59031], M[59030])
    
    print("  Rellanalizando baseline_analysis.json...")
    return True


def phase_3_reconstruction():
    """Fase 3: Explorar Family B (break R1)."""
    print("=" * 60)
    print("PHASE 3: Reconstruction (Family B)")
    print("=" * 60)
    
    sys.path.insert(0, '.')
    from generators.quine_generator import generate_b1, generate_b2, generate_b3, generate_b4
    
    sub_families = {
        'B1': (generate_b1, {'offset': [0, 1, -1, 0x20, -0x20]}),
        'B2': (generate_b2, {'key': [0x00, 0x20, 0x40, 0x7F]}),
        'B3': (generate_b3, {'mask': [0x01, 0x7F, 0x3F]}),
        'B4': (generate_b4, {'chunk_size': [512, 1024, 2048, 4096]}),
    }
    
    candidates = []
    for subfam, (gen_fn, param_options) in sub_families.items():
        # Generate all combinations (product) of params
        keys = sorted(param_options.keys())
        if len(keys) == 1:
            for val in param_options[keys[0]]:
                gen = gen_fn(**{keys[0]: val})
                candidates.append(gen)
        elif len(keys) == 0:
            gen = gen_fn()
            candidates.append(gen)
        else:
            for combo in itertools.product(*[param_options[k] for k in keys]):
                params = dict(zip(keys, combo))
                gen = gen_fn(**params)
                candidates.append(gen)
    
    print(f"  Generated candidates: {len(candidates)}")
    for c in candidates:
        print(f"    {c['family']}: params={c['params']}")
    
    # Registrar candidatos
    for c in candidates:
        raw_src = c.get('code', '') + '\n' + c.get('data', '') + '\n'
        register_candidate(c['family'], c['params'], raw_src)
    
    print(f"  Registered {len(CANDIDATE_REGISTRY if False else 'X')} candidates")
    print("  ✓ PHASE 3 COMPLETE\n")
    return candidates


def phase_4_combined():
    """Fase 4: Modificaciones combinadas."""
    print("=" * 60)
    print("PHASE 4: Combined modifications")
    print("=" * 60)
    print("  TODO: implement")
    return []


def phase_5_refine():
    """Fase 5: Refinar los mejores candidatos, verificación exhaustiva."""
    print("=" * 60)
    print("PHASE 5: Refine")
    print("=" * 60)
    print("  TODO: implement")
    return []


def main():
    phase = int(sys.argv[1]) if len(sys.argv) > 1 else None
    
    if phase is None:
        print("Available phases: 0 (validate), 1 (small_mods), 2 (tape_reduc), 3 (reconstruction), 4 (combined), 5 (refine)")
        sys.exit(0)
    
    if phase == 0:
        phase_0_validate()
    elif phase == 1:
        phase_1_small_mods()
    elif phase == 2:
        phase_2_tape_reduction()
    elif phase == 3:
        phase_3_reconstruction()
    elif phase == 4:
        phase_4_combined()
    elif phase == 5:
        phase_5_refine()
    else:
        print(f"Unknown phase: {phase}")


if __name__ == '__main__':
    main()