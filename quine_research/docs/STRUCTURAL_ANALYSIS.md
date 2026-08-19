# Estructura y Análisis del Baseline
## Quine de Malbolge - Matthias Lutter (2024)

### Resumen Ejecutivo

- **Archivo baseline:** `baseline_quine.mal`
- **Tamaño raw:** 59,852 bytes (59032 chars + 820 newlines)
- **Tamaño clean:** 59,032 chars
- **Pasos totales:** 69,547,437
- **Halt reason:** `end` opcode (comportamiento limpio)
- **Propiedad quine verificada:** El output idéntico al raw file ✅

---

## 1. Memoria: Estructura CODE vs DATA

```
Memoria total: 59049 celdas (POW10 = 3^10)
Clean source: 59032 chars (33-126)
Indicador de EOF: 59048
Celdas no utilizadas (33-126): 59032 a 59047 (16 celdas sin inicializar a 0)

Región CODE:   [0,   29515]   → 29,516 celdas
Región DATA:   [29516, 59031] → 29,516 celdas
Región FILL:   [59032, 59047] → 16 celdas (no inicializadas = 0)
```

### Hallazgo crítico: `CODE == DATA`
- `clean_source[0:29516] == clean_source[29516:59032]` → **TRUE**
- Ambas regiones contienen exactamente el mismo contenido.
- La quine opera leyendo desde la región DATA (addresses ≥ 29516) para regenerar la CODE.

---

## 2. Ejecución: Estadísticas por Opcode

| Opcode | Mnemónico | Cuenta | Fracción |
|--------|-----------|--------|----------|
| 81 | `end` | 1 | 0.001% |
| 5 | `out` | 59,852 | 0.086% |
| 39 | `rotr` | 891,133 | 1.28% |
| 62 | `crz` | 742,834 | 1.07% |
| 40 | `mov_d` | 6,631,123 | 9.53% |
| 23 | `in` | 0 | 0% |
| 4 | `jmp` | 23,901,063 | 34.37% |
| `nop` (todo lo demás) | - | 37,321,431 | 53.67% |

**Observaciones:**
- La quine casi no usa `in` (EOF_A = 59048) porque es no interactiva.
- `nop` domina (53.7%): el relleno y las celdas de DATA que no se usan, todas ejecutan nops.
- Solo accede a la región CODE y FILL directamente (**0 accesos a la región DATA como PC**).

---

## 3. Acceso a Memoria (Puntero D)

- **Direcciones D leídas únicas:** 29,868 (sobre 59048 posibles)
- **Direcciones D escritas únicas:** 29,848
- **Lecturas en región CODE:** 31,930,018 (91%)
- **Lecturas en región DATA:** 236,124 (0.67%)
- **Lecturas en región FILL:** 11 (casi cero)

**Top 10 direcciones D leídas:**

| Dirección | Lecturas | Región |
|-----------|----------|--------|
| 29421 | 1,180,642 | DATA |
| 29422 | 1,180,642 | DATA |
| 29438 | 944,516 | DATA |
| 29443 | 944,516 | DATA |
| 29424 | 944,515 | DATA |
| 29461 | 944,515 | DATA |
| 29439 | 944,513 | DATA |
| 29440 | 944,513 | DATA |
| 29441 | 944,513 | DATA |
| 29460 | 944,513 | DATA |

**Top 5 direcciones D escritas:**

| Dirección | Escrituras | Región |
|-----------|------------|--------|
| 29342 | 767,404 | DATA |
| 29313 | 265,621 | DATA |
| 29322 | 177,083 | DATA |
| 29427 | 118,066 | DATA |
| 29337 | 88,543 | DATA |

---

## 4. Implicación estructural: El bucle de impresión

El PC más ejecutado es **29200/29201** (8.2M + 4.1M ejecuciones), y la región 29400-29413 ejecuta uniformemente (2125152 cada una).

El output comienza en el paso 28,316 (primer caracter 'b'). Cada caracter se emite desde:
- **PC de salida:** 29356
- **D pointer:** 29454

Intervalo entre salidas: **~1,137 pasos** (promedio estimado)

Los 59,032 caracteres se emiten presuntamente en 59,852 pasos, con 820 saltos de línea (`\n`, chr 10).

---

## 5. Información Relevante para la Enumeración

- **CODE y DATA son idénticos**: cualquier manipulación de CODE con conservación de DATA mantiene la quine.
- **Puntero D apunta principalmente a DATA**: aproximadamente 236k lecturas a 29,516 celdas.
- **El bucle lee secuencialmente DATA** (base + offset), haciendo `in d` (mem[d]) sucesivamente.
- **No hay branching complejo**: la estructura de control es un bucle lineal de lectura.

---

## 6. Questiones Pendientes (para Fase 2+)

- **¿Cómo se inicializa el puntero D para leer DATA secuencialmente?**
- **¿Cuál es la correspondencia exacta entre output step y dirección D leída?**
- **¿Dependen los caracteres output solo de mem[d], o también de A?**
- **¿Por qué el bucle de salida termina cuando mem[c] cae fuera de [33,126]?**