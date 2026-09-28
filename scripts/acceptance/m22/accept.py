"""M22 Sosyal medya — kabul (test sunucusunda, gerçek CRM .28 + Logo, çalışan köprüye karşı).

Koşum (test sunucusu, köprünün env'i ile; Mac'te koşulmaz):

    cd <köprü kaynağı>/backend && set -a && . /etc/nanobase/semantic-bridge.env && set +a \
      && M22_COOKIE='timas_session=…' python3 ../scripts/acceptance/m22/accept.py [--month 2026-10] [--write] [--draft] \
         > m22-kabul.json

`M22_COOKIE`: `timasai` hesabının kısa ömürlü (15 dk) portal oturumu (kullanıcı belleği «test-login-as-timasai»); kabul
bitince oturum satırı giriş servisinde silinir. Yeni kullanıcı adı uydurulmaz.

Denetimler — uygulamanın verdiği sonuç, bağımsız doğrudan SQL referansıyla karşılaştırılır:
  1. Özel gün: fırsat ekranındaki her CRM özel gününün bağlı kitap sayısı = `COUNT(DISTINCT kg.new_kitapid)` (aynı adlı
     günler birleşik; gün ve kitap kartı etkin). Pencere 366 gün: tarihi hesaplanabilen bütün günler.
  2. Yeni kitaplar: ekrandaki pencerede (ay başı → pencere sonu) ilk yayını olan etkin «Kitap» kartları = CRM
     `new_kitapBase` (stok kodu kümesi birebir; tavan yok).
  3. Backlist çok satan: ilk 10 kitabın son 12 ay net adedi = Logo `STLINE` faturalı satır (TRCODE 7/8/9 − 2/3) aynı
     pencerede (adet birebir). Sıra da azalan adet olmalı.
  4. Takvim: `--month` ayının ekrandaki durum sayıları = `SELECT status, COUNT(*) FROM semantic_social_posts … GROUP BY
     status`.
  5. Marka hesapları: hesap önerisindeki Instagram kullanıcı adları = `new_markaBase.new_instagramkullaniciadi` dolu olan
     etkin markalar (küme birebir).
  6. (--write) İçe aktarma: kabul hesabına küçük bir CSV yüklenir; API toplam erişimi = `SUM(reach) … WHERE import_id`;
     kabul gönderisini gönderen onaylayamaz (409); paket yalnız onaylıdan (409). Kimlikler durum dosyasına yazılır,
     `cleanup.py` siler.
  7. Teknoloji adı ve web bayrağı: meta, takvim ve fırsat cevabında model/ürün adı yok; `WEB_WATCH_ENABLED=0` iken basın
     kutusu boş. (--draft) Zeki AI taslağında teknoloji adı ve kaynaksız rakam yok (denetim düşürmüş olmalı).
Çıktı: JSON; `ok` her denetim için; sonunda özet.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))

import sqlalchemy as sa  # noqa: E402

from semantic_bridge import budget_sources as bsrc  # noqa: E402
from semantic_bridge.marketing import guard as G  # noqa: E402
from semantic_bridge.seo_geo import seasons as SS  # noqa: E402
from semantic_layer.config import SemanticSettings  # noqa: E402
from semantic_layer.store.catalog_store import open_store  # noqa: E402

BRIDGE = os.environ.get("M22_BRIDGE", "http://127.0.0.1:8795")
STATE = Path(os.environ.get("M22_STATE", "m22-kabul-state.json"))
SCHEMA = os.environ.get("CRM_SCHEMA", "Timas_MSCRM.dbo")
KABUL_HANDLE = "@m22-kabul-hesabi"


def api(method: str, path: str, body: Any = None, raw: bool = False, data: bytes | None = None) -> tuple[int, Any]:
    headers = {"Cookie": os.environ["M22_COOKIE"], "X-Semantic-Caller": os.environ.get("SEMANTIC_CALLER_TOKEN", ""),
               "Origin": os.environ.get("M22_ORIGIN", BRIDGE)}
    payload = data
    if body is not None:
        payload = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    elif data is not None:
        headers["Content-Type"] = "application/octet-stream"
    req = urllib.request.Request(BRIDGE + path, data=payload, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=900) as r:
            got = r.read()
            return r.status, got if raw else json.loads(got or b"null")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--month", default=date.today().strftime("%Y-%m"), help="takvim sayımı ayı (YYYY-AA)")
    ap.add_argument("--write", action="store_true", help="kabul hesabı/gönderisi/içe aktarması aç, kuralları dene; cleanup siler")
    ap.add_argument("--draft", action="store_true", help="(--write ile) Zeki AI taslağı iste ve denetle")
    ap.add_argument("--allow-mail", action="store_true", help="bildirim alıcısı tanımlıyken de yazma denetimini koş")
    args = ap.parse_args()
    s = SemanticSettings.from_env()
    crm = bsrc.runner(os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json"))
    logo = bsrc.runner(s.connection_file)
    firms = bsrc.firms_by_year(logo)
    store = open_store(s.store_dsn, create=False)
    out: dict[str, Any] = {"checks": []}

    def check(name: str, ok: bool, **detail: Any) -> None:
        out["checks"].append({"ad": name, "ok": bool(ok), **detail})

    st, meta = api("GET", "/api/v1/social/meta")
    if st != 200:
        check("0-meta", False, durum=st, hata=meta)
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
        return 1

    # 1-2-3 ------------------------------------------------------------ fırsatlar
    st, opp = api("GET", "/api/v1/social/opportunities?days=366")
    if st != 200:
        check("fırsatlar", False, durum=st, hata=opp)
        opp = {"ozelGunler": [], "yeniKitaplar": {"items": []}, "backlist": {"items": []}, "basin": {"items": []}}

    rows = crm(f"""
SELECT g.new_name AS ad, kg.new_kitapid AS kitap
FROM {SCHEMA}.new_new_kitap_new_ozelgunlerBase kg
JOIN {SCHEMA}.new_ozelgunlerBase g ON g.new_ozelgunlerId = kg.new_ozelgunlerid
JOIN {SCHEMA}.new_kitapBase k ON k.new_kitapId = kg.new_kitapid
WHERE g.statecode = 0 AND k.statecode = 0""")
    ref: dict[str, set[str]] = {}
    for r in rows:
        ref.setdefault(SS.slug(str(r["ad"] or "").strip()), set()).add(str(r["kitap"]).lower())
    diffs = [{"gun": o["ad"], "ekran": o["kitapSayisi"], "crm": len(ref.get(o["key"], set()))}
             for o in opp["ozelGunler"] if o.get("kaynak") == "crm" and o["kitapSayisi"] != len(ref.get(o["key"], set()))]
    check("1-ozel-gun-kitap-sayisi", not diffs and bool(opp["ozelGunler"]), gun=len(opp["ozelGunler"]), fark=diffs[:30])

    nb = opp["yeniKitaplar"]
    if nb.get("baslangic"):
        lo, hi = date.fromisoformat(nb["baslangic"]), date.fromisoformat(nb["bitis"]) + timedelta(days=1)
        r = crm(f"""
SELECT k.new_StokKodu AS stok FROM {SCHEMA}.new_kitapBase k
WHERE k.statecode = 0 AND k.new_Tip = 1 AND k.new_StokKodu IS NOT NULL
  AND k.new_ilkyayintarihi >= DATEADD(HOUR, -3, '{lo} 00:00:00') AND k.new_ilkyayintarihi < DATEADD(HOUR, -3, '{hi} 00:00:00')""")
        want = {str(x["stok"]).strip() for x in r}
        got = {b["stokKodu"] for b in nb["items"]}
        check("2-yeni-kitaplar", want == got, pencere=[nb["baslangic"], nb["bitis"]], crm=len(want), ekran=len(got),
              eksik=sorted(want - got)[:30], fazla=sorted(got - want)[:30])

    bl = opp["backlist"]
    top = bl.get("items", [])[:10]
    if top and bl.get("pencere"):
        by, bm = (int(v) for v in bl["pencere"]["bas"].split("-"))
        ey, em = (int(v) for v in bl["pencere"]["bit"].split("-"))
        start, end = date(by, bm, 1), date(ey + (em == 12), em % 12 + 1, 1)
        vals = ", ".join("(N'" + x["stokKodu"].replace("'", "''") + "')" for x in top)
        tot: dict[str, float] = {}
        for yy in range(start.year, end.year + 1):
            if yy not in firms:
                continue
            f = firms[yy]
            for row in logo(f"""
SELECT I.CODE AS stok, SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.AMOUNT ELSE -S.AMOUNT END) AS adet
FROM dbo.LG_{f}_01_STLINE S JOIN dbo.LG_{f}_ITEMS I ON I.LOGICALREF = S.STOCKREF
JOIN (VALUES {vals}) AS kod(k) ON kod.k = I.CODE
WHERE S.CANCELLED = 0 AND S.LINETYPE = 0 AND S.INVOICEREF <> 0 AND S.TRCODE IN (2,3,7,8,9)
  AND S.DATE_ >= '{max(start, date(yy, 1, 1))}' AND S.DATE_ < '{min(end, date(yy + 1, 1, 1))}'
GROUP BY I.CODE"""):
                tot[str(row["stok"])] = tot.get(str(row["stok"]), 0.0) + float(row["adet"] or 0)
        d = [{"stok": x["stokKodu"], "ekran": x["adet12"], "logo": round(tot.get(x["stokKodu"], 0.0), 2)} for x in top]
        same = all(abs(x["ekran"] - x["logo"]) < 0.01 for x in d)
        ordered = all(top[i]["adet12"] >= top[i + 1]["adet12"] for i in range(len(top) - 1))
        check("3-backlist-ilk-10", same and ordered, pencere=bl["pencere"], satir=d, sirali=ordered)
    else:
        check("3-backlist-ilk-10", False, hata=bl.get("not") or "liste boş")

    # 4 ---------------------------------------------------------------- takvim sayımı
    y, m = (int(v) for v in args.month.split("-"))
    a_, b_ = date(y, m, 1), date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1)
    st, cal = api("GET", f"/api/v1/social/calendar?frm={a_}&to={b_}")
    with store.engine.connect() as c:
        db = dict(c.execute(sa.text("SELECT status, COUNT(*) FROM semantic_social_posts WHERE tenant_id = :t AND planned_at >= :a "
                                    "AND planned_at <= :b GROUP BY status"),
                            {"t": s.tenant_id, "a": f"{a_} 00:00", "b": f"{b_} 23:59"}).all())
    check("4-takvim-sayimi", st == 200 and cal["counts"] == db, ekran=cal.get("counts") if st == 200 else cal, db=db)

    # 5 ---------------------------------------------------------------- marka hesapları
    st, sug = api("GET", "/api/v1/social/accounts/crm-suggestions")
    r = crm(f"""SELECT new_name AS ad, new_instagramkullaniciadi AS ig FROM {SCHEMA}.new_markaBase
WHERE statecode = 0 AND NULLIF(LTRIM(RTRIM(new_instagramkullaniciadi)), '') IS NOT NULL""")
    want = {str(x["ig"]).strip().lstrip("@") for x in r}
    got = {x["instagram"] for x in (sug.get("items") if st == 200 else []) if x.get("instagram")}
    check("5-marka-instagram", st == 200 and want == got, crm=len(want), ekran=len(got), eksik=sorted(want - got), fazla=sorted(got - want))

    # 6 ---------------------------------------------------------------- yazma (isteğe bağlı)
    state: dict[str, Any] = json.loads(STATE.read_text()) if STATE.exists() else {"accounts": [], "posts": [], "imports": []}
    if args.write and meta["settings"].get("recipientsSet") and not args.allow_mail:
        check("6-yazma", False, hata="SOCIAL_ALERT_RECIPIENTS dolu: onaya gönderme gerçek e-posta atar. Ayarı boşaltın ya da "
                                    "--allow-mail ile bilerek koşun.")
        args.write = False
    if args.write:
        st, acc = api("POST", "/api/v1/social/accounts", {"platform": "instagram", "handle": KABUL_HANDLE, "ad": "Kabul hesabı"})
        if st == 201:
            state["accounts"].append(acc["id"])
            STATE.write_text(json.dumps(state))
            csv_ = (f"Date;Permalink;Reach;Impressions;Likes\n{a_};https://instagram.com/p/m22kabul1;1234;2000;50\n"
                    f"{a_};https://instagram.com/p/m22kabul2;766;900;10\n").encode()
            st, imp = api("POST", f"/api/v1/social/imports?account={acc['id']}&filename=m22-kabul.csv", data=csv_)
            if st == 201:
                state["imports"].append(imp["id"])
                STATE.write_text(json.dumps(state))
                with store.engine.connect() as c:
                    dbsum = c.execute(sa.text("SELECT SUM(reach) FROM semantic_social_metrics WHERE import_id = :i"), {"i": imp["id"]}).scalar()
                check("6a-ice-aktarma-toplami", imp["toplam"]["reach"] == 2000 and float(dbsum or 0) == 2000.0, api=imp["toplam"]["reach"], db=dbsum)
            else:
                check("6a-ice-aktarma", False, durum=st, hata=imp)
            when = (date.today() + timedelta(days=30)).isoformat()
            st, post = api("POST", "/api/v1/social/posts", {"accountId": acc["id"], "plannedAt": when, "text": "Kabul denemesi metni.",
                                                            "kind": "diger"})
            if st == 201:
                state["posts"].append(post["id"])
                STATE.write_text(json.dumps(state))
                st_pkg, _ = api("GET", f"/api/v1/social/posts/{post['id']}/package.zip", raw=True)
                if args.draft:
                    st_d, job = api("POST", f"/api/v1/social/posts/{post['id']}/draft")
                    deadline = time.time() + 300
                    j = None
                    while st_d == 202 and time.time() < deadline:
                        time.sleep(5)
                        _, jobs = api("GET", f"/api/v1/social/posts/{post['id']}/jobs")
                        j = next((x for x in jobs["items"] if x["id"] == job["job"]["id"]), None)
                        if j and j["durum"] in ("bitti", "hata"):
                            break
                    _, full = api("GET", f"/api/v1/social/posts/{post['id']}")
                    opts = ((full.get("draft") or {}).get("secenekler") or []) if isinstance(full, dict) else []
                    text = json.dumps(opts, ensure_ascii=False)
                    check("7c-zeki-taslak", bool(j) and j["durum"] == "bitti" and not G.has_tech_name(text), is_=j, secenek=len(opts))
                api("POST", f"/api/v1/social/posts/{post['id']}/submit")
                st409, msg = api("POST", f"/api/v1/social/posts/{post['id']}/approve", {})
                check("6b-gonderen-onaylayamaz-ve-paket", st409 in (403, 409) and st_pkg == 409, onay=st409, paket=st_pkg, mesaj=str(msg)[:200])
                api("POST", f"/api/v1/social/posts/{post['id']}/withdraw")
            else:
                check("6b-gonderi", False, durum=st, hata=post)
        else:
            check("6-hesap", False, durum=st, hata=acc)

    # 7 ---------------------------------------------------------------- teknoloji adı ve web bayrağı
    blob = json.dumps({"meta": meta, "opp": opp, "cal": cal if isinstance(cal, dict) else {}}, ensure_ascii=False)
    check("7a-teknoloji-adi", not G.has_tech_name(blob))
    web = str(os.environ.get("WEB_WATCH_ENABLED", "")).strip() or ("1" if meta.get("webWatch") else "0")
    check("7b-web-bayragi", meta.get("webWatch") or not opp["basin"]["items"], webWatch=meta.get("webWatch"), env=web,
          basin=len(opp["basin"]["items"]))

    out["ozet"] = {"gecti": sum(1 for c in out["checks"] if c["ok"]), "kaldi": sum(1 for c in out["checks"] if not c["ok"])}
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0 if out["ozet"]["kaldi"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
