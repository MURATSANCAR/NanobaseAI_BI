"""M23 İşbirlikleri — gerçek API ↔ doğrudan SQL kabulü (test sunucusunda, yan port köprüsü, CRM salt okunur).

Uçların kullanıcıya verdiği sonuç, köprü kodu kullanılmadan yazılmış doğrudan CRM ve katalog sorgularıyla
karşılaştırılır (`referans.sql` R1–R5). Kitap ve tanıtım siparişleri her koşuda CRM'den rastgele seçilir (sabit örnek
yok). Yazma: bir deneme içerik üreticisi ve işbirliği(leri) açılır; kimlikleri `--out` dosyasına yazılır, `cleanup.py`
siler (hesap, ölçüm, olay, taslak, ödeme satırı, hatırlatma ve değişiklik kaydı dahil).

Ortam: BASE (ör. http://127.0.0.1:8798), COOKIE (timasai'nin kısa oturum çerezi), isteğe bağlı COOKIE2 (işbirliği onay
yetkisi olan ikinci oturum: teklif onayı ve ücretli akış; yoksa o adımlar «atlandı»), isteğe bağlı COOKIE3 (onay/ödeme
yetkisi olmayan oturum: ücretin gizlendiği denetlenir), SEMANTIC_CRM_CONNECTION_FILE, SEMANTIC_CALLER_TOKEN (run-due),
PYTHONPATH=<aday ağaç>/backend. İsteğe bağlı M23_BAS / M23_BIT (R2 dönemi; varsayılan son 365 gün).
Kullanım: python kabul.py --out /tmp/claude-m23/kabul-kimlikler.json
"""
from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from datetime import date, timedelta
from decimal import Decimal

import sqlalchemy as sa

from semantic_bridge import budget_sources as bsrc
from semantic_layer.config import SemanticSettings
from semantic_layer.store.catalog_store import open_store

BASE = os.environ.get("BASE", "http://127.0.0.1:8798").rstrip("/")
COOKIE = os.environ.get("COOKIE", "")
COOKIE2 = os.environ.get("COOKIE2", "")
COOKIE3 = os.environ.get("COOKIE3", "")
P = BASE + "/api/v1/influencers"
SCHEMA = os.environ.get("CRM_SCHEMA", "Timas_MSCRM.dbo")
results: list[tuple[str, bool, str]] = []
created: dict[str, list[str]] = {"people": [], "collabs": []}


def http(method: str, url: str, body=None, timeout=900, cookie=None, headers=None, raw=False):
    data = None if body is None else json.dumps(body).encode()
    h = {"Cookie": cookie or COOKIE, "Content-Type": "application/json", **(headers or {})}
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            payload = r.read()
            if raw:
                return r.status, payload
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


def skip(name: str, why: str) -> None:
    print(f"ATLANDI {name} — {why} (DOĞRULANAMADI)", flush=True)


def q(v: str) -> str:
    return "N'" + str(v).replace("'", "''") + "'"


def close(a: float | None, b: float | None, tol: float = 0.01) -> bool:
    return (a is None and b is None) or (a is not None and b is not None and abs(float(a) - float(b)) <= tol)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    crm = bsrc.runner(os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json"))
    settings = SemanticSettings.from_env()
    store = open_store(settings.store_dsn).engine
    tenant = settings.tenant_id
    try:
        return run(crm, store, tenant)
    finally:
        with open(a.out, "w") as fh:
            json.dump(created, fh)
        ok = sum(1 for r in results if r[1])
        print(f"== SONUÇ: {ok}/{len(results)} geçti; kimlikler {a.out} (cleanup.py ile silin)")


def run(crm, store, tenant) -> int:
    today = date.today()
    # 0. Geçersiz istekler (yazmadan önce).
    s, meta = http("GET", P + "/meta")
    check("meta 200", s == 200, str(s))
    s, _ = http("POST", P + "/people", {})
    check("boş gövdeyle kişi 400", s == 400, str(s))
    s, _ = http("POST", P + "/collabs", {})
    check("boş gövdeyle işbirliği 400/404", s in (400, 404), str(s))
    s, _ = http("GET", P + "/collabs/yok-boyle")
    check("olmayan işbirliği 404", s == 404, str(s))
    s, _ = http("POST", P + "/run-due", {}, cookie="x=y")
    check("run-due oturumla çağrılamaz (401/403)", s in (401, 403), str(s))

    # R3 · Sosyal alanı olan CRM kişileri.
    s, sm = http("GET", P + "/crm/summary")
    ref = crm(f"SELECT COUNT(*) AS kisi, SUM(CASE WHEN ISNULL(new_yazarmi, 0) = 1 THEN 1 ELSE 0 END) AS yazar FROM {SCHEMA}.ContactBase "
              "WHERE statecode = 0 AND (NULLIF(LTRIM(new_Instagram), '') IS NOT NULL OR NULLIF(LTRIM(new_YoutubeKullancAd), '') IS NOT NULL "
              "OR NULLIF(LTRIM(new_TwitterKullaniciAdi), '') IS NOT NULL)")[0]
    check("R3 sosyal kullanıcı adlı CRM kişisi = doğrudan SQL", s == 200 and sm["kisi"] == int(ref["kisi"] or 0)
          and sm["yazar"] == int(ref["yazar"] or 0), f"uç {sm} · SQL {ref}")

    # R2 · CRM pazarlama bütçe modülü «Influencer» harcaması.
    bas = date.fromisoformat(os.environ.get("M23_BAS") or (today - timedelta(days=365)).isoformat())
    bit = date.fromisoformat(os.environ.get("M23_BIT") or today.isoformat())
    s, rep = http("GET", P + f"/report?frm={bas}&to={bit}")
    r2 = crm(f"SELECT SUM(new_tutar) AS toplam, COUNT(*) AS kayit FROM {SCHEMA}.new_pazarlamamoduluBase WHERE statecode = 0 "
             f"AND new_mecratipi4 = 6 AND new_baslangictarihi >= DATEADD(HOUR, -3, CAST('{bas}' AS datetime)) "
             f"AND new_baslangictarihi < DATEADD(HOUR, -3, DATEADD(DAY, 1, CAST('{bit}' AS datetime)))")[0]
    crm_part = (rep or {}).get("crm") or {}
    check("R2 CRM «Influencer» mecra harcaması = doğrudan SQL", s == 200 and close(crm_part.get("toplam"), float(r2["toplam"] or 0))
          and crm_part.get("kayit") == int(r2["kayit"] or 0), f"uç {crm_part.get('toplam')}/{crm_part.get('kayit')} · SQL {r2}")

    # Deneme verisi: rastgele bir CRM kitabı ve tanıtım gönderimi siparişleri.
    book = crm(f"SELECT TOP 1 new_kitapId AS id, new_name AS ad, new_turlertext AS turler, new_rafturu AS raf, "
               f"new_hedefkitleyasbaslangic AS yb, new_hedefkitleyasbitis AS ye FROM {SCHEMA}.new_kitapBase "
               f"WHERE statecode = 0 AND new_Tip = 1 AND NULLIF(LTRIM(new_turlertext), '') IS NOT NULL ORDER BY NEWID()")[0]
    orders = [r["no"] for r in crm(f"SELECT TOP 3 new_name AS no FROM {SCHEMA}.new_siparisBase WHERE new_siparistipi = 12 "
                                   "AND new_name IS NOT NULL ORDER BY NEWID()")]
    kitap = str(book["id"]).lower()
    s, p = http("POST", P + "/people", {"name": "M23 kabul (silinecek)", "topics": ["tarih", "edebiyat"], "ageGroups": ["18+"],
                                         "accounts": [{"platform": "blog", "handle": f"m23-kabul-{os.getpid()}"}]})
    check("kişi açıldı 201", s == 201, str(p)[:160])
    if s != 201:
        return 1
    pid = p["id"]
    created["people"].append(pid)
    s, c1 = http("POST", P + "/collabs", {"personId": pid, "kind": "hediye", "crmBookId": kitap, "bookTitle": book["ad"],
                                          "crmOrderNo": ", ".join(orders), "duePublish": today.isoformat()})
    check("hediye işbirliği açıldı 201", s == 201, str(c1)[:160])
    if s == 201:
        created["collabs"].append(c1["id"])

    # R1 · Kişi kartındaki tanıtım gönderimi adedi.
    s, card = http("GET", P + f"/people/{pid}")
    if orders:
        r1 = crm(f"SELECT SUM(ss.new_adet) AS adet, COUNT(DISTINCT s.new_name) AS siparis FROM {SCHEMA}.new_siparissatiriBase ss "
                 f"JOIN {SCHEMA}.new_siparisBase s ON s.new_siparisId = ss.new_siparisid WHERE s.new_siparistipi = 12 "
                 f"AND s.new_name IN ({', '.join(q(o) for o in orders)})")[0]
        got = (card.get("crmOrders") or {}) if s == 200 else {}
        check("R1 gönderilen kitap adedi = doğrudan SQL", close(got.get("toplamAdet"), float(r1["adet"] or 0))
              and len(got.get("siparisler") or []) == int(r1["siparis"] or 0), f"uç {got.get('toplamAdet')} · SQL {r1}")
    else:
        skip("R1 gönderilen kitap adedi", "CRM'de tanıtım gönderimi siparişi yok")

    # Aday sırası: kitap bilgisi CRM ile birebir; bu kişi aynı kitabı aldığı için «ayrı listede».
    s, cand = http("GET", P + f"/books/{kitap}/candidates")
    if s == 200:
        bk = cand["book"]
        check("aday sırası kitap bilgisi = CRM (tür, raf, yaş)", (bk.get("turler") or "").split() == str(book["turler"] or "").split()
              and (bk.get("raf") or None) == (" ".join(str(book["raf"]).split()) if book["raf"] else None)
              and (bk.get("yas") or [None, None])[0] == (int(book["yb"]) if book["yb"] is not None else None),
              f"{bk.get('turler')} · {bk.get('raf')} · {bk.get('yas')}")
        check("aynı kitabı alan kişi ayrı listede", any(e["personId"] == pid for e in cand["excluded"]),
              f"{len(cand['items'])} aday, {len(cand['excluded'])} ayrı")
        scores = [i["score"] for i in cand["items"]]
        check("aday puanı 0–100 ve sıralı, tavansız", scores == sorted(scores, reverse=True) and all(0 <= x <= 100 for x in scores)
              and cand["total"] == len(cand["items"]), f"{len(scores)} aday")
    else:
        check("aday sırası 200", False, f"{s} {str(cand)[:160]}")

    # İlerletme kapıları (gerçek uçta): bağlantısız «yayında» 400, yasal etiketsiz rapor 409.
    if c1 and created["collabs"]:
        cid = c1["id"]
        need_approval = c1.get("waitingApproval")
        if need_approval and COOKIE2:
            s, _ = http("POST", P + f"/collabs/{cid}/approve", {"decision": "onay"}, cookie=COOKIE2)
            check("ikinci kişi teklifi onayladı", s == 200, str(s))
            need_approval = s != 200
        s, _ = http("POST", P + f"/collabs/{cid}/approve", {"decision": "onay"})
        check("teklifi açan onaylayamaz (409) ya da zaten onaylı", s in (409, 403), str(s))
        if not need_approval:
            s, e = http("PATCH", P + f"/collabs/{cid}", {"stage": "yayinda"})
            check("bağlantısız «yayında» 400", s == 400, f"{s} {str(e)[:120]}")
            s, e = http("PATCH", P + f"/collabs/{cid}", {"stage": "rapor", "publishedUrl": "https://example.org/m23-kabul", "engagement": 7})
            check("yasal etiketsiz rapor 409", s == 409, f"{s} {str(e)[:120]}")
            s, e = http("PATCH", P + f"/collabs/{cid}", {"stage": "rapor", "publishedUrl": "https://example.org/m23-kabul",
                                                        "disclosureOk": True, "engagement": 7, "reach": 70})
            check("rapor 200", s == 200, f"{s} {str(e)[:120]}")
            s, e = http("PATCH", P + f"/collabs/{cid}", {"stage": "odeme"})
            check("ücretsiz iş ödemeye girmez 409", s == 409, f"{s} {str(e)[:120]}")
        else:
            skip("aşama kapıları", "COOKIE2 yok; hediye de onay istiyor (INFLUENCER_GIFT_NEEDS_APPROVAL=1)")
        s, d = http("POST", P + f"/collabs/{cid}/draft", {"kind": "brief"}, timeout=600)
        check("brief taslağı 201 ve yasal etiket maddesi sabit", s == 201 and "Reklam Kurulu" in (d.get("body") or ""),
              f"{s} kaynak={d.get('source') if s == 201 else d}")

    # Ücretli akış (ikinci onaycı varsa): ödeme satırı hazır → R5.
    if COOKIE2:
        s, c2 = http("POST", P + "/collabs", {"personId": pid, "kind": "ucretli", "fee": "1", "crmBookId": kitap, "repeat": True,
                                              "bookTitle": book["ad"], "duePublish": today.isoformat()})
        if s == 201:
            created["collabs"].append(c2["id"])
            http("POST", P + f"/collabs/{c2['id']}/approve", {"decision": "onay"}, cookie=COOKIE2)
            s, _ = http("PATCH", P + f"/collabs/{c2['id']}", {"stage": "rapor", "publishedUrl": "https://example.org/m23-kabul-2",
                                                              "disclosureOk": True, "engagement": 3})
            s, _ = http("PATCH", P + f"/collabs/{c2['id']}", {"stage": "odeme"})
            check("ücretli iş ödemeye geçti, satır hazır", s == 200, str(s))
    else:
        skip("ücretli akış ve ödeme satırı", "COOKIE2 (onay yetkili ikinci oturum) yok")

    # R4 · Rapor (bu ay) = portal kataloğunda doğrudan SQL.
    m0 = today.replace(day=1)
    s, rep = http("GET", P + f"/report?frm={m0}&to={today}&crm_spend=false")
    with store.connect() as c:
        r4 = c.execute(sa.text(
            "SELECT COUNT(*) AS n, COALESCE(SUM(fee), 0) AS harcama, COALESCE(SUM(engagement), 0) AS eng, COALESCE(SUM(reach), 0) AS reach "
            "FROM semantic_infl_collabs WHERE tenant_id = :t AND stage <> 'vazgecildi' "
            "AND COALESCE(published_at, due_publish, created_day) BETWEEN :a AND :b"), {"t": tenant, "a": m0, "b": today}).first()
    t = (rep or {}).get("total") or {}
    cpe = (Decimal(r4.harcama) / Decimal(r4.eng)).quantize(Decimal("0.0001")) if r4.eng else None
    check("R4 rapor işbirliği/harcama/etkileşim/CPE = doğrudan SQL",
          s == 200 and t.get("collabs") == r4.n and close(t.get("spend"), float(r4.harcama)) and t.get("engagement") == int(r4.eng)
          and t.get("reach") == int(r4.reach) and close(t.get("cpe"), float(cpe) if cpe is not None else None, 0.0001),
          f"uç {t} · SQL n={r4.n} harcama={r4.harcama} eng={r4.eng} cpe={cpe}")

    # R5 · Ödeme listesi tutarlılığı ve uç ↔ SQL.
    with store.connect() as c:
        bad1 = c.execute(sa.text("SELECT COUNT(*) FROM semantic_infl_payouts p JOIN semantic_infl_collabs c ON c.id = p.collab_id "
                                 "WHERE p.status IN ('hazir','onayli') AND c.stage <> 'odeme'")).scalar()
        bad2 = c.execute(sa.text("SELECT COUNT(*) FROM semantic_infl_payouts p JOIN semantic_infl_collabs c ON c.id = p.collab_id "
                                 "WHERE p.status = 'odendi' AND c.stage <> 'kapali'")).scalar()
        m1 = (m0 + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        r5 = {r.status: (r.n, float(r.t or 0)) for r in c.execute(sa.text(
            "SELECT status, COUNT(*) AS n, SUM(amount) AS t FROM semantic_infl_payouts WHERE tenant_id = :t AND "
            "(status IN ('hazir','onayli') OR (status = 'odendi' AND paid_at BETWEEN :a AND :b)) GROUP BY status"),
            {"t": tenant, "a": m0, "b": m1})}
    check("R5 açık ödeme satırının işi «ödeme»de, ödenenin işi kapalı", bad1 == 0 and bad2 == 0, f"{bad1} / {bad2}")
    s, pays = http("GET", P + "/payouts")
    if s == 200:
        got = {k: (sum(1 for i in pays["items"] if i["status"] == k), pays["totals"].get(k, 0.0)) for k in ("hazir", "onayli", "odendi")}
        want = {k: r5.get(k, (0, 0.0)) for k in got}
        check("R5b ödeme listesi ucu = doğrudan SQL", all(got[k][0] == want[k][0] and close(got[k][1], want[k][1]) for k in got),
              f"uç {got} · SQL {want}")
    else:
        check("ödeme listesi 200 (yetkili oturum)", False, str(s))

    # Yetki: onay/ödeme yetkisi olmayan kullanıcıda ücret alanları boş (kabul 6).
    if COOKIE3:
        s, card3 = http("GET", P + f"/people/{pid}", cookie=COOKIE3)
        s2, pay3 = http("GET", P + "/payouts", cookie=COOKIE3)
        check("yetkisiz kullanıcıda ücret boş, ödeme listesi 403", s == 200 and card3["feeMin"] is None and card3["feeMax"] is None
              and all(c.get("fee") is None for c in card3["collabs"]) and s2 == 403, f"{s} {s2}")
    else:
        skip("ücretin gizlenmesi", "COOKIE3 (onay/ödeme yetkisi olmayan oturum) yok")

    # Zamanlayıcı ucu (sistem çağrısı).
    tok = os.environ.get("SEMANTIC_CALLER_TOKEN", "")
    if tok:
        s, rd = http("POST", P + "/run-due", {}, cookie="", headers={"X-Semantic-Caller": tok})
        check("run-due 200", s == 200, json.dumps(rd, ensure_ascii=False)[:200])
    else:
        skip("run-due", "SEMANTIC_CALLER_TOKEN yok")
    return 0 if all(r[1] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
