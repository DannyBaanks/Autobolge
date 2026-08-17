# Provenance

## New Autobolge Components

- `relational/state.py` - compact Malbolge state representations
- `relational/transition.py` - valid opcode transitions and debugger snapshots
- `relational/relation.py` - declarative state and I/O relations
- `relational/composition.py` - relation composition
- `relational/materialization.py` - catalogs, family scans, and synthesis
- `relational/execution.py` - bounded canonical execution and evidence
- `relational/search.py` - relational search API
- `runner/interpreter.py` - classic Malbolge interpreter wrapper

## External Dependency

Autobolge uses the `malbolge` Python package as its execution backend. The
classic 10-trit interpreter and debugger are configured explicitly through
`SPARSE_CONFIG`; Malbolge20 is not used for the classic-language results in
this repository.

## Relationship To Malbolge-Translator

The sibling `Malbolge-Translator` project is a separate translator and remains
read-only from Autobolge's perspective. Autobolge does not modify its source,
backend, or generated artifacts. The two projects share the same research
interest but use different synthesis strategies.
