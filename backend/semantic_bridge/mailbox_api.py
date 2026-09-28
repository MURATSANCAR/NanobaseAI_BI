"""H4 Kurumsal e-posta uçları: /api/v1/mailbox/*.

Sayfa kapısı `access.RULES` (`sayfa:kurumsal-eposta`); atama, tür/durum düzeltme, başvuru aktarımı ve etiketleme
`ozellik:eposta.ata`, kural taslağı `ozellik:eposta.kural` (`FEATURE_RULES`). Açıkça verilen iki özellik uçların içinde
denetlenir: `ozellik:eposta.kural-onay` (kural sürümünü yürürlüğe alma; taslağı yazan onaylayamaz) ve `ozellik:eposta.ik`
(iş başvurularını görme; **yöneticiye istisna yok**, anahtar rolle verilmiş olmalı). Bütün kutuyu görmek
`ozellik:eposta.herkesinki`; yoksa kişi yalnız kendine ve birimine atananları görür.

Zamanlayıcılar yalnız iki ucu çağırır: `POST run-due` (5 dk; kutuyu okur, sınıflar, yanıtları zincirden işler) ve
`POST sla-due` (saatlik; iş saatleriyle hatırlatma/eskalasyon, iç e-posta). Dışarıya hiçbir ileti gitmez (kullanıcı kararı
2026-09-28): yanıt taslağı ekranda düzenlenir, kişi kutunun kendi arayüzünden («Kutuda aç») gönderir.

Sözleşme uçları: `GET applications?status=yeni` (yazar giriş süreci ekranı okur). Aktarım bağlantıları: dosya başvurusu →
M1 `POST /api/v1/editorial/applications` (+ ekler `PUT …/{id}/files`), iş başvurusu → M55 `POST /api/v1/hr/recruit/intake`.
İkisi de köprünün içinden, kişinin kendi oturum çereziyle çağrılır (kişinin o modüldeki yetkisi aynen uygulanır); uç bu
kurulumda yoksa ileti «aktarılmayı bekliyor» kalır.
"""
from __future__ import annotations

import logging
import os
import smtplib
import ssl
import threading
import time
from datetime import date, datetime, timedelta
from email.message import EmailMessage
from typing import Any, Callable, Optional

import httpx
from fastapi import HTTPException, Request
from starlette.concurrency import run_in_threadpool

from semantic_bridge import mailbox as M
from semantic_bridge import mailbox_classify as K
from semantic_bridge import mailbox_sources as S
from semantic_bridge import provenance as PV
from semantic_bridge import sorgu_izi as IZ

F_OZET = 'Kurumsal e-posta: bana atanan, süresi aşan, atanmamış, birimim ve bugün gelen sayıları kutudan inen ileti kayıtlarından (durum, atanan, SLA); sınıflanmayı bekleyen = türü henüz yazılmamış ileti; sekme rozetleri aynı sayımlar. İletiler posta kutusundan 5 dakikada bir portala iner (yalnız okuma + etiket).'
F_LISTE = 'İleti listesi: sayfalama toplamı süzgece uyan ileti sayısı; ek sayısı iletinin kaydından; kalan SLA süresi = türün SLA süresi − iş saati olarak geçen süre.'
F_DETAY = 'İleti: kalan/aşan SLA süresi iş saatine göre; ek boyutları posta kutusundan anlık (gövde portalda saklanmaz); gönderen tanıma CRM kişi/firma kaydından.'
F_BASVURU = 'Başvurular kutusu: bekleyen başvuru ve ek sayısı başvuru kayıtlarından.'
F_ROZET = 'Menü rozeti: size atanan açık ileti ve süresi aşan ileti sayısı.'
F_RAPOR = 'Rapor: gelen = dönemde gelen ileti; yanıtlanan = yanıt olayı olan (oranı gelen üstünden); SLA uyumu = süresi içinde yanıtlanan ÷ yanıtlanan; tür düzeltme = türü elle değiştirilen ÷ sınıflanan; ilk yanıt ve kapanış süreleri iş saati ve takvim olarak medyan; birim/kişi ve haftalık tablolar aynı sayımın kırılımı.'
F_ETIKET = 'Etiketleme: Zeki AI doğruluğu = insan etiketiyle aynı türü seçtiği ileti ÷ insan etiketi olan ileti; karışıklık tablosu tür başına uyuşan / toplam ve en sık karışan tür.'
KUTU_DIS = "Posta kutusu, anlık okuma (gövde ve ekler portalda saklanmaz)"

log = logging.getLogger("semantic.mailbox.api")
P = "/api/v1/mailbox"
M1_APPLICATIONS = "/api/v1/editorial/applications"
M55_INTAKE = "/api/v1/hr/recruit/intake"
#: M1'in kabul ettiği ek türleri (editorial_applications.FILE_EXT); diğer ekler aktarılmaz, adı nota yazılır.
M1_FILE_EXT = {"pdf", "docx", "doc"}


def send_mail(subject: str, text: str, to: list[str]) -> str:
    """İç bildirim (SMTP, Yönetim → E-posta). Kutunun adresinden değil portalın bildirim hesabından gider."""
    from semantic_bridge.alerts import smtp_settings

    if not to:
        return "no_recipient"
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
        log.warning("kurumsal e-posta bildirimi gönderilemedi: %s", e)
        return "failed"


def register(app: Any, deps: dict[str, Any]) -> dict[str, Any]:
    """app.py'de bağlanır. `deps`: auth(request) → (engine, tenant, user, display) · require_caller(request) · can(user, key)
    (yönetici her şey) · granted(user, key) (yalnız rolle verilen; yönetici istisnası yok) · is_admin(user) · audit(engine,
    user, action, kind, id, title, detail) · conf(key, default) · engine() · tenant() · crm_file() · llm(priority) → LLM
    kapısı istemcisi ya da None · people() → [{username, name, email, unit}] (CRM ∩ AD rehberi)."""
    from semantic_layer.runtime.llm_queue import BATCH, NORMAL

    from semantic_bridge import budget_sources as bsrc
    from semantic_bridge import corporate_sales_sources as csrc

    auth, require_caller, can, granted, is_admin, audit, conf = (
        deps[k] for k in ("auth", "require_caller", "can", "granted", "is_admin", "audit", "conf"))
    settings = lambda: M.settings_from(conf)  # noqa: E731
    run_lock = threading.Lock()
    sla_lock = threading.Lock()

    def ctx(request: Request) -> tuple[Any, str, str, str]:
        engine, tenant, user, display = auth(request)
        M.ensure(engine)
        return engine, tenant, user, display

    def rights(user: str) -> dict[str, bool]:
        return {"all": is_admin(user) or can(user, "ozellik:eposta.herkesinki"),
                "hr": bool(granted(user, "ozellik:eposta.ik"))}

    def call(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except M.MailError as e:
            raise HTTPException(status_code=e.status, detail={"code": "FORBIDDEN" if e.status == 403 else "MAILBOX",
                                                              "message": str(e)}) from e
        except S.NotConnected as e:
            raise HTTPException(status_code=409, detail={"code": "MAILBOX_NOT_CONNECTED", "message": str(e)}) from e
        except S.SourceError as e:
            raise HTTPException(status_code=503, detail={"code": "MAILBOX_SOURCE", "retryable": True, "message": str(e)}) from e

    def need(user: str, key: str, what: str, *, strict: bool = False) -> None:
        ok = granted(user, key) if strict else can(user, key)
        if not ok:
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": f"{what} rolünüzde yok."})

    def title_of(row: dict[str, Any]) -> str:
        return "İş başvurusu (konu gizli)" if row.get("isHr") else (row.get("subject") or "(konusuz)")[:200]

    def link(mid: str) -> str:
        base = (conf("ALERT_LINK") or "").split("/uyarilar")[0].rstrip("/")
        return f"{base}/kurumsal-eposta/ileti/{mid}" if base else ""

    def crm_run() -> Callable[[str], list[dict[str, Any]]]:
        return bsrc.runner(deps["crm_file"]())

    def live(src: S.MailSource, provider_id: str) -> S.MailItem:
        return src.fetch(provider_id)

    # ------------------------------------------------------------------ genel

    @app.get(f"{P}/meta")
    def mailbox_meta(request: Request) -> dict[str, Any]:
        engine, tenant, user, display = ctx(request)
        st = settings()
        r = rights(user)
        admin = is_admin(user)
        return {"statuses": M.STATUSES, "views": M.VIEWS, "priorities": K.PRIORITIES, "roles": M.ROLES,
                "events": M.EVENT_LABELS, "transitions": {k: sorted(v) for k, v in M.TRANSITIONS.items()},
                "connection": S.connection_state(conf), "lastRun": M.meta_get(engine, tenant, "last_run"),
                "settings": {"businessHours": st["businessHours"], "startDate": st["startDate"].isoformat() if st["startDate"] else None,
                             "thresholds": st["thresholds"], "autoAssign": sorted(st["autoAssign"])},
                "me": {"username": user, "display": display, "admin": admin, "seeAll": r["all"], "hr": r["hr"],
                       "canAssign": admin or can(user, "ozellik:eposta.ata"), "canRules": admin or can(user, "ozellik:eposta.kural"),
                       "canApprove": admin or can(user, "ozellik:eposta.kural-onay")}}

    @app.get(f"{P}/overview")
    def mailbox_overview(request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        return IZ.izli(engine, lambda: call(M.overview, engine, tenant, user, rights(user), settings()),
                       prefix="portal.eposta.ozet", title="Kurumsal e-posta özeti", text=F_OZET)

    @app.get(f"{P}/badge")
    def mailbox_badge(request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        return IZ.izli(engine, lambda: call(M.badge, engine, tenant, user, settings(), rights(user)["hr"]),
                       prefix="portal.eposta.rozet", title="Menü rozeti", text=F_ROZET)

    @app.get(f"{P}/connection")
    def mailbox_connection(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return {**S.connection_state(conf), "lastRun": M.meta_get(engine, tenant, "last_run"),
                "lastOkAt": M.meta_get(engine, tenant, "last_ok_at"), "startAt": M.meta_get(engine, tenant, "start_at")}

    @app.post(f"{P}/connection/test")
    def mailbox_connection_test(request: Request) -> dict[str, Any]:
        engine, _, user, _ = ctx(request)
        if not (is_admin(user) or can(user, "ozellik:eposta.kural")):
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "Bağlantı denemesi rolünüzde yok."})
        t0 = time.monotonic()
        try:
            ok, msg = S.source(conf).test()
        except S.SourceError as e:
            ok, msg = False, str(e)
        audit(engine, user, "run", "mailbox_connection", None, "Kurumsal e-posta bağlantı denemesi", {"ok": ok})
        return {"ok": ok, "message": msg, "ms": int((time.monotonic() - t0) * 1000)}

    # ------------------------------------------------------------------ iletiler

    @app.get(f"{P}/messages")
    def mailbox_messages(request: Request, view: str = "mine", q: str = "", category: str = "", page: int = 0,
                         pageSize: int = 50) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        return IZ.izli(engine, lambda: call(M.listing, engine, tenant, user, rights(user), settings(), view=view, q=q,
                                            category=category, page=page, page_size=pageSize),
                       prefix="portal.eposta.liste", title="İleti listesi", text=F_LISTE, skip=("page", "pageSize"))

    @app.get(P + "/messages/{mid}")
    async def mailbox_message(mid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        rg = await run_in_threadpool(rights, user)

        def read() -> tuple[dict[str, Any], list]:
            with IZ.izle(engine) as ran:
                return call(M.detail, engine, tenant, user, rg, settings(), mid), ran
        out, ran = await run_in_threadpool(read)
        src = S.source(conf)
        out["link"] = src.web_link(out["providerId"], out["threadId"]) if src.kind == out["provider"] else None
        # Gövde kutudan anlık okunur, portalda saklanmaz.
        out["body"], out["fromAddress"], out["bodyError"] = None, None, None
        try:
            item = await run_in_threadpool(live, src, out["providerId"])
            out["body"], out["fromAddress"] = item.text, item.from_addr
            out["attachments"] = [a.public() for a in item.attachments]
        except S.SourceError as e:
            out["bodyError"] = str(e)
        return PV.bagla(out, lambda: IZ.kaynak(engine, ran, out, prefix="portal.eposta.ileti", title="İleti",
                                               text=F_DETAY, extra=lambda k: [k.hesap("kutu", "Gövde ve ekler.", dis=KUTU_DIS)]))

    @app.post(P + "/messages/{mid}/assign")
    def mailbox_assign(mid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(M.assign, engine, tenant, user, rights(user), settings(), mid, body,
                   lambda who: bool(granted(who, "ozellik:eposta.ik")))
        audit(engine, user, "update", "mail_message", mid, "Kurumsal e-posta ataması",
              {"kime": out["assignee"], "onceki": out["previous"], "birim": out["unit"]})
        return out

    @app.post(P + "/messages/{mid}/category")
    def mailbox_category(mid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(M.set_category, engine, tenant, user, rights(user), settings(), mid, str(body.get("category") or ""))
        audit(engine, user, "update", "mail_message", mid, "Kurumsal e-posta tür düzeltmesi", {"tur": out["category"]})
        return out

    @app.post(P + "/messages/{mid}/status")
    def mailbox_status(mid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(M.set_status, engine, tenant, user, rights(user), settings(), mid, str(body.get("status") or ""),
                   str(body.get("note") or ""))
        audit(engine, user, "update", "mail_message", mid, "Kurumsal e-posta durumu", {"durum": out["status"]})
        return out

    @app.post(P + "/messages/{mid}/draft")
    async def mailbox_draft(mid: str, request: Request) -> dict[str, Any]:
        """Zeki AI yanıt taslağı. Kaydedilmez, gönderilmez: kişi düzenler, kopyalar, kutudan gönderir."""
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        st = settings()
        d = await run_in_threadpool(call, M.detail, engine, tenant, user, await run_in_threadpool(rights, user), st, mid)
        llm = deps["llm"](None)
        if llm is None:
            raise HTTPException(status_code=503, detail={"code": "MAILBOX_MODEL", "message": "Zeki AI bu kurulumda bağlı değil."})
        item = await run_in_threadpool(call, live, S.source(conf), d["providerId"])
        tmpl = d["templates"][0]["body"] if d["templates"] else None
        try:
            text = await run_in_threadpool(K.draft_reply, llm, item, d["categoryLabel"] or "", tmpl, st)
        except Exception as e:  # noqa: BLE001
            log.warning("posta taslağı yazılamadı: %s", e)
            raise HTTPException(status_code=503, detail={"code": "MAILBOX_MODEL", "retryable": True,
                                                         "message": "Zeki AI şu an cevap veremiyor; birazdan yeniden deneyin."}) from e
        with engine.begin() as c:
            M._event(c, tenant, mid, "taslak", user, {"sablon": d["templates"][0]["name"] if d["templates"] else None})
        return {"text": text, "template": d["templates"][0] if d["templates"] else None,
                "link": S.source(conf).web_link(d["providerId"], d["threadId"])}

    @app.post(P + "/messages/{mid}/application")
    def mailbox_application(mid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(M.update_application, engine, tenant, user, rights(user), settings(), mid, body)
        audit(engine, user, "update", "mail_application", mid, out.get("workTitle") or "Dosya başvurusu", {"durum": out["status"]})
        return out

    def _route_exists(method: str, path: str) -> bool:
        for r in getattr(app, "router", app).routes:
            if getattr(r, "path", None) == path and method in (getattr(r, "methods", None) or set()):
                return True
        return False

    async def _internal(request: Request, method: str, path: str, *, json_body: Any = None, content: Optional[bytes] = None,
                        params: Optional[dict[str, str]] = None) -> httpx.Response:
        """Köprünün kendi ucunu kişinin oturumuyla çağırır (sayfa ve işlem yetkisi o uçta yeniden denetlenir)."""
        headers = {"cookie": request.headers.get("cookie", "")}
        token = os.environ.get("SEMANTIC_CALLER_TOKEN", "")
        if token:
            headers["x-semantic-caller"] = token
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://kopru", timeout=120) as c:
            return await c.request(method, path, json=json_body, content=content, params=params, headers=headers)

    def _fail(resp: httpx.Response, what: str) -> HTTPException:
        try:
            detail = resp.json().get("detail")
            msg = detail.get("message") if isinstance(detail, dict) else detail
        except ValueError:
            msg = None
        return HTTPException(status_code=resp.status_code if resp.status_code in (400, 403, 409, 413, 422) else 502,
                             detail={"code": "MAILBOX_HANDOFF", "message": f"{what}: {msg or resp.status_code}"})

    @app.post(P + "/messages/{mid}/to-intake")
    async def mailbox_to_intake(mid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        """Dosya başvurusunu yazar giriş sürecine (M1 başvuru kaydı) aktarır; PDF/DOCX/DOC ekler de gider."""
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        st = settings()
        d = await run_in_threadpool(call, M.detail, engine, tenant, user, await run_in_threadpool(rights, user), st, mid)
        a = d.get("application")
        if not a:
            raise HTTPException(status_code=409, detail={"code": "MAILBOX", "message": "İleti dosya başvurusu olarak işaretli değil."})
        if a["status"] == "aktarildi":
            raise HTTPException(status_code=409, detail={"code": "MAILBOX", "message": f"Zaten aktarıldı ({a.get('intakeNo') or a.get('intakeRef')})."})
        if not _route_exists("POST", M1_APPLICATIONS):
            raise HTTPException(status_code=409, detail={"code": "MAILBOX_HANDOFF_MISSING",
                                                         "message": "Yazar giriş sürecinin başvuru kaydı bu kurulumda yok; "
                                                                    "başvuru «aktarılmayı bekliyor» olarak kaldı."})
        src = S.source(conf)
        item = await run_in_threadpool(call, live, src, d["providerId"])
        payload = {
            "title": str(body.get("title") or a.get("workTitle") or "").strip(),
            "authorName": str(body.get("authorName") or a.get("authorName") or "").strip(),
            "authorEmail": item.from_addr or None,
            "summary": str(body.get("summary") or "").strip(),
            "authorBio": str(body.get("authorBio") or "").strip(),
            "pageEstimate": body.get("pageEstimate") or a.get("pageEstimate"),
            "genre": str(body.get("genre") or a.get("genre") or "").strip() or None,
            "channel": "eposta",
            "receivedOn": (d["receivedAt"] or "")[:10] or None,
            "publisherNote": f"Kurumsal e-postadan aktarıldı (konu: {d.get('subject') or '-'})."[:8000],
        }
        resp = await _internal(request, "POST", M1_APPLICATIONS, json_body=payload)
        if resp.status_code >= 300:
            raise _fail(resp, "Başvuru kaydı açılamadı")
        made = resp.json()
        files, skipped = [], []
        files_path = f"{M1_APPLICATIONS}/{made['id']}/files"
        for att in item.attachments:
            ext = att.name.rsplit(".", 1)[-1].lower() if "." in att.name else ""
            if ext not in M1_FILE_EXT:
                skipped.append(att.name)
                continue
            try:
                data = await run_in_threadpool(src.attachment, d["providerId"], att)
            except S.SourceError as e:
                skipped.append(f"{att.name} ({e})")
                continue
            kind = "ozgecmis" if any(w in K.fold(att.name) for w in ("özgeçmiş", "ozgecmis", "cv")) else "dosya"
            r2 = await _internal(request, "PUT", files_path, content=data, params={"filename": att.name, "kind": kind})
            (files if r2.status_code < 300 else skipped).append(att.name if r2.status_code < 300 else
                                                                 f"{att.name} ({r2.status_code})")
        await run_in_threadpool(M.mark_transferred, engine, tenant, user, mid, "yazar-giris", made.get("id"), made.get("no"))
        audit(engine, user, "create", "mail_application", mid, payload["title"] or "Dosya başvurusu",
              {"hedef": "yazar-giris", "kayit": made.get("no"), "ekler": len(files), "aktarilmayan": skipped})
        return {"ok": True, "intake": {"id": made.get("id"), "no": made.get("no")}, "files": files, "skipped": skipped}

    @app.post(P + "/messages/{mid}/to-hr")
    async def mailbox_to_hr(mid: str, request: Request) -> dict[str, Any]:
        """İş başvurusunu İK aday kaydına (M55) aktarır. Yalnız açıkça `ozellik:eposta.ik` sahibi."""
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        await run_in_threadpool(need, user, "ozellik:eposta.ik", "İş başvurularını işlemek", strict=True)
        d = await run_in_threadpool(call, M.detail, engine, tenant, user, await run_in_threadpool(rights, user), settings(), mid)
        if not d["isHr"]:
            raise HTTPException(status_code=409, detail={"code": "MAILBOX", "message": "İleti iş başvurusu olarak işaretli değil."})
        if not _route_exists("POST", M55_INTAKE):
            raise HTTPException(status_code=409, detail={"code": "MAILBOX_HANDOFF_MISSING",
                                                         "message": "İK aday kaydı (İşe alım modülü) bu kurulumda yok; "
                                                                    "ileti İK kuyruğunda bekliyor."})
        item = await run_in_threadpool(call, live, S.source(conf), d["providerId"])
        payload = {"source": "eposta", "sourceRef": mid, "name": item.from_name or None, "email": item.from_addr or None,
                   "subject": d.get("subject"), "summary": d.get("summary"), "receivedAt": d.get("receivedAt"),
                   "attachments": [a.public() for a in item.attachments],
                   "mailbox": {"provider": d["provider"], "messageId": d["providerId"]}}
        resp = await _internal(request, "POST", M55_INTAKE, json_body=payload)
        if resp.status_code >= 300:
            raise _fail(resp, "İK aday kaydı açılamadı")
        made = resp.json()
        await run_in_threadpool(M.mark_transferred, engine, tenant, user, mid, "ik", made.get("id"), made.get("no"))
        audit(engine, user, "create", "mail_hr", mid, "İş başvurusu (konu gizli)", {"hedef": "ik", "kayit": made.get("id")})
        return {"ok": True, "candidate": made}

    @app.get(f"{P}/applications")
    def mailbox_applications(request: Request, status: str = "yeni") -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return IZ.izli(engine, lambda: call(M.applications, engine, tenant, status), prefix="portal.eposta.basvuru",
                       title="Başvurular kutusu", text=F_BASVURU)

    # ------------------------------------------------------------------ rapor

    @app.get(f"{P}/report")
    def mailbox_report(request: Request, start: str = "", end: str = "") -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        today = datetime.now(M.TZ).date()
        try:
            e = date.fromisoformat(end) if end else today
            s = date.fromisoformat(start) if start else e - timedelta(days=29)
        except ValueError:
            raise HTTPException(status_code=400, detail={"code": "MAILBOX", "message": "Tarih YYYY-AA-GG olmalı."}) from None
        return IZ.izli(engine, lambda: call(M.report, engine, tenant, settings(), s, e), prefix="portal.eposta.rapor",
                       title="Kurumsal e-posta raporu", text=F_RAPOR)

    # ------------------------------------------------------------------ kurallar

    @app.get(f"{P}/rules")
    def mailbox_rules(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return call(M.rules_view, engine, tenant, settings())

    @app.put(f"{P}/rules")
    def mailbox_rules_save(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(M.save_draft, engine, tenant, user, body, settings())
        audit(engine, user, "update", "mail_rules", str(out["version"]), f"Kurumsal e-posta kuralları sürüm {out['version']} (taslak)",
              {"tur": len(out["categories"]), "yonlendirme": len(out["routes"]), "sablon": len(out["templates"])})
        return out

    @app.delete(f"{P}/rules/draft")
    def mailbox_rules_discard(request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        v = call(M.discard_draft, engine, tenant)
        audit(engine, user, "delete", "mail_rules", str(v), f"Kurumsal e-posta kuralları sürüm {v} (taslak)", None)
        return {"ok": True, "version": v}

    @app.post(f"{P}/rules/approve")
    def mailbox_rules_approve(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        if not (is_admin(user) or can(user, "ozellik:eposta.kural-onay")):
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "Kuralları yürürlüğe almak rolünüzde yok."})
        try:
            version = int(body.get("version"))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail={"code": "MAILBOX", "message": "Sürüm numarası gerekli."}) from None
        out = call(M.approve_draft, engine, tenant, user, version)
        audit(engine, user, "approve", "mail_rules", str(version), f"Kurumsal e-posta kuralları sürüm {version} yürürlükte", None)
        return out

    # ------------------------------------------------------------------ etiketleme

    @app.get(f"{P}/labeling")
    def mailbox_labeling(request: Request, page: int = 0) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        return IZ.izli(engine, lambda: call(M.labeling, engine, tenant, user, rights(user), settings(), page=page),
                       prefix="portal.eposta.etiket", title="Etiketleme", text=F_ETIKET, skip=("page", "pageSize"))

    @app.post(P + "/labeling/{mid}")
    def mailbox_label(mid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        return call(M.add_label, engine, tenant, user, rights(user), settings(), mid, str(body.get("category") or ""))

    # ------------------------------------------------------------------ zamanlayıcılar

    def run_due(model: bool = True) -> dict[str, Any]:
        engine, tenant = deps["engine"](), deps["tenant"]()
        M.ensure(engine)
        st = settings()
        t0 = time.monotonic()
        deadline = t0 + max(60, st["llmBudgetSec"])
        out: dict[str, Any] = {"at": M._now().isoformat(), "read": 0, "new": 0, "classified": 0, "historicalClassified": 0,
                               "unclassifiable": 0, "replies": 0, "warnings": []}
        state = S.connection_state(conf)
        if not state["connected"]:
            out.update(ok=False, notConnected=True, error=state["reason"])
            M.meta_set(engine, tenant, "last_run", out)
            return out
        src = S.source(conf)
        rules = M.active_rules(engine, tenant, st)
        start = M.start_at(engine, tenant, st)
        mem: dict[str, S.MailItem] = {}
        try:
            ids = src.list_since(M.read_window(engine, tenant, st, start))
            out["read"] = len(ids)
            known = M.known_ids(engine, tenant, src.kind, ids)
            fresh = [i for i in reversed(ids) if i not in known]          # sağlayıcı yeniden eskiye verir; eskiden yeniye
            items: list[S.MailItem] = []
            for pid in fresh:
                if time.monotonic() > deadline:
                    out["warnings"].append(f"{len(fresh) - len(items)} ileti süre bittiği için sonraki tura kaldı.")
                    break
                items.append(src.fetch(pid))
            items.sort(key=lambda x: x.received_at)
            crm: dict[str, dict[str, Any]] = {}
            if items:
                try:
                    crm = S.recognize(crm_run(), csrc.prefix(conf("CRM_SCHEMA", "Timas_MSCRM.dbo")), [i.from_addr for i in items])
                except Exception as e:  # noqa: BLE001 — CRM yoksa ileti yine kaydedilir, rozet boş kalır
                    out["warnings"].append(f"CRM okunamadı, gönderen tanınmadı: {str(e)[:200]}")
            for it in items:
                mid = M.ingest(engine, tenant, src.kind, it, crm.get(it.from_addr) or {}, rules, st, start)
                if mid:
                    mem[mid] = it
                    out["new"] += 1
        except S.SourceError as e:
            out.update(ok=False, error=str(e))
            M.meta_set(engine, tenant, "last_run", out)
            return out
        # Sınıflama: önce canlı (NORMAL), sonra geçmiş (BATCH, yalnız tür). Süre dolunca kalan sonraki tura.
        enabled = [c for c in rules["categories"] if c["enabled"]]
        for historical in (False, True):
            llm = deps["llm"](BATCH if historical else NORMAL) if model else None
            for row in M.pending(engine, tenant, historical):
                if time.monotonic() > deadline:
                    break
                if llm is None:
                    if not historical:
                        M.mark_unclassifiable(engine, tenant, row.id, "Zeki AI bağlı değil")
                        out["unclassifiable"] += 1
                    continue
                try:
                    item = mem.get(row.id) or src.fetch(row.provider_id)
                except S.SourceError as e:
                    out["warnings"].append(f"İleti yeniden okunamadı: {e}")
                    continue
                crm_row = M._j(row.crm_json, {}) or {}
                try:
                    res = K.classify(llm, item, enabled, crm_row, st, with_priority=not historical)
                    summary = application = None
                    if not historical:
                        summary = K.summarize(llm, item, st)
                        cat = M._cat(rules, res["category"])
                        if cat and cat["role"] == "basvuru":
                            application = K.extract_application(llm, item, st)
                except Exception as e:  # noqa: BLE001 — model yok/cevapsız: bu tur biter, iletiler sonra denenir
                    out["llmError"] = f"{type(e).__name__}: {str(e)[:200]}"
                    break
                M.apply_classification(engine, tenant, row.id, res, rules, st, summary, application,
                                       [a.public() for a in item.attachments])
                out["historicalClassified" if historical else "classified"] += 1
            if "llmError" in out:
                break
        # Yanıt tespiti: konu zincirinde kutudan gönderilen ilk ileti.
        for row in M.reply_candidates(engine, tenant, st):
            if time.monotonic() > deadline + 60:
                break
            try:
                at = src.first_reply(row.thread_id or row.provider_id, M._aware(row.received_at))
            except S.SourceError as e:
                out["warnings"].append(f"Zincir okunamadı: {e}")
                continue
            out["replies"] += int(M.record_reply(engine, tenant, row.id, at))
        out.update(ok=True, seconds=round(time.monotonic() - t0, 1),
                   remaining=len(M.pending(engine, tenant, False)), remainingHistorical=len(M.pending(engine, tenant, True)))
        M.meta_set(engine, tenant, "last_run", out)
        M.meta_set(engine, tenant, "last_ok_at", out["at"])
        return out

    @app.post(f"{P}/run-due")
    def mailbox_run_due(request: Request, model: int = 1) -> dict[str, Any]:
        """Zamanlayıcı (5 dk): kutuyu okur, CRM'de tanır, sınıflar, yanıtları zincirden işler. Aynı anda tek koşu."""
        require_caller(request)
        if not run_lock.acquire(blocking=False):
            return {"skipped": "önceki okuma sürüyor"}
        try:
            return run_due(bool(model))
        finally:
            run_lock.release()

    def emails_for(users: list[str]) -> tuple[list[str], list[str]]:
        try:
            people = {p["username"]: p for p in deps["people"]()}
        except Exception as e:  # noqa: BLE001
            log.warning("posta: kişi rehberi okunamadı: %s", e)
            people = {}
        found, missing = [], []
        for u in users:
            mail = (people.get(u) or {}).get("email") or ""
            (found if "@" in mail else missing).append(mail if "@" in mail else u)
        return list(dict.fromkeys(found)), missing

    @app.post(f"{P}/sla-due")
    def mailbox_sla_due(request: Request) -> dict[str, Any]:
        """Zamanlayıcı (saatlik): iş saatleriyle SLA; hatırlatma → atanan, eskalasyon → birim yöneticisi, üst → yönetim.
        İç e-posta; dışarıya gönderim yok. Kutu okuması uzun süredir yoksa bağlantı uyarısı."""
        require_caller(request)
        if not sla_lock.acquire(blocking=False):
            return {"skipped": "önceki SLA turu sürüyor"}
        try:
            engine, tenant = deps["engine"](), deps["tenant"]()
            M.ensure(engine)
            st = settings()
            out: dict[str, Any] = {"notified": 0, "noRecipient": 0, "levels": {}}
            names = {"hatirlatma": "Hatırlatma", "eskalasyon": "Eskalasyon", "ust": "Üst yönetici bildirimi"}
            for it in M.sla_due(engine, tenant, st):
                emails, missing = emails_for(it["users"])
                subject = f"Kurumsal e-posta · {names[it['level']]}: {it['elapsedH']:g} iş saatidir yanıt bekliyor"
                konu = "İş başvurusu (konu gizli)" if it["isHr"] else (it["subject"] or "(konusuz)")
                text = (f"{names[it['level']]}: timas@ kutusundaki bir ileti {it['elapsedH']:g} iş saatidir yanıtsız.\n\n"
                        f"Tür: {it['category']}\nKonu: {konu}\nAtanan: {it['assignee'] or 'atanmamış'}\n"
                        + (f"\nİleti: {link(it['id'])}\n" if link(it["id"]) else "")
                        + "\nBu bildirim portal içidir; gönderene bir şey gitmedi.")
                status = send_mail(subject, text, emails) if st["notifyEmail"] else "kapali"
                M.mark_sla(engine, tenant, it["id"], it["level"], {"alicilar": it["users"], "eposta": status,
                                                                   "adresiYok": missing, "isSaati": it["elapsedH"]})
                out["notified"] += 1
                out["noRecipient"] += int(not it["users"])
                out["levels"][it["level"]] = out["levels"].get(it["level"], 0) + 1
            # Bağlantı: bağlıyken son başarılı okuma eşikten eskiyse bir kez uyarılır; okuma düzelince sıfırlanır.
            state = S.connection_state(conf)
            last_ok = M.meta_get(engine, tenant, "last_ok_at")
            if state["connected"] and last_ok:
                age = (M._now() - M._aware(datetime.fromisoformat(last_ok))).total_seconds() / 60
                sent = M.meta_get(engine, tenant, "conn_alert_at")
                if age >= st["connectionAlertMin"] and not sent:
                    run = M.meta_get(engine, tenant, "last_run") or {}
                    status = send_mail("Kurumsal e-posta · kutu okunamıyor",
                                       f"timas@ kutusu {int(age)} dakikadır okunamadı.\nSon hata: {run.get('error') or '-'}\n"
                                       "Yönetim → Kurumsal e-posta ekranından bağlantıyı deneyin.", st["connectionAlertTo"])
                    M.meta_set(engine, tenant, "conn_alert_at", {"at": M._now().isoformat(), "eposta": status})
                    out["connectionAlert"] = status
                elif age < st["connectionAlertMin"] and sent:
                    M.meta_set(engine, tenant, "conn_alert_at", None)
            return out
        finally:
            sla_lock.release()

    return {"run_due": run_due}
