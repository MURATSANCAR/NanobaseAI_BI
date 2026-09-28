#!/usr/bin/env python3
"""M51 Müşteri hizmetleri — test sunucusunda gerçek CRM (.28), Logo ve destek masasıyla kabul.

Koşturma (köprünün sanal ortamında, köprünün env dosyasıyla; `calistir.sh` hepsini sırayla yapar):

    set -a; . /etc/nanobase/semantic-bridge.env; set +a
    cd <kaynak>/backend
    # timasai'nin 15 dk'lık oturum çerezi (bellek: test-login-as-timasai); test bitince oturum satırı silinir
    BRIDGE_URL=http://127.0.0.1:8795 TIMAS_COOKIE='timas_session=…' \
      python3 ../scripts/acceptance/M51/kabul.py --out /tmp/claude-<oturum>/m51-kabul.json \
      [--destek-ref /tmp/claude-<oturum>/m51-destek-ref.json] [--yazma]

Her kontrol: OK / FARK / DOĞRULANAMADI / ÖLÇÜM. Portal tarafı köprünün API yanıtıdır (kullanıcının ekranda gördüğü);
referans aynı CRM/Logo'da bağımsız SQL'dir (referans.sql). Uygulamanın SQL'i yeniden koşturulmaz. Örnek sipariş ve
cari seçimi canlıdan yapılır; numaralar yalnız sunucudaki sonuç dosyasına yazılır, belgeye yazılmaz.

Kontroller:
  K1 sipariş durumu ve bekleyen adet (5 sipariş)          K2 kargo firması / tutar (5 takip numaralı sipariş)
  K3 bayi açık sipariş sayısı, bekleyen toplamı, risk (5 cari)   K4 Logo fatura sayısı + tutarı ve veri sonu (5 cari)
  K5 kalite: açık talep, ilk yanıt medyanı, CSAT (masanın veritabanı, --destek-ref)
  K6 güvenlik: yanıtta parola/token alanı yok, panel ucu başlıksız 422 / jetonsuz 401
  K7 KVKK: kapı sırasındaki `destek` sorularında e-posta/telefon/IBAN kalıbı 0
  K8 sınıflama isabeti (temsilcinin düzelttiği oran) — ölçüm
"""
from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))

import sqlalchemy as sa  # noqa: E402

from semantic_bridge import admin as admin_mod  # noqa: E402
from semantic_bridge import budget_sources as bsrc  # noqa: E402
from semantic_bridge import support as S  # noqa: E402
from semantic_bridge import support_sources as src  # noqa: E402
from semantic_layer.store.catalog_store import open_store  # noqa: E402

RESULTS: list[dict] = []
BRIDGE = os.environ.get("BRIDGE_URL", "http://127.0.0.1:8795").rstrip("/")
COOKIE = os.environ.get("TIMAS_COOKIE", "")
CALLER = os.environ.get("SEMANTIC_CALLER_TOKEN", "")
PENDING_EXCL = "100000015, 100000000, 100000001, 100000003, 2"


def record(name: str, status: str, **detail) -> None:
    RESULTS.append({"kontrol": name, "durum": status, **detail})
    print(f"[{status:>13}] {name}  {json.dumps(detail, ensure_ascii=False, default=str)[:400]}")


def close(a, b, tol=0.01) -> bool:
    return a is not None and b is not None and abs(float(a) - float(b)) <= tol


def api(method: str, path: str, body=None, headers=None, cookie=True):
    h = {"X-Semantic-Caller": CALLER, "Content-Type": "application/json", **(headers or {})}
    if cookie and COOKIE:
        h["Cookie"] = COOKIE
    req = urllib.request.Request(f"{BRIDGE}{path}", method=method, headers=h,
                                 data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.load(e)
        except Exception:  # noqa: BLE001
            return e.code, {}


def q(s: str) -> str:
    return str(s).replace("'", "''")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="m51-kabul.json")
    ap.add_argument("--destek-ref", default="")
    ap.add_argument("--ornek", type=int, default=5)
    ap.add_argument("--yazma", action="store_true", help="yazma uçlarını boş/geçersiz gövdeyle dener (kayıt açmaz)")
    args = ap.parse_args()
    n = max(5, args.ornek)

    engine = open_store(os.environ["SEMANTIC_STORE_DSN"], create=False).engine
    S.ensure(engine)
    admin_mod.ensure(engine)
    tenant = os.environ.get("SEMANTIC_TENANT_ID", "default")
    st = S.settings_from(admin_mod.conf)
    p = src.prefix(st["schema"])
    crm = bsrc.runner(os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json"))
    logo = bsrc.runner(os.environ["SEMANTIC_CONNECTION_FILE"])
    if not COOKIE:
        record("API oturumu", "DOĞRULANAMADI", neden="TIMAS_COOKIE yok (timasai kısa oturumu açılmalı)")
        return finish(args)
    code, meta = api("GET", "/api/v1/support/meta")
    record("meta", "OK" if code == 200 else "FARK", durum=code, yetki=(meta or {}).get("me"))

    # K1 — sipariş durumu ve bekleyen adet: son 60 günün farklı durumlarından örnek
    orders = crm(f"""SELECT TOP {n} s.new_name AS no, CAST(s.statuscode AS int) AS durum, s.new_bekleyenadet AS bekleyen
FROM {p}new_siparisBase s WHERE s.statecode = 0 AND s.new_name IS NOT NULL
  AND s.new_siparistarihi >= DATEADD(day, -60, GETDATE()) ORDER BY NEWID()""")
    for o in orders:
        c, r = api("GET", "/api/v1/support/context?" + urllib.parse.urlencode({"order": o["no"]}))
        got = next((x for x in (r or {}).get("orders", []) if x.get("no") == o["no"]), None)
        ok = c == 200 and got and int(got["durum"]) == int(o["durum"]) and close(got.get("bekleyen") or 0, o["bekleyen"] or 0)
        record("K1 sipariş durumu/bekleyen", "OK" if ok else "FARK", no=o["no"], api=got and [got["durum"], got.get("bekleyen")],
               referans=[o["durum"], o["bekleyen"]], http=c)

    # K2 — kargo: takip numaralı siparişlerin kargo kaydı (firma ve tutar, C19 metin → sayı)
    cargo = crm(f"""SELECT TOP {n} s.new_name AS no, b.new_KargoTakipNo AS takip, b.new_kargofirmasi AS firma,
  TRY_CAST(REPLACE(b.new_Tutar, ',', '.') AS FLOAT) AS tutar  -- Kural C19 (binlik noktalı değer NULL döner, karşılaştırma atlanır)
FROM {p}new_siparisBase s JOIN {p}new_kargobilgisiBase b ON b.new_KargoTakipNo = s.new_kargotakipno AND b.statecode = 0
WHERE s.statecode = 0 AND ISNULL(s.new_kargotakipno, '') <> '' ORDER BY s.new_siparistarihi DESC""")
    if not cargo:
        record("K2 kargo kaydı", "DOĞRULANAMADI", neden="takip numarasıyla eşleşen kargo kaydı yok — SUPPORT_CARGO_MATCH ölçülmeli")
    for k in cargo:
        c, r = api("GET", "/api/v1/support/context?" + urllib.parse.urlencode({"order": k["no"]}))
        got = next((x for x in (r or {}).get("cargo", []) if x.get("takipNo") == k["takip"]), None)
        ok = got and (got.get("firma") or "") == (k["firma"] or "") and (k["tutar"] is None or close(got.get("tutar"), k["tutar"]))
        record("K2 kargo firması/tutar", "OK" if ok else "FARK", no=k["no"], api=got and [got.get("firma"), got.get("tutar")],
               referans=[k["firma"], k["tutar"]])

    # K3 — bayi görünümü: açık (bekleyen) sipariş sayısı, bekleyen adet toplamı, risk onayı bekleyen
    dealers = crm(f"""SELECT TOP {n} s.new_firmaid AS id, COUNT(*) AS acik, SUM(s.new_bekleyenadet) AS bekleyen,
  SUM(CASE WHEN CAST(s.statuscode AS int) IN (100000004, 100000016) THEN 1 ELSE 0 END) AS risk
FROM {p}new_siparisBase s JOIN {p}AccountBase a ON a.AccountId = s.new_firmaid AND a.StateCode = 0
WHERE s.statecode = 0 AND s.new_bekleyenadet > 0 AND CAST(s.statuscode AS int) NOT IN ({PENDING_EXCL})
GROUP BY s.new_firmaid ORDER BY NEWID()""")
    dealer_codes = []
    for d in dealers:
        c, r = api("GET", f"/api/v1/support/dealer/{str(d['id']).strip('{}').lower()}")
        s = (r or {}).get("dealerSummary") or {}
        ok = c == 200 and int(s.get("open") or -1) == int(d["acik"]) and close(s.get("pending"), d["bekleyen"])
        # Risk: yalnız açık olanlar değil, penceredeki bütün risk durumundaki siparişler sayılır (ekranla aynı tanım).
        risk_ref = crm(f"""SELECT COUNT(*) AS v FROM {p}new_siparisBase s WHERE s.statecode = 0 AND s.new_firmaid = '{str(d['id']).strip('{}')}'
  AND CAST(s.statuscode AS int) IN (100000004, 100000016)
  AND (s.new_siparistarihi >= DATEADD(day, -{st['orderDays']}, CAST(GETDATE() AS date))
       OR (s.new_bekleyenadet > 0 AND CAST(s.statuscode AS int) NOT IN ({PENDING_EXCL})))""")[0]["v"]
        record("K3 bayi açık/bekleyen/risk", "OK" if ok and int(s.get("risk") or 0) == int(risk_ref) else "FARK",
               api=[s.get("open"), s.get("pending"), s.get("risk")], referans=[d["acik"], d["bekleyen"], risk_ref], http=c)
        acc = (r or {}).get("account") or {}
        if acc.get("cariKodu"):
            dealer_codes.append((acc["cariKodu"], r))

    # K4 — Logo faturaları (satış + iade) pencere içinde sayı ve net tutar; veri sonu
    firms = bsrc.firms_by_year(logo)
    today = date.today()
    since = src.since_months(today, st["logoMonths"])
    years = [y for y in range(since.year, today.year + 1) if y in firms]
    cur = firms[max(y for y in firms if y <= today.year)]
    end_ref = logo(f"SELECT MAX(DATE_) AS v FROM dbo.LG_{cur}_01_STLINE WHERE CANCELLED = 0 AND LINETYPE = 0 AND INVOICEREF <> 0 AND TRCODE IN (7,8,9)")[0]["v"]
    for code_, r in dealer_codes[:n]:
        cnt = tot = 0
        for y in years:
            row = logo(f"""SELECT COUNT(*) AS n, SUM(I.NETTOTAL) AS t FROM dbo.LG_{firms[y]}_01_INVOICE I
JOIN dbo.LG_{firms[y]}_CLCARD C ON C.LOGICALREF = I.CLIENTREF
WHERE I.CANCELLED = 0 AND I.TRCODE IN (2,3,7,8,9) AND C.CODE = '{q(code_)}' AND I.DATE_ >= '{since.isoformat()}'""")[0]
            cnt += int(row["n"] or 0)
            tot += float(row["t"] or 0)
        inv = r.get("invoices") or []
        ok = len(inv) == cnt and close(sum(float(i.get("tutar") or 0) for i in inv), tot)
        record("K4 Logo fatura sayısı/tutarı", "OK" if ok else "FARK", cari=code_, api=[len(inv), sum(float(i.get("tutar") or 0) for i in inv)],
               referans=[cnt, tot])
        record("K4 veri sonu", "OK" if str((r.get("logo") or {}).get("dataEnd") or "")[:10] == str(end_ref)[:10] else "FARK",
               api=(r.get("logo") or {}).get("dataEnd"), referans=str(end_ref)[:10])
    if not dealer_codes:
        record("K4 Logo faturası", "DOĞRULANAMADI", neden="cari kodlu bayi örneği yok")

    # K5 — kalite panosu masanın kendi veritabanıyla (calistir.sh docker exec ile üretir)
    c, qual = api("GET", "/api/v1/support/quality?" + urllib.parse.urlencode({"from": (today - timedelta(days=29)).isoformat(),
                                                                              "to": today.isoformat()}))
    if not (qual or {}).get("configured"):
        record("K5 kalite", "DOĞRULANAMADI", neden="destek masası bağlantısı ayarlanmamış (DESTEK_API_*)", http=c)
    elif not args.destek_ref or not Path(args.destek_ref).exists():
        record("K5 kalite", "DOĞRULANAMADI", neden="--destek-ref yok", api={k: qual.get(k) for k in ("opened", "openNow", "firstResponseMedianMin", "csat")})
    else:
        ref = json.loads(Path(args.destek_ref).read_text())
        record("K5 açılan talep (30 gün)", "OK" if qual.get("opened") == ref.get("opened") else "FARK", api=qual.get("opened"), referans=ref.get("opened"))
        record("K5 açık talep", "OK" if qual.get("openNow") == ref.get("open") else "FARK", api=qual.get("openNow"), referans=ref.get("open"))
        fr = ref.get("first_minutes") or []
        med = round(statistics.median(fr), 1) if fr else None
        record("K5 ilk yanıt medyanı (dk)", "OK" if (med is None and qual.get("firstResponseMedianMin") is None) or close(qual.get("firstResponseMedianMin"), med, 0.2) else "FARK",
               api=qual.get("firstResponseMedianMin"), referans=med)
        rt = [x * 5 if x <= 1 else x for x in (ref.get("ratings") or []) if x and x > 0]
        csat = round(sum(rt) / len(rt), 2) if rt else None
        record("K5 CSAT", "OK" if (csat is None and qual.get("csat") is None) or close(qual.get("csat"), csat) else "FARK",
               api=qual.get("csat"), referans=csat)

    # K6 — güvenlik
    blob = json.dumps(RESULTS, ensure_ascii=False).lower()
    bad = [w for w in ("new_sifre", "new_token", "clientsecret", "\"sifre\"", "password") if w in blob]
    record("K6 yanıtta kimlik bilgisi alanı yok", "OK" if not bad else "FARK", bulunan=bad)
    c1, _ = api("GET", "/api/v1/support/panel/context?ticket=X", cookie=False)
    record("K6 panel ucu temsilci başlığı olmadan", "OK" if c1 == 422 else "FARK", http=c1, beklenen=422)
    if CALLER:
        req = urllib.request.Request(f"{BRIDGE}/api/v1/support/panel/context?ticket=X", headers={"X-Destek-Agent": "timasai"})
        try:
            urllib.request.urlopen(req, timeout=30)
            c2 = 200
        except urllib.error.HTTPError as e:
            c2 = e.code
        record("K6 panel ucu çağıran jetonu olmadan", "OK" if c2 == 401 else "FARK", http=c2, beklenen=401)

    # K7 — KVKK: kapı sırasındaki destek modülü soruları
    pat = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}|(?<!\d)0?5\d{2}[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}(?!\d)|TR\d{2}\s?\d{4}")
    with engine.connect() as cn:
        rows = cn.execute(sa.text("SELECT question FROM sl_llm_queue WHERE module = 'destek' AND purpose NOT LIKE '%openai%' "
                                  "AND enqueued_at >= :d"), {"d": today - timedelta(days=7)}).all()
    leaks = sum(1 for (qq,) in rows if qq and pat.search(qq))
    record("K7 modele giden metinde kişisel veri", "OK" if leaks == 0 else "FARK", soru=len(rows), kalip=leaks,
           not_="masanın kendi paneli (openai girişi) bu sayıma girmez; o metin masanın")

    # K8 — sınıflama isabeti (ölçüm): temsilcinin düzelttiği oran
    with engine.connect() as cn:
        tot = cn.execute(sa.select(sa.func.count()).select_from(S.INSIGHTS).where(S.INSIGHTS.c.tenant_id == tenant,
                                                                                  S.INSIGHTS.c.klass_method.isnot(None))).scalar() or 0
        fixed = cn.execute(sa.select(sa.func.count()).select_from(S.INSIGHTS).where(
            S.INSIGHTS.c.tenant_id == tenant, S.INSIGHTS.c.klass_by.isnot(None), S.INSIGHTS.c.klass_by != "zeki")).scalar() or 0
        unsure = cn.execute(sa.select(sa.func.count()).select_from(S.INSIGHTS).where(
            S.INSIGHTS.c.tenant_id == tenant, S.INSIGHTS.c.klass_method.isnot(None), S.INSIGHTS.c.klass.is_(None))).scalar() or 0
    record("K8 sınıflama", "ÖLÇÜM", siniflanan=tot, duzeltilen=fixed, siniflanamadi=unsure,
           isabet=(round(1 - fixed / tot, 3) if tot else None), hedef=0.85)

    if args.yazma:
        c, _ = api("POST", "/api/v1/support/classify", {})
        record("yazma: boş sınıflama gövdesi", "OK" if c == 422 else "FARK", http=c)
        c, _ = api("POST", "/api/v1/support/draft", {})
        record("yazma: boş taslak gövdesi", "OK" if c == 422 else "FARK", http=c)
        c, _ = api("PATCH", "/api/v1/support/faq/gaps/yok", {"status": "gecersiz"})
        record("yazma: olmayan SSS maddesi", "OK" if c in (403, 404, 422) else "FARK", http=c)
    return finish(args)


def finish(args) -> int:
    Path(args.out).write_text(json.dumps(RESULTS, ensure_ascii=False, indent=1, default=str))
    bad = [r for r in RESULTS if r["durum"] == "FARK"]
    unv = [r for r in RESULTS if r["durum"] == "DOĞRULANAMADI"]
    print(f"\nOK {sum(1 for r in RESULTS if r['durum'] == 'OK')} · FARK {len(bad)} · DOĞRULANAMADI {len(unv)} → {args.out}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
