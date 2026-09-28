"""H2 Okuyucu veri tabanı — gerçek API ↔ doğrudan CRM SQL kabulü (test sunucusunda, yan port köprüsü).

Uçların kullanıcıya verdiği sayılar, köprü kodu kullanılmadan yazılmış doğrudan CRM sorgularıyla karşılaştırılır
(`referans.sql` R1–R10). Kaynak okuması bu betikte `POST /refresh` ile başlatılır ve bitmesi beklenir (okur
tabloları modülün kendi durumudur; test verisi değildir).

Yazma (test verisi, `cleanup.py` siler): bir taslak segment (önizleme sayısı portal tablosuna doğrudan SQL ile
karşılaştırılır, sonra arşivlenir) ve yapay adresli (`@ornek.invalid`) üç satırlık bir etkinlik dosyası (eşleşme
olmamalı; hemen silinir). Kimlikler `--out` dosyasına yazılır. Gerçek kişi verisi yazılmaz, dışa aktarım yapılmaz.

Ortam: BASE (ör. http://127.0.0.1:8798), COOKIE (timasai'nin kısa oturum çerezi), SEMANTIC_CRM_CONNECTION_FILE,
CRM_SCHEMA (varsayılan Timas_MSCRM.dbo), köprünün ortamı (katalog veritabanı için SemanticSettings; READERS_HASH_SALT),
PYTHONPATH=<aday ağaç>/backend.
Kullanım: python kabul.py --out /tmp/claude-h2/kabul-kimlikler.json
"""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timezone

import sqlalchemy as sa

from semantic_bridge import budget_sources as bsrc
from semantic_bridge import readers as R
from semantic_layer.config import SemanticSettings
from semantic_layer.store.catalog_store import open_store

BASE = os.environ.get("BASE", "http://127.0.0.1:8798").rstrip("/")
COOKIE = os.environ.get("COOKIE", "")
P = BASE + "/api/v1/readers"
SCHEMA = os.environ.get("CRM_SCHEMA", "Timas_MSCRM.dbo")
results: list[tuple[str, bool, str]] = []


def http(method: str, url: str, body=None, timeout=900, raw_body: bytes | None = None, ctype="application/json"):
    data = raw_body if raw_body is not None else (None if body is None else json.dumps(body).encode())
    req = urllib.request.Request(url, data=data, method=method, headers={"Cookie": COOKIE, "Content-Type": ctype})
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    started = datetime.now(timezone.utc).isoformat()
    crm = bsrc.runner(os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json"))
    st = SemanticSettings.from_env()
    engine = open_store(st.store_dsn, create=False).engine
    tenant = st.tenant_id
    ids: dict = {"startedAt": started, "tenant": tenant, "segments": [], "imports": []}

    def save() -> None:
        with open(a.out, "w") as fh:
            json.dump(ids, fh)

    # 0. Geçersiz istekler (yazmadan önce).
    s, meta = http("GET", P + "/meta")
    check("meta 200", s == 200, str(s))
    s, _ = http("POST", P + "/segments", {})
    check("boş gövdeyle segment 400", s == 400, str(s))
    s, _ = http("POST", P + "/merge-candidates/yok/decision", {})
    check("geçersiz birleştirme kararı 400", s == 400, str(s))
    s, _ = http("POST", P + "/imports?filename=bos.csv", raw_body=b"", ctype="application/octet-stream")
    check("boş dosya 400", s == 400, str(s))
    s, _ = http("GET", P + "/item/OKYOKBOYLE")
    check("olmayan okur 404", s == 404, str(s))
    s, _ = http("GET", P + "/segments/yok-boyle")
    check("olmayan segment 404", s == 404, str(s))
    s, _ = http("GET", P + "/subject")
    check("KVKK araması boş sorguyla 400", s == 400, str(s))

    # 1. Kaynak okuması (tam tur) ve bitişi.
    t0 = time.time()
    s, job = http("POST", P + "/refresh", {})
    check("okuma başlatıldı (202)", s == 202 and (job.get("started") or job.get("running")), f"{s} {str(job)[:160]}")
    while True:
        time.sleep(10)
        s, job = http("GET", P + "/status")
        if s != 200 or not job.get("running") or time.time() - t0 > 3600:
            break
    check("okuma hatasız bitti", s == 200 and not job.get("running") and not job.get("error"),
          f"{int(time.time() - t0)} sn; {job.get('error') or job.get('result')}")
    s, ov = http("GET", P + "/overview", timeout=1800)
    check("özet 200", s == 200, str(s))
    if s != 200:
        save()
        return finish(a.out)
    stats = ov["run"]["stats"]
    src_rows = {x["source"]: x["rows"] for x in ov["sources"]}

    # R1 etkin kişi, R3 açık aday.
    n1 = crm(f"SELECT COUNT(*) AS n FROM {SCHEMA}.ContactBase WHERE StateCode = 0")[0]["n"]
    check("R1 etkin kişi = CRM kişi okuması", src_rows.get("crm_contact") == n1, f"portal {src_rows.get('crm_contact')} · SQL {n1}")
    n3 = crm(f"SELECT COUNT(*) AS n FROM {SCHEMA}.LeadBase WHERE StateCode = 0")[0]["n"]
    check("R3 açık aday = CRM aday okuması (READERS_LEAD_STATES=0)", src_rows.get("crm_lead") == n3, f"portal {src_rows.get('crm_lead')} · SQL {n3}")

    # R2 form tipi kırılımı.
    ref2 = {("bos" if r["kod"] is None else str(int(r["kod"]))): r["n"]
            for r in crm(f"SELECT new_geliskanali AS kod, COUNT(*) AS n FROM {SCHEMA}.ContactBase WHERE StateCode = 0 GROUP BY new_geliskanali")}
    check("R2 form tipi kırılımı", ref2 == stats.get("formTypes"), f"{len(ref2)} değer; fark {set(ref2.items()) ^ set((stats.get('formTypes') or {}).items())}")

    # R4 tekil e-posta: SQL (harmanlama duyarsız) ve aynı ham satırların Python normalizasyonu.
    n4 = crm(f"""SELECT COUNT(DISTINCT LOWER(LTRIM(RTRIM(e)))) AS n FROM (
        SELECT EMailAddress1 e FROM {SCHEMA}.ContactBase WHERE StateCode = 0
        UNION ALL SELECT EMailAddress1 FROM {SCHEMA}.LeadBase WHERE StateCode = 0) x WHERE e LIKE '%@%'""")[0]["n"]
    raw = crm(f"SELECT EMailAddress1 AS e FROM {SCHEMA}.ContactBase WHERE StateCode = 0 "
              f"UNION ALL SELECT EMailAddress1 FROM {SCHEMA}.LeadBase WHERE StateCode = 0")
    py = len({x for x in (R.norm_email(r["e"]) for r in raw) if x})
    del raw
    portal4 = stats.get("distinctEmailsContactLead")
    check("R4a tekil e-posta = aynı satırların normalizasyonu (birebir)", portal4 == py, f"portal {portal4} · referans {py}")
    check("R4b tekil e-posta = SQL LOWER/LTRIM/RTRIM (harmanlama farkı ≤ %0,1)", abs((portal4 or 0) - n4) <= max(1, n4 // 1000),
          f"portal {portal4} · SQL {n4} · fark {(portal4 or 0) - n4} (Türkçe İ/I ve sekme/satır sonu boşlukları)")

    # R5 İYS son durum (alan × durum).
    # 2026-09-28: müşterisi boş satır sayılmaz (eski sorgu NULL müşterileri tek bölmede alan başına +1 sayıyordu), eş
    # zamanlı çelişen kayıtta ret kazanır, alanı boş satır kanalla gruplanır — portalla aynı kural (referans.sql R5).
    approve = int(R.settings()["iysApproveValue"])
    ref5: dict[str, Counter] = {}
    for r in crm(f"""WITH son AS (SELECT obs_customerid, obs_iysintegrationfieldid, CAST(obs_channel AS int) AS kanal,
            obs_permissionstatus,
            ROW_NUMBER() OVER (PARTITION BY obs_customerid, obs_iysintegrationfieldid,
                                            CASE WHEN obs_iysintegrationfieldid IS NULL THEN CAST(obs_channel AS int) END
                               ORDER BY obs_permissiondate DESC, CreatedOn DESC,
                                        CASE WHEN CAST(obs_permissionstatus AS int) = {approve} THEN 0 ELSE 1 END DESC) rn
            FROM {SCHEMA}.obs_iyslogBase WHERE ISNULL(obs_iserror, 0) = 0 AND obs_customerid IS NOT NULL)
            SELECT obs_iysintegrationfieldid AS alan, kanal, obs_permissionstatus AS durum, COUNT(*) AS n FROM son WHERE rn = 1
            GROUP BY obs_iysintegrationfieldid, kanal, obs_permissionstatus"""):
        k = str(r["alan"]).strip("{}").upper() if r["alan"] else f"kanal:{r['kanal']}"
        ref5.setdefault(k, Counter())["onay" if r["durum"] == approve else "ret"] += r["n"]
    print(f"   İYS: müşterisi boş satır (sayılmaz) portal {stats.get('iysNoCustomer')}; ayrıntı: scripts/acceptance/H2/iys-fark.sql")
    got5 = {k: Counter(v) for k, v in (stats.get("iysLatest") or {}).items()}
    diff5 = {k: {"sql": dict(ref5.get(k, {})), "portal": dict(got5.get(k, {}))} for k in set(ref5) | set(got5)
             if dict(ref5.get(k, {})) != dict(got5.get(k, {}))}
    check("R5 İYS son durum (alan × onay/ret)", not diff5,
          f"{len(ref5)} alan; fark: " + json.dumps(diff5, ensure_ascii=False)[:1200])
    chans = stats.get("iysChannels") or {}
    check("R5b her İYS alanının kanalı belirlendi", all(k in chans for k in ref5 if not k.startswith("kanal:")),
          f"eşlenen {len(chans)} / {len(ref5)}; eşlenemeyen İYS kaydı {stats.get('iysUnmapped')}")

    # R6 e-posta engeli olan kişi e-posta listesine giremez (portalın okur/izin tablosu).
    blocked = {str(r["id"]).strip("{}").upper() for r in crm(
        f"SELECT ContactId AS id FROM {SCHEMA}.ContactBase WHERE StateCode = 0 AND (DoNotEMail = 1 OR DoNotBulkEMail = 1)")}
    with engine.connect() as c:
        rmap = {r.source_id: r.reader_id for r in c.execute(sa.select(R.LINKS.c.source_id, R.LINKS.c.reader_id).where(
            sa.and_(R.LINKS.c.tenant_id == tenant, R.LINKS.c.source == "crm_contact")))}
    profs = {p["id"]: p for p in R.profiles(engine, tenant)}
    cfg = R.settings()
    leak = [cid for cid in blocked if cid in rmap and R.exportable(profs.get(rmap[cid], {"consent": {"email": "ret"}, "minor": False, "sources": {}}), "email", cfg)[0]]
    check("R6 e-posta engelli kişi e-posta listesine giremez", not leak, f"engelli {len(blocked)}, okur kartına bağlı {sum(1 for x in blocked if x in rmap)}, sızan {len(leak)}")

    # R7 etkinlik katılımı, R8 kampanyalar, R9 okur sayılmayan, R10 İYS satırı.
    n7 = crm(f"SELECT COUNT(DISTINCT contactid) AS n FROM {SCHEMA}.new_new_etkinlik_contactBase")[0]["n"]
    check("R7 etkinliğe katılan kişi", stats.get("eventContacts") == n7, f"portal {stats.get('eventContacts')} · SQL {n7}")
    ref8 = sorted((str(r["ad"]), float(r["gonderim"] or 0), float(r["okunma"] or 0), float(r["tiklama"] or 0)) for r in crm(
        f"SELECT Name AS ad, obs_totalcount AS gonderim, obs_readcount AS okunma, obs_clickcount AS tiklama FROM {SCHEMA}.CampaignBase"))
    got8 = sorted((str(x["ad"]), float(x["gonderim"] or 0), float(x["okunma"] or 0), float(x["tiklama"] or 0)) for x in stats.get("campaigns") or [])
    check("R8 kampanya geçmişi", ref8 == got8, f"{len(ref8)} kampanya")
    # SQL Server toplama içinde alt sorgu kabul etmez (hata 130): katkı sağlayanlar ayrı kümeden LEFT JOIN ile.
    r9 = crm(f"""SELECT SUM(CASE WHEN c.ParentCustomerId IS NOT NULL THEN 1 ELSE 0 END) AS kurum,
        SUM(CASE WHEN c.ParentCustomerId IS NULL AND k.cid IS NOT NULL THEN 1 ELSE 0 END) AS katki
        FROM {SCHEMA}.ContactBase c
        LEFT JOIN (SELECT DISTINCT new_Katilimsaglayan AS cid FROM {SCHEMA}.new_eserkatilimBase WHERE statecode = 0) k
          ON k.cid = c.ContactId
        WHERE c.StateCode = 0""")[0]
    ex = stats.get("excluded") or {}
    check("R9 okur sayılmayan kişi kartı (kurum / katkı)", (ex.get("kurum"), ex.get("katki")) == (r9["kurum"], r9["katki"]),
          f"portal {ex} · SQL {dict(r9)}")
    n10 = crm(f"SELECT COUNT(*) AS n FROM {SCHEMA}.obs_iyslogBase WHERE ISNULL(obs_iserror, 0) = 0")[0]["n"]
    check("R10 hatasız İYS satırı", stats.get("iysRows") == n10, f"portal {stats.get('iysRows')} · SQL {n10}")

    # Tutarlılık: özet ↔ portal tablosu.
    with engine.connect() as c:
        active = c.execute(sa.select(sa.func.count()).select_from(R.READERS).where(sa.and_(
            R.READERS.c.tenant_id == tenant, R.READERS.c.status == "aktif"))).scalar()
        links = c.execute(sa.select(sa.func.count()).select_from(R.LINKS).where(R.LINKS.c.tenant_id == tenant)).scalar()
        top_city = c.execute(sa.select(R.READERS.c.city, sa.func.count().label("n")).where(sa.and_(
            R.READERS.c.tenant_id == tenant, R.READERS.c.status == "aktif", R.READERS.c.city.isnot(None)))
            .group_by(R.READERS.c.city).order_by(sa.text("n DESC")).limit(1)).first()
    check("tekil okur = etkin okur satırı", ov["readers"] == active, f"özet {ov['readers']} · tablo {active}")
    check("kaynak kaydı = bağ satırı", ov["records"] == links, f"özet {ov['records']} · tablo {links}")
    check("kanal başına izin toplamı = okur", all(sum(ov["consent"][ch].values()) == ov["readers"] for ch in ov["consent"]))
    check("ulaşılabilir ≤ izinli", all(ov["reach"][ch] <= ov["consent"][ch]["izinli"] for ch in ("email", "sms", "call")))
    for path in ("/sources", "/mine", "/fields", "/segments", "/exports", "/imports", "/merge-candidates", "/contract/segments"):
        s, _ = http("GET", P + path, timeout=900)
        check(f"GET {path} 200", s == 200, str(s))

    # Yazma 1: taslak segment → önizleme sayısı = tabloya doğrudan SQL → arşiv. Kimlik cleanup için yazılır.
    if top_city:
        body = {"name": "H2 kabul (silinecek)", "definition": {"match": "all", "rules": [{"field": "il", "op": "in", "value": [top_city.city]}]}}
        s, seg = http("POST", P + "/segments", body)
        check("taslak segment 201", s == 201, str(s))
        if s == 201:
            ids["segments"].append(seg["id"])
            save()
            s, cnt = http("POST", P + f"/segments/{seg['id']}/preview", {})
            check("segment büyüklüğü = il sayısı (doğrudan SQL)", s == 200 and cnt["total"] == top_city.n, f"{top_city.city}: {cnt.get('total') if s == 200 else s} · SQL {top_city.n}")
            s, ex_ = http("POST", P + f"/segments/{seg['id']}/export", {"channel": "email", "purpose": "kabul denemesi"})
            check("taslak segment dışa aktarılamaz (409/403)", s in (409, 403), str(s))
            s, _ = http("POST", P + f"/segments/{seg['id']}/approve", {})
            check("yazan kendi segmentini onaylayamaz (409/403)", s in (409, 403), str(s))
            s, _ = http("POST", P + f"/segments/{seg['id']}/archive", {})
            check("segment arşive kaldırıldı", s == 200, str(s))

    # Yazma 2: yapay adresli etkinlik dosyası; eşleşme olmamalı; satırlar hemen silinir.
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    csv = (f"Ad Soyad;E-posta;Telefon\nKabul Bir;h2-kabul-{stamp}@ornek.invalid;\nKabul İki;;\n"
           f"Kabul Üç;H2-KABUL-{stamp}@ORNEK.INVALID;\n").encode("utf-8")
    s, imp = http("POST", P + "/imports?filename=h2-kabul.csv", raw_body=csv, ctype="application/octet-stream")
    check("etkinlik dosyası 201", s == 201, str(s))
    if s == 201:
        ids["imports"].append(imp["id"])
        save()
        s, done = http("POST", P + f"/imports/{imp['id']}/confirm", {"eventName": "H2 kabul (silinecek)", "eventDate": datetime.now().date().isoformat()})
        ok = s == 200 and (done["matched"], done["new"], done["rejected"], done["duplicates"]) == (0, 1, 1, 1)
        check("eşleştirme: 0 eşleşti, 1 yeni, 1 geçersiz, 1 tekrar", ok, str({k: done.get(k) for k in ("matched", "new", "rejected", "duplicates")}) if s == 200 else str(s))
        s, _ = http("DELETE", P + f"/imports/{imp['id']}")
        check("yükleme satırları silindi", s == 200, str(s))
    save()
    return finish(a.out)


def finish(out_path: str) -> int:
    ok = sum(1 for r in results if r[1])
    print(f"== SONUÇ: {ok}/{len(results)} geçti; kimlikler {out_path} (cleanup.py ile silin)")
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
