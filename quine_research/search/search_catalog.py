"""
search_catalog.py - Catálogo de familias y parámetros para la búsqueda estructurada
de quines de Malbolge.

Registra:
  - FAMILIES: nombres, restricciones, parametros
  - SEARCH_PATTERNS: patrones de búsqueda por familia
  - CANDIDATE_IDS: identificadores únicos de candidatos generados

Uso:
    from search_catalog import FAMILIES, register_candidate
"""

import hashlib

FAMILIES = {
    'A': {
        'name': 'Baseline (CODE == DATA)',
        'type': 'baseline',
        'params': [],
        'size_reduction': 1.0,   # no reduce tamaño
        'halt_proof_difficulty': 'easy',
        'typical_step_multiplier': 1.0,
        'restrictions': ['R1', 'R2', 'R3', 'QUI_NE', 'HALT'],
    },
    'B': {
        'name': 'Reconstrucción (CODE → DATA transformada)',
        'type': 'transform',
        'params': ['transform_type', 'key/seed'],
        'size_reduction': 0.8,  # potencial reducción si se puede codificar transformación en 1-2 llamadas
        'halt_proof_difficulty': 'medium',
        'typical_step_multiplier': 1.2,
        'restrictions': ['R2', 'R3', 'QUI_NE', 'HALT'],
    },
    'C': {
        'name': 'Generación parcial (boot + seed)',
        'type': 'generative',
        'params': ['split_point', 'generation_fcn'],
        'size_reduction': 0.5,  # potencial
        'halt_proof_difficulty': 'hard',
        'typical_step_multiplier': 1.5,
        'restrictions': ['QUI_NE', 'HALT'],
    },
    'D': {
        'name': 'Memoria derivada (crz/rotr en runtime)',
        'type': 'derived',
        'params': ['prefix_size', 'derivation_fcn'],
        'size_reduction': 0.7,
        'halt_proof_difficulty': 'medium',
        'typical_step_multiplier': 1.3,
        'restrictions': ['R2', 'R3', 'QUI_NE', 'HALT'],
    },
    'E': {
        'name': 'Output indirecto (uso de in)',
        'type': 'io_indirect',
        'params': ['in_positions', 'num_in_calls'],
        'size_reduction': 0.3,
        'halt_proof_difficulty': 'medium',
        'typical_step_multiplier': 1.4,
        'restrictions': ['QUI_NE', 'HALT'],
    },
}

CANDIDATE_REGISTRY = []

def candidate_id(family, params_dict):
    sha = hashlib.sha256()
    sha.update(family.encode())
    for k in sorted(params_dict.keys()):
        sha.update(f"{k}={params_dict[k]}".encode())
    return f"Q_{family}_{sha.hexdigest()[:12]}"

def register_candidate(family, params_dict, raw_source, extra=None):
    cid = candidate_id(family, params_dict)
    entry = {
        'id': cid,
        'family': family,
        'params': params_dict,
        'raw_source': raw_source,
        'raw_size': len(raw_source),
        'extra': extra or {},
    }
    CANDIDATE_REGISTRY.append(entry)
    return cid

def get_registered(family=None):
    if family is None:
        return CANDIDATE_REGISTRY
    return [c for c in CANDIDATE_REGISTRY if c['family'] == family]

def list_families():
    for fid, info in FAMILIES.items():
        print(f"  {fid}: {info['name']}  (type={info['type']}, params={info['params']})")

if __name__ == '__main__':
    print("Registered families:")
    list_families()