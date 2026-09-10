"""Public catalog: content-addressed export of anchors, traces, and manifests.

Generates canonical artifacts from known programs, persists them to pub/,
and produces a unified index (pub/index.json).

Usage:
    py pub_catalog.py              # generate all
    py pub_catalog.py --anchors    # anchors only
    py pub_catalog.py --traces     # traces only
    py pub_catalog.py --verify     # verify existing pub/ against index
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

PUB_DIR = Path("pub")
INDEX_PATH = PUB_DIR / "index.json"

# ── Known programs for catalog generation ──────────────────────────
# Programs that have been verified by Gate1 (417/417) or template catalog.
# These are the "canonical" programs whose anchors/traces are publishable.
CATALOG_PROGRAMS = [
    # Single-char programs (from gate1 test cases)
    "", "!", "\"", "#", "$", "%", "&", "'", "(", ")", "*", "+", ",", "-",
    ".", "/", "0", "1", "2", "3", "4", "5", "6", "7", "8", "9", ":",
    ";", "<", "=", ">", "?", "@", "A", "B", "C", "D", "E", "F", "G",
    "H", "I", "J", "K", "L", "M", "N", "O", "P", "Q", "R", "S", "T",
    "U", "V", "W", "X", "Y", "Z", "[", "\\", "]", "^", "_", "`", "a",
    "b", "c", "d", "e", "f", "g", "h", "i", "j", "k", "l", "m", "n",
    "o", "p", "q", "r", "s", "t", "u", "v", "w", "x", "y", "z", "{",
    "|", "}", "~",
    # Template catalog programs (zig_verified)
    "c=", "(=", "a=", "b=", "d=", "e=",
]

MAX_STEPS = 3000


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _content_path(base_dir: Path, digest: str, ext: str) -> Path:
    """Content-addressed path: pub/ab/cdef1234...ext (first 2 chars = subdir)."""
    subdir = base_dir / digest[:2]
    subdir.mkdir(parents=True, exist_ok=True)
    return subdir / f"{digest}{ext}"


def generate_anchors(programs: list[str], input_data: str = "") -> list[dict]:
    """Generate EpochAnchorV1 for each program and persist to pub/."""
    from relational.anchors import EpochAnchorV1
    from relational.classic import TraceEvent
    from relational.execution import run_bounded

    anchors_dir = PUB_DIR / "anchors"
    anchors_dir.mkdir(parents=True, exist_ok=True)

    entries = []
    for prog in programs:
        trace: list[TraceEvent] = []
        try:
            dbg = __import__("relational.classic", fromlist=["ClassicDebugger"]).ClassicDebugger(
                prog, input_data, MAX_STEPS, trace=trace
            )
            while not dbg.is_stopped and dbg.step_count < MAX_STEPS:
                dbg.step()
        except Exception:
            continue

        try:
            anchor = EpochAnchorV1.from_debugger(dbg, trace)
        except Exception:
            continue

        anchor_json = anchor.to_json()
        digest = anchor.digest()
        path = _content_path(anchors_dir, digest, ".json")
        path.write_text(anchor_json, encoding="utf-8")

        entries.append({
            "type": "anchor",
            "schema": anchor.schema,
            "digest": digest,
            "program": prog,
            "stop_reason": anchor.stop_reason,
            "step": anchor.step,
            "pc": anchor.pc,
            "a": anchor.a,
            "d": anchor.d,
            "memory_root": anchor.memory_root,
            "output_len": len(anchor.output),
            "path": str(path).replace("\\", "/"),
            "sha256": _sha256(anchor_json.encode("utf-8")),
        })

    return entries


def generate_traces(programs: list[str], input_data: str = "") -> list[dict]:
    """Generate traces for each program and persist to pub/."""
    from relational.classic import ClassicDebugger, TraceEvent
    from relational.trace import serialize_trace, verify_trace, checkpoint_digests

    traces_dir = PUB_DIR / "traces"
    traces_dir.mkdir(parents=True, exist_ok=True)

    entries = []
    for prog in programs:
        trace: list[TraceEvent] = []
        try:
            dbg = __import__("relational.classic", fromlist=["ClassicDebugger"]).ClassicDebugger(
                prog, input_data, MAX_STEPS, trace=trace
            )
            while not dbg.is_stopped and dbg.step_count < MAX_STEPS:
                dbg.step()
        except Exception:
            continue

        if not trace:
            continue

        try:
            verify_trace(trace)
        except Exception:
            continue

        trace_json = serialize_trace(trace)
        trace_hash = _sha256(trace_json.encode("utf-8"))
        path = _content_path(traces_dir, trace_hash, ".json")
        path.write_text(trace_json, encoding="utf-8")

        cps = checkpoint_digests(trace, interval=max(1, len(trace) // 4))

        entries.append({
            "type": "trace",
            "schema": "autobolge-trace/v1",
            "hash": trace_hash,
            "program": prog,
            "events": len(trace),
            "checkpoints": cps,
            "stop_reason": trace[-1].reason,
            "path": str(path).replace("\\", "/"),
            "sha256": _sha256(trace_json.encode("utf-8")),
        })

    return entries


def generate_manifests() -> list[dict]:
    """Index existing semantic manifests from evidence files."""
    manifests_dir = PUB_DIR / "manifests"
    manifests_dir.mkdir(parents=True, exist_ok=True)

    entries = []
    evidence_dir = Path("experiments/evidence")
    if evidence_dir.exists():
        for f in sorted(evidence_dir.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            manifest = data.get("semantic_manifest")
            if not manifest:
                continue
            manifest_json = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
            manifest_hash = _sha256(manifest_json.encode("utf-8"))
            path = _content_path(manifests_dir, manifest_hash, ".json")
            path.write_text(manifest_json, encoding="utf-8")

            entries.append({
                "type": "manifest",
                "schema": manifest.get("schema", ""),
                "semantic_epoch": manifest.get("semantic_epoch", ""),
                "hash": manifest_hash,
                "source_evidence": str(f).replace("\\", "/"),
                "path": str(path).replace("\\", "/"),
                "sha256": _sha256(manifest_json.encode("utf-8")),
            })

    return entries


def generate_campaign_index() -> list[dict]:
    """Index pipeline campaigns from runs/."""
    entries = []
    runs_root = Path("runs")
    if not runs_root.exists():
        return entries

    for art in sorted(runs_root.rglob("artifact.json")):
        try:
            raw = art.read_bytes()
            d = json.loads(raw.decode("utf-8"))
        except Exception:
            continue
        meta = d.get("_meta", {})
        data = d.get("data", {})
        label = meta.get("label", "CURRENT")
        entries.append({
            "type": "campaign",
            "pipeline": art.parent.parent.name,
            "stage": meta.get("stage_id"),
            "kind": data.get("kind"),
            "label": label,
            "sha256": _sha256(raw),
            "path": str(art).replace("\\", "/"),
        })

    return entries


def build_index(anchors: list[dict], traces: list[dict],
                manifests: list[dict], campaigns: list[dict]) -> dict:
    """Build unified content-addressed index."""
    all_entries = anchors + traces + manifests + campaigns

    index = {
        "schema": "autobolge-pub-index/v1",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "counts": {
            "anchors": len(anchors),
            "traces": len(traces),
            "manifests": len(manifests),
            "campaigns": len(campaigns),
            "total": len(all_entries),
        },
        "entries": all_entries,
    }
    return index


def verify_index(index: dict) -> list[str]:
    """Verify all entries in the index exist on disk and hashes match."""
    errors = []
    for entry in index.get("entries", []):
        path = Path(entry["path"])
        if not path.exists():
            errors.append(f"MISSING: {entry['path']}")
            continue
        actual = _sha256(path.read_bytes())
        expected = entry.get("sha256")
        if expected and actual != expected:
            errors.append(f"HASH MISMATCH: {entry['path']} expected={expected[:16]} actual={actual[:16]}")
    return errors


def main():
    parser = argparse.ArgumentParser(description="Autobolge public catalog generator")
    parser.add_argument("--anchors", action="store_true", help="Generate anchors only")
    parser.add_argument("--traces", action="store_true", help="Generate traces only")
    parser.add_argument("--verify", action="store_true", help="Verify existing pub/ against index")
    args = parser.parse_args()

    PUB_DIR.mkdir(parents=True, exist_ok=True)

    if args.verify:
        if not INDEX_PATH.exists():
            print("ERROR: pub/index.json not found")
            sys.exit(1)
        index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
        errors = verify_index(index)
        if errors:
            for e in errors:
                print(f"  {e}")
            print(f"VERIFICATION FAILED: {len(errors)} errors")
            sys.exit(1)
        else:
            print(f"VERIFICATION OK: {index['counts']['total']} entries verified")
            sys.exit(0)

    do_anchors = args.anchors or not (args.anchors or args.traces)
    do_traces = args.traces or not (args.anchors or args.traces)

    t0 = time.time()
    anchors = generate_anchors(CATALOG_PROGRAMS) if do_anchors else []
    traces = generate_traces(CATALOG_PROGRAMS) if do_traces else []
    manifests = generate_manifests()
    campaigns = generate_campaign_index()

    index = build_index(anchors, traces, manifests, campaigns)
    INDEX_PATH.write_text(json.dumps(index, indent=2, ensure_ascii=False),
                          encoding="utf-8")

    elapsed = time.time() - t0
    print(f"pub_catalog: {index['counts']['total']} entries "
          f"(anchors={len(anchors)}, traces={len(traces)}, "
          f"manifests={len(manifests)}, campaigns={len(campaigns)}) "
          f"in {elapsed:.1f}s -> {INDEX_PATH}")


if __name__ == "__main__":
    main()
