# Autobolge

![Autobolge relational synthesis](assets/autobolge.gif)

**Autobolge is an evidence-first relational synthesizer for Malbolge.**

It searches for Malbolge programs from behavioral relations, executes every
candidate through a canonical debugger, and verifies the resulting program
against explicit I/O cases. The project combines exhaustive short-program
catalogs, state-aware beam search, structured family scans, and reproducible
verification artifacts.

## Why It Matters

Malbolge is deliberately hostile to ordinary program synthesis: its memory is
self-modifying, instruction decoding depends on program position, and small
source changes can destroy an otherwise useful behavior. Autobolge treats that
behavior as a relational search problem instead of relying on hand-written
programs.

## Verified Results

The current reproducible demo demonstrates:

- 299,593 valid programs indexed through length 6.
- 802 distinct observed outputs in that catalog.
- Automatic one-character echo synthesis: `ub`.
- Automatic two-character prefix echo synthesis: `ubs``.
- `ubs`` verified for `AB -> AB`, `HI -> HI`, and `XYZ -> XY`.
- Canonical `Hello, world.` execution verified through the real interpreter.
- Structured exploration of the canonical `(=<` Malbolge family.

The synthesizer does **not** yet claim arbitrary text synthesis. For example,
the current evidence shows that `HI` without input is not found through the
complete valid program space up to length 7; that negative result is retained
as part of the research record rather than hidden.

## Quick Start

```bash
pip install malbolge pillow
python experiments/relational_synthesis_demo.py
```

The demo loads the persisted catalog under `experiments/catalog_cache/`, runs
exact and guided synthesis, verifies the generated programs, and checks the
canonical Hello World program.

## Architecture

| Module | Purpose |
| --- | --- |
| `relational/execution.py` | Bounded canonical execution and fitness functions |
| `relational/transition.py` | Valid opcode transitions and debugger snapshots |
| `relational/materialization.py` | Catalogs, structured family scans, beam synthesis |
| `relational/relation.py` | Declarative state and I/O relations |
| `relational/search.py` | Relational search API |
| `runner/interpreter.py` | Classic Malbolge interpreter wrapper |
| `experiments/relational_synthesis_demo.py` | Reproducible evidence demo |

## Evidence Policy

Every reported program is re-executed before it is called successful. Reports
include exact outputs, step counts, stop reasons, and program SHA-256 hashes.
The project reports both successful constructions and search limits.

## Status

Research prototype. The short-program synthesizer and verification pipeline are
working; longer multi-character output synthesis remains the frontier.

## License

MIT. See `LICENSE` when present.
