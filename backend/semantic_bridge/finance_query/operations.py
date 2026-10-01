"""Typed aggregate-result operations; no model expression is evaluated as code."""
from decimal import Decimal, InvalidOperation
from .contracts import ContractError


def analytics(rows, specs, metrics, group_fields):
    """Aggregate-level analytics. Every remainder preserves signed totals."""
    for spec in specs:
        groups = {}
        keys = spec.get("group_by", [])
        for row in rows:
            groups.setdefault(tuple(row.get(k) for k in keys), []).append(row)
        output = []
        metric = spec["metric"]
        for key, members in groups.items():
            members = sorted(members, key=lambda r:(decimal(r.get(metric)) or Decimal(0), str(tuple(r.get(k) for k in group_fields))), reverse=True)
            if spec["op"] == "contribution":
                total = sum((decimal(r.get(metric)) or Decimal(0) for r in members), Decimal(0))
                running = Decimal(0)
                for row in members:
                    value = decimal(row.get(metric))
                    running += value or Decimal(0)
                    output.append({**row, spec["id"]+"_group_total": total,
                                   spec["id"]+"_share_pct": None if total == 0 or value is None else value/total*100,
                                   spec["id"]+"_cumulative_pct": None if total == 0 else running/total*100})
            elif spec["op"] == "top_remainder":
                limit = spec["limit"]
                group_output = [{**row, "row_kind": "Detay"} for row in members[:limit]]
                rest = members[limit:]
                if rest:
                    remainder = {k: None for k in rest[0]}
                    remainder.update(dict(zip(keys, key)))
                    remainder.update({m:sum((decimal(r.get(m)) or Decimal(0) for r in rest),Decimal(0)) for m in metrics})
                    remainder["row_kind"] = spec.get("label") or "Kalan"
                    group_output.append(remainder)
                for metric_id in metrics:
                    before = sum((decimal(row.get(metric_id)) or Decimal(0) for row in members), Decimal(0))
                    after = sum((decimal(row.get(metric_id)) or Decimal(0) for row in group_output), Decimal(0))
                    if before != after:
                        raise ContractError("İlk N ve kalan ayrımında ölçü toplamı değişti.", code="SOURCE_CONTRACT_VIOLATION")
                output.extend(group_output)
            else:
                raise ContractError("Analitik işlem tanımlı değil.", code="PLAN_INVALID")
        rows = output
    return rows


def decimal(value):
    if value is None:
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ContractError("Hesap girdisi sayısal değil.", code="SOURCE_CONTRACT_VIOLATION")
    if not result.is_finite():
        raise ContractError("Hesap girdisi sonlu değil.", code="SOURCE_CONTRACT_VIOLATION")
    return result


def calculate(op, left, right, scale=1):
    a, b = decimal(left), decimal(right)
    if a is None or b is None:
        return None
    if op == "difference":
        return a - b
    if op == "ratio":
        return None if b == 0 else a / b * decimal(scale)
    if op == "percent_change":
        return None if b == 0 else (a - b) / b * Decimal(100)
    raise ContractError("Tanımsız türetilmiş hesap işlemi.", code="PLAN_INVALID")


def derived(rows, specs):
    for row in rows:
        for spec in specs:
            row[spec.id] = calculate(spec.op, row.get(spec.left), row.get(spec.right), spec.scale)
    return rows


def compare(period_rows, plan, group_fields):
    spec = plan.comparison
    base, target = {}, {}
    for index, rows in enumerate(period_rows):
        if index not in (spec.base_period, spec.target_period):
            continue
        dest = base if index == spec.base_period else target
        for row in rows:
            key = tuple(row.get(k) for k in group_fields)
            if key in dest:
                raise ContractError("Dönem karşılaştırma anahtarı tekil değil.", code="SOURCE_CONTRACT_VIOLATION")
            dest[key] = row.get(spec.metric)
    a, b = plan.periods[spec.base_period], plan.periods[spec.target_period]
    return [{**dict(zip(group_fields, key)), "base_period_start": a[0], "base_period_end_exclusive": a[1],
             "target_period_start": b[0], "target_period_end_exclusive": b[1],
             "base_value": base.get(key), "target_value": target.get(key),
             spec.id: calculate(spec.op, target.get(key), base.get(key))}
            for key in dict.fromkeys([*base, *target])]


def finish(rows, plan, group_fields):
    operators = {"gt": lambda a,b:a>b, "gte": lambda a,b:a>=b, "lt": lambda a,b:a<b,
                 "lte": lambda a,b:a<=b, "eq": lambda a,b:a==b, "neq": lambda a,b:a!=b}
    for predicate in plan.having:
        if predicate.op not in operators:
            raise ContractError("Tanımsız sonuç filtresi.", code="PLAN_INVALID")
        threshold = decimal(predicate.value)
        rows = [row for row in rows if row.get(predicate.metric) is not None
                and operators[predicate.op](decimal(row[predicate.metric]), threshold)]
    # NULL stays last in either direction; secondary sort preserves deterministic ties.
    present = [row for row in rows if row.get(plan.order_by) is not None]
    missing = [row for row in rows if row.get(plan.order_by) is None]
    present.sort(key=lambda r:(decimal(r[plan.order_by]), str(tuple(r.get(k) for k in group_fields))), reverse=plan.descending)
    missing.sort(key=lambda r:str(tuple(r.get(k) for k in group_fields)), reverse=plan.descending)
    rows = present + missing
    return rows[:plan.limit] if plan.limit else rows
