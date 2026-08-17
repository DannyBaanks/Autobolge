from __future__ import annotations

import hashlib
import itertools
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

from .execution import RunResult, evaluate_io, fitness, guided_fitness, prefix_score, run_bounded
from .relation import Relation
from .state import MalbolgeSnapshot
from .transition import valid_opcode_chars

DEFAULT_CATALOG_PATH = str(Path(__file__).resolve().parent.parent / "experiments" / "catalog_cache")


@dataclass
class SynthesisReport:
    """Evidence-first report of a synthesis attempt."""

    target: str
    input_data: str
    success: bool
    program: str = ""
    output: str = ""
    steps: int = 0
    evaluations: int = 0
    best_prefix: int = 0
    catalog_hit: bool = False
    elapsed_s: float = 0.0
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "target": self.target,
            "input_data": self.input_data,
            "success": self.success,
            "program": self.program,
            "program_sha256": hashlib.sha256(self.program.encode()).hexdigest(),
            "output": self.output,
            "steps": self.steps,
            "evaluations": self.evaluations,
            "best_prefix": self.best_prefix,
            "catalog_hit": self.catalog_hit,
            "elapsed_s": round(self.elapsed_s, 3),
            "notes": self.notes,
        }


@dataclass
class Materialization:
    """Materializes a relational specification into a Malbolge program.

    Strategy (the Cooke method, modernized):
      1. Build an exhaustive catalog of all valid programs up to `catalog_len`.
      2. Quick-check the catalog for an exact output match.
      3. Beam-search: grow programs one valid char at a time, run each fully
         under a step budget, rank by prefix-match fitness against the target.
    """

    relations: List[Relation] = field(default_factory=list)
    catalog_cache: Dict[tuple, List[dict]] = field(default_factory=dict)
    catalog_path: Optional[str] = None

    def materialize(
        self,
        target_state: Optional[MalbolgeSnapshot] = None,
        target_output: Optional[str] = None,
        input_data: str = "",
        **kwargs,
    ) -> str:
        """Compatibility entry point: returns the synthesized program string."""
        if target_output is None and target_state is not None:
            target_output = target_state.output_buffer.decode(errors="replace")
        if target_output is None:
            raise ValueError("materialize requires target_output or a target_state")
        report = self.synthesize(target_output=target_output, input_data=input_data, **kwargs)
        return report.program

    def materialize_to_program(self, target_state: Optional[MalbolgeSnapshot] = None, **kwargs) -> str:
        return self.materialize(target_state=target_state, **kwargs)

    def _catalog_file(self, max_len: int, input_data: str) -> Optional[str]:
        if not self.catalog_path:
            return None
        import hashlib
        import os

        tag = hashlib.md5(f"{max_len}|{input_data}".encode()).hexdigest()[:8]
        return os.path.join(self.catalog_path, f"catalog_{tag}.json")

    def build_catalog(self, max_len: int = 4, max_steps: int = 3000, input_data: str = "") -> List[dict]:
        """Exhaustively enumerate all valid programs up to max_len and run them.

        Results are cached in-memory and optionally persisted to disk
        (catalog_path) so repeated builds are instant.
        """
        cache_key = (max_len, input_data)
        if cache_key in self.catalog_cache:
            return self.catalog_cache[cache_key]

        import json
        import os

        cache_file = self._catalog_file(max_len, input_data)
        if cache_file and os.path.exists(cache_file):
            with open(cache_file, "r", encoding="utf-8") as f:
                self.catalog_cache[cache_key] = json.load(f)
            return self.catalog_cache[cache_key]

        catalog: List[dict] = []
        level: List[str] = [""]
        for length in range(max_len + 1):
            for prog in level:
                r = run_bounded(prog, input_data, max_steps)
                catalog.append(
                    {
                        "program": prog,
                        "output": r.output,
                        "steps": r.steps,
                        "terminated": r.terminated,
                        "stop_reason": r.stop_reason,
                        "final_a": r.final_a,
                        "final_pc": r.final_pc,
                        "final_d": r.final_d,
                    }
                )
            if length < max_len:
                nxt = []
                for prog in level:
                    for cand in valid_opcode_chars(len(prog)):
                        nxt.append(prog + cand["char"])
                level = nxt

        self.catalog_cache[cache_key] = catalog
        if cache_file:
            os.makedirs(os.path.dirname(cache_file), exist_ok=True)
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(catalog, f, ensure_ascii=False)
        return catalog

    def scan_prefix_family(
        self,
        prefix: str,
        suffix_len: int,
        input_data: str = "",
        max_steps: int = 3000,
        target_output: Optional[str] = None,
    ) -> List[dict]:
        """Evaluate every valid suffix for a fixed program prefix.

        This is a structured alternative to global enumeration. A suffix of
        length ``n`` has at most 8**n candidates, and each result keeps the
        same evidence fields as catalog entries. If ``target_output`` is
        supplied, only exact matches are returned.
        """
        if suffix_len < 0:
            raise ValueError("suffix_len must be non-negative")

        levels = [valid_opcode_chars(pos) for pos in range(len(prefix), len(prefix) + suffix_len)]
        results: List[dict] = []
        for suffix_parts in itertools.product(*levels) if levels else [()]:
            program = prefix + "".join(part["char"] for part in suffix_parts)
            result = run_bounded(program, input_data, max_steps)
            if target_output is not None and result.output != target_output:
                continue
            results.append(
                {
                    "program": program,
                    "output": result.output,
                    "steps": result.steps,
                    "terminated": result.terminated,
                    "stop_reason": result.stop_reason,
                    "final_a": result.final_a,
                    "final_pc": result.final_pc,
                    "final_d": result.final_d,
                }
            )
        return results

    def catalog_exact_match(self, target: str, max_len: int = 4, input_data: str = "") -> Optional[dict]:
        catalog = self.build_catalog(max_len=max_len, input_data=input_data)
        for entry in catalog:
            if entry["output"] == target:
                return entry
        return None

    def catalog_best_match(self, target: str, max_len: int = 4, input_data: str = "") -> dict:
        catalog = self.build_catalog(max_len=max_len, input_data=input_data)
        best = None
        best_score = -1
        for entry in catalog:
            r = RunResult(
                program=entry["program"],
                output=entry["output"],
                steps=entry["steps"],
                stop_reason=entry["stop_reason"],
                terminated=entry["terminated"],
                final_a=entry["final_a"],
                final_pc=entry["final_pc"],
                final_d=entry["final_d"],
            )
            score = fitness(r, target)
            if score > best_score:
                best_score = score
                best = entry
        return best or {"program": "", "output": "", "steps": 0, "terminated": False}

    def catalog_summary(self, max_len: int = 4, input_data: str = "") -> dict:
        catalog = self.build_catalog(max_len=max_len, input_data=input_data)
        outputs = [e["output"] for e in catalog]
        terminated = sum(1 for e in catalog if e["terminated"])
        distinct_outputs = set(outputs)
        longest = max(outputs, key=len) if outputs else ""
        return {
            "programs_evaluated": len(catalog),
            "distinct_outputs": len(distinct_outputs),
            "terminated": terminated,
            "longest_output": longest,
            "longest_output_len": len(longest),
        }

    # ------------------------------------------------------------------
    # Beam search
    # ------------------------------------------------------------------

    def _diverse_seeds(self, target: str, k: int = 64, max_len: int = 5, input_data: str = "") -> List[str]:
        """Pick the top-k catalog programs, keeping behavioral diversity.

        Deduplicates by (output, final_a % 256) so the beam starts from
        distinct behavioral families instead of many copies of the same idiom.
        """
        catalog = self.build_catalog(max_len=max_len, input_data=input_data)
        scored = []
        for entry in catalog:
            r = RunResult(
                program=entry["program"],
                output=entry["output"],
                steps=entry["steps"],
                stop_reason=entry["stop_reason"],
                terminated=entry["terminated"],
                final_a=entry["final_a"],
                final_pc=entry["final_pc"],
                final_d=entry["final_d"],
            )
            scored.append((fitness(r, target), entry))
        scored.sort(key=lambda t: t[0], reverse=True)

        seeds: List[str] = []
        seen_buckets = set()
        for score, entry in scored:
            if len(seeds) >= k:
                break
            bucket = (entry["output"], entry["final_a"] % 256)
            if bucket in seen_buckets:
                continue
            seen_buckets.add(bucket)
            seeds.append(entry["program"])
        return seeds

    def _diverse_guided_seeds(self, target: str, k: int, max_len: int, input_data: str) -> List[str]:
        """Select guided seeds while retaining distinct machine states."""
        catalog = self.build_catalog(max_len=max_len, input_data=input_data)
        scored = []
        for entry in catalog:
            result = RunResult(
                program=entry["program"], output=entry["output"], steps=entry["steps"],
                stop_reason=entry["stop_reason"], terminated=entry["terminated"],
                final_a=entry["final_a"], final_pc=entry["final_pc"], final_d=entry["final_d"],
            )
            scored.append((guided_fitness(result, target), entry))
        scored.sort(key=lambda item: item[0], reverse=True)

        seeds: List[str] = []
        seen = set()
        for _, entry in scored:
            bucket = (entry["output"], entry["final_a"] % 256,
                      entry["final_d"] % 256, entry["final_pc"] % 256)
            if bucket in seen:
                continue
            seen.add(bucket)
            seeds.append(entry["program"])
            if len(seeds) >= k:
                break
        return seeds

    def synthesize(
        self,
        target_output: str,
        input_data: str = "",
        beam_width: int = 64,
        max_len: int = 48,
        max_evals: int = 200_000,
        max_steps: int = 20_000,
        seed: Optional[int] = None,
        progress_cb: Optional[Callable[[dict], None]] = None,
        catalog_len: int = 5,
        guided: bool = False,
    ) -> SynthesisReport:
        start = time.perf_counter()
        rng = random.Random(seed)
        report = SynthesisReport(
            target=target_output,
            input_data=input_data,
            success=False,
        )

        exact = self.catalog_exact_match(target_output, max_len=catalog_len, input_data=input_data)
        if exact:
            report.success = True
            report.program = exact["program"]
            report.output = exact["output"]
            report.steps = exact["steps"]
            report.catalog_hit = True
            report.notes = "exact catalog hit"
            report.elapsed_s = time.perf_counter() - start
            return report

        if guided:
            frontier = self._diverse_guided_seeds(
                target_output, k=beam_width, max_len=catalog_len, input_data=input_data
            )
        else:
            frontier = self._diverse_seeds(
                target_output, k=beam_width, max_len=catalog_len, input_data=input_data
            )
        if not frontier:
            frontier = [""]
        best_prog = ""
        best_output = ""
        best_score = -1
        evals = 0
        stall = 0
        length_exhausted = True

        # Keep the strongest seed as a valid incumbent. Without this, a
        # guided extension could replace a useful partial output with a
        # lower-prefix candidate merely because its register is promising.
        for seed_program in frontier:
            seed_result = run_bounded(seed_program, input_data, max_steps)
            evals += 1
            seed_score = guided_fitness(seed_result, target_output) if guided else fitness(seed_result, target_output)
            if seed_score > best_score:
                best_score = seed_score
                best_prog = seed_program
                best_output = seed_result.output
            if seed_result.output == target_output:
                report.success = True
                report.program = seed_program
                report.output = seed_result.output
                report.steps = seed_result.steps
                report.evaluations = evals
                report.best_prefix = len(target_output)
                report.notes = "seed exact match"
                report.elapsed_s = time.perf_counter() - start
                return report

        for length in range(0, max_len):
            candidates: List[tuple] = []
            for prog in frontier:
                for cand in valid_opcode_chars(len(prog)):
                    candidate = prog + cand["char"]
                    r = run_bounded(candidate, input_data, max_steps)
                    evals += 1

                    if r.output == target_output:
                        report.success = True
                        report.program = candidate
                        report.output = r.output
                        report.steps = r.steps
                        report.evaluations = evals
                        report.best_prefix = len(target_output)
                        report.notes = f"found at length {len(candidate)}"
                        report.elapsed_s = time.perf_counter() - start
                        return report

                    score = guided_fitness(r, target_output) if guided else fitness(r, target_output)
                    if score > best_score:
                        best_score = score
                        best_prog = candidate
                        best_output = r.output
                    candidates.append((score, candidate))

                    if evals >= max_evals:
                        break
                if evals >= max_evals:
                    break
            if evals >= max_evals or not candidates:
                length_exhausted = False
                break

            candidates.sort(key=lambda t: t[0], reverse=True)
            next_frontier = [c[1] for c in candidates[:beam_width]]

            if progress_cb:
                progress_cb(
                    {
                        "length": length + 1,
                        "evals": evals,
                        "best_prefix": prefix_score(best_output, target_output),
                        "best_program": best_prog,
                        "best_output": best_output,
                    }
                )

            if best_score <= candidates[0][0]:
                stall += 1
            else:
                stall = 0

            frontier = next_frontier

            if prefix_score(best_output, target_output) == len(target_output):
                report.success = True
                report.program = best_prog
                report.output = best_output
                report.steps = run_bounded(best_prog, input_data, max_steps).steps
                report.evaluations = evals
                report.best_prefix = len(target_output)
                report.notes = "full prefix matched during search"
                report.elapsed_s = time.perf_counter() - start
                return report

            if stall >= 4:
                next_char = rng.choice(valid_opcode_chars(len(best_prog)))["char"]
                frontier = [best_prog + next_char]
                stall = 0

        report.program = best_prog
        report.output = best_output
        report.evaluations = evals
        report.best_prefix = prefix_score(best_output, target_output)
        if length_exhausted:
            report.notes = f"length limit ({max_len}) reached; best partial match reported"
        elif evals >= max_evals:
            report.notes = "evaluation budget exhausted; best partial match reported"
        else:
            report.notes = "no candidates; best partial match reported"
        report.elapsed_s = time.perf_counter() - start
        return report

    def verify(self, program: str, test_cases: List[tuple], max_steps: int = 20000) -> dict:
        """Verify a synthesized program against (input, expected) cases."""
        cases = evaluate_io(program, test_cases, max_steps)
        return {
            "program": program,
            "program_sha256": hashlib.sha256(program.encode()).hexdigest(),
            "cases": cases,
            "all_pass": all(c["match"] for c in cases.values()),
        }


def materialize_relations(relations, target_state):
    """Helper function to materialize a list of relations."""
    m = Materialization(relations=relations)
    return m.materialize(target_state=target_state)


def verify_materialization(program, relations, target_state):
    """Verify that a materialized program satisfies the relations."""
    target_output = target_state.output_buffer.decode(errors="replace")
    r = run_bounded(program)
    matched = prefix_score(r.output, target_output)
    return {
        "program": program,
        "output": r.output,
        "target": target_output,
        "prefix_matched": matched,
        "satisfied": matched == len(target_output) or r.output == target_output,
    }
