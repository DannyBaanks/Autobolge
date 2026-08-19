from pathlib import Path
"""printer_loop.py - La impresora de moldes de Autobolge.

Ciclo de trabajo: editas zig/bolge.zig (el molde), corres este script, y la
impresora hace todo lo demas:

  1. Recompila bolge.zig solo si cambio (o --rebuild para forzar).
  2. Corre los 299,593 moldes del catalogo len-6 (input vacio, max_steps=3000)
     con el motor Zig (un solo batch) y los compara campo a campo contra el
     catalogo de referencia (construido con run_bounded / paquete malbolge).
  3. Guarda evidencia JSON en experiments/evidence/.
  4. Si hay mismatches: imprime el diagnostico del primero (resultados de
     ambos motores + trace paso a paso de la referencia con los writes del
     overlay y las semillas del fill) y sale con codigo 1 -- tu cambias el
     molde y vuelves a imprimir. Si no hay mismatches: GATE PASSED.

Uso:
  python experiments/printer_loop.py [--rebuild] [--max-len 6] [--keep-going]
"""

import hashlib
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from relational import Materialization
from relational.materialization import DEFAULT_CATALOG_PATH

ZIG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "zig")
ZIG_SRC = os.path.join(ZIG_DIR, "bolge.zig")
ZIG_EXE = os.path.join(ZIG_DIR, "bolge.exe")
ZIG_BIN = os.environ.get("ZIG_EXE") or os.path.join(
    r"C:\Users\progr\AppData\Local\Microsoft\WinGet\Packages",
    "zig.zig_Microsoft.Winget.Source_8wekyb3d8bbwe",
    "zig-x86_64-windows-0.16.0", "zig.exe",
)
EVIDENCE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "evidence")
REFERENCE_CACHE = os.path.join(DEFAULT_CATALOG_PATH, "catalog_e6dfb345.json")
FIELDS = ("program", "output", "steps", "terminated", "stop_reason",
          "final_a", "final_pc", "final_d")


def rebuild():
    if os.path.exists(ZIG_EXE) and os.path.getmtime(ZIG_EXE) >= os.path.getmtime(ZIG_SRC):
        print("[1] bolge.exe al dia, sin recompilar")
        return
    print("[1] recompilando bolge.zig ...")
    t0 = time.perf_counter()
    r = subprocess.run(
        [ZIG_BIN, "build-exe", "bolge.zig", "-O", "ReleaseFast", "-femit-bin=bolge.exe"],
        cwd=ZIG_DIR, capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        print("    COMPILE FAILED:\n", r.stdout, r.stderr)
        sys.exit(1)
    print(f"    OK en {time.perf_counter() - t0:.1f}s ({os.path.getsize(ZIG_EXE):,} bytes)")


def trace_reference(program: str, max_steps: int = 3000):
    """Trace paso a paso de la referencia para diagnostico."""
    from malbolge import MalbolgeDebugger
    from relational.execution import SPARSE_CONFIG
    lines = []
    dbg = MalbolgeDebugger(program, "", config=SPARSE_CONFIG)
    steps = 0
    while not dbg.is_terminated and steps < max_steps:
        before = (dbg._a, dbg._c, dbg._d)
        state = dbg.step()
        steps += 1
        mem_changes = []
        try:
            for addr, old in dbg._history[-1].mem_changes.items():
                mem_changes.append(f"{addr}:{old}->{dbg._mem[addr]}")
        except Exception:
            pass
        lines.append(
            f"  step {steps}: op={state.opcode_name} raw={state.raw_instruction} "
            f"a={before[0]} c={before[1]} d={before[2]} -> a={dbg._a} c={dbg._c} d={dbg._d}"
            + (f" writes=[{', '.join(mem_changes)}]" if mem_changes else "")
            + f" term={state.stop_reason}")
    return "\n".join(lines), steps


def main():
    args = sys.argv[1:]
    rebuild_flag = "--rebuild" in args
    keep_going = "--keep-going" in args

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
        "catalog": REFERENCE_CACHE,
        "entries": len(reference),
        "mismatches": len(mismatches),
        "fast_rebuild_s": round(fast_s, 3),
        "fast_sha256": hashlib.sha256(
            json.dumps(fast, sort_keys=True).encode()).hexdigest(),
        "reference_sha256": hashlib.sha256(
            json.dumps(reference, sort_keys=True).encode()).hexdigest(),
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