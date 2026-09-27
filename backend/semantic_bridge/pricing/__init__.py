"""Fiyatlama ve Maliyet Analizi (M9): kitap bazlı maliyet (kâğıt, baskı, telif, çeviri, grafik…), başabaş, kapak fiyatı
önerisi, baskı adedi senaryoları, kanal fiyat matrisi, gerçekleşen maliyet/marj (Logo) ve backlist fiyat revizyonu.

- `model`: saf hesap (birim maliyetin tek sahibi; M10/M12/M46 buradan çağırır).
- `sources` + `data`: Logo/CRM'den salt okunur anlık görüntü ve üstündeki hesaplar.
- `store`: analizler, onaylar, elle girilen pazar fiyatları, varsayılanlar, toplu zam teklifleri (kendi tablolarımız).

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


def calculate(snap: Optional[dict], body: dict[str, Any]) -> dict[str, Any]:
    """Senaryo tablosu + fiyat önerisi + kanal matrisi. Emsal fiyatları görüntüden (ve elle girilen pazar fiyatlarından)."""
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
        comp = D.comparables(snap, pages, spec.get("binding") or None, exclude=spec.get("code"))
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


def freelance_costs(engine: Any, tenant: str, book_id: Optional[str]) -> dict[str, Any]:
    """M8'de bu kitaba açılmış iş paketlerinin tutarı (iptal hariç), maliyet kalemine göre. Tablo yoksa boş."""
    if not book_id:
        return {"items": [], "byKey": {}}
    try:
        import sqlalchemy as sa
        from semantic_bridge import freelance as fl
        with engine.connect() as c:
            rows = c.execute(
                sa.select(fl.TASKS.c.role, fl.TASKS.c.status, fl.TASKS.c.units, fl.TASKS.c.unit_price, fl.PACKAGES.c.title)
                .join(fl.PACKAGES, fl.PACKAGES.c.id == fl.TASKS.c.package_id)
                .where(fl.TASKS.c.tenant_id == tenant, fl.PACKAGES.c.book_id == book_id.lower(),
                       fl.PACKAGES.c.status != "iptal", fl.TASKS.c.status != "iptal")).all()
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
        return {"status": st, "measured": measured, "defaults": S.get_defaults(engine, tenant), "counts": counts,
                "toApprove": len(todo), "me": mine, "stages": S.STAGES, "approvers": S.APPROVERS,
                "required": {k: list(v) for k, v in S.REQUIRED.items()}, "fixedLabels": M.FIXED_LABELS}

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
        return {"sources": [{"id": s.id, "connection": s.connection, "title": s.title, "description": s.description,
                             "sql": (executed.get(s.id) or [s.sql])[0], "runs": len(executed.get(s.id) or []),
                             "stats": stats.get(s.id)} for s in SRC.SOURCES],
                "copies": snap.get("copies"), "dataEnd": snap.get("dataEnd"), "asOf": snap.get("asOf")}

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
        det["analyses"] = S.list_analyses(engine, tenant, book=(det["book"] or {}).get("id"))["items"] \
            if (det["book"] or {}).get("id") else []
        det["market"] = S.market_list(engine, tenant, book=(det["book"] or {}).get("id"))["items"] \
            if (det["book"] or {}).get("id") else []
        return det

    @app.post("/api/v1/pricing/suggest")
    def pricing_suggest(request: Request, body: dict[str, Any]) -> dict[str, Any]:
        """Stok kodu olmayan (yeni) kitap için: teknik özelliklerden öneri girdileri."""
        engine, tenant, _, _ = ses(request)
        spec = {k: body.get(k) for k in ("pages", "trim", "gsm", "binding", "vat", "code")}
        return D.suggested_inputs(need_snap(), spec, S.get_defaults(engine, tenant))

    @app.get("/api/v1/pricing/comparables")
    def pricing_comparables(request: Request, pages: Optional[float] = None, binding: str = "", months: int = 12,
                            exclude: str = "") -> dict[str, Any]:
        ses(request)
        if months < 1 or months > 120:
            raise HTTPException(400, detail={"code": "PRICING", "message": "Ay 1 ile 120 arasında olmalı."})
        return D.comparables(need_snap(), pages, binding or None, months, exclude or None)

    @app.post("/api/v1/pricing/calc")
    def pricing_calc(request: Request, body: dict[str, Any]) -> dict[str, Any]:
        ses(request)
        return call(calculate, snaps.get(), body)

    @app.get("/api/v1/pricing/actuals")
    def pricing_actuals(request: Request, q: str = "", since: Optional[int] = None, sort: str = "net",
                        offset: int = 0, limit: int = 100) -> dict[str, Any]:
        ses(request)
        out = D.actuals(need_snap(), q=q, since_year=since, sort=sort)
        offset, limit = max(0, offset), max(1, limit)
        out["offset"], out["limit"] = offset, limit
        out["rows"] = out["rows"][offset:offset + limit]
        return out

    @app.get("/api/v1/pricing/backlist")
    def pricing_backlist(request: Request, target: Optional[float] = None, minSold: float = 1.0) -> dict[str, Any]:  # noqa: N803
        ses(request)
        if target is not None and not 0 < target < 1:
            raise HTTPException(400, detail={"code": "PRICING", "message": "Hedef oran 0 ile 1 arasında olmalı."})
        return D.backlist(need_snap(), target_ratio=target, min_sold=minSold)

    # ---- analizler
    @app.get("/api/v1/pricing/analyses")
    def pricing_analyses(request: Request, status: str = "", q: str = "") -> dict[str, Any]:
        engine, tenant, _, _ = ses(request)
        return S.list_analyses(engine, tenant, status=status or None, q=q)

    @app.post("/api/v1/pricing/analyses", status_code=201)
    def pricing_analysis_create(request: Request, body: dict[str, Any]) -> dict[str, Any]:
        engine, tenant, user, _ = ses(request)
        out = call(S.create_analysis, engine, tenant, user, body)
        audit(engine, user, "create", "pricing_analysis", out["id"], out["title"], {"stage": out["stage"]})
        return out

    @app.get("/api/v1/pricing/analyses/{aid}")
    def pricing_analysis(aid: str, request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ses(request)
        return call(S.get_analysis, engine, tenant, aid)

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

    # ---- backlist toplu zam teklifi
    @app.get("/api/v1/pricing/proposals")
    def pricing_proposals(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ses(request)
        return S.proposal_list(engine, tenant)

    @app.post("/api/v1/pricing/proposals", status_code=201)
    def pricing_proposal_create(request: Request, body: dict[str, Any]) -> dict[str, Any]:
        engine, tenant, user, _ = ses(request)
        snap = need_snap()
        codes = {str(c) for c in (body.get("codes") or [])}
        target = body.get("target")
        bl = D.backlist(snap, target_ratio=float(target) if target else None, min_sold=float(body.get("minSold") or 1))
        # Teklif sunucuda yeniden hesaplanır; ekrandan yalnız seçilen kodlar gelir.
        items = [{k: r[k] for k in ("code", "name", "price", "proposed", "increase", "ratio", "unit", "sold2y",
                                    "lastPrintDate")} for r in bl["rows"] if not codes or r["code"] in codes]
        out = call(S.proposal_create, engine, tenant, user, str(body.get("title") or ""), items,
                   {"target": bl["target"], "measuredTarget": bl["measuredTarget"], "dataEnd": bl["dataEnd"]})
        audit(engine, user, "create", "pricing_proposal", out["id"], out["title"], {"kitap": out["count"]})
        return out

    @app.get("/api/v1/pricing/proposals/{pid}")
    def pricing_proposal(pid: str, request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ses(request)
        return call(S.proposal_get, engine, tenant, pid)

    @app.post("/api/v1/pricing/proposals/{pid}/decide")
    def pricing_proposal_decide(pid: str, request: Request, body: dict[str, Any]) -> dict[str, Any]:
        engine, tenant, user, _ = ses(request)
        out = call(S.proposal_decide, engine, tenant, user, pid, str(body.get("decision") or ""),
                   str(body.get("note") or ""), can(user, S.approve_key("mali")))
        audit(engine, user, "approve" if body.get("decision") == "onay" else "reject", "pricing_proposal", pid,
              out["title"], {"kitap": out["count"]})
        return out

    return snaps
