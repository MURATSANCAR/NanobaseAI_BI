"""Sözleşme karşılaştırma — test sunucusunda gerçek uç ↔ bağımsız referans kabulü. Yerelde koşulmaz.

Referanslar köprünün hesabını kullanmaz: CRM doğrudan SQL ile (connector_from_file; yüzdelik PERCENTILE_CONT, sayımlar
COUNT), PDF metni bu betikte ayrıca okunur (pypdf), köprü veritabanı doğrudan SQL.

  K1  CRM'deki etkin sözleşme sayısı (COUNT) = ekrandaki «CRM sözleşmesi»; anlaşma sayısı ≤ sözleşme
  K2  tarama: en çok farklı maddesi olan 5 anlaşma; her birinin sözleşme sayfası taramadaki farklı maddelerle aynı
  K3  sayısal farklı madde: emsal grubu (tip/ödeme/para/bölüm, dönem) CRM'de SQL ile yeniden kurulur (anlaşma başına tek
      satır); emsal sayısı, dolu sayısı, «bu değer ya da üstü/altı» sayısı, medyan ve %10/%90 (PERCENTILE_CONT) uçla aynı
  K4  seçim/bayrak farklı madde: aynı değeri taşıyan emsal sayısı SQL sayımıyla aynı
  K5  özgün not: aynı metin (kırpılmış, küçük harf) başka anlaşmada yok (SQL); kalıp not ≥ eşik anlaşmada var
  K6  aynı hak sahibi: taraf tablosundan (SQL) aynı kişi/firmanın öbür anlaşmaları uçtakiyle aynı küme (anlaşma düzeyinde)
  K7  tek ödeme tutarı: sözleşme sayfası (M6) `new_TekdemeTutari`'nı okuyor (düzeltme), 3 tek ödemeli sözleşmede SQL = uç
  K8  belge arşivi: CRM ek sayısı (SQL) = arşivdeki CRM eki; PDF okunur, her maddenin metni betiğin kendi okuduğu PDF
      metninde (katlanmış) geçer
  K9  yüklenen iki Word belgesi: değişen sayı «değişmiş» + sayı farkı, eklenen madde «yalnız bu belgede», aynı madde «aynı»
  K10 arşive karşı: belge sayısı = okunmuş belge − 1
  K11 her cevapta kaynağı yazılmamış rakam yok, SQL'de yer tutucu/sır yok; ekrana giden metinde teknoloji adı yok
  K12 oturumsuz istek 401
  --- faz 1–3
  K13 kur: TL avanslı bir sözleşmenin kıyas değeri = avans / (betiğin kendi okuduğu TCMB USD alış kuru, başlangıç ayı)
  K14 şekil: «başlangıç tarihi yok» sayısı = SQL (anlaşma temsilcisi, başlangıcı boş)
  K15 inceleme: yazılır (SQL satırı), sözleşmede görünür, «incelenmemiş» süzgecinde o bulgu kapanır, silinir (SQL)
  K16 liste: CSV satır sayısı = tarama toplamı; Excel eşi xlsx
  K17 taslak: kaydedilmeden emsal kontrolü (aşırı oran «yüksek»), kayıt yok (SQL)
  K18 ek ölçüt: ajans + hedef kitle seçilince emsal daralır, ölçütler kıyas grubunda
  K19 pozisyon: «karton telif en çok %10» kuralına aykıran anlaşmalar = SQL (tip 5, satıştan ödeme, new_Telif > 10; 0 değil)
  K20 öneri: emsalden karton telif alt sınırı = SQL PERCENTILE_CONT(0,05) (anlaşma temsilcisi, son N yıl)
  K21 madde türü: gerçek PDF maddelerinde kuralla bulunan her tür, maddenin kendi metninde türün sözcüğünü taşır
  K22 Word: sözleşme raporu ve belge farkı açılır, metni taşır
  K23 maske: sahte kimlik no ve e-posta maskeli cevapta yok, maskesiz cevapta var, görüntüleme kayda yazılır (SQL)
  K24 eşleşme: dosya adındaki sözleşme numarası okununca bağlanır
  K25 olaylar: ek protokol tarihi olan sözleşmede olay çizelgesi CRM tarihini taşır

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
import urllib.parse
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


def tcmb_usd(year: int, month: int) -> float | None:
    """Betiğin kendi TCMB okuması (uygulamanın okuyucusundan bağımsız): ayın 1'i ya da önceki son iş günü."""
    import datetime as dt

    d = dt.date(year, month, 1)
    for back in range(0, 11):
        x = d - dt.timedelta(days=back)
        url = f"https://www.tcmb.gov.tr/kurlar/{x:%Y%m}/{x:%d%m%Y}.xml"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "kabul"}), timeout=20) as r:
                text = r.read().decode("iso-8859-9", "replace")
        except urllib.error.HTTPError:
            continue
        m = re.search(r'Kod="USD".*?<ForexBuying>([\d.]+)</ForexBuying>', text, re.S) or \
            re.search(r'CurrencyCode="USD".*?<ForexBuying>([\d.]+)</ForexBuying>', text, re.S)
        if m:
            v = float(m.group(1))
            return v / 1_000_000 if v > 10000 else v
    return None


REP = ("WITH x AS (SELECT LOWER(COALESCE(NULLIF(REPLACE(REPLACE(s.new_anasozlesmeid, '{', ''), '}', ''), ''), "
       "CAST(s.new_sozlesmeId AS varchar(40)))) AS k, s.*, ROW_NUMBER() OVER (PARTITION BY LOWER(COALESCE(NULLIF(REPLACE("
       "REPLACE(s.new_anasozlesmeid, '{', ''), '}', ''), ''), CAST(s.new_sozlesmeId AS varchar(40)))) ORDER BY CASE WHEN "
       "LOWER(CAST(s.new_sozlesmeId AS varchar(40))) = LOWER(COALESCE(NULLIF(REPLACE(REPLACE(s.new_anasozlesmeid, '{', ''), "
       "'}', ''), ''), CAST(s.new_sozlesmeId AS varchar(40)))) THEN 0 ELSE 1 END, LEN(s.new_name), s.new_name) AS rn "
       "FROM {P}new_sozlesmeBase s WHERE s.statecode = 0) ")


def all_items(path: str) -> list[dict]:
    out, page = [], 0
    while True:
        st, d = http("GET", f"{path}&page={page}")
        if st != 200:
            return out
        out += d["items"]
        if (page + 1) * d["pageSize"] >= d["total"]:
            return out
        page += 1


def faz123(run, engine, meta: dict, scan: dict, created: list[str]) -> None:
    rep = REP.replace("{P}", P)
    t0 = time.time()
    for _ in range(180):                      # kurlar ilk açılışta arka planda okunur (~4 dk)
        _, m = http("GET", B + "/meta")
        if m and not m["kur"]["okunuyor"] and m["kur"]["okunan"] > 0:
            break
        time.sleep(5)
    # Başlangıcı gelecek aydaki sözleşmenin kuru TCMB'de henüz yok: en çok o aylar eksik kalabilir.
    import datetime as _dt
    future = sum(1 for r in run(f"SELECT DISTINCT CONVERT(varchar(7), new_SozlesmeBaslangicTarihi, 126) AS m FROM {P}new_sozlesmeBase "
                                "WHERE statecode = 0 AND new_sozlesmeparabirimi = 1 AND new_SozlesmeBaslangicTarihi > GETDATE()")
                 if r["m"] and r["m"] > _dt.date.today().strftime("%Y-%m"))
    ok("kur önbelleği", m["kur"]["ay"] - m["kur"]["okunan"] <= future,
       f"{m['kur']['okunan']}/{m['kur']['ay']} ay (gelecek ay {future}), {round(time.time() - t0)} sn")
    _, scan = http("GET", B + "/scan?only=sapan&page=0")
    # K13 kur
    rows = run(f"SELECT TOP 3 LOWER(CAST(new_sozlesmeId AS varchar(40))) AS id, new_sozlesmeavanstutari AS a, new_SozlesmeBaslangicTarihi AS b"
               f" FROM {P}new_sozlesmeBase WHERE statecode = 0 AND new_sozlesmeparabirimi = 1 AND new_sozlesmeavanstutari > 0"
               " AND new_SozlesmeBaslangicTarihi >= '2015-01-01' ORDER BY new_SozlesmeBaslangicTarihi DESC")
    for r in rows:
        st, d = http("GET", B + f"/contract/{r['id']}")
        c = next((x for g in (d or {}).get("groups", []) for x in g["clauses"] if x["key"] == "new_sozlesmeavanstutari"), None)
        b = str(r["b"])[:7]
        rate = tcmb_usd(int(b[:4]), int(b[5:7]))
        want = round(float(r["a"]) / rate, 2) if rate else None
        got = round(float(c["kiyas"]), 2) if c and c.get("kiyas") is not None else None
        ok(f"K13 kur {r['id'][:8]} ({b})", st == 200 and want is not None and got is not None and abs(want - got) <= 0.01,
           f"uç {got} USD / betik {want} USD (kur {rate})")
    # K14 şekil
    n_start = run(rep + "SELECT COUNT(*) AS n FROM x WHERE x.rn = 1 AND x.new_SozlesmeBaslangicTarihi IS NULL")[0]["n"]
    got = next((x["sayi"] for x in scan.get("sekilSayim", []) if x["id"] == "baslangic"), 0)
    ok("K14 şekil: başlangıç tarihi yok", got >= n_start and got - n_start <= scan["ozet"]["anlasma"] * 0.01,
       f"uç {got} (anlaşma kopyaları dahil) / SQL temsilci {n_start}")
    # K15 inceleme
    it = next(x for x in scan["items"] if x["sapmalar"])
    clause = it["sapmalar"][0]["key"]
    st, rv = http("POST", B + "/reviews", {"key": it["id"], "clause": clause, "status": "istisna", "note": "kabul denemesi"})
    with engine.connect() as c:
        nrow = c.execute(sa.text("SELECT COUNT(*) FROM semantic_contract_compare_reviews WHERE agreement = :a AND clause = :c"),
                         {"a": it["agreement"], "c": clause}).scalar()
    st2, d = http("GET", B + f"/contract/{it['id']}")
    seen = next((x.get("inceleme") for g in d["groups"] for x in g["clauses"] if x["key"] == clause), None)
    st3, _ = http("DELETE", B + f"/reviews?key={it['id']}&clause={clause}")
    with engine.connect() as c:
        left = c.execute(sa.text("SELECT COUNT(*) FROM semantic_contract_compare_reviews WHERE agreement = :a"), {"a": it["agreement"]}).scalar()
    ok("K15 inceleme yaz/gör/sil", st == 200 and nrow == 1 and seen and seen["status"] == "istisna" and not seen["open"] and st3 == 200 and left == 0,
       f"yaz {st}, SQL {nrow}, görünen {seen and seen['statusLabel']}, sil {st3}, kalan {left}")
    # K16 CSV / Excel
    req = urllib.request.Request(BASE + B + "/scan.csv?only=sapan&enAz=5", headers={"Cookie": COOKIE})
    with urllib.request.urlopen(req, timeout=300) as r:
        csv_text = r.read().decode("utf-8-sig")
    st, s5 = http("GET", B + "/scan?only=sapan&enAz=5&page=0")
    lines = [l for l in csv_text.splitlines() if l.strip()]
    req = urllib.request.Request(BASE + B + "/scan.csv?only=sapan&enAz=5&bicim=xlsx", headers={"Cookie": COOKIE})
    with urllib.request.urlopen(req, timeout=300) as r:
        ctype, xbytes = r.headers.get("Content-Type", ""), r.read()
    ok("K16 CSV = tarama toplamı, Excel eşi", len(lines) - 1 == s5["total"] and "spreadsheetml" in ctype and xbytes[:2] == b"PK",
       f"CSV {len(lines) - 1} satır / tarama {s5['total']}; Excel {ctype} {len(xbytes)} bayt")
    # K17 taslak
    with engine.connect() as c:
        before = c.execute(sa.text("SELECT COUNT(*) FROM semantic_contracts")).scalar()
    st, d = http("POST", B + "/terms", {"terms": {"kind": "telif-alis", "paymentType": "satis", "currency": "TRY", "rates": {"karton": 60},
                                                  "start": "2026-09-01", "parties": [], "books": [], "title": "Kabul taslağı", "rights": {}}})
    c17 = next((x for g in (d or {}).get("groups", []) for x in g["clauses"] if x["key"] == "new_Telif"), {})
    with engine.connect() as c:
        after = c.execute(sa.text("SELECT COUNT(*) FROM semantic_contracts")).scalar()
    ok("K17 taslak kontrolü", st == 200 and c17.get("status") == "yuksek" and before == after and any(not x["ok"] for x in d["sekil"]),
       f"durum {c17.get('status')}, şekil eksiği {sum(1 for x in d['sekil'] if not x['ok'])}, portal kaydı {before}→{after}")
    # K18 ek ölçüt
    key = scan["items"][0]["id"]
    st, base = http("GET", B + f"/contract/{key}?olcut=-")
    st2, dd = http("GET", B + f"/contract/{key}?olcut=ajans,hedef")
    ids = [b_["id"] for b_ in dd["criteria"]["boyutlar"]] + [x for x in dd["criteria"]["gevsetilen"]]
    ok("K18 ek ölçüt", st == 200 and st2 == 200 and dd["criteria"]["emsal"] <= base["criteria"]["emsal"] and ("ajans" in ids or "Ajans üzerinden" in ids),
       f"emsal {base['criteria']['emsal']} → {dd['criteria']['emsal']}; ölçütler {ids}")
    # K19 pozisyon
    st, rule = http("POST", B + "/positions", {"clause": "new_Telif", "op": "max", "value": 10, "level": "kirmizi",
                                                "scope": {"tip": 5, "odeme": 2}, "reason": "kabul denemesi"})
    items = all_items(B + "/scan?only=pozisyon&enAz=1")
    got_ag = {x["agreement"] for x in items}
    want = run(rep + "SELECT COUNT(DISTINCT x.k) AS n FROM x WHERE x.new_SozlesmeTipi = 5 AND x.new_TelifTipi = 2 AND x.new_Telif > 10")[0]["n"]
    ok("K19 pozisyon ihlali = SQL", st == 200 and want > 0 and len(got_ag) >= want and len(got_ag) - want <= max(2, want * 0.05),
       f"uç {len(got_ag)} anlaşma / SQL temsilci {want} (fark = temsilcisi uyan ama kopyası aykırı anlaşma)")
    http("DELETE", B + f"/positions/{rule['id']}") if st == 200 else None
    # K20 öneri
    yil = meta["ayarlar"]["yil"]
    import datetime as dt
    now = dt.date.today().year
    st, sg = http("POST", B + "/positions/suggest", {"tip": 5, "odeme": 2})
    st2, pl = http("GET", B + "/positions")
    mine = [p for p in pl["items"] if p["state"] == "oneri" and p["scope"]["tip"] == 5 and p["scope"]["odeme"] == 2]
    low = next((p["value"] for p in mine if p["clause"] == "new_Telif" and p["op"] == "min"), None)
    vals = [r["v"] for r in run(rep + f"SELECT CAST(x.new_Telif AS float) AS v FROM x WHERE x.rn = 1 AND x.new_SozlesmeTipi = 5 "
                                     f"AND x.new_TelifTipi = 2 AND x.new_Telif > 0 AND YEAR(x.new_SozlesmeBaslangicTarihi) BETWEEN {now - yil} AND {now}")]
    ok("K20 öneri alt sınırı = SQL %5", st == 200 and low is not None and abs(low - pct(vals, 0.05)) < 1e-6,
       f"uç {low} / SQL {pct(vals, 0.05)} ({len(vals)} değer); {sg.get('eklenen')} öneri")
    for p in mine:
        http("DELETE", B + f"/positions/{p['id']}")
    # K21 madde türü (gerçek PDF; kuralla bulunanlar)
    st, docs = http("GET", B + "/documents")
    pdf = next((x for x in docs["items"] if x["kind"] == "crm" and (x["filename"] or "").lower().endswith(".pdf")), None)
    if pdf:
        if pdf["status"] != "hazir":
            http("POST", B + "/documents/read", {"ref": pdf["ref"]})
            created.append(pdf["ref"])
            wait_ready(pdf["ref"])
        st, cp = http("POST", B + "/documents/corpus", {"a": pdf["ref"]})
        from semantic_bridge import contracts_compare_docs as CDm
        bad, rule_n, zeki_n = [], 0, 0
        for r in cp.get("maddeler", []):
            c = r["a"]
            if c.get("turKaynak") == "kural":
                rule_n += 1
                words = CDm.CLAUSE_TYPES[c["tur"]][1]
                txt = " " + fold((c.get("baslik") or "") + " " + (c.get("metin") or "")[:500]) + " "
                if not any(f" {w}" in txt for w in words):
                    bad.append(c["sira"])
            elif c.get("turKaynak") == "zeki":
                zeki_n += 1
        ok("K21 madde türü (gerçek PDF)", st == 200 and rule_n > 0 and not bad,
           f"{len(cp.get('maddeler', []))} madde: {rule_n} kuralla, {zeki_n} Zeki AI ile; sözcüğü tutmayan {bad}")
    # K22–K24 Word, maske, eşleşme
    no = scan["items"][0]["no"]
    body = ["TELİF SÖZLEŞMESİ", f"Sözleşme No: {no}", "Madde 1 - Taraflar", "Hak sahibi Kabul Deneme, T.C. Kimlik No: 12345678950, "
            "e-posta: kabul.deneme@ornek.invalid", "Madde 2 - Fesih", "Taraflardan biri ihlal halinde sözleşmeyi feshedebilir.",
            "Madde 3 - Telif", "Yayınevi net satış tutarı üzerinden %10 telif öder."]
    st, up = http("PUT", B + f"/documents?filename={urllib.parse.quote(no)}-kabul.docx", raw=docx(body))
    if st == 201:
        created.append(up["ref"])
        d = wait_ready(up["ref"])
        ok("K24 sözleşmeye kendiliğinden bağlandı", d.get("contractNo") == no, f"bağ {d.get('contractNo')} / beklenen {no}")
        other = next((x["ref"] for x in docs["items"] if x["kind"] == "sablon"), None)
        if other:
            http("POST", B + "/documents/read", {"ref": other})
            if other not in created:
                created.append(other)
            wait_ready(other)
            st, masked = http("POST", B + "/documents/diff", {"a": up["ref"], "b": other})
            text_m = json.dumps(masked, ensure_ascii=False)
            st2, raw_ = http("POST", B + "/documents/diff", {"a": up["ref"], "b": other, "maskesiz": True})
            text_r = json.dumps(raw_, ensure_ascii=False)
            with engine.connect() as c:
                views = c.execute(sa.text("SELECT COUNT(*) FROM semantic_audit WHERE actor = 'timasai' AND action = 'view' AND object_id = :r"),
                                  {"r": up["ref"]}).scalar()
            ok("K23 maske", st == 200 and "12345678950" not in text_m and "kabul.deneme@ornek.invalid" not in text_m
               and "12345678950" in text_r and views >= 1, f"maskeli cevapta yok, maskesiz cevapta var; görüntüleme kaydı {views}")
            req = urllib.request.Request(BASE + B + f"/documents/diff.docx?a={urllib.parse.quote(up['ref'])}&b={urllib.parse.quote(other)}",
                                         headers={"Cookie": COOKIE})
            with urllib.request.urlopen(req, timeout=120) as r:
                xml = zipfile.ZipFile(io.BytesIO(r.read())).read("word/document.xml").decode()
            ok("K22 Word belge farkı", "Belge karşılaştırma raporu" in xml and "12345678950" not in xml, f"{len(xml)} karakter, maskeli")
    req = urllib.request.Request(BASE + B + f"/contract/{scan['items'][0]['id']}/report.docx", headers={"Cookie": COOKIE})
    with urllib.request.urlopen(req, timeout=300) as r:
        xml = zipfile.ZipFile(io.BytesIO(r.read())).read("word/document.xml").decode()
    ok("K22 Word sözleşme raporu", scan["items"][0]["no"] in xml and "Farklı maddeler" in xml, f"{len(xml)} karakter")
    # K25 olaylar
    ev = run(f"SELECT TOP 1 LOWER(CAST(new_sozlesmeId AS varchar(40))) AS id, CONVERT(varchar(10), new_ekprotokoltarihi, 23) AS t"
             f" FROM {P}new_sozlesmeBase WHERE statecode = 0 AND new_ekprotokoltarihi IS NOT NULL ORDER BY new_ekprotokoltarihi DESC")
    if ev:
        st, d = http("GET", B + f"/contract/{ev[0]['id']}")
        got = [x for x in d.get("olaylar", []) if x["olay"] == "Ek protokol"]
        ok("K25 olay çizelgesi", st == 200 and any(x["tarih"] == ev[0]["t"] for x in got), f"uç {[x['tarih'] for x in got]} / SQL {ev[0]['t']}")


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
            others = run(f"SELECT DISTINCT LOWER(CAST(s.new_sozlesmeId AS varchar(40))) AS id,"
                         f" LOWER(COALESCE(NULLIF(REPLACE(REPLACE(s.new_anasozlesmeid, '{{', ''), '}}', ''), ''), CAST(s.new_sozlesmeId AS varchar(40)))) AS k"
                         f" FROM {P}new_sozlesmetarafiBase t JOIN {P}new_sozlesmeBase s"
                         f" ON s.new_sozlesmeId = t.new_sozlesmeid WHERE t.statecode = 0 AND s.statecode = 0 AND COALESCE(t.new_kisi, t.new_Firma) IN ({ids})"
                         f" AND LOWER(COALESCE(NULLIF(REPLACE(REPLACE(s.new_anasozlesmeid, '{{', ''), '}}', ''), ''), CAST(s.new_sozlesmeId AS varchar(40)))) <> '{row['k']}'")
            want = {r["id"] for r in others}
            want_ag = {r["k"] for r in others}
            got_ids = {h["id"] for h in d["history"]["items"]}
            # Uç her anlaşmayı (kopyalarıyla) tek satırda, ana kaydın kimliğiyle verir; taraf ise yalnız bir kopyada olabilir.
            # Karşılaştırma anlaşma düzeyinde: uçtaki her satırın anlaşması SQL'in anlaşma kümesinde, küme uçla aynı.
            got_ag = set()
            if got_ids:
                got_ag = {r["k"] for r in run(
                    f"SELECT LOWER(COALESCE(NULLIF(REPLACE(REPLACE(new_anasozlesmeid, '{{', ''), '}}', ''), ''), CAST(new_sozlesmeId AS varchar(40)))) AS k"
                    f" FROM {P}new_sozlesmeBase WHERE statecode = 0 AND LOWER(CAST(new_sozlesmeId AS varchar(40))) IN ({', '.join(repr(i) for i in got_ids)})")}
            ok(f"K6 {it['no']} aynı hak sahibi", got_ag == want_ag,
               f"uç {len(got_ag)} anlaşma / SQL {len(want_ag)} anlaşma ({len(want)} sözleşme kaydı)")
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
    # Yalnız etkin sözleşmenin ekleri (kullanıcı kuralı 2026-09-29: durum nedeni «Pasif» olan hiçbir ekranda yok; bağlantı süzer).
    n_crm = run(f"SELECT COUNT(*) AS n FROM {P}AnnotationBase a JOIN {P}new_sozlesmeBase s ON s.new_sozlesmeId = a.ObjectId"
                f" WHERE a.IsDocument = 1 AND a.ObjectTypeCode = (SELECT ObjectTypeCode FROM {P}EntityView WHERE Name = 'new_sozlesme')")[0]["n"]
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

    faz123(run, engine, meta, scan, created)

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
