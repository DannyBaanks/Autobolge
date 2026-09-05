"""Pipeline runner del dataflow Autobolge.

Reglas de oro:
  1. Cada nodo = un directorio runs/<pipeline>/<stage_id>__<hash>/ con
     artifact.json explícito. Nada de "el siguiente proceso adivina".
  2. La clave de un nodo = sha256(params + inputs (path+sha256 upstream)).
     Si cambia cualquier upstream, el hash cambia y el nodo se re-ejecuta.
  3. Si el artifact existe y status == "complete" => SKIP (no rerun).
     Esto es lo que evita reventar otros 200 millones de Malbolges.
  4. --force fuerza re-ejecución de todo el pipeline.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from .contracts import contract_from_dict, contract_to_dict
from .stages import EXECUTORS, STAGES


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PipelineRunner:
    def __init__(self, spec_path: str | Path, runs_root: str | Path = "runs",
                 force: bool = False, variables: dict | None = None):
        self.spec_path = Path(spec_path)
        text = self.spec_path.read_text(encoding="utf-8")
        if variables:
            for key, value in variables.items():
                text = text.replace("${" + key + "}", str(value))
        if "${" in text:
            missing = text[text.index("${"):].split("}", 1)[0] + "}"
            raise ValueError(f"variable sin valor en el template: {missing}")
        self.spec = json.loads(text)
        self.pipeline = self.spec["pipeline"]
        self.runs_root = Path(runs_root) / self.pipeline
        self.force = force
        self.artifacts: dict[str, dict] = {}  # stage_id -> artifact dict

    # ---------- claves ----------
    def stage_key_data(self, stage: dict) -> dict:
        upstream = []
        for dep in stage.get("inputs", []):
            art = self.artifacts.get(dep)
            if art is None:
                raise ValueError(f"stage {stage['id']!r}: input {dep!r} no resuelto")
            upstream.append({"stage": dep,
                             "sha256": art["_meta"]["artifact_sha256"]})
        return {"id": stage["id"], "kind": stage["kind"],
                "params": stage.get("params", {}), "inputs": upstream}

    def stage_dir(self, key_data: dict) -> Path:
        digest = hashlib.sha256(
            json.dumps(key_data, sort_keys=True).encode()).hexdigest()[:8]
        return self.runs_root / f"{key_data['id']}__{digest}"

    # ---------- ejecución ----------
    def run(self) -> dict:
        print(f"[dataflow] pipeline={self.pipeline} "
              f"stages={len(self.spec['stages'])} force={self.force}")
        for stage in self.spec["stages"]:
            self.run_stage(stage)
        return {sid: a["_meta"]["status"] for sid, a in self.artifacts.items()}

    def run_stage(self, stage: dict) -> None:
        sid = stage["id"]
        kind = stage["kind"]
        if kind not in STAGES:
            raise ValueError(f"stage {sid!r}: kind desconocido {kind!r}")

        key_data = self.stage_key_data(stage)
        sdir = self.stage_dir(key_data)
        artifact_path = sdir / "artifact.json"
        executor = stage.get("executor", EXECUTORS[kind])

        if artifact_path.exists() and not self.force:
            artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
            if artifact["_meta"]["status"] == "complete":
                print(f"[SKIP] {sid} ({kind}) <- {artifact_path}")
                self.artifacts[sid] = artifact
                return
            print(f"[RERUN] {sid}: artifact previo incompleto")

        inputs = []
        for dep in stage.get("inputs", []):
            data = self.artifacts[dep]["data"]
            inputs.append((dep, contract_from_dict(data)))

        print(f"[RUN ] {sid} ({kind} @{executor}) inputs={[d for d in stage.get('inputs', [])]}")
        t0 = time.time()
        contract, summary = STAGES[kind]({"spec": self.spec},
                                         stage.get("params", {}), inputs)
        elapsed = round(time.time() - t0, 2)
        for line in summary:
            print(f"       {line}")

        sdir.mkdir(parents=True, exist_ok=True)
        artifact = {
            "data": contract_to_dict(contract),
            "_meta": {
                "stage_id": sid,
                "kind": kind,
                "executor": executor,
                "params": stage.get("params", {}),
                "inputs": key_data["inputs"],
                "elapsed_s": elapsed,
                "status": "complete",
                "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            },
        }
        tmp = artifact_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(artifact, indent=2, ensure_ascii=False),
                       encoding="utf-8")
        artifact["_meta"]["artifact_sha256"] = _sha256_file(tmp)
        tmp.write_text(json.dumps(artifact, indent=2, ensure_ascii=False),
                       encoding="utf-8")
        tmp.replace(artifact_path)
        self.artifacts[sid] = artifact
        print(f"[DONE] {sid} -> {artifact_path}")


def run_pipeline(spec_path: str, force: bool = False,
                 runs_root: str = "runs",
                 variables: dict | None = None) -> dict:
    return PipelineRunner(spec_path, runs_root=runs_root,
                          force=force, variables=variables).run()
