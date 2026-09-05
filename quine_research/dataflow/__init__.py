"""Autobolge dataflow: motor de campañas experimentales.

flujo: search -> classify -> select -> transform -> search -> compare -> verdict

Cada nodo produce un artefacto explícito en disco:
    runs/<pipeline>/<stage_id>__<hash>/artifact.json

Ninguna etapa conoce a otra: solo contratos (contracts.py) y rutas de
artefactos. El runner decide skip/rerun por hash de params+inputs.
"""
