"""M17 Backlist uçları: /api/v1/marketing/backlist*.

Sayfa kapısı `access.RULES` (`sayfa:pazarlama-backlist`); plan açma, kitap listesi, içerik taslağı ve konu eşleşmesi
kararı `ozellik:pazarlama.plan-yaz` (M15 ile aynı anahtar), ekip ağırlığı `ozellik:pazarlama.backlist-ayar`, CSV
`ozellik:veri.disa-aktar` (`FEATURE_RULES`). Ciro, marj, hedef ciro ve kampanya cirosu `ozellik:pazarlama.butce-gor`
olmayan kişiye gitmez (bileşen yüzdeliği sıra bilgisidir, gider).

Plan onayı, bütçe satırı, takvim ve materyal onayı çekirdeğin uçlarıyla (`/api/v1/marketing/plans/*`); backlist planı
`kind='backlist'` olarak aynı onay akışından geçer.

Zamanlayıcı yalnız `POST /api/v1/marketing/backlist/run-due`'yu çağırır: `adim=gece` (04:00; liste, pazar günü geçmiş
yıllar ve konu eşleşmesi), `adim=bildirim` (08:00; aylık özet, özel gün hatırlatması, haftalık sapma, çapraz satış).
"""
from __future__ import annotations

import csv
import io
import logging
import threading
from datetime import timedelta
from typing import Any, Callable

import sqlalchemy as sa
from fastapi import HTTPException, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from semantic_bridge import budget as B
from semantic_bridge import pazarlama_kaynak as PK
from semantic_bridge import provenance as PV
from semantic_bridge.marketing import backlist as BL
from semantic_bridge.marketing import kaynak_backlist as K
from semantic_bridge.marketing import books as BK
from semantic_bridge.marketing import core as C
from semantic_bridge.marketing import plans as P
from semantic_bridge.marketing.sources import SourceError, crm_runner
from semantic_layer.runtime.llm_queue import BATCH, NORMAL

log = logging.getLogger("semantic.marketing.backlist.api")

R = "/api/v1/marketing/backlist"
F_WRITE = "ozellik:pazarlama.plan-yaz"
F_BUDGET = "ozellik:pazarlama.butce-gor"
F_APPROVE = "ozellik:pazarlama.plan-onay"
F_EDITORIAL = "ozellik:pazarlama.materyal-editoryal-onay"
F_TEAM = "ozellik:pazarlama.backlist-ayar"
F_EXPORT = "ozellik:veri.disa-aktar"
TEAM_WEIGHTS = "backlist-weights"


def hide_money(x: dict[str, Any]) -> dict[str, Any]:
    """Bütçe görme yetkisi olmayan kişi: ciro, marj, hedef ciro, açık tutar, kampanya cirosu boş."""
    x = {**x, "ciroSon12": None, "marj": None}
    if "bilesen" in x:
        x["bilesen"] = {**x["bilesen"], "marj": {**x["bilesen"]["marj"], "ham": None}}
    if "m46" in x:
        x["m46"] = {**x["m46"], "hedefCiro": None, "acikTutar": None}
    if "seri" in x:
        x["seri"] = [{**m, "ciro": None} for m in x["seri"]]
    if "kampanyalar" in x:
        x["kampanyalar"] = [{**k, "planlananCiro": None, "gerceklesenCiro": None} for k in x["kampanyalar"]]
    return x


def register(app, rt: Callable[[], Any], require_caller: Callable[[Request], None], can: Callable[[str, str], bool],
             base: dict[str, Any]) -> dict[str, Any]:
    from semantic_bridge import admin as admin_mod
    from semantic_bridge import board as board_mod
    from semantic_bridge.budget_api import _send_mail
    from semantic_bridge.marketing.api import _redact

    crm = base["crm"]
    pool = base["pool"]
    run_lock = threading.Lock()

    def st() -> dict[str, Any]:
        return BL.settings(admin_mod.conf)

    def mkt() -> dict[str, Any]:
        return P.settings(admin_mod.conf)

    def db() -> tuple[Any, str]:
        r = rt()
        BL.ensure(r.store.engine)
        admin_mod.ensure(r.store.engine)
        return r.store.engine, r.settings.tenant_id

    def ctx(request: Request) -> tuple[Any, str, str]:
        require_caller(request)
        try:
            user, _display = board_mod.session_of(request.headers.get("cookie", ""))
        except board_mod.NoUser:
            raise HTTPException(status_code=401, detail={"code": "UNAUTHORIZED", "message": "Oturum gerekli."}) from None
        engine, tenant = db()
        return engine, tenant, user

    def call(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except C.MarketingError as e:
            raise HTTPException(status_code=e.status, detail={"code": "MARKETING", "message": str(e)}) from e
        except SourceError as e:
            raise HTTPException(status_code=503, detail={"code": "MARKETING_SOURCE", "message": str(e)}) from e

    def need(user: str, key: str, what: str) -> None:
        if not can(user, key):
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": f"{what} rolünüzde yok."})

    def weights(engine, tenant: str, raw: str) -> dict[str, float]:
        if raw:
            return call(BL.parse_weights, raw)
        team = C.meta_get(engine, tenant, TEAM_WEIGHTS)
        try:
            return BL.parse_weights({k: v for k, v in team.items() if k in BL.KEYS}) if team else dict(BL.DEFAULT_WEIGHTS)
        except C.MarketingError:
            return dict(BL.DEFAULT_WEIGHTS)

    def sources() -> BL.Sources:
        return BL.Sources(lambda: rt().settings.connection_file, crm_runner, lambda: admin_mod.conf("CRM_SCHEMA") or "Timas_MSCRM.dbo")

    def link(path: str = "") -> str:
        b = (admin_mod.conf("ALERT_LINK") or "").split("/uyarilar")[0]
        return f"{b}/pazarlama/{path}" if b else ""

    def audit(engine, user: str, action: str, kind: str, oid: Any, label: Any, detail: Any = None) -> None:
        admin_mod.audit(engine, user, action, kind, oid, label, detail)

    # ------------------------------------------------------------------ okuma

    @app.get(R + "/meta")
    def bl_meta(request: Request) -> dict[str, Any]:
        engine, tenant, user = ctx(request)
        s = st()
        team = C.meta_get(engine, tenant, TEAM_WEIGHTS)
        return {
            "components": [{"key": k, "ad": a, "aciklama": d} for k, a, d in BL.COMPONENTS], "formula": BL.FORMULA,
            "sorts": BL.SORTS, "m46States": BL.M46_STATES, "matchTypes": BL.MATCH_TYPES, "roles": BK.ROLES,
            "materials": {k: v[0] for k, v in BL.MATERIALS.items()}, "defaultWeights": BL.DEFAULT_WEIGHTS,
            "teamWeights": {k: team[k] for k in BL.KEYS if k in team} or None,
            "teamWeightsBy": team.get("kim"), "teamWeightsAt": team.get("_at"),
            "settings": {k: s[k] for k in ("agendaWeeks", "remindWeeks", "topicWeeks", "campaignYears", "digestMin", "minMonths")},
            "run": {k_: v for k_, v in C.meta_get(engine, tenant, "backlist").items() if k_ != "sql"} or None, "lastRun": C.meta_get(engine, tenant, "backlist-run-due") or None,
            "modelReady": getattr(rt(), "llm", None) is not None,
            "me": {"username": user, "canWrite": can(user, F_WRITE), "canSeeBudget": can(user, F_BUDGET),
                   "canApprove": can(user, F_APPROVE), "canEditorial": can(user, F_EDITORIAL),
                   "canSetTeamWeights": can(user, F_TEAM), "canExport": can(user, F_EXPORT)},
        }

    @app.get(R)
    def bl_list(request: Request, sirala: str = "oncelik", yon: str = "", agirlik: str = "", yayinevi: str = "",
                kitaplik: str = "", hedef_kitle: str = "", m46: str = "", stokta: bool = False, ozel_gun: str = "",
                plan: str = "", q: str = "", page: int = 0) -> dict[str, Any]:
        engine, tenant, user = ctx(request)
        w = weights(engine, tenant, agirlik)
        out = BL.list_rows(engine, tenant, weights=w, sirala=sirala, yon=yon, yayinevi=yayinevi, kitaplik=kitaplik,
                           hedef_kitle=hedef_kitle, m46=m46, stokta=stokta, ozel_gun=ozel_gun, plan=plan, q=q, page=page,
                           agenda_weeks=st()["agendaWeeks"])
        if not can(user, F_BUDGET):
            out["items"] = [hide_money(x) for x in out["items"]]
        out["agirlik"] = w
        out["run"] = C.meta_get(engine, tenant, "backlist") or None
        if out["run"]:
            out["run"] = {k_: v for k_, v in out["run"].items() if k_ != "sql"}   # çalışmış metinler sorgu bilgisinde
        return PV.bagla(out, lambda: K.for_list(engine, tenant, out, PK.logo_db(rt)))

    @app.get(R + "/agenda")
    def bl_agenda(request: Request, hafta: int = 0) -> dict[str, Any]:
        engine, tenant, _ = ctx(request)
        weeks = hafta if hafta > 0 else st()["agendaWeeks"]
        out = BL.agenda(engine, tenant, weeks)
        return PV.bagla(out, lambda: K.for_agenda(engine, tenant, out, PK.logo_db(rt)))

    @app.get(R + "/effects")
    def bl_effects(request: Request, yil: int = 0, backlist: bool = False) -> dict[str, Any]:
        engine, tenant, user = ctx(request)
        out = BL.effects(engine, tenant, yil or None, only_backlist=backlist)
        if not can(user, F_BUDGET):
            for c_ in out["items"]:
                c_["planlananCiro"] = c_["gerceklesenCiro"] = None
                c_["urunler"] = [{**u, "planlananCiro": None, "gerceklesenCiro": None} for u in c_["urunler"]]
        return PV.bagla(out, lambda: K.for_effects(engine, tenant, yil or None, backlist, PK.logo_db(rt)))

    @app.get(R + "/activations")
    def bl_activations(request: Request, durum: str = "", arsiv: bool = False) -> dict[str, Any]:
        engine, tenant, user = ctx(request)
        out = BL.activations(engine, tenant, durum=durum, include_archive=arsiv)
        if not can(user, F_BUDGET):
            out["items"] = [_redact(p) for p in out["items"]]
        return PV.bagla(out, lambda: K.for_activations(engine, tenant, out, durum, arsiv))

    @app.get(R + "/export.csv")
    def bl_csv(request: Request, sirala: str = "oncelik", agirlik: str = "", yayinevi: str = "", kitaplik: str = "",
               hedef_kitle: str = "", m46: str = "", stokta: bool = False, ozel_gun: str = "", plan: str = "",
               q: str = "") -> Response:
        engine, tenant, user = ctx(request)
        w = weights(engine, tenant, agirlik)
        rows = BL.all_rows(engine, tenant, w, sirala=sirala, yayinevi=yayinevi, kitaplik=kitaplik, hedef_kitle=hedef_kitle,
                           m46=m46, stokta=stokta, ozel_gun=ozel_gun, plan=plan, q=q, agenda_weeks=st()["agendaWeeks"])
        money = can(user, F_BUDGET)
        buf = io.StringIO()
        wr = csv.writer(buf, delimiter=";")
        head = ["Stok kodu", "Kitap", "Yazar", "Yayınevi", "Kitaplık", "Hedef kitle", "İlk yayın", "Son 12 ay adet",
                "Önceki 12 ay adet", "Değişim", "Stok", "Tükenme (ay)", "Tahmin 12 ay", "Hedef durumu", "Açık sapma",
                "Uyku endeksi"] + [f"{a} yüzdeliği" for _, a, _ in BL.COMPONENTS] + (["Son 12 ay ciro", "Marj"] if money else [])
        wr.writerow(head)

        def n(v: Any) -> str:
            return "" if v is None else f"{v}".replace(".", ",")

        for x in rows:
            wr.writerow([x["stokKodu"], x["ad"] or "", x["yazar"] or "", x["yayinevi"] or "", x["kitaplik"] or "",
                         x["hedefKitle"] or "", x["ilkYayin"] or "", n(x["adetSon12"]), n(x["adetOnceki12"]), n(x["degisim"]),
                         n(x["stok"]), "satış yok" if x["satisYok"] else n(x["tukenmeAy"]), n(x["tahmin12"]),
                         x["m46"]["durumAdi"] or "", "evet" if x["m46"]["sapmaAcik"] else "", n(x["endeks"])]
                        + [n(x["bilesen"][k]["yuzdelik"]) for k in BL.KEYS] + ([n(x["ciroSon12"]), n(x["marj"])] if money else []))
        audit(engine, user, "run", "marketing_backlist", None, "Backlist listesi", {"disaAktar": "csv", "satir": len(rows)})
        return Response(("\ufeff" + buf.getvalue()).encode("utf-8"), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": 'attachment; filename="backlist-firsatlar.csv"'})

    # ------------------------------------------------------------------ yazma

    @app.put(R + "/weights")
    def bl_weights(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user = ctx(request)
        need(user, F_TEAM, "Backlist ekip ağırlığını kaydetme")
        w = call(BL.parse_weights, body.get("agirlik"))
        old = C.meta_get(engine, tenant, TEAM_WEIGHTS)
        C.meta_set(engine, tenant, TEAM_WEIGHTS, {**w, "kim": user})
        audit(engine, user, "update", "marketing_backlist", TEAM_WEIGHTS, "Backlist ekip ağırlıkları",
              {"eski": {k: old.get(k) for k in BL.KEYS} if old else None, "yeni": w})
        return {"teamWeights": w}

    @app.post(R + "/matches/{mid}/decide")
    def bl_decide(mid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user = ctx(request)
        m = call(BL.decide_match, engine, tenant, user, mid, str(body.get("karar") or ""))
        audit(engine, user, "approve" if m["onay"] == "kabul" else "reject", "marketing_match", m["id"],
              f"{m['etiket']} · {m['stokKodu']}", {"karar": m["onay"], "skor": m["skor"]})
        return {"match": m}

    @app.post(R + "/plans", status_code=201)
    async def bl_plan_create(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user = await run_in_threadpool(ctx, request)
        pid = await run_in_threadpool(call, BL.create_activation, engine, tenant, user, crm, mkt(), st(), body)
        plan = C.plan_full(engine, tenant, pid)
        plan["kitaplar"] = BK.of(engine, pid)
        audit(engine, user, "create", "marketing_plan", pid, plan["baslik"],
              {"kind": "backlist", "kitap": [b["stokKodu"] for b in plan["kitaplar"]], "baslangic": plan["yayinTarihi"],
               "cerceve": (plan.get("butceCerceveKaynak") or {}).get("kaynak")})
        return plan if can(user, F_BUDGET) else _redact(plan)

    @app.get(R + "/plans/{plan_id}/books")
    def bl_plan_books(plan_id: str, request: Request) -> dict[str, Any]:
        engine, tenant, _ = ctx(request)
        call(C.plan_full, engine, tenant, plan_id)
        return PV.bagla({"items": BK.of(engine, plan_id)}, lambda: K.for_plan_books(engine, plan_id))

    @app.put(R + "/plans/{plan_id}/books")
    def bl_plan_books_put(plan_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user = ctx(request)
        plan = call(C.plan_full, engine, tenant, plan_id)
        if plan["kind"] != "backlist":
            raise HTTPException(status_code=409, detail={"code": "MARKETING", "message": "Bu plan backlist planı değil."})
        items = call(BK.put, engine, tenant, user, plan_id, body.get("kitaplar"))
        audit(engine, user, "update", "marketing_plan", plan_id, plan["baslik"], {"kitap": [b["stokKodu"] for b in items]})
        return {"items": items}

    def run_material(jid: str, tenant: str, user: str, plan_id: str, tur: str) -> None:
        engine = rt().store.engine
        try:
            C.job_update(engine, jid, durum="calisiyor", adim="Kitap bilgisi okunuyor")
            plan = C.plan_full(engine, tenant, plan_id)
            books_ = BK.of(engine, plan_id)
            rows = BL.rows_by_code(engine, tenant, [b["stokKodu"] for b in books_])
            details: dict[str, Any] = {}
            for b in books_:
                try:
                    details[b["stokKodu"]] = crm.book(b["stokKodu"])
                except SourceError as e:
                    log.warning("backlist: CRM kartı okunamadı (%s): %s", b["stokKodu"], e)
                    details[b["stokKodu"]] = None
            with engine.connect() as c:
                mts = [BL.match_dict(m) for m in c.execute(sa.select(BL.MATCHES).where(
                    BL.MATCHES.c.tenant_id == tenant, BL.MATCHES.c.stok_kodu.in_([b["stokKodu"] for b in books_] or [""]))).all()
                    if m.tur == "yazar-yeni" or (m.tur == "konu" and m.onay == "kabul")]
            llm = rt().llm_for("marketing", NORMAL)
            if llm is None:
                C.job_update(engine, jid, durum="bitti", adim=None,
                             sonuc={"uyari": "Zeki AI modeli bu kurulumda bağlı değil: taslak yazılamadı; metni elle yazın."})
                return
            C.job_update(engine, jid, adim=f"{BL.MATERIALS[tur][0]} taslağı")
            metin, dog = BL.draft(llm, plan, books_, rows, details, mts, tur, mkt())
            if metin:
                m = C.add_material(engine, tenant, user, plan_id, tur, metin, "zeki", dog, replace_draft=True)
                res = {"materyal": [{"tur": tur, "id": m["id"], "dusen": dog["dusenSayisi"]}]}
            else:
                res = {"materyal": [{"tur": tur, "id": None, "dusen": dog["dusenSayisi"],
                                     "not": "Denetimden geçen cümle kalmadı; taslak yazılmadı."}]}
            C.job_update(engine, jid, durum="bitti", adim=None, sonuc=res)
            admin_mod.audit(engine, user, "run", "marketing_plan", plan_id, "Zeki AI backlist taslağı", res)
        except Exception as e:  # noqa: BLE001 — iş hatası ekranda görünür, köprüyü düşürmez
            log.exception("backlist material job failed")
            C.job_update(engine, jid, durum="hata", adim=None, hata=str(e)[:500] or e.__class__.__name__)

    @app.post(R + "/plans/{plan_id}/materials", status_code=201)
    def bl_material(plan_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user = ctx(request)
        plan = call(C.plan_full, engine, tenant, plan_id)
        if plan["kind"] != "backlist":
            raise HTTPException(status_code=409, detail={"code": "MARKETING", "message": "Bu plan backlist planı değil."})
        tur = str(body.get("tur") or "")
        if tur not in BL.MATERIALS:
            raise HTTPException(status_code=400, detail={"code": "MARKETING", "message": "Materyal türü tanınmıyor."})
        if body.get("metin"):
            m = call(C.add_material, engine, tenant, user, plan_id, tur, body["metin"], "kullanici")
            audit(engine, user, "create", "marketing_material", m["id"], m["turAdi"], {"plan": plan_id, "kaynak": "kullanici"})
            return {"material": m}
        job = call(C.job_create, engine, tenant, user, plan_id, "material", {"materyaller": [tur]})
        pool.submit(run_material, job["id"], tenant, user, plan_id, tur)
        return {"job": job}

    @app.get(R + "/{stok:path}")
    def bl_detail(stok: str, request: Request, agirlik: str = "") -> dict[str, Any]:
        engine, tenant, user = ctx(request)
        out = call(BL.detail, engine, tenant, stok, st(), weights(engine, tenant, agirlik))
        out = out if can(user, F_BUDGET) else hide_money(out)
        return PV.bagla(out, lambda: K.for_detail(engine, tenant, stok, PK.logo_db(rt)))

    # ------------------------------------------------------------------ zamanlayıcı

    def _mail(subject: str, text: str, to: list[str]) -> str:
        return _send_mail(subject, text, to) if to else "no_recipient"

    def notifications(engine, tenant: str, force: bool) -> dict[str, Any]:
        s, m = st(), mkt()
        today = C.today()
        out: dict[str, Any] = {}
        to = list(m["recipients"])
        # aylık fırsat özeti
        last = C.meta_get(engine, tenant, "backlist-digest")
        if BL.first_workday(today) or force:
            if last.get("tarih") == today.isoformat() and last.get("sonuc") == "sent" and not force:
                out["aylik"] = "bugün gönderildi"
            else:
                text = BL.digest_month(engine, tenant, s, link("backlist"))
                status = _mail(f"ZEKİ pazarlama: backlist fırsatları ({today.strftime('%m.%Y')})", text, to) if text else "yok"
                C.meta_set(engine, tenant, "backlist-digest", {"tarih": today.isoformat(), "sonuc": status})
                out["aylik"] = status
        # özel güne N hafta kala
        due = BL.remind_days(engine, tenant, s, today=today)
        if due:
            lines = [f"Başlangıcına {s['remindWeeks']} hafta ya da daha az kalan özel günler ve backlist planı olmayan stoklu kitaplar:", ""]
            for d in due:
                lines.append(f"- {d['ad']} ({P._tr_day(d['baslangic'])}, {d['kalanGun']} gün): bağlı {len(d['kitaplar'])} kitap, "
                             f"stokta {d['stokta']}, aktivasyonu olmayan {d['aktivasyonsuz']}.")
            lines += ["", f"Gündem: {link('backlist?sekme=gundem')}" if link() else "Gündem: Pazarlama › Planlama › Backlist › Gündem"]
            status = _mail("ZEKİ pazarlama: yaklaşan özel günler (backlist)", "\n".join(lines), to)
            if status == "sent":
                for d in due:
                    C.meta_set(engine, tenant, d["_key"], {"sonuc": status})
            out["ozelGun"] = {"gun": len(due), "sonuc": status}
        # haftalık: yeni hedef sapması (pazartesi)
        if today.weekday() == 0 or force:
            run = C.meta_get(engine, tenant, "backlist")
            year = (run.get("kume") or {}).get("yil")
            if year and (run.get("kume") or {}).get("kaynak") == "m46":
                codes = {x["stokKodu"] for x in BL.all_rows(engine, tenant, BL.DEFAULT_WEIGHTS)}
                devs = BL._deviations(engine, tenant, int(year))
                since = (today - timedelta(days=7)).isoformat()
                new = [d for k, d in devs.items() if k in codes and (d.get("firstAt") or "")[:10] >= since]
                if new:
                    gap = sum(d.get("gap") or 0 for d in new)
                    text = (f"Son bir haftada satış hedefinde yeni sapma uyarısı açılan backlist kitap: {len(new)}; beklenenden "
                            f"eksik ciro {B._tr(gap)} ₺.\n\nListe: " + (link("backlist?m46=acik") or "Pazarlama › Planlama › Backlist"))
                    out["sapma"] = {"kitap": len(new), "sonuc": _mail("ZEKİ pazarlama: backlist hedef sapması (haftalık)", text, to)}
                else:
                    out["sapma"] = {"kitap": 0}
        # yazarın yeni kitabının planı onaylandı → plan sahibine çapraz satış adayları
        ag = BL.agenda(engine, tenant, s["agendaWeeks"], today=today)
        by_new = {a["stokKodu"]: a for a in ag["yazarlar"]}
        sent = 0
        for p in C.list_plans(engine, tenant, kind="yeni", durum="onayli"):
            a = by_new.get(p.get("stokKodu") or "")
            key = f"backlist-cross:{p['id']}"
            if not a or C.meta_get(engine, tenant, key).get("_at"):
                continue
            mail = crm.email_of(p["sahip"]) if p.get("sahip") else None
            names = "\n".join(f"  - {b['ad'] or b['stokKodu']} ({b['stokKodu']})" for b in a["kitaplar"])
            text = (f"{p['baslik']} planı onaylandı. Yazarın backlist kitapları ({len(a['kitaplar'])}) çapraz satış adayıdır:\n"
                    f"{names}\n\nBacklist: " + (link("backlist?sekme=gundem") or "Pazarlama › Planlama › Backlist › Gündem"))
            status = _mail(f"ZEKİ pazarlama: çapraz satış adayı · {p['baslik']}", text, [mail] if mail else to)
            if status == "sent":
                C.meta_set(engine, tenant, key, {"sonuc": status})
                sent += 1
        out["caprazSatis"] = sent
        return out

    @app.post(R + "/run-due")
    def bl_run_due(request: Request, adim: str = "gece", force: bool = False) -> dict[str, Any]:
        """Gece: liste (M46 + Logo stok + tahmin + CRM), pazar günü geçmiş yıllar ve konu eşleşmesi. Bildirim: e-postalar."""
        require_caller(request)
        engine, tenant = db()
        today = C.today()
        out: dict[str, Any] = {"tarih": today.isoformat(), "adim": adim}
        if not run_lock.acquire(blocking=False):
            return {**out, "atlandi": "başka bir koşu sürüyor"}
        try:
            if adim == "gece":
                weekly = today.weekday() == 6 or force
                src = sources()
                try:
                    out["liste"] = BL.build(engine, tenant, src, st(), refresh_past=weekly, today=today)
                except (SourceError, C.MarketingError) as e:
                    out["hata"] = str(e)
                if weekly and "hata" not in out:
                    try:
                        out["konu"] = BL.match_topics(engine, tenant, src, rt().llm_for("marketing", BATCH), st(), mkt(), today=today)
                    except SourceError as e:
                        out["konu"] = {"hata": str(e)}
                    except Exception as e:  # noqa: BLE001 — model yoksa/kapıda hata: liste yine kurulu kalır
                        log.exception("backlist topic matching failed")
                        out["konu"] = {"hata": str(e)[:300]}
            elif adim == "bildirim":
                try:
                    out["bildirim"] = notifications(engine, tenant, force)
                except (SourceError, C.MarketingError) as e:
                    out["hata"] = str(e)
            else:
                raise HTTPException(status_code=400, detail={"code": "MARKETING", "message": "adim gece ya da bildirim olmalı."})
            C.meta_set(engine, tenant, "backlist-run-due", {k: v for k, v in out.items() if k != "liste"}
                       | ({"liste": {k: out["liste"].get(k) for k in ("veriSonu", "sureMs", "kume")}} if "liste" in out else {}))
            return out
        finally:
            run_lock.release()

    return {"settings": st}
