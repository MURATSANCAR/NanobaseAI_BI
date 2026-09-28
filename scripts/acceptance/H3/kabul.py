"""H3 E-ticaret müşteri yönetimi — gerçek API ↔ doğrudan SQL / doğrudan T-soft kabulü (test sunucusunda, yan port köprüsü).

Uçların kullanıcıya verdiği sayılar köprü kodu kullanılmadan yazılmış sorgularla karşılaştırılır:

- K1  sipariş sayısı: T-soft `order/get` (yalnız okuma, sonuna kadar sayfalanır) bir gün = portal sipariş tablosu
- K2  Logo timas.com.tr kanalı net ciro, ay: `STLINE` faturalı satır × M42 eşlemesindeki cari/kanal kodu = özet
- K3  CRM'de son 12 ayda B2C sipariş = 0 («kaynak T-soft» kararının kanıtı)
- K4  sipariş satırı barkod eşleşmesi: CRM `new_kitapBase.new_ean13` ile doğrudan ↔ portal satırındaki kitap bağı
- K5  RFM: son 90 günde siparişi olan müşteri iki yoldan (müşteri tablosu / sipariş tablosu) ve API matrisi toplamı
- K6  kişisel veri yok: `semantic_commerce_*` hiçbir kolonda e-posta ya da cep telefonu biçimli değer
- K7  aday sayısı doğrudan SQL ile; kontrol = round(ulaşılabilir × pay) (±1)
- K8  dünün özeti: API sipariş/ciro = doğrudan SQL (geçerli sipariş)
- K9  M42 D2C sekmesi site özeti = doğrudan SQL (yıl başından dönem sonuna, iptal/iade hariç)
- K10 sözleşme ucu segment toplamı = müşteri tablosu

Yazma (test verisi, `temizlik.py` siler): bir tetik («H3 kabul (silinecek)») ve onun tek listesi. Liste onaylanmaz, dışa
aktarılmaz; kimse ileti almaz. Kimlikler `--out` dosyasına yazılır.

Ortam: BASE (ör. http://127.0.0.1:8798), COOKIE (timasai'nin kısa oturum çerezi), SEMANTIC_CRM_CONNECTION_FILE, CRM_SCHEMA,
köprünün ortamı (katalog veritabanı, READERS_HASH_SALT, Logo bağlantı dosyası), PYTHONPATH=<aday ağaç>/backend.
Kullanım: python kabul.py --out /tmp/claude-h3/kabul-kimlikler.json [--gun 2026-09-20]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone

import sqlalchemy as sa

from semantic_bridge import admin as admin_mod
from semantic_bridge import budget_sources as bsrc
from semantic_bridge import commerce as C
from semantic_bridge import commerce_sources as src
from semantic_bridge.seo_geo import connections
from semantic_layer.config import SemanticSettings
from semantic_layer.store.catalog_store import open_store

BASE = os.environ.get("BASE", "http://127.0.0.1:8798").rstrip("/")
COOKIE = os.environ.get("COOKIE", "")
P = BASE + "/api/v1/commerce"
SCHEMA = os.environ.get("CRM_SCHEMA", "Timas_MSCRM.dbo")
results: list[tuple[str, bool, str]] = []


def http(method: str, url: str, body=None, timeout=1800):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method, headers={"Cookie": COOKIE, "Content-Type": "application/json"})
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


def info(name: str, detail: str) -> None:
    print(f"BİLGİ {name} — {detail}", flush=True)


def raw_day(v) -> date | None:
    """Referans için bağımsız tarih okuması (köprünün ayrıştırıcısı kullanılmaz)."""
    if v in (None, ""):
        return None
    s = str(v).strip()
    if s.isdigit():
        return datetime.fromtimestamp(int(s) / (1000 if len(s) > 11 else 1)).date()
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return date(int(m[1]), int(m[2]), int(m[3]))
    m = re.match(r"(\d{2})[./](\d{2})[./](\d{4})", s)
    return date(int(m[3]), int(m[2]), int(m[1])) if m else None


def lit(v: str) -> str:
    return "N'" + str(v).replace("'", "''") + "'"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--gun", help="K1 için gün (YYYY-AA-GG); boşsa dün")
    a = ap.parse_args()
    started = datetime.now(timezone.utc).isoformat()
    st = SemanticSettings.from_env()
    engine = open_store(st.store_dsn, create=False).engine
    admin_mod.ensure(engine)   # ekrandan kaydedilen ayarlar (T-soft girişi) veritabanında; bağlanmazsa conf yalnız ortamı okur
    tenant = st.tenant_id
    ids: dict = {"startedAt": started, "tenant": tenant, "triggers": [], "runs": []}
    crm = bsrc.runner(os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json"))
    conf = lambda k, d="": admin_mod.conf(k, d)  # noqa: E731
    today = date.today()

    def save() -> None:
        with open(a.out, "w") as fh:
            json.dump(ids, fh)

    # 0. Geçersiz istekler (yazmadan önce).
    s, meta = http("GET", P + "/meta")
    check("meta 200", s == 200, str(s))
    s, _ = http("POST", P + "/triggers", {})
    check("boş gövdeyle tetik 400", s == 400, str(s))
    s, _ = http("POST", P + "/triggers", {"name": "H3 kabul sepet", "kind": "terk-sepeti"})
    check("terk sepeti tetiği 409 (sepet verisi yok)", s == 409, str(s))
    s, _ = http("GET", P + "/customers/yok-boyle")
    check("olmayan müşteri 404", s == 404, str(s))
    s, _ = http("POST", P + "/runs/yok-boyle/approve", {})
    check("olmayan liste onayı 404/403", s in (404, 403), str(s))
    s, _ = http("PUT", P + "/settings", {"controlShare": 0.9})
    check("sınır dışı eşik 400/403", s in (400, 403), str(s))
    if not isinstance(meta, dict) or not (meta.get("freshness") or {}).get("okAt"):
        check("site siparişleri okunmuş", False, "önce POST /refresh {\"full\": true} ya da run-due koşturun")
        save()
        return finish(a.out)

    # K1 sipariş sayısı: T-soft'tan doğrudan (yalnız okuma) ↔ portal tablosu.
    d1 = date.fromisoformat(a.gun) if a.gun else today - timedelta(days=1)
    f = src.fields(conf)
    path = conf("COMMERCE_TSOFT_ORDER_PATH", "order/get") or "order/get"
    if not connections.READ_ONLY.match(path):
        raise SystemExit(f"{path} yalnız okuma yöntemi değil")
    n_ref, start, total = 0, 0, 0
    seen: set[str] = set()
    while True:
        rows = connections.tsoft.call(path, {"start": start, "limit": 500}).get("data") or []
        total += len(rows)
        for r in rows:
            _k, no = src.pick(r, f["order_no"])
            _k, dt = src.pick(r, f["ordered_at"])
            if no is not None and raw_day(dt) == d1 and str(no) not in seen:
                seen.add(str(no))
                n_ref += 1
        if len(rows) < 500:
            break
        start += len(rows)
    lo, hi = datetime.combine(d1, datetime.min.time()), datetime.combine(d1 + timedelta(days=1), datetime.min.time())
    with engine.connect() as c:
        n_portal = c.execute(sa.select(sa.func.count()).select_from(C.ORDERS).where(
            C.ORDERS.c.tenant_id == tenant, C.ORDERS.c.ordered_at >= lo, C.ORDERS.c.ordered_at < hi)).scalar()
    check(f"K1 {d1} sipariş sayısı T-soft = portal", n_ref == n_portal, f"T-soft {n_ref} (toplam {total} okundu) · portal {n_portal}")

    # K2 Logo timas.com.tr kanalı net ciro (ay) ↔ özet.
    s, ov = http("GET", P + "/overview?period=ay")
    check("özet 200", s == 200, str(s))
    lg = (ov or {}).get("logo") or {} if isinstance(ov, dict) else {}
    if not lg.get("bagli"):
        info("K2 Logo kanal cirosu", f"bağlı değil: {lg.get('neden')}")
    else:
        from semantic_bridge.channels import mapping as CM
        from semantic_bridge.channels import store as CS
        run = bsrc.runner(st.connection_file)
        firm = bsrc.firms_by_year(run)[lg["yil"]]
        caris = [k for k, v in CS.approved_map(engine, tenant).items() if v == CM.D2C]
        kanal = [k for k, v in CM.kanal_map(engine, tenant).items() if v == CM.D2C]
        conds = []
        if caris:
            conds.append("c.CODE IN (" + ", ".join(lit(x) for x in caris) + ")")
        if kanal:
            conds.append("c.SPECODE2 IN (" + ", ".join(lit(x) for x in kanal) + ")")
        m0 = date(lg["yil"], lg["ay"], 1)
        m1 = (m0 + timedelta(days=32)).replace(day=1)
        sql = (f"SELECT SUM(CASE WHEN s.TRCODE IN (7,8,9) THEN s.LINENET ELSE -s.LINENET END) AS n FROM LG_{firm}_01_STLINE s "
               f"JOIN LG_{firm}_CLCARD c ON c.LOGICALREF = s.CLIENTREF WHERE s.CANCELLED = 0 AND s.LINETYPE = 0 AND s.INVOICEREF <> 0 "
               f"AND s.TRCODE IN (2,3,7,8,9) AND ({' OR '.join(conds) or '1=0'}) AND s.DATE_ >= '{m0}' AND s.DATE_ < '{m1}'")
        ref = float(run(sql)[0].get("n") or 0)
        check("K2 Logo timas.com.tr net ciro (ay) = özet", abs(ref - float(lg["netCiro"] or 0)) <= 0.01,
              f"{lg['ayAdi']} {lg['yil']}: SQL {ref:.2f} · özet {lg['netCiro']} · cari {len(caris)}, kanal kodu {len(kanal)}")

    # K3 CRM'de son 12 ayda B2C sipariş yok.
    n3 = crm(f"SELECT COUNT(*) AS n FROM {SCHEMA}.new_siparisBase WHERE (new_b2cid IS NOT NULL OR new_yenib2cid IS NOT NULL) "
             f"AND CreatedOn >= DATEADD(month, -12, GETDATE())")[0]["n"]
    check("K3 CRM'de son 12 ayda B2C sipariş = 0 (kaynak T-soft)", n3 == 0, f"CRM {n3}")

    # K4 barkod eşleşmesi: CRM'den doğrudan ↔ portal satırındaki kitap bağı.
    with engine.connect() as c:
        lines = list(c.execute(sa.select(C.LINES.c.barcode, C.LINES.c.book_id).where(C.LINES.c.tenant_id == tenant)))
    codes = sorted({r.barcode for r in lines if r.barcode and re.fullmatch(r"\d{8,14}", r.barcode)})
    crm_eans: set[str] = set()
    for i in range(0, len(codes), 500):
        part = codes[i:i + 500]
        for r in crm(f"SELECT new_ean13 AS e FROM {SCHEMA}.new_kitapBase WHERE new_ean13 IN ({', '.join(lit(x) for x in part)})"):
            crm_eans.add(re.sub(r"\D", "", str(r["e"])))
    ref_match = sum(1 for r in lines if r.barcode in crm_eans)
    portal_match = sum(1 for r in lines if r.book_id)
    unmatched = sorted({r.barcode for r in lines if r.barcode and r.barcode not in crm_eans})
    check("K4 satır barkodu CRM kitap kartıyla eşleşme (portal ≤ CRM; fark kitap profili kapsamı)", portal_match <= ref_match,
          f"satır {len(lines)} · CRM'de eşleşen {ref_match} · portalda kitap bağı {portal_match} · eşleşmeyen barkod "
          f"{len(unmatched)} {unmatched[:10]}")

    # K5 RFM iki yol + API matrisi.
    cut = datetime.combine(today - timedelta(days=90), datetime.min.time())
    with engine.connect() as c:
        k5a = c.execute(sa.select(sa.func.count()).select_from(C.CUSTOMERS).where(
            C.CUSTOMERS.c.tenant_id == tenant, C.CUSTOMERS.c.last_order >= cut)).scalar()
        k5b = c.execute(sa.select(sa.func.count(sa.distinct(C.ORDERS.c.customer_key))).where(
            C.ORDERS.c.tenant_id == tenant, C.ORDERS.c.valid.is_(True), C.ORDERS.c.ordered_at >= cut)).scalar()
        buyers = c.execute(sa.select(sa.func.count()).select_from(C.CUSTOMERS).where(
            C.CUSTOMERS.c.tenant_id == tenant, C.CUSTOMERS.c.orders > 0)).scalar()
        allc = c.execute(sa.select(sa.func.count()).select_from(C.CUSTOMERS).where(C.CUSTOMERS.c.tenant_id == tenant)).scalar()
    check("K5a son 90 gün: müşteri tablosu = sipariş tablosu", k5a == k5b, f"{k5a} · {k5b} (müşteri tablosu okumada kurulur; okumadan sonra koşun)")
    s, rfm = http("GET", P + "/customers/rfm")
    tot = sum(x["musteri"] for x in rfm["matrix"]) if s == 200 else None
    check("K5b API matrisi toplamı = siparişli müşteri", tot == buyers, f"{tot if s == 200 else s} · SQL {buyers}")

    # K6 kişisel veri taraması.
    phone = re.compile(r"^\+?(90)?0?5\d{9}$")
    bad = 0
    with engine.connect() as c:
        for t in (C.ORDERS, C.LINES, C.CUSTOMERS, C.MOVES, C.PRODUCT_STATS, C.TRIGGERS, C.RUNS, C.RUN_MEMBERS, C.CAMPAIGNS, C.META):
            for row in c.execute(sa.select(t)):
                for v in row:
                    if isinstance(v, str) and ("@" in v or phone.match(re.sub(r"[\s()-]", "", v))):
                        bad += 1
    check("K6 semantic_commerce_* içinde e-posta/telefon biçimli değer yok", bad == 0, f"{bad} değer")

    # K8 dünün özeti.
    s, ovd = http("GET", P + "/overview?period=dun")
    y0 = datetime.combine(today - timedelta(days=1), datetime.min.time())
    with engine.connect() as c:
        r8 = c.execute(sa.select(sa.func.count(), sa.func.coalesce(sa.func.sum(C.ORDERS.c.total), 0)).where(
            C.ORDERS.c.tenant_id == tenant, C.ORDERS.c.valid.is_(True), C.ORDERS.c.ordered_at >= y0,
            C.ORDERS.c.ordered_at < y0 + timedelta(days=1))).first()
    ok8 = s == 200 and ovd["cur"]["siparis"] == r8[0] and abs(ovd["cur"]["ciro"] - float(r8[1])) <= 0.01
    check("K8 dün sipariş ve ciro = doğrudan SQL", ok8,
          f"API {(ovd['cur']['siparis'], ovd['cur']['ciro']) if s == 200 else s} · SQL {(r8[0], round(float(r8[1]), 2))}")

    # K9 M42 D2C sekmesi.
    s, d2c = http("GET", BASE + "/api/v1/channels/d2c")
    site = (d2c or {}).get("site") or {} if isinstance(d2c, dict) else {}
    if s != 200 or not site.get("bagli"):
        info("K9 D2C site özeti", f"HTTP {s}; {site.get('neden')}")
    else:
        p = d2c["period"]
        lo9 = datetime(p["yil"], 1, 1)
        hi9 = (datetime(p["yil"], p["ay"], 1) + timedelta(days=32)).replace(day=1)
        with engine.connect() as c:
            n9 = c.execute(sa.select(sa.func.count()).select_from(C.ORDERS).where(
                C.ORDERS.c.tenant_id == tenant, C.ORDERS.c.valid.is_(True), C.ORDERS.c.ordered_at >= lo9,
                C.ORDERS.c.ordered_at < hi9)).scalar()
        check("K9 D2C site sipariş sayısı = doğrudan SQL (iptal/iade hariç)", site["siparis"] == n9, f"D2C {site['siparis']} · SQL {n9}")

    # K10 sözleşme ucu.
    s, ss = http("GET", P + "/segments/summary")
    tot10 = sum(x["musteri"] for x in ss["segmentler"]) if s == 200 else None
    check("K10 segment toplamı = müşteri tablosu", tot10 == allc, f"{tot10 if s == 200 else s} · SQL {allc}")
    for pth in ("/customers?segment=sadik", "/products/funnel?days=30", "/triggers", "/runs", "/campaigns", "/settings", "/mine",
                "/triggers/new-books", "/customers/moves"):
        s, _ = http("GET", P + pth)
        check(f"GET {pth} 200", s == 200, str(s))

    # K7 yazma: tetik → önizleme (adaylar doğrudan SQL) → liste (kontrol payı). Onay ve dışa aktarım yok.
    body = {"name": "H3 kabul (silinecek)", "kind": "geri-kazanim", "channel": "email", "controlShare": 0.2,
            "params": {"minGun": 90, "maxGun": 365, "minSiparis": 1}}
    s, t = http("POST", P + "/triggers", body)
    check("tetik 201", s == 201, str(s))
    if s == 201:
        ids["triggers"].append(t["id"])
        save()
        s, pv = http("POST", P + f"/triggers/{t['id']}/preview", {})
        with engine.connect() as c:
            rows7 = list(c.execute(sa.select(C.CUSTOMERS.c.last_order).where(C.CUSTOMERS.c.tenant_id == tenant, C.CUSTOMERS.c.orders >= 1)))
        n7 = sum(1 for r in rows7 if r.last_order and 90 <= (today - r.last_order.date()).days <= 365)
        check("K7a aday sayısı = doğrudan hesap (son sipariş 90–365 gün önce)", s == 200 and pv["candidates"] == n7,
              f"API {pv.get('candidates') if s == 200 else s} · SQL {n7}")
        s, run = http("POST", P + f"/triggers/{t['id']}/run", {})
        check("liste 201", s == 201, str(s))
        if s == 201:
            ids["runs"].append(run["id"])
            save()
            exp = round(run["reachable"] * 0.2)
            check("K7b kontrol = round(ulaşılabilir × pay) ±1", abs(run["control"] - exp) <= 1 and run["target"] + run["control"] == run["reachable"],
                  f"ulaşılabilir {run['reachable']} · kontrol {run['control']} · beklenen {exp}")
            s, _ = http("POST", P + f"/runs/{run['id']}/export", {"purpose": "kabul denemesi"})
            check("onaysız liste dışa aktarılamaz (409/403)", s in (409, 403), str(s))
            s, _ = http("POST", P + f"/runs/{run['id']}/approve", {})
            check("listeyi çalıştıran onaylayamaz (403)", s == 403, str(s))
        s, _ = http("PATCH", P + f"/triggers/{t['id']}", {"archive": True})
        check("tetik arşive kaldırıldı", s == 200, str(s))
    save()
    return finish(a.out)


def finish(out_path: str) -> int:
    ok = sum(1 for r in results if r[1])
    print(f"== SONUÇ: {ok}/{len(results)} geçti; kimlikler {out_path} (temizlik.py ile silin)")
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
