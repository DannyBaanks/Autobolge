#!/usr/bin/env python3
"""Scan the len<=6 catalog for exact self-reproducing programs."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "experiments" / "catalog_cache" / "catalog_e6dfb345.json"
OUT = ROOT / "experiments" / "evidence" / "tiny_quine_catalog_scan.json"


def main() -> int:
    entries = json.loads(CATALOG.read_text(encoding="utf-8"))
    by_length = Counter(len(entry["program"]) for entry in entries)
    hits = [entry for entry in entries if entry["output"] == entry["program"]]
    payload = {
        "format": "autobolge-tiny-quine-catalog-scan/1",
        "label": "CURRENT",
        "catalog": "experiments/catalog_cache/catalog_e6dfb345.json",
        "catalog_sha256": hashlib.sha256(CATALOG.read_bytes()).hexdigest(),
        "entries": len(entries),
        "by_length": dict(sorted(by_length.items())),
        "hits": hits,
        "negative": len(hits) == 0,
        "definition": "output bytes == program bytes (raw source, exact)",
    }
    OUT.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(
        f"entries={len(entries)} hits={len(hits)} "
        f"by_length={dict(sorted(by_length.items()))}"
    )
    print(f"evidence: {OUT.relative_to(ROOT)}")
    return 0 if not hits else 1


if __name__ == "__main__":
    raise SystemExit(main())
