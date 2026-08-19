# Constraints Extraction
## Formalización de restricciones para Quines de Malbolge

### Notación

- `M` = mem[0..59048] (vector de 59049 enteros)
- `C, D, A` = registros (enteros)
- `E(M, C, D, A)` = un paso de ejecución (función determinista)
- `halt(M, C, D, A)` = (M[C] < 33 o M[C] > 126) o (v == 81, es decir, V(M,C) mod 94 == 81)
- `V(M, C) = (M[C] + C) mod 94` = opcode decodificado
- `encrypt(M, C)` = M[C] := ENCRYPT[M[C] - 33] (si 33 <= M[C] <= 126)
- `advance(C, D) = (C+1 mod 59049, D+1 mod 59049)`

---

## Restricciones Formales del Problema Quine

### QUI_NE: Propiedad de identidad de output

```
define QUI_NE(M₀, C₀=0, D₀=0, A₀=0) ≡
  let res = eval_classic(M₀, C₀, D₀, A₀) in
  res.output == decode_raw(M₀)
```

Donde `decode_raw(M₀)` es la conversión ASCII de los valores en M₀ que están en [33,126], manteniendo newlines del archivo raw.

Para Lutter (2024), el archivo es `baseline_quine.mal`:
- 59,032 chars ASCII (33-126)
- 820 newlines (chr 10)

---

### HALT: Terminación segura

```
define HALT(σ) ≡
  halt(M, C, D, A) ∧
  (existe un paso t tal que V(M_t, C_t) = 81)  -- fin por opcode `end`, NO por EOF
```

El baseline termina por `end` (V=81), no por memoria inválida. Esto es un requerimiento de calidad.

---

### VALID: Memoria accesible

```
define VALID(M, C, D, A, hist) ≡
  ∀(c_f, d_f) ∈ hist : 0 ≤ c_f, d_f < 59049 ∧
  ∀d ∈ reads : 0 ≤ d < 59049 ∧
  ∀d ∈ writes : 0 ≤ d < 59049
```

El explorador solo debe generar programas cuyo M inicial tenga valores ≤ 126 en todos los accesos posibles.

---

### OUTPUT: Características del output

```
define OUTPUT_SIZE(M) ≡ ∈ { 29516 + 820 = 59852 }  (32,952 printable + 820 newlines)
```

Para el baseline:
- 59,032 caracteres imprimibles (corresponden 1:1 con M[0..29515])
- 820 saltos de línea insertados

El output esperado del baseline (sin conclusión teórica):
```
str1 = clean_source[0..29515]   → línea 1
'\n'
str2 = clean_source[0..29515]   → línea 2
'\n'
...
820 veces (approx)
```

---

## Restricciones Estructurales

### R1: CODE == DATA (Identidad estructural)

```
R1(M) := M[0..29515] == M[29516..59031]
```

Esta es la propiedad central del baseline. Satisfacela reduce el espacio de búsqueda a la mitad.

**Contraejemplo que NO la satisface:** un programa donde CODE y DATA sean diferentes pero la salida se construya en tiempo real (ver Family C).

### R2: Accesibilidad de DATA

```
R2(M, D_init) := D_init = 29516
```

El puntero D debe inicializarse en el primer byte de DATA para permitir lectura directa.

**Valor real:** D inicia en 0, pero se modifica rápidamente vía `mov_d, [d]` para apuntar a 29516.

### R3: No-uso de stdin (interactividad)

```
R3 := no hay opcode `in` (v == 23) ejecutado
```

El baseline no lee input. Imposición: cualquier quine derivado no debe necesitar stdin.

### R4: Completeness (cobertura de DATA)

```
R4(accs_D) := todos los bytes 29516..59031 se leen al menos una vez
```

**Hallazgo:** Se accede a 29,868 posiciones únicas de D durante la ejecución, pero no todas están en DATA (se leen posiciones fuera de DATA también).

---

## Restricciones de Ejecución

### E1: Ocurrencia de `out`

```
E1 := cantidad de `out` = 59852 (59,032 printable + 820 newline)
```

Valor exacto para Lutter baseline.

### E2: Ocurrencia de `jmp`

```
E2 := cantidad de `jmp` = 23,901,063  (digestir saltos para posicionarse)
```

Los `jmp` permiten c = M[d] y son el mecanismo principal de control de flujo.

### E3: Ocurrencia de `mov_d`

```
E3 := cantidad de `mov_d` = 6,631,123 (mover puntero D)
```

`mov_d` (v==40) mueve D = M[D]. Es el mecanismo de recorrido a través de DATA.

### E4: Complejidad de `nop`

```
E4 := cantidad de `nop` = 37,321,431
```

El 53.7% del tiempo de ejecución es nop. Esto refleja el relleno lazy de celdas.

---

## Restricciones de Inicialización

### I1: Mem[C] inicial válida

```
I1(C₀,D₀,A₀,M) := 33 ≤ M[0] ≤ 126
```

El primer PC siempre es 0. M[0] debe estar en rango imprimible.

### I2: Estados iniciales

```
I2 := C₀ = 0, D₀ = 0, A₀ = 0  (siempre así en Malbolge)
```

### I3: Relleno crazy

```
I3 := ∀i ∈ [29516..59047]. M[i] = crazy(M[i-1], M[i-2])
```

El relleno crazy funciona hacia adelante desde M[59032..59047]=0 (valores EOF).

---

## Constraints para la Búsqueda (Bبان multiplicativo)

Las familias de búsqueda satisfacen restricciones específicas:

### Para Family B (Reconstrucción)

```
F_B_relax :=  R1 ∧ QUI_NE ∧ HALT
F_B_strict := R1 ∧ QUI_NE ∧ HALT ∧ E1 ∧ E3
```

### Para Family C (Generación parcial)

```
F_C_relax :=  QUI_NE ∧ HALT
F_C_strict := QUI_NE ∧ HALT ∧ R2 (si DATA_AREA) ∨ R1 (si CODE_AREA solo)
```

### Para Family D (Memoria derivada)

```
F_D_relax :=  QUI_NE ∧ HALT ∧ R2
F_D_strict := QUI_NE ∧ HALT ∧ R2 ∧ E4 ≤ threshold
```

---

## Métricas para Detectar Degradación de Restricción

| Métrica | Baseline | Valor a preservar |
|---------|----------|-------------------|
| Tamaño (raw) | 59,852 | Reducir |
| Pasos totales | 69.5M | No crítico |
| Ejecuciones en CODE | 100% | ≈100% |
| Ejecuciones en FILL | 0.86% (619k) | << 10% |
| Lecturas en DATA | 236k | ≈ 29516 x 8 |
| Count `out` | 59,852 | = 59852 |
| Count `end` | 1 | = 1 |