"""M20 Basın ilişkileri uçları: /api/v1/pr/*.

Sayfa kapısı `access.RULES` (`sayfa:basin-iliskileri`, açıkça verilen sayfa: medya kişilerinin e-posta ve telefonu
kişisel veridir). Yazma (PR dosyası, liste, medya kişisi, yansıma) `ozellik:pr.duzenle` (`FEATURE_RULES`); rapor dışa
aktarımı `ozellik:veri.disa-aktar`. Açıkça verilen yetkiler ucun içinde denetlenir: dosya ve satır onayı
`ozellik:pr.onay` (gönderen onaylayamaz), tek alıcılı e-posta `ozellik:pr.gonder`. Toplu gönderim ucu yoktur.

Zamanlayıcı (`timas-pr.timer`, her gün 08:30) yalnız `POST /api/v1/pr/run-due`'yu çağırır: cevapsız gönderim
hatırlatması, Basın ve web taramasından aday yansıma (ortamda tarama kapalıysa atlanır), elle girilen yansımaların
ton sınıflaması, haftalık yansıma özeti (Yönetim ayarındaki gün).

Model çağrıları LLM kapısından: ekranda bekleyen iş `rt.llm_for("pr", NORMAL)`, gece işi `rt.llm_for("pr", BATCH)`;
`LlmClient` doğrudan kurulmaz. CRM'e, Logo'ya, T-soft'a yazılmaz.
"""
from __future__ import annotations

import logging
import os
import re
import smtplib
import ssl
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import formataddr
from typing import Any, Callable, Optional

from fastapi import HTTPException, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from semantic_bridge import pr as PR
from semantic_bridge import pr_kaynak as K
from semantic_bridge import pr_export as X
from semantic_bridge import pr_sources as S
from semantic_bridge import provenance as PV

log = logging.getLogger("semantic.pr.api")

R = "/api/v1/pr"
PAGE = "sayfa:basin-iliskileri"
F_EDIT = "ozellik:pr.duzenle"
F_APPROVE = "ozellik:pr.onay"
F_SEND = "ozellik:pr.gonder"
F_EXPORT = "ozellik:veri.disa-aktar"


def _month(v: str) -> tuple[date, date]:
    if v:
        if not re.match(r"^\d{4}-\d{2}$", v):
            raise PR.PrError("Ay YYYY-AA biçiminde olmalı.")
        y, m = int(v[:4]), int(v[5:7])
        if not 1 <= m <= 12:
            raise PR.PrError("Ay YYYY-AA biçiminde olmalı.")
    else:
        t = PR.today()
        y, m = t.year, t.month
    first = date(y, m, 1)
    nxt = date(y + (m == 12), m % 12 + 1, 1)
    return first, nxt - timedelta(days=1)


def register(app, rt: Callable[[], Any], require_caller: Callable[[Request], None], can: Callable[[str, str], bool]):
    from semantic_bridge import admin as admin_mod
    from semantic_bridge import alerts as alerts_mod
    from semantic_bridge import board as board_mod
    from semantic_bridge.budget_api import _send_mail
    from semantic_bridge.marketing import core as MC

    def st() -> dict[str, Any]:
        return PR.settings(admin_mod.conf)

    crm = S.Crm(lambda: admin_mod.conf("CRM_SCHEMA") or "Timas_MSCRM.dbo", lambda: st()["crmRoles"])
    pool = ThreadPoolExecutor(max_workers=max(1, int(os.environ.get("PR_JOB_WORKERS", "2"))), thread_name_prefix="pr")
    started = {"stale": False}
    lock = threading.Lock()

    def db() -> tuple[Any, str]:
        r = rt()
        PR.ensure(r.store.engine)
        admin_mod.ensure(r.store.engine)
        with lock:
            if not started["stale"]:
                started["stale"] = True
                n = PR.fail_stale_jobs(r.store.engine)
                if n:
                    log.info("pr: yarıda kalan %d iş kapatıldı", n)
        return r.store.engine, r.settings.tenant_id

    def ctx(request: Request) -> tuple[Any, str, str, str]:
        require_caller(request)
        try:
            user, display = board_mod.session_of(request.headers.get("cookie", ""))
        except board_mod.NoUser:
            raise HTTPException(status_code=401, detail={"code": "UNAUTHORIZED", "message": "Oturum gerekli."}) from None
        engine, tenant = db()
        return engine, tenant, user, display

    def call(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except PR.PrError as e:
            raise HTTPException(status_code=e.status, detail={"code": "PR", "message": str(e)}) from e
        except S.SourceError as e:
            raise HTTPException(status_code=503, detail={"code": "PR_SOURCE", "message": str(e)}) from e

    def need(user: str, key: str, what: str) -> None:
        if not can(user, key):
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": f"{what} rolünüzde yok."})

    def audit(engine, user: str, action: str, kind: str, oid: Any, title: Any, detail: Any = None) -> None:
        admin_mod.audit(engine, user, action, kind, oid, title, detail)

    def llm(priority: str = "normal") -> Any:
        try:
            from semantic_layer.runtime.llm_queue import BATCH, NORMAL
            return rt().llm_for("pr", BATCH if priority == "batch" else NORMAL)
        except Exception:  # noqa: BLE001 — model tanımlı değil
            return None

    def link(path: str = "") -> str:
        base = (admin_mod.conf("ALERT_LINK") or "").split("/uyarilar")[0]
        return f"{base}/basin-iliskileri{('/' + path) if path else ''}" if base else ""

    # ------------------------------------------------------------------ kaynak yardımcıları

    def archive_or_empty(fresh: bool = False) -> tuple[list[dict[str, Any]], Optional[str]]:
        try:
            return crm.archive(fresh), None
        except S.SourceError as e:
            return [], f"CRM haber arşivi okunamadı: {e}"

    def contacts_all(engine, tenant, fresh: bool = False) -> tuple[list[dict[str, Any]], Optional[str]]:
        note = None
        try:
            archive, anote = archive_or_empty(fresh)
            rows = S.with_archive_counts(crm.media_contacts(fresh), archive)
            note = anote
        except S.SourceError as e:
            rows, note = [], f"CRM medya kişileri okunamadı: {e}"
        return PR.merge_contacts(rows, PR.overlays(engine, tenant)), note

    def book_of(bid: str, fresh: bool = False) -> dict[str, Any]:
        b = crm.book(S.guid(bid).lower(), fresh)
        if not b:
            raise PR.PrError("CRM'de bu kitap kartı yok.", 404)
        return b

    def m15_release(engine, tenant, stok: Optional[str]) -> Optional[dict[str, Any]]:
        """Pazarlama çekirdeğinde (M15) bu kitabın onaylı basın bülteni materyali."""
        if not stok:
            return None
        try:
            import sqlalchemy as sa
            MC.ensure(engine)
            with engine.connect() as c:
                m = c.execute(sa.select(MC.MATERIALS).where(MC.MATERIALS.c.stok_kodu == stok, MC.MATERIALS.c.tur == "basin-bulteni",
                                                            MC.MATERIALS.c.durum == "onayli")
                              .order_by(MC.MATERIALS.c.onay_zamani.desc())).first()
        except Exception as e:  # noqa: BLE001 — pazarlama tabloları okunamıyorsa CRM alanına düşülür
            log.warning("pr: M15 materyali okunamadı: %s", e)
            return None
        return {"id": m.id, "planId": m.plan_id, "metin": m.metin, "surum": m.surum, "onaylayan": m.onaylayan,
                "onayZamani": PR.iso(m.onay_zamani)} if m else None

    # ------------------------------------------------------------------ genel

    @app.get(R + "/meta")
    def pr_meta(request: Request) -> dict[str, Any]:
        engine, tenant, user, display = ctx(request)
        s = st()
        return {
            "outletTypes": PR.OUTLET_TYPES, "regions": PR.REGIONS, "kitStatuses": PR.KIT_STATUSES, "channels": PR.CHANNELS,
            "sendStatuses": PR.SEND_STATUSES, "tones": PR.TONES, "coverageSources": PR.COVERAGE_SOURCES,
            "coverageStates": PR.COVERAGE_STATES, "parts": PR.PARTS,
            "settings": {"followUpDays": s["followUpDays"], "reportWeekday": s["reportWeekday"], "webWatch": s["webWatch"],
                         "recipientsSet": bool(s["recipients"]), "smtpSet": bool(alerts_mod.smtp_settings())},
            "lastRun": PR.meta_get(engine, tenant, "run-due") or None,
            "modelReady": getattr(rt(), "llm", None) is not None,
            "me": {"username": user, "display": display, "canEdit": can(user, F_EDIT), "canApprove": can(user, F_APPROVE),
                   "canSend": can(user, F_SEND), "canExport": can(user, F_EXPORT)},
        }

    @app.get(R + "/home")
    async def pr_home(request: Request, ay: str = "", yenile: bool = False) -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        frm, to = call(_month, ay)
        books, err = [], None
        try:
            books = await run_in_threadpool(crm.month_books, frm, to, yenile)
        except S.SourceError as e:
            err = f"CRM okunamadı: {e}"
        kits = PR.list_kits(engine, tenant, books=[b["kitapId"] for b in books]) if books else []
        by_book: dict[str, dict[str, Any]] = {}
        for k in kits:
            cur = by_book.get(k["crmBookId"])
            if cur is None or (cur["status"] == "kapali" and k["status"] != "kapali"):
                by_book[k["crmBookId"]] = k
        rows = [{**b, "kit": by_book.get(b["kitapId"])} for b in books]
        rows.sort(key=lambda b: (b.get("onem") or 999999999, b.get("yayinTarihi") or "", b.get("ad") or ""))
        pending = PR.list_kits(engine, tenant, status="onayda")
        overdue = PR.overdue_sends(engine, tenant)
        since = (PR.today() - timedelta(days=30)).isoformat()
        recent = PR.filter_coverage(PR.list_coverage(engine, tenant, state="kayitli"), frm=since)
        cands = len(PR.list_coverage(engine, tenant, state="aday"))
        out = {
            "month": frm.isoformat()[:7], "from": frm.isoformat(), "to": to.isoformat(), "books": rows, "booksError": err,
            "kpi": {"books": len(rows), "noKit": sum(1 for r in rows if not r["kit"]), "pending": len(pending),
                    "overdue": len(overdue), "recent": len(recent), "candidates": cands},
            "pending": pending, "overdue": overdue, "recentCoverage": recent, "webWatch": st()["webWatch"],
        }
        return PV.bagla(out, lambda: K.for_home(engine, tenant, crm, frm, to, [b["kitapId"] for b in books]))

    @app.get(R + "/books")
    async def pr_books(request: Request, q: str = "", page: int = 0) -> dict[str, Any]:
        await run_in_threadpool(ctx, request)
        if len(q.strip()) < 2:
            return {"items": [], "total": 0, "page": 0, "pageSize": S.SEARCH_PAGE}
        out = await run_in_threadpool(call, crm.search_books, q, page)
        return PV.bagla(out, lambda: K.for_search(q, page))

    @app.get(R + "/books/{bid}")
    async def pr_book(bid: str, request: Request, yenile: bool = False) -> dict[str, Any]:
        engine, tenant, _, _ = await run_in_threadpool(ctx, request)
        book = await run_in_threadpool(call, book_of, bid, yenile)
        archive, note = await run_in_threadpool(archive_or_empty, yenile)
        news = [a for a in archive if any(b.get("kitapId") == book["kitapId"] for b in a.get("books") or [])]
        orders, onote = [], None
        if book.get("stokKodu"):
            try:
                orders = await run_in_threadpool(crm.promo_orders, book["stokKodu"])
            except S.SourceError as e:
                onote = f"Tanıtım gönderimi siparişleri okunamadı: {e}"
        kits = PR.list_kits(engine, tenant, books=[book["kitapId"]])
        out = {"book": book, "kits": kits, "openKit": next((k for k in kits if k["status"] != "kapali"), None),
               "archive": sorted(news, key=lambda a: a.get("tarih") or "", reverse=True), "archiveNote": note,
               "promoOrders": orders, "promoTotal": sum(o["adet"] for o in orders), "promoNote": onote,
               "m15Release": m15_release(engine, tenant, book.get("stokKodu"))}
        return PV.bagla(out, lambda: K.for_book(engine, tenant, crm, book))

    # ------------------------------------------------------------------ PR dosyası

    @app.get(R + "/kits")
    def pr_kits(request: Request, status: str = "") -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        items = PR.list_kits(engine, tenant, status=status)
        return PV.bagla({"items": items, "total": len(items)}, lambda: K.for_kits(engine, tenant, status))

    @app.post(R + "/kits", status_code=201)
    async def pr_kit_create(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        book = await run_in_threadpool(call, book_of, str(body.get("crmBookId") or ""))
        m15 = m15_release(engine, tenant, book.get("stokKodu"))
        crm_text = next((m["metin"] for m in book.get("metinler") or [] if m["alan"] == "new_BasnBlteni"), None)
        release = (m15["metin"], f"m15:{m15['id']}") if m15 else ((crm_text, "crm:new_BasnBlteni") if crm_text else None)
        kid = call(PR.create_kit, engine, tenant, user, book, release)
        kit = PR.kit_full(engine, tenant, kid)
        audit(engine, user, "create", "pr_kit", kid, kit["bookTitle"], {"kitap": kit["crmBookId"], "bulten": (release or (None, None))[1]})
        return kit

    @app.get(R + "/kits/{kit_id}")
    def pr_kit(kit_id: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        kit = call(PR.kit_full, engine, tenant, kit_id)
        # Portal işareti (CRM'deki «E-postaya izin verme» e-posta ucunda ayrıca denetlenir; burada CRM'e gidilmez).
        dnc = {(PR.crm_key(o.crm_contact_id) if o.crm_contact_id else o.id) for o in PR.overlays(engine, tenant) if o.do_not_contact}
        for s in kit["sends"]:
            s["doNotContact"] = s["contactKey"] in dnc
        kit["me"] = {"isSubmitter": (kit.get("submittedBy") or "").lower() == user.lower()}
        return PV.bagla(kit, lambda: K.for_kit(engine, tenant, kit))

    @app.patch(R + "/kits/{kit_id}")
    def pr_kit_update(kit_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        before = call(PR.kit_full, engine, tenant, kit_id)
        out = call(PR.update_kit, engine, tenant, user, kit_id, body)
        audit(engine, user, "update", "pr_kit", kit_id, out["bookTitle"],
              {"alanlar": sorted(body), "durum": out["status"], "onayDustu": before["status"] == "onayli" and out["status"] == "taslak"})
        return out

    @app.get(R + "/kits/{kit_id}/events")
    def pr_kit_events(kit_id: str, request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        call(PR.kit_full, engine, tenant, kit_id)
        return PV.bagla({"items": PR.events(engine, tenant, kit_id)}, lambda: K.for_events(engine, tenant, kit_id))

    def run_draft(jid: str, tenant: str, user: str, kit_id: str, parts: list[str]) -> None:
        engine = rt().store.engine
        try:
            PR.job_update(engine, jid, status="calisiyor", step="Kitap kartı okunuyor")
            kit = PR.kit_full(engine, tenant, kit_id)
            book = crm.book(kit["crmBookId"])
            if not book:
                raise PR.PrError("CRM'de kitap kartı bulunamadı.")
            m = llm()
            if m is None:
                PR.job_update(engine, jid, status="bitti", step=None,
                              result={"uyari": "Zeki AI modeli bu kurulumda bağlı değil; taslak yazılamadı."})
                return
            extra = []
            m15 = m15_release(engine, tenant, book.get("stokKodu"))
            if m15:
                extra.append(("Pazarlama planında onaylı basın bülteni", m15["metin"]))
            drafts: dict[str, dict[str, Any]] = {}
            for part in parts:
                PR.job_update(engine, jid, step=f"{PR.PARTS[part]} yazılıyor")
                drafts[part] = PR.draft_part(m, book, part, st()["claims"], extra)
            filled = PR.put_draft(engine, tenant, user, kit_id, drafts)
            PR.job_update(engine, jid, status="bitti", step=None,
                          result={"parcalar": {k: {"sonuc": filled.get(k, "oneri"), "dusen": v.get("dusenSayisi", 0),
                                                   "bos": not v.get("metin")} for k, v in drafts.items()}})
            audit(engine, user, "run", "pr_kit", kit_id, "Zeki AI taslağı", {"parcalar": parts, "sonuc": filled})
        except Exception as e:  # noqa: BLE001 — iş hatası ekranda görünür, köprüyü düşürmez
            log.exception("pr draft job failed")
            PR.job_update(engine, jid, status="hata", step=None, error=str(e)[:500] or e.__class__.__name__)

    @app.post(R + "/kits/{kit_id}/draft", status_code=202)
    def pr_kit_draft(kit_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        """Zeki AI taslağı arka planda; ekran `GET kits/{id}`deki `job` alanını sorar. Boş alan doldurulur, yazılmış
        metin ezilmez (öneri olarak yanında durur)."""
        engine, tenant, user, _ = ctx(request)
        kit = call(PR.kit_full, engine, tenant, kit_id)
        if kit["status"] == "kapali":
            raise HTTPException(status_code=409, detail={"code": "PR", "message": "Kapalı dosyaya taslak yazılmaz."})
        parts = [p for p in (body.get("parts") or ["national", "local", "pitch", "openings"]) if p in PR.PROMPTS]
        if not parts:
            raise HTTPException(status_code=400, detail={"code": "PR", "message": "Yazılacak bölüm seçilmedi."})
        job = call(PR.job_create, engine, tenant, user, kit_id, "draft")
        pool.submit(run_draft, job["id"], tenant, user, kit_id, parts)
        return {"job": job}

    @app.get(R + "/jobs/{jid}")
    def pr_job(jid: str, request: Request) -> dict[str, Any]:
        engine, _, _, _ = ctx(request)
        return call(PR.job_get, engine, jid)

    @app.post(R + "/kits/{kit_id}/submit")
    def pr_kit_submit(kit_id: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(PR.submit_kit, engine, tenant, user, kit_id)
        audit(engine, user, "update", "pr_kit", kit_id, out["bookTitle"], {"durum": "onayda", "liste": len(out["sends"])})
        s = st()
        if s["recipients"]:
            text = (f"{user} basın dosyasını onaya gönderdi.\nKitap: {out['bookTitle']} ({out['id']})\n"
                    f"Gönderim listesi: {sum(1 for x in out['sends'] if x['status'] == 'hazir')} kişi\n"
                    + (f"\nDosya: {link('dosya/' + out['id'])}" if link() else ""))
            pool.submit(_send_mail, f"Onay bekleyen basın dosyası: {out['bookTitle']}", text, s["recipients"])
        return out

    @app.post(R + "/kits/{kit_id}/withdraw")
    def pr_kit_withdraw(kit_id: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(PR.withdraw_kit, engine, tenant, user, kit_id)
        audit(engine, user, "update", "pr_kit", kit_id, out["bookTitle"], {"durum": "taslak", "neden": "onaydan geri çekildi"})
        return out

    def _decide(kit_id: str, body: dict[str, Any], request: Request, approve: bool) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, F_APPROVE, "Basın dosyası onayı")
        out = call(PR.decide_kit, engine, tenant, user, kit_id, approve, body.get("note"))
        audit(engine, user, "approve" if approve else "reject", "pr_kit", kit_id, out["bookTitle"],
              {"not": body.get("note"), "durum": out["status"]})
        owner_mail = crm.email_of(out.get("submittedBy") or out.get("owner") or "")
        if owner_mail:
            what = "onaylandı" if approve else "geri gönderildi"
            text = (f"Basın dosyası {what} ({user}).\nKitap: {out['bookTitle']} ({out['id']})\n"
                    + (f"Gerekçe: {body.get('note')}\n" if body.get("note") else "")
                    + (f"\nDosya: {link('dosya/' + out['id'])}" if link() else ""))
            pool.submit(_send_mail, f"Basın dosyası {what}: {out['bookTitle']}", text, [owner_mail])
        return out

    @app.post(R + "/kits/{kit_id}/approve")
    def pr_kit_approve(kit_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        return _decide(kit_id, body, request, True)

    @app.post(R + "/kits/{kit_id}/reject")
    def pr_kit_reject(kit_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        return _decide(kit_id, body, request, False)

    @app.post(R + "/kits/{kit_id}/close")
    def pr_kit_close(kit_id: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(PR.close_kit, engine, tenant, user, kit_id)
        audit(engine, user, "update", "pr_kit", kit_id, out["bookTitle"], {"durum": "kapali"})
        return out

    @app.post(R + "/kits/{kit_id}/reopen")
    def pr_kit_reopen(kit_id: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(PR.close_kit, engine, tenant, user, kit_id, True)
        audit(engine, user, "update", "pr_kit", kit_id, out["bookTitle"], {"durum": out["status"], "yenidenAcildi": True})
        return out

    @app.get(R + "/kits/{kit_id}/suggest-contacts")
    async def pr_suggest(kit_id: str, request: Request, page: int = 0, q: str = "") -> dict[str, Any]:
        """Kitaba uygun medya kişileri, kural puanıyla sıralı (hepsi; sayfa başı 50). Gerekçe her satırda."""
        engine, tenant, _, _ = await run_in_threadpool(ctx, request)
        kit = call(PR.kit_full, engine, tenant, kit_id)
        book = await run_in_threadpool(call, book_of, kit["crmBookId"])
        contacts, note = await run_in_threadpool(contacts_all, engine, tenant)
        archive, anote = await run_in_threadpool(archive_or_empty)
        ranked = PR.suggest(contacts, archive, book, PR.history_by_contact(engine, tenant), {s["contactKey"] for s in kit["sends"]})
        if q:
            fq = PR.fold(q)
            ranked = [r for r in ranked if fq in PR.fold(f"{r['name']} {r.get('outlet') or ''} {' '.join(r.get('topics') or [])}")]
        out = {**PR.page_of(ranked, page), "note": note or anote,
               "rule": "Puan kuraldır: yazarın kitapları hakkında haber ×3, aynı kitaplık ×2, aynı hedef kitle ×1 (CRM haber "
                       "arşivi), konu etiketi eşleşmesi ×2, portalda yansıma ×1, dönüş ×1, olumsuz −1, son bir yılda temas +1."}
        return PV.bagla(out, lambda: K.for_suggest(engine, tenant, crm, kit))

    # ------------------------------------------------------------------ gönderim satırları

    @app.post(R + "/kits/{kit_id}/sends", status_code=201)
    async def pr_sends_add(kit_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        keys = [str(k) for k in (body.get("contactKeys") or []) if k]
        contacts, _ = await run_in_threadpool(contacts_all, engine, tenant)
        by = {c["key"]: c for c in contacts}
        missing = [k for k in keys if k not in by]
        if missing:
            raise HTTPException(status_code=404, detail={"code": "PR", "message": f"{len(missing)} kişi bulunamadı (CRM okunamamış olabilir)."})
        out = call(PR.add_sends, engine, tenant, user, kit_id, [by[k] for k in keys], str(body.get("channel") or "eposta"))
        kit = PR.kit_full(engine, tenant, kit_id)
        audit(engine, user, "update", "pr_kit", kit_id, kit["bookTitle"], {"listeyeEklenen": len(out["added"]), "atlanan": len(out["skipped"])})
        return {**out, "kit": kit}

    @app.patch(R + "/sends/{sid}")
    def pr_send_update(sid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(PR.update_send, engine, tenant, user, sid, body, st()["followUpDays"])
        audit(engine, user, "update", "pr_send", sid, out["contactName"], {k: body[k] for k in ("status", "channel", "crmOrderNo") if k in body})
        return out

    @app.delete(R + "/sends/{sid}")
    def pr_send_delete(sid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(PR.delete_send, engine, tenant, user, sid)
        audit(engine, user, "delete", "pr_send", sid, None)
        return out

    @app.post(R + "/sends/{sid}/approve")
    def pr_send_approve(sid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, F_APPROVE, "Gönderim onayı")
        out = call(PR.approve_send, engine, tenant, user, sid)
        audit(engine, user, "approve", "pr_send", sid, out["contactName"])
        return out

    def run_pitch(jid: str, tenant: str, user: str, sid: str) -> None:
        engine = rt().store.engine
        try:
            PR.job_update(engine, jid, status="calisiyor", step="Kişiye özel metin yazılıyor")
            send = PR.get_send(engine, tenant, sid)
            kit = PR.kit_full(engine, tenant, send["kitId"])
            book = crm.book(kit["crmBookId"])
            contacts, _ = contacts_all(engine, tenant)
            contact = PR.find_contact(contacts, send["contactKey"])
            archive, _ = archive_or_empty()
            guid, _pid = PR.split_key(send["contactKey"])
            titles = [a["baslik"] for a in archive if guid and guid in (a.get("muhabirId"), a.get("gorusulenId")) and a.get("baslik")]
            m = llm()
            if m is None or not book:
                PR.job_update(engine, jid, status="bitti", step=None, result={"uyari": "Zeki AI modeli ya da kitap kartı yok; metin yazılamadı."})
                return
            res = PR.personal_pitch(m, book, contact, kit.get("pitchTemplate"), titles, st()["claims"])
            if res["metin"]:
                PR.update_send(engine, tenant, user, sid, {"pitch": res["metin"], "pitchSource": "zeki"}, st()["followUpDays"])
            PR.job_update(engine, jid, status="bitti", step=None, result={"dusen": res["dusenSayisi"], "bos": not res["metin"], "dusenler": res["dusen"]})
        except Exception as e:  # noqa: BLE001
            log.exception("pr pitch job failed")
            PR.job_update(engine, jid, status="hata", step=None, error=str(e)[:500] or e.__class__.__name__)

    @app.post(R + "/sends/{sid}/pitch", status_code=202)
    def pr_send_pitch(sid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        send = call(PR.get_send, engine, tenant, sid)
        if send["sentAt"]:
            raise HTTPException(status_code=409, detail={"code": "PR", "message": "Gönderilmiş satırın metni değiştirilemez."})
        job = call(PR.job_create, engine, tenant, user, sid, "pitch")
        pool.submit(run_pitch, job["id"], tenant, user, sid)
        return {"job": job}

    @app.get(R + "/sends/{sid}/job")
    def pr_send_job(sid: str, request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        import sqlalchemy as sa
        with engine.connect() as c:
            j = c.execute(sa.select(PR.JOBS).where(PR.JOBS.c.ref_id == sid, PR.JOBS.c.tenant_id == tenant)
                          .order_by(PR.JOBS.c.created_at.desc()).limit(1)).first()
        return {"job": PR.job_dict(j) if j else None}

    def mail_one(engine, tenant: str, user: str, display: str, kit: dict[str, Any], send: dict[str, Any], contact: dict[str, Any],
                 bulten: str, subject: str) -> str:
        cfg = alerts_mod.smtp_settings()
        if not cfg:
            return "no_smtp"
        reply_to = crm.email_of(user)
        body = send["pitch"].strip()
        release = {"ulusal": kit.get("releaseNational"), "yerel": kit.get("releaseLocal")}.get(bulten)
        if release:
            body += "\n\n———\nBasın bülteni\n\n" + release.strip()
        body += f"\n\n—\n{display or user}\nTimaş Yayınları" + (f"\n{reply_to}" if reply_to else "")
        try:
            msg = EmailMessage()
            msg["Subject"] = subject
            msg["From"] = formataddr((f"{display or user} (Timaş Yayınları)", cfg["sender"]))
            msg["To"] = formataddr((contact.get("name") or "", contact["email"]))
            if reply_to:
                msg["Reply-To"] = formataddr((display or user, reply_to))
            msg.set_content(body)
            ctx_ = ssl.create_default_context()
            server = (smtplib.SMTP_SSL(cfg["host"], cfg["port"], timeout=20, context=ctx_) if cfg["ssl"]
                      else smtplib.SMTP(cfg["host"], cfg["port"], timeout=20))
            with server as s:
                if not cfg["ssl"] and cfg["starttls"]:
                    s.starttls(context=ctx_)
                if cfg["user"]:
                    s.login(cfg["user"], cfg["password"])
                s.send_message(msg)
            return "gonderildi"
        except Exception as e:  # noqa: BLE001
            log.warning("pr: e-posta gönderilemedi (%s): %s", send["id"], e)
            return "gonderilemedi"

    @app.post(R + "/sends/{sid}/mail")
    async def pr_send_mail(sid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        """Tek alıcıya, onaylı satırdan e-posta. Toplu gönderim yok: her çağrı bir kişi, bir satır."""
        engine, tenant, user, display = await run_in_threadpool(ctx, request)
        need(user, F_SEND, "Basına e-posta gönderme")
        send = call(PR.get_send, engine, tenant, sid)
        kit = call(PR.kit_full, engine, tenant, send["kitId"])
        contacts, _ = await run_in_threadpool(contacts_all, engine, tenant)
        contact = call(PR.find_contact, contacts, send["contactKey"])
        why = PR.mail_check(kit, send, contact)
        if why:
            raise HTTPException(status_code=409, detail={"code": "PR", "message": why})
        bulten = str(body.get("bulten") or "ulusal")
        if bulten not in ("ulusal", "yerel", "yok"):
            raise HTTPException(status_code=400, detail={"code": "PR", "message": "Bülten ulusal, yerel ya da yok olmalı."})
        subject = PR.one_line(body.get("subject"), 200) or f"{kit['bookTitle']} · Timaş Yayınları"
        result = await run_in_threadpool(mail_one, engine, tenant, user, display, kit, send, contact, bulten, subject)
        if result == "no_smtp":
            raise HTTPException(status_code=503, detail={"code": "PR", "message": "E-posta ayarı yok (Yönetim → E-posta); gönderilmedi."})
        out = PR.record_mail(engine, tenant, user, sid, result, st()["followUpDays"])
        audit(engine, user, "run", "pr_send", sid, send["contactName"], {"eposta": result, "kisi": contact["key"], "bulten": bulten,
                                                                         "kit": kit["id"]})
        if result != "gonderildi":
            raise HTTPException(status_code=502, detail={"code": "PR", "message": "E-posta gönderilemedi; satır «gönderilecek» kaldı."})
        return out

    # ------------------------------------------------------------------ medya kişileri

    @app.get(R + "/contacts")
    async def pr_contacts(request: Request, q: str = "", tur: str = "", etiket: str = "", kaynak: str = "", izin: str = "",
                          page: int = 0, yenile: bool = False) -> dict[str, Any]:
        engine, tenant, _, _ = await run_in_threadpool(ctx, request)
        contacts, note = await run_in_threadpool(contacts_all, engine, tenant, yenile)
        hist = PR.history_by_contact(engine, tenant)
        fq, fe = PR.fold(q), PR.fold(etiket)
        rows = []
        for c in contacts:
            if fq and fq not in PR.fold(f"{c['name']} {c.get('outlet') or ''} {c.get('email') or ''} {c.get('role') or ''}"):
                continue
            if tur and c.get("outletType") != tur:
                continue
            if fe and not any(fe in PR.fold(t) for t in c.get("topics") or []):
                continue
            if kaynak and c["source"] != kaynak:
                continue
            if izin == "yok" and not c["doNotContact"]:
                continue
            if izin == "var" and c["doNotContact"]:
                continue
            rows.append({**c, "history": hist.get(c["key"]) or {}})
        rows.sort(key=lambda c: PR.fold(c["name"]))
        tags = sorted({t for c in contacts for t in c.get("topics") or []}, key=PR.fold)
        return PV.bagla({**PR.page_of(rows, page), "note": note, "tags": tags, "all": len(contacts)},
                        lambda: K.for_contacts(engine, tenant, crm))

    @app.post(R + "/contacts", status_code=201)
    async def pr_contact_create(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        cid = call(PR.create_contact, engine, tenant, user, body)
        audit(engine, user, "create", "pr_contact", cid, PR.one_line(body.get("name"), 200))
        contacts, _ = await run_in_threadpool(contacts_all, engine, tenant)
        return PR.find_contact(contacts, cid)

    @app.get(R + "/contacts/{key}")
    async def pr_contact(key: str, request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = await run_in_threadpool(ctx, request)
        contacts, note = await run_in_threadpool(contacts_all, engine, tenant)
        c = call(PR.find_contact, contacts, key)
        archive, anote = await run_in_threadpool(archive_or_empty)
        guid, _ = PR.split_key(key)
        news = [a for a in archive if guid and guid in (a.get("muhabirId"), a.get("gorusulenId"))]
        cov = [x for x in PR.list_coverage(engine, tenant, state="kayitli") if x["contactKey"] == key]
        out = {"contact": c, "history": PR.history_by_contact(engine, tenant).get(key) or {},
               "archive": sorted(news, key=lambda a: a.get("tarih") or "", reverse=True), "sends": PR.sends_of_contact(engine, tenant, key),
               "coverage": sorted(cov, key=lambda x: x["publishedAt"] or "", reverse=True), "events": PR.events(engine, tenant, key),
               "note": note or anote}
        return PV.bagla(out, lambda: K.for_contact(engine, tenant, crm, key))

    @app.patch(R + "/contacts/{key}")
    async def pr_contact_update(key: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        known: set[str] = set()
        if key.startswith("crm:"):
            try:
                known = {c["id"] for c in await run_in_threadpool(crm.media_contacts)}
            except S.SourceError as e:
                raise HTTPException(status_code=503, detail={"code": "PR_SOURCE", "message": str(e)}) from e
        call(PR.update_contact, engine, tenant, user, key, body, lambda g: g in known)
        audit(engine, user, "update", "pr_contact", key, None, {"alanlar": sorted(body), "haberdarOlmakIstemiyor": body.get("doNotContact")})
        contacts, _ = await run_in_threadpool(contacts_all, engine, tenant)
        return PR.find_contact(contacts, key)

    @app.delete(R + "/contacts/{key}")
    def pr_contact_delete(key: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(PR.delete_contact, engine, tenant, user, key)
        audit(engine, user, "delete", "pr_contact", key, out.get("name"))
        return out

    # ------------------------------------------------------------------ yansımalar

    @app.get(R + "/coverage")
    async def pr_coverage(request: Request, frm: str = "", to: str = "", kitap: str = "", kaynak: str = "", ton: str = "",
                          q: str = "", durum: str = "kayitli", kisi: str = "", page: int = 0) -> dict[str, Any]:
        engine, tenant, _, _ = await run_in_threadpool(ctx, request)
        state = durum if durum in PR.COVERAGE_STATES else "kayitli"
        rows = PR.list_coverage(engine, tenant, state=state)
        note = None
        with_archive = kaynak in ("", "crm-arsiv") and durum in ("", "kayitli")
        if with_archive:
            archive, note = await run_in_threadpool(archive_or_empty)
            rows += [PR.archive_as_coverage(a) for a in archive]
        out = PR.filter_coverage(rows, frm=frm or None, to=to or None, book=kitap, source=kaynak, tone=ton, q=q, contact=kisi)
        counts = {"kayitli": 0, "aday": 0, "reddedildi": 0}
        for r in PR.list_coverage(engine, tenant, state=""):
            counts[r["state"]] = counts.get(r["state"], 0) + 1
        res = {**PR.page_of(out, page), "note": note, "counts": counts, "webWatch": st()["webWatch"], "archivePath": crm.archive_path}
        return PV.bagla(res, lambda: K.for_coverage(engine, tenant, crm, state, with_archive))

    @app.post(R + "/coverage/preview")
    async def pr_coverage_preview(body: dict[str, Any], request: Request) -> dict[str, Any]:
        """Yapıştırılan bağlantının başlığı, tarihi ve mecrası (yalnız o sayfa). Ortamda web okuma kapalıysa istek
        yapılmaz; ekran elle girişe geçer. Kitap ve kişi önerisi açık PR dosyalarından ve medya kişilerinden."""
        engine, tenant, _, _ = await run_in_threadpool(ctx, request)
        url = call(PR._clean_url, body.get("url"))
        if not url:
            raise HTTPException(status_code=400, detail={"code": "PR", "message": "Bağlantı gerekli."})
        import sqlalchemy as sa
        with engine.connect() as c:
            dup = c.execute(sa.select(PR.COVERAGE.c.id, PR.COVERAGE.c.state).where(PR.COVERAGE.c.tenant_id == tenant,
                                                                                  PR.COVERAGE.c.url == url)).first()
        if dup:
            return {"duplicate": {"id": dup.id, "state": dup.state}}
        if not st()["webWatch"]:
            page = {"disabled": True, "error": "Bu ortamda web okuma kapalı; başlık ve tarihi elle girin."}
        else:
            page = await run_in_threadpool(S.fetch_page, url)
        hay = PR.fold(f"{page.get('title') or ''} {page.get('summary') or ''}")
        books = []
        if hay:
            for k in PR.list_kits(engine, tenant, include_closed=False):
                if (k["bookTitle"] and PR.fold(k["bookTitle"]) in hay) or (k["author"] and PR.fold(k["author"]) in hay):
                    books.append({"crmBookId": k["crmBookId"], "bookTitle": k["bookTitle"], "author": k["author"], "kitId": k["id"]})
        people = []
        host = (page.get("host") or "").replace("www.", "")
        if host or page.get("outlet"):
            contacts, _ = await run_in_threadpool(contacts_all, engine, tenant)
            fo = PR.fold(page.get("outlet"))
            for c in contacts:
                dom = (c.get("email") or "").split("@")[-1].lower()
                if (host and dom and (dom == host or host.endswith("." + dom))) or (fo and c.get("outlet") and PR.fold(c["outlet"]) == fo):
                    people.append({"key": c["key"], "name": c["name"], "outlet": c.get("outlet")})
        return {**page, "summary": PR.short_summary(page.get("summary")), "books": books, "contacts": people}

    def run_tone(jid: str, tenant: str, cid: str) -> None:
        engine = rt().store.engine
        try:
            PR.job_update(engine, jid, status="calisiyor", step="Ton sınıflanıyor")
            import sqlalchemy as sa
            with engine.connect() as c:
                r = c.execute(sa.select(PR.COVERAGE).where(PR.COVERAGE.c.id == cid)).first()
            if r is None:
                PR.job_update(engine, jid, status="bitti", step=None, result={"uyari": "Kayıt silinmiş."})
                return
            s = st()
            tone, prob, info = PR.classify_tone(llm(), r.title, r.summary, r.book_title, r.author_name, s["toneMinProb"], s["toneMinMargin"])
            if info.get("method") != "yok":
                PR.set_tone(engine, cid, tone, prob)
            PR.job_update(engine, jid, status="bitti", step=None, result={"ton": tone, "olasilik": prob, "yontem": info.get("method")})
        except Exception as e:  # noqa: BLE001
            log.exception("pr tone job failed")
            PR.job_update(engine, jid, status="hata", step=None, error=str(e)[:500] or e.__class__.__name__)

    @app.post(R + "/coverage", status_code=201)
    def pr_coverage_add(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(PR.add_coverage, engine, tenant, user, body)
        audit(engine, user, "create", "pr_coverage", out["id"], out["title"], {"url": out["url"], "kitap": out["crmBookId"],
                                                                              "satir": out["sendId"]})
        if not out["tone"] and getattr(rt(), "llm", None) is not None:
            try:
                job = PR.job_create(engine, tenant, user, out["id"], "tone")
                pool.submit(run_tone, job["id"], tenant, out["id"])
                out["job"] = job
            except PR.PrError:
                pass
        return out

    @app.patch(R + "/coverage/{cid}")
    def pr_coverage_update(cid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(PR.update_coverage, engine, tenant, user, cid, body)
        audit(engine, user, "update", "pr_coverage", cid, out["title"], {k: body[k] for k in body if k in ("state", "tone", "crmBookId", "contactKey")})
        return out

    @app.delete(R + "/coverage/{cid}")
    def pr_coverage_delete(cid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(PR.delete_coverage, engine, tenant, user, cid)
        audit(engine, user, "delete", "pr_coverage", cid, out["title"])
        return out

    # ------------------------------------------------------------------ rapor

    def _range(frm: str, to: str) -> tuple[str, str]:
        f, t = PR.day(frm, "Başlangıç"), PR.day(to, "Bitiş")
        if not f or not t:
            f, t = PR.week_of(PR.today())
        if t < f:
            raise PR.PrError("Bitiş başlangıçtan önce olamaz.")
        return f, t

    def build_report(engine, tenant, frm: str, to: str) -> dict[str, Any]:
        archive, note = archive_or_empty()
        rep = PR.report(engine, tenant, frm, to, archive)
        if note:
            rep["archive"] = {"total": None, "note": note}
        return rep

    @app.get(R + "/report")
    async def pr_report(request: Request, frm: str = "", to: str = "", yorum: bool = False) -> dict[str, Any]:
        engine, tenant, _, _ = await run_in_threadpool(ctx, request)
        f, t = call(_range, frm, to)
        rep = await run_in_threadpool(build_report, engine, tenant, f, t)
        if yorum:
            m = llm()
            rep["comment"] = (await run_in_threadpool(PR.report_comment, m, rep, st()["claims"])) if m is not None else None
        return PV.bagla(rep, lambda: K.for_report(engine, tenant, crm))

    @app.get(R + "/report/export.pdf")
    async def pr_report_pdf(request: Request, frm: str = "", to: str = "") -> Response:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        f, t = call(_range, frm, to)
        rep = await run_in_threadpool(build_report, engine, tenant, f, t)
        body = await run_in_threadpool(call, X.report_pdf, rep, None, user)
        audit(engine, user, "run", "pr_report", f"{f}_{t}", "Basın yansıma raporu", {"disaAktar": "pdf"})
        return Response(body, media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="basin-yansima-{f}-{t}.pdf"'})

    @app.get(R + "/report/export.xlsx")
    async def pr_report_xlsx(request: Request, frm: str = "", to: str = "") -> Response:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        f, t = call(_range, frm, to)
        rep = await run_in_threadpool(build_report, engine, tenant, f, t)
        body = await run_in_threadpool(X.report_xlsx, rep)
        audit(engine, user, "run", "pr_report", f"{f}_{t}", "Basın yansıma raporu", {"disaAktar": "xlsx"})
        return Response(body, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="basin-yansima-{f}-{t}.xlsx"'})

    # ------------------------------------------------------------------ zamanlayıcı

    @app.post(R + "/run-due")
    def pr_run_due(request: Request, force: bool = False) -> dict[str, Any]:
        """Günlük: (1) takip günü geçen cevapsız gönderimler tek özet e-postayla (alıcılar + dosya sahipleri);
        (2) Basın ve web taramasından yeni aday yansımalar (ortamda kapalıysa atlanır); (3) tonu sınıflanmamış elle
        girilmiş yansımalar; (4) haftalık yansıma özeti (Yönetim ayarındaki gün, haftada bir)."""
        require_caller(request)
        engine, tenant = db()
        s = st()
        t = PR.today()
        out: dict[str, Any] = {"tarih": t.isoformat()}

        # 1 — hatırlatma
        due = [x for x in PR.overdue_sends(engine, tenant, t) if not x["remindedAt"] or force]
        out["hatirlatma"] = {"bekleyen": len(due)}
        if due:
            groups: dict[str, list[dict[str, Any]]] = {}
            for x in due:
                groups.setdefault(x.get("owner") or "", []).append(x)
            lines = [f"- {x['bookTitle']} → {x['contactName']} ({x.get('outlet') or '—'}), gönderim "
                     f"{PR.local_day(datetime.fromisoformat(x['sentAt'])) if x['sentAt'] else '—'}, takip günü {x['followUpAt']}"
                     for x in due]
            text = ("Takip günü geçmiş, cevap beklenen basın gönderimleri:\n\n" + "\n".join(lines)
                    + (f"\n\nBasın ilişkileri: {link()}" if link() else "") + "\n\nPortal hiçbir gazeteciye kendiliğinden yazmaz; takibi siz yaparsınız.")
            to = list(s["recipients"])
            for owner in groups:
                m = crm.email_of(owner) if owner else None
                if m and m not in to:
                    to.append(m)
            status = _send_mail(f"ZEKİ basın: cevap beklenen {len(due)} gönderim ({t.strftime('%d.%m.%Y')})", text, to) if to else "no_recipient"
            out["hatirlatma"]["eposta"] = status
            if status == "sent":
                PR.mark_reminded(engine, [x["id"] for x in due])

        # 2 — Basın ve web adayları
        if s["webWatch"]:
            last = PR.meta_get(engine, tenant, "web-since")
            since = datetime.fromisoformat(last["at"]) if last.get("at") else None
            started_at = PR.now()
            try:
                items = S.web_candidates(engine, tenant, since)
                out["web"] = PR.import_web(engine, tenant, items)
                PR.meta_set(engine, tenant, "web-since", {"at": started_at.isoformat()})
            except Exception as e:  # noqa: BLE001
                out["web"] = {"hata": str(e)[:300]}
        else:
            out["web"] = {"atlandi": "Basın ve web taraması bu ortamda kapalı (WEB_WATCH_ENABLED)."}

        # 3 — ton sınıflaması (gece, arka plan önceliği)
        pending = PR.untoned(engine, tenant)
        m = llm("batch") if pending else None
        done = unsure = 0
        if m is not None:
            for c in pending:
                try:
                    tone, prob, info = PR.classify_tone(m, c["title"], c["summary"], c["bookTitle"], c["authorName"],
                                                        s["toneMinProb"], s["toneMinMargin"])
                except Exception as e:  # noqa: BLE001 — model yok/cevap yok: sonraki gece
                    out["tonHata"] = str(e)[:300]
                    break
                PR.set_tone(engine, c["id"], tone, prob)
                done += 1
                unsure += tone is None
        out["ton"] = {"bekleyen": len(pending), "siniflanan": done, "eminDegil": unsure, "model": m is not None}

        # 4 — haftalık özet
        week_key = f"{t.isocalendar()[0]}-W{t.isocalendar()[1]:02d}"
        last_rep = PR.meta_get(engine, tenant, "weekly")
        if (t.isoweekday() == s["reportWeekday"] and last_rep.get("hafta") != week_key) or force:
            f, e = PR.week_of(t)
            rep = build_report(engine, tenant, f, e)
            cm = llm("batch")
            comment = None
            if cm is not None:
                try:
                    comment = PR.report_comment(cm, rep, s["claims"]).get("metin")
                except Exception as ex:  # noqa: BLE001
                    log.warning("pr: haftalık yorum yazılamadı: %s", ex)
            text = (f"Basın yansıma özeti {f} – {e}\n\n" + (f"{comment}\n\n" if comment else "")
                    + f"Gönderim: {rep['sends']['total']} · dönüş: {rep['sends']['answered']}\n"
                    + f"Kayıtlı yansıma: {rep['coverage']['total']} · onay bekleyen aday: {rep['pendingCandidates']}\n"
                    + "".join(f"- {r['publishedAt'] or '—'} · {r['outlet'] or '—'} · {r['title']}\n" for r in rep["coverage"]["items"])
                    + (f"\nRapor: {link('rapor')}" if link() else ""))
            rcp = s["reportRecipients"]
            status = _send_mail(f"ZEKİ basın: haftalık yansıma özeti ({f} – {e})", text, rcp) if rcp else "no_recipient"
            PR.meta_set(engine, tenant, "weekly", {"hafta": week_key, "sonuc": status, "donem": [f, e]})
            out["haftalik"] = {"hafta": week_key, "eposta": status}
        PR.meta_set(engine, tenant, "run-due", out)
        return out

    return {"crm": crm, "pool": pool}
