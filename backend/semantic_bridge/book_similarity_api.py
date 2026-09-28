"""Kitap benzerliği dizini uçları: /api/v1/books/similar/*.

`GET status` (oturum yeter): dizindeki kitap sayısı, son koşu. `POST index` (yönetici ya da zamanlayıcı): arka planda
CRM'den oku + artımlı dizin; `?sifirdan=1` dizini boşaltıp baştan kurar (gömme servisi değiştiğinde). `POST run-due`
(zamanlayıcı `timas-book-similar.timer`): aynı iş, süre bütçesiyle (`BOOK_SIMILAR_SECONDS`, varsayılan 3000 sn); bitmeyen
kitaplar sonraki tura kalır. Arama ayrı bir uç değildir: her ekran kendi yetkisiyle `book_similarity.similar_books`'u
çağırır (M15, M39, SEO, M1). CRM'e yazılmaz.
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Any, Callable

from fastapi import HTTPException, Request

from semantic_bridge import book_similarity as BS

log = logging.getLogger("semantic.book_similarity.api")
B = "/api/v1/books/similar"


def register(app, rt: Callable[[], Any], require_caller: Callable[[Request], None], can: Callable[[str, str], bool]):
    from semantic_bridge import admin as admin_mod
    from semantic_bridge import board as board_mod

    job: dict[str, Any] = {"thread": None, "state": {"running": False, "startedAt": None, "finishedAt": None,
                                                     "error": None, "result": None, "done": 0, "total": 0}}
    lock = threading.Lock()

    def engine_tenant() -> tuple[Any, str]:
        r = rt()
        BS.ensure(r.store.engine)
        return r.store.engine, r.settings.tenant_id

    def user_of(request: Request) -> str:
        require_caller(request)
        cookie = request.headers.get("cookie", "")
        if "timas_session" not in cookie:
            return "zamanlayici"
        try:
            user, _ = board_mod.session_of(cookie)
        except board_mod.NoUser:
            raise HTTPException(status_code=401, detail={"code": "UNAUTHORIZED", "message": "Oturum gerekli."}) from None
        return user

    def running() -> bool:
        t = job["thread"]
        return bool(t and t.is_alive())

    def start(engine, tenant: str, user: str, fresh: bool) -> bool:
        with lock:
            if running():
                return False
            st = job["state"]

            def progress(done: int, total: int) -> None:
                st.update(done=done, total=total)

            def work() -> None:
                st.update(running=True, startedAt=BS.now().isoformat(), finishedAt=None, error=None, result=None, done=0, total=0)
                try:
                    if fresh:
                        BS.reset(engine, tenant)
                    st["result"] = BS.refresh(engine, tenant, progress=progress)
                except Exception as e:  # noqa: BLE001
                    log.warning("kitap benzerliği dizini kurulamadı: %s", e)
                    st["error"] = str(e)[:400]
                finally:
                    st.update(running=False, finishedAt=BS.now().isoformat())

            job["thread"] = threading.Thread(target=work, name="book-similar-index", daemon=True)
            job["thread"].start()
            admin_mod.audit(engine, user, "run", "book_similarity", None, "Kitap benzerliği dizini",
                            {"sifirdan": fresh})
            return True

    @app.get(B + "/status")
    def book_similar_status(request: Request) -> dict[str, Any]:
        require_caller(request)
        engine, tenant = engine_tenant()
        return {**BS.status(engine, tenant), "is": {**job["state"], "running": running()}}

    @app.post(B + "/index", status_code=202)
    def book_similar_index(request: Request, sifirdan: bool = False) -> dict[str, Any]:
        user = user_of(request)
        if user != "zamanlayici" and not admin_mod.is_admin(user):
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "Dizin kurma yöneticiye aittir."})
        engine, tenant = engine_tenant()
        return {"started": start(engine, tenant, user, bool(sifirdan)), "is": job["state"]}

    @app.post(B + "/run-due")
    def book_similar_run_due(request: Request) -> dict[str, Any]:
        """Zamanlayıcı: CRM'den oku, değişen kitapları göm (süre bütçesiyle)."""
        require_caller(request)
        engine, tenant = engine_tenant()
        if running():
            return {"skipped": "dizin kurma zaten sürüyor"}
        try:
            seconds = float(os.environ.get("BOOK_SIMILAR_SECONDS", "3000") or 3000)
        except ValueError:
            seconds = 3000.0
        try:
            return BS.refresh(engine, tenant, seconds=seconds)
        except BS.SimilarityError as e:
            raise HTTPException(status_code=e.status, detail={"code": "BOOK_SIMILAR", "message": str(e)}) from e

    return {"status": lambda: BS.status(*engine_tenant())}
