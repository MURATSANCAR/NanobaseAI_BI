"""Approved join path graph from declared FKs."""

from __future__ import annotations

from dataclasses import dataclass, field

from nanobase_api.scenario_engine.infrastructure.schema_snapshot import SchemaSnapshot


@dataclass(frozen=True)
class JoinEdge:
    from_table: str
    to_table: str
    from_column: str
    to_column: str
    cardinality: str = "MANY_TO_ONE"  # default FK direction

    @property
    def approved(self) -> bool:
        return self.cardinality in ("MANY_TO_ONE", "ONE_TO_ONE")


@dataclass
class RelationshipGraph:
    edges: list[JoinEdge] = field(default_factory=list)

    def approved_edges(self) -> list[JoinEdge]:
        return [e for e in self.edges if e.approved and e.cardinality != "MANY_TO_MANY"]

    def path(self, from_table: str, to_table: str) -> list[JoinEdge] | None:
        """BFS shortest approved path."""
        if from_table == to_table:
            return []
        adj: dict[str, list[JoinEdge]] = {}
        for e in self.approved_edges():
            adj.setdefault(e.from_table, []).append(e)
            # allow reverse traversal for path finding
            rev = JoinEdge(e.to_table, e.from_table, e.to_column, e.from_column, "ONE_TO_MANY")
            adj.setdefault(e.to_table, []).append(rev)
        seen = {from_table}
        queue: list[tuple[str, list[JoinEdge]]] = [(from_table, [])]
        while queue:
            node, path = queue.pop(0)
            for e in adj.get(node, []):
                nxt = e.to_table
                if nxt in seen:
                    continue
                new_path = path + [e]
                if nxt == to_table:
                    return new_path
                seen.add(nxt)
                queue.append((nxt, new_path))
        return None


def build_relationship_graph(snapshot: SchemaSnapshot) -> RelationshipGraph:
    edges: list[JoinEdge] = []
    for fk in snapshot.foreign_keys:
        frm = fk.get("from") or ""
        to = fk.get("to") or ""
        if not frm or not to:
            continue
        f_parts = frm.rsplit(".", 1)
        t_parts = to.rsplit(".", 1)
        if len(f_parts) != 2 or len(t_parts) != 2:
            continue
        from_table, from_col = f_parts[0], f_parts[1]
        to_table, to_col = t_parts[0], t_parts[1]
        edges.append(
            JoinEdge(
                from_table=from_table,
                to_table=to_table,
                from_column=from_col,
                to_column=to_col,
                cardinality="MANY_TO_ONE",
            )
        )
    # Also derive from column fk_ref metadata
    for t in snapshot.tables:
        for c in t.columns:
            if c.fk_ref:
                t_parts = c.fk_ref.rsplit(".", 1)
                if len(t_parts) == 2:
                    edges.append(
                        JoinEdge(
                            from_table=t.fqn,
                            to_table=t_parts[0],
                            from_column=c.name,
                            to_column=t_parts[1],
                            cardinality="MANY_TO_ONE",
                        )
                    )
    # Dedupe
    uniq: dict[tuple[str, str, str, str], JoinEdge] = {}
    for e in edges:
        uniq[(e.from_table, e.to_table, e.from_column, e.to_column)] = e
    return RelationshipGraph(edges=list(uniq.values()))
