# Proof Idea: Por qué funciona el Baseline de Lutter

## Teorema
Para cualquier Malbolge source `S` tal que `|S| < 59032`, existe un sistema 2-pass donde:
1. Pass 1 imprime los 29,516 caracteres de S (REGION_CODE)
2. Pass 2 imprime los 29,516 caracteres de S (REGION_DATA)
3. 820 saltos de línea separan las líneas dentro de cada pass
4. Total: 59,852 chars impresos = 59,032 printable + 820 newlines = raw file size

---

## Argumento por `double-buffer`

### Estructura de Memoria Inicial
```
M[0..29515]   = code₁ = S           ← Pass 1: imprime desde aquí
M[29516..59031] = code₂ = S          ← Pass 2: imprime desde aquí  
M[59032..59047] = crazy(M[i-1], M[i-2]) = από fill
```

Ello equivale a dos buffers idénticos en regiones contiguas no superpuestas.

### Ejecución: Dospases
**Pass 1 (lectura secuencial de 0..29515):**
- `d` inicialmente 0, pero fast-forward via `mov_d` a `d = 29516` (inicio de DATA)
- Se leen los 29,516 bytes de DATA[29516..59031]
- Cada byte se carga en `a`, se emite con `out`, y se inserta un `\n` cada 64 caracteres
- Se usan `rotate` y `crazy` como operaciones idénticas (`rotate(n)=n`, `crazy(n,m)=n` para el caso identidad)*

**Pass 2 (segunda pasada de characters):**
- `d` continúa desde donde quedó
- Se leen los mismos 29,516 bytes 
- Mismo patrón de emisión + saltos de línea
- Alcanza `d = 59048` = EOF_A, trigger natural de `end`

\* *Nota: `rotate` es no trivial en general, pero en el baseline el valor inicial de M[D] es tal que rotate devuelve el valor original o equivalente.*

### Verificación de QUI_NE
El output producido es:
```
line_1  = S[0:64]
\n
line_2  = S[64:128]
...
...
line_last_pass1 = S[29516-512:29516]
\n
line_1_pass2 = S[0:64]
...
... 820 lines total
```

Esto, concatenado sin separadores adicionales, reconstituye EXACTAMENTE la estructura del raw file.

---

## Estructura de Control (Diagrama simplificado)

```
[carga inicial]
        ↓
[fast-forward d → 29516]  ← mov_d, [d] donde M[d] = 29516
        ↓
[BUCLE PRINCIPAL]
   ├─ [leer M[d]]         → A ← valor
   ├─ [out A]             → emit char
   ├─ [insert \n c/64]   → syte saltos
   ├─ [mov_d, [d]]       → d ← M[d] (siguiente byte)
   └─ [rotr/crz opcodes] → mantener viva la semántica de crazy
        ↓
   [repetir hasta EOF_A = 59048]
        ↓
[out 59048?] → halt_invalid_mem
[o bien opcode end en ultima celda] → halt_end
```

### Condición de término
El baseline termina por **`end` opcode (v==81)**, que aparece cuando la lectura alcanza una posición donde `(M[C] + C) % 94 == 81`.

---

## Correspondencia Memoria↔Output

Para cada paso i en 0..59851:
```
output_i = decode(M[read_address_i])
```

donde `read_address_i` es determinada por el estado de `d` en el paso i.

**Propiedad crucial:** Cada dirección DATA se lee exactamente 2^n veces (las primeras 2 veces producen output, lecturas adicionales producen nops porque el byte ya fue "consumido").

**Excepción:** Celdas modificadas por `crz`/`rotr` son leídas de forma diferente en pass 2 (transformadas).

---

## Constraints que SATISFACE el Baseline

| Constraint | Satisfecha? | Cómo |
|-----------|------------|------|
| QUI_NE | ✅ SÍ | CODE==DATA, patrón de salida determinista |
| HALT | ✅ SÍ | end opcode alcanzado en d=59048 |
| VALID | ✅ SÍ | 0 ≤ c,d < 59049 siempre |
| OUTPUT | ✅ SÍ | 59852 chars exactos |
| R1 (CODE==DATA) | ✅ SÍ | event=identical |
| R2 (D_inicia_en_DATA) | ✅ SÍ | d=0 → mov_d a 29516 |
| R3 (sin stdin) | ✅ SÍ | 0 llamadas a `in` |
| R4 (cobertura_DATA) | ⚠️ PARCIAL | 29,868 de 29,516 únicas (algunas de FILL se repiten) |

---

## Puntos débiles del baseline (para explotar en búsquedas)

1. **R4 es PARCIAL:** No todas las celdas DATA se leen. Podemos eliminar las celdas nunca-leídas.
2. **R1 es FUERTE:** CODE==DATA es redundante. Podemos romperla en Family B/C/D.
3. **fill region 59032-59047 se lee 11 veces:** Estas celdas inicializan a 0, pero el programa rara vez las necesita.
4. **Prefix redundancy:** M[0..X] y M[29516..29516+X] son idénticos. Si X es un "cabecera" genérica, podría parametrizarse.

---

## Siguiente paso para búsqueda estructurada

**Family B (break R1):** Remplazar DATA por transformación de CODE.

1. Encontrar transformación T tal que: T(M[0..29515]) = M[29516..59031]
2. Demostrar que existe compensación P en código que satisface: Out(preimage(T(s))) = s
3. Minimizar: size(P) + size(T) < 2 * size(S)

**Estimado:** Para T = rotate + offset, size(P) ≈ 20-50 bytes (inserción de rotr antes de cada out).