"""Shared result-column meanings for standalone answers and report sections."""
from .contracts import METRICS

LABELS = {
    "book_code": "Stok kodu", "book_name": "Kitap adı", "customer_code": "Müşteri kodu",
    "customer_name": "Müşteri adı", "channel": "Satış kanalı", "author": "Yazar künyesi",
    "publisher": "Yayınevi", "day": "Gün", "month": "Ay", "year": "Yıl",
    "period_start": "Dönem başlangıcı", "period_end_exclusive": "Dönem sonu (hariç)",
    "base_period_start": "Baz dönem başlangıcı", "base_period_end_exclusive": "Baz dönem sonu (hariç)",
    "target_period_start": "Karşılaştırılan dönem başlangıcı", "target_period_end_exclusive": "Karşılaştırılan dönem sonu (hariç)",
    "section": "Bölüm", "status": "Durum", "row_count": "Satır sayısı", "row_kind": "Satır türü",
}


def _metadata(plan):
    labels = {name: {"label": label} for name,label in LABELS.items()}
    for key in plan.metrics:
        metric = METRICS[key]
        labels[key] = {"label": metric.label, "unit": metric.unit, "definition": metric.definition}
    for spec in plan.derived:
        left, right = METRICS[spec.left], METRICS[spec.right]
        if spec.op == "difference":
            label, unit = f"{left.label} − {right.label}", left.unit
            formula = f"{spec.left}−{spec.right}"
        elif spec.op == "percent_change":
            label, unit = f"{left.label}, {right.label} bazına göre değişim", "%"
            formula = f"({spec.left}−{spec.right})/{spec.right}×100"
        else:
            label = f"{left.label} / {right.label}"
            unit = ("%" if spec.scale == 100 else "oran") if left.unit == right.unit else left.unit + "/" + right.unit
            formula = f"{spec.left}/{spec.right}×{spec.scale:g}"
        labels[spec.id] = {"label": label, "unit": unit, "formula": formula}
    if plan.comparison:
        spec = plan.comparison
        metric = METRICS[spec.metric]
        labels.update(base_value={"label": "Baz dönem " + metric.label, "unit": metric.unit},
                      target_value={"label": "Karşılaştırılan dönem " + metric.label, "unit": metric.unit})
        labels[spec.id] = {"label": "Dönem farkı" if spec.op == "difference" else "Dönem değişimi",
                          "unit": metric.unit if spec.op == "difference" else "%",
                          "formula": "target_value−base_value" if spec.op == "difference" else "(target_value−base_value)/base_value×100"}
    for spec in getattr(plan, "analytics", ()):
        if spec["op"] != "contribution": continue
        metric = METRICS[spec["metric"]]
        labels[spec["id"]+"_group_total"] = {"label": metric.label + " grup toplamı", "unit": metric.unit}
        labels[spec["id"]+"_share_pct"] = {"label": metric.label + " payı", "unit": "%", "formula": "satır ölçüsü / grup toplamı × 100"}
        labels[spec["id"]+"_cumulative_pct"] = {"label": metric.label + " kümülatif payı", "unit": "%", "formula": "azalan sıralı birikimli ölçü / grup toplamı × 100"}
    return labels


def describe_columns(plan, fields, numeric):
    """Do not infer a report column's accounting unit merely from its numeric type."""
    labels = _metadata(plan)
    numeric = set(numeric)
    return [{"name": field, "type": "float" if field in numeric else "str", **labels.get(field, {})} for field in fields]


def calculation_definitions(plan):
    labels = _metadata(plan)
    definitions = [METRICS[m].definition for m in plan.metrics]
    for spec in plan.derived:
        meta = labels[spec.id]
        definitions.append(f"{meta['label']}: {meta['formula']} ({meta['unit']}).")
    if plan.comparison:
        meta = labels[plan.comparison.id]
        definitions.append(f"{meta['label']}: {meta['formula']} ({meta['unit']}).")
    if plan.derived or plan.comparison:
        definitions.append("Sıfır/eksik payda veya eksik dönem değeri hesaplanmış sıfır değildir; sonuç boş gösterilir.")
    for spec in getattr(plan, "analytics", ()):
        if spec["op"] == "contribution":
            definitions.append(f"{METRICS[spec['metric']].label} payı: ölçü / aynı grubun tam toplamı × 100; kümülatif pay azalan ölçü sırasında hesaplanır. Negatif değerler korunur, sıfır toplamın oranı boştur.")
        else:
            definitions.append(f"Her grupta {METRICS[spec['metric']].label} sırasına göre ilk {spec['limit']} öğe ve kalanların işaretli toplamı; aynı öğe iki kez sayılmaz.")
    if "author" in plan.dimensions:
        definitions.append("Yazar kırılımı kitap künyesindeki metindir; kişi kimliği veya telif sahipliği değildir.")
    if getattr(plan, "logo_report", None):
        from .logo_reports import LOGO_REPORT_CAPABILITIES
        description = LOGO_REPORT_CAPABILITIES.get(plan.logo_report["mode"])
        if description: definitions.append(str(description))
    if getattr(plan, "crm_report", None):
        from .crm_reports import CRM_REPORT_CAPABILITIES
        description = CRM_REPORT_CAPABILITIES["reports"].get(plan.crm_report["report"])
        if description: definitions.append(str(description))
    return list(dict.fromkeys(definitions))
