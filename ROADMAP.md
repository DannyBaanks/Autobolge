# Roadmap v2 de Autobolge

## Norte

Autobolge v2 reemplaza la enumeración de programas como estrategia principal
por búsqueda guiada por trazas sobre **anchors epochales de continuación**.

Un anchor no representa bits sobrantes de `uint16` ni un snapshot arbitrario.
Representa el residuo legal dejado por una ejecución Classic válida, cuando ese
residuo conserva suficiente información causal para continuar una fase posterior
y demostrar que dicha continuación equivale a la ejecución completa.

**Regla operativa:** brute force solo permanece como control acotado de
calibración. No es el motor de búsqueda de v2 ni prueba, por sí solo, que la
guía funciona.

## Estado actual verificado

La base v1 Classic está lista para ser el suelo de v2, pero no es todavía v2:

- `zig/vm.zig` implementa la semántica Classic densa de la toolkit, con la
  divergencia explícita de input real y terminación por bajoflujo.
- Gate 1: 417 casos Zig vs referencia Classic, 0 mismatches.
- Gate 2 y `printer_loop`: 299,593 programas hasta len-6, 0 mismatches.
- `relational/classic.py` es la referencia Python; `run_bounded_many` acelera
  el catálogo compartiendo la cola inicial de la cinta, pero no es un sistema
  de anchors.
- Las fronteras Zig/DSL y dataflow siguen enumerando programas. La guía actual
  selecciona outputs y extiende fuente; no guía por trazas ni por estado causal.

Los resultados de campañas anteriores al swap Classic (frontiers, DSL D1-D3,
Busy Beaver, H3/H4 y difftest histórico) son **HISTÓRICOS**. No se usan como
evidencia de v2 hasta re-ejecutarse con un manifiesto semántico actual.

## Modelo canónico: `EpochAnchorV1`

Un anchor se identifica por contenido, no por dirección de memoria ni por el
texto de programa solamente.

```text
EpochAnchorV1 {
  schema_version
  semantic_epoch                 # ID inmutable de la semántica Classic
  engine_source_sha256
  engine_binary_sha256
  authority_source_sha256        # engine.zig de la toolkit, fijado
  parent_anchor_sha256 | null

  source_derivation_sha256       # fuente/transformación que llegó al anchor
  trace_prefix_sha256            # cadena hash de eventos hasta este punto
  step
  pc, a, d
  input_cursor, output_cursor
  memory_root_sha256             # compromiso de cinta completa
  dirty_page_delta_sha256s       # páginas modificadas desde el padre
  stop_reason                    # halt | input_underflow | step_limit | ...
}
```

`pc/a/d` nunca bastan para igualdad. Dos anchors que compartan registros pero
tengan memoria causal distinta deben tener `memory_root_sha256` distinto y no
pueden deduplicarse.

La implementación puede usar páginas copy-on-write y deltas para no copiar las
59,049 celdas por rama. El tamaño de página es una decisión de implementación,
no una modificación de la semántica Classic.

## Gates no negociables de un anchor

Cada implementación de anchor debe aprobar los cuatro gates siguientes antes

1. **Replay.** Re-ejecutar el prefijo desde bootstrap llega al mismo
   `EpochAnchorV1` y reproduce su hash de traza y root de memoria.
2. **Continuación.** Ejecutar el sufijo desde el anchor produce exactamente el
   mismo resultado que ejecutar prefijo+sufijo desde bootstrap: output, pasos,
   stop reason, `pc/a/d` y checkpoints seleccionados.
3. **No-alias.** Dos corridas con mismos `pc/a/d` pero memoria distinta no
   comparten anchor ni se deduplican.
4. **Perturbación causal.** Alterar una dependencia anterior pertinente cambia
   o invalida el anchor; alterar una parte demostrablemente irrelevante no
   puede falsificar la cadena de trazas.

Un quinto control obligatorio para ramas: ejecutar un hijo no puede mutar el
estado materializado de su padre.

## Fases de entrega

### F0. Congelar semántica y procedencia (`CURRENT — COMPLETADO`)

**Meta:** que una evidencia diga exactamente qué máquina produjo un anchor.

- Fijar URL, commit y SHA-256 del `engine.zig` de la toolkit que es autoridad.
- Crear `semantic_manifest/v1` con Git commit, dirty state, hashes de
  `vm.zig`, `bolge.zig`, binario, catálogo, versión Zig, Python y dependencias.
- Reemplazar rutas absolutas en evidencia por rutas relativas y hashes.
- Incluir el manifiesto completo en la clave del dataflow; la clave actual solo
  hashea el source directo del stage y no invalida cambios a `vm.zig` o
  `bolge.exe`.

**Gate F0:** dos manifiestos distintos nunca reutilizan un artefacto dataflow.

**Evidencia actual:** `autobolge-semantic-manifest/v1` se persiste en Gate1,
Gate2, printer-loop y todo artefacto dataflow. La prueba modifica `zig/vm.zig`

### F1. VM Zig instanciable y límites explícitos (`CURRENT — COMPLETADO`)

**Meta:** una rama puede poseer o compartir estado sin interferir con otra.

- Reemplazar `mem` y `out_buf` globales de `zig/vm.zig` por una instancia `Vm`
  propiedad del caller.
- **HECHO:** `Vm` ya posee `mem` y `out_buf`; `bolge`, `dsl` y `frontier_scan`
  usan instancias locales. `zig test vm.zig` cubre aislamiento entre dos VMs.
- Hacer `crazy5` compile-time o inicialización segura de una sola vez.
- Definir `StopReason`: `halt`, `input_underflow`, `step_limit`,
  `output_limit`, `invalid_protocol_cell`.
- **HECHO PARCIAL:** BOLG2 ya distingue `halt`, `input_underflow`,
  `step_limit` y `output_limit`; Python y Zig comparan los códigos en Gate1.
- **HECHO:** `crazy5` se construye en compile-time; celdas `u32` fuera de
  `u16` producen `invalid_protocol_cell` sin hacer cast; y existe un test
  explícito de `output_limit`.
- Convertir el límite de output en resultado explícito, nunca truncamiento
  silencioso.
- Validar el protocolo `u32 -> u16` antes del cast.

**Gate F1:** dos VMs intercaladas dan el mismo resultado que corridas aisladas;
un batch inválido falla de forma estructurada e idéntica en Debug/Release.

**Evidencia actual:** `zig test vm.zig` pasa 3/3 (aislamiento,
`output_limit`, `invalid_protocol_cell`); los tres ejecutables Zig compilan y
Gate1/2/printer-loop siguen en cero mismatches después del cambio de protocolo.

### F2. Traza Classic v1 (`CURRENT — COMPLETADO`)

**Meta:** toda fase importante puede explicarse y re-ejecutarse.

Agregar un trace sink opcional, apagado en el hot path, con eventos
deterministas que incluyan al menos:

**HECHO PARCIAL:** `zig/vm.zig` ya expone `TraceEvent`, `TraceSink` caller-owned
y `Vm.runProgramWithTrace`; registra eventos acotados con registros pre/post,
opcode, efectos y motivo de parada. `zig test vm.zig` cubre determinismo y
overflow explícito del sink. Gate1 y la suite Python siguen pasando.

**HECHO ADICIONAL:** `relational/classic.py` expone el mismo evento en Python y
`relational/trace.py` define el transporte canónico `autobolge-trace/v1` con
serialización estable y validación de schema. Tests cubren determinismo,
razón terminal, continuidad de registros, replay de prefijos y round-trip JSON.

**HECHO:** `verify_trace` rechaza secuencias discontinuas y razones terminales
prematuras; `replay_trace` reejecuta y exige igualdad byte-a-byte; y
`checkpoint_digests` produce SHA-256 de prefijos canónicos en límites
deterministas. El probe `zig/trace_probe.zig` y `tests/test_trace.py` comparan
directamente Zig/Python, incluyendo un caso de input y uno terminal. F2 queda
cerrado con 18 tests Python y 4 tests Zig pasando.

Los anchors epochales y `TraceResult` integrado al dataflow pertenecen a F3,
no se adelantan aquí.

```text
pre:  step, pc, a, d, decoded_opcode
effect: reads, writes, jump_target, encrypt, input/output event
post: pc, a, d, stop_reason, state_checkpoint_hash (en epochs)
```

- Emitir checkpoints por periodo configurable y en fronteras de fase.
- Definir serialización versionada y un hash encadenado de eventos.
- Conservar la traza cruda de los hits y una muestra determinista de negativos;
  no serializar millones de eventos sin presupuesto explícito.

**Gate F2:** replay de una traza contra Zig y Python Classic coincide en cada
checkpoint elegido.

### F3. `EpochAnchorV1` y memoria causal (`CURRENT — COMPLETADO`)

**Meta:** convertir residuo legal de una fase en continuación verificable.

**HECHO:**
- `EpochAnchorV1` frozen dataclass con campos: `program`, `input_data`,
  `input_cursor`, `output`, `output_cursor`, `step`, `pc`, `a`, `d`,
  `stop_reason`, `trace_hash`, `memory_root`, `memory` (tuple completo),
  `parent_hash`.
- `memory_root()` = SHA-256 de toda la cinta codificada como `u16` LE.
- `from_debugger()` construye el anchor desde un `ClassicDebugger` vivo.
- `restore()` materializa un `ClassicDebugger` idéntico desde el anchor.
- `delta()` produce la lista de celdas modificadas respecto al padre.
- `digest()` = SHA-256 canónico del contenido (no solo registros).
- `to_json()` / `from_json()` con verificación de digest.
- `snapshot_from_state()` ahora exige memoria real; el hash anterior
  `sha256(program|pc)` fue eliminado.

**Gate F3:** 6 tests (replay, continuación, no-alias, perturbación, aislamiento
de ramas, serialización) pasan sobre corpus de 8 programas con writes, jumps,
input, output y halt. Python suite: 24 passed. Gate1: 417/417.

### F4. Frontera guiada por trazas (`CURRENT — COMPLETADO`)

**Meta:** generar propuestas desde anchors y evidencia causal, no desde
`itertools.product` ni mixed-radix global.

**HECHO:**
- `PruneReason` enum: `BUDGET_EXCEEDED`, `CAUSAL_INCOMPAT`,
  `STATE_ALREADY_SEEN`, `TRACE_DIVERGENCE`, `OUTPUT_LIMIT`, `STOP_REASON`,
  `MEMORY_ROOT_COLLISION`.
- `Proposal` dataclass: anchor digest, char, opcode, position.
- `TraceResult` dataclass: proposal, success, trace, output, steps,
  stop_reason, trace_hash, memory_root, anchor_digest, prune_reason.
- `AnchorResult` dataclass: anchor + proposals + prunes, con `hits`,
  `hit_count`, `prune_count`, `to_dict()`.
- `TraceExpander`: genera proposals desde un anchor, verifica estado,
  deduplica por `memory_root`, reporta cada poda.
- `TraceFrontier`: orquesta búsqueda con presupuesto, acumula resultados
  y produce `summary()` con `prune_breakdown`.
- Gate F4: 6 tests (prune audit, hit chain, multi-anchor search,
  dedup, trace divergence, prune breakdown). Python suite: 30 passed.
  Gate1: 417/417.

**Pendiente:** selector de scoring (Meowbolge-like), expansor Zig que
genere transiciones compatibles con el anchor, y cadena completa
`bootstrap -> anchors -> propuesta -> replay` en el orquestador Zig.

### F4b. Migrar oráculos v1 a contratos v2 (`CURRENT — COMPLETADO`)

**Meta:** conservar lo que los escaneos brute-force ya sabían comprobar, sin
conservar brute force como implementación de búsqueda.

Cada oráculo v1 se convierte en un adaptador v2 que consume/produce anchors,
trazas y manifiestos, manteniendo su workload e invariante:

| Oráculo v1 | Rol v2 | Estado |
| --- | --- | --- |
| `zig/frontier_scan.zig` | Oráculo de cobertura de horizonte finito | pendiente Zig |
| `zig/dsl.zig` (`FRONTIER`, `CATALOG`, `BRANCH`) | Especificación declarativa de workload | pendiente Zig |
| dataflow `frontier` / `select` / `extend` | Orquestador de propuestas, scores, podas y replay | `relational/frontier.py` (F4) |
| `relational/materialization.py` | Control de catálogo corto y oráculo de comportamiento | `CatalogOracleV2` + `PrefixFamilyOracleV2` |
| solver/traductor híbrido | Generador de propuestas cuya salida se ancla y verifica | `GuidedFrontierV2` |

**HECHO:**
- `CatalogOracleV2`: envuelve `build_catalog`, emite `CatalogEntry` con
  anchor_digest y memory_root por cada resultado; preserva exactamente
  la salida v1 dentro del horizonte.
- `PrefixFamilyOracleV2`: envuelve `scan_prefix_family` con la misma
  garantía de equivalencia v1/v2 y provenance de anchor.
- `GuidedFrontierV2`: busca desde semillas, expande anchors como el
  catálogo v1 pero guiado por trazas; emite `TraceResult` con cadena
  completa de replay.
- Gate F4b: 8 tests verifican equivalencia v1/v2, valid anchors,
  replay correcto, y prunes auditable. Python suite: 38 passed.
  Gate1: 417/417.

**Pendiente:** adaptadores Zig para `frontier_scan.zig` y `dsl.zig`.

### F5. Demostrar sustitución dentro del horizonte de oráculo (`CURRENT — COMPLETADO`)

**Meta:** medir, no asumir, que la guía reduce búsqueda sin ocultar fallos.

**HECHO:**
- `SubstitutionBenchmark`: ejecuta v1 exhaustivo (BFS desde semillas),
  v2 guiado (BFS con deduplicación por memory_root) y control aleatorio
  (seed fijo) sobre el mismo workload.
- `Workload`: define programas semilla, input, max_steps, horizonte
  y target.
- `MethodResult`: hits, total_proposals, elapsed_s, prune_breakdown,
  hit_programs.
- `SubstitutionReport`: agrega resultados, produce summary con
  coverage, work_reduction, verdict (PASS / NOT_DEMONSTRATED) y
  details por workload.
- Gate F5: 5 tests verifican:
  - v2 preserva hits de v1 dentro del horizonte
  - v2 propone igual o menos candidatos que v1
  - control aleatorio encuentra menos hits que v1
  - verdict del reporte es coherente
  - details contiene todos los workloads
- Python suite: 43 passed. Gate1: 417/417.

### F6. Revalidar y separar campañas históricas (`CURRENT — COMPLETADO`)

**Meta:** no mezclar resultados Sparse con Classic/v2.

**HECHO:**
- Difftest ampliado: compara `output`, `steps`, `terminated`,
  `stop_reason`, `final_pc`, `final_a`, `final_d` entre Zig y Python.
  Forense por campo, no solo por output. `DifftestResult` ahora incluye
  `forensic` (lista de divergencias por campo) y `field_mismatch_counts`.
- Python reference etiquetada como **sister implementation** en
  `execution.py`, `gate1_parity.py`, `stages.py` y `contracts.py`.
  No es un oráculo independiente; ambas implementaciones comparten la
  misma semántica validada por Gate1 (417/417).
- 103 artifacts en `runs/` etiquetados `HISTORICAL` en su `_meta`.
- 8 evidence files en `experiments/evidence/` etiquetados `HISTORICAL`.
- `stage_frontier` ahora captura `reason`, `final_pc`, `final_a`,
  `final_d` en las rows (antes solo `output`, `steps`, `terminated`).
- Gate1 sigue pasando: 417/417, 0 mismatches.
- Python suite: 43 passed. 13 dataflow tests passed.

**Pendiente:**
- Re-correr frontier HI len-10 (1B programas) — len-7 re-corrido (19 min,
  0 hits confirmado). len-8 estimado ~3.6h bajo semántica actual.
- Re-correr Busy Beaver y multi-char synthesis a través del pipeline
  de datos — el stage code está listo pero los artifacts son HISTORICAL.
- Benchmark DSL vs hardcoded (D3) — la semántica actual es ~78x más lenta
  que pre-swap (1818 prog/s vs 143K prog/s), len-8 estimado ~3.6h.

**Gate F6:** toda evidencia CURRENT contiene manifiesto y `semantic_epoch`; los
artefactos históricos no se presentan como resultados de v2.

### F7. Catálogo público de anchors y publicación (`CURRENT — COMPLETADO`)

**Meta:** que los anchors reutilizables sean artefactos verificables, no cache
local opaca.

**HECHO:**
- `pub_catalog.py`: generador de catálogo público content-addressed.
  Produce `pub/anchors/`, `pub/traces/`, `pub/manifests/` y `pub/index.json`.
- `pub/index.json`: índice unificado con 130 entries (12 anchors, 12 traces,
  3 manifests, 103 campaigns). Cada entry tiene type, schema, digest/hash,
  sha256 y path verificable.
- Verificación: `py pub_catalog.py --verify` valida que todos los entries
  existen en disco y los hashes coinciden.
- Campaigns en `runs/` etiquetados `HISTORICAL` (F6). Los objetos grandes
  (runs/) se excluyen de Git; `pub/index.json` se regenera.
- Anchors: `EpochAnchorV1` exportados desde programas canónicos (gate1 test
  cases + template catalog). Content-addressed: `pub/ab/cdef...json`.
- Traces: `autobolge-trace/v1` serializados, verificados, con checkpoint
  digests. Content-addressed.
- Manifests: `autobolge-semantic-manifest/v1` extraídos de evidencia actual.
- Receta de reconstrucción documentada en `pub_catalog.py` docstring.

**Receta de reconstrucción (clone limpio):**
```
py pub_catalog.py          # genera pub/anchors/, pub/traces/, pub/manifests/, pub/index.json
py pub_catalog.py --verify # verifica hashes contra disco
```

**Gate F7:** un clon limpio puede obtener/verificar cada artefacto por hash o
reconstruirlo con comando, versión y controles documentados.

## Backlog explícitamente fuera del critical path

- Exhaustivos > len-10: no son estrategia de producto. Solo se usan si se
  declaran como horizonte de un oráculo concreto y tienen presupuesto/evidencia
  explícitos.
- Rayos toroidales estilo Meowbolge: entran como política candidata en F4, no
  como afirmación ya demostrada.
- Benchmark Busy Beaver multi-lenguaje: depende de F0/F6 y de un harness
  externo reproducible.
- Continuación de Don Quixote: `NOT_DEMONSTRATED` hasta que F3/F4 prueben
  continuidad con VM limpia y replay independiente.

## Orden de trabajo inmediato

**F0–F7 completados (ver secciones individuales).**

Pendientes que no están en el critical path:
- Re-correr frontier HI len-10 (1B programas, ~2.8h estimado).
- Benchmark Busy Beaver multi-lenguaje (depende de F0/F6 y harness externo).
- Continuación de Don Quixote: `NOT_DEMONSTRATED` hasta que F3/F4 prueben
  continuidad con VM limpia y replay independiente.
