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
DIM_LABELS = {"tip": "Sözleşme tipi", "odeme": "Ödeme türü", "para": "Para birimi", "bolum": "İlgili bölüm", "yil": "Dönem",
              "ajans": "Ajans üzerinden", "satis": "Hak sahibinin satış dilimi", "hedef": "Hedef kitle", "tur": "Tür",
              "dil": "Yerli / çeviri"}
RELAX = ("yil", "bolum", "para", "odeme")
#: İsteğe bağlı ticari ölçütler (ekrandan seçilir; varsayılanı Yönetim ayarı). Gevşetmede ilk bunlar düşer.
EXTRA_DIMS = ("ajans", "satis", "hedef", "tur", "dil")
SALES_TIERS = {"ust": "Üst %20 (çok satan)", "orta": "Orta %40", "alt": "Alt %40", "yok": "Son 36 ayda satışı yok"}
#: Kıyaslanmayan ama şekil denetiminin okuduğu bilgiler (kitap bağı sayısı, telif satışında ülke var mı).
META_COLS = ("kitapsay", "ulkevar")
#: Olay zaman çizelgesi (kıyaslanmaz): CRM'deki ek belge ve durum tarihleri.
EVENT_COLS = {
    "new_ekprotokoltarihi": "Ek protokol", "new_ekprotokolbitist": "Ek protokol bitişi",
    "new_muvafakatnametarihi": "Muvafakatname", "new_muvafakatnamebitist": "Muvafakatname bitişi",
    "new_emuvafakatnamebitistt": "E-kitap muvafakatnamesi bitişi", "new_malihakdevirt": "Mali hak devri",
    "new_fesihtarihi": "Fesih", "new_yenilemebaslangictarihi": "Yenileme başlangıcı",
    "new_yenilemebitistarihi": "Yenileme bitişi", "new_YaynlanmamasHalindeFesihTarihi": "Yayınlanmama hâlinde fesih tarihi",
}
TRY_CODE, USD_CODE = 1, 2
OPTION_COLS = tuple(DIMS.values()) + tuple(c.key for c in CLAUSES if c.kind == "secim") + ("statuscode",)

STATUS = {
    "olagan": "Emsalle uyumlu",
    "yuksek": "Emsalden yüksek",
    "dusuk": "Emsalden düşük",
    "nadir": "Emsalde nadir",
    "nadir-madde": "Emsalde nadir madde",
    "eksik": "Emsalde var, bunda yok",
    "emsal-az": "Karar için emsal az",
    "kur-yok": "Kur okunamadı",
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
    dims: tuple = ()

    def key(self) -> tuple:
        return (self.min_peers, self.rare, self.years, self.text_similar, self.template_min, self.dims)


SETTINGS = {
    "CONTRACT_COMPARE_MIN_PEERS": ("min_peers", int, 20, 3, 1000),
    "CONTRACT_COMPARE_RARE_PCT": ("rare", float, 5.0, 1.0, 40.0),
    "CONTRACT_COMPARE_YEARS": ("years", int, 5, 0, 60),
    "CONTRACT_COMPARE_TEXT_SIMILAR": ("text_similar", float, 0.80, 0.5, 1.0),
    "CONTRACT_COMPARE_TEMPLATE_MIN": ("template_min", int, 5, 2, 1000),
    "CONTRACT_COMPARE_REFRESH_HOURS": ("refresh_hours", float, 12.0, 0.25, 720.0),
}


def parse_dims(raw: Any) -> tuple:
    """«ajans,satis» → ('ajans', 'satis'); bilinmeyen ölçüt atılır, sıra EXTRA_DIMS sırasıdır."""
    got = {x.strip() for x in str(raw or "").split(",") if x.strip()}
    return tuple(d for d in EXTRA_DIMS if d in got)


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
    return Cfg(**vals, dims=parse_dims(conf("CONTRACT_COMPARE_EXTRA_DIMS")))


def with_overrides(cfg: Cfg, years: Optional[int] = None, dims: Optional[str] = None) -> Cfg:
    """Ekrandan seçilen dönem (yıl sayısı; -1 = bütün yıllar) ve isteğe bağlı ölçütler («ajans,satis»; boş = hiçbiri)."""
    y = cfg.years if years is None else max(-1, min(int(years), 60))
    d = cfg.dims if dims is None else parse_dims(dims)
    return Cfg(cfg.min_peers, cfg.rare, y, cfg.text_similar, cfg.template_min, cfg.refresh_hours, d)


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
            + "".join(f", s.{c}" for c in EVENT_COLS)
            + f", (SELECT COUNT(*) FROM {p}new_new_sozlesme_new_kitapBase sk WHERE sk.new_sozlesmeid = s.new_sozlesmeId) AS kitapsay,"
            " CASE WHEN s.new_telifsatilanulke IS NULL THEN 0 ELSE 1 END AS ulkevar"
            f" FROM {p}new_sozlesmeBase s WHERE s.statecode = 0 ORDER BY s.new_name, s.new_sozlesmeId")


def parties_sql(p: str) -> str:
    """Sözleşme tarafları (kişi ya da firma kimliği + adı): aynı hak sahibinin önceki sözleşmeleri için."""
    return ("SELECT t.new_sozlesmeid AS sid, CAST(COALESCE(t.new_kisi, t.new_Firma) AS varchar(36)) AS pid,"
            " COALESCE(c.FullName, a.Name) AS ad, CAST(ISNULL(t.new_aracivarmi, 0) AS int) AS araci"
            f" FROM {p}new_sozlesmetarafiBase t LEFT JOIN {p}ContactBase c ON c.ContactId = t.new_kisi"
            f" LEFT JOIN {p}AccountBase a ON a.AccountId = t.new_Firma"
            " WHERE t.statecode = 0 AND COALESCE(t.new_kisi, t.new_Firma) IS NOT NULL ORDER BY t.new_sozlesmeid")


def books_sql(p: str) -> str:
    """Sözleşmenin kitapları: stok kodu (satış dilimi), hedef kitle, tür ve orijinal dil (yerli/çeviri). Lookup adı için
    CRM'in `new_kitap` görünümü okunur."""
    return ("SELECT sk.new_sozlesmeid AS sid, k.new_StokKodu AS kod, CAST(k.new_hedefkitle AS int) AS hedef,"
            " k.new_turlertext AS tur, k.new_orjinaldiliName AS dil"
            f" FROM {p}new_new_sozlesme_new_kitapBase sk JOIN {p}new_kitap k ON k.new_kitapId = sk.new_kitapid"
            " ORDER BY sk.new_sozlesmeid, k.new_name")


def book_options_sql(p: str) -> str:
    return (f"SELECT m.AttributeValue AS kod, m.Value AS ad FROM {p}StringMapBase m"
            f" WHERE m.ObjectTypeCode = (SELECT e.ObjectTypeCode FROM {p}EntityView e WHERE e.Name = 'new_kitap')"
            " AND m.LangId = 1055 AND m.AttributeName = 'new_hedefkitle' ORDER BY m.AttributeValue")


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
    parts = (("portfoy", portfolio_sql(prefix)), ("taraf", parties_sql(prefix)), ("kitap", books_sql(prefix)),
             ("etiket", labels_sql(prefix)), ("secenek", options_sql(prefix)), ("kitapsecenek", book_options_sql(prefix)))
    rows: dict[str, list[dict[str, Any]]] = {}
    for name, sql in parts:
        t0 = time.monotonic()
        try:
            got = run(sql)
        except Exception as e:  # noqa: BLE001 — etiketler okunamazsa yerel ad kullanılır; portföy okunamazsa hata
            if name in ("etiket", "secenek", "kitap", "kitapsecenek"):
                log.warning("sözleşme karşılaştırma: CRM %s okunamadı: %s", name, str(e)[:200])
                got = []
            else:
                raise
        rows[name] = got
        out["queries"][name] = {"sql": sql, "rows": len(got), "ms": int((time.monotonic() - t0) * 1000),
                                "at": datetime.now(timezone.utc).isoformat()}
    cols = (["id", "no", "ana", "statuscode", "bas", "bit", "kitap", "yazar"] + list(DIMS.values()) + [c.key for c in CLAUSES]
            + list(META_COLS) + list(EVENT_COLS))
    out["columns"] = cols
    out["rows"] = [[_cell(r.get(c)) for c in cols] for r in rows["portfoy"]]
    parties: dict[str, list[list[str]]] = defaultdict(list)
    for r in rows["taraf"]:
        sid, pid = _gid(r.get("sid")), _gid(r.get("pid"))
        if sid and pid:
            parties[sid].append([pid, str(r.get("ad") or "").strip(), int(r.get("araci") or 0)])
    out["parties"] = parties
    books: dict[str, list[list[Any]]] = defaultdict(list)
    for r in rows["kitap"]:
        sid = _gid(r.get("sid"))
        if sid:
            books[sid].append([str(r.get("kod") or "").strip() or None, r.get("hedef"), str(r.get("tur") or "").strip() or None,
                               str(r.get("dil") or "").strip() or None])
    out["books"] = books
    out["bookOptions"] = {str(int(r["kod"])): str(r.get("ad") or "").strip() for r in rows["kitapsecenek"] if r.get("kod") is not None}
    out["labels"] = {str(r.get("kolon") or "").lower(): str(r.get("ad") or "").strip() for r in rows["etiket"] if r.get("ad")}
    opts: dict[str, dict[str, str]] = defaultdict(dict)
    for r in rows["secenek"]:
        if r.get("kod") is not None:
            opts[str(r.get("kolon") or "").lower()][str(int(r["kod"]))] = str(r.get("ad") or "").strip()
    out["options"] = opts
    return out


def _gid(v: Any) -> str:
    return str(v or "").strip().strip("{}").lower()


# ================================================================================ kur (TL tutarlar dolara çevrilir)

#: TL tutarlar sözleşmenin başladığı ayın ilk günü geçerli TCMB döviz alış (USD) kuruyla dolara çevrilip kıyaslanır:
#: beş yılda kur beş katına çıktığı için nominal TL kıyası eskiyi «düşük», yeniyi «yüksek» gösteriyordu. 2005 öncesi
#: TCMB dosyası eski lira yazar (1 USD ≈ 1.500.000 TL) → milyona bölünür. Okunamayan ayın tutarı kıyasa girmez.
RATE_RETRY_SECONDS = 24 * 3600


def month_of(iso: Any) -> Optional[str]:
    t = str(iso or "")[:7]
    return t if re.match(r"^\d{4}-\d{2}$", t) and 1990 <= int(t[:4]) <= datetime.now(timezone.utc).year + 1 else None


def needed_months(data: dict[str, Any]) -> set[str]:
    """Kura çevrilecek TL tutarların başlangıç ayları."""
    at = {c: i for i, c in enumerate(data["columns"])}
    money = [c.key for c in CLAUSES if c.kind == "tutar"]
    out: set[str] = set()
    for row in data["rows"]:
        if row[at[DIMS["para"]]] == TRY_CODE and any((row[at[k]] or 0) not in (0, None) for k in money):
            m = month_of(row[at["bas"]])
            if m:
                out.add(m)
    return out


def default_fetch(url: str) -> tuple[int, str]:
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "TimasZekiBot/1.0"}), timeout=15) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""


class Rates:
    """Ay → USD kuru (diskte `kur.json`). Eksik aylar arka planda TCMB'den tamamlanır; okunamayan ay bir gün sonra
    yeniden denenir."""

    def __init__(self, root: Callable[[], str], fetch: Optional[Callable[[str], tuple[int, str]]] = None):
        self.root = root
        self.fetch = fetch or default_fetch
        self.lock = threading.Lock()
        self.busy: set[str] = set()

    def path(self, tenant: str) -> Path:
        d = Path(self.root()) / re.sub(r"[^A-Za-z0-9_.-]", "_", tenant or "default")
        d.mkdir(parents=True, exist_ok=True, mode=0o700)
        return d / "kur.json"

    def load(self, tenant: str) -> dict[str, Any]:
        try:
            return json.loads(self.path(tenant).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def mtime(self, tenant: str) -> float:
        try:
            return self.path(tenant).stat().st_mtime
        except OSError:
            return 0.0

    def missing(self, tenant: str, months: set[str]) -> list[str]:
        have = self.load(tenant)
        now = time.time()
        return sorted(m for m in months if not (have.get(m) or {}).get("kur")
                      and now - float((have.get(m) or {}).get("denendi") or 0) > RATE_RETRY_SECONDS)

    def fill(self, tenant: str, months: list[str]) -> int:
        from datetime import date as _date
        from semantic_bridge.contracts_royalty import tcmb_rate

        got = self.load(tenant)
        n = 0
        for i, m in enumerate(months):
            y, mo = int(m[:4]), int(m[5:7])
            try:
                r = tcmb_rate("USD", _date(y, mo, 1), self.fetch)
            except Exception as e:  # noqa: BLE001 — ağ düşerse o ay sonra denenir
                log.warning("sözleşme karşılaştırma: %s kuru okunamadı: %s", m, str(e)[:120])
                r = None
            if r and r.get("rate"):
                rate = float(r["rate"])
                if rate > 10000:                     # 2005 öncesi eski lira
                    rate = rate / 1_000_000
                got[m] = {"kur": round(rate, 6), "gun": r.get("on"), "kaynak": r.get("source")}
                n += 1
            else:
                got[m] = {"kur": None, "denendi": time.time()}
            if i % 20 == 19 or i == len(months) - 1:
                self._save(tenant, got)
        return n

    def _save(self, tenant: str, data: dict[str, Any]) -> None:
        path = self.path(tenant)
        tmp = path.with_name("." + uuid.uuid4().hex + ".tmp")
        with open(tmp, "x", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, sort_keys=True)
        os.replace(tmp, path)

    def fill_bg(self, tenant: str, months: list[str]) -> None:
        with self.lock:
            if tenant in self.busy or not months:
                return
            self.busy.add(tenant)

        def job() -> None:
            try:
                n = self.fill(tenant, months)
                log.info("sözleşme karşılaştırma: %d/%d ayın kuru okundu", n, len(months))
            except Exception:  # noqa: BLE001
                log.exception("sözleşme karşılaştırma: kurlar okunamadı")
            finally:
                with self.lock:
                    self.busy.discard(tenant)

        threading.Thread(target=job, name="contract-compare-rates", daemon=True).start()

    def status(self, tenant: str, months: set[str]) -> dict[str, Any]:
        have = self.load(tenant)
        ok = sum(1 for m in months if (have.get(m) or {}).get("kur"))
        with self.lock:
            busy = tenant in self.busy
        return {"ay": len(months), "okunan": ok, "okunuyor": busy}


# ================================================================================ Logo satışı (satış dilimi)

def sales_last_months(part: Optional[dict[str, Any]], months: int = 36) -> Optional[dict[str, float]]:
    """Yazar ilişkilerinin hazırladığı Logo satışından (stok kodu × ay × satış/iade) stok kodu başına son `months` ayın
    net adedi (satış − iade). Hazırlık yoksa None (satış dilimi ölçütü kullanılamaz, ekranda yazar)."""
    data = (part or {}).get("data") or {}
    years = data.get("years") or {}
    if not years:
        return None
    end = str(data.get("dataEnd") or "")[:7]
    if re.match(r"^\d{4}-\d{2}$", end):
        last = int(end[:4]) * 12 + int(end[5:7]) - 1
    else:
        y = max(int(k) for k in years)
        last = y * 12 + 11
    first = last - months + 1
    out: dict[str, float] = defaultdict(float)
    for y, blob in years.items():
        for code, rows in ((blob or {}).get("rows") or {}).items():
            for ay, ret, qty, _net in rows:
                m = int(y) * 12 + int(ay) - 1
                if first <= m <= last:
                    out[code] += -abs(float(qty or 0)) if ret else float(qty or 0)
    return dict(out)


# ================================================================================ anlık görüntü (disk + bellek)

class Snapshots:
    """CRM okuması diskte tutulur (işçiler ve yeniden başlatma aynı görüntüyü okur). Yaşı `refresh_hours`'u geçince
    arka planda yenilenir, bu sırada eski görüntü verilir (cevapta yaşı yazar). Hiç yoksa ilk istek okumayı bekler."""

    def __init__(self, root: Callable[[], str], reader: Callable[[], dict[str, Any]],
                 fetch: Optional[Callable[[str], tuple[int, str]]] = None):
        self.root = root
        self.reader = reader
        self.rates = Rates(root, fetch)
        self.lock = threading.Lock()
        self.mem: dict[str, tuple[tuple[float, float], "Portfolio"]] = {}
        self.months: dict[str, tuple[float, set[str]]] = {}
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

    def get(self, tenant: str, cfg: Cfg, *, force: bool = False,
            sales: Optional[tuple[float, dict[str, float]]] = None) -> "Portfolio":
        """`sales`: (hazırlandığı an, stok kodu → son 36 ay net adet) — yazar ilişkilerinin Logo satış hazırlığından."""
        path = self.path(tenant)
        if force or not path.exists():
            self._build(tenant)
        mtime = path.stat().st_mtime
        key = (mtime, self.rates.mtime(tenant), sales[0] if sales else None)
        with self.lock:
            hit = self.mem.get(tenant)
        if hit is None or hit[0] != key:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            months = needed_months(data)
            with self.lock:
                self.months[tenant] = (mtime, months)
            port = Portfolio(data, self.rates.load(tenant), sales[1] if sales else None)
            port.rate_status = self.rates.status(tenant, months)
            with self.lock:
                self.mem[tenant] = (key, port)
            hit = (key, port)
            self.rates.fill_bg(tenant, self.rates.missing(tenant, months))
        if time.time() - mtime > cfg.refresh_hours * 3600:
            self._refresh_bg(tenant)
        return hit[1]

    def rate_status(self, tenant: str) -> dict[str, Any]:
        with self.lock:
            months = (self.months.get(tenant) or (0, set()))[1]
        return self.rates.status(tenant, months)

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
    meta: dict[str, Any] = field(default_factory=dict)      # kitap bağı sayısı, ülke var mı (şekil denetimi)
    real: dict[str, Optional[float]] = field(default_factory=dict)  # tutar maddeleri: TL ise USD karşılığı

    @property
    def id(self) -> str:
        return self.ids[0]

    @property
    def no(self) -> str:
        return self.nos[0]


_MONTHS = ("Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık")


def _month_tr(ym: Optional[str]) -> str:
    return f"{_MONTHS[int(ym[5:7]) - 1]} {ym[:4]}" if ym else "—"


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

    def __init__(self, data: dict[str, Any], rates: Optional[dict[str, Any]] = None,
                 sales: Optional[dict[str, float]] = None):
        self.rate_info = {m: v for m, v in (rates or {}).items() if (v or {}).get("kur")}
        self.rates = {m: float(v["kur"]) for m, v in self.rate_info.items()}
        self.rate_status: dict[str, Any] = {}
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
            meta = {k: (row[at[k]] if k in at else None) for k in META_COLS}
            meta["olaylar"] = {k: str(row[at[k]])[:10] for k in EVENT_COLS if k in at and row[at[k]] not in (None, "", 0)}
            if e is None:
                e = Entry(idx=len(self.entries), agreement=agreement, ids=[cid], nos=[no], dims=dims, year=_year(row[at["bas"]]),
                          values=values, texts=texts, status=row[at["statuscode"]], start=str(row[at["bas"]] or "")[:10] or None,
                          end=str(row[at["bit"]] or "")[:10] or None, book=str(row[at["kitap"]] or "").strip(),
                          author=str(row[at["yazar"]] or "").strip(), meta=dict(meta))
                by_sig[sig] = e
                self.entries.append(e)
            else:
                e.ids.append(cid)
                e.nos.append(no)
                if meta.get("kitapsay") is not None:
                    e.meta["kitapsay"] = (e.meta.get("kitapsay") or 0) + int(meta["kitapsay"] or 0)
                e.meta["ulkevar"] = max(int(e.meta.get("ulkevar") or 0), int(meta.get("ulkevar") or 0))
                if row[at["kitap"]] and str(row[at["kitap"]]).strip() not in e.book:
                    e.book = (e.book + " · " + str(row[at["kitap"]]).strip()).strip(" ·")
            self.entry_of[cid] = e
        for e in self.entries:
            e.real = self.to_real(e.values, e.dims.get("para"), e.start)
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
        self.agent_agreements: set[str] = set()
        for sid, items in (data.get("parties") or {}).items():
            e = self.entry_of.get(sid)
            if e is None:
                continue
            for it in items:
                pid, name = it[0], it[1]
                if len(it) > 2 and it[2]:
                    self.agent_agreements.add(e.agreement)
                self.parties_of.setdefault(e.agreement, [])
                if (pid, name) not in self.parties_of[e.agreement]:
                    self.parties_of[e.agreement].append((pid, name))
                self.entries_of_party[pid].add(e.idx)
        self.name_of_party = {pid: name for items in self.parties_of.values() for pid, name in items}
        self.party_by_name: dict[str, set[str]] = defaultdict(set)
        for pid, name in self.name_of_party.items():
            if name:
                self.party_by_name[fold(name)].add(pid)
        self.book_options = data.get("bookOptions") or {}
        self.sales_known = sales is not None
        self._extra_dims(data.get("books") or {}, sales)
        self.texts = TextIndex(self.entries)
        self._windows: dict[tuple, "Window"] = {}
        self._groups: dict[tuple, dict[tuple, list[Entry]]] = {}
        self._scan: dict[tuple, dict[str, Any]] = {}
        self.lock = threading.Lock()

    # ---------------------------------------------------------------- ticari ölçütler

    def _extra_dims(self, books: dict[str, list[list[Any]]], sales: Optional[dict[str, float]]) -> None:
        """Anlaşma başına isteğe bağlı ölçütler: ajans üzerinden mi, hak sahibinin satış dilimi, kitapların hedef kitlesi,
        türü (türler metninin ilk türü) ve yerli/çeviri (kitabın orijinal dili; Türkçe ve Osmanlı Türkçesi yerli)."""
        self.party_sales: dict[str, float] = {}
        codes_of: dict[int, set[str]] = {}
        for e in self.entries:
            rows = [b for cid in e.ids for b in books.get(cid, [])]
            codes_of[e.idx] = {b[0] for b in rows if b[0]}
            hedef = Counter(int(b[1]) for b in rows if b[1] is not None).most_common(1)
            tur = Counter(str(b[2]).split(",")[0].strip() for b in rows if b[2]).most_common(1)
            langs = {str(b[3]) for b in rows if b[3]}
            e.dims["hedef"] = hedef[0][0] if hedef else None
            e.dims["tur"] = tur[0][0] if tur and tur[0][0] else None
            e.dims["dil"] = (("ceviri" if langs - {"Türkçe", "Osmanlı Türkçesi"} else "yerli") if langs else None)
            e.dims["ajans"] = 1 if e.agreement in self.agent_agreements else 0
            e.dims["satis"] = None
        if sales is None:
            return
        # Hak sahibinin son 36 ay net satış adedi: bütün sözleşmelerinin kitaplarının stok kodları
        qty: dict[str, float] = {}
        for pid, idxs in self.entries_of_party.items():
            codes = set().union(*(codes_of.get(i, set()) for i in idxs)) if idxs else set()
            qty[pid] = sum(sales.get(c, 0.0) for c in codes)
        sold = sorted(v for v in qty.values() if v > 0)
        def tier(v: float) -> str:
            if v <= 0 or not sold:
                return "yok"
            below = bisect.bisect_left(sold, v) / len(sold)
            return "ust" if below >= 0.8 else "orta" if below >= 0.4 else "alt"
        self.party_sales = qty
        for e in self.entries:
            pids = [pid for pid, _ in self.parties_of.get(e.agreement, [])]
            if pids:
                best = max(qty.get(p, 0.0) for p in pids)
                e.dims["satis"] = tier(best)

    # ---------------------------------------------------------------- kur

    def to_real(self, values: dict[str, Any], para: Optional[int], start: Optional[str]) -> dict[str, Optional[float]]:
        """Tutar maddelerinin kıyas değeri: TL ise başlangıç ayının USD kuruyla dolar, döviz ise kendisi; kur yoksa None."""
        rate = self.rates.get(month_of(start) or "") if para == TRY_CODE else None
        out: dict[str, Optional[float]] = {}
        for c in CLAUSES:
            if c.kind != "tutar":
                continue
            v = values.get(c.key)
            if not isinstance(v, (int, float)) or isinstance(v, bool):
                out[c.key] = None
            elif para == TRY_CODE:
                out[c.key] = round(v / rate, 4) if rate else None
            else:
                out[c.key] = float(v)
        return out

    def money_label(self, c: "Clause", nominal: Any, real: Optional[float], para: Optional[int], start: Optional[str]) -> str:
        base = self.show(c, nominal, para)
        if para != TRY_CODE or nominal is None:
            return base
        m = month_of(start)
        info = self.rate_info.get(m or "")
        if real is None or not info:
            return f"{base} (başlangıç ayının kuru okunamadı)"
        return f"{base} ≈ {T.fmt_num(real, 0)} USD ({_month_tr(m)} kuru {T.fmt_num(info['kur'], 4)})"

    def stat_currency(self, para: Optional[int]) -> Optional[int]:
        """Dağılım rakamlarının para birimi: TL sözleşmelerde kıyas dolar üzerinden."""
        return USD_CODE if para == TRY_CODE else para

    # ---------------------------------------------------------------- etiketler

    def option(self, col: str, code: Any) -> Optional[str]:
        if code is None:
            return None
        return (self.options.get(col.lower()) or {}).get(str(int(code))) or str(code)

    def dim_label(self, dim: str, code: Any) -> Optional[str]:
        if code is None:
            return None
        if dim in DIMS:
            return self.option(DIMS[dim], code)
        if dim == "ajans":
            return "Ajans üzerinden" if code else "Doğrudan (ajanssız)"
        if dim == "satis":
            return SALES_TIERS.get(code, str(code))
        if dim == "hedef":
            return self.book_options.get(str(int(code))) or str(code)
        if dim == "dil":
            return {"yerli": "Yerli", "ceviri": "Çeviri"}.get(code, str(code))
        return str(code)

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
        extras = [d for d in cfg.dims if subject.dims.get(d) is not None and not (d == "satis" and not self.sales_known)]
        missing += [d for d in cfg.dims if d not in extras]
        use += extras
        year = subject.year
        years = cfg.years if year is not None else -1
        relaxed: list[str] = []
        steps = list(reversed(extras)) + list(RELAX)
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
                v, nominal = clause_value(self, c, subj)
                r = evaluate(c, v, w, own, cfg, subj, full=False, nominal=nominal)
                if r["status"] in DEVIATING:
                    devs.append({"key": c.key, "status": r["status"]})
                    by_clause[c.key] += 1
            specials = [c.key for c in TEXT_CLAUSES if e.texts.get(c.key)
                        and text_counts.get((c.key, e.idx), 0) == 0]
            sekil = [x["id"] for x in formal(self, subj) if not x["ok"]]
            rows.append({"e": e.idx, "devs": devs, "specials": specials, "sekil": sekil, "peers": crit["emsal"],
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
                    # dolu sayısı nominal değerden; dağılım kıyas değerinden (TL ise USD karşılığı, kuru yoksa girmez)
                    for e in members:
                        cur = e.dims.get("para")
                        if isinstance(e.values.get(c.key), (int, float)):
                            self.present_by_currency[(c.key, cur)] += 1
                            r = e.real.get(c.key)
                            if r is not None:
                                self.by_currency.setdefault((c.key, cur), []).append(r)
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


def evaluate(c: Clause, v: Any, w: Window, own: list[Entry], cfg: Cfg, subj: "Subject", *, full: bool = True,
             nominal: Any = None) -> dict[str, Any]:
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
        own_vals = [e.real.get(c.key) for e in own if e.dims.get("para") == cur and e.real.get(c.key) is not None]
        texts: Counter = Counter()
        if nominal is not None and v is None:          # TL tutar var ama başlangıç ayının kuru okunamadı
            return {"status": "kur-yok", "n": n, "dolu": present, "doluPay": _share(present, n), "sayisal": len(nums) - len(own_vals)}
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
    start: Optional[str] = None
    real: Optional[dict[str, Optional[float]]] = None
    meta: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def of_entry(cls, e: Entry) -> "Subject":
        return cls("crm", e.id, e.no, e.book or e.no, e.agreement, e.dims, e.year, e.values, e.texts, entry=e,
                   start=e.start, real=e.real, meta=e.meta)


def clause_value(port: "Portfolio", c: Clause, subj: Subject) -> tuple[Any, Any]:
    """(kıyas değeri, nominal değer): tutar maddesinde kıyas değeri TL için USD karşılığıdır."""
    v = subj.values.get(c.key)
    if c.kind != "tutar":
        return v, None
    if subj.real is None:
        subj.real = port.to_real(subj.values, subj.dims.get("para"), subj.start)
    return subj.real.get(c.key), v


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
    meta = {"kitapsay": len([b for b in terms.get("books") or [] if b.get("title")]),
            "ulkevar": 1 if str(terms.get("territory") or "").strip() else 0, "taraf": len(names)}
    return Subject(kind, key, no, str(terms.get("title") or no), agreement, dims, _year(terms.get("start")), values, texts,
                   party_ids=[i for i in ids if i], party_names=names, compared=compared, entry=crm_entry,
                   start=str(terms.get("start") or "")[:10] or None, meta=meta)


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

# ================================================================================ şekil denetimi

#: (kimlik, ad, dayanak). Hukuki görüş değildir: kaydın bu şartları taşıyıp taşımadığının denetimidir.
FORMAL = {
    "hak": ("Devredilen mali haklar tek tek işaretli",
            "FSEK md. 52: mali haklara ilişkin sözleşmede konusu olan haklar ayrı ayrı gösterilir; gösterilmeyen hak "
            "devredilmiş sayılmaz."),
    "sure": ("Süre belirtilmiş (yıl, bitiş ya da süresiz)", "Süresi yazılmayan devir ya da lisansın süresi yoruma kalır."),
    "baslangic": ("Başlangıç tarihi var", "Süre, telif dönemi ve yenileme başlangıç tarihinden hesaplanır."),
    "tarih": ("Tarihler tutarlı", "Bitiş başlangıçtan önce olamaz; başlangıç ileri bir yılda olamaz."),
    "taraf": ("Hak sahibi taraf olarak kayıtlı", "Karşı taraf CRM'de sözleşme tarafı olarak kayıtlı değilse hakediş ve "
                                                "bildirim kime yapılacağı belirsiz kalır."),
    "kitap": ("Sözleşmeye kitap bağlı", "Kitap bağı yoksa satış ve baskı sözleşmeye bağlanamaz."),
    "ucret": ("Ücret şartı kayıtlı", "Oran, tek ödeme, avans ya da hesaplama açıklaması yoksa ödemenin dayanağı görünmez."),
    "ulke": ("Lisans verilen ülke yazılı", "Telif satışında lisansın geçerli olduğu bölge belirtilmelidir."),
}
_MALI = ("new_cogaltmahakki", "new_yaymahakki", "new_islemehakki", "new_iletimhakki", "new_tamsilhakki", "new_isaretsesgoruntu")
_PAID = ("new_Telif", "new_sertkapaktelif", "new_e_kitap_telif", "new_SesliKitap", "new_yurtdisitelif", "new_TekdemeTutari",
         "new_sozlesmeavanstutari")


def formal(port: "Portfolio", subj: Subject) -> list[dict[str, Any]]:
    """Kaydın şekil denetimi (sözleşme tipine göre). Belgeden okunan şartlarda yapılmaz (belge her alanı taşımaz)."""
    if subj.kind == "belge":
        return []
    tip = subj.dims.get("tip")
    v = subj.values
    public = bool(v.get("new_KorumaDEser"))
    if tip == 5:
        ids = ["kitap", "baslangic", "tarih"] if public else ["hak", "sure", "baslangic", "tarih", "taraf", "kitap", "ucret"]
    elif tip == 1:
        ids = ["sure", "baslangic", "tarih", "taraf", "kitap", "ucret", "ulke"]
    else:
        ids = ["baslangic", "tarih", "taraf"]
    if subj.entry is not None:
        parties = len(port.parties_of.get(subj.agreement, []))
    else:
        parties = int(subj.meta.get("taraf") or len(subj.party_names))
    start, end = subj.start, (subj.entry.end if subj.entry is not None else None)
    now = datetime.now(timezone.utc).year
    out = []
    for i in ids:
        label, law = FORMAL[i]
        if i == "hak":
            ok, detail = any(v.get(k) for k in _MALI), "İşaretli mali hak yok."
        elif i == "sure":
            ok = bool((v.get("new_SozlesmeSuresiYil") or 0) > 0 or end or v.get("new_suresizsozlesme"))
            detail = "Süre yılı, bitiş tarihi ve «süresiz» işareti boş."
        elif i == "baslangic":
            ok, detail = bool(start), "Başlangıç tarihi boş."
        elif i == "tarih":
            bad_order = bool(start and end and end < start)
            bad_year = bool(subj.year and subj.year > now + 1)
            ok = not (bad_order or bad_year)
            detail = ("Bitiş başlangıçtan önce." if bad_order else f"Başlangıç yılı {subj.year}.") if not ok else ""
        elif i == "taraf":
            ok, detail = parties > 0, "Taraf kaydı yok."
        elif i == "kitap":
            n = subj.meta.get("kitapsay")
            ok, detail = (n is None) or int(n) > 0, "Bağlı kitap yok."
        elif i == "ucret":
            ok = any((v.get(k) or 0) for k in _PAID) or bool(subj.texts.get("new_hesaplamatutari"))
            detail = "Oran, tek ödeme, avans ve hesaplama açıklaması boş."
        else:
            ok, detail = bool(subj.meta.get("ulkevar")), "Ülke boş."
        out.append({"id": i, "label": label, "ok": ok, "detail": None if ok else detail, "law": law})
    return out


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
            v, nominal = clause_value(port, c, subj)
            r = evaluate(c, v, w, own, cfg, subj, full=True, nominal=nominal)
            scur = port.stat_currency(cur) if c.kind == "tutar" else cur
            shown = (port.money_label(c, nominal, v, cur, subj.start) if c.kind == "tutar" else port.show(c, v, cur))
            for x in r.get("enSik") or []:
                x["ad"] = "Boş" if x["deger"] is None else port.show(c, x["deger"], scur)
            for k in ("medyan", "p10", "p90", "enAz", "enCok"):
                if r.get(k) is not None:
                    r[k + "Ad"] = port.show(c, r[k], scur)
            counts[r["status"]] += 1
            item = {"key": c.key, "label": port.labels[c.key], "kind": c.kind, "value": v if c.kind != "tutar" else nominal,
                    "valueLabel": shown, "statusLabel": STATUS[r["status"]],
                    "reason": reason(c, r, port.show(c, v, scur), port, scur, cfg), **r}
            if c.kind == "tutar":
                item["kiyas"] = v                      # dağılımla aynı birimde (TL sözleşmede USD)
                item["kiyasBirim"] = port.option("new_sozlesmeparabirimi", scur) if scur is not None else None
            items.append(item)
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
    crit["kur"] = ("TL tutarlar sözleşmenin başladığı ayın TCMB döviz alış kuruyla dolara çevrilip kıyaslanır."
                   if cur == TRY_CODE else None)
    return {
        "criteria": crit,
        "groups": groups,
        "texts": texts,
        "sekil": formal(port, subj),
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


def timeline(port: Portfolio, subj: Subject) -> list[dict[str, Any]]:
    """Anlaşmanın olayları (başlangıç, bitiş, ek protokol, muvafakatname, fesih, yenileme…), kopyalarıyla, tarih sırasıyla."""
    group = port.by_agreement.get(subj.agreement, []) if subj.entry is not None else []
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, Any]] = []

    def add(day: Optional[str], what: str, no: Optional[str]) -> None:
        if not day or (day, what) in seen:
            return
        seen.add((day, what))
        out.append({"tarih": day[:10], "olay": what, "no": no})

    for e in group:
        add(e.start, "Başlangıç", e.no)
        add(e.end, "Bitiş", e.no)
        for col, day in (e.meta.get("olaylar") or {}).items():
            add(day, EVENT_COLS.get(col, col), e.no)
    if subj.entry is None:
        add(subj.start, "Başlangıç", subj.no)
    out.sort(key=lambda x: x["tarih"])
    return out


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
            "anlasma": [{"id": x.id, "no": x.no} for x in port.by_agreement.get(subj.agreement, []) if e is None or x.idx != e.idx],
            "olcutler": [{"id": d, "ad": DIM_LABELS[d], "deger": port.dim_label(d, subj.dims.get(d))} for d in EXTRA_DIMS]}


# ================================================================================ tarama listesi

Reviews = dict[tuple[str, str], dict[str, Any]]


def finding_reviews(e: Entry, r: dict[str, Any], reviews: Optional[Reviews]) -> dict[str, Optional[dict[str, Any]]]:
    """Bir tarama satırının bulguları (farklı madde, özgün not, şekil eksiği) ve incelemesi; anahtar inceleme anahtarı."""
    from semantic_bridge import contracts_compare_store as ST

    rv = reviews or {}
    out: dict[str, Optional[dict[str, Any]]] = {}
    for d in r["devs"]:
        out[d["key"]] = ST.attach(rv.get((e.agreement, d["key"])), ST.sig(e.values.get(d["key"])))
    for key in r["specials"]:
        out["not:" + key] = ST.attach(rv.get((e.agreement, "not:" + key)), ST.sig(e.texts.get(key)))
    for i in r.get("sekil") or []:
        out["sekil:" + i] = ST.attach(rv.get((e.agreement, "sekil:" + i)), ST.sig("eksik"))
    return out


def scan_rows(port: Portfolio, cfg: Cfg, *, q: str = "", tip: Optional[int] = None, odeme: Optional[int] = None,
              bolum: Optional[int] = None, yil_from: Optional[int] = None, yil_to: Optional[int] = None, only: str = "sapan",
              clause: str = "", aktif: bool = False, min_devs: int = 1, reviews: Optional[Reviews] = None,
              unreviewed: bool = False) -> list[tuple[dict[str, Any], Entry, dict[str, Any]]]:
    """Süzgece uyan tarama satırları, sıralı (en çok farklı maddesi olan üstte). Satır tavanı yok."""
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
        if only == "sekil" and not r.get("sekil"):
            continue
        if only == "hepsi-sapma" and not (r["devs"] or r["specials"] or r.get("sekil")):
            continue
        if k and k not in fold(" ".join([*e.nos, e.book, e.author])):
            continue
        rv = finding_reviews(e, r, reviews)
        if unreviewed and not any(x is None or x["open"] for x in rv.values()):
            continue
        rows.append((r, e, rv))
    rows.sort(key=lambda x: (-len(x[0]["devs"]), -len(x[0].get("sekil") or []), -len(x[0]["specials"]), -(x[1].year or 0),
                             _natural(x[1].no)))
    return rows


def scan_item(port: Portfolio, r: dict[str, Any], e: Entry, rv: dict[str, Optional[dict[str, Any]]]) -> dict[str, Any]:
    cur = e.dims.get("para")

    def value_label(key: str) -> str:
        c = BY_KEY[key]
        if c.kind == "tutar":
            return port.money_label(c, e.values.get(key), e.real.get(key), cur, e.start)
        return port.show(c, e.values.get(key), cur)

    def short(x: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
        return None if x is None else {k: x.get(k) for k in ("status", "statusLabel", "stale", "open", "owner", "by", "at")}

    return {
        "id": e.id, "no": e.no, "kopya": len(e.ids), "kitap": e.book, "yazar": e.author, "yil": e.year,
        "agreement": e.agreement,
        "tip": port.dim_label("tip", e.dims.get("tip")), "odeme": port.dim_label("odeme", e.dims.get("odeme")),
        "para": port.dim_label("para", cur), "bolum": port.dim_label("bolum", e.dims.get("bolum")),
        "durum": port.option("statuscode", e.status) if e.status is not None else None,
        "emsal": r["peers"], "gevsetilen": r["relaxed"], "yeterli": r["enough"],
        "sapmalar": [{"key": d["key"], "label": port.labels[d["key"]], "status": d["status"], "statusLabel": STATUS[d["status"]],
                      "valueLabel": value_label(d["key"]), "inceleme": short(rv.get(d["key"]))} for d in r["devs"]],
        "ozgunNotlar": [{"key": key, "label": port.labels[key], "inceleme": short(rv.get("not:" + key))} for key in r["specials"]],
        "sekilEksik": [{"id": i, "label": FORMAL[i][0], "inceleme": short(rv.get("sekil:" + i))} for i in r.get("sekil") or []],
        "acikBulgu": sum(1 for x in rv.values() if x is None or x["open"]),
    }


def scan_page(port: Portfolio, cfg: Cfg, *, page: int = 0, size: int = 50, **kw: Any) -> dict[str, Any]:
    """Tarama sonucu süzülür ve sayfalanır (toplam her zaman yazar; sessiz kesme yok)."""
    res = port.scan(cfg)
    rows = scan_rows(port, cfg, **kw)
    total = len(rows)
    size = max(1, min(int(size), 200))
    page = max(0, int(page))
    items = [scan_item(port, r, e, rv) for r, e, rv in rows[page * size:(page + 1) * size]]
    all_rows = res["rows"]
    return {
        "items": items, "total": total, "page": page, "pageSize": size,
        "ozet": {
            "sozlesme": port.contracts,
            "anlasma": len(port.reps),
            "sapan": sum(1 for r in all_rows if r["devs"]),
            "ozgun": sum(1 for r in all_rows if r["specials"]),
            "sekil": sum(1 for r in all_rows if r.get("sekil")),
            "emsalYetersiz": sum(1 for r in all_rows if not r["enough"]),
        },
        "maddeler": [{"key": key, "label": port.labels[key], "sayi": n}
                     for key, n in sorted(res["byClause"].items(), key=lambda x: (-x[1], x[0]))],
        "sekilSayim": [{"id": i, "label": FORMAL[i][0], "sayi": n}
                       for i, n in sorted(Counter(x for r in all_rows for x in r.get("sekil") or []).items(), key=lambda x: -x[1])],
        "hesapMs": res["ms"],
    }


def scan_csv(port: Portfolio, cfg: Cfg, **kw: Any) -> str:
    """Süzgece uyan bütün satırlar (sayfa yok) CSV olarak; Excel eşi ortak katmandan (`bicim=xlsx`)."""
    import csv
    import io

    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Sözleşme no", "Kitap", "Yazar", "Başlangıç yılı", "Sözleşme tipi", "Ödeme türü", "Para birimi", "Bölüm",
                "Durum", "Emsal sayısı", "Gevşetilen ölçüt", "Farklı madde sayısı", "Farklı maddeler", "Özgün notlar",
                "Şekil eksikleri", "Açık bulgu", "İncelemeler"])
    for r, e, rv in scan_rows(port, cfg, **kw):
        it = scan_item(port, r, e, rv)
        notes = []
        for key, x in rv.items():
            if x is not None:
                notes.append(f"{key}: {x['statusLabel']}{' (eski değere ait)' if x['stale'] else ''}"
                             + (f" — {x['note']}" if x.get("note") else "") + (f" [{x['owner']}]" if x.get("owner") else ""))
        w.writerow([" / ".join(e.nos), e.book, e.author, e.year or "", it["tip"] or "", it["odeme"] or "", it["para"] or "",
                    it["bolum"] or "", it["durum"] or "", it["emsal"], ", ".join(it["gevsetilen"]), len(it["sapmalar"]),
                    " | ".join(f"{d['label']}: {d['valueLabel']} ({d['statusLabel']})" for d in it["sapmalar"]),
                    ", ".join(n["label"] for n in it["ozgunNotlar"]), ", ".join(x["label"] for x in it["sekilEksik"]),
                    it["acikBulgu"], " | ".join(notes)])
    return "\ufeff" + buf.getvalue()


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
