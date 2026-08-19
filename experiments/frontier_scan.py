from pathlib import Path
"""frontier_scan.py - Escaneo exhaustivo del frontier de Autobolge con el motor Zig.

Genera TODOS los programas validos de longitud exacta `length` (en el mismo
orden de enumeracion que build_catalog), los imprime en batches de 1M via
bolge.exe, y filtra los que producen el output objetivo (p.ej. 'HI').

Evidencia: experiments/evidence/frontier_<target>_len<length>.json por
longitud (hits verificados con run_bounded, negativos honestos, timings).

Uso:
  python experiments/frontier_scan.py --target HI --lengths 7,8
"""

import argparse
import itertools
import json
import os
import struct
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from relational.fast_engine import BOLGE_EXE, MAGIC_IN, MAGIC_OUT

CHUNK = 1_000_000
MAX_STEPS = 3000
EVIDENCE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "evidence")


def level_cells(pos: int):
    from relational.materialization import valid_opcode_chars
    return tuple(ord(c["char"]) for c in valid_opcode_chars(pos))


def gen_programs(length: int):
    """Yield cell tuples for every valid program of exact length, catalog order."""
    if length == 0:
        yield ()
        return
    levels = [level_cells(p) for p in range(length)]
    for combo in itertools.product(*levels):
        yield combo


def build_batch(records):
    buf = bytearray()
    buf += MAGIC_IN
    buf += struct.pack("<Q", len(records))
    for cells in records:
        buf += struct.pack("<I", len(cells))
        buf += struct.pack("<%dI" % len(cells), *cells)
        buf += struct.pack("<I", 0)  # input_len
        buf += struct.pack("<I", MAX_STEPS)
    return bytes(buf)


def run_chunk(records):
    batch = build_batch(records)
    with tempfile.TemporaryDirectory() as tmp:
        in_path = os.path.join(tmp, "in.bin")
        out_path = os.path.join(tmp, "out.bin")
        with open(in_path, "wb") as f:
            f.write(batch)
        proc = subprocess.run([BOLGE_EXE, in_path, out_path], capture_output=True, timeout=900)
        if proc.returncode != 0:
            raise RuntimeError(
                f"bolge.exe failed (rc={proc.returncode}): "
                f"{proc.stdout.decode(errors='replace')} {proc.stderr.decode(errors='replace')}")
        with open(out_path, "rb") as f:
            data = f.read()
    pos = 5
    (n,) = struct.unpack_from("<Q", data, pos)
    pos += 8
    assert n == len(records), f"count mismatch: {n} != {len(records)}"
    out = []
    for _ in range(n):
        (olen,) = struct.unpack_from("<I", data, pos)
        pos += 4
        o = data[pos : pos + olen]
        pos += olen
        (steps,) = struct.unpack_from("<Q", data, pos)
        pos += 8
        terminated = data[pos] != 0
        pos += 2
        (final_c, final_a, final_d) = struct.unpack_from("<III", data, pos)
        pos += 12
        out.append((o, steps, terminated, final_c, final_a, final_d))
    return out


def scan_length(target: str, length: int, keep_going: bool):
    print(f"\n=== frontier len {length}: {8**length} programas, target={target!r} ===")
    t0 = time.perf_counter()
    hits = []
    total = 0
    chunk_records = []
    chunk_hits = []

    def flush():
        nonlocal chunk_records, chunk_hits
        if not chunk_records:
            return
        results = run_chunk(chunk_records)
        for cells, res in zip(chunk_records, results):
            out_bytes, steps, terminated, final_c, final_a, final_d = res
            if out_bytes == target.encode("latin-1"):
                program = "".join(chr(c) for c in cells)
                chunk_hits.append({
                    "program": program,
                    "output": out_bytes.decode("latin-1"),
                    "steps": steps,
                    "terminated": terminated,
                    "final_pc": final_c,
                    "final_a": final_a,
                    "final_d": final_d,
                })
        chunk_records = []
        chunk_hits = []

    for cells in gen_programs(length):
        chunk_records.append(cells)
        total += 1
        if len(chunk_records) >= CHUNK:
            flush()
            hits.extend(chunk_hits)
            chunk_hits = []
            if total % (8 * CHUNK) == 0:
                print(f"  {total:,} listos en {time.perf_counter() - t0:.0f}s "
                      f"({total / (time.perf_counter() - t0):,.0f} prog/s)")
    flush()
    hits.extend(chunk_hits)

    elapsed = time.perf_counter() - t0
    print(f"  total: {total:,} programas en {elapsed:.1f}s "
          f"({total / elapsed:,.0f} prog/s), hits: {len(hits)}")

    # verificar hits con el motor de referencia (paridad ya probada por los gates)
    verified = []
    if hits:
        from relational.execution import run_bounded
        for h in hits:
            r = run_bounded(h["program"], "", MAX_STEPS)
            verified.append({
                **h,
                "verified_by_reference": {
                    "output": r.output, "steps": r.steps, "terminated": r.terminated,
                    "final_pc": r.final_pc, "final_a": r.final_a, "final_d": r.final_d,
                },
                "reference_match": r.output == h["output"] and r.steps == h["steps"],
            })

    os.makedirs(EVIDENCE_DIR, exist_ok=True)
    out_path = os.path.join(EVIDENCE_DIR, f"frontier_{target}_len{length}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "target": target,
            "input": "",
            "length": length,
            "total_programs": total,
            "elapsed_s": round(elapsed, 2),
            "rate_prog_per_s": round(total / elapsed, 1),
            "hits": verified,
            "negative": not verified,
        }, f, ensure_ascii=False, indent=2)
    print(f"  evidencia: {out_path}")

    if verified and not keep_going:
        sys.exit(0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default="HI")
    ap.add_argument("--lengths", default="7,8", help="longitudes exactas a escanear")
    ap.add_argument("--keep-going", action="store_true")
    args = ap.parse_args()

    if not os.path.exists(BOLGE_EXE):
        print(f"bolge.exe no existe: {BOLGE_EXE}")
        sys.exit(1)

    for length in (int(x) for x in args.lengths.split(",")):
        scan_length(args.target, length, args.keep_going)

    print("\nFRONTIER SCAN COMPLETE")


if __name__ == "__main__":
    main()