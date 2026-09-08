"""A declared, scoped NOT EXISTS plan; unsupported absence stays closed."""
from semantic_layer.models import CompiledQuery, Mapping
from semantic_layer.runtime import periods


def compile_absence(compiler, q):
    if q.shape != "ABSENCE" or q.unresolved or q.unhandled or q.clarification or q.filters or q.comparison:
        return None
    subjects = {s.mapping.entity for s in q.slots if s.mapping}
    roots = {m.get("verb_root") for m in q.modifiers if m.get("decision") == "ABSENCE"}
    rules = [r for r in compiler.conventions.absence_rules if subjects == {r["subject"]} and roots == {r["verb_root"]}]
    if len(rules) != 1 or len(q.temporal) != 1:
        return None
    rule = rules[0]
    t = q.temporal[0]
    if not t.start or not t.end or t.ambiguous:
        return None
    d = compiler.d
    target, event, scope = rule["subject"], rule["event"], rule["scope_entity"]
    chosen = compiler._chosen(scope, q)
    if not chosen or len({compiler._firm_of(p) for p in chosen}) != 1:
        return None
    anchor = chosen[0].context
    sources, tables = {}, []
    for entity, columns in rule["columns"].items():
        selected = compiler._chosen(entity, q, spread=entity != target, anchor=anchor)
        if any(compiler._firm_of(p) != compiler._firm_of(chosen[0]) for p in selected):
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
    conditions += [f"{col(correlation[0],correlation[1])} = {col(target,correlation[3])}",
                   f"{col(scope,rule['date_column'])} >= '{t.start.isoformat()}'",
                   f"{col(scope,rule['date_column'])} < '{t.end.isoformat()}'"]
    top = f"TOP {int(q.limit)} " if q.limit and d.name == "tsql" else ""
    sql = f"SELECT {top}" + ", ".join(col(target,c) for c in rule["columns"][target])
    sql += f" FROM {sources[target]} AS {target} WHERE NOT EXISTS (SELECT 1 FROM {sources[event]} AS {event} JOIN {sources[scope]} AS {scope} ON {col(inner[0],inner[1])} = {col(inner[2],inner[3])} WHERE " + " AND ".join(conditions) + ")"
    sql += f" ORDER BY {col(target,rule['columns'][target][0])}"
    if q.limit and d.name != "tsql":
        sql += f" LIMIT {int(q.limit)}"
    window = periods.spans(compiler.tables_of.get(scope, []))
    if window and (t.end <= window[0] or t.start > window[1]):
        return None
    q.absence_contract = {"sql": sql, "subject": target, "event": event, "period": t.to_dict(), "reason": rule["reason"]}
    note = f"{t.start}–{t.end} dönemindeki mevcut kayıtlarda satış hareketi bulunmayan ürünler. Yükleme bütünlüğü doğrulanmadı; tüm geçmişte hiç satılmadığı anlamına gelmez."
    q.absence_contract["scope_note"] = note
    q.explanation.append(note)
    return CompiledQuery(sql=sql, compiler="deterministic_absence", tables=tables, catalog_version=q.catalog_version, explain=[rule["reason"],note], certified=True)
