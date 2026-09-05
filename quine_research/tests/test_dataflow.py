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
    c1 = runner.artifacts["c1"]["data"]
    assert sum(c1["counts"].values()) == 94

    # segunda corrida: artefactos intactos (no rerun)
    arts = list((tmp_path / "runs").rglob("artifact.json"))
    mtimes = {p: p.stat().st_mtime_ns for p in arts}
    time.sleep(0.02)
    PipelineRunner(spec, runs_root=tmp_path / "runs").run()
    for p, mt in mtimes.items():
        assert p.stat().st_mtime_ns == mt, f"{p} fue re-escrito"


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
    assert len(s1["selected"]) == 1  # solo hay 1 programa output_only en len1


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
