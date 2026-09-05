"""Etapas del dataflow Autobolge.

Cada etapa: fn(ctx, params, inputs) -> (contract, summary_lines)
  ctx     : dict con utilidades compartidas (paths de repo)
  params  : dict declarativo desde el pipeline JSON
  inputs  : lista de (stage_id, Contract) resueltos por el engine

Las etapas NO se conocen entre sí; solo hablan contratos. Todo
re-ejecutable pesado (zig) vive detrás de funciones lazy-importadas.
"""
from __future__ import annotations

import itertools
import operator
import time

from .contracts import (
    ClassifierResult,
    CompareResult,
    SearchResult,
    SelectionResult,
    SolverResult,
    TransformResult,
    Verdict,
)

PRINTABLE = [chr(c) for c in range(33, 127)]
MAX_ROWS_IN_ARTIFACT = 50_000  # evidencia completa, pero el artefacto no explota


def _zig_execute(programs: list[str], max_steps: int) -> list[dict]:
    from zig_batch import prepare_batch_from_dicts, run_batch

    results = []
    chunk = 50_000
    for i in range(0, len(programs), chunk):
        sub = [{"program": p, "input_data": "", "max_steps": max_steps}
               for p in programs[i:i + chunk]]
        batch = prepare_batch_from_dicts(sub, max_steps=max_steps)
        for rr in run_batch(batch, bolge_path="zig/bolge.exe", work_dir="."):
            if "error" in rr:
                results.append({"output": "", "steps": 0,
                                "terminated": False, "error": rr["error"]})
            else:
                results.append(rr)
    return results


# ── SEARCH ─────────────────────────────────────────────────────────
def stage_frontier(ctx, params, inputs):
    """FRONTIER(nivel): ejecuta la frontera declarada contra la VM Zig.

    params:
      level     int    nivel de longitud al que se llega
      seeds     [str]  semillas; se extienden exhaustivamente hasta level
      max_steps int    presupuesto VM por candidato
    Si hay inputs (SelectionResult/TransformResult), la frontera son los
    programas recibidos y se ignoran seeds (provenance queda en params).
    """
    level = int(params.get("level", 1))
    seeds = params.get("seeds", [""])
    max_steps = int(params.get("max_steps", 100_000))

    if inputs:
        programs = []
        for _sid, contract in inputs:
            if isinstance(contract, (SelectionResult, TransformResult)):
                programs.extend(contract.selected
                                if isinstance(contract, SelectionResult)
                                else contract.derived)
        exhaustive = False
        source = "upstream"
    else:
        programs = []
        for seed in seeds:
            remaining = level - len(seed)
            if remaining < 0:
                continue
            for comb in itertools.product(PRINTABLE, repeat=remaining):
                programs.append(seed + "".join(comb))
        exhaustive = True
        source = "exhaustive"

    t0 = time.time()
    results = _zig_execute(programs, max_steps)
    rows = [{
        "program": p,
        "output": r.get("output", ""),
        "steps": r.get("steps", 0),
        "terminated": r.get("terminated", False),
    } for p, r in zip(programs, results)]

    truncated = len(rows) > MAX_ROWS_IN_ARTIFACT
    if truncated:
        rows = rows[:MAX_ROWS_IN_ARTIFACT]

    sr = SearchResult(
        level=level, seeds=list(seeds), candidates_examined=len(programs),
        exhaustive=exhaustive, rows=rows, rows_truncated=truncated,
    )
    return sr, [f"frontier level={level} source={source} "
                f"candidates={len(programs):,} in {time.time()-t0:.1f}s"]


# ── CLASSIFY ───────────────────────────────────────────────────────
def stage_classify(ctx, params, inputs):
    """CLASSIFY: particiona un SearchResult por firma de comportamiento.

    Clases: quine | prefix_match | output_only | halt_silent | no_halt
    """
    sr = _require(inputs, SearchResult)
    classes: dict[str, list[str]] = {
        "quine": [], "prefix_match": [], "output_only": [],
        "halt_silent": [], "no_halt": [],
    }
    for row in sr.rows:
        out, prog = row["output"], row["program"]
        if not row["terminated"]:
            classes["no_halt"].append(prog)
        elif out == prog + "\n\n":
            classes["quine"].append(prog)
        elif out and (prog + "\n\n").startswith(out):
            classes["prefix_match"].append(prog)
        elif out:
            classes["output_only"].append(prog)
        else:
            classes["halt_silent"].append(prog)
    cr = ClassifierResult(
        classes=classes,
        counts={k: len(v) for k, v in classes.items()},
    )
    return cr, [f"classify: {cr.counts}"]


# ── SELECT ─────────────────────────────────────────────────────────
def stage_select(ctx, params, inputs):
    """SELECT top_n por score. by= prefix | output_len."""
    by = params.get("by", "prefix")
    top_n = int(params.get("top_n", 1000))

    sr = None
    for _sid, contract in inputs:
        if isinstance(contract, SearchResult):
            sr = contract
    if sr is None:
        # sin SearchResult directo: seleccionar la clase pedida
        cr = _require(inputs, ClassifierResult)
        cls = params.get("class", "prefix_match")
        selected = cr.classes.get(cls, [])[:top_n]
        sel = SelectionResult(selected=selected, rule=f"class={cls} top_n={top_n}")
        return sel, [f"select class={cls}: {len(selected)}"]

    def score(row):
        if by == "prefix":
            return _prefix_len(row["output"], row["program"] + "\n\n")
        return len(row["output"])

    scored = sorted(sr.rows, key=lambda r: -score(r))
    chosen = [r for r in scored if score(r) > 0][:top_n]
    sel = SelectionResult(
        selected=[r["program"] for r in chosen],
        scores={r["program"]: float(score(r)) for r in chosen},
        rule=f"by={by} top_n={top_n}",
    )
    return sel, [f"select {sel.rule}: {len(sel.selected)}"]


# ── TRANSFORM ──────────────────────────────────────────────────────
def stage_transform(ctx, params, inputs):
    """TRANSFORM: deriva nueva frontera sin tocar el solver.

    op = extend_length | compose | mutate | seed_solver
    """
    op = params.get("op", "extend_length")
    limit = int(params.get("limit", 100_000))
    base: list[str] = []
    for _sid, contract in inputs:
        if isinstance(contract, SelectionResult):
            base.extend(contract.selected)
        elif isinstance(contract, ClassifierResult):
            for progs in contract.classes.values():
                base.extend(progs)

    if op == "extend_length":
        derived = [p + ch for p in base for ch in PRINTABLE]
        prov = f"{len(base)} programs x{len(PRINTABLE)} chars"
    elif op == "mutate":
        derived = [p[:-1] + ch for p in base for ch in PRINTABLE] if base else []
        prov = f"last-char mutation of {len(base)} programs"
    elif op == "compose":
        cap = int(params.get("pair_limit", 100))
        head = base[:cap]
        derived = [a + b for a in head for b in head]
        prov = f"pairwise compose of first {len(head)} programs"
    elif op == "seed_solver":
        # extrae targets para el solver: outputs no vacíos observados
        # en un SearchResult upstream (la evidencia SIEMBRA la búsqueda)
        outputs: set[str] = set()
        for _sid, contract in inputs:
            if isinstance(contract, SearchResult):
                outputs.update(r["output"] for r in contract.rows
                               if r["terminated"] and r["output"])
        derived = sorted(outputs)
        prov = f"unique observed outputs -> solver targets ({len(derived)})"
    else:
        raise ValueError(f"unknown transform op: {op!r}")

    if len(derived) > limit:
        derived = derived[:limit]
        prov += f" (capped at {limit})"
    tr = TransformResult(op=op, derived=derived, provenance=prov)
    return tr, [f"transform {op}: {len(derived)} derived | {prov}"]


# ── COMPARE ────────────────────────────────────────────────────────
def stage_compare(ctx, params, inputs):
    """COMPARE: intersección/deltas entre dos SearchResult (por programa)."""
    if len(inputs) < 2:
        raise ValueError("compare necesita 2 inputs")
    (lid, lc), (rid, rc) = inputs[0], inputs[1]
    if not isinstance(lc, SearchResult) or not isinstance(rc, SearchResult):
        raise ValueError("compare solo soporta SearchResult por ahora")
    lset = {r["program"] for r in lc.rows}
    rset = {r["program"] for r in rc.rows}
    cr = CompareResult(
        left=lid, right=rid,
        only_left=len(lset - rset), only_right=len(rset - lset),
        shared=len(lset & rset),
        samples={
            "only_left": sorted(lset - rset)[:10],
            "only_right": sorted(rset - lset)[:10],
        },
    )
    return cr, [f"compare {lid} vs {rid}: shared={cr.shared} "
                f"only_left={cr.only_left} only_right={cr.only_right}"]


# ── SOLVE ──────────────────────────────────────────────────────────
def stage_solve(ctx, params, inputs):
    """SOLVE: generator sembrado + verificación zig.

    Input: TransformResult(op=seed_solver) con targets en `derived`.
    params:
      workers          int   1 = serial; >1 = ProcessPoolExecutor (H4)
      max_search_depth int
      max_steps        int   presupuesto VM en la verificación zig
    """
    tr = _require(inputs, TransformResult)
    targets = list(tr.derived)
    workers = int(params.get("workers", 1))
    max_search_depth = int(params.get("max_search_depth", 5))
    max_steps = int(params.get("max_steps", 5_000_000))

    if not targets:
        return SolverResult(), ["solve: 0 targets (nada que hacer)"]

    from translator_hybrid import (
        TranslatorCandidateFactory,
        generate_chunk_worker,
    )

    t0 = time.time()
    if workers > 1:
        import math
        from concurrent.futures import ProcessPoolExecutor

        items = list(enumerate(targets))
        chunk_size = math.ceil(len(items) / (workers * 4))
        chunks = [items[i:i + chunk_size]
                  for i in range(0, len(items), chunk_size)]
        with ProcessPoolExecutor(max_workers=workers) as pool:
            results = []
            for chunk_out in pool.map(
                    generate_chunk_worker,
                    [(c, max_search_depth) for c in chunks]):
                results.extend(chunk_out)
        results.sort(key=lambda c: c["_index"])
        cands = results
    else:
        factory = TranslatorCandidateFactory(max_search_depth=max_search_depth)
        cands = factory.batch(targets)
    gen_s = time.time() - t0

    # verificación zig del lote completo (un lote: la frontera entre
    # ejecutores no se cruza candidato por candidato)
    programs = [c["program_source"] for c in cands]
    zig = _zig_execute(programs, max_steps)

    rows = []
    matched = 0
    for c, zr in zip(cands, zig):
        zout = zr.get("output", "")
        ok = zout == c["target"]
        matched += ok
        rows.append({
            "target": c["target"],
            "program": c["program_source"],
            "opcodes": c["opcodes"],
            "nodes_expanded": c["stats"]["evaluations"],
            "generation_ms": round(c["stats"]["duration_ns"] / 1e6, 3),
            "zig_output": zout,
            "zig_match": ok,
        })

    sr = SolverResult(
        rows=rows,
        matched=matched,
        mismatched=len(rows) - matched,
        total_nodes=sum(r["nodes_expanded"] for r in rows),
        gen_time_s=round(gen_s, 2),
    )
    return sr, [f"solve: {matched}/{len(rows)} matched, "
                f"{sr.total_nodes:,} nodes in {gen_s:.1f}s "
                f"(workers={workers})"]


# ── VERDICT ────────────────────────────────────────────────────────
_OPS = {"==": operator.eq, "!=": operator.ne, ">": operator.gt,
        ">=": operator.ge, "<": operator.lt, "<=": operator.le}


def stage_verdict(ctx, params, inputs):
    """VERDICT: evalúa gates contra artefactos upstream y dictamina.

    params: gates=[{name, artifact_attr, field, op, value, inputs_index}]
    closed => campaña cerrada (no rerun recomendado).
    """
    gates: dict[str, bool] = {}
    for gate in params.get("gates", []):
        idx = int(gate.get("inputs_index", 0))
        _sid, contract = inputs[idx]
        value = getattr(contract, gate["field"])
        ok = _OPS[gate["op"]](value, gate["value"])
        gates[gate["name"]] = bool(ok)
        if not ok and gate.get("required", False):
            pass  # marcado en closed
    closed = params.get("closed_if") == "no_hits" and all(
        not getattr(c, "counts", {}).get("quine") for _s, c in inputs
        if isinstance(c, ClassifierResult)
    )
    summary_lines = [f"gate {name}: {'PASS' if ok else 'FAIL'}"
                     for name, ok in gates.items()]
    v = Verdict(gates=gates, summary="; ".join(summary_lines), closed=closed)
    return v, [f"verdict: {v.summary or 'no gates'} closed={v.closed}"]


STAGES = {
    "frontier": stage_frontier,
    "classify": stage_classify,
    "select": stage_select,
    "transform": stage_transform,
    "solve": stage_solve,
    "compare": stage_compare,
    "verdict": stage_verdict,
}

# Routing por sustrato: qué ejecutor implementa cada clase de nodo.
# El orquestador no pregunta "¿en qué lenguaje está Autobolge?"; pregunta
# "¿qué sustrato conviene para ESTE tramo del flujo?".
# La frontera entre ejecutores se cruza por LOTES (un artifact.json por
# nodo), nunca candidato por candidato.
EXECUTORS = {
    "frontier": "zig",      # hot loops / millones de candidatos
    "classify": "python",   # partición sobre artefactos
    "select": "python",
    "transform": "python",
    "solve": "python+zig",  # generador python (workers dentro) + verificación zig batch
    "compare": "python",
    "verdict": "python",
}


def _prefix_len(output: str, source: str) -> int:
    n = 0
    for a, b in zip(output, source):
        if a != b:
            break
        n += 1
    return n


def _require(inputs, cls):
    for _sid, contract in inputs:
        if isinstance(contract, cls):
            return contract
    raise ValueError(f"stage requiere input de tipo {cls.__name__}")
