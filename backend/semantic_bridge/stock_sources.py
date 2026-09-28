"""M43 Depo ve stok: Logo ve CRM okuması (yalnız okuma — Logo'ya, CRM'e ve T-soft'a hiçbir şey yazılmaz).

Sorgular `stock_sql/*.sql` dosyalarındadır; ekrandaki «kaynak» paneli aynı metni gösterir. Baskı Öneri raporunun
(M11) iki kaynağı **içe aktarılır, kopyalanmaz**: satış hızı (`management/sql/baski_oneri/logo_satis_hizi.sql`, yıllık
satış görünümleri `{satis:2024}` ile) ve CRM bekleyen sipariş (`crm_bekleyen_siparis.sql`); mevcut raporun depo stoku
(`logo_depo_stok.sql`, `EOS_DEPO_STOK_KONTROL_211` görünümü) karşılaştırma için okunur. Böylece «satış hızı» ve
«tükenme süresi» Baskı Öneri ile birebir aynı sayıdır.

Tanımlar (katalog, `configs/semantic/knowledge/logo/knowledge/metrics/logo-timas.md`):

- **Stok bakiyesi** = güncel yıl kopyasında `IOCODE 1,2` giriş − `3,4` çıkış, `LINETYPE 0`, `CANCELLED 0`, tarih süzgeci
  yok; ambar = `SOURCEINDEX` (Kural 14). Planlanan üretimden giriş fişi (`PRODSTAT 1`) ayarla dışarıda (M29 ile aynı karar).
- **Stok devir hızı** = katalogdaki sertifikalı ifade, birebir (`logo_devir.sql`).
- **Hareketsiz** = pencerede `STLINE` satırı olmayan (Kural 17); açılış devri (TRCODE 14) hareket sayılmaz.
- **Bekleyen sipariş (Logo)** = `ORFLINE TRCODE 1, CLOSED 0, CANCELLED 0, LINETYPE 0`, `AMOUNT − SHIPPEDAMOUNT`.
- **Satış** = faturalı satır (M46 ile aynı): net satış `INVOICEREF <> 0`, iade eksi.

CRM: raf stoğu `new_serilothareketsatiri.new_kalanmiktar` (ürün × raf × depo), Logo'ya aktarılamamış hareket
`new_malzemehareketi` (`new_logoyaaktarildi = 0`, mesaj dolu = hata), bekleyen ürün `new_bekleyenurun` (durum 1), sipariş
hazırlık hattı `new_siparis` aşama tarihleri. `SystemUser.new_deposifre` / `new_depokullaniciadi` hiçbir sorguda seçilmez.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable, Optional

from semantic_bridge import budget_sources as bsrc
from semantic_bridge.budget_sources import Runner, SourceError, firms_by_year  # noqa: F401 — yeniden kullanım
from semantic_bridge.distribution_sources import crm_prefix

log = logging.getLogger("semantic.stock.sources")

SQL_DIR = Path(__file__).with_name("stock_sql")
_FIRM = re.compile(r"^[0-9]{3}$")
_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")

#: (kimlik, bağlantı, başlık, açıklama) — ekrandaki kaynak paneli. `baski-oneri:` önekli olanlar Baskı Öneri'nin dosyası.
SOURCES = [
    ("logo_bakiye", "logo", "Stok bakiyesi (ambar kırılımlı)", "Güncel yıl kopyası, giriş − çıkış, tarih süzgeci yok."),
    ("logo_ambarlar", "logo", "Ambarlar", "Logo ambar tanımları."),
    ("baski-oneri:logo_satis_hizi", "logo", "Satış hızı (Baskı Öneri)", "Ağırlıklı aylık satış hızı; Baskı Öneri raporuyla aynı dosya."),
    ("baski-oneri:logo_depo_stok", "logo", "Mevcut rapordaki depo stoku", "Karşılaştırma için; Baskı Öneri raporunun kaynağı."),
    ("logo_devir", "logo", "Stok devir hızı", "Katalogdaki sertifikalı ölçü."),
    ("logo_hareket", "logo", "Pencerede hareket", "Hareketsiz stok ve 12 ay net satış (faturalı satır)."),
    ("logo_orfline_bekleyen", "logo", "Logo bekleyen sipariş", "Açık satış siparişi satırları."),
    ("baski-oneri:crm_bekleyen_siparis", "crm", "CRM bekleyen sipariş (Baskı Öneri)", "Açık sipariş satırları; Baskı Öneri raporuyla aynı dosya."),
    ("crm_raf_stok", "crm", "CRM raf stoğu", "Seri/lot kalan miktarı, ürün × raf × depo."),
    ("crm_depo", "crm", "CRM depoları", "Depo kartları ve raf sayısı."),
    ("crm_aktarim_hatasi", "crm", "Logo'ya aktarılmamış hareketler", "Aktarılmamış etkin malzeme hareketi fişleri."),
    ("crm_aktarim_urun", "crm", "Aktarılmamış hareket (kitap başına)", "Logo–CRM farkının kök nedeni."),
    ("crm_bekleyen_urun", "crm", "Bekleyen ürün", "Stok yokken açılan talepler."),
    ("crm_depo_hatti", "crm", "Sipariş hazırlık hattı", "Depo aşamasındaki siparişler ve sevkler."),
]


def sql_text(source_id: str) -> str:
    """Kaynağın SQL metni. `baski-oneri:` önekli kaynak yönetim raporlarının dosyasıdır (içe aktarma, kopya yok)."""
    if source_id.startswith("baski-oneri:"):
        from semantic_bridge import management

        return management.sql_text("baski-oneri", source_id.split(":", 1)[1])
    return (SQL_DIR / f"{source_id}.sql").read_text(encoding="utf-8")


def _firm(firm: str) -> str:
    if not _FIRM.match(firm or ""):
        raise SourceError("Logo firma numarası geçersiz.")
    return firm


def render(source_id: str, *, firm: str = "", schema: str = "", exclude_planned: bool = True,
           start: Optional[date] = None, end: Optional[date] = None) -> str:
    """Yer tutucuları doldurur. Değerler doğrulanmış kod/tarih/şema adıdır; kullanıcı metni SQL'e girmez."""
    text = sql_text(source_id)
    if "{planli_join}" in text:
        text = text.replace("{planli_join}", "LEFT JOIN dbo.LG_{firma}_01_STFICHE AS F ON F.LOGICALREF = L.STFICHEREF"
                            if exclude_planned else "")
        text = text.replace("{planli_kosul}", "AND NOT (L.TRCODE = 13 AND ISNULL(F.PRODSTAT, 0) = 1)" if exclude_planned else "")
    if "{firma" in text:
        f = _firm(firm)
        text = text.replace("{firma_nr}", str(int(f))).replace("{firma}", f)
    if "{crm}" in text:
        text = text.replace("{crm}", crm_prefix(schema))
    for key, v in (("{bas}", start), ("{bitis}", end)):
        if key in text:
            s = v.isoformat() if v else ""
            if not _DAY.match(s):
                raise SourceError("Tarih penceresi geçersiz.")
            text = text.replace(key, s)
    return text


def num(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    return n if n == n else None


def key(v: Any) -> str:
    return str(v or "").strip()


def day(v: Any) -> Optional[date]:
    return bsrc._day(v)


def clean(v: Any) -> Optional[str]:
    return bsrc._clean(v)


def _timed(run: Runner, runs: dict[str, dict[str, Any]], run_id: str, text: str) -> list[dict[str, Any]]:
    """Sorguyu çalıştırır ve sorgu bilgisi için çalışan metni, satır sayısını, süreyi ve anı saklar
    (`runs[run_id]`; ekrandaki «i» bu kaydı gösterir — şablon değil, çalışmış metin)."""
    t = time.monotonic()
    rows = run(text)
    runs[run_id] = {"sql": text, "rows": len(rows), "ms": int((time.monotonic() - t) * 1000), "at": time.time()}
    return rows


class Logo:
    """Logo okuması; yıl → firma eşlemesi bir kez okunur."""

    def __init__(self, run: Runner, exclude_planned: bool = True):
        self.run = run
        self.exclude_planned = exclude_planned
        self._firms: Optional[dict[int, str]] = None
        self.sql: dict[str, str] = {}
        #: Sorgu bilgisi: çalıştırma kimliği → {sql, rows, ms, at}. Yıl kopyası başına okunan kaynakta kimlik `ad:yıl`.
        self.runs: dict[str, dict[str, Any]] = {}

    @property
    def firms(self) -> dict[int, str]:
        if self._firms is None:
            self._firms = firms_by_year(self.run)
            if not self._firms:
                raise SourceError("Logo'da dönem tanımı okunamadı.")
        return self._firms

    @property
    def current(self) -> str:
        return self.firms[max(self.firms)]

    def _q(self, source_id: str, run_id: str = "", **kw: Any) -> list[dict[str, Any]]:
        text = render(source_id, exclude_planned=self.exclude_planned, **kw)
        self.sql[source_id] = text
        return _timed(self.run, self.runs, run_id or source_id, text)

    def data_end(self) -> Optional[date]:
        rows = _timed(self.run, self.runs, "logo_veri_sonu", bsrc.data_end_sql(self.current))
        return day(rows[0].get("son")) if rows else None

    def balances(self) -> tuple[dict[str, dict[str, Any]], dict[str, dict[int, float]]]:
        """(kitap → {ad, bakiye}, kitap → {ambar no → bakiye})."""
        items: dict[str, dict[str, Any]] = {}
        wh: dict[str, dict[int, float]] = {}
        for r in self._q("logo_bakiye", firm=self.current):
            k = key(r.get("stok_kodu"))
            if not k:
                continue
            q = num(r.get("bakiye")) or 0.0
            it = items.setdefault(k, {"ad": clean(r.get("ad")), "bakiye": 0.0})
            it["bakiye"] += q
            no = int(num(r.get("ambar_no")) or 0)
            wh.setdefault(k, {})[no] = wh.get(k, {}).get(no, 0.0) + q
        return items, wh

    def warehouses(self) -> dict[int, dict[str, Any]]:
        out = {}
        for r in self._q("logo_ambarlar", firm=self.current):
            out[int(num(r.get("ambar_no")) or 0)] = {"ad": clean(r.get("ambar_adi")), "maliyetGrubu": num(r.get("maliyet_grubu"))}
        return out

    def eos_stock(self) -> dict[str, float]:
        """Mevcut rapordaki (Power BI) depo stoku, Baskı Öneri'nin dosyasıyla."""
        text = sql_text("baski-oneri:logo_depo_stok")
        self.sql["baski-oneri:logo_depo_stok"] = text
        return {key(r["stok_kodu"]): num(r.get("depo_stok")) or 0.0
                for r in _timed(self.run, self.runs, "baski-oneri:logo_depo_stok", text) if key(r.get("stok_kodu"))}

    def speeds(self, today: date) -> dict[str, dict[str, Any]]:
        """Baskı Öneri'nin satış hızı sorgusu, aynı dosya ve aynı yıllık görünüm açılımıyla."""
        from semantic_bridge import management

        existing = {int(r["name"][-4:]) for r in self.run(
            "SELECT name FROM sys.views WHERE name LIKE 'V[_]SatisRaporu[_]20[0-9][0-9]'")}
        text, missing = management.expand_sales(sql_text("baski-oneri:logo_satis_hizi"), today, existing)
        self.sql["baski-oneri:logo_satis_hizi"] = text
        if missing:
            log.warning("stock: satış görünümü eksik yıllar %s", missing)
        return {key(r["stok_kodu"]): r for r in _timed(self.run, self.runs, "baski-oneri:logo_satis_hizi", text)
                if key(r.get("stok_kodu"))}

    def turnover(self) -> dict[str, Optional[float]]:
        return {key(r["stok_kodu"]): num(r.get("devir_hizi")) for r in self._q("logo_devir", firm=self.current)
                if key(r.get("stok_kodu"))}

    def movement(self, start: date, end: date) -> dict[str, dict[str, Any]]:
        """[start, end) penceresindeki hareket; pencerenin düştüğü her yıl kopyası okunur."""
        out: dict[str, dict[str, Any]] = {}
        for y in range(start.year, end.year + 1):
            f = self.firms.get(y)
            if not f:
                continue
            a, b = max(start, date(y, 1, 1)), min(end, date(y + 1, 1, 1))
            if a >= b:
                continue
            for r in self._q("logo_hareket", f"logo_hareket:{y}", firm=f, start=a, end=b):
                k = key(r.get("stok_kodu"))
                if not k:
                    continue
                cur = out.setdefault(k, {"son": None, "netSatis": 0.0})
                d = day(r.get("son_hareket"))
                if d and (cur["son"] is None or d > cur["son"]):
                    cur["son"] = d
                cur["netSatis"] += num(r.get("net_satis")) or 0.0
        return out

    def open_orders(self) -> dict[str, dict[str, float]]:
        return {key(r["stok_kodu"]): {"adet": num(r.get("bekleyen")) or 0.0, "siparis": num(r.get("siparis")) or 0.0}
                for r in self._q("logo_orfline_bekleyen", firm=self.current) if key(r.get("stok_kodu"))}


class Crm:
    """CRM okuması (Timas_MSCRM, salt okunur bağlantı)."""

    def __init__(self, run: Runner, schema: str):
        self.run = run
        self.schema = schema
        self.sql: dict[str, str] = {}
        self.runs: dict[str, dict[str, Any]] = {}

    def _q(self, source_id: str, **kw: Any) -> list[dict[str, Any]]:
        text = render(source_id, schema=self.schema, **kw)
        self.sql[source_id] = text
        return _timed(self.run, self.runs, source_id, text)

    def books(self) -> dict[str, dict[str, Any]]:
        return bsrc.read_books(self.run, self.schema.rstrip("."))

    def pending_orders(self) -> dict[str, float]:
        """Baskı Öneri'nin CRM bekleyen sipariş dosyası (B2C ve iki iç cari hariç)."""
        text = sql_text("baski-oneri:crm_bekleyen_siparis")
        self.sql["baski-oneri:crm_bekleyen_siparis"] = text
        return {key(r["stok_kodu"]): num(r.get("bekleyen_siparis")) or 0.0
                for r in _timed(self.run, self.runs, "baski-oneri:crm_bekleyen_siparis", text) if key(r.get("stok_kodu"))}

    def shelves(self) -> list[dict[str, Any]]:
        out = []
        for r in self._q("crm_raf_stok"):
            k = key(r.get("stok_kodu"))
            if not k:
                continue
            out.append({"stokKodu": k, "rafId": key(r.get("raf_id")).lower() or None, "raf": clean(r.get("raf")),
                        "rafTipi": {1: "Ana raf", 2: "Perakende raf"}.get(int(num(r.get("raf_tipi")) or 0)),
                        "satisaAcik": (num(r.get("satisa_acik")) or 0) == 1, "yerlesim": clean(r.get("yerlesim")),
                        "depoId": key(r.get("depo_id")).lower() or None, "depo": clean(r.get("depo")),
                        "depoNo": clean(r.get("depo_no")), "adet": num(r.get("kalan")) or 0.0})
        return out

    def depots(self) -> list[dict[str, Any]]:
        return [{"id": key(r.get("depo_id")).lower(), "ad": clean(r.get("depo")), "kod": clean(r.get("depo_kodu")),
                 "no": clean(r.get("depo_no")), "maliyetGrubu": num(r.get("maliyet_grubu")),
                 "etkin": (num(r.get("durum")) or 0) == 0, "raf": int(num(r.get("raf_sayisi")) or 0)}
                for r in self._q("crm_depo")]

    def transfers(self) -> list[dict[str, Any]]:
        out = []
        for r in self._q("crm_aktarim_hatasi"):
            out.append({"id": key(r.get("id")).lower(), "fisNo": clean(r.get("fis_no")), "belgeNo": clean(r.get("belge_no")),
                        "fisTarihi": day(r.get("fis_tarihi")), "olusturma": day(r.get("olusturma")),
                        "islemTuru": int(num(r.get("islem_turu")) or 0), "islemTipi": int(num(r.get("islem_tipi")) or 0),
                        "durum": int(num(r.get("durum")) or 0), "depo": clean(r.get("depo")),
                        "hata": (num(r.get("hata")) or 0) == 1, "mesaj": (str(r.get("mesaj")) if r.get("mesaj") is not None else None),
                        "satir": int(num(r.get("satir")) or 0), "miktar": num(r.get("miktar")) or 0.0})
        return out

    def transfer_items(self) -> dict[str, dict[str, float]]:
        return {key(r["stok_kodu"]): {"net": num(r.get("net")) or 0.0, "fis": num(r.get("fis")) or 0.0}
                for r in self._q("crm_aktarim_urun") if key(r.get("stok_kodu"))}

    def waiting_products(self) -> dict[str, dict[str, Any]]:
        return {key(r["stok_kodu"]): {"adet": num(r.get("adet")) or 0.0, "kayit": int(num(r.get("kayit")) or 0),
                                      "enEski": day(r.get("en_eski"))}
                for r in self._q("crm_bekleyen_urun") if key(r.get("stok_kodu"))}

    def pick_line(self, since: date) -> list[dict[str, Any]]:
        out = []
        for r in self._q("crm_depo_hatti", start=since):
            out.append({"id": key(r.get("id")).lower(), "no": clean(r.get("siparis_no")), "durum": int(num(r.get("durum")) or 0),
                        "tip": int(num(r.get("tip")) or 0), "oncelik": int(num(r.get("oncelik")) or 0),
                        "siparis": bsrc._day(r.get("siparis_tarihi")), "depoda": r.get("depoda"), "pusula": r.get("pusula"),
                        "kutulandi": r.get("kutulandi"), "sevk": r.get("sevk"), "depo": clean(r.get("depo")),
                        "toplayan": clean(r.get("toplayan")), "koli": num(r.get("koli"))})
        return out


def movement_window(end: date, days: int) -> tuple[date, date]:
    """Hareketsiz stok penceresi: [bitiş − gün, bitiş + 1)."""
    return end - timedelta(days=days), end + timedelta(days=1)


def runner_for(path: Callable[[], str]) -> Callable[[], Runner]:
    return lambda: bsrc.runner(path())
