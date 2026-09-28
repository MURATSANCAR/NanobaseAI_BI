"""M44 Lojistik ve kargo: CRM ve Logo okumaları (yalnız okuma).

SQL metinleri `shipping_sql/` altındadır (bir dosya bir sorgu ya da bir WHERE parçası). Dosyadaki `--` açıklama satırları
yüklenirken atılır, yer tutucular (`{p}`, `{f}`, `{kosul}` …) yalnız burada doğrulanmış değerlerle doldurulur ve her SQL
çalışmadan önce `guard()`'dan geçer.

Kaynaklar (analiz: `docs/analiz/kullanici-ihtiyaclari/M44-lojistik-kargo.md` §6, §13):

- **Sipariş aşamaları** CRM `new_siparisBase`: sipariş, depoda bekliyor, pusula, kutulandı, sevk, tamamlandı tarihleri;
  kargo firması (`new_kargofirmasiid`), takip no ve adresi, etiket, koli adedi, dört firmanın (Aras, UPS, MNG, Akademi)
  entegrasyon sonucu ve mesajı. Teslimat adresinden yalnız il adı okunur.
- **Kargo firmasının gönderi kaydı** CRM `new_kargobilgisiBase` (Kural C19): bütün kolonlar metin, ondalık virgüllü;
  sayı `x.replace(',', '.')` ile okunur (`TRY_CAST(REPLACE(x, ',', '.') AS FLOAT)` ile aynı anlam), tarih ayardaki
  biçimlerle (`SHIPPING_CARGO_DATE_FORMATS`, ölçülecek). Okunamayan değer sayılır ve ekranda yazılır, tahmin edilmez.
- **Takip bilgisi** `new_kargotakipbilgisiBase` ve **sevkiyat** `new_sevkiyatBase` siparişe kimlikle bağlıdır.
- **Gerçekleşen sevk** Logo `STLINE` TRCODE 7,8 IOCODE 4 (Kural 10); kargo faturası Logo alınan hizmet faturası (TRCODE 4),
  kargo carileri ayardan (insan onaylı eşleme).

**Kimlik bilgisi yasağı:** CRM `new_kargofirmasiBase`'in kullanıcı adı, parola, token, istemci kimliği/sırrı ve UPS hesap
kolonları hiçbir sorguda geçmez. Kolonlar tek tek adıyla seçilir (`SELECT *` yok); `guard()` yasak kolon adı ya da
`SELECT *` geçen SQL'i çalıştırmadan durdurur.

**Kargo kaydı ↔ sipariş eşlemesi** M51 müşteri hizmetlerinin de işidir (`SUPPORT_CARGO_MATCH`). Burada yalnız takip
numarasıyla doğrudan eşleme vardır (`match_by_tracking`); M51 main'e girince kendi eşleyicisini
`register_cargo_matcher(...)` ile bağlar ve iki modül aynı mantığı kullanır (kopya yok).
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Optional
from zoneinfo import ZoneInfo

from semantic_bridge import budget_sources as bsrc
from semantic_bridge.field_sales_sources import prefix

log = logging.getLogger("semantic.shipping.sources")

TZ = ZoneInfo("Europe/Istanbul")
SQL_DIR = Path(__file__).with_name("shipping_sql")

SourceError = bsrc.SourceError
Runner = bsrc.Runner
runner = bsrc.runner
firms_by_year = bsrc.firms_by_year

#: Hiçbir sorguda geçmeyecek kolonlar (kargo firması kimlik bilgileri ve gönderici hesabı). Küçük harfle karşılaştırılır.
FORBIDDEN_COLUMNS = (
    "new_kullaniciadi", "new_sifre", "new_token", "new_tokenexpirationdate", "new_clientid", "new_clientsecret",
    "new_ups_shipperaccountnumber", "new_ups_shippername", "new_ups_shippercontactname", "new_ups_shipperaddress",
    "new_ups_shipperphonenumber", "new_ups_shippershoneextension", "new_ups_shippermobilephonenumber", "new_ups_shipperemail",
    "new_ups_shipperexpensecode",
)
#: Kargo kaydının kişisel kolonları: yalnız `ozellik:kargo.alici` olan kişinin gönderi kartında, tek kayıt için okunur.
PERSONAL_COLUMNS = ", b.new_alici AS alici, b.new_TeslimAlan AS teslim_alan"

#: CRM sipariş durumu (Kural C13).
ORDER_STATUS = {
    1: "Taslak", 2: "Etkin değil", 100000000: "Sevk edildi", 100000001: "İptal", 100000002: "Sipariş", 100000003: "Birleştirildi",
    100000004: "Risk limit onayı bekliyor", 100000005: "Pazarlama bütçesi onayı bekliyor", 100000011: "Depoda bekliyor",
    100000012: "Pusula alındı, toplanıyor", 100000013: "Kutulanıyor", 100000014: "Kutulandı", 100000015: "Tamamlandı",
    100000016: "Risk bilgisi bekleniyor",
}
ORDER_TYPE = {1: "B2B", 2: "Dağılım", 3: "Standart", 4: "Fuar", 5: "Etkinlik", 6: "Telif", 7: "Market", 8: "B2C", 9: "Pazar yeri",
              10: "Okul örneği", 11: "Öğretmen örneği", 12: "Tanıtım gönderimi", 13: "Okul satışı", 14: "Amazon konsinye",
              15: "Bağış", 16: "İmza siparişi", 17: "Kırmızı / Mor"}
SHIPMENT_KIND = {1: "Üretimden giriş", 2: "Faturalı kabul", 4: "İade", 5: "Raf transferi", 6: "Depolar arası sevk",
                 7: "İrsaliye", 8: "Sayım eksiği"}
PAYMENT = {1: "Gönderici öder", 2: "Alıcı öder"}
#: Entegrasyon alanı öneki → ekranda firma adı.
INTEGRATIONS = (("aras", "Aras"), ("ups", "UPS"), ("mng", "MNG"), ("akademi", "Akademi"))
#: Durum grupları (sipariş listesi süzgeci).
STATUS_GROUPS = {"depoda": (100000011, 100000012, 100000013), "kutulandi": (100000014,)}
#: Entegrasyon hatası sayılmayan durumlar: iptal, birleştirildi, etkin değil, taslak.
ERROR_EXCLUDED = (100000001, 100000003, 2, 1)

_INT = re.compile(r"^-?\d{1,12}$")
_GUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_SEARCH = re.compile(r"^[0-9A-Za-zÇĞİÖŞÜçğıöşüÂâÎîÛû .,'\-_/#&()]{2,80}$")
_CODE = re.compile(r"^[0-9A-Za-zÇĞİÖŞÜçğıöşü .\-_/]{1,40}$")
_HINT = re.compile(r"^[0-9A-Za-zÇĞİÖŞÜçğıöşü .\-&]{2,40}$")


# ------------------------------------------------------------------ SQL dosyaları ve koruma


def guard(sql: str) -> str:
    """Yasak kolon ya da `SELECT *` geçen SQL'i çalıştırmadan durdurur (seçim, koşul ya da sıralama fark etmez)."""
    low = sql.lower()
    for col in FORBIDDEN_COLUMNS:
        if re.search(rf"(?<![a-z0-9_]){re.escape(col)}(?![a-z0-9_])", low):
            raise SourceError("Bu sorgu kargo firmasının kimlik bilgisi kolonuna dokunuyor; çalıştırılmadı.")
    if re.search(r"select\s+(top\s+\d+\s+)?(\w+\.)?\*", low):
        raise SourceError("Kolonlar adıyla seçilmeli; «SELECT *» çalıştırılmadı.")
    return sql


def sql_text(name: str) -> str:
    """Dosyanın SQL'i; `--` açıklama satırları atılır (açıklamadaki yer tutucu doldurulup koda dönüşmesin)."""
    path = SQL_DIR / f"{name}.sql"
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if not ln.lstrip().startswith("--")]
    return "\n".join(lines).strip()


def sql(name: str, **kw: Any) -> str:
    return guard(sql_text(name).format(**kw))


def all_sql_files() -> list[Path]:
    return sorted(SQL_DIR.glob("*.sql"))


# ------------------------------------------------------------------ değer güvenliği


def q(v: Any) -> str:
    return "N'" + str(v).replace("'", "''") + "'"


def ints(values: Iterable[Any]) -> str:
    out = []
    for v in values:
        s = str(v).strip()
        if not _INT.match(s):
            raise SourceError("Durum/tip kodu geçersiz.")
        out.append(str(int(s)))
    if not out:
        raise SourceError("Kod listesi boş.")
    return ", ".join(out)


def guid(v: Any) -> str:
    s = str(v or "").strip().strip("{}")
    if not _GUID.match(s):
        raise SourceError("Kayıt kimliği geçersiz.")
    return s.lower()


def guids(values: Iterable[Any]) -> str:
    out = sorted({guid(v) for v in values if v})
    if not out:
        raise SourceError("Kimlik listesi boş.")
    return ", ".join(f"'{g}'" for g in out)


def search_text(v: str) -> str:
    s = re.sub(r"\s+", " ", (v or "").strip())
    if not _SEARCH.match(s):
        raise SourceError("Arama metni 2–80 karakter olmalı; harf, rakam ve . , ' - _ / # & ( ) kullanılabilir.")
    return s.replace("'", "''")


def like_text(s: str) -> str:
    """`search_text` çıktısını LIKE için kaçışlar (köşeli parantez, yüzde, alt çizgi harf olarak aranır)."""
    return s.replace("[", "[[]").replace("%", "[%]").replace("_", "[_]")


def code_text(v: str) -> str:
    s = (v or "").strip()
    if not _CODE.match(s):
        raise SourceError(f"Cari kodu «{v}» geçersiz.")
    return s.replace("'", "''")


def texts(values: Iterable[Any], limit: int = 60, unicode: bool = True) -> str:
    out = []
    pre = "N'" if unicode else "'"
    for v in values:
        s = re.sub(r"\s+", " ", str(v or "")).strip()
        if s and len(s) <= limit:
            out.append(pre + s.replace("'", "''") + "'")
    if not out:
        raise SourceError("Değer listesi boş.")
    return ", ".join(sorted(set(out)))


def firm(f: Any) -> str:
    s = str(f or "")
    if not re.match(r"^[0-9]{3}$", s):
        raise SourceError("Logo firma numarası geçersiz.")
    return s


def utc_bound(d: date) -> str:
    """İstanbul gününün başlangıcı UTC olarak (CRM tarihleri UTC saklanır)."""
    start = datetime(d.year, d.month, d.day, tzinfo=TZ).astimezone(timezone.utc)
    return start.strftime("%Y-%m-%d %H:%M:%S")


# ------------------------------------------------------------------ metin → sayı / tarih (Kural C19)


def cargo_number(v: Any) -> Optional[float]:
    """Kargo kaydındaki metin sayı: ondalık virgül noktaya çevrilir; okunamazsa None (SQL'deki TRY_CAST ile aynı)."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v) if v == v else None
    s = str(v).strip().replace(",", ".")
    if not s:
        return None
    try:
        n = float(s)
    except ValueError:
        return None
    return n if n == n and abs(n) != float("inf") else None


def cargo_date(v: Any, formats: Iterable[str]) -> Optional[date]:
    """Kargo kaydındaki metin tarih: ayardaki biçimlerle sırayla denenir. 1900 ve öncesi boş sayılır."""
    if v is None:
        return None
    if isinstance(v, datetime):
        d = v.date()
    elif isinstance(v, date):
        d = v
    else:
        s = re.sub(r"\s+", " ", str(v)).strip()
        if not s:
            return None
        d = None
        for fmt in formats:
            try:
                d = datetime.strptime(s, fmt).date()
                break
            except ValueError:
                continue
        if d is None:
            return None
    return d if d.year > 1900 else None


def crm_day(v: Any) -> Optional[date]:
    """CRM tarih kolonu (UTC) → İstanbul günü. 1900 ve öncesi boş."""
    if v is None or v == "":
        return None
    if isinstance(v, str):
        s = v.strip().replace(" ", "T", 1).replace("Z", "+00:00")
        try:
            v = datetime.fromisoformat(s) if len(s) > 10 else date.fromisoformat(s[:10])
        except ValueError:
            return None
    if isinstance(v, datetime):
        v = (v.replace(tzinfo=timezone.utc) if v.tzinfo is None else v).astimezone(TZ).date()
    if not isinstance(v, date) or v.year < 1901:
        return None
    return v


def logo_day(v: Any) -> Optional[date]:
    """Logo tarihi (saatsiz, yerel) → gün. 1900 ve öncesi Logo'nun boş değeridir."""
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        v = v.date()
    elif isinstance(v, str):
        try:
            v = date.fromisoformat(v.strip()[:10])
        except ValueError:
            return None
    return v if isinstance(v, date) and v.year > 1900 else None


def crm_time(v: Any) -> Optional[str]:
    """CRM tarih-saat (UTC) → İstanbul ISO (dakikaya kadar)."""
    if v is None or v == "":
        return None
    if isinstance(v, str):
        try:
            v = datetime.fromisoformat(v.strip().replace(" ", "T", 1).replace("Z", "+00:00"))
        except ValueError:
            return None
    if isinstance(v, datetime):
        if v.year < 1901:
            return None
        return (v.replace(tzinfo=timezone.utc) if v.tzinfo is None else v).astimezone(TZ).strftime("%Y-%m-%dT%H:%M")
    if isinstance(v, date):
        return v.isoformat() if v.year > 1900 else None
    return None


def clean(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = re.sub(r"\s+", " ", str(v)).strip()
    return s or None


def lower_keys(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{str(k).lower(): v for k, v in r.items()} for r in rows]


# ------------------------------------------------------------------ CRM okumaları


def order_sql(schema: str, kosul: str, sira: str = "ORDER BY s.new_siparistarihi DESC, s.new_name DESC", sayfa: str = "") -> str:
    return sql("crm_siparis_asama", p=prefix(schema), kosul=kosul, sira=sira, sayfa=sayfa)


def errors_where(since: date, excluded: Iterable[int] = ERROR_EXCLUDED) -> str:
    return sql_text("crm_entegrasyon_hata").format(haric=ints(excluded), bas=since.isoformat())


def untracked_where(since: date, statuses: Iterable[int], exclude_types: Iterable[int] = ()) -> str:
    ex = list(exclude_types)
    tip = f"\nAND ISNULL(CAST(s.new_siparistipi AS int), 0) NOT IN ({ints(ex)})" if ex else ""
    return sql_text("crm_takipsiz_sevk").format(durumlar=ints(statuses), bas=since.isoformat(), tip_haric=tip)


def boxed_where() -> str:
    return sql_text("crm_kutulandi_bekleyen")


def search_where(q_: str) -> str:
    """Tek arama: sipariş no (B2C ve dış no dahil), takip no (sipariş ya da takip kaydı), sevkiyat fatura no, müşteri
    ünvanı ya da cari kodu."""
    s = search_text(q_)
    like = f"N'%{like_text(s)}%'"
    exact = f"N'{s}'"
    return ("(" + " OR ".join([
        f"s.new_name = {exact}", f"s.new_b2csiparisnumarasi = {exact}", f"s.new_yenib2csiparisnumarasi = {exact}",
        f"s.new_dissiparisno = {exact}", f"s.new_kargotakipno = {exact}", f"a.new_CariKodu = {exact}",
        f"a.Name LIKE {like}",
        "EXISTS (SELECT 1 FROM {p}new_kargotakipbilgisiBase k WHERE k.new_siparisid = s.new_siparisId AND k.statecode = 0"
        f" AND (k.new_kargotakipnumarasi = {exact} OR k.new_name = {exact}))",
        "EXISTS (SELECT 1 FROM {p}new_sevkiyatBase v WHERE v.new_siparisid = s.new_siparisId AND v.statecode = 0"
        f" AND v.new_faturanumarasi = {exact})",
    ]) + ")")


def read_orders(run: Runner, schema: str, kosul: str, *, sira: Optional[str] = None, offset: int = 0,
                size: Optional[int] = None) -> list[dict[str, Any]]:
    """Sipariş satırları. `size` verilirse sayfalı (`size + 1` satır okunur; fazlası «devamı var» demektir)."""
    p = prefix(schema)
    page = ""
    if size is not None:
        page = f"\nOFFSET {max(0, int(offset))} ROWS FETCH NEXT {max(1, int(size)) + 1} ROWS ONLY"
    kw = {"sira": sira} if sira else {}
    return lower_keys(run(order_sql(schema, kosul.replace("{p}", p), sayfa=page, **kw)))


def read_shipped_count(run: Runner, schema: str, since: date, today: date, statuses: Iterable[int]) -> dict[str, int]:
    rows = lower_keys(run(sql("crm_sevk_sayisi", p=prefix(schema), durumlar=ints(statuses), bas=utc_bound(since),
                              bugun_utc=utc_bound(today))))
    r = rows[0] if rows else {}
    return {"adet": int(r.get("adet") or 0), "bugun": int(r.get("bugun") or 0)}


def read_carriers(run: Runner, schema: str) -> dict[str, dict[str, Any]]:
    """Kargo firması kimliği → {ad, kod}. Yalnız üç kolon (bkz. FORBIDDEN_COLUMNS)."""
    out = {}
    for r in lower_keys(run(sql("crm_kargo_firma", p=prefix(schema)))):
        if r.get("id"):
            out[str(r["id"]).lower().strip("{}")] = {"ad": clean(r.get("ad")), "kod": clean(r.get("kod"))}
    return out


def read_tracking(run: Runner, schema: str, order_ids: Iterable[str]) -> list[dict[str, Any]]:
    ids = [i for i in order_ids if i]
    if not ids:
        return []
    return lower_keys(run(sql("crm_kargo_takip", p=prefix(schema), siparisler=guids(ids))))


def read_shipments(run: Runner, schema: str, order_ids: Iterable[str]) -> list[dict[str, Any]]:
    ids = [i for i in order_ids if i]
    if not ids:
        return []
    return lower_keys(run(sql("crm_sevkiyat", p=prefix(schema), siparisler=guids(ids))))


def read_cargo_rows(run: Runner, schema: str) -> list[dict[str, Any]]:
    """Bütün etkin kargo kayıtları (13.242 kayıt, 2026-09; kişisel kolonsuz). Sayı ve tarih çevrimi çağıranda."""
    return lower_keys(run(sql("crm_kargo_bilgisi", p=prefix(schema), kisisel="", kosul="")))


def read_cargo_personal(run: Runner, schema: str, ids: Iterable[str]) -> dict[str, dict[str, Any]]:
    """Tek gönderinin alıcı ve teslim alan adı (yalnız `ozellik:kargo.alici`)."""
    idl = [i for i in ids if i]
    if not idl:
        return {}
    rows = lower_keys(run(sql("crm_kargo_bilgisi", p=prefix(schema), kisisel=PERSONAL_COLUMNS,
                              kosul=f" AND b.new_kargobilgisiId IN ({guids(idl)})")))
    return {str(r["id"]).lower().strip("{}"): {"alici": clean(r.get("alici")), "teslimAlan": clean(r.get("teslim_alan"))} for r in rows}


def read_crm_month_shipments(run: Runner, schema: str, start: date, end: date) -> list[dict[str, Any]]:
    return lower_keys(run(sql("crm_sevkiyat_ay", p=prefix(schema), bas_utc=utc_bound(start), bit_utc=utc_bound(end))))


# ------------------------------------------------------------------ Logo okumaları


def firm_for(firms: dict[int, str], year: int) -> str:
    f = firms.get(year)
    if not f:
        raise SourceError(f"Logo'da {year} yılının dönemi yok.")
    return firm(f)


def read_logo_shipments(run: Runner, f: str, start: date, end: date) -> list[dict[str, Any]]:
    return lower_keys(run(sql("logo_sevk", f=firm(f), bas=start.isoformat(), bit=end.isoformat())))


def read_logo_invoices_by_no(run: Runner, f: str, numbers: Iterable[str]) -> list[dict[str, Any]]:
    nums = [n for n in numbers if n]
    if not nums:
        return []
    return lower_keys(run(sql("logo_fatura_no", f=firm(f), numaralar=texts(nums, 40, unicode=False))))


def read_carrier_invoices(run: Runner, f: str, codes: Iterable[str], start: date, end: date) -> list[dict[str, Any]]:
    cl = [c for c in codes if c]
    if not cl:
        return []
    cariler = ", ".join(sorted({f"'{code_text(c)}'" for c in cl}))
    return lower_keys(run(sql("logo_kargo_fatura", f=firm(f), cariler=cariler, bas=start.isoformat(), bit=end.isoformat())))


def read_carrier_candidates(run: Runner, f: str, hints: Iterable[str], since: date) -> list[dict[str, Any]]:
    words = sorted({h.strip().upper() for h in hints if h and _HINT.match(h.strip())})
    if not words:
        return []
    kosul = " OR ".join(f"UPPER(C.DEFINITION_) LIKE '%{w.replace(chr(39), chr(39) * 2)}%'" for w in words)
    return lower_keys(run(sql("logo_kargo_cari_aday", f=firm(f), bas=since.isoformat(), kosul=kosul)))


def read_data_end(run: Runner, firms: dict[int, str]) -> Optional[date]:
    try:
        return bsrc.read_data_end(run, firms)
    except SourceError:
        return None


# ------------------------------------------------------------------ kargo kaydı ↔ sipariş (bağlantı noktası)

#: fn(order, tracking_rows, index) → sipariş için kargo kayıtları. `index` = `CargoIndex`.
CargoMatcher = Callable[[dict[str, Any], list[dict[str, Any]], Any], list[dict[str, Any]]]
_matcher: dict[str, Any] = {"fn": None, "label": "Takip numarasıyla"}


def normal_key(v: Any) -> Optional[str]:
    s = re.sub(r"\s+", "", str(v or "")).upper()
    return s or None


def match_by_tracking(order: dict[str, Any], tracking: list[dict[str, Any]], index: Any) -> list[dict[str, Any]]:
    """Varsayılan: siparişin ve takip kayıtlarının takip numaraları kargo kaydının takip numarasıyla birebir."""
    keys = {normal_key(order.get("takip_no"))} | {normal_key(t.get("takip_no")) for t in tracking}
    seen, out = set(), []
    for k in keys:
        for row in index.by_tracking.get(k, []) if k else []:
            if row["id"] not in seen:
                seen.add(row["id"])
                out.append(row)
    return out


def register_cargo_matcher(fn: Optional[CargoMatcher], label: str = "") -> None:
    """M51 (müşteri hizmetleri) eşleyicisi main'e girince app.py buradan bağlar; iki modül aynı eşlemeyi kullanır."""
    _matcher["fn"] = fn
    _matcher["label"] = label or ("Müşteri hizmetleri eşlemesi" if fn else "Takip numarasıyla")


def cargo_matcher() -> tuple[CargoMatcher, str]:
    return (_matcher["fn"] or match_by_tracking), _matcher["label"]
