"""Contratos del dataflow Autobolge.

Cada etapa produce exactamente UNO de estos artefactos (serializado a JSON).
El `kind` es discriminatorio; to_dict/from_dict hacen round-trip exacto.

Ninguna clase importa lógica de otra etapa: son datos puros.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class Contract:
    kind: str = "contract"


@dataclass
class SearchResult(Contract):
    """Salida de una búsqueda (frontier / exhaustiva / seeded)."""
    kind: str = "search_result"
    level: int = 0
    seeds: list[str] = field(default_factory=list)
    candidates_examined: int = 0
    exhaustive: bool = False
    rows: list[dict] = field(default_factory=list)  # {program, output, steps, terminated}
    rows_truncated: bool = False


@dataclass
class ClassifierResult(Contract):
    """Partición de un SearchResult en clases de comportamiento."""
    kind: str = "classifier_result"
    classes: dict[str, list[str]] = field(default_factory=dict)  # label -> programs
    counts: dict[str, int] = field(default_factory=dict)


@dataclass
class SelectionResult(Contract):
    """Subconjunto elegido de un ClassifierResult / SearchResult."""
    kind: str = "selection_result"
    selected: list[str] = field(default_factory=list)  # programas
    scores: dict[str, float] = field(default_factory=dict)  # program -> score
    rule: str = ""


@dataclass
class TransformResult(Contract):
    """Frontera derivada de una selección sin conocer el solver."""
    kind: str = "transform_result"
    op: str = ""  # compose | extend_length | mutate | seed_solver
    derived: list[str] = field(default_factory=list)  # programas
    provenance: str = ""  # descripción legible de la transformación


@dataclass
class CompareResult(Contract):
    """Diferencia entre dos artefactos del mismo tipo."""
    kind: str = "compare_result"
    left: str = ""   # stage id
    right: str = ""  # stage id
    only_left: int = 0
    only_right: int = 0
    shared: int = 0
    samples: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class Verdict(Contract):
    """Dictamen de campaña: gates evaluados + resumen legible."""
    kind: str = "verdict"
    gates: dict[str, bool] = field(default_factory=dict)
    summary: str = ""
    closed: bool = False  # True => no tiene sentido re-correr esta campaña


CONTRACTS = {
    c.kind: c
    for c in (SearchResult, ClassifierResult, SelectionResult,
              TransformResult, CompareResult, Verdict)
}


def contract_from_dict(d: dict) -> Contract:
    kind = d.get("kind")
    cls = CONTRACTS.get(kind)
    if cls is None:
        raise ValueError(f"unknown contract kind: {kind!r}")
    init_fields = {f for f in cls.__dataclass_fields__ if f != "kind"}
    return cls(**{k: v for k, v in d.items() if k in init_fields})


def contract_to_dict(c: Contract) -> dict:
    return asdict(c)
