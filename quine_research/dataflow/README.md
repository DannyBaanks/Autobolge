# Autobolge Dataflow

Motor de campañas experimentales. Autobolge deja de ser "un buscador"
(`target -> search -> verdict`) y pasa a ser un flujo entre búsquedas:

```
frontier -> classify -> select -> transform -> frontier' -> compare -> verdict
```

## Principios

1. **Cada nodo produce un artefacto explícito**: `runs/<pipeline>/<stage>__<hash>/artifact.json`.
   Nada de "el siguiente proceso sabe mágicamente qué pasó".
2. **Contratos, no conocimiento cruzado**: cada etapa consume/produce uno de
   los contratos de `contracts.py` (`SearchResult`, `ClassifierResult`,
   `SelectionResult`, `TransformResult`, `CompareResult`, `Verdict`).
   `classify` no sabe qué es el solver; `verdict` no sabe qué es Zig.
3. **No-rerun por hash**: la clave de un nodo es
   `sha256(params + sha256 de artefactos upstream)`. Si nada cambió, SKIP.
   Si cambiaste `params` de un nodo, solo ese nodo y sus downstreams recalculan.
   Esto es lo que evita reventar 200 millones de Malbolges dos veces.
4. **Orquestación por sustrato, paralelismo dentro del ejecutor**:
   `EXECUTORS` en `stages.py` decide qué sustrato corre cada nodo
   (`frontier` -> Zig batch; el resto -> Python). La frontera entre
   ejecutores se cruza por LOTES (un artefacto entero), nunca candidato
   por candidato. Dentro de un nodo pesado se pueden usar workers (ver
   `--workers N` en `hybrid_scale_ABC.py`).

## Uso

```powershell
py quine_research\dataflow\run_pipeline.py quine_research\dataflow\pipelines\hi_frontier.json
py quine_research\dataflow\run_pipeline.py <pipeline.json> --force   # ignora cache
```

Pipelines declarativos en JSON: `pipelines/`. Ejemplo ejecutado:
`hi_frontier.json` (frontier len2 exhaustivo 8,836 -> classify -> select
output_only top 50 -> extend_length -> frontier len3 (4,700) -> classify
-> compare -> verdict con gates).

## Tests

```powershell
py -m pytest quine_research/tests/test_dataflow.py -q
```
