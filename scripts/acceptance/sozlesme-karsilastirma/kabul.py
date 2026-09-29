"""Sözleşme karşılaştırma — test sunucusunda gerçek uç ↔ bağımsız referans kabulü. Yerelde koşulmaz.

Referanslar köprünün hesabını kullanmaz: CRM doğrudan SQL ile (connector_from_file; yüzdelik PERCENTILE_CONT, sayımlar
COUNT), PDF metni bu betikte ayrıca okunur (pypdf), köprü veritabanı doğrudan SQL.

  K1  CRM'deki etkin sözleşme sayısı (COUNT) = ekrandaki «CRM sözleşmesi»; anlaşma sayısı ≤ sözleşme
  K2  tarama: en çok farklı maddesi olan 5 anlaşma; her birinin sözleşme sayfası taramadaki farklı maddelerle aynı
  K3  sayısal farklı madde: emsal grubu (tip/ödeme/para/bölüm, dönem) CRM'de SQL ile yeniden kurulur (anlaşma başına tek
      satır); emsal sayısı, dolu sayısı, «bu değer ya da üstü/altı» sayısı, medyan ve %10/%90 (PERCENTILE_CONT) uçla aynı
  K4  seçim/bayrak farklı madde: aynı değeri taşıyan emsal sayısı SQL sayımıyla aynı
  K5  özgün not: aynı metin (kırpılmış, küçük harf) başka anlaşmada yok (SQL); kalıp not ≥ eşik anlaşmada var
  K6  aynı hak sahibi: taraf tablosundan (SQL) aynı kişi/firmanın öbür sözleşmeleri uçtakiyle aynı küme
  K7  tek ödeme tutarı: sözleşme sayfası (M6) `new_TekdemeTutari`'nı okuyor (düzeltme), 3 tek ödemeli sözleşmede SQL = uç
  K8  belge arşivi: CRM ek sayısı (SQL) = arşivdeki CRM eki; PDF okunur, her maddenin metni betiğin kendi okuduğu PDF
      metninde (katlanmış) geçer
  K9  yüklenen iki Word belgesi: değişen sayı «değişmiş» + sayı farkı, eklenen madde «yalnız bu belgede», aynı madde «aynı»
  K10 arşive karşı: belge sayısı = okunmuş belge − 1
  K11 her cevapta kaynağı yazılmamış rakam yok, SQL'de yer tutucu/sır yok; ekrana giden metinde teknoloji adı yok
  K12 oturumsuz istek 401

Yazma: iki karşılaştırma belgesi (yükleme) ve arşiv okumaları. Hepsi sonunda uçtan silinir, silindiği SQL ile denetlenir.
CRM'e hiçbir şey yazılmaz. Ortam: BASE (yan köprü), COOKIE, SEMANTIC_STORE_DSN, SEMANTIC_CRM_CONNECTION_FILE,
CRM_SCHEMA (varsayılan Timas_MSCRM.dbo), PYTHONPATH=<aday ağaç>/backend.
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import re
import time
import unicodedata
import urllib.error
import urllib.request
import zipfile
from xml.sax.saxutils import escape

import sqlalchemy as sa

BASE = os.environ.get("BASE", "http://127.0.0.1:8801").rstrip("/")
COOKIE = os.environ.get("COOKIE", "")
P = os.environ.get("CRM_SCHEMA", "Timas_MSCRM.dbo").rstrip(".") + "."
B = "/api/v1/editorial/contracts/compare"
TECH = re.compile(r"\b(qwen\w*|vllm|llama|openai|llm|tesseract|timesfm|postgres\w*|sqlite|python|fastapi)\b", re.I)
results: list[tuple[str, bool, str]] = []
t_start = time.time()


def ok(name: str, cond: bool, detail: str = "") -> None:
    results.append((name, bool(cond), detail))
    print(("GEÇTİ " if cond else "KALDI ") + name + (f" — {detail}" if detail else ""), flush=True)


def http(method: str, path: str, body: object = None, *, raw: bytes | None = None, cookie: str | None = None, timeout: int = 300):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(BASE + path, data=data, method=method)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    c = COOKIE if cookie is None else cookie
    if c:
        req.add_header("Cookie", c)
    req.add_header("Origin", "https://portal.nanobase.ai")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"null")
        except ValueError:
            return e.code, None


def crm():
    from semantic_layer.profiler.connectors import connector_from_file

    c = connector_from_file(os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json"))

    def run(sql: str) -> list[dict]:
        cols, rows, trunc = c.execute(sql, 2_000_000)
        assert not trunc
        return rows
    return run


def fold(s: object) -> str:
    t = str(s or "").replace("İ", "i").replace("I", "ı").lower()
    for a, b in (("ı", "i"), ("ş", "s"), ("ğ", "g"), ("ü", "u"), ("ö", "o"), ("ç", "c")):
        t = t.replace(a, b)
    t = unicodedata.normalize("NFKD", t)
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    t = re.sub(r"[^0-9a-z]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def check_provenance(name: str, out: dict) -> None:
    from semantic_bridge import contracts_compare_api as API
    from semantic_bridge import provenance as PV

    un = PV.uncovered_numbers(out, API.NOT_RAKAM)
    pr = PV.problems(out)
    text = json.dumps({k: v for k, v in out.items() if k != "kaynaklar"}, ensure_ascii=False)
    tech = TECH.findall(text)
    ok(f"K11 {name}: sorgu bilgisi ve metin", not un and not pr and not tech, f"kapsanmayan={un[:5]} sorun={pr[:3]} teknoloji={tech[:3]}")


def docx(paragraphs: list[str]) -> bytes:
    body = "".join(f'<w:p><w:r><w:t xml:space="preserve">{escape(p)}</w:t></w:r></w:p>' for p in paragraphs)
    doc = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document '
           'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>' + body + '</w:body></w:document>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                   '<Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" '
                   'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        z.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        z.writestr("word/document.xml", doc)
    return buf.getvalue()


def wait_ready(ref: str, limit: int = 900) -> dict:
    for _ in range(limit):
        st, out = http("GET", B + "/documents")
        d = next((x for x in (out or {}).get("items", []) if x["ref"] == ref), None)
        if d and d["status"] in ("hazir", "hata"):
            return d
        time.sleep(1)
    return d or {}


# ------------------------------------------------------------------ referans SQL


DIMCOL = {"tip": "new_SozlesmeTipi", "odeme": "new_TelifTipi", "para": "new_sozlesmeparabirimi", "bolum": "new_ilgilidepartman"}


def peers_sql(dims: dict, years: tuple | None, own_agreement: str, col: str, per_currency: bool, kind: str = "sayi") -> str:
    """Emsal grubu, anlaşma başına tek satır: anlaşma = ana sözleşme kimliği (süslü parantezsiz) ya da kendi kimliği;
    anlaşmayı ana kayıt temsil eder, etkin değilse numarası en küçük kayıt (uzunluk, sonra metin: «-2» «-10»dan önce).
    Değer: sayıda 0 → boş; bayrakta boş → 0; seçimde boş → -1."""
    key = "LOWER(COALESCE(NULLIF(REPLACE(REPLACE(s.new_anasozlesmeid, '{', ''), '}', ''), ''), CAST(s.new_sozlesmeId AS varchar(40))))"
    w = []
    for d, v in dims.items():
        w.append(f"x.{DIMCOL[d]} = {int(v)}" if v is not None else f"x.{DIMCOL[d]} IS NULL")
    if years:
        w.append(f"x.y BETWEEN {years[0]} AND {years[1]}")
    val = {"sayi": f"CASE WHEN x.{col} <> 0 THEN CAST(x.{col} AS float) END",
           "bayrak": f"CAST(ISNULL(x.{col}, 0) AS float)", "secim": f"CAST(ISNULL(x.{col}, -1) AS float)"}[kind]
    return (f"WITH x AS (SELECT {key} AS k, YEAR(s.new_SozlesmeBaslangicTarihi) AS y, {', '.join('s.' + c for c in sorted(set(DIMCOL.values()) | {col}))},"
            f" ROW_NUMBER() OVER (PARTITION BY {key} ORDER BY CASE WHEN LOWER(CAST(s.new_sozlesmeId AS varchar(40))) = {key} THEN 0 ELSE 1 END,"
            f" LEN(s.new_name), s.new_name) AS rn FROM {P}new_sozlesmeBase s WHERE s.statecode = 0)"
            f" SELECT x.k, {val} AS v FROM x WHERE x.rn = 1 AND x.k <> '{own_agreement}'" + "".join(" AND " + c for c in w))


def pct(vals: list[float], q: float) -> float | None:
    if not vals:
        return None
    vals = sorted(vals)
    pos = q * (len(vals) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(vals) - 1)
    return round(vals[lo] + (vals[hi] - vals[lo]) * (pos - lo), 6)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--sample", type=int, default=5)
    args = ap.parse_args()
    run = crm()
    engine = sa.create_engine(os.environ["SEMANTIC_STORE_DSN"])
    created: list[str] = []

    # K12
    st, _ = http("GET", B + "/meta", cookie="")
    ok("K12 oturumsuz istek", st == 401, f"durum {st}")

    t0 = time.time()
    st, meta = http("GET", B + "/meta", timeout=600)
    ok("meta", st == 200, f"{st} {round(time.time() - t0, 1)} sn (ilk açılışta CRM okunur)")
    check_provenance("meta", meta)

    # CRM görüntüsü yeniden okunur (K1 bugünkü CRM'le karşılaştırılsın; yenile düğmesinin kendisi de sınanır)
    before = meta["gorunum"]["okunduAn"]
    t0 = time.time()
    st, _ = http("POST", B + "/refresh", {})
    for _ in range(600):
        time.sleep(2)
        _, m2 = http("GET", B + "/meta")
        if m2 and not m2["gorunum"]["yenileniyor"] and m2["gorunum"]["okunduAn"] != before:
            break
    ok("CRM'i yeniden oku", st == 200 and m2["gorunum"]["okunduAn"] != before, f"{round(time.time() - t0, 1)} sn, okundu {m2['gorunum']['okunduAn']}")
    t0 = time.time()
    st, scan = http("GET", B + "/scan?only=sapan&page=0")
    ok("tarama", st == 200 and scan["total"] > 0, f"{st} {round(time.time() - t0, 1)} sn, {scan.get('total')} farklı maddeli anlaşma")
    check_provenance("tarama", scan)
    n_active = run(f"SELECT COUNT(*) AS n FROM {P}new_sozlesmeBase WHERE statecode = 0")[0]["n"]
    ok("K1 etkin sözleşme sayısı", scan["ozet"]["sozlesme"] == n_active and scan["ozet"]["anlasma"] <= n_active,
       f"uç {scan['ozet']['sozlesme']} / SQL {n_active}; anlaşma {scan['ozet']['anlasma']}")

    sample = scan["items"][: args.sample]
    checked_num = checked_cat = 0
    for it in sample:
        st, d = http("GET", B + f"/contract/{it['id']}")
        if st != 200:
            ok(f"K2 {it['no']}", False, f"durum {st}")
            continue
        dev_page = {c["key"] for g in d["groups"] for c in g["clauses"] if c["status"] in ("yuksek", "dusuk", "nadir", "nadir-madde", "eksik")}
        dev_scan = {s["key"] for s in it["sapmalar"]}
        ok(f"K2 {it['no']} tarama = sözleşme sayfası", dev_page == dev_scan, f"sayfa {sorted(dev_page)} / tarama {sorted(dev_scan)}")
        check_provenance(f"sözleşme {it['no']}", d)
        crit = d["criteria"]
        dims = {b["id"]: None for b in crit["boyutlar"]}
        # boyut değerleri: konunun kendi CRM satırından
        row = run(f"SELECT {', '.join(f'CAST({c} AS int) AS {k}' for k, c in DIMCOL.items())}, YEAR(new_SozlesmeBaslangicTarihi) AS y,"
                  f" LOWER(COALESCE(NULLIF(REPLACE(REPLACE(new_anasozlesmeid, '{{', ''), '}}', ''), ''), CAST(new_sozlesmeId AS varchar(40)))) AS k"
                  f" FROM {P}new_sozlesmeBase WHERE new_sozlesmeId = '{it['id']}'")[0]
        for k in dims:
            dims[k] = row[k]
        years = None
        if crit["yil"] >= 0 and row["y"] is not None:
            years = (row["y"] - crit["yil"], row["y"])
        for g in d["groups"]:
            for c in g["clauses"]:
                if c["status"] not in ("yuksek", "dusuk", "nadir", "eksik", "nadir-madde"):
                    continue
                if c["kind"] in ("oran", "sayi", "tutar") and isinstance(c["value"], (int, float)) and c["status"] in ("yuksek", "dusuk"):
                    use = dict(dims)
                    per_cur = c["kind"] == "tutar"
                    if per_cur:
                        use["para"] = row["para"]
                    ref = run(peers_sql(use, years, row["k"], c["key"], per_cur))
                    n = len(ref)
                    vals = [r["v"] for r in ref if r["v"] is not None]
                    v = float(c["value"])
                    ge, le = sum(1 for x in vals if x >= v), sum(1 for x in vals if x <= v)
                    same = (n == c["n"] and len(vals) == c["dolu"] and ge == c.get("ustunde") and le == c.get("altinda")
                            and pct(vals, 0.5) == c["medyan"] and pct(vals, 0.1) == c["p10"] and pct(vals, 0.9) == c["p90"])
                    ok(f"K3 {it['no']} {c['label']}", same,
                       f"uç n={c['n']} dolu={c['dolu']} üst={c.get('ustunde')} alt={c.get('altinda')} med={c['medyan']} p10={c['p10']} p90={c['p90']}"
                       f" | SQL n={n} dolu={len(vals)} üst={ge} alt={le} med={pct(vals, .5)} p10={pct(vals, .1)} p90={pct(vals, .9)}")
                    checked_num += 1
                elif c["kind"] in ("secim", "bayrak") and c["status"] == "nadir":
                    ref = run(peers_sql(dims, years, row["k"], c["key"], False, c["kind"]))
                    want = (1.0 if c["value"] else 0.0) if c["kind"] == "bayrak" else (float(c["value"]) if c["value"] is not None else -1.0)
                    same_n = sum(1 for r in ref if r["v"] == want)
                    ok(f"K4 {it['no']} {c['label']}", len(ref) == c["n"] and same_n == c["ayni"],
                       f"uç n={c['n']} aynı={c['ayni']} | SQL n={len(ref)} aynı={same_n}")
                    checked_cat += 1
        for t in d["texts"]:
            col = t["key"]
            exact = run(f"SELECT COUNT(DISTINCT LOWER(COALESCE(NULLIF(REPLACE(REPLACE(s.new_anasozlesmeid, '{{', ''), '}}', ''), ''), CAST(s.new_sozlesmeId AS varchar(40))))) AS n"
                        f" FROM {P}new_sozlesmeBase s WHERE s.statecode = 0 AND LTRIM(RTRIM(LOWER(CAST(s.{col} AS nvarchar(4000))))) = LTRIM(RTRIM(LOWER(N'{t['text'][:3900].replace(chr(39), chr(39) * 2)}')))"
                        f" AND LOWER(COALESCE(NULLIF(REPLACE(REPLACE(s.new_anasozlesmeid, '{{', ''), '}}', ''), ''), CAST(s.new_sozlesmeId AS varchar(40)))) <> '{row['k']}'")[0]["n"]
            if t["status"] == "ozgun":
                ok(f"K5 {it['no']} {t['label']} özgün", exact == 0, f"SQL'de aynı metin {exact} başka anlaşmada")
            elif t["status"] == "kalip":
                ok(f"K5 {it['no']} {t['label']} kalıp", t["toplam"] >= meta["ayarlar"]["kalip"] and t["birebir"] >= exact,
                   f"uç toplam={t['toplam']} birebir={t['birebir']} | SQL birebir (aynı alan) {exact}")
        # K6 aynı hak sahibi
        pids = run(f"SELECT DISTINCT CAST(COALESCE(new_kisi, new_Firma) AS varchar(40)) AS p FROM {P}new_sozlesmetarafiBase"
                   f" WHERE statecode = 0 AND new_sozlesmeid IN (SELECT new_sozlesmeId FROM {P}new_sozlesmeBase WHERE statecode = 0 AND"
                   f" LOWER(COALESCE(NULLIF(REPLACE(REPLACE(new_anasozlesmeid, '{{', ''), '}}', ''), ''), CAST(new_sozlesmeId AS varchar(40)))) = '{row['k']}')"
                   " AND COALESCE(new_kisi, new_Firma) IS NOT NULL")
        if pids:
            ids = ", ".join(f"'{r['p']}'" for r in pids)
            others = run(f"SELECT DISTINCT LOWER(CAST(s.new_sozlesmeId AS varchar(40))) AS id FROM {P}new_sozlesmetarafiBase t JOIN {P}new_sozlesmeBase s"
                         f" ON s.new_sozlesmeId = t.new_sozlesmeid WHERE t.statecode = 0 AND s.statecode = 0 AND COALESCE(t.new_kisi, t.new_Firma) IN ({ids})"
                         f" AND LOWER(COALESCE(NULLIF(REPLACE(REPLACE(s.new_anasozlesmeid, '{{', ''), '}}', ''), ''), CAST(s.new_sozlesmeId AS varchar(40)))) <> '{row['k']}'")
            want = {r["id"] for r in others}
            got_ids: set[str] = set()
            for h in d["history"]["items"]:
                got_ids.add(h["id"])
            # uç her anlaşma kopyası kümesini tek satırda verir; SQL bütün kopyaları: uçtaki her satır SQL kümesinde olmalı,
            # SQL kümesindeki her kimlik uçtaki bir satırın anlaşmasına düşmeli
            covered = all(i in want for i in got_ids)
            ok(f"K6 {it['no']} aynı hak sahibi", covered and (len(want) == 0) == (len(got_ids) == 0),
               f"uç {len(got_ids)} satır / SQL {len(want)} sözleşme kaydı")
    ok("K3/K4 kapsam", checked_num + checked_cat > 0, f"{checked_num} sayısal, {checked_cat} seçim/bayrak maddesi SQL ile denetlendi")

    # K7 tek ödeme (M6 sözleşme sayfası)
    tek = run(f"SELECT TOP 3 LOWER(CAST(new_sozlesmeId AS varchar(40))) AS id, new_TekdemeTutari AS t FROM {P}new_sozlesmeBase"
              " WHERE statecode = 0 AND new_TelifTipi = 3 AND new_TekdemeTutari > 0 ORDER BY new_SozlesmeBaslangicTarihi DESC")
    for r in tek:
        st, dd = http("GET", f"/api/v1/editorial/contracts/item/{r['id']}")
        got = ((dd or {}).get("terms") or {}).get("flatFee")
        ok(f"K7 tek ödeme {r['id'][:8]}", st == 200 and got is not None and abs(float(got) - float(r["t"])) < 0.005, f"uç {got} / SQL {r['t']}")

    # K8 belge arşivi
    st, docs = http("GET", B + "/documents")
    check_provenance("belgeler", docs)
    n_crm = run(f"SELECT COUNT(*) AS n FROM {P}AnnotationBase a WHERE a.IsDocument = 1 AND a.ObjectTypeCode = "
                f"(SELECT ObjectTypeCode FROM {P}EntityView WHERE Name = 'new_sozlesme')")[0]["n"]
    crm_docs = [x for x in docs["items"] if x["kind"] == "crm"]
    ok("K8 CRM ek sayısı", len(crm_docs) == n_crm, f"uç {len(crm_docs)} / SQL {n_crm}")
    pdf = next((x for x in crm_docs if (x["filename"] or "").lower().endswith(".pdf")), None)
    tpl = next((x for x in docs["items"] if x["kind"] == "sablon"), None)
    pdf_ready = None
    if pdf:
        pre = pdf["status"]
        http("POST", B + "/documents/read", {"ref": pdf["ref"]})
        if pre != "hazir":
            created.append(pdf["ref"])
        pdf_ready = wait_ready(pdf["ref"])
        body = run(f"SELECT DocumentBody AS b FROM {P}AnnotationBase WHERE AnnotationId = '{pdf['ref'].split(':', 1)[1]}'")[0]["b"]
        from pypdf import PdfReader

        text = fold(" ".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(base64.b64decode(body))).pages))
        st, dd = http("POST", B + "/documents/diff", {"a": pdf["ref"], "b": tpl["ref"]}) if tpl else (0, None)
        if tpl and tpl["status"] != "hazir":
            http("POST", B + "/documents/read", {"ref": tpl["ref"]})
            created.append(tpl["ref"])
            wait_ready(tpl["ref"])
            st, dd = http("POST", B + "/documents/diff", {"a": pdf["ref"], "b": tpl["ref"]})
        if dd and st == 200:
            clauses = [r["a"] for r in dd["maddeler"] if r["a"]]
            missing = [c["sira"] for c in clauses if fold(c["metin"])[:60] not in text]
            ok("K8 PDF maddeleri belge metninde", pdf_ready.get("status") == "hazir" and len(clauses) >= 5 and not missing,
               f"{len(clauses)} madde, metinde bulunmayan {missing[:5]}")
            check_provenance("PDF↔şablon", dd)

    # K9 iki yüklenen belge
    A = ["TELİF SÖZLEŞMESİ (KABUL DENEMESİ)", "Madde 1 - Taraflar", "Yayınevi ile hak sahibi arasında yapılmıştır.",
         "Madde 2 - Telif", "Yayınevi net satış tutarı üzerinden yüzde 10 yerine %12 telif öder.", "Madde 3 - Süre",
         "Sözleşme 10 yıl geçerlidir.", "Madde 4 - Film hakları", "Film ve dizi uyarlama hakları hak sahibinde kalır."]
    Bdoc = ["TELİF SÖZLEŞMESİ (KABUL DENEMESİ)", "Madde 1 - Taraflar", "Yayınevi ile hak sahibi arasında yapılmıştır.",
            "Madde 2 - Telif", "Yayınevi net satış tutarı üzerinden yüzde 10 yerine %10 telif öder.", "Madde 3 - Süre",
            "Sözleşme 10 yıl geçerlidir."]
    refs = []
    for name, paras in (("kabul-a.docx", A), ("kabul-b.docx", Bdoc)):
        st, up = http("PUT", B + f"/documents?filename={name}", raw=docx(paras))
        ok(f"K9 yükleme {name}", st == 201, f"durum {st}")
        if st == 201:
            refs.append(up["ref"])
            created.append(up["ref"])
    if len(refs) == 2:
        for r in refs:
            wait_ready(r)
        st, dd = http("POST", B + "/documents/diff", {"a": refs[0], "b": refs[1]})
        by = {(r["a"] or r["b"])["baslik"]: r for r in (dd or {}).get("maddeler", [])}
        good = (st == 200 and by.get("Telif", {}).get("durum") == "degismis" and by["Telif"].get("sayilar") == {"a": ["10", "%12"], "b": ["10", "%10"]}
                and by.get("Film hakları", {}).get("durum") == "eklenmis" and by.get("Taraflar", {}).get("durum") == "ayni")
        ok("K9 madde farkı", good, json.dumps({k: (v["durum"], v.get("sayilar")) for k, v in by.items()}, ensure_ascii=False))
        check_provenance("belge farkı", dd or {})
        # K10
        st, cp = http("POST", B + "/documents/corpus", {"a": refs[0]})
        with engine.connect() as c:
            n_ready = c.execute(sa.text("SELECT COUNT(*) FROM semantic_contract_compare_docs WHERE status = 'hazir'")).scalar()
        ok("K10 arşive karşı", st == 200 and cp["belgeSayisi"] == n_ready - 1
           and next(r for r in cp["maddeler"] if r["a"]["baslik"] == "Film hakları")["durum"] == "arsivde-yok",
           f"belge {cp.get('belgeSayisi')} / okunmuş {n_ready}")
        check_provenance("arşive karşı", cp)

    # temizlik
    for ref in created:
        st, _ = http("DELETE", B + f"/documents?ref={ref}")
        ok(f"temizlik {ref[:24]}", st == 200, f"durum {st}")
    with engine.connect() as c:
        left = c.execute(sa.text("SELECT COUNT(*) FROM semantic_contract_compare_docs WHERE ref = ANY(:r)"), {"r": created}).scalar()
        audit = c.execute(sa.text("SELECT MIN(id), MAX(id), COUNT(*) FROM semantic_audit WHERE actor = 'timasai' AND at >= to_timestamp(:t)"),
                          {"t": t_start}).first()
    ok("temizlik: satır kalmadı", left == 0, f"{left} satır")
    summary = {"gecti": sum(1 for _, g, _ in results if g), "kaldi": sum(1 for _, g, _ in results if not g),
               "audit": {"min": audit[0], "max": audit[1], "sayi": audit[2]} if audit else None,
               "sonuclar": [{"ad": n, "gecti": g, "ayrinti": d} for n, g, d in results]}
    with open(args.out, "w") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=1)
    print(f"== {summary['gecti']} geçti, {summary['kaldi']} kaldı; değişiklik kaydı {summary['audit']}")


if __name__ == "__main__":
    main()
