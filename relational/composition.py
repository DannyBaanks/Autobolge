from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Callable
from .relation import Relation, RelationSet
from .state import MalbolgeSnapshot

@dataclass
class Composition:
    """Represents the composition of multiple relations."""
    relations: List[Relation]

    def evaluate(self, state):
        """Evaluate all relations on a state."""
        return {r.name: r.holds(state) for r in self.relations}

    def evaluate_transition(self, from_state, to_state):
        return {r.name: r.check_transition(from_state, to_state) for r in self.relations}

    def add(self, relation):
        self.relations.append(relation)

    def __and__(self, other):
        """Compose with another composition (sequential)."""
        return Composition(relations=self.relations + other.relations)

    def __or__(self, other):
        """Compose with another composition (parallel/alternative)."""
        return Composition(relations=self.relations + other.relations)

def compose_sequential(comp1, comp2):
    """Compose two compositions sequentially."""
    return Composition(relations=comp1.relations + comp2.relations)

def compose_parallel(comp1, comp2):
    """Compose two compositions in parallel."""
    return Composition(relations=comp1.relations + comp2.relations)

def compose_all(compositions):
    """Compose multiple compositions."""
    all_relations = []
    for c in compositions:
        all_relations.extend(c.relations)
    return Composition(relations=all_relations)
