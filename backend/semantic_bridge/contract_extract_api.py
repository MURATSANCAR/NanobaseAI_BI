"""Öneri 13 uçları — sözleşme belgesinden şart çıkarma: `/api/v1/editorial/contracts/extracts`.

    PUT    …/extracts?filename=&key=     belge yüklenir (ham gövde), okuma arka planda başlar
    GET    …/extracts?key=               sözleşmeye bağlı okumalar (en yeni önce)
    GET    …/extracts/{id}               tek okuma (ilerleme, sonuç, öneri) + sorgu bilgisi
    GET    …/extracts/{id}/file          yüklenen belgenin kendisi
    POST   …/extracts/{id}/accepted      insanın forma aktardığı alanlar + sözleşme bağı (yeni taslakta sonradan)
    DELETE …/extracts/{id}               okuma ve belge silinir

Okuma sayfa yetkisiyle (`sayfa:telif-sozlesme`), yükleme/onay/silme `ozellik:sozlesme.duzenle` ile (M6'nın açıkça
verilen düzenleme yetkisi). Model LLM kapısından (`rt.llm_for("sozlesme", NORMAL)`); model yoksa yalnız kural katı
çalışır ve bu ekranda yazılır. Şartlar forma öneri olarak gelir; kayıt sözleşme uçlarından, insanın elinden geçer.
CRM'e yazma yok. Her yazma `semantic_audit`'e düşer.
"""
from __future__ import annotations

import logging
import threading
from typing import Any, Callable, Optional

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

from semantic_bridge import contract_extract as CE
from semantic_bridge import doc_read as DR

log = logging.getLogger("semantic.contract_extract")

B = "/api/v1/editorial/contracts/extracts"
EDIT = "ozellik:sozlesme.duzenle"


def spawn(target: Callable[[], None], name: str) -> None:
    """Arka plan işi (testte eşzamanlı çalıştırılmak üzere değiştirilir)."""
    threading.Thread(target=target, name=name, daemon=True).start()


def kaynaklar(eid: Optional[str]):
    from semantic_bridge import provenance as P

    k = P.Kaynaklar()
    stmt = (f"SELECT * FROM semantic_contract_extracts WHERE id = '{eid}'" if eid else
            "SELECT * FROM semantic_contract_extracts WHERE 1 = 0")
    src = k.portal("belge", "Sözleşme belgesi okuması", stmt, None,
                   description="Belgenin okunması ve alıntı denetiminden geçen şart adayları bu kayıtta saklanır.")
    k.alan("item", k.hesap("belge", "Oran, tutar, tarih ve süre belgedeki alıntının kendisinden kodla okunur (Türkçe "
                                    "yazım: 10.000,50); model sayı yazmaz. Sayfa sayısı, OCR sayfaları ve güven belgenin "
                                    "okunmasından; pencere sayısı metin bütçesine göre bölümlemedir.", [src]))
    k.alan("items", "hesap:belge")
    return k


def register(app, *, rt: Callable[[], Any], greetings: Callable[[Request], tuple], can: Callable[[str, str], bool],
             audit: Callable[..., None], conf: Callable[[str], Any]) -> None:
    state = {"reset": set()}

    def session(request: Request) -> tuple[Any, str, str]:
        engine, tenant, user, _ = greetings(request)
        CE.ensure(engine)
        if id(engine) not in state["reset"]:
            state["reset"].add(id(engine))
            n = CE.reset_stale(engine)
            if n:
                log.warning("sözleşme belgesi: %d yarıda kalan okuma hata olarak işaretlendi", n)
        return engine, tenant, user

    def need(user: str) -> None:
        if not can(user, EDIT):
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "Bu işlem rolünüzde yok."})

    def call(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except CE.ExtractError as e:
            raise HTTPException(status_code=e.status, detail={"code": "CONTRACT", "message": str(e)}) from e

    def llm():
        try:
            from semantic_layer.runtime.llm_queue import NORMAL
            return rt().llm_for(CE.MODULE, NORMAL)
        except Exception:  # noqa: BLE001 — model tanımlı değil
            return None

    def party_names(engine, tenant: str, key: Optional[str]) -> list[str]:
        if not key:
            return []
        from semantic_bridge import contracts as C

        try:
            rec = C.find(engine, tenant, key)
        except Exception as e:  # noqa: BLE001
            log.info("sözleşme belgesi: taraf adları okunamadı: %s", e)
            return []
        return [p.get("name") for p in ((rec or {}).get("terms") or {}).get("parties") or [] if p.get("name")]

    def run(engine, tenant: str, row: dict[str, Any], names: list[str]) -> None:
        from semantic_bridge import doc_extract as X

        eid = row["id"]
        m = llm()
        chat = (lambda messages: m.chat(messages, max_tokens=1800, temperature=0.0)) if m is not None else None

        def job() -> None:
            try:
                path, filename = CE.path_of(engine, tenant, eid)
                with open(path, "rb") as fh:
                    data = fh.read()
                try:
                    reading = DR.read(filename, data, allowed=CE.ALLOWED)
                except DR.ReadError as e:
                    CE.finish(engine, eid, None, str(e))
                    return
                res = CE.analyse(reading, names=names, chat=chat, cfg=X.settings(conf),
                                 progress=CE.progress_writer(engine, eid))
                CE.finish(engine, eid, res, None)
            except CE.ExtractError as e:
                CE.finish(engine, eid, None, str(e))
            except Exception:  # noqa: BLE001 — ayrıntı günlükte
                log.exception("sözleşme belgesi okunamadı (%s)", eid)
                CE.finish(engine, eid, None, "Belge okunurken beklenmeyen bir hata oldu; yeniden okutun.")

        spawn(job, f"contract-extract-{eid[:6]}")

    @app.put(B, status_code=201)
    async def contract_extract_upload(request: Request, filename: str = "", key: str = "") -> dict[str, Any]:
        engine, tenant, user = await run_in_threadpool(session, request)
        need(user)
        if int(request.headers.get("content-length") or 0) > CE.FILE_MAX:
            raise HTTPException(status_code=413, detail={"code": "CONTRACT", "message": "Belge 10 MB sınırını aşıyor."})
        data = await request.body()
        row = await run_in_threadpool(call, CE.create, engine, tenant, user, filename, data, key or None)
        names = await run_in_threadpool(party_names, engine, tenant, key or None)
        run(engine, tenant, row, names)
        audit(engine, user, "upload", "contract_document", row["id"], row["filename"], {"bytes": row["bytes"], "sozlesme": key or None})
        return row

    @app.get(B)
    def contract_extract_list(request: Request, key: str = "") -> dict[str, Any]:
        from semantic_bridge import provenance as P

        engine, tenant, _ = session(request)
        items = CE.for_contract(engine, tenant, key) if key else []
        return P.bagla({"items": items, "model": llm() is not None}, lambda: kaynaklar(items[0]["id"] if items else None))

    @app.get(B + "/{eid}")
    def contract_extract_get(eid: str, request: Request) -> dict[str, Any]:
        from semantic_bridge import provenance as P

        engine, tenant, _ = session(request)
        item = call(CE.get, engine, tenant, eid)
        return P.bagla({"item": item, "model": llm() is not None}, lambda: kaynaklar(item["id"]))

    @app.get(B + "/{eid}/file")
    def contract_extract_file(eid: str, request: Request) -> FileResponse:
        engine, tenant, _ = session(request)
        path, filename = call(CE.path_of, engine, tenant, eid)
        mime = DR.IMAGES.get(DR.ext_of(filename)) or {"pdf": "application/pdf", "docx": "application/vnd.openxmlformats-"
                                                       "officedocument.wordprocessingml.document"}.get(DR.ext_of(filename),
                                                                                                      "application/octet-stream")
        return FileResponse(path, media_type=mime, filename=filename, headers={"Cache-Control": "private, no-store"})

    @app.post(B + "/{eid}/accepted")
    def contract_extract_accept(eid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user = session(request)
        need(user)
        out = call(CE.accept, engine, tenant, user, eid, body.get("fields"), body.get("key"))
        audit(engine, user, "accept", "contract_document", eid, out["filename"],
              {"alanlar": out["accepted"], "sozlesme": out["contractKey"]})
        return out

    @app.delete(B + "/{eid}")
    def contract_extract_delete(eid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user = session(request)
        need(user)
        out = call(CE.delete, engine, tenant, eid)
        audit(engine, user, "delete", "contract_document", eid, out["filename"], None)
        return {"ok": True}


__all__ = ["register", "kaynaklar"]
