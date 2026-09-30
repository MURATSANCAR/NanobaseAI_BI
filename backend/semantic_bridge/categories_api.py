"""H1 Kategori ağacı uçları: /api/v1/categories/*.

Sayfa kapısı `access.RULES` (`sayfa:kategori-agaci`). İşlem yetkileri: öneri üretme ve kaynak yenileme
`ozellik:kategori.oneri-uret`, ağaç taslağı / eşleme / kural / etiket sözlüğü `ozellik:kategori.agac-duzenle`
(`FEATURE_RULES`); açıkça verilenler burada denetlenir: ağacı yürürlüğe alma / geri gönderme
`ozellik:kategori.agac-onay` (gönderen onaylayamaz), profil kararı `ozellik:kategori.profil-onay` (editör kendi
kitabında — kartın editörü ya da yayın yönetmeni), başkasının kitabı `ozellik:kategori.herkesinki`.

Zamanlayıcı (`timas-categories.timer`, her gece) yalnız `POST /api/v1/categories/run-due`'yu çağırır: kaynakları
okur, kuralları koşar, yürürlükte ağaç varsa profili olmayan kitaplara (önce yeni kartlar, sonra satış önceliği)
süre bütçesi içinde öneri üretir; bitmeyen iş sonraki geceye kalır.

Sözleşme uçları (diğer modüller okur): `GET /api/v1/categories/profile/{stok_kodu}`, `GET /api/v1/categories/nodes`,
`GET /api/v1/categories/nodes/{düğüm}/books`.

CRM'e, T-soft'a ve Logo'ya yazılmaz.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Callable, Optional

from fastapi import HTTPException, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from semantic_bridge import categories as C
from semantic_bridge import categories_kaynak as CK
from semantic_bridge import crm_kisi as KISI
from semantic_bridge import hizli_bellek as HB
from semantic_bridge import provenance as PV
from semantic_bridge import sorgu_izi as IZ
from semantic_bridge import categories_propose as CP
from semantic_bridge import categories_sources as src

log = logging.getLogger("semantic.categories.api")

CRM_FILE_DEFAULT = "/data/nanobaseai/bi/secrets/crm-mssql-connection.json"

#: Kişinin CRM kullanıcısı (portal hesabı → CRM `SystemUserId`) en çok bu kadar saniyede bir CRM'den yeniden okunur.
#: Okuma arkadadır; ekran eldeki değeri (süreç belleği, yoksa portal tablosundaki son okuma) beklemeden alır.
KISI_TAZE = 600
#: Özetin herkes için aynı kısmı (bütün etkin profillerin CRM kopyası okunup sayılır): profil/ağaç/kural/eşitleme yazan
#: her yerde düşer ve arkada yeniden hesaplanır. Yazma dışında zamanla değişen tek sayı «N günden eski CRM farkı»dır:
#: taze pencereden sonra eldeki değer hemen döner, aynı anda arkada yeniden hesaplanır.
OZET_TAZE = 60
OZET_BAYAT = 12 * 3600


class Job:
    """Kaynak okuması: tek iş parçacığı, durum ekrana yoklanır."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.state: dict[str, Any] = {"running": False, "step": None, "startedAt": None, "finishedAt": None,
                                      "error": None, "result": None}
        self.thread: Optional[threading.Thread] = None

    def running(self) -> bool:
        return bool(self.thread and self.thread.is_alive())

    def status(self) -> dict[str, Any]:
        return {**self.state, "running": self.running()}

    def step(self, text: str) -> None:
        self.state["step"] = text


def register(app, rt: Callable[[], Any], require_caller: Callable[[Request], None], can: Callable[[str, str], bool]):
    from semantic_bridge import admin as admin_mod
    from semantic_bridge import board as board_mod

    job = Job()
    stats_cache: dict[tuple, dict[str, Any]] = {}
    # Hız (2026-09-29): ekranı açan kişi canlı CRM'i ve bütün profillerin taranmasını beklemesin.
    kisi_bellek = HB.Bellek("kategori.crm-kisi", taze=float("inf"), en_cok=4096)
    ozet_bellek = HB.Bellek("kategori.ozet", taze=OZET_TAZE, bayat=OZET_BAYAT, en_cok=16)

    def crm_file() -> str:
        return os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", CRM_FILE_DEFAULT)

    def izli(engine, tenant: str, fn, *, prefix: str, title: str, text: str, skip: tuple = (), crm: bool = True,
             logo: bool = True):
        """Sorgu bilgisi: uçta koşan portal okumaları + tabloları dolduran gece eşitlemesinin CRM/Logo sorguları."""
        with IZ.izle(engine) as ran:
            out = fn()
        if not isinstance(out, dict):
            return out
        return kaynak_bagla(engine, tenant, out, ran, prefix=prefix, title=title, text=text, skip=skip, crm=crm, logo=logo)

    def kaynak_bagla(engine, tenant: str, out: dict[str, Any], ran: list, *, prefix: str, title: str, text: str,
                     skip: tuple = (), crm: bool = True, logo: bool = True, description: str = "") -> dict[str, Any]:
        """`ran`: rakamları üreten portal okumaları (bellekten gelen kısımda onu hesaplayan okumanın ifadeleri)."""
        dbs = (PV.connection_database(rt().settings.connection_file), PV.connection_database(crm_file()))
        return PV.bagla(out, lambda: IZ.kaynak(engine, ran, out, prefix=prefix, title=title, text=text, skip=skip,
                                               description=description,
                                               origin=lambda k: CK.origin(k, engine, tenant, *dbs, crm=crm, logo=logo)))

    def schema() -> str:
        s = (admin_mod.conf("CRM_SCHEMA") or "").strip()
        if not s:
            raise HTTPException(status_code=503, detail={"code": "CATEGORY_SOURCE", "message": "CRM şeması tanımlı değil."})
        return s

    def ctx(request: Request) -> tuple[Any, str, str, str]:
        require_caller(request)
        try:
            user, display = board_mod.session_of(request.headers.get("cookie", ""))
        except board_mod.NoUser:
            raise HTTPException(status_code=401, detail={"code": "UNAUTHORIZED", "message": "Oturum gerekli."}) from None
        r = rt()
        C.ensure(r.store.engine)
        admin_mod.ensure(r.store.engine)
        return r.store.engine, r.settings.tenant_id, user, display

    def call(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except C.CategoryError as e:
            raise HTTPException(status_code=e.status, detail={"code": "CATEGORY", "message": str(e)}) from e
        except src.SourceError as e:
            raise HTTPException(status_code=503, detail={"code": "CATEGORY_SOURCE", "message": str(e)}) from e

    def need(user: str, key: str, what: str) -> None:
        if not can(user, key):
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": f"{what} rolünüzde yok."})

    def audit(engine, user, action, kind, oid, title, detail=None) -> None:
        admin_mod.audit(engine, user, action, kind, oid, title, detail)
        if kind != "category_export":
            # Her yazma ucu işini yazdıktan sonra buraya gelir: özet belleği düşer, arkada yeniden hesaplanır.
            yazildi(engine, rt().settings.tenant_id)

    def _kisi_meta_key(user: str) -> Optional[str]:
        key = "crm_me:" + (user or "").strip().lower()
        return key if len(key) <= 60 else None   # tablo anahtarı 60 karakter; uzun hesap adı yalnız süreç belleğinde

    def _kisi_canli(engine, tenant: str, user: str) -> dict[str, Any]:
        """CRM'den okur (`editorial_assign.crm_me`, yeni bağlantı) ve portal tablosuna yazar (köprü yeniden kalkınca
        kişi CRM'i beklemesin). CRM okunamazsa hata yükselir: eldeki değer kalır, hiç yoksa çağıran None verir."""
        from semantic_bridge import editorial_assign as M2

        run = src.runner(crm_file())
        me = M2.crm_me(schema(), lambda sql: {"records": run(sql)}, user)
        v = {"id": (me or {}).get("id"), "at": time.time()}
        key = _kisi_meta_key(user)
        if key:
            try:
                C.meta_set(engine, tenant, key, v)
            except Exception as e:  # noqa: BLE001 — yazılamazsa bellekte kalır
                log.info("kategori: %s için CRM kullanıcısı saklanamadı: %s", user, e)
        return v

    def _kisi_kayitli(engine, tenant: str, user: str) -> Optional[dict[str, Any]]:
        key = _kisi_meta_key(user)
        if not key:
            return None
        try:
            v = C.meta_get(engine, tenant, key)
        except Exception:  # noqa: BLE001 — tablo okunamazsa CRM'den okunur
            return None
        return v if isinstance(v, dict) and "at" in v else None

    def kisi_okuyucu() -> tuple[str, Any]:
        return schema(), src.runner(crm_file())

    def me_crm(user: str) -> Optional[str]:
        """Portal hesabı → CRM kullanıcısı (kartın editör / yayın yönetmeni alanıyla karşılaştırmak için).

        Hız 2. tur: önce bütün CRM kullanıcılarının saklanmış eşlemesi (`crm_kisi`: gece eşitlemesinde tek sorgu,
        gündüz 10 dk'dan eskiyse arkada yenilenir; kural `editorial_assign.crm_me` ile aynı). Eşleme cevap veremezse
        (hiç okunmamış ve CRM kapalı, ya da hesap adı eşlemeye uygun değil) eski yol: süreç belleği → portal
        tablosundaki son kişi okuması (`semantic_category_meta`, `crm_me:<hesap>`) → canlı CRM; değer `KISI_TAZE`
        saniyeden eskiyse eldeki döner ve CRM arkada yeniden okunur. Hiç değer yokken CRM okunamazsa None."""
        r = rt()
        engine, tenant = r.store.engine, r.settings.tenant_id
        try:
            found = KISI.bul(engine, tenant, user, kisi_okuyucu)
            return found.get("id") if found else None
        except KISI.Bilinmiyor:
            pass
        except Exception as e:  # noqa: BLE001 — saklanmış eşleme yoksa ve CRM okunamıyorsa eski yol denenir
            log.info("kategori: CRM kullanıcı eşlemesi okunamadı (%s), kişi başına okumaya dönülüyor: %s", user, e)
        acct = (tenant, (user or "").strip().lower())
        try:
            C.ensure(engine)
            v = kisi_bellek.al(acct, lambda: _kisi_kayitli(engine, tenant, user) or _kisi_canli(engine, tenant, user))
        except Exception as e:  # noqa: BLE001 — CRM okunamazsa «benim kitaplarım» boş kalır
            log.info("kategori: %s için CRM kullanıcısı okunamadı: %s", user, e)
            return None
        if time.time() - float(v.get("at") or 0) >= KISI_TAZE:
            kisi_bellek.isit(acct, lambda: _kisi_canli(engine, tenant, user))
        return v.get("id")

    # ------------------------------------------------------------------ özet belleği

    def ozet_anahtari(engine, tenant: str) -> tuple:
        # Eşikler (ekrandan değişebilir) anahtarda: «N günden eski» sayısı ve çıktıdaki eşikler onlara bağlı.
        return (id(engine), tenant, tuple(sorted(C.thresholds().items())))

    def ozet_hesapla(engine, tenant: str) -> dict[str, Any]:
        """Özetin ortak kısmı + onu üreten portal okumaları (sorgu bilgisi bellekten dönen değerde de bu okumadır)."""
        with IZ.izle(engine) as ran:
            out = C.overview_ortak(engine, tenant)
        return {"out": out, "ran": list(ran)}

    def yazildi(engine, tenant: str) -> None:
        """Profil, ağaç, eşleme, kural, bulgu ya da eşitleme yazıldı: özet düşer ve beklemeden arkada yeniden hesaplanır."""
        ozet_bellek.dusur()
        try:
            ozet_bellek.isit(ozet_anahtari(engine, tenant), lambda: ozet_hesapla(engine, tenant))
        except Exception as e:  # noqa: BLE001 — ısıtılamazsa sonraki açılış hesaplar
            log.info("kategori: özet ısıtılamadı: %s", e)

    def everyone(user: str) -> bool:
        return can(user, "ozellik:kategori.herkesinki")

    # ------------------------------------------------------------------ kaynak okuma

    def sync(engine, tenant: str, actor: str) -> dict[str, Any]:
        t0 = time.monotonic()
        prev = C.meta_get(engine, tenant, "sync", {}) or {}
        info: dict[str, Any] = {"startedAt": C.iso(C.now()), "previousAt": prev.get("at"), "by": actor}
        job.step("CRM kitap kartları okunuyor")
        crm = src.read_crm(schema(), src.runner(crm_file()))
        info["crm"] = {"books": len(crm["books"]), "ms": int((time.monotonic() - t0) * 1000), "schema": schema()}
        job.step("CRM kullanıcıları okunuyor (kişi eşlemesi)")
        try:
            # Ekranı açan kişinin CRM kullanıcısı istek anında CRM'i beklemesin: herkes tek sorguda (crm_kisi).
            info["kisiler"] = KISI.oku(engine, tenant, kisi_okuyucu)
        except Exception as e:  # noqa: BLE001 — eşitleme durmaz; eldeki eşleme kalır
            info["kisiler"] = {"error": str(e)[:300]}
            log.warning("kategori: CRM kullanıcı eşlemesi okunamadı: %s", e)
        priority = None
        job.step("Logo satışları okunuyor (öncelik puanı)")
        try:
            months = int(C.thresholds()["priorityMonths"])
            priority = src.read_priority(src.runner(rt().settings.connection_file), months)
            info["logo"] = {k: v for k, v in priority.items() if k != "byCode"} | {"codes": len(priority["byCode"])}
        except Exception as e:  # noqa: BLE001 — Logo yoksa önceki puan korunur
            info["logo"] = {"error": str(e)[:300]}
            log.warning("kategori: Logo önceliği okunamadı: %s", e)
        job.step("T-soft kategorileri (SEO eşitlemesi) okunuyor")
        try:
            tsoft = src.read_tsoft(engine, tenant)
            info["tsoft"] = {"products": len(tsoft["products"]), "categories": len(tsoft["categories"]),
                             "syncedAt": tsoft.get("syncedAt")}
        except Exception as e:  # noqa: BLE001
            tsoft = None
            info["tsoft"] = {"error": str(e)[:300]}
        job.step("Profiller ve tutarsızlık kuralları yazılıyor")
        res = C.apply_sync(engine, tenant, crm, priority, tsoft, actor)
        info.update({"at": res["at"], "result": res, "ms": int((time.monotonic() - t0) * 1000)})
        C.meta_set(engine, tenant, "sync", info)
        stats_cache.clear()
        yazildi(engine, tenant)
        return info

    def start_sync(engine, tenant: str, actor: str) -> bool:
        with job.lock:
            if job.running():
                return False

            def work() -> None:
                job.state.update({"startedAt": C.iso(C.now()), "finishedAt": None, "error": None, "result": None})
                try:
                    job.state["result"] = sync(engine, tenant, actor)
                except Exception as e:  # noqa: BLE001
                    log.warning("kategori kaynak okuması başarısız: %s", e)
                    job.state["error"] = str(e)[:400]
                finally:
                    job.state["finishedAt"] = C.iso(C.now())
                    job.state["step"] = None

            job.thread = threading.Thread(target=work, name="categories-sync", daemon=True)
            job.thread.start()
            return True

    # ------------------------------------------------------------------ öneri

    def proposer(engine, tenant: str, llm: Any, user_id: Optional[str]) -> CP.Proposer:
        tree = C.in_force(engine, tenant)
        tctx = C.tree_ctx(engine, tree)
        sync_at = (C.meta_get(engine, tenant, "sync", {}) or {}).get("at")
        key = (tenant, sync_at, (tree or {}).get("id"))
        stats = stats_cache.get(key)
        if stats is None:
            stats_cache.clear()
            stats = CP.corpus_stats(C.all_snapshots(engine, tenant), tctx)
            stats_cache[key] = stats
        return CP.Proposer(llm, tctx, vocab=C.meta_get(engine, tenant, "vocab", {}) or {},
                           labels=C.meta_get(engine, tenant, "labels", {}) or {}, stats=stats, th=C.thresholds(),
                           user_id=user_id)

    def propose_one(engine, tenant: str, actor: str, book_id: str, llm: Any, *, reset: bool = False,
                    fields: Optional[list[str]] = None, p: Optional[CP.Proposer] = None) -> dict[str, Any]:
        row = C.get_profile(engine, tenant, book_id)
        snap = C.loads(row["crm_snapshot_json"], {})
        texts: dict[str, Any] = {}
        try:
            texts = src.read_book_text(schema(), src.runner(crm_file()), row["book_id"])
        except src.SourceError as e:
            log.info("kategori önerisi: %s metni okunamadı, künyeyle devam: %s", row["book_id"], e)
        p = p or proposer(engine, tenant, llm, actor)
        before = p.calls
        props = p.run(snap, texts, C.vocabulary(engine, tenant, "etiket") or [])
        if fields:
            props = {k: v for k, v in props.items() if k in fields}
        calls = p.calls - before
        out = C.store_proposal(engine, tenant, row["book_id"], props, actor, reset=reset,
                               call_ids=[f"{C.iso(C.now())}:{calls}"] if calls else None)
        ozet_bellek.dusur()   # profil durumu değişti (toplu öneride kitap başına; ısıtma işin sonunda)
        out["modelCalls"] = calls
        return out

    def run_batch(engine, tenant: str, budget_sec: float) -> dict[str, Any]:
        if not C.in_force(engine, tenant):
            return {"skipped": "Yürürlükte kategori ağacı yok; toplu öneri ağaç onaylanınca başlar."}
        llm = rt().llm_for("categories", _batch_priority())
        if llm is None or not hasattr(llm, "choose"):
            return {"skipped": "Zeki AI bu kurulumda tanımlı değil."}
        order = C.batch_candidates(engine, tenant)
        t0 = time.monotonic()
        p = proposer(engine, tenant, llm, "sistem")
        done, errors, stopped = 0, [], None
        for bid in order:
            if time.monotonic() - t0 > budget_sec:
                stopped = "süre bütçesi doldu"
                break
            try:
                propose_one(engine, tenant, "Zeki AI (gece)", bid, llm, p=p)
                done += 1
            except (C.CategoryError, src.SourceError) as e:
                errors.append({"bookId": bid, "error": str(e)[:200]})
            except Exception as e:  # noqa: BLE001 — model kesintisi: bu gece durur, sıra korunur
                stopped = f"Zeki AI cevap vermedi: {str(e)[:200]}"
                break
        return {"queued": len(order), "proposed": done, "remaining": len(order) - done - len(errors),
                "errors": errors, "stopped": stopped, "modelCalls": p.calls, "seconds": int(time.monotonic() - t0)}

    def _batch_priority():
        from semantic_layer.runtime.llm_queue import BATCH

        return BATCH

    # ------------------------------------------------------------------ genel

    @app.get("/api/v1/categories/meta")
    def categories_meta(request: Request) -> dict[str, Any]:
        engine, tenant, user, display = ctx(request)
        return {"levels": C.LEVELS, "systems": C.SYSTEMS, "fields": C.FIELDS, "profileStatus": C.PROFILE_STATUS,
                "treeStatus": C.TREE_STATUS, "rules": {k: {"label": d["label"], "help": d["help"], "field": d["field"]}
                                                       for k, d in C.RULE_DEFS.items()},
                "thresholds": C.thresholds(), "job": job.status(),
                "me": {"username": user, "display": display, "crmId": me_crm(user),
                       "canPropose": can(user, "ozellik:kategori.oneri-uret"),
                       "canEditTree": can(user, "ozellik:kategori.agac-duzenle"),
                       "canApproveTree": can(user, "ozellik:kategori.agac-onay"),
                       "canDecide": can(user, "ozellik:kategori.profil-onay"),
                       "everyone": everyone(user), "canExport": can(user, "ozellik:veri.disa-aktar")}}

    @app.get("/api/v1/categories/overview")
    def categories_overview(request: Request) -> dict[str, Any]:
        """Ortak kısım süreç belleğinden (yazmada düşer; «Verileri yenile» yeniden hesaplatır), kişinin bekleyenleri her
        istekte kendi sorgusuyla. Sorgu bilgisi: ortak kısmı hesaplayan portal okumaları + bu isteğin okuması."""
        engine, tenant, user, _ = ctx(request)
        uid = me_crm(user)
        c = ozet_bellek.al(ozet_anahtari(engine, tenant), lambda: ozet_hesapla(engine, tenant),
                           zorla=request.headers.get("x-data-refresh") == "1")
        with IZ.izle(engine) as ran:
            mine = C.my_pending(engine, tenant, uid)
        out = dict(c["out"])   # bellekteki sözlük değişmesin
        out["mine"] = mine
        out["job"] = job.status()
        return kaynak_bagla(engine, tenant, out, [*c["ran"], *ran], prefix="portal.kategori.ozet",
                            title="Kategori ağacı özeti", text=CK.F_OZET, skip=("job",),
                            description="Bu özeti hesaplayan okuma (profil, ağaç ya da eşitleme yazılınca yeniden koşar).")

    @app.get("/api/v1/categories/status")
    def categories_status(request: Request) -> dict[str, Any]:
        ctx(request)
        return job.status()

    @app.get("/api/v1/categories/mine")
    def categories_mine(request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        from semantic_bridge import kampus_kaynak as KK
        from semantic_bridge import sorgu_izi as IZ

        uid = me_crm(user)   # izlemenin dışında: kişi eşlemesinin okuması sorgu bilgisine girmesin
        return IZ.izli(engine, lambda: C.my_pending(engine, tenant, uid), prefix="portal.kampus.kategori",
                       title="Onayınızı bekleyen kitap profilleri", text=KK.F_ZIL)

    @app.post("/api/v1/categories/refresh")
    def categories_refresh(request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        started = start_sync(engine, tenant, user)
        audit(engine, user, "run", "category_sync", None, "Kategori kaynakları yenilendi", {"started": started})
        return {"started": started, **job.status()}

    @app.post("/api/v1/categories/run-due")
    def categories_run_due(request: Request, budget: int = 0, propose: bool = True) -> dict[str, Any]:
        """Zamanlayıcı: kaynakları oku, kuralları koş, süre bütçesi içinde profili olmayan kitaplara öneri üret."""
        require_caller(request)
        r = rt()
        engine, tenant = r.store.engine, r.settings.tenant_id
        C.ensure(engine)
        out: dict[str, Any] = {}
        if job.running():
            out["sync"] = {"skipped": "başka bir okuma sürüyor"}
        else:
            with job.lock:
                job.state.update({"startedAt": C.iso(C.now()), "error": None})
            try:
                out["sync"] = sync(engine, tenant, "sistem")
            except Exception as e:  # noqa: BLE001
                out["sync"] = {"error": str(e)[:400]}
                job.state["error"] = str(e)[:400]
            finally:
                job.state["step"] = None
                job.state["finishedAt"] = C.iso(C.now())
        if propose:
            sec = budget or int(C.fsetting("CATEGORY_BATCH_SECONDS", 3600))
            out["propose"] = run_batch(engine, tenant, float(sec))
            yazildi(engine, tenant)
        C.meta_set(engine, tenant, "last_run", {"at": C.iso(C.now()), **{k: v for k, v in out.items() if k != "sync"}})
        return out

    @app.get("/api/v1/categories/options")
    def categories_options(request: Request) -> dict[str, Any]:
        """Eşleme ve düzeltme seçicilerinin sözlükleri: CRM Kitaplık, marka, ürün kategorisi, raf, sergilenecek, tür,
        tema, hedef kitle, T-soft kategorileri, etiket sözlüğü (aktif)."""
        engine, tenant, _, _ = ctx(request)
        vocab = C.meta_get(engine, tenant, "vocab", {}) or {}
        labels = C.meta_get(engine, tenant, "labels", {}) or {}
        ts = C.meta_get(engine, tenant, "tsoft", {}) or {}
        pack = {k: sorted(({"id": x["id"], "name": x["name"], "active": x.get("active", True), "parent": x.get("parent")}
                           for x in v.values()), key=lambda x: C.fold(x["name"])) for k, v in vocab.items() if k != "anahtarkelime"}
        return {**pack, "hedefKitle": [{"id": k, "name": v} for k, v in sorted((labels.get("hedefKitle") or {}).items())],
                "tsoft": sorted(({"id": c["id"], "name": c.get("path") or c.get("name"), "products": c.get("products", 0)}
                                 for c in (ts.get("categories") or {}).values()), key=lambda x: C.fold(x["name"])),
                "etiket": C.vocabulary(engine, tenant, "etiket") or []}

    # ------------------------------------------------------------------ ağaç

    @app.get("/api/v1/categories/tree")
    def categories_tree(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return izli(engine, tenant, lambda: C.tree_state(engine, tenant), prefix="portal.kategori.agac", title="Ağaç",
                    text=CK.F_AGAC)

    @app.get("/api/v1/categories/tree/versions")
    def categories_tree_versions(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return {"items": C.tree_versions(engine, tenant)}

    @app.get("/api/v1/categories/tree/versions/{tree_id}")
    def categories_tree_version(tree_id: str, request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        t = next((x for x in C.tree_versions(engine, tenant) if x["id"] == tree_id), None)
        if not t:
            raise HTTPException(status_code=404, detail={"code": "CATEGORY", "message": "Sürüm bulunamadı."})
        return {**t, "nodes": C.tree_ctx(engine, t).flat()}

    @app.put("/api/v1/categories/tree")
    def categories_tree_save(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(C.save_draft, engine, tenant, user, body)
        d = out.get("draft") or {}
        audit(engine, user, "update", "category_tree", d.get("id"), f"Kategori ağacı taslağı v{d.get('version')}",
              {"dugum": len(d.get("nodes") or []), "not": body.get("note")})
        return out

    @app.post("/api/v1/categories/tree/open")
    def categories_tree_open(request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(C.open_draft, engine, tenant, user)
        d = out.get("draft") or {}
        audit(engine, user, "create", "category_tree", d.get("id"), f"Kategori ağacı taslağı v{d.get('version')}",
              {"kaynak": "yürürlükteki ağaç"})
        return out

    @app.delete("/api/v1/categories/tree/draft")
    def categories_tree_discard(request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        d = C.draft(engine, tenant) or {}
        out = call(C.discard_draft, engine, tenant)
        audit(engine, user, "delete", "category_tree", d.get("id"), f"Kategori ağacı taslağı v{d.get('version')}")
        return out

    @app.post("/api/v1/categories/tree/suggest")
    async def categories_tree_suggest(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        out = await run_in_threadpool(call, C.suggest_draft, engine, tenant, user, bool(body.get("replace")))
        d = out.get("draft") or {}
        audit(engine, user, "create", "category_tree", d.get("id"), f"Kategori ağacı taslağı v{d.get('version')}",
              {"kaynak": f"{C.SUGGEST_LABEL} (kurala göre)", **(out.get("suggestion") or {})})
        return out

    @app.post("/api/v1/categories/tree/submit")
    def categories_tree_submit(request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(C.submit, engine, tenant, user)
        d = out.get("draft") or {}
        audit(engine, user, "update", "category_tree", d.get("id"), f"Kategori ağacı v{d.get('version')}", {"durum": "onay-bekliyor"})
        return out

    @app.post("/api/v1/categories/tree/withdraw")
    def categories_tree_withdraw(request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(C.withdraw, engine, tenant, user)
        d = out.get("draft") or {}
        audit(engine, user, "update", "category_tree", d.get("id"), f"Kategori ağacı v{d.get('version')}", {"durum": "taslak"})
        return out

    @app.post("/api/v1/categories/tree/approve")
    async def categories_tree_approve(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        need(user, "ozellik:kategori.agac-onay", "Kategori ağacı onayı")
        d = C.draft(engine, tenant) or {}
        out = await run_in_threadpool(call, C.decide_tree, engine, tenant, user, True, body.get("version"), body.get("note"))
        re = await run_in_threadpool(C.reresolve, engine, tenant)
        stats_cache.clear()
        audit(engine, user, "approve", "category_tree", d.get("id"), f"Kategori ağacı v{d.get('version')}",
              {"not": body.get("note"), "yenidenYerlesen": re.get("books")})
        return out

    @app.post("/api/v1/categories/tree/reject")
    def categories_tree_reject(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, "ozellik:kategori.agac-onay", "Kategori ağacı onayı")
        d = C.draft(engine, tenant) or {}
        out = call(C.decide_tree, engine, tenant, user, False, body.get("version"), body.get("note"))
        audit(engine, user, "reject", "category_tree", d.get("id"), f"Kategori ağacı v{d.get('version')}", {"not": body.get("note")})
        return out

    @app.get("/api/v1/categories/tree/impact")
    async def categories_tree_impact(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = await run_in_threadpool(ctx, request)
        return await run_in_threadpool(lambda: izli(engine, tenant, lambda: call(C.impact, engine, tenant),
                                                    prefix="portal.kategori.etki", title="Etki önizlemesi", text=CK.F_AGAC))

    @app.get("/api/v1/categories/mappings")
    def categories_mappings(request: Request, tree: str = "draft") -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        t = C.draft(engine, tenant) if tree == "draft" else C.in_force(engine, tenant)
        return {"tree": t, "items": C.mappings_of(engine, t["id"]) if t else []}

    @app.put("/api/v1/categories/mappings")
    def categories_mappings_save(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(C.set_mappings, engine, tenant, user, str(body.get("nodeId") or ""), str(body.get("system") or ""),
                   body.get("items") or [])
        audit(engine, user, "update", "category_tree", out["nodeId"], f"Eşleme: {C.SYSTEMS.get(out['system'], out['system'])}",
              {"eslemeler": [m["externalName"] or m["externalId"] for m in out["items"]]})
        return out

    # ------------------------------------------------------------------ kitaplar

    @app.get("/api/v1/categories/books")
    def categories_books(request: Request, q: str = "", owner: str = "", status: str = "", brand: str = "",
                         kitaplik: str = "", selling: str = "", finding: str = "", node: str = "",
                         order: str = "priority", page: int = 0) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        mine = me_crm(user) if owner == "me" else None
        if owner == "me" and not mine:
            return {"items": [], "total": 0, "page": 0, "pageSize": 50,
                    "note": "CRM'de hesabınıza bağlı kullanıcı bulunamadı; «benim kitaplarım» boş."}
        return izli(engine, tenant, lambda: call(C.list_books, engine, tenant, q=q, owner=mine, status=status, brand=brand,
                                                 kitaplik=kitaplik, selling=selling, finding=finding, node=node,
                                                 order=order, page=max(0, page)),
                    prefix="portal.kategori.kuyruk", title="Kitap kuyruğu", text=CK.F_KUYRUK, skip=("page", "pageSize"))

    @app.get("/api/v1/categories/books/{book_id}")
    def categories_book(book_id: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        mine = me_crm(user)   # izlemenin dışında: kişi eşlemesinin okuması sorgu bilgisine girmesin

        def read() -> dict[str, Any]:
            out = call(C.book_detail, engine, tenant, book_id)
            row = C.get_profile(engine, tenant, book_id)
            out["canDecide"] = can(user, "ozellik:kategori.profil-onay") and C.can_decide(row, mine, everyone(user))
            return out
        return izli(engine, tenant, read, prefix="portal.kategori.kitap", title="Kitap profili", text=CK.F_KITAP)

    @app.get("/api/v1/categories/books/{book_id}/text")
    def categories_book_text(book_id: str, request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        row = call(C.get_profile, engine, tenant, book_id)
        return call(src.read_book_text, schema(), src.runner(crm_file()), row["book_id"])

    @app.post("/api/v1/categories/books/{book_id}/propose")
    async def categories_book_propose(book_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        llm = rt().llm_for("categories")
        if body.get("reset"):
            need(user, "ozellik:kategori.profil-onay", "Kararları sıfırlama")
        try:
            out = await run_in_threadpool(call, propose_one, engine, tenant, user, book_id, llm,
                                          reset=bool(body.get("reset")), fields=body.get("fields") or None)
        except HTTPException:
            raise
        except Exception as e:  # noqa: BLE001 — model kesintisi
            log.warning("kategori önerisi üretilemedi (%s): %s", book_id, e)
            raise HTTPException(status_code=503, detail={"code": "CATEGORY_MODEL",
                                                          "message": "Zeki AI şu an cevap vermiyor; biraz sonra yeniden deneyin."}) from e
        audit(engine, user, "run", "book_profile", out["bookId"], out.get("name"),
              {"oneri": sorted((out.get("fields") or {}).keys()), "modelCagrisi": out.get("modelCalls"), "sifirla": bool(body.get("reset"))})
        return out

    @app.post("/api/v1/categories/books/{book_id}/decision")
    def categories_book_decision(book_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, "ozellik:kategori.profil-onay", "Kitap profili onayı")
        out = call(C.decide, engine, tenant, user, book_id, body, me_crm_id=me_crm(user), everyone=everyone(user))
        action = "approve" if out["status"] == "onayli" else "update"
        audit(engine, user, action, "book_profile", out["bookId"], out.get("name"), out.get("changed"))
        return out

    # ------------------------------------------------------------------ bulgular ve kurallar

    @app.get("/api/v1/categories/findings")
    def categories_findings(request: Request, rule: str = "", status: str = "acik", owner: str = "", q: str = "",
                            page: int = 0) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        mine = me_crm(user) if owner == "me" else None
        return izli(engine, tenant, lambda: call(C.list_findings, engine, tenant, rule=rule, status=status, owner=mine, q=q,
                                                 page=max(0, page)),
                    prefix="portal.kategori.bulgular", title="Tutarsızlıklar", text=CK.F_BULGU, skip=("page", "pageSize"))

    @app.post("/api/v1/categories/findings/apply")
    def categories_findings_apply(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, "ozellik:kategori.profil-onay", "Kitap profili onayı")
        ids = [str(x) for x in (body.get("ids") or []) if x]
        if not ids:
            raise HTTPException(status_code=400, detail={"code": "CATEGORY", "message": "Bulgu seçilmedi."})
        out = call(C.apply_findings, engine, tenant, user, ids, me_crm_id=me_crm(user), everyone=everyone(user))
        audit(engine, user, "update", "category_finding", None, "Tutarsızlık önerileri uygulandı",
              {"uygulanan": len(out["applied"]), "atlanan": len(out["skipped"])})
        return out

    @app.post("/api/v1/categories/findings/{finding_id}/status")
    def categories_finding_status(finding_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        if not (can(user, "ozellik:kategori.profil-onay") or can(user, "ozellik:kategori.agac-duzenle")):
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "Bulgu kararı rolünüzde yok."})
        out = call(C.set_finding_status, engine, tenant, user, finding_id, str(body.get("status") or ""), body.get("note"))
        audit(engine, user, "update", "category_finding", finding_id, out["ruleLabel"], {"durum": out["status"], "not": out["note"]})
        return out

    @app.get("/api/v1/categories/rules")
    def categories_rules(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return {"items": C.rules(engine, tenant)}

    @app.put("/api/v1/categories/rules/{key}")
    async def categories_rule_update(key: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        out = await run_in_threadpool(call, C.update_rule, engine, tenant, user, key, body)
        re = await run_in_threadpool(C.reresolve, engine, tenant)
        audit(engine, user, "update", "category_rule", key, out["label"], {"acik": out["enabled"], "param": out["params"],
                                                                         "bulgu": re.get("findings")})
        return out

    # ------------------------------------------------------------------ CRM'e işlenecek fark

    @app.get("/api/v1/categories/crm-diff")
    def categories_crm_diff(request: Request, owner: str = "", q: str = "") -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        mine = me_crm(user) if owner == "me" else None
        return izli(engine, tenant, lambda: call(C.crm_diff, engine, tenant, owner=mine, q=q),
                    prefix="portal.kategori.crmfarki", title="CRM farkı", text=CK.F_FARK, logo=False)

    @app.get("/api/v1/categories/crm-diff/export.xlsx")
    def categories_crm_diff_export(request: Request, owner: str = "") -> Response:
        engine, tenant, user, _ = ctx(request)
        mine = me_crm(user) if owner == "me" else None
        diff = call(C.crm_diff, engine, tenant, owner=mine)
        data = C.crm_diff_xlsx(diff, user)
        audit(engine, user, "run", "category_export", None, "CRM'e işlenecek fark (Excel)", {"satir": diff["total"]})
        return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": 'attachment; filename="crm-islenecek-fark.xlsx"'})

    # ------------------------------------------------------------------ etiket sözlüğü

    @app.get("/api/v1/categories/tags")
    def categories_tags(request: Request, status: str = "oneri", q: str = "", page: int = 0) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return izli(engine, tenant, lambda: C.list_tags(engine, tenant, status=status, q=q, page=max(0, page)),
                    prefix="portal.kategori.etiketler", title="Etiketler", text=CK.F_ETIKET, logo=False,
                    skip=("page", "pageSize"))

    @app.post("/api/v1/categories/tags/decision")
    def categories_tag_decision(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(C.decide_tag, engine, tenant, user, str(body.get("tag") or ""), str(body.get("status") or ""),
                   body.get("mergedInto"))
        audit(engine, user, "update", "category_tag", out["tag"], out["tag"], {"durum": out["status"], "birlesti": out["mergedInto"]})
        return out

    # ------------------------------------------------------------------ sözleşme (diğer modüller)

    @app.get("/api/v1/categories/profile/{stock_code}")
    def categories_profile(stock_code: str, request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return call(C.profile_by_stock, engine, tenant, stock_code)

    @app.get("/api/v1/categories/nodes")
    def categories_nodes(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return C.nodes_flat(engine, tenant)

    @app.get("/api/v1/categories/nodes/{node_id}/books")
    def categories_node_books(node_id: str, request: Request, page: int = 0, approved_only: bool = False) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return call(C.node_books, engine, tenant, node_id, page=max(0, page), include_resolved=not approved_only)

    return job
