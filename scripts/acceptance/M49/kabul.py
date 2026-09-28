"""M49 Veri güvenliği — gerçek API ↔ doğrudan referans kabulü (test sunucusunda; yan port köprüsü, gerçek meta DB,
gerçek giriş servisi, AD ve CRM; kaynaklar salt okunur).

Her kontrol uçların kullanıcıya verdiği sonucu köprü kodu kullanılmadan yazılmış referansla karşılaştırır
(`referans.sql` R1–R8; AD için ldap3 ile ayrı okuma). Yazma: timasai adına bir hatalı giriş denemesi (+ parola dosyası
verilirse bir doğru giriş), ikinci oturumla bir 403 denemesi ve bir dışa aktarma bildirimi. Zamanı `--out` dosyasına
yazılır; `cleanup.py` bu zamandan sonraki test satırlarını siler.

Ortam: BASE (ör. http://127.0.0.1:8798, aday ağaçla açılmış yan port köprüsü), COOKIE (timasai'nin 15 dk'lık oturumu),
isteğe bağlı COOKIE2 (sayfa:finansal-denetim yetkisi olmayan ikinci oturum), SEMANTIC_CALLER_TOKEN, SEMANTIC_STORE_DSN,
SEMANTIC_CRM_CONNECTION_FILE, LOGIN_URL (http://127.0.0.1:8796), PORTAL_ORIGIN, LOGIN_DB (giriş servisi SQLite'ının
okunabilir kopyasının yolu) + LOGIN_DB_SOURCE (/var/lib/timas-login/sessions.sqlite; kopya `sudo -n cp` ile denemelerden sonra alınır), AD_CONFIG_FILE, isteğe bağlı LOGIN_PASSWORD_FILE (timasai parolası, yalnız root okur),
PYTHONPATH=<aday ağaç>/backend.
Kullanım: python kabul.py --out /tmp/claude-m49/kabul.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

import sqlalchemy as sa

BASE = os.environ.get("BASE", "http://127.0.0.1:8798").rstrip("/")
P = BASE + "/api/v1/data-security"
COOKIE = os.environ.get("COOKIE", "")
COOKIE2 = os.environ.get("COOKIE2", "")
CALLER = os.environ.get("SEMANTIC_CALLER_TOKEN", "")
LOGIN_URL = os.environ.get("LOGIN_URL", "http://127.0.0.1:8796").rstrip("/")
ORIGIN = os.environ.get("PORTAL_ORIGIN", "https://portal.nanobase.ai")
results: list[tuple[str, bool, str]] = []


def http(method, url, body=None, cookie=None, headers=None, timeout=600):
    data = None if body is None else json.dumps(body).encode()
    h = {"Content-Type": "application/json", **(headers or {})}
    if cookie is not None:
        h["Cookie"] = cookie
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw[:1] in (b"{", b"[") else raw)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, raw


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(("GEÇTİ " if ok else "KALDI ") + name + (f" — {detail}" if detail else ""), flush=True)
    if len(results) % 10 == 0:
        print(f"-- ara durum: {sum(1 for r in results if r[1])} geçti, {sum(1 for r in results if not r[1])} kaldı", flush=True)


def get(path, cookie=COOKIE):
    return http("GET", P + path, cookie=cookie)


def run_due():
    return http("POST", P + "/run-due", headers={"X-Semantic-Caller": CALLER}, cookie="")


def ad_enabled() -> set[str]:
    """AD'deki etkin kişiler — köprünün Directory'si değil, ldap3 ile doğrudan."""
    from ldap3 import NONE, NTLM, SUBTREE, Connection, Server
    cfg = json.load(open(os.environ.get("AD_CONFIG_FILE", "/etc/nanobase/timas-ad.json")))
    srv = Server(cfg["host"], port=int(cfg.get("port", 389)), get_info=NONE, connect_timeout=5)
    conn = Connection(srv, user=f"{cfg['netbios']}\\{cfg['bind_user']}", password=cfg["bind_password"], authentication=NTLM)
    if not conn.bind():
        raise RuntimeError("AD servis hesabı reddedildi")
    out = set()
    flt = "(&(objectCategory=person)(objectClass=user)(!(userAccountControl:1.2.840.113556.1.4.803:=2)))"
    for e in conn.extend.standard.paged_search(cfg["base_dn"], flt, SUBTREE, attributes=["sAMAccountName"], paged_size=500, generator=True):
        if e.get("type") == "searchResEntry":
            v = (e.get("attributes") or {}).get("sAMAccountName")
            v = v[0] if isinstance(v, list) and v else v
            if v:
                out.add(str(v).lower())
    conn.unbind()
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    t0 = datetime.now(timezone.utc)
    json.dump({"t0": t0.isoformat()}, open(a.out, "w"))
    eng = sa.create_engine(os.environ["SEMANTIC_STORE_DSN"])
    st, meta = get("/meta")
    check("meta 200", st == 200, str(st))
    tenant = os.environ.get("SEMANTIC_TENANT_ID", "default")
    ds = os.environ.get("SEMANTIC_DATASOURCE_ID", "")
    if not ds:
        with eng.connect() as c:
            ds = c.execute(sa.text("SELECT datasource_id FROM sl_schema_profile GROUP BY datasource_id ORDER BY count(*) DESC LIMIT 1")).scalar()

    # K1 · Giriş kaydı: bir hatalı (+ varsa bir doğru) giriş → iki yerde aynı sayı.
    http("POST", LOGIN_URL + "/login", {"username": "timasai", "password": "kabul-yanlis-" + str(int(time.time()))},
         headers={"Origin": ORIGIN}, cookie="")
    good = 0
    pw_file = os.environ.get("LOGIN_PASSWORD_FILE", "")
    if pw_file and os.path.exists(pw_file):
        st, _ = http("POST", LOGIN_URL + "/login", {"username": "timasai", "password": open(pw_file).read().strip()},
                     headers={"Origin": ORIGIN}, cookie="")
        good = 1 if st == 200 else 0
    st, out = run_due()
    check("run-due 200 ve giriş olayları çekildi", st == 200 and isinstance(out, dict) and out.get("giris", {}).get("ok"), json.dumps(out)[:300])
    login_db = os.environ.get("LOGIN_DB", "")
    src_db = os.environ.get("LOGIN_DB_SOURCE", "")
    if login_db and src_db:            # denemelerden SONRA kopya: servis dosyası yalnız root/www-data okur
        import subprocess
        subprocess.run(["sudo", "-n", "cp", src_db, login_db], check=False)
        subprocess.run(["sudo", "-n", "chown", str(os.getuid()), login_db], check=False)
    src_n = None
    if login_db and os.path.exists(login_db):
        with sqlite3.connect(login_db) as db:
            src_n = db.execute("SELECT count(*) FROM login_events WHERE username='timasai' AND at > ?", (t0.timestamp(),)).fetchone()[0]
    with eng.connect() as c:
        n, oks = c.execute(sa.text("SELECT count(*), coalesce(sum(CASE WHEN ok THEN 1 ELSE 0 END),0) FROM semantic_security_logins "
                                   "WHERE username='timasai' AND at > :t"), {"t": t0}).one()
    check("R1 giriş kaydı meta DB = giriş servisi", src_n is None or n == src_n, f"meta={n} servis={src_n}")
    check("R1 hatalı + doğru sayısı", n == 1 + good and oks == good, f"toplam={n} başarılı={oks} beklenen={1 + good}/{good}")
    st, lg = get("/logins?user=timasai&ok=0")
    check("giriş kaydı ucu hatalı denemeyi gösteriyor", st == 200 and any(r["reason"] == "bad_password" for r in lg.get("items", [])))

    # K2 · 403 kaydı (ikinci oturum varsa).
    if COOKIE2:
        st, _ = http("GET", BASE + "/api/v1/financial-audit/overview", cookie=COOKIE2)
        with eng.connect() as c:
            n403 = c.execute(sa.text("SELECT count(*) FROM semantic_security_access WHERE kind='forbidden' "
                                     "AND perm_key='sayfa:finansal-denetim' AND at > :t"), {"t": t0}).scalar()
        check("R2 403 kaydı", st == 403 and n403 >= 1, f"durum={st} satır={n403}")
    else:
        print("ATLANDI R2 — COOKIE2 yok (yetkisiz ikinci oturum)")

    # K3 · Envanter.
    st, inv = get("/inventory")
    with eng.connect() as c:
        ref = c.execute(sa.text(
            "SELECT count(*) FROM (SELECT DISTINCT upper(p.entity), upper(c->>'name') FROM sl_schema_profile p, "
            "jsonb_array_elements(p.columns_json::jsonb) c WHERE p.datasource_id=:ds AND (c->>'sensitive')::boolean) x"), {"ds": ds}).scalar()
        tc = c.execute(sa.text(
            "SELECT p.entity, c->>'name', c->>'sensitive' FROM sl_schema_profile p, jsonb_array_elements(p.columns_json::jsonb) c "
            "WHERE p.datasource_id=:ds AND upper(p.entity) LIKE '%CONTACT%' AND lower(c->>'name') ~ '(tckimlik|tc_kimlik|tcno|nufus|tckn)'"),
            {"ds": ds}).all()
    check("R3 maskeli kolon sayısı = katalog", st == 200 and inv.get("sensitiveCount") == ref,
          f"api={inv.get('sensitiveCount') if isinstance(inv, dict) else st} ref={ref} (fark: API yüklü profilleri sayar; ölçülecek)")
    unmasked = [r for r in tc if str(r[2]).lower() != "true"]
    check("R3 CRM kişi TC kolonları işaretli", not unmasked, f"işaretsiz: {unmasked[:5]} (bulgu: SEMANTIC_PII_PATTERNS)")

    # K4 · Hesap hijyeni: CRM etkin − AD etkin.
    st, hy = get("/hygiene")
    try:
        from semantic_layer.profiler.connectors import connector_from_file
        conn = connector_from_file(os.environ["SEMANTIC_CRM_CONNECTION_FILE"])
        _, rows, _ = conn.execute("SELECT DomainName FROM Timas_MSCRM.dbo.SystemUserBase WHERE IsDisabled = 0 "
                                  "AND AccessMode IN (0, 1) AND DomainName IS NOT NULL AND DomainName <> ''", 100_000)
        crm = {str(r["DomainName"]).rsplit("\\", 1)[-1].split("@", 1)[0].strip().lower() for r in rows}
        ad = ad_enabled()
        ref = len({u for u in crm if u} - ad)
        api = (hy.get("counts") or {}).get("crm_etkin_ad_kapali", 0) if isinstance(hy, dict) else None
        check("R4 CRM etkin / AD kapalı sayısı", st == 200 and api == ref, f"api={api} ref={ref} (crm={len(crm)} ad={len(ad)})")
    except Exception as e:  # noqa: BLE001
        check("R4 CRM/AD referansı okunabildi", False, f"{type(e).__name__}: {e}")

    # K5–K6 · Saklama önizlemesi (uygulama kapalı: hiçbir şey değişmemeli).
    st, ret = get("/retention")
    objs = {o["id"]: o for o in ret.get("objects", [])} if isinstance(ret, dict) else {}
    with eng.connect() as c:
        n = objs.get("query_result", {}).get("days") or 0
        ref5 = c.execute(sa.text("SELECT count(*) FROM sl_query_log WHERE tenant_id=:t AND datasource_id=:d AND "
                                 "created_at < now() - (:n || ' days')::interval AND result_json IS NOT NULL"),
                         {"t": tenant, "d": ds, "n": str(n)}).scalar() if n else None
        m = objs.get("llm_text", {}).get("days") or 0
        ref6 = c.execute(sa.text(
            "SELECT (SELECT count(*) FROM sl_llm_queue WHERE enqueued_at < now() - (:n || ' days')::interval AND question IS NOT NULL "
            "AND status IN ('DONE','ABANDONED')) + (SELECT count(*) FROM sl_llm_job WHERE created_at < now() - (:n || ' days')::interval "
            "AND status IN ('DONE','FAILED','CANCELLED') AND (messages_json <> '[]' OR result IS NOT NULL))"), {"n": str(m)}).scalar() if m else None
        before = c.execute(sa.text("SELECT count(*) FROM sl_query_log WHERE result_json IS NOT NULL")).scalar()
    check("R5 soru sonucu önizlemesi = doğrudan sayım", objs.get("query_result", {}).get("rows") == ref5,
          f"api={objs.get('query_result', {}).get('rows')} ref={ref5} gün={n}")
    check("R6 model metni önizlemesi = doğrudan sayım", objs.get("llm_text", {}).get("rows") == ref6,
          f"api={objs.get('llm_text', {}).get('rows')} ref={ref6} gün={m}")
    if not ret.get("apply"):
        st, out = http("POST", P + "/run-due?zorla=gunluk", headers={"X-Semantic-Caller": CALLER}, cookie="")
        with eng.connect() as c:
            after = c.execute(sa.text("SELECT count(*) FROM sl_query_log WHERE result_json IS NOT NULL")).scalar()
            prev_rows = c.execute(sa.text("SELECT count(*) FROM semantic_security_retention_runs WHERE mode='onizleme' AND at > :t"), {"t": t0}).scalar()
            applied = c.execute(sa.text("SELECT count(*) FROM semantic_security_retention_runs WHERE mode='uygulama' AND at > :t"), {"t": t0}).scalar()
        check("uygulama kapalıyken gece işi hiçbir şey silmedi, önizleme yazdı",
              st == 200 and after >= before and prev_rows >= 1 and applied == 0, f"önce={before} sonra={after} önizleme={prev_rows} uygulama={applied}")

    # K7 · «Herkes» önizlemesi.
    st, pv = get("/preview-everyone?remove=sayfa:finansal-denetim")
    try:
        ad = ad_enabled()
        with eng.connect() as c:
            rows = c.execute(sa.text(
                "SELECT b.subject_type, lower(b.subject), m.members FROM semantic_access_bindings b "
                "JOIN semantic_access_role_perms rp ON rp.role_id=b.role_id AND rp.perm='sayfa:finansal-denetim' "
                "LEFT JOIN semantic_access_members m ON m.subject_type=b.subject_type AND m.subject=lower(b.subject) WHERE b.tenant_id=:t "
                "UNION ALL SELECT b.subject_type, lower(b.subject), m.members FROM semantic_access_bindings b "
                "JOIN semantic_access_roles r ON r.id=b.role_id AND r.all_perms AND NOT r.is_system "
                "LEFT JOIN semantic_access_members m ON m.subject_type=b.subject_type AND m.subject=lower(b.subject) WHERE b.tenant_id=:t"),
                {"t": tenant}).all()
            herkes_all, herkes_has = c.execute(sa.text(
                "SELECT r.all_perms, EXISTS(SELECT 1 FROM semantic_access_role_perms p WHERE p.role_id=r.id AND p.perm='sayfa:finansal-denetim') "
                "FROM semantic_access_roles r WHERE r.is_system AND r.tenant_id=:t"), {"t": tenant}).one()
            admins_row = c.execute(sa.text("SELECT value FROM semantic_settings WHERE key='TIMAS_ADMIN_USERS'")).scalar()
            grp = c.execute(sa.text("SELECT members FROM semantic_admin_group")).all()
        keep = set()
        for t, s, mem in rows:
            keep |= {s} if t == "user" else {x.lower() for x in json.loads(mem or "[]")}
        admins = {x.strip().lower() for x in (admins_row or os.environ.get("TIMAS_ADMIN_USERS", "zekiai,timasai,muratsancar")).split(",") if x.strip()}
        for (mem,) in grp:
            admins |= {x.lower() for x in json.loads(mem or "[]")}
        ref7 = len([u for u in ad if u not in admins and u not in keep]) if (herkes_all or herkes_has) else 0
        api7 = next((k["lose"] for k in pv.get("byKey", []) if k["key"] == "sayfa:finansal-denetim"), 0) if isinstance(pv, dict) else None
        check("R7 «Herkes» önizlemesi kaybeden sayısı", st == 200 and api7 == ref7, f"api={api7} ref={ref7} (AD={len(ad)} yönetici={len(admins)})")
    except Exception as e:  # noqa: BLE001
        check("R7 referans okunabildi", False, f"{type(e).__name__}: {e}")

    # K8 · Özet 24 saat 403.
    st, sm = get("/summary")
    with eng.connect() as c:
        ref8 = c.execute(sa.text("SELECT count(*) FROM semantic_security_access WHERE kind='forbidden' AND at >= now() - interval '24 hours'")).scalar()
    check("R8 özet 403 · 24 saat", st == 200 and sm["last24h"]["forbidden"] == ref8, f"api={sm.get('last24h') if isinstance(sm, dict) else st} ref={ref8}")

    # K9 · Dışa aktarma bildirimi yazılıyor.
    st, _ = http("POST", P + "/export-notice", {"what": "M49 kabul denemesi", "format": "csv", "rows": 1, "page": "/kabul"}, cookie=COOKIE)
    with eng.connect() as c:
        n = c.execute(sa.text("SELECT count(*) FROM semantic_security_access WHERE kind='export' AND path='/kabul' AND at > :t"), {"t": t0}).scalar()
    check("dışa aktarma bildirimi kaydedildi", st == 200 and n == 1, f"durum={st} satır={n}")

    # K10 · Yanıtlarda kişisel veri değeri ve teknoloji adı yok.
    bodies = {}
    for path in ("/summary", "/alerts?state=all", "/logins", "/sessions", "/access", "/hygiene", "/inventory", "/retention", "/retention/runs"):
        st, body = get(path)
        bodies[path] = json.dumps(body, ensure_ascii=False)
    leak = {p: re.findall(r"(?<!\d)\d{11}(?!\d)|[\w.+-]+@[\w-]+\.[\w.]+", b)[:3] for p, b in bodies.items()}
    leak = {p: v for p, v in leak.items() if v}
    check("yanıtlarda 11 haneli sayı ve e-posta yok", not leak, json.dumps(leak, ensure_ascii=False)[:300])
    tech = re.compile(r"\b(systemd|docker|nginx|vllm|openvpn|qwen|sqlite|postgres|ldap3)\b", re.I)
    hits = {p: sorted(set(tech.findall(b))) for p, b in bodies.items() if tech.search(b)}
    check("yanıtlarda teknoloji adı yok", not hits, json.dumps(hits, ensure_ascii=False))

    ok = sum(1 for r in results if r[1])
    print(f"== SONUÇ: {ok}/{len(results)} geçti")
    json.dump({"t0": t0.isoformat(), "results": results}, open(a.out, "w"), ensure_ascii=False, indent=1)
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
