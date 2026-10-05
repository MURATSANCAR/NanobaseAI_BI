"""Shared result-column meanings for standalone answers and report sections."""
from datetime import date, timedelta

from .contracts import METRICS


def public_definition(metric_id):
    from .presentation import public_definition as _public
    return _public(metric_id)


def _readable(identifier):
    words = str(identifier).replace("_", " ").strip()
    return words[:1].upper() + words[1:]

LABELS = {
    "passive_records": "Pasif kayıt sayısı",
    "book_code": "Stok kodu", "book_name": "Kitap adı", "customer_code": "Müşteri kodu",
    "customer_name": "Müşteri adı", "channel": "Satış kanalı", "author": "Yazar künyesi",
    "subbrand_id": "Alt marka kimliği", "subbrand": "Alt marka",
    "author_group_ids": "Ortak yazar kişi kimlikleri", "author_group_names": "Ortak yazar adları",
    "publisher": "Yayınevi", "day": "Gün", "month": "Ay", "year": "Yıl",
    "sale_type": "Satış türü", "e_document": "Belge türü", "einvoice_scenario": "e-Fatura senaryosu", "einvoice_type": "Fatura tipi", "einvoice_status": "e-Belge durumu",
    "vat_exemption": "KDV istisnası", "customer_einvoice_user": "e-Fatura mükellefi", "customer_legal_form": "Şahıs / şirket",
    "period_start": "Dönem başlangıcı", "period_end_exclusive": "Dönem sonu (hariç)",
    "base_period_start": "Baz dönem başlangıcı", "base_period_end_exclusive": "Baz dönem sonu (hariç)",
    "target_period_start": "Karşılaştırılan dönem başlangıcı", "target_period_end_exclusive": "Karşılaştırılan dönem sonu (hariç)",
    "section": "Bölüm", "status": "Durum", "row_count": "Satır sayısı", "row_kind": "Satır türü",
    "match_status": "Eşleşme durumu", "logo_codes": "Logo kodları", "logo_names": "Logo adları",
    "crm_book_ids": "CRM kitap kimlikleri", "crm_book_names": "CRM kitap adları",
    "crm_customer_ids": "CRM müşteri kimlikleri", "crm_customer_names": "CRM müşteri adları",
    "crm_address_regions": "CRM adres bölgesi", "crm_sales_territories": "CRM satış bölgesi",
    "crm_countries": "CRM ülkeleri", "tax_number": "Vergi numarası",
    "author_ids": "Yazar kişi kimlikleri", "author_names": "Yazar adları",
    "shared_authors": "Birden çok yazarlı", "missing_fields": "Eksik alanlar", "name_difference": "Ad farkı",
    "net_sales": "KDV hariç net satış", "return_amount": "KDV hariç iade tutarı", "sold_quantity": "Satılan miktar",
    "invoice_id": "Fatura kayıt kimliği", "invoice_number": "Fatura numarası", "invoice_date": "Fatura tarihi",
    "invoice_count": "Fatura sayısı", "return_invoice_count": "İade faturası sayısı",
    "invoice_count_with_returns": "Fatura sayısı (iadeler dahil)",
    "invoice_total": "Fatura genel toplamı", "invoice_mean": "Fatura ortalaması",
    "invoice_median": "Fatura medyanı", "invoice_vat": "Fatura KDV tutarı", "header_excluding_vat": "Başlık KDV hariç tutar",
    "material_line_net": "Malzeme satırları net tutarı", "material_lines": "Malzeme satırı sayısı",
    "other_lines": "Diğer satır sayısı", "other_line_net": "Diğer satırlar net tutarı",
    "difference_from_material_net": "Başlık ve malzeme toplamı farkı", "source_code": "Teknik kaynak kodu",
    "source_period": "Teknik kaynak dönemi", "finding": "İnceleme bulgusu", "line_id": "Hareket kimliği",
    "movement_date": "Hareket tarihi", "amount": "Tutar", "warehouse_no": "Depo numarası",
    "onhand": "Stok miktarı", "source_quantity": "Kaynak stok miktarı", "movement_quantity": "Hareketlerden stok",
    "reconciliation": "Uzlaştırma", "daily_change": "Günlük stok değişimi", "unit_ref": "Birim kimliği",
    "order_number": "Sipariş numarası", "order_date": "Sipariş tarihi", "ordered_quantity": "Sipariş miktarı",
    "shipped_quantity": "Sevk miktarı", "remaining_quantity": "Kalan miktar", "remaining_base_quantity": "Ana birimde kalan",
    "remaining_net_amount_proportional": "Oransal kalan net tutar", "due_date": "Vade tarihi", "overdue_days": "Gecikme günü",
    "opening_balance": "Dönem başı bakiyesi", "period_debits": "Dönem borç hareketleri", "period_credits": "Dönem alacak hareketleri",
    "closing_balance": "Dönem sonu bakiyesi", "payment_type": "Ödeme türü", "payment_amount": "Ödeme hareketi tutarı",
    "movement_count": "Hareket sayısı", "currency_code": "Para birimi", "local_invoice_net": "Yerel para net fatura toplamı",
    "original_invoice_net": "İşlem para biriminde net fatura toplamı", "purchase_quantity": "Alış miktarı",
    "purchase_net_amount": "Net alış tutarı", "weighted_unit_purchase_price": "Ağırlıklı birim alış fiyatı",
}


RETURNS_FOLLOWUP_HINT = "iadeleri de ekle"


def format_count(value):
    return f"{int(value):,}".replace(",", ".")


def return_invoice_note(counts, filtered=False):
    """User-facing note for every invoice-count answer: returns measured, not included.

    counts: [(start, end_exclusive, return_invoice_count)], one item per answered period.
    Business language only; the follow-up phrase is the one scope_extension() recognises.
    """
    scope =" seçilen koşullarla" if filtered else ""
    total = sum(int(n) for _, _, n in counts)
    if not total:
        where = "Bu dönemde" if len(counts) == 1 else "Seçilen dönemlerde"
        return f"{where}{scope} iade faturası yok; fatura sayısı yalnız satış faturalarıdır."
    hint = f" Eklemek için ‘{RETURNS_FOLLOWUP_HINT}’ yazabilirsiniz."
    if len(counts) == 1:
        return f"Bu dönemde{scope} {format_count(total)} iade faturası var; fatura sayısına dahil edilmedi." + hint
    days = "; ".join(f"{date.fromisoformat(a):%d.%m.%Y}–{date.fromisoformat(b) - timedelta(days=1):%d.%m.%Y}: {format_count(n)}"
                     for a, b, n in counts)
    return f"Seçilen dönemlerde{scope} iade faturası sayısı — {days}. Bunlar fatura sayısına dahil edilmedi." + hint


def _metadata(plan):
    labels = {name: {"label": label} for name,label in LABELS.items()}
    for key in plan.metrics:
        metric = METRICS[key]
        labels[key] = {"label": metric.label, "unit": metric.unit, "definition": public_definition(key)}
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
    if getattr(plan, "relational_query", None):
        for selected in plan.relational_query["select"]:
            key = selected["id"]
            if selected["op"] in {"count_records", "count_distinct"}:
                labels[key] = {"label": key, "unit": "adet", "definition": "Süzgeçlerden geçen tekil kayıt sayısı" if selected["op"] == "count_records" else "Seçilen alandaki boş olmayan farklı değerlerin sayısı"}
            elif selected["op"] == "missing_flag":
                labels[key] = {"label": key, "unit": "gösterge", "definition": "Eksikse 1, doluysa 0; metinde boş ve yalnız boşluk içeren değerler eksiktir"}
    return labels


def describe_columns(plan, fields, numeric):
    """Do not infer a report column's accounting unit merely from its numeric type."""
    labels = _metadata(plan)
    numeric = set(numeric)
    return [{"name": field, "type": "float" if field in numeric else "str", **labels.get(field, {})} for field in fields]


def calculation_definitions(plan):
    labels = _metadata(plan)
    definitions = [public_definition(m) for m in plan.metrics]
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
    if "author_group" in plan.dimensions:
        definitions.append("Yazar grubu aktif Yazar katılımındaki gerçek kişi kimlikleri kümesidir; satış her ortak gruba bir kez yazılır, kişi başına çoğaltılmaz. Güncel CRM ilişkisi kullanılır.")
    if "subbrand" in plan.dimensions:
        definitions.append("Alt marka, kitap kartındaki yayıncı bağlantısıyla bağlı aktif marka kaydıdır; alternatif alt marka alanıyla veya geçmiş dönem yayıncı kaydıyla karıştırılmaz.")
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
    if getattr(plan, "relational_query", None):
        definitions.append("CRM güncel aktif kaynaklarında sorudan oluşturulan alan, ilişki, filtre ve gruplama planı; geçmiş durum veya kimlik sınıflandırması anlamına gelmez.")
        for selected in plan.relational_query["select"]:
            if selected["op"] == "count_records":
                definitions.append(_readable(selected["id"]) + ": süzgeçlerden geçen tekil kayıt sayısı.")
            elif selected["op"] == "count_distinct":
                definitions.append(_readable(selected["id"]) + ": seçilen alandaki boş olmayan farklı değerlerin sayısı.")
    return list(dict.fromkeys(definitions))
