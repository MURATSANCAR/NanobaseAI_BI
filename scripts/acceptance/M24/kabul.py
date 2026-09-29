"""M24 Katalog ve bülten — gerçek API ↔ doğrudan SQL kabulü (test sunucusunda, yan port köprüsü, salt okunur kaynaklar).

Uçların kullanıcıya verdiği sonuç, köprü kodu kullanılmadan yazılmış doğrudan CRM/Logo sorgularıyla karşılaştırılır
(`referans.sql` R1–R8). Kitaplar her koşuda öneri listesinden rastgele seçilir (sabit kitap yok). Yazma: yalnız bir deneme
kataloğu ve bir deneme bülteni açılır; kimlikleri `--out` dosyasına yazılır, `cleanup.py` siler (değişiklik kaydı dahil).
Portal hiçbir e-posta göndermez; bu betik de göndermez.

Ortam: BASE (ör. http://127.0.0.1:8798), COOKIE (timasai'nin kısa oturum çerezi; yönetici olduğu için açık yetkiler de
vardır), SEMANTIC_CONNECTION_FILE (Logo), SEMANTIC_CRM_CONNECTION_FILE, PYTHONPATH=<aday ağaç>/backend (yalnız bağlantı
sürücüsü için), BASKI_SQL_DIR (varsayılan <aday ağaç>/backend/semantic_bridge/management/sql/baski_oneri).
İsteğe bağlı M24_KITAP (stok ay/fiyat için örnek sayısı, varsayılan 10), M24_HAVUZ_BEKLE_DK (varsayılan 30).
Kullanım: python kabul.py --out /tmp/claude-m24/kabul-kimlikler.json
"""
from __future__ import annotations

import argparse
import io
import json
import os
import random
import time
import urllib.error
import urllib.request
import zipfile
from datetime import date
from pathlib import Path

BASE = os.environ.get("BASE", "http://127.0.0.1:8798").rstrip("/")
COOKIE = os.environ.get("COOKIE", "")
P = BASE + "/api/v1/catalog-newsletter"
SCHEMA = os.environ.get("CRM_SCHEMA", "Timas_MSCRM.dbo")
SQL_DIR = Path(os.environ.get("BASKI_SQL_DIR", str(Path(__file__).resolve().parents[3] / "backend/semantic_bridge/management/sql/baski_oneri")))
results: list[tuple[str, bool, str]] = []
bodies: list[tuple[str, str]] = []


def http(method: str, url: str, body=None, timeout=900, raw=False):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method, headers={"Cookie": COOKIE, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            payload = r.read()
            if raw:
                return r.status, payload
            text = payload.decode("utf-8", "replace")
            bodies.append((url, text))
            return r.status, (json.loads(text) if text[:1] in "{[" else text)
    except urllib.error.HTTPError as e:
        payload = e.read()
        text = payload.decode("utf-8", "replace")
        bodies.append((url, text))
        try:
            return e.code, json.loads(text)
        except ValueError:
            return e.code, text


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(("GEÇTİ " if ok else "KALDI ") + name + (f" — {detail}" if detail else ""), flush=True)
    if len(results) % 10 == 0:
        print(f"-- ara durum: {sum(1 for r in results if r[1])} geçti, {sum(1 for r in results if not r[1])} kaldı", flush=True)


def runner(path: str):
    from semantic_layer.profiler.connectors import connector_from_file

    conn = connector_from_file(path)
    conn.query_timeout = 1800

    def run(sql: str):
        _c, rows, truncated = conn.execute(sql, 2_000_000)
        assert not truncated, "referans sonucu kesildi"
        return rows
    return run


def q(v) -> str:
    return "'" + str(v).replace("'", "''") + "'"


def speed_sql(logo, codes: list[str]) -> str:
    """logo_satis_hizi.sql, {satis:2024} köprü kodu kullanılmadan yıllık görünümlere açılır (kolonlar adla)."""
    text = (SQL_DIR / "logo_satis_hizi.sql").read_text(encoding="utf-8")
    views = {int(r["name"][-4:]) for r in logo("SELECT name FROM sys.views WHERE name LIKE 'V[_]SatisRaporu[_]20[0-9][0-9]'")}
    years = [y for y in range(2024, date.today().year + 1) if y in views]
    arms = [f"SELECT [Malzeme/Hizmet Kodu], [Yıl], [Ay], [Miktar] FROM dbo.V_SatisRaporu_{y} "
            f"WHERE [Malzeme/Hizmet Kodu] NOT LIKE '157%' AND [KDVli Tutar] <> 0 AND [Malzeme/Hizmet Kodu] IN ({', '.join(q(c) for c in codes)})"
            for y in years]
    return text.replace("{satis:2024}", "(" + " UNION ALL ".join(arms) + ")")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    logo = runner(os.environ["SEMANTIC_CONNECTION_FILE"])
    crm = runner(os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json"))
    created: dict[str, list[str]] = {"catalogs": [], "newsletters": []}

    def finish() -> int:
        Path(a.out).write_text(json.dumps(created))
        ok = sum(1 for r in results if r[1])
        print(f"== SONUÇ: {ok}/{len(results)} geçti; kimlikler {a.out} (cleanup.py ile silin)")
        return 0 if ok == len(results) else 1

    # 0. Meta ve havuz (ilk okumada birkaç dakika sürer).
    deadline = time.time() + 60 * int(os.environ.get("M24_HAVUZ_BEKLE_DK", "30"))
    while True:
        s, meta = http("GET", P + "/meta")
        if s != 200 or meta["havuz"]["okuma"] or time.time() > deadline:
            break
        print(f"   havuz okunuyor… {meta['havuz']}", flush=True)
        time.sleep(30)
    check("meta 200 ve kitap havuzu hazır", s == 200 and bool(meta["havuz"]["okuma"]), json.dumps(meta.get("havuz") if s == 200 else meta, ensure_ascii=False)[:300])
    if s != 200 or not meta["havuz"]["okuma"]:
        return finish()
    print(f"   ölçüm: havuz {meta['havuz']['kitap']} kitap, kaynaklar arası fiyatı farklı {meta['havuz']['fiyatFarkli']}, "
          f"T-soft ürünü {meta['havuz']['tsoftUrun']}; notlar {meta['havuz']['notlar']}")
    s, _ = http("POST", P + "/catalogs", {})
    check("boş gövdeyle katalog 400", s == 400, str(s))

    # R7 · Logo veri sonu.
    skip = {int(x) for x in os.environ.get("SEMANTIC_EXCLUDE_CONTEXT", "015,016").split(",") if x.strip().isdigit()}
    own = {int(x) for x in os.environ.get("SEMANTIC_FIRMS", "").split(",") if x.strip().isdigit()}   # canlı Logo başka şirketleri de taşır
    by_year: dict[int, int] = {}
    for r in logo("SELECT FIRMNR, BEGDATE, ENDDATE FROM L_CAPIPERIOD WHERE ACTIVE = 1"):
        if int(r["FIRMNR"]) in skip or (own and int(r["FIRMNR"]) not in own):
            continue
        # Bağlantı tarihleri metin olarak da dönebilir ('2026-01-01T00:00:00'); yıl ilk dört karakterden okunur.
        for y in range(int(str(r["BEGDATE"])[:4]), int(str(r["ENDDATE"])[:4]) + 1):
            by_year[y] = max(by_year.get(y, 0), int(r["FIRMNR"]))
    firm = f"{by_year[max(by_year)]:03d}"
    son = logo(f"SELECT MAX(DATE_) AS son FROM dbo.LG_{firm}_01_STLINE WHERE CANCELLED = 0 AND LINETYPE = 0 AND INVOICEREF <> 0 AND TRCODE IN (7,8,9)")[0]["son"]
    check("R7 stok verisi tarihi = Logo son faturalı satış günü", str(son)[:10] == meta["havuz"]["logoSon"], f"ekran {meta['havuz']['logoSon']} / SQL {str(son)[:10]}")

    # Deneme kataloğu ve öneri.
    s, cat = http("POST", P + "/catalogs", {"tur": "bayi", "baslik": "Kabul denemesi (silinecek)", "fiyatKaynagi": "crm"})
    check("deneme kataloğu açıldı", s == 201, str(s))
    if s != 201:
        return finish()
    created["catalogs"].append(cat["id"])
    s, sug = http("POST", P + f"/catalogs/{cat['id']}/suggest", {"page": 0, "pageSize": 200}, timeout=1800)
    check("öneri listesi 200", s == 200 and sug["total"] > 0, f"{s} aday {sug.get('total') if s == 200 else sug}")
    if s != 200:
        return finish()

    # R6 · Satıştan kalkan kitap sayısı (öneriye girmez).
    r6 = crm(f"""SELECT COUNT(*) AS n FROM {SCHEMA}.new_kitapBase k
      LEFT JOIN {SCHEMA}.StringMap sm ON sm.AttributeName = 'new_kitap_yayincilikstatusu' AND sm.LangId = 1055
        AND sm.AttributeValue = k.new_kitap_yayincilikstatusu
        AND sm.ObjectTypeCode IN (SELECT e.ObjectTypeCode FROM {SCHEMA.split('.')[0]}.MetadataSchema.Entity e WHERE e.Name = 'new_kitap')
      WHERE k.statecode = 0 AND k.new_Tip IN (1,4)
        AND (LEFT(sm.Value, 4) IN ('YS01','YS05','YS06','YS11','YS12') OR k.new_satisdurumu = 0)""")[0]["n"]
    ekran = sug["elenen"].get("satıştan kalkmış", 0)
    check("R6 satıştan kalkan kitap sayısı birebir (öneriye girmedi)", int(r6) == int(ekran), f"ekran {ekran} / SQL {r6}")

    n = int(os.environ.get("M24_KITAP", "10"))
    pool = [x for x in sug["items"] if x["stokAy"] is not None and x["stok"]]
    pick = random.sample(pool, min(n, len(pool)))
    s, det = http("PUT", P + f"/catalogs/{cat['id']}/items", {"items": [{"crmKitapId": x["id"], "gerekce": x["gerekce"]} for x in pick]})
    check("kitaplar kataloğa eklendi", s == 200 and det["ozet"]["kitap"] == len(pick), str(s))
    if s != 200:
        return finish()
    items = {k["crmKitapId"]: k for k in det["kitaplar"]}

    # R1 · Stok ay sayısı: CRM stok adedi ÷ satış hızı (doğrudan) ve Baskı önerisi ekranı.
    codes = [k["stokKodu"] for k in det["kitaplar"] if k["stokKodu"]]
    stok = {}
    for r in crm(f"SELECT StokKodu, StokAdedi FROM Timas_MSCRM.dbo.powerbikitap WHERE StokKodu IN ({', '.join(q(c) for c in codes)})"):
        if r["StokAdedi"] is not None and r["StokKodu"] not in stok:
            stok[str(r["StokKodu"]).strip()] = float(r["StokAdedi"])
    hiz = {str(r["stok_kodu"]).strip(): float(r["satis_hizi"] or 0) for r in logo(speed_sql(logo, codes))}
    bad = []
    for k in det["kitaplar"]:
        c = k["stokKodu"]
        ref = stok[c] / hiz[c] if c in stok and hiz.get(c) else None
        if ref is None or k["stokAy"] is None or abs(ref - k["stokAy"]) > 1e-6 * max(1.0, abs(ref)):
            bad.append(f"{c}: ekran {k['stokAy']} / SQL {ref}")
    check(f"R1 stok ay sayısı birebir ({len(codes)} kitap)", not bad, "; ".join(bad[:5]))
    s, rep = http("GET", BASE + "/api/v1/management/reports/baski-oneri", timeout=1800)
    if s == 200 and rep.get("data"):
        view = next(v for v in rep["data"]["views"] if v["id"] == "tekrar")
        keys = [col["key"] for col in view["columns"]]
        ik, it = keys.index("stok_kodu"), keys.index("tukenme_suresi")
        screen = {str(row[ik]).strip(): row[it] for row in view["rows"]}
        both = [k for k in det["kitaplar"] if k["stokKodu"] in screen and isinstance(screen[k["stokKodu"]], (int, float))]
        bad2 = [f"{k['stokKodu']}: katalog {k['stokAy']} / Baskı önerisi {screen[k['stokKodu']]}" for k in both
                if abs(screen[k["stokKodu"]] - k["stokAy"]) > 1e-6 * max(1.0, abs(screen[k["stokKodu"]]))]
        check(f"R1 stok ay sayısı = Baskı önerisi ekranı ({len(both)} ortak kitap)", not bad2, "; ".join(bad2[:5]))
    else:
        check("R1 Baskı önerisi ekranı okunamadı", False, str(s))

    # R2 · Fiyat (CRM KDV dahil).
    ids = list(items)
    ref_price = {str(r["id"]).lower(): (float(r["f"]) if r["f"] is not None else None)
                 for r in crm(f"SELECT new_kitapId AS id, new_kdvdahilfiyat AS f FROM {SCHEMA}.new_kitapBase WHERE new_kitapId IN ({', '.join(q(i) for i in ids)})")}
    bad = [f"{i}: ekran {items[i]['fiyat']} / SQL {ref_price.get(i)}" for i in ids
           if (ref_price.get(i) is None) != (items[i]["fiyat"] is None)
           or (ref_price.get(i) is not None and abs(round(ref_price[i], 2) - items[i]["fiyat"]) > 0.005)]
    check(f"R2 katalog fiyatı = CRM new_kdvdahilfiyat ({len(ids)} kitap)", not bad, "; ".join(bad[:5]))

    # Dışa aktarım.
    s, z = http("GET", P + f"/catalogs/{cat['id']}/package.zip", raw=True, timeout=600)
    names = set(zipfile.ZipFile(io.BytesIO(z)).namelist()) if s == 200 else set()
    check("tasarımcı paketi (Excel + kapaklar + metinler + brief)", names == {"katalog.xlsx", "kapaklar.csv", "metinler.txt", "BENIOKU.txt"}, f"{s} {sorted(names)}")
    s, pdf = http("GET", P + f"/catalogs/{cat['id']}/preview.pdf?perPage=6", raw=True, timeout=600)
    check("PDF önizleme", s == 200 and pdf[:4] == b"%PDF", str(s))

    # R3 · Segment sayısı ve izin kuralı.
    s, seg = http("POST", P + "/segments/count", {"segment": {"ilgiBayraklari": ["new_tarihveakademi"]}}, timeout=900)
    ref = crm(f"""SELECT COUNT(DISTINCT c.ContactId) AS n FROM {SCHEMA}.ContactBase c WHERE c.statecode = 0 AND ISNULL(c.DoNotBulkEMail,0) = 0
      AND ISNULL(c.DoNotEMail,0) = 0 AND c.new_iysonayi = 1 AND NULLIF(LTRIM(c.EMailAddress1),'') IS NOT NULL AND c.new_tarihveakademi = 1""")[0]["n"]
    check("R3 segment izinli sayısı birebir", s == 200 and int(ref) == seg["izinli"], f"ekran {seg.get('izinli') if s == 200 else seg} / SQL {ref}")
    ref_no = crm(f"""SELECT COUNT(*) AS n FROM {SCHEMA}.ContactBase c WHERE c.statecode = 0 AND c.new_tarihveakademi = 1
      AND NOT (ISNULL(c.DoNotBulkEMail,0) = 0 AND ISNULL(c.DoNotEMail,0) = 0 AND ISNULL(c.new_iysonayi,0) = 1
               AND NULLIF(LTRIM(c.EMailAddress1),'') IS NOT NULL)""")[0]["n"]
    check("R3b izin alanı eksik kişi sayıya girmedi (izinsiz sayısı birebir)", s == 200 and int(ref_no) == seg["izinsiz"],
          f"ekran {seg.get('izinsiz') if s == 200 else ''} / SQL {ref_no}")
    if s == 200:
        print(f"   ölçüm: izin dağılımı {seg['dagilim']}")

    # R4 · Özel güne bağlı kitap sayısı.
    ref_days = {str(r["ad"]).strip(): int(r["n"]) for r in crm(f"""SELECT o.new_name AS ad, COUNT(DISTINCT l.new_kitapid) AS n
      FROM {SCHEMA}.new_new_kitap_new_ozelgunlerBase l JOIN {SCHEMA}.new_kitapBase k ON k.new_kitapId = l.new_kitapid
      JOIN {SCHEMA}.new_ozelgunlerBase o ON o.new_ozelgunlerId = l.new_ozelgunlerid
      WHERE k.statecode = 0 AND k.new_ean13 IS NOT NULL AND o.statecode = 0 GROUP BY o.new_name""")}
    screen_days = {d["ad"]: d["kitapSayisi"] for d in meta["ozelGunler"]}
    common = [k for k in screen_days if k in ref_days]
    bad = [f"{k}: ekran {screen_days[k]} / SQL {ref_days[k]}" for k in common if screen_days[k] != ref_days[k]]
    check(f"R4 özel güne bağlı kitap sayısı birebir ({len(common)} gün)", bool(common) and not bad, "; ".join(bad[:5]))

    # R5 · CRM kampanya sonuçları.
    s, report = http("GET", P + "/report", timeout=900)
    ref_c = {str(r["id"]).lower(): r for r in crm(f"SELECT CampaignId AS id, obs_totalcount AS t, obs_readcount AS o, obs_clickcount AS c FROM {SCHEMA}.CampaignBase")}
    screen_c = {c["id"]: c for c in (report.get("crm") or [])} if s == 200 else {}
    num = lambda v: None if v is None else float(v)  # noqa: E731
    bad = [cid for cid, r in ref_c.items() if cid not in screen_c or (num(r["t"]), num(r["o"]), num(r["c"])) !=
           (screen_c[cid]["toplam"], screen_c[cid]["okunan"], screen_c[cid]["tiklanan"])]
    check(f"R5 CRM kampanya sayaçları birebir ({len(ref_c)} kampanya)", s == 200 and not bad, f"farklı: {bad[:5]}")

    # Deneme bülteni: HTML onaysız indirilmez.
    s, nl = http("POST", P + "/newsletters", {"baslik": "Kabul denemesi bülteni (silinecek)", "segment": {"ilgiBayraklari": ["new_tarihveakademi"]}})
    check("deneme bülteni açıldı", s == 201, str(s))
    if s == 201:
        created["newsletters"].append(nl["id"])
        s, nd = http("PUT", P + f"/newsletters/{nl['id']}/items", {"items": [{"crmKitapId": x["id"]} for x in pick[:3]]})
        check("bülten kitapları ve HTML", s == 200 and bool(nd.get("html")), str(s))
        s, _ = http("GET", P + f"/newsletters/{nl['id']}/html")
        check("onaysız bültenin HTML'i indirilmez (409)", s == 409, str(s))

    # R8 · Kişi verisi dışarı çıkmıyor.
    own = [(u, b) for u, b in bodies if u.startswith(P)]
    leaks = [f"{u}: {b[max(0, b.find('@') - 40):b.find('@') + 40]}" for u, b in own if "@" in b]
    check(f"R8 uç yanıtlarında e-posta adresi yok ({len(own)} yanıt)", not leaks, "; ".join(leaks[:3]))
    return finish()


if __name__ == "__main__":
    raise SystemExit(main())
