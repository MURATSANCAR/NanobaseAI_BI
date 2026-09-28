"""M44 Lojistik ve kargo — gerçek API ↔ doğrudan SQL kabulü (test sunucusunda, yan port köprüsü, salt okunur kaynaklar).

Uçların kullanıcıya verdiği sonuç, köprü kodu kullanılmadan yazılmış doğrudan CRM/Logo sorgularıyla karşılaştırılır
(`referans.sql` R1–R8). Gönderi kartı için sipariş her koşuda CRM'den rastgele seçilir (sabit sipariş yok).
Yazma: yalnız bir taslak (gerçek sipariş, Zeki AI ya da kural metni) ve bir karar kaydı açılır; kimlikleri `--out`
dosyasına yazılır, `temizlik.py` siler (değişiklik kaydı dahil). Karar kaydı hemen API ile de silinir.

`--olcum`: ölçülmemiş varsayımları sayar (entegrasyon sonuç değer kümesi, kargo kaydı tarih biçimleri, iade/tahsilatlı
değerleri, kargo kaydının güncelliği, kargo kaydı ↔ sipariş takip no eşleşme payı); yazma yapmaz, API çağırmaz.

Ortam: BASE (ör. http://127.0.0.1:8798), COOKIE (timasai'nin kısa oturum çerezi), SEMANTIC_CONNECTION_FILE (Logo),
SEMANTIC_CRM_CONNECTION_FILE, PYTHONPATH=<aday ağaç>/backend. İsteğe bağlı M44_AY (mutabakat ayı, varsayılan önceki ay).
Kullanım: python kabul.py --out /tmp/claude-m44/kabul-kimlikler.json   |   python kabul.py --olcum
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from semantic_bridge import budget_sources as bsrc
from semantic_bridge import shipping as S
from semantic_bridge import shipping_sources as src

BASE = os.environ.get("BASE", "http://127.0.0.1:8798").rstrip("/")
COOKIE = os.environ.get("COOKIE", "")
P = BASE + "/api/v1/shipping"
SCHEMA = os.environ.get("CRM_SCHEMA", "Timas_MSCRM.dbo")
TZ = ZoneInfo("Europe/Istanbul")
results: list[tuple[str, bool, str]] = []
DATE_SQL = ("CAST(COALESCE(TRY_CONVERT(datetime, {c}, 104), TRY_CONVERT(datetime, {c}, 103), TRY_CONVERT(datetime, {c}, 120), "
            "TRY_CONVERT(datetime, {c}, 112)) AS date)")


def http(method: str, url: str, body=None, timeout=1800, raw=False):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method, headers={"Cookie": COOKIE, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            payload = r.read()
            if raw:
                return r.status, payload, r.headers.get("Content-Type", "")
            return r.status, (json.loads(payload) if payload[:1] in (b"{", b"[") else payload)
    except urllib.error.HTTPError as e:
        payload = e.read()
        try:
            out = json.loads(payload)
        except ValueError:
            out = payload
        return (e.code, out, "") if raw else (e.code, out)


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(("GEÇTİ " if ok else "KALDI ") + name + (f" — {detail}" if detail else ""), flush=True)
    if len(results) % 10 == 0:
        print(f"-- ara durum: {sum(1 for r in results if r[1])} geçti, {sum(1 for r in results if not r[1])} kaldı", flush=True)


def close(a, b, tol=0.01) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return abs(float(a) - float(b)) <= tol * max(1.0, abs(float(b)) * 1e-6 + 1)


def utc(d: date) -> str:
    return datetime(d.year, d.month, d.day, tzinfo=TZ).astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def fold(s) -> str:
    return S.fold(s) or "BELIRTILMEMIS"


def no_secret(obj) -> bool:
    text = json.dumps(obj, ensure_ascii=False).lower() if not isinstance(obj, (bytes, bytearray)) else obj.decode("utf-8", "ignore").lower()
    return not any(c in text for c in src.FORBIDDEN_COLUMNS) and "clientsecret" not in text


# ------------------------------------------------------------------ ölçüm (yazmaz)


def measure(crm) -> int:
    p = SCHEMA
    print("== Entegrasyon sonuç değerleri (son 365 gün, en sık 25; boş olmayan)")
    since = (date.today() - timedelta(days=365)).isoformat()
    for firm in ("aras", "ups", "mng", "akademi"):
        rows = crm(f"SELECT TOP 25 new_{firm}kargoentegrasyonsonucu AS v, COUNT(*) AS n FROM {p}.new_siparisBase "
                   f"WHERE statecode = 0 AND new_siparistarihi >= '{since}' AND ISNULL(new_{firm}kargoentegrasyonsonucu, '') <> '' "
                   f"GROUP BY new_{firm}kargoentegrasyonsonucu ORDER BY COUNT(*) DESC")
        print(f"  {firm}: " + "; ".join(f"{r['v']!r}={r['n']}" for r in rows))
    print("== Kargo kaydı tarih biçimleri (irsaliye / teslim; rakam→9 kalıbı, en sık 10)")
    for col in ("new_kargoirstarihi", "new_TeslimTarihi"):
        shapes = Counter()
        for r in crm(f"SELECT {col} AS v FROM {p}.new_kargobilgisiBase WHERE statecode = 0"):
            shapes[re.sub(r"\d", "9", str(r["v"] or "(boş)").strip())] += 1
        print(f"  {col}: " + "; ".join(f"{k!r}={v}" for k, v in shapes.most_common(10)))
    for col in ("new_iadedurumu", "new_tahsilatlikargo", "new_kargofirmasi", "new_satiskanali"):
        rows = crm(f"SELECT TOP 20 {col} AS v, COUNT(*) AS n FROM {p}.new_kargobilgisiBase WHERE statecode = 0 GROUP BY {col} ORDER BY COUNT(*) DESC")
        print(f"== {col}: " + "; ".join(f"{r['v']!r}={r['n']}" for r in rows))
    r = crm(f"SELECT COUNT(*) AS n, MAX(CreatedOn) AS son FROM {p}.new_kargobilgisiBase WHERE statecode = 0")[0]
    print(f"== Kargo kaydı: {r['n']} etkin, son oluşturma {r['son']}")
    # SQL Server toplama içinde alt sorgu kabul etmez (130): eşleşme önce satır başına işaretlenir, sonra sayılır.
    r = crm(f"SELECT COUNT(*) AS n, SUM(x.e) AS eslesen FROM (SELECT CASE WHEN EXISTS (SELECT 1 FROM {p}.new_siparisBase s "
            f"WHERE s.new_kargotakipno = b.new_KargoTakipNo) OR EXISTS (SELECT 1 FROM {p}.new_kargotakipbilgisiBase k "
            f"WHERE k.new_kargotakipnumarasi = b.new_KargoTakipNo) THEN 1 ELSE 0 END AS e "
            f"FROM {p}.new_kargobilgisiBase b WHERE b.statecode = 0 AND ISNULL(b.new_KargoTakipNo, '') <> '') x")[0]
    print(f"== Takip no ile siparişe bağlanan kargo kaydı: {r['eslesen']}/{r['n']}")
    rows = crm(f"SELECT CAST(new_siparistipi AS int) AS t, COUNT(*) AS n FROM {p}.new_siparisBase WHERE statecode = 0 AND statuscode = 100000000 "
               f"AND ISNULL(new_kargotakipno, '') = '' AND new_sevktarihi >= '{since}' GROUP BY CAST(new_siparistipi AS int) ORDER BY COUNT(*) DESC")
    print("== Takip no'suz sevk, sipariş tipine göre (365 gün): " + "; ".join(f"{src.ORDER_TYPE.get(r['t'], r['t'])}={r['n']}" for r in rows))
    rows = crm(f"SELECT f.new_name AS ad, f.new_kargokodu AS kod FROM {p}.new_kargofirmasiBase f")
    print("== Kargo firmaları (yalnız ad ve kod): " + "; ".join(f"{r['ad']} ({r['kod']})" for r in rows))
    return 0


# ------------------------------------------------------------------ kabul


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="")
    ap.add_argument("--olcum", action="store_true")
    a = ap.parse_args()
    crm = bsrc.runner(os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json"))
    if a.olcum:
        return measure(crm)
    if not a.out:
        ap.error("--out gerekli")
    logo = bsrc.runner(os.environ["SEMANTIC_CONNECTION_FILE"])
    created: dict[str, list[str]] = {"drafts": [], "decisions": []}
    p = SCHEMA

    # 0. Meta, geçersiz istekler (yazmadan önce), kimlik bilgisi yok.
    s, meta = http("GET", P + "/meta")
    check("meta 200", s == 200, str(s))
    if s != 200:
        return finish(a.out, created)
    check("meta'da kimlik bilgisi yok", no_secret(meta))
    check("geçersiz taslak türü 400", http("POST", P + "/drafts", {"tur": "x"})[0] == 400)
    check("geçersiz eşik 400", http("PUT", P + "/settings", {"bekleyenGun": 0})[0] in (400, 403))
    check("geçersiz ay 400", http("GET", P + "/reconcile?ay=2026-13")[0] in (400, 403))
    window = meta["ayarlar"]["pencereGun"]
    today = datetime.now(TZ).date()
    since = today - timedelta(days=window)

    # R1 · Sevk edilen.
    s, ov = http("GET", P + "/overview?yenile=true")
    check("overview 200", s == 200, str(s))
    if s == 200:
        st = ", ".join(str(x) for x in meta["ayarlar"]["sevkDurumlari"])
        ref = crm(f"SELECT COUNT(*) AS n FROM {p}.new_siparisBase WHERE statecode = 0 AND statuscode IN ({st}) AND new_sevktarihi >= '{utc(since)}'")[0]["n"]
        check("R1 son N gün sevk edilen = SQL", ov["sevk"]["adet"] == ref, f"API {ov['sevk']['adet']} · SQL {ref} · {window} gün")
        check("overview'da kimlik bilgisi yok", no_secret(ov))

    # R2 · Firma bazında desi başı maliyet (API'nin varsayılan dönemi).
    s, card = http("GET", P + "/carriers")
    check("carriers 200", s == 200, str(s))
    if s == 200:
        bas, bit = date.fromisoformat(card["baslangic"]), date.fromisoformat(card["bitis"]) + timedelta(days=1)
        dcol = DATE_SQL.format(c="new_kargoirstarihi")
        rows = crm(f"SELECT UPPER(LTRIM(RTRIM(new_kargofirmasi))) AS firma, COUNT(*) AS gonderi, "
                   f"SUM(TRY_CAST(REPLACE(new_Tutar, ',', '.') AS FLOAT)) AS tutar, SUM(TRY_CAST(REPLACE(new_desi, ',', '.') AS FLOAT)) AS desi "
                   f"FROM {p}.new_kargobilgisiBase WHERE statecode = 0 AND {dcol} >= '{bas}' AND {dcol} < '{bit}' "
                   f"GROUP BY UPPER(LTRIM(RTRIM(new_kargofirmasi)))")
        ref: dict[str, dict[str, float]] = {}
        for r in rows:
            k = fold(r["firma"])
            d = ref.setdefault(k, {"gonderi": 0, "tutar": 0.0, "desi": 0.0})
            d["gonderi"] += int(r["gonderi"])
            d["tutar"] += float(r["tutar"] or 0)
            d["desi"] += float(r["desi"] or 0)
        api = {fold(i["firma"]): i for i in card["items"]}
        check("R2 firma listesi = SQL", set(api) == set(ref), f"API {sorted(api)} · SQL {sorted(ref)}")
        for k, d in ref.items():
            i = api.get(k, {})
            check(f"R2 {k} gönderi", i.get("gonderi") == d["gonderi"], f"API {i.get('gonderi')} · SQL {d['gonderi']}")
            if card.get("maliyetGorunur"):
                db = d["tutar"] / d["desi"] if d["desi"] else None
                check(f"R2 {k} desi başı", close(i.get("desiBasi"), round(db, 2) if db is not None else None), f"API {i.get('desiBasi')} · SQL {db}")

    # R3 · Şube bazında sevk başı (C19).
    s, sube = http("GET", P + "/carriers?kirilim=sube")
    if s == 200 and sube.get("maliyetGorunur"):
        bas, bit = date.fromisoformat(sube["baslangic"]), date.fromisoformat(sube["bitis"]) + timedelta(days=1)
        dcol = DATE_SQL.format(c="new_kargoirstarihi")
        rows = crm(f"SELECT ISNULL(NULLIF(LTRIM(RTRIM(new_sevkiyatcikissubesi)), ''), N'Belirtilmemiş') AS sube, COUNT(*) AS gonderi, "
                   f"SUM(TRY_CAST(REPLACE(new_Tutar, ',', '.') AS FLOAT)) / NULLIF(SUM(TRY_CAST(REPLACE(new_sevkadeti, ',', '.') AS FLOAT)), 0) AS sb "
                   f"FROM {p}.new_kargobilgisiBase WHERE statecode = 0 AND {dcol} >= '{bas}' AND {dcol} < '{bit}' "
                   f"GROUP BY ISNULL(NULLIF(LTRIM(RTRIM(new_sevkiyatcikissubesi)), ''), N'Belirtilmemiş')")
        api = {re.sub(r"\s+", " ", i["sube"]).strip(): i for i in sube["items"]}
        bad = [r["sube"] for r in rows if not (api.get(re.sub(r"\s+", " ", r["sube"]).strip(), {}).get("gonderi") == r["gonderi"]
                                               and close(api.get(re.sub(r"\s+", " ", r["sube"]).strip(), {}).get("sevkBasi"),
                                                         round(r["sb"], 2) if r["sb"] is not None else None))]
        check("R3 şube bazında sevk başı maliyet = SQL (C19)", not bad and len(rows) == len(api), f"{len(rows)} şube; farklı: {bad[:5]}")
    else:
        check("R3 şube kırılımı okunabildi (maliyet yetkisiyle)", False, str(s))

    # R4 · Entegrasyon hatası.
    s, er = http("GET", P + "/errors?yenile=true")
    check("errors 200", s == 200, str(s))
    if s == 200:
        ok_values = S.settings_from(lambda k, d="": os.environ.get(k, d))["okValues"]
        rows = crm(f"SELECT new_siparisId AS id, new_araskargoentegrasyonsonucu AS aras_sonuc, CAST(new_araskargoentegrasyonmesaji AS nvarchar(max)) AS aras_mesaj, "
                   f"new_upskargoentegrasyonsonucu AS ups_sonuc, CAST(new_upskargoentegrasyonmesaji AS nvarchar(max)) AS ups_mesaj, "
                   f"new_mngkargoentegrasyonsonucu AS mng_sonuc, new_mngkargoentegrasyonmesaji AS mng_mesaj, "
                   f"new_akademikargoentegrasyonsonucu AS akademi_sonuc, CAST(new_akademikargoentegrasyonmesaji AS nvarchar(max)) AS akademi_mesaj "
                   f"FROM {p}.new_siparisBase WHERE statecode = 0 AND ISNULL(new_kargotakipno, '') = '' "
                   f"AND statuscode NOT IN (100000001, 100000003, 2, 1) AND new_siparistarihi >= '{since}'")
        n = 0
        for r in rows:
            for firm in ("aras", "ups", "mng", "akademi"):
                so, me = (r.get(f"{firm}_sonuc") or "").strip(), (r.get(f"{firm}_mesaj") or "").strip()
                if (so and S.fold(so) not in ok_values) or (not so and me and S.fold(me) not in ok_values):
                    n += 1
                    break
        check("R4 entegrasyon hatası sayısı = SQL", er["toplam"] == n, f"API {er['toplam']} · SQL {n} (OK değerleri ortam/varsayılan)")

    # R5 · Takip no'suz sevk.
    s, un = http("GET", P + "/untracked")
    if s == 200:
        st = ", ".join(str(x) for x in meta["ayarlar"]["takipsizDurumlar"])
        ex = meta["ayarlar"]["takipsizHaricTipler"]
        tip = f" AND ISNULL(CAST(new_siparistipi AS int), 0) NOT IN ({', '.join(str(x) for x in ex)})" if ex else ""
        ref = crm(f"SELECT COUNT(*) AS n FROM {p}.new_siparisBase WHERE statecode = 0 AND statuscode IN ({st}) "
                  f"AND ISNULL(new_kargotakipno, '') = '' AND new_sevktarihi >= '{since}'{tip}")[0]["n"]
        check("R5 takip numarasız sevk = SQL", un["toplam"] == ref, f"API {un['toplam']} · SQL {ref}")
    else:
        check("untracked 200", False, str(s))

    # R6 · Mutabakat: Logo sevk ↔ CRM sevkiyat.
    ay = os.environ.get("M44_AY") or (today.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    s, rec = http("GET", P + f"/reconcile?ay={ay}")
    check("reconcile 200", s == 200, str(s) if s != 200 else f"{ay}: {len(rec['items'])} firma")
    if s == 200 and rec.get("sevk"):
        a0, a1 = S.month_bounds(ay)
        firms = bsrc.firms_by_year(logo)
        f = firms[a0.year]
        lg = logo(f"SELECT S.STFICHEREF AS irs, MAX(I.FICHENO) AS no FROM dbo.LG_{f}_01_STLINE S "
                  f"LEFT JOIN dbo.LG_{f}_01_INVOICE I ON I.LOGICALREF = S.INVOICEREF AND S.INVOICEREF <> 0 "
                  f"WHERE S.CANCELLED = 0 AND S.LINETYPE = 0 AND S.TRCODE IN (7,8) AND S.IOCODE = 4 AND S.DATE_ >= '{a0}' AND S.DATE_ < '{a1}' "
                  f"GROUP BY S.STFICHEREF")
        cr = crm(f"SELECT new_faturanumarasi AS no FROM {p}.new_sevkiyatBase WHERE statecode = 0 AND new_logoyaaktarildi = 1 "
                 f"AND new_sevktarihi >= '{utc(a0)}' AND new_sevktarihi < '{utc(a1)}'")
        nos = {re.sub(r"\s+", "", str(r["no"])).upper() for r in lg if r["no"]}
        match = sum(1 for r in cr if r["no"] and re.sub(r"\s+", "", str(r["no"])).upper() in nos)
        sv = rec["sevk"]
        check("R6 Logo irsaliye sayısı = SQL", sv["logoIrsaliye"] == len(lg), f"API {sv['logoIrsaliye']} · SQL {len(lg)}")
        check("R6 CRM sevkiyat sayısı = SQL", sv["crmSevkiyat"] == len(cr), f"API {sv['crmSevkiyat']} · SQL {len(cr)}")
        check("R6 eşleşen = SQL", sv["eslesen"] == match, f"API {sv['eslesen']} · SQL {match} · oran {sv['eslesmeOrani']}")
        check("mutabakatta kimlik bilgisi yok", no_secret(rec))

    # R7 · Teslim bekleyen.
    s, w = http("GET", P + "/waiting")
    if s == 200:
        tcol = DATE_SQL.format(c="new_TeslimTarihi")
        ref = crm(f"SELECT COUNT(*) AS n FROM {p}.new_kargobilgisiBase WHERE statecode = 0 AND {tcol} IS NULL "
                  f"AND (ISNULL(LTRIM(RTRIM(new_iadedurumu)), '') = '' OR LOWER(LTRIM(RTRIM(new_iadedurumu))) "
                  f"IN (N'hayır', 'hayir', 'yok', '0', 'false', '-', 'normal', N'iade değil'))")[0]["n"]
        check("R7 teslim bekleyen toplamı = SQL", w["toplam"] == ref, f"API {w['toplam']} · SQL {ref} (tarih biçimi/iade değerleri ölçülecek)")
    else:
        check("waiting 200", False, str(s))

    # R8 · Gönderi kartı ve arama (rastgele sipariş).
    pick = crm(f"SELECT TOP 1 new_siparisId AS id, new_name AS no FROM {p}.new_siparisBase WHERE statecode = 0 AND statuscode = 100000000 "
               f"AND ISNULL(new_kargotakipno, '') <> '' AND new_sevktarihi >= '{utc(since)}' ORDER BY NEWID()")
    if pick:
        oid, ono = str(pick[0]["id"]).lower().strip("{}"), pick[0]["no"]
        s, c = http("GET", P + f"/shipments/{oid}")
        check("gönderi kartı 200", s == 200, f"{ono}: {s}")
        if s == 200:
            nv = crm(f"SELECT COUNT(*) AS n FROM {p}.new_sevkiyatBase WHERE statecode = 0 AND new_siparisid = '{oid}'")[0]["n"]
            nt = crm(f"SELECT COUNT(*) AS n FROM {p}.new_kargotakipbilgisiBase WHERE statecode = 0 AND new_siparisid = '{oid}'")[0]["n"]
            check("R8 kartta sipariş no", c["siparis"]["no"] == ono, f"{c['siparis']['no']} · {ono}")
            check("R8 kartta sevkiyat sayısı = SQL", len(c["sevkiyatlar"]) == nv, f"API {len(c['sevkiyatlar'])} · SQL {nv}")
            check("R8 kartta takip kaydı sayısı = SQL", len(c["takip"]) == nt, f"API {len(c['takip'])} · SQL {nt}")
            check("kartta kimlik bilgisi yok", no_secret(c))
            s, sr = http("GET", P + f"/shipments?q={urllib.request.quote(ono)}")
            check("arama sipariş no ile kartı bulur", s == 200 and any(i["id"] == oid for i in sr.get("items", [])), str(s))
            # Yazma: bir taslak (sonra temizlik.py siler).
            s, dr = http("POST", P + "/drafts", {"siparisId": oid, "tur": "gecikme"})
            check("taslak 201", s == 201, f"{s} {str(dr)[:120]}")
            if s == 201:
                created["drafts"].append(dr["id"])
                check("taslakta müşteri adı yok", not (c["siparis"].get("musteri") and c["siparis"]["musteri"] in dr["metin"]), dr["kaynak"])
    else:
        check("R8 rastgele sevk edilmiş sipariş bulundu", False, "pencerede takip no'lu sevk yok")

    # Karar kaydı (yaz, hemen sil).
    s, k = http("POST", P + "/decisions", {"tur": "kurye", "karar": "Kabul denemesi — silinecek"})
    if s == 201:
        created["decisions"].append(k["id"])
        check("karar kaydı sil 200", http("DELETE", P + f"/decisions/{k['id']}")[0] == 200)
    else:
        check("karar kaydı 201 (kargo.karar yetkisi)", False, str(s))

    # Excel.
    for liste in ("hatalar", "takipsiz", "bekleyen", "firmalar"):
        s, body, ctype = http("GET", P + f"/export/{liste}.xlsx", raw=True)
        check(f"Excel {liste}", s == 200 and "spreadsheet" in ctype and body[:2] == b"PK" and no_secret(body), f"{s} {len(body) if isinstance(body, bytes) else ''}")
    return finish(a.out, created)


def finish(out_path: str, created: dict[str, list[str]]) -> int:
    with open(out_path, "w") as fh:
        json.dump(created, fh)
    ok = sum(1 for r in results if r[1])
    print(f"== SONUÇ: {ok}/{len(results)} geçti; kimlikler {out_path} (temizlik.py ile silin)")
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
