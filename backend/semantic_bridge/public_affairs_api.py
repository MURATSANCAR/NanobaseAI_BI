"""M28 Kurumsal ilişkiler uçları: /api/v1/public-affairs/*.

Sayfa kapısı `access.RULES` (`sayfa:kurumsal-iliskiler`, «Herkes» rolüne açık değil — kişi kartları hassas). Yazma uçları
`ozellik:iliskiler.duzenle` (`FEATURE_RULES`); hediye/bütçe/teklif onayı ve alan listesi açıkça verilen
`ozellik:iliskiler.onay` ile, başkasının «yalnız ben ve katılımcılar» notunu okumak açıkça verilen
`ozellik:iliskiler.hassas` ile burada denetlenir. Belge ve rapor PDF'i `ozellik:veri.disa-aktar`. Zamanlayıcı
(`timas-public-affairs.timer`) yalnız `POST /api/v1/public-affairs/run-due`'yu çağırır.

Dış gönderim yok (kullanıcı kararı 2026-09-28): kişiye e-posta/mesaj gitmez; teklif dosyası indirilir, kuruma sorumlu
verir. E-posta yalnız iç haftalık özettir (`REL_ALERT_RECIPIENTS`; boşsa gitmez). CRM'e yazma yok.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import date, datetime
from typing import Any, Callable, Optional

import sqlalchemy as sa
from fastapi import HTTPException, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from semantic_bridge import pazarlama_kaynak as PK
from semantic_bridge import provenance as PV
from semantic_bridge import public_affairs as PA
from semantic_bridge import public_affairs_kaynak as K
from semantic_bridge import public_affairs_docs as D
from semantic_bridge import public_affairs_sources as src
from semantic_bridge import relations_core as core

log = logging.getLogger("semantic.public_affairs.api")
P = "/api/v1/public-affairs"
TTL = 600.0

FIELD_PROMPT = """Bir yayınevinin kurumsal ilişkiler defterinde kişiler alanlarına göre gruplanıyor. Aşağıdaki kişinin
mesleki bilgisine göre en uygun alan hangisi? Yalnız kişinin işine ve kurumuna bak; inanç, siyasi görüş ya da köken
hakkında çıkarım yapma. Emin değilsen «Diğer»i seç.
Unvan / görev: {title}
Kurum: {org}
CRM uzmanlık alanları: {tags}"""

NOTE_PROMPT = """Bir yayınevinin kurumsal ilişkiler sorumlusu adına, hediye gönderilen kitabın içine konacak kısa ve kişisel bir
not yaz. Türkçe, sıcak ama ölçülü; en çok 3 cümle. Hitapla başla («Sayın …»), imza yazma.
KESİNLİKLE rakam, tarih, satış bilgisi, ödül ya da «en çok satan» gibi kanıtsız övgü yazma. Kitap hakkında aşağıda
olmayan bilgi uydurma. Kişinin inancı, siyasi görüşü ya da özel hayatı hakkında bir şey yazma.
Kişi: {name}{title}
Kişinin alanı ve ilgi alanları: {interests}
Kitap: {book}{author}
Kitabın arka kapak metninden: {summary}
Gönderme gerekçesi: {reason}
Not:"""


def register(app: Any, deps: dict[str, Any]) -> dict[str, Any]:
    """app.py'de bağlanır. `deps`: auth(request) → (engine, tenant, user, display) · require_caller(request) · can(user, key) ·
    is_admin(user) · audit(engine, user, action, kind, id, title, detail) · conf(key, default) · engine() · tenant() ·
    crm_file() · llm(priority) → LLM kapısı istemcisi ya da None."""
    auth, require_caller, can, is_admin, audit, conf = (deps[k] for k in ("auth", "require_caller", "can", "is_admin", "audit", "conf"))
    settings = lambda: PA.settings_from(conf)  # noqa: E731
    schema = lambda: conf("CRM_SCHEMA", "Timas_MSCRM.dbo")  # noqa: E731
    cache: dict[str, tuple[float, Any]] = {}
    jobs: dict[str, threading.Thread] = {}

    def ctx(request: Request) -> tuple[Any, str, str, str]:
        engine, tenant, user, display = auth(request)
        PA.ensure(engine)
        return engine, tenant, user, display

    def rights(user: str) -> dict[str, bool]:
        admin = bool(is_admin(user))
        return {"admin": admin, "edit": admin or can(user, "ozellik:iliskiler.duzenle"),
                "approve": admin or can(user, "ozellik:iliskiler.onay"),
                "sensitive": admin or can(user, "ozellik:iliskiler.hassas"),
                "export": admin or can(user, "ozellik:veri.disa-aktar")}

    def need(ok: bool, what: str) -> None:
        if not ok:
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": f"Bu işlem için «{what}» yetkisi gerekli."})

    def call(fn: Callable[..., Any], *a: Any, **kw: Any) -> Any:
        try:
            return fn(*a, **kw)
        except core.RelationError as e:
            raise HTTPException(status_code=e.status, detail={"code": "FORBIDDEN" if e.status == 403 else "RELATIONS",
                                                              "message": str(e), **e.extra}) from e
        except src.SourceError as e:
            raise HTTPException(status_code=503, detail={"code": "RELATIONS_SOURCE", "retryable": True, "message": str(e)}) from e

    def crm() -> Callable[[str], list[dict[str, Any]]]:
        run = src.runner(deps["crm_file"]())
        return lambda sql: src.lower_rows(run(sql))

    def cached(key: str, fn: Callable[[], Any], fresh: bool = False) -> Any:
        hit = cache.get(key)
        if hit and not fresh and time.time() - hit[0] < TTL:
            return hit[1]
        val = fn()
        cache[key] = (time.time(), val)
        return val

    def status_labels() -> dict[int, str]:
        def read() -> dict[int, str]:
            out: dict[int, str] = {}
            for r in crm()(src.order_status_labels_sql(schema())):
                code = src.ival(r.get("code"))
                if code is not None:
                    out[code] = src.s(r.get("label")) or str(code)
            return out
        try:
            return cached("labels", read)
        except Exception as e:  # noqa: BLE001 — etiket okunamazsa kod gösterilir
            log.info("public_affairs: sipariş durum etiketleri okunamadı: %s", e)
            return {}

    def csv_or_pdf(data: bytes, name: str, mime: str) -> Response:
        return Response(data, media_type=mime, headers={"Content-Disposition": f'attachment; filename="{name}"'})

    def contact_view(r: dict[str, Any]) -> dict[str, Any]:
        return {"crmContactId": src.lid(r.get("id")), "name": src.s(r.get("ad")), "title": src.s(r.get("is_unvani")),
                "role": src.ival(r.get("rol")), "roleLabel": src.ROLE.get(src.ival(r.get("rol")) or 0),
                "crmAccountId": src.lid(r.get("kurum_id")), "orgName": src.s(r.get("kurum")),
                "orgRole": src.KURUM_ROLU.get(src.ival(r.get("kurum_rolu")) or 0), "city": src.s(r.get("il")),
                "unvan": src.s(r.get("unvan")), "academicTitle": src.s(r.get("akademik_titr")),
                "profession": src.s(r.get("meslek")), "email": src.s(r.get("eposta")), "phone": src.s(r.get("telefon"))}

    def place_view(r: dict[str, Any]) -> dict[str, Any]:
        kt = src.ival(r.get("kurum_tipi"))
        return {"id": src.lid(r.get("id")), "name": src.s(r.get("ad")), "kurumTipi": kt, "kurumTipiLabel": src.KURUM_TIPI.get(kt or 0),
                "kurumTuru": src.KURUM_TURU.get(src.ival(r.get("kurum_turu")) or 0), "students": src.ival(r.get("ogrenci")),
                "teachers": src.ival(r.get("ogretmen")), "books": src.ival(r.get("kitap_sayisi")),
                "totalStudents": src.ival(r.get("toplam_ogrenci")), "cityId": src.lid(r.get("il_id")), "city": src.s(r.get("il")),
                "district": src.s(r.get("ilce")), "phone": src.s(r.get("telefon"))}

    def book_view(r: dict[str, Any]) -> dict[str, Any]:
        return {"id": src.lid(r.get("id")), "name": src.s(r.get("ad")), "stockCode": src.s(r.get("stok_kodu")),
                "genres": src.s(r.get("turler")), "categories": src.s(r.get("kategoriler")),
                "audience": src.HEDEF_KITLE.get(src.ival(r.get("hedef_kitle")) or 0), "ages": src.s(r.get("yaslar")),
                "ageFrom": src.ival(r.get("yas_bas")), "ageTo": src.ival(r.get("yas_bit")),
                "firstPrint": core.crm_day(r.get("ilk_baski")).isoformat() if core.crm_day(r.get("ilk_baski")) else None,
                "author": src.s(r.get("yazar"))}

    def crm_tags(ids: list[str]) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        if not ids:
            return out
        for r in crm()(src.contact_tags_sql(schema(), ids)):
            k = src.lid(r.get("kisi")) or ""
            out.setdefault(k, []).append(src.s(r.get("ad")) or "")
        return out

    # ------------------------------------------------------------------ genel

    @app.get(f"{P}/meta")
    def pa_meta(request: Request) -> dict[str, Any]:
        engine, tenant, user, display = ctx(request)
        st = settings()
        r = rights(user)
        pairs = lambda d: [{"key": k, "label": v} for k, v in d.items()]  # noqa: E731
        return {"fields": PA.list_fields(engine, tenant), "orgKinds": pairs(PA.ORG_KINDS), "priorities": pairs(PA.PRIORITIES),
                "giftStatus": pairs(PA.GIFT_STATUS), "projectKinds": pairs(PA.PROJECT_KINDS), "stages": pairs(PA.STAGES),
                "openStages": list(PA.OPEN_STAGES), "proposalStatus": pairs(PA.PROPOSAL_STATUS),
                "channels": pairs(core.CHANNELS), "tones": pairs(core.TONES), "visibility": pairs(PA.VISIBILITY),
                "kurumTipi": [{"key": k, "label": v} for k, v in src.KURUM_TIPI.items()],
                "roles": [{"key": k, "label": v} for k, v in src.ROLE.items()], "heat": core.heat_meta(),
                "settings": {k: st[k] for k in ("contactDays", "criticalDays", "giftGapDays", "orderTypes")},
                "month": PA.month_of(),
                "me": {"username": user, "display": display, "admin": r["admin"], "canEdit": r["edit"], "canApprove": r["approve"],
                       "canSensitive": r["sensitive"], "canExport": r["export"]}}

    @app.get(f"{P}/home")
    def pa_home(request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        return PV.bagla(call(PA.home, engine, tenant, user, settings()), lambda: K.for_home(engine, tenant))

    @app.post(f"{P}/run-due")
    async def pa_run_due(request: Request, weekly: bool = False) -> dict[str, Any]:
        """Zamanlayıcı: her gün hediye satırlarının CRM sipariş durumu; `weekly=1` ise iç haftalık özet e-postası."""
        require_caller(request)
        engine, tenant, st = deps["engine"](), deps["tenant"](), settings()
        PA.ensure(engine)
        out: dict[str, Any] = {}
        try:
            out["orders"] = await run_in_threadpool(lambda: PA.sync_orders(engine, tenant, crm(), schema(), st, status_labels()))
        except Exception as e:  # noqa: BLE001 — CRM kapalıysa özet yine hazırlanır
            log.warning("public_affairs run-due: CRM okunamadı: %s", e)
            out["orders"] = {"error": str(e)[:300]}
        if weekly:
            d = await run_in_threadpool(PA.digest, engine, tenant, st)
            from semantic_bridge.corporate_sales_api import send_mail

            link = (conf("ALERT_LINK", "") or "").split("/uyarilar")[0]
            text = d["text"] + (f"\n\nEkran: {link}/kurumsal-iliskiler\n" if link else "\n")
            out["digest"] = {k: d[k] for k in ("due", "projects", "waiting")}
            out["mail"] = send_mail("Kurumsal ilişkiler: haftalık özet", text, st["alertTo"]) if (d["due"] or d["projects"] or d["waiting"]) else "bos"
        return out

    # ------------------------------------------------------------------ alanlar (KVKK sınırlı sabit liste)

    @app.get(f"{P}/fields")
    def pa_fields(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return {"items": PA.list_fields(engine, tenant)}

    @app.post(f"{P}/fields")
    def pa_field_add(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(rights(user)["approve"], "Kurumsal ilişkiler onayı")
        out = call(PA.add_field, engine, tenant, user, body, settings()["bannedExtra"])
        audit(engine, user, "create", "rel_field", out["key"], out["label"], None)
        return out

    @app.patch(f"{P}/fields/{{key}}")
    def pa_field_update(key: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(rights(user)["approve"], "Kurumsal ilişkiler onayı")
        out = call(PA.update_field, engine, tenant, user, key, body, settings()["bannedExtra"])
        audit(engine, user, "update", "rel_field", key, out["label"], {k: body.get(k) for k in ("label", "active") if k in body})
        return out

    @app.get(f"{P}/kvkk-scan")
    def pa_kvkk_scan(request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(rights(user)["approve"], "Kurumsal ilişkiler onayı")
        return PA.kvkk_scan(engine, tenant, settings()["bannedExtra"])

    # ------------------------------------------------------------------ kişiler

    @app.get(f"{P}/people")
    def pa_people(request: Request, q: str = "", field: str = "", priority: str = "", scope: str = "", org: str = "",
                  archived: bool = False, order: str = "zaman") -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(PA.list_people, engine, tenant, user, settings(), q=q, field=field, priority=priority, scope=scope,
                   org_id=org, archived=archived, order=order)
        return PV.bagla(out, lambda: K.for_people(engine, tenant, archived))

    @app.post(f"{P}/people")
    async def pa_person_add(body: dict[str, Any], request: Request) -> dict[str, Any]:
        """Yeni kart. `fromCrm: true` + `crmContactId` ise ad, unvan, kurum, il ve iş iletişimi CRM'den okunur."""
        engine, tenant, user, _ = ctx(request)
        st = settings()
        if body.get("fromCrm") and body.get("crmContactId"):
            cid = call(core.guid, body["crmContactId"])
            rows = await run_in_threadpool(lambda: call(lambda: crm()(src.contact_sql(schema(), cid))))
            if not rows:
                raise HTTPException(status_code=404, detail={"code": "RELATIONS", "message": "CRM kişisi bulunamadı."})
            c = contact_view(rows[0])
            c["title"] = c["title"] or c.get("unvan") or c.get("academicTitle") or c.get("profession")
            out, created = call(PA.person_for_crm, engine, tenant, user, c)
            extra = {k: body[k] for k in ("fieldKey", "priority", "isPublicOfficial", "interests", "owner", "ownerDisplay", "orgId") if k in body}
            if extra and created:
                out, _ = call(PA.update_person, engine, tenant, user, True, out["id"], extra, st["bannedExtra"])
            if created:
                audit(engine, user, "create", "rel_person", out["id"], out["name"], {"crm": cid})
            return dict(out, created=created)
        out = call(PA.create_person, engine, tenant, user, body, st["bannedExtra"])
        audit(engine, user, "create", "rel_person", out["id"], out["name"], None)
        return dict(out, created=True)

    @app.get(f"{P}/people/{{pid}}")
    async def pa_person(pid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        r = rights(user)
        out = call(PA.person_detail, engine, tenant, user, r["sensitive"], pid, settings())
        out["crm"] = None
        if out.get("crmContactId"):
            def read() -> dict[str, Any]:
                run = crm()
                rows = run(src.contact_sql(schema(), out["crmContactId"]))
                tags = crm_tags([out["crmContactId"]]).get(out["crmContactId"], [])
                return {"contact": contact_view(rows[0]) if rows else None, "tags": tags}
            try:
                out["crm"] = await run_in_threadpool(read)
            except Exception as e:  # noqa: BLE001 — CRM kapalıyken kart yine açılır
                out["crm"] = {"error": "CRM şu an okunamıyor; kart portal kaydıyla gösteriliyor.", "detail": str(e)[:200]}
        return PV.bagla(out, lambda: K.for_person(engine, tenant, out["id"], out.get("crmContactId")))

    @app.patch(f"{P}/people/{{pid}}")
    def pa_person_update(pid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        r = rights(user)
        out, diff = call(PA.update_person, engine, tenant, user, r["admin"], pid, body, settings()["bannedExtra"])
        if diff:
            audit(engine, user, "update", "rel_person", out["id"], out["name"], {k: v for k, v in diff.items() if k not in ("email", "phone")})
        return out

    @app.post(f"{P}/people/{{pid}}/notes")
    def pa_person_note(pid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, display = ctx(request)
        r = rights(user)
        out = call(PA.create_note, engine, tenant, user, display, r["sensitive"], dict(body, personId=pid))
        audit(engine, user, "create", "rel_note", out["id"], out["topic"] if not out["hidden"] else "Gizli not",
              {"person": pid, "channel": out["channel"], "private": out["visibility"] == "ozel"})
        return out

    @app.post(f"{P}/people/{{pid}}/suggest-field")
    async def pa_suggest_field(pid: str, request: Request) -> dict[str, Any]:
        """Zeki AI alan önerisi: onaylı alan listesinden tek seçim (olasılıkla). Karta yazmaz; kullanıcı onaylayıp kaydeder."""
        engine, tenant, user, _ = ctx(request)
        st = settings()
        person = call(PA.person_detail, engine, tenant, user, False, pid, st)
        fields = [f for f in PA.list_fields(engine, tenant, active_only=True)]
        if not fields:
            raise HTTPException(status_code=422, detail={"code": "RELATIONS", "message": "Etkin alan yok."})
        tags: list[str] = []
        if person.get("crmContactId"):
            try:
                tags = await run_in_threadpool(lambda: crm_tags([person["crmContactId"]]).get(person["crmContactId"], []))
            except Exception:  # noqa: BLE001
                tags = []
        if not (person.get("title") or person.get("orgName") or tags):
            return {"fieldKey": None, "reason": "Unvan, kurum ya da uzmanlık alanı yok; öneri için bilgi yetersiz."}
        llm = None
        try:
            llm = deps["llm"](None)
        except Exception as e:  # noqa: BLE001
            log.info("public_affairs: model yok: %s", e)
        if llm is None or not hasattr(llm, "choose"):
            return {"fieldKey": None, "reason": "Zeki AI şu an kullanılamıyor."}
        labels = [f["label"] for f in fields]
        prompt = FIELD_PROMPT.format(title=person.get("title") or "-", org=person.get("orgName") or "-", tags=", ".join(tags) or "-")
        try:
            res = await run_in_threadpool(llm.choose, prompt, labels)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=503, detail={"code": "RELATIONS_MODEL", "retryable": True,
                                                         "message": "Zeki AI şu an cevap veremedi; biraz sonra yeniden deneyin."}) from e
        key = next((f["key"] for f in fields if f["label"] == res.choice), None)
        sure = bool(res.confident(st["llmMinProb"], min_margin=st["llmMinMargin"])) and key is not None
        return {"fieldKey": key if sure else None, "candidate": key, "probability": res.probability, "margin": res.margin,
                "sure": sure, "reason": None if sure else "Zeki AI emin değil; alanı siz seçin."}

    @app.patch(f"{P}/notes/{{nid}}")
    def pa_note_update(nid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        r = rights(user)
        out, diff = call(PA.update_note, engine, tenant, user, r["sensitive"], nid, body)
        if diff:
            audit(engine, user, "update", "rel_note", out["id"], out["topic"] if not out["hidden"] else "Gizli not", diff)
        return out

    @app.delete(f"{P}/notes/{{nid}}")
    def pa_note_delete(nid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        r = rights(user)
        out = call(PA.delete_note, engine, tenant, user, r["sensitive"], nid)
        audit(engine, user, "delete", "rel_note", out["id"], None, {"person": out["personId"], "org": out["orgId"]})
        return {"ok": True, **out}

    # ------------------------------------------------------------------ kurumlar

    @app.get(f"{P}/orgs")
    def pa_orgs(request: Request, q: str = "", kind: str = "", archived: bool = False) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        oq, pq, jq = PA.orgs_list_stmts(tenant, archived)
        with engine.connect() as c:
            rows = c.execute(oq).fetchall()
            people = {r.org_id: int(r.n) for r in c.execute(pq).fetchall()}
            projects = {r.org_id: int(r.n) for r in c.execute(jq).fetchall()}
        nq = core.norm(q)
        items = [dict(PA._org(r), people=people.get(r.id, 0), openProjects=projects.get(r.id, 0)) for r in rows
                 if (not kind or r.kind == kind) and (not nq or nq in core.norm(f"{r.name} {r.city or ''}"))]
        items.sort(key=lambda x: x["name"].casefold())
        return PV.bagla({"items": items, "total": len(items)}, lambda: K.for_orgs(engine, tenant, archived))

    @app.post(f"{P}/orgs")
    async def pa_org_add(body: dict[str, Any], request: Request) -> dict[str, Any]:
        """Yeni kurum kartı. `fromCrm: true` + `crmVisitPlaceId` ise ad, tip ve il CRM ziyaret yerinden okunur."""
        engine, tenant, user, _ = ctx(request)
        if body.get("fromCrm") and body.get("crmVisitPlaceId"):
            pid = call(core.guid, body["crmVisitPlaceId"], "CRM ziyaret yeri")
            rows = await run_in_threadpool(lambda: call(lambda: crm()(src.places_by_id_sql(schema(), [pid]))))
            if not rows:
                raise HTTPException(status_code=404, detail={"code": "RELATIONS", "message": "CRM ziyaret yeri bulunamadı."})
            pv = place_view(rows[0])
            out, created = call(PA.org_for_place, engine, tenant, user, pv)
            if created:
                audit(engine, user, "create", "rel_org", out["id"], out["name"], {"crm": pid})
            return dict(out, created=created)
        out = call(PA.create_org, engine, tenant, user, body)
        audit(engine, user, "create", "rel_org", out["id"], out["name"], None)
        return dict(out, created=True)

    @app.get(f"{P}/orgs/{{oid}}")
    async def pa_org(oid: str, request: Request) -> dict[str, Any]:
        """Kurum kartı: CRM ziyaret yeri istatistiği (öğrenci, öğretmen, kitap sayısı), kişiler, projeler, notlar."""
        engine, tenant, user, _ = ctx(request)
        r = rights(user)
        with engine.connect() as c:
            row = call(PA._get_org, c, tenant, oid)
            notes = c.execute(PA.org_notes_stmt(tenant, row.id)).fetchall()
        out = PA._org(row)
        out["people"] = PA.list_people(engine, tenant, user, settings(), org_id=row.id, order="ad")["items"]
        out["projects"] = PA.list_projects(engine, tenant, user, org_id=row.id, closed=True)["items"]
        out["timeline"] = [PA._note(n, user, r["sensitive"]) for n in notes]
        out["crm"] = None
        if row.crm_visit_place_id:
            try:
                rows = await run_in_threadpool(lambda: crm()(src.places_by_id_sql(schema(), [row.crm_visit_place_id])))
                out["crm"] = {"place": place_view(rows[0]) if rows else None}
            except Exception as e:  # noqa: BLE001
                out["crm"] = {"error": "CRM şu an okunamıyor.", "detail": str(e)[:200]}
        return PV.bagla(out, lambda: K.for_org(engine, tenant, row.id, row.crm_visit_place_id))

    @app.patch(f"{P}/orgs/{{oid}}")
    def pa_org_update(oid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out, diff = call(PA.update_org, engine, tenant, user, rights(user)["admin"], oid, body)
        if diff:
            audit(engine, user, "update", "rel_org", out["id"], out["name"], diff)
        return out

    @app.post(f"{P}/orgs/{{oid}}/notes")
    def pa_org_note(oid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, display = ctx(request)
        r = rights(user)
        out = call(PA.create_note, engine, tenant, user, display, r["sensitive"], dict({k: v for k, v in body.items() if k != "personId"}, orgId=oid))
        audit(engine, user, "create", "rel_note", out["id"], out["topic"] if not out["hidden"] else "Gizli not",
              {"org": oid, "channel": out["channel"], "private": out["visibility"] == "ozel"})
        return out

    # ------------------------------------------------------------------ CRM okuma (bağlama ve istatistik)

    @app.get(f"{P}/crm/contacts")
    async def pa_crm_contacts(request: Request, q: str = "", role: Optional[int] = None, page: int = 0) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        rows = await run_in_threadpool(lambda: call(lambda: crm()(src.contacts_sql(schema(), q, role, page))))
        items = [contact_view(r) for r in rows]
        ids = [i["crmContactId"] for i in items if i["crmContactId"]]
        linked = {}
        if ids:
            with engine.connect() as c:
                linked = {r.crm_contact_id: r.id for r in c.execute(sa.select(PA.PEOPLE.c.id, PA.PEOPLE.c.crm_contact_id).where(
                    PA.PEOPLE.c.tenant_id == tenant, PA.PEOPLE.c.crm_contact_id.in_(ids))).fetchall()}
        for i in items:
            i["personId"] = linked.get(i["crmContactId"])
        return PV.bagla({"items": items, "total": src.ival(rows[0].get("toplam")) if rows else 0, "page": max(0, page),
                         "pageSize": src.PAGE_SIZE}, lambda: K.for_crm_contacts(q, role, page))

    @app.get(f"{P}/crm/places")
    async def pa_crm_places(request: Request, q: str = "", kurumTipi: Optional[int] = None, il: str = "", page: int = 0) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        rows = await run_in_threadpool(lambda: call(lambda: crm()(src.places_sql(schema(), q, kurumTipi, il, page))))
        items = [place_view(r) for r in rows]
        ids = [i["id"] for i in items if i["id"]]
        linked = {}
        if ids:
            with engine.connect() as c:
                linked = {r.crm_visit_place_id: r.id for r in c.execute(sa.select(PA.ORGS.c.id, PA.ORGS.c.crm_visit_place_id).where(
                    PA.ORGS.c.tenant_id == tenant, PA.ORGS.c.crm_visit_place_id.in_(ids))).fetchall()}
        for i in items:
            i["orgId"] = linked.get(i["id"])
        return PV.bagla({"items": items, "total": src.ival(rows[0].get("toplam")) if rows else 0, "page": max(0, page),
                         "pageSize": src.PAGE_SIZE}, lambda: K.for_crm_places(q, kurumTipi, il, page))

    @app.get(f"{P}/crm/cities")
    async def pa_crm_cities(request: Request) -> dict[str, Any]:
        ctx(request)
        rows = await run_in_threadpool(lambda: call(cached, "cities", lambda: crm()(src.cities_sql(schema()))))
        return {"items": [{"id": src.lid(r.get("id")), "name": src.s(r.get("ad"))} for r in rows]}

    @app.get(f"{P}/crm/city-stats")
    async def pa_crm_city_stats(request: Request, il: str, kurumTipi: int = 1) -> dict[str, Any]:
        """Seçilen ilde kurum tipi başına kurum sayısı ve öğrenci toplamı; öğrenci sayısı yazılmamış kurum ayrıca."""
        ctx(request)
        rows = await run_in_threadpool(lambda: call(lambda: crm()(src.city_stats_sql(schema(), il, kurumTipi))))
        r = rows[0] if rows else {}
        out = {"il": il, "kurumTipi": kurumTipi, "kurumTipiLabel": src.KURUM_TIPI.get(kurumTipi), "places": src.ival(r.get("kurum")) or 0,
               "students": src.ival(r.get("ogrenci")) or 0, "studentsUnknown": src.ival(r.get("sayisiz")) or 0}
        return PV.bagla(out, lambda: K.for_city_stats(il, kurumTipi))

    @app.get(f"{P}/crm/roles")
    async def pa_crm_roles(request: Request) -> dict[str, Any]:
        """CRM kişi rolleri ve kullanım sayısı; «Karar Veren» rolündeki etkin kişi sayısı (kabul 4)."""
        ctx(request)

        def read() -> dict[str, Any]:
            run = crm()
            roles = [{"id": src.lid(r.get("id")), "name": src.s(r.get("ad")), "people": src.ival(r.get("kisi")) or 0}
                     for r in run(src.person_roles_sql(schema()))]
            n = run(src.decision_makers_sql(schema()))
            return {"personRoles": roles, "decisionMakers": src.ival(n[0].get("n")) if n else 0}
        return PV.bagla(await run_in_threadpool(lambda: call(cached, "roles", read)), K.for_roles)

    @app.get(f"{P}/crm/books")
    async def pa_crm_books(request: Request, q: str = "", page: int = 0, month: str = "") -> dict[str, Any]:
        """Kitap arama (ad/stok kodu, sayfalı) ya da `month=YYYY-AA` ile o ay ilk baskısı yapılan kitaplar (hepsi)."""
        ctx(request)
        if month:
            if not PA._MONTH.match(month):
                raise HTTPException(status_code=422, detail={"code": "RELATIONS", "message": "Ay YYYY-AA biçiminde olmalı."})
            y, m = (int(x) for x in month.split("-"))
            first, until = date(y, m, 1), date(y + (m == 12), m % 12 + 1, 1)
            rows = await run_in_threadpool(lambda: call(lambda: crm()(src.books_published_sql(schema(), first, until))))
            return PV.bagla({"items": [book_view(r) for r in rows], "total": len(rows), "page": 0, "pageSize": len(rows) or src.PAGE_SIZE},
                            lambda: K.for_crm_books(q, page, month))
        rows = await run_in_threadpool(lambda: call(lambda: crm()(src.books_sql(schema(), q, page))))
        return PV.bagla({"items": [book_view(r) for r in rows], "total": src.ival(rows[0].get("toplam")) if rows else 0,
                         "page": max(0, page), "pageSize": src.PAGE_SIZE}, lambda: K.for_crm_books(q, page, ""))

    # ------------------------------------------------------------------ hediye programı

    @app.get(f"{P}/gifts")
    def pa_gifts(request: Request, month: str = "", status: str = "", person: str = "") -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        out = call(PA.list_gifts, engine, tenant, month=month, status=status, person_id=person)
        return PV.bagla(out, lambda: K.for_gifts(engine, tenant, month, status, person))

    @app.post(f"{P}/gifts")
    def pa_gift_add(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(PA.add_gift, engine, tenant, user, body)
        audit(engine, user, "create", "rel_gift", out["id"], f"{out['personName']} · {out['bookName'] or out['crmBookId']}",
              {"month": out["month"]})
        return out

    @app.post(f"{P}/gifts/suggest")
    async def pa_gift_suggest(body: dict[str, Any], request: Request) -> dict[str, Any]:
        """Kitap(lar) → kime gönderelim: `bookIds` ya da `month` (o ay ilk baskısı yapılanlar). `all: true` örtüşmesi
        olmayan kişileri de puanıyla döndürür (elle seçim). Puan kuraldır, gerekçesi yazılır."""
        engine, tenant, user, _ = ctx(request)
        st = settings()
        ids = [call(core.guid, x, "CRM kitap kimliği") for x in (body.get("bookIds") or [])]
        month = str(body.get("month") or "")

        ran: list[dict[str, Any]] = []

        def read() -> dict[str, Any]:
            run = PK.recording(crm(), "crm", ran)
            if ids:
                books = run(src.books_by_id_sql(schema(), ids, summary=True))
            elif month and PA._MONTH.match(month):
                y, m = (int(x) for x in month.split("-"))
                books = run(src.books_published_sql(schema(), date(y, m, 1), date(y + (m == 12), m % 12 + 1, 1)))
                if books:
                    books = run(src.books_by_id_sql(schema(), [src.lid(b.get("id")) for b in books], summary=True))
            else:
                raise core.RelationError("Kitap seçin ya da ay verin.")
            for b in books:
                b["id"] = src.lid(b.get("id"))
                b["ozet"] = src.plain(b.get("ozet"))
                b["ad"], b["yazar"], b["stok_kodu"] = src.s(b.get("ad")), src.s(b.get("yazar")), src.s(b.get("stok_kodu"))
            people = PA.list_people(engine, tenant, user, st)["items"]
            linked = sorted({p["crmContactId"] for p in people if p.get("crmContactId")})
            tags: dict[str, list[str]] = {}
            if linked:
                for r in run(src.contact_tags_sql(schema(), linked)):
                    tags.setdefault(src.lid(r.get("kisi")) or "", []).append(src.s(r.get("ad")) or "")
            return {"books": books, "people": people, "tags": tags}

        data = await run_in_threadpool(lambda: call(read))
        items = PA.suggest(data["people"], data["books"], data["tags"], PA.gifts_by_person(engine, tenant), st,
                           include_all=bool(body.get("all")))
        out = {"items": items, "total": len(items),
               "books": [{"id": b["id"], "name": b.get("ad"), "author": b.get("yazar"), "stockCode": b.get("stok_kodu")} for b in data["books"]],
               "people": len(data["people"])}
        return PV.bagla(out, lambda: K.for_gift_suggest(engine, tenant, ran))

    @app.patch(f"{P}/gifts/{{gid}}")
    def pa_gift_update(gid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out, diff = call(PA.update_gift, engine, tenant, user, gid, body)
        if diff:
            audit(engine, user, "update", "rel_gift", out["id"], f"{out['personName']} · {out['bookName'] or ''}", diff)
        return out

    @app.post(f"{P}/gifts/approve")
    def pa_gift_approve(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        r = rights(user)
        need(r["approve"], "Kurumsal ilişkiler onayı")
        out = call(PA.approve_gifts, engine, tenant, user, r["admin"], body)
        for gid in out["done"]:
            audit(engine, user, "approve" if (body.get("decision") or "onay") == "onay" else "reject", "rel_gift", gid, None,
                  {"legalOk": gid in set(body.get("legalOk") or [])})
        return out

    @app.post(f"{P}/gifts/{{gid}}/draft-note")
    async def pa_gift_note(gid: str, request: Request) -> dict[str, Any]:
        """Zeki AI kişisel not taslağı (kitabın CRM arka kapak metni + kişinin alanı/ilgi alanları; görüşme notları
        modele gitmez). Rakam içeren satır atılır. Taslak hediye satırına yazılır; kullanıcı düzeltir."""
        engine, tenant, user, _ = ctx(request)
        with engine.connect() as c:
            g = c.execute(sa.select(PA.GIFTS).where(PA.GIFTS.c.id == call(core.cid, gid, "Hediye"), PA.GIFTS.c.tenant_id == tenant)).first()
            if not g:
                raise HTTPException(status_code=404, detail={"code": "RELATIONS", "message": "Hediye satırı bulunamadı."})
            p = c.execute(sa.select(PA.PEOPLE).where(PA.PEOPLE.c.id == g.person_id)).first()
            fields = PA._field_keys(c, tenant)
        summary = None
        try:
            rows = await run_in_threadpool(lambda: crm()(src.books_by_id_sql(schema(), [g.crm_book_id], summary=True)))
            summary = src.plain(rows[0].get("ozet")) if rows else None
        except Exception as e:  # noqa: BLE001
            log.info("public_affairs: kitap özeti okunamadı: %s", e)
        llm = None
        try:
            llm = deps["llm"](None)
        except Exception as e:  # noqa: BLE001
            log.info("public_affairs: model yok: %s", e)
        if llm is None:
            raise HTTPException(status_code=503, detail={"code": "RELATIONS_MODEL", "message": "Zeki AI şu an kullanılamıyor."})
        interests = ", ".join([x for x in [fields.get(p.field_key or "")] + core.json_list(p.interests_json) if x]) or "-"
        prompt = NOTE_PROMPT.format(name=p.name, title=f" ({p.title})" if p.title else "", interests=interests,
                                    book=g.book_name or "kitap", author=f" — {g.author}" if g.author else "",
                                    summary=summary or "-", reason=g.reason or "-")
        try:
            text = await run_in_threadpool(lambda: llm.chat([{"role": "user", "content": prompt}], max_tokens=300, temperature=0.4))
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=503, detail={"code": "RELATIONS_MODEL", "retryable": True,
                                                         "message": "Zeki AI şu an cevap veremedi; biraz sonra yeniden deneyin."}) from e
        clean = PA.strip_numbers((text or "").strip())[:2000]
        if not clean:
            raise HTTPException(status_code=422, detail={"code": "RELATIONS_MODEL", "message": "Taslak kullanılamadı; notu elle yazın."})
        out, _ = call(PA.update_gift, engine, tenant, user, g.id, {"noteText": clean})
        audit(engine, user, "update", "rel_gift", g.id, "Kişisel not taslağı", {"model": True})
        return out

    # ------------------------------------------------------------------ projeler

    @app.get(f"{P}/projects")
    def pa_projects(request: Request, stage: str = "", kind: str = "", org: str = "", q: str = "", scope: str = "",
                    closed: bool = False) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(PA.list_projects, engine, tenant, user, stage=stage, kind=kind, org_id=org, q=q, scope=scope, closed=closed)
        return PV.bagla(out, lambda: K.for_projects(engine, tenant))

    @app.post(f"{P}/projects")
    def pa_project_add(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, display = ctx(request)
        out = call(PA.create_project, engine, tenant, user, display, body)
        audit(engine, user, "create", "rel_project", out["id"], out["title"], {"kind": out["kind"]})
        return out

    @app.get(f"{P}/projects/{{pid}}")
    def pa_project(pid: str, request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        out = call(PA.project_detail, engine, tenant, pid)
        return PV.bagla(out, lambda: K.for_project(engine, tenant, out["id"]))

    @app.patch(f"{P}/projects/{{pid}}")
    def pa_project_update(pid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, display = ctx(request)
        out, diff = call(PA.update_project, engine, tenant, user, display, pid, body)
        if diff:
            audit(engine, user, "update", "rel_project", out["id"], out["title"], diff)
        return call(PA.project_detail, engine, tenant, pid)

    @app.post(f"{P}/projects/{{pid}}/approve")
    def pa_project_approve(pid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        r = rights(user)
        need(r["approve"], "Kurumsal ilişkiler onayı")
        what, decision = str(body.get("what") or ""), str(body.get("decision") or "onay")
        out = call(PA.approve_project, engine, tenant, user, r["admin"], pid, what, decision)
        audit(engine, user, "approve" if decision == "onay" else "reject", "rel_project", pid, out["title"], {"what": what})
        return call(PA.project_detail, engine, tenant, pid)

    def project_crm(project: dict[str, Any], ran: Optional[list[dict[str, Any]]] = None) -> dict[str, Any]:
        """Projenin CRM tarafı: hedef kurumlar (ziyaret yeri satırları), kitap bilgisi, siparişlerle dağıtılan adet.
        `ran` verilirse çalışan sorguların metni oraya yazılır (sorgu bilgisi)."""
        run = crm() if ran is None else PK.recording(crm(), "crm", ran)
        places = run(src.places_by_id_sql(schema(), project["places"])) if project["places"] else []
        book_ids = [b["id"] for b in project["books"]]
        books = {src.lid(r.get("id")): r for r in run(src.books_by_id_sql(schema(), book_ids))} if book_ids else {}
        delivered = None
        missing: list[str] = []
        if project["orders"]:
            found = {str(r.get("no") or "").strip(): r for r in run(src.orders_by_no_sql(schema(), project["orders"]))}
            missing = [o for o in project["orders"] if o not in found]
            ids = [src.lid(r.get("id")) for r in found.values() if src.lid(r.get("id"))]
            delivered = sum(int(src.ival(r.get("adet")) or 0) for r in run(src.order_lines_sql(schema(), ids))) if ids else 0
        return {"places": places, "books": books, "delivered": delivered, "missingOrders": missing}

    @app.get(f"{P}/projects/{{pid}}/report")
    async def pa_project_report(pid: str, request: Request) -> dict[str, Any]:
        """Proje erişim raporu: CRM'den hedef kurum/öğrenci ve siparişlerle dağıtılan kitap; elle girilen katılım."""
        engine, tenant, _, _ = ctx(request)
        project = call(PA.project_detail, engine, tenant, pid)
        ran: list[dict[str, Any]] = []
        try:
            data = await run_in_threadpool(lambda: call(project_crm, project, ran))
        except HTTPException:
            raise
        except Exception as e:  # noqa: BLE001
            return {"project": project, "crmError": str(e)[:300], "facts": None, "places": []}
        facts = PA.reach_facts(project, data["places"], data["delivered"])
        out = {"project": project, "facts": facts, "places": [place_view(r) for r in data["places"]],
               "missingOrders": data["missingOrders"], "crmError": None}
        return PV.bagla(out, lambda: K.for_project_report(engine, tenant, project["id"], ran))

    def build_proposal(engine: Any, tenant: str, pid: str, user: str) -> None:
        """Arka plan işi: CRM bağlamı → Zeki AI bölümleri → koddan tablo ve dayanak maddeleriyle teklif dosyası."""
        try:
            st = settings()
            project = PA.project_detail(engine, tenant, pid)
            data = project_crm(project)
            org = None
            if project.get("orgId"):
                with engine.connect() as c:
                    org = PA._org(PA._get_org(c, tenant, project["orgId"]))
            books = []
            for b in project["books"]:
                r = data["books"].get(b["id"]) or {}
                books.append({"id": b["id"], "name": src.s(r.get("ad")) or b.get("name"), "stockCode": b.get("stockCode"),
                              "author": src.s(r.get("yazar")), "hedefKitle": src.HEDEF_KITLE.get(src.ival(r.get("hedef_kitle")) or 0),
                              "yaslar": src.s(r.get("yaslar")), "qty": b.get("qty")})
            llm = deps["llm"](None)
            if llm is None:
                raise RuntimeError("Zeki AI şu an kullanılamıyor.")
            prompt = PA.PROPOSAL_PROMPT.format(
                company=st["company"], org=org["name"] if org else "Kurum seçilmedi", org_kind=org["kindLabel"] if org else "-",
                title=project["title"], kind=project["kindLabel"], summary=(project.get("summary") or "-")[:2000],
                books="\n".join(f"- {b['name'] or b['stockCode'] or b['id']}" + (f" ({b['author']})" if b.get("author") else "") for b in books) or "-")
            text = llm.chat([{"role": "user", "content": prompt}], max_tokens=1200, temperature=0.3)
            facts = PA.reach_facts(project, data["places"], data["delivered"])
            doc = PA.proposal_document(project, org, text or "", facts, books, st["company"])
            PA.set_proposal(engine, tenant, pid, status="hazir", text=doc)
            audit(engine, user, "update", "rel_project", pid, project["title"], {"proposal": "taslak hazır"})
        except Exception as e:  # noqa: BLE001
            log.warning("public_affairs: teklif taslağı hazırlanamadı (%s): %s", pid, e)
            PA.set_proposal(engine, tenant, pid, status="hata", error=str(e)[:300])
        finally:
            jobs.pop(pid, None)

    @app.post(f"{P}/projects/{{pid}}/draft-proposal")
    def pa_project_proposal(pid: str, request: Request) -> dict[str, Any]:
        """Teklif dosyası taslağını arka planda hazırlar; ekran `proposalStatus`'u yoklar. Aynı proje için ikinci iş açılmaz."""
        engine, tenant, user, _ = ctx(request)
        started = call(PA.start_proposal, engine, tenant, pid, user)
        if started:
            t = threading.Thread(target=build_proposal, args=(engine, tenant, call(core.cid, pid, "Proje"), user),
                                 name=f"pa-proposal-{pid[:8]}", daemon=True)
            jobs[pid] = t
            t.start()
        return {"started": started, **call(PA.project_detail, engine, tenant, pid)}

    @app.get(f"{P}/projects/{{pid}}/proposal.pdf")
    def pa_project_proposal_pdf(pid: str, request: Request) -> Response:
        engine, tenant, user, _ = ctx(request)
        p = call(PA.project_detail, engine, tenant, pid)
        if not (p.get("proposalText") or "").strip():
            raise HTTPException(status_code=404, detail={"code": "RELATIONS", "message": "Teklif metni yok."})
        data = D.text_pdf(p["proposalText"], company=settings()["company"], title=p["title"], draft=not p.get("proposalApprovedBy"),
                          footer="Teklif dosyası; kurumla görüşmede kesinleşir.")
        audit(engine, user, "export", "rel_project", pid, p["title"], {"format": "pdf"})
        return csv_or_pdf(data, f"teklif-{pid[:8]}.pdf", "application/pdf")

    # ------------------------------------------------------------------ rapor

    def full_report(engine: Any, tenant: str, user: str, year: int) -> dict[str, Any]:
        st = settings()
        rep = PA.report(engine, tenant, user, st, year)
        try:
            def read() -> list[dict[str, Any]]:
                return crm()(src.promo_totals_sql(schema(), year, st["orderTypes"], st["excludedStatus"]))
            rows = cached(f"promo:{year}:{st['orderTypes']}:{st['excludedStatus']}", read)
            rep["crm"] = {"types": [{"type": src.ival(r.get("tip")), "label": src.ORDER_TYPE_LABELS.get(src.ival(r.get("tip")) or 0, str(r.get("tip"))),
                                     "orders": src.ival(r.get("siparis")) or 0, "books": src.ival(r.get("adet")) or 0} for r in rows],
                          "excludedStatus": st["excludedStatus"], "error": None}
        except Exception as e:  # noqa: BLE001
            rep["crm"] = {"types": [], "error": "CRM şu an okunamıyor.", "detail": str(e)[:200]}
        return rep

    @app.get(f"{P}/report")
    async def pa_report(request: Request, year: Optional[int] = None) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        y = year or datetime.now(core.TZ).year
        st = settings()
        rep = await run_in_threadpool(full_report, engine, tenant, user, y)
        return PV.bagla(rep, lambda: K.for_report(engine, tenant, y, st["orderTypes"], st["excludedStatus"]))

    @app.get(f"{P}/report/export.pdf")
    async def pa_report_pdf(request: Request, year: Optional[int] = None) -> Response:
        engine, tenant, user, _ = ctx(request)
        y = year or datetime.now(core.TZ).year
        rep = await run_in_threadpool(full_report, engine, tenant, user, y)
        data = D.text_pdf(D.report_text(rep), company=settings()["company"], title=f"Kurumsal ilişkiler {y}",
                          footer="Kaynak: portal kayıtları ve CRM (salt okuma).")
        audit(engine, user, "export", "rel_report", str(y), f"Kurumsal ilişkiler raporu {y}", {"format": "pdf"})
        return csv_or_pdf(data, f"kurumsal-iliskiler-{y}.pdf", "application/pdf")

    return {"jobs": jobs, "cache": cache}
