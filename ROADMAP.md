# Roadmap de Autobolge

Roadmap de campañas. Cada ítem indica dónde vive hoy la infraestructura que
lo soporta (el dataflow ya da artefactos hasheados + no-rerun para todos).

## 1. Síntesis multi-caracter (L11–L12)

Extender el catálogo más allá de longitud 10.

- Objetivo: outputs de más de 2 caracteres (ej. "HI!", "BYE").
- Documentar tanto hallazgos como resultados negativos.
- Hoy: `frontier_campaign.template.json` con `--var L1=… --var L2=… --var L3=…`
  (no-rerun protege lo ya exhausto, ej. len10 0 hits).

## 2. Verificación Busy Beaver

Campañas para detectar programas que maximizan output antes de halting.

- Comparar con benchmarks de otros lenguajes esotéricos.
- Guardar evidencia reproducible (JSON + hash).
- Hoy: `frontier` (SearchResult con output/steps/terminated) → `classify`;
  falta un criterio de selección `by=output_len` + comparación externa.

## 3. Composición de templates

Sistema de "plantillas de comportamiento" (eco, suma, loop).

- Beam search para ensamblar programas complejos a partir de bloques conocidos.
- Publicar un catálogo de templates reutilizables.
- Hoy: `transform` ya tiene `compose` (pairwise); falta catálogo persistente
  de bloques y beam assembly.

## 4. Integración multi-backend

Conectar Autobolge con intérpretes alternativos (Engine, Oracle,
Differential).

- Validar outputs en paralelo para detectar divergencias semánticas.
- Reportar mismatches como evidencia forense.
- Hoy: verificación dual Python↔Zig existe en el solver; falta generalizar
  `difftest` como etapa del dataflow (un SearchResult por backend + compare).

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
