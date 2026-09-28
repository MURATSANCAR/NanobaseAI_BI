"""M55 İşe alım uçları: /api/v1/hr/recruit/*.

Sayfa kapısı `access.RULES` (`sayfa:ik-ise-alim`, `sayfa:ik-pozisyonlar`, `sayfa:ik-belgeler`; hepsi açıkça verilir).
İşlem anahtarları (`ozellik:ik.*`) ucun içinde ve `hr_recruit`'teki kurallarda denetlenir. `POST /intake` ve
`POST /reminders/run-due` yalnız sistem jetonuyla (kurumsal e-posta modülü ve zamanlayıcı).

Model çağrıları `HrContext.llm` (LLM kapısı, sıra kaydına yalnız etiket). Ekranda model adı yazmaz; kullanıcı «Zeki AI»
görür. Hiçbir uç adaya ya da dışarıya e-posta göndermez; hatırlatma e-postası yalnız iç İK alıcılarına ve aday bilgisi
içermez.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from semantic_bridge import hr_core as H
from semantic_bridge import hr_recruit as R
from semantic_bridge import hr_recruit_text as X
from semantic_bridge.hr_api import HrContext

log = logging.getLogger("semantic_bridge.hr.recruit.api")
P = "/api/v1/hr/recruit"


def register(app, hr: HrContext) -> None:
    ctx, need, call = hr.ctx, hr.need, hr.call
    R.register_hooks()

    def engine_ready(request: Request) -> tuple[Any, str, H.Who]:
        engine, tenant, who = ctx(request)
        R.ensure(engine)
        return engine, tenant, who

    def chatter(label: str, max_tokens: int, priority: Any = None):
        m = hr.llm(label, priority)
        if m is None:
            raise HTTPException(503, detail={"code": "HR_MODEL", "message": "Zeki AI bu kurulumda tanımlı değil."})
        return lambda messages: m.chat(messages, max_tokens=max_tokens, temperature=0.0)

    # ------------------------------------------------------------------ genel

    @app.get(P + "/meta")
    def recruit_meta(request: Request) -> dict[str, Any]:
        _, _, who = engine_ready(request)
        st = hr.settings()
        return {"stages": R.STAGES, "outcomes": R.OUTCOMES, "sources": R.SOURCES, "positionStates": R.POSITION_STATES,
                "templateKinds": X.TEMPLATE_KINDS, "templateStates": R.TEMPLATE_STATES, "fields": X.FIELDS,
                "messageStates": R.MESSAGE_STATES, "sendChannels": R.SEND_CHANNELS, "slaDays": st["slaDays"],
                "fileMaxMb": st["fileMaxMb"], "modelVar": hr.llm("durum") is not None,
                "me": {"username": who.user, "display": who.display,
                       "can": {"all": who.can(R.F_ALL), "see": who.can(R.F_SEE), "decide": who.can(R.F_DECIDE),
                               "positionOpen": who.can(R.F_POS_OPEN), "positionApprove": who.can(R.F_POS_APPROVE),
                               "letters": who.can(R.F_LETTERS), "offerApprove": who.can(R.F_OFFER_APPROVE),
                               "templates": who.can(R.F_TEMPLATES), "export": who.can(R.F_EXPORT), "kvkk": who.can(R.F_KVKK)}}}

    @app.get(P + "/pipeline")
    def recruit_pipeline(request: Request, position: str = "") -> dict[str, Any]:
        engine, tenant, who = engine_ready(request)
        out = R.pipeline(engine, tenant, who, position, hr.settings()["slaDays"])
        out["positions"] = [{"id": p["id"], "title": p["title"], "state": p["state"], "counts": p["counts"]}
                            for p in R.list_positions(engine, tenant, who)]
        return out

    # ------------------------------------------------------------------ pozisyonlar

    @app.get(P + "/positions")
    def recruit_positions(request: Request, state: str = "") -> dict[str, Any]:
        engine, tenant, who = engine_ready(request)
        return {"items": R.list_positions(engine, tenant, who, state)}

    @app.post(P + "/positions", status_code=201)
    def recruit_position_create(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, who = engine_ready(request)
        need(who, R.F_POS_OPEN, what="Pozisyon açma")
        out, _ = call(R.save_position, engine, tenant, who.user, body)
        hr.audit(engine, who.user, "create", "hr_position", out["id"], out["title"])
        return out

    @app.get(P + "/positions/{pid}")
    def recruit_position(pid: str, request: Request) -> dict[str, Any]:
        engine, tenant, who = engine_ready(request)
        return call(R.get_position, engine, tenant, who, pid)

    @app.patch(P + "/positions/{pid}")
    def recruit_position_update(pid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, who = engine_ready(request)
        need(who, R.F_POS_OPEN, what="Pozisyon düzenleme")
        out, diff = call(R.save_position, engine, tenant, who.user, body, pid)
        if diff:
            hr.audit(engine, who.user, "update", "hr_position", pid, out["title"], diff)
        return out

    for action in ("submit", "withdraw", "approve", "reject", "hold", "resume", "close"):
        def make(act: str):
            def transition(pid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
                engine, tenant, who = engine_ready(request)
                out = call(R.position_transition, engine, tenant, who, pid, act, str(body.get("note") or ""))
                hr.audit(engine, who.user, "update", "hr_position", pid, out["title"], {"islem": act, "durum": out["state"]})
                return out
            transition.__name__ = f"recruit_position_{act}"
            return transition
        app.post(P + "/positions/{pid}/" + action)(make(action))

    @app.post(P + "/positions/{pid}/posting-draft")
    async def recruit_posting_draft(pid: str, request: Request) -> dict[str, Any]:
        """Zeki AI ilan taslağı + ayrımcılık denetimi. Kaydetmez; metni İK düzeltip kaydeder."""
        engine, tenant, who = await run_in_threadpool(engine_ready, request)
        need(who, R.F_POS_OPEN, what="İlan taslağı")
        pos = await run_in_threadpool(call, R.get_position, engine, tenant, who, pid)
        if not pos["competencies"]:
            raise HTTPException(400, detail={"code": "HR", "message": "Önce yetkinlikleri yazın."})
        chat = chatter("ilan taslağı", 1500)
        text = (await run_in_threadpool(chat, X.posting_messages(pos, hr.settings()["company"])) or "").strip()
        if not text:
            raise HTTPException(502, detail={"code": "HR_MODEL", "message": "Zeki AI ilan taslağı yazamadı; yeniden deneyin."})
        warnings = await run_in_threadpool(_check_posting, text)
        hr.audit(engine, who.user, "run", "hr_position", pid, pos["title"], {"is": "ilan taslağı", "uyari": len(warnings)})
        return {"text": text, "warnings": warnings}

    def _check_posting(text: str) -> list[dict[str, Any]]:
        warnings: list[dict[str, Any]] = list(X.discrimination_rules(text))
        m = hr.llm("ilan ayrımcılık denetimi")
        if m is not None and hasattr(m, "choose"):
            try:
                got = X.discrimination_model(text, lambda p, ch: m.choose(p, ch), 0.8)
                if got:
                    warnings.append(got)
            except Exception as e:  # noqa: BLE001 — denetim yapılamadıysa ekranda söylenir
                log.warning("hr: ilan denetimi model hatası: %s", e)
                warnings.append({"label": "Zeki AI ilanı denetleyemedi; metni elle gözden geçirin", "source": "zeki"})
        return warnings

    @app.post(P + "/positions/{pid}/posting-check")
    async def recruit_posting_check(pid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, who = await run_in_threadpool(engine_ready, request)
        need(who, R.F_POS_OPEN, what="İlan denetimi")
        pos = await run_in_threadpool(call, R.get_position, engine, tenant, who, pid)
        text = str(body.get("text") if body.get("text") is not None else pos["postingText"])
        if not text.strip():
            raise HTTPException(400, detail={"code": "HR", "message": "Denetlenecek ilan metni yok."})
        return {"warnings": await run_in_threadpool(_check_posting, text)}

    @app.post(P + "/positions/{pid}/interview-kit")
    async def recruit_interview_kit(pid: str, request: Request) -> dict[str, Any]:
        engine, tenant, who = await run_in_threadpool(engine_ready, request)
        need(who, R.F_POS_OPEN, R.F_DECIDE, what="Mülakat soru seti")
        pos = await run_in_threadpool(call, R.get_position, engine, tenant, who, pid)
        chat = chatter("mülakat soru seti", 2500)
        kit = await run_in_threadpool(call, X.interview_kit, pos, chat)
        await run_in_threadpool(R.set_interview_kit, engine, tenant, pid, kit)
        hr.audit(engine, who.user, "run", "hr_position", pid, pos["title"], {"is": "mülakat soru seti", "yetkinlik": len(kit)})
        return {"items": kit}

    # ------------------------------------------------------------------ adaylar

    @app.post(P + "/candidates", status_code=201)
    def recruit_candidate_create(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, who = engine_ready(request)
        need(who, R.F_ALL, what="Aday ekleme")
        cid = call(R.create_candidate, engine, tenant, who.user, body)
        ack = R.queue_ack(engine, tenant, cid, hr.settings()["company"])
        hr.audit(engine, who.user, "create", "hr_candidate", cid, "Aday kaydı", {"kaynak": body.get("source") or "elle"})
        return {"id": cid, "ackDraft": ack}

    @app.get(P + "/candidates/{cid}")
    def recruit_candidate(cid: str, request: Request) -> dict[str, Any]:
        engine, tenant, who = engine_ready(request)
        out = call(R.detail, engine, tenant, who, cid, hr.settings()["slaDays"])
        H.log_access(engine, tenant, who.user, "aday", cid, "goruntule", "aday kartı")
        if out["can"]["consents"]:
            out["consents"] = H.list_consents(engine, tenant, "aday", cid)
        return out

    @app.patch(P + "/candidates/{cid}")
    def recruit_candidate_update(cid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, who = engine_ready(request)
        out = call(R.update_candidate, engine, tenant, who, cid, body)
        if out["changed"]:
            hr.audit(engine, who.user, "update", "hr_candidate", cid, "Aday kaydı", {"alanlar": out["changed"]})
        return out

    @app.post(P + "/candidates/{cid}/stage")
    def recruit_candidate_stage(cid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, who = engine_ready(request)
        out = call(R.change_stage, engine, tenant, who, cid, body)
        hr.audit(engine, who.user, "update", "hr_candidate", cid, "Aday aşaması",
                 {"once": out["from"], "sonra": out["to"], "sonuc": out["outcome"]})
        if out["employeeId"]:
            hr.audit(engine, who.user, "create", "hr_employee", out["employeeId"], "İşe alınan aday çalışan kaydına geçti",
                     {"aday": cid})
        return out

    @app.post(P + "/candidates/{cid}/files", status_code=201)
    async def recruit_file_add(cid: str, request: Request, filename: str = "") -> dict[str, Any]:
        engine, tenant, who = await run_in_threadpool(engine_ready, request)
        max_mb = hr.settings()["fileMaxMb"]
        if int(request.headers.get("content-length") or 0) > max_mb * 1024 * 1024:
            raise HTTPException(413, detail={"code": "HR", "message": f"Dosya {max_mb} MB sınırını aşıyor."})
        data = await request.body()
        out = await run_in_threadpool(call, R.add_file, engine, tenant, who, cid, filename, data, max_mb)
        hr.audit(engine, who.user, "upload", "hr_candidate", cid, "Özgeçmiş yüklendi", {"boyut": out["size"], "maske": out["maskCounts"]})
        return out

    @app.get(P + "/candidates/{cid}/files/{fid}")
    def recruit_file(cid: str, fid: str, request: Request) -> Response:
        engine, tenant, who = engine_ready(request)
        data, name, mime = call(R.file_blob, engine, tenant, who, cid, fid)
        H.log_access(engine, tenant, who.user, "aday", cid, "indir", "özgün özgeçmiş")
        return Response(content=data, media_type=mime, headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{_quote(name)}", "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store"})

    @app.delete(P + "/candidates/{cid}/files/{fid}")
    def recruit_file_delete(cid: str, fid: str, request: Request) -> dict[str, Any]:
        engine, tenant, who = engine_ready(request)
        call(R.delete_file, engine, tenant, who, cid, fid)
        hr.audit(engine, who.user, "delete", "hr_candidate", cid, "Özgeçmiş dosyası silindi", {"dosya": fid})
        return {"ok": True}

    @app.post(P + "/candidates/{cid}/evidence", status_code=202)
    def recruit_evidence(cid: str, request: Request) -> dict[str, Any]:
        """Zeki AI kanıtlı özet (arka plan işi): önce özel nitelikli satır maskesi, sonra yetkinlik → satır."""
        engine, tenant, who = engine_ready(request)
        inp = call(R.evidence_input, engine, tenant, who, cid)
        chat = chatter("özgeçmiş kanıt özeti", 1200)

        def work(progress):
            return R.run_evidence(engine, tenant, cid, inp, chat, progress)

        out = call(H.start_job, engine, tenant, who.user, "kanit", cid, work)
        hr.audit(engine, who.user, "run", "hr_candidate", cid, "Kanıtlı özet", {"yetkinlik": len(inp["competencies"])})
        return out

    @app.get(P + "/candidates/{cid}/export")
    def recruit_export(cid: str, request: Request) -> Response:
        """KVKK md. 11 ilgili kişi talebi: adayın bütün kaydı (JSON)."""
        import json

        engine, tenant, who = engine_ready(request)
        data = call(R.export_candidate, engine, tenant, who, cid)
        H.log_access(engine, tenant, who.user, "aday", cid, "disa_aktar", "ilgili kişi talebi")
        hr.audit(engine, who.user, "run", "hr_candidate", cid, "Aday verisi dışa aktarıldı (ilgili kişi talebi)")
        return Response(content=json.dumps(data, ensure_ascii=False, indent=2, default=str).encode("utf-8"),
                        media_type="application/json",
                        headers={"Content-Disposition": f'attachment; filename="aday-{cid[-8:]}.json"', "Cache-Control": "private, no-store"})

    @app.delete(P + "/candidates/{cid}")
    def recruit_candidate_delete(cid: str, request: Request, reason: str = "") -> dict[str, Any]:
        """Talep üzerine imha (tutanaklı). Aday satırı istatistik için kimliğiyle kalır, kişisel veri silinir."""
        engine, tenant, who = engine_ready(request)
        n = call(R.delete_on_request, engine, tenant, who, cid, reason)
        H.log_access(engine, tenant, who.user, "aday", cid, "sil", "ilgili kişi talebi")
        hr.audit(engine, who.user, "delete", "hr_candidate", cid, "Aday verisi talep üzerine imha edildi", {"silinen": n})
        return {"ok": True, "purged": n}

    # ------------------------------------------------------------------ mülakat

    @app.post(P + "/interviews", status_code=201)
    def recruit_interview_create(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, who = engine_ready(request)
        out = call(R.create_interview, engine, tenant, who, body)
        hr.audit(engine, who.user, "create", "hr_interview", out["id"], "Mülakat planlandı",
                 {"aday": out["candidateId"], "gorusmeci": out["interviewers"]})
        return out

    @app.post(P + "/interviews/{iid}/notes")
    def recruit_interview_note(iid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, who = engine_ready(request)
        return call(R.save_note, engine, tenant, who, iid, body)

    # ------------------------------------------------------------------ şablonlar ve yazışma

    @app.get(P + "/templates")
    def recruit_templates(request: Request, kind: str = "") -> dict[str, Any]:
        engine, tenant, _ = engine_ready(request)
        return {"items": R.list_templates(engine, tenant, kind), "kinds": X.TEMPLATE_KINDS, "fields": X.FIELDS}

    @app.get(P + "/templates/starters")
    def recruit_template_starters(request: Request) -> dict[str, Any]:
        engine_ready(request)
        return {"items": X.STARTERS}

    @app.post(P + "/templates", status_code=201)
    def recruit_template_create(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, who = engine_ready(request)
        need(who, R.F_TEMPLATES, what="Şablon düzenleme")
        out, diff = call(R.save_template, engine, tenant, who.user, body)
        hr.audit(engine, who.user, "create", "hr_template", out["id"], out["name"], diff)
        return out

    @app.patch(P + "/templates/{tid}")
    def recruit_template_update(tid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, who = engine_ready(request)
        need(who, R.F_TEMPLATES, what="Şablon düzenleme")
        out, diff = call(R.save_template, engine, tenant, who.user, body, tid)
        if diff:
            hr.audit(engine, who.user, "update", "hr_template", tid, out["name"], diff)
        return out

    @app.post(P + "/candidates/{cid}/letters/{kind}", status_code=201)
    async def recruit_letter(cid: str, kind: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        """Şablondan mektup taslağı. İsteğe bağlı «tonu yumuşat» Zeki AI'dan geçer; bilgi kaybolursa şablon metni kalır."""
        engine, tenant, who = await run_in_threadpool(engine_ready, request)
        soften = None
        if body.get("soften"):
            chat = chatter("mektup tonu", 1500)
            soften = lambda text, keep: X.soften(text, keep, chat)  # noqa: E731
        out = await run_in_threadpool(call, R.draft_letter, engine, tenant, who, cid, kind, body, hr.settings()["company"], soften)
        hr.audit(engine, who.user, "create", "hr_message", out["id"], f"{out['kindLabel']} taslağı", {"aday": cid})
        return out

    for action in ("edit", "submit", "approve", "reject", "sent", "cancel"):
        def make_msg(act: str):
            def msg_action(mid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
                engine, tenant, who = engine_ready(request)
                out = call(R.message_action, engine, tenant, who, mid, act, body)
                hr.audit(engine, who.user, "update", "hr_message", mid, out["kindLabel"], {"islem": act, "durum": out["status"]})
                return out
            msg_action.__name__ = f"recruit_message_{act}"
            return msg_action
        app.post(P + "/messages/{mid}/" + action)(make_msg(action))

    @app.get(P + "/messages/{mid}/document.docx")
    def recruit_message_doc(mid: str, request: Request) -> Response:
        engine, tenant, who = engine_ready(request)
        data, name = call(R.message_document, engine, tenant, who, mid)
        return Response(content=data, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "private, no-store"})

    # ------------------------------------------------------------------ sistem uçları

    @app.post(P + "/intake", status_code=201)
    def recruit_intake(body: dict[str, Any], request: Request) -> dict[str, Any]:
        """Kurumsal e-posta modülü (H4) «iş başvurusu» iletisini buraya yollar (sistem jetonuyla). Adaya hiçbir şey
        gönderilmez; «başvurunuz alındı» taslağı İK'nın önüne düşer."""
        hr.require_caller(request)
        engine, tenant = hr.system()
        R.ensure(engine)
        st = hr.settings()
        out = call(R.intake, engine, tenant, body, st["company"], st["fileMaxMb"])
        if out["created"]:
            hr.audit(engine, "eposta", "create", "hr_candidate", out["id"], "E-postadan başvuru aktarıldı",
                     {"dosya": out["files"], "alinmayan": len(out["skipped"]), "pozisyon": out.get("positionId")})
        return out

    @app.post(P + "/reminders/run-due")
    def recruit_reminders(request: Request) -> dict[str, Any]:
        """Zamanlayıcı (15 dk): aşamasında eşik günden uzun bekleyen adaylar için İK alıcılarına tek özet e-posta.
        Eşik (`HR_RECRUIT_SLA_DAYS`) ya da alıcı (`HR_ALERT_RECIPIENTS`) yoksa hiçbir şey gönderilmez."""
        from semantic_bridge.budget_api import _send_mail

        hr.require_caller(request)
        engine, tenant = hr.system()
        R.ensure(engine)
        st = hr.settings()
        items = R.due_reminders(engine, tenant, st["slaDays"])
        mail = "esik_yok" if not st["slaDays"] else "bos"
        if items:
            if st["alertRecipients"]:
                link = (hr.conf("ALERT_LINK") or "").split("/uyarilar")[0]
                mail = _send_mail(f"İşe alım: {len(items)} aday bekliyor", R.reminder_text(items, st["slaDays"], f"{link}/ik/ise-alim" if link else ""),
                                  st["alertRecipients"])
                if mail == "sent":
                    R.mark_reminded(engine, tenant, items)
            else:
                mail = "alici_yok"
        return {"slaDays": st["slaDays"], "due": len(items), "mail": mail, "recipients": len(st["alertRecipients"])}


def _quote(name: str) -> str:
    from urllib.parse import quote

    return quote(name, safe="")
