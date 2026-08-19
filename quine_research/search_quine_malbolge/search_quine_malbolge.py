"""
search_quine_malbolge.py — SEARCHQUINELANG para Malbolge (clásico).
Arquitectura: Pipeline de filtros incrementales.
Motor de ejecución: Zig batch (bolge.exe) via zig_batch.py
"""

import sys, os, hashlib, json, time, collections, itertools, argparse
from typing import Optional, Dict, List, Tuple

# ──────────────────────────────────────────────────────────────
# Semántica Malbolge (autoridad: pipeline.py / quine_tracer.py)
# Esta es la VM Python de referencia. NO MODIFICAR.
# ──────────────────────────────────────────────────────────────
ENCRYPT = "5z]&gqtyfr$(we4{WP)H-Zn,[%\\3dL+Q;>U!pJS72FhOA1CB6v^=I_0/8|jsb9m<.TVac`uY*MK'X~xDl}REokN:#?G\"i@"
CRAZY_TBL = [[1,0,0],[1,0,2],[2,2,1]]
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

# ──────────────────────────────────────────────────────────────
# Zig batch interface (ver zig_batch.py)
# Motor de ejecución preferido (~144x más rápido que Python inline).
# ──────────────────────────────────────────────────────────────
from zig_batch import prepare_batch, run_batch as run_zig_batch, program_to_cells

# ──────────────────────────────────────────────────────────────
# Serialización canónica de candidato
# ──────────────────────────────────────────────────────────────
def encode_candidate(program: str, input_data: str = "") -> str:
    return program + "\n" + input_data + "\n"

def source_len(program: str, input_data: str = "") -> int:
    return len(program) + len(input_data) + 2

# ──────────────────────────────────────────────────────────────
# Candidate + ExecutionResult
# ──────────────────────────────────────────────────────────────
class Candidate:
    __slots__ = ('program', 'input_data', 'source')
    def __init__(self, program: str, input_data: str = ""):
        self.program = program
        self.input_data = input_data
        self.source = encode_candidate(program, input_data)

class ExecutionResult:
    __slots__ = ('candidate', 'output', 'halted', 'steps', 'status', 'tier')
    def __init__(self, candidate, output, halted, steps, status, tier):
        self.candidate = candidate
        self.output = output or ""
        self.halted = halted
        self.steps = steps
        self.status = status
        self.tier = tier

    def survived(self) -> bool:
        return self.status in ('executed', 'budget_exhausted')

# ──────────────────────────────────────────────────────────────
# STAGE 0: EXECUTE (batch Zig)
# ──────────────────────────────────────────────────────────────
TIERS = [100, 1_000, 10_000, 100_000, 1_000_000]

def execute_stage(candidates: List[Candidate], tiers: List[int] = None,
                  bolge_path: str = "zig/bolge.exe",
                  work_dir: str = ".") -> List[ExecutionResult]:
    """
    Ejecuta candidatos via Zig batch.
    
    Early-exit heuristic (Malbolge-specific):
      - Si un candidato no produce output en el tier más bajo,
        se descarta como 'non_productive'.
      - Esto elimina NOP-loops sin gastar presupuesto alto.
    
    Survived: status='executed' (terminó) o 'budget_exhausted' (sin output, pero corrió).
    """
    if tiers is None:
        tiers = TIERS

    results = []

    # Tier 0: ejecutar todo el batch
    tier_budget = tiers[0] if tiers else 100
    batch = prepare_batch(candidates, max_steps=tier_budget)
    raw_results = run_zig_batch(batch, bolge_path=bolge_path, work_dir=work_dir)

    for i, rr in enumerate(raw_results):
        cand = candidates[i] if i < len(candidates) else Candidate("", "")
        output = rr.get('output', '')
        steps = rr.get('steps', 0)
        terminated = rr.get('terminated', False)

        # Zig autoridad: halted = terminated (cualquier terminación cuenta)
        halted = terminated
        status = 'executed' if terminated else 'budget_exhausted'

        # Early-exit: si no produjo output en Tier 0, descartar
        if not terminated and len(output) == 0:
            status = 'non_productive'
            results.append(ExecutionResult(cand, output, halted, steps, status, tier=0))
            continue

        results.append(ExecutionResult(cand, output, halted, steps, status, tier=0))

    return results

# ──────────────────────────────────────────────────────────────
# STAGE 1: HALT
# ──────────────────────────────────────────────────────────────
def halt_stage(results: List[ExecutionResult]) -> List[ExecutionResult]:
    """S2 = candidatos que alcanzaron estado halt (terminated=True)."""
    return [r for r in results if r.halted]

# ──────────────────────────────────────────────────────────────
# STAGE 2: OUTPUT
# ──────────────────────────────────────────────────────────────
def output_stage(results: List[ExecutionResult]) -> List[ExecutionResult]:
    """S3 = candidatos halted con output no vacío."""
    return [r for r in results if len(r.output) > 0]

# ──────────────────────────────────────────────────────────────
# STAGE 3: PREFIX
# ──────────────────────────────────────────────────────────────
def _common_prefix_len(a: str, b: str) -> int:
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n

def prefix_stage(results: List[ExecutionResult]) -> List[Dict]:
    """Calcula prefix_length y prefix_ratio. No filtra."""
    enriched = []
    for r in results:
        prefix = _common_prefix_len(r.output, r.candidate.source)
        ratio = prefix / max(1, len(r.candidate.source))
        enriched.append({
            'candidate': r.candidate,
            'result': r,
            'prefix_length': prefix,
            'prefix_ratio': ratio,
            'output_length': len(r.output),
            'source_length': len(r.candidate.source),
        })
    enriched.sort(key=lambda x: (-x['prefix_length'], -int(x['result'].halted), x['result'].steps))
    return enriched

# ──────────────────────────────────────────────────────────────
# STAGE 4: EXACT
# ──────────────────────────────────────────────────────────────
def exact_stage(ranked: List[Dict]) -> List[Dict]:
    """S5 = candidatos con output == source AND halted == true."""
    return [r for r in ranked
            if r['result'].halted and r['result'].output == r['candidate'].source]

# ──────────────────────────────────────────────────────────────
# PIPELINE
# ──────────────────────────────────────────────────────────────
def run_pipeline(candidates: List[Candidate], tiers: List[int] = None,
                 verbose: bool = True) -> Dict:
    t0 = time.time()
    stats = {}

    stats['S0_count'] = len(candidates)

    # S1: EXECUTE
    s1_all = execute_stage(candidates, tiers=tiers)
    s1 = [r for r in s1_all if r.survived()]
    stats['S1_all_count'] = len(s1_all)
    stats['S1_count'] = len(s1)
    stats['S1_reduction'] = 1.0 - len(s1) / max(1, stats['S0_count'])
    stats['S1_elapsed'] = time.time() - t0
    stats['S1_candidates_per_sec'] = len(s1) / max(0.001, stats['S1_elapsed'])
    stats['S1_status_dist'] = dict(collections.Counter(r.status for r in s1_all))

    # S2: HALT
    t1 = time.time()
    s2 = halt_stage(s1)
    stats['S2_count'] = len(s2)
    stats['S2_reduction'] = 1.0 - len(s2) / max(1, len(s1))
    stats['S2_elapsed'] = time.time() - t1

    # S3: OUTPUT
    t2 = time.time()
    s3 = output_stage(s2)
    stats['S3_count'] = len(s3)
    stats['S3_reduction'] = 1.0 - len(s3) / max(1, len(s2))
    stats['S3_elapsed'] = time.time() - t2

    # S4: PREFIX
    t3 = time.time()
    s4 = prefix_stage(s3)
    stats['S4_count'] = len(s4)
    stats['S4_reduction'] = 1.0 - len(s4) / max(1, len(s3))
    stats['S4_elapsed'] = time.time() - t3
    stats['S4_best_prefix'] = s4[0]['prefix_length'] if s4 else 0
    stats['S4_best_prefix_ratio'] = s4[0]['prefix_ratio'] if s4 else 0.0

    # S5: EXACT
    t4 = time.time()
    s5 = exact_stage(s4)
    stats['S5_count'] = len(s5)
    stats['S5_reduction'] = 1.0 - len(s5) / max(1, len(s4))
    stats['S5_elapsed'] = time.time() - t4
    stats['S5_quines'] = [{
        'program': r['candidate'].program,
        'input': r['candidate'].input_data,
        'output': r['result'].output,
        'steps': r['result'].steps,
        'source': r['candidate'].source,
    } for r in s5]

    stats['total_elapsed'] = time.time() - t0
    stats['candidates_per_sec'] = stats['S0_count'] / max(0.001, stats['total_elapsed'])

    if verbose:
        print("=" * 60)
        print("PIPELINE RESULTS (Zig batch backend)")
        print("=" * 60)
        print(f"S0 in:              {stats['S0_count']:>10,}")
        print(f"S1 EXECUTE:         {stats['S1_count']:>10,}  ({stats['S1_reduction']*100:.1f}% reduction)")
        print(f"S2 HALT:            {stats['S2_count']:>10,}  ({stats['S2_reduction']*100:.1f}%)")
        print(f"S3 OUTPUT:          {stats['S3_count']:>10,}  ({stats['S3_reduction']*100:.1f}%)")
        print(f"S4 PREFIX:          {stats['S4_count']:>10,}  (best_prefix={stats['S4_best_prefix']})")
        print(f"S5 EXACT quines:    {stats['S5_count']:>10,}")
        print(f"Total:              {stats['total_elapsed']:.2f}s | {stats['candidates_per_sec']:>10.1f} cand/s")
        print(f"Status dist:        {stats['S1_status_dist']}")
        print("=" * 60)

    return stats

# ──────────────────────────────────────────────────────────────
# Candidate Generation
# ──────────────────────────────────────────────────────────────
def generate_candidates(mode="both", max_program_length=1, max_input_length=1,
                       alphabet=None, limit=None) -> List[Candidate]:
    if alphabet is None:
        alphabet = [chr(c) for c in range(33, 127)]
    candidates = []
    count = 0

    if mode in ("program", "both"):
        for l in range(0, max_program_length + 1):
            for p in itertools.product(alphabet, repeat=l):
                candidates.append(Candidate(''.join(p), ""))
                count += 1
                if limit and count >= limit:
                    return candidates

    if mode in ("input", "both"):
        for l in range(0, max_input_length + 1):
            for inp in itertools.product(alphabet, repeat=l):
                inp_str = ''.join(inp)
                if mode == "input":
                    candidates.append(Candidate("", inp_str))
                else:
                    candidates.append(Candidate("", inp_str))
                count += 1
                if limit and count >= limit:
                    return candidates

    return candidates

# ──────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────
def cli_main():
    parser = argparse.ArgumentParser(description="SEARCHQUINELANG-MALBOLGE pipeline")
    parser.add_argument("action", choices=["search", "bench", "help"])
    parser.add_argument("--mode", default="both", choices=["program","input","both"])
    parser.add_argument("--program-length", type=int, default=1)
    parser.add_argument("--input-length", type=int, default=1)
    parser.add_argument("--max-steps", type=int, default=100_000)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if args.action == "help":
        print("Pipeline: EXECUTE→HALT→OUTPUT→PREFIX→EXACT")
        print(f"Tiers: {TIERS}")
        return

    config = {"mode": args.mode, "program_length": args.program_length,
              "input_length": args.input_length, "max_steps": args.max_steps}

    t0 = time.time()
    candidates = generate_candidates(args.mode, args.program_length, args.input_length, limit=args.limit)
    gen_time = time.time() - t0
    print(f"Generated {len(candidates):,} in {gen_time:.2f}s")

    stats = run_pipeline(candidates, verbose=args.verbose)

    evidence = {
        "search_type": "quine", "method": "pipeline", "mode": args.mode,
        "config": config, "stats": stats, "engine_version": "0.3.0-zig-batch",
    }
    out_dir = "quine_research/search_quine_malbolge/results"
    os.makedirs(out_dir, exist_ok=True)
    fpath = os.path.join(out_dir, f"pipeline_{time.strftime('%Y%m%d_%H%M%S')}.json")
    with open(fpath, 'w', encoding='utf-8') as f:
        json.dump(evidence, f, indent=2, ensure_ascii=False)
    print(f"Evidence: {fpath}")

if __name__ == '__main__':
    cli_main()