#!/usr/bin/env python3
"""H4 Kurumsal e-posta — test sunucusunda gerçek kutu (Gmail, yalnız okuma), gerçek CRM ve köprü tablolarıyla kabul.

Koşturma (köprünün sanal ortamında, köprünün env dosyasıyla; önce `run-due` bir kez ELLE koşturulmuş olmalı — bellek:
«zamanlı işi önce elle koştur»):

    set -a; . /etc/nanobase/semantic-bridge.env; set +a
    curl -fsS -X POST -H "X-Semantic-Caller: $SEMANTIC_CALLER_TOKEN" http://127.0.0.1:8795/api/v1/mailbox/run-due
    cd <kaynak>/backend && python3 ../scripts/acceptance/H4/kabul.py --out /tmp/claude-<oturum>/h4-kabul.json
    # API da denenecekse: timasai'nin 15 dk'lık oturum çerezi (bellek: test-login-as-timasai)
    BRIDGE_URL=http://127.0.0.1:8795 TIMAS_COOKIE='timas_session=…' python3 ../scripts/acceptance/H4/kabul.py --api
    # Yazma (kural taslağı aç-sil, bir etiket): kimlikler --ids dosyasına yazılır, temizlik.py siler
    ... kabul.py --api --yazma --ids /tmp/claude-<oturum>/h4-ids.json

Her kontrol: OK / FARK / DOĞRULANAMADI / BİLGİ. Portal tarafı köprünün kendi tablolarından ya da API'den; referans kutunun
kendi API'si (Gmail) ve CRM'de bağımsız SQL'dir (referans.sql). Uygulamanın SQL'i yeniden koşturulmaz. Kutuya ve CRM'e
hiçbir şey yazılmaz; hiçbir ileti gönderilmez.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))

import sqlalchemy as sa  # noqa: E402

from semantic_bridge import admin as admin_mod  # noqa: E402
from semantic_bridge import budget_sources as bsrc  # noqa: E402
from semantic_bridge import corporate_sales_sources as csrc  # noqa: E402
from semantic_bridge import mailbox as M  # noqa: E402
from semantic_bridge import mailbox_sources as S  # noqa: E402
from semantic_layer.store.catalog_store import open_store  # noqa: E402

RESULTS: list[dict] = []


def record(name: str, status: str, **detail) -> None:
    RESULTS.append({"kontrol": name, "durum": status, **detail})
    print(f"[{status:>13}] {name}  {json.dumps(detail, ensure_ascii=False, default=str)[:400]}")


def q(s: str) -> str:
    return s.replace("'", "''")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="h4-kabul.json")
    ap.add_argument("--api", action="store_true")
    ap.add_argument("--yazma", action="store_true")
    ap.add_argument("--ids", default="h4-ids.json")
    ap.add_argument("--ornek", type=int, default=30, help="gönderen tanıma örneği (en az 5)")
    args = ap.parse_args()

    engine = open_store(os.environ["SEMANTIC_STORE_DSN"], create=False).engine
    M.ensure(engine)
    admin_mod.ensure(engine)
    tenant = os.environ.get("SEMANTIC_TENANT_ID", "default")
    st = M.settings_from(admin_mod.conf)
    state = S.connection_state(admin_mod.conf)
    record("kutu bağlı mı", "OK" if state["connected"] else "DOĞRULANAMADI", **{k: state.get(k) for k in ("mailbox", "authLabel", "identity", "reason")})
    last = M.meta_get(engine, tenant, "last_run") or {}
    record("son okuma", "OK" if last.get("ok") else "DOĞRULANAMADI", son=last.get("at"), hata=last.get("error"), yeni=last.get("new"))
    src = S.source(admin_mod.conf) if state["connected"] else None

    # H1 — hacim: kutunun son 7 günü (spam dahil, gönderilmiş/taslak hariç) = köprüdeki kayıt
    since = datetime.now(timezone.utc) - timedelta(days=7)
    if src:
        try:
            ids = set(src.list_since(since))
            with engine.connect() as c:
                mine = {r[0] for r in c.execute(sa.select(M.MESSAGES.c.provider_id).where(
                    M.MESSAGES.c.tenant_id == tenant, M.MESSAGES.c.provider == src.kind, M.MESSAGES.c.received_at >= since))}
            eksik, fazla = sorted(ids - mine), sorted(mine - ids)
            record("H1 son 7 gün ileti sayısı (kutu = portal)", "OK" if not eksik and not fazla else "FARK", kutu=len(ids),
                   portal=len(mine), portaldaEksik=eksik[:20], kutudaYok=fazla[:20],
                   not_="run-due'dan sonra gelen ileti «eksik» görünür; bir tur sonra yeniden koşturun")
        except S.SourceError as e:
            record("H1 hacim", "DOĞRULANAMADI", hata=str(e))
    else:
        record("H1 hacim", "DOĞRULANAMADI", neden="kutu bağlı değil")

    # H2 — gönderen tanıma: rastgele n ileti, adres kutudan anlık; CRM'de bağımsız sorgu
    crm_file = os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json")
    schema = admin_mod.conf("CRM_SCHEMA", "Timas_MSCRM.dbo")
    try:
        crm = bsrc.runner(crm_file)
        p = csrc.prefix(schema)
    except Exception as e:  # noqa: BLE001
        crm, p = None, ""
        record("H2 CRM bağlantısı", "DOĞRULANAMADI", hata=str(e))
    if src and crm:
        with engine.connect() as c:
            rows = c.execute(sa.select(M.MESSAGES.c.id, M.MESSAGES.c.provider_id, M.MESSAGES.c.crm_json)
                             .where(M.MESSAGES.c.tenant_id == tenant, M.MESSAGES.c.provider == src.kind)).all()
        for r in random.sample(rows, min(len(rows), max(5, args.ornek))):
            try:
                addr = src.fetch(r.provider_id).from_addr
            except S.SourceError as e:
                record(f"H2 {r.id}", "DOĞRULANAMADI", hata=str(e))
                continue
            ref = {}
            for kind, table, key in (("kisi", "ContactBase", "ContactId"), ("firma", "AccountBase", "AccountId"), ("aday", "LeadBase", "LeadId")):
                got = crm(f"SELECT TOP 1 CAST({key} AS nvarchar(40)) AS id FROM {p}{table} WHERE StateCode = 0 "
                          f"AND LOWER(LTRIM(RTRIM(EMailAddress1))) = N'{q(addr)}' ORDER BY CAST({key} AS nvarchar(40))")
                if got:
                    ref[kind] = str(got[0]["id"]).strip("{}").lower()
            app = {k: v.get("id") for k, v in (json.loads(r.crm_json) if r.crm_json else {}).items()}
            record(f"H2 gönderen tanıma {r.id}", "OK" if app == ref else "FARK", portal=app, referans=ref)

    # H3 — yönlendirme hedefleri CRM'de etkin kullanıcı
    rules = M.active_rules(engine, tenant, st)
    users = sorted({u for r in rules["routes"] for u in (r["primary"], r["backup"], r["manager"]) if u}
                   | set(st["inboxOwners"]) | set(st["topManagers"]))
    if not users:
        record("H3 yönlendirme hedefleri", "BİLGİ", not_="yürürlükteki tabloda kişi yok (kurulum başlangıcı)")
    elif crm:
        for u in users:
            n = crm(f"SELECT COUNT(*) AS v FROM {p}SystemUserBase WHERE IsDisabled = 0 AND LOWER(DomainName) = LOWER(N'timas\\{q(u)}')")[0]["v"]
            record(f"H3 hedef {u} CRM'de etkin", "OK" if int(n) == 1 else "FARK", sayi=n)

    # H4 — SLA raporu: ilk yanıt ortalaması (takvim saati) doğrudan SQL = rapor
    end = datetime.now(M.TZ).date()
    start = end - timedelta(days=29)
    rep = M.report(engine, tenant, st, start, end)
    a = datetime(start.year, start.month, start.day, tzinfo=M.TZ).astimezone(timezone.utc)
    with engine.connect() as c:
        ref_rows = c.execute(sa.text(
            "SELECT COALESCE(category, '-') AS k, AVG(EXTRACT(EPOCH FROM (first_reply_at - received_at)) / 3600.0) AS h, COUNT(*) AS n "
            "FROM semantic_mail_messages WHERE tenant_id = :t AND historical = false AND received_at >= :a "
            "AND first_reply_at IS NOT NULL GROUP BY 1"), {"t": tenant, "a": a}).all()
    ref_map = {r.k: (float(r.h), int(r.n)) for r in ref_rows}
    for cat in rep["categories"]:
        ref = ref_map.get(cat["category"])
        if ref is None and cat["avgFirstReplyH"] is None:
            continue
        ok = ref is not None and cat["avgFirstReplyH"] is not None and abs(ref[0] - cat["avgFirstReplyH"]) <= 0.06 and ref[1] == cat["replied"]
        record(f"H4 ilk yanıt ortalaması {cat['label']}", "OK" if ok else "FARK", rapor=cat["avgFirstReplyH"], referans=ref)

    # H5 — sınıflandırma doğruluğu (insan etiketi ↔ modelin ilk seçimi)
    acc = M.accuracy(engine, tenant)
    if not acc["n"]:
        record("H5 doğruluk", "DOĞRULANAMADI", neden="etiketlenmiş ileti yok (Etiketleme ekranı)")
    else:
        record("H5 doğruluk ≥ %90", "OK" if acc["rate"] >= 0.90 else "FARK", oran=acc["rate"], n=acc["n"],
               turBazinda=acc["byCategory"], not_="tutmazsa otomatik atama açılmaz")

    # H6 — otomatik yanıt yok: sistem adına «yanıtlandı» olayı sıfır
    with engine.connect() as c:
        n = c.execute(sa.select(sa.func.count()).select_from(M.EVENTS).where(M.EVENTS.c.action == "yanitlandi",
                                                                             M.EVENTS.c.by.in_(("sistem", "zeki")))).scalar()
    record("H6 portal adına yanıt = 0", "OK" if int(n) == 0 else "FARK", sayi=n)

    # H7 — gövde saklanmıyor, tekillik
    with engine.connect() as c:
        cols = {r[0] for r in c.execute(sa.text("SELECT column_name FROM information_schema.columns WHERE table_name = 'semantic_mail_messages'"))}
        long_summary = c.execute(sa.text("SELECT COUNT(*) FROM semantic_mail_messages WHERE LENGTH(summary) > 600")).scalar()
        dup = c.execute(sa.text("SELECT COUNT(*) - COUNT(DISTINCT tenant_id || provider || provider_id) FROM semantic_mail_messages")).scalar()
    record("H7 gövde/adres kolonu yok", "OK" if not ({"body", "text", "from_addr", "html"} & cols) else "FARK", kolonlar=sorted(cols))
    record("H7 özet ≤ 600 karakter", "OK" if int(long_summary) == 0 else "FARK", uzun=long_summary)
    record("H7 aynı ileti iki kez yok", "OK" if int(dup) == 0 else "FARK", fazla=dup)

    # H8 — başvuru aktarımı: aktarılan kaydın yazar giriş sürecinde karşılığı (API ile)
    with engine.connect() as c:
        moved = c.execute(sa.select(M.APPLICATIONS.c.message_id, M.APPLICATIONS.c.intake_ref, M.APPLICATIONS.c.crm_project_id)
                          .where(M.APPLICATIONS.c.status == "aktarildi")).all()
    if not moved:
        record("H8 başvuru aktarımı", "DOĞRULANAMADI", neden="aktarılmış başvuru yok")
    for r in moved:
        if args.api:
            code, _ = http("GET", f"/api/v1/editorial/applications/{r.intake_ref}")
            record(f"H8 aktarılan başvuru {r.intake_ref}", "OK" if code == 200 else "FARK", durum=code)
        if r.crm_project_id and crm:
            n = crm(f"SELECT COUNT(*) AS v FROM {p}new_projeBase WHERE new_projeId = '{q(r.crm_project_id)}'")[0]["v"]
            record(f"H8 CRM proje bağı {r.crm_project_id}", "OK" if int(n) == 1 else "FARK")

    if args.api:
        api_checks(args, engine, tenant)
    return finish(args)


def http(method: str, path: str, body=None):
    url = os.environ.get("BRIDGE_URL", "http://127.0.0.1:8795") + path
    req = urllib.request.Request(url, method=method, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Cookie": os.environ.get("TIMAS_COOKIE", ""), "Content-Type": "application/json",
                                          "X-Semantic-Caller": os.environ.get("SEMANTIC_CALLER_TOKEN", "")})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw[:1] in (b"{", b"[") else raw)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, raw


def api_checks(args, engine, tenant: str) -> None:
    P = "/api/v1/mailbox"
    for path in ("/meta", "/overview", "/badge", "/connection", "/messages?view=mine", "/rules", "/labeling", "/report",
                 "/applications?status=yeni"):
        code, _ = http("GET", P + path)
        record(f"API GET {path}", "OK" if code == 200 else "FARK", durum=code)
    # İK gizliliği: timasai'de `ozellik:eposta.ik` rolle verilmemişse (yönetici olsa da) İK iletisi 403.
    with engine.connect() as c:
        hr = c.execute(sa.select(M.MESSAGES.c.id).where(M.MESSAGES.c.tenant_id == tenant, M.MESSAGES.c.is_hr.is_(True),
                                                        M.MESSAGES.c.historical.is_(False)).limit(1)).scalar()
    code, meta = http("GET", f"{P}/meta")
    has_hr = bool(isinstance(meta, dict) and meta.get("me", {}).get("hr"))
    if hr and not has_hr:
        code, _ = http("GET", f"{P}/messages/{hr}")
        record("H9 İK iletisi yetkisiz 403", "OK" if code == 403 else "FARK", durum=code)
        code, lst = http("GET", f"{P}/messages?view=unassigned")
        leak = [x["id"] for x in (lst.get("items") if isinstance(lst, dict) else []) if x.get("isHr")]
        record("H9 listede İK iletisi yok", "OK" if not leak else "FARK", sizan=leak)
    else:
        record("H9 İK gizliliği", "DOĞRULANAMADI", neden="İK iletisi yok ya da test hesabında İK yetkisi var")
    # Yazma uçları önce boş/geçersiz gövdeyle.
    for path, body in (("/messages/yok/assign", {"assignee": "Ali Veli"}), ("/messages/yok/category", {}), ("/rules/approve", {})):
        code, b = http("POST", P + path, body)
        record(f"API POST {path} geçersiz", "OK" if code in (400, 403, 404, 422) else "FARK", durum=code, mesaj=str(b)[:160])
    code, _ = http("PUT", f"{P}/rules", {"categories": []})
    record("API PUT /rules boş", "OK" if code in (400, 403) else "FARK", durum=code)
    if not args.yazma:
        return
    ids: dict[str, list] = {"labels": [], "draft": []}
    try:
        code, r = http("GET", f"{P}/rules")
        active = r.get("active") if isinstance(r, dict) else None
        if active and not r.get("draft"):
            body = {"note": "KABUL TESTİ (silinecek)", "categories": active["categories"], "routes": active["routes"],
                    "sla": active["sla"], "templates": [{k: t[k] for k in ("category", "name", "body")} for t in active["templates"]]}
            code, d = http("PUT", f"{P}/rules", body)
            record("API kural taslağı aç", "OK" if code == 200 else "FARK", durum=code)
            if code == 200:
                ids["draft"].append(d["version"])
                code, _ = http("POST", f"{P}/rules/approve", {"version": d["version"]})
                record("API taslağı yazan onaylayamaz", "OK" if code == 403 else "FARK", durum=code)
                code, _ = http("DELETE", f"{P}/rules/draft")
                record("API taslağı sil", "OK" if code == 200 else "FARK", durum=code)
                if code == 200:
                    ids["draft"].clear()
        code, lab = http("GET", f"{P}/labeling")
        if code == 200 and lab["items"]:
            mid = lab["items"][0]["id"]
            key = next((c["key"] for c in active["categories"] if c["enabled"]), None) if active else None
            if key:
                code, _ = http("POST", f"{P}/labeling/{mid}", {"category": key})
                record("API etiket yaz", "OK" if code == 200 else "FARK", durum=code)
                ids["labels"].append(mid)
    finally:
        Path(args.ids).write_text(json.dumps(ids))


def finish(args) -> int:
    Path(args.out).write_text(json.dumps({"zaman": datetime.now().isoformat(), "sonuc": RESULTS}, ensure_ascii=False, indent=1, default=str))
    bad = [r for r in RESULTS if r["durum"] in ("FARK", "DOĞRULANAMADI")]
    print(f"\n{len(RESULTS) - len(bad)}/{len(RESULTS)} OK/BİLGİ · FARK {sum(r['durum'] == 'FARK' for r in RESULTS)} · "
          f"DOĞRULANAMADI {sum(r['durum'] == 'DOĞRULANAMADI' for r in RESULTS)} → {args.out}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
