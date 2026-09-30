#!/usr/bin/env python3
"""Bilgi İşlem e-postaları — test sunucusunda (ve VM'de) gerçek meta DB ve CRM ile kabul.

Beş bildirim canlı tablolardan uygulamanın kendi kurucu işlevleriyle kurulur (gönderilmez) ve iki şey denetlenir:
1. Şablon: konu durumla başlar, «Ne oldu / Etkisi / Ne yapmalı», portal bağlantısı ve alt not var, teknoloji adı
   yok, ileti `multipart/alternative`.
2. Rakamlar: bildirimdeki her sayı bağımsız SQL referansıyla karşılaştırılır (R1–R7). Uygulamanın SQL'i yeniden
   koşturulmaz.

    set -a; . /etc/nanobase/semantic-bridge.env; set +a
    cd <kaynak>/backend && python3 ../scripts/acceptance/bt-eposta/kabul.py --out /tmp/claude-<oturum>/bt-eposta.json
    # Kurulan köprünün açılış kaydı (R7) için birim adı:
    … kabul.py --unit nanobase-semantic-bridge.service
    # İsteğe bağlı ve yalnız açıkça: kurulan bildirimleri bir iç adrese gerçekten gönder (kullanıcıya göstermek için)
    … kabul.py --gonder bilgiislem@timas.com.tr --html-dir /tmp/claude-<oturum>/bt-eposta

Her kontrol: OK / FARK / DOĞRULANAMADI. Betik veritabanına yazmaz (temizlik.py yalnız çıktı klasörünü siler).
"""
from __future__ import annotations

import argparse
import email
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))

import sqlalchemy as sa  # noqa: E402

from semantic_bridge import admin as admin_mod  # noqa: E402
from semantic_bridge import crm_unassigned as CU  # noqa: E402
from semantic_bridge import data_security as D  # noqa: E402
from semantic_bridge import ic_bildirim as IB  # noqa: E402
from semantic_bridge import it_ops as I  # noqa: E402
from semantic_bridge import it_ops_sources as S  # noqa: E402
from semantic_bridge import mailbox as M  # noqa: E402
from semantic_layer.profiler.connectors import connector_from_file  # noqa: E402
from semantic_layer.store.catalog_store import open_store  # noqa: E402

RESULTS: list[dict] = []
BUILT: dict[str, tuple[IB.Notice, list]] = {}


def record(name: str, status: str, **detail) -> None:
    RESULTS.append({"kontrol": name, "durum": status, **detail})
    print(f"[{status:>13}] {name}  {json.dumps(detail, ensure_ascii=False, default=str)[:400]}")


def direct(path: str, sql: str) -> list[dict]:
    conn = connector_from_file(path)
    try:
        _cols, rows, truncated = conn.execute(sql, 10_000_000)
        if truncated:
            raise RuntimeError("referans sorgusu kesildi")
        return rows
    finally:
        conn.close()


def template(name: str, n: IB.Notice, tag: str, path: str, att: list | None = None) -> None:
    BUILT[name] = (n, att or [])
    html, text = IB.render_html(n), IB.render_text(n)
    msg = email.message_from_bytes(IB.message(n, "zeki@timas.com.tr", ["bilgiislem@timas.com.tr"], att).as_bytes())
    kinds = [p.get_content_type() for p in msg.walk()]
    problems = []
    if not n.subject.startswith(f"[{tag}] "):
        problems.append("konu durumla başlamıyor")
    for t in ("Ne oldu", "Etkisi", "Ne yapmalı"):
        if f">{t}</p>" not in html:
            problems.append(f"bölüm yok: {t}")
    if IB.FOOTER not in text:
        problems.append("alt not yok")
    if admin_mod.conf("ALERT_LINK") and (not n.link or path not in n.link):
        problems.append("portal bağlantısı yok")
    if "multipart/alternative" not in kinds or "text/html" not in kinds or "text/plain" not in kinds:
        problems.append(f"ileti yapısı {kinds}")
    words = IB.tech_words(html + text)
    if words:
        problems.append(f"teknoloji adı: {words}")
    record(f"T {name}", "OK" if not problems else "FARK", konu=n.subject, sorun=problems)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="bt-eposta-kabul.json")
    ap.add_argument("--unit", default="nanobase-semantic-bridge.service")
    ap.add_argument("--gonder", default="", help="kurulan bildirimleri bu İÇ adrese gerçekten gönder (isteğe bağlı)")
    ap.add_argument("--html-dir", default="", help="kurulan bildirimlerin HTML/metin kopyası buraya yazılır")
    args = ap.parse_args()

    engine = open_store(os.environ["SEMANTIC_STORE_DSN"], create=False).engine
    I.ensure(engine)
    admin_mod.ensure(engine)
    tenant = os.environ.get("SEMANTIC_TENANT_ID", "default")
    ds = os.environ.get("SEMANTIC_DATASOURCE_ID", "logo")
    crm_file = os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json")
    link = admin_mod.conf("ALERT_LINK") or ""
    now = datetime.now(timezone.utc)
    st = I.settings(admin_mod.conf)

    # R1/R2 — haftalık özet: bağlantı başına kopma sayısı ve dakikası, şu an açık olay sayısı
    try:
        n = I.weekly_notice(engine, tenant, now, I.failing_jobs(engine, tenant), link)
        template("2-haftalik", n, "Haftalık", "/sistem-durumu")
        since = now - timedelta(days=7)
        app = I.downtime(engine, tenant, since, now)
        with engine.connect() as c:
            ref = {r["ring"]: r for r in c.execute(sa.text(
                "SELECT ring, count(*) AS n, COALESCE(sum(floor(extract(epoch FROM (LEAST(COALESCE(closed_at, :u), :u) "
                "- GREATEST(opened_at, :s))) / 60)), 0) AS dk FROM semantic_itops_incidents WHERE tenant_id = :t "
                "AND kind = 'kopma' AND NOT false_alarm AND opened_at < :u AND (closed_at IS NULL OR closed_at > :s) "
                "GROUP BY ring"), {"t": tenant, "s": since, "u": now}).mappings().all()}
            open_n = c.execute(sa.text("SELECT count(*) FROM semantic_itops_incidents WHERE tenant_id = :t "
                                       "AND closed_at IS NULL"), {"t": tenant}).scalar()
        diff = {rid: {"portal": v, "referans": dict(ref.get(rid) or {})} for rid, v in app.items()
                if v["count"] != int((ref.get(rid) or {}).get("n") or 0)
                or v["minutes"] != int((ref.get(rid) or {}).get("dk") or 0)}
        record("R1 haftalık kesinti (bağlantı başına sayı ve dakika)", "OK" if not diff else "FARK", fark=diff,
               toplam_dk=sum(v["minutes"] for v in app.values()))
        shown = next((len(t.rows) for t in n.tables if t.title == "Şu an açık"), 0)
        record("R2 haftalık «şu an açık»", "OK" if shown == int(open_n or 0) else "FARK", portal=shown, referans=open_n)
    except Exception as e:  # noqa: BLE001
        record("R1/R2 haftalık", "DOĞRULANAMADI", hata=str(e)[:300])

    # R3 — en son kopma olayının e-postadaki deneme sayısı; şablon: kopma ve (kapandıysa) düzelme
    try:
        with engine.connect() as c:
            last = c.execute(sa.select(I.INCIDENTS).where(I.INCIDENTS.c.tenant_id == tenant, I.INCIDENTS.c.kind == "kopma")
                             .order_by(I.INCIDENTS.c.opened_at.desc()).limit(1)).mappings().first()
        if not last:
            record("R3 kopma deneme sayısı", "DOĞRULANAMADI", neden="kopma olayı yok (gürültü kuralıyla beklenir)")
        else:
            until = last["closed_at"] or now
            d = I.down_notice(engine, tenant, [last], until, link)
            template("1a-kesinti", d, "Kesinti", "/sistem-durumu")
            if last["closed_at"]:
                template("1b-duzeldi", I.fixed_notice([last], now, link), "Düzeldi", "/sistem-durumu")
            with engine.connect() as c:
                ref = c.execute(sa.text("SELECT count(*) FROM semantic_itops_checks WHERE tenant_id = :t AND ring = :r "
                                        "AND ok = false AND at >= :a"), {"t": tenant, "r": last["ring"],
                                                                         "a": last["opened_at"]}).scalar()
            shown = I._fail_count(engine, tenant, last["ring"], last["opened_at"])
            record("R3 kopma deneme sayısı", "OK" if f"{ref} kez art arda" in IB.render_text(d) and shown == ref else "FARK",
                   olay=last["id"], halka=last["ring"], portal=shown, referans=ref,
                   not_="kapanmış olayda sayı kapanıştan sonraki denemeleri de sayar; ikisi aynı tanımla")
    except Exception as e:  # noqa: BLE001
        record("R3 kopma deneme sayısı", "DOĞRULANAMADI", hata=str(e)[:300])

    # R4/R5 — güvenlik günlük özeti: kişi başına 403 ve yetki dışı soru
    try:
        D.ensure(engine)
        counts = D.digest_counts(engine, engine, tenant, ds, now)
        since = now - timedelta(hours=24)
        with engine.connect() as c:
            ref_f = {r[0]: int(r[1]) for r in c.execute(sa.text(
                "SELECT username, count(*) FROM semantic_security_access WHERE kind = 'forbidden' AND at >= :s "
                "GROUP BY username"), {"s": since}).all()}
            ref_q = {(r[0] or "?"): int(r[1]) for r in c.execute(sa.text(
                "SELECT lower(username), count(*) FROM sl_query_log WHERE tenant_id = :t AND datasource_id = :ds "
                "AND answer_type = 'NOT_PERMITTED' AND created_at >= :s GROUP BY lower(username)"),
                {"t": tenant, "ds": ds, "s": since}).all()}
        app_f = {u: v["forbidden"] for u, v in counts.items() if v["forbidden"]}
        app_q = {u: v["not_permitted"] for u, v in counts.items() if v["not_permitted"]}
        record("R4 güvenlik özeti: sayfa reddi", "OK" if app_f == ref_f else "FARK", portal=app_f, referans=ref_f)
        record("R5 güvenlik özeti: yetki dışı soru", "OK" if app_q == ref_q else "FARK", portal=app_q, referans=ref_q)
        dn = D.digest_notice_from(counts, now, IB.portal_link(link, "veri-guvenligi"))
        if dn:
            template("3b-guvenlik-gunluk", dn, "Günlük", "/veri-guvenligi")
        with engine.connect() as c:
            alerts = [dict(r) for r in c.execute(sa.select(D.ALERTS).order_by(D.ALERTS.c.id.desc()).limit(3)).mappings().all()]
        if alerts:
            template("3a-guvenlik-uyarisi", D.alert_notice(alerts, IB.portal_link(link, "veri-guvenligi"), now),
                     "Güvenlik", "/veri-guvenligi")
    except Exception as e:  # noqa: BLE001
        record("R4/R5 güvenlik özeti", "DOĞRULANAMADI", hata=str(e)[:300])

    # R6 — departmansız CRM kullanıcı sayısı (CRM'den bağımsız sorgu)
    try:
        prefix = S.crm_prefix(admin_mod.conf("CRM_SCHEMA", "Timas_MSCRM.dbo"))

        class Dir:
            def _crm_prefix(self):
                return prefix

            def _crm_rows(self, sql):
                return direct(crm_file, sql)

            def list_people(self):
                return []

        rows = CU.build(Dir())
        ref = direct(crm_file, (
            f"SELECT COUNT(*) AS n FROM {prefix}SystemUserBase WHERE IsDisabled = 0 AND AccessMode IN (0, 1) "
            f"AND ISNULL(DomainName, '') <> '' AND BusinessUnitId IN "
            f"(SELECT BusinessUnitId FROM {prefix}BusinessUnitBase WHERE ParentBusinessUnitId IS NULL)"))[0]["n"]
        n = CU.notice(rows, datetime.now(), link)
        att = [("liste.xlsx", CU.xlsx(rows, datetime.now(), minimal=True), CU.XLSX_MIME)]
        template("5-crm-departmansiz", n, "Bilgi", "/yonetim", att)
        record("R6 departmansız CRM kullanıcısı", "OK" if f"olmayan {len(rows)} kullanıcı" in n.subject and len(rows) == int(ref)
               else "FARK", portal=len(rows), referans=ref)
    except Exception as e:  # noqa: BLE001
        record("R6 departmansız CRM kullanıcısı", "DOĞRULANAMADI", hata=str(e)[:300])

    # Kurumsal e-posta kutusu: son başarılı okuma zamanından (kutu bağlıysa) örnek kurulur
    try:
        last_ok = M.meta_get(engine, tenant, "last_ok_at")
        since = M._aware(datetime.fromisoformat(last_ok)) if last_ok else now - timedelta(minutes=45)
        addr = admin_mod.conf("MAIL_ADDRESS", "") or ""
        template("4a-kesinti-eposta", M.connection_down_notice(addr, since, now, "", link), "Kesinti", "/kurumsal-eposta")
        template("4b-duzeldi-eposta", M.connection_fixed_notice(addr, since, now, now, link), "Düzeldi", "/kurumsal-eposta")
    except Exception as e:  # noqa: BLE001
        record("T kurumsal e-posta", "DOĞRULANAMADI", hata=str(e)[:300])

    # R7 — köprünün açılış kaydı: systemd'nin «etkin oldu» anı ile ±2 dk içinde bir kayıt olmalı (test sunucusu)
    try:
        out = subprocess.run(["systemctl", "show", args.unit, "-p", "ActiveEnterTimestamp", "--value"],
                             capture_output=True, text=True, timeout=10).stdout.strip()
        started = S._stamp(out) if out else None
        boots = I.boots(engine, tenant)
        if started is None:
            record("R7 köprü açılış kaydı", "DOĞRULANAMADI", neden=f"{args.unit} zamanı okunamadı (VM'de kapsayıcı)",
                   son_kayit=boots[-1] if boots else None)
        else:
            near = [b for b in boots if abs((b - started).total_seconds()) <= 120]
            record("R7 köprü açılış kaydı", "OK" if near else "FARK", servis=started, kayit=near or boots[-3:],
                   not_="kayıt ilk denetim turunda yazılır; köprü açıldıktan sonra en az bir tur koşmuş olmalı",
                   bekleme_dk=st["restartGraceMin"], kesinti_esigi_dk=st["outageMin"])
    except Exception as e:  # noqa: BLE001
        record("R7 köprü açılış kaydı", "DOĞRULANAMADI", hata=str(e)[:300])

    if args.html_dir:
        d = Path(args.html_dir)
        d.mkdir(parents=True, exist_ok=True)
        for name, (nt, _att) in BUILT.items():
            (d / f"{name}.html").write_text(IB.render_html(nt), encoding="utf-8")
            (d / f"{name}.txt").write_text(IB.render_text(nt), encoding="utf-8")
    if args.gonder:
        ok, bad = I.internal_recipients(args.gonder, admin_mod.conf("ITOPS_INTERNAL_DOMAINS", "timas.com.tr") or "timas.com.tr")
        if bad or not ok:
            record("G gönderim", "FARK", neden=f"yalnız iç adrese gönderilir: {bad or args.gonder}")
        else:
            for name, (nt, att) in BUILT.items():
                record(f"G gönderim {name}", "OK" if IB.send(nt, ok, att) == "sent" else "FARK", alici=ok)

    Path(args.out).write_text(json.dumps(RESULTS, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    n = {s: sum(1 for r in RESULTS if r["durum"] == s) for s in ("OK", "FARK", "DOĞRULANAMADI")}
    print(json.dumps(n, ensure_ascii=False))
    return 0 if not n["FARK"] else 1


if __name__ == "__main__":
    sys.exit(main())
