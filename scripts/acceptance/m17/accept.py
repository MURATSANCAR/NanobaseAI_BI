"""M17 Backlist — kabul (test sunucusunda, gerçek Logo .25 + CRM .28, çalışan köprüye karşı).

Koşum (test sunucusu, köprünün env'i ile; Mac'te koşulmaz):

    cd <köprü kaynağı>/backend && set -a && . /etc/nanobase/semantic-bridge.env && set +a \
      && M17_COOKIE='timas_session=…' python3 ../scripts/acceptance/m17/accept.py [--stok K1,K2,…] [--write] > m17-kabul.json

`M17_COOKIE`: `timasai` hesabının kısa ömürlü (15 dk) portal oturumu (kullanıcı belleği «test-login-as-timasai»);
kabul bitince oturum satırı silinir. Önce liste kurulmuş olmalı (`run.sh` `BUILD=1` ile gece koşusunu tetikler).

Denetimler — ekranın/uçların verdiği sonuç, bağımsız doğrudan SQL referansıyla karşılaştırılır:
  1. Küme: `GET /api/v1/budget/targets?year=Y&segment=backlist` kodları (157 hariç) = `semantic_mkt_backlist` kodları
     (küme birebir; fark varsa listelenir). Onaylı plan yoksa atlanır ve yedek tanım yazılır.
  2. Eğilim: örnek kitaplarda Logo `STLINE` (faturalı, TRCODE 7/8/9 − 2/3, iptal ve malzeme dışı satır hariç) son 12 ve
     önceki 12 **tam ay** net adedi (yıl firmaları ayrı ayrı) = `adet_son12` / `adet_onceki12`.
  3. Stok: Baskı Öneri'nin `logo_depo_stok.sql` sorgusu (EOS_DEPO_STOK_KONTROL_211, 157 hariç) = `stok`.
  4. Tahmin: `sum(read_forecast()['p50'][kod][:12])` = `tahmin12_p50`.
  5. Sapma: `GET /api/v1/budget/deviations?year=Y&status=acik&scope=kitap` anahtarları ∩ küme = `sapma_acik` kümesi.
  6. Özel gün: CRM `new_new_kitap_new_ozelgunlerBase` (etkin özel gün) bağ sayısı = kartın `ozelGunler` sayısı.
  7. Endeks: süzgeçsiz liste toplamı = küme sayısı (tavan yok); her satırda beş bileşen; iki farklı ağırlıkta endeks
     formülle yeniden hesaplanır (Σ w·p ÷ Σ w, değeri olan bileşenler).
  8. Kampanya etkisi: bir CRM kampanyası ürününde Logo net adedi (kampanya ayları, ay düzeyinde) = `kampanya_adet`.
  9. Teknoloji adı: liste, kart ve gündem yanıtında model/ürün adı yok.
 10. (--write) Aktivasyon planı: iki kitapla açılır, `kind='backlist'`, kitaplar ve bütçe satırı DB ile aynı; taslak silinir.
     Kimlikler `M17_STATE` dosyasına yazılır, `cleanup.py` siler.
Çıktı: JSON; `ok` her denetim için; sonunda özet.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))

import sqlalchemy as sa  # noqa: E402

from semantic_bridge import budget_sources as bsrc  # noqa: E402
from semantic_bridge.marketing import backlist_sql as Q  # noqa: E402
from semantic_bridge.marketing import guard as G  # noqa: E402
from semantic_layer.config import SemanticSettings  # noqa: E402
from semantic_layer.store.catalog_store import open_store  # noqa: E402

BRIDGE = os.environ.get("M17_BRIDGE", "http://127.0.0.1:8795")
STATE = Path(os.environ.get("M17_STATE", "m17-kabul-state.json"))
SCHEMA = os.environ.get("CRM_SCHEMA", "Timas_MSCRM.dbo")


def api(method: str, path: str, body: Any = None) -> tuple[int, Any]:
    headers = {"Cookie": os.environ["M17_COOKIE"], "X-Semantic-Caller": os.environ.get("SEMANTIC_CALLER_TOKEN", "")}
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


def near(a: Any, b: Any, tol: float = 0.01) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return abs(float(a) - float(b)) <= tol


def ym_to_date(ym: str) -> date:
    return date(int(ym[:4]), int(ym[5:7]), 1)


def next_month(d: date) -> date:
    return date(d.year + d.month // 12, d.month % 12 + 1, 1)


def logo_units(logo, firms: dict[int, str], codes: list[str], start: date, end: date) -> dict[str, float]:
    """[start, end) aralığında kod başına net adet; her yıl kendi firmasından."""
    out = {c: 0.0 for c in codes}
    vals = ", ".join("(N'" + c.replace("'", "''") + "')" for c in codes)
    for y in range(start.year, end.year + 1):
        a, b = max(start, date(y, 1, 1)), min(end, date(y + 1, 1, 1))
        if a >= b:
            continue
        if y not in firms:
            raise RuntimeError(f"Logo'da {y} yılı yok")
        f = firms[y]
        for r in logo(f"""
SELECT I.CODE AS kod, SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.AMOUNT ELSE -S.AMOUNT END) AS adet
FROM dbo.LG_{f}_01_STLINE S JOIN dbo.LG_{f}_ITEMS I ON I.LOGICALREF = S.STOCKREF
JOIN (VALUES {vals}) AS kod(k) ON kod.k = I.CODE
WHERE S.CANCELLED = 0 AND S.LINETYPE = 0 AND S.INVOICEREF <> 0 AND S.TRCODE IN (2,3,7,8,9)
  AND S.DATE_ >= '{a.isoformat()}' AND S.DATE_ < '{b.isoformat()}'
GROUP BY I.CODE"""):
            out[str(r["kod"]).strip()] = out.get(str(r["kod"]).strip(), 0.0) + float(r["adet"] or 0)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stok", default="", help="virgülle örnek kitaplar (boşsa en çok satan 5 backlist kitabı)")
    ap.add_argument("--write", action="store_true", help="aktivasyon planı aç, denetle, sil")
    args = ap.parse_args()
    s = SemanticSettings.from_env()
    crm = bsrc.runner(os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json"))
    logo = bsrc.runner(s.connection_file)
    firms = bsrc.firms_by_year(logo)
    store = open_store(s.store_dsn, create=False)
    tenant = s.tenant_id
    out: dict[str, Any] = {"checks": []}

    def check(name: str, ok: bool, **detail: Any) -> None:
        out["checks"].append({"ad": name, "ok": bool(ok), **detail})

    st, meta = api("GET", "/api/v1/marketing/backlist/meta")
    run = (meta or {}).get("run") if st == 200 else None
    if not run:
        check("0-liste-kurulu", False, hata="Liste kurulmamış: önce BUILD=1 sh run.sh ya da timas-marketing-backlist.service")
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
        return 1
    out["run"] = {k: run.get(k) for k in ("veriSonu", "sonTamAy", "son12", "onceki12", "kume", "sureMs", "notlar")}
    with store.engine.connect() as c:
        rows = {r.stok_kodu: r for r in c.execute(sa.text("SELECT * FROM semantic_mkt_backlist WHERE tenant_id = :t"), {"t": tenant}).all()}
    year = run["kume"].get("yil")

    # 1 ---------------------------------------------------------------- küme
    if run["kume"]["kaynak"] == "m46":
        st, tg = api("GET", f"/api/v1/budget/targets?year={year}&segment=backlist")
        want = {x["stokKodu"] for x in (tg or {}).get("items", []) if not x["stokKodu"].startswith("157")} if st == 200 else set()
        check("1-kume", st == 200 and want == set(rows), butce=len(want), backlist=len(rows),
              eksik=sorted(want - set(rows))[:50], fazla=sorted(set(rows) - want)[:50])
    else:
        check("1-kume", True, atlandi=True, not_=f"{year} için onaylı bütçe planı yok; yedek tanım: {run['kume'].get('ad')}")

    # örnekler
    codes = [c.strip() for c in args.stok.split(",") if c.strip()]
    if not codes:
        st, lst = api("GET", "/api/v1/marketing/backlist?sirala=adet")
        codes = [x["stokKodu"] for x in (lst or {}).get("items", [])[:5]] if st == 200 else []
    codes = [c for c in codes if c in rows]
    out["ornek"] = codes

    # 2 ---------------------------------------------------------------- eğilim (Logo STLINE)
    s12 = run["son12"]
    o12 = run["onceki12"]
    son = logo_units(logo, firms, codes, ym_to_date(s12[0]), next_month(ym_to_date(s12[1])))
    onc = logo_units(logo, firms, codes, ym_to_date(o12[0]), next_month(ym_to_date(o12[1])))
    diff = [{"kod": k, "ekran": [rows[k].adet_son12, rows[k].adet_onceki12], "logo": [son[k], onc[k]]} for k in codes]
    check("2-egilim", bool(codes) and all(near(rows[k].adet_son12, son[k]) and near(rows[k].adet_onceki12, onc[k]) for k in codes), satir=diff)

    # 3 ---------------------------------------------------------------- stok (Baskı Öneri sorgusu)
    stock = {str(r["stok_kodu"]).strip(): float(r["depo_stok"] or 0) for r in logo(Q.logo_stock_sql())}
    check("3-stok", all(near(rows[k].stok, stock.get(k)) for k in codes),
          satir=[{"kod": k, "ekran": rows[k].stok, "logo": stock.get(k)} for k in codes])

    # 4 ---------------------------------------------------------------- tahmin
    fc = bsrc.read_forecast()
    exp = {k: (round(sum((fc.get("p50") or {}).get(k, [])[:12]), 1) if (fc.get("p50") or {}).get(k) else None) for k in codes}
    check("4-tahmin", all(near(rows[k].tahmin12_p50, exp[k], 0.2) for k in codes),
          satir=[{"kod": k, "ekran": rows[k].tahmin12_p50, "onbellek": exp[k]} for k in codes])

    # 5 ---------------------------------------------------------------- sapma
    if run["kume"]["kaynak"] == "m46":
        keys: set[str] = set()
        page = 0
        while True:
            st, dv = api("GET", f"/api/v1/budget/deviations?year={year}&status=acik&scope=kitap&page={page}")
            if st != 200:
                break
            keys |= {a["key"] for a in dv["items"] if a["kind"] == "satis"}
            if (page + 1) * dv["pageSize"] >= dv["total"]:
                break
            page += 1
        want = keys & set(rows)
        got = {k for k, r in rows.items() if r.sapma_acik}
        check("5-sapma", st == 200 and want == got, butce=len(want), backlist=len(got), fark=sorted(want ^ got)[:50])
    else:
        check("5-sapma", True, atlandi=True)

    # 6 ---------------------------------------------------------------- özel gün bağı (CRM)
    sat = []
    for k in codes:
        ref = crm(f"""
SELECT COUNT(DISTINCT l.new_ozelgunlerid) AS n FROM {SCHEMA}.new_new_kitap_new_ozelgunlerBase l
JOIN {SCHEMA}.new_kitapBase k ON k.new_kitapId = l.new_kitapid
JOIN {SCHEMA}.new_ozelgunlerBase o ON o.new_ozelgunlerId = l.new_ozelgunlerid AND o.statecode = 0
WHERE k.statecode = 0 AND k.new_StokKodu = N'{k.replace("'", "''")}'""")[0]["n"]
        n = len(json.loads(rows[k].ozel_gunler or "[]"))
        sat.append({"kod": k, "crm": int(ref or 0), "ekran": n})
    check("6-ozel-gun", all(x["crm"] == x["ekran"] for x in sat), satir=sat)

    # 7 ---------------------------------------------------------------- endeks açıklanabilirliği, tavan yok
    st, a = api("GET", "/api/v1/marketing/backlist?agirlik=egilim:1,stok:1,marj:1,tahmin:1,sapma:1&sirala=endeks")
    st2, b = api("GET", "/api/v1/marketing/backlist?agirlik=egilim:3,stok:0,marj:0,tahmin:1,sapma:0&sirala=endeks")
    ok = st == 200 and st2 == 200 and a["total"] == a["hepsi"] == len(rows)

    def recompute(x: dict[str, Any], w: dict[str, float]) -> Any:
        num = den = 0.0
        for kk, ww in w.items():
            p = x["bilesen"][kk]["yuzdelik"]
            if p is not None and ww > 0:
                num += ww * p
                den += ww
        return round(num / den, 1) if den else None

    w2 = {"egilim": 3, "stok": 0, "marj": 0, "tahmin": 1, "sapma": 0}
    ok = ok and all(len(x["bilesen"]) == 5 for x in a["items"]) and all(recompute(x, w2) == x["endeks"] for x in b["items"])
    check("7-endeks", ok, toplam=a.get("total") if st == 200 else a, hepsi=a.get("hepsi") if st == 200 else None, kume=len(rows),
          ilk_esit=[x["stokKodu"] for x in a["items"][:5]] if st == 200 else None,
          ilk_egilim=[x["stokKodu"] for x in b["items"][:5]] if st2 == 200 else None)

    # 8 ---------------------------------------------------------------- kampanya etkisi (ay düzeyi)
    st, ef = api("GET", "/api/v1/marketing/backlist/effects")
    cand = next((u for c in (ef or {}).get("items", []) for u in c["urunler"] if u["kapsam"] == "tam"), None) if st == 200 else None
    if cand:
        a0 = ym_to_date(cand["baslangic"][:7])
        z0 = next_month(ym_to_date(cand["bitis"][:7]))
        ref = logo_units(logo, firms, [cand["stokKodu"]], a0, z0)[cand["stokKodu"]]
        check("8-kampanya", near(cand["kampanya"], ref), kampanya=cand["kampanyaId"], kod=cand["stokKodu"], ekran=cand["kampanya"], logo=ref)
    else:
        check("8-kampanya", True, atlandi=True, not_="tam penceresi olan kampanya ürünü yok")

    # 9 ---------------------------------------------------------------- teknoloji adı
    st, card = api("GET", f"/api/v1/marketing/backlist/{codes[0]}") if codes else (0, {})
    st2, ag = api("GET", "/api/v1/marketing/backlist/agenda")
    blob = json.dumps([a, card, ag], ensure_ascii=False)
    check("9-teknoloji-adi", not G.has_tech_name(blob) and st == 200 and st2 == 200)

    # 10 --------------------------------------------------------------- yazma: aktivasyon planı
    if args.write:
        stocked = [k for k in codes if (rows[k].stok or 0) > 0][:2]
        st, plan = api("POST", "/api/v1/marketing/backlist/plans", {"kitaplar": [{"stokKodu": k} for k in stocked]})
        if st == 201:
            state = json.loads(STATE.read_text()) if STATE.exists() else {"plans": []}
            state["plans"].append(plan["id"])
            STATE.write_text(json.dumps(state))
            with store.engine.connect() as c:
                bk = [r[0] for r in c.execute(sa.text("SELECT stok_kodu FROM semantic_mkt_plan_books WHERE plan_id = :p ORDER BY sira"),
                                              {"p": plan["id"]}).all()]
                dbsum = c.execute(sa.text("SELECT COALESCE(SUM(tutar), 0) FROM semantic_mkt_plan_lines WHERE plan_id = :p"),
                                  {"p": plan["id"]}).scalar()
            check("10a-plan", plan["kind"] == "backlist" and bk == stocked and near(dbsum, plan.get("butceToplam") or 0),
                  plan=plan["id"], kitap=bk, db=dbsum, ekran=plan.get("butceToplam"), cerceve=plan.get("butceCerceveKaynak"))
            st, _ = api("DELETE", f"/api/v1/marketing/plans/{plan['id']}")
            with store.engine.connect() as c:
                left = c.execute(sa.text("SELECT COUNT(*) FROM semantic_mkt_plan_books WHERE plan_id = :p"), {"p": plan["id"]}).scalar()
            check("10b-taslak-silindi", st == 200 and left == 0, durum=st, kalan_kitap=left)
        else:
            check("10-plan-ac", False, durum=st, hata=plan)

    out["ozet"] = {"gecti": sum(1 for c in out["checks"] if c["ok"]), "kaldi": sum(1 for c in out["checks"] if not c["ok"])}
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0 if out["ozet"]["kaldi"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
