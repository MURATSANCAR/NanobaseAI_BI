"""M39 Pazar — dağıtımcı ve perakende katalogları uçları: /api/v1/pazar/dagitim/*.

Sayfa kapısı `access.RULES`: durum ve endeks `sayfa:pazar-arastirma` / `sayfa:pazar-rakipler`; elle yenileme
`ozellik:pazar.kategori-esleme` (M39'un kaynak yenileme yetkisi). Zamanlayıcı (`timas-pazar-dagitim.timer`, her gün
06:15) yalnız `POST /api/v1/pazar/dagitim/run-due`'yu çağırır. Kaynağa (`API_URUN_DB`), Logo'ya ve CRM'e yazılmaz.
"""
from __future__ import annotations

import logging
import threading
from datetime import date
from typing import Any, Callable, Optional

from fastapi import HTTPException, Request

from semantic_bridge import pazar_dagitim as D
from semantic_bridge import provenance as PV

log = logging.getLogger("semantic.pazar.dagitim.api")
B = "/api/v1/pazar/dagitim"
F_REFRESH = "ozellik:pazar.kategori-esleme"


class Job:
    """Tek arka plan turu; ikinci başlatma reddedilir, durum ekrandan yoklanır."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.thread: Optional[threading.Thread] = None
        self.state: dict[str, Any] = {"step": None, "startedAt": None, "finishedAt": None, "error": None, "result": None}

    def running(self) -> bool:
        return bool(self.thread and self.thread.is_alive())

    def status(self) -> dict[str, Any]:
        return {**self.state, "running": self.running()}

    def start(self, work: Callable[[Callable[[str], None]], Any]) -> bool:
        with self.lock:
            if self.running():
                return False

            def step(t: str) -> None:
                self.state["step"] = t

            def run() -> None:
                self.state.update({"startedAt": D.now().isoformat(), "finishedAt": None, "error": None, "result": None})
                try:
                    self.state["result"] = work(step)
                except Exception as e:  # noqa: BLE001
                    log.warning("pazar dagitim turu başarısız: %s", e)
                    self.state["error"] = str(e)[:400]
                finally:
                    self.state["finishedAt"] = D.now().isoformat()
                    self.state["step"] = None

            self.thread = threading.Thread(target=run, name="pazar-dagitim", daemon=True)
            self.thread.start()
            return True


def register(app: Any, deps: dict[str, Any]) -> Job:
    """`deps`: auth(request) → (engine, tenant, user, display) · require_caller(request) · can(user, key) ·
    is_admin(user) · audit(engine, user, action, kind, id, title, detail) · engine() / tenant() · logo_file()."""
    from semantic_bridge import budget_sources as bsrc

    auth, require_caller, can, is_admin, audit = (deps[k] for k in ("auth", "require_caller", "can", "is_admin", "audit"))
    job = Job()

    def ctx(request: Request) -> tuple[Any, str, str, str]:
        engine, tenant, user, display = auth(request)
        D.ensure(engine)
        return engine, tenant, user, display

    def call(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except D.DagitimError as e:
            raise HTTPException(status_code=e.status, detail={"code": "PAZAR_DAGITIM", "message": str(e)}) from e
        except bsrc.SourceError as e:
            raise HTTPException(status_code=503, detail={"code": "PAZAR_DAGITIM_SOURCE", "message": str(e)}) from e

    def tur(engine: Any, tenant: str, step: Callable[[str], None]) -> dict[str, Any]:
        run = bsrc.runner(deps["logo_file"]())
        return D.run_all(engine, tenant, run, bsrc.firms_by_year(run), step=step)

    def day(v: str) -> Optional[date]:
        if not v:
            return None
        try:
            return date.fromisoformat(v[:10])
        except ValueError:
            raise HTTPException(status_code=400, detail={"code": "PAZAR_DAGITIM", "message": "Tarih YYYY-AA-GG olmalı."}) from None

    @app.get(B + "/status")
    def dagitim_status(request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        return {**D.status(engine, tenant), "job": job.status(),
                "canRefresh": bool(is_admin(user) or can(user, F_REFRESH)), "notlar": D.NOTLAR}

    def summary_sources(engine: Any, tenant: str, out: dict[str, Any]) -> PV.Kaynaklar:
        pen = out.get("pencere") or {}
        k = PV.Kaynaklar(data_end=pen.get("son"))
        g = k.sorgu("pazar.dagitim.basari", "Başarı Dağıtım kataloğu", "logo", D.SQL_BASARI,
                    description="Başarı'nın güncel kataloğu; her gün okunur, yalnız değişen satır saklanır.")
        ins = [g]
        if pen:
            ins.append(k.portal("pazar.dagitim.gozlem", "Pencere içindeki depo hareketleri",
                                D.summary_stmt(tenant, date.fromisoformat(pen["bas"]), date.fromisoformat(pen["son"])),
                                engine, description="Görüntüler arası stok düşüşü (çıkış), kategori, yayınevi ve ay kırılımı.",
                                origin=[g]))
        f = k.hesap("cikis", D.F_CIKIS, ins)
        k.alanlar({"kategoriler": f, "yayinevleri": f, "aylar": f, "toplam": f, "timasToplam": f})
        if out.get("kalibrasyon"):
            k.alan("kalibrasyon", k.hesap("kalibrasyon", D.F_KALIBRASYON, ins))
        return k

    @app.get(B + "/summary")
    def dagitim_summary(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        out = call(D.summary, engine, tenant)
        return PV.bagla(out, lambda: summary_sources(engine, tenant, out))

    @app.get(B + "/outflow")
    def dagitim_outflow(request: Request, by: str = "yayinevi", kaynak: str = "basari", bas: str = "", son: str = "",
                        timas: str = "", limit: int = 50) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        if kaynak not in D.KAYNAK:
            raise HTTPException(status_code=400, detail={"code": "PAZAR_DAGITIM", "message": "Bilinmeyen kaynak."})
        t = {"1": True, "true": True, "0": False, "false": False}.get(timas.lower()) if timas else None
        rows = call(D.outflow, engine, tenant, kaynak=kaynak, bas=day(bas), son=day(son), by=by, timas=t,
                    limit=max(1, min(limit, 1000)) if by != "ay" else None)
        return {"by": by, "kaynak": kaynak, "items": rows, "not": D.NOTLAR["endeks"]}

    @app.post(B + "/refresh")
    def dagitim_refresh(request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        if not (is_admin(user) or can(user, F_REFRESH)):
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "Kaynak yenileme rolünüzde yok."})
        started = job.start(lambda step: tur(engine, tenant, step))
        audit(engine, user, "run", "pazar_dagitim", None, "Dağıtımcı katalogları yenilendi", {"started": started})
        return {"started": started, "job": job.status()}

    @app.post(B + "/run-due")
    def dagitim_run_due(request: Request) -> dict[str, Any]:
        """Zamanlayıcı: turu bekleyerek koşar."""
        require_caller(request)
        engine, tenant = deps["engine"](), deps["tenant"]()
        D.ensure(engine)
        if job.running():
            return {"skipped": "başka bir tur sürüyor", "job": job.status()}
        done = threading.Event()
        box: dict[str, Any] = {}

        def work(step: Callable[[str], None]) -> dict[str, Any]:
            try:
                box["out"] = tur(engine, tenant, step)
                return box["out"]
            finally:
                done.set()

        if not job.start(work):
            return {"skipped": "başka bir tur sürüyor", "job": job.status()}
        done.wait()
        if "out" not in box:
            raise HTTPException(status_code=500, detail={"code": "PAZAR_DAGITIM", "message": job.status().get("error")})
        return box["out"]

    return job
