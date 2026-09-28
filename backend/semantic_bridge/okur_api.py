"""M37 Okur topluluğu uçları: /api/v1/okur/*.

Sayfa kapısı `access.RULES` (`sayfa:okur-toplulugu`, `okur-segmentler`, `okur-programlar`, `okur-yorumlar`). Segment yazma
`ozellik:topluluk.segment-yaz`, program `ozellik:topluluk.program-yaz`, yorum taslağı `ozellik:topluluk.yorum-taslak`
(`FEATURE_RULES`). Açıkça verilenler ucun içinde: segment onayı ve ilgi alanı çağrışım kararı
`ozellik:topluluk.segment-onay` (KVKK sorumlusu; yazan/gönderen onaylayamaz), kişi listesi dışa aktarımı
`ozellik:topluluk.liste-disa-aktar` (ikinci sürüm; bu sürümde uç 501 döner).

H2 okur çekirdeği `okur_sources.ReadersCore.resolve(app)` ile her istekte aranır (H2 sonradan kaydolursa yeniden başlatma
gerekmez); yoksa sayı uçları `bagli: false` ve «Okur çekirdeği bağlı değil» döner, ölçüm ve onaya gönderme 409 verir.

Zamanlayıcı (`timas-okur.timer`, her gece 03:50; H2'nin 03:20 turundan sonra) yalnız `POST /api/v1/okur/run-due`'yu
çağırır: envanter ve izin anlık görüntüsü, segment büyüklükleri, süresi dolan segment, ilgi alanı çağrışım sınıflaması,
cevapsız yorum sayısı, yaklaşan program; iç ekibe tek özet e-posta (`OKUR_ALERT_RECIPIENTS`). Okura hiçbir şey gitmez.

Model çağrıları LLM kapısından: `rt.llm_for("okur", NORMAL)` ekrandan, `rt.llm_for("okur", BATCH)` gece. `LlmClient`
doğrudan kurulmaz. Rakamı model üretmez; istemde kişi verisi yoktur (`okur.assert_no_personal`).
"""
from __future__ import annotations

import logging
import os
from datetime import date
from typing import Any, Callable, Optional

from fastapi import HTTPException, Request
from starlette.concurrency import run_in_threadpool

from semantic_bridge import okur as O
from semantic_bridge import okur_sources as src

log = logging.getLogger("semantic.okur.api")
P = "/api/v1/okur"
FEATURE_SEGMENT = "ozellik:topluluk.segment-yaz"
FEATURE_APPROVE = "ozellik:topluluk.segment-onay"
FEATURE_PROGRAM = "ozellik:topluluk.program-yaz"
FEATURE_REVIEW = "ozellik:topluluk.yorum-taslak"
FEATURE_EXPORT = "ozellik:topluluk.liste-disa-aktar"


def register(app, rt: Callable[[], Any], require_caller: Callable[[Request], None], can: Callable[[str, str], bool]):
    from semantic_bridge import admin as admin_mod
    from semantic_bridge import board as board_mod

    comments = src.Comments()

    def crm_path() -> str:
        return os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json")

    def schema() -> str:
        return admin_mod.conf("CRM_SCHEMA") or "Timas_MSCRM.dbo"

    def crm():
        return src.runner(crm_path())

    def core() -> Optional[src.ReadersCore]:
        return src.ReadersCore.resolve(app)

    def need_core() -> src.ReadersCore:
        c = core()
        if c is None:
            raise HTTPException(409, detail={"code": "OKUR_CORE", "message": src.NOT_CONNECTED + "; okur sayıları ve segment ölçümü "
                                                                            "okur veri tabanı modülü kurulunca açılır."})
        return c

    def llm(batch: bool = False):
        try:
            from semantic_layer.runtime.llm_queue import BATCH, NORMAL
            return rt().llm_for("okur", BATCH if batch else NORMAL)
        except Exception:  # noqa: BLE001 — model tanımlı değil
            return None

    def chooser(batch: bool = False):
        m = llm(batch)
        if m is None or not hasattr(m, "choose"):
            return None
        return lambda prompt, choices: m.choose(prompt, choices)

    def ctx(request: Request) -> tuple[Any, str, str, str]:
        require_caller(request)
        try:
            user, display = board_mod.session_of(request.headers.get("cookie", ""))
        except board_mod.NoUser:
            raise HTTPException(status_code=401, detail={"code": "UNAUTHORIZED", "message": "Oturum gerekli."}) from None
        r = rt()
        O.ensure(r.store.engine)
        admin_mod.ensure(r.store.engine)
        return r.store.engine, r.settings.tenant_id, user, display

    def call(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except O.OkurError as e:
            raise HTTPException(status_code=e.status, detail={"code": "OKUR", "message": str(e)}) from e
        except src.CoreUnavailable as e:
            raise HTTPException(status_code=409, detail={"code": "OKUR_CORE", "message": str(e)}) from e
        except src.SourceError as e:
            raise HTTPException(status_code=503, detail={"code": "OKUR_SOURCE", "message": str(e)}) from e

    def need(user: str, key: str, what: str) -> None:
        if not can(user, key):
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": f"{what} rolünüzde yok."})

    def audit(engine, user, action, kind, oid, title, detail=None) -> None:
        admin_mod.audit(engine, user, action, kind, oid, title, detail)

    def rule_info(c: Optional[src.ReadersCore], rule: dict[str, Any]) -> tuple[list[str], Optional[str]]:
        if c is None:
            return O.rule_interest_ids(rule), None
        return call(c.rule_interests, rule), c.rule_text(rule)

    def guard_for(engine, tenant: str, interest_ids: list[str]) -> dict[str, Any]:
        c = core()
        names = {}
        if c is not None and interest_ids:
            try:
                names = {i["id"]: i["ad"] for i in c.interests(tenant)}
            except (src.SourceError, src.CoreUnavailable):
                names = {}
        return O.guard_rule(engine, tenant, interest_ids, names)

    def unavailable(e: Exception) -> dict[str, Any]:
        return {"bagli": False, "mesaj": str(e) if isinstance(e, src.SourceError) else src.NOT_CONNECTED}

    # ------------------------------------------------------------------ genel

    @app.get(P + "/meta")
    def okur_meta(request: Request) -> dict[str, Any]:
        _, _, user, display = ctx(request)
        c = core()
        out = O.meta()
        out["me"] = {"username": user, "display": display, "canSegment": can(user, FEATURE_SEGMENT),
                     "canApprove": can(user, FEATURE_APPROVE), "canProgram": can(user, FEATURE_PROGRAM),
                     "canReview": can(user, FEATURE_REVIEW), "canExport": can(user, FEATURE_EXPORT)}
        out["cekirdek"] = {"bagli": c is not None, "mesaj": None if c else src.NOT_CONNECTED,
                           "kuralAlanlari": c.rule_fields() if c else []}
        out["modelVar"] = llm() is not None
        return out

    def _overview(engine, tenant: str) -> dict[str, Any]:
        c = core()
        inv: dict[str, Any] = {"bagli": False, "mesaj": src.NOT_CONNECTED}
        consent: dict[str, Any] = {"bagli": False, "mesaj": src.NOT_CONNECTED}
        if c is not None:
            try:
                inv = {"bagli": True, **c.inventory(tenant)}
            except (src.SourceError, src.CoreUnavailable) as e:
                inv = unavailable(e)
            try:
                items = c.consent(tenant)
                consent = {"bagli": True, "items": items, "toplam": sum(x["sayi"] for x in items)}
            except (src.SourceError, src.CoreUnavailable) as e:
                consent = unavailable(e)
        segs = O.list_segments(engine, tenant)
        progs = O.due_programs(engine, tenant, 30)
        return {"envanter": inv, "izin": consent, "segmentSayilari": segs["durumSayilari"], "yaklasanProgramlar": progs,
                "yorum": O.meta_get(engine, tenant, "yorum_ozet", None),
                "egilim": O.trend(engine, tenant, (date.today().replace(day=1).replace(year=date.today().year - 1)).isoformat())}

    @app.get(P + "/overview")
    def okur_overview(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return O.scrub(call(_overview, engine, tenant))

    @app.get(P + "/consent-health")
    def okur_consent(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        c = core()
        if c is None:
            return {"bagli": False, "mesaj": src.NOT_CONNECTED, "items": []}
        try:
            items = c.consent(tenant)
        except (src.SourceError, src.CoreUnavailable) as e:
            return {**unavailable(e), "items": []}
        today = O.today().isoformat()
        return O.scrub({"bagli": True, "items": items, "toplam": sum(x["sayi"] for x in items),
                        "onceki": O.consent_previous(engine, tenant, today)})

    @app.get(P + "/inventory")
    def okur_inventory(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        qp = request.query_params
        since = call(O._day, qp.get("from"), "Başlangıç") if qp.get("from") else None
        until = call(O._day, qp.get("to"), "Bitiş") if qp.get("to") else None
        return O.trend(engine, tenant, since, until)

    # ------------------------------------------------------------------ ilgi alanları ve çağrışım koruması

    @app.get(P + "/categories")
    def okur_categories(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        c = core()
        if c is None:
            return {"bagli": False, "mesaj": src.NOT_CONNECTED, "items": [], "hassasAcik": O.settings()["sensitiveOpen"]}
        try:
            items = O.interest_view(engine, tenant, c.interests(tenant))
        except (src.SourceError, src.CoreUnavailable) as e:
            return {**unavailable(e), "items": []}
        return O.scrub({"bagli": True, "items": items, "hassasAcik": O.settings()["sensitiveOpen"],
                        "sayilar": {k: sum(1 for i in items if i["isaret"] == k) for k in O.FLAG_STATES}})

    @app.post(P + "/categories/classify")
    async def okur_categories_classify(request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        c = need_core()
        choose = chooser()
        if choose is None:
            raise HTTPException(503, detail={"code": "OKUR", "message": "Zeki AI bu kurulumda tanımlı değil; ilgi alanları sınıflanamıyor."})
        items = await run_in_threadpool(call, c.interests, tenant)
        out = await run_in_threadpool(O.classify_missing, engine, tenant, items, choose)
        audit(engine, user, "run", "okur_interest", None, "İlgi alanı çağrışım sınıflaması", out)
        return out

    @app.post(P + "/categories/{kid}/decision")
    def okur_category_decision(kid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, FEATURE_APPROVE, "İlgi alanı KVKK kararı")
        out = call(O.set_flag, engine, tenant, kid, body.get("ad"), str(body.get("isaret") or ""), kaynak="insan",
                   karar_veren=user, gerekce=body.get("gerekce"))
        audit(engine, user, "update", "okur_interest", kid, body.get("ad") or kid,
              {"isaret": out["isaret"], "gerekce": (body.get("gerekce") or "")[:500]})
        return out

    # ------------------------------------------------------------------ segmentler

    @app.get(P + "/segments")
    def okur_segments(request: Request, durum: str = "") -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return call(O.list_segments, engine, tenant, durum)

    @app.post(P + "/segments", status_code=201)
    def okur_segment_create(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        rule = body.get("kural") if isinstance(body.get("kural"), dict) else {}
        ids, text = rule_info(core(), rule) if rule else ([], None)
        out = call(O.create_segment, engine, tenant, user, body, ids, text)
        out["kvkk"] = guard_for(engine, tenant, out["ilgiAlanlari"])
        audit(engine, user, "create", "okur_segment", out["id"], out["ad"], {"kanal": out["kanal"], "amac": out["amac"]})
        return out

    @app.post(P + "/segments/preview-rule")
    def okur_segment_preview_rule(body: dict[str, Any], request: Request) -> dict[str, Any]:
        """Kaydedilmemiş kuralın büyüklüğü (segment kurucusu). Yalnız sayı; kayıt yazılmaz."""
        engine, tenant, _, _ = ctx(request)
        c = need_core()
        rule = body.get("kural")
        if not isinstance(rule, dict) or not rule:
            raise HTTPException(400, detail={"code": "OKUR", "message": "Kural boş."})
        ids, text = rule_info(c, rule)
        g = guard_for(engine, tenant, ids)
        if not g["ok"]:
            return {"olcum": None, "kvkk": g, "kuralCumlesi": text}
        return O.scrub({"olcum": call(c.size, tenant, rule), "kvkk": g, "kuralCumlesi": text})

    @app.get(P + "/segments/{sid}")
    def okur_segment(sid: str, request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        out = call(O.segment_detail, engine, tenant, sid)
        out["kvkk"] = guard_for(engine, tenant, out["ilgiAlanlari"])
        return out

    @app.patch(P + "/segments/{sid}")
    def okur_segment_update(sid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        ids, text = (None, None)
        if isinstance(body.get("kural"), dict) and body["kural"]:
            ids, text = rule_info(core(), body["kural"])
        out, diff = call(O.update_segment, engine, tenant, user, sid, body, ids, text)
        if diff:
            audit(engine, user, "update", "okur_segment", sid, out["ad"], {k: v for k, v in diff.items() if k != "kural_json"}
                  | ({"kural": "değişti"} if "kural_json" in diff else {}))
        out["kvkk"] = guard_for(engine, tenant, out["ilgiAlanlari"])
        return out

    @app.delete(P + "/segments/{sid}")
    def okur_segment_delete(sid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(O.delete_segment, engine, tenant, sid)
        audit(engine, user, "delete", "okur_segment", sid, out["ad"])
        return {"ok": True}

    @app.post(P + "/segments/{sid}/preview")
    def okur_segment_preview(sid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        c = need_core()
        seg = call(O.segment_detail, engine, tenant, sid)
        g = guard_for(engine, tenant, seg["ilgiAlanlari"])
        if not g["ok"]:
            raise HTTPException(409, detail={"code": "OKUR_KVKK", "message": " ".join(x["mesaj"] for x in g["engel"])})
        size = call(c.size, tenant, seg["kural"])
        call(O.record_size, engine, tenant, sid, size)
        out = call(O.segment_detail, engine, tenant, sid)
        out["kvkk"] = g
        return O.scrub(out)

    @app.post(P + "/segments/{sid}/submit")
    def okur_segment_submit(sid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need_core()
        seg = call(O.segment_detail, engine, tenant, sid)
        out = call(O.submit_segment, engine, tenant, user, sid, guard_for(engine, tenant, seg["ilgiAlanlari"]))
        audit(engine, user, "update", "okur_segment", sid, out["ad"], {"durum": "onay_bekliyor", "amac": out["amac"],
                                                                        "sureBitis": out["sureBitis"], "sonOlcum": out["sonOlcum"]})
        return out

    @app.post(P + "/segments/{sid}/withdraw")
    def okur_segment_withdraw(sid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(O.withdraw_segment, engine, tenant, user, sid)
        audit(engine, user, "update", "okur_segment", sid, out["ad"], {"durum": "geri çekildi"})
        return out

    @app.post(P + "/segments/{sid}/decision")
    def okur_segment_decision(sid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, FEATURE_APPROVE, "Segment KVKK onayı")
        karar = str(body.get("karar") or "")
        if karar not in ("onayla", "reddet"):
            raise HTTPException(400, detail={"code": "OKUR", "message": "Karar onayla ya da reddet olmalı."})
        seg = call(O.segment_detail, engine, tenant, sid)
        out = call(O.decide_segment, engine, tenant, user, sid, karar == "onayla", body.get("not"),
                   guard_for(engine, tenant, seg["ilgiAlanlari"]))
        audit(engine, user, "approve" if karar == "onayla" else "reject", "okur_segment", sid, out["ad"],
              {"amac": out["amac"], "sureBitis": out["sureBitis"], "kanal": out["kanal"], "not": body.get("not"),
               "sonOlcum": out["sonOlcum"]})
        return out

    @app.post(P + "/segments/{sid}/export")
    def okur_segment_export(sid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, FEATURE_EXPORT, "Okur listesi dışa aktarımı")
        call(O.segment_detail, engine, tenant, sid)
        raise HTTPException(501, detail={"code": "OKUR_EXPORT", "message": "Kişi listesi dışa aktarımı ikinci sürümde; hukuk görüşü "
                                                                           "(aydınlatma ve rıza metni) gelmeden açılmaz."})

    @app.get(P + "/contract/segments")
    def okur_contract_segments(request: Request) -> dict[str, Any]:
        """Sözleşme: onaylı ve süresi dolmamış topluluk segmentleri (M24 bülten, M35 kampanya). Kişi listesi yok."""
        engine, tenant, _, _ = ctx(request)
        return {"items": O.approved_segments(engine, tenant)}

    # ------------------------------------------------------------------ programlar

    @app.get(P + "/programs")
    def okur_programs(request: Request, durum: str = "", tur: str = "") -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        qp = request.query_params
        return call(O.list_programs, engine, tenant, qp.get("from") or "", qp.get("to") or "", durum, tur)

    @app.post(P + "/programs", status_code=201)
    def okur_program_create(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(O.create_program, engine, tenant, user, body)
        audit(engine, user, "create", "okur_program", out["id"], out["ad"], {"tur": out["tur"], "tarih": out["tarih"]})
        return out

    @app.get(P + "/programs/{pid}")
    def okur_program(pid: str, request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return call(O.program_detail, engine, tenant, pid)

    @app.patch(P + "/programs/{pid}")
    def okur_program_update(pid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out, diff = call(O.update_program, engine, tenant, user, pid, body)
        if diff:
            audit(engine, user, "update", "okur_program", pid, out["ad"], diff)
        return out

    @app.delete(P + "/programs/{pid}")
    def okur_program_delete(pid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(O.delete_program, engine, tenant, pid)
        audit(engine, user, "delete", "okur_program", pid, out["ad"])
        return {"ok": True}

    @app.post(P + "/programs/{pid}/draft")
    async def okur_program_draft(pid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        m = llm()
        if m is None:
            raise HTTPException(503, detail={"code": "OKUR", "message": "Zeki AI bu kurulumda tanımlı değil; duyuru taslağı üretilemiyor."})
        p = await run_in_threadpool(call, O.program_detail, engine, tenant, pid)
        book = None
        if p.get("kitapId"):
            try:
                book = await run_in_threadpool(src.read_book, crm(), schema(), p["kitapId"])
            except src.SourceError as e:
                log.warning("okur: kitap kartı okunamadı: %s", e)
        seg = None
        if p.get("segmentId"):
            seg = await run_in_threadpool(call, O.segment_detail, engine, tenant, p["segmentId"])
        msgs = call(O.announcement_messages, p, book, seg)
        try:
            text = await run_in_threadpool(lambda: m.chat(msgs, max_tokens=900, temperature=0.4))
        except Exception as e:  # noqa: BLE001
            raise HTTPException(503, detail={"code": "OKUR", "message": f"Zeki AI cevap vermedi ({str(e)[:160]})."}) from e
        text = O.clean_model_text(text)
        if not text:
            raise HTTPException(503, detail={"code": "OKUR", "message": "Zeki AI boş taslak döndürdü; yeniden deneyin."})
        out = await run_in_threadpool(O.set_announcement, engine, tenant, user, pid, text)
        audit(engine, user, "run", "okur_program", pid, p["ad"], {"is": "duyuru taslağı", "kitapKarti": bool(book)})
        return out

    @app.get(P + "/books")
    async def okur_books(request: Request, q: str = "") -> dict[str, Any]:
        await run_in_threadpool(ctx, request)
        return {"items": await run_in_threadpool(call, lambda: src.search_books(crm(), schema(), q))}

    # ------------------------------------------------------------------ geçmiş etkinlikler (CRM)

    @app.get(P + "/events-summary")
    async def okur_events(request: Request, yil: int = 0) -> dict[str, Any]:
        await run_in_threadpool(ctx, request)
        cfg = O.settings()
        run = await run_in_threadpool(call, crm)
        years = await run_in_threadpool(call, src.read_event_years, run, schema(), cfg["eventsExcludeVisits"])
        y = yil or (years[0] if years else date.today().year)
        if not 2000 <= y <= 2100:
            raise HTTPException(400, detail={"code": "OKUR", "message": "Yıl geçersiz."})
        out = await run_in_threadpool(call, src.read_events, run, schema(), y, cfg["eventsExcludeVisits"], cfg["eventTypes"])
        return {**out, "yillar": years, "ziyaretHaric": cfg["eventsExcludeVisits"], "tipSuzgeci": cfg["eventTypes"]}

    # ------------------------------------------------------------------ yorumlar

    def _reviews(engine, tenant: str, fresh: bool = False) -> list[dict[str, Any]]:
        rows = comments.read(O.settings()["reviewCacheSeconds"], fresh)
        names = src.product_names(engine, tenant, [r["productId"] for r in rows if r.get("productId")])
        return O.merge_reviews(rows, O.review_status(engine, tenant), names)

    @app.get(P + "/reviews")
    async def okur_reviews(request: Request, durum: str = "", yenile: bool = False) -> dict[str, Any]:
        engine, tenant, _, _ = await run_in_threadpool(ctx, request)
        if durum and durum not in O.REVIEW_STATES:
            raise HTTPException(400, detail={"code": "OKUR", "message": "Bilinmeyen yorum durumu."})
        items = await run_in_threadpool(call, _reviews, engine, tenant, yenile)
        counts = O.review_counts(items)
        return O.scrub({"items": [r for r in items if not durum or r["durum"] == durum], "sayilar": counts,
                        "seo": src.seo_review_total(engine, tenant)})

    @app.post(P + "/reviews/{cid}/draft")
    async def okur_review_draft(cid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        m = llm()
        if m is None:
            raise HTTPException(503, detail={"code": "OKUR", "message": "Zeki AI bu kurulumda tanımlı değil; cevap taslağı üretilemiyor."})
        cm = await run_in_threadpool(call, comments.one, cid, O.settings()["reviewCacheSeconds"])
        if cm is None:
            raise HTTPException(404, detail={"code": "OKUR", "message": "Yorum bulunamadı."})
        if not (cm.get("metin") or "").strip():
            raise HTTPException(400, detail={"code": "OKUR", "message": "Yorumun metni yok; cevap taslağı elle yazılır."})
        name = src.product_names(engine, tenant, [cm.get("productId") or ""]).get(cm.get("productId") or "")
        msgs = call(O.review_messages, name, cm.get("puan"), cm["metin"], cm.get("baslik"))
        try:
            text = await run_in_threadpool(lambda: m.chat(msgs, max_tokens=500, temperature=0.3))
        except Exception as e:  # noqa: BLE001
            raise HTTPException(503, detail={"code": "OKUR", "message": f"Zeki AI cevap vermedi ({str(e)[:160]})."}) from e
        text = O.clean_model_text(text)
        if not text:
            raise HTTPException(503, detail={"code": "OKUR", "message": "Zeki AI boş taslak döndürdü; yeniden deneyin."})
        out = call(O.set_review, engine, tenant, user, cid, cm.get("productId"), "taslak", text, "zeki")
        audit(engine, user, "run", "okur_review", cid, name or cm.get("productId"), {"is": "yorum cevap taslağı", "puan": cm.get("puan")})
        return out

    @app.post(P + "/reviews/{cid}/mark")
    def okur_review_mark(cid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        durum = str(body.get("durum") or "")
        taslak = body.get("taslak")
        out = call(O.set_review, engine, tenant, user, cid, body.get("productId"), durum,
                   str(taslak) if isinstance(taslak, str) else None, "elle" if isinstance(taslak, str) else None)
        audit(engine, user, "update", "okur_review", cid, None, {"durum": durum, "taslakDegisti": isinstance(taslak, str)})
        return out

    # ------------------------------------------------------------------ zamanlayıcı

    @app.post(P + "/run-due")
    def okur_run_due(request: Request) -> dict[str, Any]:
        """Gece turu (yalnız sayı): anlık görüntü, segment ölçümü, süre, çağrışım sınıflaması, yorum ve program özeti."""
        require_caller(request)
        from semantic_bridge.budget_api import _send_mail

        r = rt()
        engine, tenant = r.store.engine, r.settings.tenant_id
        O.ensure(engine)
        admin_mod.ensure(engine)
        cfg = O.settings()
        day = O.today().isoformat()
        out: dict[str, Any] = {"tarih": day}
        c = core()
        consent_now = None
        if c is None:
            out["cekirdek"] = src.NOT_CONNECTED
        else:
            try:
                inv = c.inventory(tenant)
                cons = c.consent(tenant)
                out["anlikGoruntu"] = O.save_snapshot(engine, tenant, inv, cons, day)
                consent_now = sum(x["sayi"] for x in cons)
            except (src.SourceError, src.CoreUnavailable) as e:
                out["anlikGoruntu"] = {"hata": str(e)}
            measured, failed = 0, []
            for s in O.measurable_segments(engine, tenant):
                try:
                    O.record_size(engine, tenant, s["id"], c.size(tenant, s["kural"]), day)
                    measured += 1
                except (src.SourceError, src.CoreUnavailable, O.OkurError) as e:
                    failed.append({"segment": s["ad"], "hata": str(e)[:200]})
            out["segmentOlcumu"] = {"olculen": measured, "hata": failed}
            choose = chooser(batch=True)
            if choose is not None:
                try:
                    out["ilgiAlani"] = O.classify_missing(engine, tenant, c.interests(tenant), choose)
                except (src.SourceError, src.CoreUnavailable) as e:
                    out["ilgiAlani"] = {"hata": str(e)}
            else:
                out["ilgiAlani"] = "model yok"
        expired = O.expire_segments(engine, tenant)
        out["suresiDolan"] = len(expired)

        new_reviews, unanswered = 0, None
        try:
            items = _reviews(engine, tenant, fresh=True)
            open_ids = sorted(x["id"] for x in items if x["durum"] == "cevapsiz")
            known = set(O.meta_get(engine, tenant, "cevapsiz_yorumlar", []) or [])
            new_reviews = len([i for i in open_ids if i not in known]) if known or O.meta_get(engine, tenant, "yorum_ozet") else 0
            unanswered = len(open_ids)
            O.meta_set(engine, tenant, "cevapsiz_yorumlar", open_ids)
            O.meta_set(engine, tenant, "yorum_ozet", {**O.review_counts(items), "zaman": O._iso(O._now())})
            out["yorum"] = {"cevapsiz": unanswered, "yeni": new_reviews}
        except src.SourceError as e:
            out["yorum"] = {"hata": str(e)}

        progs = [p for p in O.due_programs(engine, tenant, cfg["programRemindDays"])]
        sent_keys = set(O.meta_get(engine, tenant, "program_hatirlatma", []) or [])
        remind = [p for p in progs if f"{p['id']}:{p['tarih']}" not in sent_keys]
        pending = O.pending_segments(engine, tenant)
        before = O.consent_previous(engine, tenant, day)
        increased = consent_now is not None and before is not None and consent_now > before
        recipients = [x.strip() for x in (admin_mod.conf("OKUR_ALERT_RECIPIENTS") or "").replace(";", ",").split(",") if "@" in x]
        mail = "bos"
        if pending or increased or new_reviews or remind or expired:
            if recipients:
                link = (admin_mod.conf("ALERT_LINK") or "").split("/uyarilar")[0]
                link = f"{link}/okur-toplulugu" if link else ""
                mail = _send_mail("Okur topluluğu: günlük özet", O.summary_text(pending, consent_now, before, new_reviews, unanswered,
                                                                               remind, expired, link), recipients)
                if mail == "sent" and remind:
                    O.meta_set(engine, tenant, "program_hatirlatma", sorted(sent_keys | {f"{p['id']}:{p['tarih']}" for p in remind}))
            else:
                mail = "alici_yok"
        out.update({"onayBekleyen": len(pending), "izinArtti": increased, "programHatirlatma": len(remind), "eposta": mail,
                    "alici": len(recipients)})
        return out

    return comments
