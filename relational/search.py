from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional, Set

from .state import MalbolgeSnapshot, MalbolgeStateWrapper, are_equivalent_states
from .transition import Transition, TransitionSystem, discover_transitions
from .relation import Relation, RelationSet
from .composition import Composition
from .materialization import Materialization


@dataclass
class SearchNode:
    """A node in the search tree."""

    state: MalbolgeSnapshot
    program: str
    depth: int
    parent: Optional["SearchNode"] = None
    transition: Optional[str] = None
    cost: float = 0.0

    def __lt__(self, other):
        return self.cost < other.cost


@dataclass
class SearchResult:
    """Result of a search."""

    success: bool
    final_state: Optional[MalbolgeSnapshot] = None
    program: str = ""
    nodes_explored: int = 0
    depth_reached: int = 0
    path: List[MalbolgeSnapshot] = field(default_factory=list)


class RelationalSearch:
    """Relational search for Malbolge programs."""

    def __init__(self, max_depth=100, max_nodes=10000):
        self.max_depth = max_depth
        self.max_nodes = max_nodes
        self.visited: Set[MalbolgeSnapshot] = set()
        self.transition_system = TransitionSystem()

    def search(self, initial_state, goal_relation, max_iterations=1000):
        """Beam-search for a program satisfying the goal relation.

        Grows the program one instruction at a time, expanding each prefix
        through its discoverable transitions, and checks the goal relation
        on the resulting state after each step.
        """
        frontier = [SearchNode(state=initial_state, program="", depth=0)]
        nodes_explored = 0
        best = None

        while frontier and nodes_explored < self.max_nodes:
            node = frontier.pop(0)
            nodes_explored += 1

            if node.depth >= self.max_depth:
                continue
            if node.state in self.visited:
                continue
            self.visited.add(node.state)

            transitions = discover_transitions(node.program)
            for t in transitions:
                if nodes_explored >= self.max_nodes:
                    break
                child = SearchNode(
                    state=t.to_state,
                    program=node.program + t.char,
                    depth=node.depth + 1,
                    parent=node,
                    transition=t.opcode,
                    cost=node.cost + t.step_cost,
                )
                if goal_relation.holds(t.to_state):
                    return SearchResult(
                        success=True,
                        final_state=t.to_state,
                        program=child.program,
                        nodes_explored=nodes_explored,
                        depth_reached=child.depth,
                        path=[node.state, t.to_state],
                    )
                if best is None or child.cost < best.cost:
                    best = child
                frontier.append(child)

        return SearchResult(
            success=False,
            final_state=best.state if best else None,
            program=best.program if best else "",
            nodes_explored=nodes_explored,
            depth_reached=best.depth if best else 0,
        )

    def bfs_search(self, initial_state, goal_test, max_depth=50):
        """Breadth-first search over discovered transitions."""
        from collections import deque

        queue = deque([(initial_state, [])])
        visited = set()

        while queue:
            state, path = queue.popleft()
            if state in visited:
                continue
            visited.add(state)

            if goal_test(state):
                return path

            if len(path) >= max_depth:
                continue

            for t in self.transition_system.get_transitions_from(state):
                queue.append((t.to_state, path + [t]))

        return None


def heuristic_search(initial_state, goal_relation, heuristic_fn, max_nodes=10000):
    """A* search with heuristic."""
    from queue import PriorityQueue

    search = RelationalSearch(max_nodes=max_nodes)
    return search.search(initial_state, goal_relation)


def synthesize(
    target_output: str,
    input_data: str = "",
    beam_width: int = 64,
    max_len: int = 48,
    max_evals: int = 200_000,
    max_steps: int = 20_000,
    seed: Optional[int] = None,
    progress_cb=None,
):
    """Convenience entry point: synthesize a program matching target_output."""
    from .materialization import Materialization

    m = Materialization(relations=[])
    return m.synthesize(
        target_output=target_output,
        input_data=input_data,
        beam_width=beam_width,
        max_len=max_len,
        max_evals=max_evals,
        max_steps=max_steps,
        seed=seed,
        progress_cb=progress_cb,
    )