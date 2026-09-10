# Procedencia semántica

La semántica CURRENT de Autobolge es Classic densa, implementada por
`zig/vm.zig` y reflejada por `relational/classic.py`. El paquete Python
`malbolge` y su `SparseMemory` ya no son autoridad de ejecución; la evidencia
que los usó permanece HISTÓRICA.

La autoridad externa es el `engine.zig` de Malbolge-Translator. Autobolge lo
trata como solo lectura y registra su remoto, commit, dirty-state y SHA-256 en
el manifiesto semántico de cada artefacto dataflow.

## Manifiesto semántico v1

`quine_research/dataflow/semantic_manifest.py` construye
`autobolge-semantic-manifest/v1`. Incluye, sin rutas absolutas:

- epoch y contrato Classic (input real, bajoflujo termina, inválidas son NOP);
- Git commit/remoto/diff hash de las fuentes semánticas de Autobolge y de la
  autoridad;
- hashes de las fuentes Zig/Python que afectan ejecución y dataflow;
- hash del binario Zig y catálogo cuando existen;
- versión de Zig, Python, OS y arquitectura.

Su SHA-256 entra en la clave de cada stage y el manifiesto completo se persiste
en `_meta` del artefacto. Un cambio a VM, binario, toolkit, catálogo o entorno
relevante ya no puede reutilizar silenciosamente una corrida anterior.

## Componentes propios

- `relational/classic.py` — referencia Classic densa y debugger.
- `relational/execution.py` — ejecución bounded y bulk de referencia.
- `relational/materialization.py` — catálogo, familias y síntesis.
- `relational/transition.py` / `relational/search.py` — superficies v1 de
  transiciones; no son todavía anchors epochales v2.
- `runner/interpreter.py` — wrapper de intérprete Classic.
