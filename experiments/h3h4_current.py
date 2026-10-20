"""Re-run H3 (memoization) and H4 (parallelization) under current semantic_epoch.

H3: Re-run memoized solver on 676 AA-ZZ targets, measure cache hits + timing.
H4: Re-run solver with 1/2/4 workers on 676 targets, measure speedup.
"""
import json
import time
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "quine_research" / "search_quine_malbolge"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from quine_research.dataflow.stages import _python_execute


def gen_targets():
    return [chr(a) + chr(b)
            for a in range(ord('A'), ord('Z') + 1)
            for b in range(ord('A'), ord('Z') + 1)]


def run_h3():
    from translator_hybrid import TranslatorCandidateFactory
    targets = gen_targets()
    print(f"H3: {len(targets)} targets, memoized search")

    t0 = time.time()
    factory = TranslatorCandidateFactory(max_search_depth=5)
    # La firma batch(shared_state_cache=...) se acepta por compatibilidad
    # pero la API actual del toolkit (generate_for_string(target, *, config))
    # eliminó el kwarg: la memoización cross-target H3 quedó obsoleta.
    cands = factory.batch(targets, shared_state_cache={})
    elapsed = time.time() - t0

    matched = sum(1 for c in cands if "program_source" in c)
    cache_hits = sum(c.get("cache_hits", 0) for c in cands)
    states_revisited = sum(c.get("states_revisited", 0) for c in cands)

    print(f"  matched: {matched}/{len(targets)}")
    print(f"  cache_hits: {cache_hits}")
    print(f"  states_revisited: {states_revisited}")
    print(f"  elapsed: {elapsed:.1f}s ({len(targets)/elapsed:.1f} targets/s)")

    per_target = []
    for c in cands:
        per_target.append({
            "target": c["target"],
            "nodes_expanded": c.get("nodes_expanded", 0),
            "states_revisited": c.get("states_revisited", 0),
            "cache_hits": c.get("cache_hits", 0),
            "solution_length": c.get("solution_length", 0),
            "generation_ms": round(c.get("generation_ms", 0.0), 3),
            "evaluations": c.get("evaluations", 0),
            "verified": "program_source" in c,
        })

    return {
        "hypothesis": "H3 memoization",
        "config": {"targets": len(targets), "max_search_depth": 5},
        "mode": "no_memo_api",
        "gen_time_s": round(elapsed, 2),
        "matched": f"{matched}/{len(targets)}",
        "total_cache_hits": cache_hits,
        "total_states_revisited": states_revisited,
        "per_target": per_target,
        "_meta": {
            "stage_id": "h3_current",
            "semantic_epoch": "autobolge-classic-dense-input-underflow/v1",
            "label": "CURRENT",
            "status": "ok",
            "toolkit": "malbolge-generator 0.1.0 / malbolge 1.0.0 (PyPI malbolge-generator, GitHub wallstop/MalbolgeGenerator)",
            "api_note": "generate_for_string(target, *, config) sin shared_state_cache; hipotesis de memoizacion cross-target obsoleta en esta API",
        },
    }


def run_h4():
    from translator_hybrid import TranslatorCandidateFactory, generate_chunk_worker
    import math
    from concurrent.futures import ProcessPoolExecutor

    targets = gen_targets()
    items = list(enumerate(targets))
    print(f"H4: {len(targets)} targets, parallelization sweep")

    results = {}
    for workers in [1, 2, 4]:
        print(f"  workers={workers}...")
        t0 = time.time()
        if workers == 1:
            factory = TranslatorCandidateFactory(max_search_depth=5)
            cands = factory.batch(targets)
        else:
            chunk_size = math.ceil(len(items) / (workers * 4))
            chunks = [items[i:i + chunk_size] for i in range(0, len(items), chunk_size)]
            with ProcessPoolExecutor(max_workers=workers) as pool:
                cands = []
                for chunk_out in pool.map(generate_chunk_worker, [(c, 5) for c in chunks]):
                    cands.extend(chunk_out)
            cands.sort(key=lambda c: c.get("_index", 0))

        elapsed = time.time() - t0
        matched = sum(1 for c in cands if "program_source" in c)
        # Verify determinism: programs should be identical across runs
        programs = {c["target"]: c.get("program_source", "") for c in cands if "program_source" in c}

        results[workers] = {
            "workers": f"{workers}" if workers > 1 else "1 (serial)",
            "gen_time_s": round(elapsed, 2),
            "targets_per_s": round(len(targets) / elapsed, 1),
            "matched": f"{matched}/{len(targets)}",
        }
        print(f"    {matched}/{len(targets)} matched, {elapsed:.1f}s")

    # Cross-check determinism: compare serial vs parallel programs
    serial = {}
    for w in [1]:
        r = results[w]
        # Re-run serial to get programs
        factory = TranslatorCandidateFactory(max_search_depth=5)
        cands = factory.batch(targets)
        serial = {c["target"]: c.get("program_source", "") for c in cands if "program_source" in c}

    mismatches = 0
    for w in [2, 4]:
        # Re-run to compare programs
        chunk_size = math.ceil(len(items) / (w * 4))
        chunks = [items[i:i + chunk_size] for i in range(0, len(items), chunk_size)]
        with ProcessPoolExecutor(max_workers=w) as pool:
            cands = []
            for chunk_out in pool.map(generate_chunk_worker, [(c, 5) for c in chunks]):
                cands.extend(chunk_out)
        cands.sort(key=lambda c: c.get("_index", 0))
        par = {c["target"]: c.get("program_source", "") for c in cands if "program_source" in c}
        for t in serial:
            if t in par and serial[t] != par[t]:
                mismatches += 1

    verdict = "SUPPORTED" if mismatches == 0 else f"FAILED: {mismatches} mismatches"

    return {
        "hypothesis": "H4 parallelization by target",
        "config": {"targets": len(targets), "seed": 42, "max_search_depth": 5},
        "runs": list(results.values()),
        "determinism_mismatches": mismatches,
        "verdict": verdict,
        "_meta": {
            "stage_id": "h4_current",
            "semantic_epoch": "autobolge-classic-dense-input-underflow/v1",
            "label": "CURRENT",
            "status": "ok",
        },
    }


if __name__ == "__main__":
    # Run H3
    h3 = run_h3()
    out = Path("runs/h3_memo_current")
    out.mkdir(parents=True, exist_ok=True)
    (out / "artifact.json").write_text(json.dumps(h3, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  saved: {out / 'artifact.json'}\n")

    # Run H4
    h4 = run_h4()
    out = Path("runs/h4_parallel_current")
    out.mkdir(parents=True, exist_ok=True)
    (out / "artifact.json").write_text(json.dumps(h4, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  saved: {out / 'artifact.json'}")
