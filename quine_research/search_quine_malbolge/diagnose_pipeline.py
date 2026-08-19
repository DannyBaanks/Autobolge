from pathlib import Path
"""Diagnóstico rápido del pipeline con Zig batch."""
import sys, os
os.chdir(Path(__file__).resolve().parents[2])
sys.path.insert(0, 'quine_research/search_quine_malbolge')
from search_quine_malbolge import (Candidate, ExecutionResult, execute_stage,
                                     halt_stage, output_stage, prefix_stage, exact_stage,
                                     generate_candidates, run_pipeline, TIERS)
from zig_batch import prepare_batch, run_batch

def diagnose(plen, ilen, limit=500, max_steps=100000):
    print(f"\n=== Diagnóstico plen={plen} ilen={ilen} limit={limit} max_steps={max_steps} ===")
    candidates = generate_candidates(mode='both', max_program_length=plen, max_input_length=ilen, limit=limit)
    stats = run_pipeline(candidates, tiers=TIERS, verbose=True)

    # Re-run para obtener detalles de OUTPUT y PREFIX
    print("\n--- S3 OUTPUT survivors ---")
    s1_all = execute_stage(candidates, tiers=TIERS)
    s1 = [r for r in s1_all if r.survived()]
    s2 = halt_stage(s1)
    s3 = output_stage(s2)
    for r in s3:
        src = r.candidate.source
        out = r.output
        prefix_len = 0
        for a, b in zip(out, src):
            if a != b: break
            prefix_len += 1
        print(f"  prog={r.candidate.program!r} inp={r.candidate.input_data!r} "
              f"steps={r.steps} out_len={len(out)} out={out!r} "
              f"prefix={prefix_len} src_len={len(src)}")

    # Save evidence
    evidence = {
        "config": {"plen": plen, "ilen": ilen, "limit": limit, "max_steps": max_steps},
        "stats": stats,
    }
    out_path = f'quine_research/search_quine_malbolge/results/diagnostic_plen{plen}_ilen{ilen}.json'
    with open(out_path, 'w') as f:
        import json
        json.dump(evidence, f, indent=2, ensure_ascii=False)
    print(f"Saved: {out_path}")

if __name__ == '__main__':
    diagnose(plen=2, ilen=1, limit=200, max_steps=100000)