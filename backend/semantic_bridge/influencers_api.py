"""M23 İşbirlikleri uçları: /api/v1/influencers/*.

Sayfa kapısı `access.RULES` (`sayfa:isbirlikleri`). Kayıt defteri, işbirliği, ölçüm, taslak ve «gönderildi» kaydı
`ozellik:isbirligi.duzenle` (`FEATURE_RULES`). Açıkça verilen yetkiler ucun içinde denetlenir:
`ozellik:isbirligi.onay` (teklif/seçim onayı, taslak onayı, ücret değişikliği, ödeme satırı onayı) ve
`ozellik:isbirligi.odeme` (ödeme listesi, ödendi kaydı). Ücret alanları yalnız bu iki yetkiden birine döner.
Excel dışa aktarma `ozellik:veri.disa-aktar`.

Zamanlayıcı (`timas-influencers.timer`, her gün 08:00) yalnız `POST /api/v1/influencers/run-due`'yu çağırır:
hatırlatmalar iç ekibe tek özet e-postayla (içerik üreticisine hiçbir gönderim yok). `INFLUENCER_API_ENABLED=1`
olsa bile resmî API ile hesap sayısı alma ikinci sürümdedir; bu sürümde yalnız durum döner.

Model çağrıları LLM kapısından: `rt.llm_for("isbirligi", NORMAL)` — `choose` ile konu etiketi, `chat` ile aday
gerekçesi ve taslak paragrafı. `LlmClient` doğrudan kurulmaz; rakamı model üretmez.
"""
from __future__ import annotations

import logging
import os
from datetime import date
from typing import Any, Callable, Optional

from fastapi import HTTPException, Request
from fastapi.responses import Response

from semantic_bridge import freelance as fl
from semantic_bridge import influencers as I
from semantic_bridge import influencers_sources as src

log = logging.getLogger("semantic.influencers.api")
P = "/api/v1/influencers"
FEATURE_EDIT = "ozellik:isbirligi.duzenle"
FEATURE_APPROVE = "ozellik:isbirligi.onay"
FEATURE_PAY = "ozellik:isbirligi.odeme"
FEATURE_EXPORT = "ozellik:veri.disa-aktar"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _recipients(key: str) -> list[str]:
    from semantic_bridge.admin import conf

    return [x.strip() for x in (conf(key) or "").replace(";", ",").split(",") if "@" in x]


def register(app, rt: Callable[[], Any], require_caller: Callable[[Request], None], can: Callable[[str, str], bool]):
    from semantic_bridge import admin as admin_mod
    from semantic_bridge import board as board_mod

    def crm() -> src.Crm:
        path = os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json")
        return src.Crm(lambda: src.runner(path), lambda: admin_mod.conf("CRM_SCHEMA") or "Timas_MSCRM.dbo")

    def llm():
        try:
            from semantic_layer.runtime.llm_queue import NORMAL
            return rt().llm_for("isbirligi", NORMAL)
        except Exception:  # noqa: BLE001 — model tanımlı değil
            return None

    def chatter(max_tokens: int) -> Optional[Callable[[list[dict[str, str]]], str]]:
        m = llm()
        if m is None:
            return None
        return lambda messages: m.chat(messages, max_tokens=max_tokens, temperature=0.3)

    def ctx(request: Request) -> tuple[Any, str, str, str]:
        require_caller(request)
        try:
            user, display = board_mod.session_of(request.headers.get("cookie", ""))
        except board_mod.NoUser:
            raise HTTPException(status_code=401, detail={"code": "UNAUTHORIZED", "message": "Oturum gerekli."}) from None
        r = rt()
        I.ensure(r.store.engine)
        admin_mod.ensure(r.store.engine)
        return r.store.engine, r.settings.tenant_id, user, display

    def call(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except fl.FreelanceError as e:  # InfluencerError ve paylaşılan M8 yardımcılarının hatası
            raise HTTPException(status_code=e.status, detail={"code": "INFLUENCER", "message": str(e)}) from e
        except src.SourceError as e:
            raise HTTPException(status_code=503, detail={"code": "INFLUENCER_SOURCE", "message": str(e)}) from e

    def fee_ok(user: str) -> bool:
        return can(user, FEATURE_APPROVE) or can(user, FEATURE_PAY)

    def need(ok: bool, what: str) -> None:
        if not ok:
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": f"{what} rolünüzde yok."})

    def audit(engine, user, action, kind, oid, title, detail=None) -> None:
        admin_mod.audit(engine, user, action, kind, oid, title, detail)

    def book_info(kitap: str) -> tuple[dict[str, Any], dict[str, Any]]:
        book = call(crm().book, kitap)
        if book is None:
            raise HTTPException(404, detail={"code": "INFLUENCER", "message": "Kitap CRM'de bulunamadı."})
        cfg = I.settings()
        profile = I.book_profile(book, cfg)
        if not profile["topics"]:
            m = llm()
            if m is not None and hasattr(m, "choose"):
                text = " | ".join(x for x in (book.get("ad"), book.get("turler"), book.get("raf"), book.get("hedefKitle"),
                                               (book.get("ozet") or "")[:1200]) if x)
                labels = [v for k, v in I.TOPICS.items() if k != "diger"]
                try:
                    res = m.choose("Bu kitabın ana konusu hangisi?\n\n" + text, labels)
                    if res.choice and res.confident(cfg["explainProb"], 0.2):
                        key = next(k for k, v in I.TOPICS.items() if v == res.choice)
                        profile.update(topics=[key], topicSource="zeki", topicProbability=round(res.probability, 3))
                except Exception as e:  # noqa: BLE001 — model yoksa konu «bilinmiyor» kalır, puan nötr
                    log.warning("kitap konu etiketi modelden alınamadı: %s", e)
        return book, profile

    # ------------------------------------------------------------------ genel

    @app.get(P + "/meta")
    def infl_meta(request: Request) -> dict[str, Any]:
        _, _, user, display = ctx(request)
        from semantic_bridge import alerts as alerts_mod

        out = I.meta()
        out["me"] = {"username": user, "display": display, "canEdit": can(user, FEATURE_EDIT),
                     "canApprove": can(user, FEATURE_APPROVE), "canPay": can(user, FEATURE_PAY), "canSeeFee": fee_ok(user),
                     "canExport": can(user, FEATURE_EXPORT)}
        out["modelVar"] = llm() is not None
        out["eposta"] = alerts_mod.email_status()
        return out

    @app.get(P + "/board")
    def infl_board(request: Request, mine: bool = False) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        return call(I.board, engine, tenant, user, fee_ok(user), mine=mine)

    # ------------------------------------------------------------------ kayıt defteri

    @app.get(P + "/people")
    def infl_people(request: Request, q: str = "", platform: str = "", topic: str = "", age: str = "",
                    idle: Optional[int] = None, dnc: bool = True) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        return call(I.list_people, engine, tenant, can_fee=fee_ok(user), q=q, platform=platform, topic=topic, age=age,
                    idle_days=idle, include_dnc=dnc)

    @app.post(P + "/people", status_code=201)
    def infl_people_create(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        if any(body.get(k) not in (None, "") for k in ("feeMin", "feeMax")) and not fee_ok(user):
            raise HTTPException(403, detail={"code": "FORBIDDEN", "message": "Ücret aralığını onay ya da ödeme yetkisi olan girer."})
        out = call(I.create_person, engine, tenant, user, body)
        audit(engine, user, "create", "influencer_person", out["id"], out["name"],
              {"hesap": len(body.get("accounts") or []), "konu": body.get("topics")})
        return out

    @app.post(P + "/people/import")
    def infl_people_import(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(I.import_csv, engine, tenant, user, str(body.get("text") or ""))
        audit(engine, user, "upload", "influencer_person", None, str(body.get("filename") or "CSV")[:200],
              {k: (len(v) if isinstance(v, list) else v) for k, v in out.items()})
        return out

    @app.get(P + "/people/{pid}")
    def infl_person(pid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(I.get_person, engine, tenant, pid, fee_ok(user))
        # Tanıtım gönderimi: kartlara yazılmış CRM sipariş numaralarından (yalnız okuma). CRM kapalıysa kart yine açılır.
        out["crmOrders"] = None
        if out["orderNos"]:
            try:
                out["crmOrders"] = crm().promo_orders(out["orderNos"])
            except src.SourceError as e:
                out["crmOrders"] = {"hata": str(e)}
        return out

    @app.patch(P + "/people/{pid}")
    def infl_person_update(pid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out, changed = call(I.update_person, engine, tenant, user, pid, body, fee_ok(user))
        if changed:
            audit(engine, user, "update", "influencer_person", pid, out["name"], changed)
        return out

    @app.post(P + "/people/{pid}/suggest-topics")
    def infl_person_topics(pid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        """Biyografi ya da son gönderi başlıklarından (elle yapıştırılan metin) konu önerisi; kaydedilmez."""
        engine, tenant, _, _ = ctx(request)
        call(I.get_person, engine, tenant, pid, False)
        text = str(body.get("text") or "").strip()[:4000]
        if len(text) < 20:
            raise HTTPException(400, detail={"code": "INFLUENCER", "message": "En az bir iki cümlelik biyografi ya da gönderi metni yapıştırın."})
        m = llm()
        if m is None or not hasattr(m, "choose"):
            raise HTTPException(503, detail={"code": "INFLUENCER", "message": "Zeki AI bu kurulumda tanımlı değil."})
        labels = list(I.TOPICS.values())
        try:
            res = m.choose("Bu içerik üreticisinin paylaşımları en çok hangi kitap konusunda?\n\n" + text, labels)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(503, detail={"code": "INFLUENCER", "message": "Zeki AI şu an cevap vermiyor."}) from e
        key = next((k for k, v in I.TOPICS.items() if v == res.choice), None)
        cfg = I.settings()
        return {"topic": key, "label": res.choice, "probability": res.probability,
                "confident": bool(key and res.confident(cfg["explainProb"], 0.2))}

    @app.post(P + "/accounts/{aid}/snapshots", status_code=201)
    def infl_snapshot(aid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(I.add_snapshot, engine, tenant, user, aid, body)
        audit(engine, user, "create", "influencer_snapshot", aid, out["day"],
              {k: out[k] for k in ("followers", "posts", "avg_likes", "avg_comments")})
        return out

    @app.get(P + "/crm/contacts")
    def infl_crm_contacts(request: Request, instagram: str = "", youtube: str = "", x: str = "") -> dict[str, Any]:
        ctx(request)
        handles = {k: [v] for k, v in (("instagram", instagram), ("youtube", youtube), ("x", x)) if v.strip()}
        if not handles:
            return {"items": []}
        return {"items": call(crm().social_contacts, handles)}

    @app.get(P + "/crm/summary")
    def infl_crm_summary(request: Request) -> dict[str, Any]:
        ctx(request)
        return call(crm().social_summary)

    # ------------------------------------------------------------------ aday sırası

    @app.get(P + "/books/{kitap}/candidates")
    def infl_candidates(kitap: str, request: Request, butce: Optional[float] = None) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        book, profile = book_info(kitap)
        out = call(I.candidates, engine, tenant, book, profile, budget=butce if butce and butce > 0 else None,
                   can_fee=fee_ok(user))
        out["collabs"] = call(I.book_collabs, engine, tenant, book["kitapId"], fee_ok(user))["items"] if book.get("kitapId") else []
        out["modelVar"] = llm() is not None
        return out

    @app.post(P + "/books/{kitap}/candidates/explain")
    def infl_candidates_explain(kitap: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        """Seçilen adaylar için Zeki AI gerekçe cümlesi. Kural gerekçesindeki olgular dışında sayı içeren cümle düşer;
        o zaman kural gerekçesi kalır."""
        from semantic_bridge.marketing import guard

        engine, tenant, user, _ = ctx(request)
        ids = [str(x) for x in body.get("personIds") or []]
        if not ids:
            raise HTTPException(400, detail={"code": "INFLUENCER", "message": "Aday seçilmedi."})
        book, profile = book_info(kitap)
        ranked = call(I.candidates, engine, tenant, book, profile, budget=None, can_fee=False)
        by = {i["personId"]: i for i in ranked["items"]}
        chat = chatter(160)
        out = []
        for pid in ids:
            c = by.get(pid)
            if c is None:
                continue
            text, source, dropped = c["reason"], "kural", []
            if chat is not None:
                msg = [{"role": "system", "content": "Sen Zeki AI'sın. Verilen olgulardan tek bir Türkçe cümle yaz: bu içerik "
                                                     "üreticisi bu kitap için neden uygun ya da değil. Olgu dışında sayı, ad "
                                                     "ya da iddia yazma."},
                       {"role": "user", "content": f"Kitap: {book.get('ad')}\nİçerik üreticisi: {c['name']}\nPuan: {c['score']}\n"
                                                   f"Olgular: {c['reason']}"}]
                try:
                    raw = (chat(msg) or "").strip()
                except Exception as e:  # noqa: BLE001
                    log.warning("aday gerekçesi modelden alınamadı: %s", e)
                    raw = ""
                if raw:
                    checked = guard.check(raw, [c["reason"]], [c["name"], book.get("ad") or "", str(c["score"])])
                    dropped = checked["dusen"]
                    if checked["metin"].strip():
                        text, source = checked["metin"].strip(), "zeki"
            out.append({"personId": pid, "text": text, "source": source, "dropped": len(dropped)})
        return {"items": out}

    @app.get(P + "/books/{kitap}/collabs")
    def infl_book_collabs(kitap: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        return call(I.book_collabs, engine, tenant, kitap, fee_ok(user))

    # ------------------------------------------------------------------ işbirliği

    @app.post(P + "/collabs", status_code=201)
    def infl_collab_create(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(I.create_collab, engine, tenant, user, body)
        audit(engine, user, "create", "influencer_collab", out["id"], f"İŞB-{out['no']} {out['personName']} · {out['bookTitle'] or ''}",
              {"tur": body.get("kind"), "kitap": body.get("crmBookId"), "ucret": "girildi" if body.get("fee") else "yok"})
        recips = _recipients("INFLUENCER_APPROVAL_RECIPIENTS")
        if out["waitingApproval"] and recips:
            from semantic_bridge.budget_api import _send_mail

            link = (admin_mod.conf("ALERT_LINK") or "").split("/uyarilar")[0]
            out["bildirim"] = _send_mail(f"Onay bekleyen işbirliği: İŞB-{out['no']}",
                                         f"İŞB-{out['no']} {out['personName']} · {out['bookTitle'] or ''} teklifi onayınızı bekliyor.\n"
                                         f"Açan: {user}\n" + (f"\nPano: {link}/isbirlikleri\n" if link else ""), recips)
        return out

    @app.get(P + "/collabs/{cid}")
    def infl_collab(cid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        return call(I.get_collab, engine, tenant, cid, fee_ok(user))

    @app.patch(P + "/collabs/{cid}")
    def infl_collab_update(cid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out, diff = call(I.update_collab, engine, tenant, user, cid, body, fee_ok(user))
        if diff:
            audit(engine, user, "update", "influencer_collab", cid, f"{out['code']} {out['personName'] or ''}", diff)
        return out

    @app.post(P + "/collabs/{cid}/approve")
    def infl_collab_approve(cid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(can(user, FEATURE_APPROVE), "İşbirliği onayı")
        out = call(I.approve_collab, engine, tenant, user, cid, body)
        audit(engine, user, "approve" if out["decision"] == "onay" else "reject", "influencer_collab", cid,
              f"İŞB-{out['no']}", {"not": body.get("note")})
        return out

    @app.post(P + "/collabs/{cid}/draft", status_code=201)
    def infl_collab_draft(cid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        kind = str(body.get("kind") or "brief")
        c = call(I.get_collab, engine, tenant, cid, False)
        book = None
        if c.get("crmBookId") or c.get("bookCode"):
            try:
                book = crm().book(c.get("crmBookId") or c.get("bookCode"))
            except src.SourceError as e:
                log.warning("taslak için kitap okunamadı: %s", e)
        facts = call(I.draft_facts, engine, tenant, cid, book)
        extra = [x.strip() for x in (admin_mod.conf("MARKETING_BANNED_CLAIMS") or "").split(",") if x.strip()]
        d = call(I.render_draft, kind, facts, chatter(700), extra)
        out = call(I.save_draft, engine, tenant, user, cid, kind, d)
        audit(engine, user, "create", "influencer_draft", out["id"], f"{c['code']} {I.DRAFT_KINDS.get(kind, kind)}",
              {"kaynak": out["source"], "dusen": len(out["dropped"]), "kitapCrm": book is not None})
        return out

    @app.patch(P + "/collabs/{cid}/drafts/{did}")
    def infl_draft_edit(cid: str, did: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(I.edit_draft, engine, tenant, user, cid, did, body)
        audit(engine, user, "update", "influencer_draft", did, out["kindLabel"], {"isbirligi": cid})
        return out

    @app.post(P + "/collabs/{cid}/drafts/{did}/approve")
    def infl_draft_approve(cid: str, did: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(can(user, FEATURE_APPROVE), "Taslak onayı")
        out = call(I.approve_draft, engine, tenant, user, cid, did)
        audit(engine, user, "approve", "influencer_draft", did, out["kindLabel"], {"isbirligi": cid})
        return out

    @app.post(P + "/collabs/{cid}/mail")
    def infl_collab_mail(cid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        """Onaylı taslağın insan tarafından kendi e-postasıyla gönderildiğinin kaydı (portal dışarı e-posta atmaz)."""
        engine, tenant, user, _ = ctx(request)
        out = call(I.mark_mailed, engine, tenant, user, cid, str(body.get("draftId") or ""))
        audit(engine, user, "update", "influencer_draft", out["id"], f"{out['kindLabel']} elle gönderildi", {"isbirligi": cid})
        return out

    # ------------------------------------------------------------------ ödeme

    @app.get(P + "/payouts")
    def infl_payouts(request: Request, month: str = "") -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(fee_ok(user), "Ödeme listesi")
        out = call(I.list_payouts, engine, tenant, month)
        out["me"] = {"canApprove": can(user, FEATURE_APPROVE), "canPay": can(user, FEATURE_PAY),
                     "canExport": can(user, FEATURE_EXPORT)}
        return out

    @app.post(P + "/payouts/{pid}/decide")
    def infl_payout_decide(pid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(fee_ok(user), "Ödeme işlemi")
        out = call(I.decide_payout, engine, tenant, user, pid, body, can_approve=can(user, FEATURE_APPROVE),
                   can_pay=can(user, FEATURE_PAY))
        audit(engine, user, {"onayla": "approve", "geri": "reject", "iptal": "delete"}.get(out["action"], "update"),
              "influencer_payout", pid, f"#{out['no']}", {"islem": out["action"], "tutar": out["amount"],
                                                         "logo": body.get("logoDocNo"), "not": body.get("note")})
        return out

    @app.get(P + "/payouts/export.xlsx")
    def infl_payouts_export(request: Request, month: str = "") -> Response:
        engine, tenant, user, _ = ctx(request)
        need(fee_ok(user), "Ödeme listesi")
        data = call(I.list_payouts, engine, tenant, month)
        audit(engine, user, "export", "influencer_payout", None, f"Ödeme listesi {data['month']}", {"satir": len(data["items"])})
        return Response(I.payouts_xlsx(data), media_type=XLSX,
                        headers={"Content-Disposition": f'attachment; filename="isbirligi-odeme-{data["month"]}.xlsx"'})

    # ------------------------------------------------------------------ rapor

    def period(frm: str, to: str) -> tuple[date, date]:
        """Varsayılan dönem: bu ayın başından bugüne."""
        today = I._today()
        try:
            a = date.fromisoformat(frm) if frm else today.replace(day=1)
            b = date.fromisoformat(to) if to else today
        except ValueError as e:
            raise HTTPException(400, detail={"code": "INFLUENCER", "message": "Tarih YYYY-AA-GG biçiminde olmalı."}) from e
        return a, b

    @app.get(P + "/report")
    def infl_report(request: Request, frm: str = "", to: str = "", crm_spend: bool = True) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        a, b = period(frm, to)
        out = call(I.report, engine, tenant, a, b, fee_ok(user))
        out["crm"] = None
        if crm_spend and fee_ok(user):
            try:
                out["crm"] = crm().crm_spend(a, b)
            except src.SourceError as e:
                out["crm"] = {"hata": str(e)}
        return out

    @app.get(P + "/report/export.xlsx")
    def infl_report_export(request: Request, frm: str = "", to: str = "") -> Response:
        engine, tenant, user, _ = ctx(request)
        a, b = period(frm, to)
        rep = call(I.report, engine, tenant, a, b, fee_ok(user))
        crm_part = None
        if fee_ok(user):
            try:
                crm_part = crm().crm_spend(a, b)
            except src.SourceError:
                crm_part = None
        audit(engine, user, "export", "influencer_report", None, f"İşbirlikleri raporu {a}–{b}", {"is": rep["total"]["collabs"]})
        return Response(I.report_xlsx(rep, crm_part, fee_ok(user)), media_type=XLSX,
                        headers={"Content-Disposition": f'attachment; filename="isbirlikleri-{a}-{b}.xlsx"'})

    # ------------------------------------------------------------------ zamanlayıcı

    @app.post(P + "/run-due")
    def infl_run_due(request: Request) -> dict[str, Any]:
        """Zamanlayıcı: bugünün hatırlatmaları iç ekibe tek özet e-postayla (bir kez)."""
        require_caller(request)
        from semantic_bridge.budget_api import _send_mail

        r = rt()
        engine, tenant = r.store.engine, r.settings.tenant_id
        I.ensure(engine)
        cfg = I.settings()
        items = I.unsent(engine, tenant, I.reminders(engine, tenant, cfg))
        link = (admin_mod.conf("ALERT_LINK") or "").split("/uyarilar")[0]
        link = f"{link}/isbirlikleri" if link else ""
        groups = {"INFLUENCER_ALERT_RECIPIENTS": [i for i in items if i["to"] not in ("mudur", "muhasebe")],
                  "INFLUENCER_APPROVAL_RECIPIENTS": [i for i in items if i["to"] == "mudur"],
                  "INFLUENCER_PAYOUT_RECIPIENTS": [i for i in items if i["to"] == "muhasebe"]}
        result: dict[str, Any] = {}
        for key, group in groups.items():
            recips = _recipients(key) or _recipients("INFLUENCER_ALERT_RECIPIENTS")
            if not group:
                result[key] = "bos"
            elif not recips:
                result[key] = "alici_yok"
            else:
                status = _send_mail(f"İşbirlikleri: {len(group)} hatırlatma", I.reminder_text(group, link), recips)
                if status == "sent":
                    I.mark_sent(engine, tenant, [i["key"] for i in group])
                result[key] = status
        return {"hatirlatma": len(items), "eposta": result,
                "hesapSayilari": "kapalı" if not cfg["apiEnabled"] else "ikinci sürümde (resmî API istemcisi yok)"}

    return {"crm": crm}
