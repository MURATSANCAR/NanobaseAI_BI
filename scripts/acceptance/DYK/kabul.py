"""DYK Kurul — gerçek API ↔ doğrudan SQL kabulü (test sunucusunda, yan port köprüsü, salt okunur kaynaklar).

Göstergeler gerçek köprüde «şimdi ölç» ile ölçülür (M45/M46/M47/M59/M50/M48/M6 çıktıları, gerçek Logo/CRM/katalog);
paneldeki değer köprü kodu kullanılmadan yazılmış doğrudan sorguyla (`referans.sql` R1–R6) ya da kaynak modülün kendi
ucuyla karşılaştırılır. Ayrıca gri kural, paket akışı (derle → dondur → PDF sha256 → kaynak değişse de aynı → yeni
sürüm), Zeki AI özetinde olgu dışı sayı ve yetkiler denenir. Yazılan her kayıt kimliğiyle `--out` dosyasına gider;
`cleanup.py` siler (toplantı, gündem, karar, aksiyon, paket, PDF, dağıtım, iş).

Ortam: BASE (ör. http://127.0.0.1:8798), COOKIE (timasai'nin 15 dk'lık oturumu; yönetici), isteğe bağlı COOKIE2
(yöneticisi olmayan ikinci oturum; yoksa yetki denemeleri atlanır), SEMANTIC_CONNECTION_FILE (Logo),
SEMANTIC_CRM_CONNECTION_FILE, PYTHONPATH=<aday ağaç>/backend, isteğe bağlı CRM_SCHEMA.
Kullanım: python kabul.py --out /tmp/claude-dyk/kabul-kimlikler.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone

from semantic_bridge import budget_sources as bsrc
from semantic_bridge import kurul as K

BASE = os.environ.get("BASE", "http://127.0.0.1:8798").rstrip("/")
COOKIE = os.environ.get("COOKIE", "")
COOKIE2 = os.environ.get("COOKIE2", "")
P = BASE + "/api/v1/kurul"
SCHEMA = os.environ.get("CRM_SCHEMA", "Timas_MSCRM.dbo")
results: list[tuple[str, bool, str]] = []


def http(method: str, url: str, body=None, timeout=1800, cookie=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method, headers={"Cookie": cookie or COOKIE, "Content-Type": "application/json",
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


def f(v) -> float:
    return float(v or 0)


def day(v) -> date:
    return v if isinstance(v, date) and not isinstance(v, datetime) else (v.date() if isinstance(v, datetime) else date.fromisoformat(str(v)[:10]))


def wait_measure(limit_s: int = 900) -> None:
    t0 = time.time()
    while time.time() - t0 < limit_s:
        s, st = http("GET", P + "/status")
        if s == 200 and not st.get("olcumSuruyor"):
            return
        time.sleep(5)


def wait_job(jid: str, limit_s: int = 900) -> dict:
    t0 = time.time()
    while time.time() - t0 < limit_s:
        s, j = http("GET", P + f"/jobs/{jid}")
        if s == 200 and j.get("durum") != "calisiyor":
            return j
        time.sleep(3)
    return {"durum": "zaman_asimi"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    started = datetime.now(timezone.utc).isoformat()
    created: dict[str, list[str]] = {"meetings": [], "packages": []}

    def finish() -> int:
        with open(a.out, "w") as fh:
            json.dump({**created, "since": started}, fh)
        ok = sum(1 for r in results if r[1])
        print(f"== SONUÇ: {ok}/{len(results)} geçti; kimlikler {a.out} (cleanup.py ile silin)")
        return 0 if ok == len(results) else 1

    logo = bsrc.runner(os.environ["SEMANTIC_CONNECTION_FILE"])
    crm = bsrc.runner(os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json"))
    firms = bsrc.firms_by_year(logo)

    # 0 · Geçersiz istekler (yazmadan önce).
    s, meta = http("GET", P + "/meta")
    check("meta 200", s == 200, str(s))
    s, _ = http("POST", P + "/meetings", {})
    check("tarihsiz toplantı 400", s == 400, str(s))
    s, _ = http("GET", P + "/indicators/yok_boyle")
    check("olmayan gösterge 404", s == 404, str(s))
    s, _ = http("POST", P + "/packages/yok-boyle/freeze")
    check("olmayan paketi dondurma 404", s == 404, str(s))

    # 1 · Ölç.
    s, r = http("POST", P + "/refresh")
    check("ölçüm başladı (202)", s == 202, str(r)[:200])
    time.sleep(3)
    wait_measure()
    s, panel = http("GET", P + "/panel")
    check("panel 200", s == 200, str(s))
    if s != 200:
        return finish()
    g = {x["kod"]: x for b in panel["bolumler"] for x in b["gostergeler"]}
    print(f"-- panel {panel['donem']}: {panel['sayilar']}", flush=True)

    # R1 · Net satış (yıl başından) ↔ doğrudan STLINE.
    ns = g.get("net_satis") or {}
    if ns.get("durum") == "ok":
        end = day(ns["veriSonGunu"])
        firm = firms[end.year]
        ref = f(logo(f"""SELECT SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN 1 ELSE -1 END * S.LINENET) AS net
            FROM dbo.LG_{firm}_01_STLINE AS S WHERE S.CANCELLED = 0 AND S.LINETYPE = 0 AND S.INVOICEREF <> 0 AND S.TRCODE IN (2,3,7,8,9)
            AND S.DATE_ >= '{end.year}-01-01' AND S.DATE_ < '{(end + timedelta(days=1)).isoformat()}'""")[0]["net"])
        check("R1 net satış = doğrudan satır toplamı", abs(ns["deger"] - ref) < 0.01, f"panel {ns['deger']:.2f} / SQL {ref:.2f} (veri son günü {end})")
        inv = f(logo(f"""SELECT SUM(CASE WHEN TRCODE IN (7,8,9) THEN NETTOTAL ELSE -NETTOTAL END) AS n FROM dbo.LG_{firm}_01_INVOICE
            WHERE CANCELLED = 0 AND TRCODE IN (2,3,7,8,9) AND DATE_ >= '{end.year}-01-01' AND DATE_ < '{end.year + 1}-01-01'""")[0]["n"])
        print(f"-- bilgi: fatura başlığı seviyesinde net ciro {inv:.2f} (analiz: 848.110.178,82); satır seviyesiyle fark {inv - ref:.2f}", flush=True)
        # R2 · Geçen yılın aynı dönemi.
        if (end.year - 1) in firms:
            try:
                same = end.replace(year=end.year - 1)
            except ValueError:
                same = end.replace(year=end.year - 1, day=28)
            prev = f(logo(f"""SELECT SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN 1 ELSE -1 END * S.LINENET) AS net
                FROM dbo.LG_{firms[end.year - 1]}_01_STLINE AS S WHERE S.CANCELLED = 0 AND S.LINETYPE = 0 AND S.INVOICEREF <> 0
                AND S.TRCODE IN (2,3,7,8,9) AND S.DATE_ >= '{same.year}-01-01' AND S.DATE_ < '{(same + timedelta(days=1)).isoformat()}'""")[0]["net"])
            check("R2 geçen yıl aynı dönem = doğrudan satır toplamı", ns.get("onceki") is not None and abs(ns["onceki"] - prev) < 0.01,
                  f"panel {ns.get('onceki')} / SQL {prev:.2f} ({same})")
        # R3 · Brüt kâr marjı.
        bm = g.get("brut_kar_marji") or {}
        r3 = logo(f"""SELECT SUM(CASE WHEN S.OUTCOST <> 0 THEN CASE WHEN S.TRCODE IN (7,8,9) THEN 1 ELSE -1 END * S.LINENET ELSE 0 END) AS mn,
            SUM(CASE WHEN S.OUTCOST <> 0 THEN CASE WHEN S.TRCODE IN (7,8,9) THEN 1 ELSE -1 END * S.AMOUNT * S.OUTCOST ELSE 0 END) AS mc
            FROM dbo.LG_{firm}_01_STLINE AS S WHERE S.CANCELLED = 0 AND S.LINETYPE = 0 AND S.INVOICEREF <> 0 AND S.TRCODE IN (2,3,7,8,9)
            AND S.DATE_ >= '{end.year}-01-01' AND S.DATE_ < '{(end + timedelta(days=1)).isoformat()}'""")[0]
        ref3 = (f(r3["mn"]) - f(r3["mc"])) / f(r3["mn"]) * 100 if f(r3["mn"]) else None
        check("R3 brüt kâr marjı = doğrudan (0,01 puan)", bm.get("durum") == "ok" and ref3 is not None and abs(bm["deger"] - ref3) < 0.01,
              f"panel {bm.get('deger')} / SQL {ref3}")
        # R4 · Kasa ve banka.
        kb = g.get("kasa_banka") or {}
        ref4 = f(logo(f"""SELECT SUM(L.DEBIT - L.CREDIT) AS kb FROM dbo.LG_{firm}_01_EMFLINE AS L
            JOIN dbo.LG_{firm}_01_EMFICHE AS F ON F.LOGICALREF = L.ACCFICHEREF JOIN dbo.LG_{firm}_EMUHACC AS A ON A.LOGICALREF = L.ACCOUNTREF
            WHERE L.CANCELLED = 0 AND F.CANCELLED = 0 AND A.CODE LIKE '10[02]%'
            AND L.DATE_ >= '{end.year}-01-01' AND L.DATE_ < '{(end + timedelta(days=1)).isoformat()}'""")[0]["kb"])
        if kb.get("durum") == "ok":
            check("R4 kasa ve banka = doğrudan muhasebe bakiyesi", abs(kb["deger"] - ref4) < 0.01, f"panel {kb['deger']:.2f} / SQL {ref4:.2f}")
        else:
            check("R4 kasa ve banka hazır değilse gri (sayı yok)", kb.get("deger") is None, f"durum {kb.get('durum')}: {kb.get('not')}")
    else:
        check("R1 net satış ölçüldü", False, f"durum {ns.get('durum')}: {ns.get('not')}")

    # R5 · Süresi yaklaşan sözleşme ↔ CRM.
    sz = g.get("sozlesme_bitecek") or {}
    n = int(crm(f"""SELECT COUNT(*) AS n FROM {SCHEMA}.new_sozlesmeBase s WHERE s.statecode = 0 AND s.statuscode IN (100000000, 100000006, 100000007)
        AND ISNULL(s.new_suresizsozlesme, 0) = 0 AND s.new_SozlesmeBitisTarihi >= CAST(GETDATE() AS date)
        AND s.new_SozlesmeBitisTarihi < DATEADD(day, 61, CAST(GETDATE() AS date))""")[0]["n"])
    check("R5 60 günde biten sözleşme = CRM (EDITORIAL_CONTRACT_WARN_DAYS=60)", sz.get("durum") == "ok" and sz["deger"] == float(n),
          f"panel {sz.get('deger')} ({sz.get('durum')}) / SQL {n}")

    # R6 · Logo verisinin yaşı.
    lv = g.get("logo_veri_gecikmesi") or {}
    cur = firms[max(firms)]
    last = day(logo(f"SELECT MAX(DATE_) AS son FROM dbo.LG_{cur}_01_INVOICE WHERE CANCELLED = 0")[0]["son"])
    if lv.get("durum") == "ok":
        check("R6 Logo veri son günü = son fatura", day(lv["veriSonGunu"]) == last and lv["deger"] == float((date.today() - last).days),
              f"panel {lv['deger']} ({lv['veriSonGunu']}) / SQL {(date.today() - last).days} ({last})")
    else:
        check("R6 sistem durumu ölçülmediyse gri", lv.get("deger") is None, f"durum {lv.get('durum')}: {lv.get('not')}")

    # Uç ↔ uç: bütçe (analiz kabul 3), bayi, risk, Zeki AI.
    bs = g.get("butce_satis") or {}
    yr = day(ns["veriSonGunu"]).year if ns.get("veriSonGunu") else date.today().year
    s, tr = http("GET", BASE + f"/api/v1/budget/tracking?year={yr}")
    if s == 200 and tr.get("plan") and (tr.get("sirket") or {}).get("oran") is not None:
        check("K3 bütçe oranı = bütçe izleme ucu", bs.get("durum") == "ok" and abs(bs["deger"] - tr["sirket"]["oran"] * 100) < 1e-6,
              f"panel {bs.get('deger')} / uç {tr['sirket']['oran'] * 100}")
    else:
        check("K3 onaylı plan yoksa bütçe göstergesi gri (değer 0 değil)", bs.get("durum") == "kaynak_yok" and bs.get("deger") is None,
              f"tracking {s}, panel {bs.get('durum')}: {bs.get('not')}")
    s, ds = http("GET", BASE + "/api/v1/dealers/summary")
    bv = g.get("bayi_vadesi_gecmis") or {}
    if s == 200 and ds.get("gun"):
        check("bayi vadesi geçmiş = bayi riski ucu", bv.get("durum") == "ok" and abs(bv["deger"] - f(ds["vadesiGecmis"])) < 0.01,
              f"panel {bv.get('deger')} / uç {ds.get('vadesiGecmis')}")
    else:
        check("bayi turu koşmadıysa gri", bv.get("deger") is None, f"dealers {s}")
    s, rs = http("GET", BASE + "/api/v1/risk/summary")
    rk = g.get("risk_kritik") or {}
    if s == 200 and (rs.get("sayilar") or {}).get("canli"):
        check("kritik risk = risk özeti ucu", rk.get("durum") == "ok" and rk["deger"] == float(rs["sayilar"]["kritik"]),
              f"panel {rk.get('deger')} / uç {rs['sayilar']['kritik']}")
    else:
        check("risk kaydı boşsa gri", rk.get("durum") == "kaynak_yok" and rk.get("deger") is None, f"risk {s}")
    s, sc = http("GET", BASE + "/api/v1/model-quality/scorecard")
    zc = g.get("zeki_cevaplama") or {}
    bi = next((x for x in (sc.get("rows") or []) if x.get("id") == "bi"), None) if s == 200 else None
    rate = next((m.get("value") for m in (bi or {}).get("metrics", []) if m.get("key") == "answeredRate"), None)
    if rate is not None:
        check("Zeki AI cevaplama = karne ucu (0,01 puan)", zc.get("durum") == "ok" and abs(zc["deger"] - rate * 100) < 0.01,
              f"panel {zc.get('deger')} / karne {rate * 100}")
    else:
        check("karne ölçmediyse gri", zc.get("deger") is None, f"scorecard {s}")

    # Gri kural: sağlayıcısı olmayan gösterge sayı ve renk taşımaz.
    for kod in ("stok_riski", "pazarlama_plani", "ik_saglik"):
        x = g.get(kod) or {}
        check(f"gri: {kod}", x.get("durum") == "kaynak_yok" and x.get("deger") is None and x.get("renk") is None and x.get("degerMetin") is None,
              str({k: x.get(k) for k in ("durum", "deger", "renk")}))
    bad = [k for k, x in g.items() if x["durum"] != "ok" and (x.get("deger") is not None or x.get("renk"))]
    check("hazır olmayan hiçbir gösterge sayı ya da renk taşımıyor", not bad, str(bad))

    # Paket akışı: derle → dondur → PDF sha256 → yeniden ölçüm sonrası aynı → yeni derleme yeni sürüm.
    tarih = (date.today() + timedelta(days=30)).isoformat()
    s, m = http("POST", P + "/meetings", {"tarih": tarih, "baslik": "Kabul denemesi (silinecek)"})
    check("toplantı açıldı", s == 201, str(m)[:200])
    if s != 201:
        return finish()
    created["meetings"].append(m["id"])
    s, p1 = http("POST", P + f"/meetings/{m['id']}/packages")
    check("paket derlendi", s == 201 and p1.get("surum") == 1, str(p1)[:200])
    if s == 201:
        created["packages"].append(p1["id"])
        s, fr = http("POST", P + f"/packages/{p1['id']}/freeze")
        check("paket donduruldu", s == 200 and fr.get("durum") == "donduruldu" and fr.get("pdfSha256"), str(fr)[:200])
        s, pdf = http("GET", P + f"/packages/{p1['id']}/document.pdf")
        check("PDF sha256 = kayıt", s == 200 and isinstance(pdf, bytes) and hashlib.sha256(pdf).hexdigest() == fr.get("pdfSha256"),
              f"{s}, {len(pdf) if isinstance(pdf, bytes) else pdf}")
        http("POST", P + "/refresh")
        time.sleep(3)
        wait_measure()
        s, again = http("GET", P + f"/packages/{p1['id']}")
        check("yeniden ölçümden sonra dondurulmuş içerik aynı", s == 200 and again["icerikSha256"] == fr["icerikSha256"]
              and again["pdfSha256"] == fr["pdfSha256"], f"{again.get('icerikSha256')} / {fr.get('icerikSha256')}")
        s, pdf2 = http("GET", P + f"/packages/{p1['id']}/document.pdf")
        check("PDF ikinci indirmede aynı bayt", s == 200 and pdf2 == pdf)
        s, dist = http("GET", P + f"/packages/{p1['id']}")
        check("indirme dağıtım kaydına yazıldı", sum(1 for d in dist.get("dagitim", []) if d["kanal"] == "indirme") >= 2)
        s, p2 = http("POST", P + f"/meetings/{m['id']}/packages")
        check("yeni derleme yeni sürüm", s == 201 and p2.get("surum") == 2, str(p2)[:120])
        if s == 201:
            created["packages"].append(p2["id"])
            if meta.get("modelVar"):
                s, j = http("POST", P + f"/packages/{p2['id']}/summary/draft")
                job = wait_job(j["id"]) if s == 202 else {"durum": "baslamadi"}
                s, pk = http("GET", P + f"/packages/{p2['id']}")
                if job.get("durum") == "bitti" and pk.get("ozetMetin"):
                    extra = K.foreign_numbers(pk["ozetMetin"], K.summary_facts(pk["icerik"]))
                    check("Zeki AI özetinde olgu dışı sayı yok", not extra, str(sorted(extra)))
                else:
                    check("olgu dışı sayılı taslak kaydedilmedi (ya da model yanıt vermedi)", not pk.get("ozetMetin"),
                          f"iş {job.get('durum')}: {job.get('hata')}")

    # Yetki: yönetici olmayan ikinci oturum.
    if COOKIE2:
        s, _ = http("GET", P + "/panel", cookie=COOKIE2)
        print(f"-- bilgi: ikinci oturum panel {s} (sayfa:kurul rolünde yoksa 403 beklenir)")
        if created["packages"]:
            s, _ = http("POST", P + f"/packages/{created['packages'][-1]}/freeze", cookie=COOKIE2)
            check("kurul.dondur olmayan dondurma → 403", s == 403, str(s))
        s, _ = http("POST", P + "/run-due", cookie=COOKIE2)
        check("kişi zamanlayıcı ucunu tetikleyemez → 403", s == 403, str(s))
    else:
        print("-- COOKIE2 yok: yetki denemeleri DOĞRULANAMADI")
    return finish()


if __name__ == "__main__":
    raise SystemExit(main())
