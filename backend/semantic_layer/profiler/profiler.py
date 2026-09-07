"""Profiler — "what exists in this data world": tables, columns, types, enum values with frequencies,
keys, relationships and the table-name pattern each table follows.
Output: SchemaProfile rows (sl_schema_profile)."""

from __future__ import annotations

import logging
import os
import re
import time
from typing import Any, Optional

from semantic_layer.models import ColumnProfile, SchemaProfile
from semantic_layer.naming import disambiguate, logical_table
from semantic_layer.profiler import sensitivity
from semantic_layer.profiler.connectors import Connector, ModelFileConnector

log = logging.getLogger(__name__)

# Value inventories are only useful for short, low-cardinality columns; everything else is skipped
# on shape alone (type, key role, text width) — never on a customer's column names.
_ENUM_TYPES = ("smallint", "tinyint", "int", "integer", "bit", "char", "varchar", "nvarchar", "nchar", "boolean", "bool", "enum")
_SKIP_TYPES = ("date", "time", "timestamp", "binary", "blob", "clob", "image", "xml", "json", "uuid", "guid", "text", "ntext")
_MAX_CODE_WIDTH = 32


def _enum_candidate(col: dict[str, Any], *, is_key: bool, is_ref: bool, sample: list[Any] | None = None) -> bool:
    """Shape-only test: not a key, not a reference, not a wide/opaque type. When the declared type says
    nothing useful (an unsized TEXT), the row sample decides: short values that repeat are a code list."""
    if is_key or is_ref:
        return False
    dt = str(col.get("data_type") or "").lower()
    if any(t in dt for t in _SKIP_TYPES):
        values = [str(v) for v in (sample or []) if v is not None]
        if not values or any(t in dt for t in ("date", "time", "binary", "blob", "image", "json", "xml")):
            return False
        short = all(len(v) <= _MAX_CODE_WIDTH for v in values)
        repeating = len(set(values)) <= max(2, len(values) // 2)
        return short and repeating
    if dt.startswith(("varchar", "nvarchar", "char", "nchar")):
        m = re.search(r"\((\d+)\)", dt)
        return int(m.group(1)) <= _MAX_CODE_WIDTH if m else True  # unsized (MDL import): let the probe decide
    return dt.startswith(_ENUM_TYPES)


class Profiler:
    def __init__(self, connector: Connector, *, enum_max_distinct: int = 64, top_n: int = 12, max_tables: int = 300, sample_rows: int = 20,
                 deep_budget_seconds: Optional[float] = None, max_probes_per_table: int = 40):
        self.c = connector
        self.enum_max_distinct = enum_max_distinct
        self.top_n = top_n
        self.max_tables = max_tables
        self.sample_rows = sample_rows
        self.deep_budget_seconds = deep_budget_seconds if deep_budget_seconds is not None else float(os.environ.get("SEMANTIC_DEEP_BUDGET_SEC", "1800"))
        self.max_probes_per_table = max_probes_per_table
        self.deep_skipped: list[str] = []
        self.truncated: list[str] = []

    def _sample(self, schema: str, table: str) -> dict[str, list[Any]]:
        """column (upper) → the values seen in a bounded row sample; empty when sampling is unavailable."""
        if self.sample_rows <= 0 or not hasattr(self.c, "sample_rows"):
            return {}
        try:
            rows = self.c.sample_rows(schema, table, self.sample_rows) or []
        except Exception as e:  # noqa: BLE001
            log.debug("sample failed %s.%s: %s", schema, table, e)
            return {}
        out: dict[str, list[Any]] = {}
        for row in rows:
            for k, v in row.items():
                out.setdefault(str(k).upper(), []).append(v)
        return out

    def _time_window(self, schema: str, table: str, columns: list[ColumnProfile]) -> Optional[tuple[str, str]]:
        """The period this table actually holds. One query, and it is what lets the system say "there is
        no 2019 data here" instead of returning an empty result as if it were an answer."""
        time_cols = [c for c in columns if any(t in c.data_type.lower() for t in ("date", "time", "timestamp"))]
        if not time_cols or not getattr(self.c, "supports_execution", False):
            return None
        col = time_cols[0].name
        q = getattr(self.c, "q", lambda x: f'"{x}"')
        target = f"{q(schema)}.{q(table)}" if schema and getattr(self.c, "dialect", "") != "sqlite" else q(table)
        try:
            _, rows, _ = self.c.execute(f"SELECT MIN({q(col)}) AS a, MAX({q(col)}) AS b FROM {target}", 1)
        except Exception as e:  # noqa: BLE001
            log.debug("time window probe failed %s.%s: %s", table, col, e)
            return None
        if not rows:
            return None
        values = [str(v)[:10] for v in rows[0].values() if v is not None]
        return (values[0], values[1]) if len(values) == 2 else None

    def _bulk_row_counts(self, schema: str, names: list[str]) -> dict[str, Optional[int]]:
        """All the counts at once where the engine offers it, one at a time where it does not."""
        bulk: dict[str, int] = {}
        if hasattr(self.c, "row_counts"):
            try:
                bulk = self.c.row_counts(schema) or {}
            except Exception as e:  # noqa: BLE001
                log.debug("bulk row counts failed: %s", e)
        return {n: (bulk.get(n) if n in bulk else self.c.row_count(schema, n)) for n in names}

    def profile(self, datasource_id: str, schema: str = "", like: Optional[str] = None, *, deep_limit: Optional[int] = None) -> list[SchemaProfile]:
        """`deep_limit` caps how many tables get value inventories and row samples; the rest are still
        catalogued (names, columns, keys) so nothing disappears, they simply are not probed."""
        discovered = self.c.list_tables(schema, like)
        tables = discovered
        if len(discovered) > self.max_tables:
            # Which tables to drop is a decision about value, not about the alphabet. Cutting the list
            # where it happens to end left behind the table that defines what this database's own codes
            # mean, purely because of its initial. The same volume-and-centrality score that picks the
            # deep set picks what is worth cataloguing at all.
            counts = self._bulk_row_counts(schema, [t for _, t in discovered])
            refs: dict[str, int] = {}
            for fk in self.c.foreign_keys(schema):
                refs[fk["ref_table"]] = refs.get(fk["ref_table"], 0) + 1
            score = dict(rank_tables({t: counts.get(t) for _, t in discovered}, refs))
            ordered = sorted(discovered, key=lambda st: -score.get(st[1], 0.0))
            tables, dropped = ordered[: self.max_tables], ordered[self.max_tables:]
            self.truncated = [t for _, t in dropped]
            biggest = sorted(((counts.get(t) or 0, t) for t in self.truncated), reverse=True)[:5]
            log.warning("scope matched %d tables; cataloguing the %d that carry the most (volume + centrality) — %d left out%s",
                        len(discovered), len(tables), len(self.truncated),
                        (", largest dropped: " + ", ".join(f"{t} ({n})" for n, t in biggest if n)) if biggest else "")
        names = [logical_table(t, sch) for sch, t in tables]
        entity_by_pattern = disambiguate([(lt.entity, lt.table_pattern) for lt in names])
        fks = self.c.foreign_keys(schema)
        # What the people who built this database wrote about it. Read once for the whole schema, so a
        # documented source costs one query rather than one per table, and an engine that keeps no
        # comments simply contributes nothing.
        try:
            described = self.c.descriptions(schema) if hasattr(self.c, "descriptions") else {}
        except Exception as e:  # noqa: BLE001
            log.debug("schema descriptions unavailable: %s", e)
            described = {}
        if described:
            log.info("source documents itself: %d table/column descriptions found", len(described))
        fk_by_table: dict[str, list[dict[str, str]]] = {}
        for fk in fks:
            fk_by_table.setdefault(fk["table"].upper(), []).append(fk)
        # Which tables earn the expensive treatment (value inventories, row samples): the ones that carry
        # data and that other tables point at. The rest are still catalogued, just not probed.
        deep: Optional[set[str]] = None
        if deep_limit is not None and len(tables) > deep_limit:
            counts = self._bulk_row_counts(schema, [t for _, t in tables])
            refs: dict[str, int] = {}
            for fk in fks:
                refs[fk["ref_table"]] = refs.get(fk["ref_table"], 0) + 1
            ranked = rank_tables(counts, refs)
            deep = {name for name, _ in ranked[:deep_limit]}
            log.info("profiling %d/%d tables deeply (volume + centrality)", len(deep), len(tables))
        out: list[SchemaProfile] = []
        started = time.time()
        deep_done = 0
        budget_spent: list[str] = []
        for index, ((sch, table), lt) in enumerate(zip(tables, names), start=1):
            entity = entity_by_pattern.get(lt.table_pattern, lt.entity)
            pk = self.c.primary_keys(sch, table)
            is_deep = deep is None or table in deep
            # A value inventory over a large table is a full scan per column. Give the whole deep phase a
            # wall clock, so a slow source degrades to a catalogued-but-unprobed schema instead of a
            # deployment that never finishes — and say out loud which tables that cost.
            if is_deep and self.deep_budget_seconds and time.time() - started > self.deep_budget_seconds:
                is_deep = False
                budget_spent.append(table)
            t_table = time.time()
            sample = self._sample(sch, table) if is_deep else {}
            cols: list[ColumnProfile] = []
            rels: list[dict[str, str]] = []
            probes_left = self.max_probes_per_table
            for col in self.c.columns(sch, table):
                cp = ColumnProfile(name=col["name"], data_type=str(col.get("data_type") or ""), nullable=bool(col.get("nullable", True)), is_primary_key=col["name"] in pk or bool(col.get("pk")),
                                   description=col.get("description") or described.get((table, col["name"])))
                observed = [v for v in sample.get(cp.name.upper(), []) if v is not None and str(v) != ""]
                reason = sensitivity.name_is_sensitive(cp.name) or sensitivity.values_are_sensitive([str(v) for v in observed])
                if reason:
                    cp.sensitive, cp.sensitivity_reason = True, reason
                seen = sample.get(cp.name.upper(), [])
                if seen:
                    cp.null_ratio = round(sum(1 for v in seen if v is None) / len(seen), 3)
                fk = next((f for f in fk_by_table.get(table.upper(), []) if f["column"].upper() == col["name"].upper()), None)
                if fk:
                    ref_lt = logical_table(fk["ref_table"], sch)
                    cp.ref_entity = entity_by_pattern.get(ref_lt.table_pattern, ref_lt.entity)
                    cp.ref_column = fk["ref_column"]
                if cp.ref_entity:
                    rels.append({"column": cp.name, "ref_entity": cp.ref_entity, "ref_column": cp.ref_column or ""})
                if is_deep and probes_left > 0 and not cp.sensitive and _enum_candidate(col, is_key=cp.is_primary_key, is_ref=bool(cp.ref_entity), sample=sample.get(cp.name.upper())):
                    probes_left -= 1
                    try:
                        hint = self.c.distinct_hint(table, col["name"]) if hasattr(self.c, "distinct_hint") else None
                        top = self.c.top_values(sch, table, col["name"], self.enum_max_distinct + 1)
                        # A column named innocuously can still hold personal data — check the sample too,
                        # and drop it before anything is stored.
                        reason = sensitivity.values_are_sensitive([v for v, _ in top])
                        if reason:
                            cp.sensitive, cp.sensitivity_reason, top = True, reason, []
                        if top and len(top) <= self.enum_max_distinct:
                            cp.top_values = top[: self.enum_max_distinct]
                            cp.distinct_count = hint if hint is not None else len(top)
                        elif top:
                            cp.top_values = top[: self.top_n]
                            cp.distinct_count = hint if hint is not None else len(top)
                    except Exception as e:  # noqa: BLE001
                        log.debug("top_values failed %s.%s: %s", table, col["name"], e)
                _mark_sentinels(cp, [str(v) for v in sample.get(cp.name.upper(), []) if v is not None])
                cols.append(cp)
            desc = (self.c.table_description(table) if hasattr(self.c, "table_description") else None) or described.get((table, None))
            window = self._time_window(sch, table, cols) if is_deep else None
            if is_deep:
                deep_done += 1
                log.info("profiled %s (%d/%d, %d columns, %.1fs, toplam %.0fs)", table, index, len(tables), len(cols), time.time() - t_table, time.time() - started)
            elif index % 25 == 0:
                log.info("catalogued %d/%d tables (%.0fs)", index, len(tables), time.time() - started)
            out.append(
                SchemaProfile(
                    datasource_id=datasource_id,
                    table_name=table,
                    table_pattern=lt.table_pattern,
                    entity=entity,
                    schema_name=sch,
                    columns=cols,
                    primary_key=pk,
                    relationships=rels,
                    row_count=self.c.row_count(sch, table),
                    description=desc,
                    time_window=window,
                    context=dict(lt.context),
                )
            )
        if budget_spent:
            self.deep_skipped = budget_spent
            log.warning("deep profiling budget (%.0fs) spent after %d tables; %d left catalogued but unprobed: %s",
                        self.deep_budget_seconds, deep_done, len(budget_spent), ", ".join(budget_spent[:10]))
        # drop relationships whose target entity is not profiled (keeps the graph honest)
        entities = {p.entity for p in out}
        for p in out:
            p.relationships = [r for r in p.relationships if r["ref_entity"] in entities]
            for c in p.columns:
                if c.ref_entity and c.ref_entity not in entities:
                    c.ref_entity, c.ref_column = None, None
        return out


# Values that mean "no value" rather than a real one. A reference column stores 0/-1 for "unset", and a
# measure that is only filled once a background process has run reads 0 until then — counting either as
# data silently corrupts averages, ratios and joins.
_ABSENT_MARKERS = ("0", "-1", "")


def _mark_sentinels(col: ColumnProfile, sample: list[str] | None = None) -> None:
    """A reference column stores 0/-1 for "unset"; a measure filled by a later process reads 0 until then.
    Either counted as data corrupts averages, ratios and joins — so mark them, from the value inventory
    when there is one and otherwise from the row sample."""
    if col.ref_entity:
        col.sentinel_values = [v for v in _ABSENT_MARKERS if v != ""]
        return
    if col.is_primary_key or not _is_numeric_type(col.data_type):
        return
    pairs = col.top_values or [(v, 1) for v in (sample or [])]
    if not pairs:
        return
    total = sum(n for _, n in pairs) or 1
    for value in ("0", "0.0", ""):
        hits = sum(n for v, n in pairs if str(v).strip() in (value, "0", "0.0") and value != "")
        if value and hits / total >= 0.25 and value not in col.sentinel_values:
            col.sentinel_values.append("0")
            break


def _key_shaped(col: ColumnProfile, row_count: Optional[int]) -> bool:
    """Could this column hold references? A key takes many different values relative to the table's size;
    a status or type code takes a handful whatever the size. Decided from the measured spread, so it holds
    on a 30-row fixture and on a 2-million-row fact table alike."""
    distinct = col.distinct_count if col.distinct_count is not None else (len(col.top_values) or None)
    if distinct is not None and distinct <= 2:
        return False
    if distinct is not None and row_count:
        return (distinct / max(1, row_count)) >= 0.05
    return True                      # unknown spread: let the value-overlap test decide


def _is_numeric_type(data_type: str) -> bool:
    return any(t in (data_type or "").lower() for t in ("int", "float", "decimal", "numeric", "money", "real", "double"))


def column_index(profiles: list[SchemaProfile]) -> dict[str, set[str]]:
    return {p.entity: {c.name.upper() for c in p.columns} for p in profiles}


def rank_tables(rows: dict[str, Optional[int]], references: dict[str, int]) -> list[tuple[str, float]]:
    """Which tables deserve the expensive treatment, decided from the data world itself: volume says the
    table is used, and being referenced by other tables says it is central. Both are normalised so neither
    a huge log table nor a tiny lookup dominates."""
    import math

    scored = []
    max_ref = max(references.values() or [1]) or 1
    for name, count in rows.items():
        volume = math.log10(max(1, count or 1)) / 8.0            # 10^8 rows ≈ 1.0
        centrality = references.get(name, 0) / max_ref
        scored.append((name, round(min(1.0, volume) * 0.5 + centrality * 0.5, 4)))
    scored.sort(key=lambda x: -x[1])
    return scored


def infer_links(
    profiles: list[SchemaProfile],
    connector: Connector,
    *,
    sample: int = 40,
    min_overlap: float = 0.95,
    min_values: int = 5,
    max_columns_per_table: int = 20,
    max_targets: int = 30,
    max_probes: int = 2000,
    max_target_rows: Optional[int] = 5_000_000,
    deadline_seconds: float = 300.0,
) -> int:
    """Relationships where the database declares no foreign keys: sample a column's values and keep the
    link when they are contained in another table's single-column key. Pure data evidence — no naming
    conventions.

    Every dimension of this search is bounded, because it runs against a customer's live database: the
    candidate columns per table, the target tables (smallest first, huge ones skipped), the total number
    of probes and the wall-clock budget. Values already collected during profiling are reused instead of
    re-aggregating the same column. Whatever the budget does not cover is simply not inferred — the
    catalog stays smaller rather than the database being hammered.
    """
    started = time.monotonic()
    probes = 0
    added = 0
    keys: list[tuple[SchemaProfile, str]] = [(p, p.primary_key[0]) for p in profiles if len(p.primary_key) == 1]
    keys = [(p, k) for p, k in keys if max_target_rows is None or (p.row_count or 0) <= max_target_rows]
    keys.sort(key=lambda pk: pk[0].row_count if pk[0].row_count is not None else 0)
    keys = keys[:max_targets]
    if not keys:
        return 0
    for p in profiles:
        known = {r["column"].upper() for r in p.relationships}
        candidates = [
            c for c in p.columns
            if not c.is_primary_key
            and c.name.upper() not in known
            and not c.ref_entity
            and not c.sensitive
            and any(t in c.data_type.lower() for t in ("int", "bigint", "smallint"))
            and _key_shaped(c, p.row_count)   # a type code repeats; a key spreads
        ][:max_columns_per_table]
        for col in candidates:
            if probes >= max_probes or time.monotonic() - started > deadline_seconds:
                log.warning("link inference stopped at its budget (%d probes, %.0fs) — %d links found", probes, time.monotonic() - started, added)
                return added
            values = [v for v, _ in (col.top_values or [])]
            if not values:
                try:
                    values = [v for v, _ in connector.top_values(p.schema_name, p.table_name, col.name, sample)]
                    probes += 1
                except Exception as e:  # noqa: BLE001
                    log.debug("link probe failed %s.%s: %s", p.table_name, col.name, e)
                    continue
            values = [str(v) for v in values if str(v).lstrip("-").isdigit()]
            values = [v for v in values if v not in set(col.sentinel_values) | {"0", "-1"}][:sample]
            if len(values) < min_values:
                continue
            best: Optional[tuple[float, SchemaProfile, str]] = None
            for target, key in keys:
                if target.entity == p.entity or probes >= max_probes:
                    continue
                probes += 1
                try:
                    rows = connector.execute(
                        f'SELECT COUNT(*) AS n FROM {connector.q(target.schema_name)}.{connector.q(target.table_name)} WHERE {connector.q(key)} IN ({", ".join(values)})'
                        if getattr(connector, "quote_l", '"') == "["
                        else f'SELECT COUNT(*) AS n FROM {connector.q(target.table_name)} WHERE {connector.q(key)} IN ({", ".join(values)})',
                        1,
                    )[1]
                except Exception:  # noqa: BLE001
                    continue
                n = int(list(rows[0].values())[0]) if rows else 0
                ratio = n / len(values)
                if ratio >= min_overlap and (best is None or ratio > best[0]):
                    best = (ratio, target, key)
                    if ratio >= 0.999:
                        break            # a perfect containment needs no further comparison
            if best is not None:
                col.ref_entity, col.ref_column = best[1].entity, best[2]
                p.relationships.append({"column": col.name, "ref_entity": best[1].entity, "ref_column": best[2], "source": "value-overlap", "confidence": round(best[0], 3)})
                added += 1
    return added



def profile_summary(profiles: list[SchemaProfile]) -> dict[str, Any]:
    return {
        "tables": len(profiles),
        "columns": sum(len(p.columns) for p in profiles),
        "enum_columns": sum(1 for p in profiles for c in p.columns if c.is_enum()),
        "relationships": sum(len(p.relationships) for p in profiles),
        "entities": sorted(p.entity for p in profiles),
    }
