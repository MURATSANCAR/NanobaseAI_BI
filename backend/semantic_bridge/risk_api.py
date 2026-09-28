"""M47 Risk ve uyum uçları: /api/v1/risk/*.

Sayfa kapısı `access.RULES` (`sayfa:risk-uyum`, açıkça verilen sayfa). İşlem yetkileri:
- `ozellik:risk.yaz` (`FEATURE_RULES`): risk kaydı, gözden geçirme, aksiyon ekleme, Zeki AI önerisi/sınıflaması, brifing
  taslağı. Kişi yalnız sahibi olduğu riski değiştirir; bütün riskleri görmek ve değiştirmek açıkça verilen
  `ozellik:risk.herkesinki` ile (uçta denetlenir).
- Aksiyonun durumu/notu/kanıtı: riskin ya da aksiyonun sahibi (yetki anahtarı gerekmez) ya da `risk.yaz` + `risk.herkesinki`.
- `ozellik:risk.gosterge` (açıkça): gösterge tanımı ve eşik taslağı, «şimdi ölç»; `ozellik:risk.gosterge-onay` (açıkça):
  taslağı yürürlüğe alma/ret — hazırlayan onaylayamaz.
- `ozellik:uyum.yaz` (`FEATURE_RULES`): uyum yükümlülüğü, kanıt, dönem kapatma; KVKK alanındaki maddeler ayrıca açıkça
  verilen `ozellik:uyum.kvkk` ister.
- `ozellik:risk.sigorta-bcp` (`FEATURE_RULES`): poliçe ve iş sürekliliği kaydı.
- `ozellik:risk.rapor-onay` (açıkça): brifing onayı (taslağı hazırlatan onaylayamaz). Word dışa aktarımı `veri.disa-aktar`.

Zamanlayıcı (`timas-risk.timer`, her gün 06:15) yalnız `POST /api/v1/risk/run-due`'yu çağırır: sıklığı gelen
göstergeleri ölçer, kırmızı kenarında ve hatırlatmalarda e-posta gönderir (koordinatöre özet `RISK_ALERT_RECIPIENTS`,
etkisi kritik riske bağlı kırmızı için aynı gün `RISK_CRITICAL_RECIPIENTS`, kayıtlarda e-postası olan sahiplere kendi
maddeleri), uyum takviminin ufkunu açar.

Model çağrıları LLM kapısından: `rt.llm_for("risk", NORMAL)` (`choose` ile kategori, `chat` ile risk taslağı),
brifing `BATCH`. Rakamı model üretmez: metinde girdide olmayan sayı varsa kural metnine düşülür.

DYK modülü bu modülün `GET summary` ve `GET reports` uçlarını okuyacak (sayfa anahtarı RULES satırına eklenir).
"""
from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, Response
from starlette.concurrency import run_in_threadpool

from semantic_bridge import provenance as PK
from semantic_bridge import risk as R
from semantic_bridge import risk_kaynak as K
from semantic_bridge import risk_sources as src

log = logging.getLogger("semantic.risk.api")
P = "/api/v1/risk"
F_WRITE = "ozellik:risk.yaz"
F_ALL = "ozellik:risk.herkesinki"
F_IND = "ozellik:risk.gosterge"
F_IND_OK = "ozellik:risk.gosterge-onay"
F_REPORT_OK = "ozellik:risk.rapor-onay"
F_COMP = "ozellik:uyum.yaz"
F_KVKK = "ozellik:uyum.kvkk"
F_POLICY = "ozellik:risk.sigorta-bcp"
F_EXPORT = "ozellik:veri.disa-aktar"


def register(app, rt: Callable[[], Any], require_caller: Callable[[Request], None], can: Callable[[str, str], bool]):
    from semantic_bridge import admin as admin_mod
    from semantic_bridge import board as board_mod

    status: dict[str, Any] = {"lastRun": None}
    measure_lock = threading.Lock()

    def crm_file() -> str:
        return os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json")

    def dbs() -> tuple[Optional[str], Optional[str]]:
        """Bağlantı dosyalarından YALNIZ veritabanı adları (sorgu bilgisinde USE satırı için)."""
        from semantic_bridge import provenance as PV
        return PV.connection_database(rt().settings.connection_file), PV.connection_database(crm_file())

    def context(engine, tenant) -> src.Context:
        return src.Context(logo_file=lambda: rt().settings.connection_file, crm_file=crm_file,
                           crm_schema=lambda: admin_mod.conf("CRM_SCHEMA") or "Timas_MSCRM.dbo",
                           app_state=app.state, engine=engine, tenant=tenant, asof=R.today())

    def llm(priority: str = "normal"):
        try:
            from semantic_layer.runtime.llm_queue import BATCH, NORMAL
            return rt().llm_for("risk", BATCH if priority == "batch" else NORMAL)
        except Exception:  # noqa: BLE001 — model tanımlı değil
            return None

    def chooser():
        m = llm()
        if m is None or not hasattr(m, "choose"):
            return None
        return lambda prompt, choices: m.choose(prompt, choices)

    def chatter(max_tokens: int, priority: str = "normal"):
        m = llm(priority)
        if m is None:
            return None
        return lambda messages: m.chat(messages, max_tokens=max_tokens, temperature=0.0)

    def ctx(request: Request) -> tuple[Any, str, str, str]:
        require_caller(request)
        try:
            user, display = board_mod.session_of(request.headers.get("cookie", ""))
        except board_mod.NoUser:
            raise HTTPException(status_code=401, detail={"code": "UNAUTHORIZED", "message": "Oturum gerekli."}) from None
        r = rt()
        R.ensure(r.store.engine)
        admin_mod.ensure(r.store.engine)
        return r.store.engine, r.settings.tenant_id, user, display

    def call(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except R.RiskError as e:
            raise HTTPException(status_code=e.status, detail={"code": "RISK", "message": str(e)}) from e
        except src.SourceError as e:
            raise HTTPException(status_code=503, detail={"code": "RISK_SOURCE", "message": str(e)}) from e

    def need(user: str, key: str, what: str) -> None:
        if not can(user, key):
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": f"{what} rolünüzde yok."})

    def audit(engine, user, action, kind, oid, title, detail=None) -> None:
        admin_mod.audit(engine, user, action, kind, oid, title, detail)

    def see_all(user: str) -> bool:
        return can(user, F_ALL)

    def owns(user: str, *names: Optional[str]) -> bool:
        u = (user or "").lower()
        return any(n and n.lower() == u for n in names)

    def risk_for(engine, tenant, user, rid, *, write: bool = False) -> dict[str, Any]:
        d = call(R.risk_detail, engine, tenant, rid)
        owners = [a["sahip"] for a in d["aksiyonlar"]]
        if not R.visible(d, user, see_all(user), owners):
            raise HTTPException(404, detail={"code": "RISK", "message": "Risk bulunamadı."})
        if write and not (see_all(user) or owns(user, d["sahip"], d["olusturan"])):
            raise HTTPException(403, detail={"code": "FORBIDDEN", "message": "Yalnız sahibi olduğunuz riski değiştirebilirsiniz."})
        return d

    def indicator_list(engine, tenant) -> list[dict[str, Any]]:
        R.seed_library(engine, tenant, src.LIBRARY)
        items = R.indicators(engine, tenant, set(src.BY_CODE))
        for g in items:
            spec = src.BY_CODE.get(g["kod"], {})
            g["ekran"] = spec.get("ekran") or None
            g["kategori"] = spec.get("kategori")
        return items

    async def body_bytes(request: Request) -> bytes:
        max_mb = R.settings()["fileMaxMb"]
        if int(request.headers.get("content-length") or 0) > max_mb * 1024 * 1024:
            raise HTTPException(413, detail={"code": "RISK", "message": f"Dosya {max_mb} MB sınırını aşıyor."})
        return await request.body()

    def send_file(path: str, name: str, mime: str) -> FileResponse:
        return FileResponse(path, media_type=mime, filename=name, headers={"X-Content-Type-Options": "nosniff",
                                                                          "Cache-Control": "private, no-store"})

    def recipients(key: str) -> list[str]:
        return [x.strip() for x in (admin_mod.conf(key) or "").replace(";", ",").split(",") if "@" in x]

    # ------------------------------------------------------------------ bildirim

    def notify(engine, tenant, ind_events: list[dict[str, Any]], reminders: list[dict[str, Any]]) -> dict[str, Any]:
        """Koordinatöre tek özet; kritik riske bağlı kırmızı aynı gün kritik alıcılarına; sahiplere kendi maddeleri.
        Gönderilemeyen hatırlatma işaretlenmez (sonraki koşuda yeniden denenir)."""
        from semantic_bridge.budget_api import _send_mail

        if not ind_events and not reminders:
            return {"eposta": "bos"}
        cfg = R.settings()
        live = R.list_risks(engine, tenant, "", True, durum="canli")["items"]
        by_kod: dict[str, list[dict[str, Any]]] = {}
        for r in live:
            for k in r["gostergeler"]:
                by_kod.setdefault(k, []).append(r)
        link = (admin_mod.conf("ALERT_LINK") or "").split("/uyarilar")[0]
        link = f"{link}/risk-uyum" if link else ""
        ind_lines = R.indicator_alert_lines(ind_events, by_kod)
        rem_lines = [x["metin"] for x in reminders]
        foot = ["", f"Ayrıntı: {link}" if link else "Ayrıntı portalda Risk ve uyum ekranında.",
                "Göstergeler inceleme adayıdır; puanı ve kararı risk sahibi verir."]
        delivered: set[str] = set()
        out: dict[str, Any] = {}
        coord = recipients("RISK_ALERT_RECIPIENTS")
        if coord:
            body = (["Gösterge değişiklikleri:"] + [f"- {x}" for x in ind_lines] + [""] if ind_lines else []) + \
                   (["Hatırlatmalar:"] + [f"- {x}" for x in rem_lines] if rem_lines else []) + foot
            st = _send_mail(f"Risk ve uyum: {len(ind_lines)} gösterge, {len(rem_lines)} hatırlatma", "\n".join(body), coord)
            out["koordinator"] = st
            if st == "sent":
                delivered |= {x["key"] for x in reminders}
        else:
            out["koordinator"] = "alici_yok"
        critical = [e for e in ind_events if any((r["etki"] or 0) >= cfg["criticalImpact"] for r in by_kod.get(e["kod"], []))]
        crit_to = recipients("RISK_CRITICAL_RECIPIENTS")
        if critical and crit_to:
            out["kritik"] = _send_mail("Kritik risk göstergesi kırmızı", "\n".join(
                [f"- {x}" for x in R.indicator_alert_lines(critical, by_kod)] + foot), crit_to)
        elif critical:
            out["kritik"] = "alici_yok"
        per: dict[str, list[tuple[Optional[str], str]]] = {}
        for e, line in zip(ind_events, ind_lines):
            addrs = {e.get("sahipEposta")} | {r["sahipEposta"] for r in by_kod.get(e["kod"], [])}
            for a in addrs - {None, ""}:
                per.setdefault(a, []).append((None, line))
        for x in reminders:
            if x.get("eposta"):
                per.setdefault(x["eposta"], []).append((x["key"], x["metin"]))
        sent_owner = 0
        for addr, rows in per.items():
            st = _send_mail("Risk ve uyum: size düşen maddeler", "\n".join([f"- {t}" for _, t in rows] + foot), [addr])
            if st == "sent":
                sent_owner += 1
                delivered |= {k for k, _ in rows if k}
        out["sahip"] = {"adres": len(per), "gonderilen": sent_owner}
        if delivered:
            R.mark_sent(engine, tenant, delivered)
        out["iletilenHatirlatma"] = len(delivered)
        return out

    # ------------------------------------------------------------------ genel

    @app.get(P + "/meta")
    def risk_meta(request: Request) -> dict[str, Any]:
        _, _, user, display = ctx(request)
        return {"kategoriler": R.KATEGORILER, "durumlar": R.RISK_STATES, "egilimler": R.TRENDS, "kaynaklar": R.SOURCES,
                "aksiyonDurumlari": R.ACTION_STATES, "gostergeDurumlari": R.IND_STATES, "degerDurumlari": R.VALUE_STATES,
                "birimler": R.UNITS, "yonler": R.DIRECTIONS, "sikliklar": R.FREQ_LABELS, "alanlar": R.AREAS,
                "uyumSikliklari": R.COMP_FREQS, "donemDurumlari": R.EVENT_STATES, "bcpDurumlari": R.BCP_STATES,
                "raporDurumlari": R.REPORT_STATES, "seviyeler": R.LEVELS, "ayarlar": R.settings(),
                "me": {"username": user, "display": display, "canWrite": can(user, F_WRITE), "seeAll": can(user, F_ALL),
                       "canIndicator": can(user, F_IND), "canIndicatorApprove": can(user, F_IND_OK),
                       "canReportApprove": can(user, F_REPORT_OK), "canCompliance": can(user, F_COMP),
                       "canKvkk": can(user, F_KVKK), "canPolicy": can(user, F_POLICY), "canExport": can(user, F_EXPORT)},
                "modelVar": llm() is not None}

    @app.get(P + "/summary")
    def risk_summary(request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        ind = indicator_list(engine, tenant)
        out = call(R.summary, engine, tenant, user, see_all(user), ind)
        return PK.bagla(out, lambda: K.for_summary(engine, tenant, out, *dbs(), ind))

    @app.get(P + "/status")
    def risk_status(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return {"sonKosu": status["lastRun"], "olcumBekleyen": R.due_indicators(engine, tenant)}

    @app.get(P + "/kvkk")
    def risk_kvkk(request: Request) -> dict[str, Any]:
        """M49 kişisel veri envanteri bağlantı noktası. M49 modülü `app.state.data_security` üstünde
        `inventory_summary(engine, tenant) -> dict` verdiğinde özeti buraya gelir; yoksa ekran nedenini yazar."""
        engine, tenant, _, _ = ctx(request)
        ds = getattr(app.state, "data_security", None)
        fn = getattr(ds, "inventory_summary", None)
        if not callable(fn):
            return {"available": False, "message": "Kişisel veri işleme envanteri Veri güvenliği modülünde tutulur; bu kurulumda henüz yok."}
        try:
            return {"available": True, **fn(engine, tenant)}
        except Exception as e:  # noqa: BLE001
            log.warning("kvkk envanter özeti okunamadı: %s", e)
            return {"available": False, "message": "Kişisel veri envanteri şu an okunamadı."}

    # ------------------------------------------------------------------ riskler

    @app.get(P + "/risks")
    def risk_list(request: Request, durum: str = "canli", kategori: str = "", q: str = "", sahip: str = "", hucre: str = "") -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(R.list_risks, engine, tenant, user, see_all(user), durum=durum, kategori=kategori, q=q, sahip=sahip, hucre=hucre)
        return PK.bagla(out, lambda: K.for_list(engine, tenant))

    @app.post(P + "/risks", status_code=201)
    def risk_create(body: dict[str, Any], request: Request) -> dict[str, Any]:
        # Sahibi başka biri olabilir; açan kişi (olusturan) riski görmeye ve değiştirmeye devam eder.
        engine, tenant, user, _ = ctx(request)
        out = call(R.create_risk, engine, tenant, user, body)
        audit(engine, user, "create", "risk", out["id"], out["baslik"], {"kategori": out["kategori"], "puan": out["puan"],
                                                                         "gostergeler": out["gostergeler"]})
        return out

    @app.post(P + "/risks/classify")
    def risk_classify(body: dict[str, Any], request: Request) -> dict[str, Any]:
        ctx(request)
        choose = chooser()
        if choose is None:
            raise HTTPException(503, detail={"code": "RISK", "message": "Zeki AI bu kurulumda tanımlı değil."})
        text = " ".join(str(body.get(k) or "") for k in ("baslik", "tanim", "neden", "sonuc")).strip()
        if not text:
            raise HTTPException(400, detail={"code": "RISK", "message": "Önce başlık ya da tanım yazın."})
        out = R.classify(text, choose)
        if out is None:
            raise HTTPException(503, detail={"code": "RISK", "message": "Zeki AI kategori seçemedi; elle seçin."})
        return out

    @app.post(P + "/risks/suggest", status_code=202)
    def risk_suggest(request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        targets = R.suggestion_targets(engine, tenant, indicator_list(engine, tenant))
        chat, choose = chatter(900), chooser()

        def work() -> dict[str, Any]:
            made, notes = [], []
            for g in targets:
                facts = R.suggestion_facts(g)
                draft, source, note = R.draft_suggestion(facts, chat)
                cat = R.classify(" ".join(v for v in (draft.get("baslik"), draft.get("tanim")) if v), choose) if choose else None
                if cat is None:
                    spec = src.BY_CODE.get(g["kod"], {})
                    cat = {"kategori": spec.get("kategori") or "operasyonel", "emin": True}
                r = R.create_suggestion(engine, tenant, user, g, draft, cat)
                made.append({"id": r["id"], "baslik": r["baslik"], "kaynak": source, "gosterge": g["kod"]})
                if note:
                    notes.append(note)
                audit(engine, user, "create", "risk", r["id"], r["baslik"], {"oneri": True, "gosterge": g["kod"], "kaynak": source})
            return {"oneri": len(made), "items": made, "notlar": notes}

        return call(R.start_job, engine, tenant, user, "oneri", work)

    @app.get(P + "/risks/{rid}")
    def risk_detail(rid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        d = risk_for(engine, tenant, user, rid)
        d["yazabilir"] = can(user, F_WRITE) and (see_all(user) or owns(user, d["sahip"], d["olusturan"]))
        return PK.bagla(d, lambda: K.for_detail(engine, tenant, rid, d, *dbs()))

    @app.patch(P + "/risks/{rid}")
    def risk_update(rid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        risk_for(engine, tenant, user, rid, write=True)
        out, diff = call(R.update_risk, engine, tenant, user, rid, body)
        if diff:
            audit(engine, user, "update", "risk", rid, out["baslik"], diff)
        return out

    @app.post(P + "/risks/{rid}/review")
    def risk_review(rid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        d = risk_for(engine, tenant, user, rid, write=True)
        ind = {g["kod"]: g for g in R.indicators(engine, tenant)}
        triggers = [{"kod": k, "ad": ind[k]["ad"], "deger": (ind[k]["son"] or {}).get("deger"), "durum": (ind[k]["son"] or {}).get("durum")}
                    for k in d["gostergeler"] if k in ind]
        out = call(R.review_risk, engine, tenant, user, rid, body, triggers)
        audit(engine, user, "update", "risk_review", rid, out["baslik"],
              {"eskiPuan": d["puan"], "yeniPuan": out["puan"], "egilim": out["egilim"], "not": (body.get("not") or "")[:200]})
        return out

    @app.post(P + "/risks/{rid}/accept")
    def risk_accept(rid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        risk_for(engine, tenant, user, rid, write=True)
        out = call(R.accept_suggestion, engine, tenant, user, rid, True, body)
        audit(engine, user, "approve", "risk", rid, out["baslik"], {"oneri": "kabul", "puan": out["puan"]})
        return out

    @app.post(P + "/risks/{rid}/reject")
    def risk_reject(rid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        risk_for(engine, tenant, user, rid, write=True)
        out = call(R.accept_suggestion, engine, tenant, user, rid, False, body)
        audit(engine, user, "reject", "risk", rid, out["baslik"], {"oneri": "ret", "not": (body.get("not") or "")[:200]})
        return out

    @app.get(P + "/risks/{rid}/actions")
    def risk_actions(rid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        return {"items": risk_for(engine, tenant, user, rid)["aksiyonlar"]}

    @app.post(P + "/risks/{rid}/actions", status_code=201)
    def risk_action_add(rid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        d = risk_for(engine, tenant, user, rid, write=True)
        out = call(R.add_action, engine, tenant, user, rid, body)
        audit(engine, user, "create", "risk_action", out["id"], out["eylem"][:200], {"risk": rid, "riskBaslik": d["baslik"],
                                                                                     "sahip": out["sahip"], "termin": out["termin"]})
        return out

    def action_guard(engine, tenant, user, aid) -> tuple[dict[str, Any], dict[str, Any], bool]:
        a, r = call(R.action_scope, engine, tenant, aid)
        full = can(user, F_WRITE) and (see_all(user) or owns(user, r["sahip"], r["olusturan"]))
        if not (full or owns(user, a["sahip"], r["sahip"])):
            raise HTTPException(403, detail={"code": "FORBIDDEN", "message": "Bu aksiyonu yalnız sahibi ya da riskin sahibi güncelleyebilir."})
        return a, r, full

    @app.patch(P + "/actions/{aid}")
    def risk_action_update(aid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        _, r, full = action_guard(engine, tenant, user, aid)
        out, diff = call(R.update_action, engine, tenant, user, aid, body, full=full)
        if diff:
            audit(engine, user, "update", "risk_action", aid, out["eylem"][:200], {"risk": r["id"], **diff})
        return out

    @app.post(P + "/actions/{aid}/evidence")
    async def risk_action_evidence(aid: str, request: Request, filename: str = "") -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        _, r, _ = await run_in_threadpool(action_guard, engine, tenant, user, aid)
        data = await body_bytes(request)
        out = await run_in_threadpool(call, R.attach_action_evidence, engine, tenant, aid, filename, data)
        audit(engine, user, "upload", "risk_action", aid, out["kanitAd"], {"risk": r["id"], "bytes": len(data)})
        return out

    @app.get(P + "/actions/{aid}/evidence")
    def risk_action_evidence_file(aid: str, request: Request):
        engine, tenant, user, _ = ctx(request)
        a, r = call(R.action_scope, engine, tenant, aid)
        if not R.visible(r, user, see_all(user), [a["sahip"]]):
            raise HTTPException(404, detail={"code": "RISK", "message": "Dosya bulunamadı."})
        return send_file(*call(R.file_of, R.ACTIONS, engine, tenant, aid, "kanit"))

    # ------------------------------------------------------------------ göstergeler

    @app.get(P + "/indicators")
    def risk_indicators(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        out = {"items": indicator_list(engine, tenant), "kutuphane": [{k: v for k, v in s.items()} for s in src.LIBRARY]}
        return PK.bagla(out, lambda: K.for_indicators(engine, tenant, out, *dbs()))

    @app.post(P + "/indicators", status_code=201)
    def risk_indicator_propose(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, F_IND, "Gösterge tanımı")
        R.seed_library(engine, tenant, src.LIBRARY)
        out = call(R.propose_indicator, engine, tenant, user, body, src.BY_CODE)
        audit(engine, user, "create", "risk_indicator", out["kod"], out["ad"],
              {"surum": out["surum"], "sari": out["esikSari"], "kirmizi": out["esikKirmizi"], "yon": out["yon"], "sahip": out["sahip"]})
        return out

    @app.post(P + "/indicators/{kod}/approve")
    def risk_indicator_approve(kod: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, F_IND_OK, "Gösterge onayı")
        out = call(R.decide_indicator, engine, tenant, user, kod, True, body.get("not"))
        audit(engine, user, "approve", "risk_indicator", kod, out["ad"], {"surum": out["surum"], "sari": out["esikSari"],
                                                                           "kirmizi": out["esikKirmizi"]})
        return out

    @app.post(P + "/indicators/{kod}/reject")
    def risk_indicator_reject(kod: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, F_IND_OK, "Gösterge onayı")
        out = call(R.decide_indicator, engine, tenant, user, kod, False, body.get("not"))
        audit(engine, user, "reject", "risk_indicator", kod, out["ad"], {"surum": out["surum"], "not": body.get("not")})
        return out

    @app.get(P + "/indicators/{kod}/values")
    def risk_indicator_values(kod: str, request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        out = call(R.indicator_values, engine, tenant, kod)
        return PK.bagla(out, lambda: K.for_values(engine, tenant, kod, *dbs()))

    @app.post(P + "/indicators/{kod}/measure")
    async def risk_indicator_measure(kod: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        need(user, F_IND, "Göstergeyi ölçme")
        if kod not in src.BY_CODE:
            raise HTTPException(404, detail={"code": "RISK", "message": "Gösterge bulunamadı."})

        def run() -> dict[str, Any]:
            if not measure_lock.acquire(blocking=False):
                raise R.RiskError("Başka bir ölçüm sürüyor; biraz sonra deneyin.", 409)
            try:
                R.seed_library(engine, tenant, src.LIBRARY)
                res = src.measure(context(engine, tenant), kod)
                out, note = R.record_measure(engine, tenant, kod, res, user)
            finally:
                measure_lock.release()
            if note:
                out["bildirim"] = note
                out["eposta"] = notify(engine, tenant, [{**out, "bildirim": note}], [])
            return out

        out = await run_in_threadpool(call, run)
        audit(engine, user, "run", "risk_indicator", kod, out["ad"], {"deger": out["deger"], "durum": out["durum"], "hata": out["hata"]})
        return await run_in_threadpool(PK.bagla, out, lambda: K.for_measure(engine, tenant, kod, out, *dbs()))

    # ------------------------------------------------------------------ uyum

    def comp_guard(user: str, area: str) -> None:
        if area == "kvkk":
            need(user, F_KVKK, "KVKK uyum maddesi")

    @app.get(P + "/compliance/items")
    def risk_comp_items(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        out = R.compliance_items(engine, tenant)
        return PK.bagla(out, lambda: K.for_compliance(engine, tenant, out))

    @app.post(P + "/compliance/items", status_code=201)
    def risk_comp_item_add(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        comp_guard(user, str(body.get("alan") or ""))
        out, _ = call(R.save_item, engine, tenant, user, None, body)
        audit(engine, user, "create", "compliance_item", out["id"], out["madde"][:200], {"alan": out["alan"], "siklik": out["siklik"],
                                                                                         "ilkSonGun": out["ilkSonGun"]})
        return out

    @app.patch(P + "/compliance/items/{iid}")
    def risk_comp_item_update(iid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        comp_guard(user, call(R.item_area, engine, tenant, iid))
        if "alan" in body:
            comp_guard(user, str(body.get("alan") or ""))
        out, diff = call(R.save_item, engine, tenant, user, iid, body)
        if diff:
            audit(engine, user, "update", "compliance_item", iid, out["madde"][:200], diff)
        return out

    @app.get(P + "/compliance/calendar")
    def risk_comp_calendar(request: Request, ay: str = "") -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        out = call(R.calendar, engine, tenant, ay)
        return PK.bagla(out, lambda: K.for_compliance(engine, tenant, out, out["ay"]))

    @app.post(P + "/compliance/events/{eid}/evidence")
    async def risk_comp_evidence(eid: str, request: Request, filename: str = "", note: str = "") -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        comp_guard(user, await run_in_threadpool(call, R.event_area, engine, tenant, eid))
        data = await body_bytes(request)
        out = await run_in_threadpool(call, R.attach_event_evidence, engine, tenant, user, eid, filename, data, note)
        audit(engine, user, "upload", "compliance_event", eid, out["kanitAd"], {"donem": out["donem"], "bytes": len(data)})
        return out

    @app.get(P + "/compliance/events/{eid}/evidence")
    def risk_comp_evidence_file(eid: str, request: Request):
        engine, tenant, user, _ = ctx(request)
        comp_guard(user, call(R.event_area, engine, tenant, eid))      # KVKK kanıtı yalnız KVKK yetkilisine
        return send_file(*call(R.file_of, R.COMP_EVENTS, engine, tenant, eid, "kanit"))

    @app.post(P + "/compliance/events/{eid}/close")
    def risk_comp_close(eid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        comp_guard(user, call(R.event_area, engine, tenant, eid))
        out = call(R.close_event, engine, tenant, user, eid, str(body.get("not") or ""))
        audit(engine, user, "update", "compliance_event", eid, out["donem"], {"durum": "kapandi", "kanit": out["kanitVar"]})
        return out

    # ------------------------------------------------------------------ sigorta ve BCP

    @app.get(P + "/policies")
    def risk_policies(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        out = R.policies(engine, tenant)
        return PK.bagla(out, lambda: K.for_manual(engine, tenant, out, "police"))

    @app.post(P + "/policies", status_code=201)
    def risk_policy_add(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out, _ = call(R.save_policy, engine, tenant, user, None, body)
        audit(engine, user, "create", "risk_policy", out["id"], out["tur"], {"bit": out["bit"], "sigortaci": out["sigortaci"]})
        return out

    @app.patch(P + "/policies/{pid}")
    def risk_policy_update(pid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out, diff = call(R.save_policy, engine, tenant, user, pid, body)
        if diff:
            audit(engine, user, "update", "risk_policy", pid, out["tur"], diff)
        return out

    @app.delete(P + "/policies/{pid}")
    def risk_policy_delete(pid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        old = call(R.delete_row, engine, R.POLICIES, tenant, pid, "Poliçe", "belge_yolu")
        audit(engine, user, "delete", "risk_policy", pid, old["tur"])
        return {"ok": True}

    @app.post(P + "/policies/{pid}/document")
    async def risk_policy_document(pid: str, request: Request, filename: str = "") -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        data = await body_bytes(request)
        out = await run_in_threadpool(call, R.attach_policy_document, engine, tenant, pid, filename, data)
        audit(engine, user, "upload", "risk_policy", pid, out["belgeAd"], {"bytes": len(data)})
        return out

    @app.get(P + "/policies/{pid}/document")
    def risk_policy_document_file(pid: str, request: Request):
        engine, tenant, _, _ = ctx(request)
        return send_file(*call(R.file_of, R.POLICIES, engine, tenant, pid, "belge"))

    @app.get(P + "/bcp")
    def risk_bcp(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        out = R.bcp(engine, tenant)
        return PK.bagla(out, lambda: K.for_manual(engine, tenant, out, "bcp"))

    @app.post(P + "/bcp", status_code=201)
    def risk_bcp_add(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out, _ = call(R.save_bcp, engine, tenant, user, None, body)
        audit(engine, user, "create", "risk_bcp", out["id"], out["surec"], {"kritiklik": out["kritiklik"]})
        return out

    @app.patch(P + "/bcp/{bid}")
    def risk_bcp_update(bid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out, diff = call(R.save_bcp, engine, tenant, user, bid, body)
        if diff:
            audit(engine, user, "update", "risk_bcp", bid, out["surec"], diff)
        return out

    @app.delete(P + "/bcp/{bid}")
    def risk_bcp_delete(bid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        old = call(R.delete_row, engine, R.BCP, tenant, bid, "Süreç")
        audit(engine, user, "delete", "risk_bcp", bid, old["surec"])
        return {"ok": True}

    # ------------------------------------------------------------------ brifing

    @app.get(P + "/reports")
    def risk_reports(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        out = R.reports(engine, tenant)
        return PK.bagla(out, lambda: K.for_reports(engine, tenant, out))

    @app.post(P + "/reports/draft", status_code=202)
    def risk_report_draft(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        donem = str(body.get("donem") or R.quarter_of(R.today())).strip()[:20]
        # Brifing kurul içindir: bütün riskler (kişinin görünürlüğünden bağımsız) girdi olur; bu yüzden yalnız
        # bütün riskleri görebilen hazırlatır.
        need(user, F_ALL, "Bütün riskleri görme")
        ind = indicator_list(engine, tenant)
        facts = R.report_facts(R.summary(engine, tenant, user, True, ind), ind, donem)
        rid = R.start_report(engine, tenant, user, donem, facts)
        chat = chatter(3000, "batch")

        def work() -> dict[str, Any]:
            try:
                text, source, note = R.draft_report_text(facts, chat)
            except Exception:
                R.finish_report(engine, rid, None, None, "Taslak hazırlanamadı.", error=True)
                raise
            R.finish_report(engine, rid, text, source, note)
            return {"raporId": rid, "kaynak": source, "not": note}

        job = call(R.start_job, engine, tenant, user, "brifing", work)
        audit(engine, user, "run", "risk_report", rid, f"Risk brifingi {donem}", {"is": job["id"]})
        return {**job, "raporId": rid}

    @app.get(P + "/reports/{rid}")
    def risk_report(rid: str, request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        out = call(R.report, engine, tenant, rid)
        return PK.bagla(out, lambda: K.for_reports(engine, tenant, out, rid))

    @app.patch(P + "/reports/{rid}")
    def risk_report_edit(rid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(R.edit_report, engine, tenant, user, rid, str(body.get("metin") or ""))
        audit(engine, user, "update", "risk_report", rid, f"Risk brifingi {out['donem']}", {"karakter": len(out["metin"] or "")})
        return out

    @app.post(P + "/reports/{rid}/approve")
    def risk_report_approve(rid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, F_REPORT_OK, "Brifing onayı")
        out = call(R.approve_report, engine, tenant, user, rid)
        audit(engine, user, "approve", "risk_report", rid, f"Risk brifingi {out['donem']}", {"girdiHash": out["girdiHash"]})
        return out

    @app.get(P + "/reports/{rid}/document.docx")
    def risk_report_docx(rid: str, request: Request) -> Response:
        from semantic_bridge.contracts_docs import docx_from_text

        engine, tenant, user, _ = ctx(request)
        d = call(R.report, engine, tenant, rid)
        if not d.get("metin"):
            raise HTTPException(409, detail={"code": "RISK", "message": "Raporun metni henüz yok."})
        data = docx_from_text(d["metin"], f"Risk brifingi {d['donem']}")
        audit(engine, user, "run", "risk_export", rid, f"Risk brifingi {d['donem']} (Word)", {"durum": d["durum"]})
        return Response(data, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        headers={"Content-Disposition": f'attachment; filename="risk-brifingi-{d["donem"]}.docx"'})

    @app.get(P + "/jobs/{jid}")
    def risk_job(jid: str, request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return call(R.job, engine, tenant, jid)

    # ------------------------------------------------------------------ zamanlayıcı

    @app.post(P + "/run-due")
    def risk_run_due(request: Request) -> dict[str, Any]:
        """Zamanlayıcı: sıklığı gelen göstergeleri ölçer, kenar bildirimi ve hatırlatmaları gönderir, uyum ufkunu açar."""
        require_caller(request)
        r = rt()
        engine, tenant = r.store.engine, r.settings.tenant_id
        R.ensure(engine)
        started = datetime.now(timezone.utc)
        seeded = R.seed_library(engine, tenant, src.LIBRARY)
        codes = R.due_indicators(engine, tenant)
        events, measured = [], []
        if codes and measure_lock.acquire(timeout=1800):
            try:
                c = context(engine, tenant)
                for kod in codes:
                    res = src.measure(c, kod)
                    try:
                        out, note = R.record_measure(engine, tenant, kod, res, "sistem")
                    except R.RiskError as e:
                        measured.append({"kod": kod, "hata": str(e)})
                        continue
                    measured.append({"kod": kod, "deger": out["deger"], "durum": out["durum"], "hata": out["hata"]})
                    if note:
                        events.append({**out, "bildirim": note})
            finally:
                measure_lock.release()
        opened = R.generate_events(engine, tenant)
        reminders = R.due_reminders(engine, tenant)
        mail = notify(engine, tenant, events, reminders)
        result = {"basladi": started.isoformat(), "bitti": datetime.now(timezone.utc).isoformat(), "yeniTanim": seeded,
                  "olculen": measured, "kirmiziBildirim": len(events), "hatirlatma": len(reminders), "acilanDonem": opened,
                  "eposta": mail}
        status["lastRun"] = result
        return result

    return status
