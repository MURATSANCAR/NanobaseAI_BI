"""Fark ayrıştırma uçları (`/api/v1/fark/*`): sohbet cevabının altındaki «Neden?» ve pano kartı.

- `POST /api/v1/fark/ayristir` {queryId | question, karsi: gecen-yil|onceki-donem, boyutlar?, anlat?} → ayrıştırma +
  anlatım. `queryId` sohbet cevabının kaydıdır: soru kaydedildiği hâliyle (konuşma bağlamı dahil) çözülmüş olarak okunur,
  yeniden çözülmez; yalnız soran kişi (ya da yönetici) kullanır. `question` pano kartı ve uyarı içindir: soru çözümleyiciden
  bağlamsız geçer. SQL köprünün `run_complete` yolundan koşar (yetki kapsamı, yıl kopyaları, önbellek sohbetle aynı).
- `POST /api/v1/fark/ipucu` {queryId | question} → yalnız «ayrıştırılabilir mi» (SQL koşmaz).

Rakamlar SQL'den; Zeki AI yalnız 2–3 cümle anlatır ve metindeki her sayı olgularla denetlenir. Her cevapta çalıştırılan
tam SQL `kaynak.sql` alanındadır (ekrandaki «sorgu bilgisi»ne bağlanır).
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from fastapi import HTTPException, Request

from semantic_bridge import variance as V

log = logging.getLogger(__name__)


def rows_of(r: Any, out: dict[str, Any]) -> list[dict[str, Any]]:
    path = out.get("_result_file")
    return r.result_files.read(path) if path else list(out.get("records") or [])


def runner_for(r: Any) -> V.Runner:
    def run(sql: str, period: Optional[tuple]) -> list[dict[str, Any]]:
        return rows_of(r, r.run_complete(sql, period))
    return run


def logged_query(r: Any, query_id: str, user: Optional[str], is_admin: Callable[[str], bool]) -> dict[str, Any]:
    """Sohbet kaydındaki çözüm (konuşma bağlamıyla). Başkasının kaydı okunmaz."""
    import sqlalchemy as sa
    from semantic_layer.store import schema as S

    t = S.sl_query_log
    with r.store.engine.connect() as c:
        row = c.execute(sa.select(t.c.resolved_json, t.c.username, t.c.question).where(
            t.c.id == str(query_id)[:64], t.c.tenant_id == r.settings.tenant_id)).mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Cevap kaydı bulunamadı."})
    owner = (row["username"] or "").strip().lower()
    if owner and user and owner != user.strip().lower() and not is_admin(user):
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Cevap kaydı bulunamadı."})
    resolved = row["resolved_json"]
    if isinstance(resolved, str):
        import json

        resolved = json.loads(resolved or "{}")
    return resolved or {}


def resolve(r: Any, body: dict[str, Any], user: Optional[str], is_admin: Callable[[str], bool]) -> Any:
    qid = str(body.get("queryId") or "").strip()
    if qid:
        return logged_query(r, qid, user, is_admin)
    q = " ".join(str(body.get("question") or "").split())
    if not q:
        raise HTTPException(status_code=422, detail={"code": "INVALID", "message": "Cevap kaydı ya da soru gerekli."})
    return r.resolver.resolve(q[:2000])


def register(app: Any, rt: Callable[[], Any], require_caller: Callable[[Request], Any], user_of: Callable[[Request], str],
             is_admin: Callable[[str], bool], audit: Callable[..., Any]) -> None:
    P = "/api/v1/fark"

    @app.post(f"{P}/ipucu")
    def fark_hint(request: Request, body: dict[str, Any]) -> dict[str, Any]:
        require_caller(request)
        user = user_of(request)
        r = rt()
        return V.hint(resolve(r, body, user, is_admin))

    @app.post(f"{P}/ayristir")
    def fark_decompose(request: Request, body: dict[str, Any]) -> dict[str, Any]:
        require_caller(request)
        user = user_of(request)
        r = rt()
        sq = resolve(r, body, user, is_admin)
        karsi = str(body.get("karsi") or "gecen-yil")
        dims = [str(x) for x in (body.get("boyutlar") or V.DEFAULT_DIMS)]
        try:
            res = V.for_question(runner_for(r), sq, karsi=karsi, boyutlar=dims)
        except V.VarianceError as e:
            return {"ok": False, "neden": str(e)}
        except Exception as e:  # noqa: BLE001 — yetki kapsamı ve kaynak hatası düz cümleyle
            from semantic_bridge import access as access_mod

            if isinstance(e, access_mod.DataScopeError):     # veri alanı rolde yok: düz cümle (oturum hatası değil)
                return {"ok": False, "neden": str(e)}
            log.warning("fark ayrıştırma koşamadı: %s", e)
            raise HTTPException(status_code=502, detail={"code": "SOURCE", "message": f"Ayrıştırma sorgusu çalışmadı: {str(e)[:200]}"}) from None
        if body.get("anlat", True):
            res["anlatim"] = V.explain(res, rt=r, module="fark")
        audit(r.store.engine, user, "run", "fark", str(body.get("queryId") or "")[:64] or "soru",
              str((res.get("olcu") or {}).get("ad") or "")[:200], {"karsi": karsi, "boyutlar": dims})
        return res
