from pathlib import Path
"""printer_loop.py - La impresora de moldes de Autobolge.

Ciclo de trabajo: editas zig/bolge.zig (el molde), corres este script, y la
impresora hace todo lo demas:

  1. Recompila bolge.zig solo si cambio (o --rebuild para forzar).
  2. Corre los 299,593 moldes del catalogo len-6 (input vacio, max_steps=3000)
     con el motor Zig (un solo batch) y los compara campo a campo contra el
     catalogo de referencia (construido con run_bounded / referencia Classic
     densa anclada en la toolkit malbolge).

     IMPORTANTE (2026-09): la cache (catalog_e6dfb345.json) fue regenerada con
     la SEMANTICA ACTUAL (referencia Classic densa anclada en la toolkit
     malbolge; tail-shared, ~152s el len-6 completo). Si vuelve a cambiar la
     semantica del molde, regenere primero el catalogo
     (build_catalog(engine="reference") + guardar en experiments/catalog_cache);
     este gate fallara por diseno hasta que la cache y el molde cuadren.
     No alterar la comparacion para que "pase".
  3. Guarda evidencia JSON en experiments/evidence/.
  4. Si hay mismatches: imprime el diagnostico del primero (resultados de
     ambos motores + trace paso a paso de la referencia: maquina Classic
     densa) y sale con codigo 1 -- tu cambias el molde y vuelves a imprimir.
     Si no hay mismatches: GATE PASSED.

Uso:
  python experiments/printer_loop.py [--rebuild] [--max-len 6] [--keep-going]
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from relational import Materialization
from relational.materialization import DEFAULT_CATALOG_PATH
from quine_research.dataflow.semantic_manifest import build_semantic_manifest, manifest_sha256

ZIG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "zig")
ZIG_SRC = os.path.join(ZIG_DIR, "bolge.zig")
ZIG_EXE = os.path.join(ZIG_DIR, "bolge.exe")
ZIG_BIN = os.environ.get("ZIG_EXE") or shutil.which("zig")
EVIDENCE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "evidence")
REFERENCE_CACHE = os.path.join(DEFAULT_CATALOG_PATH, "catalog_e6dfb345.json")
REFERENCE_CACHE_LOGICAL = "experiments/catalog_cache/catalog_e6dfb345.json"
FIELDS = ("program", "output", "steps", "terminated", "stop_reason",
          "final_a", "final_pc", "final_d")


def rebuild():
    semantic_sources = [ZIG_SRC, os.path.join(ZIG_DIR, "vm.zig")]
    up_to_date = os.path.exists(ZIG_EXE) and all(
        os.path.getmtime(ZIG_EXE) >= os.path.getmtime(p) for p in semantic_sources
    )
    if up_to_date:
        print("[1] bolge.exe al dia (bolge.zig + vm.zig), sin recompilar")
        return
    print("[1] recompilando bolge.zig ...")
    if not ZIG_BIN:
        print("    ERROR: zig no encontrado. Define la variable de entorno "
              "ZIG_EXE con la ruta a zig.exe o pon `zig` en PATH.")
        sys.exit(1)
    t0 = time.perf_counter()
    r = subprocess.run(
        [ZIG_BIN, "build-exe", "bolge.zig", "-O", "ReleaseFast", "-femit-bin=bolge.exe"],
        cwd=ZIG_DIR, capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        print("    COMPILE FAILED:\n", r.stdout, r.stderr)
        sys.exit(1)
    print(f"    OK en {time.perf_counter() - t0:.1f}s ({os.path.getsize(ZIG_EXE):,} bytes)")


def trace_reference(program: str, max_steps: int = 3000):
    """Trace paso a paso de la referencia (maquina Classic densa)."""
    from relational.classic import ClassicDebugger
    lines = []
    dbg = ClassicDebugger(program, "", max_steps)
    steps = 0
    while not dbg.is_terminated and steps < max_steps:
        before = (dbg.a, dbg.c, dbg.d)
        state = dbg.step()
        steps += 1
        lines.append(
            f"  step {steps}: op={state.opcode_name} raw={state.raw_instruction} "
            f"a={before[0]} c={before[1]} d={before[2]} -> a={dbg.a} c={dbg.c} d={dbg.d}"
            f" term={state.stop_reason}")
    return "\n".join(lines), steps


def main():
    args = sys.argv[1:]
    rebuild_flag = "--rebuild" in args
    keep_going = "--keep-going" in args
    semantic_manifest = build_semantic_manifest()

    rebuild()

    print("[2] cargando catalogo de referencia (run_bounded)")
    with open(REFERENCE_CACHE, "r", encoding="utf-8") as f:
        reference = json.load(f)
    print(f"    {len(reference)} moldes, sha256="
          f"{hashlib.sha256(json.dumps(reference, sort_keys=True).encode()).hexdigest()[:16]}")

    print("[3] imprimiendo moldes con el motor Zig ...")
    mat = Materialization(relations=[], catalog_path=None)
    t0 = time.perf_counter()
    fast = mat.build_catalog(max_len=6, max_steps=3000, input_data="", engine="fast")
    fast_s = time.perf_counter() - t0
    print(f"    {len(fast)} moldes en {fast_s:.2f}s")

    print("[4] comparando campo a campo ...")
    mismatches = []
    for i, (a, b) in enumerate(zip(fast, reference)):
        if a != b:
            mismatches.append((i, a, b))
    print(f"    mismatches: {len(mismatches)} / {len(reference)}")

    os.makedirs(EVIDENCE_DIR, exist_ok=True)
    evidence = {
        "gate": "printer_loop",
        "catalog": REFERENCE_CACHE_LOGICAL,
        "entries": len(reference),
        "mismatches": len(mismatches),
        "fast_rebuild_s": round(fast_s, 3),
        "fast_sha256": hashlib.sha256(
            json.dumps(fast, sort_keys=True).encode()).hexdigest(),
        "reference_sha256": hashlib.sha256(
            json.dumps(reference, sort_keys=True).encode()).hexdigest(),
        "semantic_manifest": semantic_manifest,
        "semantic_manifest_sha256": manifest_sha256(semantic_manifest),
        "mismatch_summary": [
            {"index": i, "program": a["program"],
             "fast": {k: a[k] for k in FIELDS[1:]},
             "reference": {k: b[k] for k in FIELDS[1:]}}
            for i, a, b in mismatches[:10]
        ],
    }
    with open(os.path.join(EVIDENCE_DIR, "printer_loop.json"), "w", encoding="utf-8") as f:
        json.dump(evidence, f, ensure_ascii=False, indent=2)

    if mismatches:
        print("\n[5] DIAGNOSTICO del primer mismatch:")
        idx, fa, rf = mismatches[0]
        print(f"  programa: {rf['program']!r}")
        print(f"  fast:      {json.dumps({k: fa[k] for k in FIELDS[1:]}, ensure_ascii=False)}")
        print(f"  referencia:{json.dumps({k: rf[k] for k in FIELDS[1:]}, ensure_ascii=False)}")
        trace, steps = trace_reference(rf["program"])
        print(f"  trace referencia ({steps} pasos):")
        print(trace)
        print("\n  evidencia parcial en experiments/evidence/printer_loop.json")
        if not keep_going:
            sys.exit(1)
        sys.exit(1)

    print("\nGATE PASSED - los 299,593 moldes salen identicos "
          f"({fast_s:.2f}s con el motor Zig)")


if __name__ == "__main__":
    main()
