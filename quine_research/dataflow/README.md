# Autobolge Dataflow

Motor de campañas experimentales. Autobolge deja de ser "un buscador"
(`target -> search -> verdict`) y pasa a ser un flujo entre búsquedas:

```
frontier -> classify -> select -> transform -> frontier' -> compare -> verdict
    \-> transform(seed_solver: outputs observados como targets)
        -> solve (translator generator + verificación zig, workers opcionales)
        -> verdict
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

## Template de lens (coordenadas relativas)

`frontier_campaign.template.json` no sabe qué es "len3": los ids son
lógicos (`f1`, `f2`, `f3`...) y las longitudes físicas entran por
`--var`:

```powershell
# Assembly A: 2 -> 3 -> 4
py quine_research\dataflow\run_pipeline.py quine_research\dataflow\pipelines\frontier_campaign.template.json --var L1=2 --var L2=3 --var L3=4 --var TOP_N=50 --var WORKERS=4
# Assembly B: 3 -> 4 -> 5   (c1 de A sigue siendo c1 aquí: otro físico, otro hash)
py quine_research\dataflow\run_pipeline.py quine_research\dataflow\pipelines\frontier_campaign.template.json --var L1=3 --var L2=4 --var L3=5 --var TOP_N=50 --var WORKERS=4
# Donde quepa, incluso no consecutivas: 2 -> 4 -> 5 reutiliza f1..t1 de A
py quine_research\dataflow\run_pipeline.py quine_research\dataflow\pipelines\frontier_campaign.template.json --var L1=2 --var L2=4 --var L3=5 --var TOP_N=50 --var WORKERS=4
```

Dos assemblies en el mismo namespace `frontier_campaign`: el puesto lógico
es el mismo id, el físico cambia el hash, así que no pisan artefactos y lo
que coincide se reutiliza (no-rerun entre campañas). El artefacto `frontier`
registra el `level` físico REAL de los programas ejecutados — con mappings
no consecutivos puede diferir del `L` declarado, y eso queda a la vista.

Verificado en vivo:
- A(2,3,4): 14 nodos, SOLVE 4/4, gates PASS; rerun completo = 14× SKIP.
- B(3,4,5): exhaustivo físico 3 = 830,584 candidatos en 6.7s
  (1 prefix_match detectado), SOLVE 4/4.
- Ensayo (2,4,5): `f1..t1` SKIP (reusados de A), resto recalcula.

## Tests

```powershell
py -m pytest quine_research/tests/test_dataflow.py -q
```
