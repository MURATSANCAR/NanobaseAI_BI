"""Köprünün bütün 403 cevapları `FORBIDDEN` koduyla çıkar.

Ön yüz sözleşmesi (`src/canvas/engine.ts` → `send`): 401 = oturum yok; 403 yalnız `detail.code === 'FORBIDDEN'` ise
«bu iş rolünüzde yok» sayılır, başka kodlu 403 «oturum düştü» sayılır ve kişi oturumdan atılmış gibi görür. Modüllerin
çoğu kendi hata sınıfını (`FieldError(…, 403)`, `HrError(…, 403)` …) tek bir kodla (`FIELD`, `HR` …) HTTP'ye çeviriyordu;
kabulde (2026-09-28, M30) bu, yetki reddini oturum düşmesine çevirdi. Modülleri tek tek yamamak yeni modülde aynı hatayı
yeniden açar; bu yüzden kural tek yerde: köprü uygulamasına kurulan HTTPException işleyicisi 403'ün kodunu FORBIDDEN
yapar, modülün kendi kodu `module` alanında kalır. 403 dışındaki cevaplar olduğu gibi geçer.
"""
from __future__ import annotations

from typing import Any

FORBIDDEN = "FORBIDDEN"
DEFAULT_MESSAGE = "Bu işlem rolünüzde yok."


def forbidden_detail(detail: Any) -> Any:
    """403 gövdesinin `detail`'i: kod FORBIDDEN; modülün kodu `module`'de; düz metin mesaj sözlüğe çevrilir."""
    if isinstance(detail, dict):
        code = detail.get("code")
        if code == FORBIDDEN:
            return detail
        out = {**detail, "code": FORBIDDEN}
        if code:
            out["module"] = code
        if not out.get("message"):
            out["message"] = DEFAULT_MESSAGE
        return out
    if detail is None or isinstance(detail, str):
        return {"code": FORBIDDEN, "message": detail or DEFAULT_MESSAGE}
    return detail


def install(app: Any) -> None:
    """FastAPI uygulamasına HTTPException işleyicisi kurar (403 → FORBIDDEN; diğerleri FastAPI'nin varsayılanıyla)."""
    from fastapi import HTTPException
    from fastapi.exception_handlers import http_exception_handler
    from starlette.exceptions import HTTPException as StarletteHTTPException

    async def _handler(request: Any, exc: StarletteHTTPException):
        if exc.status_code == 403:
            exc = HTTPException(status_code=403, detail=forbidden_detail(exc.detail), headers=getattr(exc, "headers", None))
        return await http_exception_handler(request, exc)

    app.add_exception_handler(StarletteHTTPException, _handler)
