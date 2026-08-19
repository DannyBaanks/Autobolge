# Quine Malbolge Research: Estructura, Candidatos y Búsqueda

## Resumen

Repositorio de investigación estructurada para Quines de Malbolge, enfocada en:
1. **Describir** por qué funciona el baseline de Lutter (2024, 59,032 bytes)
2. **Reducir** tamaño del quine mediante variantes paramétricas
3. **Verificar** cualquier candidato propuesto mediante un pipeline estricto

**Baseline:** `quine_research/baseline_quine.mal`
- Tamaño: 59,852 bytes (59,032 chars + 820 newlines)
- Pasos: 69,547,437
- Estructura: `CODE == DATA` (ambas regiones de 29,516 chars idénticas)

---

## Estructura del Repo

```
quine_research/
├── baseline_quine.mal           # Quine baseline (input)
├── baseline_check.py            # Verificación rápida del baseline
├── README.md                    # Este archivo
├── evidence/                    # Resultados de análisis
│   └── baseline_analysis.json  # Trazado completo del baseline
├── docs/                        # Documentación de investigación
│   ├── BASELINE.md             # Documento Phase 0
│   ├── STRUCTURAL_ANALYSIS.md  # Documento Phase 1
│   ├── CONSTRAINTS.md          # Documento Phase 2
│   ├── FAMILIES.md             # Documento Phase 3
│   └── PROOF_IDEA.md           # Esbozo de prueba
├── analyzer/                    # Scripts de análisis
│   ├── quine_tracer.py         # Tracer detallado con contadores
│   └── loop_analyzer.py        # Análisis del bucle de impresión
├── generators/                  # Generadores paramétricos de candidatos
│   └── quine_generator.py      # Families B1-B4
├── search/                      # Framework de búsqueda
│   ├── search_catalog.py       # Catálogo de familias y params
│   └── staged_search.py        # Búsqueda en fases (0-5)
└── verification/                # Pipeline de verificación
    ├── proof_checker.py        # Verificación estructural (sin ejecución)
    └── pipeline.py             # Verificación completa (ejecución + QUI_NE)
```

---

## Metodología: Fases 0-9

### Fase 0: Baseline ✅
Cargar el baseline, verificar propiedad quine, medir ejecución.
- `python analyzer/quine_tracer.py 200000000`
- Verificación: `QUINE PROPERTY VERIFIED`

### Fase 1: Análisis estructural ✅
Identificar CODE, DATA, FILL. Medir accesos a memoria D. Analizar loop de impresión.

### Fase 2: Extracción de constraints ✅
Formalizar:
- **QUI_NE:** output == raw_source
- **HALT:** termina por `end` opcode
- **VALID:** 0 ≤ c,d < 59049
- **OUTPUT:** 59,852 chars total

Reglas estructurales:
- **R1:** CODE == DATA
- **R2:** D inicia en 29516 (área DATA)
- **R3:** sin stdin (sin opcode `in`)
- **R4:** cobertura de DATA (parcial en baseline)

### Fase 3: Familias de construcción ✅
Definir familias A-E para guiar búsqueda:
- **A:** Baseline exacto (no paramétrico)
- **B:** Transformación de DATA (rompe R1, más factible)
  - B1: rotate(S) + offset
  - B2: S XOR k + compensación
  - B3: S & mask
  - B4: chunk + repetición (reduce singularidad de DATA)
- **C:** Generación parcial (boot + seed)
- **D:** Memoria derivada (crz/rotr en runtime)
- **E:** Output indirecto (uso de `in`)

### Fase 4: Espacio de parámetros
Generar candidatos de Family B (con posibles combinaciones futuras).

### Fase 5: Búsqueda estructurada (framework)
Establecer el staged_search.py con fases:
- **0:** Validación del baseline
- **1:** Pequeñas modificaciones (swap order, separadores)
- **2:** Reducción del fill (59032-59047)
- **3:** Reconstruction (Family B)
- **4:** Modificaciones combinadas
- **5:** Refinar y verificación exhaustiva

### Fase 6: Verificación pipeline
Ejecutar pipeline completo para cada candidato:
1. **PARSER:** Lee candidate.mal, extrae CODE y DATA
2. **EXECUTION:** Ejecuta con Python (evaluador de referencia)
3. **HALT:** Verifica que termina (no loop infinito, max_steps=200M)
4. **OUTPUT_EXACT:** Compara byte por byte
5. **DETERMINISM:** Ejecuta 2 veces, compara outputs

### Fase 7: Comparación de métricas
Comparar candidatos válidos vs baseline:
- Tamaño (raw)
- Pasos totales
- Cobertura de regiones de memoria
- (Opcional) velocidad de ejecución

### Fase 8: Negativos (si no hay candidato exitoso)
Documentar qué familias fallaron y por qué.
Investigar por qué R1 no puede ser relajada (o puede).

---

## Ejecutar

### Verificación del baseline:
```bash
cd quine_research
python analyzer/quine_tracer.py 200000000 10000000
python verification/pipeline.py baseline_quine.mal
```

### Generar candidatos Family B:
```bash
python generators/quine_generator.py --family B2 --key 0x40
python generators/quine_generator.py --family B4 --chunk-size 1024
```

### Ejecutar búsqueda en fases:
```bash
cd quine_research
python search/staged_search.py 0  # Validar baseline
python search/staged_search.py 3  # Generar Family B candidates
```

### Verificación estructural (rápida, sin ejecución):
```bash
python verification/proof_checker.py quine_research/generated/candidate_B2.mal
```

---

## Cómo Contribuir

1. Añadir nuevas familias en `generators/quine_generator.py`
2. Añadir análisis en `analyzer/loop_analyzer.py`
3. Verificar candidatos con `verification/pipeline.py`
4. Documentar resultados en `evidence/*.json`

---

## Referencias

- [Malbolge - Wikipedia](https://en.wikipedia.org/wiki/Malbolge)
- [Lutter 2024: A Quine in Malbolge](https://www.heise.de/news/Rekord-Kuerzeste-Malbolge-Quine-9366616.html)
- [Esolang Wiki: Malbolge](https://esolangs.org/wiki/Malbolge)

## License

MIT