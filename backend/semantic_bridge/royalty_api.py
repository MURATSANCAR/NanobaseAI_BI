"""M54 Telif dönemi ve haklar: köprü uçları `/api/v1/royalty/*` ve `/api/v1/rights/*`.

Sayfa kapısı `access.RULES` (`sayfa:telif-donem`, `sayfa:haklar`); koşu açma/hesaplama/satır kararı `ozellik:telif.kosu`,
yenileme kararı `ozellik:telif.yenileme-karar`, hak kartı `ozellik:haklar.duzenle`, verilen lisans `ozellik:haklar.lisans`
(`FEATURE_RULES`). Açıkça verilenler ucun içinde denetlenir: `telif.kosu-onay` (hesaplatan ve gönderen onaylayamaz),
`telif.bildirim` (beyanname, hak sahibinin e-postası), `telif.odeme-listesi`, `telif.avans`. Zamanlayıcı
(`timas-royalty.timer`) yalnız `POST /api/v1/royalty/run-due`'yu çağırır.

CRM (.28) ve Logo yalnız okunur, kendi bağlantılarıyla (`budget_sources.runner`: her çağrıda yeni bağlantı, arka plan
işinde de güvenli; sonuç beklenenden büyükse sessizce kesilmez, hata verir).
"""
from __future__ import annotations

import logging
import os
import smtplib
import ssl
import threading
from datetime import date, timedelta
from email.message import EmailMessage
from typing import Any, Callable, Optional
from urllib.parse import quote

from fastapi import HTTPException, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from semantic_bridge import budget_sources as bsrc
from semantic_bridge import contracts as C
from semantic_bridge import contracts_royalty as CR
from semantic_bridge import contracts_terms as T
from semantic_bridge import royalty as RY
from semantic_bridge import royalty_sources as S

log = logging.getLogger("semantic.royalty.api")

RUN = "ozellik:telif.kosu"
APPROVE = "ozellik:telif.kosu-onay"
NOTIFY = "ozellik:telif.bildirim"
PAYLIST = "ozellik:telif.odeme-listesi"
ADVANCE = "ozellik:telif.avans"
RENEWAL = "ozellik:telif.yenileme-karar"
RIGHTS_EDIT = "ozellik:haklar.duzenle"
LICENSE = "ozellik:haklar.lisans"
EXPORT = "ozellik:veri.disa-aktar"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
NOTE_THRESHOLDS = (0.70, 0.30)  # llm-choose belgesinin «öneri» eşiği; altı «incele»
RENEWAL_CHOICES = ["Yenile", "Bırak", "Yeniden müzakere"]
RENEWAL_KEYS = {"Yenile": "yenile", "Bırak": "birak", "Yeniden müzakere": "muzakere"}


def _send_mail(subject: str, text: str, to: list[str]) -> str:
    from semantic_bridge.alerts import smtp_settings

    cfg = smtp_settings()
    if not cfg:
        return "no_smtp"
    try:
        msg = EmailMessage()
        msg["Subject"], msg["From"], msg["To"] = subject, cfg["sender"], ", ".join(to)
        msg.set_content(text)
        ctx = ssl.create_default_context()
        server = (smtplib.SMTP_SSL(cfg["host"], cfg["port"], timeout=20, context=ctx) if cfg["ssl"]
                  else smtplib.SMTP(cfg["host"], cfg["port"], timeout=20))
        with server as s:
            if not cfg["ssl"] and cfg["starttls"]:
                s.starttls(context=ctx)
            if cfg["user"]:
                s.login(cfg["user"], cfg["password"])
            s.send_message(msg)
        return "sent"
    except Exception as e:  # noqa: BLE001
        log.warning("telif bildirimi e-postası gönderilemedi: %s", e)
        return "failed"


def month_back(d: date, n: int) -> date:
    """`d`nin ayından `n` ay önceki ayın ilk günü."""
    i = d.year * 12 + d.month - 1 - n
    return date(i // 12, i % 12 + 1, 1)


def _tcmb_get(url: str) -> tuple[int, str]:
    import httpx
    try:
        r = httpx.get(url, timeout=10)
        return r.status_code, r.text
    except Exception as e:  # noqa: BLE001 — ağ yoksa kur koşuda elle girilir
        log.warning("royalty: TCMB kuru okunamadı (%s): %s", url, e)
        return 0, ""


class _Sources(RY.Sources):
    def __init__(self, crm: S.Runner, logo: S.Runner, prefix: str, statuses: tuple[int, ...], codes: tuple[int, ...]):
        self.crm, self.logo, self.p, self.statuses, self.codes = crm, logo, prefix, statuses, codes

    def scope(self) -> list[dict[str, Any]]:
        return S.read_scope(self.crm, self.p, self.statuses, self.codes)

    def present_years(self) -> set[int]:
        return S.present_years(self.logo)

    def sales(self, codes, a, b, present):
        return S.read_sales(self.logo, codes, a, b, present, date.today())

    def data_end(self, present, year):
        return S.read_data_end(self.logo, present, year)

    def fx(self, currency, on):
        return CR.tcmb_rate(currency, on, _tcmb_get)


def register(app, rt: Callable[[], Any], require_caller: Callable[[Request], None], can: Callable[[str, str], bool]):
    from semantic_bridge import admin as admin_mod
    from semantic_bridge import board as board_mod
    from semantic_bridge.editorial import EditorialError, _prefix

    work_lock = threading.Lock()   # Logo'yu aynı anda tek ağır iş okur
    notes_state: dict[str, Any] = {"running": False, "done": 0, "total": 0, "error": None, "at": None}

    def crm_file() -> str:
        return os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json")

    def crm() -> S.Runner:
        return bsrc.runner(crm_file())

    def logo() -> S.Runner:
        return bsrc.runner(rt().settings.connection_file)

    def prefix() -> str:
        return _prefix(admin_mod.conf("CRM_SCHEMA"))

    def conf_int(key: str, default: int) -> int:
        try:
            return int(str(admin_mod.conf(key) or default).strip())
        except ValueError:
            return default

    def conf_pct(key: str) -> Optional[float]:
        v = str(admin_mod.conf(key) or "").strip().replace(",", ".")
        try:
            return float(v) if v else None
        except ValueError:
            return None

    def settings() -> dict[str, Any]:
        return {"statuses": S.codes_of(admin_mod.conf("ROYALTY_CRM_STATUSES"), S.DEFAULT_STATUSES),
                "paymentCodes": S.codes_of(admin_mod.conf("ROYALTY_CRM_PAYMENT_TYPES"), S.DEFAULT_PAYMENT_CODES),
                "periodMonths": conf_int("ROYALTY_PERIOD_MONTHS", 6), "withholdingPct": conf_pct("ROYALTY_WITHHOLDING_PCT"),
                "renewalDays": sorted({int(x) for x in S.codes_of(admin_mod.conf("ROYALTY_RENEWAL_DAYS"), (90, 60, 30))}, reverse=True),
                "riskYears": conf_pct("ROYALTY_ADVANCE_RISK_YEARS") or 3.0,
                "remindWorkdays": conf_int("ROYALTY_RUN_REMIND_WORKDAYS", 5)}

    def recipients() -> list[str]:
        return [x.strip() for x in (admin_mod.conf("ROYALTY_ALERT_RECIPIENTS") or "").replace(";", ",").split(",") if "@" in x]

    def link(path: str) -> str:
        base = (admin_mod.conf("ALERT_LINK") or "").split("/uyarilar")[0]
        return f"{base}{path}" if base else ""

    def ctx(request: Request) -> tuple[Any, str, str, str]:
        require_caller(request)
        try:
            user, display = board_mod.session_of(request.headers.get("cookie", ""))
        except board_mod.NoUser:
            raise HTTPException(status_code=401, detail={"code": "UNAUTHORIZED", "message": "Oturum gerekli."}) from None
        r = rt()
        RY.ensure(r.store.engine)
        admin_mod.ensure(r.store.engine)
        return r.store.engine, r.settings.tenant_id, user, display

    def call(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except RY.RoyaltyError as e:
            raise HTTPException(status_code=e.status, detail={"code": "ROYALTY", "message": str(e)}) from e
        except T.ContractError as e:
            raise HTTPException(status_code=e.status, detail={"code": "ROYALTY", "message": str(e)}) from e
        except (bsrc.SourceError, S.SourceError) as e:
            raise HTTPException(status_code=503, detail={"code": "ROYALTY_SOURCE", "message": str(e)}) from e
        except EditorialError as e:
            raise HTTPException(status_code=e.status, detail={"code": "ROYALTY_SOURCE", "message": str(e)}) from e

    def need(user: str, key: str, what: str) -> None:
        if not can(user, key):
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": f"{what} rolünüzde yok."})

    def audit(engine, user, action, kind, obj_id, label, detail=None) -> None:
        admin_mod.audit(engine, user, action, kind, obj_id, label, detail)

    def caps(user: str) -> dict[str, bool]:
        return {"run": can(user, RUN), "approve": can(user, APPROVE), "notify": can(user, NOTIFY), "payments": can(user, PAYLIST),
                "advance": can(user, ADVANCE), "renewal": can(user, RENEWAL), "rightsEdit": can(user, RIGHTS_EDIT),
                "license": can(user, LICENSE), "export": can(user, EXPORT)}

    def background(name: str, fn: Callable[[], Any], on_error: Callable[[str], None]) -> None:
        def work():
            with work_lock:
                try:
                    fn()
                except (RY.RoyaltyError, T.ContractError, bsrc.SourceError, S.SourceError, EditorialError) as e:
                    on_error(str(e))
                except Exception as e:  # noqa: BLE001 — sürücü metni loga, ekrana düz cümle
                    log.exception("royalty: %s", name)
                    on_error("İş tamamlanamadı; kayıt günlükte. Yeniden deneyin, sürerse destek ekibine haber verin.")
        threading.Thread(target=work, name=f"royalty-{name}", daemon=True).start()

    def _docx(data: bytes, name: str, media: str = DOCX) -> Response:
        return Response(content=data, media_type=media, headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"})

    # ------------------------------------------------------------------ genel

    @app.get("/api/v1/royalty/meta")
    def royalty_meta(request: Request) -> dict[str, Any]:
        engine, tenant, user, display = ctx(request)
        st = settings()
        a, b = RY.default_period(RY.today(), st["periodMonths"])
        return {"can": caps(user), "me": {"username": user, "display": display},
                "runStatuses": RY.RUN_STATUSES, "lineStatuses": RY.LINE_STATUSES,
                "exceptions": {k: {"label": v[0], "acceptable": v[1], "fix": v[2]} for k, v in RY.EXCEPTIONS.items()},
                "autoExclude": RY.AUTO_EXCLUDE, "renewalDecisions": RY.RENEWAL_DECISIONS, "currencies": T.CURRENCIES,
                "defaultPeriod": {"start": a, "end": b}, "periodMonths": st["periodMonths"],
                "withholdingPct": st["withholdingPct"], "renewalDays": st["renewalDays"], "riskYears": st["riskYears"],
                "scope": {"statuses": list(st["statuses"]), "paymentCodes": list(st["paymentCodes"])}}

    # ------------------------------------------------------------------ koşular

    @app.get("/api/v1/royalty/runs")
    def royalty_runs(request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        return {"items": call(RY.list_runs, engine, tenant), "can": caps(user)}

    @app.post("/api/v1/royalty/runs")
    def royalty_run_create(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, RUN, "Telif koşusu açmak")
        run = call(RY.create_run, engine, tenant, user, body)
        audit(engine, user, "create", "royalty_run", run["id"], run["no"], {"period": [run["periodStart"], run["periodEnd"]]})
        return run

    @app.get("/api/v1/royalty/runs/{run_id}")
    def royalty_run(run_id: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        return {**call(RY.get_run, engine, tenant, run_id), "can": caps(user)}

    @app.get("/api/v1/royalty/runs/{run_id}/status")
    def royalty_run_status(run_id: str, request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        r = call(RY.get_run, engine, tenant, run_id)
        return {k: r[k] for k in ("id", "status", "statusLabel", "progress", "error", "summary", "updatedAt")}

    @app.patch("/api/v1/royalty/runs/{run_id}")
    def royalty_run_options(run_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, RUN, "Telif koşusu")
        run = call(RY.update_options, engine, tenant, user, run_id, body)
        audit(engine, user, "update", "royalty_run", run["id"], run["no"], {"fx": run["options"].get("fx"), "note": body.get("note")})
        return run

    @app.post("/api/v1/royalty/runs/{run_id}/compute")
    def royalty_run_compute(run_id: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, RUN, "Telif koşusu hesaplamak")
        before = call(RY.get_run, engine, tenant, run_id)
        st = settings()
        src = call(lambda: _Sources(crm(), logo(), prefix(), st["statuses"], st["paymentCodes"]))
        run = call(RY.mark_computing, engine, tenant, user, run_id)
        back = "hesaplandi" if before["status"] == "hesaplandi" else "taslak"
        background(f"compute-{run_id[:8]}", lambda: RY.compute_run(engine, tenant, run_id, user, src, st),
                   lambda msg: RY.fail_run(engine, run_id, back, msg))
        audit(engine, user, "run", "royalty_run", run["id"], run["no"], {"compute": True})
        return run

    @app.get("/api/v1/royalty/runs/{run_id}/lines")
    def royalty_lines(run_id: str, request: Request, status: str = "", code: str = "", q: str = "", page: int = 0) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return call(RY.lines, engine, tenant, run_id, status=status, code=code, q=q, page=page)

    @app.get("/api/v1/royalty/runs/{run_id}/lines/{line_id}")
    def royalty_line(run_id: str, line_id: int, request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return call(RY.line, engine, tenant, run_id, line_id)

    @app.patch("/api/v1/royalty/runs/{run_id}/lines/{line_id}")
    def royalty_line_decide(run_id: str, line_id: int, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, RUN, "Koşu satırı kararı")
        ln = call(RY.decide_line, engine, tenant, user, run_id, line_id, body)
        audit(engine, user, "update", "royalty_line", str(ln["id"]), ln["no"], {"action": body.get("action"), "reason": body.get("reason")})
        return ln

    @app.post("/api/v1/royalty/runs/{run_id}/submit")
    def royalty_submit(run_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, RUN, "Onaya göndermek")
        run = call(RY.submit, engine, tenant, user, run_id, body)
        audit(engine, user, "submit", "royalty_run", run["id"], run["no"], {"note": body.get("note")})
        return run

    @app.post("/api/v1/royalty/runs/{run_id}/withdraw")
    def royalty_withdraw(run_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, RUN, "Onaydan geri çekmek")
        run = call(RY.back_to_computed, engine, tenant, user, run_id, body, reject=False)
        audit(engine, user, "withdraw", "royalty_run", run["id"], run["no"], None)
        return run

    @app.post("/api/v1/royalty/runs/{run_id}/reject")
    def royalty_reject(run_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, APPROVE, "Telif koşusu onayı")
        run = call(RY.back_to_computed, engine, tenant, user, run_id, body, reject=True)
        audit(engine, user, "reject", "royalty_run", run["id"], run["no"], {"note": body.get("note")})
        return run

    @app.post("/api/v1/royalty/runs/{run_id}/approve")
    def royalty_approve(run_id: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, APPROVE, "Telif koşusu onayı")
        run = call(RY.mark_approving, engine, tenant, user, run_id)

        def job():
            done = RY.approve_run(engine, tenant, run_id, user)
            if done["status"] == "onayli":
                to = recipients()
                if to and RY.notice_once(engine, tenant, "odeme-listesi", run_id):
                    tot = "; ".join(f"{cur}: {T.money(t['net'], cur)} ({t['count']} sözleşme)"
                                    for cur, t in (done["summary"].get("totals") or {}).items())
                    _send_mail(f"Telif ödeme listesi hazır — {done['no']}",
                               f"{done['no']} ({done['label']}) onaylandı. Ödenecek toplam: {tot or '—'}.\n"
                               f"Ödeme listesi ve stopaj özeti Telif dönemi ekranında.\n{link('/telif-donem?kosu=' + run_id)}", to)

        background(f"approve-{run_id[:8]}", job, lambda msg: RY.fail_run(engine, run_id, "onayda", msg))
        audit(engine, user, "approve", "royalty_run", run["id"], run["no"], {"summary": run["summary"].get("totals")})
        return run

    @app.post("/api/v1/royalty/runs/{run_id}/cancel")
    def royalty_cancel(run_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, RUN, "Koşuyu iptal etmek")
        run = call(RY.cancel, engine, tenant, user, run_id, body)
        audit(engine, user, "cancel", "royalty_run", run["id"], run["no"], {"note": body.get("note")})
        return run

    # ------------------------------------------------------------------ hak sahipleri ve beyanname

    @app.get("/api/v1/royalty/runs/{run_id}/parties")
    def royalty_parties(run_id: str, request: Request, q: str = "", status: str = "", page: int = 0) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        return call(RY.parties, engine, tenant, run_id, q=q, status=status, show_email=can(user, NOTIFY), page=page)

    @app.get("/api/v1/royalty/runs/{run_id}/parties/{party}/statement.docx")
    def royalty_party_doc(run_id: str, party: str, request: Request) -> Response:
        engine, tenant, user, _ = ctx(request)
        need(user, NOTIFY, "Telif beyannamesi")
        data, name, digest = call(RY.party_document, engine, tenant, run_id, party)
        audit(engine, user, "export", "royalty_statement", run_id, name, {"party": party, "hash": digest})
        return _docx(data, name)

    @app.get("/api/v1/royalty/runs/{run_id}/statements.zip")
    def royalty_statements_zip(run_id: str, request: Request) -> Response:
        engine, tenant, user, _ = ctx(request)
        need(user, NOTIFY, "Telif beyannamesi")
        data, name = call(RY.statements_zip, engine, tenant, run_id)
        audit(engine, user, "export", "royalty_statement", run_id, name, {"zip": True})
        return _docx(data, name, "application/zip")

    @app.post("/api/v1/royalty/runs/{run_id}/parties/mark-sent")
    def royalty_mark_sent(run_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, NOTIFY, "Beyanname gönderim kaydı")
        out = call(RY.mark_sent, engine, tenant, user, run_id, body)
        audit(engine, user, "update", "royalty_statement", run_id, "Beyanname gönderim kaydı",
              {"keys": body.get("keys"), "channel": body.get("channel"), "undo": bool(body.get("undo"))})
        return out

    # ------------------------------------------------------------------ ödeme listesi

    @app.get("/api/v1/royalty/runs/{run_id}/payments")
    def royalty_payments(run_id: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, PAYLIST, "Telif ödeme listesi")
        run, rows = call(RY.payment_rows, engine, tenant, run_id)
        totals: dict[str, dict[str, float]] = {}
        for r in rows:
            t = totals.setdefault(r["currency"], {"gross": 0.0, "advance": 0.0, "withholding": 0.0, "net": 0.0, "payees": 0})
            for k in ("gross", "advance", "withholding", "net"):
                t[k] = round(t[k] + r[k], 2)
            t["payees"] += 1 if r["net"] > 0 else 0
        return {"items": rows, "totals": totals, "run": {"id": run["id"], "no": run["no"], "label": run["label"]}}

    @app.get("/api/v1/royalty/runs/{run_id}/payments.csv")
    def royalty_payments_csv(run_id: str, request: Request) -> Response:
        engine, tenant, user, _ = ctx(request)
        need(user, PAYLIST, "Telif ödeme listesi")
        data, name = call(RY.payments_csv, engine, tenant, run_id)
        audit(engine, user, "export", "royalty_payments", run_id, name, None)
        return _docx(data, name, "text/csv; charset=utf-8")

    @app.get("/api/v1/royalty/runs/{run_id}/withholding.csv")
    def royalty_withholding_csv(run_id: str, request: Request) -> Response:
        engine, tenant, user, _ = ctx(request)
        need(user, PAYLIST, "Stopaj özeti")
        data, name = call(RY.withholding_csv, engine, tenant, run_id)
        audit(engine, user, "export", "royalty_withholding", run_id, name, None)
        return _docx(data, name, "text/csv; charset=utf-8")

    # ------------------------------------------------------------------ avans

    @app.get("/api/v1/royalty/advances")
    def royalty_advances(request: Request, q: str = "", only: str = "") -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        return {**call(RY.advances, engine, tenant, risk_years=settings()["riskYears"], q=q, only=only), "can": caps(user)}

    @app.get("/api/v1/royalty/advances/{contract}")
    def royalty_advance_history(contract: str, request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return {"contractKey": contract.lower(), "history": call(RY.advance_history, engine, tenant, contract)}

    @app.put("/api/v1/royalty/advances/{contract}")
    def royalty_advance_set(contract: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, ADVANCE, "Avans açılış bakiyesi girmek")
        out = call(RY.set_advance, engine, tenant, user, contract, body)
        audit(engine, user, "update", "royalty_advance", contract.lower(), body.get("no") or contract[:8],
              {"amount": body.get("amount"), "currency": body.get("currency"), "asOf": body.get("asOf"),
               "reason": body.get("reason"), "remove": bool(body.get("remove"))})
        return out

    # ------------------------------------------------------------------ yenilemeler

    def renewal_list(engine, tenant, days: int, overdue: bool) -> list[dict[str, Any]]:
        on = RY.today()
        p = prefix()
        rows = crm()(S.renewals_sql(p, None, on) if overdue else S.renewals_sql(p, on, on + timedelta(days=days)))
        return RY.renewal_rows(rows, RY.renewal_decisions(engine, tenant), on)

    @app.get("/api/v1/royalty/renewals")
    def royalty_renewals(request: Request, days: int = 90, overdue: bool = False, q: str = "", decision: str = "",
                         kind: str = "") -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        if not 1 <= days <= 3660:
            raise HTTPException(status_code=400, detail={"code": "ROYALTY", "message": "Gün 1–3660 arasında olmalı."})
        items = call(renewal_list, engine, tenant, days, overdue)
        counts = {k: sum(1 for x in items if x["decision"] == k) for k in RY.RENEWAL_DECISIONS}
        needle = RY.fold(q)
        items = [x for x in items if (not decision or x["decision"] == decision) and (not kind or x["kind"] == kind)
                 and (not needle or needle in RY.fold(" ".join(str(x.get(k) or "") for k in ("no", "book", "author", "stockCode"))))]
        return {"items": items, "total": len(items), "counts": counts, "days": days, "overdue": overdue,
                "today": RY.today().isoformat(), "can": caps(user)}

    @app.patch("/api/v1/royalty/renewals/{contract}")
    def royalty_renewal_decide(contract: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, RENEWAL, "Yenileme kararı")
        out = call(RY.decide_renewal, engine, tenant, user, contract, body)
        audit(engine, user, "update", "royalty_renewal", contract.lower(), body.get("no") or contract[:8],
              {"decision": out["decision"], "reason": out["reason"]})
        return out

    def renewal_facts(contract: str) -> tuple[dict[str, Any], Optional[str]]:
        p = prefix()
        c_run, l_run = crm(), logo()
        rows = c_run(S.renewals_sql(p, None, None, contract_id=contract))
        if not rows:
            raise RY.RoyaltyError("Sözleşme CRM'de bulunamadı.", 404)
        r = rows[0]
        _, books_sql, _ = C.crm_contract_sql(p, contract)
        codes = sorted({str(x).strip() for b in c_run(books_sql) for x in (b.get("new_StokKodu"), b.get("new_EKitapStokKodu"))
                        if str(x or "").strip()})
        present = S.present_years(l_run)
        end = S.read_data_end(l_run, present, date.today().year) if present else None
        facts: dict[str, Any] = {"Sözleşme": r.get("no"), "Kitap": r.get("kitap"), "Yazar": r.get("yazar"),
                                 "Bitiş": T.day_tr(str(r.get("bit") or "")[:10]) if r.get("bit") else None,
                                 "Yenileme sıklığı (yıl)": r.get("yenileme_yil")}
        if codes and end:
            e = date.fromisoformat(end)
            b = date(e.year + e.month // 12, e.month % 12 + 1, 1) - timedelta(days=1)  # veri sonunun ayının son günü
            a36, a12 = month_back(b, 35), month_back(b, 11)
            rows36, _ = S.read_sales(l_run, codes, a36, b, present, date.today())
            f36 = CR.fold_sales(rows36)
            f12 = CR.fold_sales([x for x in rows36 if S.month_of(x) >= CR.ym(a12)])
            facts.update({
                "Son 36 ay net satış adedi": T.fmt_num(sum(v["qty"] for v in f36.values()), 0),
                "Son 36 ay net satış tutarı (TL)": T.fmt_num(sum(v["net"] for v in f36.values())),
                "Son 12 ay net satış adedi": T.fmt_num(sum(v["qty"] for v in f12.values()), 0),
                "Satış verisi şu güne kadar": T.day_tr(end),
            })
        elif not codes:
            facts["Satış"] = "Kitabın stok kodu yok; satış okunamadı"
        return facts, str(r.get("bit") or "")[:10] or None

    @app.post("/api/v1/royalty/renewals/{contract}/suggest")
    async def royalty_renewal_suggest(contract: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        key = contract.lower()
        if not RY._GUID.match(key):
            raise HTTPException(status_code=400, detail={"code": "ROYALTY", "message": "Sözleşme kimliği geçerli değil."})

        def work() -> dict[str, Any]:
            from semantic_bridge.marketing import guard
            from semantic_layer.runtime.llm_queue import NORMAL

            facts, end = renewal_facts(key)
            adv = RY.advances(engine, tenant, risk_years=settings()["riskYears"], q="")
            mine = next((x for x in adv["items"] if x["contractKey"] == key), None)
            if mine and mine.get("remaining") is not None:
                facts["Kazanılmamış avans"] = T.money(mine["remaining"], mine["currency"])
            llm = rt().llm_for("royalty", NORMAL)
            prompt = RY.renewal_prompt(facts)
            try:
                ch = llm.choose(prompt + "\n\nBu olgulara göre hangisi daha uygun görünüyor?", RENEWAL_CHOICES)
                text = str(llm.chat([{"role": "user", "content": prompt + "\n\nGerekçe:"}], max_tokens=300) or "").strip()
            except Exception as e:  # noqa: BLE001 — model yoksa «sonra dene»
                log.warning("royalty: yenileme önerisi alınamadı: %s", e)
                raise RY.RoyaltyError("Zeki AI şu an cevap veremiyor; biraz sonra yeniden deneyin.", 503) from None
            checked = guard.check(text, [], [str(v) for v in facts.values() if v is not None])
            sug = {"decision": RENEWAL_KEYS.get(ch.choice or ""), "probability": ch.probability, "text": checked["metin"] or None,
                   "inputs": facts, "dropped": checked["dusenSayisi"]}
            RY.save_renewal_suggestion(engine, tenant, key, end, sug)
            return sug

        out = await run_in_threadpool(call, work)
        audit(engine, user, "run", "royalty_renewal", key, "Zeki AI yenileme önerisi", {"decision": out.get("decision")})
        return out

    @app.get("/api/v1/royalty/contracts/{key}/lines")
    def royalty_contract_lines(key: str, request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return {"items": call(RY.contract_lines, engine, tenant, key)}

    # ------------------------------------------------------------------ zamanlayıcı

    @app.post("/api/v1/royalty/run-due")
    def royalty_run_due(request: Request) -> dict[str, Any]:
        """Günlük: dönem sonu + N iş günü «koşu açılmadı», bitişe 90/60/30 gün kalan kararsız sözleşmeler, bitişi geçmiş
        kararsız sözleşme sayısı. İç ekibe tek özet e-postası (yazara gönderim yok). Koşunun hesabı burada başlamaz."""
        require_caller(request)
        r = rt()
        engine, tenant = r.store.engine, r.settings.tenant_id
        RY.ensure(engine)
        st = settings()
        on = RY.today()
        msgs: list[str] = []
        a, b = RY.default_period(on, st["periodMonths"])
        due = RY.workdays_after(date.fromisoformat(b), st["remindWorkdays"])
        out: dict[str, Any] = {"period": [a, b], "runReminder": False, "renewals": {}, "overdue": None}
        if on >= due and not RY.run_exists_for(engine, tenant, a, b):
            out["runReminder"] = True
            if RY.notice_once(engine, tenant, "kosu-acilmadi", a):
                msgs.append(f"{RY.period_label(a, b)} telif dönemi için koşu açılmadı (dönem bitişinden {st['remindWorkdays']} iş günü geçti).")
        try:
            horizon = max(st["renewalDays"] or [90])
            rows = RY.renewal_rows(crm()(S.renewals_sql(prefix(), on, on + timedelta(days=horizon))),
                                   RY.renewal_decisions(engine, tenant), on)
            for d in sorted(st["renewalDays"]):
                fresh = [x for x in rows if x["decision"] == "bekliyor" and x["daysLeft"] is not None and x["daysLeft"] <= d
                         and RY.notice_once(engine, tenant, f"yenileme-{d}", f"{x['contractKey']}:{x['end']}")]
                out["renewals"][d] = len(fresh)
                if fresh:
                    msgs.append(f"Bitişine {d} gün ya da daha az kalan, kararı girilmemiş {len(fresh)} sözleşme:\n" +
                                "\n".join(f"  - {x['no']} · {x.get('book') or ''} · bitiş {T.day_tr(x['end'])}" for x in fresh))
            past = RY.renewal_rows(crm()(S.renewals_sql(prefix(), None, on)), RY.renewal_decisions(engine, tenant), on)
            out["overdue"] = sum(1 for x in past if x["decision"] == "bekliyor")
        except (bsrc.SourceError, S.SourceError, EditorialError) as e:
            out["renewalError"] = str(e)
        to = recipients()
        if msgs and to:
            out["mail"] = _send_mail("Telif dönemi ve yenileme özeti", "\n\n".join(msgs) +
                                     (f"\n\nBitişi geçmiş, kararı girilmemiş sözleşme: {out['overdue']}." if out.get("overdue") else "")
                                     + f"\n\n{link('/telif-donem')}", to)
        elif msgs:
            out["mail"] = "no_recipients"
        out["messages"] = len(msgs)
        return out

    # ------------------------------------------------------------------ haklar

    @app.get("/api/v1/rights/meta")
    def rights_meta(request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        return {"can": caps(user), "grantKinds": RY.GRANT_KINDS, "licenseStatuses": RY.LICENSE_STATUSES,
                "collectionStatuses": RY.COLLECTION_STATUSES, "noteClasses": RY.NOTE_CLASSES, "currencies": T.CURRENCIES,
                "rights": S.RIGHT_LABELS}

    @app.get("/api/v1/rights/search")
    def rights_search(request: Request, q: str = "", page: int = 0) -> dict[str, Any]:
        ctx(request)
        rows = call(lambda: crm()(C.book_lookup_sql(prefix(), q, page)))
        return {"items": [{"id": str(r.get("new_kitapId") or "").strip("{}").lower(), "title": r.get("new_name"),
                           "stockCode": r.get("new_StokKodu"), "isbn": r.get("new_isbn13")} for r in rows],
                **C.lookup_page(rows, page)}

    def book_card(engine, tenant, book_id: str) -> dict[str, Any]:
        book_id = book_id.strip("{}").lower()
        if not RY._GUID.match(book_id):
            raise RY.RoyaltyError("Kitap kimliği geçerli değil.")
        p = prefix()
        c_run = crm()
        head = c_run(S.book_head_sql(p, book_id))
        if not head:
            raise RY.RoyaltyError("Kitap CRM'de bulunamadı.", 404)
        rows = c_run(S.book_contracts_sql(p, book_id))
        parts: dict[str, list[str]] = {}
        for t in c_run(S.book_parties_sql(p, book_id)):
            parts.setdefault(str(t.get("sid") or "").strip("{}").lower(), []).append(str(t.get("kisi") or t.get("firma") or "").strip())
        try:
            options: dict[str, dict[int, str]] = {}
            for o in c_run(S.contract_options_sql(p)):
                options.setdefault(str(o["attr"]).lower(), {})[int(o["code"])] = str(o["label"])
        except (bsrc.SourceError, S.SourceError, KeyError, ValueError):
            options = {}
        on = RY.today()
        from semantic_bridge.seo_geo import crm as seo_crm
        contracts = []
        for r in rows:
            cid = str(r.get("id") or "").strip("{}").lower()
            c = {"id": cid, "no": r.get("no"), "kind": "alis" if int(r.get("tip_kod") or 0) == S.ALIS else "satis",
                 "status": r.get("status"), "statusLabel": T.STATUSES.get(T.STATUS_FROM_CRM.get(int(r.get("status") or 0), ""), None),
                 "start": str(r.get("bas") or "")[:10] or None, "ends": r.get("ends"), "end": str(r.get("ends") or "")[:10] or None,
                 "open_ended": r.get("open_ended"), "terminated": r.get("terminated"), "public_domain": r.get("public_domain"),
                 "rights_note": (str(r.get("rights_note") or "").strip() or None),
                 "rights": {key: bool(r.get(col)) for col, key in S.RIGHT_COLUMNS.items()},
                 "originalLanguage": S.option_label(options, "new_orjinaldili", r.get("orjinal_dil")),
                 "soldCountry": S.option_label(options, "new_telifsatilanulke", r.get("satilan_ulke")),
                 "grantor": S.option_label(options, "new_hakdevredenfirma", r.get("hak_devreden")),
                 "author": r.get("yazar"), "translator": r.get("mutercim"), "illustrator": r.get("cizer"),
                 "parties": [x for x in parts.get(cid, []) if x]}
            c["inForce"] = seo_crm.in_force(c, on)
            contracts.append(c)
        lic = RY.licenses(engine, tenant, book_id=book_id)
        h = head[0]
        return {"book": {"id": book_id.lower(), "title": h.get("new_name"), "stockCode": h.get("new_StokKodu"),
                         "ebookCode": h.get("new_EKitapStokKodu"), "isbn": h.get("new_isbn13")},
                "summary": RY.rights_summary(contracts, on, lic),
                "contracts": [{k: v for k, v in c.items() if k not in ("ends", "terminated", "open_ended", "public_domain", "status")}
                              | {"crmStatus": c["status"]} for c in contracts],
                "grants": RY.grants(engine, tenant, book_id), "licenses": lic}

    @app.get("/api/v1/rights/books/{book_id}")
    def rights_book(book_id: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        return {**call(book_card, engine, tenant, book_id), "can": caps(user)}

    @app.post("/api/v1/rights/grants")
    def rights_grant_create(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, RIGHTS_EDIT, "Hak kartı düzenleme")
        g = call(RY.save_grant, engine, tenant, user, body)
        audit(engine, user, "create", "rights_grant", str(g["id"]), g["kindLabel"], body)
        return g

    @app.patch("/api/v1/rights/grants/{grant_id}")
    def rights_grant_update(grant_id: int, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, RIGHTS_EDIT, "Hak kartı düzenleme")
        g = call(RY.save_grant, engine, tenant, user, body, grant_id)
        audit(engine, user, "update", "rights_grant", str(g["id"]), g["kindLabel"], body)
        return g

    @app.delete("/api/v1/rights/grants/{grant_id}")
    def rights_grant_delete(grant_id: int, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, RIGHTS_EDIT, "Hak kartı düzenleme")
        g = call(RY.delete_grant, engine, tenant, grant_id)
        audit(engine, user, "delete", "rights_grant", str(g["id"]), g["kindLabel"], g)
        return g

    @app.get("/api/v1/rights/licenses-out")
    def rights_licenses(request: Request, q: str = "", status: str = "", book: str = "") -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        items = call(RY.licenses, engine, tenant, book_id=book, q=q, status=status)
        return {"items": items, "total": len(items), "can": caps(user)}

    @app.post("/api/v1/rights/licenses-out")
    def rights_license_create(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, LICENSE, "Lisans kaydı")
        x = call(RY.save_license, engine, tenant, user, body)
        audit(engine, user, "create", "rights_license", str(x["id"]), f"{x['book']} → {x['buyer']}", body)
        return x

    @app.patch("/api/v1/rights/licenses-out/{license_id}")
    def rights_license_update(license_id: int, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, LICENSE, "Lisans kaydı")
        x = call(RY.save_license, engine, tenant, user, body, license_id)
        audit(engine, user, "update", "rights_license", str(x["id"]), f"{x['book']} → {x['buyer']}", body)
        return x

    @app.get("/api/v1/rights/notes")
    def rights_notes(request: Request, status: str = "", cls: str = "", q: str = "", page: int = 0) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        return {**call(RY.notes, engine, tenant, status=status, cls=cls, q=q, page=page), "job": dict(notes_state), "can": caps(user)}

    @app.get("/api/v1/rights/notes/classify")
    def rights_notes_job(request: Request) -> dict[str, Any]:
        ctx(request)
        return dict(notes_state)

    @app.post("/api/v1/rights/notes/classify", status_code=202)
    def rights_notes_classify(request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, RIGHTS_EDIT, "Hak açıklaması sınıflandırma")
        if notes_state["running"]:
            return dict(notes_state)
        items = call(RY.pending_notes, engine, tenant, call(lambda: crm()(S.notes_sql(prefix()))))
        labels = list(RY.NOTE_CLASSES.values())
        by_label = {v: k for k, v in RY.NOTE_CLASSES.items()}
        notes_state.update(running=True, done=0, total=len(items), error=None, at=None, failed=0)

        def job():
            from semantic_layer.runtime.llm_queue import BATCH
            llm = rt().llm_for("royalty", BATCH)
            try:
                for it in items:
                    try:
                        ch = llm.choose(RY.note_prompt(it["text"]), labels)
                    except Exception as e:  # noqa: BLE001 — model yoksa kalanlar sonraki denemeye kalır
                        log.warning("royalty: hak açıklaması sınıflanamadı: %s", e)
                        notes_state["failed"] = notes_state.get("failed", 0) + 1
                        notes_state["error"] = "Zeki AI bazı açıklamalara cevap veremedi; kalanlar bir sonraki denemede sorulur."
                        continue
                    RY.save_note(engine, tenant, it, {"class": by_label.get(ch.choice or ""), "probability": ch.probability,
                                                      "margin": ch.margin, "method": ch.method}, NOTE_THRESHOLDS)
                    notes_state["done"] += 1
            finally:
                notes_state.update(running=False, at=RY._iso(RY._now()))

        threading.Thread(target=job, name="royalty-notes", daemon=True).start()
        audit(engine, user, "run", "rights_note", None, "Hak açıklaması sınıflandırma", {"count": len(items)})
        return dict(notes_state)

    @app.post("/api/v1/rights/notes/{note_id}/approve")
    def rights_note_approve(note_id: int, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, RIGHTS_EDIT, "Hak açıklaması onayı")
        n = call(RY.approve_note, engine, tenant, user, note_id, body)
        audit(engine, user, "approve", "rights_note", str(n["id"]), n["no"], {"class": n["class"]})
        return n

    return {"settings": settings}
