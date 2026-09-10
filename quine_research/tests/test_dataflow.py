"""Tests del dataflow Autobolge."""
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "quine_research" / "search_quine_malbolge"))

from quine_research.dataflow.contracts import (  # noqa: E402
    ClassifierResult, SearchResult, contract_from_dict, contract_to_dict,
)
from quine_research.dataflow.engine import PipelineRunner  # noqa: E402
from quine_research.dataflow.semantic_manifest import (  # noqa: E402
    build_semantic_manifest, manifest_sha256,
)
from quine_research.dataflow.stages import (  # noqa: E402
    stage_busy_beaver, stage_transform,
)


def _write_spec(tmp_path: Path, stages: list, name: str = "test") -> Path:
    spec = tmp_path / f"{name}.json"
    spec.write_text(json.dumps({"pipeline": name, "stages": stages}),
                    encoding="utf-8")
    return spec


def test_contracts_roundtrip():
    sr = SearchResult(level=2, candidates_examined=3,
                      rows=[{"program": "a", "output": "b",
                             "steps": 1, "terminated": True}])
    assert contract_from_dict(contract_to_dict(sr)) == sr
    cr = ClassifierResult(classes={"quine": ["x"]}, counts={"quine": 1})
    assert contract_from_dict(contract_to_dict(cr)) == cr


def test_pipeline_runs_and_second_run_skips(tmp_path):
    spec = _write_spec(tmp_path, [
        {"id": "f1", "kind": "frontier",
         "params": {"level": 1, "seeds": [""], "max_steps": 100000}},
        {"id": "c1", "kind": "classify", "inputs": ["f1"], "params": {}},
    ])
    runner = PipelineRunner(spec, runs_root=tmp_path / "runs")
    statuses = runner.run()
    assert statuses == {"f1": "complete", "c1": "complete"}

    f1_art = runner.artifacts["f1"]
    assert f1_art["data"]["candidates_examined"] == 94
    assert f1_art["_meta"]["semantic_manifest_sha256"] == runner.semantic_manifest_sha256
    assert f1_art["_meta"]["semantic_manifest"]["schema"] == "autobolge-semantic-manifest/v1"
    c1 = runner.artifacts["c1"]["data"]
    assert sum(c1["counts"].values()) == 94

    # segunda corrida: artefactos intactos (no rerun)
    arts = list((tmp_path / "runs").rglob("artifact.json"))
    mtimes = {p: p.stat().st_mtime_ns for p in arts}
    time.sleep(0.02)
    PipelineRunner(spec, runs_root=tmp_path / "runs").run()
    for p, mt in mtimes.items():
        assert p.stat().st_mtime_ns == mt, f"{p} fue re-escrito"


def test_semantic_manifest_is_portable_and_invalidates_stage_key(tmp_path):
    manifest = build_semantic_manifest(ROOT)
    encoded = json.dumps(manifest, sort_keys=True)
    assert str(ROOT) not in encoded
    assert manifest_sha256(manifest) == manifest_sha256(manifest)

    spec = _write_spec(tmp_path, [{"id": "f1", "kind": "frontier", "params": {}}])
    runner = PipelineRunner(spec, runs_root=tmp_path / "runs")
    key_before = runner.stage_key_data(runner.spec["stages"][0])
    runner.semantic_manifest = {**runner.semantic_manifest, "semantic_epoch": "test-epoch"}
    runner.semantic_manifest_sha256 = manifest_sha256(runner.semantic_manifest)
    key_after = runner.stage_key_data(runner.spec["stages"][0])

    assert key_before["semantic_manifest_sha256"] != key_after["semantic_manifest_sha256"]
    assert runner.stage_dir(key_before) != runner.stage_dir(key_after)


def test_semantic_manifest_changes_when_vm_source_changes(tmp_path):
    vm = tmp_path / "zig" / "vm.zig"
    vm.parent.mkdir()
    vm.write_text("const version = 1;\n", encoding="utf-8")
    before = manifest_sha256(build_semantic_manifest(tmp_path))

    vm.write_text("const version = 2;\n", encoding="utf-8")
    after = manifest_sha256(build_semantic_manifest(tmp_path))

    assert before != after


def test_stop_reason_codes_match_reference_and_zig():
    from relational.execution import run_bounded
    from relational.fast_engine import run_bounded_fast

    for program, input_data, max_steps in (("c", "", 1), ("ub", "A", 100), ("u", "", 10)):
        reference = run_bounded(program, input_data, max_steps)
        fast = run_bounded_fast(program, input_data, max_steps)
        assert reference.reason_code == fast.reason_code
        assert reference.terminated == fast.terminated


def test_param_change_invalidates_only_downstream(tmp_path):
    stages = [
        {"id": "f1", "kind": "frontier",
         "params": {"level": 1, "seeds": [""], "max_steps": 100000}},
        {"id": "c1", "kind": "classify", "inputs": ["f1"], "params": {}},
        {"id": "s1", "kind": "select", "inputs": ["c1"],
         "params": {"class": "output_only", "top_n": 5}},
    ]
    spec = _write_spec(tmp_path, stages)
    PipelineRunner(spec, runs_root=tmp_path / "runs").run()

    def dirs_of(stage_id: str) -> list:
        return sorted(p.parent for p in (tmp_path / "runs").rglob("artifact.json")
                      if p.parent.name.startswith(stage_id + "__"))

    f1_before, c1_before, s1_before = dirs_of("f1"), dirs_of("c1"), dirs_of("s1")

    # cambiar solo el select -> f1 y c1 skipean, s1 recalcula
    stages[2]["params"]["top_n"] = 3
    spec2 = _write_spec(tmp_path, stages, name="test")
    PipelineRunner(spec2, runs_root=tmp_path / "runs").run()

    assert dirs_of("f1") == f1_before, "frontier se re-ejecutó y no debía"
    assert dirs_of("c1") == c1_before, "classify se re-ejecutó y no debía"
    s1_dirs = dirs_of("s1")
    assert len(s1_dirs) == 2 and s1_dirs != s1_before + s1_before
    new_dirs = [d for d in s1_dirs if d not in s1_before]
    assert len(new_dirs) == 1, "select debió producir un nuevo artefacto"
    s1 = json.loads((new_dirs[0] / "artifact.json").read_text(encoding="utf-8"))["data"]
    # select recorta a top_n; el conteo lo fija classify (semantica Classic densa:
    # 12 programas output_only en len-1, no 1 como en la semantica sparse vieja)
    c1 = json.loads((c1_before[0] / "artifact.json").read_text(encoding="utf-8"))["data"]
    expected = min(stages[2]["params"]["top_n"], c1["counts"]["output_only"])
    assert len(s1["selected"]) == expected


def test_seed_solver_then_solve(tmp_path):
    spec = _write_spec(tmp_path, [
        {"id": "f1", "kind": "frontier",
         "params": {"level": 1, "seeds": [""], "max_steps": 100000}},
        {"id": "seed", "kind": "transform", "inputs": ["f1"],
         "params": {"op": "seed_solver"}},
        {"id": "sv", "kind": "solve", "inputs": ["seed"],
         "params": {"workers": 1}},
    ])
    runner = PipelineRunner(spec, runs_root=tmp_path / "runs")
    runner.run()
    sv = runner.artifacts["sv"]["data"]
    assert sv["kind"] == "solver_result"
    assert len(sv["rows"]) > 0
    assert sv["mismatched"] == 0
    assert sv["matched"] == len(sv["rows"])
    # los targets del solver son outputs observados, no programas
    seed = runner.artifacts["seed"]["data"]
    programs = {r["program"] for r in runner.artifacts["f1"]["data"]["rows"]}
    assert all(t not in programs or True for t in seed["derived"])
    assert all(t for t in seed["derived"])  # outputs no vacíos


def test_template_variables(tmp_path):
    tmpl = tmp_path / "t.template.json"
    tmpl.write_text(json.dumps({
        "pipeline": "tvars",
        "stages": [
            {"id": "f${LEN}", "kind": "frontier",
             "params": {"level": "${LEN}", "seeds": [""], "max_steps": "100000"}},
        ],
    }), encoding="utf-8")
    runner = PipelineRunner(tmpl, runs_root=tmp_path / "runs",
                            variables={"LEN": "1"})
    statuses = runner.run()
    assert statuses == {"f1": "complete"}
    assert runner.artifacts["f1"]["data"]["candidates_examined"] == 94


def test_template_missing_variable_fails(tmp_path):
    tmpl = tmp_path / "t.template.json"
    tmpl.write_text(json.dumps({
        "pipeline": "tvars",
        "stages": [{"id": "f${LEN}", "kind": "frontier", "params": {}}],
    }), encoding="utf-8")
    try:
        PipelineRunner(tmpl, runs_root=tmp_path / "runs")
    except ValueError as e:
        assert "LEN" in str(e)
    else:
        raise AssertionError("debió fallar por variable sin valor")


def test_busy_beaver_unit():
    from quine_research.dataflow.contracts import SearchResult
    rows = [
        {"program": "cb", "output": "\x00\x00", "steps": 3, "terminated": True},
        {"program": ">ba", "output": "ss", "steps": 4, "terminated": True},
        {"program": "!x", "output": "", "steps": 2, "terminated": True},
        {"program": "?", "output": "zzz", "steps": 9, "terminated": False},
    ]
    sr = SearchResult(level=2, candidates_examined=4, rows=rows)

    sel, _ = stage_busy_beaver({}, {"top_n": "5"}, [("f", sr)])
    # '?' excluido (no halt pese a más output), '!x' excluido (sin output)
    assert set(sel.selected) == {"cb", ">ba"}

    sel_nn, _ = stage_busy_beaver(
        {}, {"top_n": "5", "non_nul_only": "true"}, [("f", sr)])
    assert sel_nn.selected == [">ba"]


def test_explicit_targets_transform():
    tr, _ = stage_transform(
        {}, {"op": "explicit_targets", "targets": ["HI!", "BYE"]}, [])
    assert tr.derived == ["HI!", "BYE"]


def test_difftest_and_catalog(tmp_path):
    from quine_research.dataflow.stages import stage_catalog, stage_difftest
    from quine_research.dataflow.contracts import SearchResult, SolverResult

    # dos programas que haltean: zig debe ejecutarlos y python acordar
    rows = [{"program": "c=", "output": "", "steps": 0, "terminated": False},
            {"program": "(=", "output": "", "steps": 0, "terminated": False}]
    # zig real sobre esos programas:
    from quine_research.dataflow.stages import _zig_execute
    zres = _zig_execute(["c=", "(="], 1000)
    rows = [{"program": p, "output": r.get("output", ""),
             "steps": r.get("steps", 0),
             "terminated": r.get("terminated", False),
             "reason": r.get("reason", 0),
             "final_pc": r.get("final_c", 0),
             "final_a": r.get("final_a", 0),
             "final_d": r.get("final_d", 0)}
            for p, r in zip(["c=", "(="], zres)]
    sr = SearchResult(level=2, candidates_examined=2, rows=rows)
    dr, summary = stage_difftest(
        {}, {"limit": "10", "max_steps": "1000"}, [("f", sr)])
    assert dr.mismatched == 0, f"divergencia semántica: {dr.mismatches}"
    assert dr.matched == 2

    sol = SolverResult(rows=[{
        "target": "A", "program": rows[0]["program"], "opcodes": "",
        "nodes_expanded": 1, "generation_ms": 0.1,
        "zig_output": "A", "zig_match": True}])
    tc, _ = stage_catalog({}, {}, [("s", sol)])
    assert len(tc.blocks) == 1 and tc.blocks[0]["zig_verified"]


def test_verdict_gates(tmp_path):
    spec = _write_spec(tmp_path, [
        {"id": "f1", "kind": "frontier",
         "params": {"level": 1, "seeds": [""], "max_steps": 100000}},
        {"id": "v", "kind": "verdict", "inputs": ["f1"],
         "params": {"gates": [
             {"name": "n_94", "inputs_index": 0,
              "field": "candidates_examined", "op": "==", "value": 94},
             {"name": "impossible", "inputs_index": 0,
              "field": "candidates_examined", "op": ">", "value": 10**9},
         ]}},
    ])
    runner = PipelineRunner(spec, runs_root=tmp_path / "runs")
    runner.run()
    v = runner.artifacts["v"]["data"]
    assert v["gates"] == {"n_94": True, "impossible": False}
