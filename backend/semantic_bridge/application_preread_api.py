"""Öneri 12 uçları — başvuru ön okuması: `/api/v1/editorial/applications/{id}/preread`.

    GET  …/preread              son ön okuma (süren ya da bitmiş) + okunabilir dosyalar + sorgu bilgisi
    POST …/preread {fileId}     ön okumayı başlatır (arka planda; aynı başvuruda süren iş varsa onu döner)

Yetki: sayfa kuralı (Başvurular), yazma `ozellik:basvuru.yaz` (`access.FEATURE_RULES`, başvuru uçlarının deseni).
Model LLM kapısından: `rt.llm_for("basvuru", NORMAL)`; `chat` ve `choose` aynı sarmalayıcıdan. Başlatma
`semantic_audit`'e düşer. Sonuç yalnız öneridir; editör raporu formuna ön yüzde aktarılır, kaydı editör yapar.
"""
from __future__ import annotations

import logging
import threading
from typing import Any, Callable, Optional

import sqlalchemy as sa
from fastapi import HTTPException, Request

from semantic_bridge import application_preread as PR
from semantic_bridge import doc_read as DR
from semantic_bridge import editorial_applications as EA

log = logging.getLogger("semantic.application_preread")

A = "/api/v1/editorial/applications"


def spawn(target: Callable[[], None], name: str) -> None:
    """Arka plan işi (testte eşzamanlı çalıştırılmak üzere değiştirilir)."""
    threading.Thread(target=target, name=name, daemon=True).start()


def kaynaklar(pid: Optional[str], result: Optional[dict[str, Any]]):
    """Sorgu bilgisi: ön okuma kaydının portal okuması + her rakamın hesabı (belge okuması, alıntıdan kod, olasılık,
    benzerlik sırası)."""
    from semantic_bridge import provenance as P

    k = P.Kaynaklar()
    stmt = f"SELECT * FROM semantic_editorial_application_prereads WHERE id = '{pid}'" if pid else \
        "SELECT * FROM semantic_editorial_application_prereads WHERE 1 = 0"
    src = k.portal("onokuma", "Başvuru ön okuması kaydı", stmt, None,
                   description="Ön okumanın sonucu (belge okuma + alıntı denetiminden geçen alanlar) bu kayıtta saklanır.")
    k.alan("preread", k.hesap("onokuma", "Sayfa sayısı, OCR sayfaları ve güven dosyanın okunmasından; yaş aralığı "
                                         "alıntının kendisinden kodla okunur; tür ve kitle olasılığı Zeki AI'ın kapalı "
                                         "kümedeki seçim olasılığıdır; pencere sayısı metin bütçesine göre bölümlemedir.",
                              [src]))
    k.alan("previous", "hesap:onokuma")
    k.alan("preread.result.benzer", k.hesap("benzer", "Sıra: kitap benzerliği dizininde ön okuma özetine anlam "
                                                       "yakınlığı sırası (puan gösterilmez, satış rakamı yok).", [src]))
    k.alan("files", k.hesap("dosyalar", "Başvurunun yüklenmiş dosyaları (tur numarası).", [src]))
    return k


def register(app, deps: dict[str, Any]) -> None:
    """deps: session(request)→(engine, tenant, user, display) · audit · conf · llm() → LLM kapısı sarmalayıcısı ya da None."""
    session: Callable[[Request], tuple[Any, str, str, str]] = deps["session"]
    audit = deps["audit"]
    conf = deps["conf"]
    llm_of: Callable[[], Any] = deps["llm"]
    state = {"reset": set()}
    active: set[str] = set()
    lock = threading.Lock()

    def ctx(request: Request):
        engine, tenant, user, display = session(request)
        EA.ensure(engine)
        PR.ensure(engine)
        if id(engine) not in state["reset"]:
            state["reset"].add(id(engine))
            n = PR.reset_stale(engine)
            if n:
                log.warning("ön okuma: %d yarıda kalan iş hata olarak işaretlendi", n)
        return engine, tenant, user, display or user

    def err(e: Exception) -> HTTPException:
        status = getattr(e, "status", 400)
        return HTTPException(status_code=status, detail={"code": "APPLICATION", "message": str(e)})

    def files_of(engine, app_id: str) -> list[dict[str, Any]]:
        with engine.connect() as c:
            rows = c.execute(sa.select(EA.FILES).where(EA.FILES.c.app_id == app_id).order_by(EA.FILES.c.uploaded_at.desc())).all()
        return [dict(EA._file_out(f), path=f.path) for f in rows]

    @app.get(A + "/{app_id}/preread")
    def application_preread(app_id: str, request: Request) -> dict[str, Any]:
        from semantic_bridge import provenance as P

        engine, tenant, _, _ = ctx(request)
        try:
            a = EA.snapshot(engine, tenant, app_id)["app"]
        except EA.ApplicationError as e:
            raise err(e) from e
        cur = PR.latest(engine, tenant, a["id"])
        out = {"preread": cur, "files": PR.readable(files_of(engine, a["id"]), a["round"]),
               "model": llm_of() is not None}
        if cur and cur.get("previous"):
            out["previous"] = cur.pop("previous")
        return P.bagla(out, lambda: kaynaklar(cur["id"] if cur else None, (cur or {}).get("result")))

    @app.post(A + "/{app_id}/preread")
    def application_preread_start(app_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        try:
            a = EA.snapshot(engine, tenant, app_id)["app"]
        except EA.ApplicationError as e:
            raise err(e) from e
        files = files_of(engine, a["id"])
        fid = str(body.get("fileId") or "")
        options = {f["id"]: f for f in PR.readable(files, a["round"])}
        if not fid:
            cur = [f for f in options.values() if f["readable"] and f["current"]] or [f for f in options.values() if f["readable"]]
            fid = cur[0]["id"] if cur else ""
        f = options.get(fid)
        if f is None:
            raise HTTPException(status_code=400, detail={"code": "APPLICATION", "message": (
                "Ön okuma için eser dosyası ya da revize dosya seçin (özgeçmiş okunmaz)." if fid else
                "Başvuruda okunacak eser dosyası yok; önce PDF ya da DOCX yükleyin.")})
        if not f["readable"]:
            raise HTTPException(status_code=400, detail={"code": "APPLICATION", "message": f["why"]})
        llm = llm_of()
        if llm is None:
            raise HTTPException(status_code=503, detail={"code": "APPLICATION",
                                                         "message": "Zeki AI bu kurulumda bağlı değil; ön okuma yapılamaz."})
        row, fresh = PR.start(engine, tenant, user, a["id"], a["round"], f)
        if not fresh:
            return {"preread": row, "already": True}
        path = next(x["path"] for x in files if x["id"] == fid)
        names = [n for n in (a.get("authorName"), a.get("agencyContact")) if n]
        cfg = PR.settings(conf)

        def chat(messages):
            return llm.chat(messages, max_tokens=1800, temperature=0.0)

        choose = (lambda prompt, choices: llm.choose(prompt, choices)) if hasattr(llm, "choose") else None

        def similar(text: str) -> dict[str, Any]:
            from semantic_bridge import book_similarity as BS

            return BS.similar_books(engine, tenant, metin=text, n=cfg["similar"],
                                    suzgec={"baglam": {"kitaplik": a.get("categoryName"), "turler": a.get("genre")}})

        def job() -> None:
            pid = row["id"]
            try:
                with open(path, "rb") as fh:
                    data = fh.read()
                try:
                    reading = DR.read(f["filename"], data, allowed=PR.READABLE_EXT)
                except DR.ReadError as e:
                    PR.finish(engine, pid, None, str(e))
                    return
                res = PR.analyse(reading, names=names, chat=chat, choose=choose, cfg=cfg,
                                 themes=PR.themes_from_index(engine, tenant), similar=similar,
                                 progress=PR.progress_writer(engine, pid))
                res["dosya"] = {"id": f["id"], "ad": f["filename"], "tur": f.get("kindLabel"), "round": f.get("round")}
                PR.finish(engine, pid, res, None)
            except PR.PrereadError as e:
                PR.finish(engine, pid, None, str(e))
            except OSError as e:
                log.error("ön okuma: dosya okunamadı (%s): %s", path, e)
                PR.finish(engine, pid, None, "Dosya sunucuda bulunamadı; yeniden yükleyin.")
            except Exception:  # noqa: BLE001 — ayrıntı günlükte, kişiye düz cümle
                log.exception("ön okuma üretilemedi (%s)", app_id)
                PR.finish(engine, pid, None, "Ön okuma sırasında beklenmeyen bir hata oldu; yeniden başlatın.")
            finally:
                with lock:
                    active.discard(pid)

        with lock:
            active.add(row["id"])
        spawn(job, f"preread-{row['id'][:6]}")
        audit(engine, user, "run", "application_preread", a["id"], f"{a['no']} {a['title']}", {"dosya": f["filename"]})
        return {"preread": row, "already": False}


__all__ = ["register", "kaynaklar"]
