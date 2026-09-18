"""A declared, scoped NOT EXISTS plan; unsupported absence stays closed."""
import logging
import re

from semantic_layer.models import CompiledQuery, Mapping
from semantic_layer.runtime import periods

log = logging.getLogger(__name__)


def compile_absence(compiler, q):
    if q.shape != "ABSENCE" or q.unresolved or q.unhandled or q.clarification or q.comparison:
        return None
    # Filters are allowed only on the subject itself ("satış siparişi" = TRCODE 1 on the order
    # header): they narrow which subjects are looked at, not what counts as the absent event.
    subject_filters = [f for f in q.filters if f.mapping and f.mapping.entity]
    subjects = {s.mapping.entity for s in q.slots if s.mapping and str(s.semantic_type) not in ("DEFAULT_FILTER", "SemanticType.DEFAULT_FILTER")
                and not (s.explain or {}).get("absent")}          # the absent thing is the event, not the subject
    subject_filters = [f for f in subject_filters if not (f.explain or {}).get("absent")]
    roots = {m.get("verb_root") for m in q.modifiers if m.get("decision") == "ABSENCE"}
    from semantic_layer.normalize import stem as _stem
    def _bare(e: str) -> str:
        return re.sub(r"^LG_", "", str(e or "").upper())     # the catalog names a shape both ways
    rules = [r for r in compiler.conventions.absence_rules
             if {_bare(x) for x in subjects} == {_bare(r["subject"])} and {_stem(str(x or "")) for x in roots} == {_stem(str(r["verb_root"]))}]
    if len(rules) != 1 or len(q.temporal) > 1:
        log.info("absence: no declared rule for subjects=%s roots=%s (declared: %s)", sorted(subjects), sorted(map(str, roots)),
                 [(r["subject"], r["verb_root"]) for r in compiler.conventions.absence_rules])
        return None
    if any(_bare(f.mapping.entity) != _bare(rules[0]["subject"]) for f in subject_filters):
        log.info("absence: a filter outside the subject: %s", [(f.term, f.mapping.entity) for f in subject_filters])
        return None
    rule = rules[0]
    t = q.temporal[0] if q.temporal else None
    if t is not None and (not t.start or not t.end or t.ambiguous):
        return None
    if t is None and rule.get("requires_period", True):
        return None                            # "never sold" over an unbounded past is a different claim
    d = compiler.d
    target, event, scope = rule["subject"], rule["event"], rule["scope_entity"]
    chosen = compiler._chosen(scope, q)
    if not chosen or len({compiler._firm_of(p) for p in chosen}) != 1:
        return None
    anchor = chosen[0].context
    sources, tables = {}, []
    for entity, columns in rule["columns"].items():
        selected = compiler._chosen(entity, q, spread=entity != target, anchor=anchor)
        selected = [p for p in selected if compiler._firm_of(p) == compiler._firm_of(chosen[0])]
        if not selected:
            return None
        src, names, _ = compiler._source(entity, q, set(columns), entity, chosen=selected)
        sources[entity] = src
        tables += names
    def col(e, c):
        return f"{e}.{d.q(c)}"
    from semantic_layer.runtime.compiler import _pred_sql as compiled_predicate
    conditions = [compiled_predicate(p["entity"], Mapping("",p["entity"],"",column=p["column"],operator=p["operator"],values=p["values"]),d) for p in rule["predicates"]]
    links = rule["joins"]
    correlation = next(j for j in links if j[2] == target)
    inner = next(j for j in links if j[2] == scope)
    conditions += [f"{col(correlation[0],correlation[1])} = {col(target,correlation[3])}"]
    if t is not None:
        conditions += [f"{col(scope,rule['date_column'])} >= '{t.start.isoformat()}'",
                       f"{col(scope,rule['date_column'])} < '{t.end.isoformat()}'"]
    outer = []
    for f in subject_filters:
        m = f.mapping
        outer.append(compiled_predicate(target, m, d))
        for cond in (m.extra or {}).get("conditions") or []:
            outer.append(cond.replace(f"{m.entity}.", f"{target}."))
    for p in rule.get("subject_predicates") or []:
        outer.append(compiled_predicate(target, Mapping("",target,"",column=p["column"],operator=p["operator"],values=p["values"]), d))
    top = f"TOP {int(q.limit)} " if q.limit and d.name == "tsql" else ""
    sql = f"SELECT {top}" + ", ".join(col(target,c) for c in rule["columns"][target])
    sql += f" FROM {sources[target]} AS {target} WHERE " + "".join(f"{o} AND " for o in outer) + f"NOT EXISTS (SELECT 1 FROM {sources[event]} AS {event} JOIN {sources[scope]} AS {scope} ON {col(inner[0],inner[1])} = {col(inner[2],inner[3])} WHERE " + " AND ".join(conditions) + ")"
    sql += f" ORDER BY {col(target,rule['columns'][target][0])}"
    if q.limit and d.name != "tsql":
        sql += f" LIMIT {int(q.limit)}"
    window = periods.spans(compiler.tables_of.get(scope, []))
    if t is not None and window and (t.end <= window[0] or t.start > window[1]):
        return None
    q.absence_contract = {"sql": sql, "subject": target, "event": event, "period": t.to_dict() if t is not None else None, "reason": rule["reason"]}
    note = (f"{t.start}–{t.end} dönemindeki mevcut kayıtlarda {rule.get('event_label', 'satış hareketi')} bulunmayan {rule.get('subject_label', 'ürünler')}. Yükleme bütünlüğü doğrulanmadı; tüm geçmişte hiç olmadığı anlamına gelmez."
            if t is not None else f"Mevcut kayıtlarda {rule.get('event_label', 'satış hareketi')} bulunmayan {rule.get('subject_label', 'ürünler')} (yüklü tüm dönem).")
    q.absence_contract["scope_note"] = note
    q.explanation.append(note)
    return CompiledQuery(sql=sql, compiler="deterministic_absence", tables=tables, catalog_version=q.catalog_version, explain=[rule["reason"],note], certified=True)
