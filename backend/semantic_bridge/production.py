"""M12 Üretim Yönetimi: baskı kararı verilmiş kitapların üretim takvimi, matbaa takibi, gecikme uyarıları.

Kaynaklar (2026-09-28 canlı ölçüm; ayrıntı geliştirme günlüğünde):

- **CRM üretim kartı** `new_UretimBase`: kitap + baskı numarası başına bir kart (2026'da 1.708 etkin kart). Kart
  türü (`new_baskikartidurumu`: yeni baskı / baskı tekrarı / yenileme), üretim aşaması (`statuscode`), matbaa
  (seçenek listesi, 40 matbaa), kesin adet ve fiyat, öncelik, bekleme nedeni, sorumlu editör/grafiker, kitap
  (`new_kitapid`), Logo stok kodu. Tarihlerin bir kısmı **plandır** (CRM takvimi, gün dağılımı tek güne yığılı:
  baskı tarihi %99 ayın 1'i, üretim teslim ayın 15'i, grafik teslim 25'i), bir kısmı **gerçekleşen** (matbaa
  belirleme, baskıya hazır, depo girişi: bütün günlere yayılı).
- **Logo** (gerçekleşen üretim): üretim emri `LG_<firma>_PRODORD` (açıklama 1 = CRM kartının üretim no'su
  `URTN-…`; 2026'da emirlerin %55'inde dolu, boş olanlar stok koduyla eşlenir) ve emre bağlı üretimden giriş fişleri
  (`STFICHE` TRCODE 13, `PRODORDERREF`). `PRODSTAT` 1 = planlanan giriş (emir başına bir fiş, planlanan adet),
  0 = gerçek giriş (emir başına ortalama 1,5 fiş, planlanan adedin %103'ü). Firma yıla göre değişir (211 = 2021–2025,
  411 = 2026); hangi firmaların okunacağı `L_CAPIPERIOD`'dan ölçülür.
- **Portal kayıtları** (`production_store`): CRM'de olmayan ya da CRM'e yazılamayanlar.

Baskı tekrarı kartları önceki karttan kopyalanarak açılıyor: gerçekleşen tarih kolonlarında önceki baskının tarihi
kalıyor (2025-06 sonrası 2.393 tekrar kartının 33'ünde depo, 100'ünde baskıya hazır tarihi kart açılmadan 30 günden
eski). Kart açılışından 30 günden eski «gerçekleşen» tarih önceki baskınındır, bu karta sayılmaz.

CRM ve Logo yalnız okunur, köprünün kendi salt okunur bağlantılarıyla (yönetim raporları ve SEO/GEO'daki gibi).
Bir okuma ≈ 45 sn sürer (2026-09-28: CRM 10 sn, Logo 33 sn). Son okuma diskte kalır (`PRODUCTION_CACHE_DIR`, türleri koruyan
JSON; pickle değil) ve istek onu hemen alır; 5 dakikadan eskiyse yenisi arka planda okunur. İstek yalnız hiç okuma yokken (ilk kurulum, okuma sorguları
değişti) ya da «Verileri yenile»de (X-Data-Refresh) kaynağı bekler.

Kartların kurulması (okuma + portal kayıtları → birleştirme, plan, gecikme) ve özet de süreç belleğindedir
(2026-09-29): anahtar okumanın anı + portal kayıtlarının parmak izi + ayarlar + gün; yeni okuma bitince ve portal kaydı
yazılınca arkada yeniden kurulur. Bellek yalnız bu ekranın uçlarınındır; diğer modüller `Service.cards` ile her seferinde
kendi kopyalarını kurar.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import statistics
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Optional
from zoneinfo import ZoneInfo

# Uç imzalarındaki `Request` modül düzeyinde olmalı: `from __future__ import annotations` tip adını modülün
# globallerinde arar; fonksiyon içinde içe aktarılırsa `request` sorgu parametresi sanılır ve her uç 422 döner.
from fastapi import HTTPException, Request

from semantic_layer.firm_scope import firm_in_scope

from semantic_bridge import hizli_bellek as HB
from semantic_bridge import production_plan as plan_mod
from semantic_bridge import production_store as store
from semantic_bridge import typed_json as TJ
from semantic_bridge.production_plan import KEYS, MILESTONES, STAGES, parse_day
from semantic_bridge.production_store import ProductionError

log = logging.getLogger("semantic.production")
TZ = ZoneInfo("Europe/Istanbul")
UTC = ZoneInfo("UTC")
TTL = 300
PAGE_SIZE = 50
#: Baskı tekrarı kartında kart açılışından bu kadar eski «gerçekleşen» tarih önceki baskınındır.
INHERITED_DAYS = 30
_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_FIRM = re.compile(r"^[0-9]{3}$")
_PERIOD = re.compile(r"^[0-9]{2}$")


def today() -> date:
    return datetime.now(TZ).date()


def _prefix(schema: str) -> str:
    db, _, sch = (schema or "").strip().rpartition(".")
    for part in (db, sch):
        if part and not _NAME.match(part):
            raise ProductionError(f"CRM şeması «{schema}» geçerli bir ad değil.", 503)
    if not sch:
        raise ProductionError("CRM şeması girilmemiş; CRM okunamıyor.", 503)
    return (f"{db}." if db else "") + f"{sch}."


# ------------------------------------------------------------------------------------------ CRM

#: Gerçekleşen tarih kolonları (nokta → kolon).
CRM_ACTUAL = {"matbaa": "new_MatbaaBelirlemeTarihi", "dosya": "new_baskiyahazirtarihi", "depo": "new_DepoGiriTarihi"}
#: CRM takviminin plan kolonları (anahtar → kolon); `dosya` ve `baski` kartın planıdır.
CRM_PLAN = {"grafik": "new_dosyalaringrafikteslimtarihi", "son": "new_sontarih", "dosya": "new_uretimteslimtarihi",
            "baski": "new_new_baskitarihi", "dagilim": "new_dagilimtarihi"}
#: Ekrandaki «CRM'deki bütün tarihler» (kolon, ad, plan mı).
CRM_DATES = [
    ("new_editoryalhazirliktarihi", "Editoryal hazırlık", False),
    ("new_dosyalaringrafikteslimtarihi", "Dosyaların grafiğe teslimi (plan)", True),
    ("new_BilgiKontrolTarihi", "Bilgi kontrolü", False),
    ("new_kesinadetfiyattarihi", "Kesin adet ve fiyat", False),
    ("new_MatbaaBelirlemeTarihi", "Matbaa belirleme", False),
    ("new_sontarih", "Son tarih (plan)", True),
    ("new_baskiyahazirtarihi", "Baskıya hazır", False),
    ("new_uretimteslimtarihi", "Üretime teslim (plan)", True),
    ("new_baskilistetarihi", "Baskı listesine alındı", False),
    ("new_bandrolalinantarih", "Bandrol alındı", False),
    ("new_new_baskitarihi", "Baskı tarihi (plan)", True),
    ("new_dagilimtarihi", "Dağılım (plan)", True),
    ("new_DepoGiriTarihi", "Depo girişi", False),
]
#: CRM üretim aşaması (statuscode) → tarihsiz de olsa gerçekleşmiş sayılan noktalar.
STATUS_DONE = {100000005: ("matbaa", "dosya"), 100000006: ("matbaa", "dosya", "baski", "depo")}
STATUS_CANCELLED = 100000007
STATUS_WAITING = 100000008
#: Basılmayan üretimler: e-kitap türü ve e-kitap aşamaları.
EBOOK_TYPE = 8
EBOOK_STATUS = (100000011, 100000012)
#: Üretim tipi «Kitap» (`new_UretimTipi`); diğerleri promosyon, set, katalog, dergi, defter, ajanda…
KIND_BOOK = 100000000
#: Kart türü (`new_baskikartidurumu`): 1 baskı tekrarı, 2 yeni baskı, 3 yenileme.
CARD_REPRINT = 1
#: Seçenek listesi kolonları (StringMap adı küçük harf).
OPTION_ATTRS = ("new_matbaa", "new_uretimtipi", "new_baskitipi", "statuscode", "new_baskikartidurumu", "new_oncelikdurumu",
                "new_beklemedurumu", "new_bandroldurumu")


def crm_cards_sql(schema: str, since: date) -> str:
    p = _prefix(schema)
    dates = ", ".join(f"r.{c}" for c, _, _ in CRM_DATES)
    return (
        "SELECT r.new_UretimId AS id, r.new_name AS name, r.new_uretimidno AS idno, r.new_StokKodu AS stok,"
        " r.new_BaskiNo AS baski_no, CAST(r.new_baskikartidurumu AS int) AS kart, CAST(r.new_UretimTipi AS int) AS tip,"
        " CAST(r.new_Matbaa AS int) AS matbaa, CAST(r.statuscode AS int) AS durum, CAST(r.new_oncelikdurumu AS int) AS oncelik,"
        " CAST(r.new_BeklemeDurumu AS int) AS bekleme, CAST(r.new_bandroldurumu AS int) AS bandrol, r.new_baskiayi AS baski_ayi,"
        " r.new_kesinlesenbaskiadeti AS adet, r.new_onerilenbaskiadeti AS oneri_adet, r.new_netbaskiadedi AS net_adet,"
        " r.new_kesinlesenbaskifiyati AS fiyat, r.CreatedOn AS olusturma,"
        f" r.new_kitapid AS kitap_id, k.new_name AS kitap, u.FullName AS editor, g.FullName AS grafiker, {dates}"
        f" FROM {p}new_UretimBase r"
        f" LEFT JOIN {p}new_kitapBase k ON k.new_kitapId = r.new_kitapid"
        f" LEFT JOIN {p}SystemUserBase u ON u.SystemUserId = r.new_SorumluEditor"
        f" LEFT JOIN {p}SystemUserBase g ON g.SystemUserId = r.new_sorumlugrafiker"
        f" WHERE r.statecode = 0 AND r.CreatedOn >= '{since.isoformat()}'"
        f" AND ISNULL(CAST(r.new_UretimTipi AS int), 0) <> {EBOOK_TYPE}"
        f" AND CAST(r.statuscode AS int) NOT IN ({', '.join(str(s) for s in EBOOK_STATUS)})"
        " ORDER BY r.CreatedOn DESC"
    )


def crm_options_sql(schema: str) -> str:
    p = _prefix(schema)
    attrs = ", ".join(f"'{a}'" for a in OPTION_ATTRS)
    return (
        "SELECT s.AttributeName AS attr, s.AttributeValue AS code, s.Value AS label"
        f" FROM {p}StringMapBase s"
        f" WHERE s.ObjectTypeCode = (SELECT TOP 1 e.ObjectTypeCode FROM {p}EntityView e WHERE e.Name = 'new_uretim')"
        f" AND s.AttributeName IN ({attrs}) AND s.LangId = 1055"
    )


# ------------------------------------------------------------------------------------------ Logo

#: Üretim emri tablosu olan Logo firmaları (dönem tanımında olup tablosu olmayan firma okunmaz).
LOGO_TABLES_SQL = "SELECT name FROM sys.tables WHERE name LIKE 'LG[_]___[_]PRODORD'"


def _dbname(conn: Any) -> Optional[str]:
    """Bağlantının YALNIZ veritabanı adı (sorgu bilgisindeki «USE [..]» satırı için; sunucu, kullanıcı, parola okunmaz)."""
    cfg = getattr(conn, "cfg", None)
    db = str((cfg.get("database") if isinstance(cfg, dict) else "") or "").strip()
    return db if re.fullmatch(r"[A-Za-z0-9_\-\. ]{1,128}", db) else None


def logo_periods_sql(since: date) -> str:
    """Geçmiş penceresine düşen Logo firma/dönemleri (her yıl ayrı firma)."""
    return ("SELECT p.FIRMNR AS firma, p.NR AS donem FROM dbo.L_CAPIPERIOD p"
            f" WHERE p.ENDDATE >= '{since.isoformat()}'")


def _fp(firm: str, period: str) -> tuple[str, str]:
    if not _FIRM.match(firm or "") or not _PERIOD.match(period or ""):
        raise ProductionError("Logo firma/dönem numarası geçersiz.", 503)
    return firm, period


def logo_orders_sql(firm: str, since: date) -> str:
    _fp(firm, "01")
    return (
        "SELECT o.LOGICALREF AS ref, o.FICHENO AS no, o.DATE_ AS tarih, o.GENEXP1 AS idno, o.PLNAMOUNT AS plan_adet,"
        " o.PLNENDDATE AS plan_bit, o.STATUS AS durum, i.CODE AS stok"
        f" FROM dbo.LG_{firm}_PRODORD o LEFT JOIN dbo.LG_{firm}_ITEMS i ON i.LOGICALREF = o.ITEMREF"
        f" WHERE o.DATE_ >= '{since.isoformat()}'"
    )


def logo_receipts_sql(firm: str, period: str, since: date) -> str:
    """Emre bağlı üretimden giriş fişlerinin ana ürün satırı: PRODSTAT 1 planlanan, 0 gerçek."""
    firm, period = _fp(firm, period)
    return (
        "SELECT f.PRODORDERREF AS emir, f.PRODSTAT AS ps, f.FICHENO AS no, f.DATE_ AS tarih, l.AMOUNT AS adet,"
        " f.SOURCEINDEX AS ambar"
        f" FROM dbo.LG_{firm}_{period}_STFICHE f"
        f" JOIN dbo.LG_{firm}_{period}_STLINE l ON l.STFICHEREF = f.LOGICALREF"
        f" JOIN dbo.LG_{firm}_PRODORD o ON o.LOGICALREF = f.PRODORDERREF AND l.STOCKREF = o.ITEMREF"
        f" WHERE f.TRCODE = 13 AND f.CANCELLED = 0 AND l.LINETYPE = 0 AND f.PRODORDERREF > 0"
        f" AND o.DATE_ >= '{since.isoformat()}'"
    )


#: Matbaanın baskı faturası: alınan hizmet faturası (TRCODE 4), hizmet kartı «Komple Baskı Giderleri»; satırın özel
#: kodu kitabın stok kodu, miktarı basılan adet, fiyatı adet başı baskı bedeli (2026'da 1.638, 2024–25'te 4.406 satır).
PRINT_SERVICE = "730.38.381"


def logo_costs_sql(firm: str, period: str, since: date) -> str:
    firm, period = _fp(firm, period)
    return (
        "SELECT inv.DATE_ AS tarih, inv.FICHENO AS no, c.DEFINITION_ AS cari, l.SPECODE AS stok, l.AMOUNT AS adet,"
        " l.LINENET AS tutar"
        f" FROM dbo.LG_{firm}_{period}_INVOICE inv"
        f" JOIN dbo.LG_{firm}_{period}_STLINE l ON l.INVOICEREF = inv.LOGICALREF"
        f" JOIN dbo.LG_{firm}_SRVCARD s ON s.LOGICALREF = l.STOCKREF"
        f" JOIN dbo.LG_{firm}_CLCARD c ON c.LOGICALREF = inv.CLIENTREF"
        f" WHERE inv.TRCODE = 4 AND inv.CANCELLED = 0 AND l.LINETYPE = 4 AND s.CODE = '{PRINT_SERVICE}'"
        f" AND l.SPECODE <> '' AND inv.DATE_ >= '{since.isoformat()}'"
    )


#: Logo üretim emri durumu (PRODORD.STATUS): 2026'da 1.200 emrin 1.200'ünde 3 ile gerçek bitiş birlikte.
ORDER_STATUS = {1: "Açık", 3: "Kapandı", 4: "Durduruldu"}
ORDER_CLOSED = 3


# ------------------------------------------------------------------------------------------ okuma (önbellekli)

def _rows(result: Any) -> list[dict[str, Any]]:
    _, rows, _ = result
    return [{str(k).lower(): v for k, v in r.items()} for r in rows]


def _s(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _num(v: Any) -> Optional[float]:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _dayiso(v: Any) -> Optional[str]:
    """CRM tarihleri UTC saklanır (İstanbul gece yarısı = önceki gün 21:00): saatli değer İstanbul gününe çevrilir.
    Logo tarihleri saatsizdir (00:00), olduğu gibi kalır. 1900 ve öncesi Logo'nun «boş» değeridir."""
    if v is None:
        return None
    if isinstance(v, str) and len(v) > 10:
        # Bağlayıcı tarihleri ISO metni olarak verir ('2026-06-30T21:00:00'): saatiyle okunur, yoksa gün kayar.
        try:
            v = datetime.fromisoformat(v.strip().replace(" ", "T", 1).replace("Z", "+00:00"))
        except ValueError:
            pass
    if isinstance(v, datetime):
        if v.hour or v.minute:
            v = (v.replace(tzinfo=UTC) if v.tzinfo is None else v).astimezone(TZ)
        d = v.date()
    else:
        d = parse_day(v)
    if d is None or d.year < 1901:
        return None
    return d.isoformat()


def _close(conn: Any) -> None:
    try:
        conn.close()
    except Exception:  # noqa: BLE001
        pass


def _cache_dir() -> Path:
    return Path(os.environ.get("PRODUCTION_CACHE_DIR", "/data/nanobaseai/bi/var/production"))


#: Diskteki okumanın biçimi okuma sorgularına bağlıdır: sorgu değişince eski kayıt okunmaz.
SHAPE = hashlib.sha256("|".join((
    crm_cards_sql("s", date(2000, 1, 1)), crm_options_sql("s"), logo_periods_sql(date(2000, 1, 1)),
    logo_orders_sql("001", date(2000, 1, 1)), logo_receipts_sql("001", "01", date(2000, 1, 1)),
    logo_costs_sql("001", "01", date(2000, 1, 1)))).encode()).hexdigest()[:16]


class Source:
    """CRM + Logo okuması. Bağlantılar okuma başına açılıp kapanır (pyodbc bağlantısı iş parçacıkları arasında
    paylaşılamaz); aynı anda tek okuma yapılır. Son okuma bellekte ve diskte kalır, istek onu beklemeden alır; 5 dakikadan
    eskiyse yenisi arka planda okunur."""

    def __init__(self, crm_connect: Callable[[], Any], logo_connect: Callable[[], Any], schema: Callable[[], str],
                 history_from: Callable[[], date], cache_dir: Callable[[], Path] = _cache_dir):
        self._crm = crm_connect
        self._logo = logo_connect
        self._schema = schema
        self._history_from = history_from
        self._cache_dir = cache_dir
        self._lock = threading.Lock()        # _snap/_at
        self._reading = threading.Lock()     # aynı anda tek okuma
        self._snap: Optional[dict[str, Any]] = None
        self._at = 0.0
        self._disk_tried = False
        #: Yeni okuma bitince çağrılır (Service kartları beklemeden arkada kurar); hata okumayı düşürmez.
        self.on_new: Optional[Callable[[dict[str, Any]], None]] = None

    def _file(self) -> Path:
        """Türleri koruyan JSON + zlib (`typed_json`; 2026-09-29'a kadar pickle'dı). Pickle okunurken kod çalıştırabilir:
        klasöre yazabilen biri köprüde kod çalıştırırdı. Eski `snapshot.pkl` hiç açılmaz; ilk okumada kaynaktan okunur
        ve yeni kayıt yazılınca silinir."""
        return self._cache_dir() / "snapshot.json.z"

    def _legacy_file(self) -> Path:
        return self._cache_dir() / "snapshot.pkl"

    def _current(self) -> Optional[dict[str, Any]]:
        """Bellekteki ya da (köprü yeni kalktıysa) diskteki son okuma; geçmiş penceresi değiştiyse yok sayılır."""
        with self._lock:
            if self._snap is None and not self._disk_tried:
                self._disk_tried = True
                try:
                    saved = TJ.unpack(self._file().read_bytes())
                    if isinstance(saved, dict) and saved.get("shape") == SHAPE:
                        self._snap, self._at = saved["snap"], float(saved["at"])
                except FileNotFoundError:
                    pass
                except Exception as e:  # noqa: BLE001 — bozuk kayıt: kaynaktan okunur
                    log.warning("production: diskteki okuma açılamadı: %s", e)
            snap = self._snap
        if snap is not None and snap.get("since") != self._history_from().isoformat():
            return None
        return snap

    def _save(self, snap: dict[str, Any], at: float) -> None:
        path = self._file()
        tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_bytes(TJ.pack({"shape": SHAPE, "at": at, "snap": snap}))
            os.replace(tmp, path)
        except (OSError, TypeError, ValueError) as e:          # TypeError: typed_json'un tanımadığı tür (okuma bellekte kalır)
            log.warning("production: okuma diske yazılamadı (%s): %s", path, e)
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            return
        try:
            self._legacy_file().unlink(missing_ok=True)        # eski pickle: açılmadan silinir
        except OSError:
            pass

    def _refresh(self, asked: float) -> dict[str, Any]:
        """Kaynağı okur; bu istekten sonra başlamış bir okuma bittiyse onu kullanır."""
        with self._reading:
            with self._lock:
                if self._snap is not None and self._at >= asked:
                    return self._snap
            snap = self.read()
            at = time.time()
            with self._lock:
                self._snap, self._at = snap, at
            self._save(snap, at)
        if self.on_new is not None:
            try:
                self.on_new(snap)
            except Exception as e:  # noqa: BLE001 — ısıtma okumayı düşürmez
                log.warning("production: yeni okuma sonrası ısıtma başlatılamadı: %s", e)
        return snap

    def _refresh_later(self) -> None:
        if self._reading.locked():
            return

        def run() -> None:
            try:
                self._refresh(time.time())
            except Exception as e:  # noqa: BLE001 — eski okuma gösterilmeye devam eder
                log.warning("production: arka plan okuması başarısız: %s", e)

        threading.Thread(target=run, name="production-refresh", daemon=True).start()

    def peek(self) -> Optional[dict[str, Any]]:
        """Beklemeden: son okuma ya da None (okuma arka planda başlar)."""
        snap = self._current()
        if snap is None or time.time() - self._at >= TTL:
            self._refresh_later()
        return snap

    def snapshot(self, fresh: bool = False) -> dict[str, Any]:
        if not fresh:
            snap = self.peek()
            if snap is not None:
                return snap
        return self._refresh(time.time())

    def last(self) -> Optional[dict[str, Any]]:
        """Beklemeden ve okuma başlatmadan son okuma (sorgu bilgisi, uç cevabının dayandığı okuma)."""
        return self._current()

    def read(self) -> dict[str, Any]:
        since = self._history_from()
        started = time.monotonic()
        crm = self._crm()
        schema = self._schema()
        # Sorgu bilgisi: okumada ÇALIŞAN metin (firma/dönem kopyası ve tarih yerinde), satır, süre, an, veritabanı adı.
        # Sonuç satırı saklanmaz; ekrandaki «i» penceresi bunları gösterir.
        queries: list[dict[str, Any]] = []

        def run(conn: Any, kind: str, tag: str, sql: str, limit: int, **extra: Any) -> Any:
            t0 = time.monotonic()
            res = conn.execute(sql, limit)
            queries.append({"tag": tag, "conn": kind, "sql": sql, "rows": len(res[1]), "dbMs": int((time.monotonic() - t0) * 1000),
                            "at": time.time(), "database": _dbname(conn), **extra})
            return res

        try:
            cards = _rows(run(crm, "crm", "crm.kartlar", crm_cards_sql(schema, since), 1_000_000))
            options: dict[str, dict[int, str]] = {}
            for r in _rows(run(crm, "crm", "crm.secenekler", crm_options_sql(schema), 10_000)):
                options.setdefault(str(r["attr"]).lower(), {})[int(r["code"])] = str(r["label"])
        finally:
            _close(crm)
        crm_ms = int((time.monotonic() - started) * 1000)
        warnings: list[str] = []
        orders: list[dict[str, Any]] = []
        receipts: list[dict[str, Any]] = []
        costs: list[dict[str, Any]] = []
        firms: list[str] = []
        t1 = time.monotonic()
        try:
            logo = self._logo()
            try:
                have = {str(r["name"]).upper() for r in _rows(run(logo, "logo", "logo.tablolar", LOGO_TABLES_SQL, 1000))}
                for r in _rows(run(logo, "logo", "logo.donemler", logo_periods_sql(since), 1000)):
                    firm, period = f"{int(r['firma']):03d}", f"{int(r['donem']):02d}"
                    if f"LG_{firm}_PRODORD" not in have or not firm_in_scope(firm):
                        continue
                    firms.append(firm)
                    fp = {"firm": firm, "period": period}
                    orders += [dict(o, firma=firm) for o in
                               _rows(run(logo, "logo", f"logo.emirler.{firm}", logo_orders_sql(firm, since), 1_000_000, **fp))]
                    receipts += [dict(x, firma=firm) for x in _rows(run(
                        logo, "logo", f"logo.girisler.{firm}.{period}", logo_receipts_sql(firm, period, since), 1_000_000, **fp))]
                    costs += [dict(x, firma=firm) for x in _rows(run(
                        logo, "logo", f"logo.faturalar.{firm}.{period}", logo_costs_sql(firm, period, since), 1_000_000, **fp))]
            finally:
                _close(logo)
        except Exception as e:  # noqa: BLE001 — Logo'ya ulaşılamazsa CRM ile devam; ekranda söylenir
            log.warning("production: Logo okunamadı: %s", e)
            warnings.append("Logo'ya şu an ulaşılamıyor; baskı çıkışı ve depo girişi CRM ve portal kayıtlarından gösteriliyor.")
        logo_ms = int((time.monotonic() - t1) * 1000)
        return {"cards": cards, "options": options, "orders": orders, "receipts": receipts, "costs": costs,
                "firms": sorted(set(firms)),
                "since": since.isoformat(), "at": time.time(), "crmMs": crm_ms, "logoMs": logo_ms, "warnings": warnings,
                "queries": queries}


# ------------------------------------------------------------------------------------------ birleştirme

def _label(options: dict[str, dict[int, str]], attr: str, code: Any) -> Optional[str]:
    if code is None:
        return None
    try:
        return options.get(attr, {}).get(int(code)) or f"Kod {int(code)}"
    except (TypeError, ValueError):
        return None


def _card_windows(cards: list[dict[str, Any]]) -> dict[str, tuple[Optional[date], Optional[date]]]:
    """Aynı stok kodlu kartlar arasında zaman penceresi: kart açılışından 7 gün önce başlar, aynı kitabın bir sonraki
    kartının penceresi başlayınca biter. Bir baskı tekrarı için verilen emir/fatura öncekinin kartına gitmez."""
    by_code: dict[str, list[tuple[date, str]]] = {}
    for c in cards:
        created = parse_day(_dayiso(c.get("olusturma")))
        if created and c.get("stok"):
            by_code.setdefault(str(c["stok"]).strip().upper(), []).append((created, str(c["id"]).lower()))
    out: dict[str, tuple[Optional[date], Optional[date]]] = {}
    for rows in by_code.values():
        rows.sort()
        for n, (created, cid) in enumerate(rows):
            nxt = rows[n + 1][0] - timedelta(days=7) if n + 1 < len(rows) else None
            out[cid] = (created - timedelta(days=7), nxt)
    return out


def _in(window: tuple[Optional[date], Optional[date]], d: Optional[date]) -> bool:
    lo, hi = window
    return bool(d and lo and d >= lo and (hi is None or d < hi))


def _idkey(v: Any) -> Optional[str]:
    """Üretim no'nun rakamları: `URTN-202600001410`; emir açıklamasındaki yazım farkları (URTM, küçük harf) dahil."""
    m = re.search(r"URT[A-Z]?-?(\d{6,})", str(v or "").upper())
    return m.group(1) if m else None


def match_orders(cards: list[dict[str, Any]], orders: list[dict[str, Any]],
                 windows: Optional[dict] = None) -> dict[str, tuple[dict, str]]:
    """CRM kartı → Logo üretim emri. Önce üretim no ile (emrin 1. açıklaması); açıklaması boş emirler stok koduyla,
    kartın penceresindeki en erken emir. Bir emir tek karta gider."""
    windows = windows if windows is not None else _card_windows(cards)
    by_idno: dict[str, list[dict]] = {}
    by_code: dict[str, list[dict]] = {}
    for o in orders:
        k = _idkey(o.get("idno"))
        if k:
            by_idno.setdefault(k, []).append(o)
        elif o.get("stok"):
            by_code.setdefault(str(o["stok"]).strip().upper(), []).append(o)
    used: set[tuple] = set()
    out: dict[str, tuple[dict, str]] = {}
    for c in cards:
        cand = [o for o in by_idno.get(_idkey(c.get("idno")) or "", []) if (o["firma"], o["ref"]) not in used]
        if cand:
            o = min(cand, key=lambda x: str(x.get("tarih")))
            used.add((o["firma"], o["ref"]))
            out[str(c["id"]).lower()] = (o, "no")
    for c in cards:
        cid = str(c["id"]).lower()
        if cid in out or not c.get("stok") or cid not in windows:
            continue
        cand = [o for o in by_code.get(str(c["stok"]).strip().upper(), [])
                if (o["firma"], o["ref"]) not in used and _in(windows[cid], parse_day(_dayiso(o.get("tarih"))))]
        if cand:
            o = min(cand, key=lambda x: str(x.get("tarih")))
            used.add((o["firma"], o["ref"]))
            out[cid] = (o, "stok")
    return out


def match_costs(cards: list[dict[str, Any]], costs: list[dict[str, Any]], windows: Optional[dict] = None) -> dict[str, list[dict]]:
    """CRM kartı → Logo'daki matbaa baskı faturası satırları («Komple Baskı Giderleri» hizmeti; satır özel kodu =
    kitabın stok kodu), kartın penceresindeki bütün satırlar."""
    windows = windows if windows is not None else _card_windows(cards)
    by_code: dict[str, list[dict]] = {}
    for x in costs:
        if x.get("stok"):
            by_code.setdefault(str(x["stok"]).strip().upper(), []).append(x)
    out: dict[str, list[dict]] = {}
    for c in cards:
        cid = str(c["id"]).lower()
        if cid not in windows or not c.get("stok"):
            continue
        rows = [x for x in by_code.get(str(c["stok"]).strip().upper(), []) if _in(windows[cid], parse_day(_dayiso(x.get("tarih"))))]
        if rows:
            out[cid] = rows
    return out


def cost_of(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Faturalanan adet, tutar, adet başı fiyat ve faturayı kesen matbaa (tutarı en büyük olan)."""
    qty = sum(float(r.get("adet") or 0) for r in rows)
    total = sum(float(r.get("tutar") or 0) for r in rows)
    by: dict[str, float] = {}
    for r in rows:
        name = _s(r.get("cari")) or "?"
        by[name] = by.get(name, 0.0) + float(r.get("tutar") or 0)
    return {"qty": qty or None, "total": round(total, 2) if rows else None,
            "unit": round(total / qty, 4) if qty > 0 else None,
            "supplier": max(by, key=by.get) if by else None,
            "last": max((d for d in (_dayiso(r.get("tarih")) for r in rows) if d), default=None)}


def logo_points(order: dict[str, Any], receipts: list[dict[str, Any]]) -> dict[str, Any]:
    """Emrin gerçek girişlerinden baskı çıkışı (ilk giriş) ve depo girişi (toplam planlanan adede ulaştığı gün; ulaşmadan
    emir kapandıysa son giriş), planlanan girişten depo planı."""
    real = sorted((r for r in receipts if int(r.get("ps") or 0) == 0), key=lambda r: str(r.get("tarih")))
    planned = [r for r in receipts if int(r.get("ps") or 0) == 1]
    need = _num(order.get("plan_adet")) or 0
    first = _dayiso(real[0]["tarih"]) if real else None
    full, total = None, 0.0
    for r in real:
        total += float(r.get("adet") or 0)
        if need and total >= need and full is None:
            full = _dayiso(r["tarih"])
    if full is None and real and int(order.get("durum") or 0) == ORDER_CLOSED:
        full = _dayiso(real[-1]["tarih"])
    plan_depo = min((d for d in (_dayiso(r.get("tarih")) for r in planned) if d), default=None)
    return {"baski": first, "depo": full, "planDepo": plan_depo, "qty": total if real else None}


def _crm_day(r: dict[str, Any], col: str, created: Optional[date], reprint: bool) -> Optional[str]:
    d = _dayiso(r.get(col.lower()))
    if d and reprint and created and parse_day(d) < created - timedelta(days=INHERITED_DAYS):
        return None
    return d


def build_cards(snap: dict[str, Any], entries: dict[str, list[dict]], leads: Optional[dict] = None,
                settings: Optional[dict] = None, now: Optional[date] = None,
                template: Optional[dict] = None) -> list[dict[str, Any]]:
    """CRM kartı + Logo emri/girişleri + portal kayıtları → ekrandaki kart. `leads` (gerçekleşen süreler) ve
    `template` (CRM takviminin uzaklıkları) verilmezse bu kartlardan ölçülür."""
    now = now or today()
    settings = settings or {}
    opts = snap["options"]
    windows = _card_windows(snap["cards"])
    matched = match_orders(snap["cards"], snap["orders"], windows)
    costs = match_costs(snap["cards"], snap.get("costs") or [], windows)
    rec_by: dict[tuple, list[dict]] = {}
    for x in snap["receipts"]:
        rec_by.setdefault((x["firma"], int(x["emir"])), []).append(x)
    base = []
    for r in snap["cards"]:
        cid = str(r["id"]).lower()
        created = parse_day(_dayiso(r.get("olusturma")))
        reprint = r.get("kart") == CARD_REPRINT
        status = int(r["durum"]) if r.get("durum") is not None else None
        order, how = matched.get(cid, (None, None))
        recs = rec_by.get((order["firma"], int(order["ref"])), []) if order else []
        lp = logo_points(order, recs) if order else {"baski": None, "depo": None, "planDepo": None, "qty": None}
        crm_actual = {k: _crm_day(r, col, created, reprint) for k, col in CRM_ACTUAL.items()}
        crm_plan = {k: _dayiso(r.get(col.lower())) for k, col in CRM_PLAN.items()}
        cur = store.current(entries.get(cid, []))
        done_by_status = STATUS_DONE.get(status, ())
        actual = plan_mod.resolve_actual({"baski": lp["baski"], "depo": lp["depo"]}, crm_actual, cur["actual"], done_by_status)
        qty = _num(r.get("adet")) or _num(r.get("net_adet"))
        cost = cost_of(costs.get(cid, []))
        base.append({
            "id": cid, "name": _s(r.get("name")), "idno": _s(r.get("idno")), "bookId": (_s(r.get("kitap_id")) or "").lower() or None,
            "bookTitle": _s(r.get("kitap")), "stockCode": _s(r.get("stok")),
            "printNo": int(r["baski_no"]) if r.get("baski_no") is not None else None,
            "cardKind": _label(opts, "new_baskikartidurumu", r.get("kart")),
            "firstPrint": not reprint,
            "kind": _label(opts, "new_uretimtipi", r.get("tip")), "kindCode": r.get("tip"),
            "printer": _label(opts, "new_matbaa", r.get("matbaa")),
            "crmStatus": _label(opts, "statuscode", status),
            "crmStatusCode": status,
            "waiting": _label(opts, "new_beklemedurumu", r.get("bekleme")) if status == STATUS_WAITING else None,
            "bandrol": _label(opts, "new_bandroldurumu", r.get("bandrol")),
            "priority": _label(opts, "new_oncelikdurumu", r.get("oncelik")),
            "editor": _s(r.get("editor")), "designer": _s(r.get("grafiker")),
            "qty": qty, "qtySuggested": _num(r.get("oneri_adet")), "coverPrice": _num(r.get("fiyat")) or None,
            "price": cost["total"], "unitPrice": cost["unit"], "costQty": cost["qty"], "costSupplier": cost["supplier"],
            "costRows": costs.get(cid, []), "created": created.isoformat() if created else None,
            "promised": crm_plan["baski"], "crmPlan": crm_plan,
            "crm": {c: _dayiso(r.get(c.lower())) for c, _, _ in CRM_DATES},
            "actual": actual, "manual": cur, "logoQty": lp["qty"], "logoPlanDepo": lp["planDepo"], "logoMatch": how,
            "logoOrder": order, "logoReceipts": recs,
            "quality": (cur["quality"] or {}).get("value"), "approval": (cur["approval"] or {}).get("value"),
        })
    if leads is None:
        leads = plan_mod.measure_leads(base)
    if template is None:
        template = plan_mod.measure_template(base)
    fd, mb, esc = settings.get("filesDay", 15), settings.get("monthsBefore", 1), settings.get("escalateDays", 7)
    stale = settings.get("staleDays", 180)
    for c in base:
        pub_entry = c["manual"]["publication"]
        pub = parse_day(pub_entry["day"]) if pub_entry else None
        c["publication"] = pub.isoformat() if pub else None
        c["plan"], c["planBasis"] = card_plan(c, pub, leads, template, fd, mb)
        c["stage"] = plan_mod.stage(c["actual"])
        c["delays"] = plan_mod.delays(c["plan"], c["actual"], now, esc) if c["stage"] != "tamam" else []
        if c["crmStatusCode"] == STATUS_CANCELLED:
            c["stage"], c["delays"] = "iptal", []
        elif c["stage"] != "tamam" and _stale(c, now, stale):
            # Son plan tarihi ayardaki günden (180) eski, depoya girmemiş kart: iş bırakılmış ya da CRM'de
            # kapatılmamış. Gecikme listesini doldurmasın, «Eski» süzgecinde görünsün.
            c["stage"], c["delays"] = "eski", []
        c["stageLabel"] = STAGES[c["stage"]]
    return base


def _stale(c: dict[str, Any], now: date, days: int) -> bool:
    last = max((d for d in (c["plan"].get(k) for k in KEYS) if d), default=None)
    ref = parse_day(last) or parse_day(c.get("created"))
    return bool(ref and ref < now - timedelta(days=days))


def card_plan(c: dict[str, Any], pub: Optional[date], leads: dict, template: dict, fd: int,
              mb: int) -> tuple[dict[str, Optional[str]], Optional[str]]:
    """Kartın planı. Portalda hedef yayın tarihi girildiyse geriye doğru takvim (15 kuralı + ölçülen uzaklıklar);
    yoksa CRM'in kendi plan tarihleri (üretime teslim, baskı tarihi), depo için Logo'daki planlanan giriş. Matbaa
    seçiminin planı dosya teslim planından, gerçekleşmiş kartlarda ölçülen süre kadar önce."""
    if pub:
        return plan_mod.backward(pub, leads, template, fd, mb)["plan"], "yayin"
    plan: dict[str, Optional[str]] = {k: None for k in KEYS}
    plan["dosya"] = c["crmPlan"].get("dosya")
    # CRM baskı tarihi ay düzeyinde (kartların %99'unda ayın 1'i): baskı o ay içinde, en geç ayın son günü çıkar.
    b = parse_day(c["crmPlan"].get("baski"))
    plan["baski"] = (plan_mod.month_end(b) if b.day == 1 else b).isoformat() if b else None
    basis = "crm" if (plan["dosya"] or plan["baski"]) else None
    dosya_d = parse_day(plan["dosya"])
    ml = leads.get("matbaa>dosya", {}).get("days")
    if dosya_d and ml is not None:
        plan["matbaa"] = (dosya_d - timedelta(days=ml)).isoformat()
    baski_d = parse_day(plan["baski"])
    dl = leads.get("baski>depo", {}).get("days")
    if c.get("logoPlanDepo"):
        plan["depo"] = c["logoPlanDepo"]
        basis = basis or "logo"
    elif baski_d and dl is not None:
        plan["depo"] = (baski_d + timedelta(days=dl)).isoformat()
    return plan, basis


def summary(c: dict[str, Any]) -> dict[str, Any]:
    keep = ("id", "name", "idno", "bookId", "bookTitle", "stockCode", "printNo", "firstPrint", "cardKind", "kind", "printer",
            "crmStatus", "waiting", "bandrol", "editor", "designer", "qty", "qtySuggested", "coverPrice", "price", "unitPrice",
            "costQty", "costSupplier", "priority",
            "created", "promised", "publication", "plan", "planBasis", "actual", "stage", "stageLabel", "delays", "quality",
            "approval", "logoQty", "logoMatch")
    return {k: c.get(k) for k in keep}


# ------------------------------------------------------------------------------------------ servis

def _parmak(entries: dict[str, list[dict]]) -> str:
    """Portal kayıtlarının parmak izi: kartları etkileyen kayıtların (silinmemiş, bütün alanlarıyla) özeti. Kayıt
    eklenince ya da silinince değişir; kartlar yeniden kurulur."""
    return hashlib.sha256(repr(sorted(entries.items())).encode("utf-8")).hexdigest()


def _ayar_anahtari(settings: dict[str, Any]) -> tuple:
    return tuple(sorted((str(k), repr(v)) for k, v in (settings or {}).items()))


class Service:
    """Ekranın uçları: kaynak okuması + portal kayıtları → kartlar ve raporlar."""

    def __init__(self, source: Source, settings: Callable[[], dict[str, Any]],
                 studio_jobs: Optional[Callable[[], dict]] = None):
        self.source = source
        self.settings = settings
        self.studio_jobs = studio_jobs
        # Hız (2026-09-29): kartlar ve özet süreç belleğinde. Anahtar = motor + kiracı + portal kayıtlarının parmak izi
        # + ayarlar + gün + kaynak okumasının anı: bunlardan biri değişince yeniden kurulur, rakam eski hesapla aynıdır.
        # `en_cok` bellek korumasıdır (en eski anahtar düşer), sonuç kesilmez.
        self._kartlar = HB.Bellek("uretim.kartlar", taze=float("inf"), en_cok=6)
        self._ozetler = HB.Bellek("uretim.ozet", taze=float("inf"), en_cok=6)
        self._lock = threading.Lock()
        self._son: dict[tuple, tuple[tuple, dict[str, Any]]] = {}      # yan anahtar → (anahtar, okuma) son kurulan
        self._baglam: dict[tuple, tuple] = {}                          # (motor, kiracı) → son isteğin kayıtları, ayarları
        self._isitiliyor: set[tuple] = set()                           # arkada kurulan anahtarlar
        self._okunan = threading.local()                               # bu isteğin kartlarının dayandığı okuma
        source.on_new = self._yeni_okuma

    def cards(self, engine: Any, tenant: str, fresh: bool = False, now: Optional[date] = None) -> tuple[list[dict], dict]:
        """Diğer modüllerin (tedarik, stok, dağıtım) okuduğu kartlar: her çağrıda yeniden kurulur (dönen liste
        çağıranındır, değiştirebilir). Bu ekranın uçları bellekteki kopyayı `_kart_al` ile okur."""
        snap = self.source.snapshot(fresh)
        entries, _ = store.load(engine, tenant)
        cards = build_cards(snap, entries, settings=self.settings(), now=now)
        return cards, snap

    # ---- bellek
    def _hesap(self, yan: tuple, key: tuple, snap: dict[str, Any], entries: dict[str, list[dict]],
               settings: dict[str, Any], now: date) -> Callable[[], list[dict]]:
        def run() -> list[dict]:
            cards = build_cards(snap, entries, settings=settings, now=now)
            with self._lock:
                son = self._son.get(yan)
                if son is None or float(son[1].get("at") or 0) <= float(snap.get("at") or 0):
                    self._son[yan] = (key, snap)
            return cards
        return run

    def _kart_al(self, engine: Any, tenant: str, fresh: bool = False,
                 now: Optional[date] = None) -> tuple[list[dict], dict[str, Any], tuple]:
        """Ekranın kartları (değiştirilmez; uçlar yeni sözlük üretir). Aynı okuma + aynı portal kayıtları + aynı
        ayarlar + aynı gün → bellekten. Kaynağın yeni okuması geldi ama kartları henüz kurulmadıysa önceki okumanın
        kartları hemen döner (eskisi gibi: okuma arkada tazelenirken son okuma gösterilir), yenisi arkada kurulur.
        «Verileri yenile» (`fresh`) kaynağı bekler ve o okumanın kartlarını kurar."""
        return self._okumanin_kartlari(engine, tenant, self.source.snapshot(fresh), fresh, now or today())

    def _okumanin_kartlari(self, engine: Any, tenant: str, snap: dict[str, Any], fresh: bool,
                           now: date) -> tuple[list[dict], dict[str, Any], tuple]:
        settings = self.settings()
        entries, _ = store.load(engine, tenant)
        yan = (id(engine), tenant, _parmak(entries), _ayar_anahtari(settings), now.isoformat())
        key = yan + (snap.get("at"), snap.get("since"))
        hesap = self._hesap(yan, key, snap, entries, settings, now)
        with self._lock:
            self._baglam[(id(engine), tenant)] = (id(engine), tenant, entries, settings)
            son = self._son.get(yan)
            if son is None and not fresh:
                # Gün değişti (hız 4. tur): aynı kayıt ve ayarlarla dünün kartları varsa bugünkü kurulana kadar onlar
                # gösterilir, bugünkü arkada kurulur (günün ilk açılışı kart kurulumunu beklemez).
                son = self._son.get(yan[:4] + ((now - timedelta(days=1)).isoformat(),))
        if not fresh and self._kartlar.an(key) is None and son is not None and son[0] != key \
                and self._kartlar.an(son[0]) is not None:
            self._isit(key, hesap, snap, now)
            old_key, old_snap = son
            cards = self._kartlar.al(old_key, self._hesap(yan, old_key, old_snap, entries, settings, now))
            self._okunan.snap = old_snap
            return cards, old_snap, old_key
        cards = self._kartlar.al(key, hesap)
        self._okunan.snap = snap
        return cards, snap, key

    def yazildi(self, engine: Any, tenant: str) -> None:
        """Portal kaydı eklendi ya da silindi: yeni kayıtlarla kartlar ve özet beklemeden arkada kurulur (ekran
        yenilenince hesabın kalanını bekler). Okuma yoksa bir şey yapılmaz."""
        try:
            snap = self.source.peek()
            if snap is None:
                return
            now, settings = today(), self.settings()
            entries, _ = store.load(engine, tenant)
            yan = (id(engine), tenant, _parmak(entries), _ayar_anahtari(settings), now.isoformat())
            key = yan + (snap.get("at"), snap.get("since"))
            with self._lock:
                self._baglam[(id(engine), tenant)] = (id(engine), tenant, entries, settings)
            if self._kartlar.an(key) is None:
                self._isit(key, self._hesap(yan, key, snap, entries, settings, now), snap, now)
        except Exception as e:  # noqa: BLE001 — ısıtılamazsa sonraki açılış kurar
            log.info("production: yazma sonrası ısıtma başlatılamadı: %s", e)

    def okunan(self) -> Optional[dict[str, Any]]:
        """Bu iş parçacığında son `_kart_al`'ın dayandığı okuma (sorgu bilgisi o okumanın SQL'ini gösterir)."""
        return getattr(self._okunan, "snap", None)

    def _isit(self, key: tuple, hesap: Callable[[], list[dict]], snap: dict[str, Any], now: date) -> None:
        """Kartları ve özeti beklemeden arkada kurar (tek iş: aynı anahtarı isteyen bu hesabı bekler)."""
        with self._lock:
            if key in self._isitiliyor:
                return
            self._isitiliyor.add(key)

        def run() -> None:
            try:
                cards = self._kartlar.al(key, hesap)
                self._ozetler.al(key, lambda: self._ozet(cards, snap, now))
            except Exception as e:  # noqa: BLE001 — ısıtılamazsa istek kendisi kurar
                log.warning("production: kartlar arkada kurulamadı: %s", e)
            finally:
                with self._lock:
                    self._isitiliyor.discard(key)

        threading.Thread(target=run, name="bellek:uretim.isit", daemon=True).start()

    def _yeni_okuma(self, snap: dict[str, Any]) -> None:
        """Kaynağın yeni okuması bitti: son isteğin portal kayıtları ve ayarlarıyla kartlar arkada kurulur (portal
        tablosuna dokunmaz; kayıt o arada değiştiyse istek kendi anahtarıyla yeniden kurar)."""
        now = today()
        with self._lock:
            ctxs = list(self._baglam.values())
        for eid, tenant, entries, settings in ctxs:
            yan = (eid, tenant, _parmak(entries), _ayar_anahtari(settings), now.isoformat())
            key = yan + (snap.get("at"), snap.get("since"))
            if self._kartlar.an(key) is None:
                self._isit(key, self._hesap(yan, key, snap, entries, settings, now), snap, now)

    # ---- özet
    def overview(self, engine: Any, tenant: str, fresh: bool = False, now: Optional[date] = None) -> dict[str, Any]:
        now = now or today()
        cards, snap, key = self._kart_al(engine, tenant, fresh, now)
        return self._ozetler.al(key, lambda: self._ozet(cards, snap, now))

    def _ozet(self, cards: list[dict[str, Any]], snap: dict[str, Any], now: date) -> dict[str, Any]:
        leads = plan_mod.measure_leads(cards)
        open_ = [c for c in cards if c["stage"] not in ("tamam", "iptal", "eski")]
        late = [c for c in open_ if c["delays"]]
        soon = [c for c in open_ if not c["delays"] and _due_within(c, now, 14)]
        done = [c for c in cards if (parse_day((c["actual"].get("depo") or {}).get("day")) or date.min)
                >= now - timedelta(days=30)]
        matched = sum(1 for c in cards if c["logoMatch"])
        by_stage = {k: 0 for k in STAGES}
        for c in cards:
            by_stage[c["stage"]] += 1
        # Planlanan giriş fişleri (PRODSTAT 1) ileri tarihlidir: Logo'nun ne zamana kadar dolu olduğu gerçek girişten okunur.
        rec = [d for d in (_dayiso(r.get("tarih")) for r in snap["receipts"] if int(r.get("ps") or 0) == 0) if d]
        ords = [d for d in (_dayiso(r.get("tarih")) for r in snap["orders"]) if d]
        warnings = list(snap["warnings"])
        last_rec = max(rec) if rec else None
        last_day = parse_day(last_rec)
        if last_day and (now - last_day).days > 10:
            warnings.append(f"Logo'daki son gerçek depo girişi {last_day.day:02d}.{last_day.month:02d}.{last_day.year}: bu tarihten "
                            "sonra gerçekleşen baskı ve depo girişleri Logo kopyasına henüz gelmedi; CRM aşaması ve portal "
                            "kaydından gösterilir.")
        return {
            "asOf": datetime.fromtimestamp(snap["at"], TZ).isoformat(timespec="seconds"), "historyFrom": snap["since"],
            "total": len(cards), "open": len(open_), "late": len(late),
            "escalated": sum(1 for c in late if any(d["level"] == "yonetici" for d in c["delays"])),
            "dueSoon": len(soon), "doneRecent": len(done), "byStage": by_stage, "leads": leads,
            "template": plan_mod.measure_template(cards), "logoMatched": matched,
            "logo": ({"firms": snap["firms"], "lastReceipt": last_rec, "lastOrder": max(ords) if ords else None}
                     if snap["firms"] else None),
            "warnings": warnings, "db": {"crmMs": snap["crmMs"], "logoMs": snap["logoMs"]},
        }

    # ---- liste
    def list(self, engine: Any, tenant: str, *, durum: str = "", matbaa: str = "", q: str = "", tur: str = "",
             urun: str = "", page: int = 0, fresh: bool = False, now: Optional[date] = None) -> dict[str, Any]:
        cards, _, _ = self._kart_al(engine, tenant, fresh, now)
        items = filter_cards(cards, durum=durum, matbaa=matbaa, q=q, tur=tur, urun=urun)
        page = max(0, int(page or 0))
        return {"items": [summary(c) for c in items[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]], "total": len(items),
                "page": page, "pageSize": PAGE_SIZE}

    def delays(self, engine: Any, tenant: str, fresh: bool = False, now: Optional[date] = None) -> dict[str, Any]:
        cards, _, _ = self._kart_al(engine, tenant, fresh, now)
        late = [c for c in cards if c["delays"]]
        late.sort(key=lambda c: (-max(d["days"] for d in c["delays"]), c["bookTitle"] or ""))
        return {"items": [summary(c) for c in late], "escalateDays": self.settings()["escalateDays"]}

    # ---- matbaalar
    def printers(self, engine: Any, tenant: str, fresh: bool = False, now: Optional[date] = None) -> dict[str, Any]:
        now = now or today()
        cards, snap, _ = self._kart_al(engine, tenant, fresh, now)
        stats = plan_mod.printer_stats(cards, now)
        ref, prior = _price_ref(stats), plan_mod.overall_on_time(stats)
        for s in stats:
            sc = plan_mod.score(s, ref, prior)
            s.update(score=sc["score"], scoreParts=sc["parts"], scoreNotes=sc["notes"])
        return {"items": stats, "priceRef": ref, "historyFrom": snap["since"]}

    # ---- kart ayrıntısı
    def detail(self, engine: Any, tenant: str, cid: str, fresh: bool = False, now: Optional[date] = None) -> dict[str, Any]:
        now = now or today()
        cid = store.card_id(cid)
        cards, _, _ = self._kart_al(engine, tenant, fresh, now)
        c = next((x for x in cards if x["id"] == cid), None)
        if c is None:
            raise ProductionError("Üretim kartı bulunamadı (geçmiş penceresinin dışında ya da CRM'de pasif olabilir).", 404)
        entries, quotes = store.load(engine, tenant, [cid])
        stats = plan_mod.printer_stats(cards, now)
        ref = _price_ref(stats)
        out = summary(c)
        out.update(
            entries=entries.get(cid, []), quotes=quotes.get(cid, []),
            suggestions=suggest(c, stats, quotes.get(cid, []), ref),
            logoOrders=[{"no": _s(o.get("no")), "date": _dayiso(o.get("tarih")), "planned": _num(o.get("plan_adet")),
                         "planEnd": _dayiso(o.get("plan_bit")), "status": ORDER_STATUS.get(int(o.get("durum") or 0)),
                         "item": _s(o.get("stok")), "firm": o.get("firma")}
                        for o in ([c["logoOrder"]] if c["logoOrder"] else [])],
            logoReceipts=[{"no": _s(r.get("no")), "date": _dayiso(r.get("tarih")), "qty": _num(r.get("adet")),
                           "planned": int(r.get("ps") or 0) == 1}
                          for r in sorted(c["logoReceipts"], key=lambda r: (int(r.get("ps") or 0) == 0, str(r.get("tarih"))))],
            logoCosts=[{"no": _s(x.get("no")), "date": _dayiso(x.get("tarih")), "supplier": _s(x.get("cari")),
                        "qty": _num(x.get("adet")), "total": _num(x.get("tutar"))}
                       for x in sorted(c["costRows"], key=lambda x: str(x.get("tarih")))],
            crmDates=[{"key": col, "label": lbl, "day": c["crm"].get(col), "plan": is_plan} for col, lbl, is_plan in CRM_DATES],
            studio=self._studio(c),
        )
        return out

    def _studio(self, c: dict[str, Any]) -> list[dict[str, Any]]:
        """Kitap Tasarım Stüdyosu'ndaki (M13/M14) işler: aynı CRM kitabına bağlı ya da adı birebir aynı olan."""
        if not self.studio_jobs:
            return []
        try:
            data = self.studio_jobs()
        except Exception as e:  # noqa: BLE001 — stüdyo kapalıysa üretim kartı yine açılır
            log.info("production: stüdyo işleri okunamadı: %s", e)
            return []
        return studio_links(c, data)

    # ---- geriye doğru takvim
    def calendar(self, engine: Any, tenant: str, publication: str, fresh: bool = False) -> dict[str, Any]:
        pub = parse_day(publication)
        if not pub:
            raise ProductionError("Yayın tarihi YYYY-AA-GG biçiminde olmalı.")
        cards, _, _ = self._kart_al(engine, tenant, fresh)
        leads = plan_mod.measure_leads(cards)
        template = plan_mod.measure_template(cards)
        s = self.settings()
        out = plan_mod.backward(pub, leads, template, s["filesDay"], s["monthsBefore"])
        out.update(leads=leads, template=template)
        return out

    # ---- M29 / M16 için: baskı çıkış tarihi
    def print_exit(self, engine: Any, tenant: str, book: str, fresh: bool = False) -> dict[str, Any]:
        bid = store.card_id(book)  # CRM kitap kimliği de GUID
        cards, _ = self.cards(engine, tenant, fresh)
        items = []
        for c in sorted((x for x in cards if x["bookId"] == bid), key=lambda x: (x["printNo"] or 0, x["created"] or "")):
            a = c["actual"].get("baski") or {}
            items.append({"cardId": c["id"], "printNo": c["printNo"], "qty": c["qty"], "stage": c["stage"],
                          "planned": c["plan"].get("baski"), "actual": a.get("day"), "source": a.get("source"),
                          "depot": (c["actual"].get("depo") or {}).get("day"), "depotPlanned": c["plan"].get("depo")})
        return {"book": bid, "items": items}

    # ---- Kampüs: matbaadan yeni çıkanlar
    def new_prints(self, engine: Any, tenant: str, now: Optional[date] = None) -> dict[str, Any]:
        """Kampüs açılışını bekletmez: son okuma yoksa boş döner (`ready: false`), okuma arka planda başlar."""
        now = now or today()
        days = self.settings()["newPrintsDays"]
        snap = self.source.peek()
        if snap is None:
            return {"items": [], "days": days, "ready": False, "asOf": None}
        cards, snap, _ = self._okumanin_kartlari(engine, tenant, snap, False, now)
        return {"items": new_prints(cards, now, days), "days": days, "ready": True,
                "asOf": datetime.fromtimestamp(snap["at"], TZ).isoformat(timespec="seconds")}


def _due_within(c: dict[str, Any], now: date, days: int) -> bool:
    for k in KEYS:
        d = parse_day(c["plan"].get(k))
        if d and k not in c["actual"] and now <= d <= now + timedelta(days=days):
            return True
    return False


def _price_ref(stats: list[dict[str, Any]]) -> Optional[float]:
    xs = [s["unitPrice"] for s in stats if s.get("unitPrice")]
    return round(statistics.median(xs), 4) if xs else None


_TR = str.maketrans("İIıŞşĞğÜüÖöÇç", "iiissgguuoocc")


def _fold(s: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (s or "").translate(_TR).lower()).strip()


def filter_cards(cards: list[dict[str, Any]], *, durum: str = "", matbaa: str = "", q: str = "", tur: str = "",
                 urun: str = "") -> list[dict[str, Any]]:
    """durum: acik (süren: depoya girmemiş, iptal ve eski olmayan; varsayılan) · gecikme · hepsi · bir aşama anahtarı
    (tamam, eski, iptal…). tur: ilk | tekrar. urun: kitap | diger (promosyon, set, katalog…)."""
    durum = durum or "acik"
    needle = _fold(q)
    out = []
    for c in cards:
        if durum == "acik" and c["stage"] in ("tamam", "iptal", "eski"):
            continue
        if durum == "gecikme" and not c["delays"]:
            continue
        if durum in STAGES and c["stage"] != durum:
            continue
        if matbaa and (c["printer"] or "") != matbaa:
            continue
        if tur == "ilk" and not c["firstPrint"]:
            continue
        if tur == "tekrar" and c["firstPrint"]:
            continue
        if urun == "kitap" and c.get("kindCode") != KIND_BOOK:
            continue
        if urun == "diger" and c.get("kindCode") == KIND_BOOK:
            continue
        if needle and needle not in _fold(" ".join(filter(None, [c["bookTitle"], c["name"], c["idno"], c["stockCode"], c["printer"]]))):
            continue
        out.append(c)

    def key(c: dict[str, Any]) -> tuple:
        nxt = min((d for k in KEYS if k not in c["actual"] and (d := c["plan"].get(k))), default="9999")
        late = max((d["days"] for d in c["delays"]), default=0)
        return (-late, nxt, c["bookTitle"] or "")

    if durum == "tamam":
        out.sort(key=lambda c: (c["actual"].get("depo") or {}).get("day") or "", reverse=True)
    else:
        out.sort(key=key)
    return out


def suggest(card: dict[str, Any], stats: list[dict[str, Any]], quotes: list[dict[str, Any]], ref: Optional[float]) -> list[dict[str, Any]]:
    """Matbaa seçim raporu: teklif veren matbaalar önce, sonra geçmiş puanı en yüksekler; ilk 3 öneri olarak döner
    (tam liste Matbaalar sekmesinde). Her önerinin gerekçesi yazılır."""
    by = {s["printer"]: s for s in stats}
    quoted: dict[str, dict[str, Any]] = {}
    for q in quotes:  # yeniden eskiye: aynı matbaanın son teklifi
        quoted.setdefault(q["printer"], q)
    names = list(quoted) + [s["printer"] for s in stats if s["printer"] not in quoted]
    empty = {"jobs": 0, "open": 0, "done": 0, "copies": 0, "onTimeRate": None, "measured": 0, "leadDays": None,
             "leadSamples": 0, "unitPrice": None, "unitSamples": 0, "unitRecent": None, "unitPrevious": None,
             "unitTrend": None, "qualityRate": None, "qualityMarked": 0, "last": None}
    out = []
    for n in names:
        s = dict(by.get(n) or dict(empty, printer=n))
        q = quoted.get(n)
        probe = dict(s)
        if q and q.get("unitPrice"):
            probe["unitPrice"] = q["unitPrice"]
        sc = plan_mod.score(probe, ref, plan_mod.overall_on_time(stats))
        why = []
        if s.get("onTimeRate") is not None:
            why.append(f"zamanında teslim %{round(s['onTimeRate'] * 100)} ({s['measured']} iş)")
        if s.get("leadDays") is not None:
            why.append(f"dosyadan depoya ortanca {s['leadDays']} gün")
        if q:
            why.append("teklif verdi" + (f", teslim {q['deliveryDay']}" if q.get("deliveryDay") else ""))
        elif s.get("unitRecent") is not None:
            why.append(f"son 12 ayda adet başı baskı {s['unitRecent']:.2f} ₺".replace(".", ","))
        if s.get("open"):
            why.append(f"şu an {s['open']} açık iş")
        last = parse_day(s.get("last"))
        if last and last < today() - timedelta(days=180):
            why.append(f"son işi {last.day:02d}.{last.month:02d}.{last.year} (uzun süredir iş verilmemiş)")
        why += sc["notes"]
        out.append(dict(s, score=sc["score"], scoreParts=sc["parts"], scoreNotes=sc["notes"], quote=q, why=why))
    out.sort(key=lambda x: (x["quote"] is None, -x["score"], x["printer"]))
    return out[:3]


def studio_links(c: dict[str, Any], data: Any) -> list[dict[str, Any]]:
    jobs = data.get("items") if isinstance(data, dict) else data
    title = _fold(c.get("bookTitle"))
    out = []
    for j in jobs or []:
        src = j.get("source") or {}
        linked = bool(c.get("bookId")) and str(src.get("crm_book_id") or "").lower() == c["bookId"]
        same = bool(title) and _fold(j.get("title")) == title
        if not (linked or same):
            continue
        steps = {s.get("key"): s.get("status") for s in j.get("steps") or []}
        ready = any(steps.get(k) == "done" for k in ("preflight", "print", "baski"))
        when = j.get("created_at")
        out.append({"job": j.get("id"), "title": j.get("title"), "status": "Baskı dosyası hazır" if ready else "Hazırlanıyor",
                    "ready": ready,
                    "when": datetime.fromtimestamp(when, TZ).date().isoformat() if isinstance(when, (int, float)) else None})
    return out


# ------------------------------------------------------------------------------------------ ayarlar

def settings_from(conf: Callable[..., str]) -> dict[str, Any]:
    """Ayarlar ekran/ortamdan (`admin.conf`), yoksa varsayılan: dosya günü 15, 1 ay önce, 7 günde yöneticiye, planı
    180 günden eski ve hiçbir adımı gerçekleşmemiş kart «kapanmamış eski kart», geçmiş penceresi iki yıl önceki 1 Ocak'tan."""
    def num(key: str, default: int, lo: int, hi: int) -> int:
        try:
            return max(lo, min(hi, int(str(conf(key, str(default)) or default))))
        except ValueError:
            return default

    now = today()
    hist = parse_day(conf("PRODUCTION_HISTORY_FROM", "") or "") or date(now.year - 2, 1, 1)
    return {"filesDay": num("PRODUCTION_FILES_DAY", 15, 1, 28), "monthsBefore": num("PRODUCTION_FILES_MONTHS_BEFORE", 1, 0, 6),
            "escalateDays": num("PRODUCTION_ESCALATE_DAYS", 7, 1, 90), "staleDays": num("PRODUCTION_STALE_DAYS", 180, 30, 3650),
            "newPrintsDays": num("PRODUCTION_NEW_PRINTS_DAYS", 30, 1, 365),
            "historyFrom": hist.isoformat()}


def new_prints(cards: list[dict[str, Any]], now: date, days: int) -> list[dict[str, Any]]:
    """Kampüs «Matbaadan yeni çıkanlar»: son `days` günde baskısı gerçekleşen kitap kartları, yeniden eskiye.

    Gün = gerçekleşen baskı (Logo giriş fişi > CRM > portal kaydı; `actual`), yoksa gerçekleşen depo girişi. Planlanan
    tarih sayılmaz; iptal kartı ve kitap dışı ürün (promosyon, set, katalog) girmez. Sayı tavanı yok: pencere ayardadır
    (`PRODUCTION_NEW_PRINTS_DAYS`, varsayılan 30)."""
    since = now - timedelta(days=days)
    out = []
    for c in cards:
        if c.get("kindCode") != KIND_BOOK or c.get("stage") == "iptal":
            continue
        act = c.get("actual") or {}
        day = parse_day((act.get("baski") or {}).get("day") or (act.get("depo") or {}).get("day"))
        if not day or day < since or day > now:
            continue
        out.append({"cardId": c.get("id"), "bookId": c.get("bookId"), "title": c.get("bookTitle") or c.get("name"),
                    "printNo": c.get("printNo"), "firstPrint": bool(c.get("firstPrint")), "day": day.isoformat(),
                    "depot": (act.get("depo") or {}).get("day")})
    out.sort(key=lambda x: _fold(x["title"]))
    out.sort(key=lambda x: x["day"], reverse=True)
    return out


# ------------------------------------------------------------------------------------------ uçlar

def register(app: Any, deps: dict[str, Any]) -> Service:
    """app.py'de bağlanır. `deps`:
    auth(request) → (engine, tenant, user, display) · can(user, key) → bool · is_admin(user) → bool ·
    audit(engine, user, action, kind, id, title, detail) · conf(key, default) → str · fresh() → bool ·
    crm_connect() / logo_connect() → salt okunur bağlantı · studio_jobs() → stüdyo iş listesi (isteğe bağlı)."""
    auth, can, is_admin, audit, conf, fresh = (deps[k] for k in ("auth", "can", "is_admin", "audit", "conf", "fresh"))
    settings = lambda: settings_from(conf)  # noqa: E731
    source = Source(deps["crm_connect"], deps["logo_connect"], lambda: conf("CRM_SCHEMA"),
                    lambda: parse_day(settings()["historyFrom"]) or date(today().year - 2, 1, 1))
    svc = Service(source, settings, deps.get("studio_jobs"))
    from semantic_bridge import hizli_kaynak as HK
    from semantic_bridge import production_kaynak as K
    from semantic_bridge import provenance as PV

    def isit() -> None:
        """Köprü açılışı (hız 4. tur): diskteki son okumadan bugünün kartları ve özeti arkada kurulur — üretim özetini
        ilk açan kişi kart kurulumunu (5.600 kart) beklemesin. Okuma eskiyse kaynak ayrıca arkada okunur (`peek`)."""
        system = deps.get("system")
        if system is None:
            return
        engine, tenant = system()
        if HK.sqlite_mi(engine):
            return
        store.ensure(engine)
        svc.overview(engine, tenant)

    HK.acilista("uretim.kartlar", isit)

    def ctx(request: Request) -> tuple[Any, str, str, str]:
        engine, tenant, user, display = auth(request)
        store.ensure(engine)
        return engine, tenant, user, display

    def call(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except ProductionError as e:
            raise HTTPException(status_code=e.status, detail={"code": "PRODUCTION", "message": str(e)}) from e
        except HTTPException:
            raise
        except Exception as e:  # noqa: BLE001 — kaynak düştüyse kişiye düz cümle, ayrıntı günlükte
            log.exception("production: okuma başarısız")
            state = str(getattr(e, "args", [""])[0])
            if state in ("08S01", "08001", "HYT00", "HYT01") or "timeout" in str(e).lower():
                raise HTTPException(status_code=503, detail={"code": "DATA_SOURCE_UNAVAILABLE", "retryable": True,
                                    "message": "CRM ya da Logo şu anda yanıt vermiyor; birazdan tekrar deneyin."}) from e
            raise HTTPException(status_code=502, detail={"code": "PRODUCTION", "message": "Üretim kayıtları okunamadı."}) from e

    def need(user: str, key: str, what: str) -> None:
        if not (is_admin(user) or can(user, key)):
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": f"{what} rolünüzde yok."})

    P = "/api/v1/editorial/production"

    @app.get(f"{P}/meta")
    def production_meta(request: Request) -> dict[str, Any]:
        engine, tenant, user, display = ctx(request)
        admin = is_admin(user)
        printers: list[str] = []
        snap = source.peek()   # matbaa adları: okuma yoksa beklenmez, liste sonraki açılışta dolar
        if snap is not None:
            printers = sorted(set(snap["options"].get("new_matbaa", {}).values()), key=_fold)
        out = {"milestones": [{"key": k, "label": v} for k, v in MILESTONES],
                "stages": [{"key": k, "label": v} for k, v in STAGES.items()],
                "kinds": [{"key": k, "label": v} for k, v in store.KINDS.items()],
                "quality": [{"key": k, "label": v} for k, v in store.QUALITY.items()],
                "printers": printers, "settings": settings(),
                "me": {"username": user, "display": display, "admin": admin,
                       "canWrite": admin or can(user, "ozellik:uretim.yaz"),
                       "canApprove": admin or can(user, "ozellik:uretim.matbaa-onay")}}
        return PV.bagla(out, lambda: K.for_meta(engine, tenant, out, snap))

    @app.get(f"{P}/overview")
    def production_overview(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        out = call(svc.overview, engine, tenant, fresh())
        return PV.bagla(out, lambda: K.for_overview(engine, tenant, out, svc.okunan() or source.last()))

    @app.get(f"{P}/cards")
    def production_cards(request: Request, durum: str = "", matbaa: str = "", q: str = "", tur: str = "", urun: str = "",
                         page: int = 0) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        out = call(svc.list, engine, tenant, durum=durum, matbaa=matbaa, q=q, tur=tur, urun=urun, page=page, fresh=fresh())
        return PV.bagla(out, lambda: K.for_list(engine, tenant, out, svc.okunan() or source.last()))

    @app.get(f"{P}/cards/{{card}}")
    def production_card(card: str, request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        out = call(svc.detail, engine, tenant, card, fresh())
        return PV.bagla(out, lambda: K.for_detail(engine, tenant, out["id"], out, svc.okunan() or source.last()))

    @app.post(f"{P}/cards/{{card}}/entries", status_code=201)
    def production_entry(card: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, display = ctx(request)
        if str(body.get("kind") or "") == "onay":
            raise HTTPException(status_code=400, detail={"code": "PRODUCTION", "message": "Matbaa onayı kendi düğmesinden verilir."})
        out = call(store.add_entry, engine, tenant, user, display, card, body, today())
        audit(engine, user, "create", "production_entry", out["id"], out["kindLabel"],
              {"card": out["cardId"], "milestone": out["milestone"], "day": out["day"], "value": out["value"]})
        svc.yazildi(engine, tenant)
        return out

    @app.delete(f"{P}/entries/{{rid}}")
    def production_entry_delete(rid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(store.delete_entry, engine, tenant, user, is_admin(user), rid)
        audit(engine, user, "delete", "production_entry", out["id"], out["kindLabel"], {"card": out["cardId"]})
        svc.yazildi(engine, tenant)
        return {"ok": True}

    @app.post(f"{P}/cards/{{card}}/quotes", status_code=201)
    def production_quote(card: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, display = ctx(request)
        out = call(store.add_quote, engine, tenant, user, display, card, body)
        audit(engine, user, "create", "production_quote", out["id"], out["printer"],
              {"card": out["cardId"], "unit": out["unitPrice"], "total": out["totalPrice"], "delivery": out["deliveryDay"]})
        return out

    @app.delete(f"{P}/quotes/{{rid}}")
    def production_quote_delete(rid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(store.delete_quote, engine, tenant, user, is_admin(user), rid)
        audit(engine, user, "delete", "production_quote", out["id"], out["printer"], {"card": out["cardId"]})
        return {"ok": True}

    @app.post(f"{P}/cards/{{card}}/approve", status_code=201)
    def production_approve(card: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        """Prodüksiyon müdürünün matbaa onayı: açıkça verilen yetki (`uretim.matbaa-onay`) ister."""
        engine, tenant, user, display = ctx(request)
        need(user, "ozellik:uretim.matbaa-onay", "Matbaa onayı")
        out = call(store.add_entry, engine, tenant, user, display, card,
                   {"kind": "onay", "value": body.get("printer"), "note": body.get("note")}, today())
        audit(engine, user, "approve", "production_printer", out["id"], out["value"], {"card": out["cardId"], "note": out["note"]})
        svc.yazildi(engine, tenant)
        return out

    @app.get(f"{P}/delays")
    def production_delays(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        out = call(svc.delays, engine, tenant, fresh())
        return PV.bagla(out, lambda: K.for_delays(engine, tenant, out, svc.okunan() or source.last()))

    @app.get(f"{P}/printers")
    def production_printers(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        out = call(svc.printers, engine, tenant, fresh())
        return PV.bagla(out, lambda: K.for_printers(engine, tenant, out, svc.okunan() or source.last()))

    @app.get(f"{P}/calendar")
    def production_calendar(request: Request, publication: str = "") -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        out = call(svc.calendar, engine, tenant, publication, fresh())
        return PV.bagla(out, lambda: K.for_calendar(engine, tenant, out, svc.okunan() or source.last()))

    @app.get(f"{P}/print-exit")
    def production_print_exit(request: Request, book: str = "") -> dict[str, Any]:
        """M29 İlk dağılım ve M16 için kitabın baskı çıkış tarihleri (baskı başına plan + gerçekleşen)."""
        engine, tenant, _, _ = ctx(request)
        return call(svc.print_exit, engine, tenant, book, fresh())

    @app.get(f"{P}/new-prints")
    def production_new_prints(request: Request) -> dict[str, Any]:
        """Kampüs «Matbaadan yeni çıkanlar» (oturum yeter): kitap adı, baskı no ve gün; adet ve maliyet yok."""
        engine, tenant, _, _ = ctx(request)
        return call(svc.new_prints, engine, tenant)

    return svc
