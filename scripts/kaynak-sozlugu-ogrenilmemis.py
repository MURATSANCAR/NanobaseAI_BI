"""Logo ve CRM'de verisi dolu ama bizim öğrenmediğimiz tablo ve kolonlar (2026-10-02).

Öğrenilmiş = kaynak sözlüğünde anlamı yazılı (Logo kolon_sozlugu) ya da ürün kodunda, o tabloyu anan
bir dosyada adı geçiyor. Öğrenilmemiş = canlı veride dolu ama ikisi de değil.
Yalnız SELECT; WITH (NOLOCK); tablo başına tek toplulaştırılmış sorgu; ham satır okunmaz.
"""
import json, re, sys, time
sys.path.insert(0, "/data/nanobaseai/bi/frontend/backend")
from semantic_layer.profiler.connectors import connector_from_file

OUT = "/tmp/ogrenilmemis"
import os
os.makedirs(OUT, exist_ok=True)
code_tok = set(json.load(open("/tmp/kod_tokenlari.json")))
fam_tok = {k: set(v) for k, v in json.load(open("/tmp/logo_aile_tok.json")).items()}
crm_tok = {k: set(v) for k, v in json.load(open("/tmp/crm_tablo_tok.json")).items()}
learned = {k: {c.lower() for c in v} for k, v in json.load(open("/tmp/logo_ogrenilen.json")).items()}
ldds = json.load(open("/tmp/logo-ldds.json"))["tables"]
ldds_by_fam = {}
for k, t in ldds.items():
    fam = re.sub(r"^LG_(XXX_)?(XX_)?", "", t.get("physical") or k).upper()
    ldds_by_fam[fam] = t


def run(conn, sql):
    return conn.execute(sql, 1000000)[1]


def fill_expr(col, typ):
    q = f"[{col}]"
    if typ in ("int", "smallint", "tinyint", "bigint", "float", "real", "decimal", "numeric", "money", "smallmoney"):
        return f"SUM(CASE WHEN {q}<>0 THEN 1 ELSE 0 END)"
    if typ == "bit":
        return f"SUM(CASE WHEN {q}=1 THEN 1 ELSE 0 END)"
    if typ in ("datetime", "smalldatetime", "date", "datetime2"):
        return f"SUM(CASE WHEN {q}>'1900-01-02' THEN 1 ELSE 0 END)"
    if typ in ("varchar", "nvarchar", "char", "nchar"):
        return f"SUM(CASE WHEN LEN(LTRIM(RTRIM({q})))>0 THEN 1 ELSE 0 END)"
    if typ in ("uniqueidentifier",):
        return f"COUNT({q})"
    return None  # text/ntext/image/varbinary/xml: doluluk sayılmaz


def measure(conn, schema, table, cols, rows, sample):
    exprs, names = [], []
    for c, t in cols:
        e = fill_expr(c, t)
        if e:
            exprs.append(f"{e} AS [f{len(names)}]"); names.append(c)
    if not exprs:
        return {}, 0
    src = f"[{schema}].[{table}]"
    base = f"(SELECT TOP {sample} * FROM {src} WITH (NOLOCK)) X" if sample else f"{src} X WITH (NOLOCK)"
    out = {}
    n = 0
    # Çok kolonlu tabloyu parçala (SQL Server tek SELECT'te 4096 kolon sınırı ve plan boyu)
    for i in range(0, len(exprs), 300):
        part = exprs[i:i + 300]
        r = run(conn, "SET LOCK_TIMEOUT 20000; SELECT COUNT_BIG(*) AS n, " + ", ".join(part) + f" FROM {base}")[0]
        n = int(r["n"] or 0)
        for j, e in enumerate(part):
            out[names[i + j]] = int(r[f"f{i + j}"] or 0)
    return out, n


def inventory(conn, name_filter):
    return run(conn, f"""SELECT s.name sch, t.name tab, SUM(p.rows) rows
      FROM sys.tables t JOIN sys.schemas s ON s.schema_id=t.schema_id
      JOIN sys.partitions p ON p.object_id=t.object_id AND p.index_id IN (0,1)
      WHERE {name_filter} GROUP BY s.name, t.name""")


def columns(conn, sch, tab):
    return [(r["c"], r["t"]) for r in run(conn, f"""SELECT c.name c, ty.name t FROM sys.columns c
      JOIN sys.types ty ON ty.user_type_id=c.user_type_id
      WHERE c.object_id=OBJECT_ID(N'[{sch}].[{tab}]') ORDER BY c.column_id""")]


log = open(f"{OUT}/log.txt", "a")
def note(*a):
    print(*a, file=log, flush=True)


# ------------------------------------------------------------------ Logo
def logo():
    conn = connector_from_file("/data/nanobaseai/bi/secrets/logo-mssql-connection.json")
    inv = inventory(conn, "(t.name LIKE 'LG[_]411[_]%' OR t.name LIKE 'L[_]%' OR (t.name NOT LIKE 'LG[_]%' AND t.name NOT LIKE 'L[_]%'))")
    res = []
    for r in sorted(inv, key=lambda x: x["tab"]):
        tab, rows = r["tab"], int(r["rows"] or 0)
        m = re.match(r"^LG_411_(?:01_)?(.+)$", tab)
        fam = m.group(1).upper() if m else tab.upper()
        kind = "dönem" if re.match(r"^LG_411_01_", tab) else "firma" if m else "genel" if tab.startswith("L_") else "özel"
        item = {"tablo": tab, "aile": fam, "tur": kind, "satir": rows,
                "ldds": (ldds_by_fam.get(fam) or {}).get("description"),
                "kodda": fam in fam_tok or fam.lower() in code_tok, "sozlukte": fam in learned}
        if rows == 0:
            res.append(item); continue
        cols = columns(conn, r["sch"], tab)
        t0 = time.time()
        try:
            fill, n = measure(conn, r["sch"], tab, cols, rows, 1000000 if rows > 3000000 else 0)
            item["olculen_satir"] = n
        except Exception as e:
            item["hata"] = str(e)[:200]; note("logo", tab, e); res.append(item); continue
        item["sure_sn"] = round(time.time() - t0, 1)
        lt = fam_tok.get(fam, set()); lc = learned.get(fam, set())
        ldcols = (ldds_by_fam.get(fam) or {}).get("columns") or {}
        item["kolonlar"] = []
        for c, t in cols:
            f = fill.get(c)
            if not f:
                continue
            item["kolonlar"].append({"kolon": c, "tur": t, "dolu": f, "oran": round(f / max(n, 1), 4),
                "ogrenildi": c.lower() in lc or c.lower() in lt,
                "ldds": (ldcols.get(c) or {}).get("description_tr") or (ldcols.get(c) or {}).get("description")})
        res.append(item)
        note("logo", tab, rows, item["sure_sn"])
        time.sleep(0.2)
    json.dump(res, open(f"{OUT}/logo.json", "w"), ensure_ascii=False)


# ------------------------------------------------------------------ CRM
def crm():
    conn = connector_from_file("/data/nanobaseai/bi/secrets/crm-mssql-connection.json")
    conn = getattr(conn, "inner", conn)  # ölçüm ham tabloda; pasif süzgeci doluluk sayımını değiştirmesin
    full = json.load(open("/tmp/crm-sozluk.json"))
    ents = full["varliklar"] if isinstance(full, dict) else full
    rows_by = {r["tab"]: int(r["rows"] or 0) for r in inventory(conn, "1=1")}
    res = []
    for e in sorted(ents, key=lambda x: x.get("tablo") or ""):
        tab = e.get("tablo")
        if not tab:
            continue
        rows = rows_by.get(tab, 0)
        sinif = e.get("sinif")
        item = {"tablo": tab, "varlik": e.get("mantiksal_ad"), "ad": e.get("turkce_ad"), "sinif": sinif, "ozel": e.get("ozel"),
                "satir": rows, "kodda": tab in crm_tok}
        if rows == 0 or sinif in ("sistem", "entegrasyon_log"):
            item["olculmedi"] = "boş" if rows == 0 else f"sınıf {sinif}"
            res.append(item); continue
        fields = {}
        for a in e.get("alanlar") or []:
            for t in {a.get("tablo") or tab}:
                fields.setdefault(t, {})[a.get("fiziksel_kolon") or a.get("alan")] = a
        item["kolonlar"] = []
        lt = crm_tok.get(tab, set())
        for t, fmap in fields.items():
            cols = [(c, ty) for c, ty in columns(conn, "dbo", t) if c in fmap]
            t0 = time.time()
            try:
                fill, n = measure(conn, "dbo", t, cols, rows, 300000 if rows > 1000000 else 0)
            except Exception as ex:
                item.setdefault("hata", []).append(f"{t}: {str(ex)[:160]}"); note("crm", t, ex); continue
            item["olculen_satir"] = n
            for c, ty in cols:
                f = fill.get(c)
                if not f:
                    continue
                a = fmap[c]
                item["kolonlar"].append({"kolon": c, "tablo": t, "tur": a.get("tur") or ty, "etiket": a.get("etiket"),
                    "ozel": a.get("ozel"), "dolu": f, "oran": round(f / max(n, 1), 4),
                    "ogrenildi": c.lower() in lt or (a.get("alan") or "").lower() in lt})
            note("crm", t, rows, round(time.time() - t0, 1))
            time.sleep(0.2)
        res.append(item)
    json.dump(res, open(f"{OUT}/crm.json", "w"), ensure_ascii=False)


if __name__ == "__main__":
    which = sys.argv[1]
    (logo if which == "logo" else crm)()
    open(f"{OUT}/{which}.done", "w").write("ok")
