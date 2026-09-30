"""Remote-only composable finance acceptance; independent SQL, real API, no engine imports.

Run on the test server, never locally. All source queries are read-only. The only
write is a short-lived session for the existing timasai account, deleted in finally.
Derived output aliases may come from the plan, but their operations and operands
must match the independently specified case before any alias is accepted.
"""
import argparse
from collections import Counter
from datetime import datetime
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

REFERENCE_DATE = "2026-09-30"
REFERENCE_RETRIES = []
REFERENCE_CONTEXT = {}
EXACT_COUNT_COLUMNS = frozenset({"sold_quantity", "net_quantity", "invoice_count", "record_count",
                                 "missing_isbn", "missing_book_code", "missing_author"})
ROOT = Path("/data/nanobaseai/bi/frontend/backend")
ST = "dbo.LG_411_01_STLINE S"
MEASURES = {
    "sales_amount": "SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.LINENET ELSE 0 END)",
    "return_amount": "SUM(CASE WHEN S.TRCODE IN (2,3) THEN S.LINENET ELSE 0 END)",
    "net_sales": "SUM(CASE WHEN S.TRCODE IN (2,3) THEN -S.LINENET ELSE S.LINENET END)",
    "sold_quantity": "SUM(CASE WHEN S.TRCODE IN (7,8) THEN S.AMOUNT ELSE 0 END)",
    "net_quantity": "SUM(CASE WHEN S.TRCODE IN (2,3) THEN -S.AMOUNT WHEN S.TRCODE IN (7,8) THEN S.AMOUNT ELSE 0 END)",
}
DIMENSIONS = {
    "channel": ("C.SPECODE2", "LEFT JOIN dbo.LG_411_CLCARD C ON C.LOGICALREF=S.CLIENTREF"),
    "day": ("CONVERT(varchar(10),S.DATE_,23)", ""),
    "month": ("CONVERT(varchar(7),S.DATE_,23)", ""),
}


def sales_sql(start, end, metrics, dimension=None, having=None, limit=None):
    # This reference builder has its own tiny, fixed allowlist. Never accepts AI SQL.
    expression, join = DIMENSIONS[dimension] if dimension else (None, "")
    columns = ([f"{expression} [{dimension}]"] if dimension else [])
    columns += [f"COALESCE({MEASURES[m]},0) [{m}]" for m in metrics]
    sql = "SELECT " + (f"TOP ({limit}) " if limit else "") + ",".join(columns)
    sql += f" FROM {ST} {join} WHERE S.CANCELLED=0 AND S.LINETYPE=0 AND S.INVOICEREF<>0 AND S.TRCODE IN (2,3,7,8,9) AND S.DATE_>='{start}' AND S.DATE_<'{end}'"
    if expression:
        sql += " GROUP BY " + expression
    if having:
        metric, op, threshold = having
        assert op in (">", ">=", "<", "<=")
        sql += f" HAVING {MEASURES[metric]} {op} {Decimal(str(threshold))}"
    if limit:
        sql += f" ORDER BY {MEASURES[metrics[0]]} DESC,{expression} DESC"
    return sql


def cases():
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
    add("Son üç ayın KDV hariç, iadeler düşülmüş net satışını ay ay göster; bugünden üç takvim ayı geriye git, bugün de dahil olsun.",["net_sales"],"month",start="2026-06-30",end="2026-10-01",relative=True)
    add("Bu yılın üçüncü çeyreğinde KDV hariç iade düşülmüş net satış toplamımız ne kadar?",["net_sales"],start="2026-07-01",end="2026-10-01",relative=True)
    add("Son otuz günde KDV hariç iade düşülmüş net satış ve iade tutarını göster; bugün de dahil olsun.",["net_sales","return_amount"],relative=True)
    add("Dünkü KDV hariç net satış ve satılan adet toplamını göster.",["net_sales","sold_quantity"],start="2026-09-29",end="2026-09-30",relative=True)
    add("Eylül 2026'da KDV hariç net satışı en yüksek ilk beş kanalı tutarlarıyla göster.",["net_sales"],"channel",limit=5)
    add("Eylül 2026'da satılan kitap adedi en yüksek ilk on günü adetleriyle göster.",["sold_quantity"],"day",limit=10)
    add("Eylül 2026'da KDV hariç iade tutarı en yüksek ilk üç kanalı listele.",["return_amount"],"channel",limit=3)
    add("Eylül 2026'nın KDV hariç net satış toplamını göster.",["net_sales"],thread="followup1")
    add("Peki aynı dönemin iade tutarı toplamı ne kadar?",["return_amount"],thread="followup1",followup=True)
    add("Bir de aynı dönemde iadeler düşülmeden satılan adet toplamını ver.",["sold_quantity"],thread="followup1",followup=True)
    for question, sql, columns, keys in [
        ("CRM'deki aktif kitaplarda güncel ISBN, stok kodu ve yazar künyesi metni boş olanların sayılarını ayrı ayrı, aktif kitap toplamıyla birlikte göster.", "SELECT COUNT_BIG(*) record_count,SUM(CASE WHEN NULLIF(LTRIM(RTRIM(new_isbn13)),'') IS NULL THEN 1 ELSE 0 END) missing_isbn,SUM(CASE WHEN NULLIF(LTRIM(RTRIM(new_stokkodu)),'') IS NULL THEN 1 ELSE 0 END) missing_book_code,SUM(CASE WHEN NULLIF(LTRIM(RTRIM(new_yazartext)),'') IS NULL THEN 1 ELSE 0 END) missing_author FROM dbo.new_kitapBase WHERE statecode=0 AND statuscode=1", ["record_count","missing_isbn","missing_book_code","missing_author"], []),
        ("CRM'de aynı stok kodunu kullanan birden fazla aktif kitap kaydı var mı? Boş stok kodlarını dahil etme, her kodu kayıt sayısıyla göster.", "SELECT LTRIM(RTRIM(new_stokkodu)) book_code,COUNT_BIG(*) record_count FROM dbo.new_kitapBase WHERE statecode=0 AND statuscode=1 AND NULLIF(LTRIM(RTRIM(new_stokkodu)),'') IS NOT NULL GROUP BY LTRIM(RTRIM(new_stokkodu)) HAVING COUNT_BIG(*)>=2", ["book_code","record_count"],["book_code"]),
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
         "WITH sales AS (SELECT C.CODE customer_code,C.DEFINITION_ customer_name,COALESCE("+MEASURES["net_sales"]+",0) net_sales FROM "+ST+" LEFT JOIN dbo.LG_411_CLCARD C ON C.LOGICALREF=S.CLIENTREF WHERE S.CANCELLED=0 AND S.LINETYPE=0 AND S.INVOICEREF<>0 AND S.TRCODE IN (2,3,7,8,9) AND S.DATE_>='20260901' AND S.DATE_<'20261001' GROUP BY C.CODE,C.DEFINITION_), invoices AS (SELECT C.CODE customer_code,C.DEFINITION_ customer_name,SUM(I.NETTOTAL) invoice_amount FROM dbo.LG_411_01_INVOICE I LEFT JOIN dbo.LG_411_CLCARD C ON C.LOGICALREF=I.CLIENTREF WHERE "+invoice_where+" GROUP BY C.CODE,C.DEFINITION_) SELECT COALESCE(S.customer_code,I.customer_code) customer_code,COALESCE(S.customer_name,I.customer_name) customer_name,COALESCE(S.net_sales,0) net_sales,COALESCE(I.invoice_amount,0) invoice_amount FROM sales S FULL OUTER JOIN invoices I ON (S.customer_code=I.customer_code OR S.customer_code IS NULL AND I.customer_code IS NULL) AND (S.customer_name=I.customer_name OR S.customer_name IS NULL AND I.customer_name IS NULL)",
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
    for case in out:
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


def reference(case,conn):
    if not case.get("comparison"):
        rows=query(conn,case["referenceSql"])
        if case.get("derived"):
            d=case["derived"]
            for row in rows:row["__derived"]=calculate(d["op"],row[d["left"]],row[d["right"]],d["scale"])
        return rows
    spec=case["comparison"]; metric=spec["metric"]; keys=case["keys"]
    pairs=[]
    for start,end in case["periods"]:
        sql=sales_sql(start,end,[metric],keys[0] if keys else None)
        pairs.append({tuple(r[k] for k in keys):r[metric] for r in query(conn,sql)})
    base,target=pairs; rows=[]
    for key in set(base)|set(target):
        a,b=base.get(key),target.get(key)
        rows.append(dict(zip(keys,key),base_period_start=case["periods"][0][0],base_period_end_exclusive=case["periods"][0][1],target_period_start=case["periods"][1][0],target_period_end_exclusive=case["periods"][1][1],base_value=a,target_value=b,__derived=calculate(spec["op"],b,a)))
    return rows


def numeric_tolerance(column, derived_alias=None):
    if column == "__derived" or derived_alias is not None and column == derived_alias:
        return Decimal("0.000001")
    return Decimal("0") if column in EXACT_COUNT_COLUMNS else Decimal("0.01")


def references_equal(case, before, after):
    """Ignore float serialization noise, never hide row/key/column/NULL changes.

    Uses the same per-column numeric tolerance as the API comparison. Matching
    bracketing reads is a stability check, not a database snapshot guarantee.
    """
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
            elif isinstance(a, (Decimal, int, float)) and isinstance(b, (Decimal, int, float)):
                av, bv = Decimal(str(a)), Decimal(str(b))
                if not av.is_finite() or not bv.is_finite():
                    return False
                if abs(av - bv) > numeric_tolerance(column):
                    return False
            elif type(a) is not type(b) or a != b:
                return False
    return True


def data_dependent_error(message):
    # Only discrepancies that changing source rows/values can explain may be
    # demoted to UNVERIFIED. Capability, plan, schema and result-delivery failures
    # remain FAIL even if the surrounding live reference also changed.
    return message.startswith(("Numeric mismatch:", "NULL mismatch:", "Value mismatch:",
                               "Row count ", "Row identity set differs"))


def compare(case,answer,whole,expected):
    errors=[]
    if answer.get("type")!="TEXT_TO_SQL":return ["Expected full answer, received "+str(answer.get("type"))+": "+str(answer.get("explanation",""))[:350]]
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
    if case["source"]=="logo" and plan.get("periods")!=case["periods"]:
        errors.append("Resolved time coverage differs from independently fixed periods")
    alias=None
    spec=case.get("derived")
    if spec:
        matches=[d for d in plan.get("derived",[]) if all(d.get(k)==v for k,v in spec.items())]
        if len(matches)!=1:return errors+["Derived operation/operands/scale differ from independent specification"]
        alias=matches[0].get("id");columns.append(alias)
    if case.get("comparison"):
        spec=case["comparison"]; found=plan.get("comparison") or {}
        if not all(found.get(k)==v for k,v in spec.items()) or plan.get("periods")!=case["periods"]:
            return errors+["Comparison operands/period direction differ from independent specification"]
        alias=found.get("id")
        columns=case["keys"]+["base_period_start","base_period_end_exclusive","target_period_start","target_period_end_exclusive","base_value","target_value",alias]
    if alias:
        expected=[{(alias if k=="__derived" else k):v for k,v in row.items()} for row in expected]
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
                elif isinstance(bv,(Decimal,int,float)):
                    tolerance=numeric_tolerance(col, alias)
                    if abs(Decimal(str(av))-Decimal(str(bv)))>tolerance:errors.append(f"Numeric mismatch: {col}")
                elif av!=bv:errors.append(f"Value mismatch: {col}")
    except Exception as exc:errors.append(str(exc))
    return errors[:20]


def manifest():
    files=list((ROOT/"semantic_bridge/finance_query").glob("*.py"))
    files += [ROOT/p for p in ("semantic_bridge/app.py","semantic_bridge/runtime.py","semantic_layer/profiler/connectors.py","semantic_layer/profiler/connection_pool.py","semantic_layer/runtime/crm_active.py")]
    return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files) if p.is_file()}


def save(path,value):path.write_text(json.dumps(value,ensure_ascii=False,default=str,indent=2))


def main():
    p=argparse.ArgumentParser();p.add_argument("--out",required=True);p.add_argument("--only",default="");p.add_argument("--base",default="http://127.0.0.1:8795");args=p.parse_args()
    if sys.platform!="linux" or not ROOT.is_dir() or not Path("/proc").is_dir():raise SystemExit("Remote test-server execution only; local runs prohibited")
    if not args.base.startswith("http://127.0.0.1:"):raise SystemExit("Use the connected test server's loopback API")
    os.umask(0o077)
    lock=open("/tmp/finance-composable-live.lock","a")
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:raise SystemExit("Another acceptance run is active")
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    if (out/"report.json").exists():raise SystemExit("Use a fresh evidence directory")
    selected=[c for c in cases() if not args.only or c["id"] in args.only.split(",")]
    if not selected:raise SystemExit("No cases selected")
    if any(c.get("relative") for c in selected) and str(datetime.now(ZoneInfo("Europe/Istanbul")).date())!=REFERENCE_DATE:
        raise SystemExit("Natural-date cases require 2026-09-30; do not silently shift acceptance dates")
    session=None;digest=None;conns={};results=[];counts=Counter();threads={};before=manifest();removed=0
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
            req=urllib.request.Request(args.base+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
            with urllib.request.urlopen(req,timeout=180) as response:return json.load(response)
        for source in {c["source"] for c in selected}:conns[source]=connect(f"/data/nanobaseai/bi/secrets/{source}-mssql-connection.json")
        for case in selected:
            item={**case,"started":time.time()};stop=False
            retry_offset=len(REFERENCE_RETRIES)
            try:
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
                if answer.get("semantic",{}).get("engine")!="finance_contract_v1":errors.append("Wrong engine/source routing")
                expected_hash=hashlib.sha256(json.dumps({k.rsplit('/',1)[-1]:v for k,v in before.items() if '/finance_query/' in k},sort_keys=True).encode()).hexdigest()
                if answer.get("semantic",{}).get("engineCodeHash")!=expected_hash:errors.append("Loaded engine hash differs from deployed files")
                item["errors"]=errors;item["status"]="FAIL" if errors else "PASS"
                # If live source changed between reference and API, do not claim a mismatch or pass.
                REFERENCE_CONTEXT["phase"]="after_api"
                after_ref=reference(case,conns[case["source"]]);item["referenceAfter"]=after_ref
                if not references_equal(case,expected,after_ref):
                    item["referenceChanged"]=True
                    structural=[error for error in errors if not data_dependent_error(error)]
                    item["status"]="FAIL" if structural else "UNVERIFIED"
                    if structural:item["structuralErrorsDespiteSourceChange"]=structural
            except Exception as exc:
                structural=[error for error in item.get("errors",[]) if not data_dependent_error(error)]
                item["status"]="FAIL" if structural else "UNVERIFIED"
                item["error"]=type(exc).__name__+": "+str(exc)[:500]
                if structural:item["structuralErrorsDespiteReferenceFailure"]=structural
                stop=isinstance(exc,TimeoutError) or isinstance(exc,urllib.error.URLError) and isinstance(exc.reason,TimeoutError)
            item["referenceRetries"]=REFERENCE_RETRIES[retry_offset:]
            item["elapsedSeconds"]=round(time.time()-item["started"],2)
            save(out/(case["id"]+".json"),item);counts[item["status"]]+=1
            results.append({k:item[k] for k in ("id","status","errors","error","elapsedSeconds") if k in item})
            print(json.dumps(results[-1],ensure_ascii=False),flush=True)
            if len(results)%10==0:print("BATCH",len(results),dict(counts),flush=True)
            if stop:print("STOP: request may still run; do not duplicate workload",flush=True);break
    except BaseException as exc:
        counts["UNVERIFIED"]+=1;results.append(dict(id="ENVIRONMENT",status="UNVERIFIED",error=type(exc).__name__+": "+str(exc)[:500]))
    finally:
        for conn in conns.values():
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
        report=dict(referenceDate=REFERENCE_DATE,api=args.base,executionEnvironment="connected test server",counts=dict(counts),results=results,planned=len(selected),completed=len([r for r in results if r["id"].startswith("CP")]),sessionsDeleted=removed,sourceWrites=0,codeBefore=before,codeAfter=after,codeStable=before==after,runnerSha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),referenceRetries=REFERENCE_RETRIES,referenceRetryIsProductRecoveryEvidence=False)
        save(out/"report.json",report);print("FINAL",dict(counts),"sessionsDeleted",removed,flush=True)
        fcntl.flock(lock,fcntl.LOCK_UN);lock.close()
    return 1 if counts["FAIL"] or counts["UNVERIFIED"] or report["completed"]!=len(selected) else 0


if __name__=="__main__":raise SystemExit(main())
