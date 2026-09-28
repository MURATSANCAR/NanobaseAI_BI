"""DYK Danışma ve yönetim kurulu uçları: /api/v1/kurul/*.

Sayfa kapısı `access.RULES` (`sayfa:kurul`, **açıkça verilir** — «Herkes»e ve «Bütün sayfalar»a girmez; kurul paketi
şirketin en hassas belgesidir). İşlem yetkileri ucun içinde denetlenir:
- `ozellik:kurul.hazirla` (açıkça; kurul sekreteri): toplantı, gündem, karar, aksiyon, üye, paket derleme, tutanak ve
  yorum taslağı, göstergeleri şimdi ölçme. Taslak paketi yalnız bu yetkiyle görülür.
- `ozellik:kurul.dondur` (açıkça; genel müdür): yönetici özetini düzeltme ve onaylama, paketi dondurma ve dağıtım kaydı,
  başkasının yazdığı gösterge yorumunu onaylama.
- `ozellik:kurul.gosterge` (açıkça): gösterge kataloğu (tanım, eşik, sahip, sıra, etkinlik).
- `ozellik:kurul.yorum`: kendi göstergesine (katalogda sahibi olduğu) yorum yazma; sahibin yorumu doğrudan onaylıdır.
- `ozellik:kurul.aksiyon`: kendisine atanmış kurul aksiyonunun durumunu ve notunu güncelleme (sahiplik burada denetlenir).
- PDF indirme `ozellik:veri.disa-aktar` (`FEATURE_RULES`) + sayfa; her indirme dağıtım kaydına «indirildi» diye yazılır.

Zamanlayıcı (`timas-kurul.timer`, her gün 06:30) yalnız `POST /api/v1/kurul/run-due` çağırır: göstergeleri
sağlayıcılardan ölçer (hazır raporları okur, ağır sorgu yok), renk değişimini kaydeder, aksiyon ve yorum hatırlatmalarını
yalnız iç adreslere e-postalar. Model çağrıları LLM kapısından (`llm("kurul", BATCH)`). Dış gönderim yok.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from fastapi import HTTPException, Request
from fastapi.responses import Response

from semantic_bridge import kurul as K
from semantic_bridge import kurul_pdf
from semantic_bridge import kurul_sources as S

log = logging.getLogger("semantic.kurul.api")
P = "/api/v1/kurul"
F_PREP = "ozellik:kurul.hazirla"
F_FREEZE = "ozellik:kurul.dondur"
F_CATALOG = "ozellik:kurul.gosterge"
F_COMMENT = "ozellik:kurul.yorum"
F_ACTION = "ozellik:kurul.aksiyon"
F_EXPORT = "ozellik:veri.disa-aktar"


class Service:
    """app.state.kurul: panel ve ölçüm diğer modüllerden (ör. Kampüs kartı) okunabilsin diye."""

    def __init__(self, measure: Callable[[Any, str], list[dict[str, Any]]]):
        self.measure = measure


def register(app: Any, deps: dict[str, Any]) -> Service:
    """deps: auth(request) → (engine, tenant, user, display) · require_caller(request) · can(user, key) · audit(...) ·
    conf(key, default) · engine() / tenant() · datasource() · crm() → (şema, run_sql) · llm(priority) → kapıdan geçen
    model ya da None · send_mail(subject, text, to) → durum."""
    auth, require_caller, can, audit, conf = (deps[k] for k in ("auth", "require_caller", "can", "audit", "conf"))
    measure_lock = threading.Lock()
    state: dict[str, Any] = {"running": False}

    def ctx(request: Request) -> tuple[Any, str, str, str]:
        engine, tenant, user, display = auth(request)
        K.ensure(engine)
        K.seed_library(engine, tenant)
        return engine, tenant, user, display

    def call(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except K.KurulError as e:
            code = {401: "UNAUTHORIZED", 403: "FORBIDDEN", 404: "NOT_FOUND", 409: "CONFLICT"}.get(e.status, "KURUL")
            raise HTTPException(status_code=e.status, detail={"code": code, "message": str(e)}) from e

    def need(user: str, key: str, what: str) -> None:
        if not can(user, key):
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": f"{what} rolünüzde yok."})

    def need_any(user: str, keys: tuple[str, ...], what: str) -> None:
        if not any(can(user, k) for k in keys):
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": f"{what} rolünüzde yok."})

    def owns(user: str, owner: Optional[str]) -> bool:
        return bool(owner) and (owner or "").lower() == (user or "").lower()

    def llm_chat(max_tokens: int):
        try:
            from semantic_layer.runtime.llm_queue import BATCH

            m = deps["llm"](BATCH)
        except Exception:  # noqa: BLE001 — model tanımlı değil
            return None
        if m is None:
            return None
        return lambda messages: m.chat(messages, max_tokens=max_tokens, temperature=0.0)

    def source_ctx(engine, tenant) -> S.Ctx:
        return S.Ctx(engine=engine, tenant=tenant, conf=conf, today=K.today(), datasource=deps.get("datasource") or (lambda: "default"),
                     crm=deps.get("crm"))

    def measure_now(engine, tenant) -> list[dict[str, Any]]:
        """Bütün etkin göstergeler; aynı anda tek ölçüm."""
        if not measure_lock.acquire(timeout=600):
            raise K.KurulError("Başka bir ölçüm sürüyor; birazdan yeniden deneyin.", 409)
        state["running"] = True
        try:
            K.seed_library(engine, tenant)
            inds = K.indicators(engine, tenant, only_active=True)
            res = S.measure(source_ctx(engine, tenant), inds)
            return K.record(engine, tenant, K.current_donem(), res)
        finally:
            state["running"] = False
            measure_lock.release()

    def measure_background(engine, tenant) -> bool:
        if state["running"] or measure_lock.locked():
            return False

        def go() -> None:
            try:
                measure_now(engine, tenant)
            except Exception as e:  # noqa: BLE001
                log.warning("kurul: arka plan ölçümü düştü: %s", e)

        threading.Thread(target=go, name="kurul-olcum", daemon=True).start()
        return True

    def internal_mail(subject: str, body: str, to: list[str]) -> str:
        """Yalnız iç alıcılar: izinli alan adı ayarı doluysa dışındaki adrese gitmez."""
        allowed = [d.strip().lower().lstrip("@") for d in (conf("ALERT_RECIPIENT_DOMAINS") or "").split(",") if d.strip()]
        to = [x for x in to if x and "@" in x and (not allowed or x.lower().rsplit("@", 1)[-1] in allowed)]
        if not to:
            return "alici_yok"
        return deps["send_mail"](subject, body, to)

    def link(path: str = "") -> str:
        base = (conf("ALERT_LINK") or "").split("/uyarilar")[0].rstrip("/")
        return f"{base}/kurul{path}" if base else ""

    def me(user: str, display: str) -> dict[str, Any]:
        return {"username": user, "display": display, "canPrepare": can(user, F_PREP), "canFreeze": can(user, F_FREEZE),
                "canCatalog": can(user, F_CATALOG), "canComment": can(user, F_COMMENT), "canAction": can(user, F_ACTION),
                "canExport": can(user, F_EXPORT)}

    def package_for(engine, tenant, user, pid) -> dict[str, Any]:
        pkg = call(K.package, engine, tenant, pid)
        if not K.visible_package(pkg, can(user, F_PREP)):
            raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "Paket bulunamadı."})
        return pkg

    def comment_scope(engine, tenant, user, kod: str) -> dict[str, Any]:
        """Yorum yazabilen: göstergenin sahibi (`kurul.yorum`) ya da hazırlayan. Sahip yazınca yorum onaylıdır."""
        ind = call(K.indicator, engine, tenant, kod)
        mine = owns(user, ind.get("sahip")) and can(user, F_COMMENT)
        if not (mine or can(user, F_PREP)):
            raise HTTPException(403, detail={"code": "FORBIDDEN", "message": "Yalnız sahibi olduğunuz göstergeye yorum yazabilirsiniz."})
        return {"ind": ind, "mine": mine}

    # ------------------------------------------------------------------ genel

    @app.get(P + "/meta")
    def kurul_meta(request: Request) -> dict[str, Any]:
        _, _, user, display = ctx(request)
        return {"bolumler": S.BOLUMLER, "birimler": K.UNITS, "yonler": K.DIRECTIONS, "renkler": K.COLORS,
                "toplantiTurleri": K.MEETING_TYPES, "toplantiDurumlari": K.MEETING_STATES, "gundemTurleri": K.AGENDA_TYPES,
                "aksiyonDurumlari": K.ACTION_STATES, "paketDurumlari": K.PACKAGE_STATES, "ozetDurumlari": K.SUMMARY_STATES,
                "yorumDurumlari": K.COMMENT_STATES, "kanallar": K.CHANNELS, "saglayicilar": {k: v[0] for k, v in S.SOURCE_NAMES.items()},
                "ayarlar": K.settings(), "me": me(user, display), "modelVar": llm_chat(100) is not None}

    @app.get(P + "/status")
    def kurul_status(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return {**K.status(engine, tenant), "olcumSuruyor": state["running"]}

    @app.post(P + "/refresh", status_code=202)
    def kurul_refresh(request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, F_PREP, "Göstergeleri ölçme")
        started = measure_background(engine, tenant)
        audit(engine, user, "run", "kurul_measure", None, "Kurul göstergeleri ölçüldü", {"basladi": started})
        return {"started": started, "olcumSuruyor": True}

    # ------------------------------------------------------------------ panel ve göstergeler

    @app.get(P + "/panel")
    def kurul_panel(request: Request, donem: str = "") -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        started = False
        if not donem and K.is_stale(engine, tenant):
            started = measure_background(engine, tenant)
        out = call(K.panel, engine, tenant, donem or None)
        return {**out, "olcumSuruyor": state["running"] or started}

    @app.get(P + "/indicators")
    def kurul_indicators(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return {"items": K.indicators(engine, tenant)}

    @app.post(P + "/indicators", status_code=201)
    def kurul_indicator_create(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, F_CATALOG, "Gösterge kataloğu")
        out = call(K.create_indicator, engine, tenant, user, body)
        audit(engine, user, "create", "kurul_indicator", out["kod"], out["ad"], {"saglayici": out["saglayici"]})
        return out

    @app.get(P + "/indicators/{kod}")
    def kurul_indicator(kod: str, request: Request, donem: str = "") -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return call(K.indicator_detail, engine, tenant, kod, donem or None)

    @app.patch(P + "/indicators/{kod}")
    def kurul_indicator_update(kod: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, F_CATALOG, "Gösterge kataloğu")
        out, diff = call(K.update_indicator, engine, tenant, user, kod, body)
        if diff:
            audit(engine, user, "update", "kurul_indicator", kod, out["ad"], diff)
        return out

    @app.post(P + "/indicators/{kod}/comments", status_code=201)
    def kurul_comment_add(kod: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        sc = comment_scope(engine, tenant, user, kod)
        donem = call(K.valid_donem, body.get("donem") or K.current_donem())
        out = call(K.add_comment, engine, tenant, user, kod, donem, body.get("metin"), approve=sc["mine"])
        audit(engine, user, "create", "kurul_comment", out["id"], sc["ind"]["ad"], {"donem": donem, "durum": out["durum"]})
        return out

    @app.post(P + "/indicators/{kod}/comments/draft", status_code=202)
    def kurul_comment_draft(kod: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        sc = comment_scope(engine, tenant, user, kod)
        donem = call(K.valid_donem, body.get("donem") or K.current_donem())
        detail = call(K.indicator_detail, engine, tenant, kod, donem)
        if detail["gosterge"]["durum"] != "ok":
            raise HTTPException(409, detail={"code": "CONFLICT", "message": "Kaynağı olmayan göstergeye taslak yazılmaz."})
        facts = K.comment_facts(detail)
        chat = llm_chat(600)
        cm = call(K.start_comment_draft, engine, tenant, user, kod, donem)

        def work(jid: str) -> dict[str, Any]:
            text, err = K.draft_text(chat, K.COMMENT_SYSTEM, facts)
            K.finish_comment_draft(engine, cm["id"], text, err, jid)
            if err:
                raise K.KurulError(err, 422)
            return {"yorumId": cm["id"]}

        job = K.start_job(engine, tenant, user, "yorum", work)
        audit(engine, user, "run", "kurul_comment", cm["id"], sc["ind"]["ad"], {"donem": donem, "is": job["id"], "kaynak": "Zeki AI"})
        return {**job, "yorumId": cm["id"]}

    def comment_editable_by(engine, tenant, user, cid: str) -> dict[str, Any]:
        cm = call(K.comment, engine, tenant, cid)
        comment_scope(engine, tenant, user, cm["kod"])
        return cm

    @app.patch(P + "/comments/{cid}")
    def kurul_comment_edit(cid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        comment_editable_by(engine, tenant, user, cid)
        out = call(K.edit_comment, engine, tenant, cid, body.get("metin"))
        audit(engine, user, "update", "kurul_comment", cid, out["kod"], {"karakter": len(out["metin"] or "")})
        return out

    @app.post(P + "/comments/{cid}/approve")
    def kurul_comment_approve(cid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        cm = call(K.comment, engine, tenant, cid)
        ind = call(K.indicator, engine, tenant, cm["kod"])
        if not ((owns(user, ind.get("sahip")) and can(user, F_COMMENT)) or can(user, F_FREEZE)):
            raise HTTPException(403, detail={"code": "FORBIDDEN", "message": "Yorumu göstergenin sahibi ya da genel müdür onaylar."})
        out = call(K.approve_comment, engine, tenant, user, cid)
        audit(engine, user, "approve", "kurul_comment", cid, ind["ad"], {"donem": out["donem"], "kaynak": out["kaynak"]})
        return out

    @app.delete(P + "/comments/{cid}")
    def kurul_comment_delete(cid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        comment_editable_by(engine, tenant, user, cid)
        out = call(K.delete_comment, engine, tenant, cid)
        audit(engine, user, "delete", "kurul_comment", cid, out["kod"], {"donem": out["donem"]})
        return {"ok": True}

    # ------------------------------------------------------------------ toplantılar

    @app.get(P + "/meetings")
    def kurul_meetings(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return K.list_meetings(engine, tenant)

    @app.post(P + "/meetings", status_code=201)
    def kurul_meeting_create(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, F_PREP, "Toplantı hazırlama")
        out = call(K.create_meeting, engine, tenant, user, body)
        audit(engine, user, "create", "kurul_meeting", out["id"], out["baslik"], {"tarih": out["tarih"], "tur": out["tur"]})
        return out

    @app.get(P + "/meetings/{mid}")
    def kurul_meeting(mid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        m = call(K.meeting, engine, tenant, mid)
        prep = can(user, F_PREP)
        m["paketler"] = [p for p in m["paketler"] if K.visible_package(p, prep)]
        if not prep:
            m["notlar"] = None          # sekreterin çalışma notu kurul üyesine açılmaz
        return m

    @app.patch(P + "/meetings/{mid}")
    def kurul_meeting_update(mid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, F_PREP, "Toplantı hazırlama")
        out, diff = call(K.update_meeting, engine, tenant, user, mid, body)
        audit(engine, user, "update", "kurul_meeting", mid, out["baslik"], diff)
        return out

    @app.put(P + "/meetings/{mid}/agenda")
    def kurul_agenda(mid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, F_PREP, "Gündem hazırlama")
        items = call(K.set_agenda, engine, tenant, mid, body.get("items"))
        audit(engine, user, "update", "kurul_agenda", mid, "Gündem", {"madde": len(items)})
        return {"items": items}

    @app.get(P + "/meetings/{mid}/agenda/suggest")
    def kurul_agenda_suggest(mid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, F_PREP, "Gündem hazırlama")
        return {"items": call(K.agenda_suggestions, engine, tenant, mid)}

    @app.post(P + "/meetings/{mid}/decisions", status_code=201)
    def kurul_decision_add(mid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, F_PREP, "Karar kaydı")
        out = call(K.add_decision, engine, tenant, user, mid, body)
        audit(engine, user, "create", "kurul_decision", out["id"], out["metin"][:80], {"toplanti": mid, "aksiyon": len(out["aksiyonlar"])})
        return out

    @app.patch(P + "/decisions/{did}")
    def kurul_decision_update(did: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, F_PREP, "Karar kaydı")
        out = call(K.update_decision, engine, tenant, user, did, body)
        audit(engine, user, "update", "kurul_decision", did, out["metin"][:80], {k: True for k in body})
        return out

    @app.delete(P + "/decisions/{did}")
    def kurul_decision_delete(did: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, F_PREP, "Karar kaydı")
        out = call(K.delete_decision, engine, tenant, did)
        audit(engine, user, "delete", "kurul_decision", did, (out["metin"] or "")[:80], {"toplanti": out["toplantiId"]})
        return {"ok": True}

    @app.post(P + "/decisions/{did}/actions", status_code=201)
    def kurul_action_add(did: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, F_PREP, "Aksiyon kaydı")
        out = call(K.add_action, engine, tenant, user, did, body)
        audit(engine, user, "create", "kurul_action", out["id"], out["eylem"][:80], {"sahip": out["sahip"], "termin": out["termin"]})
        return out

    @app.get(P + "/actions")
    def kurul_actions(request: Request, durum: str = "acik", mine: bool = False) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        return K.list_actions(engine, tenant, durum=durum, sahip=user if mine else None)

    @app.patch(P + "/actions/{aid}")
    def kurul_action_update(aid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        cur = call(K.action, engine, tenant, aid)
        full = can(user, F_PREP)
        if not full and not (owns(user, cur["sahip"]) and can(user, F_ACTION)):
            raise HTTPException(403, detail={"code": "FORBIDDEN", "message": "Yalnız size atanmış kurul aksiyonunu güncelleyebilirsiniz."})
        out, diff = call(K.update_action, engine, tenant, user, aid, body, full=full)
        if diff:
            audit(engine, user, "update", "kurul_action", aid, out["eylem"][:80], diff)
        return out

    @app.post(P + "/meetings/{mid}/minutes/draft", status_code=202)
    def kurul_minutes_draft(mid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        """Sekreterin serbest notlarından karar/aksiyon önerisi. Öneri kaydedilmez: sekreter tek tek karar olarak ekler."""
        engine, tenant, user, _ = ctx(request)
        need(user, F_PREP, "Tutanak taslağı")
        if "notlar" in body:
            call(K.update_meeting, engine, tenant, user, mid, {"notlar": body.get("notlar")})
        m = call(K.meeting, engine, tenant, mid)
        notes = (m.get("notlar") or "").strip()
        if not notes:
            raise HTTPException(422, detail={"code": "KURUL", "message": "Önce toplantı notlarını yazın."})
        chat = llm_chat(2500)
        if chat is None:
            raise HTTPException(503, detail={"code": "KURUL", "message": "Zeki AI bu kurulumda tanımlı değil."})
        agenda = [{"sira": a["sira"], "baslik": a["baslik"]} for a in m["gundem"]]

        def work(_jid: str) -> dict[str, Any]:
            raw = chat([{"role": "system", "content": K.MINUTES_SYSTEM},
                        {"role": "user", "content": "Gündem:\n" + K._dump(agenda) + "\n\nNotlar:\n" + notes}])
            items, dropped = K.parse_minutes(raw, notes + "\n" + K._dump(agenda))
            return {"oneriler": items, "dusenler": dropped}

        job = K.start_job(engine, tenant, user, "tutanak", work)
        audit(engine, user, "run", "kurul_minutes", mid, m["baslik"], {"is": job["id"], "kaynak": "Zeki AI"})
        return job

    # ------------------------------------------------------------------ paketler

    @app.post(P + "/meetings/{mid}/packages", status_code=201)
    def kurul_package_compile(mid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, F_PREP, "Paket derleme")
        sc = source_ctx(engine, tenant)

        def safe(fn):
            try:
                return fn(sc)
            except Exception as e:  # noqa: BLE001 — risk/pazar modülü okunamazsa paket o bölümsüz derlenir
                log.warning("kurul: paket bölümü okunamadı (%s): %s", getattr(fn, "__name__", fn), e)
                return None

        content = call(K.build_content, engine, tenant, mid, risk=safe(S.risk_briefing), risk_numbers=safe(S.risk_numbers),
                       market=safe(S.market_brief))
        out = call(K.compile_package, engine, tenant, user, mid, content)
        audit(engine, user, "create", "kurul_package", out["id"], f"Kurul paketi v{out['surum']}",
              {"toplanti": mid, "icerikSha256": out["icerikSha256"], "eksikYorum": len(content["eksikYorum"])})
        return out

    @app.get(P + "/packages")
    def kurul_packages(request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        prep = can(user, F_PREP)
        items = [p for p in K.list_packages(engine, tenant)["items"] if K.visible_package(p, prep)]
        return {"items": items}

    @app.get(P + "/packages/{pid}")
    def kurul_package(pid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        pkg = package_for(engine, tenant, user, pid)
        if not (can(user, F_PREP) or can(user, F_FREEZE)):
            pkg["dagitim"] = []        # kime gittiği hazırlayan ve genel müdürün bilgisidir
        return pkg

    @app.post(P + "/packages/{pid}/summary/draft", status_code=202)
    def kurul_summary_draft(pid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need_any(user, (F_PREP, F_FREEZE), "Yönetici özeti taslağı")
        content = call(K.start_summary, engine, tenant, pid)
        facts = K.summary_facts(content)
        chat = llm_chat(3000)

        def work(_jid: str) -> dict[str, Any]:
            text, err = K.draft_text(chat, K.SUMMARY_SYSTEM, facts)
            K.finish_summary(engine, pid, text, err)
            if err:
                raise K.KurulError(err, 422)
            return {"paketId": pid}

        job = K.start_job(engine, tenant, user, "ozet", work)
        audit(engine, user, "run", "kurul_package", pid, "Yönetici özeti taslağı", {"is": job["id"], "kaynak": "Zeki AI"})
        return {**job, "paketId": pid}

    @app.patch(P + "/packages/{pid}")
    def kurul_package_edit(pid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, F_FREEZE, "Yönetici özeti düzeltme")
        out = call(K.edit_summary, engine, tenant, pid, body.get("ozetMetin"))
        audit(engine, user, "update", "kurul_package", pid, f"Kurul paketi v{out['surum']} özeti",
              {"karakter": len(out.get("ozetMetin") or ""), "olguDisiSayi": out.get("olguDisiSayilar")})
        return out

    @app.post(P + "/packages/{pid}/summary/approve")
    def kurul_summary_approve(pid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, F_FREEZE, "Yönetici özeti onayı")
        out = call(K.approve_summary, engine, tenant, user, pid)
        audit(engine, user, "approve", "kurul_package", pid, f"Kurul paketi v{out['surum']} özeti", {"kaynak": out["ozetKaynak"]})
        return out

    @app.post(P + "/packages/{pid}/freeze")
    def kurul_package_freeze(pid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, F_FREEZE, "Paketi dondurma")
        out = call(K.freeze_package, engine, tenant, user, pid, kurul_pdf.render)
        audit(engine, user, "approve", "kurul_package", pid, f"Kurul paketi v{out['surum']} donduruldu",
              {"icerikSha256": out["icerikSha256"], "pdfSha256": out["pdfSha256"]})
        return out

    @app.get(P + "/packages/{pid}/document.pdf")
    def kurul_package_pdf(pid: str, request: Request) -> Response:
        engine, tenant, user, display = ctx(request)
        package_for(engine, tenant, user, pid)
        data, brief = call(K.package_pdf, engine, tenant, pid)
        call(K.record_distribution, engine, tenant, user, pid, [{"alici": display or user, "kanal": "indirme",
                                                                 "sonuc": f"portal hesabı {user}"}])
        audit(engine, user, "run", "kurul_export", pid, f"Kurul paketi v{brief['surum']} (PDF)", {"pdfSha256": brief["pdfSha256"]})
        return Response(data, media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="kurul-paketi-v{brief["surum"]}.pdf"',
                                 "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})

    @app.post(P + "/packages/{pid}/distribute")
    def kurul_package_distribute(pid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        """Dağıtım kaydı. Portal kimseye e-posta göndermez: AD'li üye portaldan açar, AD'siz üyeye PDF'i insan iletir."""
        engine, tenant, user, _ = ctx(request)
        need(user, F_FREEZE, "Paket dağıtımı")
        rows = call(K.distribution_rows, engine, tenant, body.get("uyeler"))
        out = call(K.record_distribution, engine, tenant, user, pid, rows)
        audit(engine, user, "run", "kurul_distribution", pid, f"Kurul paketi v{out['surum']} dağıtıldı",
              {"alici": [r["alici"] for r in rows], "kanal": [r["kanal"] for r in rows]})
        return out

    # ------------------------------------------------------------------ üyeler

    @app.get(P + "/members")
    def kurul_members(request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need_any(user, (F_PREP, F_FREEZE), "Kurul üyeleri")
        return {"items": K.members(engine, tenant)}

    @app.post(P + "/members", status_code=201)
    def kurul_member_create(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, F_PREP, "Kurul üyeleri")
        out = call(K.save_member, engine, tenant, user, None, body)
        audit(engine, user, "create", "kurul_member", out["id"], out["ad"], {"kurul": out["kurul"], "adHesabi": bool(out["adHesabi"])})
        return out

    @app.patch(P + "/members/{mid}")
    def kurul_member_update(mid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, F_PREP, "Kurul üyeleri")
        out = call(K.save_member, engine, tenant, user, mid, body)
        audit(engine, user, "update", "kurul_member", mid, out["ad"], {k: True for k in body})
        return out

    @app.delete(P + "/members/{mid}")
    def kurul_member_delete(mid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, F_PREP, "Kurul üyeleri")
        out = call(K.delete_member, engine, tenant, mid)
        audit(engine, user, "delete", "kurul_member", mid, out["ad"], None)
        return {"ok": True}

    @app.get(P + "/jobs/{jid}")
    def kurul_job(jid: str, request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return call(K.job, engine, tenant, jid)

    # ------------------------------------------------------------------ zamanlayıcı

    @app.post(P + "/run-due")
    def kurul_run_due(request: Request) -> dict[str, Any]:
        """Günde bir: ölçüm, renk değişimi, aksiyon ve yorum hatırlatmaları (yalnız iç adresler)."""
        require_caller(request)
        engine, tenant = deps["engine"](), deps["tenant"]()
        K.ensure(engine)
        started = datetime.now(timezone.utc)
        try:
            changes = measure_now(engine, tenant)
            measure_error = None
        except K.KurulError as e:
            changes, measure_error = [], str(e)
        reminders = K.due_reminders(engine, tenant)
        per: dict[str, list[dict[str, Any]]] = {}
        for x in reminders:
            if x.get("eposta"):
                per.setdefault(x["eposta"], []).append(x)
        for ch in changes:
            if ch["yeni"] == "kirmizi" and ch.get("sahipEposta"):
                per.setdefault(ch["sahipEposta"], []).append({"key": None, "metin": f"«{ch['ad']}» göstergesi kırmızıya döndü: "
                                                             f"{K.fmt_value(ch['deger'], ch['birim'])}."})
        delivered: list[str] = []
        mail: dict[str, Any] = {"adres": len(per), "gonderilen": 0}
        foot = ["", f"Ayrıntı: {link()}" if link() else "Ayrıntı portalda Kurul ekranında."]
        for addr, rows in per.items():
            st = internal_mail("Kurul: size düşen maddeler", "\n".join([f"- {r['metin']}" for r in rows] + foot), [addr])
            if st == "sent":
                mail["gonderilen"] += 1
                delivered += [r["key"] for r in rows if r.get("key")]
        if delivered:
            K.mark_sent(engine, tenant, delivered)
        result = {"basladi": started.isoformat(), "bitti": datetime.now(timezone.utc).isoformat(), "olcumHata": measure_error,
                  "renkDegisimi": [{k: ch[k] for k in ("kod", "ad", "eski", "yeni")} for ch in changes],
                  "hatirlatma": len(reminders), "sahipsizHatirlatma": sum(1 for x in reminders if not x.get("eposta")),
                  "eposta": mail}
        K.meta_set(engine, tenant, "son-kosu", result)
        return result

    return Service(measure_now)
