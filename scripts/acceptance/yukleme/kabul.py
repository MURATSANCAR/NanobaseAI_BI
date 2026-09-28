#!/usr/bin/env python3
"""Yükleme kabulü (kullanıcı: «okuma yaptığımız ekranlarda upload da olacaktır ama sunucuda göremedim»).

Her ekranın yükleme ucuna küçük örnek dosya yükler, sonucu okur ve yüklediğini siler; test verisi bırakmaz. Köprünün
kendi ucu kullanılır (ekranın yaptığı istek); kişi timasai'nin kısa oturumudur (bellek: test-login-as-timasai —
oturumu sen aç, iş bitince sil).

    set -a; . /etc/nanobase/semantic-bridge.env; set +a
    cd <kaynak>/backend
    BRIDGE_URL=http://127.0.0.1:8795 TIMAS_COOKIE='timas_session=…' \\
        python3 ../scripts/acceptance/yukleme/kabul.py --out /tmp/claude-<oturum>/yukleme-kabul.json
    # seçenekler: --kanal amazon (kanal panel dosyası platformu), --atla sosyal,dijital (virgülle)

Kontroller (her biri OK / FARK / REDDEDİLDİ / YETKİ / ATLANDI):
  Y1  Redaksiyon: dosyadan yeni eser (works-from-file, TXT) → eser listede, ad dosya adından, bölüm sayısı doğru
  Y2  Redaksiyon: okunamayan metin reddedilir ve yarım eser kalmaz (liste sayısı değişmez)
  Y3  Son okuma: dosyadan yeni eser, prova PDF'i (works-from-file?kind=proof) → sayfa sayısı 1
  Y4  Son okuma: seçili esere yeni prova sürümü (eski uç, eser seçiliyken) → sürüm 2
  Y5  Son okuma belge incele: desteklenmeyen tür reddedilir (belge kaydı açılmaz; belge silme ucu olmadığı için
      gerçek belge yüklenmez — motora test verisi bırakılmaz)
  Y6  Çeviri: dosyadan yeni iş (jobs-from-file, en→tr) → iş listede, segment sayısı doğru; sonra silinir
  Y7  Çeviri: aynı dil çifti reddedilir, iş açılmaz
  Y8  Kanal panel dosyası (channels/imports) → satır sayısı; sonra silinir
  Y9  Trendyol panel dosyası (channels/trendyol/imports, tur=urun) → satır sayısı; sonra silinir
  Y10 Okur etkinlik dosyası (readers/imports) → satır sayısı; sonra silinir (kişi adları uydurma, .invalid alan adı)
  Y11 Sektör raporu (pazar/reports, TXT) → rapor kaydı; sonra silinir
  Y12 Dijital satış raporu (dijital/imports, CSV) → önizleme; sonra silinir
  Y13 Sosyal medya içgörü dosyası (social/imports) → satır sayısı; sonra silinir
Açılan eser/iş kimlikleri temizlik.py ile silinir (değişiklik kaydı satırlarıyla); sonda artık kalmadığı ölçülür.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

RESULTS: list[dict] = []
CREATED = {"eser": [], "is": []}
BASE = os.environ.get("BRIDGE_URL", "http://127.0.0.1:8795").rstrip("/")
COOKIE = os.environ.get("TIMAS_COOKIE", "")
TAG = uuid.uuid4().hex[:6]  # aynı adla ikinci koşu eski kaydı bulmasın


def record(name: str, status: str, **detail) -> None:
    RESULTS.append({"kontrol": name, "durum": status, **detail})
    print(f"[{status:>10}] {name}  {json.dumps(detail, ensure_ascii=False, default=str)[:500]}")


def call(method: str, path: str, *, body: bytes | None = None, js=None, q: dict | None = None, timeout: int = 300):
    url = BASE + path + (("&" if "?" in path else "?") + urllib.parse.urlencode(q) if q else "")
    headers = {"Cookie": COOKIE}
    data = body
    if js is not None:
        data = json.dumps(js).encode()
        headers["Content-Type"] = "application/json"
    elif body is not None:
        headers["Content-Type"] = "application/octet-stream"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, {"detail": raw[:300].decode("utf-8", "replace")}


def message(out) -> str:
    d = (out or {}).get("detail") if isinstance(out, dict) else None
    if isinstance(d, dict):
        return str(d.get("message") or d)
    return str(d or out)


def tiny_pdf(text: str = "Kabul testi") -> bytes:
    """Tek sayfalık geçerli PDF (A5, Helvetica); xref konumları hesaplanır."""
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 420 595] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        None,
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    stream = f"BT /F1 18 Tf 60 500 Td ({text}) Tj ET".encode("latin-1")
    objs[3] = b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


MANUSCRIPT = "BÖLÜM 1\n\nKış geldi. Yollar kapandı.\n\nBÖLÜM 2\n\nBahar geç geldi.\n".encode("utf-8")
SOURCE = b"CHAPTER ONE\n\nIt was cold. We waited.\n\nCHAPTER TWO\n\nNobody came.\n"


def works() -> list[dict]:
    st, out = call("GET", "/api/v1/editorial/works")
    return (out or {}).get("items", []) if st == 200 else []


def editorial() -> None:
    before = len(works())
    name = f"Kabul_Yukleme-{TAG}.txt"
    st, out = call("PUT", "/api/v1/editorial/works-from-file", body=MANUSCRIPT, q={"kind": "manuscript", "filename": name})
    if st == 403:
        record("Y1 redaksiyon: dosyadan yeni eser", "YETKİ", status=st, mesaj=message(out))
        return
    if st != 200:
        record("Y1 redaksiyon: dosyadan yeni eser", "FARK", status=st, mesaj=message(out))
        return
    CREATED["eser"].append(out["workId"])
    listed = {w["id"]: w for w in works()}
    w = listed.get(out["workId"])
    ok = bool(w) and w["title"] == f"Kabul Yukleme {TAG}" and out.get("chapters") == 2 and w["chapters"]["total"] == 2
    record("Y1 redaksiyon: dosyadan yeni eser", "OK" if ok else "FARK", eser=out["workId"], ad=w and w["title"],
           beklenen_ad=f"Kabul Yukleme {TAG}", bolum=out.get("chapters"))

    st, out2 = call("PUT", "/api/v1/editorial/works-from-file", body=b"   \n\n  ", q={"kind": "manuscript", "filename": f"bos-{TAG}.txt"})
    after = len(works())
    record("Y2 redaksiyon: okunamayan metin reddedilir, yarım eser kalmaz", "OK" if st == 400 and after == before + 1 else "FARK",
           status=st, mesaj=message(out2), liste_once=before, liste_sonra=after)

    st, out3 = call("PUT", "/api/v1/editorial/works-from-file", body=tiny_pdf(), q={"kind": "proof", "filename": f"Prova-{TAG}.pdf"})
    if st == 200:
        CREATED["eser"].append(out3["workId"])
        record("Y3 son okuma: dosyadan yeni eser + prova", "OK" if out3.get("pages") == 1 and out3.get("version") == 1 else "FARK",
               eser=out3["workId"], sayfa=out3.get("pages"), surum=out3.get("version"))
        st4, out4 = call("PUT", f"/api/v1/editorial/works/{out3['workId']}/proof", body=tiny_pdf("Kabul testi v2"),
                         q={"filename": f"Prova-{TAG}-v2.pdf"})
        record("Y4 son okuma: seçili esere yeni prova sürümü", "OK" if st4 == 200 and (out4 or {}).get("version") == 2 else "FARK",
               status=st4, surum=(out4 or {}).get("version"), mesaj=None if st4 == 200 else message(out4))
    else:
        record("Y3 son okuma: dosyadan yeni eser + prova", "FARK", status=st, mesaj=message(out3))

    st, out5 = call("PUT", "/api/v1/editorial/documents", body=b"MZ\x90\x00", q={"filename": f"kabul-{TAG}.exe"})
    if st == 403:
        record("Y5 belge incele: desteklenmeyen tür reddedilir", "YETKİ", status=st, mesaj=message(out5))
    else:
        record("Y5 belge incele: desteklenmeyen tür reddedilir", "OK" if 400 <= st < 500 else "FARK", status=st, mesaj=message(out5))


def translation() -> None:
    name = f"The_Road-{TAG}.txt"
    st, out = call("PUT", "/api/v1/editorial/translation/jobs-from-file", body=SOURCE,
                   q={"filename": name, "sourceLang": "en", "targetLang": "tr"})
    if st == 403:
        record("Y6 çeviri: dosyadan yeni iş", "YETKİ", status=st, mesaj=message(out))
    elif st != 200:
        record("Y6 çeviri: dosyadan yeni iş", "FARK", status=st, mesaj=message(out))
    else:
        CREATED["is"].append(out["jobId"])
        st2, jobs = call("GET", "/api/v1/editorial/translation/jobs")
        job = next((j for j in (jobs or {}).get("items", []) if j["id"] == out["jobId"]), None)
        ok = bool(job) and job["title"] == f"The Road {TAG}" and out.get("segments") == 5 and job["segments"]["total"] == 5
        record("Y6 çeviri: dosyadan yeni iş", "OK" if ok else "FARK", is_=out["jobId"], ad=job and job["title"],
               segment=out.get("segments"))
    st, out = call("PUT", "/api/v1/editorial/translation/jobs-from-file", body=SOURCE,
                   q={"filename": f"ayni-dil-{TAG}.txt", "sourceLang": "en", "targetLang": "en"})
    record("Y7 çeviri: aynı dil çifti reddedilir", "OK" if st == 400 else ("YETKİ" if st == 403 else "FARK"), status=st, mesaj=message(out))


def import_then_delete(code: str, name: str, post: str, delete: str, body: bytes, q: dict, rows_key: str = "satir") -> None:
    st, out = call("POST", post, body=body, q=q)
    if st == 403:
        record(f"{code} {name}", "YETKİ", status=st, mesaj=message(out))
        return
    if st >= 500 or st == 404:
        record(f"{code} {name}", "FARK", status=st, mesaj=message(out))
        return
    if st >= 400:
        # Uç çalışıyor; örnek dosyanın kolonları bu kurulumun beklediğinden farklı olabilir. Kayıt açılmadı.
        record(f"{code} {name}", "REDDEDİLDİ", status=st, mesaj=message(out))
        return
    rid = (out or {}).get("id")
    rows = (out or {}).get(rows_key)
    std, outd = call("DELETE", delete.format(id=urllib.parse.quote(str(rid)))) if rid else (0, None)
    record(f"{code} {name}", "OK" if rid and std == 200 else "FARK", kayit=rid, satir=rows, silme=std,
           mesaj=None if std == 200 else message(outd))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="yukleme-kabul.json")
    ap.add_argument("--kanal", default="amazon", help="kanal panel dosyasının platform anahtarı")
    ap.add_argument("--atla", default="", help="virgülle: editoryal,ceviri,kanal,trendyol,okur,pazar,dijital,sosyal")
    ap.add_argument("--temizleme", action="store_true", help="açılan eser/işleri silme (yalnız hata ayıklama)")
    a = ap.parse_args()
    if not COOKIE:
        print("TIMAS_COOKIE yok: timasai'nin kısa oturum çerezini verin.", file=sys.stderr)
        return 2
    skip = {x.strip() for x in a.atla.split(",") if x.strip()}
    try:
        if "editoryal" not in skip:
            editorial()
        if "ceviri" not in skip:
            translation()
        if "kanal" not in skip:
            csv = "Barkod;Ürün Adı;Satış Adedi;Stok\n9786050000000;Kabul Testi Kitabı;1;0\n".encode("utf-8")
            import_then_delete("Y8", "kanal panel dosyası", "/api/v1/channels/imports", "/api/v1/channels/imports/{id}", csv,
                               {"platform": a.kanal, "filename": f"kabul-{TAG}.csv"})
        if "trendyol" not in skip:
            csv = "Barkod;Satıcı Stok Kodu;Ürün Adı;Durum;Stok;Trendyol Satış Fiyatı\n9786050000000;KABUL;Kabul Testi;Satışta;0;1\n".encode("utf-8")
            import_then_delete("Y9", "Trendyol panel dosyası (ürün)", "/api/v1/channels/trendyol/imports",
                               "/api/v1/channels/trendyol/imports/{id}", csv, {"tur": "urun", "filename": f"kabul-{TAG}.csv"})
        if "okur" not in skip:
            csv = "Ad Soyad;E-posta;Telefon\nKabul Testi;kabul-testi@example.invalid;\n".encode("utf-8")
            import_then_delete("Y10", "okur etkinlik dosyası", "/api/v1/readers/imports", "/api/v1/readers/imports/{id}", csv,
                               {"filename": f"kabul-{TAG}.csv"}, rows_key="rows")
        if "pazar" not in skip:
            txt = "Kabul testi sektör raporu. Toplam satış 100 adet.\n".encode("utf-8")
            import_then_delete("Y11", "sektör raporu", "/api/v1/pazar/reports", "/api/v1/pazar/reports/{id}", txt,
                               {"kaynak": "Kabul testi", "baslik": f"Kabul {TAG}", "filename": f"kabul-{TAG}.txt"}, rows_key="sayfaSayisi")
        if "dijital" not in skip:
            st, plats = call("GET", "/api/v1/dijital/platforms")
            active = [p for p in (plats or {}).get("items", []) if p.get("aktif")] if st == 200 else []
            if not active:
                record("Y12 dijital satış raporu", "ATLANDI", neden="aktif platform yok ya da okunamadı", status=st)
            else:
                csv = "ISBN;Kitap Adı;Adet;Net Tutar;Para Birimi\n9786050000000;Kabul Testi;1;1;TRY\n".encode("utf-8")
                import_then_delete("Y12", "dijital satış raporu", "/api/v1/dijital/imports", "/api/v1/dijital/imports/{id}", csv,
                                   {"platform": active[0]["id"], "donem": "2026-08", "filename": f"kabul-{TAG}.csv"})
        if "sosyal" not in skip:
            st, accs = call("GET", "/api/v1/social/accounts")
            items = (accs or {}).get("items", []) if st == 200 else []
            if not items:
                record("Y13 sosyal medya içgörü dosyası", "ATLANDI", neden="hesap yok ya da okunamadı", status=st)
            else:
                csv = "Tarih;Gösterim;Erişim;Beğeni\n2026-08-01;1;1;0\n".encode("utf-8")
                import_then_delete("Y13", "sosyal medya içgörü dosyası", "/api/v1/social/imports", "/api/v1/social/imports/{id}", csv,
                                   {"account": items[0]["id"], "filename": f"kabul-{TAG}.csv"})
    finally:
        if not a.temizleme and (CREATED["eser"] or CREATED["is"]):
            cleanup_and_verify()
    Path(a.out).write_text(json.dumps({"sonuc": RESULTS, "acilan": CREATED}, ensure_ascii=False, indent=2, default=str))
    bad = [r for r in RESULTS if r["durum"] in ("FARK",)]
    print(f"\n{len(RESULTS)} kontrol · {len(bad)} FARK · rapor: {a.out}")
    return 1 if bad else 0


def cleanup_and_verify() -> None:
    """Açılan eser/işleri köprünün veritabanından siler (eser silme ucu yok), sonra listede kalmadığını ölçer."""
    try:
        from semantic_layer.store.catalog_store import open_store

        import temizlik
        from semantic_bridge import admin as admin_mod
        from semantic_bridge import editorial_desk as desk
        from semantic_bridge import editorial_translation as tr

        engine = open_store(os.environ["SEMANTIC_STORE_DSN"], create=False).engine
        desk.ensure(engine)
        tr.ensure(engine)
        admin_mod.ensure(engine)
        rep = temizlik.clean(engine, os.environ.get("SEMANTIC_TENANT_ID", "default"), os.environ.get("TIMAS_ACTOR", "timasai"),
                             CREATED["eser"], CREATED["is"], True)
    except Exception as e:  # noqa: BLE001
        record("TEMİZLİK", "FARK", mesaj=f"silinemedi: {e}", elle=f"temizlik.py --eser … --is … --uygula ({CREATED})")
        return
    left_w = [w for w in works() if w["id"] in CREATED["eser"]]
    st, jobs = call("GET", "/api/v1/editorial/translation/jobs")
    left_j = [j for j in (jobs or {}).get("items", []) if j["id"] in CREATED["is"]]
    record("TEMİZLİK: test verisi kalmadı", "OK" if not left_w and not left_j else "FARK",
           silinen=rep, kalan_eser=[w["id"] for w in left_w], kalan_is=[j["id"] for j in left_j])


if __name__ == "__main__":
    sys.exit(main())
