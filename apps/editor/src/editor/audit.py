"""Merkezi denetim kaydı — editör tarafı (portal Yönetim → Denetim kaydı).

- **Ara katman** (`Middleware`, kart servisi ve stüdyo): yazma isteğinde (POST/PUT/PATCH/DELETE) kişi `X-Editor`,
  istek kimliği portal köprüsünün `X-Audit-Rid`'i (yoksa yeni). Bağlam `db.audit_context`'e konur; o istekte açılan
  her işlemde `ed.nb_audit_row` değişen satırı önceki/sonraki hâliyle `ed.audit_outbox`'a yazar. İsteğin kendisi de
  (yol, yöntem, kod, süre, maskeli JSON gövde) kutuya bir satır olur. Okuma istekleri portal köprüsünde zaten kayıtlı.
- **Uçlar** (yalnız kart servisinde, aynı Bearer anahtarı): `GET /v1/audit/outbox?after=&limit=` verilen sıradan
  sonraki olaylar (her köprü kendi imlecini tutar: test sunucusu ve müşteri VM'i aynı editörü okur);
  `POST /v1/audit/outbox/ack` silmez, yalnız 90 günden eski satırları temizler.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from typing import Any

from . import db

_WRITE = {"POST", "PUT", "PATCH", "DELETE"}
SECRET = re.compile(r"(pass(word|wd)?|pwd|parola|sifre|şifre|secret|token|api_?key|apikey|credential|private_?key|cookie|"
                    r"authorization)", re.I)


def _mask(v: Any, key: str = "") -> Any:
    if key and SECRET.search(key) and v not in (None, "", [], {}):
        return "«gizli»"
    if isinstance(v, dict):
        return {k: _mask(x, str(k)) for k, x in v.items()}
    if isinstance(v, list):
        return [_mask(x, key) for x in v]
    return v


def _put(event: dict) -> None:
    try:
        with db.tx() as c:
            c.execute("INSERT INTO ed.audit_outbox(body) VALUES (%s)", (db.J(event),))
    except Exception:  # noqa: BLE001 — kayıt asıl işi durdurmaz
        import logging

        logging.getLogger("editor.audit").warning("denetim olayı yazılamadı", exc_info=True)


class Middleware:
    def __init__(self, app: Any, service: str = "editor") -> None:
        self.app = app
        self.service = service

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope.get("type") != "http" or scope.get("method", "GET").upper() not in _WRITE:
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers") or []}
        actor = (headers.get("x-editor") or "").strip()[:200] or None
        rid = re.sub(r"[^0-9a-f]", "", (headers.get("x-audit-rid") or "").lower())[:32] or uuid.uuid4().hex
        ct = headers.get("content-type", "").lower()
        chunks: list[bytes] = []
        size = 0

        async def rec() -> dict:
            nonlocal size
            msg = await receive()
            if msg.get("type") == "http.request":
                b = msg.get("body") or b""
                size += len(b)
                if "json" in ct:
                    chunks.append(b)
            return msg

        status: dict[str, Any] = {"code": None}

        async def snd(msg: dict) -> None:
            if msg.get("type") == "http.response.start":
                status["code"] = msg.get("status")
            await send(msg)

        token = db.audit_context.set(json.dumps({"rid": rid, "actor": actor or "ZEKİ AI"}, ensure_ascii=False))
        t0 = time.monotonic()
        try:
            await self.app(scope, rec, snd)
        except Exception:
            status["code"] = status["code"] or 500
            raise
        finally:
            db.audit_context.reset(token)
            body: Any = None
            if chunks:
                raw = b"".join(chunks).decode("utf-8", "replace")
                try:
                    body = _mask(json.loads(raw))
                except ValueError:
                    body = raw
            code = status["code"]
            event = {"type": "request", "id": f"req:{rid}:{self.service}", "rid": rid, "at": time.time(),
                     "actor": actor, "method": scope.get("method"), "path": scope.get("path"),
                     "query": (scope.get("query_string") or b"").decode("latin-1") or None,
                     "module": self.service, "status": code, "ms": int((time.monotonic() - t0) * 1000),
                     "reqBytes": size or None, "contentType": ct or None, "body": body,
                     "kind": "denied" if code in (401, 403) else "error" if (code or 0) >= 500 else "write"}
            from starlette.concurrency import run_in_threadpool

            await run_in_threadpool(_put, event)


#: Kutu bir taşıma tamponudur; asıl kayıt merkezdedir. GPU editörü test sunucusu ve müşteri VM'i tarafından ortak
#: kullanılır: iki köprü de kendi kaldığı sıradan (`after`) okur, okuma hiçbir şeyi silmez (2026-10-03: onayla silmek
#: her olayı yalnız önce çeken tarafa veriyordu). Bu süreden eski satırlar temizlenir.
KEEP_DAYS = 90


def outbox(limit: int = 1000, after: int = 0) -> dict:
    import random

    if random.random() < 0.01:
        ack(0)                       # saklama süresi (okuma silmez; yalnız 90 günden eski)
    rows = db.all_rows("SELECT seq, body FROM ed.audit_outbox WHERE seq > %s ORDER BY seq LIMIT %s",
                       max(0, int(after)), max(1, int(limit)))
    return {"items": [{**r["body"], "seq": r["seq"]} for r in rows]}


def ack(upto: int) -> dict:
    """Geriye uyum: eski köprü sürümleri çağırır. Silmez; yalnız saklama süresini aşanları temizler."""
    with db.tx() as c:
        n = c.execute("DELETE FROM ed.audit_outbox WHERE at < now() - make_interval(days => %s)", (KEEP_DAYS,)).rowcount
    return {"deleted": n}
