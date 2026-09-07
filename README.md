# Autobolge

![Autobolge relational synthesis](assets/autobolge.gif)

**Autobolge es un sintetizador relacional evidencia-first para Malbolge.**

Roadmap de campanas: ver [ROADMAP.md](ROADMAP.md).

Busca programas de Malbolge a partir de relaciones de comportamiento, ejecuta cada
candidato a traves de un debugger canonico, y verifica el programa resultante
contra casos I/O explicitos. El proyecto combina catalogos exhaustivos de
programas cortos, beam search con awareness de estado, exploraciones de familia
estructuradas, y artifacts de verificacion reproducibles.

---

## Por que importa

Malbolge es deliberadamente hostil para la sintesis normal de programas: su memoria se
auto-modifica, la decodificacion de instrucciones depende de la posicion del programa, y cambios
pequenos en el fuente pueden destruir un comportamiento de otro util. Autobolge trata ese
comportamiento como un problema de busqueda relacional en vez de depender de programas escritos a mano.

**Insight clave:** Los traductores existentes de Malbolge a C restauran la memoria a su estado original
**despues de cada instruccion**. La sintesis de printer-loop / template de Autobolge avanza
**multiples pasos antes de restaurar** — un enfoque fundamentalmente
diferente que permite la sintesis relacional desde clases de equivalencia de comportamiento.

---

## Resultados Verificados

### Catalogo y Sintesis (Gate 1 & 2 — PASSED)
- 299,593 programas validos indexados hasta longitud 6.
- 802 outputs observados distintos en ese catalogo.
- Sintesis automatica de echo de un caracter: `ub`.
- Sintacion automatica de prefijo de dos caracteres: `ubs``.
- `ubs`` verificado para `AB -> AB`, `HI -> HI`, y `XYZ -> XY`.
- Ejecucion canonica de `Hello, world.` verificada a traves del interprete real.
- Exploracion estructurada de la familia canonica `(=<` de Malbolge.

### Motor Zig Rapido — Paridad Semantica (Gate 2 — PASSED)
- `zig/bolge.zig` replica exactamente la semantica del debugger de referencia,
  incluyendo el comportamiento de **overlay de crazy-fill lazy** del paquete `malbolge`
  (el quirk critico: la semilla block-tail+1 se lee del overlay en el primer
  acceso lejano, asi que los encrypts/rotations previos cambian el fill).
- Puertas de paridad: 417 casos aleatorios + las 299,593 entradas del catalogo **identicas
  (0 desajustes)**.
- Throughput: ~28x mas rapido en longitud ≤ 5 (13.9s → 0.5s); catalogo len-6 reconstruido
  en ~4 s en vez de minutos (referencia Python).

### Frontier Scans — Negativos Honrosos (Gate D1 — PASSED)
Frontiers exhaustivos negativos con el motor Zig: `HI` sin input no
se encuentra en el espacio completo de programas validos a:
- Longitud 7:   2,097,152 programas  (22.7 s Python → **2.7 s DSL**)
- Longitud 8:  16,777,216 programas (170.7 s Python → **2.2 min DSL**)
- Longitud 9: 134,217,728 programas (1,720 s Python → **14.7 min DSL**)
- **Longitud 10: 1,073,741,824 programas — 2.85 h DSL, 0 hits**
  Evidencia: `experiments/evidence/frontier_HI_len10.json` (sha256 `2a31218d446c224b8a46536af24cff93ef94f2eba5a88e7f8843e17ef7cd2b44`)

Los resultados negativos se conservan como evidencia (`experiments/evidence/frontier_HI_len*.json`)
en vez de ocultarse — el registro de investigacion incluye tanto construcciones como limites.

### DSL Especializado — Abstraccion de Costo Cero (Gate D3 — MEASURED)
Una ISA minimal de maquina de busqueda (programas `.bolge`) ejecutada por un runtime Zig
(`bolge-dsl.exe`) con primitivas que existen **solo para esta carga de trabajo**:
`FRONTIER`, `CATALOG`, `BRANCH`, `ENUMERATE`, `EXECUTE`, `FILTER`, `DEDUP`,
`EMIT`, `HASH`, `TRACE`.

| Carga de trabajo | Zig Hardcoded | DSL (`bolge-dsl.exe`) | Overhead |
|----------|---------------|----------------------|----------|
| len-8 (16.7M) | 134.6 s @ 124,651 p/s | 134.7 s @ 124,569 p/s | **0.07%** |
| Memoria Pico | 6.0 MB | 4.1 MB | — |

El DSL agrega **programabilidad a ~0 costo** porque cada primitiva mapea 1:1
a una operacion nativa del runtime; no hay capa de interprete general.

### Campanas de Solver — Hibrrido Generador + Dataflow (H3/H4 — MEASURED)
El solver de investigacion de quines (`quine_research/search_quine_malbolge/`) genera
programas de Malbolge para targets de output via el traductor del paquete `malbolge`,
batch-verificados a traves de la VM Zig.

- **H3 memoizacion cross-target** — veredicto dividido. H3a SOPORTADO: estructura
  compartida existe (12.9% hits de cache, −15% evaluaciones sobre 676 targets ABC).
  H3b FALSIFICADO: wall-clock sin cambios (83.1 s vs banda baseline 79.3–83.7 s);
  costo por nodo subio ~23% por overhead de dict/hash. Se conserva como hook
  opt-in `shared_state_cache`.
- **H4 paralelizacion por target** — SOPORTADO. Con `random_seed=42` ahora
  realmente pasando (antes se descartaba silenciosamente), la generacion es
  completamente deterministica: 2,730,128 nodos identicos y programas byte-identicos
  en serial y todos los conteos de workers. 676/676 concuerdan, 0 desajustes.

| Workers | Generacion | Targets/s | Peak worker RSS |
|---------|-----------|-----------|-----------------|
| 1 (serial) | 76.3 s | 8.9 | — |
| 2 | 44.6 s | 15.2 | 95 MB |
| 4 | 23.8 s | 28.4 | 161 MB |
| 6 | 18.0 s | 37.5 | 226 MB |
| 8 | 14.7 s | 45.9 | 294 MB |

Evidencia: `quine_research/search_quine_malbolge/results/h4_sweep.json` mas
bancos por config (`program_bank_ABC_zig*.json`).

### Orquestador Dataflow (`quine_research/dataflow/`)
Autobolge ya no es una sola busqueda: los nodos son contratos tipados
(`SearchResult → ClassifierResult → SelectionResult → TransformResult →
SolverResult → CompareResult → Verdict`), cada uno persistido como un
`runs/<pipeline>/<stage>__<hash>/artifact.json` explicito. La identidad del nodo es
`sha256(params + hashes de artifacts upstream)` — nodos sin cambios SE SALTAN, params cambiados
invalidan solo downstream (sin reruns accidentales de 200M programas). Los ejecutadores se rutean
por nodo (`frontier` → batch Zig, el resto → Python), cruzando la frontera de lenguaje
por batch, nunca por candidato. La plantilla lens
(`frontier_campaign.template.json`) usa **coordenadas logicas**
(`L1/L2/L3` via `--var`, no consecutivas permitidas), asi que los ensamblajes se rebasean
(2,3,4) → (3,4,5) y comparten artifacts por hash. Verificado end-to-end:
ensamblaje B corrio un frontier fisico exhaustivo longitud-3 (830,584 candidatos
en 6.7 s), solver 4/4 concordados, todas las puertas PASS.

Campanas del roadmap ejecutadas en el (ver ROADMAP.md):
- **Sintesis multi-char**: 14 targets de 3–9 chars ("HI!" … "AUTOBOLGE"),
  14/14 concordados y verificados por Zig.
- **Busy Beaver**: champions exhaustivos longitud 1–3 (all-NUL en longitud ≤ 3:
  `'c'`/`'cb'`/`'cba'`; non-NUL en longitud 3: `'ba` → `'\r\r'`, `'>ba'` → `'ss'`).
- **Composicion de templates**: 8 bloques verificados → catalogo → 64
  composites pareados, todos ejecutados. Negativo estructural: la concatenacion naive es
  dominada por prefijo — el `v` del primer bloque (halt) mata al segundo bloque.
- **Difftest multi-backend**: mismos programas a traves de Zig y el
  interprete de referencia Python — 428 casos comparables, **0 desajustes**
  (2,509 invalid-opcode + 63 input-underflow reportados honestamente como
  non-comparables). Los hashes de stage-code son parte de las keys de artifacts, asi que evidencia vieja
  no sobrevive a un fix de motor.
- **Guiado vs fuerza bruta** (longitud 3): 830,584 candidatos exhaustivos → 15
  outputs distintos; select+extend guiado 4,700 → 6 (40% de clases a
  0.57% de compute); muestreo random puro 4,700 → 4.
- **Atlas**: `pipelines/atlas.json` exporta `runs/atlas_index.json`
  (102 artifacts con sha256 por nodo, ejecutable despues de cualquier campana).

---

## Inicio Rapido

```bash
# Demo Python (sintesis relacional, beam search, catalogo)
pip install malbolge pillow
python experiments/relational_synthesis_demo.py

# Motor Zig rapido (runner batch, paridad verificada)
cd zig
..\zig.exe build-exe bolge.zig -O ReleaseFast "-femit-bin=bolge.exe"
.\bolge.exe in.bin out.bin 3000

# DSL especializado (frontier scans de produccion)
..\zig.exe build-exe dsl.zig -O ReleaseFast "-femit-bin=bolge-dsl.exe"
.\bolge-dsl.exe ..\experiments\frontier_HI_len10.bolge

# Relacion bounded multi-case input: una fuente debe satisfacer cada CASE
.\bolge-dsl.exe ..\experiments\dsl_maldoom_input_branch_smoke.bolge
```

El demo carga el catalogo persistido bajo `experiments/catalog_cache/`, corre
sintesis exacta y guiada, verifica los programas generados, y checa el
programa canónico Hello World.

---

## Arquitectura

```
┌─────────────────────────────────────────────────────────────────┐
│                    SEARCH MACHINE ISA                            │
│  .bolge programs: FRONTIER, CATALOG, ENUMERATE, EXECUTE, ...   │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                   ZIG RUNTIME (bolge-dsl.exe)                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │ ENUMERATE    │  │ EXECUTE      │  │ EMIT + HASH  │           │
│  │ mixed-radix  │──▶│ vm.runProgram│──▶│ JSON + sha256│           │
│  │ valid chars  │  │ (in-process) │  │ evidence     │           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                      SHARED VM (vm.zig)                         │
│  • Crazy table (trit-wise, base-3)                              │
│  • Rotate (×19683 mod 59049)                                    │
│  • Lazy crazy-fill overlay (block=243, seed=tail+1 from overlay)│
│  • Encrypt post-step (guarded 33..126)                          │
│  • Step counter = ALL steps including terminating               │
└────────────────────────────┬────────────────────────────────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
       bolge.exe         bolge-dsl.exe   printer_loop.py
       (batch CLI)       (DSL runtime)   (oracle gate)
```

### Mapa de Modulos

| Modulo | Proposito |
| --- | --- |
| `zig/vm.zig` | **Fuente unica de verdad** para la semantica de Malbolge (lazy fill, encrypt, rotate) |
| `zig/bolge.zig` | CLI batch (`in.bin` → `out.bin`), importa `vm.zig` |
| `zig/dsl.zig` | Runtime de ISA de maquina de busqueda (parser + executor `.bolge`) |
| `zig/frontier_scan.zig` | Baseline hardcoded para benchmarking |
| `relational/materialization.py` | Catalogos, family scans, beam synthesis (engine param = "fast"|"reference") |
| `relational/fast_engine.py` | Wrapper Python → protocolo batch `bolge.exe` |
| `experiments/printer_loop.py` | Gate 2: recompila `bolge.exe`, corre 299,593 molds, 0 desajustes |
| `experiments/gate1_parity.py` | Gate 1: 417 casos aleatorios vs `run_bounded` |
| `experiments/*.bolge` | Programas DSL (specs de busqueda declarativos) |
| `quine_research/dataflow/` | Orquestador dataflow: contratos nodales, artifacts hash-keyed, no-rerun, ejecutadores por nodo (Zig/Python), plantilla lens |
| `quine_research/search_quine_malbolge/` | Solver hibrido (generador de traductores + verificacion batch Zig), `--workers N` generacion paralela |

---

## Politica de Evidencia

Cada programa reportado se re-ejecuta antes de llamarse exitoso. Los reportes
incluyen outputs exactos, conteos de pasos, razones de parada, y hashes SHA-256 de programas.
El proyecto reporta tanto construcciones exitosas como limites de busqueda.

Archivos clave de evidencia:
- `experiments/evidence/gate1_parity.json` — 417/417 paridad
- `experiments/evidence/gate2_catalog.json` — reconstruccion completa del catalogo
- `experiments/evidence/printer_loop.json` — verificacion mold por mold
- `experiments/evidence/frontier_HI_len{7,8,9,10}.json` — frontiers negativos
- `experiments/evidence/dsl_frontier_HI_len7.json` — DSL reproduccion len-7
- `experiments/evidence/dsl_catalog_len6.json` — DSL catalogo (299,593 entradas, 0 desajustes vs referencia)
- `experiments/evidence/bench_hardcoded_len8.json` / `bench_dsl_len8.json` — benchmark D3

---

## Reproducir Puertas

```bash
# Gate 1: paridad aleatoria (417 casos)
python experiments/gate1_parity.py

# Gate 2: paridad de catalogo + printer loop (299,593 entradas)
python experiments/printer_loop.py

# Gate D1: reproduccion DSL frontier len-7
cd zig && ..\zig.exe build-exe dsl.zig -O ReleaseFast "-femit-bin=bolge-dsl.exe"
.\bolge-dsl.exe ..\experiments\dsl_gate_d1_len7.bolge

# Gate D2: DSL catalogo len-6 (paridad entry-by-entry)
.\bolge-dsl.exe ..\experiments\dsl_gate_d2_catalog.bolge
python -c "
import json
ref = json.load(open('experiments/catalog_cache/catalog_e6dfb345.json', encoding='utf-8'))
dsl = json.load(open('experiments/evidence/dsl_catalog_len6.json', encoding='utf-8'))['entries']
assert all(all(a[f]==b[f] for f in ('program','output','steps','terminated','stop_reason','final_a','final_pc','final_d')) for a,b in zip(ref,dsl))
print('D2 PASSED: 0/299593 desajustes')
"

# Gate D3: benchmark (Zig hardcoded vs DSL)
# (correr ambos, comparar rates + memoria pico)
```

---

## Estado

**Prototipo de investigacion — puertas pasando, frontier abierto.**

| Componente | Estado |
| --- | --- |
| Sintetizador de programas cortos | ✅ Funcionando |
| Pipeline de verificacion | ✅ Puertas 1, 2, D1, D2, D3 pasadas |
| Motor Zig rapido (bolge.exe) | ✅ 0 desajustes, ~28x speedup |
| DSL especializado (bolge-dsl.exe) | ✅ Abstraccion de costo cero medida |
| Prototipo de continuidad streaming | ✅ `Hi` compuesto desde dos continuaciones en el interprete del toolkit |
| `FRONTIER PREFIX_FILE` | ✅ Busca sufijos posicion-correctos despues de una semilla Classic fija |
| Relacion bounded multi-case `BRANCH` | 🔬 Busqueda MALDOOM V1; echo solo no demuestra un branch de control interno |
| Secuencia ternaria `012 -> 120` | ❌ Sin hit en el frontier bounded longitud-3 |
| Frontier `HI` (longitud ≤ 9) | ✅ Exhaustivamente negativo |
| **Frontier `HI` (longitud 10)** | ✅ **Completado: 1.07B programas, 2.85 h, 0 hits** |
| Orquestador dataflow | ✅ Contratos + artifacts hash-keyed + no-rerun + routing de ejecutadores |
| Solver H3 (memoizacion cross-target) | ✅ Medido: estructura existe (12.9% hits) pero wall-clock plano — memo se conserva opt-in |
| Solver H4 (paralelizacion) | ✅ Deterministico; serial 76.3s → 14.7s con 8 workers, 676/676 |
| Sintesis multi-caracter | ✅ Solve dirigido: 14/14 targets de 3–9 chars, verificados por Zig |
| Busy Beaver (longitud ≤ 3) | ✅ Champions hasheados en artifacts (NUL: `'c'`/`'cb'`/`'cba'`; non-NUL: `>ba`→`ss`) |
| Composicion de templates | 🔬 Medido con negativo estructural: concat es dominada por prefijo (halt mata bloque 2) |
| Difftest multi-backend | ✅ Zig vs Python referencia: 0 desajustes en 428 casos comparables |
| Guiado vs busqueda bruta | ✅ Guiado le gana a random en mismo compute (6 vs 4 clases); heuristica toroidal sin implementar |
| Indice Atlas | ✅ `atlas_index.json` exportado sobre 102 artifacts hash-keyed |

Detalle del roadmap: [ROADMAP.md](ROADMAP.md) — items 1-6 ejecutados; extensiones abiertas
son exhaustivos > longitud 10, benchmark cross-language Busy Beaver, y reensamblaje semantico de bloques.

## Limite de Continuidad

`malbolge_translator/streaming.py` mantiene un snapshot del toolkit mientras sintetiza
continuaciones de texto fijo pequenas, y luego verifica el programa Classic
resultante desde bootstrap. **No** serializa estado para una VM fresca.

`FRONTIER ... PREFIX_FILE <path>` evalua sufijos despues de una semilla fija con
encoding posicional correcto de opcodes. La sonda `truth_machine.mal` establecio
que su branch de halt sale antes de que el codigo anexado se ejecute; no es un ancla
usable de continuation. Reanudacion en VM fresca, paridad de runtime independiente para una continuation, y
generacion completa de Don Quixote siguen `NOT_DEMONSTRATED`.

---

## Licencia

MIT. Ver `LICENSE` cuando exista.
