"""Fiyatlama ve Maliyet Analizi (M9): kitap bazlı maliyet (kâğıt, baskı, telif, çeviri, grafik…), başabaş, kapak fiyatı
önerisi, baskı adedi senaryoları, kanal fiyat matrisi, gerçekleşen maliyet/marj (Logo) ve backlist fiyat revizyonu.

- `model`: saf hesap (birim maliyetin tek sahibi; M10/M12/M46 buradan çağırır).
- `sources` + `data`: Logo/CRM'den salt okunur anlık görüntü ve üstündeki hesaplar.
- `store`: analizler, onaylar, elle girilen pazar fiyatları, varsayılanlar, toplu zam teklifleri (kendi tablolarımız).
- `dagitim`: dağıtımcı kataloğundan (M39 Başarı/D&R tabloları) kategori fiyat dağılımı; ortanca tek tıkla pazar
  fiyatı olarak eklenir, `recommend()`'e o yoldan girer.
- `karsilastir`: eski kitaplar — CRM'deki güncel kapak fiyatı ↔ «Kitap hesabı»nın aynı zinciriyle bizim fiyatımız,
  bütün kitaplar için (arka planda hesaplanır, girdiler değişince yenilenir); toplu fiyat teklifi buradan çıkar.
- `cost_provider`: öbür modüllere (M32, M33, M53) kitap birim maliyeti — onaylı analiz → Logo gerçekleşen → yok.

CRM'e, Logo'ya, e-ticarete yazılmaz. Uçlar `/api/v1/pricing/*`; sayfa `sayfa:fiyatlama`, yazma `ozellik:fiyatlama.yaz`,
imzalar açıkça verilen `ozellik:fiyatlama.onay-<rol>`.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Callable, Optional

from fastapi import HTTPException, Request

from semantic_bridge.pricing import data as D
from semantic_bridge.pricing import model as M
from semantic_bridge import provenance as P
from semantic_bridge.pricing import kaynak as K
from semantic_bridge.pricing import karsilastir as KS
from semantic_bridge.pricing import sources as SRC
from semantic_bridge.pricing import store as S

log = logging.getLogger("semantic.pricing")

#: M8 serbest çalışan rolü → maliyet kalemi.
FREELANCE_ROLE = {"ceviri": "ceviri", "cizer": "grafik", "kapak": "grafik", "mizanpaj": "redaksiyon",
                  "redaksiyon": "redaksiyon", "tashih": "redaksiyon", "yayina-hazirlik": "redaksiyon",
                  "danismanlik": "diger"}


def _num(body: dict, key: str, default: Optional[float] = None, lo: float = 0.0, hi: float = 1e12) -> Optional[float]:
    v = body.get(key, default)
    if v is None or v == "":
        return default
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise S.PricingError(f"«{key}» sayı olmalı.") from None
    if not lo <= x <= hi:
        raise S.PricingError(f"«{key}» {lo:g} ile {hi:g} arasında olmalı.")
    return x


def cost_inputs(inp: dict) -> M.CostInputs:
    """Ekrandan gelen girdiler → hesap girdisi. Oranlar 0–1."""
    fixed = {}
    for k in M.FIXED_KEYS:
        v = _num(inp.get("fixed") or {}, k, 0.0)
        fixed[k] = v or 0.0
    per_copy = _num(inp, "printPerCopy")
    if per_copy is None or per_copy <= 0:
        raise S.PricingError("Adet başına baskı ve kâğıt maliyetini girin.")
    overhead = _num(inp, "overheadRate", 0.0, 0.0, 2.0) or 0.0
    base = inp.get("royaltyBase") or "kapak"
    on = inp.get("royaltyOn") or "satis"
    if base not in ("kapak", "net") or on not in ("satis", "baski"):
        raise S.PricingError("Telif tabanı kapak/net, telif doğuşu satış/baskı olmalı.")
    sell = _num(inp, "sellThrough", 1.0, 0.0, 1.0)
    if not sell:
        raise S.PricingError("Satış oranı sıfır olamaz.")
    return M.CostInputs(
        print_per_copy=per_copy * (1 + overhead), print_setup=(_num(inp, "printSetup", 0.0) or 0.0) * (1 + overhead),
        fixed=fixed, royalty_rate=_num(inp, "royaltyRate", 0.0, 0.0, 0.9) or 0.0, royalty_base=base, royalty_on=on,
        vat=_num(inp, "vat", 0.0, 0.0, 0.5) or 0.0, discount=_num(inp, "discount", 0.0, 0.0, 0.95) or 0.0,
        variable_rate=_num(inp, "variableRate", 0.0, 0.0, 0.9) or 0.0, sell_through=sell)


def calculate(snap: Optional[dict], body: dict[str, Any], pool: Optional[list[dict]] = None) -> dict[str, Any]:
    """Senaryo tablosu + fiyat önerisi + kanal matrisi. Emsal fiyatları görüntüden (ve elle girilen pazar fiyatlarından).
    `pool`: toplu hesapta bir kez kurulan emsal havuzu (`data.comparable_pool`)."""
    inp = body.get("inputs") or {}
    ci = cost_inputs(inp)
    qtys = S._qtys(inp.get("qtys") or body.get("qtys") or list(M.DEFAULT_QTYS))
    price = _num(inp, "price")
    target = _num(inp, "targetMargin", 0.15, 0.0, 0.9) or 0.0
    chosen_qty = int(_num(inp, "chosenQty") or qtys[len(qtys) // 2])
    spec = body.get("spec") or {}
    comp = None
    comp_prices: list[float] = []
    if snap:
        pages = _num(spec, "pages")
        comp = D.comparables(snap, pages, spec.get("binding") or None, exclude=spec.get("code"), pool=pool)
        comp_prices = [r["price"] for r in comp["rows"] if r.get("price")]
    market = [float(m) for m in (body.get("marketPrices") or []) if isinstance(m, (int, float)) and m > 0]
    rec = M.recommend(ci, chosen_qty, target, comp_prices + market)
    use_price = price or rec.get("price")
    scenarios = [M.scenario(ci, q, use_price) for q in qtys]
    floors = [{"qty": q, **M.price_for_margin(ci, q, target)} for q in qtys]
    matrix = []
    for ch in (snap or {}).get("channels") or []:
        if not use_price or ch.get("share", 0) < 0.001:
            continue
        n = M.net_unit(use_price, ci.vat, ch["discount"])
        base = use_price / (1 + ci.vat) if ci.royalty_base != "net" else n
        r = ci.royalty_rate * base
        var = ci.variable_rate * n
        uc = M.unit_cost(ci, chosen_qty)["perCopy"]
        contrib = n - r - var - uc
        matrix.append({"channel": ch["channel"], "discount": ch["discount"], "share": ch["share"], "netUnit": round(n, 2),
                       "royaltyUnit": round(r, 2), "variableUnit": round(var, 2), "unitCost": round(uc, 2),
                       "contribution": round(contrib, 2), "margin": round(contrib / n, 4) if n > 0 else None})
    sc_chosen = M.scenario(ci, chosen_qty, use_price)
    summary = {"price": use_price, "qty": chosen_qty, "unitCost": sc_chosen["unitCost"], "totalCost": sc_chosen["totalCost"],
               "breakeven": sc_chosen.get("breakeven"), "margin": sc_chosen.get("margin"), "profit": sc_chosen.get("profit"),
               "recommended": rec.get("price"), "floor": rec.get("floor"), "band": rec.get("band"),
               "targetMargin": target}
    return {"scenarios": scenarios, "floors": floors, "recommendation": rec, "channels": matrix, "summary": summary,
            "comparables": comp, "marketCount": len(market),
            "inputs": {"printPerCopy": ci.print_per_copy, "printSetup": ci.print_setup, "fixed": ci.fixed,
                       "royaltyRate": ci.royalty_rate, "royaltyBase": ci.royalty_base, "royaltyOn": ci.royalty_on,
                       "vat": ci.vat, "discount": ci.discount, "variableRate": ci.variable_rate,
                       "sellThrough": ci.sell_through, "qtys": qtys, "targetMargin": target}}


def freelance_stmt(tenant: str, book_id: str):
    """M8'de bu kitaba açılmış, iptal olmayan iş paketlerinin görevleri (sorgu bilgisi de bu ifadeyi gösterir)."""
    import sqlalchemy as sa
    from semantic_bridge import freelance as fl
    return (sa.select(fl.TASKS.c.role, fl.TASKS.c.status, fl.TASKS.c.units, fl.TASKS.c.unit_price, fl.PACKAGES.c.title)
            .join(fl.PACKAGES, fl.PACKAGES.c.id == fl.TASKS.c.package_id)
            .where(fl.TASKS.c.tenant_id == tenant, fl.PACKAGES.c.book_id == book_id.lower(),
                   fl.PACKAGES.c.status != "iptal", fl.TASKS.c.status != "iptal"))


def freelance_costs(engine: Any, tenant: str, book_id: Optional[str]) -> dict[str, Any]:
    """M8'de bu kitaba açılmış iş paketlerinin tutarı (iptal hariç), maliyet kalemine göre. Tablo yoksa boş."""
    if not book_id:
        return {"items": [], "byKey": {}}
    try:
        with engine.connect() as c:
            rows = c.execute(freelance_stmt(tenant, book_id)).all()
    except Exception:  # noqa: BLE001 — M8 tabloları bu kurulumda yoksa kalem boş kalır
        log.info("pricing: serbest çalışan tabloları okunamadı", exc_info=True)
        return {"items": [], "byKey": {}}
    by: dict[str, float] = {}
    items = []
    for role, status, units, price, title in rows:
        amount = float(units or 0) * float(price or 0)
        key = FREELANCE_ROLE.get(role, "diger")
        by[key] = round(by.get(key, 0.0) + amount, 2)
        items.append({"role": role, "status": status, "amount": round(amount, 2), "package": title, "key": key})
    return {"items": items, "byKey": by}


def freelance_all(engine: Any, tenant: str) -> dict[str, dict[str, float]]:
    """`freelance_costs`'un bütün kitaplar için tek sorguluk eşi: CRM kitap kimliği (küçük harf) → maliyet kalemi → tutar."""
    import sqlalchemy as sa
    from semantic_bridge import freelance as fl
    stmt = (sa.select(fl.PACKAGES.c.book_id, fl.TASKS.c.role, fl.TASKS.c.units, fl.TASKS.c.unit_price)
            .join(fl.PACKAGES, fl.PACKAGES.c.id == fl.TASKS.c.package_id)
            .where(fl.TASKS.c.tenant_id == tenant, fl.PACKAGES.c.status != "iptal", fl.TASKS.c.status != "iptal"))
    try:
        with engine.connect() as c:
            rows = c.execute(stmt).all()
    except Exception:  # noqa: BLE001 — M8 tabloları bu kurulumda yoksa kalem boş kalır
        log.info("pricing: serbest çalışan tabloları okunamadı", exc_info=True)
        return {}
    out: dict[str, dict[str, float]] = {}
    for book_id, role, units, price in rows:
        by = out.setdefault((book_id or "").lower(), {})
        key = FREELANCE_ROLE.get(role, "diger")
        by[key] = round(by.get(key, 0.0) + float(units or 0) * float(price or 0), 2)
    return out


def market_all(engine: Any, tenant: str) -> dict[str, list[float]]:
    """Kitaplara elle girilmiş pazar fiyatları: CRM kitap kimliği (küçük harf) → fiyatlar (kitap ekranındaki sırayla)."""
    out: dict[str, list[float]] = {}
    for m in S.market_list(engine, tenant)["items"]:
        if m.get("crmBookId") and m.get("price"):
            out.setdefault(m["crmBookId"].lower(), []).append(m["price"])
    return out


#: Sözleşme türlerinin dökümdeki sırası (Excel «Yetişkin Fiyat Çalışması»); listede olmayan tür sona eklenir.
ROYALTY_ORDER = ("Metin (Eser Sözleşmesi)", "Yayına Hazırlama", "Çizim- İllüstrasyon", "Tercüme",
                 "Ajans-Yabancı Yayınevi Telif Sözleşmesi (Alış)", "Metin (Yabancı Eser Sözleşmesi)",
                 "Çizim- İllüstrasyon (Yabancı)", "Edisyon", "Danışmanlık", "Grafik Tasarım Mizanpaj")


def compare_csv(rows: list[dict]) -> str:
    """Eski kitap fiyat çalışması CSV (Excel eşi ortak katmandan, `bicim=xlsx`). Süzgece uyan bütün satırlar; sütunlar
    Fiyat Çalışması Excel'inin sırasında, sonda bizim hesap."""
    import csv
    import io
    label = {"zam": "Zam gerekiyor", "yuksek": "Güncel fiyat hesabın üstünde", "esit": "Aynı", "hesaplanamadi": "Hesaplanamadı"}
    seen = {t for r in rows for t in (r.get("royalties") or {})}
    types = [t for t in ROYALTY_ORDER if t in seen] + sorted(seen - set(ROYALTY_ORDER))
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Stok kodu", "Yayınevi", "Kitaplık", "Kitap", "Yazar", "Sayfa", "Fiyat", "Stok", "Kâr % (güncel fiyatla)",
                "Yeni fiyat", "Artış (%)", "Sayfa birim fiyatı", "Zamlı birim fiyat", "Ebat", "Cilt", "Renk", "İç kâğıt (gr)",
                "Kapak ve cilt (CRM)", "Son fiyat değişimi", "Önceki fiyat", "Son baskı tarihi", "Son baskı adedi",
                "Tek ödeme tutarı", *[f"{t} karton" for t in types], *[f"{t} sert" for t in types],
                "Emsal grubu", "Merdiven sayfası", "Merdiven fiyatı", "Satış (2 yıl, adet)", "Birim maliyet",
                "Bizim hesap", "Fark (%)", "Maliyet alt sınırı", "Emsal ortancası", "Durum", "Neden", "Yeni fiyatı yazan"])

    def n(v: Any, d: int = 2) -> str:
        return "" if v is None else f"{v:.{d}f}".replace(".", ",")

    def pct(v: Any) -> str:
        return "" if v is None else n(v * 100, 1) + "%"

    for r in rows:
        roy = r.get("royalties") or {}
        lad = r.get("ladder") or {}
        w.writerow([r["code"], r.get("publisher") or "", r.get("library") or "", r["name"], r.get("author") or "",
                    r.get("pages") or "", n(r.get("price")), n(r.get("stock"), 0), pct(r.get("margin")),
                    n(r.get("newPrice")), pct(r.get("newPct")), n(r.get("perPage")), n(r.get("newPerPage")),
                    r.get("trim") or "", r.get("binding") or "", r.get("color") or "", n(r.get("gsm"), 0), r.get("cover") or "",
                    r.get("priceChanged") or (f"{r['priceSince']} öncesi" if r.get("priceSince") else ""), n(r.get("prevPrice")),
                    r.get("lastPrintDate") or "", r.get("lastPrintQty") or "", n(r.get("singlePay")),
                    *[n((roy.get(t) or {}).get("karton"), 1) for t in types], *[n((roy.get(t) or {}).get("sert"), 1) for t in types],
                    r.get("group") or "", lad.get("pages") or "", n(lad.get("price")), n(r.get("sold2y"), 0),
                    n(r.get("unitCost")), n(r.get("ours")), pct(r.get("diffPct")), n(r.get("floor")), n(r.get("median")),
                    label.get(r["status"], r["status"]), r.get("reason") or "", r.get("newBy") or ""])
    return "\ufeff" + buf.getvalue()


def production_quotes(engine: Any, tenant: str, crm_prints: list[dict]) -> list[dict]:
    """M12 üretim kartlarına girilen matbaa teklifleri (kitabın CRM üretim kayıtlarına göre). Yalnız okunur;
    Aşama 2'de «baskı hizmeti» kutusuna yazılabilir. M12 tabloları yoksa boş."""
    ids = {p["id"]: p for p in crm_prints if p.get("id")}
    if not ids:
        return []
    try:
        from semantic_bridge import production_store as ps
        _, quotes = ps.load(engine, tenant, list(ids))
    except Exception:  # noqa: BLE001 — üretim modülü bu kurulumda yoksa teklif listesi boş
        log.info("pricing: üretim teklifleri okunamadı", exc_info=True)
        return []
    out = []
    for cid, items in quotes.items():
        for q in items:
            out.append({**q, "printNo": (ids.get(cid) or {}).get("no"), "printQty": (ids.get(cid) or {}).get("qty")})
    out.sort(key=lambda q: q.get("at") or "", reverse=True)
    return out


def register(app, runtime: Callable[[], Any], ctx: dict[str, Any]):
    """ctx: session(request) → (engine, tenant, user, display); can(user, key) → bool; audit(...); is_admin(user)."""
    session, can, audit, is_admin = ctx["session"], ctx["can"], ctx["audit"], ctx["is_admin"]

    def connect(name: str):
        from semantic_layer.profiler.connectors import connector_from_file
        path = (runtime().settings.connection_file if name == "logo"
                else os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json"))
        if not path or not Path(path).exists():
            raise RuntimeError(("Logo" if name == "logo" else "CRM") + " bağlantısı bu kurulumda tanımlı değil.")
        conn = connector_from_file(path)
        conn.query_timeout = D.QUERY_TIMEOUT
        return conn

    def dbs() -> tuple[Optional[str], Optional[str]]:
        """Sorgu bilgisindeki «USE [..]» satırı için yalnız veritabanı adları (bağlantı bilgisi okunmaz)."""
        return (P.connection_database(runtime().settings.connection_file),
                P.connection_database(os.environ.get("SEMANTIC_CRM_CONNECTION_FILE",
                                                     "/data/nanobaseai/bi/secrets/crm-mssql-connection.json")))

    snaps = D.Store(connect)
    scheduler = {"on": False}

    def ses(request: Request):
        engine, tenant, user, display = session(request)
        if not scheduler["on"]:  # zamanlayıcı ilk istekte başlar (açılışı ve testleri Logo'ya bağlamaz)
            scheduler["on"] = True
            snaps.start()
        S.ensure(engine)
        return engine, tenant, user, display

    def call(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except S.PricingError as e:
            raise HTTPException(status_code=e.status, detail={"code": "PRICING", "message": str(e)}) from e

    def need_snap() -> dict:
        snap = snaps.get()
        if not snap:
            st = snaps.status()
            if not st.get("refreshing"):
                snaps.start_refresh()
            msg = st.get("error") or "Logo ve CRM verisi ilk kez hazırlanıyor; birkaç dakika sonra yeniden deneyin."
            raise HTTPException(status_code=503, detail={"code": "PRICING_WARMING", "message": msg})
        return snap

    def me(user: str) -> dict:
        return {"user": user, "canWrite": can(user, "ozellik:fiyatlama.yaz"),
                "approve": {r: can(user, S.approve_key(r)) for r in S.APPROVERS}}

    @app.get("/api/v1/pricing/overview")
    def pricing_overview(request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ses(request)
        snap = snaps.get()
        st = snaps.status()
        if not snap and not st.get("refreshing"):
            snaps.start_refresh()
        counts = S.list_analyses(engine, tenant)["counts"]
        waiting = [a for a in S.list_analyses(engine, tenant, status="onayda")["items"]]
        mine = me(user)
        todo = [a for a in waiting if (a["submittedBy"] or "").lower() != user.lower()
                and any(mine["approve"].get(r["role"]) and not any(x["role"] == r["role"] for x in a["approvals"])
                        for r in a["required"])]
        measured = None
        if snap:
            measured = {"dataEnd": snap.get("dataEnd"), "asOf": snap.get("asOf"), "copies": snap.get("copies"),
                        "channels": snap.get("channels"), "paper": snap.get("paper"),
                        "distribution": snap.get("distribution"), "discount": D.weighted_discount(snap),
                        "books": len(snap.get("books") or {}), "printedBooks": len(snap.get("prints") or {}),
                        "printInvoices": sum(len(v) for v in (snap.get("prints") or {}).values()),
                        "warnings": snap.get("warnings") or []}
        out = {"status": st, "measured": measured, "defaults": S.get_defaults(engine, tenant), "counts": counts,
               "toApprove": len(todo), "me": mine, "stages": S.STAGES, "approvers": S.APPROVERS,
               "required": {k: list(v) for k, v in S.REQUIRED.items()}, "fixedLabels": M.FIXED_LABELS}
        return P.bagla(out, lambda: K.for_overview(engine, tenant, snap, out, *dbs()))

    @app.post("/api/v1/pricing/refresh")
    def pricing_refresh(request: Request) -> dict[str, Any]:
        engine, _, user, _ = ses(request)
        started = snaps.start_refresh()
        audit(engine, user, "run", "pricing_snapshot", None, "Fiyatlama verisi", {"started": started})
        return {"started": started, "status": snaps.status()}

    @app.get("/api/v1/pricing/sources")
    def pricing_sources(request: Request) -> dict[str, Any]:
        ses(request)
        snap = snaps.get() or {}
        stats = snap.get("sources") or {}
        executed = snap.get("sql") or {}
        # Çalışmış metin yoksa (görüntü henüz kurulmadı) şablon gösterilmez: yer tutucusu kalmış SQL çalıştırılamaz.
        out = {"sources": [{"id": s.id, "connection": s.connection, "title": s.title, "description": s.description,
                            "sql": (executed.get(s.id) or [""])[0], "runs": len(executed.get(s.id) or []),
                            "stats": stats.get(s.id)} for s in SRC.SOURCES],
               "copies": snap.get("copies"), "dataEnd": snap.get("dataEnd"), "asOf": snap.get("asOf")}
        return P.bagla(out, lambda: K.for_sources(snap or None, *dbs()))

    @app.get("/api/v1/pricing/books")
    def pricing_books(request: Request, q: str = "") -> dict[str, Any]:
        ses(request)
        return D.search_books(need_snap(), q)

    @app.get("/api/v1/pricing/books/{code}")
    def pricing_book(code: str, request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ses(request)
        snap = need_snap()
        det = D.book_detail(snap, code)
        if not det:
            raise HTTPException(404, detail={"code": "PRICING", "message": "Bu stok koduyla kitap bulunamadı."})
        defaults = S.get_defaults(engine, tenant)
        det["suggested"] = D.suggested_inputs(snap, det["spec"], defaults)
        det["freelance"] = freelance_costs(engine, tenant, (det["book"] or {}).get("id"))
        det["quotes"] = production_quotes(engine, tenant, det["crmPrints"])
        det["analyses"] = S.list_analyses(engine, tenant, book=(det["book"] or {}).get("id"))["items"] \
            if (det["book"] or {}).get("id") else []
        det["market"] = S.market_list(engine, tenant, book=(det["book"] or {}).get("id"))["items"] \
            if (det["book"] or {}).get("id") else []
        return P.bagla(det, lambda: K.for_book(engine, tenant, snap, det, *dbs()))

    @app.post("/api/v1/pricing/suggest")
    def pricing_suggest(request: Request, body: dict[str, Any]) -> dict[str, Any]:
        """Stok kodu olmayan (yeni) kitap için: teknik özelliklerden öneri girdileri."""
        engine, tenant, _, _ = ses(request)
        spec = {k: body.get(k) for k in ("pages", "trim", "gsm", "binding", "vat", "code")}
        snap = need_snap()
        out = D.suggested_inputs(snap, spec, S.get_defaults(engine, tenant))
        return P.bagla(out, lambda: K.for_suggest(engine, tenant, snap, *dbs()))

    @app.get("/api/v1/pricing/comparables")
    def pricing_comparables(request: Request, pages: Optional[float] = None, binding: str = "", months: int = 12,
                            exclude: str = "") -> dict[str, Any]:
        ses(request)
        if months < 1 or months > 120:
            raise HTTPException(400, detail={"code": "PRICING", "message": "Ay 1 ile 120 arasında olmalı."})
        snap = need_snap()
        out = D.comparables(snap, pages, binding or None, months, exclude or None)
        return P.bagla(out, lambda: K.for_comparables(snap, *dbs()))

    @app.post("/api/v1/pricing/calc")
    def pricing_calc(request: Request, body: dict[str, Any]) -> dict[str, Any]:
        ses(request)
        snap = snaps.get()
        out = call(calculate, snap, body)
        return P.bagla(out, lambda: K.for_calc(snap, *dbs()))

    @app.get("/api/v1/pricing/actuals")
    def pricing_actuals(request: Request, q: str = "", since: Optional[int] = None, sort: str = "net",
                        offset: int = 0, limit: int = 100) -> dict[str, Any]:
        ses(request)
        snap = need_snap()
        out = D.actuals(snap, q=q, since_year=since, sort=sort)
        offset, limit = max(0, offset), max(1, limit)
        out["offset"], out["limit"] = offset, limit
        out["rows"] = out["rows"][offset:offset + limit]
        return P.bagla(out, lambda: K.for_actuals(snap, *dbs()))

    compare_cache = KS.Cache(lambda: D.cache_dir() / "compare.json")

    def compare_result(engine: Any, tenant: str, snap: dict) -> dict[str, Any]:
        """Eski kitap karşılaştırmasının güncel girdilerle sonucu (hazır değilse arka planda başlar)."""
        defaults = S.get_defaults(engine, tenant)
        tariff = S.get_form_tariff(engine, tenant)
        kur = snap_kur(snap, tariff)
        fl, mk = freelance_all(engine, tenant), market_all(engine, tenant)
        key = KS.fingerprint(snap, defaults, tariff, kur, fl, mk)
        got = compare_cache.get(key, lambda: KS.compare_all(snap, defaults=defaults, tariff=tariff, kur=kur, freelance=fl,
                                                            market=mk, calculate=calculate))
        got["kurKaynak"] = tariff.get("kurKaynak") or "logo"
        got["kur"] = kur or tariff.get("kur")
        return got

    def compare_select(engine: Any, tenant: str, got: dict, q: str, status: str, new: bool, min_sold: float, sort: str,
                       entered: bool = False, group: str = "") -> Optional[dict]:
        if status and status not in KS.STATUS:
            raise HTTPException(400, detail={"code": "PRICING", "message": "Durum zam, yuksek, esit ya da hesaplanamadi olmalı."})
        res = got.get("result")
        return KS.select(res, q=q, status=status, new=new, min_sold=max(0.0, min_sold), sort=sort,
                         manual=S.backlist_prices(engine, tenant), entered=entered, group=group) if res else None

    @app.get("/api/v1/pricing/compare")
    def pricing_compare(request: Request, q: str = "", status: str = "", new: bool = False, minSold: float = 0.0,  # noqa: N803
                        sort: str = "diffPct", offset: int = 0, limit: int = 100, entered: bool = False,
                        group: str = "") -> dict[str, Any]:
        engine, tenant, _, _ = ses(request)
        snap = need_snap()
        got = compare_result(engine, tenant, snap)
        sel = compare_select(engine, tenant, got, q, status, new, minSold, sort, entered, group)
        res = got.get("result") or {}
        offset, limit = max(0, offset), max(1, limit)
        out = {"ready": got["ready"], "stale": got["stale"], "error": got.get("error"), "startedAt": got.get("startedAt"),
               "kur": got["kur"], "kurKaynak": got["kurKaynak"], "logoKur": snap.get("kur") or {},
               "dataEnd": res.get("dataEnd"), "since": res.get("since"), "targetMargin": res.get("targetMargin"),
               "seconds": res.get("seconds"), "offset": offset, "limit": limit,
               # Grup listesi özet (seçim kutusu); basamaklar yalnız seçilen grubun (yanıt her 3 sn'de bir sorulabiliyor).
               "groups": [{k: v for k, v in g.items() if k != "steps"} | {"stepCount": len(g.get("steps") or [])}
                          for g in res.get("groups") or []],
               "ladder": next((g for g in res.get("groups") or [] if group and g["key"] == group), None)}
        if sel:
            out.update({k: v for k, v in sel.items() if k != "rows"}, rows=sel["rows"][offset:offset + limit])
        return P.bagla(out, lambda: K.for_compare(snap, *dbs(), engine, tenant))

    @app.put("/api/v1/pricing/backlist-prices")
    def pricing_backlist_prices(request: Request, body: dict[str, Any]) -> dict[str, Any]:
        """Eski kitap fiyat çalışması: kitap başına elle yeni kapak fiyatı (boş = sil). CRM'e yazılmaz."""
        engine, tenant, user, _ = ses(request)
        books = need_snap().get("books") or {}
        items = body.get("items") if isinstance(body.get("items"), list) else []
        unknown = [str(i.get("code")) for i in items if isinstance(i, dict) and str(i.get("code") or "") not in books]
        if unknown:
            raise HTTPException(400, detail={"code": "PRICING", "message": f"Bu stok kodları bulunamadı: {', '.join(unknown[:5])}"})
        out = call(S.set_backlist_prices, engine, tenant, user, [i for i in items if isinstance(i, dict)])
        audit(engine, user, "update", "pricing_backlist_price", tenant, "Eski kitap yeni fiyatı",
              {"yazilan": out["written"], "silinen": out["removed"],
               "kitaplar": [{"kod": i.get("code"), "fiyat": i.get("price")} for i in items[:50]]})
        return out

    @app.get("/api/v1/pricing/compare.csv")
    def pricing_compare_csv(request: Request, q: str = "", status: str = "", new: bool = False, minSold: float = 0.0,  # noqa: N803
                            sort: str = "diffPct", entered: bool = False, group: str = ""):
        from fastapi.responses import Response
        engine, tenant, user, _ = ses(request)
        got = compare_result(engine, tenant, need_snap())
        sel = compare_select(engine, tenant, got, q, status, new, minSold, sort, entered, group)
        if not sel:
            raise HTTPException(409, detail={"code": "PRICING_WARMING", "message": "Karşılaştırma hesaplanıyor; biraz sonra yeniden deneyin."})
        audit(engine, user, "export", "pricing_compare", tenant, "Eski kitap fiyat karşılaştırması", {"satir": len(sel["rows"])})
        return Response(compare_csv(sel["rows"]).encode("utf-8"), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": 'attachment; filename="eski-kitap-fiyatlari.csv"'})

    # ---- analizler
    @app.get("/api/v1/pricing/analyses")
    def pricing_analyses(request: Request, status: str = "", q: str = "") -> dict[str, Any]:
        engine, tenant, _, _ = ses(request)
        out = S.list_analyses(engine, tenant, status=status or None, q=q)
        return P.bagla(out, lambda: K.for_analyses(engine, tenant, status=status, q=q))

    @app.post("/api/v1/pricing/analyses", status_code=201)
    def pricing_analysis_create(request: Request, body: dict[str, Any]) -> dict[str, Any]:
        engine, tenant, user, _ = ses(request)
        out = call(S.create_analysis, engine, tenant, user, body)
        audit(engine, user, "create", "pricing_analysis", out["id"], out["title"], {"stage": out["stage"]})
        return out

    @app.get("/api/v1/pricing/analyses/{aid}")
    def pricing_analysis(aid: str, request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ses(request)
        out = call(S.get_analysis, engine, tenant, aid)
        return P.bagla(out, lambda: K.for_analysis(engine, tenant, aid))

    @app.patch("/api/v1/pricing/analyses/{aid}")
    def pricing_analysis_update(aid: str, request: Request, body: dict[str, Any]) -> dict[str, Any]:
        engine, tenant, user, _ = ses(request)
        before = call(S.get_analysis, engine, tenant, aid)
        out = call(S.update_analysis, engine, tenant, user, aid, body)
        changed = {k: {"once": before.get(k), "sonra": out.get(k)} for k in ("title", "stage", "chosenPrice", "chosenQty")
                   if before.get(k) != out.get(k)}
        audit(engine, user, "update", "pricing_analysis", aid, out["title"], changed or sorted(body.keys()))
        return out

    @app.post("/api/v1/pricing/analyses/{aid}/submit")
    def pricing_analysis_submit(aid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ses(request)
        cur = call(S.get_analysis, engine, tenant, aid)
        # Onaya giden sonuç sunucuda yeniden hesaplanır: ekranın gönderdiği sayı değil, kayıtlı girdiler dondurulur.
        inputs = {**(cur["inputs"] or {}), "price": cur["chosenPrice"], "chosenQty": cur["chosenQty"]}
        result = call(calculate, snaps.get(), {"inputs": inputs, "spec": cur["specs"],
                                               "marketPrices": [m["price"] for m in cur.get("market") or []]})
        result["dataEnd"] = (snaps.get() or {}).get("dataEnd")
        out = call(S.submit, engine, tenant, user, aid, result)
        audit(engine, user, "run", "pricing_analysis", aid, out["title"],
              {"islem": "onaya gönderildi", "fiyat": out["chosenPrice"], "adet": out["chosenQty"], "surum": out["version"]})
        return out

    @app.post("/api/v1/pricing/analyses/{aid}/withdraw")
    def pricing_analysis_withdraw(aid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ses(request)
        out = call(S.withdraw, engine, tenant, user, aid)
        audit(engine, user, "update", "pricing_analysis", aid, out["title"], {"islem": "taslağa alındı"})
        return out

    @app.post("/api/v1/pricing/analyses/{aid}/archive")
    def pricing_analysis_archive(aid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ses(request)
        out = call(S.archive, engine, tenant, user, aid)
        audit(engine, user, "delete", "pricing_analysis", aid, out["title"], {"islem": "arşiv"})
        return out

    @app.post("/api/v1/pricing/analyses/{aid}/decide")
    def pricing_analysis_decide(aid: str, request: Request, body: dict[str, Any]) -> dict[str, Any]:
        engine, tenant, user, _ = ses(request)
        role = str(body.get("role") or "")
        out = call(S.decide, engine, tenant, user, aid, role, str(body.get("decision") or ""), str(body.get("note") or ""),
                   int(body.get("version") or 0), can(user, S.approve_key(role)) if role in S.APPROVERS else False)
        audit(engine, user, "approve" if body.get("decision") == "onay" else "reject", "pricing_analysis", aid,
              out["title"], {"rol": S.APPROVERS.get(role), "surum": out["version"], "durum": out["statusLabel"]})
        return out

    # ---- dağıtımcı kataloğundan pazar fiyatı (M39 portal tabloları; Logo görüntüsü gerekmez)
    @app.get("/api/v1/pricing/distributor")
    def pricing_distributor(request: Request, code: str = "", kategori: str = "", pages: Optional[float] = None,
                            kapak: str = "") -> dict[str, Any]:
        """Kitabın kategorisinde TİMAŞ dışı başlıkların liste fiyatı dağılımı. `kategori` verilirse o Başarı kategorisi
        (tam yol ya da üst kategori); sayfa ve kapak verilmezse kitabın künyesinden."""
        from semantic_bridge.pricing import dagitim as DG
        engine, tenant, _, _ = ses(request)
        snap = snaps.get()
        det = D.book_detail(snap, code) if (snap and code) else None
        spec = (det or {}).get("spec") or {}
        out = DG.suggest(engine, tenant, code=code or None, kategori=kategori.strip() or None,
                         library=((det or {}).get("book") or {}).get("library"),
                         pages=pages if pages and pages > 0 else spec.get("pages"), kapak=kapak or spec.get("binding"))
        return P.bagla(out, lambda: K.for_distributor(engine, tenant, out))

    @app.get("/api/v1/pricing/distributor/categories")
    def pricing_distributor_categories(request: Request) -> dict[str, Any]:
        from semantic_bridge.pricing import dagitim as DG
        engine, tenant, _, _ = ses(request)
        out = DG.categories(engine, tenant)
        return P.bagla(out, lambda: K.for_distributor_categories(engine, tenant, out))

    # ---- pazar fiyatları
    @app.post("/api/v1/pricing/market", status_code=201)
    def pricing_market_add(request: Request, body: dict[str, Any]) -> dict[str, Any]:
        engine, tenant, user, _ = ses(request)
        out = call(S.market_add, engine, tenant, user, body)
        audit(engine, user, "create", "pricing_market", out["id"], str(body.get("title") or "")[:200],
              {"fiyat": body.get("price")})
        return out

    @app.delete("/api/v1/pricing/market/{mid}")
    def pricing_market_delete(mid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ses(request)
        out = call(S.market_delete, engine, tenant, user, mid, is_admin(user))
        audit(engine, user, "delete", "pricing_market", mid, out["title"], None)
        return out

    @app.put("/api/v1/pricing/defaults")
    def pricing_defaults(request: Request, body: dict[str, Any]) -> dict[str, Any]:
        engine, tenant, user, _ = ses(request)
        before = S.get_defaults(engine, tenant)
        out = call(S.save_defaults, engine, tenant, user, body)
        audit(engine, user, "update", "pricing_defaults", tenant, "Fiyatlama varsayılanları",
              {k: {"once": before.get(k), "sonra": out.get(k)} for k in S.BASE_DEFAULTS if before.get(k) != out.get(k)})
        return out

    # ---- maliyet formu (TİMAŞ basım Excel'iyle aynı hesap)
    def form_call(fn, *a, **kw):
        from semantic_bridge.pricing import form as F
        try:
            return fn(*a, **kw)
        except F.FormError as e:
            raise HTTPException(status_code=400, detail={"code": "PRICING_FORM", "message": str(e)}) from e

    def snap_kur(snap: Optional[dict], tariff: dict) -> Optional[dict]:
        """Formun kuru: fiyat listesinde «elle» seçildiyse None (hesap listedeki kuru kullanır), değilse Logo faturalarının
        son kuru (Logo'da o dövizle fatura yoksa yine listedeki kur)."""
        if tariff.get("kurKaynak") == "elle":
            return None
        k = (snap or {}).get("kur") or {}
        return {c: v["rate"] for c, v in k.items() if (v or {}).get("rate")} or None

    @app.get("/api/v1/pricing/form/setup")
    def pricing_form_setup(request: Request, kitap: str = "") -> dict[str, Any]:
        """Formun seçenekleri (tarife), başlangıç girdileri (yeni kitap ya da `kitap` stok kodundan), Logo kuru ve kâğıt fiyatları."""
        from semantic_bridge.pricing import form as F
        engine, tenant, user, _ = ses(request)
        snap = snaps.get()
        tariff = S.get_form_tariff(engine, tenant)
        kur = snap_kur(snap, tariff)
        start = {"inputs": F.blank_inputs(tariff, kur=kur), "origin": {}}
        if kitap:
            det = D.book_detail(need_snap(), kitap)
            if not det:
                raise HTTPException(404, detail={"code": "PRICING", "message": "Bu stok koduyla kitap bulunamadı."})
            start = F.from_book(det, tariff, kur=kur)
            start["book"] = {k: (det.get("book") or {}).get(k) for k in ("code", "name", "author", "publisher", "price", "pages", "trim")}
            start["book"]["lastPrint"] = (det.get("prints") or [None])[-1]
            start["book"]["logoUnitCost"] = (det.get("total") or {}).get("unitCost")
        out = {"tariff": tariff, "bindings": list(F.BINDINGS), "laminates": list(F.LAMINATES), "varnishes": list(F.VARNISHES),
               "extras": {k: {"row": v[0], "label": v[1], "kind": v[7]} for k, v in F.EXTRAS.items()},
               "logoKur": (snap or {}).get("kur") or {}, "paper": (snap or {}).get("paper"), "dataEnd": (snap or {}).get("dataEnd"),
               "canWrite": can(user, "ozellik:fiyatlama.yaz"), **start}
        out["paperSource"] = "logo"
        return P.bagla(out, lambda: K.for_form(engine, tenant, snap, out, *dbs()))

    @app.post("/api/v1/pricing/form/calc")
    def pricing_form_calc(request: Request, body: dict[str, Any]) -> dict[str, Any]:
        """Kitap hesabının maliyet kısmı (basım Excel'iyle aynı kurallar). Kâğıt Logo alışından; `paperSource: "tarife"`
        ve `tariff` yalnız kabul içindir (Excel'in kendi fiyatlarıyla birebir karşılaştırma)."""
        from semantic_bridge.pricing import form as F
        engine, tenant, _, _ = ses(request)
        snap = snaps.get()
        tariff = body.get("tariff") if isinstance(body.get("tariff"), dict) else S.get_form_tariff(engine, tenant)
        src = body.get("paperSource") if body.get("paperSource") in ("logo", "tarife") else "logo"
        inputs = body.get("inputs") or {}
        paper = (snap or {}).get("paper")
        out = form_call(F.compute, inputs, tariff, paper_source=src, snap_paper=paper)
        try:
            out["analysis"] = F.to_analysis(inputs, tariff, paper_source=src, snap_paper=paper)
        except F.FormError:
            out["analysis"] = None
        out["dataEnd"] = (snap or {}).get("dataEnd")
        return P.bagla(out, lambda: K.for_form(engine, tenant, snap, out, *dbs()))

    @app.put("/api/v1/pricing/form/tariff")
    def pricing_form_tariff(request: Request, body: dict[str, Any]) -> dict[str, Any]:
        engine, tenant, user, _ = ses(request)
        if not can(user, "ozellik:fiyatlama.yaz"):
            raise HTTPException(403, detail={"code": "PRICING", "message": "Fiyat listesini değiştirmek «Fiyat analizi hazırlama» yetkisi ister."})
        reset = bool(body.get("reset"))
        before = S.get_form_tariff(engine, tenant)
        out = call(S.reset_form_tariff, engine, tenant) if reset else call(S.save_form_tariff, engine, tenant, user, body)
        keys = ("kur", "kurKaynak", "vade", "papers", "prices", "fire", "dolayli", "kapakBolen", "publishers", "dijital")
        audit(engine, user, "update", "pricing_form_tariff", tenant, "Matbaa ve malzeme fiyat listesi",
              {"sifirla": reset} if reset else {k: "değişti" for k in keys if before.get(k) != out.get(k)})
        return out

    # ---- backlist toplu zam teklifi
    @app.get("/api/v1/pricing/proposals")
    def pricing_proposals(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ses(request)
        out = S.proposal_list(engine, tenant)
        return P.bagla(out, lambda: K.for_proposals(engine, tenant))

    @app.post("/api/v1/pricing/proposals", status_code=201)
    def pricing_proposal_create(request: Request, body: dict[str, Any]) -> dict[str, Any]:
        engine, tenant, user, _ = ses(request)
        snap = need_snap()
        codes = {str(c) for c in (body.get("codes") or [])}
        if not codes:
            raise HTTPException(400, detail={"code": "PRICING", "message": "Teklife en az bir kitap seçin."})
        got = compare_result(engine, tenant, snap)
        if not got["ready"]:
            raise HTTPException(409, detail={"code": "PRICING_WARMING", "message": "Fiyatlar güncel girdilerle yeniden "
                                             "hesaplanıyor; bir dakika sonra teklifi yeniden oluşturun."})
        # Teklif sunucudaki son hesaptan dondurulur; ekrandan yalnız seçilen kodlar gelir.
        res = got["result"]
        manual = S.backlist_prices(engine, tenant)
        items = []
        for r0 in res["rows"]:
            if r0["code"] not in codes:
                continue
            r = KS.with_manual(r0, manual.get(r0["code"]))
            # Kullanıcının yazdığı yeni fiyat varsa teklif odur; yoksa bizim hesap.
            proposed = r.get("newPrice") if r.get("newPrice") is not None else r.get("ours")
            if not proposed:
                continue
            items.append({"code": r["code"], "name": r["name"], "price": r["price"], "proposed": proposed,
                          "source": "elle" if r.get("newPrice") is not None else "hesap", "ours": r.get("ours"),
                          "increase": round(proposed / r["price"] - 1, 4) if r.get("price") else None,
                          "unit": r.get("unitCost"), "qty": r.get("qty"), "margin": r.get("margin"), "sold2y": r["sold2y"],
                          "stock": r.get("stock"), "lastPrintDate": r.get("lastPrintDate") or r.get("lastPrint")})
        out = call(S.proposal_create, engine, tenant, user, str(body.get("title") or ""), items,
                   {"method": "kitap-hesabi", "manual": sum(1 for i in items if i["source"] == "elle"),
                    "targetMargin": res["targetMargin"], "kur": got["kur"],
                    "kurKaynak": got["kurKaynak"], "dataEnd": res["dataEnd"]})
        audit(engine, user, "create", "pricing_proposal", out["id"], out["title"], {"kitap": out["count"]})
        return out

    @app.get("/api/v1/pricing/proposals/{pid}")
    def pricing_proposal(pid: str, request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ses(request)
        out = call(S.proposal_get, engine, tenant, pid)
        return P.bagla(out, lambda: K.for_proposals(engine, tenant, pid))

    @app.post("/api/v1/pricing/proposals/{pid}/decide")
    def pricing_proposal_decide(pid: str, request: Request, body: dict[str, Any]) -> dict[str, Any]:
        engine, tenant, user, _ = ses(request)
        out = call(S.proposal_decide, engine, tenant, user, pid, str(body.get("decision") or ""),
                   str(body.get("note") or ""), can(user, S.approve_key("mali")))
        audit(engine, user, "approve" if body.get("decision") == "onay" else "reject", "pricing_proposal", pid,
              out["title"], {"kitap": out["count"]})
        return out

    return snaps
