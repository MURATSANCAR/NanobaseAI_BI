"""Kampüs «Bugün» özeti uçları: /api/v1/bugun (AI fırsatları öneri 19).

Oturum yeter (`access.RULES` OPEN); her kaynak kişinin kendi yetkisiyle köprüde süzülür (`today_brief.collect`). Zeki AI
özeti yalnız `POST /api/v1/bugun/ozet` ile (kişi paneli açınca), LLM kapısından `rt.llm_for("bugun", NORMAL)`.
"""
from __future__ import annotations

import logging
from typing import Any, Callable

from fastapi import HTTPException, Request
from starlette.concurrency import run_in_threadpool

from semantic_bridge import today_brief as T

log = logging.getLogger("semantic.today_brief.api")
P = "/api/v1/bugun"


def register(app, rt: Callable[[], Any], require_caller: Callable[[Request], None], can: Callable[[str, str], bool]):
    from semantic_bridge import admin as admin_mod
    from semantic_bridge import board as board_mod

    def ctx(request: Request) -> tuple[Any, str, str]:
        require_caller(request)
        try:
            user, _display = board_mod.session_of(request.headers.get("cookie", ""))
        except board_mod.NoUser:
            raise HTTPException(status_code=401, detail={"code": "UNAUTHORIZED", "message": "Oturum gerekli."}) from None
        r = rt()
        T.ensure(r.store.engine)
        return r.store.engine, r.settings.tenant_id, user

    def flag_of(user: str) -> Callable[[str], bool]:
        admin = admin_mod.is_admin(user)
        return lambda key: admin or can(user, key)

    def llm():
        try:
            from semantic_layer.runtime.llm_queue import NORMAL
            return rt().llm_for("bugun", NORMAL)
        except Exception:  # noqa: BLE001 — model tanımlı değil
            return None

    def view(engine, tenant: str, user: str) -> dict[str, Any]:
        out = T.collect(engine, tenant, user, flag_of(user), T.settings(admin_mod.conf))
        out["ozet"] = T.cached(engine, tenant, user, out["gun"], out["items"])
        out["modelVar"] = llm() is not None
        return out

    @app.get(P)
    async def today_view(request: Request) -> dict[str, Any]:
        engine, tenant, user = await run_in_threadpool(ctx, request)
        return await run_in_threadpool(view, engine, tenant, user)

    @app.post(P + "/ozet")
    async def today_summary(request: Request) -> dict[str, Any]:
        engine, tenant, user = await run_in_threadpool(ctx, request)
        m = llm()
        if m is None:
            raise HTTPException(503, detail={"code": "BUGUN", "message": "Zeki AI bu kurulumda bağlı değil; kural özeti gösteriliyor."})
        data = await run_in_threadpool(T.collect, engine, tenant, user, flag_of(user), T.settings(admin_mod.conf))
        try:
            await run_in_threadpool(T.write, engine, tenant, user, data["gun"], data["items"], m)
        except Exception as e:  # noqa: BLE001 — model düştüyse kural özeti kalır
            log.warning("bugün özeti yazılamadı: %s", e)
            raise HTTPException(503, detail={"code": "BUGUN", "message": "Zeki AI şu an cevap vermedi; kural özeti gösteriliyor."}) from e
        return await run_in_threadpool(view, engine, tenant, user)

    return {"view": view}
