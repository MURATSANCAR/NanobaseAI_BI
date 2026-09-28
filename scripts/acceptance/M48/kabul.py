#!/usr/bin/env python3
"""M48 Sistem durumu — test sunucusunda (ve VM'de) gerçek Logo/CRM/meta DB ile kabul.

Önce tur elle bir kez koşturulur (bellek run-it-before-it-runs-itself), sonra bu betik:

    sudo systemctl start timas-itops.service            # ya da: curl -X POST -H "X-Semantic-Caller: …" :8795/api/v1/it-ops/run-due
    set -a; . /etc/nanobase/semantic-bridge.env; set +a
    cd <kaynak>/backend && python3 ../scripts/acceptance/M48/kabul.py --out /tmp/claude-<oturum>/m48-kabul.json
    # API da denenecekse: timasai'nin 15 dk'lık oturum çerezi (bellek test-login-as-timasai); bitince oturum silinir
    BRIDGE_URL=http://127.0.0.1:8795 TIMAS_COOKIE='timas_session=…' python3 ../scripts/acceptance/M48/kabul.py --api
    # Sürüm eşliği: kurulumda kullanılan main sürümü
    … kabul.py --sha "$(git -C <depo> rev-parse main)"

Her kontrol: OK / FARK / DOĞRULANAMADI. Portal tarafı köprünün kendi tablolarından (ekrana giden değer) ya da API'den
okunur; referans aynı kaynakta bağımsız SQL'dir (referans.sql). Uygulamanın SQL'i yeniden koşturulmaz. Betik yazmaz;
«--dene» verilirse bir «Şimdi dene» çağrısı yapar (değişiklik kaydı yazar → temizlik.py siler).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))

import sqlalchemy as sa  # noqa: E402

from semantic_bridge import admin as admin_mod  # noqa: E402
from semantic_bridge import it_ops as I  # noqa: E402
from semantic_bridge import it_ops_sources as S  # noqa: E402
from semantic_layer.profiler.connectors import connector_from_file  # noqa: E402
from semantic_layer.store.catalog_store import open_store  # noqa: E402

RESULTS: list[dict] = []
BANNED = re.compile(r"systemd|systemctl|docker|nginx|vllm|openvpn|qwen|socat|freetds|pyodbc", re.I)


def record(name: str, status: str, **detail) -> None:
    RESULTS.append({"kontrol": name, "durum": status, **detail})
    print(f"[{status:>13}] {name}  {json.dumps(detail, ensure_ascii=False, default=str)[:400]}")


def direct(path: str, sql: str) -> list[dict]:
    conn = connector_from_file(path)
    try:
        return conn.execute(sql, 1000)[1]
    finally:
        conn.close()


def api(path: str) -> dict:
    base = os.environ["BRIDGE_URL"].rstrip("/")
    req = urllib.request.Request(base + path, headers={"cookie": os.environ["TIMAS_COOKIE"],
                                                       "X-Semantic-Caller": os.environ.get("SEMANTIC_CALLER_TOKEN", "")})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.load(r)


def api_post(path: str, body: dict) -> dict:
    base = os.environ["BRIDGE_URL"].rstrip("/")
    req = urllib.request.Request(base + path, data=json.dumps(body).encode(), method="POST",
                                 headers={"cookie": os.environ["TIMAS_COOKIE"], "Content-Type": "application/json",
                                          "X-Semantic-Caller": os.environ.get("SEMANTIC_CALLER_TOKEN", "")})
    with urllib.request.urlopen(req, timeout=330) as r:
        return json.load(r)


def last_check(engine, tenant: str, ring: str):
    with engine.connect() as c:
        return c.execute(sa.select(I.CHECKS).where(I.CHECKS.c.tenant_id == tenant, I.CHECKS.c.ring == ring)
                         .order_by(I.CHECKS.c.id.desc()).limit(1)).mappings().first()


def job(engine, tenant: str, name: str):
    with engine.connect() as c:
        return c.execute(sa.select(I.JOBS).where(I.JOBS.c.tenant_id == tenant, I.JOBS.c.job == name)).mappings().first()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="m48-kabul.json")
    ap.add_argument("--api", action="store_true")
    ap.add_argument("--dene", action="store_true", help="API'den bir «Şimdi dene» (Logo) çağrısı yap")
    ap.add_argument("--sha", default="", help="kurulan main sürümü (git rev-parse main)")
    ap.add_argument("--vm", action="store_true", help="VM'de koşuluyor: bütün halkalar ölçülmüş olmalı (kabul 7)")
    args = ap.parse_args()

    engine = open_store(os.environ["SEMANTIC_STORE_DSN"], create=False).engine
    I.ensure(engine)
    admin_mod.ensure(engine)
    tenant = os.environ.get("SEMANTIC_TENANT_ID", "default")
    ds = os.environ.get("SEMANTIC_DATASOURCE_ID", "logo")
    logo_file = os.environ["SEMANTIC_CONNECTION_FILE"]
    crm_file = os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json")
    status = api("/api/v1/it-ops/status") if args.api else None
    ring_api = {r["id"]: r for r in (status or {}).get("rings", [])}

    # K1 — Logo veri sonu. Referans: dönem tablosundan güncel firma bağımsız okunur (en yeni bitiş yılı), sonra MAX(DATE_).
    try:
        per = direct(logo_file, "SELECT FIRMNR, BEGDATE, ENDDATE FROM L_CAPIPERIOD WHERE ACTIVE = 1")
        years = {}
        for r in per:
            if str(r["FIRMNR"]).zfill(3) in ("015", "016"):
                continue
            end = r["ENDDATE"] if isinstance(r["ENDDATE"], (date, datetime)) else datetime.fromisoformat(str(r["ENDDATE"])[:19])
            years[end.year] = max(years.get(end.year, 0), int(r["FIRMNR"]))
        firm = f"{years.get(datetime.now().year) or years[max(years)]:03d}"
        ref = direct(logo_file, f"SELECT MAX(DATE_) AS son FROM LG_{firm}_01_INVOICE WHERE CANCELLED = 0 AND DATE_ <= CAST(GETDATE() AS date)")[0]["son"]
        raw = direct(logo_file, f"SELECT MAX(DATE_) AS son FROM LG_{firm}_01_INVOICE WHERE CANCELLED = 0")[0]["son"]
        ref_d = (ref.date() if isinstance(ref, datetime) else ref)
        row = last_check(engine, tenant, "logo")
        app_d = I._aware(row["data_end"]).astimezone(timezone(timedelta(hours=3))).date() if row and row["data_end"] else None
        api_d = ring_api.get("logo", {}).get("dataEnd")
        api_d = datetime.fromisoformat(api_d).astimezone(timezone(timedelta(hours=3))).date() if api_d else None
        ok = app_d == ref_d and (not args.api or api_d == ref_d)
        record("K1 Logo veri sonu", "OK" if ok else "FARK", firma=firm, portal=app_d, api=api_d, referans=ref_d,
               sinirsiz=raw, bellek_2026_09_23="2026-08-17")
    except Exception as e:  # noqa: BLE001
        record("K1 Logo veri sonu", "DOĞRULANAMADI", hata=str(e)[:300])

    # K2 — CRM veri sonu (dakika hassasiyeti; tur ile kabul arasında yeni değişiklik gelmişse referans ileri olabilir)
    try:
        schema = admin_mod.conf("CRM_SCHEMA", "Timas_MSCRM.dbo")
        ref = direct(crm_file, f"SELECT MAX(ModifiedOn) AS son FROM {S.crm_prefix(schema)}new_kitapBase WHERE ModifiedOn <= GETUTCDATE()")[0]["son"]
        ref = ref.replace(tzinfo=timezone.utc) if isinstance(ref, datetime) and ref.tzinfo is None else ref
        row = last_check(engine, tenant, "crm")
        app = I._aware(row["data_end"]) if row and row["data_end"] else None
        diff = abs((ref - app).total_seconds()) / 60 if app and ref else None
        ok = diff is not None and (diff < 1 or (ref > app and row and I._aware(row["at"]) and ref > I._aware(row["at"]) - timedelta(minutes=1)))
        record("K2 CRM veri sonu", "OK" if ok else "FARK", portal=app, referans=ref, fark_dk=diff,
               not_="referans tur zamanından sonraysa yeni değişiklik gelmiştir; turu yeniden koşturup tekrar bakın")
    except Exception as e:  # noqa: BLE001
        record("K2 CRM veri sonu", "DOĞRULANAMADI", hata=str(e)[:300])

    jobs_api = {j["job"]: j for j in api("/api/v1/it-ops/jobs")["items"]} if args.api else {}

    def table_job(label: str, name: str, sql: str) -> None:
        with engine.connect() as c:
            ref_n = c.execute(sa.text(sql), {"t": tenant, "ds": ds}).scalar()
        j = job(engine, tenant, name)
        app_n = j["failed_count"] if j else None
        api_n = jobs_api.get(name, {}).get("failedCount") if args.api else None
        ok = app_n is not None and int(app_n) == int(ref_n or 0) and (not args.api or api_n == app_n)
        record(label, "OK" if ok else ("DOĞRULANAMADI" if j is None else "FARK"), portal=app_n, api=api_n, referans=ref_n,
               tazelendi=j["updated_at"] if j else None)

    # K3/K4/K6 — tablo kaynaklı iş hataları (meta DB). K3'te Yönetim özetindeki reportsFailed da aynı sayı olmalı.
    table_job("K3 hatalı planlı rapor", "tablo:planli-raporlar",
              "SELECT count(*) FROM semantic_reports WHERE tenant_id = :t AND datasource_id = :ds AND last_status = 'failed'")
    table_job("K4 hatalı pano kartı", "tablo:pano-kartlari",
              "SELECT count(*) FROM semantic_board_cards WHERE tenant_id = :t AND datasource_id = :ds AND last_error IS NOT NULL")
    table_job("K6 hatalı uyarı kuralı", "tablo:uyarilar",
              "SELECT count(*) FROM semantic_alert_rules WHERE tenant_id = :t AND datasource_id = :ds AND state = 'error'")

    # K5 — model kuyruğu ortancaları (Kapasite). Aynı pencere: portal hesaplanırken referans da hemen ardından alınır.
    try:
        ctx = S.Ctx(engine=engine, tenant=tenant, conf=admin_mod.conf, logo_file=lambda: logo_file, crm_file=lambda: crm_file)
        cap = api("/api/v1/it-ops/capacity") if args.api else S.capacity(ctx)
        with engine.connect() as c:
            ref = c.execute(sa.text(
                "SELECT module, count(*) AS n, percentile_cont(0.5) WITHIN GROUP (ORDER BY queue_wait_ms) AS w, "
                "percentile_cont(0.5) WITHIN GROUP (ORDER BY llm_ms) AS m FROM sl_llm_job "
                "WHERE created_at > now() - interval '7 days' AND status = 'DONE' GROUP BY module")).mappings().all()
        app = {m["module"]: m for m in cap["modules"]}
        if not ref:
            record("K5 model kuyruğu", "DOĞRULANAMADI", neden="son 7 günde tamamlanan model işi yok")
        for r in ref:
            a = app.get(r["module"])
            close = a is not None and abs(a["jobs"] - r["n"]) <= 3 and all(
                (x is None and y is None) or (x is not None and y is not None and abs(float(x) - float(y)) <= max(50.0, 0.05 * float(y)))
                for x, y in ((a["waitP50Ms"], r["w"]), (a["modelP50Ms"], r["m"])))
            record(f"K5 model kuyruğu {r['module']}", "OK" if close else "FARK", portal=a,
                   referans={"n": r["n"], "bekleme": r["w"], "model": r["m"]}, not_="pencere kayması için ±3 iş, ±%5/50 ms")
    except Exception as e:  # noqa: BLE001
        record("K5 model kuyruğu", "DOĞRULANAMADI", hata=str(e)[:300])

    # K7 — halkaların ölçülmüş olması (VM'de «bilinmiyor» kalmamalı; test sunucusunda VM adresi girilmemişse vm None olabilir)
    st = status or I.status(engine, tenant, I.settings(admin_mod.conf))
    unmeasured = [r["id"] for r in st["rings"] if r["ok"] is None]
    if args.vm:
        allowed = {"vpn"}   # VM şirket ağının içinde: bu halka orada uygulanmaz
    else:
        allowed = set() if admin_mod.conf("ITOPS_VM_URL", "") else {"vm"}
    record("K7 halkalar ölçüldü", "OK" if set(unmeasured) <= allowed else "FARK", olculmeyen=unmeasured,
           beklenen_bos=sorted(allowed), ozet=st["summary"])

    # K8 — sürüm eşliği ve Mac artığı
    rel = I.list_releases(engine, tenant, size=5)
    for env in ("test", "vm"):
        r = rel["latest"].get(env)
        if not r:
            record(f"K8 sürüm kaydı {env}", "DOĞRULANAMADI", neden="bu ortamdan kayıt gelmedi (kurulum betiği bildirmeli)")
            continue
        ok = r["appledoubleCount"] == 0 and (not args.sha or (r["codeSha"] or "").startswith(args.sha[:12]))
        record(f"K8 sürüm kaydı {env}", "OK" if ok else "FARK", kayit=r, beklenen_sha=args.sha or None)

    # K9 — ekran ve uç metinlerinde teknoloji adı yok
    root = Path(__file__).resolve().parents[3] / "src" / "canvas" / "it-ops"
    hits = [f"{p.name}:{i}" for p in root.glob("*.ts*") for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
            if BANNED.search(line) and not line.strip().startswith(("//", "*", "/*")) and "'systemd'" not in line and "systemd:" not in line]
    payload = json.dumps(st, ensure_ascii=False, default=str)
    if args.api:
        payload += json.dumps(jobs_api, ensure_ascii=False) + json.dumps(api("/api/v1/it-ops/incidents?state=all"), ensure_ascii=False)
    api_hits = sorted(set(m.group(0).lower() for m in BANNED.finditer(payload)))
    record("K9 teknoloji adı taraması", "OK" if not hits and not api_hits else "FARK", ekran=hits, uc=api_hits)

    # K10 — «Şimdi dene» (isteğe bağlı): Logo halkası tek başına koşar, sonuç tabloya yazılır
    if args.api and args.dene:
        before = last_check(engine, tenant, "logo")
        out = api_post("/api/v1/it-ops/check-now", {"ring": "logo"})
        after = last_check(engine, tenant, "logo")
        ok = out.get("checked") == 1 and after and (not before or after["id"] > before["id"]) and after["source"] == "manual"
        record("K10 şimdi dene", "OK" if ok else "FARK", sonuc=out.get("failed"), satir=after["id"] if after else None,
               not_="değişiklik kaydı satırı temizlik.py ile silinir")

    return finish(args)


def finish(args) -> int:
    Path(args.out).write_text(json.dumps(RESULTS, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    n = {s: sum(1 for r in RESULTS if r["durum"] == s) for s in ("OK", "FARK", "DOĞRULANAMADI")}
    print(json.dumps(n, ensure_ascii=False))
    return 0 if not n["FARK"] else 1


if __name__ == "__main__":
    sys.exit(main())
