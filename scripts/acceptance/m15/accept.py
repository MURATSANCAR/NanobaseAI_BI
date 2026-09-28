"""M15 Yeni kitap pazarlama planı — kabul (test sunucusunda, gerçek CRM .28 + Logo .155, çalışan köprüye karşı).

Koşum (test sunucusu, köprünün env'i ile; Mac'te koşulmaz):

    cd <köprü kaynağı>/backend && set -a && . /etc/nanobase/semantic-bridge.env && set +a \
      && M15_COOKIE='timas_session=…' python3 ../scripts/acceptance/m15/accept.py --stok <yeni kitap stok kodu> \
         [--author-year 2025] [--write] > m15-kabul.json

`M15_COOKIE`: `timasai` hesabının kısa ömürlü (15 dk) portal oturumu (kullanıcı belleği «test-login-as-timasai»);
kabul bitince oturum satırı silinir. Yeni kullanıcı adı uydurulmaz.

Denetimler — uygulamanın ekrana verdiği sonuç, bağımsız doğrudan SQL referansıyla karşılaştırılır:
  1. Liste kapsamı: CRM'de yayın günü (kitap kartı ilk baskı tarihi) bugün..bugün+120 olan etkin «Kitap» kartları =
     `GET /new-books` satırlarından kaynağı kitap kartı olanlar (stok kodu kümesi birebir; tavan yok).
  2. Yazar geçmişi: karnedeki `--author-year` yılı yazar toplamı = Logo `STLINE` faturalı satır (TRCODE 7/8/9 − 2/3,
     LINENET) bu kitap kodlarıyla (kuruşu kuruşuna, adet birebir).
  3. Emsal: CRM emsal bağı (`new_new_kitap_new_emsalkitap3Base`, kitap → emsal) = karnede «CRM emsali» etiketli satırlar
     (küme birebir); ilk 12 ay net adedi Logo STLINE ile karşılaştırılır (M10 satış görünümüyle fark raporlanır,
     `--emsal-tol` payı aşan satır başarısız).
  4. Hedef: `semantic_budget_approved_targets` (yayın yılı, stok) hedef adet/ciro = karnedeki hedef.
  5. CRM ön değerleri: proje kartı bütçe/öncelik alanları = karnedeki «CRM'deki bütçe»; kitap kartı föy/arka kapak/
     basın bülteni metni = karnedeki metin (karakter karakter, satır sonu sadeleştirmesi dışında).
  6. (--write) Bütçe toplamı ve onay: kabul planı açılır, satır yazılır; `SUM(tutar)` = API toplamı = CSV toplamı;
     gönderen onaylayınca 409; plan geri çekilip silinir. Kimlikler `m15-kabul-state.json`'a yazılır, `cleanup.py` siler.
  7. Teknoloji adı: karne, plan ve PDF metninde model/ürün adı taraması 0.
Çıktı: JSON; `ok` her denetim için; sonunda özet.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))

import sqlalchemy as sa  # noqa: E402

from semantic_bridge import budget_sources as bsrc  # noqa: E402
from semantic_bridge.marketing import guard as G  # noqa: E402
from semantic_layer.config import SemanticSettings  # noqa: E402
from semantic_layer.store.catalog_store import open_store  # noqa: E402

BRIDGE = os.environ.get("M15_BRIDGE", "http://127.0.0.1:8795")
STATE = Path(os.environ.get("M15_STATE", "m15-kabul-state.json"))
SCHEMA = os.environ.get("CRM_SCHEMA", "Timas_MSCRM.dbo")


def api(method: str, path: str, body: Any = None, raw: bool = False) -> tuple[int, Any]:
    headers = {"Cookie": os.environ["M15_COOKIE"], "X-Semantic-Caller": os.environ.get("SEMANTIC_CALLER_TOKEN", "")}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BRIDGE + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            payload = r.read()
            return r.status, payload if raw else json.loads(payload or b"null")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def near(a: Any, b: Any, tol: float = 0.005) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return abs(float(a) - float(b)) <= tol


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stok", required=True, help="karnesi denetlenecek yeni kitabın stok kodu")
    ap.add_argument("--author-year", type=int, default=date.today().year - 1)
    ap.add_argument("--emsal-tol", type=float, default=0.02, help="emsal ilk 12 ay: M10 görünümü ile STLINE arasındaki pay")
    ap.add_argument("--write", action="store_true", help="kabul planı aç, onay kuralını dene, sonra sil")
    ap.add_argument("--allow-mail", action="store_true", help="bildirim alıcısı tanımlıyken de yazma denetimini koş")
    args = ap.parse_args()
    s = SemanticSettings.from_env()
    crm = bsrc.runner(os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json"))
    logo = bsrc.runner(s.connection_file)
    firms = bsrc.firms_by_year(logo)
    store = open_store(s.store_dsn, create=False)
    out: dict[str, Any] = {"stok": args.stok, "checks": []}

    def check(name: str, ok: bool, **detail: Any) -> None:
        out["checks"].append({"ad": name, "ok": bool(ok), **detail})

    code = args.stok.replace("'", "''")

    # 1 ---------------------------------------------------------------- liste kapsamı
    today = date.today()
    to = today + timedelta(days=120)
    lo = f"{today.isoformat()} 00:00:00"
    ref = crm(f"""
SELECT k.new_StokKodu AS stok FROM {SCHEMA}.new_kitapBase k
WHERE k.statecode = 0 AND k.new_Tip = 1 AND k.new_StokKodu IS NOT NULL
  AND k.new_ilkyayintarihi >= DATEADD(HOUR, -3, '{lo}') AND k.new_ilkyayintarihi < DATEADD(HOUR, -3, '{(to + timedelta(days=1)).isoformat()} 00:00:00')""")
    want = {str(r["stok"]).strip() for r in ref}
    got: set[str] = set()
    page = 0
    while True:
        st, body = api("GET", f"/api/v1/marketing/new-books?frm={today}&to={to}&page={page}&yenile=1")
        if st != 200:
            check("1-liste", False, hata=body)
            break
        got |= {r["stokKodu"] for r in body["items"] if r["yayinKaynagi"] == "crm-kitap"}
        if (page + 1) * body["pageSize"] >= body["total"]:
            break
        page += 1
    check("1-liste", want == got, crm=len(want), ekran=len(got), eksik=sorted(want - got)[:50], fazla=sorted(got - want)[:50])

    # karne (önbellekte yoksa kabulün oluşturduğu satır cleanup.py ile silinir)
    state: dict[str, Any] = json.loads(STATE.read_text()) if STATE.exists() else {"plans": [], "cards": []}
    with store.engine.connect() as c:
        try:
            had_card = c.execute(sa.text("SELECT 1 FROM semantic_mkt_book_cards WHERE stok_kodu = :k"), {"k": args.stok}).first()
        except Exception:  # noqa: BLE001 — tablo ilk kullanımda kurulur
            had_card = None
    if not had_card and args.stok not in state["cards"]:
        state["cards"].append(args.stok)
        STATE.write_text(json.dumps(state))
    st, card = api("GET", f"/api/v1/marketing/books/{args.stok}/card?yenile=1")
    if st != 200:
        check("karne", False, hata=card)
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
        return 1

    # 2 ---------------------------------------------------------------- yazar geçmişi (Logo STLINE)
    y = args.author_year
    codes = [b["stokKodu"] for b in card["yazar"]["items"]]
    screen = next((x for x in card["yazar"]["yillar"] if x["yil"] == y), None)
    if codes and y in firms:
        vals = ", ".join("(N'" + c.replace("'", "''") + "')" for c in codes)
        f = firms[y]
        r = logo(f"""
SELECT SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.AMOUNT ELSE -S.AMOUNT END) AS adet,
       SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.LINENET ELSE -S.LINENET END) AS ciro
FROM dbo.LG_{f}_01_STLINE S JOIN dbo.LG_{f}_ITEMS I ON I.LOGICALREF = S.STOCKREF
JOIN (VALUES {vals}) AS kod(k) ON kod.k = I.CODE
WHERE S.CANCELLED = 0 AND S.LINETYPE = 0 AND S.INVOICEREF <> 0 AND S.TRCODE IN (2,3,7,8,9)
  AND S.DATE_ >= '{y}-01-01' AND S.DATE_ < '{y + 1}-01-01'""")[0]
        check("2-yazar", screen is not None and near(screen["adet"], r["adet"] or 0) and near(screen["ciro"], r["ciro"] or 0, 0.01),
              yil=y, kitap=len(codes), ekran=screen, logo={"adet": r["adet"], "ciro": r["ciro"]})
    else:
        check("2-yazar", True, not_=f"yazarın başka kitabı yok ya da {y} Logo'da yok — başka --stok ile tekrarlayın", atlandi=True)

    # 3 ---------------------------------------------------------------- emsal (CRM bağı + ilk 12 ay)
    em = crm(f"""
SELECT k2.new_StokKodu AS emsal FROM {SCHEMA}.new_new_kitap_new_emsalkitap3Base e
JOIN {SCHEMA}.new_kitapBase k1 ON k1.new_kitapId = e.new_kitapidOne
JOIN {SCHEMA}.new_kitapBase k2 ON k2.new_kitapId = e.new_kitapidTwo
WHERE k1.new_StokKodu = N'{code}' AND k2.new_StokKodu IS NOT NULL AND k2.new_StokKodu <> k1.new_StokKodu""")
    crm_em = {str(r["emsal"]).strip() for r in em}
    items = (card.get("emsal") or {}).get("items") or []
    scr_em = {x["stokKodu"] for x in items if "CRM emsali" in x["kaynak"]}
    if (card.get("emsal") or {}).get("hazir"):
        check("3a-emsal-kume", crm_em == scr_em, crm=sorted(crm_em), ekran=sorted(scr_em))
        diffs = []
        for x in items:
            if x.get("ilk12") is None or not x.get("lansman"):
                continue
            ly, lm = (int(v) for v in x["lansman"].split("-"))
            start = date(ly, lm, 1)
            end = date(ly + (lm + 11) // 12, (lm + 11) % 12 + 1, 1)
            total = 0.0
            for yy in range(start.year, end.year + 1):
                if yy not in firms:
                    continue
                f = firms[yy]
                r = logo(f"""
SELECT SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.AMOUNT ELSE -S.AMOUNT END) AS adet
FROM dbo.LG_{f}_01_STLINE S JOIN dbo.LG_{f}_ITEMS I ON I.LOGICALREF = S.STOCKREF
WHERE S.CANCELLED = 0 AND S.LINETYPE = 0 AND S.INVOICEREF <> 0 AND S.TRCODE IN (2,3,7,8,9) AND I.CODE = N'{x['stokKodu'].replace("'", "''")}'
  AND S.DATE_ >= '{max(start, date(yy, 1, 1))}' AND S.DATE_ < '{min(end, date(yy + 1, 1, 1))}'""")[0]
                total += float(r["adet"] or 0)
            rel = abs(total - x["ilk12"]) / max(1.0, total)
            diffs.append({"stok": x["stokKodu"], "ekran": x["ilk12"], "stline": round(total), "fark": round(rel, 4)})
        check("3b-emsal-12ay", all(d["fark"] <= args.emsal_tol for d in diffs), satir=diffs)
    else:
        check("3-emsal", False, hata="İlk baskı tahmini veri kümesi hazır değil")

    # 4 ---------------------------------------------------------------- hedef
    h = card.get("hedef") or {}
    if h.get("year"):
        with store.engine.connect() as c:
            row = c.execute(sa.text("SELECT hedef_adet, hedef_ciro FROM semantic_budget_approved_targets "
                                    "WHERE year = :y AND stok_kodu = :k"), {"y": h["year"], "k": args.stok}).first()
        ok = (row is None and h.get("adet") is None) or (row is not None and near(row[0], h.get("adet")) and near(row[1], h.get("ciro"), 0.01))
        check("4-hedef", ok, ekran={k: h.get(k) for k in ("adet", "ciro", "planId")}, db=list(row) if row else None)
    else:
        check("4-hedef", True, atlandi=True, not_="kitabın yayın tarihi yok")

    # 5 ---------------------------------------------------------------- CRM ön değerleri ve metinler
    pj = crm(f"""
SELECT j.new_toplampazarlamabutcesi AS toplam, j.new_toplampazarlamabutcesi_kurulsonucu AS kurul, j.new_basinbutcesi AS basin,
       j.new_kampanyabutcesi AS kampanya, j.new_pazarlamaonceligi AS oncelik,
       k.new_TantmFyMetni AS foy, k.new_ozet AS ozet, k.new_BasnBlteni AS bulten
FROM {SCHEMA}.new_kitapBase k LEFT JOIN {SCHEMA}.new_projeBase j ON j.new_projeId = k.new_projekarti
WHERE k.statecode = 0 AND k.new_StokKodu = N'{code}'""")
    if pj:
        r = pj[0]
        cb = card.get("crmButce") or {}
        nums = all(near(r[a], cb.get(b)) for a, b in (("toplam", "toplam"), ("kurul", "toplamKurul"), ("basin", "basin"),
                                                    ("kampanya", "kampanya"), ("oncelik", "oncelik")))
        texts = {m["alan"]: m["metin"] for m in card.get("metinler") or []}
        norm = lambda v: "\n".join(" ".join(x.split()) for x in re.sub(r"<[^>]+>", "", str(v or "")).splitlines()).strip()  # noqa: E731
        tx = all(norm(r[a]) == norm(texts.get(b)) for a, b in (("foy", "new_TantmFyMetni"), ("ozet", "new_ozet"), ("bulten", "new_BasnBlteni")))
        check("5-crm-on-deger", nums and tx, butce=nums, metin=tx)

    # 6 ---------------------------------------------------------------- yazma (isteğe bağlı): toplam + onay
    if args.write:
        from semantic_bridge import admin as admin_mod

        admin_mod.ensure(store.engine)
        if (admin_mod.conf("MARKETING_ALERT_RECIPIENTS") or "").strip() and not args.allow_mail:
            check("6-yazma", False, hata="MARKETING_ALERT_RECIPIENTS dolu: onaya gönderme gerçek e-posta atar. Ayarı boşaltın "
                                        "ya da --allow-mail ile bilerek koşun.")
            args.write = False
    if args.write:
        st, plan = api("POST", "/api/v1/marketing/plans", {"kind": "yeni", "stokKodu": args.stok})
        if st == 201:
            state["plans"].append(plan["id"])
            STATE.write_text(json.dumps(state))
            st, p2 = api("PUT", f"/api/v1/marketing/plans/{plan['id']}/lines",
                         {"items": [{"kanal": "basin", "tutar": 1234.56}, {"kanal": "dijital", "tutar": 765.44}]})
            with store.engine.connect() as c:
                dbsum = c.execute(sa.text("SELECT SUM(tutar) FROM semantic_mkt_plan_lines WHERE plan_id = :p"), {"p": plan["id"]}).scalar()
            _, csv_bytes = api("GET", f"/api/v1/marketing/plans/{plan['id']}/export.csv", raw=True)
            csv_total = next((ln.split(";")[3] for ln in csv_bytes.decode("utf-8-sig").splitlines() if ln.startswith("Toplam;")), None)
            check("6a-butce-toplami", near(dbsum, 2000) and near(p2.get("butceToplam"), 2000) and csv_total == "2000,00",
                  db=dbsum, ekran=p2.get("butceToplam"), csv=csv_total)
            api("POST", f"/api/v1/marketing/plans/{plan['id']}/submit")
            st409, msg = api("POST", f"/api/v1/marketing/plans/{plan['id']}/approve", {})
            check("6b-gonderen-onaylayamaz", st409 in (403, 409), durum=st409, mesaj=str(msg)[:200])
            st, pdf = api("GET", f"/api/v1/marketing/plans/{plan['id']}/export.pdf", raw=True)
            check("7b-pdf-teknoloji-adi", st == 200 and not G.has_tech_name(pdf.decode("latin-1", "ignore")), durum=st)
            api("POST", f"/api/v1/marketing/plans/{plan['id']}/withdraw")
            st, _ = api("DELETE", f"/api/v1/marketing/plans/{plan['id']}")
            check("6c-plan-silindi", st == 200, durum=st)
        else:
            check("6-plan-ac", False, durum=st, hata=plan)

    # 7 ---------------------------------------------------------------- teknoloji adı (karne)
    check("7a-karne-teknoloji-adi", not G.has_tech_name(json.dumps(card, ensure_ascii=False)))

    out["ozet"] = {"gecti": sum(1 for c in out["checks"] if c["ok"]), "kaldi": sum(1 for c in out["checks"] if not c["ok"])}
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0 if out["ozet"]["kaldi"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
