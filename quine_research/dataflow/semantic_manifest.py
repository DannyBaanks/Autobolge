"""Identidad reproducible de la semántica que ejecuta Autobolge.

El manifiesto es deliberadamente puro: no lleva timestamp ni rutas absolutas,
para que su digest sea una clave estable de cache. Los artefactos dataflow lo
incluyen completo y usan su digest en la clave de cada stage.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
from pathlib import Path
from typing import Any


SCHEMA = "autobolge-semantic-manifest/v1"
SEMANTIC_EPOCH = "autobolge-classic-dense-input-underflow/v1"
ROOT = Path(__file__).resolve().parents[2]
AUTHORITY_LOGICAL_PATH = "Malbolge-Translator/zig/src/engine.zig"


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")


def manifest_sha256(manifest: dict) -> str:
    """Digest de contenido del manifiesto, sin depender del formato del archivo."""
    return hashlib.sha256(_canonical_bytes(manifest)).hexdigest()


def _run(args: list[str], cwd: Path) -> str | None:
    try:
        result = subprocess.run(
            args,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _git_metadata(root: Path, semantic_files: list[Path] | None = None) -> dict:
    commit = _run(["git", "rev-parse", "HEAD"], root)
    if commit is None:
        return {"available": False}
    diff_args = ["git", "diff", "--no-ext-diff", "--binary", "HEAD"]
    if semantic_files is not None:
        diff_args.append("--")
        diff_args.extend(str(path.relative_to(root)) for path in semantic_files)
    diff = _run(diff_args, root)
    return {
        "available": True,
        "commit": commit,
        "remote": _run(["git", "remote", "get-url", "origin"], root),
        # Solo fuentes semánticas: evidencia o documentación no deben cambiar
        # la identidad de una ejecución que las está escribiendo.
        "semantic_dirty": bool(diff),
        "semantic_dirty_sha256": hashlib.sha256((diff or "").encode()).hexdigest(),
    }


def _file_record(path: Path, logical_path: str) -> dict:
    if not path.is_file():
        return {"path": logical_path, "present": False, "sha256": None}
    return {
        "path": logical_path,
        "present": True,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _zig_version(root: Path) -> str | None:
    zig = os.environ.get("ZIG_EXE", "zig")
    return _run([zig, "version"], root)


def _package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _authority_engine(root: Path) -> tuple[Path, str]:
    configured = os.environ.get("AUTOBOLGE_AUTHORITY_ENGINE")
    if configured:
        return Path(configured), "AUTOBOLGE_AUTHORITY_ENGINE"
    return root.parent / AUTHORITY_LOGICAL_PATH, AUTHORITY_LOGICAL_PATH


def build_semantic_manifest(repo_root: Path | None = None) -> dict:
    """Describe todos los insumos que pueden cambiar la semántica ejecutada."""
    root = (repo_root or ROOT).resolve()
    authority_engine, authority_label = _authority_engine(root)
    authority_root = (
        authority_engine.parents[2]
        if len(authority_engine.parents) > 2
        else authority_engine.parent
    )

    sources = [
        "zig/vm.zig",
        "zig/bolge.zig",
        "zig/dsl.zig",
        "zig/frontier_scan.zig",
        "experiments/gate1_parity.py",
        "experiments/gate2_catalog.py",
        "experiments/printer_loop.py",
        "relational/classic.py",
        "relational/execution.py",
        "relational/fast_engine.py",
        "relational/materialization.py",
        "relational/transition.py",
        "runner/interpreter.py",
        "quine_research/dataflow/contracts.py",
        "quine_research/dataflow/engine.py",
        "quine_research/dataflow/semantic_manifest.py",
        "quine_research/dataflow/stages.py",
        "quine_research/search_quine_malbolge/zig_batch.py",
    ]
    artifacts = [
        "zig/bolge.exe",
        "experiments/catalog_cache/catalog_e6dfb345.json",
    ]
    source_paths = [root / item for item in sources]
    return {
        "schema": SCHEMA,
        "semantic_epoch": SEMANTIC_EPOCH,
        "semantic_contract": {
            "machine": "classic-dense",
            "input": "utf8-real-input",
            "input_underflow": "terminate",
            "invalid_decoded_opcode": "nop",
        },
        "repository": _git_metadata(root, source_paths),
        "authority": {
            "engine": _file_record(authority_engine, authority_label),
            "repository": _git_metadata(authority_root, [authority_engine]),
        },
        "sources": [_file_record(root / item, item) for item in sources],
        "artifacts": [_file_record(root / item, item) for item in artifacts],
        "toolchain": {
            "zig_version": _zig_version(root),
            "python_implementation": platform.python_implementation(),
            "python_version": platform.python_version(),
            "packages": {"malbolge": _package_version("malbolge")},
            "os": platform.system(),
            "machine": platform.machine(),
        },
    }
