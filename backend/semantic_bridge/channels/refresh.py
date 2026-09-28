"""M42 Logo/CRM okuması (arka plan, aynı anda tek okuma) ve kapsam hesabı.

Okunan: (1) kanal × ay (bütün cariler), (2) kapsamdaki grup × ay, (3) grup × kitap × ay, (4) kitap adları, (5) eşleme
listesinin cari kartları + CRM karşılığı, (6) CRM sipariş tipi sayıları, (7) CRM satış hedefleri (bölge × ay), (8) D2C
sekmesi site verisine bağlıysa barkod → stok kodu. Logo hatası okumayı durdurur (eski önbellek kalır); CRM hatası kayda
yazılır, Logo kısmı yine yazılır.

Kapsam = e-ticaret kanal kodları (Yönetim ayarı) ∪ kanal koduyla platforma bağlanan kodlar ∪ tek tek eşlenmiş cariler.
Eşleme kapsam dışı bir cariyi platforma bağlarsa o carinin satırı önbellekte yoktur: `missing_scope` bunu bildirir, API
okumayı başlatır.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import date, datetime
from typing import Any, Callable, Iterable, Optional

import sqlalchemy as sa

from semantic_bridge.channels import mapping as M
from semantic_bridge.channels import sources as src
from semantic_bridge.channels import store as S

log = logging.getLogger("semantic.channels.refresh")


def scope(engine: sa.engine.Engine, tenant: str, st: dict[str, Any]) -> dict[str, Any]:
    """Okuma kapsamı: kanal kodları, tek tek eşlenmiş (kapsam kodları dışında kalan) cari kodları ve SQL parçaları."""
    kmap = M.kanal_map(engine, tenant)
    km = sorted(k for k, v in kmap.items() if v != "degil")
    specodes = sorted(set(st["specodes"]) | set(km))
    # Tek tek eşlenen cari yalnız e-ticaret kanal kodlarının dışındaysa (ya da kanal koduyla bağlanan bir koddaysa, grup
    # ifadesinde öne geçsin diye) kapsama adıyla girer; e-ticaret kodlu cari zaten kod koşuluyla okunur.
    with engine.connect() as c:
        rows = c.execute(sa.select(S.ACCOUNTS.c.logo_cari_kodu, S.ACCOUNTS.c.kanal)
                         .where(S.ACCOUNTS.c.tenant_id == tenant, S.ACCOUNTS.c.durum == "onayli",
                                S.ACCOUNTS.c.platform.isnot(None), S.ACCOUNTS.c.platform != "degil")).all()
    base = set(st["specodes"])
    codes = sorted(r.logo_cari_kodu for r in rows if (r.kanal or "").strip() not in base)
    return {"specodes": specodes, "kanalMapped": km, "codes": codes,
            "scopeSql": src.scope_sql(specodes, codes), "grupSql": src.grup_sql(km, codes)}


def missing_scope(engine: sa.engine.Engine, tenant: str, st: dict[str, Any], years: Iterable[int]) -> list[int]:
    """Okunduktan sonra kapsamı genişleyen yıllar (yeni eşlenen cari ya da kanal kodu önbellekte yok)."""
    cur = scope(engine, tenant, st)
    out = []
    for y in years:
        m = S.meta_get(engine, tenant, f"read:{y}")
        if not m:
            continue
        if not set(cur["specodes"]) <= set(m.get("specodes") or []) or not set(cur["codes"]) <= set(m.get("codes") or []) \
                or sorted(cur["kanalMapped"]) != sorted(m.get("kanalMapped") or []):
            out.append(int(y))
    return out


def data_end(engine: sa.engine.Engine, tenant: str) -> Optional[date]:
    v = S.meta_get(engine, tenant, "data_end").get("date")
    return date.fromisoformat(v) if v else None


def h3_connected(engine: sa.engine.Engine) -> bool:
    try:
        return sa.inspect(engine).has_table("semantic_commerce_orders")
    except Exception:  # noqa: BLE001
        return False


class Refresher:
    def __init__(self, engine_fn: Callable[[], sa.engine.Engine], tenant_fn: Callable[[], str], logo_file: Callable[[], str],
                 crm_file: Callable[[], str], crm_schema: Callable[[], str], conf: Callable[[str], str]):
        self._engine, self._tenant = engine_fn, tenant_fn
        self._logo, self._crm, self._schema, self._conf = logo_file, crm_file, crm_schema, conf
        self._thread: Optional[threading.Thread] = None
        self._guard = threading.Lock()
        self.state: dict[str, Any] = {"running": False, "step": None, "startedAt": None, "error": None}

    # ------------------------------------------------------------------ durum

    def status(self) -> dict[str, Any]:
        engine, tenant = self._engine(), self._tenant()
        S.ensure(engine)
        reads = {k.split(":", 1)[1]: v for k, v in S.meta_like(engine, tenant, "read:").items()}
        de = S.meta_get(engine, tenant, "data_end")
        return {**self.state, "running": self.running(), "dataEnd": de.get("date"), "dataEndAt": de.get("_at"),
                "years": dict(sorted(reads.items())), "cards": S.meta_get(engine, tenant, "cards"),
                "crm": S.meta_get(engine, tenant, "crm")}

    def needed_years(self, engine: sa.engine.Engine, tenant: str, extra: Iterable[int] = ()) -> list[int]:
        st = M.settings(self._conf)
        end = data_end(engine, tenant)
        top = end.year if end else date.today().year
        years = {top - i for i in range(st["years"])} | set(extra)
        return sorted(y for y in years if 2015 <= y <= top)

    def due(self, engine: sa.engine.Engine, tenant: str, now: Optional[float] = None) -> list[int]:
        """Bayat yıllar: verinin son yılı `CHANNEL_TTL_SEC` (20 sa), geçmiş yıllar 7 gün; kapsamı genişleyen yıl hemen."""
        now = now or time.time()
        st = M.settings(self._conf)
        end = data_end(engine, tenant)
        top = end.year if end else date.today().year
        ttl_now = int(M._num(self._conf("CHANNEL_TTL_SEC"), 20 * 3600))
        ttl_past = 7 * 86400
        years = self.needed_years(engine, tenant)
        grown = set(missing_scope(engine, tenant, st, years))
        out = []
        for y in years:
            at = S.meta_get(engine, tenant, f"read:{y}").get("_at")
            age = now - datetime.fromisoformat(at).timestamp() if at else None
            if y in grown or age is None or age > (ttl_now if y >= top else ttl_past):
                out.append(y)
        return out

    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self, years: Optional[list[int]] = None) -> bool:
        with self._guard:
            if self.running():
                return False
            self.state.update(running=True, step="Başlıyor", startedAt=time.time(), error=None)
            self._thread = threading.Thread(target=self.run, args=(years,), daemon=True, name="channels-refresh")
            self._thread.start()
            return True

    # ------------------------------------------------------------------ okuma

    def run(self, years: Optional[list[int]] = None) -> dict[str, Any]:
        """`years` None = gereken bütün yıllar."""
        engine, tenant = self._engine(), self._tenant()
        S.ensure(engine)
        st = M.settings(self._conf)
        done: dict[str, Any] = {}
        try:
            self.state.update(running=True, step="Logo dönemleri")
            logo = src.runner(self._logo())
            firms = src.firms_by_year(logo)
            end = src.bsrc.read_data_end(logo, firms)
            if end:
                S.meta_set(engine, tenant, "data_end", {"date": end.isoformat()})
            latest = firms[max(firms)]
            want = self.needed_years(engine, tenant) if years is None else [y for y in years if y in firms]

            # Eşleme listesinin kartları (en son firmadan) + CRM karşılığı.
            self.state["step"] = "Cari kartları"
            sc = scope(engine, tenant, st)
            cards = src.read_cariler(logo, latest, src.scope_sql(st["specodes"], sc["codes"]))
            crm_err = None
            crm_info: dict[int, dict[str, Any]] = {}
            try:
                crm_run = src.runner(self._crm())
                crm_info = src.read_crm_accounts(crm_run, self._schema(), [c["ref"] for c in cards if c.get("ref") is not None])
            except src.SourceError as e:
                crm_run, crm_err = None, str(e)
            sync = S.sync_accounts(engine, tenant, cards, crm_info)
            S.meta_set(engine, tenant, "cards", {"count": len(cards), **sync, "crmError": crm_err})

            codes: set[str] = set()
            for y in want:
                self.state["step"] = f"{y} kanal karnesi"
                kan, ms1 = self._timed(lambda y=y: src.read_kanal(logo, firms, y))
                self.state["step"] = f"{y} cari satışları"
                car, ms2 = self._timed(lambda y=y: src.read_cari(logo, firms, y, sc["scopeSql"], sc["grupSql"]))
                self.state["step"] = f"{y} kitap × kanal"
                bok, ms3 = self._timed(lambda y=y: src.read_books(logo, firms, y, sc["scopeSql"], sc["grupSql"]))
                S.replace_year(engine, tenant, S.KANAL_MONTHS, y, kan)
                S.replace_year(engine, tenant, S.CARI_MONTHS, y, car)
                S.replace_year(engine, tenant, S.BOOK_MONTHS, y, bok)
                codes |= {r["stok_kodu"] for r in bok}
                S.meta_set(engine, tenant, f"read:{y}", {
                    "firm": firms[y], "kanal": len(kan), "cari": len(car), "kitap": len(bok), "dbMs": ms1 + ms2 + ms3,
                    "specodes": sc["specodes"], "codes": sc["codes"], "kanalMapped": sc["kanalMapped"],
                    "sirketCiro": round(sum(r["satis_ciro"] - r["iade_ciro"] for r in kan), 2)})
                done[str(y)] = {"kanal": len(kan), "cari": len(car), "kitap": len(bok)}

            if codes:
                self.state["step"] = "Kitap adları"
                S.upsert_books(engine, tenant, src.read_item_names(logo, latest, codes))
            if h3_connected(engine):
                self.state["step"] = "Barkodlar"
                bc = src.read_barcodes(logo, latest)
                S.replace_all(engine, tenant, S.BARCODES, [{"barkod": k, "stok_kodu": v} for k, v in bc.items()])

            # CRM: sipariş tipleri ve satış hedefleri. Hata kayda düşer, Logo kısmı yine geçerli.
            crm_meta: dict[str, Any] = {"error": crm_err}
            if crm_run is not None:
                try:
                    self.state["step"] = "CRM siparişleri"
                    S.meta_set(engine, tenant, "crm_orders", src.read_crm_orders(crm_run, self._schema(), st["orderDays"]))
                    self.state["step"] = "CRM satış hedefleri"
                    labels = src.read_target_labels(crm_run, self._schema())
                    codes_by_year = {int(v): int(k) for k, v in labels["years"].items() if str(k).lstrip("-").isdigit()}
                    codes_by_year.update(st["yearCodes"])
                    S.meta_set(engine, tenant, "target_labels", {"years": {str(y): c for y, c in codes_by_year.items()},
                                                                 "regions": labels["regions"]})
                    for y in want:
                        yc = codes_by_year.get(y)
                        if yc is None:
                            continue
                        rows = src.read_targets(crm_run, self._schema(), yc)
                        S.replace_year(engine, tenant, S.TARGETS, y, [
                            {"yil": y, "bolge": r["bolge"], "bolge_ad": labels["regions"].get(r["bolge"]), "satir": r["satir"],
                             "toplam": r["toplam"], "aylar_json": _json(r["aylar"])} for r in rows])
                except src.SourceError as e:
                    crm_meta["error"] = str(e)
            S.meta_set(engine, tenant, "crm", crm_meta)
            self.state.update(step=None, error=None)
            return {"ok": True, "years": done}
        except src.SourceError as e:
            self.state.update(step=None, error=str(e))
            return {"ok": False, "error": str(e), "years": done}
        except Exception as e:  # noqa: BLE001 — beklenmeyen hata ekranda düz cümle
            log.exception("channels refresh failed")
            self.state.update(step=None, error=f"Okuma yarıda kaldı: {str(e)[:200]}")
            return {"ok": False, "error": self.state["error"], "years": done}
        finally:
            self.state["running"] = False

    @staticmethod
    def _timed(fn: Callable[[], Any]) -> tuple[Any, int]:
        t = time.monotonic()
        out = fn()
        return out, int((time.monotonic() - t) * 1000)


def _json(v: Any) -> str:
    import json

    return json.dumps(v)
