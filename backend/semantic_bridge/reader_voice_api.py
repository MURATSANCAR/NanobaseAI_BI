"""Okur sesi uçları: /api/v1/okur-sesi/* (AI fırsatları öneri 15).

Sayfa kapısı `access.RULES`: okur yorumları (M37), Trendyol soru/yorum ve sipariş/iade (M40), üretim (M12) sayfaları.
Kaynak süzgeci ucun içinde: kişi yalnız sayfa yetkisi olan kaynağın etiketini görür. Baskı hatası uyarısını «görüldü»
işaretlemek üretim sayfası (`sayfa:uretim`) ister.

Zamanlayıcı (`timas-okur-sesi.timer`, her gece 04:20; M37 03:50 ve M40 panel yüklemelerinden sonra) yalnız
`POST /api/v1/okur-sesi/run-due`'yu çağırır: site yorumlarını (T-soft, yalnız okuma) ve M40 tablolarını okur, yeni ya da
metni değişmiş kayıtları sınıflar (kural → M40 iade nedeni → Zeki AI `choose`, BATCH), baskı hatası kümelerini uyarıya
çevirir, iç alıcı ayarı doluysa iç e-posta atar. Model yalnız LLM kapısından: `rt.llm_for("okur-sesi", BATCH)`.
"""
from __future__ import annotations

import logging
from typing import Any, Callable

from fastapi import HTTPException, Request
from starlette.concurrency import run_in_threadpool

from semantic_bridge import provenance as PV
from semantic_bridge import reader_voice as V
from semantic_bridge import signals_kaynak as SK

log = logging.getLogger("semantic.reader_voice.api")
P = "/api/v1/okur-sesi"

#: Kaynak → ekranın sayfa anahtarı (etiket yalnız o sayfayı görene gider).
SOURCE_PAGES = {
    "site-yorum": ("sayfa:okur-yorumlar",),
    "trendyol-soru": ("sayfa:trendyol-sorular",),
    "trendyol-yorum": ("sayfa:trendyol-sorular",),
    "trendyol-iade": ("sayfa:trendyol-siparisler",),
}
PAGE_PRODUCTION = "sayfa:uretim"


def register(app, rt: Callable[[], Any], require_caller: Callable[[Request], None], can: Callable[[str, str], bool]):
    from semantic_bridge import admin as admin_mod
    from semantic_bridge import board as board_mod

    def st() -> dict[str, Any]:
        return V.settings(admin_mod.conf)

    def db() -> tuple[Any, str]:
        r = rt()
        V.ensure(r.store.engine)
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

    def sees(user: str, src: str) -> bool:
        return admin_mod.is_admin(user) or any(can(user, k) for k in SOURCE_PAGES.get(src, ()))

    def production(user: str) -> bool:
        return admin_mod.is_admin(user) or can(user, PAGE_PRODUCTION)

    def call(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except V.VoiceError as e:
            raise HTTPException(status_code=e.status, detail={"code": "OKUR_SESI", "message": str(e)}) from e

    def llm():
        try:
            from semantic_layer.runtime.llm_queue import BATCH
            return rt().llm_for("okur-sesi", BATCH)
        except Exception:  # noqa: BLE001 — model tanımlı değil
            return None

    def link() -> str:
        base = (admin_mod.conf("ALERT_LINK") or "").split("/uyarilar")[0]
        return f"{base}/okur-toplulugu/yorumlar" if base else ""

    def internal_mail(subject: str, body: str, to: list[str]) -> str:
        """Yalnız iç alıcılar: izinli alan adı ayarı doluysa dışındaki adrese gitmez."""
        from semantic_bridge.budget_api import _send_mail

        allowed = [d.strip().lower().lstrip("@") for d in (admin_mod.conf("ALERT_RECIPIENT_DOMAINS") or "").split(",") if d.strip()]
        to = [x for x in to if not allowed or x.lower().rsplit("@", 1)[-1] in allowed]
        return _send_mail(subject, body, to) if to else "alici_yok"

    # ------------------------------------------------------------------ okuma

    @app.get(P + "/labels")
    def voice_labels(request: Request, kaynak: str = "") -> dict[str, Any]:
        engine, tenant, user = ctx(request)
        if kaynak not in V.SOURCES:
            raise HTTPException(400, detail={"code": "OKUR_SESI", "message": "Bilinmeyen kaynak."})
        if not sees(user, kaynak):
            raise HTTPException(403, detail={"code": "FORBIDDEN", "message": "Bu kaynağın ekranı rolünüzde yok."})
        out = {"items": call(V.labels, engine, tenant, kaynak), "konular": V.TOPICS}
        return PV.bagla(out, lambda: SK.for_voice_labels(engine, tenant, kaynak))

    @app.get(P + "/summary")
    def voice_summary(request: Request) -> dict[str, Any]:
        engine, tenant, user = ctx(request)
        s = st()
        out = V.summary(engine, tenant, s)
        out["kaynakKonu"] = {k: v for k, v in out["kaynakKonu"].items() if sees(user, k)}
        out["toplam"] = {k: sum(v[k] for v in out["kaynakKonu"].values()) for k in (*V.TOPICS, "belirsiz")}
        out["uyarilar"] = V.alerts(engine, tenant)
        out["uretim"] = production(user)
        out["ayarlar"] = {k: s[k] for k in ("minProb", "minMargin", "defectDays", "defectMin", "windowDays")}
        out["ayarlar"]["iceAlici"] = len(s["recipients"])
        out["sonKosu"] = V.meta_get(engine, tenant, "run") or None
        return PV.bagla(out, lambda: SK.for_voice_summary(engine, tenant, s, out))

    @app.post(P + "/alerts/{key}/seen")
    def voice_alert_seen(key: str, request: Request) -> dict[str, Any]:
        engine, tenant, user = ctx(request)
        if not production(user):
            raise HTTPException(403, detail={"code": "FORBIDDEN", "message": "Baskı hatası uyarısını üretim sayfası yetkisi olan işaretler."})
        out = call(V.mark_seen, engine, tenant, user, key)
        admin_mod.audit(engine, user, "update", "okur_sesi_uyari", key, out.get("ad") or key, {"durum": out["durum"]})
        return out

    # ------------------------------------------------------------------ zamanlayıcı

    def run_due(engine, tenant: str, force: bool = False) -> dict[str, Any]:
        s = st()
        out: dict[str, Any] = {"kaynak": {}}
        items: list[dict[str, Any]] = []
        comments = getattr(app.state, "okur", None)
        if comments is not None and hasattr(comments, "read"):
            try:
                from semantic_bridge import okur as O

                rows = comments.read(O.settings()["reviewCacheSeconds"], True)
                site = V.site_items(engine, tenant, rows)
                items += site
                out["kaynak"]["site-yorum"] = len(site)
            except Exception as e:  # noqa: BLE001 — T-soft kapalıysa Trendyol yine sınıflanır
                out["kaynak"]["site-yorum"] = {"hata": str(e)[:200]}
        else:
            out["kaynak"]["site-yorum"] = {"hata": "okur topluluğu modülü bağlı değil"}
        try:
            ty = V.trendyol_items(engine, tenant)
            items += ty
            out["kaynak"]["trendyol"] = len(ty)
        except Exception as e:  # noqa: BLE001
            out["kaynak"]["trendyol"] = {"hata": str(e)[:200]}
        out["siniflama"] = V.classify(engine, tenant, items, llm(), s, force=force)
        found = V.clusters(engine, tenant, s)
        out["kume"] = V.sync_alerts(engine, tenant, found)
        due = V.due_notifications(engine, tenant)
        mail = "yok"
        if due:
            if s["recipients"]:
                mail = internal_mail(f"Okur sesi: {len(due)} kitapta baskı/cilt hatası kümesi", V.notify_text(due, s, link()),
                                     s["recipients"])
            else:
                mail = "alici_yok"          # yalnız ekranda
            V.record_notification(engine, tenant, due, mail)
        out["eposta"] = {"sonuc": mail, "uyari": len(due), "alici": len(s["recipients"])}
        V.meta_set(engine, tenant, "run", {k: v for k, v in out.items()})
        return out

    @app.post(P + "/run-due")
    async def voice_run_due(request: Request, force: bool = False) -> dict[str, Any]:
        require_caller(request)
        engine, tenant = db()
        return await run_in_threadpool(run_due, engine, tenant, force)

    return {"run_due": run_due}
