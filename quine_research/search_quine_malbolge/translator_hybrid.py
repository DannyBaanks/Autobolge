"""
translator_hybrid.py — FUSIÓN: Malbolge-Translator (asistido) + Pipeline Zig (verificación).

Arquitectura:
  ProgramGenerator (translator)  →  opcodes + program_source
              ↓
  MalbolgeInterpreter (translator)  →  output
              ↓
  Nuestro pipeline  →  verificación + evidencia

Filosofía:
  - El translator evita el espacio brutal 94^n
  - Nuestro pipeline mantiene verificación exacta
  - Evidence-first: todo resultado se guarda y verifica
"""
import sys, os, json, time, collections

# ──────────────────────────────────────────────────────────────
# Paths al entorno del translator (no tocamos pip, usamos el venv existente)
# ──────────────────────────────────────────────────────────────
TRANSLATOR_VENV = os.environ.get(
    'TRANSLATOR_VENV',
    os.path.join(os.path.expanduser('~'), '.malbolge_toolkit', '.venv', 'Lib', 'site-packages'),
)
TRANSLATOR_BUILD = os.environ.get(
    'TRANSLATOR_BUILD',
    os.path.join(os.path.expanduser('~'), '.malbolge_toolkit', 'build', 'lib'),
)

if TRANSLATOR_VENV not in sys.path:
    sys.path.insert(0, TRANSLATOR_VENV)
if TRANSLATOR_BUILD not in sys.path:
    sys.path.insert(0, TRANSLATOR_BUILD)

from malbolge import GenerationConfig, ProgramGenerator, MalbolgeInterpreter
from malbolge.encoding import reverse_normalize


# ──────────────────────────────────────────────────────────────
# Candidate Factory (Translator-backed)
# ──────────────────────────────────────────────────────────────
class TranslatorCandidateFactory:
    """
    Genera programas Malbolge que producen targets específicos.
    
    Usa ProgramGenerator del malbolge-generator (traducción asistida).
    Cada candidato tiene:
      - opcodes: ejecutable por MalbolgeInterpreter
      - program_source: printable string (reverse_normalized)
      - target: string que se espera que produzca
    """

    def __init__(self, max_search_depth: int = 5, random_seed: int = 42):
        self.generator = ProgramGenerator()
        self.config = GenerationConfig(
            opcode_choices="op*",
            max_search_depth=max_search_depth,
            random_seed=random_seed,
        )

    def generate(self, target: str, shared_state_cache: dict | None = None) -> dict:
        """Genera un programa que produce `target`. Retorna dict con metadata."""
        result = self.generator.generate_for_string(
            target, shared_state_cache=shared_state_cache
        )
        opcodes = result.opcodes
        program_source = "".join(reverse_normalize(opcodes))
        rstats = result.stats
        
        return {
            "program_source": program_source,
            "opcodes": opcodes,
            "target": target,
            "target_len": len(target),
            "stats": {
                "evaluations": rstats.get("evaluations", 0),
                "cache_hits": rstats.get("cache_hits", 0),
                "pruned": rstats.get("pruned", 0),
                "repeated_state_pruned": rstats.get("repeated_state_pruned", 0),
                "duration_ns": rstats.get("duration_ns", 0),
            }
        }

    def batch(self, targets: list, shared_state_cache: dict | None = None) -> list:
        candidates = []
        for target in targets:
            try:
                c = self.generate(target, shared_state_cache=shared_state_cache)
                candidates.append(c)
            except Exception as e:
                print(f"[WARN] target={target!r}: {e}")
        return candidates


# ──────────────────────────────────────────────────────────────
# Verificación (usa MalbolgeInterpreter del translator)
# ──────────────────────────────────────────────────────────────
class TranslatorVerifier:
    """
    Verifica programas generados por el translator.
    Compara output real vs target esperado.
    """

    def __init__(self, max_steps: int = 5_000_000):
        self.interpreter = MalbolgeInterpreter()
        self.max_steps = max_steps

    def verify(self, program_source: str, opcodes: str, target: str) -> dict:
        """
        Ejecuta `opcodes` y compara output vs `target`.
        
        Nota: se ejecutan los opcodes (formato interno del translator),
        no el printable source. El printable source es para registro/display.
        """
        try:
            result = self.interpreter.execute(
                opcodes,
                max_steps=self.max_steps,
                capture_machine=True
            )
            output = result.output
            halt_reason = result.halt_reason
            steps = result.steps
            
            return {
                "program_source": program_source,
                "opcodes_len": len(opcodes),
                "target": target,
                "output": output,
                "output_len": len(output),
                "steps": steps,
                "halt_reason": halt_reason,
                "match": output == target,
                "target_len": len(target),
                "error": None,
            }
        except Exception as e:
            return {
                "program_source": program_source,
                "opcodes_len": len(opcodes),
                "target": target,
                "output": "",
                "output_len": 0,
                "steps": 0,
                "halt_reason": "error",
                "match": False,
                "target_len": len(target),
                "error": str(e),
            }


# ──────────────────────────────────────────────────────────────
# Pipeline Híbrido
# ──────────────────────────────────────────────────────────────
def run_hybrid(
    targets: list,
    max_search_depth: int = 5,
    max_steps: int = 5_000_000,
) -> dict:
    """
    Pipeline completo: Translator genera → Verifier verifica → Evidencia.
    
    NO usa beam search. NO usa nuestro pipeline Malbolge inline.
    Usa el interpreter nativo del translator para máxima fidelidad.
    """
    t0 = time.time()
    stats = {
        "mode": "hybrid_translator",
        "targets_count": len(targets),
        "max_search_depth": max_search_depth,
        "max_steps": max_steps,
    }

    # Fase 1: Generación asistida
    print(f"[HYBRID] Generating {len(targets)} candidates via translator...")
    factory = TranslatorCandidateFactory(max_search_depth=max_search_depth)
    t1 = time.time()
    raw = factory.batch(targets)
    stats["generation_time_s"] = round(time.time() - t1, 3)
    stats["generated_count"] = len(raw)
    print(f"[HYBRID] Generated {len(raw)}/{len(targets)} in {stats['generation_time_s']}s")

    if not raw:
        stats["status"] = "NO_GENERATION"
        return stats

    # Fase 2: Verificación
    print(f"[HYBRID] Verifying via MalbolgeInterpreter...")
    verifier = TranslatorVerifier(max_steps=max_steps)
    t2 = time.time()

    matched = []
    unmatched = []
    errors = []

    for c in raw:
        r = verifier.verify(c["program_source"], c["opcodes"], c["target"])
        r["program_len"] = len(c["program_source"])
        r["program_source"] = c["program_source"]
        r["opcodes"] = c["opcodes"]

        if r["error"]:
            errors.append(r)
        elif r["match"]:
            matched.append(r)
        else:
            unmatched.append(r)

    stats["verify_time_s"] = round(time.time() - t2, 3)
    stats["matched"] = len(matched)
    stats["unmatched"] = len(unmatched)
    stats["errors"] = len(errors)
    stats["match_rate"] = round(len(matched) / max(1, len(raw)), 4)
    stats["total_time_s"] = round(time.time() - t0, 3)
    stats["candidates_per_sec"] = round(len(raw) / max(0.001, stats["total_time_s"]), 1)
    stats["status"] = "COMPLETE"

    # Reporte
    print(f"[HYBRID] Matched: {len(matched)} | Unmatched: {len(unmatched)} | Errors: {len(errors)}")
    print(f"[HYBRID] Match rate: {stats['match_rate']*100:.1f}%")
    print(f"[HYBRID] Total: {stats['total_time_s']}s @ {stats['candidates_per_sec']} cand/s")

    # Evidencia
    evidence = {
        "search_type": "hybrid_translator",
        "stats": stats,
        "best_matched": matched[:10],
        "best_unmatched_by_output_len": sorted(
            unmatched, key=lambda x: (-x["output_len"], -x["steps"])
        )[:10],
    }

    out_dir = "quine_research/search_quine_malbolge/results"
    os.makedirs(out_dir, exist_ok=True)
    fpath = os.path.join(out_dir, f"hybrid_{time.strftime('%Y%m%d_%H%M%S')}.json")
    with open(fpath, 'w', encoding='utf-8') as f:
        json.dump(evidence, f, indent=2, ensure_ascii=False)
    print(f"[HYBRID] Evidence: {fpath}")

    return stats


if __name__ == '__main__':
    targets = ['AB', 'HI', 'XYZ']
    stats = run_hybrid(targets, max_search_depth=5, max_steps=5_000_000)
    print(json.dumps(stats, indent=2, ensure_ascii=False))