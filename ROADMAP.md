# Roadmap de Autobolge

Roadmap de campañas. Cada ítem indica dónde vive hoy la infraestructura que
lo soporta (el dataflow ya da artefactos hasheados + no-rerun para todos).

## 1. Síntesis multi-caracter (L11–L12)

Extender el catálogo más allá de longitud 10.

- Objetivo: outputs de más de 2 caracteres (ej. "HI!", "BYE").
- Documentar tanto hallazgos como resultados negativos.
- Hoy: `frontier_campaign.template.json` con `--var L1=… --var L2=… --var L3=…`
  (no-rerun protege lo ya exhausto, ej. len10 0 hits).
- **EN MARCHA (dirigido por solver)**: `pipelines/multichar_synthesis.json` —
  14 targets de 3–9 caracteres ("HI!", "BYE", "AUTOBOLGE", "MALBOLGE", …),
  14/14 matched y verificados por Zig batch, 106,306 nodos en 1.9s (w6).
  Extensión del CATÁLOGO a programas de len>10: PENDIENTE (exhaustivo
  inabordable; ir por fronteras selectivas).

## 2. Verificación Busy Beaver

Campañas para detectar programas que maximizan output antes de halting.

- Comparar con benchmarks de otros lenguajes esotéricos.
- Guardar evidencia reproducible (JSON + hash).
- **EN MARCHA**: `pipelines/busy_beaver.json` con stage `busy_beaver`
  (pool = terminated con output; solo cuentan programas que haltean).
  Campeones exhaustivos medidos:
  - len1 (94): max out 1 — `'c'` → `\x00`
  - len2 (8,836): max out 2 — `'cb'` → `\x00\x00`
  - len3 (830,584): max out 3 — `'cba'` → `\x00\x00\x00`;
    no-NUL: 548 con output, max out 2 — `'ba` → `\r\r`, `>ba` → `ss`
  Comparación con OTROS lenguajes: NOT_DEMONSTRATED (no hay harness
  multi-lenguaje en el repo).

## 3. Composición de templates

Sistema de "plantillas de comportamiento" (eco, suma, loop).

- Beam search para ensamblar programas complejos a partir de bloques conocidos.
- Publicar un catálogo de templates reutilizables.
- **EN MARCHA**: `pipelines/template_composition.json` + stages `catalog`
  (publica bloques verificados por Zig como TemplateCatalog) y
  `compose` sobre el catálogo. Resultado medido: 8 primitivos → 64
  compuestos → 64/64 ejecutan y haltean, PERO negativo estructural
  importante: la concatenación es **prefix-dominated** — el `v` (halt)
  del primer bloque termina el programa y el segundo bloque nunca
  ejecuta (todos los compuestos que empiezan por el bloque "A" imprimen
  "A"). La composición real necesita reensamblado semántico (ej. quitar
  el halt del primer bloque), no concatenación cruda.
- Catálogo persistente versionado (`catalogs/`): PENDIENTE.

## 4. Integración multi-backend

Conectar Autobolge con intérpretes alternativos (Engine, Oracle,
Differential).

- Validar outputs en paralelo para detectar divergencias semánticas.
- Reportar mismatches como evidencia forense.
- **EN MARCHA**: stage `difftest` (Zig vs intérprete Python de referencia).
  `pipelines/multi_backend_difftest.json`: 3,000 programas len2 muestreados
  (seed 42) → **428 comparables, 0 mismatches**; 2,572 no-comparables
  por backend (desglose honesto: 2,509 InvalidOpcodeError — instrucción
  inválida al cargar, Zig la trata como dato — y 63 InputUnderflowError).
  La clave del artefacto incluye el hash del CÓDIGO del stage: un fix del
  motor invalida la evidencia vieja, no se cuele silenciosa.

## 5. Exploración probabilística

Heurísticas de búsqueda guiada (ej. rayos toroidales estilo Meowbolge).

- Objetivo: reducir tiempo en longitudes > 12.
- Documentar eficiencia comparada vs brute force.
- Hoy: baseline brute-force ya medido (len 7–10 en el README); falta la
  variante guiada + etapa `compare` contra esa baseline.

## 6. Repositorio de evidencia pública

Centralizar resultados en el MB-Database.

- Cada campaña → JSON + hash + log reproducible.
- "Atlas Malbolge" abierto para la comunidad.
- Hoy: `runs/<pipeline>/<stage>__<hash>/artifact.json` con provenance
  sha256 por nodo; falta el índice/publicación del atlas.
