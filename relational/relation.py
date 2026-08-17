from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Callable
from .state import MalbolgeSnapshot, MalbolgeStateWrapper
from .transition import Transition, TransitionSystem

@dataclass(frozen=True)
class Relation:
    """Represents a relation between two states - a behavioral constraint."""
    name: str
    precondition: Callable[[MalbolgeSnapshot], bool]
    postcondition: Callable[[MalbolgeSnapshot], bool]
    weight: float = 1.0

    def holds(self, state: MalbolgeSnapshot) -> bool:
        return self.precondition(state) and self.postcondition(state)

    def check_transition(self, from_state, to_state) -> bool:
        return self.precondition(from_state) and self.postcondition(to_state)

@dataclass
class RelationSet:
    """A set of relations that can be checked together."""
    relations: List[Relation] = field(default_factory=list)

    def add(self, relation):
        self.relations.append(relation)
    def check_all(self, state) -> Dict[str, bool]:
        return {r.name: r.holds(state) for r in self.relations}
    def check_transition(self, from_state, to_state) -> Dict[str, bool]:
        return {r.name: r.check_transition(from_state, to_state) for r in self.relations}

def compose_relations(r1, r2):
    """Compose two relations sequentially."""
    from typing import Callable
    def new_precondition(state):
        return r1.precondition(state)
    def new_postcondition(state):
        return r2.postcondition(state)
    return Relation(
        name=f"{r1.name}_then_{r2.name}",
        precondition=r1.precondition,
        postcondition=r2.postcondition,
        weight=min(r1.weight, r2.weight)
    )
