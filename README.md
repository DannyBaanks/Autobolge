# Autobolge

![Autobolge relational synthesis](assets/autobolge.gif)

**Autobolge es un sintetizador relacional de Malbolge orientado a evidencia.**

Hoja de ruta de la campaña: [ROADMAP.md](ROADMAP.md).

Busca programas de Malbolge a partir de relaciones de comportamiento, ejecuta
cada candidato a través de un depurador canónico y verifica el programa
resultante contra casos I/O explícitos. El proyecto combina catálogos
exhaustivos de programas cortos, búsqueda de haz con estado, escaneos
estructurados por familia y artefactos de verificación reproducibles.

> **Cambio de semántica (septiembre 2026):** el motor Zig (`zig/vm.zig`) y la
> referencia Python abandonaron la semántica `SparseMemory` del paquete
> `malbolge` y ahora implementan la **semántica Classic densa** del motor de la
> toolkit (`engine.zig`, Malbolge-Translator), que es la autoridad.
> Consecuencia directa: el catálogo de referencia (299,593 moldes) se
> **regeneró** bajo la semántica nueva; los conteos que salieron de la
> semántica vieja (por ejemplo "802 outputs distintos" en el catálogo) quedan
> marcados abajo como `HISTÓRICO`.

---

## Por qué importa

Malbolge es deliberadamente hostil a la síntesis ordinaria de programas: su
memoria se auto-modifica, la decodificación de instrucciones depende de la
posición y un cambio minúsculo puede destruir un comportamiento útil.
Autobolge trata ese comportamiento como un problema de búsqueda relacional en
lugar de depender de programas escritos a mano.

**Idea clave:** los traductores Malbolge→C existentes restauran la memoria a su
estado original **después de cada instrucción**. El printer-loop / síntesis de
moldes de Autobolge avanza **varios pasos antes de restaurar** — un enfoque
fundamentalmente distinto que habilita la síntesis relacional a partir de
clases de equivalencia de comportamiento.

---

## Resultados verificados

### Migración a la semántica Classic densa (`CURRENT` — 2026-09)

- `zig/vm.zig` reescrito como port denso del `engine.zig` de la toolkit:
  cinta de 59049 celdas rellenada por la recurrencia crazy, decodificación
  `(cell+pc)%94` con ensanchamiento sobre los 94 imprimibles, celdas
  inválidas → **NOP** (ya no terminan la ejecución), input real con
  **terminación por bajoflujo**, encrypt/rotate/incremento de punteros
  después de cada paso. `bolge.exe` y `frontier_scan.exe` recompilados.
- Referencia Python: `relational/classic.py` (`ClassicDebugger`, máquina
  Classic densa) anclada en las primitivas de la toolkit
  (`crazy_operation`, `ENCRYPTION_TRANSLATE`); `run_bounded` y el bulk
  `run_bounded_many` comparten el **mismo bucle de pasos** (cero deriva).
- **Optimización del relleno (`run_bounded_many`)**: la cola de la cinta a
  partir de la posición `n` depende solo de las dos últimas celdas, así que se
  computa **una vez por par** y se copia por programa. Fidelidad densa exacta
  (los writes de `op39`/`op62` mutan solo la copia local) verificada contra la
  referencia single: 0 mismatches.
- Rendimiento de la referencia: len≤5 de **614 s → 19.5 s**; el catálogo
  len-6 completo se construyó en **152 s** (antes proyectado ~80 min).
- **GATE1 PASSED**: 417 casos aleatorios, **0 mismatches**, 12.49 s
  (`experiments/evidence/gate1_parity.json`, sha `ead638ba0187…`).
- **GATE2 PASSED**: catálogo regenerado (`catalog_e6dfb345.json`,
  299,593 entradas) y reconstruido con el motor Zig: **0 mismatches**
  (`experiments/evidence/gate2_catalog.json`).
- **printer_loop GATE PASSED**: 299,593 moldes, **0 mismatches**, 111.37 s con
  el motor Zig (`experiments/evidence/printer_loop.json`).

### Catálogo y síntesis (Gates 1 y 2 — PASSED `CURRENT`)

- 299,593 programas válidos indexados hasta longitud 6.
- 1,705 outputs distintos en ese catálogo (semántica Classic; la semántica
  vieja daba 802 — `HISTÓRICO`); 294,606 terminan; 98,510 con salida no vacía.
- Síntesis de eco automática de un carácter: `ub` (`ub` + `A` → `'A'`, 20 pasos).
- Síntesis de eco de dos caracteres: `ubs`` → `AB`→`AB`, `HI`→`HI`,
  `XYZ`→`XY` (9/9/22 pasos).
- Ejecución del `Hello, world.` canónico a través del motor: 48 pasos
  `'Hello, world.'`, sha `3f98ae21fc3e1997`.
- Exploración estructurada de la familia canónica `(=<`.

### Motor Zig rápido — paridad semántica Classic (`CURRENT` 2026-09)

- `zig/bolge.zig` + `zig/vm.zig` replican la **semántica Classic densa** de la
  toolkit (autoridad), ya NO la semántica `SparseMemory` del paquete
  `malbolge` (overlay lazy crazy-fill por bloques de 243). Este swap fue
  deliberado: la semántica clásica de Malbolge es la del motor de referencia de
  la toolkit.
- Paridad: 417 casos de Gate 1 + los 299,593 moldes del catálogo, **0
  mismatches**.
- Reconstrucción len-6: **156.86 s** con `bolge.exe` (~1,910 programas/s) vs
  la referencia Classic tail-shared; len-5: referencia 19.51 s vs fast 27.74 s.
- Referencia single `run_bounded` == `run_bounded_fast` (verificado: Gate 1
  sobre 417 casos + len≤5 exhaustivo de 37,449 programas, 0 mismatches).

### Escaneos de frontera — negativos honestos (Gate D1 — `HISTÓRICO` pre-swap)

Escaneos negativos exhaustivos con el motor Zig: `HI` sin input **no** aparece
en todo el espacio de programas válidos a:

- Longitud 7: 2,097,152 programas (22.7 s Python → 2.7 s DSL)
- Longitud 8: 16,777,216 programas (170.7 s Python → 2.2 min DSL)
- Longitud 9: 134,217,728 programas (1,720 s Python → 14.7 min DSL)
- **Longitud 10: 1,073,741,824 programas — 2.85 h DSL, 0 hits**
  Evidencia: `experiments/evidence/frontier_HI_len10.json`
  (sha `2a31218d446c224b8a46536af24cff93ef94f2eba5a88e7f8843e17ef7cd2b44`)

Los negativos se conservan como evidencia
(`experiments/evidence/frontier_HI_len*.json`) en lugar de ocultarse: el
registro de investigación incluye tanto construcciones como límites.
**Nota:** estos resultados y sus hashes corresponden a la semántica vieja; su
re-corrida bajo semántica Classic sigue pendiente.

### DSL especializado — abstracción de costo cero (Gate D3 — `HISTÓRICO` pre-swap)

ISA de máquina de búsqueda mínima (programas `.bolge`) ejecutada por un
runtime Zig (`bolge-dsl.exe`) con primitivas que existen **solo** para esta
carga de trabajo: `FRONTIER`, `CATALOG`, `BRANCH`, `ENUMERATE`, `EXECUTE`,
`FILTER`, `DEDUP`, `EMIT`, `HASH`, `TRACE`.

| Workload | Zig hardcodeado | DSL (`bolge-dsl.exe`) | Overhead |
|----------|-----------------|----------------------|----------|
| len-8 (16.7M) | 134.6 s @ 124,651 p/s | 134.7 s @ 124,569 p/s | **0.07%** |
| Pico de memoria | 6.0 MB | 4.1 MB | — |

El DSL agrega **programabilidad a ~cero costo** porque cada primitiva mapea
1:1 a una operación nativa del runtime; no hay capa de intérprete de propósito
general. **Nota:** medido sobre el `vm.zig` pre-swap.

### Campañas del solver — generador híbrido + dataflow (H3/H4 — `HISTÓRICO` pre-swap)

El solver de quine-research (`quine_research/search_quine_malbolge/`) genera
programas de Malbolge para outputs objetivo vía el traductor del paquete
`malbolge`, verificado por lotes contra la VM Zig.

- **H3 memoización cross-target** — veredicto dividido. H3a SOPORTADO: la
  estructura compartida existe (12.9% de hits de caché, −15% evaluaciones
  sobre 676 targets ABC). H3b FALSADO: wall-clock sin cambio (83.1 s vs la
  banda baseline 79.3–83.7 s); el costo por nodo subió ~23% por el overhead de
  dict/hash. Se conserva como hook opt-in `shared_state_cache`.
- **H4 paralelización por target** — SOPORTADO. Con `random_seed=42` (antes se
  perdía silenciosamente) la generación es determinista: 2,730,128 nodos y
  programas byte-idénticos en todas las configuraciones de workers.
  676/676 match, 0 mismatched.

| Workers | Generación | Targets/s | Pico RSS por worker |
|---------|-----------|-----------|---------------------|
| 1 (serial) | 76.3 s | 8.9 | — |
| 2 | 44.6 s | 15.2 | 95 MB |
| 4 | 23.8 s | 28.4 | 161 MB |
| 6 | 18.0 s | 37.5 | 226 MB |
| 8 | 14.7 s | 45.9 | 294 MB |

Evidencia: `quine_research/search_quine_malbolge/results/h4_sweep.json` más los
bancos por configuración (`program_bank_ABC_zig*.json`).

### Orquestador dataflow (`quine_research/dataflow/` — `CURRENT`)

Autobolge ya no es una sola búsqueda: los nodos son contratos tipados
(`SearchResult → ClassifierResult → SelectionResult → TransformResult →
SolverResult → CompareResult → Verdict`), cada uno persistido como artefacto
explícito `runs/<pipeline>/<stage>__<hash>/artifact.json`. La identidad de
cada nodo es `sha256(params + hashes de artefactos upstream)` — los nodos sin
cambios se **saltan**, un cambio de params invalida solo la cadena
descendente. Los ejecutores se enrutan por nodo (`frontier` → lote Zig, el
resto → Python), cruzando la frontera de lenguaje por lote, nunca por
candidato.

- **Difftest multi-backend actualizado**: el backend Python de referencia es
  ahora `run_bounded` (semántica Classic densa), no el `MalbolgeInterpreter`
  del paquete `malbolge` (sparse, divergía del motor). La suite de pruebas
  pasa **12/12**.
- Plantilla de lente (`frontier_campaign.template.json`) con coordenadas
  lógicas (`L1/L2/L3` vía `--var`), rebase de ensamblajes y compartición de
  artefactos por hash.
- Campañas del roadmap sobre dataflow (`HISTÓRICO` pre-swap): síntesis
  multi-char 14/14, Busy Beaver len 1–3, composición de moldes (negativo
  estructural: la concatenación está dominada por prefijo), difftest multi-
  backend (428 casos comparables, 0 mismatches — con el intérprete viejo),
  guided vs brute force, Atlas (`runs/atlas_index.json`, 102 artefactos).

---

## Inicio rápido

```bash
# Demo Python (síntesis relacional, beam search, catálogo)
pip install malbolge pillow
python experiments/relational_synthesis_demo.py

# Motor Zig rápido (runner por lotes, paridad verificada)
cd zig
zig build-exe bolge.zig -O ReleaseFast "-femit-bin=bolge.exe"
.\bolge.exe in.bin out.bin 3000

# DSL especializado (escaneos de frontera en producción)
zig build-exe dsl.zig -O ReleaseFast "-femit-bin=bolge-dsl.exe"
.\bolge-dsl.exe ..\experiments\frontier_HI_len10.bolge

# Relación de input con múltiples casos acotados: una fuente debe cumplir TODOS.
.\bolge-dsl.exe ..\experiments\dsl_maldoom_input_branch_smoke.bolge
```

`zig` se resuelve desde el PATH (0.16.0 en esta máquina, instalado vía
WinGet); si prefieres un binario explícito, define la variable de entorno
`ZIG_EXE`.

La demo carga el catálogo persistido en `experiments/catalog_cache/`, corre
síntesis exacta y guiada, verifica los programas generados y compara el
programa canónico de Hello World.

---

## Arquitectura

```
┌─────────────────────────────────────────────────────────────────┐
│                      ISA DE MÁQUINA DE BÚSQUEDA                  │
│  programas .bolge: FRONTIER, CATALOG, ENUMERATE, EXECUTE, ...   │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    RUNTIME ZIG (bolge-dsl.exe)                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │ ENUMERATE    │  │ EXECUTE      │  │ EMIT + HASH  │           │
│  │ mixed-radix  │──▶│ vm.runProgram│──▶│ JSON + sha256│           │
│  │ char válido  │  │ (in-process) │  │ evidencia     │           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                      VM COMPARTIDA (vm.zig)                      │
│  • Cinta densidad Classic: 59049 celdas, recurrencia crazy      │
│  • Decode (cell+pc)%94 con ensanchamiento; inválidas → NOP      │
│  • Input real + bajoflujo → termina; op81 → termina             │
│  • Encrypt post-step (guardado 33..126), rotate, ++wrap         │
└────────────────────────────┬────────────────────────────────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
       bolge.exe         bolge-dsl.exe   printer_loop.py
       (CLI por lote)    (runtime DSL)    (gate oráculo)
```

### Mapa de módulos

| Módulo | Propósito |
| --- | --- |
| `zig/vm.zig` | **Fuente única de verdad** de la semántica Classic densa (autoridad: toolkit malbolge). Comparte bolge.exe / bolge-dsl.exe / frontier_scan.exe |
| `zig/bolge.zig` | CLI por lotes (`in.bin` → `out.bin`), importa `vm.zig` |
| `zig/dsl.zig` | Runtime de la ISA de búsqueda (parser + ejecutor `.bolge`) |
| `zig/frontier_scan.zig` | Baseline hardcodeado para benchmark |
| `relational/classic.py` | **Referencia**: `ClassicDebugger`, máquina Classic densa, `parse_cells`, `_compute_tail` (relleno compartido por par) |
| `relational/execution.py` | `run_bounded` (loop canónico único) + `run_bounded_many` (bulk tail-shared) |
| `relational/materialization.py` | Catálogos, escaneos de familia, síntesis por haz (engine = "fast"\|"reference") |
| `relational/fast_engine.py` | Wrapper Python → protocolo por lotes de `bolge.exe` |
| `relational/transition.py` | Descubrimiento de transiciones con `ClassicDebugger` |
| `experiments/printer_loop.py` | Gate de la impresora: recomprime `bolge.exe`, corre 299,593 moldes, 0 mismatches |
| `experiments/gate1_parity.py` | Gate 1: 417 casos aleatorios vs `run_bounded` |
| `experiments/gate2_catalog.py` | Gate 2: paridad de catálogo + rendimiento |
| `experiments/*.bolge` | Programas DSL (specs de búsqueda declarativas) |
| `quine_research/dataflow/` | Orquestador dataflow: nodos contrato, artefactos con hash, sin re-runs, ejecutores por nodo (Zig/Python), plantilla lente |
| `quine_research/search_quine_malbolge/` | Solver híbrido (generador traductor + verificación Zig por lote), `--workers N` |

---

## Política de evidencia

Cada programa reportado se re-ejecuta antes de llamarlo exitoso. Los reportes
incluyen outputs exactos, conteos de pasos, motivos de parada y SHA-256 del
programa. El proyecto reporta tanto construcciones exitosas como límites de
búsqueda.

Archivos de evidencia clave:

- `experiments/evidence/gate1_parity.json` — 417/417 paridad (Classic, sha `ead638ba…`)
- `experiments/evidence/gate2_catalog.json` — reconstrucción completa del catálogo (0 mismatches)
- `experiments/evidence/printer_loop.json` — verificación molde a molde (0/299,593)
- `experiments/catalog_cache/catalog_e6dfb345.json` — catálogo de referencia Classic (299,593; sha de contenido `bce358642b3bac3719c53bb99d401545bce6f432aabd9957b37528d9dc669ccc`; la copia stale quedó en `catalog_e6dfb345.legacy-stale.json.backup`)
- `experiments/evidence/frontier_HI_len{7,8,9,10}.json` — fronteras negativas (`HISTÓRICO` pre-swap)
- `experiments/evidence/dsl_frontier_HI_len7.json` / `dsl_catalog_len6.json` — gates DSL (`HISTÓRICO` pre-swap)
- `experiments/evidence/bench_hardcoded_len8.json` / `bench_dsl_len8.json` — benchmark D3 (`HISTÓRICO` pre-swap)

---

## Reproducción de gates

```bash
# Gate 1: paridad aleatoria (417 casos, semántica Classic)
python experiments/gate1_parity.py

# Gate 2: paridad de catálogo + rendimiento (299,593 entradas)
python experiments/gate2_catalog.py

# Impresora de moldes: reconstruye el catálogo con el motor Zig y compara
# campo a campo contra la referencia Classic (0 mismatches esperado)
python experiments/printer_loop.py
```

Gate 2 y printer_loop comparan contra el catálogo en cache
(`catalog_e6dfb345.json`). Si algún día cambias la semántica de `vm.zig`,
**regenera primero el catálogo** con la referencia
(`build_catalog(max_len=6, max_steps=3000, input_data="", engine="reference")`
persistido en `experiments/catalog_cache/`) antes de volver a correr los gates;
un catálogo stale hace fallar printer_loop por diseño (no lo "arregles"
silenciosamente).

Gates DSL (D1/D2/D3) — medidas `HISTÓRICAS` de la semántica vieja; su re-corrida
bajo semántica Classic sigue pendiente y la reproducción documentada está en
`ROADMAP.md`.

---

## Estado

**Prototipo de investigación — gates principales pasando, frontera abierta.**

| Componente | Estado |
| --- | --- |
| Sintetizador de programas cortos | ✅ Operativo (catálogo + beam) |
| Pipeline de verificación | ✅ Gates 1 y 2 + printer_loop PASSED (semántica Classic) |
| Motor Zig rápido (`bolge.exe`) | ✅ 0 mismatches: 417 (gate1) + 299,593 (catálogo) |
| Referencia Classic densa (`classic.py`) | ✅ Bucle único compartido, relleno tail-shared (len≤5: 614 s → 19.5 s) |
| Catálogo len-6 | ✅ Regenerado: 299,593 entradas, 1,705 outputs distintos |
| DSL especializado (`bolge-dsl.exe`) | 🕓 HISTÓRICO (medido pre-swap); re-corrida bajo Classic pendiente |
| Fronteras negativas `HI` (len ≤ 10) | 🕓 HISTÓRICO pre-swap (veredicto sólido: 0 hits en 1.07B) |
| Prototipo de continuidad por streaming | ✅ `Hi` compuesto desde dos continuaciones en el intérprete de la toolkit |
| `FRONTIER PREFIX_FILE` | ✅ Busca sufijos con posición correcta tras un seed Classic fijo |
| `BRANCH` acotado multi-caso | 🔬 Búsqueda de primitivas MALDOOM V1; el eco solo no prueba una rama interna |
| Secuencia ternaria `012 -> 120` | ❌ Sin hit en la frontera acotada de longitud 3 |
| Orquestador dataflow | ✅ Contratos + artefactos con hash + sin re-runs + difftest sobre la referencia Classic (12/12 tests) |
| Solver H3/H4, multi-char, Busy Beaver, difftest 428, Atlas | 🕓 HISTÓRICO pre-swap (evidencia preservada) |

Detalle en [ROADMAP.md](ROADMAP.md) — ítems 1–6 ejecutados; extensiones
abiertas son exhaustivos > len 10, benchmark Busy Beaver cross-language y
re-ensamblaje semántico de bloques.

## Límite de afirmaciones sobre continuación

`malbolge_translator/streaming.py` mantiene una fotografía de la toolkit
mientras sintetiza continuaciones cortas de texto fijo, y después verifica el
programa Classic resultante desde bootstrap. **No** serializa estado para una
VM limpia.

`FRONTIER ... PREFIX_FILE <path>` evalúa sufijos tras un seed fijo con la
codificación posicional de opcodes correcta. La sonda `truth_machine.mal`
estableció que su rama de parada sale antes del código anexado; no es un ancla
de continuación usable. Continuación con VM limpia, paridad con runtime
independiente y la generación completa de Don Quixote permanecen
`NOT_DEMONSTRATED`.

---

## Licencia

MIT. Ver `LICENSE` cuando exista.