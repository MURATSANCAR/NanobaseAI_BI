"""M16 izleme okuması: açık lansmanların CRM sipariş sinyali (saatlik), açık sipariş / bekleyen ürün, Logo faturalı satış
ve depo stoku (günde bir), M46 hedefinin günlük payı, emsallerin ilk 7/30 günü ve yayın günü adayları.

Okuma kitap başına değil toplu yapılır (bütün açık lansmanların stok kodları tek sorguda); her lansmanın kendi
penceresi (yayından `MARKETING_LAUNCH_PRE_DAYS` gün önce … D+29, bugünden ileri değil) sonuçtan süzülür.
Bir kaynak okunamazsa diğerleri yazılır, hata lansman özetine düşer (ekranda «okunamadı»); sessiz sıfır yazılmaz.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, Callable, Optional

import sqlalchemy as sa

from semantic_bridge.marketing import core as C
from semantic_bridge.marketing import launch as L
from semantic_bridge.marketing.launch_sources import Sources, first_days
from semantic_bridge.marketing.sources import SourceError

log = logging.getLogger("semantic.marketing.launch")

EMSAL_WINDOW_DAYS = 120   # emsalin lansman ayı başından ilk satış gününü ve ilk 30 gününü aramak için


def _targets(engine: Any, tenant: str, code: str, years: list[int]) -> dict[int, dict[str, Any]]:
    from semantic_bridge.marketing import plans as P

    out = {}
    for y in years:
        out[y] = P.target_for(engine, tenant, code, f"{y}-01-01")
    return out


def date_candidates(launch: dict[str, Any], detail: Optional[dict[str, Any]], exit_: Optional[dict[str, Any]],
                    today: date) -> tuple[dict[str, str], list[str]]:
    """Yayın günü adayları (CRM kitap/proje/üretim kartı ve M12 baskı çıkışı) ve çelişki uyarıları."""
    cand: dict[str, str] = {}
    t = (detail or {}).get("tarihler") or {}
    for src, key in (("crm-kitap", "kitap"), ("crm-proje", "proje"), ("uretim-dagilim", "uretim-dagilim"), ("uretim-depo", "uretim-depo")):
        if t.get(src):
            cand[key] = t[src]
    first = None
    for it in (exit_ or {}).get("items") or []:
        if first is None or (it.get("printNo") or 0) < (first.get("printNo") or 0):
            first = it
    if first:
        if first.get("depot"):
            cand["uretim-depo"] = first["depot"]           # M12: gerçekleşen depo girişi (CRM + Logo üretim)
        elif first.get("depotPlanned") and "uretim-depo" not in cand:
            cand["uretim-dagilim"] = cand.get("uretim-dagilim") or first["depotPlanned"]
    pub = launch["yayinGunu"]
    warn = []
    depot = cand.get("uretim-depo")
    p = date.fromisoformat(pub)
    if depot and depot > pub:
        warn.append(f"Kitap depoya yayın gününden {(date.fromisoformat(depot) - p).days} gün sonra girdi ({depot}).")
    if not depot and 0 <= (p - today).days <= 3:
        warn.append("Depo girişi henüz görünmüyor; yayına 3 gün ya da daha az kaldı.")
    if not depot and today > p:
        warn.append("Yayın günü geçti; üretim kartında depo girişi görünmüyor.")
    if launch.get("yayinGunuKaynagi") != "elle":
        for k in ("kitap", "proje"):
            if cand.get(k) and cand[k] != pub:
                warn.append(f"{L.DATE_SOURCES[k]} {cand[k]} diyor; lansman {pub} gününe göre izleniyor.")
    return cand, warn


def emsal_days(engine: Any, tenant: str, src: Sources, firms: dict[int, str], data_end: Optional[date],
               items: list[dict[str, Any]]) -> dict[str, Any]:
    """Emsallerin ilk satış gününden itibaren ilk 7/30 gün (Logo faturalı net adet). Tamamlanmış sonuç kalıcı saklanır
    (geçmiş değişmez), eksik olan her günlük okumada yeniden denenir."""
    out = []
    errors = []
    for e in items:
        code, lan = e.get("stokKodu"), e.get("lansman")
        if not code or not lan or len(lan) < 7:
            continue
        key = f"launch-emsal:{code}"
        hit = C.meta_get(engine, tenant, key)
        if hit.get("tam"):
            out.append({**{k: v for k, v in hit.items() if k != "_at"}, "stokKodu": code, "ad": e.get("ad")})
            continue
        start = date(int(lan[:4]), int(lan[5:7]), 1)
        end = start + timedelta(days=EMSAL_WINDOW_DAYS)
        if data_end:
            end = min(end, data_end)
        if end < start:
            continue
        try:
            rows, _ = src.daily_sales(firms, [code], start, end)
        except SourceError as ex:
            errors.append(f"Emsal {code}: {ex}")
            continue
        daily = {g: v["adet"] for (k, g), v in rows.items() if k == code}
        res = first_days(daily, start, 30, data_end)
        C.meta_set(engine, tenant, key, res)
        out.append({**res, "stokKodu": code, "ad": e.get("ad")})
    full = [x for x in out if x.get("ilk30") is not None]
    week = [x for x in out if x.get("ilk7") is not None]
    curve = []
    for i in range(30):
        vals = [x["gunluk"][i] for x in full if len(x["gunluk"]) > i]
        curve.append(round(sum(vals) / len(vals), 2) if vals else 0.0)
    return {"items": out, "ort7": round(sum(x["ilk7"] for x in week) / len(week), 2) if week else None,
            "ort30": round(sum(x["ilk30"] for x in full) / len(full), 2) if full else None,
            "egri": curve if full else [], "hatalar": errors,
            "not": None if out else "Emsal yok ya da emsallerin lansman ayı bilinmiyor (M15 karnesi, İlk baskı veri kümesi)."}


def refresh(engine: Any, tenant: str, launches: list[dict[str, Any]], src: Sources, st: dict[str, Any], *, logo: bool,
            today: Optional[date] = None, detail_of: Callable[[str], Optional[dict[str, Any]]] = lambda s: None,
            exit_of: Callable[[str], Optional[dict[str, Any]]] = lambda k: None) -> dict[str, Any]:
    """Açık lansmanları okur, gün satırlarını ve özetlerini yazar. `logo`: günlük Logo okuması (satış, depo, veri sonu,
    emsal) da yapılsın mı. Dönen: rapor (okunan lansman, yazılan gün, hatalar)."""
    today = today or C.today()
    report: dict[str, Any] = {"lansman": 0, "gun": 0, "hatalar": [], "logo": logo}
    if not launches:
        return report
    wins = {x["id"]: L.window(x["yayinGunu"], st["preDays"], today) for x in launches}
    codes = sorted({x["stokKodu"] for x in launches})
    lo = min(w[0] for w in wins.values())
    hi = max(max(w[1], w[0]) for w in wins.values())
    if any(w[1] < w[0] for w in wins.values()):
        lo = min(lo, today)     # penceresi henüz başlamamış lansman: bugünün anlık okuması için
    errors: list[str] = []
    sqls: dict[str, Any] = {}

    def read(label: str, fn: Callable[[], Any], default: Any) -> Any:
        try:
            return fn()
        except SourceError as e:
            errors.append(f"{label}: {e}")
            log.warning("launch refresh %s: %s", label, e)
            return default

    orders, sqls["siparis"] = read("CRM sipariş", lambda: src.orders(codes, lo, hi, st["orderExclude"]), ({}, None))
    ok_orders = sqls["siparis"] is not None
    open_, sqls["acikSiparis"] = read("CRM açık sipariş", lambda: src.open_orders(codes), (None, None))
    pend, sqls["bekleyenUrun"] = read("CRM bekleyen ürün", lambda: src.pending_items(codes), (None, None))
    crm_stock, sqls["siparisAnindakiStok"] = read("CRM sipariş anındaki stok",
                                                  lambda: src.order_time_stock(codes, lo - timedelta(days=30)), ({}, None))
    firms: dict[int, str] = {}
    data_end: Optional[date] = None
    sales: dict[tuple[str, str], dict[str, float]] = {}
    depot: Optional[dict[str, float]] = None
    if logo:
        firms = read("Logo dönemleri", src.firms, {})
        if firms:
            data_end = read("Logo veri sonu", lambda: src.data_end(firms), None)
            sales, sqls["fatura"] = read("Logo faturalı satış", lambda: src.daily_sales(firms, codes, lo, hi), ({}, None))
            depot, sqls["depo"] = read("Logo depo stoku", lambda: src.depot(codes), (None, None))
    ok_sales = logo and sqls.get("fatura") is not None

    for x in launches:
        lid, code, pub = x["id"], x["stokKodu"], x["yayinGunu"]
        a, b = wins[lid]
        with engine.connect() as c:
            r = c.execute(sa.select(L.LAUNCHES.c.ozet_json, L.LAUNCHES.c.elle_kapandi).where(L.LAUNCHES.c.id == lid)).first()
        prev = C.loads(r.ozet_json if r else None, {})
        mine_err = list(errors)
        rows: dict[str, dict[str, Any]] = {}
        p = date.fromisoformat(pub)
        years = sorted({y for y in range(p.year, (p + timedelta(days=29)).year + 1)})
        targets = _targets(engine, tenant, code, years)
        # Yayına pencereden uzun süre varsa (elle erken açılan lansman) yalnız bugünün anlık okuması yazılır.
        for g in (L.days_between(a, b) or [today.isoformat()]):
            d = date.fromisoformat(g)
            v: dict[str, Any] = {}
            if ok_orders:
                o = orders.get((code, g)) or {}
                v.update(siparis_adet=o.get("siparis_adet", 0.0), siparis_satiri=o.get("siparis_satiri", 0.0),
                         dagilim_adet=o.get("dagilim_adet", 0.0), sevk_adet=o.get("sevk_adet", 0.0))
            if ok_sales:
                s = sales.get((code, g))
                covered = data_end is not None and d <= data_end
                v.update(fatura_net_adet=(s["adet"] if s else 0.0) if covered else None,
                         fatura_net_ciro=(s["ciro"] if s else 0.0) if covered else None,
                         veri_sonu_logo=data_end.isoformat() if data_end else None)
            if d >= p:
                t = targets.get(d.year) or {}
                v.update(hedef_payi_adet=L.daily_target(t.get("aylik"), d, "adet"),
                         hedef_payi_ciro=L.daily_target(t.get("aylik"), d, "ciro"))
            if g == today.isoformat():
                if open_ is not None:
                    v["bekleyen_adet"] = open_.get(code, 0.0)
                if pend is not None:
                    v["bekleyen_urun_adet"] = pend.get(code, 0.0)
                if depot is not None:
                    v["depo_stok"] = depot.get(code, 0.0)
            if v:
                rows[g] = v
        report["gun"] += L.upsert_days(engine, lid, rows)

        dist = prev.get("dagilim")
        if ok_orders:
            try:
                dd, sqls_d = src.distribution([code], a, b, st["orderExclude"])
                dist = {**(dd.get(code) or {"adet": 0.0, "siparis": 0.0, "bayi": 0.0}), "bas": a.isoformat(), "bit": b.isoformat()}
                prev.setdefault("sql", {})["dagilim"] = sqls_d
            except SourceError as e:
                mine_err.append(f"CRM dağılım: {e}")
        cand, date_warn = prev.get("adaylar") or {}, prev.get("tarihUyarilari") or []
        if logo or not prev.get("adaylar"):
            # Üretim kartı (M12 baskı çıkışı) ağır okumadır: günde bir, ya da aday hiç okunmamışsa.
            try:
                cand, date_warn = date_candidates(x, detail_of(code), exit_of(x["crmKitapId"]) if x.get("crmKitapId") else None, today)
            except (SourceError, C.MarketingError, ValueError) as e:
                mine_err.append(f"Yayın günü adayları: {e}")
        ozet = {**prev, "onGun": st["preDays"], "dagilim": dist, "adaylar": cand, "tarihUyarilari": date_warn,
                "crmStok": crm_stock.get(code) if crm_stock else prev.get("crmStok"),
                "hedef": {str(y): {k: t.get(k) for k in ("year", "planId", "version", "adet", "not")} for y, t in targets.items()},
                "hatalar": mine_err, "okuma": C.iso(C.now())}
        sql_now = {k: v for k, v in sqls.items() if v}
        ozet["sql"] = {**(prev.get("sql") or {}), **sql_now}
        if data_end:
            ozet["veriSonuLogo"] = data_end.isoformat()
        if logo and firms:
            card = C.card_get(engine, tenant, code) or {}
            em_items = ((card.get("emsal") or {}).get("items")) or []
            em = emsal_days(engine, tenant, src, firms, data_end, em_items)
            mine_err += em.pop("hatalar")
            ozet["emsal"] = em
        tasks = L.get_full(engine, tenant, lid)["tasks"]
        ev = L.evaluate(pub, L.days_of(engine, lid), tasks, ozet, st, today)
        ozet.update(renk=ev["renk"], uyarilar=ev["uyarilar"], sinyal=ev["sinyal"])
        closed = bool(r and r.elle_kapandi)
        durum = L.phase(pub, today, closed)
        if durum == "izleme" and (today - p).days > 30 and L.review_get(engine, lid, 30):
            durum = "kapandi"
        L.set_summary(engine, lid, ozet, durum=durum)
        report["lansman"] += 1
        report["hatalar"] += [f"{lid}: {e}" for e in mine_err if e not in errors]
    report["hatalar"] = errors + report["hatalar"]
    report["veriSonuLogo"] = data_end.isoformat() if data_end else None
    return report
