"""Ortak yapı taşı 4 (belge okuma + OCR) ve 5 (kitap benzerliği) ile öneri 9, 10, 20 — test sunucusunda gerçek uç ↔
bağımsız referans kabulü. Yerelde koşulmaz.

Referanslar köprünün hesabını kullanmaz: CRM doğrudan SQL (R1–R3), köprü veritabanı doğrudan SQL (R4–R7), OCR için
bilinen metin (R8–R9: metni görüntüye çizilmiş PDF üretilir, okunan kelimeler sayılır). Ekrana giden metinde teknoloji
adı yok (R10).

Yazma: yalnız soru kümeleme (`semantic_mq_clusters`, «öneri» durumunda; `--no-cluster` ile atlanır). Kümeye karar
verilmez. Kimlikler `--out` dosyasına yazılır, `temizlik.py` siler.
Ortam: BASE (yan port köprüsü), COOKIE (timasai'nin 15 dk'lık oturumu), SEMANTIC_STORE_DSN (köprü veritabanı),
SEMANTIC_CRM_CONNECTION_FILE (CRM bağlantısı), CRM_SCHEMA (varsayılan Timas_MSCRM.dbo), PYTHONPATH=<aday ağaç>/backend.
Kullanım: python kabul.py --out /tmp/claude-benzerlik/kabul.json [--no-cluster]
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import time
import urllib.error
import urllib.parse
import urllib.request

import sqlalchemy as sa

BASE = os.environ.get("BASE", "http://127.0.0.1:8798").rstrip("/")
COOKIE = os.environ.get("COOKIE", "")
SCHEMA = os.environ.get("CRM_SCHEMA", "Timas_MSCRM.dbo")
TECH = ("qwen", "vllm", "dots", "deepseek", "tesseract", "bge", "llama", "openai", "dil modeli")
results: list[tuple[str, bool, str]] = []


def http(method: str, path: str, body=None, timeout=900):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(BASE + path, data=data, method=method, headers={"Cookie": COOKIE, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw[:1] in (b"{", b"[") else raw)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, raw


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(("GEÇTİ " if ok else "KALDI ") + name + (f" — {detail}" if detail else ""), flush=True)


def crm_rows(sql: str) -> list[dict]:
    from semantic_layer.profiler.connectors import connector_from_file

    conn = connector_from_file(os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json"))
    try:
        _, rows, _ = conn.execute(sql, 2_000_000)
        return rows
    finally:
        conn.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--no-cluster", action="store_true")
    a = ap.parse_args()
    eng = sa.create_engine(os.environ["SEMANTIC_STORE_DSN"])
    created: dict[str, list] = {"kume": []}
    p = SCHEMA + "."

    # ------------------------------------------------ R1: dizin kapsamı ↔ CRM etkin kitap sayısı (doğrudan SQL)
    crm_n = int(list(crm_rows(f"SELECT COUNT(*) AS n FROM {p}new_kitapBase WHERE statecode = 0 AND new_Tip = 1")[0].values())[0])
    s, st = http("GET", "/api/v1/books/similar/status")
    with eng.connect() as c:
        idx_n = c.execute(sa.text("SELECT COUNT(*) FROM semantic_book_embeddings WHERE aktif")).scalar()
    check("R1 dizin = CRM etkin kitap", s == 200 and st.get("kitap") == crm_n == idx_n,
          f"CRM {crm_n} · tablo {idx_n} · uç {st.get('kitap') if isinstance(st, dict) else s}")

    # ------------------------------------------------ R2: 5 kitabın adı/stok kodu CRM ile birebir
    with eng.connect() as c:
        sample = [dict(r._mapping) for r in c.execute(sa.text(
            "SELECT kitap_id, stok_kodu, ad FROM semantic_book_embeddings WHERE aktif AND stok_kodu IS NOT NULL"))]
    random.seed(28)
    pick = random.sample(sample, min(5, len(sample)))
    for r in pick:
        ref = crm_rows(f"SELECT new_name AS ad, new_StokKodu AS stok FROM {p}new_kitapBase WHERE new_kitapId = '{r['kitap_id']}'")
        ok = bool(ref) and " ".join(str(ref[0]["ad"]).split()) == r["ad"] and str(ref[0]["stok"]).strip() == r["stok_kodu"]
        check(f"R2 kitap kartı {r['stok_kodu']}", ok, r["ad"])

    # ------------------------------------------------ R3: M15 emsal adayı — emsali olmayan kitap, aday kendisi değil, stoklu
    no_emsal = crm_rows(
        f"SELECT TOP 3 k.new_StokKodu AS stok FROM {p}new_kitapBase k WHERE k.statecode = 0 AND k.new_Tip = 1"
        f" AND k.new_StokKodu IS NOT NULL AND k.new_ozet IS NOT NULL AND NOT EXISTS (SELECT 1 FROM {p}new_new_kitap_new_emsalkitap3Base e"
        f" WHERE e.new_kitapidOne = k.new_kitapId) ORDER BY k.new_ilkyayintarihi DESC")
    for r in no_emsal:
        stok = str(r["stok"]).strip()
        s, out = http("GET", f"/api/v1/marketing/books/{urllib.parse.quote(stok)}/emsal-adaylari?n=10")
        ok = s == 200 and out.get("gerekli") and out.get("items") and all(x["stokKodu"] and x["stokKodu"] != stok for x in out["items"])
        check(f"R3 emsal adayı {stok}", bool(ok), f"HTTP {s} · {len((out or {}).get('items') or []) if isinstance(out, dict) else ''} aday")

    # ------------------------------------------------ R4: M39 emsal bul — anlamla eklenen adaylar TİMAŞ kitabı, satış tablodan
    with eng.connect() as c:
        base = c.execute(sa.text("SELECT crm_id, stok_kodu FROM semantic_pazar_own_books WHERE ozet_kisa IS NOT NULL ORDER BY crm_id LIMIT 1")).first()
    s, out = http("POST", "/api/v1/pazar/comparables", {"crmKitapId": base.crm_id})
    added = [x for x in (out.get("timas") or []) if any("anlamca yakın" in g for g in x.get("gerekce") or [])] if s == 200 else []
    ok = s == 200 and out["counts"].get("anlamAday", 0) > 0
    with eng.connect() as c:
        for x in added[:5]:
            row = c.execute(sa.text("SELECT 1 FROM semantic_pazar_own_books WHERE crm_id = :i"), {"i": x["id"]}).first()
            ok = ok and row is not None
            if x.get("satis") and x.get("stokKodu"):
                ref = c.execute(sa.text("SELECT ytd_adet FROM semantic_pazar_own_sales WHERE boyut = 'stok' AND anahtar = :k "
                                        "AND yil = (SELECT MAX(yil) FROM semantic_pazar_own_sales)"), {"k": x["stokKodu"]}).scalar()
                ok = ok and abs(float(ref or 0) - float(x["satis"]["adet"])) < 0.5
    check("R4 emsal bul anlam genişletme", bool(ok), f"anlam adayı {out.get('counts', {}).get('anlamAday') if isinstance(out, dict) else s}, eklenen {len(added)}")

    # ------------------------------------------------ R5–R7: M50 soru kümeleri ↔ sl_query_log (doğrudan SQL)
    if not a.no_cluster:
        s, out = http("POST", "/api/v1/model-quality/clusters/build")
        check("R5 kümeleme başladı", s == 202, str(out)[:200])
        for _ in range(120):
            time.sleep(10)
            s, lst = http("GET", "/api/v1/model-quality/clusters")
            if s == 200 and not lst["job"]["running"]:
                break
        created["kume"] = [x["id"] for x in lst.get("items") or []]
        with eng.connect() as c:
            members = c.execute(sa.text("SELECT m.cluster_id, m.query_id, l.answer_type, l.error, l.executed, l.row_count "
                                        "FROM semantic_mq_cluster_members m LEFT JOIN sl_query_log l ON l.id = m.query_id "
                                        "JOIN semantic_mq_clusters k ON k.id = m.cluster_id WHERE k.status = 'oneri'")).all()
            size = c.execute(sa.text("SELECT COALESCE(SUM(size), 0) FROM semantic_mq_clusters WHERE status = 'oneri'")).scalar()
        check("R6 küme boyutu = üye satırı", int(size) == len(members), f"{size} ↔ {len(members)}")
        non = ("CLARIFICATION", "INCOMPLETE_ANSWER", "DATA_UNAVAILABLE", "NON_SQL_QUERY", "SQL_INVALID", "DATA_SOURCE_UNAVAILABLE", "NOT_PERMITTED")
        bad = [m for m in members if not (m.answer_type in non or m.error or (m.executed and m.row_count == 0))]
        # Kullanıcının Kısmen/Yanlış dediği sorular da kümeye girer; bunlar geri bildirim tablosunda olmalı
        with eng.connect() as c:
            fb = {r[0] for r in c.execute(sa.text("SELECT query_id FROM semantic_mq_feedback WHERE verdict IN ('kismen','yanlis')"))}
        bad = [m for m in bad if m.query_id not in fb]
        check("R7 her üye başarısız soru", not bad, f"{len(bad)} uymayan")
        texts = json.dumps(lst, ensure_ascii=False).lower()
        check("R7b küme ekranında teknoloji adı yok", not any(re.search(r"(?<![a-z])" + t, texts) for t in TECH))

    # ------------------------------------------------ R8–R9: OCR — bilinen metin, görüntü PDF (köprünün doc_read yolu)
    import pymupdf  # test sunucusunda köprü ortamında yoksa: pip install pymupdf (yalnız kabul için)
    from semantic_bridge import doc_read as DR

    known = ("Teknik şartname gereği yüklenici kırk beş gün içinde numune teslim edecektir. Gecikme halinde günlük "
             "binde üç ceza uygulanır. Yerli malı belgesi istenmektedir.")
    doc = pymupdf.open()
    pg = doc.new_page()
    pg.insert_textbox(pymupdf.Rect(50, 60, 540, 400), known, fontsize=13)
    pix = pg.get_pixmap(matrix=pymupdf.Matrix(2, 2))
    scan = pymupdf.open()
    sp = scan.new_page(width=pg.rect.width, height=pg.rect.height)
    sp.insert_image(sp.rect, pixmap=pix)
    text_page = scan.new_page()
    text_page.insert_textbox(pymupdf.Rect(50, 60, 540, 400), known, fontsize=11)
    t0 = time.time()
    r = DR.read("kabul-sartname.pdf", scan.tobytes())
    words = set(DR.fold(known).split())
    got = set(DR.fold(r.pages[0]["metin"]).split()) if r.pages and r.pages[0].get("metin") else set()
    share = len(words & got) / len(words)
    check("R8 taranmış sayfa OCR ile okundu", r.pages[0]["okuma"] == "ocr" and share >= 0.9,
          f"kelime isabeti %{round(share * 100)} · güven {r.pages[0].get('guven')} · {round(time.time() - t0)} sn · {r.errors}")
    check("R9 metin katmanlı sayfa katmandan", len(r.pages) == 2 and r.pages[1]["okuma"] == "metin"
          and DR.find_quote("günlük binde üç ceza uygulanır", r) is not None)
    check("R10 okuma özetinde teknoloji adı yok", not any(t in json.dumps(r.summary(), ensure_ascii=False).lower() for t in TECH))

    with open(a.out, "w") as f:
        json.dump(created, f)
    ok = sum(1 for x in results if x[1])
    print(f"== {ok}/{len(results)} geçti")
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
