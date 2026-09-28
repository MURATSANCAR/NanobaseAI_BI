#!/usr/bin/env python3
"""M19 Pazarlama görsel ve metin — kabul (test sunucusu + GPU stüdyosu + gerçek CRM .28). Mac'te koşulmaz.

Koşum (test sunucusunda, köprünün env'iyle; `TIMAS_SESSION` = timasai hesabının 15 dk'lık oturum çerezi — test
bitince oturum satırı silinir, AGENTS.md «Test kullanıcısı ve test verisi bırakılmaz»):

    cd <köprü kaynağı>/backend && set -a && . /etc/nanobase/semantic-bridge.env && set +a \\
      && TIMAS_SESSION=<çerez> python3 ../scripts/acceptance/marketing-creative/accept.py \\
         --base http://127.0.0.1:8795 [--stok 15201.01.XXXX] [--write] [--dist /data/nanobaseai/bi/cockpit/dist]

Yalnız okuma (varsayılan) ve yazma (`--write`: bir talep açar, dizer, Zeki AI metni yazar, onay dener; kampanya adı
`KABUL-M19-<zaman>`). Yazmadan sonra temizlik şart: `python3 cleanup.py --evidence <kanıt.json>`.

Doğrudan-SQL referansları (uygulamanın SQL'i yeniden çalıştırılmaz; ayrı yazılmış sorgu, ayrı normalleştirme):
  R1 kitap kartı: CRM `new_kitapBase` ad, yazar, hashtag, en önemli cümle = API `/books/{stok}` (karakter karakter).
  R2 kitap araması: CRM'de eşleşen etkin kart sayısı = API `/books?q=` toplamı.
  R3 arşiv: `semantic_mkt_creative_assets` onaylı güncel varlık sayısı (stok kodu) = API arşiv toplamı = zip dosya sayısı.
  R4 alıntı: her metin varyantındaki alıntı CRM metin alanlarında (bu betiğin normalleştirmesiyle) birebir geçer.
  R5 hashtag: CRM `new_hastag` etiketleri üretilen hashtag setinin başında.
  R6 kapak özeti: talebe kaydedilen kapak özeti = stüdyodaki kitapsız işin kaydettiği kaynak özeti.
Diğer denetimler: her biçim tam piksel ölçüsünde (PIL), sınırı aşan metin varyantı 0, aynı kişi iki onay → 409,
her onay `semantic_audit`'te, lisans taslağının adı TASLAK-, ekran/dosya adında teknoloji adı 0, geçersiz gövde 4xx.

Ölçülecek (bu betik kapsamaz): rolsüz hesapla 403 (yalnız timasai var; test sunucusunda «Herkes» rolü her şeyi
içeriyor — M10 notu), GPU gateway kaydında görsel model devri olmaması (GPU'da: `journalctl -u editor-gateway
--since <başlangıç> | grep -ci image` = 0).
Çıktı: /data/nanobaseai/bi/logs/accept-m19-<zaman>.json (kanıt; temizlik bu dosyadaki kimlikleri siler).
"""
from __future__ import annotations

import argparse
import html
import io
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))

LOGS = Path("/data/nanobaseai/bi/logs")
CRM_FILE = os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json")
SIZES = {"kare": (1080, 1080), "dikey": (1080, 1920), "yatay": (1200, 628), "dikey-gonderi": (1080, 1350),
         "kare-1200": (1200, 1200), "banner-300x250": (300, 250), "banner-728x90": (728, 90),
         "banner-160x600": (160, 600), "banner-320x50": (320, 50), "site-bandi": (1920, 600), "e-bulten": (600, 200)}
TECH = re.compile(r"qwen|vllm|temporal|pillow|typst|timesfm|real-?esrgan|ghostscript|stable diffusion|flux|openai|gpt-|"
                  r"llama|mistral|comfyui|diffusers|pymupdf", re.I)


class Api:
    def __init__(self, base: str, cookie: str, token: str):
        self.base = base.rstrip("/")
        self.headers = {"Cookie": f"timas_session={cookie}"}
        if token:
            self.headers["X-Semantic-Caller"] = token

    def call(self, method: str, path: str, body: Any = None, raw: bool = False) -> tuple[int, Any, dict]:
        data = None if body is None else json.dumps(body).encode()
        h = dict(self.headers)
        if body is not None:
            h["Content-Type"] = "application/json"
        req = urllib.request.Request(self.base + path, data=data, headers=h, method=method)
        try:
            with urllib.request.urlopen(req, timeout=900) as res:
                payload, code, hdr = res.read(), res.status, dict(res.headers)
        except urllib.error.HTTPError as e:
            payload, code, hdr = e.read(), e.code, dict(e.headers)
        if raw:
            return code, payload, hdr
        try:
            return code, json.loads(payload.decode() or "null"), hdr
        except ValueError:
            return code, payload.decode(errors="replace"), hdr


def crm_rows(sql: str) -> list[dict[str, Any]]:
    from semantic_layer.profiler.connectors import connector_from_file
    conn = connector_from_file(CRM_FILE)
    try:
        _, rows, _ = conn.execute(sql, 100_000)
        return [{str(k).lower(): v for k, v in r.items()} for r in rows]
    finally:
        conn.close()


def lit(s: str) -> str:
    return str(s).replace("'", "''")


def ref_text(v: Any) -> str:
    """Bu betiğin kendi normalleştirmesi (uygulamanın strip_html'inden bağımsız): etiket at, varlık çöz, boşluk tekle."""
    t = html.unescape(re.sub(r"<[^>]*>", " ", str(v or ""))).replace("\xa0", " ")
    return re.sub(r"\s+", " ", t).strip()


def fold(s: str) -> str:
    s = unicodedata.normalize("NFC", s or "").replace("İ", "i").replace("I", "ı")
    for a, b in (("’", "'"), ("‘", "'"), ("“", '"'), ("”", '"'), ("«", '"'), ("»", '"'), ("…", "..."), ("–", "-"), ("—", "-")):
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", s).strip().casefold()


def wait(api: Api, rid: str, limit: int = 1800) -> dict:
    t0 = time.time()
    while time.time() - t0 < limit:
        _, d, _ = api.call("GET", f"/api/v1/marketing/creative/requests/{rid}")
        if isinstance(d, dict) and not any(j["durum"] == "suruyor" for j in d.get("isler", [])):
            return d
        time.sleep(3)
    raise TimeoutError("iş bitmedi")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="http://127.0.0.1:8795")
    ap.add_argument("--stok", default="")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--dist", default="")
    args = ap.parse_args()
    cookie = os.environ.get("TIMAS_SESSION", "")
    if not cookie:
        print("TIMAS_SESSION gerekli (timasai 15 dk'lık oturum çerezi)")
        return 2
    api = Api(args.base, cookie, os.environ.get("SEMANTIC_CALLER_TOKEN", ""))
    P = "/api/v1/marketing/creative"
    schema = os.environ.get("CRM_SCHEMA", "Timas_MSCRM.dbo")
    ev: dict[str, Any] = {"started": datetime.now().isoformat(), "base": args.base, "checks": [], "created": {}}

    def check(name: str, ok: bool, **detail: Any) -> None:
        ev["checks"].append({"name": name, "ok": bool(ok), **detail})
        print(("GEÇTİ " if ok else "KALDI ") + name, json.dumps(detail, ensure_ascii=False, default=str)[:400])

    stok = args.stok or crm_rows(
        f"SELECT TOP 1 new_StokKodu AS s FROM {schema}.new_kitapBase WHERE statecode = 0 AND new_StokKodu IS NOT NULL"
        " AND new_hastag IS NOT NULL AND new_kitabinenonemlicumlesi IS NOT NULL ORDER BY ModifiedOn DESC")[0]["s"]
    ev["stok"] = stok

    # R1 kitap kartı
    ref = crm_rows(f"SELECT TOP 1 new_name AS ad, new_yazartext AS yazar, new_hastag AS hashtag,"
                   f" CAST(new_kitabinenonemlicumlesi AS nvarchar(max)) AS onemli, CAST(new_alintlar AS nvarchar(max)) AS alinti,"
                   f" CAST(new_ozet AS nvarchar(max)) AS ozet, CAST(new_kitapspotu AS nvarchar(max)) AS spot,"
                   f" CAST(new_sosyalmedyametni AS nvarchar(max)) AS sosyal"
                   f" FROM {schema}.new_kitapBase WHERE new_StokKodu = N'{lit(stok)}' ORDER BY statecode, ModifiedOn DESC")[0]
    code, b, _ = api.call("GET", f"{P}/books/{urllib.parse.quote(stok)}")
    k = (b or {}).get("kitap") or {}
    check("R1 kitap kartı (CRM = API)", code == 200 and ref_text(ref["ad"]) == ref_text(k.get("ad"))
          and ref_text(ref["yazar"]) == ref_text(k.get("yazar")) and ref_text(ref["hashtag"]) == ref_text(k.get("hashtag"))
          and ref_text(ref["onemli"]) == ref_text(k.get("onemli_cumle")), status=code, crm=ref["ad"], api=k.get("ad"))

    # R2 kitap araması
    q = (ref["ad"] or "").split()[0]
    qq = lit(q).replace("[", "[[]").replace("%", "[%]").replace("_", "[_]")
    n_ref = crm_rows(f"SELECT COUNT(*) AS n FROM {schema}.new_kitapBase WHERE statecode = 0 AND new_StokKodu IS NOT NULL"
                     f" AND (new_name LIKE N'%{qq}%' OR new_StokKodu LIKE N'%{qq}%' OR new_isbn13 LIKE N'%{qq}%')")[0]["n"]
    code, s, _ = api.call("GET", f"{P}/books?q={urllib.parse.quote(q)}")
    check("R2 kitap araması toplamı", code == 200 and int(s["total"]) == int(n_ref), q=q, crm=n_ref, api=(s or {}).get("total"))

    # Geçersiz gövdeler (yazma yok)
    c1, _, _ = api.call("POST", f"{P}/requests", {})
    c2, _, _ = api.call("POST", f"{P}/requests/MC-1900-0001/produce", {})
    c3, _, _ = api.call("POST", f"{P}/assets/{'0' * 32}/approve", {"seviye": "mesaj"})
    check("geçersiz gövde 4xx", 400 <= c1 < 500 and c2 == 404 and c3 == 404, codes=[c1, c2, c3])

    code, meta, _ = api.call("GET", f"{P}/meta")
    tech_hits = TECH.findall(json.dumps(meta, ensure_ascii=False))

    if args.write:
        tag = f"KABUL-M19-{datetime.now():%Y%m%d%H%M%S}"
        code, r, _ = api.call("POST", f"{P}/requests", {
            "stokKodu": stok, "kanal": "instagram", "formatlar": list(SIZES), "metinTurleri": ["aciklama", "baslik", "hashtag"],
            "kampanya": tag, "brief": "Kabul testi (otomatik; test sonunda silinir)."})
        check("talep açıldı", code == 201, status=code, body=r if code != 201 else None)
        if code != 201:
            return finish(ev)
        rid = r["id"]
        ev["created"] = {"request": rid, "kampanya": tag}
        api.call("POST", f"{P}/requests/{rid}/produce", {})
        d = wait(api, rid)
        job = next(j for j in d["isler"] if j["tur"] == "gorsel")
        ev["created"]["studioJob"] = d.get("studioJob")
        visuals = [a for a in d["varliklar"] if a["tur"] == "gorsel"]
        bad = []
        from PIL import Image
        for a in visuals:
            c, png, _ = api.call("GET", f"{P}/assets/{a['id']}/file", raw=True)
            size = Image.open(io.BytesIO(png)).size if c == 200 else None
            if size != SIZES.get(a["format"]):
                bad.append({"format": a["format"], "size": size})
        check("her biçim tam piksel ölçüsünde", job["durum"] == "bitti" and visuals and not bad,
              uretilen=len(visuals), atlanan=(job.get("sonuc") or {}).get("atlanan"), yanlis=bad, hata=job.get("hata"))
        drafts = [a for a in visuals if a["taslakLisans"]]
        check("lisans taslağı adı TASLAK-", all(a["dosyaAdi"].startswith("TASLAK-") for a in drafts)
              and not any(a["dosyaAdi"].startswith("TASLAK-") for a in visuals if not a["taslakLisans"]), taslak=len(drafts))

        # R6 kapak özeti (kitapsız iş)
        if d.get("studioKind") == "pazarlama":
            from semantic_bridge import editorial_studio as es
            base, headers, ca = es._base()
            with es._client(ca) as cl:
                sj = cl.get(f"{base}/v1/studio/marketing-jobs/{d['studioJob']}", headers=headers).json()
            kap = d.get("kapak") or {}
            check("R6 kapak özeti (talep = stüdyo işi)", bool(kap.get("sha256"))
                  and (sj.get("cover") or {}).get("source_sha256") == kap.get("sha256"),
                  talep=kap.get("sha256"), studyo=(sj.get("cover") or {}).get("source_sha256"), kaynak=kap.get("kaynak"))

        api.call("POST", f"{P}/requests/{rid}/copy", {"turler": ["aciklama", "baslik", "hashtag"]})
        d = wait(api, rid)
        texts = [a for a in d["varliklar"] if a["tur"] == "metin"]
        lim = meta["sinirlar"]
        over = [a["id"] for a in texts if (lim.get(a["format"] or "", {}).get(a["metinTuru"] or "", {}) or {}).get("sinir")
                and len(a["metin"] or "") > lim[a["format"]][a["metinTuru"]]["sinir"]]
        check("sınırı aşan metin varyantı 0", texts and not over, metin=len(texts), asan=over,
              elenen=(next(j for j in d["isler"] if j["tur"] == "metin").get("sonuc") or {}).get("elenen"))
        src = fold(" ".join(ref_text(ref[x]) for x in ("ad", "yazar", "onemli", "alinti", "ozet", "spot", "sosyal")))
        quotes = [(a["id"], m.group(1)) for a in texts for m in re.finditer(r"[“«\"]([^”»\"]{12,})[”»\"]", a["metin"] or "")]
        missing = [x for x in quotes if fold(x[1].strip(" \"'“”«»")) not in src]
        check("R4 alıntılar CRM metninde birebir", not missing, alinti=len(quotes), bulunamayan=missing)
        tags = next((a["metin"] for a in texts if a["metinTuru"] == "hashtag"), "")
        crm_tags = [("#" + t.lstrip("#")) for t in re.split(r"[\s,;]+", ref_text(ref["hashtag"])) if len(t.lstrip("#")) >= 2]
        check("R5 CRM hashtag'i sette önce", [fold(t) for t in tags.split()[:len(crm_tags)]] == [fold(t) for t in crm_tags],
              crm=crm_tags, set=tags)

        # onay: aynı kişi iki onay → 409; metin mesaj onayı → arşiv
        a = next((x for x in visuals if x["format"] == "kare"), None)
        if a:
            c1, _, _ = api.call("POST", f"{P}/assets/{a['id']}/approve", {"seviye": "tasarim"})
            c2, _, _ = api.call("POST", f"{P}/assets/{a['id']}/approve", {"seviye": "mesaj"})
            check("aynı kişi tasarım + mesaj → 409", c1 == 200 and c2 == 409, codes=[c1, c2])
        t_ok = next((x for x in texts if (x.get("dogrulama") or {}).get("durum") != "hata"), None)
        if t_ok:
            c, _, _ = api.call("POST", f"{P}/assets/{t_ok['id']}/approve", {"seviye": "mesaj"})
            check("metin mesaj onayı", c == 200, status=c)
        import sqlalchemy as sa
        from semantic_layer.config import SemanticSettings
        from semantic_layer.store.catalog_store import open_store
        eng = open_store(SemanticSettings.from_env().store_dsn, create=False).engine
        with eng.connect() as c:
            n_db = c.execute(sa.text("SELECT COUNT(*) FROM semantic_mkt_creative_assets WHERE stok_kodu = :s AND request_id = :r"
                                     " AND mesaj_onay IS NOT NULL AND guncel = :t AND red_zaman IS NULL"),
                             {"s": stok, "r": rid, "t": True}).scalar()
            ids = [x["id"] for x in d["varliklar"]] + [rid]
            n_audit = c.execute(sa.text("SELECT COUNT(*) FROM semantic_audit WHERE kind LIKE 'mkt_creative%'"
                                        " AND action = 'approve' AND object_id IN :ids").bindparams(
                sa.bindparam("ids", expanding=True)), {"ids": ids}).scalar()
        code, arc, _ = api.call("GET", f"{P}/assets?stok={urllib.parse.quote(stok)}&etiket={urllib.parse.quote(tag)}&durum=onayli")
        zc, zb, _ = api.call("GET", f"{P}/requests/{rid}/zip", raw=True)
        n_zip = len([n for n in zipfile.ZipFile(io.BytesIO(zb)).namelist() if n != "OKUYUN.txt"]) if zc == 200 else 0
        check("R3 arşiv = DB = zip", int(n_db) == int(arc["total"]) == n_zip, db=n_db, api=arc.get("total"), zip=n_zip)
        check("onaylar değişiklik kaydında", int(n_audit) >= (2 if t_ok and a else 1), audit=n_audit)
        names = " ".join(x["dosyaAdi"] for x in d["varliklar"]) + json.dumps(d, ensure_ascii=False)
        tech_hits += TECH.findall(names)

    if args.dist:
        for p in Path(args.dist).rglob("*.js"):
            txt = p.read_text(errors="ignore")
            if "pazarlama/icerik" in txt or "Görsel ve metin" in txt:
                seg = txt[max(0, txt.find("Görsel ve metin") - 20000): txt.find("Görsel ve metin") + 60000]
                tech_hits += TECH.findall(seg)
    check("ekranda/dosya adında teknoloji adı 0", not tech_hits, bulunan=sorted(set(tech_hits)))
    return finish(ev)


def finish(ev: dict) -> int:
    ev["finished"] = datetime.now().isoformat()
    ok = all(c["ok"] for c in ev["checks"])
    LOGS.mkdir(parents=True, exist_ok=True)
    out = LOGS / f"accept-m19-{datetime.now():%Y%m%d-%H%M%S}.json"
    out.write_text(json.dumps(ev, ensure_ascii=False, indent=1, default=str))
    print(f"{sum(c['ok'] for c in ev['checks'])}/{len(ev['checks'])} geçti · kanıt {out}")
    if ev.get("created"):
        print(f"TEMİZLİK ŞART: python3 {Path(__file__).with_name('cleanup.py')} --evidence {out}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
