"""Presentation metadata from the executed SELECT, never from guessed column names."""
import sqlglot
from sqlglot import exp


def additive(node):
    if isinstance(node, (exp.Alias, exp.Paren)):
        return additive(node.this)
    if isinstance(node, (exp.Add, exp.Sub)):
        return additive(node.left) and additive(node.right)
    return isinstance(node, (exp.Sum, exp.Count)) and not node.find(exp.Distinct)


def presentation_spec(sql, result, query, compiler):
    try:
        tree = sqlglot.parse_one(sql, read="tsql")
        select = tree if isinstance(tree, exp.Select) else None
        if select is None:
            return {"metrics": [], "dimensions": [], "comparisons": []}
        columns = {c["name"] for c in result["columns"]}
        metrics, dimensions = [], []
        for item in select.expressions:
            key = item.alias_or_name
            if key not in columns:
                continue
            if item.find(exp.AggFunc):
                metrics.append({"key": key, "label": key.replace("_", " "), "additive": bool(additive(item))})
            else:
                dimensions.append({"key": key, "label": key.replace("_", " "),
                    "temporal": any(word in item.sql().upper() for word in ("MONTH(", "YEAR(", "DATEPART(", "DATE_TRUNC("))})
        comparisons = []
        if compiler == "deterministic" and query.comparison:
            from semantic_layer.runtime.compiler import _alias_of, _snake
            def key_for(period, metric):
                part = _snake(period["text"]) or "donem"
                return ("d" + part if part[0].isdigit() else part) + "_" + _alias_of(metric)
            current, reference = query.comparison.get("current"), query.comparison.get("reference")
            if current and reference:
                for metric in query.metrics:
                    ck, rk = key_for(current, metric), key_for(reference, metric)
                    if ck in columns and rk in columns:
                        comparisons.append({"currentKey": ck, "referenceKey": rk, "label": metric.term,
                                            "currentLabel": current["text"], "referenceLabel": reference["text"]})
        return {"metrics": metrics, "dimensions": dimensions, "comparisons": comparisons}
    except Exception:
        # Missing presentation metadata must never change the query result.
        return {"metrics": [], "dimensions": [], "comparisons": []}
