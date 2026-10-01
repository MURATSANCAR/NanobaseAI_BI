"""Remote real API / independent document and cross-source acceptance.

Reuses only acceptance transport and strict full-result comparison; never imports
the product planner, executor, report builders, or product SQL.
"""
from collections import defaultdict
from decimal import Decimal
import json
from statistics import median

import composable_live as gate
import independent_reference as ir


def cases():
    common = dict(source="logo", periods=[["2026-09-01", "2026-10-01"]])
    return [
        dict(common, id="CPD01", mode="invoice_statistics", question="Eylül 2026 satış faturalarının müşteri bazında fatura sayısını, genel toplamını, aritmetik ortalamasını ve medyanını göster. İadeleri bu başlık istatistiğine katma.", columns=["customer_code","customer_name","invoice_count","invoice_total","invoice_mean","invoice_median"], keys=["customer_code","customer_name"]),
        dict(common, id="CPD02", mode="orphan_invoice_lines", question="Eylül 2026 için malzeme satırı olmayan satış faturalarını ve fatura referansı boş ya da hedef faturası bulunamayan malzeme hareketlerini belge kimlikleriyle göster. Faturasız hareketi otomatik hata sayma.", columns=["invoice_id","invoice_number","invoice_date","customer_code","customer_name","amount","finding","line_id","movement_date","source_code"], keys=["source_code","finding","invoice_id","line_id"]),
        dict(common, id="CPD03", mode="cross_book_sales_quality", match_status="unmatched", question="Eylül 2026'da faturalı satışı veya iadesi bulunan Logo stok kodlarından aktif CRM kitap kartıyla eşleşmeyenleri getir. Kod, Logo adı, CRM eşleşme durumu, KDV hariç net satış, iade tutarı ve birimi doğrulanabilen satış miktarı olsun; isim benzerliğiyle eşleştirme yapma.", columns=["match_status","logo_codes","logo_names","net_sales","return_amount","sold_quantity","book_code","crm_book_ids","crm_book_names","publisher","author_ids","author_names","shared_authors","missing_fields","name_difference"], keys=["book_code","logo_codes"]),
    ]


def reference(case, conn):
    if case["mode"] == "invoice_statistics":
        # Raw, independently selected header values; median uses all invoices.
        rows=gate.query(conn,"SELECT C.CODE code,C.DEFINITION_ name,I.NETTOTAL total FROM dbo.LG_411_01_INVOICE I LEFT JOIN dbo.LG_411_CLCARD C ON C.LOGICALREF=I.CLIENTREF WHERE I.DATE_ >= '20260901' AND I.DATE_ < '20261001' AND I.CANCELLED=0 AND I.TRCODE IN (7,8,9)")
        grouped=defaultdict(list)
        for row in rows:grouped[(row["code"],row["name"])].append(Decimal(str(row["total"] or 0)))
        return [dict(customer_code=key[0],customer_name=key[1],invoice_count=len(values),invoice_total=sum(values),invoice_mean=sum(values)/len(values),invoice_median=median(values)) for key,values in grouped.items()]
    if case["mode"] == "orphan_invoice_lines":
        # Two independently selected populations. NOT EXISTS avoids fan-out.
        rows=gate.query(conn,"SELECT I.LOGICALREF invoice_id,I.FICHENO invoice_number,CONVERT(varchar(10),I.DATE_,23) invoice_date,C.CODE customer_code,C.DEFINITION_ customer_name,I.NETTOTAL amount FROM dbo.LG_411_01_INVOICE I LEFT JOIN dbo.LG_411_CLCARD C ON C.LOGICALREF=I.CLIENTREF WHERE I.CANCELLED=0 AND I.TRCODE IN (7,8,9) AND I.DATE_>='20260901' AND I.DATE_<'20261001' AND NOT EXISTS (SELECT 1 FROM dbo.LG_411_01_STLINE L WHERE L.INVOICEREF=I.LOGICALREF AND L.CANCELLED=0 AND L.LINETYPE=0)")
        for row in rows:row.update(line_id=None,movement_date=None,finding="invoice_without_material_line",source_code="411_01")
        movements=gate.query(conn,"SELECT L.LOGICALREF line_id,L.INVOICEREF invoice_id,CONVERT(varchar(10),L.DATE_,23) movement_date,L.LINENET amount FROM dbo.LG_411_01_STLINE L WHERE L.DATE_>='20260901' AND L.DATE_<'20261001' AND L.CANCELLED=0 AND L.LINETYPE=0 AND L.TRCODE IN (2,3,7,8,9) AND (L.INVOICEREF=0 OR NOT EXISTS (SELECT 1 FROM dbo.LG_411_01_INVOICE I WHERE I.LOGICALREF=L.INVOICEREF))")
        for row in movements:row.update(invoice_number=None,invoice_date=None,customer_code=None,customer_name=None,source_code="411_01",finding="movement_without_invoice_reference" if row["invoice_id"]==0 else "movement_invoice_not_found")
        return rows+movements
    crm=gate.connect("/data/nanobaseai/bi/secrets/crm-mssql-connection.json")
    try:
        # Etkin kitap: kullanıcı kararı K-CRM-PASIF (ir.crm_active), ürünün Aktif/Etkin listesi değil.
        codes={str(row["code"]).strip().casefold() for row in gate.query(crm,"SELECT K.new_stokkodu code FROM dbo.new_kitapBase K WITH (NOLOCK) WHERE "+ir.crm_active("new_kitapBase","K")+" AND NULLIF(LTRIM(RTRIM(K.new_stokkodu)),'') IS NOT NULL")}
    finally:crm.close()
    rows=gate.query(conn,"SELECT L.STOCKREF stock_id,I.CODE code,I.NAME name,L.TRCODE type,L.IOCODE iocode,L.LINENET amount,L.AMOUNT quantity,L.UINFO1 unit1,L.UINFO2 unit2 FROM dbo.LG_411_01_STLINE L WITH (NOLOCK) LEFT JOIN dbo.LG_411_ITEMS I WITH (NOLOCK) ON I.LOGICALREF=L.STOCKREF WHERE L.DATE_>='20260901' AND L.DATE_<'20261001' AND "+ir.population_where("L"))
    # Karar işaret haritaları: net_sales/return_amount K-SATIS-SATIR+K-IADE, satılan adet altın C040 (7/8/9, IOCODE 3/4).
    net=ir.LOGO_MEASURES["net_sales"].signs;ret=ir.LOGO_MEASURES["return_amount"].signs;sold=ir.LOGO_MEASURES["sold_quantity"]
    all_cards=gate.query(conn,"SELECT CODE code,NAME name FROM dbo.LG_411_ITEMS")
    names=defaultdict(set); identities=defaultdict(set)
    for row in all_cards:
        if row["code"] and str(row["code"]).strip():
            key=str(row["code"]).strip().casefold();names[key].add(str(row["name"] or ""));identities[key].add(str(row["code"]).strip())
    groups={}
    for row in rows:
        key=str(row["code"]).strip().casefold() if row["code"] and str(row["code"]).strip() else "__unresolved:411:"+str(row["stock_id"])
        if key in codes:continue
        g=groups.setdefault(key,[Decimal(0),Decimal(0),Decimal(0),False])
        amount=Decimal(str(row["amount"] or 0))
        g[0]+=net.get(row["type"],0)*amount
        g[1]+=ret.get(row["type"],0)*amount
        if row["type"] in sold.signs and row["iocode"] in sold.sales_iocodes:
            g[2]+=Decimal(str(row["quantity"] or 0))
            g[3]|= row["unit1"] is None or row["unit2"] is None or row["unit1"]<=0 or row["unit1"]!=row["unit2"]
        names[key].add(str(row["name"] or ""));identities[key].add(str(row["code"] or "411:"+str(row["stock_id"])).strip())
    def packed(value):return json.dumps(value,ensure_ascii=False)
    return [dict(match_status="unmatched",logo_codes=packed(sorted(identities[key])),logo_names=packed(sorted(names[key])),net_sales=v[0],return_amount=v[1],sold_quantity=None if v[3] else v[2],book_code=None if key.startswith("__unresolved:") else key,crm_book_ids="[]",crm_book_names="[]",publisher=None,author_ids="[]",author_names="[]",shared_authors=False,missing_fields=packed(["isbn","publisher","author_link"]),name_difference=False) for key,v in groups.items()]


_compare=gate.compare
def compare(case,answer,whole,expected):
    errors=[]
    spec=answer.get("semantic",{}).get("plan",{}).get("logo_report") or {}
    if spec.get("mode")!=case["mode"]:errors.append("Document report mode differs")
    if spec.get("start")!="2026-09-01" or spec.get("end")!="2026-10-01":errors.append("Document report period differs")
    if case.get("match_status") and spec.get("match_status")!=case["match_status"]:errors.append("Cross-source filter differs")
    # The report's own explicit period is authoritative; parent period is unused.
    adapted={**answer,"semantic":{**answer.get("semantic",{}),"plan":{**answer.get("semantic",{}).get("plan",{}),"periods":case["periods"]}}}
    return errors+_compare(case,adapted,whole,expected)


if __name__=="__main__":
    gate.cases=cases;gate.reference=reference;gate.compare=compare
    raise SystemExit(gate.main())
