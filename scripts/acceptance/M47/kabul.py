"""M47 Risk ve uyum — gerçek API ↔ doğrudan SQL kabulü (test sunucusunda, yan port köprüsü, salt okunur kaynaklar).

Göstergeler «şimdi ölç» ucuyla (gerçek Logo/CRM, gerçek köprü) ölçülür; ekrandaki değer köprü kodu kullanılmadan
yazılmış doğrudan sorguyla karşılaştırılır (`referans.sql` R1–R9). Ayrıca finansal denetim göstergesinin hazır raporla
aynı olduğu, yazma akışları (risk → gözden geçirme → kuyruk, uyum kanıtı ve kapanış, poliçe maskesi, brifing iki göz)
ve yetkiler denenir. Yazılan her kayıt kimliğiyle `--out` dosyasına gider; `cleanup.py` siler (ölçüm satırları,
dosyalar, değişiklik kaydı dahil).

Ortam: BASE (ör. http://127.0.0.1:8798), COOKIE (timasai'nin 15 dk'lık oturumu; yönetici), isteğe bağlı COOKIE2
(yöneticisi olmayan ikinci oturum; yoksa yetki denemeleri atlanır), SEMANTIC_CONNECTION_FILE (Logo),
SEMANTIC_CRM_CONNECTION_FILE, PYTHONPATH=<aday ağaç>/backend, isteğe bağlı CRM_SCHEMA.
Kullanım: python kabul.py --out /tmp/claude-m47/kabul-kimlikler.json
"""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timezone

from semantic_bridge import budget_sources as bsrc

BASE = os.environ.get("BASE", "http://127.0.0.1:8798").rstrip("/")
COOKIE = os.environ.get("COOKIE", "")
COOKIE2 = os.environ.get("COOKIE2", "")
P = BASE + "/api/v1/risk"
SCHEMA = os.environ.get("CRM_SCHEMA", "Timas_MSCRM.dbo")
results: list[tuple[str, bool, str]] = []


def http(method: str, url: str, body=None, timeout=1800, cookie=None, raw: bytes | None = None, ctype="application/json"):
    data = raw if raw is not None else (None if body is None else json.dumps(body).encode())
    req = urllib.request.Request(url, data=data, method=method, headers={"Cookie": cookie or COOKIE, "Content-Type": ctype,
                                                                         "Origin": BASE})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            payload = r.read()
            return r.status, (json.loads(payload) if payload[:1] in (b"{", b"[") else payload)
    except urllib.error.HTTPError as e:
        payload = e.read()
        try:
            return e.code, json.loads(payload)
        except ValueError:
            return e.code, payload


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(("GEÇTİ " if ok else "KALDI ") + name + (f" — {detail}" if detail else ""), flush=True)
    if len(results) % 10 == 0:
        print(f"-- ara durum: {sum(1 for r in results if r[1])} geçti, {sum(1 for r in results if not r[1])} kaldı", flush=True)


def q(v: str) -> str:
    return "'" + str(v).replace("'", "''") + "'"


def day(v) -> date:
    return v if isinstance(v, date) and not isinstance(v, datetime) else (v.date() if isinstance(v, datetime) else date.fromisoformat(str(v)[:10]))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    started = datetime.now(timezone.utc).isoformat()
    created: dict[str, list[str]] = {"risks": [], "items": [], "policies": [], "bcp": [], "reports": []}

    def finish() -> int:
        with open(a.out, "w") as fh:
            json.dump({**created, "since": started}, fh)
        ok = sum(1 for r in results if r[1])
        print(f"== SONUÇ: {ok}/{len(results)} geçti; kimlikler {a.out} (cleanup.py ile silin)")
        return 0 if ok == len(results) else 1

    logo = bsrc.runner(os.environ["SEMANTIC_CONNECTION_FILE"])
    crm = bsrc.runner(os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json"))
    firms = bsrc.firms_by_year(logo)
    year = max(firms)
    f = firms[year]
    today = date.today()

    # 0. Geçersiz istekler (yazmadan önce).
    s, meta = http("GET", P + "/meta")
    check("meta 200", s == 200, str(s))
    s, _ = http("POST", P + "/risks", {})
    check("boş gövdeyle risk 400", s == 400, str(s))
    s, _ = http("GET", P + "/risks/yok-boyle-risk")
    check("olmayan risk 404", s == 404, str(s))
    s, _ = http("POST", P + "/indicators", {"kod": "serbest_sql", "ad": "x"})
    check("hazır hesapçı dışı gösterge 400", s == 400, str(s))

    def measure(kod: str) -> dict:
        s, out = http("POST", P + f"/indicators/{kod}/measure", {})
        check(f"{kod} ölçüldü", s == 200 and out.get("deger") is not None, str(out)[:200] if s != 200 or out.get("hata") else f"{out.get('deger')}")
        return out if s == 200 else {}

    # R1 · Logo veri gecikmesi.
    last = day(logo(f"SELECT MAX(DATE_) AS son FROM dbo.LG_{f}_01_INVOICE WHERE CANCELLED = 0")[0]["son"])
    g = measure("logo_veri_gecikmesi")
    if g:
        check("R1 veri gecikmesi = bugün − son fatura", g["deger"] == float((today - last).days) and g["veriSonGunu"] == last.isoformat(),
              f"ekran {g['deger']} ({g['veriSonGunu']}) / SQL {(today - last).days} ({last})")

    # R2 · Müşteri yoğunlaşması (ilk 4).
    r = logo(f"""WITH N AS (SELECT CLIENTREF, SUM(CASE WHEN TRCODE IN (7,8,9) THEN NETTOTAL ELSE -NETTOTAL END) AS n
        FROM dbo.LG_{f}_01_INVOICE WHERE CANCELLED = 0 AND TRCODE IN (2,3,7,8,9) AND DATE_ >= '{year}-01-01' AND DATE_ < '{year + 1}-01-01'
        GROUP BY CLIENTREF) SELECT (SELECT SUM(n) FROM (SELECT TOP 4 n FROM N ORDER BY n DESC) t) / SUM(n) AS pay, SUM(n) AS payda FROM N""")[0]
    g = measure("musteri_yogunlasmasi_ilk4")
    if g:
        ref = float(r["pay"]) * 100
        check("R2 ilk 4 müşteri payı birebir", abs(g["deger"] - ref) < 1e-3 and abs(g["kanit"]["toplam"] - float(r["payda"])) < 0.01,
              f"ekran %{g['deger']:.4f} payda {g['kanit']['toplam']:.2f} / SQL %{ref:.4f} payda {float(r['payda']):.2f}")

    # R3 · Karşılıksız çek (hareketten karta, ters yazım).
    r = logo(f"""SELECT COUNT(*) AS adet, SUM(K.AMOUNT) AS tutar FROM (SELECT DISTINCT T.CSREF FROM dbo.LG_{f}_01_CSTRANS T
        WHERE T.STATUS = 11 AND T.DEVIR = 0 AND T.CANCELLED = 0 AND T.DATE_ >= '{year}-01-01' AND T.DATE_ < '{year + 1}-01-01') E
        JOIN dbo.LG_{f}_01_CSCARD K ON K.LOGICALREF = E.CSREF WHERE K.CANCELLED = 0 AND K.DOC IN (1, 2)""")[0]
    g = measure("karsiliksiz_cek")
    if g:
        check("R3 karşılıksız çek adet ve tutar birebir", g["deger"] == float(r["adet"] or 0) and abs(g["kanit"]["tutar"] - float(r["tutar"] or 0)) < 0.01,
              f"ekran {g['deger']} / {g['kanit']['tutar']:.2f} ₺ — SQL {r['adet']} / {float(r['tutar'] or 0):.2f} ₺ (ölçüm 09-20: 6 / 6.326.658)")

    # R4 · Döviz faturası.
    n_local = int(logo(f"SELECT COUNT(*) AS n FROM dbo.LG_{f}_01_INVOICE WHERE CANCELLED = 0 AND TRCURR NOT IN (0, 160)")[0]["n"])
    n_nonzero = int(logo(f"SELECT COUNT(*) AS n FROM dbo.LG_{f}_01_INVOICE WHERE CANCELLED = 0 AND TRCURR <> 0")[0]["n"])
    g = measure("doviz_faturasi")
    if g:
        check("R4 döviz faturası birebir", g["deger"] == float(n_local),
              f"ekran {g['deger']} / SQL {n_local}; TRCURR <> 0 = {n_nonzero} (bilgi paketi 74; fark 160 kodlu satırlardır)")

    # R5 · Süresi bitmiş ama satan kitap.
    expired = [str(x["stok"]).strip() for x in crm(f"""SELECT k.new_StokKodu AS stok,
        SUM(CASE WHEN ISNULL(s.new_suresizsozlesme,0) = 0 AND s.new_SozlesmeBitisTarihi < CAST(GETDATE() AS date) THEN 1 ELSE 0 END) AS biten,
        SUM(CASE WHEN ISNULL(s.new_suresizsozlesme,0) = 1 OR s.new_SozlesmeBitisTarihi >= CAST(GETDATE() AS date) THEN 1 ELSE 0 END) AS yururlukte
        FROM {SCHEMA}.new_kitapBase k JOIN {SCHEMA}.new_new_sozlesme_new_kitapBase sk ON sk.new_kitapid = k.new_kitapId
        JOIN {SCHEMA}.new_sozlesmeBase s ON s.new_sozlesmeId = sk.new_sozlesmeid
        WHERE s.statecode = 0 AND s.new_SozlesmeTipi = 5 AND k.new_StokKodu IS NOT NULL GROUP BY k.new_StokKodu""")
        if int(x["biten"] or 0) > 0 and int(x["yururlukte"] or 0) == 0 and str(x["stok"] or "").strip()]
    sold: set[str] = set()
    codes = sorted(set(expired))
    for i in range(0, len(codes), 800):
        part = codes[i:i + 800]
        for x in logo(f"""SELECT I.CODE AS stok, SUM(L.AMOUNT) AS adet FROM dbo.LG_{f}_01_STLINE L JOIN dbo.LG_{f}_ITEMS I ON I.LOGICALREF = L.STOCKREF
            WHERE L.CANCELLED = 0 AND L.LINETYPE = 0 AND L.INVOICEREF <> 0 AND L.TRCODE IN (7,8,9)
              AND L.DATE_ > DATEADD(day, -30, '{last.isoformat()}') AND L.DATE_ <= '{last.isoformat()}'
              AND I.CODE IN ({', '.join(q(c) for c in part)}) GROUP BY I.CODE HAVING SUM(L.AMOUNT) > 0"""):
            sold.add(str(x["stok"]))
    g = measure("suresi_bitmis_satan_kitap")
    if g:
        screen = {k["stok"] for k in g["kanit"]["kitaplar"]}
        check("R5 süresi bitmiş ama satan kitap listesi birebir", screen == sold and g["deger"] == float(len(sold)),
              f"ekran {len(screen)} / SQL {len(sold)}; süresi biten kitap {len(codes)}; fark {sorted(screen ^ sold)[:10]}")

    # R6 · Maliyetsiz satış payı (M45 kabul 4 ile aynı kapsam).
    r = logo(f"SELECT SUM(CASE WHEN OUTCOST <> 0 THEN LINENET END) / SUM(LINENET) AS p FROM dbo.LG_{f}_01_STLINE "
             f"WHERE CANCELLED = 0 AND LINETYPE = 0 AND INVOICEREF <> 0 AND TRCODE IN (7,8)")[0]
    g = measure("maliyetsiz_satis_payi")
    if g:
        ref = (1 - float(r["p"])) * 100
        check("R6 maliyetsiz satış payı birebir", abs(g["deger"] - ref) < 1e-3, f"ekran %{g['deger']:.4f} / SQL %{ref:.4f}")

    # R7 · Tedarikçi yoğunlaşması.
    r = logo(f"""WITH N AS (SELECT CLIENTREF, SUM(NETTOTAL) AS n FROM dbo.LG_{f}_01_INVOICE WHERE CANCELLED = 0 AND TRCODE IN (1,4)
        AND DATE_ >= '{year}-01-01' AND DATE_ < '{year + 1}-01-01' GROUP BY CLIENTREF)
        SELECT (SELECT SUM(n) FROM (SELECT TOP 4 n FROM N ORDER BY n DESC) t) / SUM(n) AS pay FROM N""")[0]
    g = measure("tedarikci_yogunlasmasi_ilk4")
    if g:
        check("R7 tedarikçi ilk 4 payı birebir", abs(g["deger"] - float(r["pay"]) * 100) < 1e-3, f"ekran %{g['deger']:.4f} / SQL %{float(r['pay']) * 100:.4f}")

    # R8 · Maliyetlendirme gecikmesi.
    c = day(logo(f"SELECT MAX(DATE_) AS son FROM dbo.LG_{f}_01_STLINE WHERE CANCELLED = 0 AND LINETYPE = 0 AND INVOICEREF <> 0 "
                 f"AND TRCODE IN (7,8) AND OUTCOST <> 0")[0]["son"])
    g = measure("maliyet_gecikmesi")
    if g:
        check("R8 maliyetlendirme gecikmesi birebir", g["deger"] == float((last - c).days), f"ekran {g['deger']} / SQL {(last - c).days} (son maliyetli {c})")

    # R9 · 60 gün içinde biten sözleşme.
    n = int(crm(f"""SELECT COUNT(*) AS n FROM {SCHEMA}.new_sozlesmeBase s WHERE s.statecode = 0 AND s.statuscode IN (100000000, 100000006, 100000007)
        AND ISNULL(s.new_suresizsozlesme, 0) = 0 AND s.new_SozlesmeBitisTarihi >= CAST(GETDATE() AS date)
        AND s.new_SozlesmeBitisTarihi < DATEADD(day, 61, CAST(GETDATE() AS date))""")[0]["n"])
    g = measure("sozlesme_bitiyor")
    if g:
        check("R9 süresi yaklaşan sözleşme birebir (EDITORIAL_CONTRACT_WARN_DAYS=60)", g["deger"] == float(n), f"ekran {g['deger']} / SQL {n}")

    # R10 · Finansal denetim: hazır rapor, Logo'ya yeni sorgu gitmez.
    s, fa = http("GET", BASE + "/api/v1/financial-audit/overview")
    g = measure("denetim_inceleme_adayi")
    if s == 200 and g:
        n = sum(1 for x in fa.get("checks", []) if x.get("status") == "finding") + \
            sum(1 for x in (fa.get("deepAudit") or {}).get("checks", []) if x.get("status") == "finding")
        check("R10 denetim inceleme adayı = hazır rapor", g["deger"] == float(n) and g["kanit"]["raporId"] == fa.get("runId"),
              f"ekran {g['deger']} / rapor {n} ({fa.get('runId')})")
    else:
        check("R10 finansal denetim raporu okunabildi", False, f"overview {s}")

    # Kalan hazır göstergeler: ölçülebiliyor mu (değer ya da okunur hata).
    for kod in ("musteri_yogunlasmasi_ilk10", "vadesi_gecmis_alacak_90", "stok_risk_acil", "butce_sapmasi", "kvkk_izin_tarihsiz"):
        s, out = http("POST", P + f"/indicators/{kod}/measure", {})
        check(f"{kod} ucu yanıt verdi", s == 200, f"değer {out.get('deger')} hata {out.get('hata')}" if s == 200 else str(out)[:160])
        if kod == "kvkk_izin_tarihsiz" and s == 200 and out.get("hata"):
            print("   ölçülecek: RISK_KVKK_CONSENT_COLUMN / RISK_KVKK_DATE_COLUMN kolon adları CRM'de doğrulanmalı")

    # Yazma akışları. Deneme kayıtları açıkça işaretlenir; cleanup.py siler.
    s, rk = http("POST", P + "/risks", {"baslik": "KABUL TESTİ — silinecek (veri gecikmesi)", "kategori": "bt", "sahip": "timasai",
                                        "olasilik": 4, "etki": 3, "gostergeler": ["logo_veri_gecikmesi"]})
    check("deneme riski açıldı (puan 12)", s == 201 and rk.get("puan") == 12, str(s))
    if s != 201:
        return finish()
    created["risks"].append(rk["id"])
    s, _ = http("PATCH", P + f"/risks/{rk['id']}", {"etki": 5})
    check("puan PATCH ile değişmez (400)", s == 400, str(s))
    s, act = http("POST", P + f"/risks/{rk['id']}/actions", {"eylem": "Kabul testi aksiyonu", "sahip": "timasai", "termin": "2020-01-01"})
    check("aksiyon eklendi, gecikti görünüyor", s == 201 and act.get("gecikti") is True, str(s))
    s, sm = http("GET", P + "/summary")
    check("özet: ısı haritasında hücre dolu", s == 200 and any(c["sayi"] >= 1 for row in sm["isiHaritasi"] for c in row), str(s))
    check("özet: geciken aksiyon listede", s == 200 and any(x["id"] == act.get("id") for x in sm["gecikenAksiyon"]), "")
    s, rv = http("POST", P + f"/risks/{rk['id']}/review", {"olasilik": 4, "etki": 4, "egilim": "sabit", "not": "kabul testi"})
    check("gözden geçirme puanı değiştirdi (16, kritik)", s == 200 and rv.get("puan") == 16 and rv.get("seviye") == "kritik", str(s))
    s, sm = http("GET", P + "/summary")
    check("gözden geçirilen risk kuyrukta yok", s == 200 and all(x["risk"]["id"] != rk["id"] for x in sm["kuyruk"]), "")

    s, it = http("POST", P + "/compliance/items", {"alan": "vergi", "madde": "KABUL TESTİ — silinecek", "siklik": "aylik",
                                                   "ilkSonGun": today.replace(day=1).isoformat()})
    check("uyum yükümlülüğü açıldı", s == 201, str(s))
    if s == 201:
        created["items"].append(it["id"])
        s, cal = http("GET", P + f"/compliance/calendar?ay={today.strftime('%Y-%m')}")
        ev = next((e for e in cal.get("items", []) if e["itemId"] == it["id"]), None) if s == 200 else None
        check("bu ayın takviminde", ev is not None, str(s))
        if ev:
            s, _ = http("POST", P + f"/compliance/events/{ev['id']}/close", {})
            check("kanıtsız ve açıklamasız kapanış 400", s == 400, str(s))
            s, up = http("POST", P + f"/compliance/events/{ev['id']}/evidence?filename=kanit.pdf", raw=b"%PDF-1.4 kabul", ctype="application/octet-stream")
            check("kanıt yüklendi", s == 200 and up.get("kanitVar"), str(s))
            s, _ = http("POST", P + f"/compliance/events/{ev['id']}/close", {})
            check("kanıtlı dönem kapandı", s == 200, str(s))
    s, pol = http("POST", P + "/policies", {"tur": "KABUL TESTİ — silinecek", "policeNo": "TR 0000 1234", "bit": today.isoformat()})
    check("poliçe numarası maskeli", s == 201 and pol.get("policeNo") == "••••1234", str(pol)[:120])
    if s == 201:
        created["policies"].append(pol["id"])

    if meta.get("modelVar"):
        s, job = http("POST", P + "/reports/draft", {"donem": "KABUL"})
        check("brifing taslağı başladı (202)", s == 202, str(s))
        if s == 202:
            created["reports"].append(job["raporId"])
            for _ in range(120):
                time.sleep(5)
                s, j = http("GET", P + f"/jobs/{job['id']}")
                if j.get("durum") != "calisiyor":
                    break
            s, rep = http("GET", P + f"/reports/{job['raporId']}")
            check("brifing taslağı hazır", s == 200 and rep.get("durum") == "taslak" and rep.get("metin"), f"kaynak {rep.get('kaynak')} not {rep.get('kaynakNotu')}")
            s, _ = http("POST", P + f"/reports/{job['raporId']}/approve", {})
            check("taslağı hazırlatan onaylayamaz (403)", s == 403, str(s))
    else:
        print("   atlandı: Zeki AI bu kurulumda tanımlı değil (brifing kural metniyle yine hazırlanır)")

    if COOKIE2:
        s, _ = http("POST", P + "/indicators/logo_veri_gecikmesi/measure", {}, cookie=COOKIE2)
        check("gösterge yetkisi olmayan ölçemez (403)", s == 403, str(s))
        s, _ = http("GET", P + f"/risks/{rk['id']}", cookie=COOKIE2)
        check("bütün riskleri göremeyen başkasının riskini görmez (404)", s in (403, 404), str(s))
    return finish()


if __name__ == "__main__":
    raise SystemExit(main())
