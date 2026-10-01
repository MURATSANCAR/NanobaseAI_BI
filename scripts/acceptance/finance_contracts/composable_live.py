"""Remote-only composable finance acceptance; independent SQL, real API, no engine imports.

Run on the test server, never locally. All source queries are read-only. The only
write is a short-lived session for the existing timasai account, deleted in finally.
Derived output aliases may come from the plan, but their operations and operands
must match the independently specified case before any alias is accepted.
"""
import argparse
import calendar
from collections import Counter
from datetime import date, datetime, timedelta
from decimal import Decimal
import fcntl
import hashlib
import json
import os
from pathlib import Path
import random
import secrets
import signal
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from zoneinfo import ZoneInfo

# Bağımsız referans: ölçüler kullanıcı kararı/altın setten, ürünün METRICS ifadesinden değil (2026-10-01).
import independent_reference as ir

REFERENCE_DATE = "2026-09-30"


class ReferenceDateChanged(RuntimeError):
    pass


def require_reference_day(reference_date):
    if date.fromisoformat(reference_date).isoformat()!=reference_date:
        raise ValueError("Reference date must be canonical YYYY-MM-DD")
    actual=datetime.now(ZoneInfo("Europe/Istanbul")).date().isoformat()
    if actual!=reference_date:
        raise ReferenceDateChanged(f"Istanbul day {actual} differs from explicit reference date {reference_date}; stop without shifting the oracle")

REFERENCE_RETRIES = []
REFERENCE_CONTEXT = {}
EXACT_COUNT_COLUMNS = frozenset({"sold_quantity", "net_quantity", "invoice_count", "record_count",
                                 "missing_isbn", "missing_book_code", "missing_author"})
ROOT = Path("/data/nanobaseai/bi/frontend/backend")
ST = ir.sales_from("411")  # K-DONEM-FATURA: dönem SH.DATE_
SALES_METRICS = ("sales_amount", "return_amount", "net_sales", "sold_quantity", "net_quantity")


def measures(variant="decision"):
    """`decision`: ir.LOGO_MEASURES (karar/altın set). `product`: kurulu ürün ifadesi, yalnız TANIM_FARKI sınıflaması."""
    return {m: ir.measure_sql(m, "S", variant) for m in SALES_METRICS}


MEASURES = measures("decision")
DIMENSIONS = {
    "channel": ("C.SPECODE2", "LEFT JOIN dbo.LG_411_CLCARD C WITH (NOLOCK) ON C.LOGICALREF=S.CLIENTREF"),
    "day": ("CONVERT(varchar(10),SH.DATE_,23)", ""),
    "month": ("CONVERT(varchar(7),SH.DATE_,23)", ""),
}


def sales_sql(start, end, metrics, dimension=None, having=None, limit=None, variant="decision"):
    # This reference builder has its own tiny, fixed allowlist. Never accepts AI SQL.
    MEASURES = measures(variant)
    expression, join = DIMENSIONS[dimension] if dimension else (None, "")
    columns = ([f"{expression} [{dimension}]"] if dimension else [])
    columns += [f"COALESCE({MEASURES[m]},0) [{m}]" for m in metrics]
    sql = "SELECT " + (f"TOP ({limit}) " if limit else "") + ",".join(columns)
    sql += f" FROM {ST} {join} WHERE {ir.population_where('S')} AND SH.DATE_>='{start}' AND SH.DATE_<'{end}'"
    if expression:
        sql += " GROUP BY " + expression
    if having:
        metric, op, threshold = having
        assert op in (">", ">=", "<", "<=")
        sql += f" HAVING {MEASURES[metric]} {op} {Decimal(str(threshold))}"
    if limit:
        sql += f" ORDER BY {MEASURES[metrics[0]]} DESC,{expression} DESC"
    return sql


def cases(reference_date=REFERENCE_DATE, variant="decision"):
    """`variant='product'` aynı vakaları ürünün bugünkü tanımıyla kurar; yalnız TANIM_FARKI sınıflaması içindir."""
    MEASURES = measures(variant)
    def sales_sql(*a, **k):
        return globals()["sales_sql"](*a, variant=variant, **k)
    def kitap(alias="K"):
        return ir.crm_active("new_kitapBase", alias, variant)
    anchor=date.fromisoformat(reference_date)
    month_index=anchor.year*12+anchor.month-1-3
    back_year,back_month=divmod(month_index,12);back_month+=1
    three_month_start=date(back_year,back_month,min(anchor.day,calendar.monthrange(back_year,back_month)[1])).isoformat()
    tomorrow=(anchor+timedelta(days=1)).isoformat()

    out = []
    def add(question, metrics, dimension=None, start="2026-09-01", end="2026-10-01", **extra):
        row = dict(id=f"CP{len(out)+1:03d}", question=question, source="logo", metrics=metrics,
                   keys=[dimension] if dimension else [], columns=([dimension] if dimension else [])+metrics,
                   periods=[[start,end]], referenceSql=sales_sql(start,end,metrics,dimension,extra.get("having"),extra.get("limit")))
        row.update(extra); out.append(row)
    add("Eylül 2026'da iade tutarı, iadeler düşülmeden KDV hariç satış tutarının yüzde kaçı? İki tutarı da göster.", ["return_amount","sales_amount"], derived=dict(op="ratio",left="return_amount",right="sales_amount",scale=100))
    add("Eylül 2026'da kanallara göre iade tutarının KDV hariç brüt satış tutarına oranını yüzde olarak ver, iki tutarı da yanında göster.", ["return_amount","sales_amount"], "channel", derived=dict(op="ratio",left="return_amount",right="sales_amount",scale=100))
    add("Eylül 2026'da net satılan adedin iade düşülmeden satılan adede oranı kaç? İki adet toplamını da ver; oranı yüzdeye çevirme.", ["net_quantity","sold_quantity"], derived=dict(op="ratio",left="net_quantity",right="sold_quantity",scale=1))
    add("Eylül 2026'da kanal bazında KDV hariç net satışın, iade düşülmeden KDV hariç satışa oranını yüzde göster. Pay ve paydayı da göster.", ["net_sales","sales_amount"], "channel", derived=dict(op="ratio",left="net_sales",right="sales_amount",scale=100))
    add("Eylül 2026'da KDV hariç satış tutarından iade tutarını çıkar, satış ve iade tutarlarını da ayrı kolonlarda göster.", ["sales_amount","return_amount"], derived=dict(op="difference",left="sales_amount",right="return_amount",scale=1))
    add("Eylül 2026'da kanal bazında satılan adetten net satılan adedi çıkar; iki adet toplamı ve aralarındaki fark birlikte görünsün.", ["sold_quantity","net_quantity"], "channel", derived=dict(op="difference",left="sold_quantity",right="net_quantity",scale=1))
    for dimension, wording in [(None,"toplam"),("channel","kanal bazında")]:
        for op, instruction in [("difference","Eylül tutarından ağustos tutarını çıkar"),("percent_change","ağustosa göre eylülün değişimini yüzde olarak hesapla")]:
            add(f"Ağustos 2026 ile Eylül 2026 {wording} KDV hariç iade düşülmüş net satışını karşılaştır; {instruction}. İki dönemin tutarı da olsun.", ["net_sales"], dimension,
                comparison=dict(op=op,metric="net_sales",base_period=0,target_period=1), periods=[["2026-08-01","2026-09-01"],["2026-09-01","2026-10-01"]])
    for dimension, noun, metric, label, op, threshold in [
        ("channel","kanalları","net_sales","KDV hariç net satış tutarı",">",100000),
        ("day","günleri","net_sales","KDV hariç net satış tutarı",">",100000),
        ("channel","kanalları","return_amount","KDV hariç iade tutarı",">",0),
        ("day","günleri","sold_quantity","satılan adet",">",1000),
        ("channel","kanalları","net_sales","KDV hariç net satış tutarı","<",0),
        ("day","günleri","return_amount","KDV hariç iade tutarı",">=",10000),
    ]:
        condition = {">":"büyük","<":"küçük",">=":"büyük veya eşit"}[op]
        add(f"Eylül 2026'da {label} {threshold} değerinden {condition} olan {noun}, toplamlarıyla listele.",[metric],dimension,having=[metric,op,threshold])
    add("Son üç ayın KDV hariç, iadeler düşülmüş net satışını ay ay göster; bugünden üç takvim ayı geriye git, bugün de dahil olsun.",["net_sales"],"month",start=three_month_start,end=tomorrow,relative=True)
    add("Bu yılın üçüncü çeyreğinde KDV hariç iade düşülmüş net satış toplamımız ne kadar?",["net_sales"],start=f"{anchor.year:04d}-07-01",end=f"{anchor.year:04d}-10-01",relative=True)
    add("Son otuz günde KDV hariç iade düşülmüş net satış ve iade tutarını göster; bugün de dahil olsun.",["net_sales","return_amount"],start=(anchor-timedelta(days=29)).isoformat(),end=tomorrow,relative=True)
    add("Dünkü KDV hariç net satış ve satılan adet toplamını göster.",["net_sales","sold_quantity"],start=(anchor-timedelta(days=1)).isoformat(),end=anchor.isoformat(),relative=True)
    add("Eylül 2026'da KDV hariç net satışı en yüksek ilk beş kanalı tutarlarıyla göster.",["net_sales"],"channel",limit=5)
    add("Eylül 2026'da satılan kitap adedi en yüksek ilk on günü adetleriyle göster.",["sold_quantity"],"day",limit=10)
    add("Eylül 2026'da KDV hariç iade tutarı en yüksek ilk üç kanalı listele.",["return_amount"],"channel",limit=3)
    add("Eylül 2026'nın KDV hariç net satış toplamını göster.",["net_sales"],thread="followup1")
    add("Peki aynı dönemin iade tutarı toplamı ne kadar?",["return_amount"],thread="followup1",followup=True)
    add("Bir de aynı dönemde iadeler düşülmeden satılan adet toplamını ver.",["sold_quantity"],thread="followup1",followup=True)
    for question, sql, columns, keys in [
        ("CRM'deki aktif kitaplarda güncel ISBN, stok kodu ve yazar künyesi metni boş olanların sayılarını ayrı ayrı, aktif kitap toplamıyla birlikte göster.", "SELECT COUNT_BIG(*) record_count,SUM(X.mi) missing_isbn,SUM(X.mb) missing_book_code,SUM(X.ma) missing_author FROM (SELECT CASE WHEN NULLIF(LTRIM(RTRIM(K.new_isbn13)),'') IS NULL THEN 1 ELSE 0 END mi,CASE WHEN NULLIF(LTRIM(RTRIM(K.new_stokkodu)),'') IS NULL THEN 1 ELSE 0 END mb,CASE WHEN NULLIF(LTRIM(RTRIM(K.new_yazartext)),'') IS NULL THEN 1 ELSE 0 END ma FROM dbo.new_kitapBase K WITH (NOLOCK) WHERE "+kitap()+") X", ["record_count","missing_isbn","missing_book_code","missing_author"], []),
        ("CRM'de aynı stok kodunu kullanan birden fazla aktif kitap kaydı var mı? Boş stok kodlarını dahil etme, her kodu kayıt sayısıyla göster.", "SELECT LTRIM(RTRIM(K.new_stokkodu)) book_code,COUNT_BIG(*) record_count FROM dbo.new_kitapBase K WITH (NOLOCK) WHERE "+kitap()+" AND NULLIF(LTRIM(RTRIM(K.new_stokkodu)),'') IS NOT NULL GROUP BY LTRIM(RTRIM(K.new_stokkodu)) HAVING COUNT_BIG(*)>=2", ["book_code","record_count"],["book_code"]),
    ]:
        out.append(dict(id=f"CP{len(out)+1:03d}",question=question,source="crm",referenceSql=sql,columns=columns,keys=keys,periods=[]))
    add("Eylül 2026'da iadeler düşülmeden KDV hariç satış tutarı, KDV hariç net satış tutarından yüzde kaç farklı? Farkı net satış tutarına böl; her iki tutarı da göster.", ["sales_amount","net_sales"], derived=dict(op="percent_change",left="sales_amount",right="net_sales",scale=100))
    add("31 Aralık 2026'da KDV hariç iade tutarının, iade düşülmeden KDV hariç satış tutarına yüzde oranını ve iki tutarı göster. Satış sıfırsa oranı hesaplanamadı olarak bırak.", ["return_amount","sales_amount"],start="2026-12-31",end="2027-01-01",derived=dict(op="ratio",left="return_amount",right="sales_amount",scale=100))
    # Aggregate each fact independently before joining. Never multiply invoice
    # or collection amounts by sales-line cardinality.
    invoice_where="I.CANCELLED=0 AND I.TRCODE IN (7,8,9) AND I.DATE_>='20260901' AND I.DATE_<'20261001'"
    collection_where="L.CANCELLED=0 AND L.SIGN=1 AND L.TRCODE IN (1,20,61,62,70) AND C.CODE LIKE '120%' AND L.DATE_>='20260901' AND L.DATE_<'20261001'"
    mixed_cases=[
        ("Eylül 2026 için KDV hariç iadeler düşülmüş net satış tutarını, satış faturası sayısını ve müşteri ödeme hareketleri toplamını aynı satırda göster. Ödeme hareketlerine nakit, havale, çek, senet ve kart dahil olsun.",
         "WITH sales AS ("+sales_sql("2026-09-01","2026-10-01",["net_sales"])+"), invoices AS (SELECT COUNT_BIG(*) invoice_count FROM dbo.LG_411_01_INVOICE I WHERE "+invoice_where+"), payments AS (SELECT COALESCE(SUM(L.AMOUNT),0) collections FROM dbo.LG_411_01_CLFLINE L JOIN dbo.LG_411_CLCARD C ON C.LOGICALREF=L.CLIENTREF WHERE "+collection_where+") SELECT S.net_sales,I.invoice_count,P.collections FROM sales S CROSS JOIN invoices I CROSS JOIN payments P",
         ["net_sales","invoice_count","collections"],[]),
        ("Eylül 2026'da müşteri bazında KDV hariç iadeler düşülmüş net satış tutarı ile satış faturalarının genel toplamını ayrı kolonlarda göster. Bir tarafta hareketi olmayan müşteriyi listeden düşürme.",
         "WITH sales AS (SELECT C.CODE customer_code,C.DEFINITION_ customer_name,COALESCE("+MEASURES["net_sales"]+",0) net_sales FROM "+ST+" LEFT JOIN dbo.LG_411_CLCARD C WITH (NOLOCK) ON C.LOGICALREF=S.CLIENTREF WHERE "+ir.population_where("S")+" AND SH.DATE_>='20260901' AND SH.DATE_<'20261001' GROUP BY C.CODE,C.DEFINITION_), invoices AS (SELECT C.CODE customer_code,C.DEFINITION_ customer_name,SUM(I.NETTOTAL) invoice_amount FROM dbo.LG_411_01_INVOICE I LEFT JOIN dbo.LG_411_CLCARD C ON C.LOGICALREF=I.CLIENTREF WHERE "+invoice_where+" GROUP BY C.CODE,C.DEFINITION_) SELECT COALESCE(S.customer_code,I.customer_code) customer_code,COALESCE(S.customer_name,I.customer_name) customer_name,COALESCE(S.net_sales,0) net_sales,COALESCE(I.invoice_amount,0) invoice_amount FROM sales S FULL OUTER JOIN invoices I ON (S.customer_code=I.customer_code OR S.customer_code IS NULL AND I.customer_code IS NULL) AND (S.customer_name=I.customer_name OR S.customer_name IS NULL AND I.customer_name IS NULL)",
         ["customer_code","customer_name","net_sales","invoice_amount"],["customer_code","customer_name"]),
        ("Eylül 2026'da kanal bazında satış faturası sayısını ve iadeler düşülmeden satılan kitap adedini birlikte göster. Yalnız bir ölçüde hareketi olan kanallar da kalsın.",
         "WITH sales AS ("+sales_sql("2026-09-01","2026-10-01",["sold_quantity"],"channel")+"), invoices AS (SELECT C.SPECODE2 channel,COUNT_BIG(*) invoice_count FROM dbo.LG_411_01_INVOICE I LEFT JOIN dbo.LG_411_CLCARD C ON C.LOGICALREF=I.CLIENTREF WHERE "+invoice_where+" GROUP BY C.SPECODE2) SELECT COALESCE(S.channel,I.channel) channel,COALESCE(I.invoice_count,0) invoice_count,COALESCE(S.sold_quantity,0) sold_quantity FROM sales S FULL OUTER JOIN invoices I ON S.channel=I.channel OR S.channel IS NULL AND I.channel IS NULL",
         ["channel","invoice_count","sold_quantity"],["channel"]),
        ("Eylül 2026'da gün gün KDV hariç iadeler düşülmüş net satış tutarını ve müşteri ödeme hareketleri toplamını göster. Ödemelere nakit, havale, çek, senet ve kart dahil; yalnız satış ya da ödeme olan günler de listede kalsın.",
         "WITH sales AS ("+sales_sql("2026-09-01","2026-10-01",["net_sales"],"day")+"), payments AS (SELECT CONVERT(varchar(10),L.DATE_,23) day,SUM(L.AMOUNT) collections FROM dbo.LG_411_01_CLFLINE L JOIN dbo.LG_411_CLCARD C ON C.LOGICALREF=L.CLIENTREF WHERE "+collection_where+" GROUP BY CONVERT(varchar(10),L.DATE_,23)) SELECT COALESCE(S.day,P.day) day,COALESCE(S.net_sales,0) net_sales,COALESCE(P.collections,0) collections FROM sales S FULL OUTER JOIN payments P ON S.day=P.day",
         ["day","net_sales","collections"],["day"]),
    ]
    for question,sql,columns,keys in mixed_cases:
        out.append(dict(id=f"CP{len(out)+1:03d}",question=question,source="logo",referenceSql=sql,columns=columns,keys=keys,periods=[["2026-09-01","2026-10-01"]],mixedFamily=True))
    # Independent analytic references use SQL window/UNION semantics, not product helpers.
    base_sql = sales_sql("2026-09-01", "2026-10-01", ["net_sales", "return_amount"], "channel")
    ordered = "net_sales DESC,CASE WHEN channel IS NULL THEN 1 ELSE 0 END DESC,channel COLLATE Latin1_General_100_BIN2 DESC"
    top_cte = "WITH base AS (" + base_sql + "), ranked AS (SELECT *,ROW_NUMBER() OVER(ORDER BY " + ordered + ") rn FROM base), selected AS (SELECT channel,net_sales,return_amount,CAST(N'Detay' AS nvarchar(16)) row_kind FROM ranked WHERE rn<=3 UNION ALL SELECT NULL,SUM(net_sales),SUM(return_amount),N'Kalan' FROM ranked WHERE rn>3 HAVING COUNT(*)>0) "
    contribution_columns = ["__contribution_group_total", "__contribution_share_pct", "__contribution_cumulative_pct"]
    def contribution_select(table):
        return "SELECT *,SUM(net_sales) OVER() __contribution_group_total,100.0*net_sales/NULLIF(SUM(net_sales) OVER(),0) __contribution_share_pct,100.0*SUM(net_sales) OVER(ORDER BY " + ordered + " ROWS UNBOUNDED PRECEDING)/NULLIF(SUM(net_sales) OVER(),0) __contribution_cumulative_pct FROM " + table
    analytic_cases = [
        ("Eylül 2026 için kanallara göre KDV hariç iadeler düşülmüş net satış ve iade tutarını göster. Her kanalın net satış payını, azalan net satış sırasında kümülatif payını ve genel net satış toplamını da ayrı kolonlara koy. Negatifleri koru.",
         "WITH base AS (" + base_sql + ") " + contribution_select("base"),
         ["channel", "net_sales", "return_amount", *contribution_columns], ["channel"],
         [dict(op="contribution",metric="net_sales",group_by=[],limit=None,label="")]),
        ("Eylül 2026 için net satışı en yüksek ilk üç kanalı ve kalan kanalların toplamını göster. KDV hariç iadeler düşülmüş net satış ile iade tutarı ayrı olsun, negatifleri koru. Satır türünde ilk üç için Detay, diğerlerinin toplamı için Kalan yaz.",
         top_cte + "SELECT channel,net_sales,return_amount,row_kind FROM selected",
         ["channel", "net_sales", "return_amount", "row_kind"], ["row_kind", "channel"],
         [dict(op="top_remainder",metric="net_sales",group_by=[],limit=3,label="Kalan")]),
        ("Eylül 2026 için KDV hariç iadeler düşülmüş net satışı en yüksek ilk üç kanal ve Kalan satırı olsun; iade tutarını da göster. Önce ilk üç ve kalan toplamını oluştur, sonra bu satırların net satış payını, azalan sıradaki kümülatif payını ve genel toplamı hesapla. Satır türleri Detay ve Kalan olsun.",
         top_cte + contribution_select("selected"),
         ["channel", "net_sales", "return_amount", "row_kind", *contribution_columns], ["row_kind", "channel"],
         [dict(op="top_remainder",metric="net_sales",group_by=[],limit=3,label="Kalan"),dict(op="contribution",metric="net_sales",group_by=[],limit=None,label="")]),
    ]
    for question,sql,columns,keys,analytics_spec in analytic_cases:
        out.append(dict(id=f"CP{len(out)+1:03d}",question=question,source="logo",referenceSql=sql,columns=columns,keys=keys,periods=[["2026-09-01","2026-10-01"]],analytics=analytics_spec))
    mixed_sql = "WITH invoices AS (SELECT C.SPECODE2 channel,SUM(I.NETTOTAL) invoice_amount,COUNT_BIG(*) invoice_count FROM dbo.LG_411_01_INVOICE I LEFT JOIN dbo.LG_411_CLCARD C ON C.LOGICALREF=I.CLIENTREF WHERE " + invoice_where + " GROUP BY C.SPECODE2), payments AS (SELECT C.SPECODE2 channel,SUM(L.AMOUNT) collections FROM dbo.LG_411_01_CLFLINE L JOIN dbo.LG_411_CLCARD C ON C.LOGICALREF=L.CLIENTREF WHERE " + collection_where + " GROUP BY C.SPECODE2) SELECT COALESCE(I.channel,P.channel) channel,COALESCE(I.invoice_amount,0) invoice_amount,COALESCE(I.invoice_count,0) invoice_count,COALESCE(P.collections,0) collections FROM invoices I FULL OUTER JOIN payments P ON I.channel=P.channel OR I.channel IS NULL AND P.channel IS NULL"
    out.append(dict(id=f"CP{len(out)+1:03d}",question="Eylül 2026'da kanallara göre satış faturalarının genel toplamını, fatura sayısını ve müşteri ödeme hareketlerini ayrı kolonlarda göster. Nakit, banka, çek, senet ve kart dahil; yalnız bir tarafta hareketi olan kanallar kalsın.",source="logo",referenceSql=mixed_sql,columns=["channel","invoice_amount","invoice_count","collections"],keys=["channel"],periods=[["2026-09-01","2026-10-01"]],mixedFamily=True))
    def leaf(metrics, dimension):
        return dict(source="logo",metrics=metrics,dimensions=[dimension],keys=[dimension],columns=[dimension,*metrics],periods=[["2026-09-01","2026-10-01"]],referenceSql=sales_sql("2026-09-01","2026-10-01",metrics,dimension))
    for question, children in [
        ("Eylül 2026'nın KDV hariç iadeler düşülmüş net satışını iki ayrı rapor bölümünde ver: birinci bölüm kanallara göre, ikinci bölüm gün gün olsun. Her iki bölüm tüm satırları içersin; ilk N sınırı istemiyorum.", [leaf(["net_sales"],"channel"),leaf(["net_sales"],"day")]),
        ("Eylül 2026 için iki bağımsız tablo hazırla: kanallara göre KDV hariç iadeler düşülmüş net satış ve iade tutarı birinci tabloda; gün gün iadeler düşülmeden satılan kitap adedi ikinci tabloda olsun. Tüm satırları ver.", [leaf(["net_sales","return_amount"],"channel"),leaf(["sold_quantity"],"day")]),
    ]:
        out.append(dict(id=f"CP{len(out)+1:03d}",question=question,source="logo",sections=children,columns=["section","status","row_count"],keys=["section"],periods=[],referenceSql="SELECT 1 ignored"))
    mixed_summary = dict(source="logo",metrics=["net_sales","invoice_count","collections"],dimensions=[],keys=[],columns=["net_sales","invoice_count","collections"],periods=[["2026-09-01","2026-10-01"]],referenceSql=mixed_cases[0][1])
    out.append(dict(id=f"CP{len(out)+1:03d}",question="Eylül 2026 için iki ayrı bölüm hazırla. Genel özette KDV hariç iadeler düşülmüş net satış toplamı, satış faturası sayısı ve nakit, havale, çek, senet, kart dahil müşteri ödeme hareketleri toplamı olsun. İkinci bölümde sadece kanallara göre aynı net satış tutarı bulunsun; tüm kanalları göster.",source="logo",sections=[mixed_summary,leaf(["net_sales"],"channel")],columns=["section","status","row_count"],keys=["section"],periods=[],referenceSql="SELECT 1 ignored"))
    # Cross-source identity dimensions: independent SQL plus Python aggregation.
    for dim, cols, question in [
        ("subbrand", ["subbrand_id","subbrand"], "Eylül 2026 net satış tutarını CRM new_yayinciid ile bağlı güncel alt marka kimliği ve adına göre göster; eşleşmeyenleri boş grupta koru."),
        ("author_group", ["author_group_ids","author_group_names"], "Eylül 2026 net satış tutarını aktif gerçek Yazar katılımındaki kişi kimlikleri ortak grubuna göre göster. Çok yazarlı kitabı bir grupta bir kez say; kişilere dağıtma, eşleşmeyenleri boş grupta koru.")]:
        out.append(dict(id=f"CP{len(out)+1:03d}",question=question,source="cross_dimensions",crossDimension=dim,metrics=["net_sales"],dimensions=[dim],columns=[*cols,"net_sales"],keys=cols,periods=[["2026-09-01","2026-10-01"]],allowCoverageGap=True,referenceSql="SELECT LTRIM(RTRIM(I.CODE)) book_code,COALESCE("+MEASURES["net_sales"]+",0) net_sales FROM "+ST+" LEFT JOIN dbo.LG_411_ITEMS I WITH (NOLOCK) ON I.LOGICALREF=S.STOCKREF WHERE "+ir.population_where("S")+" AND SH.DATE_>='20260901' AND SH.DATE_<'20261001' GROUP BY LTRIM(RTRIM(I.CODE))"))
    # Modifier-scope regressions: opposite operand order and different fact grains.
    add("Eylül 2026'da iadeler düşülmeden satılan adedi, iadeler düşüldükten sonraki net satılan adede böl. İki adet toplamını ayrı kolonlarda ver; oran yüzde değil katsayı olsun.",
        ["sold_quantity","net_quantity"], derived=dict(op="ratio",left="sold_quantity",right="net_quantity",scale=1))
    out.append(dict(id=f"CP{len(out)+1:03d}",
        question="Eylül 2026 için iki ayrı kayıt kümesinden toplam hesapla: pay, iptal edilmemiş satış faturalarının KDV dahil genel toplamı; payda, satış satırlarından iadeler düşülmüş KDV hariç net satış tutarı olsun. Fatura başlıklarını satış satırlarıyla çoğaltmadan ayrı ayrı topla. Aynı tek satırda iki toplamı ve payın paydaya oranını katsayı olarak göster; yüzdeye çevirme.",
        source="logo",metrics=["invoice_amount","net_sales"],dimensions=[],keys=[],columns=["invoice_amount","net_sales"],
        periods=[["2026-09-01","2026-10-01"]],mixedFamily=True,
        derived=dict(op="ratio",left="invoice_amount",right="net_sales",scale=1),
        referenceSql="WITH invoice_totals AS (SELECT COALESCE(SUM(I.NETTOTAL),0) invoice_amount FROM dbo.LG_411_01_INVOICE I WHERE "+invoice_where+"), sales_totals AS ("+sales_sql("2026-09-01","2026-10-01",["net_sales"])+") SELECT I.invoice_amount,S.net_sales FROM invoice_totals I CROSS JOIN sales_totals S"))
    for case in out:
        if case.get("sections"):
            case["referenceQueries"] = [child["referenceSql"] for child in case["sections"]]
            continue
        case["variant"] = variant
        case["referenceQueries"] = ([sales_sql(a,b,[case["comparison"]["metric"]],case["keys"][0] if case["keys"] else None) for a,b in case["periods"]]
                                    if case.get("comparison") else [case["referenceSql"]])
    return out


def environment(unit):
    pid = subprocess.check_output(["systemctl","show",unit,"-p","MainPID","--value"],text=True).strip()
    if not pid.isdigit() or int(pid)<1: raise RuntimeError(f"Service not running: {unit}")
    return dict(x.split("=",1) for x in Path(f"/proc/{pid}/environ").read_text().split("\0") if "=" in x)


def connect(path):
    import pyodbc
    cfg=json.loads(Path(path).read_text())
    def esc(value): return "{"+str(value).replace("}","}}")+"}"
    values=dict(DRIVER=cfg.get("driver","FreeTDS"),SERVER=cfg["host"],PORT=cfg.get("port",1433),DATABASE=cfg["database"],UID=cfg["user"],PWD=cfg["password"],TDS_Version=cfg.get("tds_version","7.4"))
    conn=pyodbc.connect(";".join(k+"="+esc(v) for k,v in values.items()),timeout=15,autocommit=True,readonly=True)
    conn.timeout=90
    return conn


def query(conn,sql):
    if not sql.lstrip().upper().startswith(("SELECT ","WITH ")): raise ValueError("Reference is not a SELECT/CTE")
    for attempt in range(1,4):
        try:
            return query_once(conn,sql)
        except Exception as exc:
            args=getattr(exc,"args",())
            if not args or args[0] not in ("40001","42000") or "(1205)" not in str(exc):
                raise
            delay=random.uniform(1,3) if attempt<3 else None
            REFERENCE_RETRIES.append({**REFERENCE_CONTEXT,
                "observedAtUtc":datetime.now(ZoneInfo("UTC")).isoformat(),
                "sqlSha256":hashlib.sha256(sql.encode()).hexdigest(),
                "sqlState":args[0],"errorCode":1205,"failedAttempt":attempt,
                "retryAfterMs":round(delay*1000) if delay is not None else None,
                "error":str(exc)[:600],"execution":"independent_reference_not_product_api"})
            if delay is None:raise
            time.sleep(delay)


def query_once(conn,sql):
    cur=conn.cursor()
    try:
        cur.execute(sql); cols=[x[0] for x in cur.description]; rows=cur.fetchmany(250001)
        if len(rows)>250000: raise RuntimeError("Independent reference truncated")
        return [dict(zip(cols,r)) for r in rows]
    finally: cur.close()


def calculate(op,left,right,scale=1):
    if left is None or right is None:return None
    left,right=Decimal(str(left)),Decimal(str(right))
    if op=="difference":return (left-right)*Decimal(str(scale))
    if not right:return None
    if op=="ratio":return left/right*Decimal(str(scale))
    if op=="percent_change":return (left-right)/right*100
    raise ValueError("Unknown independent operation")


def dimension_reference(case, conns):
    sales = query(conns["logo"], case["referenceSql"])
    # Etkin kayıt: kullanıcı kararı K-CRM-PASIF (durum nedeni Pasif değil), ürünün Aktif/Etkin listesi değil.
    def active(entity, alias):
        table = {"new_kitap":"new_kitapBase","new_marka":"new_markaBase","contact":"ContactBase"}[entity]
        return ir.crm_active(table, alias, case.get("variant","decision"))
    cards = query(conns["crm"], "SELECT K.new_kitapId book_id,K.new_stokkodu book_code,M.new_markaId subbrand_id,M.new_name subbrand FROM dbo.new_kitapBase K LEFT JOIN dbo.new_markaBase M ON M.new_markaId=K.new_yayinciid AND " + active("new_marka","M") + " WHERE " + active("new_kitap","K"))
    people = query(conns["crm"], "SELECT DISTINCT L.new_Kitap book_id,C.ContactId person_id,C.FullName person_name FROM dbo.new_eserkatilimBase L JOIN dbo.ContactBase C ON C.ContactId=L.new_Katilimsaglayan AND " + active("contact","C") + " JOIN dbo.new_katilimcitipiBase R ON R.new_katilimcitipiId=L.new_katilimciTipi AND R.statecode=0 AND LTRIM(RTRIM(R.new_name))=N'Yazar' WHERE L.statecode=0") if case["crossDimension"]=="author_group" else []
    broken = query(conns["crm"], "SELECT DISTINCT L.new_Kitap book_id FROM dbo.new_eserkatilimBase L JOIN dbo.new_katilimcitipiBase R ON R.new_katilimcitipiId=L.new_katilimciTipi AND R.statecode=0 AND LTRIM(RTRIM(R.new_name))=N'Yazar' LEFT JOIN dbo.ContactBase C ON C.ContactId=L.new_Katilimsaglayan AND " + active("contact","C") + " WHERE L.statecode=0 AND C.ContactId IS NULL") if case["crossDimension"]=="author_group" else []
    incomplete={str(r["book_id"]).lower() for r in broken if r["book_id"]}
    links={}
    for r in people: links.setdefault(str(r["book_id"]).lower(),{})[str(r["person_id"]).lower()]=r["person_name"]
    bycode={}
    for r in cards: bycode.setdefault(str(r["book_code"] or "").strip().casefold(),[]).append(r)
    totals={}
    for row in sales:
        candidates=bycode.get(str(row["book_code"] or "").strip().casefold(),[])
        key=(None,None)
        if len(candidates)==1:
            card=candidates[0]
            if case["crossDimension"]=="subbrand":key=(str(card["subbrand_id"]).lower() if card["subbrand_id"] and card["subbrand"] else None,card["subbrand"])
            else:
                authors=links.get(str(card["book_id"]).lower(),{}) if str(card["book_id"]).lower() not in incomplete else {}
                ids=sorted(authors)
                if ids:key=(json.dumps(ids,ensure_ascii=False),json.dumps([authors[i] for i in ids],ensure_ascii=False))
        totals[key]=totals.get(key,Decimal(0))+Decimal(str(row["net_sales"]))
    return [dict(zip(case["keys"],key),net_sales=value) for key,value in totals.items()]


def reference(case,conn):
    variant=case.get("variant","decision")
    if case.get("crossDimension"):
        return dimension_reference(case,conn)
    if case.get("sections"):
        return {"sections": [reference(child,conn) for child in case["sections"]]}
    if not case.get("comparison"):
        rows=query(conn,case["referenceSql"])
        if case.get("derived"):
            d=case["derived"]
            for row in rows:row["__derived"]=calculate(d["op"],row[d["left"]],row[d["right"]],d["scale"])
        return rows
    spec=case["comparison"]; metric=spec["metric"]; keys=case["keys"]
    pairs=[]
    for start,end in case["periods"]:
        sql=sales_sql(start,end,[metric],keys[0] if keys else None,variant=variant)
        pairs.append({tuple(r[k] for k in keys):r[metric] for r in query(conn,sql)})
    base,target=pairs; rows=[]
    for key in set(base)|set(target):
        a,b=base.get(key),target.get(key)
        rows.append(dict(zip(keys,key),base_period_start=case["periods"][0][0],base_period_end_exclusive=case["periods"][0][1],target_period_start=case["periods"][1][0],target_period_end_exclusive=case["periods"][1][1],base_value=a,target_value=b,__derived=calculate(spec["op"],b,a)))
    return rows


# Units are specified independently of application result metadata. A monetary
# subtraction remains money; a ratio/percentage has its own numeric precision.
REFERENCE_METRIC_UNITS = {
    "sales_amount":"TRY", "net_sales":"TRY", "return_amount":"TRY",
    "invoice_amount":"TRY", "collections":"TRY",
    "sold_quantity":"quantity", "net_quantity":"quantity", "invoice_count":"count",
}


def numeric_tolerance(column, derived_alias=None, case=None):
    case = case or {}
    unit_tolerance = {"TRY":Decimal("0.01"), "quantity":Decimal("0.000001"), "count":Decimal("0")}
    if column.endswith(("_share_pct", "_cumulative_pct")):
        return Decimal("0.000001")
    if column == "__derived" or derived_alias is not None and column == derived_alias:
        spec = case.get("derived") or case.get("comparison") or {}
        if spec.get("op") == "difference":
            left = spec.get("left", spec.get("metric"))
            right = spec.get("right", spec.get("metric"))
            unit = REFERENCE_METRIC_UNITS.get(left)
            if unit and unit == REFERENCE_METRIC_UNITS.get(right):
                return unit_tolerance[unit]
        return Decimal("0.000001")
    if column in {"base_value", "target_value"} and case.get("comparison"):
        return unit_tolerance.get(REFERENCE_METRIC_UNITS.get(case["comparison"]["metric"]), Decimal("0.000001"))
    if column.endswith("_group_total"):
        contributions = [op for op in case.get("analytics",[]) if op["op"] == "contribution"]
        if len(contributions) == 1:
            return unit_tolerance.get(REFERENCE_METRIC_UNITS.get(contributions[0]["metric"]), Decimal("0.000001"))
    if column in REFERENCE_METRIC_UNITS:
        return unit_tolerance[REFERENCE_METRIC_UNITS[column]]
    return Decimal("0") if column in EXACT_COUNT_COLUMNS else Decimal("0.01")


def references_equal(case, before, after):
    """Ignore float serialization noise, never hide row/key/column/NULL changes.

    Uses the same per-column numeric tolerance as the API comparison. Matching
    bracketing reads is a stability check, not a database snapshot guarantee.
    """
    if case.get("sections"):
        return all(references_equal(child, a, b) for child,a,b in zip(case["sections"], before["sections"], after["sections"]))
    if len(before) != len(after):
        return False
    def indexed(rows):
        result = {}
        for row in rows:
            if any(key not in row for key in case["keys"]):
                raise ValueError("Missing reference identity column")
            identity = tuple(row[key] for key in case["keys"])
            if identity in result:
                raise ValueError("Duplicate reference row identity")
            result[identity] = row
        return result
    left, right = indexed(before), indexed(after)
    if set(left) != set(right):
        return False
    for identity, first in left.items():
        second = right[identity]
        if set(first) != set(second):
            return False
        for column, a in first.items():
            b = second[column]
            if a is None or b is None:
                if a is not b:
                    return False
            elif isinstance(a, bool) or isinstance(b, bool):
                if type(a) is not bool or type(b) is not bool or a is not b:
                    return False
            elif isinstance(a, (Decimal, int, float)) and isinstance(b, (Decimal, int, float)):
                av, bv = Decimal(str(a)), Decimal(str(b))
                if not av.is_finite() or not bv.is_finite():
                    return False
                if abs(av - bv) > numeric_tolerance(column, case=case):
                    return False
            elif type(a) is not type(b) or a != b:
                return False
    return True


def data_dependent_error(message):
    # Only discrepancies that changing source rows/values can explain may be
    # demoted to UNVERIFIED. Capability, plan, schema and result-delivery failures
    # remain FAIL even if the surrounding live reference also changed.
    if message.startswith("Section[") and "]: " in message:
        return data_dependent_error(message.split("]: ", 1)[1])
    return message.startswith(("Numeric mismatch:", "NULL mismatch:", "Value mismatch:",
                               "Row count ", "Row identity set differs"))


# Independent algebraic identities, never learned from model output or values.
# Same raw sales-line population: positive sales (7/8/9) minus returns (2/3).
DERIVED_BASE_EQUIVALENCES = {
    ("difference", "sales_amount", "return_amount", 1): "net_sales",
}


def equivalent_base_metric(case, plan, specification):
    key = tuple(specification.get(k) for k in ("op", "left", "right", "scale"))
    metric = DERIVED_BASE_EQUIVALENCES.get(key)
    if not metric or case.get("source") != "logo":
        return None
    required = {specification["left"], specification["right"], metric}
    metrics = plan.get("metrics", [])
    expected_dimensions = case.get("dimensions", case.get("keys", []))
    if len(metrics) != len(required) or set(metrics) != required:
        return None
    if plan.get("sale_kind") != "all" or plan.get("filters") != [] or case.get("filters"):
        return None
    if plan.get("dimensions") != expected_dimensions or plan.get("periods") != case.get("periods"):
        return None
    if any(plan.get(k) for k in ("derived", "comparison", "having", "analytics", "crm", "crm_report", "logo_report", "sections", "gaps", "coverage")):
        return None
    if plan.get("limit") is not None or case.get("limit") or case.get("having") or case.get("analytics") or case.get("comparison"):
        return None
    return metric


def compare(case,answer,whole,expected):
    case.pop("acceptedEquivalence", None)
    errors=[]
    if answer.get("type") not in ({"TEXT_TO_SQL","PARTIAL_ANSWER"} if case.get("allowCoverageGap") else {"TEXT_TO_SQL"}):return ["Expected full answer, received "+str(answer.get("type"))+": "+str(answer.get("explanation",""))[:350]]
    if answer.get("type")=="PARTIAL_ANSWER" and not answer.get("dataNotes"):
        errors.append("Partial answer must disclose source coverage gaps")
    rid=answer.get("resultId")
    if not rid or whole.get("id")!=rid:errors.append("Stored full result identity differs from same execution")
    actual=whole.get("records")
    if not isinstance(actual,list):return errors+["Full result records missing"]
    if whole.get("truncated") is not False:errors.append("Full result truncation status not false")
    if whole.get("totalRows")!=len(actual) or answer.get("rowCount")!=len(actual):errors.append("Row metadata mismatch")
    preview=answer.get("records",[])
    if preview!=actual[:len(preview)] or answer.get("shownRows")!=len(preview):errors.append("Preview differs from stored execution")
    columns=list(case["columns"])
    plan=answer.get("semantic",{}).get("plan",{})
    if case.get("sections"):
        return errors + compare_sections(case, answer, whole, expected)
    if case["source"] in {"logo","cross_dimensions"} and plan.get("periods")!=case["periods"]:
        errors.append("Resolved time coverage differs from independently fixed periods")
    if case.get("crossDimension"):
        if plan.get("dimensions")!=case["dimensions"] or plan.get("metrics")!=case["metrics"]:
            errors.append("Identity dimension or metric differs from independent specification")
        if plan.get("gaps") or plan.get("filters") or plan.get("limit") or plan.get("sections"):
            errors.append("Cross dimension request was narrowed or partially omitted by planner")
    alias=None
    spec=case.get("derived")
    if spec:
        matches=[d for d in plan.get("derived",[]) if all(d.get(k)==v for k,v in spec.items())]
        if len(matches)==1:
            alias=matches[0].get("id")
        else:
            alias=equivalent_base_metric(case,plan,spec)
            if alias is None:return errors+["Derived operation/operands/scale differ from independent specification"]
            case["acceptedEquivalence"]={"operation":dict(spec),"baseMetric":alias,
                "reason":"Independent identity on identical unfiltered all-sales line population; full result values still compared with raw-reference subtraction."}
        columns.append(alias)
    if case.get("comparison"):
        spec=case["comparison"]; found=plan.get("comparison") or {}
        if not all(found.get(k)==v for k,v in spec.items()) or plan.get("periods")!=case["periods"]:
            return errors+["Comparison operands/period direction differ from independent specification"]
        alias=found.get("id")
        columns=case["keys"]+["base_period_start","base_period_end_exclusive","target_period_start","target_period_end_exclusive","base_value","target_value",alias]
    if alias:
        expected=[{(alias if k=="__derived" else k):v for k,v in row.items()} for row in expected]
    if case.get("analytics"):
        found=plan.get("analytics",[])
        if len(found)!=len(case["analytics"]):return errors+["Analytic operation count differs from independent specification"]
        mapping={}
        for actual_op, required in zip(found,case["analytics"]):
            if not all(actual_op.get(k)==v for k,v in required.items()):
                return errors+["Analytic operation/metric/group/limit differs from independent specification"]
            if required["op"]=="contribution":
                for suffix in ("_group_total","_share_pct","_cumulative_pct"):
                    mapping["__contribution"+suffix]=actual_op["id"]+suffix
        columns=[mapping.get(k,k) for k in columns]
        expected=[{mapping.get(k,k):v for k,v in row.items()} for row in expected]
    if set(c.get("name") for c in whole.get("columns",[]))!=set(columns):errors.append("Column identity mismatch")
    if len(actual)!=len(expected):errors.append(f"Row count {len(actual)} != {len(expected)}")
    def indexed(rows):
        result={}
        for row in rows:
            key=tuple(row.get(k) for k in case["keys"])
            if key in result:raise ValueError("Duplicate row identity")
            result[key]=row
        return result
    try:
        a,b=indexed(actual),indexed(expected)
        if set(a)!=set(b):errors.append("Row identity set differs")
        for key in set(a)&set(b):
            if set(a[key])!=set(columns):errors.append("Record column set differs")
            for col in columns:
                av,bv=a[key].get(col),b[key].get(col)
                if av is None or bv is None:
                    if av!=bv:errors.append(f"NULL mismatch: {col}")
                elif isinstance(av,bool) or isinstance(bv,bool):
                    if type(av) is not bool or type(bv) is not bool or av is not bv:
                        errors.append(f"Value mismatch: {col} (boolean)")
                elif isinstance(bv,(Decimal,int,float)):
                    tolerance=numeric_tolerance(col, alias, case)
                    if abs(Decimal(str(av))-Decimal(str(bv)))>tolerance:errors.append(f"Numeric mismatch: {col}")
                elif av!=bv:errors.append(f"Value mismatch: {col}")
    except Exception as exc:errors.append(str(exc))
    return errors[:20]


def compare_sections(case,answer,whole,expected):
    errors=[]
    actual=whole.get("sections",[])
    plans=answer.get("semantic",{}).get("plan",{}).get("sections",[])
    if len(actual)!=len(case["sections"]) or len(plans)!=len(actual):
        return ["Section count differs from independent specification"]
    if whole.get("gaps") or answer.get("gaps"):
        errors.append("Unexpected partial gaps in fully specified section report")
    if {c.get("name") for c in whole.get("columns",[])} != set(case["columns"]):
        errors.append("Section overview column identity mismatch")
    overview=whole.get("records",[])
    if len(overview)!=len(actual) or any(row.get("section")!=section.get("title") or row.get("status")!=section.get("status") or row.get("row_count")!=section.get("totalRows") for row,section in zip(overview,actual)):
        errors.append("Section overview differs from its stored datasets")
    if answer.get("sections")!=actual:
        errors.append("Preview section datasets differ from stored execution")
    used=set()
    for expected_index, child in enumerate(case["sections"]):
        matches=[i for i,p in enumerate(plans) if set(p.get("metrics",[]))==set(child["metrics"]) and p.get("dimensions")==child["dimensions"]]
        if len(matches)!=1 or matches[0] in used:
            errors.append(f"Section[{expected_index}]: Unique independent metric/grain section not found")
            continue
        index=matches[0];used.add(index);dataset=actual[index]
        if dataset.get("status")!="COMPLETE":
            errors.append(f"Section[{expected_index}]: Expected COMPLETE, received {dataset.get('status')}")
        if not dataset.get("definitions"):
            errors.append(f"Section[{expected_index}]: Calculation definitions missing")
        if dataset.get("sourceComplete") is not True:
            errors.append(f"Section[{expected_index}]: Complete source coverage not declared")
        # Reuse strict cell/column comparison, without inventing a second execution.
        child_answer={"type":"TEXT_TO_SQL","resultId":answer["resultId"],"rowCount":dataset.get("totalRows"),
                      "records":dataset.get("records",[]),"shownRows":len(dataset.get("records",[])),
                      "semantic":{"plan":plans[index]}}
        child_whole={**dataset,"id":answer["resultId"]}
        errors.extend(f"Section[{expected_index}]: "+e for e in compare(child,child_answer,child_whole,expected["sections"][expected_index]))
    return errors


def manifest():
    files=list((ROOT/"semantic_bridge/finance_query").glob("*.py"))
    files += [ROOT/p for p in ("semantic_bridge/app.py","semantic_bridge/runtime.py","semantic_layer/profiler/connectors.py","semantic_layer/profiler/connection_pool.py","semantic_layer/runtime/crm_active.py")]
    return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files) if p.is_file()}


def save(path,value):path.write_text(json.dumps(value,ensure_ascii=False,default=str,indent=2))


def main():
    p=argparse.ArgumentParser();p.add_argument("--out",required=True);p.add_argument("--only",default="");p.add_argument("--base",default="http://127.0.0.1:8795");p.add_argument("--reference-date",default=REFERENCE_DATE);args=p.parse_args()
    if sys.platform!="linux" or not ROOT.is_dir() or not Path("/proc").is_dir():raise SystemExit("Remote test-server execution only; local runs prohibited")
    if not args.base.startswith("http://127.0.0.1:"):raise SystemExit("Use the connected test server's loopback API")
    require_reference_day(args.reference_date)
    os.umask(0o077)
    lock=open("/tmp/finance-composable-live.lock","a")
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:raise SystemExit("Another acceptance run is active")
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    if (out/"report.json").exists():raise SystemExit("Use a fresh evidence directory")
    selected=[c for c in cases(args.reference_date) if not args.only or c["id"] in args.only.split(",")]
    if not selected:raise SystemExit("No cases selected")
    session=None;digest=None;conns={};results=[];counts=Counter();threads={};before=manifest();removed=0
    cross_counts=Counter();crosschecks=None;product_cases={}
    def product_case(cid):
        if "map" not in product_cases:
            try:product_cases["map"]={c["id"]:c for c in cases(args.reference_date,variant="product")}
            except Exception as exc:product_cases["map"]={};product_cases["error"]=type(exc).__name__+": "+str(exc)[:300]
        return product_cases["map"].get(cid)
    def interrupt(signum,frame):raise KeyboardInterrupt(f"Signal {signum}")
    signal.signal(signal.SIGTERM,interrupt)
    try:
        env=environment("nanobase-semantic-bridge");login=environment("timas-login")
        if env.get("FINANCE_QUERY_MODE")!="contract":raise RuntimeError("Contract engine is not active")
        session=sqlite3.connect(login.get("SESSION_DB","/var/lib/timas-login/sessions.sqlite"))
        token=secrets.token_urlsafe(32);digest=hashlib.sha256(token.encode()).hexdigest()
        session.execute("INSERT INTO sessions(token,username,expires) VALUES(?,?,?)",(digest,"timasai",time.time()+900));session.commit()
        headers={"Content-Type":"application/json","X-Semantic-Caller":env.get("SEMANTIC_CALLER_TOKEN",""),"Cookie":("__Secure-timas_session" if login.get("COOKIE_SECURE","1")!="0" else "timas_session")+"="+token}
        def call(path,body=None):
            require_reference_day(args.reference_date)
            req=urllib.request.Request(args.base+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
            with urllib.request.urlopen(req,timeout=180) as response:result=json.load(response)
            require_reference_day(args.reference_date)
            return result
        sources={c["source"] for c in selected}
        cross_dimensions="cross_dimensions" in sources
        if cross_dimensions:sources=(sources-{"cross_dimensions"})|{"logo","crm"}
        for source in sources:conns[source]=connect(f"/data/nanobaseai/bi/secrets/{source}-mssql-connection.json")
        if cross_dimensions:conns["cross_dimensions"]={"logo":conns["logo"],"crm":conns["crm"]}
        crosschecks=ir.CrossChecks(query,conns["logo"]) if "logo" in conns else None
        for case in selected:
            if manifest()!=before:
                raise RuntimeError("Deployed code changed; acceptance stopped before another question")
            item={**case,"started":time.time(),"referenceDate":args.reference_date};stop=False
            retry_offset=len(REFERENCE_RETRIES)
            try:
                require_reference_day(args.reference_date)
                if case.get("followup") and case["thread"] not in threads:raise RuntimeError("Follow-up prerequisite did not produce a conversation")
                session.execute("UPDATE sessions SET expires=? WHERE token=?",(time.time()+900,digest));session.commit()
                REFERENCE_CONTEXT.clear();REFERENCE_CONTEXT.update(caseId=case["id"],source=case["source"],phase="before_api")
                expected=reference(case,conns[case["source"]]);item["reference"]=expected
                body={"question":case["question"],"sampleSize":7}
                if case.get("thread") in threads:body["threadId"]=threads[case["thread"]]
                answer=call("/api/v1/ask",body);item["answer"]=answer
                if case.get("thread") and answer.get("threadId"):threads[case["thread"]]=answer["threadId"]
                whole=call("/api/v1/result/"+answer["resultId"]) if answer.get("resultId") else answer;item["fullResult"]=whole
                errors=compare(case,answer,whole,expected)
                if case.get("acceptedEquivalence"):item["acceptedEquivalence"]=case["acceptedEquivalence"]
                if answer.get("semantic",{}).get("engine")!="finance_contract_v1":errors.append("Wrong engine/source routing")
                expected_hash=hashlib.sha256(json.dumps({k.rsplit('/',1)[-1]:v for k,v in before.items() if '/finance_query/' in k},sort_keys=True).encode()).hexdigest()
                if answer.get("semantic",{}).get("engineCodeHash")!=expected_hash:errors.append("Loaded engine hash differs from deployed files")
                item["errors"]=errors;item["status"]="FAIL" if errors else "PARTIAL_REFERENCE_MATCH" if answer.get("type")=="PARTIAL_ANSWER" else "PASS"
                # TANIM_FARKI: karar referansı tutmuyor ama ürünün bugünkü tanımıyla kurulan referans tutuyor.
                if errors and not [error for error in errors if not data_dependent_error(error)]:
                    variant_case=product_case(case["id"])
                    if variant_case is not None:
                        REFERENCE_CONTEXT["phase"]="product_variant"
                        product_ref=reference(variant_case,conns[case["source"]]);item["productVariantReference"]=product_ref
                        product_errors=compare(dict(variant_case),answer,whole,product_ref);item["productVariantErrors"]=product_errors
                        if ir.classify(errors,product_errors)=="TANIM_FARKI":item["status"]="TANIM_FARKI"
                if crosschecks is not None and case["source"] in ("logo","cross_dimensions"):
                    REFERENCE_CONTEXT["phase"]="second_path"
                    item["referenceCrossCheck"]=cross_check_case(crosschecks,case)
                    if not item["referenceCrossCheck"]["reconciled"]:cross_counts["REFERANS_UZLASMADI"]+=1
                    else:cross_counts["REFERANS_UZLASTI"]+=1
                # If live source changed between reference and API, do not claim a mismatch or pass.
                REFERENCE_CONTEXT["phase"]="after_api"
                after_ref=reference(case,conns[case["source"]]);item["referenceAfter"]=after_ref
                if not references_equal(case,expected,after_ref):
                    item["referenceChanged"]=True
                    structural=[error for error in errors if not data_dependent_error(error)]
                    item["status"]="FAIL" if structural else "UNVERIFIED"
                    if structural:item["structuralErrorsDespiteSourceChange"]=structural
                require_reference_day(args.reference_date)
            except Exception as exc:
                structural=[error for error in item.get("errors",[]) if not data_dependent_error(error)]
                item["status"]="FAIL" if structural else "UNVERIFIED"
                item["error"]=type(exc).__name__+": "+str(exc)[:500]
                if structural:item["structuralErrorsDespiteReferenceFailure"]=structural
                stop=isinstance(exc,(TimeoutError,urllib.error.URLError,ReferenceDateChanged))
                if isinstance(exc,ReferenceDateChanged):item["referenceDayChanged"]=True
            item["referenceRetries"]=REFERENCE_RETRIES[retry_offset:]
            item["elapsedSeconds"]=round(time.time()-item["started"],2)
            save(out/(case["id"]+".json"),item);counts[item["status"]]+=1
            results.append({k:item[k] for k in ("id","status","errors","error","elapsedSeconds") if k in item})
            if "referenceCrossCheck" in item:results[-1]["referenceReconciled"]=item["referenceCrossCheck"]["reconciled"]
            print(json.dumps(results[-1],ensure_ascii=False),flush=True)
            if len(results)%10==0:print("BATCH",len(results),dict(counts),flush=True)
            if stop:print("STOP: reference day changed or API unavailable; preserve evidence and do not duplicate workload",flush=True);break
    except BaseException as exc:
        counts["UNVERIFIED"]+=1;results.append(dict(id="ENVIRONMENT",status="UNVERIFIED",error=type(exc).__name__+": "+str(exc)[:500]))
    finally:
        for conn in (value for value in conns.values() if not isinstance(value,dict)):
            try:conn.close()
            except Exception:pass
        if session is not None:
            try:
                if digest:removed=session.execute("DELETE FROM sessions WHERE token=?",(digest,)).rowcount;session.commit()
            except Exception as exc:
                counts["UNVERIFIED"]+=1;results.append(dict(id="SESSION_CLEANUP",status="UNVERIFIED",error=type(exc).__name__+": "+str(exc)[:300]))
            finally:session.close()
        after=manifest()
        if before!=after:counts["UNVERIFIED"]+=1;results.append(dict(id="CODE_CHANGED",status="UNVERIFIED"))
        report=dict(referenceDate=args.reference_date,api=args.base,executionEnvironment="connected test server",counts=dict(counts),results=results,
                    referenceIndependence=dict(sources=ir.SOURCES,crossCheckCounts=dict(cross_counts),
                        crossChecks=ir.jsonable(list(crosschecks.cache.values())) if crosschecks else [],
                        productVariantError=product_cases.get("error"),
                        definitionDifferenceCases=[r["id"] for r in results if r.get("status")=="TANIM_FARKI"],
                        note="TANIM_FARKI ve REFERANS_UZLASMADI PASS/FAIL'e karışmaz; ayrı sayılır."),planned=len(selected),completed=len([r for r in results if r["id"].startswith("CP")]),sessionsDeleted=removed,sourceWrites=0,codeBefore=before,codeAfter=after,codeStable=before==after,runnerSha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),referenceRetries=REFERENCE_RETRIES,referenceRetryIsProductRecoveryEvidence=False)
        save(out/"report.json",report);print("FINAL",dict(counts),"sessionsDeleted",removed,flush=True)
        fcntl.flock(lock,fcntl.LOCK_UN);lock.close()
    if counts["FAIL"] or counts["UNVERIFIED"] or report["completed"]!=len(selected):return 1
    return 2 if counts["TANIM_FARKI"] or cross_counts["REFERANS_UZLASMADI"] else 0


def case_metrics(case):
    known=set(ir.LOGO_MEASURES)|set(ir.HEADER_MEASURES)
    found=list(case.get("metrics") or [])+[c for c in case.get("columns",[]) if c in known]
    for child in case.get("sections") or []:found+=case_metrics(child)
    return [m for m in dict.fromkeys(found) if m in known]


def cross_check_case(crosschecks,case):
    """Vakanın dönemleri için ikinci yol (V_SatisRaporu_411 + fatura başlığı) uzlaşma özeti."""
    periods=list(case.get("periods") or [])
    for child in case.get("sections") or []:periods+=child.get("periods") or []
    dimension="channel" if "channel" in (case.get("keys") or []) else None
    checks=[c for a,b in dict.fromkeys(tuple(p) for p in periods) for c in crosschecks.check("411",a,b,dimension)]
    return ir.jsonable(ir.CrossChecks.summary(checks,case_metrics(case)))


if __name__=="__main__":raise SystemExit(main())
