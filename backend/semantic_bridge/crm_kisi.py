"""Portal hesabı → CRM kullanıcısı eşlemesi, saklanmış (hız 2. tur, 2026-09-29).

Neden: kategori ağacı (`categories_api.me_crm`) ve Masam › Görevlerim (`app.py` `_asg_me`) ekranı açan kişinin CRM
kullanıcısını istek anında canlı CRM'den okuyordu (`editorial_assign.crm_me`: kişi başına `SystemUserBase` üstünde
baştan `%` ile başlayan LIKE — bütün tabloyu tarar). Bir ekranı ilk kez açan kişi bu okumayı bekliyordu.

Şimdi: CRM kullanıcılarının hepsi **tek sorguda** okunur (`all_users_sql`), portal tablosuna (`semantic_crm_kisi`,
kiracı başına tek satır) ve süreç belleğine yazılır; kişi bellekten bulunur. Okuma gece eşitlemesinde
(`timas-categories.timer` → `categories_api.sync`) yapılır; gündüz eşleme `TAZE` saniyeden (varsayılan 600 — eski kişi
belleğinin süresi) eskiyse bir kişi baktığında eldeki değer hemen döner, okuma arkada bir kez tekrarlanır (herkes için tek
sorgu). Hiç okuma yokken ilk bakan bekler (tek sorgu — eski kişi sorgusuyla aynı tablo taraması).

Kural `editorial_assign.crm_me` ile birebir: `me_sql`'in süzgeci (`LOWER(DomainName) LIKE N'%\\<hesap>'` ya da
`LIKE N'<hesap>@%'`) burada SQL Server'ın kendi `LOWER` çıktısı (`DomainNameLower`) üstünde aynı biçimde uygulanır —
Türkçe harmanlamada `I` → `ı` gibi farklar eskisiyle aynı sonuç verir —, satır seçimi `crm_me_from_rows` (eski
fonksiyonun kendisi). Pasif kullanıcılar da okunur: eski kural etkin satır yoksa pasif olanı döndürüyordu. Tek bilinen
fark: aynı hesaba birden çok etkin CRM kullanıcısı düşerse eski sorgunun sırası belirsizdi, burada `SystemUserId`
sırası (kabul betiği bu durumu ayrıca listeler). ASCII dışı, 80 karakterden uzun ya da baş/son boşluklu hesap adı
eşlemeye sorulmaz (`Bilinmiyor`): çağıran eski canlı yola döner.

Rakam üretmez; okuması ekranın sorgu bilgisine girmez (`sorgu_izi.disarida`). CRM'e yazılmaz.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Optional

import sqlalchemy as sa

from semantic_bridge import sorgu_izi as IZ
from semantic_bridge.editorial import _prefix, _s

log = logging.getLogger("semantic.crm_kisi")

_md = sa.MetaData()

OKUMA = sa.Table(
    "semantic_crm_kisi", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("okundu_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("satir", sa.Integer, nullable=False),
    sa.Column("sure_ms", sa.Integer),
    sa.Column("sql_text", sa.Text),
    sa.Column("rows_json", sa.Text, nullable=False),   # [{SystemUserId, FullName, IsDisabled, DomainName, DomainNameLower}]
)

#: Eşleme bu kadar saniyeden eskiyse bakıldığında arkada yeniden okunur (beklenmez).
TAZE = float(os.environ.get("CRM_KISI_TAZE_SN", "600"))
#: Süreç belleği tabloya en çok bu aralıkla bakar (gece turu ya da başka süreç yeni okuma yazdıysa alınır).
KONTROL = 60.0

Okuyucu = Callable[[], "tuple[str, Callable[[str], list[dict[str, Any]]]]"]


class Bilinmiyor(LookupError):
    """Saklanmış eşleme bu kişi için cevap veremez: çağıran eski yola (kişi başına canlı okuma) döner."""


_ready: set[int] = set()
_ready_lock = threading.Lock()


def ensure(engine: sa.engine.Engine) -> None:
    with _ready_lock:
        if id(engine) in _ready:
            return
        from semantic_layer.store import schema_stamp
        schema_stamp.create_all(_md, engine)   # sürüm damgası: tanım değişmediyse açılışta veritabanına sorulmaz
        _ready.add(id(engine))


# ------------------------------------------------------------------ kural


def all_users_sql(schema: str) -> str:
    """Bütün CRM kullanıcıları tek sorguda. `LOWER` SQL Server'da (harmanlama eski süzgeçle aynı olsun diye)."""
    p = _prefix(schema)
    return (f"SELECT SystemUserId, FullName, IsDisabled, DomainName, LOWER(DomainName) AS DomainNameLower"
            f" FROM {p}SystemUserBase WHERE DomainName IS NOT NULL AND DomainName <> '' ORDER BY SystemUserId")


def _true(v: Any) -> bool:
    return str(v).strip().lower() in ("1", "true", "evet")


def _norm(r: dict[str, Any]) -> dict[str, Any]:
    """Satır JSON'a yazılabilir biçimde; `crm_me_from_rows`'un okuduğu değerler aynı kalır (`_s`, `_is_true`)."""
    dn = r.get("DomainName")
    low = r.get("DomainNameLower")
    return {"SystemUserId": _s(r.get("SystemUserId")), "FullName": _s(r.get("FullName")),
            "IsDisabled": _true(r.get("IsDisabled")), "DomainName": None if dn is None else str(dn),
            "DomainNameLower": "" if low is None else str(low)}


def hesap_kismi(domain_name: Any) -> str:
    """`crm_me`'nin karşılaştırdığı hesap kısmı (`TIMAS\\ad` ya da `ad@alan` → `ad`)."""
    return ((_s(domain_name) or "").rsplit("\\", 1)[-1].split("@", 1)[0]).lower()


def _like_tutar(row: dict[str, Any], username: str) -> bool:
    """`me_sql` süzgeci: `_like(username.lower())` (baş/son boşluk atılır, en çok 80 karakter; kaçışlar yalnız SQL
    için) ve SQL Server LIKE'ın eşlenen ifadenin sonundaki boşlukları saymaması."""
    u = username.lower().strip()[:80]
    d = (row.get("DomainNameLower") or "").rstrip(" ")
    return d.endswith("\\" + u) or d.startswith(u + "@")


def uygun(username: str) -> bool:
    """Eşleme bu hesap adını eskisiyle birebir cevaplayabilir mi (aksi hâlde canlı yol)."""
    u = username or ""
    return bool(u.strip()) and u == u.strip() and u.isascii() and len(u) <= 80


def dizin_kur(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Hesap kısmı → o hesaba düşen satırlar (okunma sırasıyla)."""
    out: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        out.setdefault(hesap_kismi(r.get("DomainName")), []).append(r)
    return out


def eslestir(dizin: dict[str, list[dict[str, Any]]], username: str) -> Optional[dict[str, Any]]:
    """Kişinin CRM kullanıcısı ({id, name, disabled}) ya da None — `crm_me` ile aynı sonuç."""
    from semantic_bridge import editorial_assign as M2

    if not uygun(username):
        raise Bilinmiyor(username)
    acct = username.strip().lower()
    rows = [r for r in dizin.get(acct, []) if _like_tutar(r, username)]
    return M2.crm_me_from_rows(rows, username)


# ------------------------------------------------------------------ okuma ve bellek


class _Durum:
    def __init__(self) -> None:
        self.dizin: Optional[dict[str, list[dict[str, Any]]]] = None
        self.at = 0.0            # okumanın zamanı (epoch)
        self.bakildi = -1e18     # tabloya son bakış (monotonic)
        self.kilit = threading.Lock()      # okuma: aynı anda tek
        self.arkada = False


_durumlar: dict[tuple[int, str], _Durum] = {}
_durum_kilit = threading.Lock()


def _durum(engine: sa.engine.Engine, tenant: str) -> _Durum:
    with _durum_kilit:
        return _durumlar.setdefault((id(engine), tenant), _Durum())


def sifirla() -> None:
    """Süreç belleğini boşaltır (testlerde köprünün yeniden kalkışı)."""
    with _durum_kilit:
        _durumlar.clear()


def _aware(v: datetime) -> datetime:
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


def oku(engine: sa.engine.Engine, tenant: str, okuyucu: Okuyucu) -> dict[str, Any]:
    """CRM'den bütün kullanıcıları okur, tabloya ve belleğe yazar. Aynı anda ikinci okuma başlamaz; bekleyen, biten
    okumanın sonucunu alır. CRM okunamazsa hata yükselir (eldeki eşleme kalır)."""
    ensure(engine)
    d = _durum(engine, tenant)
    istek = time.time()
    with d.kilit:
        if d.dizin is not None and d.at >= istek:      # beklerken başkası okudu
            return {"satir": sum(len(v) for v in d.dizin.values()), "at": d.at, "ayni": True}
        schema, run = okuyucu()
        sql = all_users_sql(schema)
        t0 = time.monotonic()
        with IZ.disarida():
            rows = [_norm(r) for r in run(sql)]
        ms = int((time.monotonic() - t0) * 1000)
        now = datetime.now(timezone.utc)
        try:
            with IZ.disarida(), engine.begin() as c:
                c.execute(OKUMA.delete().where(OKUMA.c.tenant_id == tenant))
                c.execute(OKUMA.insert().values(tenant_id=tenant, okundu_at=now, satir=len(rows), sure_ms=ms,
                                                sql_text=sql, rows_json=json.dumps(rows, ensure_ascii=False)))
        except Exception as e:  # noqa: BLE001 — yazılamazsa bellekte kalır
            log.warning("crm kişi eşlemesi portal tablosuna yazılamadı: %s", e)
        d.dizin, d.at, d.bakildi = dizin_kur(rows), now.timestamp(), time.monotonic()
        return {"satir": len(rows), "ms": ms, "at": d.at}


def _arkada_oku(engine: sa.engine.Engine, tenant: str, okuyucu: Okuyucu) -> None:
    d = _durum(engine, tenant)
    with _durum_kilit:
        if d.arkada:
            return
        d.arkada = True

    def run() -> None:
        try:
            oku(engine, tenant, okuyucu)
        except Exception as e:  # noqa: BLE001 — eldeki eşleme kalır
            log.info("crm kişi eşlemesi arkada yenilenemedi: %s", e)
        finally:
            d.arkada = False

    threading.Thread(target=run, name="crm-kisi", daemon=True).start()


def _yukle(engine: sa.engine.Engine, tenant: str, d: _Durum) -> None:
    """Bellek → tablo (en çok `KONTROL` saniyede bir; tabloda daha yeni okuma varsa alınır)."""
    if d.dizin is not None and time.monotonic() - d.bakildi < KONTROL:
        return
    ensure(engine)
    try:
        with IZ.disarida(), engine.connect() as c:
            at = c.execute(sa.select(OKUMA.c.okundu_at).where(OKUMA.c.tenant_id == tenant)).scalar()
            if at is not None and (d.dizin is None or _aware(at).timestamp() > d.at):
                raw = c.execute(sa.select(OKUMA.c.rows_json).where(OKUMA.c.tenant_id == tenant)).scalar()
                d.dizin, d.at = dizin_kur(json.loads(raw or "[]")), _aware(at).timestamp()
    except Exception as e:  # noqa: BLE001 — bellekte varsa o kullanılır
        if d.dizin is None:
            raise
        log.info("crm kişi eşlemesi tablosu okunamadı, bellekteki kullanılıyor: %s", e)
    d.bakildi = time.monotonic()


def bul(engine: sa.engine.Engine, tenant: str, username: str, okuyucu: Okuyucu, *,
        taze: Optional[float] = None) -> Optional[dict[str, Any]]:
    """Kişinin CRM kullanıcısı ({id, name, disabled}) ya da None (CRM'de karşılığı yok).

    `Bilinmiyor`: hesap adı eşlemeye uygun değil. Hiç okuma yokken CRM okunamazsa hata yükselir. Her iki durumda
    çağıran eski yola (kişi başına canlı okuma) dönebilir."""
    if not uygun(username):
        raise Bilinmiyor(username)
    d = _durum(engine, tenant)
    _yukle(engine, tenant, d)
    if d.dizin is None:
        oku(engine, tenant, okuyucu)
    elif time.time() - d.at >= (TAZE if taze is None else taze):
        _arkada_oku(engine, tenant, okuyucu)
    return eslestir(d.dizin or {}, username)


def durum(engine: sa.engine.Engine, tenant: str) -> dict[str, Any]:
    """Teşhis: son okumanın zamanı ve satır sayısı (tablodan)."""
    ensure(engine)
    with IZ.disarida(), engine.connect() as c:
        r = c.execute(sa.select(OKUMA.c.okundu_at, OKUMA.c.satir, OKUMA.c.sure_ms)
                      .where(OKUMA.c.tenant_id == tenant)).first()
    if r is None:
        return {"okundu": None}
    return {"okundu": _aware(r[0]).isoformat(), "satir": r[1], "ms": r[2]}
