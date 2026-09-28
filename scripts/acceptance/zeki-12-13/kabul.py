"""Öneri 12 (başvuru ön okuması) ve 13 (sözleşme belgesinden şart çıkarma) — test sunucusunda gerçek uç ↔ bağımsız
referans kabulü. Yerelde koşulmaz.

Referanslar köprünün hesabını kullanmaz: belge metni bu betikte ayrıca okunur (Word XML'i elle, PDF'i pypdf ile),
köprü veritabanı doğrudan SQL, CRM doğrudan SQL (connector_from_file). Sentetik belgelerdeki bilinen değerler
(yazar adı/e-postası uydurma; gerçek kişi yok) sonuçla karşılaştırılır.

  R1  ön okuma kaydı (doğrudan SQL) = uç sonucu; durum «hazir»
  R2  her alıntı, betiğin kendi okuduğu belge metninde birebir (katlamalı) geçer
  R3  yaş aralığı alıntıdaki rakamlardır; özet cümlesindeki her sayı kendi alıntısında geçer
  R4  benzer kitaplar CRM'de etkin kitap (doğrudan CRM SQL) ve dizinde etkin
  R5  taslak puan/öneri alanı taşımaz, «temiz» önermez; ilke işareti varsa «dikkat»
  R6  sentetik yazar adı ve e-postası sonuçta yok (modele maskeli gitti, alıntı maskeli metinden)
  R7  sözleşme: avans, oranlar, bitiş, para birimi belgedeki bilinen değerler; kayıt (doğrudan SQL) = uç
  R8  sözleşme: modelin yazdığı ama belgede olmayan değer yok (her kanıt alıntısı belgede)
  R9  kabul kaydı: aktarılan alanlar ve sözleşme bağı doğrudan SQL'de
  R10 değişiklik kaydı (semantic_audit): ön okuma başlatma, belge yükleme, kabul
  R11 ekrana giden metinde teknoloji adı yok
  R12 (isteğe bağlı, --app-id) gerçek bir başvurunun dosyasında R1–R3, R5 aynı kurallarla

Yazma: bir sentetik başvuru + dosyası, ön okuma kayıtları, bir sözleşme belgesi okuması. Kimlikler `--out` dosyasına
yazılır; `temizlik.py` hepsini ve diskteki dosyaları siler. CRM'e hiçbir şey yazılmaz.
Ortam: BASE (yan port köprüsü), COOKIE (timasai'nin 15 dk'lık oturumu), SEMANTIC_STORE_DSN, SEMANTIC_CRM_CONNECTION_FILE,
CRM_SCHEMA (varsayılan Timas_MSCRM.dbo), PYTHONPATH=<aday ağaç>/backend.
Kullanım: python kabul.py --out /tmp/claude-zeki1213/kabul.json [--app-id <gerçek başvuru>]
"""
from __future__ import annotations

import argparse
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

BASE = os.environ.get("BASE", "http://127.0.0.1:8798").rstrip("/")
COOKIE = os.environ.get("COOKIE", "")
SCHEMA = os.environ.get("CRM_SCHEMA", "Timas_MSCRM.dbo")
TECH = ("qwen", "vllm", "llama", "openai", "dil modeli", "llm", "tesseract", "deepseek", "timesfm")
AUTHOR, EMAIL = "Kabul Denemeyazarı", "kabul.deneme@ornek.invalid"
results: list[tuple[str, bool, str]] = []

APP_TEXT = [
    "BİRİNCİ BÖLÜM",
    "Bu roman, 1923 yılında İstanbul'da geçen bir aile hikâyesini anlatır.",
    f"Yazar {AUTHOR} ile {EMAIL} adresinden iletişim kurulabilir.",
    "Kitap 12-15 yaş arası genç okurlar için yazılmıştır.",
    "Ana tema dostluk, aile ve cesarettir.",
    "İKİNCİ BÖLÜM",
    "Kahraman Ali, savaş yıllarında kaybolan kardeşini aramak için Anadolu'ya yola çıkar.",
    "Yolculukta bir köy öğretmeniyle tanışır ve okumayı öğrenir.",
    "Kitapta sert bir kavga sahnesi ayrıntılı anlatılır.",
    "ÜÇÜNCÜ BÖLÜM",
    "Ali sonunda kardeşini bulur ve aile yeniden bir araya gelir.",
]
CONTRACT_TEXT = [
    "TELİF SÖZLEŞMESİ",
    f"Adı Soyadı: {AUTHOR}",
    "Madde 3. Yayınevi, eserin net satış tutarı üzerinden yazara %10 (yüzde on) telif öder.",
    "Madde 4. E-kitap satışlarında telif oranı %25'tir.",
    "Madde 5. Yayınevi yazara imza tarihinde 15.000,00 TL avans öder; avans telif ücretinden mahsup edilir.",
    "Madde 6. Bu sözleşme 01.01.2026 tarihinden 31.12.2030 tarihine kadar geçerlidir.",
    "Madde 7. Yazar, eserin Türkçe dilinde basılı ve e-kitap olarak çoğaltma, yayma ve umuma iletim haklarını yayınevine münhasır olarak devreder.",
    "Madde 8. Sesli kitap hakları yazarda saklıdır.",
]


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


def own_text(path: str) -> str:
    """Belgenin metni köprü kodu kullanılmadan: Word XML'inin w:t düğümleri ya da pypdf."""
    data = open(path, "rb").read()
    if data[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            xml = z.read("word/document.xml").decode("utf-8", "replace")
        return "\n".join(re.sub(r"<[^>]+>", "", p) for p in re.findall(r"<w:p[ >].*?</w:p>", xml, flags=re.S))
    from pypdf import PdfReader
    return "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(data)).pages)


def fold(s: str) -> str:
    t = str(s or "").replace("İ", "i").replace("I", "ı").lower()
    t = t.translate(str.maketrans("ışğüöç", "isguoc"))
    t = "".join(ch for ch in unicodedata.normalize("NFKD", t) if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", re.sub(r"[^0-9a-z]+", " ", t)).strip()


def quote_in(quote: str, text_fold: str) -> bool:
    """Maskeli alıntı: yer tutucu ([kişi], [e-posta] …) dışındaki her parça belgede sırasıyla geçmeli."""
    parts = [fold(p) for p in re.split(r"\[[^\]]{1,30}\]", quote) if fold(p)]
    pos = 0
    for p in parts:
        i = text_fold.find(p, pos)
        if i < 0:
            return False
        pos = i + len(p)
    return bool(parts)


def http(method: str, path: str, body=None, raw: bytes | None = None, timeout=900):
    data = raw if raw is not None else (None if body is None else json.dumps(body).encode())
    headers = {"Cookie": COOKIE, "Content-Type": "application/octet-stream" if raw is not None else "application/json"}
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            b = r.read()
            return r.status, (json.loads(b) if b[:1] in (b"{", b"[") else b)
    except urllib.error.HTTPError as e:
        b = e.read()
        try:
            return e.code, json.loads(b)
        except ValueError:
            return e.code, b


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(("GEÇTİ " if ok else "KALDI ") + name + (f" — {detail}" if detail else ""), flush=True)


def crm_rows(sql: str) -> list[dict]:
    from semantic_layer.profiler.connectors import connector_from_file

    conn = connector_from_file(os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json"))
    try:
        _, rows, _ = conn.execute(sql, 100000)
        return rows
    finally:
        conn.close()


def all_quotes(res: dict) -> list[str]:
    out: list[str] = []

    def walk(v):
        if isinstance(v, dict):
            if isinstance(v.get("alinti"), str):
                out.append(v["alinti"])
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)
    walk(res)
    return out


def wait(path: str, key: str, limit: float = 1800.0) -> dict:
    t0 = time.time()
    while True:
        s, out = http("GET", path)
        item = (out or {}).get(key) if isinstance(out, dict) else None
        if s != 200 or item is None or item.get("status") != "hazirlaniyor" or time.time() - t0 > limit:
            return out if isinstance(out, dict) else {}
        time.sleep(5)


def preread_checks(eng, app_id: str, file_path: str, tag: str, synthetic: bool) -> None:
    g = wait(f"/api/v1/editorial/applications/{app_id}/preread", "preread")
    p = g.get("preread") or {}
    with eng.connect() as c:
        row = c.execute(sa.text("SELECT status, result_json FROM semantic_editorial_application_prereads WHERE id = :i"),
                        {"i": p.get("id")}).first()
    res = p.get("result") or {}
    check(f"R1{tag} ön okuma kaydı = uç", bool(row) and row.status == "hazir" and json.loads(row.result_json) == res,
          f"durum {p.get('status')} {p.get('error') or ''}")
    tf = fold(own_text(file_path))
    qs = all_quotes(res.get("alanlar") or {})
    bad = [q for q in qs if not quote_in(q, tf)]
    check(f"R2{tag} alıntılar belgede", bool(qs) and not bad, f"{len(qs)} alıntı, {len(bad)} bulunamadı {bad[:2]}")
    a = res.get("alanlar") or {}
    ok = True
    if a.get("yas") and a["yas"].get("ad"):
        for ev in a["yas"]["kanit"]:
            ok = ok and all(str(n) in ev["alinti"] for n in (a["yas"]["alt"], a["yas"]["ust"]) if n is not None)
    for c_ in (a.get("ozet") or {}).get("cumleler") or []:
        ok = ok and all(n in c_["kanit"]["alinti"] for n in re.findall(r"\d+", c_["cumle"]))
    check(f"R3{tag} yaş ve özet sayıları alıntıdan", ok)
    d = res.get("taslak") or {}
    ok = set(d) == {"topic", "genre", "ageGroup", "overlapNote", "redline", "redlineNote", "report"} and d.get("redline") != "temiz"
    ok = ok and (d.get("redline") == "dikkat") == bool(a.get("ilke"))
    check(f"R5{tag} taslak puan/karar taşımaz", ok, f"redline={d.get('redline')}")
    text = json.dumps(res, ensure_ascii=False).lower()
    check(f"R11{tag} teknoloji adı yok", not any(t in text for t in TECH))
    if synthetic:
        check("R6 yazar kişisel verisi sonuçta yok", AUTHOR.lower() not in text and EMAIL not in text)
        items = (res.get("benzer") or {}).get("items") or []
        ok = True
        p_ = SCHEMA + "."
        with eng.connect() as c:
            for x in items:
                ref = crm_rows(f"SELECT COUNT(*) AS n FROM {p_}new_kitapBase WHERE new_kitapId = '{x['kitapId']}' AND statecode = 0 AND new_Tip = 1")
                idx = c.execute(sa.text("SELECT COUNT(*) FROM semantic_book_embeddings WHERE kitap_id = :k AND aktif"), {"k": x["kitapId"]}).scalar()
                ok = ok and int(list(ref[0].values())[0]) == 1 and idx >= 1
        check("R4 benzer kitaplar CRM'de etkin", ok, f"{len(items)} kitap · {(res.get('benzer') or {}).get('not') or ''}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--app-id", default="")
    a = ap.parse_args()
    eng = sa.create_engine(os.environ["SEMANTIC_STORE_DSN"])
    created: dict[str, list] = {"basvuru": [], "onokuma": [], "belge": []}
    t_start = time.strftime("%Y-%m-%dT%H:%M:%S")

    # ------------------------------------------------ öneri 12: sentetik başvuru
    s, app = http("POST", "/api/v1/editorial/applications", {
        "title": "Kabul denemesi — Kayıp Yıllar", "authorName": AUTHOR, "authorEmail": EMAIL, "summary": "Kabul denemesi.",
        "authorBio": "Kabul denemesi.", "pageEstimate": 120, "channel": "eposta", "receivedOn": time.strftime("%Y-%m-%d"),
        "audience": "genc"})
    if s != 201:
        check("başvuru açıldı", False, f"HTTP {s} {app}")
        return 1
    created["basvuru"].append(app["id"])
    s, f = http("PUT", f"/api/v1/editorial/applications/{app['id']}/files?kind=dosya&filename=kabul-eser.docx", raw=docx(APP_TEXT))
    check("dosya yüklendi", s == 201, f"HTTP {s}")
    s, st = http("POST", f"/api/v1/editorial/applications/{app['id']}/preread", {"fileId": f.get("id")})
    check("ön okuma başladı", s == 200, f"HTTP {s} {st if s != 200 else ''}")
    if s == 200:
        created["onokuma"].append(st["preread"]["id"])
    with eng.connect() as c:
        path = c.execute(sa.text("SELECT path FROM semantic_editorial_application_files WHERE id = :i"), {"i": f.get("id")}).scalar()
    preread_checks(eng, app["id"], path, "", True)

    # ------------------------------------------------ öneri 13: sentetik sözleşme belgesi
    s, ex = http("PUT", "/api/v1/editorial/contracts/extracts?filename=kabul-sozlesme.docx", raw=docx(CONTRACT_TEXT))
    check("sözleşme belgesi yüklendi", s == 201, f"HTTP {s} {ex if s != 201 else ''}")
    if s == 201:
        created["belge"].append(ex["id"])
        g = wait(f"/api/v1/editorial/contracts/extracts/{ex['id']}", "item")
        item = g.get("item") or {}
        res = item.get("result") or {}
        o = res.get("oneri") or {}
        with eng.connect() as c:
            row = c.execute(sa.text("SELECT status, result_json, path FROM semantic_contract_extracts WHERE id = :i"), {"i": ex["id"]}).first()
        ok = (o.get("advance") == 15000 and (o.get("rates") or {}).get("karton") == 10 and (o.get("rates") or {}).get("ekitap") == 25
              and o.get("end") == "2030-12-31" and o.get("currency") == "TRY" and o.get("basis") == "net"
              and bool(row) and row.status == "hazir" and json.loads(row.result_json) == res)
        check("R7 sözleşme şartları = belgedeki değerler, kayıt = uç", ok, json.dumps(o, ensure_ascii=False)[:300])
        tf = fold(own_text(row.path)) if row else ""
        qs = all_quotes(res)
        bad = [q for q in qs if not quote_in(q, tf)]
        check("R8 her sözleşme alıntısı belgede", bool(qs) and not bad, f"{len(qs)} alıntı, {len(bad)} bulunamadı {bad[:2]}")
        check("R11 sözleşme sonucunda teknoloji adı yok", not any(t in json.dumps(res, ensure_ascii=False).lower() for t in TECH))
        s, acc = http("POST", f"/api/v1/editorial/contracts/extracts/{ex['id']}/accepted", {"fields": ["advance", "rates.karton"], "key": "kabul-deneme"})
        with eng.connect() as c:
            r2 = c.execute(sa.text("SELECT accepted_json, contract_key FROM semantic_contract_extracts WHERE id = :i"), {"i": ex["id"]}).first()
        check("R9 kabul kaydı", s == 200 and r2 is not None and json.loads(r2.accepted_json) == ["advance", "rates.karton"] and r2.contract_key == "kabul-deneme")

    with eng.connect() as c:
        kinds = {r[0] for r in c.execute(sa.text("SELECT kind FROM semantic_audit WHERE actor = 'timasai' AND at >= :t AND kind IN "
                                                 "('application_preread', 'contract_document')"), {"t": t_start})}
    check("R10 değişiklik kaydı", kinds == {"application_preread", "contract_document"}, ", ".join(sorted(kinds)))

    # ------------------------------------------------ R12: gerçek başvuru (isteğe bağlı; yalnız ön okuma kaydı yazılır)
    if a.app_id:
        s, info = http("GET", f"/api/v1/editorial/applications/{a.app_id}/preread")
        fid = next((x["id"] for x in (info or {}).get("files") or [] if x.get("readable")), None) if s == 200 else None
        if fid:
            s, st = http("POST", f"/api/v1/editorial/applications/{a.app_id}/preread", {"fileId": fid})
            if s == 200 and not st.get("already"):
                created["onokuma"].append(st["preread"]["id"])
            with eng.connect() as c:
                path = c.execute(sa.text("SELECT path FROM semantic_editorial_application_files WHERE id = :i"), {"i": fid}).scalar()
            preread_checks(eng, a.app_id, path, " (gerçek)", False)
        else:
            check("R12 gerçek başvuruda okunabilir dosya", False, f"HTTP {s}")

    json.dump(created, open(a.out, "w"))
    n_ok = sum(1 for _, ok, _ in results if ok)
    print(f"\n{n_ok}/{len(results)} geçti · kimlikler {a.out}")
    return 0 if n_ok == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
