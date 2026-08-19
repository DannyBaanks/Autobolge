# Construction Families
## Taxonomía de familias paramétricas para Quine de Malbolge

---

## Family A: Baseline (Copia directa CODE == DATA)

**Mecanismo:** El programa almacena su código fuente completo en dos copias idénticas en memoria. Durante la ejecución, lee la segunda copia (DATA) y la imprime como output, más algunos newlines insertados.

**Estructura de M₀:**
```
M[0..29515]   = S          -- source code
M[29516..59031] = S        -- data (identical to source)
M[59032..59047] = crazy(M[i-1], M[i-2])  -- fill
```

**Condición de satisfacción:**
```
R1(M) ∧ QUI_NE ∧ HALT
```

**Rango de parámetros:** No paramétrico (0 grados de libertad)
**Costo:** Basado en 100% eficiencia (máxima redundancia posible en una quine simple)

**Cuándo buscar en esta familia:** No tiene sentido buscar en esta familia - es el baseline mismo. Útil solo como punto de comparación.

---

## Family B: Reconstrucción DATA desde CODE

**Mecanismo:** DATA no es una copia idéntica de CODE. En su lugar, DATA es una versión preprocesada o comprimida, y algún mecanismo de transformación (decodificación) reconvierte DATA a CODE a medida que se imprime.

**Estructura M₀:**
```
M[0..29515]   = S          -- source code (no modificado)
M[29516..59031] = f(S)     -- transformación de S: e.g., rotación, complemento, ...
M[59032..59047] = crazy(M[i-1], M[i-2])  -- fill
```

**Transformaciones candidatas para f:**
- `f_rot(x) = rotate(x)` - rotación de trits
- `f_neg(x) = (3^10 - 1) - x` - complemento
- `f_xor(x) = x xor 0x40` - XOR con clave fija
- `f_perm(x, π) = permuta índices de trit según π`

**Condición de satisfacción:**
```
QUI_NE ∧ HALT ∧ R2  -- R2: D inicia en 29516 y recorre hasta 59031
```

**Rango de parámetros:** Depende de la transformación. Para `f_rot`: 0 param. Para `f_xor`: 1 (clave XOR).

**Impacto en métricas:** No reduce tamaño, pero cambia la relación de dependencia.

---

## Family C: Generación parcial en tiempo real

**Mecanismo:** En lugar de almacenar todo el source en la DATA, se usa CODE para generar parte de la salida, y DATA para almacenar solo una clave o semilla que genera el resto.

**Estructura M₀:**
```
M[0..k]       = boot_code + loop
M[k+1..29515] = padding
M[29516..29515+c] = seed_k   -- solo una parte de DATA contiene datos
M[29516+c..59031] = compute_from_seed(seed_k)  -- relleno calculado
```

**Condición de satisfacción:**
```
QUI_NE ∧ HALT (sin R1 estricta)
```

**Rango de parámetros:**
- Split point: 0 < k < 29516
- Función de generación: g: {0,1}^seed → {0,1}^(29516-k)

**Beneficio potencial:** Reducción lineal en tamaño si seed_k es considerablemente menor que 29516.

**Riesgo:** REQUIERE HALT. Es extremadamente difícil demostrar HALT en esta familia, ya que depende de la interacción boot_code × seed.

---

## Family D: Memoria derivada (computación redundante)

**Mecanismo:** La memoria DATA contiene valores derivados del prefix de CODE, calculados en tiempo de ejecución.

**Estructura M₀:**
```
M[0..P]         = source_prefix
M[P+1..29515]   = compute(M[P])  -- código se auto-deriva a partir del prefix
M[29516..59031] = same computation on DATA side
```

**Nota:** Malbolge ejecuta lazy, así que M[i] solo cambia cuando se lee (vía rotr/crz). Podemos hacer que M[i+i] = crazy(M[i], source[i]) para efectos precomputados.

**Condición de satisfacción:**
```
QUI_NE ∧ HALT ∧ R2
```

**Rango de parámetros:**
- Prefix size P, 0 < P < 29516
- Función de derivación: h: Mem_t → Mem_{t+1}

**Optimización:** En vez de precomputar DATA, usar que `M[i] := crazy(A_old, M[i])` (mediante `crz`) para modificar M[D] durante la ejecución y así derivar el output.

---

## Family E: Output indirecto (uso de stdin como seed)

**Mecanismo:** Usar el opcode `in` (v==23) en puntos estratégicos para leer sy caracteres de EOF_A (59048) como pseudo-input, luego computa el output necesario.

**Estructura M₀:**
```
M[0..P]         = ejecutable con puntos de entrada para `in`
M[P+1..29515]   = padding
M[29516..59031] = tabla de lookup (M[i] = expected_output[i])
```

**Condición de satisfacción:**
```
QUI_NE ∧ HALT  -- con R3 relajada (se permite in)
```

**Rango de parámetros:**
- Número de llamadas a `in`: 0 < N ≤ numero_de_chars
- Posiciones de `in` en el código

**Beneficio potencial:** Muy reducido (tinynquine).
**Riesgo:** La restricción R3 (sin input interactivo) se rompe. Necesita ser IO_AWARE.

---

## Family F: Combined (Family D + Baseline randomness)

**Mecanismo:** Mantiene la estructura CODE == DATA como base, pero usa `crz`/`rotr` para modificar DATA a medida que se imprime, generando bytes de output no-triviales.

**Estructura M₀:**
```
M[0..29515]   = S          -- source code
M[29516..59031] = S        -- data (identical)
M[59032..59047] = crazy(M[i-1], M[i-2])  -- fill
```

**Operaciones en tiempo de ejecución:**
- Al final de la impresión del n-ésimo caracter, se ejecuta:
  ```
  mem[D] = crz(A_old, mem[D])  -- modifica el dato original
  d = mem[d]  -- avanza puntero
  ```

**Condición de satisfacción:**
```
R1(M_pre) ∧ QUI_NE ∧ HALT
donde M_pre es el snapshot antes de la primera modificación de MEM[D]
```

**Observación:** El baseline ya usa this pattern parcialmente - algunas celdas DATA se modifican (767k writes en posición 29342, etc).

---

## Matriz de Familias: Parámetros vs Restricciones

| Familia | Parámetros | Reduce tamaño? | HALT fácil? | R1? | Preserva correspondencia output→mem? |
|---------|-----------|---------------|------------|-----|---------------------------------------|
| A | 0 | No | Sí | Sí | Sí |
| B | n-1 | No | Sí | No | Sí |
| C | (split, g) | Sí | **Difícil** | No | No |
| D | (prefix, h) | Sí | Moderado | No | Sí |
| E | (pos_in, N) | Sí (tiny) | Moderado | No | Sí |
| F | - | No | Sí | No (parcial) | Sí |

---

## Recomendaciones de Exploración (orden sugerido)

1. **Family B** (familia más fácil): Buscar transformaciones simples f(S) = rotate(S) XOR k. La verificación es directa.
2. **Family D** (mecanismo de derivación): Investigar cómo `crz` y `rotr` pueden reemplazar contenido estático en DATA.
3. **Family C** (generación en runtime): Solo si Family D falla, considerar generación dinámica de prefix.

**Posibilidad 0:** Si existe una variante con R1 rota (CODE != DATA), la verificación requiere probar QUI_NE directamente, sin confiar en R1. Esto requiere más pruebas pero es factible.

---

## Ejemplo: Exploración de Family B (break R1)

**Hipótesis:** Tomar el baseline, reemplazar DATA por rotate(CODE), y compensar esta rotación en el loop de lectura.

**Pasos de implementación:**
1. Determinar qué operación de COMPENSACIÓN se necesita para que rotate(CODE) produzca el output correcto.
2. Insertar esa compensación ANTES del `out` en el bucle de impresión.
3. Verificar QUI_NE.

**Resultado esperado:** Si tiene éxito, obtendremos una quine con R1 rota pero QUI_NE satisfecha. Implicación: `CODE != DATA` no implica no-válidez.

**Implicación para tamaño:** R1 rota no reduce automáticamente el tamaño. Para reducir tamaño, necesitamos Family C o D.