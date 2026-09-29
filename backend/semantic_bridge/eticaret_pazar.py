"""M34 pazar yeri uçları: Logo okuması portal tablosunda, ekranı açan kişi Logo'yu beklemez (2026-09-29).

Neden yavaştı (test sunucusunda hazır cevap atlanarak `GET /eticaret/marketplaces` 14,0 / 5,8 sn, `/stock-risk` 7,5 / 6,9 sn):
her iki uç istek anında Logo'yu okuyordu (`eticaret_api.markets` / `stock_risk` eski `load`): firma listesi
(`L_CAPIPERIOD`) ve kesim günü (`MAX(DATE_)` fatura tablosu) 10 dakikada bir, pazar yeri cari × ay satışı iki yılın
firma kopyalarında (`marketplace_sql`) ve kitap kırılımı (`channel_books_sql`, STLINE ⋈ CLCARD ⋈ ITEMS) 30 dakikada bir.
Süre dolunca ya da köprü yeniden başlayınca bu okumalar ekranı açan kişinin isteğinde koşuyordu.

Şimdi üç okuma ayrı ayrı saklanır (`semantic_eticaret_market_reads`, kiracı + anahtar başına tek satır, JSON):
- `baglam`: yıl → firma, kesim günü (eski `firms_cache`, taze 10 dk);
- `pazar:<yıl>:<kanallar>`: iki yılın cari × ay satırları (eski «m» önbelleği, taze 30 dk);
- `risk:<yıl>:<kanallar>`: bu yılın kitap kırılımı (eski «r» önbelleği, taze 30 dk).
Her kayıtta okumada ÇALIŞAN Logo SQL'i (metin, satır, süre, an) durur; «i» penceresi onu gösterir (eskiden bellekteki
`cache_q` ile aynı). Uç önce süreç belleğine (`hizli_bellek`), yoksa tabloya bakar; kayıt tazelik süresinden eskiyse
değeri hemen verir, yenisini arkada okur. Logo yalnız hiç kayıt yokken beklenir (ilk kurulum). Gece turu (`run-due`,
04:30) üç okumayı da tazeler; «yenile=true» (ekrandaki pazar yeri yenilemesi) eskisi gibi Logo'yu bekler.

Rakamlar değişmez: saklanan satırlar Logo okumasının çıktısıdır (`eticaret_sources.read_*`), hesap aynı işlevlerle
(`marketplace_summary`, `marketplace_books`) istek anında yapılır. Logo'ya yazma yok; sayı tavanı yok.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from contextlib import contextmanager
from datetime import date, datetime, timezone
from typing import Any, Callable, Iterator, Optional

import sqlalchemy as sa

from semantic_bridge import eticaret as E
from semantic_bridge import eticaret_sources as src
from semantic_bridge import sorgu_yakala as Y
from semantic_bridge.hizli_bellek import Bellek

log = logging.getLogger("semantic.eticaret.pazar")

TABLE_NAME = "semantic_eticaret_market_reads"
_md = sa.MetaData()
READS = sa.Table(
    TABLE_NAME, _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("anahtar", sa.String(300), primary_key=True),
    sa.Column("veri_json", sa.Text, nullable=False),
    sa.Column("okundu", sa.DateTime(timezone=True), nullable=False),
)

#: Tazelik (sn): eski uç bellekleriyle aynı — firma/kesim 10 dk, pazar yeri okumaları 30 dk.
TAZE_BAGLAM = float(os.environ.get("ECOM_MARKET_CONTEXT_FRESH_SEC", "600") or 600)
TAZE_OKUMA = float(os.environ.get("ECOM_MARKET_FRESH_SEC", "1800") or 1800)
#: Bundan eski kayıt verilmez, Logo beklenir (gece turu durmuş ve kimse açmamışsa). Varsayılan 7 gün.
BAYAT = max(TAZE_OKUMA, float(os.environ.get("ECOM_MARKET_STALE_MAX_SEC", str(7 * 86400)) or 7 * 86400))

_lock = threading.Lock()
_ready: set[int] = set()


def ensure(engine: sa.engine.Engine) -> None:
    with _lock:
        if id(engine) in _ready:
            return
        _md.create_all(engine, checkfirst=True)
        _ready.add(id(engine))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(v: Optional[datetime]) -> Optional[datetime]:
    if v is None:
        return None
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


@contextmanager
def _yalniz_yakala() -> Iterator[Y.Yakalanan]:
    """Logo okumasının sorguları yalnız bu kayda yazılır: isteğin açık yakalamasına ikinci kez düşüp «2 kez çalıştı»
    yazmasın (uç, saklanan sorguları ayrıca ekler)."""
    token = Y._ACTIVE.set(())
    try:
        with Y.yakala() as q:
            yield q
    finally:
        Y._ACTIVE.reset(token)


# ------------------------------------------------------------------ JSON (tarih ve int anahtarları geri kurulur)


def _dump_baglam(v: dict[str, Any]) -> str:
    return json.dumps({"firms": {str(k): f for k, f in v["firms"].items()}, "cut": v["cut"].isoformat() if v["cut"] else None,
                       "q": v["q"], "okundu": v["okundu"]}, ensure_ascii=False, default=str)


def _load_baglam(s: str) -> dict[str, Any]:
    d = json.loads(s)
    return {"firms": {int(k): f for k, f in (d.get("firms") or {}).items()},
            "cut": date.fromisoformat(d["cut"]) if d.get("cut") else None, "q": d.get("q") or [], "okundu": d.get("okundu")}


def _dump_rows(v: dict[str, Any]) -> str:
    return json.dumps(v, ensure_ascii=False, default=str)


def _load_rows(s: str) -> dict[str, Any]:
    return json.loads(s)


class PazarOkuma:
    """Pazar yeri Logo okumaları: bellek → tablo → Logo. `engine`, `tenant`, `logo_file` register'daki bağımlılıklardır."""

    def __init__(self, engine: Callable[[], Any], tenant: Callable[[], str], logo_file: Callable[[], str]) -> None:
        self.engine, self.tenant, self.logo_file = engine, tenant, logo_file
        # Kayıt başına (uygulama başına) ayrı bellek: testlerde her istemci kendi belleğini kullanır.
        self.bellek = Bellek("eticaret.pazar", taze=TAZE_OKUMA, bayat=BAYAT, en_cok=256)
        self.baglam_bellek = Bellek("eticaret.pazar.baglam", taze=TAZE_BAGLAM, bayat=BAYAT, en_cok=16)

    # -------------------------------------------------------------- tablo

    def _tablodan(self, engine: Any, tenant: str, anahtar: str) -> Optional[tuple[str, datetime]]:
        ensure(engine)
        with engine.connect() as c:
            r = c.execute(sa.select(READS.c.veri_json, READS.c.okundu)
                          .where(READS.c.tenant_id == tenant, READS.c.anahtar == anahtar)).first()
        return (r.veri_json, _aware(r.okundu)) if r else None

    def _yaz(self, engine: Any, tenant: str, anahtar: str, body: str, at: datetime) -> None:
        ensure(engine)
        try:
            with engine.begin() as c:
                c.execute(READS.delete().where(READS.c.tenant_id == tenant, READS.c.anahtar == anahtar))
                c.execute(READS.insert().values(tenant_id=tenant, anahtar=anahtar, veri_json=body, okundu=at))
        except Exception as e:  # noqa: BLE001 — kayıt yazılamasa da okunan değer ekrana gider
            log.warning("eticaret pazar: okuma kaydı yazılamadı (%s): %s", anahtar, e)

    # -------------------------------------------------------------- ortak akış

    def _al(self, bellek: Bellek, taze: float, anahtar: str, oku: Callable[[], dict[str, Any]],
            dump: Callable[[dict[str, Any]], str], load: Callable[[str], dict[str, Any]], zorla: bool, arkada: bool) -> dict[str, Any]:
        engine, tenant = self.engine(), self.tenant()
        key = (tenant, anahtar)

        def logo_oku() -> dict[str, Any]:
            v = oku()
            self._yaz(engine, tenant, anahtar, dump(v), datetime.fromisoformat(v["okundu"]))
            return v

        def hesap() -> dict[str, Any]:
            # Süreçte hiç değer yoksa önce saklanan okuma (köprü yeniden başladı); varsa ya da tablo boşsa Logo.
            if bellek.an(key) is None:
                row = self._tablodan(engine, tenant, anahtar)
                if row is not None:
                    return load(row[0])
            return logo_oku()

        if zorla:
            return bellek.al(key, logo_oku, zorla=True)
        v = bellek.al(key, hesap)
        yas = _yas(v)
        if arkada or yas is None or yas >= taze:
            bellek.isit(key, logo_oku)
        return v

    # -------------------------------------------------------------- okumalar

    def baglam(self, zorla: bool = False, arkada: bool = False) -> dict[str, Any]:
        """{firms: {yıl: firma}, cut: date|None, q: [çalışan Logo SQL'i], okundu: iso}."""
        def oku() -> dict[str, Any]:
            run = Y.izle(src.runner(self.logo_file()), "logo", Y.db_of(self.logo_file()))
            with _yalniz_yakala() as fq:
                firms = src.firms_by_year(run)
                cut = src.read_data_end(run, firms)
            return {"firms": firms, "cut": cut, "q": fq.queries, "okundu": _now().isoformat()}
        return self._al(self.baglam_bellek, TAZE_BAGLAM, "baglam", oku, _dump_baglam, _load_baglam, zorla, arkada)

    def this_year(self, zorla: bool = False) -> int:
        cut = self.baglam(zorla)["cut"]
        return cut.year if cut else date.today().year

    def pazar(self, year: int, channels: list[str], zorla: bool = False, arkada: bool = False) -> dict[str, Any]:
        """{rows: cari × ay satırları (geçen yıl aynı dönem + bu yıl), q, okundu, cut, firms}."""
        def oku() -> dict[str, Any]:
            b = self.baglam()
            run = Y.izle(src.runner(self.logo_file()), "logo", Y.db_of(self.logo_file()))
            this, prev = E.marketplace_windows(year, b["cut"])
            with _yalniz_yakala() as mq:
                rows = (src.read_marketplaces(run, b["firms"], channels, *prev)
                        + src.read_marketplaces(run, b["firms"], channels, *this))
            return {"rows": rows, "q": mq.queries, "okundu": _now().isoformat(), **_kesim(b)}
        return self._al(self.bellek, TAZE_OKUMA, _anahtar("pazar", year, channels), oku, _dump_rows, _load_rows, zorla, arkada)

    def risk(self, year: int, channels: list[str], zorla: bool = False, arkada: bool = False) -> dict[str, Any]:
        """{rows: bütün pazar yeri carilerinin kitap kırılımı (bu yıl), q, okundu, cut, firms}."""
        def oku() -> dict[str, Any]:
            b = self.baglam()
            run = Y.izle(src.runner(self.logo_file()), "logo", Y.db_of(self.logo_file()))
            this, _ = E.marketplace_windows(year, b["cut"])
            with _yalniz_yakala() as rq:
                rows = src.read_channel_books(run, b["firms"], channels, *this)
            return {"rows": rows, "q": rq.queries, "okundu": _now().isoformat(), **_kesim(b)}
        return self._al(self.bellek, TAZE_OKUMA, _anahtar("risk", year, channels), oku, _dump_rows, _load_rows, zorla, arkada)


def _kesim(b: dict[str, Any]) -> dict[str, Any]:
    """Okumanın yapıldığı bağlam: kesim günü, firma listesi ve onları bulan sorgular (satırla birlikte saklanır; ekrandaki
    kesim ve «i» okumanın kendi bağlamını gösterir)."""
    return {"cut": b["cut"].isoformat() if b["cut"] else None, "firms": sorted(b["firms"]), "baglamQ": b["q"]}


def _anahtar(kind: str, year: int, channels: list[str]) -> str:
    return f"{kind}:{int(year)}:" + ",".join(channels)


def _yas(v: dict[str, Any]) -> Optional[float]:
    try:
        at = datetime.fromisoformat(str(v.get("okundu")))
    except (TypeError, ValueError):
        return None
    return (_now() - _aware(at)).total_seconds()


def cut_of(v: dict[str, Any]) -> Optional[date]:
    return date.fromisoformat(v["cut"]) if v.get("cut") else None
