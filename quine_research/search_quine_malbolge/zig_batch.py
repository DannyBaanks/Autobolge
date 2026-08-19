"""
zig_batch.py — Interface batch a bolge.exe (motor Zig Malbolge).

API:
  prepare_batch(candidates, max_steps) -> bytes  (formato BOLG1)
  run_batch(batch_bytes, bolge_path) -> list[dict]  (resultados parseados)
  
Diseñado para throughput máximo: un solo invocation de bolge.exe
procesa TODOS los candidatos del batch.
"""

import struct, os, subprocess, json, time
from typing import List, Dict, Optional

# Formato BOLG1 / BOLG2 documentado en zig/bolge.zig
BOLG_HEADER = b'BOLG1'
BOLG2_HEADER = b'BOLG2'
MAGIC_SIZE = 5
U32_SIZE = 4
U64_SIZE = 8

def _encode_u32(v: int) -> bytes:
    return struct.pack('<I', v)

def _encode_u64(v: int) -> bytes:
    return struct.pack('<Q', v)

def _decode_u32(b: bytes, pos: int) -> tuple:
    v = struct.unpack_from('<I', b, pos)[0]
    return v, pos + 4

def _decode_u64(b: bytes, pos: int) -> tuple:
    v = struct.unpack_from('<Q', b, pos)[0]
    return v, pos + 8

def program_to_cells(program: str) -> List[int]:
    """Convierte programa Malbolge ASCII a lista de celdas (valores ASCII)."""
    clean = ''.join(c for c in program if 33 <= ord(c) <= 126)
    return [ord(c) for c in clean]

def prepare_batch(candidates: list, max_steps: int = 100_000) -> bytes:
    """
    Empaqueta candidatos en formato BOLG1.
    Cada candidato lleva su propio max_steps (para tiers progresivos).
    
    candidate: objeto con .program, .input_data, .max_steps (opcional)
    """
    parts = [BOLG_HEADER]
    count = len(candidates)
    parts.append(_encode_u64(count))
    
    for cand in candidates:
        cells = program_to_cells(cand.program if hasattr(cand, 'program') else cand)
        inp = cand.input_data if hasattr(cand, 'input_data') else ""
        ms = getattr(cand, 'max_steps', max_steps) or max_steps
        
        parts.append(_encode_u32(len(cells)))
        for cell in cells:
            parts.append(_encode_u32(cell))
        parts.append(_encode_u32(len(inp)))
        parts.append(inp.encode('latin1'))
        parts.append(_encode_u32(ms))
    
    return b''.join(parts)

def prepare_batch_from_dicts(candidates: list, max_steps: int = 100_000) -> bytes:
    """Versión para dicts: {'program': str, 'input_data': str, 'max_steps': int}."""
    parts = [BOLG_HEADER]
    count = len(candidates)
    parts.append(_encode_u64(count))
    
    for c in candidates:
        cells = program_to_cells(c['program'])
        inp = c.get('input_data', '')
        ms = c.get('max_steps', max_steps)
        
        parts.append(_encode_u32(len(cells)))
        for cell in cells:
            parts.append(_encode_u32(cell))
        parts.append(_encode_u32(len(inp)))
        parts.append(inp.encode('latin1'))
        parts.append(_encode_u32(ms))
    
    return b''.join(parts)

def parse_batch_results(buf: bytes) -> List[Dict]:
    """Parsea formato BOLG2."""
    if len(buf) < MAGIC_SIZE + U64_SIZE:
        return []
    if buf[:MAGIC_SIZE] != BOLG2_HEADER:
        return []
    
    pos = MAGIC_SIZE
    count, pos = _decode_u64(buf, pos)
    results = []
    
    for i in range(count):
        if pos + U32_SIZE > len(buf):
            break
        output_len, pos = _decode_u32(buf, pos)
        if pos + output_len + U64_SIZE + 1 + 1 + U32_SIZE * 3 > len(buf):
            break
        output = buf[pos:pos+output_len].decode('latin1', errors='replace')
        pos += output_len
        steps, pos = _decode_u64(buf, pos)
        terminated = buf[pos] == 1
        pos += 1
        reason = buf[pos]  # 0=running, 1=terminated
        pos += 1
        final_c, pos = _decode_u32(buf, pos)
        final_a, pos = _decode_u32(buf, pos)
        final_d, pos = _decode_u32(buf, pos)
        
        results.append({
            'output': output,
            'steps': steps,
            'terminated': terminated,
            'reason': reason,
            'final_c': final_c,
            'final_a': final_a,
            'final_d': final_d,
            'output_len': output_len,
        })
    
    return results

def run_batch(batch_bytes: bytes, bolge_path: str = "zig/bolge.exe",
              work_dir: str = ".") -> List[Dict]:
    """
    Ejecuta batch en bolge.exe y retorna resultados.
    Escribe in.bin, ejecuta, lee out.bin.
    """
    in_path = os.path.join(work_dir, "_batch_in.bin")
    out_path = os.path.join(work_dir, "_batch_out.bin")
    
    with open(in_path, 'wb') as f:
        f.write(batch_bytes)
    
    try:
        proc = subprocess.run(
            [bolge_path, in_path, out_path],
            capture_output=True, timeout=300
        )
        if proc.returncode != 0:
            return [{'error': f'bolge exited {proc.returncode}', 'stderr': proc.stderr.decode()[:200]}]
        
        with open(out_path, 'rb') as f:
            out_buf = f.read()
        return parse_batch_results(out_buf)
    finally:
        for p in (in_path, out_path):
            if os.path.exists(p):
                os.remove(p)