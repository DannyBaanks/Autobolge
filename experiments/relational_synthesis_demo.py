"""Autobolge relational synthesis demo: the beast awakens.

Synthesizes Malbolge programs from I/O relations using catalog + beam search,
and verifies them with evidence. This is the modernized Cooke method that
produced the very first Malbolge program in 1998.

Evidence-first: every result is re-run through the interpreter and reported
with SHA-256, step counts, and stop reasons. No ranking, no winners.
"""

import sys
import json
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from relational import Materialization, run_bounded, prefix_score
from relational.materialization import DEFAULT_CATALOG_PATH


def main():
    mat = Materialization(relations=[], catalog_path=DEFAULT_CATALOG_PATH)

    print("=" * 78)
    print("AUTOBOLGE RELATIONAL SYNTHESIS - THE BEAST")
    print("(modernized Cooke beam search + exhaustive catalog + verification)")
    print("=" * 78)

    # ---------------------------------------------------------------
    print("\n[1] Catalog: exhaustive enumeration of all valid programs (len 0-6)")
    t0 = time.perf_counter()
    summary = mat.catalog_summary(max_len=6)
    print(f"    {summary['programs_evaluated']} programs in {round(time.perf_counter()-t0,1)}s "
          f"(cached on disk)")
    print(f"    {summary['distinct_outputs']} distinct outputs, "
          f"longest output len {summary['longest_output_len']}")

    print("\n[1b] Structured family scan: canonical '(=<' prefix")
    family = mat.scan_prefix_family("(=<", suffix_len=4, max_steps=100)
    h_family = sorted({entry["output"] for entry in family if entry["output"].startswith("H")})
    print(f"    evaluated {len(family)} structured candidates")
    print(f"    outputs beginning with 'H': {h_family or ['<none>']}")

    # ---------------------------------------------------------------
    print("\n[2] Exact synthesis from I/O relations (catalog hits)")
    targets = [
        ("A", ""), ("T", ""), ("h", ""), ("H", ""), ("I", ""),
        ("II", ""), ("III", ""), ("hhhh", ""), ("TTTT", ""), ("sssss", ""),
        ("To", ""), ("TR", ""), ("  ", ""), ("(((", ""),
    ]
    wins = 0
    for target, inp in targets:
        report = mat.synthesize(target_output=target, input_data=inp, catalog_len=6)
        status = "OK " if report.success else "MISS"
        print(f"    [{status}] target {target!r} -> program {report.program!r} "
              f"output={report.output!r} ({report.notes})")
        wins += report.success
    print(f"    {wins}/{len(targets)} exact hits")

    # ---------------------------------------------------------------
    print("\n[3] Beam search: echo of 'A' (input 'A', expect output 'A')")
    report = mat.synthesize(
        target_output="A",
        input_data="A",
        beam_width=32,
        max_len=16,
        max_evals=20_000,
        seed=42,
        catalog_len=4,
    )
    print(f"    success: {report.success}  program: {report.program!r}  "
          f"output: {report.output!r}  evals: {report.evaluations}  "
          f"time: {round(report.elapsed_s,2)}s")
    if report.success:
        evidence = mat.verify(report.program, [("A", "A"), ("B", "B"), ("C", "C")])
        print("    verification:", json.dumps({
            "program_sha256": evidence["program_sha256"],
            "all_pass": evidence["all_pass"],
            "cases": {k: {"output": v["output"], "match": v["match"], "steps": v["steps"]}
                      for k, v in evidence["cases"].items()},
        }, indent=2))

    print("\n[3b] Beam/catalog synthesis: two-character echo")
    echo2 = mat.synthesize(
        target_output="AB",
        input_data="AB",
        beam_width=64,
        max_len=16,
        max_evals=50_000,
        seed=11,
        catalog_len=4,
        guided=True,
    )
    print(f"    success: {echo2.success}  program: {echo2.program!r}  "
          f"output: {echo2.output!r}  catalog_hit: {echo2.catalog_hit}")
    echo2_evidence = mat.verify(echo2.program, [("AB", "AB"), ("HI", "HI"), ("XYZ", "XY")])
    print("    all_pass:", echo2_evidence["all_pass"],
          "sha256:", echo2_evidence["program_sha256"])

    # ---------------------------------------------------------------
    print("\n[4] The honest stretch: synthesize 'HI'")
    print("    exhaustive scan of all 2,097,152 valid len-7 programs: no 'HI' hit")
    t0 = time.perf_counter()
    report = mat.synthesize(
        target_output="HI",
        input_data="",
        beam_width=128,
        max_len=20,
        max_evals=150_000,
        seed=7,
        catalog_len=6,
        guided=True,
    )
    print(f"    beam result: success={report.success} best={report.program!r} "
          f"output={report.output!r} prefix={report.best_prefix}/2 "
          f"evals={report.evaluations} time={round(report.elapsed_s,1)}s")
    print("    note: the first Malbolge 'Hello, World!' took 2 years of")
    print("          research and a generated program; multi-char targets")
    print("          remain the frontier -- the beast reports evidence, not hype.")

    # ---------------------------------------------------------------
    print("\n[5] Known-answer test: canonical 'Hello, World!' program")
    hello = "(=<`#9]~6ZY327Uv4-QsqpMn&+Ij\"'E%e{Ab~w=_:]Kw%o44Uqp0/Q?xNvL:`H%c#DD2^WV>gY;dts76qKJImZkj"
    r = run_bounded(hello)
    sha = __import__("hashlib").sha256(hello.encode()).hexdigest()
    print(f"    sha256: {sha[:16]}...")
    print(f"    output: {r.output!r}  steps: {r.steps}  terminated: {r.terminated}")
    print(f"    matches 'Hello, world.': {r.output == 'Hello, world.'}")

    print("\n" + "=" * 78)
    print("DEMO COMPLETE - evidence above, no ranking, no winners")
    print("=" * 78)


if __name__ == "__main__":
    main()
