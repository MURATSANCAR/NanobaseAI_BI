"""M20 Basın, medya ve halkla ilişkiler — kabul (test sunucusunda, gerçek CRM .28, çalışan köprüye karşı).

Koşum (test sunucusu, köprünün env'i ile; Mac'te koşulmaz):

    cd <köprü kaynağı>/backend && set -a && . /etc/nanobase/semantic-bridge.env && set +a \
      && M20_COOKIE='timas_session=…' python3 ../scripts/acceptance/m20/accept.py [--ay 2026-09] [--kitap <guid>] \
         [--stok <stok kodu>] [--write] [--run-due] > m20-kabul.json

`M20_COOKIE`: `timasai` hesabının kısa ömürlü (15 dk) portal oturumu (kullanıcı belleği «test-login-as-timasai»);
kabul bitince oturum satırı giriş servisinde silinir. Yeni kullanıcı adı uydurulmaz. Sayfa açıkça verilen bir sayfadır
(`sayfa:basin-iliskileri`); timasai yönetici olduğu için açılır.

Denetimler — ekrana giden sonuç, bağımsız doğrudan SQL referansıyla karşılaştırılır (tavan yok, bütün sayfalar okunur):
  1. CRM arşivi: `GET /coverage?kaynak=crm-arsiv` toplamı = `COUNT(*) new_haberlerBase WHERE statecode = 0`.
  2. Kitap başına arşiv: seçilen kitabın (`--kitap`, yoksa en çok haber bağı olan kitap) `GET /books/{id}` arşivi =
     N:N tablo ∪ haberin «Kitap» alanı, etkin haber, DISTINCT. İki yolun ayrı sayıları ve farkı raporlanır.
  3. Medya kişisi havuzu: `GET /contacts?kaynak=crm` toplamı = etkin kişi ve (mecra dolu ∪ haberi yapan ∪ basında
     görüşülen [∪ PR_CRM_MEDIA_ROLES]). Ölçüm: «Haberi Yapan Kişi» alanındaki kimliklerin kaçı ContactBase'de, kaçı
     SystemUserBase'de (hangisine baktığı bu turda ölçülür, günlüğe yazılır).
  4. Tanıtım gönderimi: `--stok` (yoksa tip 12 siparişte en çok geçen stok kodu) için `GET /books/{id}` promoTotal =
     `SUM(new_adet)` tip 12 sipariş satırları.
  5. Ayın kitapları: `GET /home?ay=` kitap kimliği kümesi = etkin «Kitap» kartı, ilk baskı tarihi o ayda (İstanbul günü).
  6. Portal kayıtları: `GET /report` (son 90 gün) gönderim toplamı ve durum dağılımı = `semantic_pr_sends` doğrudan SQL;
     kayıtlı yansıma toplamı = `semantic_pr_coverage` doğrudan SQL.
  7. VM davranışı ve teknoloji adı: `WEB_WATCH_ENABLED` kapalıyken `POST /coverage/preview` web'e gitmez («kapalı»);
     (`--run-due`) run-due aday toplamayı «atlandı» der. `src/canvas/pr` ve köprünün M20 metinlerinde teknoloji adı 0.
  8. (--write) Onay kuralı: kabul dosyası açılır, bülten yazılır, onaya gönderilir; aynı kişi onaylayınca 409; geri
     çekilir, kapatılır. Kimlikler durum dosyasına yazılır, `cleanup.py` siler (dosya, geçmiş, iş, değişiklik kaydı).
Çıktı: JSON; `ok` her denetim için; sonunda özet.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))

import sqlalchemy as sa  # noqa: E402

from semantic_bridge import budget_sources as bsrc  # noqa: E402
from semantic_bridge.marketing import guard as G  # noqa: E402
from semantic_layer.config import SemanticSettings  # noqa: E402
from semantic_layer.store.catalog_store import open_store  # noqa: E402

BRIDGE = os.environ.get("M20_BRIDGE", "http://127.0.0.1:8795")
STATE = Path(os.environ.get("M20_STATE", "m20-kabul-state.json"))
SCHEMA = os.environ.get("CRM_SCHEMA", "Timas_MSCRM.dbo")


def api(method: str, path: str, body: Any = None) -> tuple[int, Any]:
    headers = {"Cookie": os.environ["M20_COOKIE"], "X-Semantic-Caller": os.environ.get("SEMANTIC_CALLER_TOKEN", "")}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BRIDGE + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def all_pages(path: str) -> tuple[list[dict[str, Any]], Any]:
    items: list[dict[str, Any]] = []
    page = 0
    sep = "&" if "?" in path else "?"
    while True:
        st, body = api("GET", f"{path}{sep}page={page}")
        if st != 200:
            return items, body
        items += body["items"]
        if (page + 1) * body["pageSize"] >= body["total"] or not body["items"]:
            return items, None
        page += 1


def utc(d: date) -> str:
    return (datetime(d.year, d.month, d.day) - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ay", default=date.today().strftime("%Y-%m"))
    ap.add_argument("--kitap", default="", help="arşivi denetlenecek kitabın CRM kimliği (boşsa en çok haberi olan)")
    ap.add_argument("--stok", default="", help="tanıtım gönderimi denetlenecek stok kodu (boşsa tip 12'de en çok geçen)")
    ap.add_argument("--write", action="store_true", help="kabul dosyası aç, onay kuralını dene, kapat (cleanup.py siler)")
    ap.add_argument("--run-due", action="store_true", help="run-due'yu da koştur (hatırlatma/özet e-postası gidebilir)")
    args = ap.parse_args()
    s = SemanticSettings.from_env()
    crm = bsrc.runner(os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json"))
    store = open_store(s.store_dsn, create=False)
    out: dict[str, Any] = {"checks": [], "calisma": {"koprü": BRIDGE, "sema": SCHEMA, "zaman": datetime.now().isoformat()}}

    def check(name: str, ok: bool, **detail: Any) -> None:
        out["checks"].append({"ad": name, "ok": bool(ok), **detail})

    p = SCHEMA + "."

    # 1 ---------------------------------------------------------------- CRM arşivi
    ref = crm(f"SELECT COUNT(*) AS n FROM {p}new_haberlerBase WHERE statecode = 0")[0]["n"]
    st, body = api("GET", "/api/v1/pr/coverage?kaynak=crm-arsiv&page=0")
    check("1-crm-arsiv", st == 200 and body["total"] == ref, crm=ref, ekran=body["total"] if st == 200 else body)

    # 2 ---------------------------------------------------------------- kitap başına arşiv
    union = (f"SELECT l.new_haberlerid AS hid, l.new_kitapid AS kid, 'nn' AS yol FROM {p}new_new_haberler_new_kitapBase l "
             f"UNION ALL SELECT h.new_haberlerId, h.new_Kitapid, 'alan' FROM {p}new_haberlerBase h WHERE h.new_Kitapid IS NOT NULL")
    kitap = args.kitap
    if not kitap:
        top = crm(f"SELECT TOP 1 x.kid, COUNT(DISTINCT x.hid) AS n FROM ({union}) x JOIN {p}new_haberlerBase h "
                  f"ON h.new_haberlerId = x.hid AND h.statecode = 0 GROUP BY x.kid ORDER BY 2 DESC")
        kitap = str(top[0]["kid"]).strip("{}").lower() if top else ""
    if kitap:
        k = kitap.replace("'", "")
        r = crm(f"""
SELECT COUNT(DISTINCT x.hid) AS toplam,
       COUNT(DISTINCT CASE WHEN x.yol = 'nn' THEN x.hid END) AS nn,
       COUNT(DISTINCT CASE WHEN x.yol = 'alan' THEN x.hid END) AS alan
FROM ({union}) x JOIN {p}new_haberlerBase h ON h.new_haberlerId = x.hid AND h.statecode = 0
WHERE x.kid = '{k}'""")[0]
        st, body = api("GET", f"/api/v1/pr/books/{k}")
        n = len(body["archive"]) if st == 200 else None
        check("2-kitap-arsivi", n == r["toplam"], kitap=k, crm=r, ekran=n, fark_nn_alan=(r["toplam"] - r["nn"], r["toplam"] - r["alan"]))
    else:
        check("2-kitap-arsivi", False, hata="Haber bağı olan kitap yok")

    # 3 ---------------------------------------------------------------- medya kişisi havuzu
    roles = [x.strip() for x in os.environ.get("PR_CRM_MEDIA_ROLES", "").split(",") if x.strip()]
    role_sql = ""
    if roles:
        names = ", ".join("N'" + x.replace("'", "''") + "'" for x in roles)
        role_sql = (f" UNION SELECT cr.contactid FROM {p}new_contact_new_kisiroluBase cr JOIN {p}new_kisiroluBase r "
                    f"ON r.new_kisiroluId = cr.new_kisiroluid WHERE r.new_name IN ({names})")
    pool = crm(f"""
SELECT COUNT(*) AS n FROM {p}ContactBase c WHERE c.StateCode = 0 AND c.ContactId IN (
  SELECT ContactId FROM {p}ContactBase WHERE NULLIF(LTRIM(RTRIM(new_ilgilioldugumecra)), '') IS NOT NULL
  UNION SELECT new_HaberinYazari FROM {p}new_haberlerBase WHERE new_HaberinYazari IS NOT NULL
  UNION SELECT new_basindagorusulenkisi FROM {p}new_haberlerBase WHERE new_basindagorusulenkisi IS NOT NULL{role_sql})""")[0]["n"]
    who = crm(f"""
SELECT COUNT(DISTINCT h.new_HaberinYazari) AS toplam,
       COUNT(DISTINCT CASE WHEN c.ContactId IS NOT NULL THEN h.new_HaberinYazari END) AS kisi,
       COUNT(DISTINCT CASE WHEN u.SystemUserId IS NOT NULL THEN h.new_HaberinYazari END) AS kullanici
FROM {p}new_haberlerBase h LEFT JOIN {p}ContactBase c ON c.ContactId = h.new_HaberinYazari
LEFT JOIN {p}SystemUserBase u ON u.SystemUserId = h.new_HaberinYazari WHERE h.new_HaberinYazari IS NOT NULL""")[0]
    st, body = api("GET", "/api/v1/pr/contacts?kaynak=crm&page=0")
    check("3-medya-kisileri", st == 200 and body["total"] == pool, crm=pool, ekran=body["total"] if st == 200 else body,
          olcum_haberi_yapan=who)

    # 4 ---------------------------------------------------------------- tanıtım gönderimi
    stok = args.stok
    if not stok:
        top = crm(f"SELECT TOP 1 ss.new_StokKodu AS stok FROM {p}new_siparissatiriBase ss JOIN {p}new_siparisBase s "
                  f"ON s.new_siparisId = ss.new_siparisid WHERE s.new_siparistipi = 12 AND ss.new_StokKodu IS NOT NULL "
                  f"GROUP BY ss.new_StokKodu ORDER BY SUM(ss.new_adet) DESC")
        stok = str(top[0]["stok"]).strip() if top else ""
    if stok:
        sc = stok.replace("'", "''")
        adet = crm(f"SELECT SUM(ss.new_adet) AS n FROM {p}new_siparissatiriBase ss JOIN {p}new_siparisBase s "
                   f"ON s.new_siparisId = ss.new_siparisid WHERE s.new_siparistipi = 12 AND ss.new_StokKodu = N'{sc}'")[0]["n"] or 0
        kid = crm(f"SELECT TOP 1 new_kitapId AS id FROM {p}new_kitapBase WHERE new_StokKodu = N'{sc}' AND statecode = 0")
        if kid:
            st, body = api("GET", f"/api/v1/pr/books/{str(kid[0]['id']).strip('{}').lower()}")
            ekran = body.get("promoTotal") if st == 200 else body
            check("4-tanitim-gonderimi", st == 200 and abs(float(ekran or 0) - float(adet)) < 0.001, stok=stok, crm=adet, ekran=ekran)
        else:
            check("4-tanitim-gonderimi", False, stok=stok, hata="Stok kodunun etkin kitap kartı yok")
    else:
        check("4-tanitim-gonderimi", True, atlandi=True, not_="Tip 12 sipariş yok")

    # 5 ---------------------------------------------------------------- ayın kitapları
    y, m = int(args.ay[:4]), int(args.ay[5:7])
    first = date(y, m, 1)
    nxt = date(y + (m == 12), m % 12 + 1, 1)
    ref_ids = {str(r["id"]).strip("{}").lower() for r in crm(f"""
SELECT new_kitapId AS id FROM {p}new_kitapBase WHERE statecode = 0 AND new_Tip = 1
  AND new_ilkyayintarihi >= '{utc(first)}' AND new_ilkyayintarihi < '{utc(nxt)}'""")}
    st, body = api("GET", f"/api/v1/pr/home?ay={args.ay}&yenile=true")
    got = {b["kitapId"] for b in body["books"]} if st == 200 else set()
    check("5-ayin-kitaplari", st == 200 and got == ref_ids, crm=len(ref_ids), ekran=len(got),
          eksik=sorted(ref_ids - got), fazla=sorted(got - ref_ids))

    # 6 ---------------------------------------------------------------- portal kayıtları
    to = date.today()
    frm = to - timedelta(days=90)
    lo = datetime(frm.year, frm.month, frm.day, tzinfo=timezone(timedelta(hours=3)))
    hi = datetime(to.year, to.month, to.day, tzinfo=timezone(timedelta(hours=3))) + timedelta(days=1)
    with store.engine.connect() as c:
        tenant = s.tenant_id
        rows = c.execute(sa.text("SELECT status, COUNT(*) FROM semantic_pr_sends WHERE tenant_id = :t AND sent_at >= :lo "
                                 "AND sent_at < :hi GROUP BY status"), {"t": tenant, "lo": lo, "hi": hi}).all()
        cov = c.execute(sa.text("SELECT COUNT(*) FROM semantic_pr_coverage WHERE tenant_id = :t AND state = 'kayitli' AND ("
                                "(published_at IS NOT NULL AND published_at BETWEEN :f AND :e) OR "
                                "(published_at IS NULL AND created_at >= :lo AND created_at < :hi))"),
                        {"t": tenant, "f": frm.isoformat(), "e": to.isoformat(), "lo": lo, "hi": hi}).scalar()
    ref_status = {r[0]: int(r[1]) for r in rows}
    st, body = api("GET", f"/api/v1/pr/report?frm={frm}&to={to}")
    ok = st == 200 and body["sends"]["byStatus"] == ref_status and body["coverage"]["total"] == int(cov or 0)
    check("6-portal-kayitlari", ok, db={"gonderim": ref_status, "yansima": cov},
          ekran={"gonderim": body["sends"]["byStatus"], "yansima": body["coverage"]["total"]} if st == 200 else body)

    # 7 ---------------------------------------------------------------- VM davranışı ve teknoloji adı
    st, meta = api("GET", "/api/v1/pr/meta")
    web = meta["settings"]["webWatch"] if st == 200 else None
    if web is False:
        st2, pv = api("POST", "/api/v1/pr/coverage/preview", {"url": "https://example.org/m20-kabul"})
        check("7a-web-kapali", st2 == 200 and pv.get("disabled") is True, ekran=pv)
        if args.run_due:
            st3, rd = api("POST", "/api/v1/pr/run-due")
            check("7b-run-due-atlar", st3 == 200 and "atlandi" in (rd.get("web") or {}), ekran=rd)
    else:
        check("7a-web-kapali", True, atlandi=True, not_="Bu ortamda tarama açık (test sunucusu); VM'de tekrar koşulur.")
    hits = []
    for f in list((ROOT / "src" / "canvas" / "pr").glob("*.ts*")) + [ROOT / "backend" / "semantic_bridge" / n
                                                                  for n in ("pr.py", "pr_api.py", "pr_export.py")]:
        for lit in re.findall(r"'([^'\n]{3,})'|\"([^\"\n]{3,})\"|>([^<>{}\n]{3,})<", f.read_text(encoding="utf-8")):
            t = next(x for x in lit if x)
            if G.has_tech_name(t) and "TECH_NAMES" not in t:
                hits.append({"dosya": f.name, "metin": t[:120]})
    # pr.py'deki model istemi «teknoloji adı yazma» der; o cümle ekrana gitmez.
    hits = [h for h in hits if "teknoloji, model ya da yazılım adı" not in h["metin"]]
    check("7c-teknoloji-adi", not hits, bulunan=hits)

    # 8 ---------------------------------------------------------------- (--write) onay kuralı
    if args.write:
        state = json.loads(STATE.read_text()) if STATE.exists() else {"kits": []}
        candidate = sorted(ref_ids) or ([kitap] if kitap else [])
        chosen = None
        for bid in candidate:
            st, b = api("GET", f"/api/v1/pr/books/{bid}")
            if st == 200 and not b.get("openKit"):
                chosen = bid
                break
        if chosen is None:
            check("8-onay-kurali", False, hata="Açık PR dosyası olmayan kitap bulunamadı")
        else:
            st, kit = api("POST", "/api/v1/pr/kits", {"crmBookId": chosen})
            if st != 201:
                check("8-onay-kurali", False, hata=kit)
            else:
                state["kits"].append(kit["id"])
                STATE.write_text(json.dumps(state))
                steps = {"yaz": api("PATCH", f"/api/v1/pr/kits/{kit['id']}", {"releaseNational": "M20 kabul metni (silinecek)"})[0],
                         "gonder": api("POST", f"/api/v1/pr/kits/{kit['id']}/submit")[0],
                         "ayni-kisi-onay": api("POST", f"/api/v1/pr/kits/{kit['id']}/approve", {})[0],
                         "geri-cek": api("POST", f"/api/v1/pr/kits/{kit['id']}/withdraw")[0],
                         "kapat": api("POST", f"/api/v1/pr/kits/{kit['id']}/close")[0]}
                check("8-onay-kurali", steps == {"yaz": 200, "gonder": 200, "ayni-kisi-onay": 409, "geri-cek": 200, "kapat": 200},
                      kit=kit["id"], adimlar=steps)

    ok = sum(1 for c in out["checks"] if c["ok"])
    out["ozet"] = {"gecen": ok, "kalan": len(out["checks"]) - ok, "toplam": len(out["checks"])}
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0 if ok == len(out["checks"]) else 1


if __name__ == "__main__":
    sys.exit(main())
