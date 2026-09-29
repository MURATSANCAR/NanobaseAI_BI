"""Sözleşme karşılaştırma (M6 alt ekranı `/telif-sozlesme/karsilastirma`): bir sözleşmenin maddeleri geçmiş sözleşmelerle.

Neden: CRM'de 14.863 etkin sözleşme var (2026-09-29 ölçümü) ama sözleşme belgesi yok denecek kadar az (9 ek: 8 telefon
fotoğrafı, 1 PDF). Maddeler CRM'de yapısal alanlarda (oranlar, avans, tek ödeme, vade, süre, fesih, baskı hediyesi, hak
bitleri) ve dört serbest metin alanında durur. Bu modül her maddeyi **benzer geçmiş sözleşmelerle** kıyaslar ve farklı
olanı çıkarır. Belgenin metni madde madde `contracts_compare_docs`'ta karşılaştırılır.

Kurallar (hepsi veriden, sözleşmeye/örneğe özel istisna yok):

- **Madde kataloğu** (`CLAUSES`): kıyaslanan CRM alanları ve türü (oran, tutar, sayı, sayı yazılmış metin, seçim, bayrak,
  serbest metin). Ekrandaki ad CRM'in kendi Türkçe etiketidir (`MetadataSchema`), seçim değerlerinin adı `StringMapBase`'ten.
- **Anlaşma**: grup sözleşmesi kitap başına kayda bölünür (`new_anasozlesmeid` hepsinde ana kaydı gösterir). Aynı anlaşmanın
  bütün maddeleri birebir aynı kopyaları tek kayıttır (`Entry`); maddesi farklı kopya ayrı kalır ve kendi maddeleriyle
  incelenir. **Emsal havuzunda her anlaşma bir kez** yer alır: ana kayıt (etkin değilse numarası en küçük kayıt) anlaşmayı
  temsil eder (`Portfolio.reps`). Bir sözleşme kendi anlaşmasıyla kıyaslanmaz.
- **Kıyas grubu**: aynı sözleşme tipi, ödeme türü, para birimi ve ilgili bölüm; başlangıcı sözleşmenin başlangıç yılı ve
  önceki N yıl içinde (`years`, Yönetim ayarı). Grup `min_peers`'ten küçükse ölçütler sırayla gevşetilir: önce dönem (bütün
  yıllar), sonra bölüm, para birimi, ödeme türü; hangisinin gevşetildiği cevapta yazar. Tutar maddeleri her zaman yalnız
  aynı para birimindeki sözleşmelerle kıyaslanır.
- **Sapma**: sayısal maddede değer grubun «bu kadar yüksek (ya da düşük)» değer taşıyan kısmı `rare` oranının altındaysa
  «emsalden yüksek/düşük»; maddenin kendisi grubun `rare`'inden azında varsa «nadir madde»; grubun (1 − `rare`)'inde olan
  madde bu sözleşmede yoksa «eksik». Seçim ve bayrakta aynı değeri taşıyanlar `rare`'in altındaysa «nadir». Grupta
  `min_peers`'ten az dolu değer varsa karar verilmez («emsal az»). 0 ve boş CRM'de aynı anlamdadır (dolu sayılmaz).
- **Serbest metin**: metin (HTML ve boşluk temizlenmiş, Türkçe katlanmış) öbür anlaşmaların notlarında birebir ya da
  kelime kümesi benzerliği `text_similar` ve üstünde aranır. Hiçbir başka anlaşmada yoksa «bu sözleşmeye özgü», `template_min`
  ve üstü anlaşmada varsa «kalıp metin».

Model kullanılmaz: bütün kararlar sayım ve sıralamadır, gerekçe cümlesi sayıların kendisinden kurulur. CRM'e yazma yok.
"""
from __future__ import annotations

import bisect
import fcntl
import json
import logging
import math
import os
import re
import threading
import time
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

from semantic_bridge import contracts_terms as T
from semantic_bridge.doc_read import fold

log = logging.getLogger("semantic.contracts_compare")


class CompareError(ValueError):
    """Kişiye olduğu gibi gösterilecek düz Türkçe hata."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


# ================================================================================ madde kataloğu

@dataclass(frozen=True)
class Clause:
    key: str                       # CRM kolonu (ekrandaki alan anahtarı)
    group: str
    kind: str                      # oran | tutar | sayi | metin-sayi | secim | bayrak | metin
    label: str                     # CRM etiketi okunamazsa
    term: Optional[str] = None     # portal şartlarındaki karşılığı (`contracts_terms`, düz anahtar)


GROUPS = {
    "odeme": "Telif ve ödeme",
    "sure": "Süre ve fesih",
    "baski": "Baskı şartları",
    "haklar": "Devredilen haklar",
    "ek": "Ek belgeler ve durum",
    "not": "Serbest metinli maddeler",
}
KINDS = {"oran": "Oran", "tutar": "Tutar", "sayi": "Sayı", "metin-sayi": "Sayı (metin)", "secim": "Seçim", "bayrak": "Var/yok",
         "metin": "Serbest metin"}

CLAUSES: tuple[Clause, ...] = (
    Clause("new_telifturu", "odeme", "secim", "Telif türü", "basis"),
    Clause("new_Telif", "odeme", "oran", "Karton kapak telif %", "rates.karton"),
    Clause("new_sertkapaktelif", "odeme", "oran", "Sert kapak telif %", "rates.sert"),
    Clause("new_e_kitap_telif", "odeme", "oran", "E-kitap telif %", "rates.ekitap"),
    Clause("new_SesliKitap", "odeme", "oran", "Sesli kitap telif %", "rates.sesli"),
    Clause("new_yurtdisitelif", "odeme", "oran", "Yurtdışı telif %", "rates.yurtdisi"),
    Clause("new_yurtdisikitap", "odeme", "oran", "Yurtdışı kitap %"),
    Clause("new_telifhesaplamaiskontosu", "odeme", "oran", "Telif hesaplama iskontosu", "discountPct"),
    Clause("new_sozlesmeavanstutari", "odeme", "tutar", "Avans tutarı", "advance"),
    Clause("new_avanstutariyuzde", "odeme", "oran", "Avans yüzdesi"),
    Clause("new_TekdemeTutari", "odeme", "tutar", "Tek ödeme tutarı", "flatFee"),
    Clause("new_gorselbedeli", "odeme", "tutar", "Görsel bedeli"),
    Clause("new_SatinAlmaIndirim", "odeme", "oran", "Satın alma indirimi %"),
    Clause("new_OdemeSekli", "odeme", "secim", "Ödeme şekli"),
    Clause("new_VadeAY", "odeme", "sayi", "Vade (gün)", "paymentDays"),
    Clause("new_RaporVermeSresi", "odeme", "sayi", "Rapor verme süresi (ay)"),
    Clause("new_SozlesmeSuresiYil", "sure", "sayi", "Sözleşme süresi (yıl)", "years"),
    Clause("new_suresizsozlesme", "sure", "bayrak", "Süresiz sözleşme", "openEnded"),
    Clause("new_imhaSuresiAy", "sure", "sayi", "Yayınlanmaması hâlinde fesih süresi (ay)"),
    Clause("new_SzlemeYenilenmeSklyl", "sure", "metin-sayi", "Sözleşme yenilenme sıklığı (yıl)"),
    Clause("new_MinimumlkBaskAdedi", "baski", "metin-sayi", "Minimum ilk baskı adedi", "printRun"),
    Clause("new_flatfee", "baski", "metin-sayi", "Azami baskı adedi"),
    Clause("new_IlkBaskiHediyeAdet", "baski", "sayi", "İlk baskı hediye (adet)"),
    Clause("new_lkBaskHediyeYzde", "baski", "oran", "İlk baskı hediye (yüzde)"),
    Clause("new_TekrarBaskiHediyeAdet", "baski", "sayi", "Tekrar baskı hediye (adet)"),
    Clause("new_SzlemedeBelirtilenFazlaBasmAdet", "baski", "sayi", "Sözleşmede belirtilen fazla basım (adet)"),
    Clause("new_SzlemedeBelirtilenFazlaBasmYzde", "baski", "oran", "Sözleşmede belirtilen fazla basım (yüzde)"),
    Clause("new_MaksimumBaskiTekrari", "baski", "sayi", "Azami baskı tekrarı"),
    Clause("new_promosyonyapilabilir", "baski", "bayrak", "Promosyon yapılabilir"),
    Clause("new_cogaltmahakki", "haklar", "bayrak", "Çoğaltma hakkı", "rights.cogaltma"),
    Clause("new_yaymahakki", "haklar", "bayrak", "Yayma hakkı", "rights.yayma"),
    Clause("new_islemehakki", "haklar", "bayrak", "İşleme hakkı", "rights.islenme"),
    Clause("new_iletimhakki", "haklar", "bayrak", "İletim hakkı", "rights.iletim"),
    Clause("new_tamsilhakki", "haklar", "bayrak", "Temsil hakkı", "rights.temsil"),
    Clause("new_isaretsesgoruntu", "haklar", "bayrak", "İşaret, ses, görüntü hakkı"),
    Clause("new_EKitap", "haklar", "bayrak", "E-kitap hakkı", "rights.ekitap"),
    Clause("new_SesliKitapHakki", "haklar", "bayrak", "Sesli kitap hakkı", "rights.sesli"),
    Clause("new_ZKitapHakki", "haklar", "bayrak", "Z-kitap hakkı"),
    Clause("new_baskadilleretercume", "haklar", "bayrak", "Başka dillere tercüme hakkı", "rights.ceviri"),
    Clause("new_yurtdisitelifsatis", "haklar", "bayrak", "Yurtdışı telif satış hakkı"),
    Clause("new_malihaklardevir", "haklar", "bayrak", "Mali haklar devri"),
    Clause("new_muvafakatname", "ek", "bayrak", "Muvafakatname"),
    Clause("new_EkProtokolyeni", "ek", "bayrak", "Ek protokol"),
    Clause("new_ciftevergilendirme", "ek", "bayrak", "Çifte vergilendirme"),
    Clause("new_KorumaDEser", "ek", "bayrak", "Koruma dışı eser"),
    Clause("new_not", "not", "metin", "Sözleşme açıklaması", "notes"),
    Clause("new_telifaciklamasi2", "not", "metin", "Telif açıklaması 2"),
    Clause("new_haklaraciklama", "not", "metin", "Haklar açıklama"),
    Clause("new_hesaplamatutari", "not", "metin", "Hesaplama tutarı (açıklama)"),
)
BY_KEY = {c.key: c for c in CLAUSES}
VALUE_CLAUSES = tuple(c for c in CLAUSES if c.kind != "metin")
TEXT_CLAUSES = tuple(c for c in CLAUSES if c.kind == "metin")

#: Kıyas grubunun boyutları (CRM kolonu) ve gevşetme sırası (ilk gevşeyen ilk).
DIMS = {"tip": "new_SozlesmeTipi", "odeme": "new_TelifTipi", "para": "new_sozlesmeparabirimi", "bolum": "new_ilgilidepartman"}
DIM_LABELS = {"tip": "Sözleşme tipi", "odeme": "Ödeme türü", "para": "Para birimi", "bolum": "İlgili bölüm", "yil": "Dönem"}
RELAX = ("yil", "bolum", "para", "odeme")
OPTION_COLS = tuple(DIMS.values()) + tuple(c.key for c in CLAUSES if c.kind == "secim") + ("statuscode",)

STATUS = {
    "olagan": "Emsalle uyumlu",
    "yuksek": "Emsalden yüksek",
    "dusuk": "Emsalden düşük",
    "nadir": "Emsalde nadir",
    "nadir-madde": "Emsalde nadir madde",
    "eksik": "Emsalde var, bunda yok",
    "emsal-az": "Karar için emsal az",
    "yok": "—",
}
DEVIATING = ("yuksek", "dusuk", "nadir", "nadir-madde", "eksik")
TEXT_STATUS = {"ozgun": "Bu sözleşmeye özgü", "az": "Az rastlanan", "kalip": "Kalıp metin"}

#: Portal şartlarının CRM kodları (`contracts_terms`'ün ters eşlemeleri).
_KIND_TO_CRM = {v: k for k, v in T.KIND_FROM_CRM.items()}
_PAY_TO_CRM = {v: k for k, v in T.PAYMENT_FROM_CRM.items()}
_BASIS_TO_CRM = {v: k for k, v in T.BASIS_FROM_CRM.items()}
_CUR_TO_CRM = {v: k for k, v in T.CURRENCY_FROM_CRM.items()}


# ================================================================================ ayarlar

@dataclass(frozen=True)
class Cfg:
    min_peers: int = 20
    rare: float = 0.05
    years: int = 5
    text_similar: float = 0.80
    template_min: int = 5
    refresh_hours: float = 12.0

    def key(self) -> tuple:
        return (self.min_peers, self.rare, self.years, self.text_similar, self.template_min)


SETTINGS = {
    "CONTRACT_COMPARE_MIN_PEERS": ("min_peers", int, 20, 3, 1000),
    "CONTRACT_COMPARE_RARE_PCT": ("rare", float, 5.0, 1.0, 40.0),
    "CONTRACT_COMPARE_YEARS": ("years", int, 5, 0, 60),
    "CONTRACT_COMPARE_TEXT_SIMILAR": ("text_similar", float, 0.80, 0.5, 1.0),
    "CONTRACT_COMPARE_TEMPLATE_MIN": ("template_min", int, 5, 2, 1000),
    "CONTRACT_COMPARE_REFRESH_HOURS": ("refresh_hours", float, 12.0, 0.25, 720.0),
}


def settings(conf: Callable[[str], Any]) -> Cfg:
    """Yönetim ayarları (ekran > ortam > varsayılan); geçersiz değer varsayılana düşer ve günlüğe yazılır."""
    vals: dict[str, Any] = {}
    for key, (name, typ, default, lo, hi) in SETTINGS.items():
        raw = conf(key)
        try:
            v = typ(str(raw).replace(",", ".")) if str(raw or "").strip() else default
        except (TypeError, ValueError):
            log.warning("sözleşme karşılaştırma: %s geçersiz (%r), varsayılan %s kullanıldı", key, raw, default)
            v = default
        v = min(max(v, lo), hi)
        vals[name] = v / 100.0 if name == "rare" else v
    return Cfg(**vals)


def with_overrides(cfg: Cfg, years: Optional[int] = None) -> Cfg:
    """Ekrandan seçilen dönem (yıl sayısı; -1 = bütün yıllar)."""
    if years is None:
        return cfg
    return Cfg(cfg.min_peers, cfg.rare, max(-1, min(int(years), 60)), cfg.text_similar, cfg.template_min, cfg.refresh_hours)


# ================================================================================ CRM okuması

def _db_of(prefix: str) -> str:
    db, _, _ = prefix.rstrip(".").rpartition(".")
    return db


def portfolio_sql(p: str) -> str:
    """Bütün etkin sözleşmeler ve karşılaştırılan maddeleri (tek sorgu, satır tavanı yok). `p` = `Timas_MSCRM.dbo.`"""
    cols = []
    for c in CLAUSES:
        if c.kind == "bayrak":
            cols.append(f"CAST(ISNULL(s.{c.key}, 0) AS int) AS {c.key}")
        elif c.kind == "secim":
            cols.append(f"CAST(s.{c.key} AS int) AS {c.key}")
        elif c.kind == "metin":
            cols.append(f"CAST(s.{c.key} AS nvarchar(max)) AS {c.key}")
        else:
            cols.append(f"s.{c.key}")
    dims = ", ".join(f"CAST(s.{col} AS int) AS {col}" for col in DIMS.values())
    return ("SELECT s.new_sozlesmeId AS id, s.new_name AS no, s.new_anasozlesmeid AS ana, CAST(s.statuscode AS int) AS statuscode,"
            " s.new_SozlesmeBaslangicTarihi AS bas, s.new_SozlesmeBitisTarihi AS bit, s.new_stokaditext AS kitap,"
            f" s.new_yazar_text AS yazar, {dims}, " + ", ".join(cols)
            + f" FROM {p}new_sozlesmeBase s WHERE s.statecode = 0 ORDER BY s.new_name, s.new_sozlesmeId")


def parties_sql(p: str) -> str:
    """Sözleşme tarafları (kişi ya da firma kimliği + adı): aynı hak sahibinin önceki sözleşmeleri için."""
    return ("SELECT t.new_sozlesmeid AS sid, CAST(COALESCE(t.new_kisi, t.new_Firma) AS varchar(36)) AS pid,"
            " COALESCE(c.FullName, a.Name) AS ad"
            f" FROM {p}new_sozlesmetarafiBase t LEFT JOIN {p}ContactBase c ON c.ContactId = t.new_kisi"
            f" LEFT JOIN {p}AccountBase a ON a.AccountId = t.new_Firma"
            " WHERE t.statecode = 0 AND COALESCE(t.new_kisi, t.new_Firma) IS NOT NULL ORDER BY t.new_sozlesmeid")


def labels_sql(p: str) -> str:
    """CRM'in kendi Türkçe alan etiketleri (ekrandaki madde adı)."""
    db = _db_of(p)
    ms = f"{db}.MetadataSchema." if db else "MetadataSchema."
    names = ", ".join(f"'{c.key.lower()}'" for c in CLAUSES)
    return (f"SELECT a.LogicalName AS kolon, MAX(l.Label) AS ad FROM {ms}Attribute a JOIN {ms}Entity e ON e.EntityId = a.EntityId"
            f" JOIN {ms}LocalizedLabel l ON l.ObjectId = a.AttributeId AND l.ObjectColumnName = 'DisplayName' AND l.LanguageId = 1055"
            f" WHERE e.LogicalName = 'new_sozlesme' AND a.LogicalName IN ({names}) GROUP BY a.LogicalName")


def options_sql(p: str) -> str:
    """Seçim listelerinin adları (sözleşme tipi, ödeme türü, para birimi, bölüm, telif türü, ödeme şekli, durum)."""
    names = ", ".join(f"'{c.lower()}'" for c in OPTION_COLS)
    return (f"SELECT m.AttributeName AS kolon, m.AttributeValue AS kod, m.Value AS ad FROM {p}StringMapBase m"
            f" WHERE m.ObjectTypeCode = (SELECT e.ObjectTypeCode FROM {p}EntityView e WHERE e.Name = 'new_sozlesme')"
            f" AND m.LangId = 1055 AND m.AttributeName IN ({names}) ORDER BY m.AttributeName, m.AttributeValue")


Runner = Callable[[str], list[dict[str, Any]]]


def _cell(v: Any) -> Any:
    if isinstance(v, datetime):
        return v.isoformat()
    if hasattr(v, "isoformat"):
        return v.isoformat()
    if isinstance(v, (bytes, bytearray)):
        return None
    try:
        import decimal
        if isinstance(v, decimal.Decimal):
            return float(v)
    except Exception:  # noqa: BLE001
        pass
    return v


def read_crm(run: Runner, prefix: str) -> dict[str, Any]:
    """CRM'den anlık görüntü: sözleşmeler (sütun listesi + satırlar), taraflar, etiketler, seçenekler ve çalışan sorgular."""
    out: dict[str, Any] = {"builtAt": datetime.now(timezone.utc).isoformat(), "queries": {}}
    parts = (("portfoy", portfolio_sql(prefix)), ("taraf", parties_sql(prefix)), ("etiket", labels_sql(prefix)),
             ("secenek", options_sql(prefix)))
    rows: dict[str, list[dict[str, Any]]] = {}
    for name, sql in parts:
        t0 = time.monotonic()
        try:
            got = run(sql)
        except Exception as e:  # noqa: BLE001 — etiketler okunamazsa yerel ad kullanılır; portföy okunamazsa hata
            if name in ("etiket", "secenek"):
                log.warning("sözleşme karşılaştırma: CRM %s okunamadı: %s", name, str(e)[:200])
                got = []
            else:
                raise
        rows[name] = got
        out["queries"][name] = {"sql": sql, "rows": len(got), "ms": int((time.monotonic() - t0) * 1000),
                                "at": datetime.now(timezone.utc).isoformat()}
    cols = ["id", "no", "ana", "statuscode", "bas", "bit", "kitap", "yazar"] + list(DIMS.values()) + [c.key for c in CLAUSES]
    out["columns"] = cols
    out["rows"] = [[_cell(r.get(c)) for c in cols] for r in rows["portfoy"]]
    parties: dict[str, list[list[str]]] = defaultdict(list)
    for r in rows["taraf"]:
        sid, pid = _gid(r.get("sid")), _gid(r.get("pid"))
        if sid and pid:
            parties[sid].append([pid, str(r.get("ad") or "").strip()])
    out["parties"] = parties
    out["labels"] = {str(r.get("kolon") or "").lower(): str(r.get("ad") or "").strip() for r in rows["etiket"] if r.get("ad")}
    opts: dict[str, dict[str, str]] = defaultdict(dict)
    for r in rows["secenek"]:
        if r.get("kod") is not None:
            opts[str(r.get("kolon") or "").lower()][str(int(r["kod"]))] = str(r.get("ad") or "").strip()
    out["options"] = opts
    return out


def _gid(v: Any) -> str:
    return str(v or "").strip().strip("{}").lower()


# ================================================================================ anlık görüntü (disk + bellek)

class Snapshots:
    """CRM okuması diskte tutulur (işçiler ve yeniden başlatma aynı görüntüyü okur). Yaşı `refresh_hours`'u geçince
    arka planda yenilenir, bu sırada eski görüntü verilir (cevapta yaşı yazar). Hiç yoksa ilk istek okumayı bekler."""

    def __init__(self, root: Callable[[], str], reader: Callable[[], dict[str, Any]]):
        self.root = root
        self.reader = reader
        self.lock = threading.Lock()
        self.mem: dict[str, tuple[float, "Portfolio"]] = {}
        self.refreshing: set[str] = set()

    def path(self, tenant: str) -> Path:
        d = Path(self.root()) / re.sub(r"[^A-Za-z0-9_.-]", "_", tenant or "default")
        d.mkdir(parents=True, exist_ok=True, mode=0o700)
        return d / "portfoy.json"

    def _build(self, tenant: str, asked: Optional[float] = None) -> None:
        path = self.path(tenant)
        asked = time.time() if asked is None else asked
        with open(path.with_name("yenile.lock"), "w") as lk:
            fcntl.flock(lk, fcntl.LOCK_EX)           # iki işçi aynı anda okumaz; ikincisi bitmiş görüntüyü bulur
            try:
                if path.exists() and path.stat().st_mtime >= asked:
                    return
                data = self.reader()
                tmp = path.with_name("." + uuid.uuid4().hex + ".tmp")
                with open(tmp, "x", encoding="utf-8") as fh:
                    os.chmod(tmp, 0o600)
                    json.dump(data, fh, ensure_ascii=False, separators=(",", ":"))
                    fh.flush()
                    os.fsync(fh.fileno())
                os.replace(tmp, path)
            finally:
                fcntl.flock(lk, fcntl.LOCK_UN)

    def _refresh_bg(self, tenant: str) -> None:
        with self.lock:
            if tenant in self.refreshing:
                return
            self.refreshing.add(tenant)

        marker = self.path(tenant).with_name("yenileniyor")
        marker.touch()                             # öbür işçiler de «yenileniyor» görsün

        def job() -> None:
            try:
                self._build(tenant)
            except Exception:  # noqa: BLE001 — eski görüntü kalır, hata günlükte ve durum ucunda
                log.exception("sözleşme karşılaştırma: CRM görüntüsü yenilenemedi")
            finally:
                marker.unlink(missing_ok=True)
                with self.lock:
                    self.refreshing.discard(tenant)

        threading.Thread(target=job, name="contract-compare-refresh", daemon=True).start()

    def get(self, tenant: str, cfg: Cfg, *, force: bool = False) -> "Portfolio":
        path = self.path(tenant)
        if force or not path.exists():
            self._build(tenant)
        mtime = path.stat().st_mtime
        with self.lock:
            hit = self.mem.get(tenant)
        if hit is None or hit[0] != mtime:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            port = Portfolio(data)
            with self.lock:
                self.mem[tenant] = (mtime, port)
            hit = (mtime, port)
        if time.time() - mtime > cfg.refresh_hours * 3600:
            self._refresh_bg(tenant)
        return hit[1]

    def status(self, tenant: str) -> dict[str, Any]:
        path = self.path(tenant)
        marker = path.with_name("yenileniyor")
        with self.lock:
            busy = tenant in self.refreshing
        try:
            busy = busy or time.time() - marker.stat().st_mtime < 900   # 15 dk'dan eski işaret düşmüş işin artığıdır
        except OSError:
            pass
        if not path.exists():
            return {"var": False, "yenileniyor": busy}
        return {"var": True, "yenileniyor": busy,
                "okunduAn": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()}


# ================================================================================ değerler

_THOUSANDS = re.compile(r"^\d{1,3}(\.\d{3})+$")


def parse_num_text(v: Any) -> tuple[Optional[float], Optional[str]]:
    """Sayı yazılmış metin: «1.000» → 1000, «2,5» → 2.5, «0» → boş; sayı olmayan («Limitsiz») metin olarak kalır."""
    t = str(v if v is not None else "").strip()
    if not t:
        return None, None
    s = t.replace(" ", "")
    if _THOUSANDS.match(s):
        s = s.replace(".", "")
    s = s.replace(",", ".")
    try:
        x = float(s)
    except ValueError:
        return None, " ".join(t.split())[:60]
    if not math.isfinite(x) or x == 0:
        return None, None
    return x, None


def norm_value(c: Clause, v: Any) -> Any:
    """Karşılaştırmada kullanılan değer: sayı (float), seçim kodu (int), bayrak (bool), metin (str) ya da None (boş/0)."""
    if c.kind == "bayrak":
        return bool(v) and v not in ("0", 0)
    if c.kind == "secim":
        try:
            return None if v is None or v == "" else int(float(v))
        except (TypeError, ValueError):
            return None
    if c.kind == "metin-sayi":
        x, txt = parse_num_text(v)
        return x if x is not None else txt
    if c.kind == "metin":
        return clean_text(v)
    try:
        x = None if v is None or v == "" else float(v)
    except (TypeError, ValueError):
        return None
    return None if x is None or not math.isfinite(x) or x == 0 else round(x, 6)


_TAG = re.compile(r"<[^>]+>")


def clean_text(v: Any) -> Optional[str]:
    import html

    if v is None:
        return None
    t = " ".join(html.unescape(_TAG.sub(" ", str(v))).split())
    return t or None


def _year(iso: Any) -> Optional[int]:
    t = str(iso or "")[:4]
    return int(t) if t.isdigit() else None


# ================================================================================ portföy

@dataclass
class Entry:
    """Bir anlaşmanın maddeleri aynı olan kopyaları (kıyasın birimi)."""

    idx: int
    agreement: str
    ids: list[str]
    nos: list[str]
    dims: dict[str, Optional[int]]
    year: Optional[int]
    values: dict[str, Any]
    texts: dict[str, Optional[str]]
    status: Optional[int]
    start: Optional[str]
    end: Optional[str]
    book: str
    author: str

    @property
    def id(self) -> str:
        return self.ids[0]

    @property
    def no(self) -> str:
        return self.nos[0]


def _label(c: Clause, crm: Optional[str]) -> str:
    """CRM'in kendi etiketi; kolon adı gibi yazılmış etiket («avanstutarıyuzde») yerine katalogdaki ad."""
    t = (crm or "").strip()
    if not t or (" " not in t and t == t.lower()):
        return c.label
    return t


def _natural(text: str) -> tuple:
    return tuple(int(p) if p.isdecimal() else p.casefold() for p in re.split(r"(\d+)", text or ""))


class Portfolio:
    """Anlık görüntünün kıyasa hazır hâli: anlaşmalar, gruplar, taraflar ve not dizini (işlem başına bir kez kurulur)."""

    def __init__(self, data: dict[str, Any]):
        self.built_at = data.get("builtAt")
        self.queries = data.get("queries") or {}
        self.labels = {c.key: _label(c, (data.get("labels") or {}).get(c.key.lower())) for c in CLAUSES}
        self.options = {k: v for k, v in (data.get("options") or {}).items()}
        cols = data["columns"]
        at = {c: i for i, c in enumerate(cols)}
        self.contracts = len(data["rows"])
        by_sig: dict[tuple, Entry] = {}
        self.entries: list[Entry] = []
        self.entry_of: dict[str, Entry] = {}
        for row in sorted(data["rows"], key=lambda r: (_natural(str(r[at["no"]] or "")), str(r[at["id"]]))):
            cid = _gid(row[at["id"]])
            if not cid:
                continue
            agreement = _gid(row[at["ana"]]) or cid
            values = {c.key: norm_value(c, row[at[c.key]]) for c in VALUE_CLAUSES}
            texts = {c.key: norm_value(c, row[at[c.key]]) for c in TEXT_CLAUSES}
            dims = {d: (int(row[at[col]]) if row[at[col]] is not None else None) for d, col in DIMS.items()}
            sig = (agreement, tuple(sorted(dims.items(), key=lambda x: x[0])), tuple(values[c.key] for c in VALUE_CLAUSES),
                   tuple(texts[c.key] for c in TEXT_CLAUSES), _year(row[at["bas"]]))
            e = by_sig.get(sig)
            no = str(row[at["no"]] or "").strip() or cid
            if e is None:
                e = Entry(idx=len(self.entries), agreement=agreement, ids=[cid], nos=[no], dims=dims, year=_year(row[at["bas"]]),
                          values=values, texts=texts, status=row[at["statuscode"]], start=str(row[at["bas"]] or "")[:10] or None,
                          end=str(row[at["bit"]] or "")[:10] or None, book=str(row[at["kitap"]] or "").strip(),
                          author=str(row[at["yazar"]] or "").strip())
                by_sig[sig] = e
                self.entries.append(e)
            else:
                e.ids.append(cid)
                e.nos.append(no)
                if row[at["kitap"]] and str(row[at["kitap"]]).strip() not in e.book:
                    e.book = (e.book + " · " + str(row[at["kitap"]]).strip()).strip(" ·")
            self.entry_of[cid] = e
        self.by_agreement: dict[str, list[Entry]] = defaultdict(list)
        for e in self.entries:
            self.by_agreement[e.agreement].append(e)
        # Emsal havuzu: anlaşma başına tek temsilci — ana kaydı taşıyan kopya, yoksa numarası en küçük olan (girdiler
        # numara sırasıyla kuruldu, ilki en küçüktür).
        self.reps: list[Entry] = [next((e for e in group if e.agreement in e.ids), group[0]) for group in self.by_agreement.values()]
        self.rep_of = {r.agreement: r for r in self.reps}
        # Taraflar: kişi/firma → anlaşmalar
        self.parties_of: dict[str, list[tuple[str, str]]] = {}
        self.entries_of_party: dict[str, set[int]] = defaultdict(set)
        for sid, items in (data.get("parties") or {}).items():
            e = self.entry_of.get(sid)
            if e is None:
                continue
            for pid, name in items:
                self.parties_of.setdefault(e.agreement, [])
                if (pid, name) not in self.parties_of[e.agreement]:
                    self.parties_of[e.agreement].append((pid, name))
                self.entries_of_party[pid].add(e.idx)
        self.name_of_party = {pid: name for items in self.parties_of.values() for pid, name in items}
        self.party_by_name: dict[str, set[str]] = defaultdict(set)
        for pid, name in self.name_of_party.items():
            if name:
                self.party_by_name[fold(name)].add(pid)
        self.texts = TextIndex(self.entries)
        self._windows: dict[tuple, "Window"] = {}
        self._groups: dict[tuple, dict[tuple, list[Entry]]] = {}
        self._scan: dict[tuple, dict[str, Any]] = {}
        self.lock = threading.Lock()

    # ---------------------------------------------------------------- etiketler

    def option(self, col: str, code: Any) -> Optional[str]:
        if code is None:
            return None
        return (self.options.get(col.lower()) or {}).get(str(int(code))) or str(code)

    def dim_label(self, dim: str, code: Any) -> Optional[str]:
        return self.option(DIMS[dim], code) if dim in DIMS else None

    def show(self, c: Clause, v: Any, currency: Optional[int] = None) -> str:
        if v is None or v == "":
            return "Yok" if c.kind == "bayrak" else "—"
        if c.kind == "bayrak":
            return "Var" if v else "Yok"
        if c.kind == "secim":
            return self.option(c.key, v) or "—"
        if isinstance(v, str):
            return v
        if c.kind == "oran":
            return f"%{T.fmt_num(v)}"
        if c.kind == "tutar":
            cur = self.option("new_sozlesmeparabirimi", currency) if currency is not None else None
            return f"{T.fmt_num(v)} {cur or ''}".strip()
        return T.fmt_num(v)

    # ---------------------------------------------------------------- kıyas grubu

    def group_members(self, dims: dict[str, Optional[int]], use: tuple[str, ...]) -> list[Entry]:
        with self.lock:
            idx = self._groups.get(use)
        if idx is None:
            built: dict[tuple, list[Entry]] = defaultdict(list)
            for e in self.reps:
                built[tuple(e.dims.get(d) for d in use)].append(e)
            with self.lock:
                self._groups[use] = idx = built
        return idx.get(tuple(dims.get(d) for d in use), [])

    def window(self, dims: dict[str, Optional[int]], use: tuple[str, ...], year: Optional[int], years: int) -> "Window":
        """Kıyas penceresi: `use` boyutlarında aynı, başlangıcı [yıl − years, yıl] aralığında (years < 0 ya da yıl yoksa
        bütün yıllar) anlaşmalar. Aynı anahtarla bir kez kurulur (tarama ve sözleşme sayfası aynı pencereyi okur)."""
        key = (tuple((d, dims.get(d)) for d in use), year if years >= 0 else None, years if year is not None else -1)
        with self.lock:
            w = self._windows.get(key)
        if w is not None:
            return w
        members = self.group_members(dims, use)
        if year is not None and years >= 0:
            members = [e for e in members if e.year is not None and year - years <= e.year <= year]
        w = Window(members)
        with self.lock:
            self._windows[key] = w
        return w

    def peers_for(self, subject: "Subject", cfg: Cfg) -> tuple["Window", list[Entry], dict[str, Any]]:
        """Konunun kıyas penceresi, pencereden çıkarılacak kendi kopyaları ve kullanılan ölçütler."""
        use = [d for d in DIMS if subject.dims.get(d) is not None]
        missing = [d for d in DIMS if subject.dims.get(d) is None]
        year = subject.year
        years = cfg.years if year is not None else -1
        relaxed: list[str] = []
        steps = list(RELAX)
        while True:
            w = self.window(subject.dims, tuple(use), year, years)
            own = [e for e in w.members if e.agreement == subject.agreement]
            n = len(w.members) - len(own)
            if n >= cfg.min_peers or not steps:
                break
            step = steps.pop(0)
            if step == "yil":
                if years >= 0:
                    years = -1
                    relaxed.append("yil")
            elif step in use:
                use.remove(step)
                relaxed.append(step)
        criteria = {
            "boyutlar": [{"id": d, "ad": DIM_LABELS[d], "deger": self.dim_label(d, subject.dims.get(d))} for d in use],
            "donem": ({"ad": DIM_LABELS["yil"], "deger": f"{year - years}–{year}"} if years >= 0 and year is not None
                      else {"ad": DIM_LABELS["yil"], "deger": "Bütün yıllar"}),
            "gevsetilen": [DIM_LABELS[d] for d in relaxed],
            "bilinmeyen": [DIM_LABELS[d] for d in missing],
            "emsal": n,
            "sozlesme": sum(sum(len(x.ids) for x in self.by_agreement[e.agreement]) for e in w.members if e.agreement != subject.agreement),
            "yeterli": n >= cfg.min_peers,
            "yil": years,
        }
        return w, own, criteria

    # ---------------------------------------------------------------- tarama

    def scan(self, cfg: Cfg) -> dict[str, Any]:
        """Bütün anlaşmalar kendi emsaliyle: sapan maddeler ve özgün notlar. Sonuç ayar başına bir kez hesaplanır."""
        key = cfg.key()
        with self.lock:
            hit = self._scan.get(key)
        if hit is not None:
            return hit
        t0 = time.monotonic()
        rows = []
        by_clause: Counter = Counter()
        text_counts = self.texts.counts(cfg)
        for e in self.entries:
            subj = Subject.of_entry(e)
            w, own, crit = self.peers_for(subj, cfg)
            devs = []
            for c in VALUE_CLAUSES:
                r = evaluate(c, subj.values.get(c.key), w, own, cfg, subj, full=False)
                if r["status"] in DEVIATING:
                    devs.append({"key": c.key, "status": r["status"]})
                    by_clause[c.key] += 1
            specials = [c.key for c in TEXT_CLAUSES if e.texts.get(c.key)
                        and text_counts.get((c.key, e.idx), 0) == 0]
            rows.append({"e": e.idx, "devs": devs, "specials": specials, "peers": crit["emsal"],
                         "relaxed": crit["gevsetilen"], "enough": crit["yeterli"]})
        out = {"rows": rows, "byClause": dict(by_clause), "ms": int((time.monotonic() - t0) * 1000)}
        with self.lock:
            self._scan[key] = out
        return out


class Window:
    """Bir kıyas penceresinin madde başına sayımları (sıralı sayılar, değer sayacı, dolu sayısı)."""

    def __init__(self, members: list[Entry]):
        self.members = members
        self.n = len(members)
        self.nums: dict[str, list[float]] = {}
        self.cats: dict[str, Counter] = {}
        self.present: dict[str, int] = {}
        self.by_currency: dict[tuple[str, Optional[int]], list[float]] = {}
        self.present_by_currency: dict[tuple[str, Optional[int]], int] = defaultdict(int)
        self.n_by_currency: Counter = Counter(e.dims.get("para") for e in members)
        for c in VALUE_CLAUSES:
            vals = [e.values.get(c.key) for e in members]
            if c.kind in ("bayrak", "secim"):
                self.cats[c.key] = Counter(vals)
                self.present[c.key] = sum(1 for v in vals if v not in (None, False))
            else:
                nums = sorted(v for v in vals if isinstance(v, (int, float)) and not isinstance(v, bool))
                self.nums[c.key] = nums
                self.cats[c.key] = Counter(v for v in vals if isinstance(v, str))
                self.present[c.key] = sum(1 for v in vals if v is not None)
                if c.kind == "tutar":
                    for e in members:
                        v = e.values.get(c.key)
                        cur = e.dims.get("para")
                        if isinstance(v, (int, float)):
                            self.by_currency.setdefault((c.key, cur), []).append(v)
                            self.present_by_currency[(c.key, cur)] += 1
                    for k in [k for k in self.by_currency if k[0] == c.key]:
                        self.by_currency[k].sort()


# ================================================================================ madde değerlendirmesi

def _pct(sorted_vals: list[float], q: float) -> Optional[float]:
    """Doğrusal aradeğerli yüzdelik (SQL Server `PERCENTILE_CONT` ile aynı)."""
    n = len(sorted_vals)
    if not n:
        return None
    pos = q * (n - 1)
    lo = int(math.floor(pos))
    hi = min(lo + 1, n - 1)
    return round(sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (pos - lo), 6)


def _without(sorted_vals: list[float], remove: Iterable[float]) -> list[float]:
    out = list(sorted_vals)
    for v in remove:
        i = bisect.bisect_left(out, v)
        if i < len(out) and out[i] == v:
            out.pop(i)
    return out


def _share(a: int, b: int) -> Optional[float]:
    return round(a / b, 4) if b else None


def evaluate(c: Clause, v: Any, w: Window, own: list[Entry], cfg: Cfg, subj: "Subject", *, full: bool = True) -> dict[str, Any]:
    """Bir maddenin emsal karşısındaki durumu. `own`: pencerede olan kendi kopyaları (sayımdan düşülür). `full` iken
    dağılım (medyan, %10–%90, en sık değerler) de döner; taramada yalnız durum hesaplanır."""
    rare = cfg.rare
    if c.kind in ("bayrak", "secim"):
        counts = w.cats[c.key].copy()
        for e in own:
            counts[e.values.get(c.key)] -= 1
        n = w.n - len(own)
        key = v if c.kind == "secim" else bool(v)
        same = counts.get(key, 0)
        if c.kind == "bayrak":
            same = counts.get(True, 0) if key else counts.get(False, 0) + counts.get(None, 0)
        present = n - counts.get(None, 0) if c.kind == "secim" else counts.get(True, 0)
        if n < cfg.min_peers:
            status = "emsal-az" if v is not None else "yok"
        elif c.kind == "secim" and v is None:
            status = "eksik" if (_share(present, n) or 0) >= 1 - rare else "yok"
        else:
            status = "nadir" if (_share(same, n) or 0) < rare else "olagan"
        out = {"status": status, "n": n, "ayni": same, "ayniPay": _share(same, n), "dolu": present, "doluPay": _share(present, n)}
        if full:
            merged: Counter = Counter()
            for k, cnt in counts.items():
                if cnt > 0:
                    merged[bool(k) if c.kind == "bayrak" else k] += cnt
            out["enSik"] = [{"deger": k, "sayi": cnt, "pay": _share(cnt, n)} for k, cnt in merged.most_common(4)]
        return out

    # sayısal maddeler (oran, tutar, sayı, sayı yazılmış metin)
    if c.kind == "tutar":
        cur = subj.dims.get("para")
        nums = w.by_currency.get((c.key, cur), [])
        n = w.n_by_currency.get(cur, 0) - sum(1 for e in own if e.dims.get("para") == cur)
        present = w.present_by_currency.get((c.key, cur), 0) - sum(
            1 for e in own if e.dims.get("para") == cur and e.values.get(c.key) is not None)
        own_vals = [e.values.get(c.key) for e in own if e.dims.get("para") == cur and isinstance(e.values.get(c.key), (int, float))]
        texts: Counter = Counter()
    else:
        nums = w.nums[c.key]
        n = w.n - len(own)
        present = w.present[c.key] - sum(1 for e in own if e.values.get(c.key) is not None)
        own_vals = [e.values.get(c.key) for e in own if isinstance(e.values.get(c.key), (int, float))
                    and not isinstance(e.values.get(c.key), bool)]
        texts = w.cats[c.key].copy()
        for e in own:
            if isinstance(e.values.get(c.key), str):
                texts[e.values.get(c.key)] -= 1
    nnum = len(nums) - len(own_vals)
    out: dict[str, Any] = {"n": n, "dolu": present, "doluPay": _share(present, n), "sayisal": nnum}
    if n < cfg.min_peers:
        status = "emsal-az" if v is not None else "yok"
    elif v is None:
        status = "eksik" if (_share(present, n) or 0) >= 1 - rare else "yok"
    elif (_share(present, n) or 0) < rare:
        status = "nadir-madde"
    elif isinstance(v, str):
        same = texts.get(v, 0)
        out["ayni"] = same
        out["ayniPay"] = _share(same, present)
        status = "nadir" if (_share(same, present) or 0) < rare else "olagan"
    elif nnum < cfg.min_peers:
        status = "emsal-az"
    else:
        ge = len(nums) - bisect.bisect_left(nums, v) - sum(1 for x in own_vals if x >= v)
        le = bisect.bisect_right(nums, v) - sum(1 for x in own_vals if x <= v)
        out["ustunde"] = ge
        out["altinda"] = le
        out["konum"] = _share(nnum - ge, nnum)   # emsallerin bu değerden küçük olan kısmı
        if _share(ge, nnum) < rare:
            status = "yuksek"
        elif _share(le, nnum) < rare:
            status = "dusuk"
        else:
            status = "olagan"
    out["status"] = status
    if full:
        vals = _without(nums, own_vals)
        out.update({"medyan": _pct(vals, 0.5), "p10": _pct(vals, 0.10), "p90": _pct(vals, 0.90),
                    "enAz": vals[0] if vals else None, "enCok": vals[-1] if vals else None})
        common = Counter(vals)
        for k, cnt in texts.items():
            if cnt > 0:
                common[k] += cnt
        out["enSik"] = [{"deger": k, "sayi": cnt, "pay": _share(cnt, present)} for k, cnt in common.most_common(4)]
    return out


def reason(c: Clause, r: dict[str, Any], shown: str, port: "Portfolio", cur: Optional[int], cfg: Cfg) -> Optional[str]:
    """Durumun gerekçesi, sayıların kendisinden (model yok). Yüzde, sayının ardından ek almadan parantezde yazılır."""
    st = r["status"]
    n = r.get("n") or 0

    def pct(a: Any, b: Any) -> str:
        return f"%{T.fmt_num(round((a or 0) / b * 100, 1))}" if b else "%0"

    med = r.get("medyan")
    tail = f"; medyan {port.show(c, med, cur)}." if med is not None else "."
    if st == "emsal-az":
        have = r.get("sayisal", n)
        return f"Karar için en az {cfg.min_peers} emsal değer gerekir; bu grupta {have} var."
    if st == "nadir" and c.kind in ("bayrak", "secim"):
        return f"Aynı değer ({shown}) yalnız {r.get('ayni')}/{n} emsalde ({pct(r.get('ayni'), n)})."
    if st == "nadir":
        return f"Bu değer ({shown}) maddesi dolu {r.get('dolu')} emsalin yalnız {r.get('ayni')} tanesinde ({pct(r.get('ayni'), r.get('dolu'))})."
    if st == "nadir-madde":
        return f"Bu madde yalnız {r.get('dolu')}/{n} emsalde dolu ({pct(r.get('dolu'), n)})."
    if st == "eksik":
        return f"Bu madde {r.get('dolu')}/{n} emsalde dolu ({pct(r.get('dolu'), n)}); bu sözleşmede boş."
    if st == "yuksek":
        return (f"Bu değer ya da daha yükseği yalnız {r.get('ustunde', 0)}/{r.get('sayisal') or 0} emsalde "
                f"({pct(r.get('ustunde', 0), r.get('sayisal'))})" + tail)
    if st == "dusuk":
        return (f"Bu değer ya da daha düşüğü yalnız {r.get('altinda', 0)}/{r.get('sayisal') or 0} emsalde "
                f"({pct(r.get('altinda', 0), r.get('sayisal'))})" + tail)
    return None


# ================================================================================ konu (kıyaslanan sözleşme)

@dataclass
class Subject:
    """Kıyaslanan: CRM anlaşması, portal kaydı ya da belgeden okunan şartlar (hepsi CRM madde değerleriyle)."""

    kind: str                        # crm | portal | belge
    key: str
    no: str
    title: str
    agreement: str
    dims: dict[str, Optional[int]]
    year: Optional[int]
    values: dict[str, Any]
    texts: dict[str, Optional[str]]
    party_ids: list[str] = field(default_factory=list)
    party_names: list[str] = field(default_factory=list)
    compared: Optional[set[str]] = None       # yalnız bu maddeler kıyaslanır (portal/belge: şartlarda karşılığı olanlar)
    entry: Optional[Entry] = None

    @classmethod
    def of_entry(cls, e: Entry) -> "Subject":
        return cls("crm", e.id, e.no, e.book or e.no, e.agreement, e.dims, e.year, e.values, e.texts, entry=e)


def subject_from_terms(kind: str, key: str, no: str, terms: dict[str, Any], *, crm_entry: Optional[Entry] = None,
                       only_present: bool = False) -> Subject:
    """Portal şartları (ya da belgeden önerilen şartlar) → CRM madde değerleri. Şartlarda karşılığı olmayan madde
    kıyaslanmaz (`compared`); belgeden okunan şartlarda (`only_present`) yalnız belgede bulunan maddeler kıyaslanır —
    belgede bulunamayan madde «yok» sayılmaz. CRM'den alınmış kayıtta boyutların boş kalanı CRM kaydından tamamlanır."""
    flat = T.flatten(terms or {})
    values: dict[str, Any] = {}
    texts: dict[str, Optional[str]] = {c.key: None for c in TEXT_CLAUSES}
    compared: set[str] = set()
    for c in CLAUSES:
        if not c.term:
            continue
        raw = flat.get(c.term)
        if c.term == "basis":
            raw = _BASIS_TO_CRM.get(raw) if raw else None
        if only_present and (raw is None or raw == "" or (c.kind == "bayrak" and not raw)):
            continue
        if c.kind == "metin":
            texts[c.key] = clean_text(raw)
            compared.add(c.key)
            continue
        if c.term in ("printRun",) and raw is not None:
            raw = str(raw)
        values[c.key] = norm_value(c, raw)
        compared.add(c.key)
    dims = {"tip": _KIND_TO_CRM.get(terms.get("kind")), "odeme": _PAY_TO_CRM.get(terms.get("paymentType")),
            "para": _CUR_TO_CRM.get(terms.get("currency")), "bolum": None}
    agreement = key
    if crm_entry is not None:
        for d, v in crm_entry.dims.items():
            if dims.get(d) is None:
                dims[d] = v
        agreement = crm_entry.agreement
    ids = [str(p.get("contactId") or p.get("accountId") or "").strip("{}").lower() for p in terms.get("parties") or []]
    names = [str(p.get("name") or "").strip() for p in terms.get("parties") or [] if p.get("name")]
    return Subject(kind, key, no, str(terms.get("title") or no), agreement, dims, _year(terms.get("start")), values, texts,
                   party_ids=[i for i in ids if i], party_names=names, compared=compared, entry=crm_entry)


# ================================================================================ serbest metin dizini

_WORD = re.compile(r"[0-9a-z]+")


def _tokens(text: Optional[str]) -> frozenset[str]:
    return frozenset(_WORD.findall(fold(text or "")))


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


class TextIndex:
    """Serbest metinli maddeler: birebir (katlanmış) eşleşme sayacı ve kelime kümesi benzerliği için ters dizin."""

    def __init__(self, entries: list[Entry]):
        self.docs: list[tuple[int, str, str, frozenset[str], str]] = []   # (entry idx, alan, metin, kelimeler, katlanmış)
        self.exact: dict[str, set[str]] = defaultdict(set)                # katlanmış metin → anlaşmalar
        self.inv: dict[str, list[int]] = defaultdict(list)
        self.agreement_of: dict[int, str] = {}
        for e in entries:
            self.agreement_of[e.idx] = e.agreement
            for c in TEXT_CLAUSES:
                t = e.texts.get(c.key)
                if not t:
                    continue
                f = fold(t)
                if not f:
                    continue
                toks = _tokens(t)
                di = len(self.docs)
                self.docs.append((e.idx, c.key, t, toks, f))
                self.exact[f].add(e.agreement)
                for tok in toks:
                    self.inv[tok].append(di)
        self._counts: dict[tuple, dict[tuple[str, int], int]] = {}

    def similar(self, text: str, agreement: str, cfg: Cfg) -> dict[str, Any]:
        """Metnin öbür anlaşmalardaki karşılığı: birebir ve benzer (kelime kümesi ≥ eşik) anlaşma sayısı ve örnekler."""
        f = fold(text)
        toks = _tokens(text)
        exact = {a for a in self.exact.get(f, set()) if a != agreement}
        best: dict[str, tuple[float, int]] = {}
        if toks:
            # Aday: sorgunun en seyrek kelimelerinden birini taşıyan metinler (benzer metin eşiği bunu garanti eder:
            # benzerlik ≥ s ise ortak kelime sayısı ≥ s·|sorgu|; en seyrek ⌈(1−s)·|sorgu|⌉+1 kelimeden biri ortaktır).
            rare_toks = sorted(toks, key=lambda t: len(self.inv.get(t, ())))
            k = min(len(rare_toks), int(math.floor((1 - cfg.text_similar) * len(rare_toks))) + 1)
            cand: set[int] = set()
            for t in rare_toks[:k]:
                cand.update(self.inv.get(t, ()))
            for di in cand:
                idx, _, _, dt, df = self.docs[di]
                a = self.agreement_of[idx]
                if a == agreement:
                    continue
                s = 1.0 if df == f else jaccard(toks, dt)
                if s >= cfg.text_similar and (a not in best or s > best[a][0]):
                    best[a] = (s, di)
        near = {a for a in best if a not in exact}
        total = len(exact | near)
        status = "ozgun" if total == 0 else ("kalip" if total >= cfg.template_min else "az")
        examples = sorted(best.values(), key=lambda x: (-x[0], x[1]))[:3]
        return {"status": status, "birebir": len(exact), "benzer": len(near), "toplam": total,
                "ornekler": [{"entry": self.docs[di][0], "alan": self.docs[di][1], "metin": self.docs[di][2][:600],
                              "benzerlik": round(s, 3)} for s, di in examples]}

    def counts(self, cfg: Cfg) -> dict[tuple[str, int], int]:
        """Tarama için: her notun öbür anlaşmalarda kaç karşılığı var (birebir + benzer)."""
        key = (cfg.text_similar, cfg.template_min)
        if key in self._counts:
            return self._counts[key]
        out: dict[tuple[str, int], int] = {}
        for idx, alan, text, _, f in self.docs:
            a = self.agreement_of[idx]
            if len(self.exact.get(f, ())) - (1 if a in self.exact.get(f, ()) else 0) >= cfg.template_min:
                out[(alan, idx)] = len(self.exact[f]) - 1
                continue
            out[(alan, idx)] = self.similar(text, a, cfg)["toplam"]
        self._counts[key] = out
        return out


# ================================================================================ sözleşme sayfası

def compare(port: Portfolio, subj: Subject, cfg: Cfg) -> dict[str, Any]:
    """Konunun bütün maddeleri: değer, emsal dağılımı, durum ve gerekçe; serbest metin maddeleri; kıyas ölçütleri."""
    w, own, crit = port.peers_for(subj, cfg)
    cur = subj.dims.get("para")
    groups = []
    counts: Counter = Counter()
    for gid, glabel in GROUPS.items():
        items = []
        for c in CLAUSES:
            if c.group != gid or c.kind == "metin":
                continue
            if subj.compared is not None and c.key not in subj.compared:
                continue
            v = subj.values.get(c.key)
            r = evaluate(c, v, w, own, cfg, subj, full=True)
            shown = port.show(c, v, cur)
            for x in r.get("enSik") or []:
                x["ad"] = "Boş" if x["deger"] is None else port.show(c, x["deger"], cur)
            for k in ("medyan", "p10", "p90", "enAz", "enCok"):
                if r.get(k) is not None:
                    r[k + "Ad"] = port.show(c, r[k], cur)
            counts[r["status"]] += 1
            items.append({"key": c.key, "label": port.labels[c.key], "kind": c.kind, "value": v,
                          "valueLabel": shown, "statusLabel": STATUS[r["status"]], "reason": reason(c, r, shown, port, cur, cfg), **r})
        if items:
            groups.append({"id": gid, "label": glabel, "clauses": items})
    texts = []
    for c in TEXT_CLAUSES:
        if subj.compared is not None and c.key not in subj.compared:
            continue
        t = subj.texts.get(c.key)
        if not t:
            continue
        sim = port.texts.similar(t, subj.agreement, cfg)
        for ex in sim["ornekler"]:
            e = port.entries[ex.pop("entry")]
            ex.update({"id": e.id, "no": e.no, "alanAd": port.labels[ex["alan"]]})
        texts.append({"key": c.key, "label": port.labels[c.key], "text": t, "statusLabel": TEXT_STATUS[sim["status"]], **sim})
    peers = sorted((e for e in w.members if e.agreement != subj.agreement), key=lambda e: (-(e.year or 0), _natural(e.no)))
    return {
        "criteria": crit,
        "groups": groups,
        "texts": texts,
        "sayim": {"sapan": sum(counts[s] for s in DEVIATING), "uyumlu": counts["olagan"], "emsalAz": counts["emsal-az"],
                  "ozgunNot": sum(1 for t in texts if t["status"] == "ozgun")},
        "peers": [{"id": e.id, "no": e.no, "kitap": e.book, "yazar": e.author, "yil": e.year, "kopya": len(e.ids)} for e in peers],
    }


def history(port: Portfolio, subj: Subject) -> dict[str, Any]:
    """Aynı hak sahibinin (taraf kişi/firma) öbür sözleşmeleri, başlangıca göre; konudan önceki en yakın sözleşmeyle
    madde madde fark."""
    pids = set(subj.party_ids)
    if subj.entry is not None:
        pids |= {pid for pid, _ in port.parties_of.get(subj.agreement, [])}
    if not pids:
        for name in subj.party_names:
            pids |= port.party_by_name.get(fold(name), set())
    idxs: set[int] = set()
    for pid in pids:
        idxs |= port.entries_of_party.get(pid, set())
    others = [port.entries[i] for i in idxs if port.entries[i].agreement != subj.agreement]
    others.sort(key=lambda e: (e.start or "", _natural(e.no)), reverse=True)
    names = sorted({port.name_of_party.get(p, "") for p in pids if port.name_of_party.get(p)})
    start = (subj.entry.start if subj.entry is not None else None) or (f"{subj.year}-12-31" if subj.year else None)
    before = [e for e in others if start and e.start and e.start <= start]
    prev = before[0] if before else None
    changes = []
    if prev is not None:
        cur = subj.dims.get("para")
        for c in CLAUSES:
            if subj.compared is not None and c.key not in subj.compared:
                continue
            a = prev.texts.get(c.key) if c.kind == "metin" else prev.values.get(c.key)
            b = subj.texts.get(c.key) if c.kind == "metin" else subj.values.get(c.key)
            if c.kind == "metin":
                if fold(a or "") != fold(b or ""):
                    changes.append({"key": c.key, "label": port.labels[c.key], "old": a, "new": b})
            elif (bool(a) if c.kind == "bayrak" else a) != (bool(b) if c.kind == "bayrak" else b):
                changes.append({"key": c.key, "label": port.labels[c.key], "old": port.show(c, a, prev.dims.get("para")),
                                "new": port.show(c, b, cur)})
    items = [{"id": e.id, "no": e.no, "kitap": e.book, "bas": e.start, "bit": e.end, "yil": e.year, "kopya": len(e.ids),
              "odeme": port.dim_label("odeme", e.dims.get("odeme")),
              "oran": port.show(BY_KEY["new_Telif"], e.values.get("new_Telif")),
              "avans": port.show(BY_KEY["new_sozlesmeavanstutari"], e.values.get("new_sozlesmeavanstutari"), e.dims.get("para")),
              "tekOdeme": port.show(BY_KEY["new_TekdemeTutari"], e.values.get("new_TekdemeTutari"), e.dims.get("para"))}
             for e in others]
    return {"taraflar": names, "items": items, "onceki": ({"id": prev.id, "no": prev.no, "bas": prev.start} if prev else None),
            "degisen": changes}


def warnings_of(subj: Subject) -> list[str]:
    out = []
    now = datetime.now(timezone.utc).year
    if subj.year is not None and subj.year > now + 1:
        out.append(f"Başlangıç yılı {subj.year}: CRM'de tarih yanlış girilmiş olabilir; dönem ölçütü bu yıla göre kuruldu.")
    if subj.year is None:
        out.append("Başlangıç tarihi yok; emsal bütün yıllardan seçildi.")
    rates = [(BY_KEY[k], subj.values.get(k)) for k in ("new_Telif", "new_sertkapaktelif", "new_e_kitap_telif", "new_SesliKitap")]
    small = [c.label for c, v in rates if isinstance(v, float) and 0 < v < 1]
    if small:
        out.append("Telif oranı 1'in altında (" + ", ".join(small) + "): yüzde yerine kesir girilmiş olabilir (0,07 = %7 mi?).")
    return out


def subject_head(port: Portfolio, subj: Subject) -> dict[str, Any]:
    e = subj.entry
    return {"kaynak": subj.kind, "key": subj.key, "no": subj.no, "baslik": subj.title,
            "yazar": e.author if e is not None else ", ".join(subj.party_names),
            "tip": port.dim_label("tip", subj.dims.get("tip")), "odeme": port.dim_label("odeme", subj.dims.get("odeme")),
            "para": port.dim_label("para", subj.dims.get("para")), "bolum": port.dim_label("bolum", subj.dims.get("bolum")),
            "yil": subj.year, "bas": e.start if e is not None else None, "bit": e.end if e is not None else None,
            "durum": port.option("statuscode", e.status) if e is not None and e.status is not None else None,
            "kopyalar": ([{"id": i, "no": n} for i, n in zip(e.ids, e.nos)] if e is not None else []),
            "anlasma": [{"id": x.id, "no": x.no} for x in port.by_agreement.get(subj.agreement, []) if e is None or x.idx != e.idx]}


# ================================================================================ tarama listesi

def scan_page(port: Portfolio, cfg: Cfg, *, q: str = "", tip: Optional[int] = None, odeme: Optional[int] = None,
              bolum: Optional[int] = None, yil_from: Optional[int] = None, yil_to: Optional[int] = None, only: str = "sapan",
              clause: str = "", aktif: bool = False, min_devs: int = 1, page: int = 0, size: int = 50) -> dict[str, Any]:
    """Tarama sonucu süzülür ve sayfalanır (toplam her zaman yazar; sessiz kesme yok)."""
    res = port.scan(cfg)
    k = fold(q)
    active = {100000000, 100000006, 100000007}
    rows = []
    for r in res["rows"]:
        e = port.entries[r["e"]]
        if tip is not None and e.dims.get("tip") != tip:
            continue
        if odeme is not None and e.dims.get("odeme") != odeme:
            continue
        if bolum is not None and e.dims.get("bolum") != bolum:
            continue
        if yil_from is not None and (e.year is None or e.year < yil_from):
            continue
        if yil_to is not None and (e.year is None or e.year > yil_to):
            continue
        if aktif and e.status not in active:
            continue
        if clause and not any(d["key"] == clause for d in r["devs"]):
            continue
        if only == "sapan" and len(r["devs"]) < max(1, int(min_devs)):
            continue
        if only == "ozgun" and not r["specials"]:
            continue
        if only == "hepsi-sapma" and not (r["devs"] or r["specials"]):
            continue
        if k and k not in fold(" ".join([*e.nos, e.book, e.author])):
            continue
        rows.append((r, e))
    rows.sort(key=lambda x: (-len(x[0]["devs"]), -len(x[0]["specials"]), -(x[1].year or 0), _natural(x[1].no)))
    total = len(rows)
    size = max(1, min(int(size), 200))
    page = max(0, int(page))
    items = []
    for r, e in rows[page * size:(page + 1) * size]:
        cur = e.dims.get("para")
        items.append({
            "id": e.id, "no": e.no, "kopya": len(e.ids), "kitap": e.book, "yazar": e.author, "yil": e.year,
            "tip": port.dim_label("tip", e.dims.get("tip")), "odeme": port.dim_label("odeme", e.dims.get("odeme")),
            "para": port.dim_label("para", cur), "bolum": port.dim_label("bolum", e.dims.get("bolum")),
            "durum": port.option("statuscode", e.status) if e.status is not None else None,
            "emsal": r["peers"], "gevsetilen": r["relaxed"], "yeterli": r["enough"],
            "sapmalar": [{"key": d["key"], "label": port.labels[d["key"]], "status": d["status"], "statusLabel": STATUS[d["status"]],
                          "valueLabel": port.show(BY_KEY[d["key"]], e.values.get(d["key"]), cur)} for d in r["devs"]],
            "ozgunNotlar": [{"key": key, "label": port.labels[key]} for key in r["specials"]],
        })
    all_rows = res["rows"]
    return {
        "items": items, "total": total, "page": page, "pageSize": size,
        "ozet": {
            "sozlesme": port.contracts,
            "anlasma": len(port.reps),
            "sapan": sum(1 for r in all_rows if r["devs"]),
            "ozgun": sum(1 for r in all_rows if r["specials"]),
            "emsalYetersiz": sum(1 for r in all_rows if not r["enough"]),
        },
        "maddeler": [{"key": key, "label": port.labels[key], "sayi": n}
                     for key, n in sorted(res["byClause"].items(), key=lambda x: (-x[1], x[0]))],
        "hesapMs": res["ms"],
    }


def facets(port: Portfolio) -> dict[str, Any]:
    """Süzgeç seçenekleri ve sayıları (anlaşma sayısı)."""
    def count(dim: str) -> list[dict[str, Any]]:
        c = Counter(e.dims.get(dim) for e in port.reps)
        return [{"kod": k, "ad": port.dim_label(dim, k), "sayi": n} for k, n in sorted(c.items(), key=lambda x: -x[1]) if k is not None]

    years = sorted({e.year for e in port.entries if e.year is not None})
    return {"tip": count("tip"), "odeme": count("odeme"), "bolum": count("bolum"), "para": count("para"),
            "yillar": years, "maddeler": [{"key": c.key, "label": port.labels[c.key], "grup": c.group} for c in VALUE_CLAUSES]}


def search(port: Portfolio, q: str, page: int = 0, size: int = 20) -> dict[str, Any]:
    """Sözleşme seçici: numara, kitap ya da yazar adında arama (anlaşma başına tek satır, toplam yazar)."""
    k = fold(q)
    if len(k) < 2:
        raise CompareError("En az iki harf yazın.")
    hits = [e for e in port.entries if k in fold(" ".join([*e.nos, e.book, e.author]))]
    hits.sort(key=lambda e: (-(e.year or 0), _natural(e.no)))
    page = max(0, int(page))
    return {"items": [{"id": e.id, "no": e.no, "kitap": e.book, "yazar": e.author, "yil": e.year, "kopya": len(e.ids),
                       "odeme": port.dim_label("odeme", e.dims.get("odeme"))}
                      for e in hits[page * size:(page + 1) * size]],
            "total": len(hits), "page": page, "pageSize": size}


__all__ = [
    "CLAUSES", "GROUPS", "STATUS", "TEXT_STATUS", "Cfg", "CompareError", "Portfolio", "Snapshots", "Subject", "compare",
    "facets", "history", "parse_num_text", "read_crm", "scan_page", "search", "settings", "subject_from_terms", "warnings_of",
]
