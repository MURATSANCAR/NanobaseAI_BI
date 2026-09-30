"""Logo report capabilities with physical-schema checks and explicit evidence gaps.

The planner supplies only this closed specification, never SQL. Stock quantities
are reconciled to independent movement aggregates before being called on-hand.
Receivable ageing and profit are not inferred from unverified closure/cost fields.
"""
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo
from .contracts import ContractError
from .executor import literal
from .invoice_reports import INVOICE_REPORTS, execute as execute_invoice_report
from .cross_reports import CROSS_REPORTS, execute as execute_cross_report

MODES = ("stock", "stock_history", "open_orders", "customer_balances",
         "payment_movements", "currencies", "purchase_prices", "aging", "profit", *INVOICE_REPORTS, *CROSS_REPORTS)
PAYMENTS = {"cash": 1, "bank": 20, "cheque": 61, "promissory_note": 62, "card": 70}
DEFAULTS = dict(start=None, end=None, as_of=None, customer_code=None, book_code=None,
                warehouse_no=None, order_kind="sales", overdue_only=False, lookback_days=None,
                stock_filter="all", coverage_days=None, match_status="all", payment_types=[], limit=None, order_by=None, descending=True)
LOGO_REPORT_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "mode": {"type": "string", "enum": list(MODES)},
        **{k: {"type": ["string", "null"]} for k in ("start", "end", "as_of", "customer_code", "book_code", "order_by")},
        "warehouse_no": {"type": ["integer", "null"]},
        "order_kind": {"type": "string", "enum": ["sales", "purchase"]},
        "overdue_only": {"type": "boolean"}, "lookback_days": {"type": ["integer", "null"]},
        "coverage_days": {"type": ["integer", "null"]},
        "match_status": {"type": "string", "enum": ["all", "matched", "unmatched", "ambiguous", "missing_fields", "name_difference", "no_sales"]},
        "stock_filter": {"type": "string", "enum": ["all", "positive", "no_recent_sales", "shortage", "transfers"]},
        "payment_types": {"type": "array", "items": {"type": "string", "enum": list(PAYMENTS)}},
        "limit": {"type": ["integer", "null"]}, "descending": {"type": "boolean"},
    },
    "required": ["mode", *DEFAULTS],
}
LOGO_REPORT_CAPABILITIES = {
    **INVOICE_REPORTS,
    **CROSS_REPORTS,
    "stock": "Kitap+depo bazında tarih itibarıyla stok; günlük stok görünümü ile bağımsız yönlü hareket uzlaşması. Eşit olmayan/bilinmeyen birim dönüşümü veya uzlaşmayan kayıt için miktar NULL ve açık veri eksiği. lookback_days ile son dönemdeki satış, son satış tarihi ve basit stok gün kapsamı; sipariş mevcut stok değildir.",
    "stock_history": "Tek Logo kaynak döneminde kitap+depo+gün bazında uzlaştırılmış stok hareketi ve gün sonu stok. Farklı yıllık yedeklerin devir stoklarını toplayamaz.",
    "open_orders": "İptal edilmemiş, kapatılmamış satış/alış sipariş satırları; sipariş adedi, sevk edilen, kalan, vade/gecikme ve oransal kalan net tutar. Farklı birimler çevrilmez; ortak stok siparişlere mükerrer tahsis edilmez. Tarihler sipariş tarihi filtresidir, as_of gecikme tarihidir.",
    "customer_balances": "120 müşteri carilerinde kaynak dönemindeki borç/alacak hareketlerinden başlangıç ve bitiş bakiyesi; başlangıç öncesi tüm hareketler dahil. Bakiye fatura bazlı açık alacak veya yaşlandırma değildir. Yıllık devirlerin toplanması yasak.",
    "payment_movements": "Müşteri+ödeme türü bazında mevcut collections sözleşmesindeki nakit,banka,çek,senet,kart hareketlerini ayırır. Çek/senet teslimini gerçekleşmiş banka nakdi saymaz; banka mutabakatı veya fatura kapama sonucu değildir.",
    "currencies": "İptal olmayan satış ve iade faturalarının işlem para birimi kodu bazında yerel NETTOTAL ve işlem TRNET toplamı, fatura sayısı. Dövizler birbirine eklenmez; yeniden kur dönüşümü yapılmaz. Kaynak kod0 için işlem para birimi belirsizse orijinal tutar NULL kalır.",
    "purchase_prices": "Tedarikçi+malzeme+satır birimi+işlem para birimi+ay bazında gerçekleşmiş alış faturası satırları; net alış tutarı, miktar, ağırlıklı birim alış fiyatı. Bu alış fiyatı satılan mal maliyeti değildir; farklı birimler/para birimleri karıştırılmaz.",
    "aging": "PAYTRANS alanları fiziksel olarak mevcut olsa da gerçek kapama ilişkisi ve ödeme eşleşmesi kanıtlanmadan kesin yaşlandırma üretmez; typed gap döner. TOTAL-PAID veya FIFO otomatik varsayılmaz.",
    "profit": "Satılan mal maliyeti ve iade maliyeti semantiği doğrulanmadan kâr üretmez; typed gap döner. Son alış veya satış fiyatı maliyet yerine geçmez.",
}


def validate_logo_report(raw):
    if not isinstance(raw, dict) or set(raw) - {"mode", *DEFAULTS}:
        raise ContractError("Logo rapor planının alanları doğrulanamadı.")
    spec = {**DEFAULTS, **raw}
    if spec.get("mode") not in MODES:
        raise ContractError("Logo rapor türü doğrulanamadı.")
    for key in ("start", "end", "as_of"):
        value = spec[key]
        if value is not None:
            try:
                if not isinstance(value, str) or str(date.fromisoformat(value)) != value: raise ValueError()
            except (TypeError, ValueError): raise ContractError("Logo rapor tarihi ISO gün biçiminde olmalı.") from None
    if bool(spec["start"]) != bool(spec["end"]) or spec["start"] and spec["start"] >= spec["end"]:
        raise ContractError("Logo raporunun başlangıç/bitiş dönemi geçerli değil.")
    if spec["mode"] in ("stock", "stock_history", "open_orders", "aging") and not spec["as_of"]:
        raise ContractError("Bu rapor için stok/gecikme tarihi belirtilmeli.")
    if spec["mode"] in ("stock_history", "customer_balances", "payment_movements", "currencies", "purchase_prices", *INVOICE_REPORTS, *CROSS_REPORTS) and not spec["start"]:
        raise ContractError("Bu rapor için işlem dönemi belirtilmeli.")
    for key in ("customer_code", "book_code", "order_by"):
        if spec[key] is not None and (not isinstance(spec[key], str) or not 1 <= len(spec[key]) <= 120):
            raise ContractError("Logo raporunun kod/sıralama alanı geçerli değil.")
    for key, lo, hi in (("warehouse_no", 0, 32767), ("lookback_days", 1, 3660), ("coverage_days", 1, 3660), ("limit", 1, 5000)):
        if spec[key] is not None and (type(spec[key]) is not int or not lo <= spec[key] <= hi):
            raise ContractError("Logo raporunun sayısal sınırı geçerli değil.")
    if type(spec["overdue_only"]) is not bool or type(spec["descending"]) is not bool:
        raise ContractError("Logo raporunun koşulu geçerli değil.")
    if spec["order_kind"] not in ("sales", "purchase") or spec["stock_filter"] not in ("all", "positive", "no_recent_sales", "shortage", "transfers"):
        raise ContractError("Logo raporunun kapsamı geçerli değil.")
    if not isinstance(spec["payment_types"], list) or any(x not in PAYMENTS for x in spec["payment_types"]):
        raise ContractError("Ödeme türü doğrulanamadı.")
    if spec["stock_filter"] in ("no_recent_sales", "shortage") and not spec["lookback_days"]:
        raise ContractError("Satışsızlık/stok kapsamı hesabının bakılacak gün sayısı belirtilmeli.")
    if spec["stock_filter"] == "shortage" and not spec["coverage_days"]:
        raise ContractError("Stok kaç günün altına düştüğünde yetersiz sayılmalı?")
    if spec["coverage_days"] is not None and spec["stock_filter"] != "shortage":
        raise ContractError("Stok gün eşiği yalnız stok yetersizlik filtresinde kullanılabilir.")
    if spec["stock_filter"] == "transfers" and spec["warehouse_no"] is not None:
        raise ContractError("Depolar arası transfer adayı için tek depo kapsamı yeterli değil.")
    if spec["match_status"] not in ("all", "matched", "unmatched", "ambiguous", "missing_fields", "name_difference", "no_sales"):
        raise ContractError("Kaynak eşleşme durumu tanımlı değil.")
    if spec["match_status"] != "all" and spec["mode"] not in CROSS_REPORTS:
        raise ContractError("Kaynak eşleşme filtresi yalnız birleşik kaynak raporunda kullanılabilir.")
    if spec["stock_filter"] != "all" and spec["mode"] != "stock":
        raise ContractError("Stok filtresi yalnız anlık stok raporunda kullanılabilir.")
    if spec["lookback_days"] and spec["mode"] != "stock":
        raise ContractError("Satış hızı penceresi yalnız stok raporunda kullanılabilir.")
    if spec["payment_types"] and spec["mode"] != "payment_movements":
        raise ContractError("Ödeme türü filtresi bu rapora uygulanamaz.")
    if spec["overdue_only"] and spec["mode"] != "open_orders":
        raise ContractError("Gecikmiş sipariş filtresi bu rapora uygulanamaz.")
    if spec["order_kind"] != "sales" and spec["mode"] != "open_orders":
        raise ContractError("Alış siparişi kapsamı yalnız sipariş raporuna uygulanabilir.")
    if spec["mode"] == "stock" and spec["start"]:
        expected_end = date.fromisoformat(spec["as_of"]) + timedelta(days=1)
        if not spec["lookback_days"] or spec["end"] != str(expected_end) or spec["start"] != str(expected_end - timedelta(days=spec["lookback_days"])):
            raise ContractError("Stok tarihinden önceki satış penceresi başlangıç/bitiş tarihleriyle uyuşmuyor.")
    if spec["as_of"] and spec["mode"] not in ("stock", "stock_history", "open_orders", "aging", "profit"):
        if not spec["end"] or spec["as_of"] != str(date.fromisoformat(spec["end"]) - timedelta(days=1)):
            raise ContractError("Raporun itibarıyla tarihi işlem dönemi bitişiyle uyuşmuyor.")
    if spec["mode"] in INVOICE_REPORTS and any(spec[key] is not None for key in ("book_code", "customer_code", "warehouse_no", "order_by")):
        raise ContractError("Bu fatura raporunda kod/depo filtresi veya özel sıralama henüz doğrulanmadı; koşul sessizce atlanmadı.")
    if spec["book_code"] and spec["mode"] not in ("stock", "stock_history", "open_orders", "purchase_prices", "profit", "cross_book_sales_quality"):
        raise ContractError("Bu rapor kitap düzeyinde değildir.")
    if spec["customer_code"] and spec["mode"] in ("stock", "stock_history", "cross_book_sales_quality"):
        raise ContractError("Stok toplamı müşteriye dağıtılamaz.")
    if spec["warehouse_no"] is not None and spec["mode"] not in ("stock", "stock_history", "open_orders", "purchase_prices"):
        raise ContractError("Bu raporda depo kapsamı bulunmuyor.")
    return spec


def _d(value):
    return Decimal(str(value or 0))


def _gap(code, reason):
    return {"status": "UNVERIFIED", "code": code, "reason": reason}


def _result(records, fields, numeric=(), notes=(), gaps=()):
    clean = []
    for row in records:
        clean.append({field: (float(row.get(field)) if isinstance(row.get(field), Decimal)
                              else str(row.get(field)) if isinstance(row.get(field), date)
                              else row.get(field)) for field in fields})
    return dict(records=clean, output_fields=list(fields), numeric_fields=list(numeric), notes=list(notes), gaps=list(gaps))


def _partitions(executor, start, end):
    return executor.partitions(date.fromisoformat(start), date.fromisoformat(end))


def _point(executor, as_of):
    at = date.fromisoformat(as_of)
    parts = executor.partitions(at, at + timedelta(days=1))
    if len(parts) != 1: raise ContractError("Tek tarih için birden fazla Logo kaynağı seçilemez.")
    return parts[0][2:]


def _table(firm, period, suffix):
    return f"LG_{firm}_{period}_{suffix}"


def _check(executor, tables, numeric=()):
    types = executor.verify_schema(tables, "logo")
    for table, column in numeric:
        if types[(table.lower(), column.lower())] not in {"float", "real", "decimal", "numeric", "money", "smallmoney", "int", "smallint", "bigint", "tinyint"}:
            raise ContractError("Logo sayısal alanının fiziksel türü uygun değil.")


def _code_filter(spec, alias="I"):
    return f" AND LTRIM(RTRIM({alias}.CODE))={literal(spec['book_code'])}" if spec["book_code"] else ""


def _customer_filter(spec, alias="C"):
    return f" AND {alias}.CODE={literal(spec['customer_code'])}" if spec["customer_code"] else ""


def _stock(executor, spec):
    firm, period = _point(executor, spec["as_of"])
    view = f"LV_{firm}_{period}_STINVTOT"
    lines, items = _table(firm, period, "STLINE"), f"LG_{firm}_ITEMS"
    history = spec["mode"] == "stock_history"
    if history:
        parts = _partitions(executor, spec["start"], spec["end"])
        if len(parts) != 1 or parts[0][2:] != (firm, period):
            return _result([], [], gaps=[_gap("STOCK_PERIOD_BRIDGE", "Stok geçmişi birden fazla yıllık yedekte; devir miktarlarının dönemler arasında uzlaşması doğrulanmadan toplanmadı.")])
    end = spec["end"] if history else str(date.fromisoformat(spec["as_of"]) + timedelta(days=1))
    _check(executor, {view: ["STOCKREF", "INVENNO", "DATE_", "ONHAND"],
                     lines: ["STOCKREF", "SOURCEINDEX", "DATE_", "CANCELLED", "LINETYPE", "IOCODE", "AMOUNT", "UINFO1", "UINFO2"],
                     items: ["LOGICALREF", "CODE", "NAME"]}, [(view, "ONHAND"), (lines, "AMOUNT")])
    book = _code_filter(spec)
    depot_v = f" AND V.INVENNO={spec['warehouse_no']}" if spec["warehouse_no"] is not None else ""
    depot_s = f" AND S.SOURCEINDEX={spec['warehouse_no']}" if spec["warehouse_no"] is not None else ""
    day_v = ",CONVERT(varchar(10),V.DATE_,23) day" if history else ""
    day_s = ",CONVERT(varchar(10),S.DATE_,23) day" if history else ""
    group_v = ",CONVERT(varchar(10),V.DATE_,23)" if history else ""
    group_s = ",CONVERT(varchar(10),S.DATE_,23)" if history else ""
    rows = executor.read(f"SELECT V.STOCKREF stock_ref,LTRIM(RTRIM(I.CODE)) book_code,I.NAME book_name,V.INVENNO warehouse_no{day_v},SUM(V.ONHAND) quantity FROM dbo.[{view}] V LEFT JOIN dbo.[{items}] I ON I.LOGICALREF=V.STOCKREF WHERE V.INVENNO>=0 AND V.DATE_<{literal(end)}{depot_v}{book} GROUP BY V.STOCKREF,I.CODE,I.NAME,V.INVENNO{group_v}")
    raw = executor.read(f"SELECT S.STOCKREF stock_ref,LTRIM(RTRIM(I.CODE)) book_code,I.NAME book_name,S.SOURCEINDEX warehouse_no{day_s},SUM(CASE WHEN S.IOCODE IN (1,2) THEN S.AMOUNT WHEN S.IOCODE IN (3,4) THEN -S.AMOUNT ELSE 0 END) quantity,SUM(CASE WHEN S.IOCODE NOT IN (1,2,3,4) OR S.IOCODE IS NULL OR S.UINFO1 IS NULL OR S.UINFO2 IS NULL OR S.UINFO1<=0 OR S.UINFO1<>S.UINFO2 THEN 1 ELSE 0 END) unverified_units FROM dbo.[{lines}] S LEFT JOIN dbo.[{items}] I ON I.LOGICALREF=S.STOCKREF WHERE S.CANCELLED=0 AND S.LINETYPE=0 AND S.SOURCEINDEX>=0 AND S.DATE_<{literal(end)}{depot_s}{book} GROUP BY S.STOCKREF,I.CODE,I.NAME,S.SOURCEINDEX{group_s}")
    keys = ["stock_ref", "warehouse_no"] + (["day"] if history else [])
    index = {tuple(r[k] for k in keys): r for r in raw}
    if len(index) != len(raw): raise ContractError("Bağımsız stok hareketi anahtarı tekil değil.")
    observed = {tuple(r[k] for k in keys): r for r in rows}
    if len(observed) != len(rows): raise ContractError("Stok görünümünün anahtarı tekil değil.")
    answer = []; invalid = 0
    for key in set(index) | set(observed):
        vendor, movement = observed.get(key), index.get(key)
        base = dict(vendor or movement)
        vq, mq = _d(vendor.get("quantity")) if vendor else Decimal(0), _d(movement.get("quantity")) if movement else Decimal(0)
        good = not (movement or {}).get("unverified_units") and abs(vq - mq) <= Decimal("0.000001")
        if not good: invalid += 1
        base.update(onhand=vq if good else None, source_quantity=vq, movement_quantity=mq,
                    reconciliation="MATCHED" if good else "UNVERIFIED")
        answer.append(base)
    gaps = [_gap("STOCK_RECONCILIATION", f"{invalid} stok/depo/gün kaydı hareket veya birim uzlaşmasını sağlamadı; doğrulanmış stok miktarı olarak sunulmadı.")] if invalid else []
    notes = ["Stok, seçilen tek dönem kaynağındaki günlük görünüm ile bağımsız giriş/çıkış hareketi uzlaştırılarak hesaplandı; kaynak dönemin devir kaydı dahildir. Fiziksel sayım doğrulaması değildir."]
    fields = ["stock_ref", "book_code", "book_name", "warehouse_no"]
    if history:
        running = defaultdict(Decimal); poisoned = set(); history_rows = []
        for row in sorted(answer, key=lambda x: (x["stock_ref"], x["warehouse_no"], str(x.get("day") or ""))):
            key = (row["stock_ref"], row["warehouse_no"])
            if row["onhand"] is None: poisoned.add(key)
            else: running[key] += row["onhand"]
            row["daily_change"] = row["onhand"]
            row["onhand"] = None if key in poisoned else running[key]
            if row.get("day") is not None and spec["start"] <= row["day"] < spec["end"]: history_rows.append(row)
        answer = history_rows
        fields += ["day", "daily_change"]
        notes.append("Yalnız hareket olan günler listelenir; hareket olmayan günün son miktarı bir önceki hareket gününden devam eder.")
    elif spec["lookback_days"]:
        _stock_sales(executor, spec, answer, notes, gaps)
        fields += ["lookback_days", "recent_net_quantity", "last_sale_date", "estimated_days_cover"]
    if spec["stock_filter"] == "positive": answer = [r for r in answer if r["onhand"] is not None and r["onhand"] > 0]
    elif spec["stock_filter"] == "no_recent_sales": answer = [r for r in answer if r["onhand"] is not None and r["onhand"] > 0 and r.get("last_sale_date") is None]
    elif spec["stock_filter"] == "shortage": answer = [r for r in answer if r.get("estimated_days_cover") is not None and r["estimated_days_cover"] < spec["coverage_days"]]
    elif spec["stock_filter"] == "transfers":
        grouped = defaultdict(list)
        for row in answer: grouped[row["stock_ref"]].append(row)
        candidates = {key for key, group in grouped.items() if any(r["onhand"] is not None and r["onhand"] > 0 for r in group) and any(r["onhand"] is not None and r["onhand"] <= 0 for r in group)}
        answer = [r for r in answer if r["stock_ref"] in candidates]
        notes.append("Depolar arası miktar farkı transfer adayıdır; sevk uygunluğu veya stok rezervasyonu kararı verilmedi. Hiç hareketi olmayan depo otomatik sıfır stok sayılmadı.")
    fields += ["onhand", "source_quantity", "movement_quantity", "reconciliation"]
    return _result(answer, fields, [x for x in fields if x in {"daily_change", "lookback_days", "recent_net_quantity", "estimated_days_cover", "onhand", "source_quantity", "movement_quantity"}], notes, gaps)


def _stock_sales(executor, spec, stocks, notes, gaps):
    end = date.fromisoformat(spec["as_of"]) + timedelta(days=1)
    start = end - timedelta(days=spec["lookback_days"])
    by_key = {}; bad = set()
    for a, b, firm, period in executor.partitions(start, end):
        table, items = _table(firm, period, "STLINE"), f"LG_{firm}_ITEMS"
        _check(executor, {table: ["STOCKREF", "SOURCEINDEX", "TRCODE", "INVOICEREF", "CANCELLED", "LINETYPE", "DATE_", "AMOUNT", "UINFO1", "UINFO2"], items: ["LOGICALREF", "CODE"]})
        rows = executor.read(f"SELECT LTRIM(RTRIM(I.CODE)) book_code,S.SOURCEINDEX warehouse_no,SUM(CASE WHEN S.TRCODE IN (2,3) THEN -S.AMOUNT ELSE S.AMOUNT END) net_quantity,MAX(CASE WHEN S.TRCODE IN (7,8) THEN CONVERT(varchar(10),S.DATE_,23) END) last_sale_date,SUM(CASE WHEN S.UINFO1 IS NULL OR S.UINFO2 IS NULL OR S.UINFO1<=0 OR S.UINFO1<>S.UINFO2 THEN 1 ELSE 0 END) bad_units FROM dbo.[{table}] S LEFT JOIN dbo.[{items}] I ON I.LOGICALREF=S.STOCKREF WHERE S.CANCELLED=0 AND S.LINETYPE=0 AND S.INVOICEREF<>0 AND S.TRCODE IN (2,3,7,8) AND S.DATE_>={literal(a)} AND S.DATE_<{literal(b)}{_code_filter(spec)} GROUP BY I.CODE,S.SOURCEINDEX")
        for row in rows:
            key = (row["book_code"], row["warehouse_no"])
            previous = by_key.setdefault(key, dict(quantity=Decimal(0), last=None))
            previous["quantity"] += _d(row["net_quantity"])
            previous["last"] = max(filter(None, (previous["last"], row["last_sale_date"])), default=None)
            if row["bad_units"]: bad.add(key)
    for row in stocks:
        key = (row["book_code"], row["warehouse_no"]); found = by_key.get(key, {})
        qty = None if key in bad else found.get("quantity", Decimal(0))
        row.update(lookback_days=spec["lookback_days"], recent_net_quantity=qty, last_sale_date=found.get("last"), estimated_days_cover=None)
        if row["onhand"] is not None and qty is not None and qty > 0:
            row["estimated_days_cover"] = max(row["onhand"], Decimal(0)) * spec["lookback_days"] / qty
    if bad: gaps.append(_gap("SALES_UNIT_CONVERSION", "Bazı satış satırlarında ortak ana birim dönüşümü doğrulanamadı; satış hızı hesaplanmadı."))
    notes.append("Satış hızı iade sonrası net adedin seçilen tüm takvim günlerine bölünmesidir; satış olmayan günler paydada kalır. Son satış tarihi yalnız bakılan pencere içindedir. Stok gün kapsamı basit hız tahminidir.")


def _orders(executor, spec):
    as_of = date.fromisoformat(spec["as_of"])
    if as_of != datetime.now(ZoneInfo("Europe/Istanbul")).date():
        return _result([], [], gaps=[_gap("ORDER_STATE_HISTORY", "Siparişin CLOSED/SHIPPEDAMOUNT alanları güncel durumu gösterir; geçmiş veya gelecek tarihli açık sipariş durumu bu alanlardan çıkarılamaz.")])
    if spec["start"]: parts = _partitions(executor, spec["start"], spec["end"])
    else:
        firm, period = _point(executor, spec["as_of"])
        parts = [(None, as_of + timedelta(days=1), firm, period)]
    out=[]; bad=0
    for start, end, firm, period in parts:
        line, header, items, clients = _table(firm,period,"ORFLINE"), _table(firm,period,"ORFICHE"), f"LG_{firm}_ITEMS", f"LG_{firm}_CLCARD"
        _check(executor, {line: ["LOGICALREF","ORDFICHEREF","STOCKREF","CLIENTREF","TRCODE","LINETYPE","CANCELLED","CLOSED","AMOUNT","SHIPPEDAMOUNT","LINENET","UOMREF","UINFO1","UINFO2","SOURCEINDEX","DUEDATE","DATE_"],header:["LOGICALREF","FICHENO","CANCELLED"],items:["LOGICALREF","CODE","NAME"],clients:["LOGICALREF","CODE","DEFINITION_"]}, [(line,c) for c in ("AMOUNT","SHIPPEDAMOUNT","LINENET")])
        scope=f" AND O.DATE_>={literal(start)}" if start else ""
        if spec["warehouse_no"] is not None:scope+=f" AND O.SOURCEINDEX={spec['warehouse_no']}"
        if spec["overdue_only"]:scope+=f" AND O.DUEDATE<{literal(as_of)} AND O.DUEDATE>='19000101'"
        rows=executor.read(f"SELECT O.LOGICALREF order_line_ref,H.FICHENO order_number,CONVERT(varchar(10),O.DATE_,23) order_date,LTRIM(RTRIM(I.CODE)) book_code,I.NAME book_name,C.CODE customer_code,C.DEFINITION_ customer_name,O.SOURCEINDEX warehouse_no,O.UOMREF unit_ref,O.UINFO1 unit_factor_1,O.UINFO2 unit_factor_2,O.AMOUNT ordered_quantity,O.SHIPPEDAMOUNT shipped_quantity,O.AMOUNT-O.SHIPPEDAMOUNT remaining_quantity,O.LINENET line_net_amount,CASE WHEN O.DUEDATE>='19000101' THEN CONVERT(varchar(10),O.DUEDATE,23) END due_date FROM dbo.[{line}] O JOIN dbo.[{header}] H ON H.LOGICALREF=O.ORDFICHEREF LEFT JOIN dbo.[{items}] I ON I.LOGICALREF=O.STOCKREF LEFT JOIN dbo.[{clients}] C ON C.LOGICALREF=O.CLIENTREF WHERE O.CANCELLED=0 AND H.CANCELLED=0 AND O.CLOSED=0 AND O.LINETYPE=0 AND O.TRCODE={1 if spec['order_kind']=='sales' else 2} AND O.AMOUNT>O.SHIPPEDAMOUNT AND O.DATE_<{literal(end)}{scope}{_code_filter(spec)}{_customer_filter(spec)}")
        for row in rows:
            row["source_period"]=f"{firm}/{period}"
            row["remaining_net_amount_proportional"]=_d(row["line_net_amount"])*_d(row["remaining_quantity"])/_d(row["ordered_quantity"]) if _d(row["ordered_quantity"])>0 else None
            row["overdue_days"]=max(0,(as_of-date.fromisoformat(row["due_date"])).days) if row["due_date"] else None
            row["remaining_base_quantity"]=_d(row["remaining_quantity"]) if row["unit_factor_1"] and row["unit_factor_1"]==row["unit_factor_2"] else None
            if row["remaining_base_quantity"] is None:bad+=1
            out.append(row)
    fields=["source_period","order_line_ref","order_number","order_date","book_code","book_name","customer_code","customer_name","warehouse_no","unit_ref","ordered_quantity","shipped_quantity","remaining_quantity","remaining_base_quantity","remaining_net_amount_proportional","due_date","overdue_days"]
    gaps=[_gap("ORDER_UNITS",f"{bad} sipariş satırının ana birim dönüşümü doğrulanamadı; satır birimi miktarı korundu.")] if bad else []
    return _result(out,fields,["ordered_quantity","shipped_quantity","remaining_quantity","remaining_base_quantity","remaining_net_amount_proportional","overdue_days"], ["Kalan tutar satır net tutarının kalan miktar oranıdır; yeni fatura veya tahsilat değildir. Stok siparişlere tahsis edilmedi.","Tarihsiz açık sipariş listesi seçilen kaynak döneminin açık satırlarını kapsar; önceki yedekte kalmış devredilmemiş siparişler ayrıca doğrulanmalıdır."],gaps)


def _balances(executor,spec):
    parts=_partitions(executor,spec["start"],spec["end"])
    if len(parts)!=1:return _result([],[],gaps=[_gap("BALANCE_CARRY_FORWARD","Bakiye dönemi birden fazla yedeğe yayılıyor; devir eşlemesi olmadan aynı borç iki kez toplanamaz.")])
    _,_,firm,period=parts[0];line,clients=_table(firm,period,"CLFLINE"),f"LG_{firm}_CLCARD"
    _check(executor,{line:["CLIENTREF","DATE_","SIGN","AMOUNT","CANCELLED"],clients:["LOGICALREF","CODE","DEFINITION_","TAXNR"]},[(line,"AMOUNT")])
    start,end=literal(spec["start"]),literal(spec["end"])
    rows=executor.read(f"SELECT C.CODE customer_code,C.DEFINITION_ customer_name,NULLIF(LTRIM(RTRIM(C.TAXNR)),'') tax_number,SUM(CASE WHEN L.DATE_<{start} THEN CASE WHEN L.SIGN=0 THEN L.AMOUNT WHEN L.SIGN=1 THEN -L.AMOUNT ELSE 0 END ELSE 0 END) opening_balance,SUM(CASE WHEN L.DATE_>={start} AND L.SIGN=0 THEN L.AMOUNT ELSE 0 END) period_debits,SUM(CASE WHEN L.DATE_>={start} AND L.SIGN=1 THEN L.AMOUNT ELSE 0 END) period_credits,SUM(CASE WHEN L.SIGN=0 THEN L.AMOUNT WHEN L.SIGN=1 THEN -L.AMOUNT ELSE 0 END) closing_balance,SUM(CASE WHEN L.SIGN IS NULL OR L.SIGN NOT IN (0,1) THEN 1 ELSE 0 END) unverified_sign_rows FROM dbo.[{line}] L JOIN dbo.[{clients}] C ON C.LOGICALREF=L.CLIENTREF WHERE L.CANCELLED=0 AND C.CODE LIKE '120%' AND L.DATE_<{end}{_customer_filter(spec)} GROUP BY C.CODE,C.DEFINITION_,C.TAXNR")
    bad=sum(row["unverified_sign_rows"] for row in rows)
    for row in rows:
        if row["unverified_sign_rows"]:
            for field in ("opening_balance","period_debits","period_credits","closing_balance"):row[field]=None
    gaps=[_gap("BALANCE_SIGN",f"{bad} cari harekette borç/alacak yönü doğrulanamadı; ilgili müşterinin bakiyesi tahmin edilmedi.")] if bad else []
    return _result(rows,["customer_code","customer_name","tax_number","opening_balance","period_debits","period_credits","closing_balance","unverified_sign_rows"],["opening_balance","period_debits","period_credits","closing_balance","unverified_sign_rows"],["Kaynak dönemi içindeki tüm önceki hareketler başlangıç bakiyesine dahil edildi. Dönem alacak hareketi yalnız nakit tahsilat değildir; bakiye kapatılmamış fatura veya vadesi geçmiş alacak demek değildir."],gaps)


def _payments(executor,spec):
    groups={};codes=[PAYMENTS[x] for x in spec["payment_types"]] or list(PAYMENTS.values());reverse={v:k for k,v in PAYMENTS.items()}
    for start,end,firm,period in _partitions(executor,spec["start"],spec["end"]):
        line,clients=_table(firm,period,"CLFLINE"),f"LG_{firm}_CLCARD"
        _check(executor,{line:["CLIENTREF","DATE_","SIGN","AMOUNT","TRCODE","CANCELLED"],clients:["LOGICALREF","CODE","DEFINITION_"]},[(line,"AMOUNT")])
        rows=executor.read(f"SELECT C.CODE customer_code,C.DEFINITION_ customer_name,L.TRCODE payment_code,COUNT_BIG(*) movement_count,SUM(L.AMOUNT) payment_amount FROM dbo.[{line}] L JOIN dbo.[{clients}] C ON C.LOGICALREF=L.CLIENTREF WHERE L.CANCELLED=0 AND L.SIGN=1 AND C.CODE LIKE '120%' AND L.TRCODE IN ({','.join(map(str,codes))}) AND L.DATE_>={literal(start)} AND L.DATE_<{literal(end)}{_customer_filter(spec)} GROUP BY C.CODE,C.DEFINITION_,L.TRCODE")
        for row in rows:
            key=(row["customer_code"],row["customer_name"],row["payment_code"])
            item=groups.setdefault(key,{**row,"movement_count":0,"payment_amount":Decimal(0),"payment_type":reverse[row["payment_code"]]})
            item["movement_count"]+=row["movement_count"];item["payment_amount"]+=_d(row["payment_amount"])
    return _result(groups.values(),["customer_code","customer_name","payment_code","payment_type","movement_count","payment_amount"],["movement_count","payment_amount"],["Çek/senet tutarı teslim hareketidir, banka veya kasaya geçmiş nakit sayılmaz. Bu rapor ödeme hareketlerini ayırır; banka mutabakatını veya hangi faturanın kapandığını kanıtlamaz."])


def _currencies(executor,spec):
    groups={};unknown=0;missing_amount=0
    for start,end,firm,period in _partitions(executor,spec["start"],spec["end"]):
        table,clients=_table(firm,period,"INVOICE"),f"LG_{firm}_CLCARD"
        _check(executor,{table:["CLIENTREF","DATE_","TRCODE","CANCELLED","TRCURR","TRNET","NETTOTAL"],clients:["LOGICALREF","CODE"],"L_CURRENCYLIST":["FIRMNR","CURTYPE","CURCODE"]},[(table,"TRNET"),(table,"NETTOTAL")])
        labels=executor.read(f"SELECT CURTYPE currency_id,CURCODE currency_code FROM L_CURRENCYLIST WHERE FIRMNR={int(firm)}",metadata=True)
        mapping={}
        for label in labels:
            if label["currency_id"] in mapping and mapping[label["currency_id"]]!=label["currency_code"]:raise ContractError("Para birimi kodunun açıklaması tekil değil.")
            mapping[label["currency_id"]]=label["currency_code"]
        rows=executor.read(f"SELECT I.TRCURR currency_id,COUNT_BIG(*) invoice_count,SUM(CASE WHEN I.TRCODE IN (2,3) THEN -I.NETTOTAL ELSE I.NETTOTAL END) local_invoice_net,SUM(CASE WHEN I.TRCODE IN (2,3) THEN -I.TRNET ELSE I.TRNET END) original_invoice_net,SUM(CASE WHEN I.TRNET IS NULL OR (ABS(I.NETTOTAL)>0.000001 AND ABS(I.TRNET)<0.000001) THEN 1 ELSE 0 END) unverified_original_amounts FROM dbo.[{table}] I LEFT JOIN dbo.[{clients}] C ON C.LOGICALREF=I.CLIENTREF WHERE I.CANCELLED=0 AND I.TRCODE IN (2,3,7,8,9) AND I.DATE_>={literal(start)} AND I.DATE_<{literal(end)}{_customer_filter(spec)} GROUP BY I.TRCURR")
        for row in rows:
            currency=mapping.get(row["currency_id"])
            key=(row["currency_id"],currency)
            item=groups.setdefault(key,dict(currency_id=key[0],currency_code=key[1],invoice_count=0,local_invoice_net=Decimal(0),original_invoice_net=Decimal(0) if currency else None))
            item["invoice_count"]+=row["invoice_count"];item["local_invoice_net"]+=_d(row["local_invoice_net"])
            if currency and not row["unverified_original_amounts"] and item["original_invoice_net"] is not None:
                item["original_invoice_net"]+=_d(row["original_invoice_net"])
            else:
                item["original_invoice_net"]=None
                if not currency:unknown+=row["invoice_count"]
            missing_amount+=row["unverified_original_amounts"]
    gaps=[_gap("CURRENCY_IDENTITY",f"{unknown} faturada işlem para birimi üretici kod listesiyle eşleşmedi; özgün para birimi tutarı tahmin edilmedi.")] if unknown else []
    if missing_amount:gaps.append(_gap("CURRENCY_ORIGINAL_AMOUNT",f"{missing_amount} faturanın işlem para birimi tutarı boş veya yerel tutara karşılık sıfır; grup toplamı eksik özgün tutarla hesaplanmadı."))
    return _result(groups.values(),["currency_id","currency_code","invoice_count","local_invoice_net","original_invoice_net"],["invoice_count","local_invoice_net","original_invoice_net"],["Tutarlar fatura genel toplamıdır; KDV hariç satış satırı cirosu değildir. NETTOTAL yerel, TRNET işlem para birimi alanından okunur; para birimleri arasında toplam/yeniden kur dönüşümü yapılmaz."],gaps)


def _purchases(executor,spec):
    groups={}
    for start,end,firm,period in _partitions(executor,spec["start"],spec["end"]):
        line,items,clients=_table(firm,period,"STLINE"),f"LG_{firm}_ITEMS",f"LG_{firm}_CLCARD"
        _check(executor,{line:["STOCKREF","CLIENTREF","DATE_","TRCODE","LINETYPE","CANCELLED","INVOICEREF","AMOUNT","LINENET","UOMREF","UINFO1","UINFO2","TRCURR","SOURCEINDEX"],items:["LOGICALREF","CODE","NAME"],clients:["LOGICALREF","CODE","DEFINITION_"]},[(line,"AMOUNT"),(line,"LINENET")])
        depot=f" AND S.SOURCEINDEX={spec['warehouse_no']}" if spec["warehouse_no"] is not None else ""
        rows=executor.read(f"SELECT LTRIM(RTRIM(I.CODE)) book_code,I.NAME book_name,C.CODE supplier_code,C.DEFINITION_ supplier_name,CONVERT(varchar(7),S.DATE_,23) month,S.UOMREF unit_ref,S.UINFO1 unit_factor_1,S.UINFO2 unit_factor_2,S.TRCURR transaction_currency_id,SUM(S.AMOUNT) purchase_quantity,SUM(S.LINENET) purchase_net_amount FROM dbo.[{line}] S LEFT JOIN dbo.[{items}] I ON I.LOGICALREF=S.STOCKREF LEFT JOIN dbo.[{clients}] C ON C.LOGICALREF=S.CLIENTREF WHERE S.CANCELLED=0 AND S.LINETYPE=0 AND S.INVOICEREF<>0 AND S.TRCODE=1 AND S.DATE_>={literal(start)} AND S.DATE_<{literal(end)}{depot}{_code_filter(spec)}{_customer_filter(spec)} GROUP BY I.CODE,I.NAME,C.CODE,C.DEFINITION_,CONVERT(varchar(7),S.DATE_,23),S.UOMREF,S.UINFO1,S.UINFO2,S.TRCURR")
        for row in rows:
            # Unit refs are local physical identities, retain the source with them.
            row["unit_source"]=firm
            keys=["book_code","book_name","supplier_code","supplier_name","month","unit_source","unit_ref","unit_factor_1","unit_factor_2","transaction_currency_id"]
            key=tuple(row[k] for k in keys);item=groups.setdefault(key,{**row,"purchase_quantity":Decimal(0),"purchase_net_amount":Decimal(0)})
            item["purchase_quantity"]+=_d(row["purchase_quantity"]);item["purchase_net_amount"]+=_d(row["purchase_net_amount"])
    for row in groups.values():row["weighted_unit_purchase_price"]=row["purchase_net_amount"]/row["purchase_quantity"] if row["purchase_quantity"] else None
    fields=["book_code","book_name","supplier_code","supplier_name","month","unit_source","unit_ref","unit_factor_1","unit_factor_2","transaction_currency_id","purchase_quantity","purchase_net_amount","weighted_unit_purchase_price"]
    return _result(groups.values(),fields,["purchase_quantity","purchase_net_amount","weighted_unit_purchase_price"],["Alış fiyatı faturalı malzeme alımının iskonto sonrası KDV hariç satır net tutarı/miktarıdır. Satılan mal maliyeti veya kâr değildir. Birim kimliği/değerleri ve işlem para birimi ayrı gruplardır; döviz kuru etkisi ayrıca ayrıştırılmadı."])


def execute_logo_report(executor, raw):
    spec=validate_logo_report(raw)
    if spec["mode"] in INVOICE_REPORTS:
        result=execute_invoice_report(executor,spec)
        return result
    if spec["mode"] in CROSS_REPORTS:
        result=execute_cross_report(executor,spec)
        return result
    if spec["mode"]=="aging":
        return _result([],[],gaps=[_gap("PAYMENT_CLOSURE_UNVERIFIED","PAYTRANS kapama alanları mevcut, fakat gerçek ödeme-fatura kapama ilişkisinin anlamı ve kapsamı doğrulanmadı. TOTAL-PAID veya FIFO ile kesin açık alacak/yaşlandırma üretilmedi.")])
    if spec["mode"]=="profit":
        return _result([],[],gaps=[_gap("ACTUAL_COST_UNVERIFIED","Satılan mal ve iade maliyetlerinin kayıt kapsamı/hesap yöntemi doğrulanmadı. OUTCOST alanının bulunması gerçek maliyetin doğrulandığı anlamına gelmez; alış/satış fiyatından kâr üretilmedi.")])
    function={"stock":_stock,"stock_history":_stock,"open_orders":_orders,"customer_balances":_balances,"payment_movements":_payments,"currencies":_currencies,"purchase_prices":_purchases}[spec["mode"]]
    result=function(executor,spec)
    if spec["order_by"]:
        field=spec["order_by"]
        if field not in result["output_fields"]:raise ContractError("Rapor sıralama alanı çıktı sözleşmesinde yok.")
        present=[r for r in result["records"] if r.get(field) is not None]
        missing=[r for r in result["records"] if r.get(field) is None]
        result["records"]=sorted(present,key=lambda r:r[field],reverse=spec["descending"])+missing
    if spec["limit"]:
        result["notes"].append(f"İstenen ilk {spec['limit']} kayıt seçildi; listenin kapsamı açık kullanıcı sınırıdır.")
        result["records"]=result["records"][:spec["limit"]]
    return result
