"""M6 Sözleşmeler: köprü uçları (`/api/v1/editorial/contracts/...`).

Okuma sayfa yetkisiyle (`sayfa:telif-sozlesme`) açıktır. Yazan işlemler açıkça verilen yetki ister; «Bütün
sayfalar ve işlemler» bunları getirmez (M6 bugüne kadar salt okunurdu, kimsenin yetkisi kendiliğinden
genişlemez):

    ozellik:sozlesme.duzenle   taslak aç, şart/metin/durum düzenle, zeyilname, ödeme planı
    ozellik:sozlesme.hakedis   hakediş hesapla/onayla/iptal, ödemeyi ödendi işaretle
    ozellik:sozlesme.sablon    şablon kütüphanesini düzenle

Hakediş Logo'dan okur (yıllık satış görünümleri, döviz kuru); CRM okuması köprünün `run_sql` yolundan geçer.
"""
from __future__ import annotations

import logging
import threading
from datetime import date, timedelta
from typing import Any, Callable, Optional
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from semantic_bridge import contracts as C
from semantic_bridge import contracts_docs as D
from semantic_bridge import contracts_kaynak as K
from semantic_bridge import provenance as P
from semantic_bridge import contracts_royalty as R
from semantic_bridge import contracts_terms as T

log = logging.getLogger("semantic.contracts")

EDIT = "ozellik:sozlesme.duzenle"
FINANCE = "ozellik:sozlesme.hakedis"
TEMPLATE = "ozellik:sozlesme.sablon"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def register(app: FastAPI, *, rt: Callable[[], Any], greetings: Callable[[Request], tuple], can: Callable[[str, str], bool],
             editorial: Callable[[Request], tuple[str, Callable[[str], dict]]], crm_prefix: Callable[[str], str],
             audit: Callable[..., None]) -> None:

    def session(request: Request) -> tuple[Any, str, str]:
        engine, tenant, user, _ = greetings(request)
        C.ensure(engine)
        return engine, tenant, user

    def need(user: str, key: str) -> None:
        if not can(user, key):
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "Bu işlem rolünüzde yok."})

    def call(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except T.ContractError as e:
            raise HTTPException(status_code=e.status, detail={"code": "CONTRACT", "message": str(e)}) from e

    def crm_loader(request: Request, qlog: Optional[K.Kayit] = None) -> Callable[[str], Optional[dict[str, Any]]]:
        schema, run = editorial(request)
        if qlog is not None:
            run = qlog.res(run, "crm")  # sorgu bilgisi: çalışan metin, satır, süre

        def load(crm_id: str) -> Optional[dict[str, Any]]:
            head_sql, books_sql, parties_sql = C.crm_contract_sql(crm_prefix(schema), crm_id)
            head = (run(head_sql).get("records") or [])
            if not head:
                return None
            out = C.crm_contract(head[0], run(books_sql).get("records") or [], run(parties_sql).get("records") or [])
            parent = C.parent_of(head[0])
            try:
                out["related"] = C.related(run(C.related_sql(crm_prefix(schema), crm_id, parent)).get("records") or [], parent)
            except Exception as e:  # noqa: BLE001 — bağlı kayıtlar okunamazsa sözleşme yine açılır
                log.warning("contracts: bağlı CRM sözleşmeleri okunamadı (%s): %s", crm_id, e)
                out["related"] = []
            return out

        return load

    def record_key(engine, tenant, user, request: Request, key: str) -> str:
        """Yazan işlemden önce: CRM kimliği verildiyse kayıt portala alınır (bir kez)."""
        if C.is_crm_id(key) and not C.find(engine, tenant, key):
            crm = crm_loader(request)(key)
            if crm is None:
                raise HTTPException(status_code=404, detail={"code": "CONTRACT", "message": "Sözleşme CRM'de bulunamadı."})
            rec = C.adopt_crm(engine, tenant, user, key, crm)
            audit(engine, user, "create", "contract", rec["id"], rec["no"], {"crmId": key})
            return rec["id"]
        return key

    def caps(user: str) -> dict[str, bool]:
        return {"edit": can(user, EDIT), "finance": can(user, FINANCE), "templates": can(user, TEMPLATE)}

    # ------------------------------------------------------------------ okuma

    @app.get("/api/v1/editorial/contracts/meta")
    def contracts_meta(request: Request) -> dict[str, Any]:
        engine, tenant, user = session(request)
        return {"can": caps(user), "kinds": T.KINDS, "paymentTypes": T.PAYMENT_TYPES, "bases": T.BASES,
                "currencies": T.CURRENCIES, "statuses": T.STATUSES, "transitions": T.TRANSITIONS, "freeEdit": list(T.FREE_EDIT),
                "rates": T.RATE_KEYS, "rights": T.RIGHT_KEYS, "partyRoles": T.PARTY_ROLES, "labels": T.LABELS,
                "salesBased": list(T.SALES_BASED), "printBased": list(T.PRINT_BASED), "tiered": list(T.TIERED),
                "paymentKinds": C.PAYMENT_KINDS, "paymentStatuses": C.PAYMENT_STATUSES,
                "templateFields": D.FIELDS, "templateTargets": D.TARGETS}

    def logo_db() -> Optional[str]:
        return P.connection_database(rt().settings.connection_file)

    @app.get("/api/v1/editorial/contracts/records")
    def contracts_records(request: Request, q: str = "", status: str = "", source: str = "") -> dict[str, Any]:
        engine, tenant, _ = session(request)
        out = {"items": call(C.list_records, engine, tenant, q=q, status=status, source=source)}
        return P.bagla(out, lambda: K.for_records(engine, tenant, out, status=status, source=source))

    @app.get("/api/v1/editorial/contracts/item/{key}")
    def contract_detail(key: str, request: Request) -> dict[str, Any]:
        engine, tenant, user = session(request)
        qlog = K.Kayit()
        out = call(C.detail, engine, tenant, key, crm_loader(request, qlog))
        out["can"] = caps(user)
        return P.bagla(out, lambda: K.for_detail(engine, tenant, out, qlog, crm_prefix(editorial(request)[0]), logo_db()))

    @app.get("/api/v1/editorial/contracts/payments")
    def contracts_due(request: Request, status: str = "planlandi", within: Optional[int] = None, kind: str = "") -> dict[str, Any]:
        engine, tenant, user = session(request)
        out = dict(call(C.due_list, engine, tenant, status=status, within=within, kind=kind), can=caps(user))
        return P.bagla(out, lambda: K.for_due(engine, tenant, out, status=status, within=within, kind=kind))

    @app.get("/api/v1/editorial/contracts/lookup/books")
    def lookup_books(request: Request, q: str = "", page: int = 0) -> dict[str, Any]:
        session(request)
        schema, run = editorial(request)
        qlog = K.Kayit()
        rows = qlog.res(run)(call(C.book_lookup_sql, crm_prefix(schema), q, page)).get("records") or []
        out = {"items": C._crm_books(rows), **C.lookup_page(rows, page)}
        return P.bagla(out, lambda: K.for_lookup(qlog, crm_prefix(schema), out))

    @app.get("/api/v1/editorial/contracts/lookup/parties")
    def lookup_parties(request: Request, q: str = "", page: int = 0) -> dict[str, Any]:
        session(request)
        schema, run = editorial(request)
        qlog = K.Kayit()
        rows = qlog.res(run)(call(C.party_lookup_sql, crm_prefix(schema), q, page)).get("records") or []
        out = {"items": [{"type": str(r.get("tur")), "id": str(r.get("id") or ""), "name": str(r.get("ad") or "").strip()}
                         for r in rows], **C.lookup_page(rows, page)}
        return P.bagla(out, lambda: K.for_lookup(qlog, crm_prefix(schema), out))

    # ------------------------------------------------------------------ kayıt

    @app.post("/api/v1/editorial/contracts/drafts")
    def contract_create(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user = session(request)
        need(user, EDIT)
        rec = call(C.create_draft, engine, tenant, user, body)
        audit(engine, user, "create", "contract", rec["id"], rec["no"], {"title": rec["terms"].get("title")})
        return rec

    @app.patch("/api/v1/editorial/contracts/item/{key}")
    def contract_update(key: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user = session(request)
        need(user, EDIT)
        rid = record_key(engine, tenant, user, request, key)
        before = C.find(engine, tenant, rid)
        rec = call(C.update_terms, engine, tenant, user, rid, body)
        audit(engine, user, "update", "contract", rec["id"], rec["no"],
              {"changes": T.diff((before or {}).get("terms") or {}, rec["terms"]), "reason": body.get("reason")})
        return rec

    @app.post("/api/v1/editorial/contracts/item/{key}/status")
    def contract_status(key: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user = session(request)
        need(user, EDIT)
        rid = record_key(engine, tenant, user, request, key)
        rec = call(C.set_status, engine, tenant, user, rid, body)
        audit(engine, user, "status", "contract", rec["id"], rec["no"], {"status": rec["status"], "note": body.get("note")})
        return rec

    @app.put("/api/v1/editorial/contracts/item/{key}/body")
    def contract_body(key: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user = session(request)
        need(user, EDIT)
        rec = call(C.set_body, engine, tenant, user, key, body)
        audit(engine, user, "update", "contract", rec["id"], rec["no"], {"body": len(rec.get("body") or "")})
        return rec

    @app.post("/api/v1/editorial/contracts/item/{key}/render")
    def contract_render(key: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user = session(request)
        need(user, EDIT)
        rec = call(C.render_body, engine, tenant, user, key, str(body.get("templateId") or ""))
        audit(engine, user, "update", "contract", rec["id"], rec["no"], {"template": rec.get("templateId")})
        return rec

    def _docx(data: bytes, name: str, missing: list[str]) -> Response:
        headers = {"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"}
        if missing:
            headers["X-Missing-Fields"] = ",".join(missing)[:1000]
        return Response(content=data, media_type=DOCX, headers=headers)

    @app.get("/api/v1/editorial/contracts/item/{key}/document.docx")
    def contract_document(key: str, request: Request, template: str = "") -> Response:
        engine, tenant, user = session(request)
        data, name, missing = call(C.document, engine, tenant, "sozlesme", key, template)
        audit(engine, user, "export", "contract", key, name, {"template": template or None})
        return _docx(data, name, missing)

    # ------------------------------------------------------------------ zeyilname

    @app.post("/api/v1/editorial/contracts/item/{key}/addenda")
    def addendum_create(key: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user = session(request)
        need(user, EDIT)
        rid = record_key(engine, tenant, user, request, key)
        a = call(C.create_addendum, engine, tenant, user, rid, body)
        audit(engine, user, "create", "contract_addendum", a["id"], a["no"], {"changes": a["changes"]})
        return a

    @app.patch("/api/v1/editorial/contracts/addenda/{addendum_id}")
    def addendum_update(addendum_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user = session(request)
        need(user, EDIT)
        a = call(C.update_addendum, engine, tenant, user, addendum_id, body)
        audit(engine, user, "update", "contract_addendum", a["id"], a["no"], {"changes": a["changes"]})
        return a

    @app.post("/api/v1/editorial/contracts/addenda/{addendum_id}/status")
    def addendum_status(addendum_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user = session(request)
        need(user, EDIT)
        a = call(C.set_addendum_status, engine, tenant, user, addendum_id, body)
        audit(engine, user, "sign" if a["status"] == "imzalandi" else "status", "contract_addendum", a["id"], a["no"],
              {"status": a["status"], "changes": a["changes"]})
        return a

    @app.get("/api/v1/editorial/contracts/addenda/{addendum_id}/document.docx")
    def addendum_document(addendum_id: str, request: Request, template: str = "") -> Response:
        engine, tenant, user = session(request)
        data, name, missing = call(C.document, engine, tenant, "zeyilname", addendum_id, template)
        audit(engine, user, "export", "contract_addendum", addendum_id, name, None)
        return _docx(data, name, missing)

    # ------------------------------------------------------------------ ödeme takvimi

    @app.post("/api/v1/editorial/contracts/item/{key}/payments")
    def payment_add(key: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user = session(request)
        need(user, EDIT)
        rid = record_key(engine, tenant, user, request, key)
        p = call(C.add_payment, engine, tenant, user, rid, body)
        audit(engine, user, "create", "contract_payment", p["id"], p["kindLabel"], {"amount": p["amount"], "due": p["dueOn"]})
        return p

    @app.post("/api/v1/editorial/contracts/item/{key}/payments/plan")
    def payment_plan(key: str, request: Request) -> dict[str, Any]:
        engine, tenant, user = session(request)
        need(user, EDIT)
        rid = record_key(engine, tenant, user, request, key)
        out = call(C.plan_payments, engine, tenant, user, rid)
        if out["added"]:
            audit(engine, user, "create", "contract_payment", rid, "Ödeme planı", out["added"])
        return out

    @app.patch("/api/v1/editorial/contracts/payments/{payment_id}")
    def payment_update(payment_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user = session(request)
        need(user, EDIT)
        p = call(C.update_payment, engine, tenant, user, payment_id, body)
        audit(engine, user, "update", "contract_payment", p["id"], p["kindLabel"], body)
        return p

    @app.post("/api/v1/editorial/contracts/payments/{payment_id}/paid")
    def payment_paid(payment_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user = session(request)
        need(user, FINANCE)
        p = call(C.mark_paid, engine, tenant, user, payment_id, body)
        audit(engine, user, "paid", "contract_payment", p["id"], p["kindLabel"],
              {"amount": p["paidAmount"], "on": p["paidOn"], "ref": p["paidRef"]})
        return p

    @app.post("/api/v1/editorial/contracts/payments/{payment_id}/cancel")
    def payment_cancel(payment_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user = session(request)
        need(user, EDIT)
        with engine.connect() as c:
            paid = c.execute(C.sa.select(C.PAYMENTS.c.status).where(C.PAYMENTS.c.tenant_id == tenant,
                                                                    C.PAYMENTS.c.id == payment_id)).scalar()
        if paid == "odendi":
            need(user, FINANCE)
        p = call(C.cancel_payment, engine, tenant, user, payment_id, body)
        audit(engine, user, "cancel", "contract_payment", p["id"], p["kindLabel"], {"note": body.get("note")})
        return p

    # ------------------------------------------------------------------ hakediş

    logo_lock = threading.Lock()
    years_cache: dict[str, Any] = {}

    def logo():
        from semantic_layer.profiler.connectors import connector_from_file
        conn = connector_from_file(rt().settings.connection_file)
        conn.query_timeout = 600
        return conn

    def logo_rows(conn, sql: str, qlog: Optional[K.Kayit] = None) -> list[dict[str, Any]]:
        import time
        t0 = time.monotonic()
        rows = list(conn.execute(sql, 100_000)[1])
        if qlog is not None:  # sorgu bilgisi: hesap anında çalışan metin (sonuç satırı kayda girmez)
            qlog.add("logo", sql, rows=len(rows), ms=int((time.monotonic() - t0) * 1000))
        return rows

    def sales_years(conn, qlog: Optional[K.Kayit] = None) -> set[int]:
        import time
        if years_cache.get("at", 0) > time.time() - 3600:
            if qlog is not None and years_cache.get("log"):
                qlog.items.append(dict(years_cache["log"], cached=True))
            return years_cache["years"]
        mine = K.Kayit()
        rows = logo_rows(conn, "SELECT name FROM sys.views WHERE name LIKE 'V[_]SatisRaporu[_]20[0-9][0-9]'", mine)
        years_cache.update(at=time.time(), years={int(r["name"][-4:]) for r in rows}, log=mine.items[0])
        if qlog is not None:
            qlog.items.append(dict(mine.items[0]))
        return years_cache["years"]

    def run_sales(conn, codes: list[str], a: date, b: date, present: set[int],
                  qlog: Optional[K.Kayit] = None) -> tuple[dict[str, dict[str, float]], list[int]]:
        from semantic_bridge.management import expand_sales
        sql, missing = expand_sales(R.sales_sql(codes, a, b), date.today(), present)
        return R.fold_sales(logo_rows(conn, sql, qlog)), missing

    def tcmb_get(url: str) -> tuple[int, str]:
        import httpx
        try:
            r = httpx.get(url, timeout=10)
            return r.status_code, r.text
        except Exception as e:  # noqa: BLE001 — ağ yoksa kur elle girilir
            log.warning("contracts: TCMB kuru okunamadı (%s): %s", url, e)
            return 0, ""

    def calculate(engine, tenant, request: Request, key: str, body: dict[str, Any]) -> dict[str, Any]:
        qlog = K.Kayit()  # hesap anında çalışan Logo/CRM metni; hesap sonucunun yanında saklanır (sorgu bilgisi)
        rec = C.find(engine, tenant, key)
        if rec:
            terms = rec["terms"]
        elif C.is_crm_id(key):
            crm = crm_loader(request, qlog)(key)
            if crm is None:
                raise T.ContractError("Sözleşme CRM'de bulunamadı.", 404)
            terms = crm["terms"]
        else:
            raise T.ContractError("Sözleşme bulunamadı.", 404)
        a, b = R.month_bounds(str(body.get("periodStart") or ""), str(body.get("periodEnd") or ""))
        pt = terms.get("paymentType")
        codes = sorted({bk["stockCode"] for bk in terms.get("books") or [] if bk.get("stockCode")})
        prints = {str(k): float(v) for k, v in (body.get("prints") or {}).items() if v not in (None, "")}
        prices = {str(k): float(v) for k, v in (body.get("listPrices") or {}).items() if v not in (None, "")}
        sales: dict[str, dict[str, float]] = {}
        prior: dict[str, float] = {}
        data_end = None
        fx = None
        notes: list[str] = []
        need_logo = pt in T.SALES_BASED and bool(codes)
        if need_logo:
            with logo_lock:  # Logo'yu aynı anda tek hakediş okur (ağır sorgu, tek bağlantı)
                conn = logo()
                present = sales_years(conn, qlog)
                if pt in T.SALES_BASED and codes:
                    sales, missing = run_sales(conn, codes, a, b, present, qlog)
                    if missing:
                        notes.append("Logo'da şu yılların satış görünümü yok: " + ", ".join(map(str, missing)) + ".")
                    if pt in T.TIERED and terms.get("tiers") and terms.get("start"):
                        s0 = date.fromisoformat(terms["start"]).replace(day=1)
                        if s0 < a:
                            before_end = a - timedelta(days=1)
                            p_sales, _ = run_sales(conn, codes, max(s0, date(min(present or {a.year}), 1, 1)), before_end, present, qlog)
                            prior = {k: v["qty"] for k, v in p_sales.items()}
                    last_year = max([y for y in present if y <= b.year] or [0])
                    if last_year:
                        rows = logo_rows(conn, R.data_end_sql(last_year), qlog)
                        data_end = str(rows[0]["son"])[:10] if rows and rows[0].get("son") else None
        if terms.get("currency") not in (None, "TRY"):
            manual = body.get("fxRate")
            if manual not in (None, ""):
                rate = T._num(manual, "Kur")
                if not rate:
                    raise T.ContractError("Kur sıfırdan büyük olmalı.")
                fx = {"rate": rate, "on": b.isoformat(), "source": "elle girildi"}
            else:
                fx = R.tcmb_rate(terms["currency"], b, tcmb_get)
        ctx = C.statement_context(engine, tenant, rec["id"], a.isoformat()) if rec else {"advanceUsed": 0.0, "carryIn": 0.0}
        out = R.compute(terms, period_start=a.isoformat(), period_end=b.isoformat(), sales=sales, prior_qty=prior,
                        prints=prints, list_prices=prices, advance_used=ctx["advanceUsed"], carry_in=ctx["carryIn"],
                        fx=fx, data_end=data_end)
        out["warnings"] = notes + out["warnings"]
        out["source"] = "Logo satış görünümleri (faturalı satır), stok kodu ile" if pt in T.SALES_BASED else "Elle girilen baskı adedi"
        out["sorgular"] = qlog.items
        return out

    @app.post("/api/v1/editorial/contracts/item/{key}/statements/preview")
    async def statement_preview(key: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user = await run_in_threadpool(session, request)
        need(user, FINANCE)
        out = await run_in_threadpool(call, calculate, engine, tenant, request, key, body)
        return await run_in_threadpool(P.bagla, out, lambda: K.for_calc(
            engine, tenant, out, key, {"logo": logo_db(), "crm": K.crm_db(crm_prefix(editorial(request)[0]))}))

    @app.post("/api/v1/editorial/contracts/item/{key}/statements")
    async def statement_save(key: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user = await run_in_threadpool(session, request)
        need(user, FINANCE)
        rid = await run_in_threadpool(record_key, engine, tenant, user, request, key)
        result = await run_in_threadpool(call, calculate, engine, tenant, request, rid, body)
        s = await run_in_threadpool(call, C.save_statement, engine, tenant, user, rid, result, str(body.get("note") or ""))
        audit(engine, user, "create", "contract_statement", s["id"], f"{s['periodStart']}–{s['periodEnd']}",
              {"net": s["net"], "currency": s["currency"]})
        return s

    @app.post("/api/v1/editorial/contracts/statements/{statement_id}/approve")
    def statement_approve(statement_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user = session(request)
        need(user, FINANCE)
        s = call(C.approve_statement, engine, tenant, user, statement_id, body)
        audit(engine, user, "approve", "contract_statement", s["id"], f"{s['periodStart']}–{s['periodEnd']}",
              {"net": s["net"], "currency": s["currency"], "payment": s["paymentId"]})
        return s

    @app.post("/api/v1/editorial/contracts/statements/{statement_id}/cancel")
    def statement_cancel(statement_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user = session(request)
        need(user, FINANCE)
        s = call(C.cancel_statement, engine, tenant, user, statement_id, body)
        audit(engine, user, "cancel", "contract_statement", s["id"], f"{s['periodStart']}–{s['periodEnd']}", {"note": body.get("note")})
        return s

    @app.get("/api/v1/editorial/contracts/statements/{statement_id}/document.docx")
    def statement_document(statement_id: str, request: Request, template: str = "") -> Response:
        engine, tenant, user = session(request)
        data, name, missing = call(C.document, engine, tenant, "hakedis", statement_id, template)
        audit(engine, user, "export", "contract_statement", statement_id, name, None)
        return _docx(data, name, missing)

    # ------------------------------------------------------------------ şablonlar

    @app.get("/api/v1/editorial/contracts/templates")
    def templates_list(request: Request, target: str = "", archived: bool = False) -> dict[str, Any]:
        engine, tenant, user = session(request)
        out = {"items": call(C.templates, engine, tenant, target=target, include_archived=archived),
               "fields": D.FIELDS, "targets": D.TARGETS, "can": caps(user)}
        return P.bagla(out, lambda: K.for_templates(engine, tenant, out, target=target, archived=archived))

    @app.post("/api/v1/editorial/contracts/templates")
    def template_create(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user = session(request)
        need(user, TEMPLATE)
        t = call(C.save_template, engine, tenant, user, body)
        audit(engine, user, "create", "contract_template", t["id"], t["name"], {"target": t["target"]})
        return t

    @app.patch("/api/v1/editorial/contracts/templates/{template_id}")
    def template_update(template_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user = session(request)
        need(user, TEMPLATE)
        t = call(C.save_template, engine, tenant, user, body, template_id)
        audit(engine, user, "update", "contract_template", t["id"], t["name"],
              {"version": t["version"], "active": t["active"], "fields": sorted(k for k in body if k != "body")})
        return t

    @app.get("/api/v1/editorial/contracts/templates/{template_id}/preview")
    def template_preview(template_id: str, request: Request, contract: str = "") -> dict[str, Any]:
        engine, tenant, _ = session(request)
        return call(C.preview, engine, tenant, template_id, contract)

    @app.put("/api/v1/editorial/contracts/templates/{template_id}/docx")
    async def template_docx(template_id: str, request: Request, filename: str = "") -> dict[str, Any]:
        engine, tenant, user = await run_in_threadpool(session, request)
        need(user, TEMPLATE)
        if int(request.headers.get("content-length") or 0) > D.MAX_DOCX:
            raise HTTPException(status_code=413, detail={"code": "CONTRACT", "message": "Word dosyası 15 MB sınırını aşıyor."})
        data = await request.body()
        t = await run_in_threadpool(call, C.upload_template_docx, engine, tenant, user, template_id, filename, data)
        audit(engine, user, "upload", "contract_template", t["id"], t["name"], {"file": t["docxName"], "bytes": len(data)})
        return t

    @app.delete("/api/v1/editorial/contracts/templates/{template_id}/docx")
    def template_docx_remove(template_id: str, request: Request) -> dict[str, Any]:
        engine, tenant, user = session(request)
        need(user, TEMPLATE)
        t = call(C.remove_template_docx, engine, tenant, user, template_id)
        audit(engine, user, "delete", "contract_template", t["id"], t["name"], {"docx": None})
        return t

    @app.get("/api/v1/editorial/contracts/templates/{template_id}/docx")
    def template_docx_get(template_id: str, request: Request) -> Response:
        engine, tenant, _ = session(request)
        t = call(C.template, engine, tenant, template_id, True)
        if not t.get("docx"):
            raise HTTPException(status_code=404, detail={"code": "CONTRACT", "message": "Şablonun Word dosyası yok."})
        return _docx(t["docx"], t["docxName"] or "sablon.docx", [])
