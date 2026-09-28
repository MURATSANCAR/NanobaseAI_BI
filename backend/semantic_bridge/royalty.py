"""M54 Telif dönemi ve haklar: portalın kendi kayıtları (dönem koşusu, istisna, onay, beyanname, avans, yenileme, hak).

M6 Sözleşmeler tek sözleşmenin defteridir; M54 dönemin ve portföyün telif muhasebesidir. Hesap **M6'nın motorudur**
(`contracts_royalty.compute`, `fold_sales`); onaylanan koşu M6'nın hakedişlerini ve ödeme takvimini M6'nın kendi
işlevleriyle oluşturur (`contracts.adopt_crm`, `save_statement`, `approve_statement`). Burada hesap yeniden yazılmaz.

Akış: taslak → hesaplanıyor → hesaplandı → onayda → onaylanıyor → onaylı (iptal: onaydan önce her an).
- **Kapsam sessizce daralmaz:** kapsamdaki her sözleşme koşuda bir satırdır; durumu «hesaplandı», «istisna» ya da
  «hariç» (kim, neden). Kabul 1: satır sayısı = CRM'deki kapsam sayısı.
- **İstisna:** hesabın güvenle yapılamadığı sözleşme. Bir kısmı «kabul edilebilir» (hesap var, insan bakıp onaylar:
  taraf payı toplamı, kademe geçmişi, değişken esas …), bir kısmı değildir (stok kodu, kur, avans açılışı, çakışan
  onaylı hakediş …): önce M6 sözleşme sayfasında düzeltilir, sonra koşu yeniden hesaplanır.
- **İki göz:** hesaplatan ve onaya gönderen onaylayamaz (`ozellik:telif.kosu-onay` açıkça verilir).
- **Onaylı koşu değişmez.** Sonradan gelen iade bir sonraki dönemin hesabına girer (M6'nın devir kuralı).
- **Avans bakiyesi sıfır varsayılmaz:** geçmiş ödemeler sözleşme bazında hiçbir kaynakta yok (CRM ödeme tablosu
  2014'te kalmış, Logo ödemeyi cariye yazar). Portalda onaylı hakedişi olmayan avanslı sözleşme, açılış bakiyesi
  (kazanılmamış kalan avans, tarihli, gerekçeli) girilene kadar istisnadır.

Kişiye gönderim yok (kullanıcı kararı 2026-09-28: ilk sürümde otomatik dış gönderim yok): beyanname Word olarak
indirilir, gönderimi insan yapar ve «gönderildi» diye işaretler. Ödeme listesi dosyadır; bankaya, Logo'ya, CRM'e gitmez.
"""
from __future__ import annotations

import copy
import csv
import hashlib
import io
import logging
import re
import threading
import unicodedata
import uuid
import zipfile
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Optional

import sqlalchemy as sa

from semantic_bridge import contracts as C
from semantic_bridge import contracts_docs as D
from semantic_bridge import contracts_royalty as R
from semantic_bridge import contracts_terms as T
from semantic_bridge import royalty_sources as S

log = logging.getLogger("semantic.royalty")

_md = sa.MetaData()
_MONEY = sa.Numeric(18, 2, asdecimal=False)
PAGE = 50


class RoyaltyError(ValueError):
    """Kişiye olduğu gibi gösterilecek düz Türkçe hata."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


RUNS = sa.Table(
    "semantic_royalty_runs", _md,
    sa.Column("id", sa.String(40), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False),
    sa.Column("no", sa.String(40), nullable=False),
    sa.Column("donem_bas", sa.String(10), nullable=False),
    sa.Column("donem_bit", sa.String(10), nullable=False),
    sa.Column("durum", sa.String(20), nullable=False),
    sa.Column("veri_son_gunu", sa.String(10)),
    sa.Column("kapsam_json", sa.JSON),
    sa.Column("ozet_json", sa.JSON),
    sa.Column("secenek_json", sa.JSON),
    sa.Column("ilerleme_json", sa.JSON),
    sa.Column("hata", sa.Text),
    sa.Column("not_", sa.Text),
    sa.Column("hazirlayan", sa.String(120)),
    sa.Column("gonderen", sa.String(120)),
    sa.Column("onaylayan", sa.String(120)),
    sa.Column("olusturan", sa.String(120), nullable=False),
    sa.Column("olusturma_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("hesap_at", sa.DateTime(timezone=True)),
    sa.Column("gonderim_at", sa.DateTime(timezone=True)),
    sa.Column("onay_at", sa.DateTime(timezone=True)),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("surum", sa.Integer, nullable=False, default=1),
    sa.UniqueConstraint("tenant_id", "no", name="uq_semantic_royalty_runs_no"),
)

LINES = sa.Table(
    "semantic_royalty_run_lines", _md,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("run_id", sa.String(40), nullable=False, index=True),
    sa.Column("tenant_id", sa.String(80), nullable=False),
    sa.Column("contract_key", sa.String(40), nullable=False),
    sa.Column("crm_id", sa.String(40)),
    sa.Column("contract_id", sa.String(40)),
    sa.Column("no", sa.String(120)),
    sa.Column("baslik", sa.String(600)),
    sa.Column("durum", sa.String(20), nullable=False),
    sa.Column("istisna_kodu", sa.String(40)),
    sa.Column("istisnalar", sa.JSON),
    sa.Column("karar", sa.JSON),
    sa.Column("party_count", sa.Integer),
    sa.Column("taraflar", sa.JSON),
    sa.Column("brut", _MONEY),
    sa.Column("avans_mahsup", _MONEY),
    sa.Column("stopaj", _MONEY),
    sa.Column("net", _MONEY),
    sa.Column("para", sa.String(3)),
    sa.Column("kur", sa.Float),
    sa.Column("kur_tarihi", sa.String(10)),
    sa.Column("calc_json", sa.JSON),
    sa.Column("terms_json", sa.JSON),
    sa.Column("crm_json", sa.JSON),
    sa.Column("fingerprint", sa.String(32)),
    sa.Column("statement_id", sa.String(40)),
    sa.Column("onay_hatasi", sa.Text),
    sa.UniqueConstraint("run_id", "contract_key", name="uq_semantic_royalty_line_contract"),
)

PARTIES = sa.Table(
    "semantic_royalty_party_statements", _md,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("run_id", sa.String(40), nullable=False, index=True),
    sa.Column("tenant_id", sa.String(80), nullable=False),
    sa.Column("party_key", sa.String(80), nullable=False),
    sa.Column("ad", sa.String(300), nullable=False),
    sa.Column("tur", sa.String(10)),
    sa.Column("eposta", sa.String(300)),
    sa.Column("toplam_json", sa.JSON),
    sa.Column("sozlesme_sayisi", sa.Integer),
    sa.Column("belge_hash", sa.String(64)),
    sa.Column("durum", sa.String(20), nullable=False),
    sa.Column("kanal", sa.String(20)),
    sa.Column("not_", sa.Text),
    sa.Column("gonderen", sa.String(120)),
    sa.Column("gonderim_at", sa.DateTime(timezone=True)),
    sa.UniqueConstraint("run_id", "party_key", name="uq_semantic_royalty_party"),
)

ADVANCES = sa.Table(
    "semantic_royalty_advances", _md,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("tenant_id", sa.String(80), nullable=False),
    sa.Column("contract_key", sa.String(40), nullable=False, index=True),
    sa.Column("acilis_tutari", _MONEY),
    sa.Column("para", sa.String(3), nullable=False),
    sa.Column("acilis_tarihi", sa.String(10), nullable=False),
    sa.Column("kaynak", sa.String(10), nullable=False),
    sa.Column("gerekce", sa.Text, nullable=False),
    sa.Column("giren", sa.String(120), nullable=False),
    sa.Column("tarih", sa.DateTime(timezone=True), nullable=False),
    sa.Column("aktif", sa.Boolean, nullable=False, default=True),
)

RENEWALS = sa.Table(
    "semantic_royalty_renewals", _md,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("tenant_id", sa.String(80), nullable=False),
    sa.Column("contract_key", sa.String(40), nullable=False),
    sa.Column("no", sa.String(120)),
    sa.Column("bitis", sa.String(10)),
    sa.Column("karar", sa.String(12), nullable=False),
    sa.Column("gerekce", sa.Text),
    sa.Column("oneri_karar", sa.String(12)),
    sa.Column("oneri_olasilik", sa.Float),
    sa.Column("oneri_metni", sa.Text),
    sa.Column("oneri_girdi", sa.JSON),
    sa.Column("oneri_at", sa.DateTime(timezone=True)),
    sa.Column("karar_veren", sa.String(120)),
    sa.Column("karar_at", sa.DateTime(timezone=True)),
    sa.Column("gecmis", sa.JSON),
    sa.UniqueConstraint("tenant_id", "contract_key", name="uq_semantic_royalty_renewal"),
)

GRANTS = sa.Table(
    "semantic_rights_grants", _md,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("tenant_id", sa.String(80), nullable=False),
    sa.Column("kitap_id", sa.String(40), nullable=False, index=True),
    sa.Column("kitap_stok_kodu", sa.String(60)),
    sa.Column("hak_turu", sa.String(30), nullable=False),
    sa.Column("dil", sa.String(80)),
    sa.Column("ulke", sa.String(120)),
    sa.Column("bas", sa.String(10)),
    sa.Column("bit", sa.String(10)),
    sa.Column("kaynak", sa.String(10), nullable=False),
    sa.Column("contract_key", sa.String(40)),
    sa.Column("not_", sa.Text),
    sa.Column("giren", sa.String(120), nullable=False),
    sa.Column("tarih", sa.DateTime(timezone=True), nullable=False),
)

LICENSES = sa.Table(
    "semantic_rights_licenses_out", _md,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("tenant_id", sa.String(80), nullable=False),
    sa.Column("kitap_id", sa.String(40), index=True),
    sa.Column("kitap", sa.String(400), nullable=False),
    sa.Column("alici_yayinevi", sa.String(300), nullable=False),
    sa.Column("dil", sa.String(80)),
    sa.Column("ulke", sa.String(120)),
    sa.Column("avans", _MONEY),
    sa.Column("oran", sa.Float),
    sa.Column("para", sa.String(3)),
    sa.Column("bas", sa.String(10)),
    sa.Column("bit", sa.String(10)),
    sa.Column("durum", sa.String(20), nullable=False),
    sa.Column("tahsilat_durumu", sa.String(20)),
    sa.Column("tahsilat_tutari", _MONEY),
    sa.Column("yazar_payi_yuzde", sa.Float),
    sa.Column("crm_contract_id", sa.String(40)),
    sa.Column("not_", sa.Text),
    sa.Column("giren", sa.String(120), nullable=False),
    sa.Column("tarih", sa.DateTime(timezone=True), nullable=False),
    sa.Column("guncelleyen", sa.String(120)),
    sa.Column("guncelleme_at", sa.DateTime(timezone=True)),
)

NOTES = sa.Table(
    "semantic_rights_notes", _md,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("tenant_id", sa.String(80), nullable=False),
    sa.Column("contract_key", sa.String(40), nullable=False),
    sa.Column("no", sa.String(120)),
    sa.Column("kitap", sa.String(400)),
    sa.Column("metin", sa.Text),
    sa.Column("metin_hash", sa.String(64), nullable=False),
    sa.Column("sinif", sa.String(20)),
    sa.Column("olasilik", sa.Float),
    sa.Column("marj", sa.Float),
    sa.Column("yontem", sa.String(12)),
    sa.Column("durum", sa.String(12), nullable=False),
    sa.Column("onaylayan", sa.String(120)),
    sa.Column("onay_at", sa.DateTime(timezone=True)),
    sa.Column("tarih", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("tenant_id", "contract_key", name="uq_semantic_rights_note"),
)

NOTICES = sa.Table(
    "semantic_royalty_notices", _md,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("tenant_id", sa.String(80), nullable=False),
    sa.Column("tur", sa.String(40), nullable=False),
    sa.Column("ref", sa.String(80), nullable=False),
    sa.Column("at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("tenant_id", "tur", "ref", name="uq_semantic_royalty_notice"),
)

RUN_STATUSES = {"taslak": "Taslak", "hesaplaniyor": "Hesaplanıyor", "hesaplandi": "Hesaplandı", "onayda": "Onayda",
                "onaylaniyor": "Onaylanıyor", "onayli": "Onaylı", "iptal": "İptal"}
LINE_STATUSES = {"hesaplandi": "Hesaplandı", "istisna": "İstisna", "haric": "Hariç"}

#: İstisna kodu → (ekrandaki ad, kabul edilebilir mi, ne yapılır). Kabul edilebilir istisnada hesap vardır; insan bakıp
#: gerekçesiyle kabul eder. Diğerleri kaynağında düzeltilip koşu yeniden hesaplanır.
EXCEPTIONS: dict[str, tuple[str, bool, str]] = {
    "kitap-yok": ("Sözleşmeye kitap bağlı değil", False, "Sözleşme sayfasında kitap ekleyin (portalda) ya da CRM'de bağlayın."),
    "stok-kodu-yok": ("Kitabın stok kodu yok", False, "CRM kitap kartına stok kodu girilmeli; satış stok koduyla okunur."),
    "oran-yok": ("Telif oranı yok", False, "Sözleşmeye oran ya da kademe girin."),
    "taraf-yok": ("Sözleşmede taraf yok", False, "Hak sahibini sözleşmeye ekleyin."),
    "odeme-sekli": ("Ödeme şekli satıştan değil", False, "Portalda ödeme şekli değişmiş; koşunun kapsamı dışında."),
    "kur-yok": ("Dönem sonu kuru bulunamadı", False, "Koşuda o para birimi için kuru elle girin ya da TCMB erişimini kontrol edin."),
    "avans-acilis-yok": ("Avans açılış bakiyesi girilmemiş", False,
                         "Avans sekmesinde kazanılmamış kalan avansı tarihiyle ve gerekçesiyle girin; bilinmeyen avans sıfır sayılmaz."),
    "avans-para-birimi": ("Avans açılışının para birimi farklı", False, "Açılışı sözleşmenin para birimiyle yeniden girin."),
    "onayli-hakedis-var": ("Bu dönemle çakışan onaylı hakediş var", False,
                           "Aynı satışa iki kez telif ödenmez; sözleşmeyi hariç tutun ya da M6'daki hakedişi gözden geçirin."),
    "sonraki-donem-onayli": ("Sonraki bir dönemin hakedişi onaylı", False, "Sıra bozulmasın diye önce sonraki hakediş iptal edilmeli."),
    "hesap-hatasi": ("Hesap yapılamadı", False, "Hata metnine göre sözleşmeyi düzeltin."),
    "pay-toplami": ("Taraf payları toplamı %100 değil", True, "Paylar girildiği gibi uygulandı; doğruysa kabul edin."),
    "kademe-gecmis-eksik": ("Kademe birikimi eksik okunabilir", True,
                            "Sözleşme Logo satış görünümlerinin başladığı yıldan önce başlamış; kademe sınırını kontrol edip kabul edin."),
    "esas-degisken": ("Telif esası değişken", True, "Net satış tutarından hesaplandı; sözleşme maddesine uyuyorsa kabul edin."),
    "donem-uyumsuz": ("Sözleşmenin hakediş dönemi farklı", True, "Sözleşmedeki dönem koşununkinden farklı; bu dönem ödenecekse kabul edin."),
    "sure-bitti-satis-var": ("Sözleşme bitmiş, dönemde satış var", True, "Stok eritme ya da yenileme olabilir; telif doğuyorsa kabul edin."),
    "mukerrer-kitap-taraf": ("Aynı kitap ve hak sahibi başka sözleşmede de var", True,
                             "Yenileme ya da grup sözleşmesi olabilir; iki kez ödenmediğini kontrol edip kabul edin ya da birini hariç tutun."),
}
AUTO_EXCLUDE = {
    "baslamamis": "Sözleşme dönem bittikten sonra başlıyor.",
    "bitmis-satissiz": "Sözleşme dönem başlamadan bitmiş ve dönemde satış yok.",
    "portal-durum": "Sözleşme portalda yürürlükte değil.",
}
RENEWAL_DECISIONS = {"bekliyor": "Karar bekliyor", "yenile": "Yenile", "birak": "Bırak", "muzakere": "Yeniden müzakere"}
GRANT_KINDS = {**S.RIGHT_LABELS, "diger": "Diğer"}
LICENSE_STATUSES = {"gorusme": "Görüşme", "teklif": "Teklif verildi", "imzalandi": "İmzalandı", "sona-erdi": "Süresi bitti",
                    "iptal": "İptal"}
COLLECTION_STATUSES = {"bekliyor": "Bekliyor", "kismi": "Kısmi", "yapildi": "Yapıldı", "bedelsiz": "Bedelsiz"}
NOTE_CLASSES = {"bolge": "Bölge kısıtı", "format": "Format kısıtı", "sure": "Süre şartı", "onay": "Onay şartı",
                "ucret": "Ücret şartı", "diger": "Diğer"}

_ready: set[int] = set()
_lock = threading.Lock()
_PID = re.compile(r"^[0-9a-f]{32}$")
_GUID = re.compile(r"^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$")


def ensure(engine: sa.engine.Engine) -> None:
    with _lock:
        if id(engine) in _ready:
            return
        C.ensure(engine)
        _md.create_all(engine, checkfirst=True)
        _ready.add(id(engine))
        recover_stuck(engine)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(v: Any) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, datetime):
        return (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).isoformat()
    return str(v)


def today() -> date:
    return C._today()


def fold(s: Any) -> str:
    t = unicodedata.normalize("NFKD", str(s or "").replace("İ", "i").replace("I", "ı").lower())
    return " ".join("".join(ch for ch in t if not unicodedata.combining(ch)).split())


def mask_email(v: Optional[str]) -> Optional[str]:
    if not v or "@" not in v:
        return None
    user, _, host = v.partition("@")
    return (user[:1] + "***@" + host) if user else "***@" + host


def _text(v: Any, n: int) -> str:
    return " ".join(str(v or "").split())[:n]


def _money(v: Any, cur: str = "TRY") -> str:
    return T.money(v, cur)


# ------------------------------------------------------------------------------------------ dönem

def period_label(a: str, b: str) -> str:
    return f"{T.day_tr(a)} – {T.day_tr(b)}"


def default_period(on: date, months: int) -> tuple[str, str]:
    """Bugünden önce biten son takvim dönemi (6 ayda: Ocak–Haziran / Temmuz–Aralık)."""
    months = max(1, min(12, int(months or 6)))
    idx = (on.year * 12 + on.month - 1) // months * months - months  # içinde bulunulan dönemin bir öncekinin başı
    y, m = divmod(idx, 12)
    a = date(y, m + 1, 1)
    e = idx + months
    ey, em = divmod(e, 12)
    b = date(ey, em + 1, 1) - timedelta(days=1)
    return a.isoformat(), b.isoformat()


def run_months(a: str, b: str) -> int:
    da, db = date.fromisoformat(a), date.fromisoformat(b)
    return (db.year - da.year) * 12 + db.month - da.month + 1


# ------------------------------------------------------------------------------------------ koşu

def _run(r: Any) -> dict[str, Any]:
    return {"id": r.id, "no": r.no, "periodStart": r.donem_bas, "periodEnd": r.donem_bit,
            "label": period_label(r.donem_bas, r.donem_bit), "status": r.durum, "statusLabel": RUN_STATUSES.get(r.durum),
            "dataEnd": r.veri_son_gunu, "scope": r.kapsam_json or {}, "summary": r.ozet_json or {},
            "options": r.secenek_json or {}, "progress": r.ilerleme_json or {}, "error": r.hata, "note": r.not_,
            "preparedBy": r.hazirlayan, "submittedBy": r.gonderen, "approvedBy": r.onaylayan,
            "createdBy": r.olusturan, "createdAt": _iso(r.olusturma_at), "computedAt": _iso(r.hesap_at),
            "submittedAt": _iso(r.gonderim_at), "approvedAt": _iso(r.onay_at), "updatedAt": _iso(r.updated_at),
            "version": r.surum}


def _get_run(c: sa.engine.Connection, tenant: str, run_id: str, lock: bool = False) -> Any:
    if not _PID.match(run_id or ""):
        raise RoyaltyError("Koşu kimliği geçerli değil.")
    q = sa.select(RUNS).where(RUNS.c.tenant_id == tenant, RUNS.c.id == run_id)
    r = c.execute(q.with_for_update() if lock else q).first()
    if not r:
        raise RoyaltyError("Koşu bulunamadı.", 404)
    return r


def get_run(engine: sa.engine.Engine, tenant: str, run_id: str) -> dict[str, Any]:
    ensure(engine)
    recover_stuck(engine)
    with engine.connect() as c:
        return _run(_get_run(c, tenant, run_id))


def list_runs(engine: sa.engine.Engine, tenant: str) -> list[dict[str, Any]]:
    """Bütün koşular, yeniden eskiye (tavan yok)."""
    ensure(engine)
    with engine.connect() as c:
        rows = c.execute(sa.select(RUNS).where(RUNS.c.tenant_id == tenant)
                         .order_by(RUNS.c.donem_bas.desc(), RUNS.c.olusturma_at.desc())).all()
    return [_run(r) for r in rows]


def _clean_fx(raw: Any) -> dict[str, float]:
    out: dict[str, float] = {}
    for cur, v in (raw or {}).items() if isinstance(raw, dict) else []:
        if cur not in T.CURRENCIES or cur == "TRY" or v in (None, ""):
            continue
        n = T._num(v, f"{cur} kuru")
        if not n:
            raise RoyaltyError(f"{cur} kuru sıfırdan büyük olmalı.")
        out[cur] = n
    return out


def create_run(engine: sa.engine.Engine, tenant: str, user: str, body: dict[str, Any]) -> dict[str, Any]:
    ensure(engine)
    try:
        a, b = R.month_bounds(str(body.get("periodStart") or ""), str(body.get("periodEnd") or ""))
    except T.ContractError as e:
        raise RoyaltyError(str(e)) from None
    if b >= today():
        raise RoyaltyError("Dönem bitmeden koşu açılmaz; bitiş bugünden önce olmalı.")
    fx = _clean_fx(body.get("fx"))
    note = str(body.get("note") or "").strip()[:2000] or None
    now = _now()
    with engine.begin() as c:
        clash = c.execute(sa.select(RUNS.c.no, RUNS.c.donem_bas, RUNS.c.donem_bit).where(
            RUNS.c.tenant_id == tenant, RUNS.c.durum != "iptal",
            RUNS.c.donem_bas <= b.isoformat(), RUNS.c.donem_bit >= a.isoformat())).first()
        if clash:
            raise RoyaltyError(f"{clash.no} ({period_label(clash.donem_bas, clash.donem_bit)}) bu dönemle çakışıyor; "
                               "önce onu iptal edin ya da açık kalanıyla devam edin.", 409)
        prefix = f"TD-{b.year}-"
        nos = c.execute(sa.select(RUNS.c.no).where(RUNS.c.tenant_id == tenant, RUNS.c.no.like(prefix + "%"))).scalars().all()
        n = max([int(x[len(prefix):]) for x in nos if x[len(prefix):].isdigit()] + [0]) + 1
        rid = uuid.uuid4().hex
        c.execute(RUNS.insert().values(
            id=rid, tenant_id=tenant, no=f"{prefix}{n:02d}", donem_bas=a.isoformat(), donem_bit=b.isoformat(),
            durum="taslak", secenek_json={"fx": fx}, not_=note, olusturan=user, olusturma_at=now, updated_at=now, surum=1))
    return get_run(engine, tenant, rid)


def update_options(engine: sa.engine.Engine, tenant: str, user: str, run_id: str, body: dict[str, Any]) -> dict[str, Any]:
    with engine.begin() as c:
        r = _get_run(c, tenant, run_id, lock=True)
        if r.durum not in ("taslak", "hesaplandi"):
            raise RoyaltyError(f"«{RUN_STATUSES[r.durum]}» koşunun seçenekleri değişmez.")
        opts = dict(r.secenek_json or {})
        if "fx" in body:
            opts["fx"] = _clean_fx(body.get("fx"))
        values: dict[str, Any] = {"secenek_json": opts, "updated_at": _now(), "surum": r.surum + 1}
        if "note" in body:
            values["not_"] = str(body.get("note") or "").strip()[:2000] or None
        c.execute(RUNS.update().where(RUNS.c.id == r.id).values(**values))
    return get_run(engine, tenant, run_id)


def mark_computing(engine: sa.engine.Engine, tenant: str, user: str, run_id: str) -> dict[str, Any]:
    with engine.begin() as c:
        r = _get_run(c, tenant, run_id, lock=True)
        if r.durum not in ("taslak", "hesaplandi"):
            raise RoyaltyError(f"«{RUN_STATUSES[r.durum]}» koşu hesaplanmaz.", 409)
        c.execute(RUNS.update().where(RUNS.c.id == r.id).values(
            durum="hesaplaniyor", hata=None, ilerleme_json={"step": "Kapsam okunuyor", "done": 0, "total": 0,
                                                              "startedBy": user, "startedAt": _iso(_now()), "at": _iso(_now())},
            updated_at=_now(), surum=r.surum + 1))
    return get_run(engine, tenant, run_id)


def _progress(engine: sa.engine.Engine, run_id: str, **kw: Any) -> None:
    with engine.begin() as c:
        cur = c.execute(sa.select(RUNS.c.ilerleme_json).where(RUNS.c.id == run_id)).scalar() or {}
        c.execute(RUNS.update().where(RUNS.c.id == run_id).values(ilerleme_json={**cur, **kw, "at": _iso(_now())}))


def fail_run(engine: sa.engine.Engine, run_id: str, back_to: str, message: str) -> None:
    with engine.begin() as c:
        c.execute(RUNS.update().where(RUNS.c.id == run_id).values(durum=back_to, hata=message[:2000], updated_at=_now()))


#: Hesap/onay işi ilerlemesini en çok bu aralıkla yazar (her 250/100 sözleşmede ve her adımda); bu süre boyunca hiç
#: ilerleme yazmamış iş yarıda kalmış sayılır (köprü yeniden başladı ya da iş başka bir süreçte öldü).
STALE_AFTER = timedelta(minutes=30)


def recover_stuck(engine: sa.engine.Engine, older_than: timedelta = STALE_AFTER) -> None:
    """Yarıda kalan hesap/onay: son ilerlemesi `older_than`dan eski iş önceki durumuna döner, ekranda yazar."""
    cut = _now() - older_than
    try:
        with engine.begin() as c:
            for r in c.execute(sa.select(RUNS.c.id, RUNS.c.durum, RUNS.c.ilerleme_json, RUNS.c.updated_at)
                               .where(RUNS.c.durum.in_(("hesaplaniyor", "onaylaniyor")))).all():
                at = (r.ilerleme_json or {}).get("at")
                try:
                    last = datetime.fromisoformat(at) if at else r.updated_at
                except ValueError:
                    last = r.updated_at
                if last is not None and last.tzinfo is None:
                    last = last.replace(tzinfo=timezone.utc)
                if last is not None and last > cut:
                    continue
                if r.durum == "hesaplaniyor":
                    has = c.execute(sa.select(LINES.c.id).where(LINES.c.run_id == r.id).limit(1)).first()
                    back, msg = ("hesaplandi" if has else "taslak"), "Hesap yarıda kaldı (hizmet yeniden başladı); yeniden hesaplatın."
                else:
                    back, msg = "onayda", "Onay yarıda kaldı (hizmet yeniden başladı); onayı yeniden başlatın, tamamlananlar tekrar yapılmaz."
                c.execute(RUNS.update().where(RUNS.c.id == r.id).values(durum=back, hata=msg, updated_at=_now()))
    except Exception as e:  # noqa: BLE001 — tablo ilk kez kuruluyor olabilir
        log.warning("royalty: yarıda kalan koşu denetlenemedi: %s", e)


# ------------------------------------------------------------------------------------------ satır değerlendirme

def party_key(p: dict[str, Any]) -> str:
    if p.get("contactId"):
        return "kisi:" + str(p["contactId"]).strip("{}").lower()
    if p.get("accountId"):
        return "firma:" + str(p["accountId"]).strip("{}").lower()
    return "ad:" + fold(p.get("name"))[:70]


def _parties(terms: dict[str, Any], emails: dict[str, str]) -> list[dict[str, Any]]:
    out = []
    for p in terms.get("parties") or []:
        cid = str(p.get("contactId") or "").strip("{}").lower()
        aid = str(p.get("accountId") or "").strip("{}").lower()
        out.append({"key": party_key(p), "name": p.get("name"), "role": p.get("role"), "share": p.get("share"),
                    "type": "kisi" if cid else ("firma" if aid else "bilinmiyor"),
                    "email": emails.get(cid) or emails.get(aid) or None})
    return out


def _exc(code: str, detail: str = "") -> dict[str, Any]:
    label, ok, fix = EXCEPTIONS[code]
    return {"code": code, "label": label, "acceptable": ok, "fix": fix, "detail": detail or None}


def _ym(iso: str) -> int:
    d = date.fromisoformat(iso[:10])
    return d.year * 12 + d.month


def evaluate(item: dict[str, Any], *, a: str, b: str, rows_by_code: dict[str, list[dict[str, Any]]],
             prior_by_code: dict[str, list[dict[str, Any]]], first_year: Optional[int], data_end: Optional[str],
             fx: dict[str, Optional[dict[str, Any]]], statements: list[dict[str, Any]], opening: Optional[dict[str, Any]],
             duplicates: set[str], withholding_default: Optional[float], months: int) -> dict[str, Any]:
    """Bir sözleşmenin dönem satırı: istisnalar + M6 motoruyla hesap (saf işlev; veritabanına dokunmaz).

    `item`: {key, crmId, recordId, recordStatus, no, terms, emails}. `statements`: M6'da bu sözleşmenin onaylı
    hakedişleri [{periodStart, periodEnd, advanceOffset, carryOut}]. `opening`: avans açılışı {amount, currency, asOf}."""
    terms = copy.deepcopy(item["terms"])
    exc: list[dict[str, Any]] = []
    auto: Optional[str] = None
    notes: list[str] = []
    pt = terms.get("paymentType")
    cur = terms.get("currency") or "TRY"
    books = terms.get("books") or []
    codes = sorted({bk["stockCode"] for bk in books if bk.get("stockCode")})

    if item.get("recordStatus") and item["recordStatus"] != "yururlukte":
        auto = "portal-durum"
    if pt not in ("satis", "satis-kademeli"):
        exc.append(_exc("odeme-sekli", T.PAYMENT_TYPES.get(pt, str(pt))))
    if not books:
        exc.append(_exc("kitap-yok"))
    nocode = [bk["title"] for bk in books if not bk.get("stockCode")]
    if nocode:
        exc.append(_exc("stok-kodu-yok", ", ".join(nocode)))
    if not terms.get("rates") and not terms.get("tiers"):
        exc.append(_exc("oran-yok"))
    parties = terms.get("parties") or []
    if not parties:
        exc.append(_exc("taraf-yok"))
    shares = [float(p.get("share") or 0) for p in parties]
    if parties and sum(shares) and abs(sum(shares) - 100) > 0.01:
        exc.append(_exc("pay-toplami", f"%{T.fmt_num(sum(shares))}"))
    if terms.get("basis") == "degisken":
        exc.append(_exc("esas-degisken"))
    if item.get("recordId") and int(terms.get("periodMonths") or 6) != months:
        exc.append(_exc("donem-uyumsuz", f"sözleşmede {terms.get('periodMonths')} ay, koşuda {months} ay"))
    if item["key"] in duplicates:
        exc.append(_exc("mukerrer-kitap-taraf"))

    # Onaylı M6 hakedişleriyle çakışma (M6 aynı satışa iki kez ödemeyi zaten reddeder; burada önceden görünür).
    clash = [s for s in statements if s["periodStart"] <= b and s["periodEnd"] >= a]
    if clash:
        exc.append(_exc("onayli-hakedis-var", ", ".join(period_label(s["periodStart"], s["periodEnd"]) for s in clash)))
    if any(s["periodStart"] > b for s in statements):
        exc.append(_exc("sonraki-donem-onayli"))
    before = sorted((s for s in statements if s["periodStart"] < a), key=lambda s: s["periodEnd"])
    used_all = sum(float(s.get("advanceOffset") or 0) for s in before)
    carry_in = float(before[-1].get("carryOut") or 0) if before else 0.0

    # Dönem ve sözleşme süresi: satış sözleşme başladığı aydan itibaren sayılır.
    start, end = terms.get("start"), terms.get("end")
    lo = _ym(a)
    if start and start > b:
        auto = auto or "baslamamis"
    elif start and start > a:
        lo = _ym(start)
        notes.append(f"Sözleşme {T.day_tr(start)} günü başladı; satış o aydan itibaren sayıldı.")
    rows = [r for code in codes for r in rows_by_code.get(code, []) if S.month_of(r) >= lo]
    sales = R.fold_sales(rows)
    has_sales = any(abs(v.get("qty") or 0) > 0.0001 or abs(v.get("net") or 0) > 0.005 for v in sales.values())
    if end and not terms.get("openEnded") and end < a:
        if has_sales:
            exc.append(_exc("sure-bitti-satis-var", f"bitiş {T.day_tr(end)}"))
        else:
            auto = auto or "bitmis-satissiz"

    prior: dict[str, float] = {}
    if pt in T.TIERED and terms.get("tiers") and start:
        s_ym = _ym(start)
        prows = [r for code in codes for r in prior_by_code.get(code, []) if s_ym <= S.month_of(r) < _ym(a)]
        prior = {k: v["qty"] for k, v in R.fold_sales(prows).items()}
        if first_year and int(start[:4]) < first_year and _ym(start) < _ym(a):
            exc.append(_exc("kademe-gecmis-eksik", f"sözleşme {start[:4]}, satış verisi {first_year}'den"))

    rate = None
    if cur != "TRY":
        rate = fx.get(cur)
        if not rate:
            exc.append(_exc("kur-yok", cur))

    # Avans: bilinmeyen bakiye sıfır sayılmaz.
    advance = float(terms.get("advance") or 0)
    advance_basis: Optional[dict[str, Any]] = None
    if advance and terms.get("advanceRecoupable", True):
        first_period = bool(start) and start >= a
        if opening:
            if (opening.get("currency") or "TRY") != cur:
                exc.append(_exc("avans-para-birimi", f"açılış {opening.get('currency')}, sözleşme {cur}"))
            else:
                pre = sum(float(s.get("advanceOffset") or 0) for s in before if s["periodStart"] < opening["asOf"])
                eff = round(float(opening["amount"] or 0) + pre, 2)
                advance_basis = {"contractAdvance": advance, "opening": opening["amount"], "openingOn": opening["asOf"],
                                 "openingBy": opening.get("by"), "effective": eff}
                terms["advance"] = eff
                notes.append(f"Avans açılış bakiyesi {_money(opening['amount'], cur)} ({T.day_tr(opening['asOf'])}) esas alındı.")
        elif not first_period and not before:
            exc.append(_exc("avans-acilis-yok", _money(advance, cur)))

    if withholding_default and terms.get("withholdingPct") is None and parties:
        if all(p.get("contactId") and not p.get("accountId") for p in parties):
            terms["withholdingPct"] = withholding_default
            notes.append(f"Stopaj oranı Yönetim ayarından: %{T.fmt_num(withholding_default)}.")
        else:
            notes.append("Tarafta firma ya da kimliği bilinmeyen kişi var; varsayılan stopaj uygulanmadı, kontrol edin.")

    calc = None
    if books and parties and pt in ("satis", "satis-kademeli"):
        try:
            calc = R.compute(terms, period_start=a, period_end=b, sales=sales, prior_qty=prior,
                             advance_used=used_all, carry_in=carry_in, fx=rate, data_end=data_end)
            calc["warnings"] = notes + calc["warnings"]
            calc["source"] = "Logo satış görünümleri (faturalı satır), stok kodu ile — dönem koşusu"
            if advance_basis:
                calc["advanceBasis"] = advance_basis
        except T.ContractError as e:
            exc.append(_exc("hesap-hatasi", str(e)))
    return {"key": item["key"], "crmId": item.get("crmId"), "recordId": item.get("recordId"), "no": item.get("no"),
            "title": (item["terms"].get("title") or "")[:600], "exceptions": exc, "auto": auto, "calc": calc,
            "terms": item["terms"], "parties": _parties(item["terms"], item.get("emails") or {}),
            "hasSales": has_sales}


def line_status(exceptions: list[dict[str, Any]], decision: dict[str, Any], auto: Optional[str]) -> tuple[str, Optional[str]]:
    """(durum, açık ilk istisna kodu)."""
    if decision.get("haric") or (auto and not decision.get("autoUndone")):
        return "haric", None
    accepted = set((decision.get("kabul") or {}).get("codes") or [])
    open_ = [e for e in exceptions if not (e["acceptable"] and e["code"] in accepted)]
    if open_:
        return "istisna", open_[0]["code"]
    return "hesaplandi", None


def duplicate_keys(items: list[dict[str, Any]]) -> set[str]:
    """Aynı stok kodu + aynı hak sahibi birden çok kapsamdaki sözleşmede → o sözleşmeler."""
    seen: dict[tuple[str, str], set[str]] = {}
    for it in items:
        codes = {bk.get("stockCode") for bk in it["terms"].get("books") or [] if bk.get("stockCode")}
        for p in it["terms"].get("parties") or []:
            for code in codes:
                seen.setdefault((code, party_key(p)), set()).add(it["key"])
    return {k for keys in seen.values() if len(keys) > 1 for k in keys}


# ------------------------------------------------------------------------------------------ hesap işi

class Sources:
    """Koşunun okuduğu dış kaynaklar (test sahte kaynak verir)."""

    def scope(self) -> list[dict[str, Any]]: ...
    def present_years(self) -> set[int]: ...
    def sales(self, codes: list[str], a: date, b: date, present: set[int]) -> tuple[list[dict[str, Any]], list[int]]: ...
    def data_end(self, present: set[int], year: int) -> Optional[str]: ...
    def fx(self, currency: str, on: date) -> Optional[dict[str, Any]]: ...


def _approved_statements(c: sa.engine.Connection, tenant: str) -> dict[str, list[dict[str, Any]]]:
    rows = c.execute(sa.select(C.STATEMENTS.c.contract_id, C.STATEMENTS.c.period_start, C.STATEMENTS.c.period_end,
                               C.STATEMENTS.c.advance_offset, C.STATEMENTS.c.carry_out)
                     .where(C.STATEMENTS.c.tenant_id == tenant, C.STATEMENTS.c.status == "onaylandi")).all()
    out: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        out.setdefault(r.contract_id, []).append({"periodStart": r.period_start, "periodEnd": r.period_end,
                                                  "advanceOffset": r.advance_offset, "carryOut": r.carry_out})
    return out


def openings(c: sa.engine.Connection, tenant: str) -> dict[str, dict[str, Any]]:
    rows = c.execute(sa.select(ADVANCES).where(ADVANCES.c.tenant_id == tenant, ADVANCES.c.aktif.is_(True))
                     .order_by(ADVANCES.c.tarih)).all()
    return {r.contract_key: {"amount": r.acilis_tutari, "currency": r.para, "asOf": r.acilis_tarihi, "by": r.giren,
                             "reason": r.gerekce, "at": _iso(r.tarih), "source": r.kaynak} for r in rows}


def candidates(c: sa.engine.Connection, tenant: str, crm_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """CRM kapsamı + portal kaydı (portal değeri kazanır) + yalnız portalda açılmış yürürlükteki satıştan ödemeli sözleşmeler."""
    recs = c.execute(sa.select(C.RECORDS).where(C.RECORDS.c.tenant_id == tenant)).all()
    by_crm = {r.crm_id: r for r in recs if r.crm_id}
    out = []
    for it in crm_items:
        r = by_crm.get(it["crmId"])
        out.append({"key": it["crmId"], "crmId": it["crmId"], "recordId": r.id if r else None,
                    "recordStatus": r.status if r else None, "recordVersion": r.version if r else None,
                    "no": (r.no if r else it["no"]) or it["crmId"][:8], "terms": (r.terms if r else it["terms"]),
                    "crm": {"no": it["no"], "status": it["status"], "terms": it["terms"]}, "emails": it.get("emails") or {}})
    for r in recs:
        t = r.terms or {}
        if r.crm_id or r.status != "yururlukte" or t.get("kind") != "telif-alis" or t.get("paymentType") not in ("satis", "satis-kademeli"):
            continue
        out.append({"key": r.id, "crmId": None, "recordId": r.id, "recordStatus": r.status, "recordVersion": r.version,
                    "no": r.no, "terms": t, "crm": None, "emails": {}})
    return out


def compute_run(engine: sa.engine.Engine, tenant: str, run_id: str, user: str, src: Sources,
                settings: dict[str, Any]) -> dict[str, Any]:
    """Koşunun hesabı (arka plan işi). Önceki kararlar (hariç / kabul) sözleşme kimliğiyle taşınır."""
    with engine.connect() as c:
        run = _get_run(c, tenant, run_id)
    a, b = run.donem_bas, run.donem_bit
    da, db = date.fromisoformat(a), date.fromisoformat(b)
    months = run_months(a, b)
    fx_manual = (run.secenek_json or {}).get("fx") or {}
    _progress(engine, run_id, step="CRM kapsamı okunuyor")
    crm_items = src.scope()
    with engine.connect() as c:
        items = candidates(c, tenant, crm_items)
        stmts = _approved_statements(c, tenant)
        opens = openings(c, tenant)
        prev = {r.contract_key: r.karar or {} for r in c.execute(
            sa.select(LINES.c.contract_key, LINES.c.karar).where(LINES.c.run_id == run_id)).all()}
    codes = sorted({bk["stockCode"] for it in items for bk in it["terms"].get("books") or [] if bk.get("stockCode")})
    _progress(engine, run_id, step="Logo satışı okunuyor", total=len(items))
    present = src.present_years()
    rows, missing = src.sales(codes, da, db, present) if codes else ([], [])
    by_code = S.group_by_code(rows)
    tiered = [it for it in items if it["terms"].get("paymentType") in T.TIERED and it["terms"].get("tiers") and it["terms"].get("start")
              and it["terms"]["start"] < a]
    prior_by: dict[str, list[dict[str, Any]]] = {}
    first_year = min(present) if present else None
    if tiered and present:
        s0 = max(min(date.fromisoformat(it["terms"]["start"]).replace(day=1) for it in tiered), date(first_year, 1, 1))
        tcodes = sorted({bk["stockCode"] for it in tiered for bk in it["terms"].get("books") or [] if bk.get("stockCode")})
        if s0 < da and tcodes:
            _progress(engine, run_id, step="Kademe birikimi okunuyor")
            prows, _ = src.sales(tcodes, s0, da - timedelta(days=1), present)
            prior_by = S.group_by_code(prows)
    data_end = src.data_end(present, db.year) if present else None
    fx: dict[str, Optional[dict[str, Any]]] = {}
    for cur in sorted({it["terms"].get("currency") or "TRY" for it in items} - {"TRY"}):
        if fx_manual.get(cur):
            fx[cur] = {"rate": float(fx_manual[cur]), "on": b, "source": "koşuda elle girildi"}
        else:
            fx[cur] = src.fx(cur, db)
    dups = duplicate_keys(items)
    wpct = settings.get("withholdingPct")
    _progress(engine, run_id, step="Telif hesaplanıyor", done=0, total=len(items))
    lines = []
    for i, it in enumerate(items):
        ev = evaluate(it, a=a, b=b, rows_by_code=by_code, prior_by_code=prior_by, first_year=first_year, data_end=data_end,
                      fx=fx, statements=stmts.get(it["recordId"] or "", []), opening=opens.get(it["key"]), duplicates=dups,
                      withholding_default=wpct, months=months)
        dec = dict(prev.get(it["key"]) or {})
        if dec.get("kabul"):
            now_codes = {e["code"] for e in ev["exceptions"] if e["acceptable"]}
            kept = [x for x in dec["kabul"].get("codes") or [] if x in now_codes]
            dec["kabul"] = {**dec["kabul"], "codes": kept} if kept else None
        durum, first = line_status(ev["exceptions"], dec, ev["auto"])
        calc = ev["calc"] or {}
        lines.append({
            "run_id": run_id, "tenant_id": tenant, "contract_key": it["key"], "crm_id": it["crmId"], "contract_id": it["recordId"],
            "no": (ev["no"] or "")[:120], "baslik": ev["title"], "durum": durum, "istisna_kodu": first,
            "istisnalar": ev["exceptions"], "karar": {**dec, "auto": ev["auto"], "autoReason": AUTO_EXCLUDE.get(ev["auto"] or "")},
            "party_count": len(ev["parties"]), "taraflar": ev["parties"],
            "brut": calc.get("gross"), "avans_mahsup": calc.get("advanceOffset"), "stopaj": calc.get("withholding"),
            "net": calc.get("net"), "para": calc.get("currency") or (it["terms"].get("currency") or "TRY"),
            "kur": (calc.get("fx") or {}).get("rate"), "kur_tarihi": (calc.get("fx") or {}).get("on"),
            "calc_json": ev["calc"], "terms_json": it["terms"],
            "crm_json": {**(it["crm"] or {}), "recordVersion": it.get("recordVersion")} if it["crm"] else {"recordVersion": it.get("recordVersion")},
            "fingerprint": R.fingerprint(ev["calc"]) if ev["calc"] else None, "statement_id": None, "onay_hatasi": None,
        })
        if (i + 1) % 250 == 0:
            _progress(engine, run_id, done=i + 1)
    summary = summarize(lines)
    summary.update(missingYears=missing, fx={k: v for k, v in fx.items()}, withholdingPct=wpct,
                   dataIncomplete=bool(data_end and data_end < b), crmScope=len(crm_items),
                   portalOnly=sum(1 for it in items if not it["crmId"]))
    with engine.begin() as c:
        c.execute(LINES.delete().where(LINES.c.run_id == run_id))
        if lines:
            c.execute(LINES.insert(), lines)
        c.execute(RUNS.update().where(RUNS.c.id == run_id).values(
            durum="hesaplandi", veri_son_gunu=data_end, ozet_json=summary, hata=None, hazirlayan=user, hesap_at=_now(),
            kapsam_json={"statuses": list(settings.get("statuses") or []), "paymentCodes": list(settings.get("paymentCodes") or []),
                         "crmCount": len(crm_items), "lines": len(lines), "firstSalesYear": first_year},
            ilerleme_json={"step": "Bitti", "done": len(lines), "total": len(lines), "at": _iso(_now())},
            updated_at=_now()))
    return get_run(engine, tenant, run_id)


def summarize(lines: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {k: 0 for k in LINE_STATUSES}
    reasons: dict[str, int] = {}
    totals: dict[str, dict[str, float]] = {}
    for ln in lines:
        counts[ln["durum"]] += 1
        if ln["durum"] == "istisna":
            for e in ln["istisnalar"]:
                if not (e["acceptable"] and e["code"] in set(((ln["karar"] or {}).get("kabul") or {}).get("codes") or [])):
                    reasons[e["code"]] = reasons.get(e["code"], 0) + 1
        if ln["durum"] == "hesaplandi":
            t = totals.setdefault(ln["para"] or "TRY", {"gross": 0.0, "advance": 0.0, "withholding": 0.0, "net": 0.0, "count": 0})
            t["gross"] += float(ln["brut"] or 0)
            t["advance"] += float(ln["avans_mahsup"] or 0)
            t["withholding"] += float(ln["stopaj"] or 0)
            t["net"] += float(ln["net"] or 0)
            t["count"] += 1
    for t in totals.values():
        for k in ("gross", "advance", "withholding", "net"):
            t[k] = round(t[k], 2)
    return {"lines": len(lines), "counts": counts, "reasons": dict(sorted(reasons.items(), key=lambda x: -x[1])),
            "totals": totals}


def _resummarize(c: sa.engine.Connection, run_id: str) -> None:
    rows = c.execute(sa.select(LINES.c.durum, LINES.c.istisnalar, LINES.c.karar, LINES.c.para, LINES.c.brut,
                               LINES.c.avans_mahsup, LINES.c.stopaj, LINES.c.net).where(LINES.c.run_id == run_id)).all()
    s = summarize([dict(r._mapping) for r in rows])
    old = c.execute(sa.select(RUNS.c.ozet_json).where(RUNS.c.id == run_id)).scalar() or {}
    c.execute(RUNS.update().where(RUNS.c.id == run_id).values(ozet_json={**old, **s}, updated_at=_now()))


# ------------------------------------------------------------------------------------------ satırlar

def _line(r: Any, full: bool = False) -> dict[str, Any]:
    out = {"id": r.id, "contractKey": r.contract_key, "crmId": r.crm_id, "contractId": r.contract_id, "no": r.no,
           "title": r.baslik, "status": r.durum, "statusLabel": LINE_STATUSES.get(r.durum), "exceptionCode": r.istisna_kodu,
           "exceptions": r.istisnalar or [], "decision": r.karar or {}, "parties": [
               {k: v for k, v in p.items() if k != "email"} for p in (r.taraflar or [])],
           "gross": r.brut, "advanceOffset": r.avans_mahsup, "withholding": r.stopaj, "net": r.net, "currency": r.para,
           "fxRate": r.kur, "fxOn": r.kur_tarihi, "statementId": r.statement_id, "approvalError": r.onay_hatasi}
    if full:
        out.update(calc=r.calc_json, terms=r.terms_json, crm=r.crm_json)
    return out


_LIGHT = [LINES.c[k] for k in ("id", "contract_key", "crm_id", "contract_id", "no", "baslik", "durum", "istisna_kodu",
                                "istisnalar", "karar", "taraflar", "brut", "avans_mahsup", "stopaj", "net", "para", "kur",
                                "kur_tarihi", "statement_id", "onay_hatasi")]


def lines(engine: sa.engine.Engine, tenant: str, run_id: str, *, status: str = "", code: str = "", q: str = "",
          page: int = 0) -> dict[str, Any]:
    """Koşunun satırları, sayfalı; `total` süzgece uyan bütün satır (kesilmez, sayfalanır)."""
    with engine.connect() as c:
        _get_run(c, tenant, run_id)
        stmt = sa.select(*_LIGHT).where(LINES.c.run_id == run_id, LINES.c.tenant_id == tenant)
        if status:
            stmt = stmt.where(LINES.c.durum == status)
        rows = c.execute(stmt.order_by(LINES.c.durum, LINES.c.no, LINES.c.id)).all()
    needle = fold(q)
    out = []
    for r in rows:
        if code and not any(e["code"] == code for e in (r.istisnalar or [])):
            continue
        if needle:
            hay = fold(" ".join([r.no or "", r.baslik or ""] + [str(p.get("name") or "") for p in r.taraflar or []]))
            if needle not in hay:
                continue
        out.append(r)
    n = max(0, int(page or 0))
    return {"items": [_line(r) for r in out[n * PAGE:(n + 1) * PAGE]], "total": len(out), "page": n, "pageSize": PAGE}


def line(engine: sa.engine.Engine, tenant: str, run_id: str, line_id: int) -> dict[str, Any]:
    with engine.connect() as c:
        r = c.execute(sa.select(LINES).where(LINES.c.run_id == run_id, LINES.c.tenant_id == tenant, LINES.c.id == int(line_id))).first()
    if not r:
        raise RoyaltyError("Satır bulunamadı.", 404)
    return _line(r, full=True)


def decide_line(engine: sa.engine.Engine, tenant: str, user: str, run_id: str, line_id: int, body: dict[str, Any]) -> dict[str, Any]:
    """Hariç tut / geri al / istisnayı kabul et — hepsi gerekçeli, kimin yaptığı satırda durur."""
    action = str(body.get("action") or "")
    reason = _text(body.get("reason"), 1000)
    if action not in ("haric", "geri-al", "kabul"):
        raise RoyaltyError("Geçersiz işlem.")
    if action != "geri-al" and not reason:
        raise RoyaltyError("Gerekçe yazın.")
    with engine.begin() as c:
        run = _get_run(c, tenant, run_id, lock=True)
        r = c.execute(sa.select(LINES).where(LINES.c.run_id == run_id, LINES.c.id == int(line_id)).with_for_update()).first()
        if not r:
            raise RoyaltyError("Satır bulunamadı.", 404)
        allowed = run.durum == "hesaplandi" or (run.durum == "onayda" and action == "haric" and r.onay_hatasi and not r.statement_id)
        if not allowed:
            raise RoyaltyError(f"«{RUN_STATUSES[run.durum]}» koşuda satır değişmez.", 409)
        dec = dict(r.karar or {})
        stamp = {"by": user, "at": _iso(_now()), "reason": reason}
        if action == "haric":
            dec["haric"] = stamp
        elif action == "geri-al":
            if dec.get("haric"):
                dec["haric"] = None
            elif dec.get("auto") and not dec.get("autoUndone"):
                dec["autoUndone"] = {"by": user, "at": _iso(_now())}
            elif dec.get("kabul"):
                dec["kabul"] = None
            else:
                raise RoyaltyError("Geri alınacak bir karar yok.")
        else:
            acceptable = [e["code"] for e in r.istisnalar or [] if e["acceptable"]]
            hard = [e for e in r.istisnalar or [] if not e["acceptable"]]
            if hard:
                raise RoyaltyError("Bu satırda kabul edilemeyen istisna var: " + ", ".join(e["label"] for e in hard)
                                   + ". Önce kaynağında düzeltip yeniden hesaplatın.")
            if not acceptable:
                raise RoyaltyError("Kabul edilecek istisna yok.")
            if not r.calc_json:
                raise RoyaltyError("Bu satırın hesabı yok; kabul edilemez.")
            dec["kabul"] = {**stamp, "codes": acceptable}
        durum, first = line_status(r.istisnalar or [], dec, dec.get("auto"))
        c.execute(LINES.update().where(LINES.c.id == r.id).values(karar=dec, durum=durum, istisna_kodu=first))
        _resummarize(c, run_id)
        row = c.execute(sa.select(LINES).where(LINES.c.id == r.id)).first()
    return _line(row, full=True)


# ------------------------------------------------------------------------------------------ onaya gönder / onay

def submit(engine: sa.engine.Engine, tenant: str, user: str, run_id: str, body: dict[str, Any]) -> dict[str, Any]:
    with engine.begin() as c:
        r = _get_run(c, tenant, run_id, lock=True)
        if r.durum != "hesaplandi":
            raise RoyaltyError(f"«{RUN_STATUSES[r.durum]}» koşu onaya gönderilmez.", 409)
        open_n = c.execute(sa.select(sa.func.count()).select_from(LINES).where(LINES.c.run_id == run_id,
                                                                               LINES.c.durum == "istisna")).scalar()
        if open_n:
            raise RoyaltyError(f"{open_n} istisna çözülmemiş: düzeltip yeniden hesaplatın, kabul edin ya da gerekçesiyle hariç tutun.")
        s = r.ozet_json or {}
        note = _text(body.get("note"), 1000)
        if s.get("dataIncomplete") and not body.get("acceptDataEnd"):
            raise RoyaltyError(f"Logo satışı {T.day_tr(r.veri_son_gunu)} gününe kadar; dönem {T.day_tr(r.donem_bit)} bitiyor. "
                               "Eksik veriyle göndermek için bunu onaylayın ve not yazın.")
        if s.get("dataIncomplete") and not note:
            raise RoyaltyError("Eksik veriyle göndermenin nedenini yazın.")
        c.execute(RUNS.update().where(RUNS.c.id == r.id).values(
            durum="onayda", gonderen=user, gonderim_at=_now(), hata=None, updated_at=_now(), surum=r.surum + 1,
            not_=((r.not_ + "\n") if r.not_ else "") + note if note else r.not_))
    return get_run(engine, tenant, run_id)


def back_to_computed(engine: sa.engine.Engine, tenant: str, user: str, run_id: str, body: dict[str, Any], *, reject: bool) -> dict[str, Any]:
    note = _text(body.get("note"), 1000)
    with engine.begin() as c:
        r = _get_run(c, tenant, run_id, lock=True)
        if r.durum != "onayda":
            raise RoyaltyError(f"Koşu «{RUN_STATUSES[r.durum]}»; onayda değil.", 409)
        done = c.execute(sa.select(sa.func.count()).select_from(LINES).where(LINES.c.run_id == run_id,
                                                                             LINES.c.statement_id.is_not(None))).scalar()
        if done:
            raise RoyaltyError(f"Onay yarıda kaldı ve {done} hakediş oluştu; geri gönderilemez, onayı tamamlayın.", 409)
        if reject and not note:
            raise RoyaltyError("Geri gönderme gerekçesini yazın.")
        prefix = "Geri gönderildi" if reject else "Geri çekildi"
        c.execute(RUNS.update().where(RUNS.c.id == r.id).values(
            durum="hesaplandi", gonderen=None, gonderim_at=None, updated_at=_now(), surum=r.surum + 1,
            hata=f"{prefix} ({user}): {note}" if note else None))
    return get_run(engine, tenant, run_id)


def cancel(engine: sa.engine.Engine, tenant: str, user: str, run_id: str, body: dict[str, Any]) -> dict[str, Any]:
    note = _text(body.get("note"), 1000)
    with engine.begin() as c:
        r = _get_run(c, tenant, run_id, lock=True)
        if r.durum not in ("taslak", "hesaplandi", "onayda"):
            raise RoyaltyError(f"«{RUN_STATUSES[r.durum]}» koşu iptal edilmez." +
                               (" Onaylı koşunun hakedişleri sözleşme sayfasından tek tek iptal edilir." if r.durum == "onayli" else ""), 409)
        if r.durum != "taslak" and not note:
            raise RoyaltyError("İptal gerekçesini yazın.")
        done = c.execute(sa.select(sa.func.count()).select_from(LINES).where(LINES.c.run_id == run_id,
                                                                             LINES.c.statement_id.is_not(None))).scalar()
        if done:
            raise RoyaltyError("Onay yarıda kaldı, hakediş oluştu; koşu iptal edilemez, onayı tamamlayın.", 409)
        c.execute(RUNS.update().where(RUNS.c.id == r.id).values(
            durum="iptal", updated_at=_now(), surum=r.surum + 1,
            not_=((r.not_ + "\n") if r.not_ else "") + f"İptal ({user}): {note or 'taslak'}"))
    return get_run(engine, tenant, run_id)


def mark_approving(engine: sa.engine.Engine, tenant: str, user: str, run_id: str) -> dict[str, Any]:
    """İki göz: hesaplatan ve onaya gönderen onaylayamaz."""
    with engine.begin() as c:
        r = _get_run(c, tenant, run_id, lock=True)
        if r.durum != "onayda":
            raise RoyaltyError(f"Koşu «{RUN_STATUSES[r.durum]}»; onayda değil.", 409)
        if user in (r.hazirlayan, r.gonderen):
            raise RoyaltyError("Koşuyu hesaplatan ya da onaya gönderen kişi onaylayamaz (iki göz kuralı).", 403)
        c.execute(RUNS.update().where(RUNS.c.id == r.id).values(
            durum="onaylaniyor", onaylayan=user, hata=None, updated_at=_now(), surum=r.surum + 1,
            ilerleme_json={"step": "Hakedişler oluşturuluyor", "done": 0, "at": _iso(_now())}))
    return get_run(engine, tenant, run_id)


def approve_run(engine: sa.engine.Engine, tenant: str, run_id: str, approver: str) -> dict[str, Any]:
    """Onay işi: her «hesaplandı» satırı için M6 hakedişi (taslak → onay) ve ödeme takvimi satırı. Yarıda kalırsa tekrar
    başlatılır; hakedişi oluşmuş satır atlanır. Sözleşme hesaptan sonra portalda değiştiyse o satır hata yazar."""
    with engine.connect() as c:
        run = _get_run(c, tenant, run_id)
        todo = c.execute(sa.select(LINES).where(LINES.c.run_id == run_id, LINES.c.durum == "hesaplandi",
                                                LINES.c.statement_id.is_(None))).all()
    preparer = run.hazirlayan or run.olusturan
    note = f"{run.no} telif dönemi koşusu ({period_label(run.donem_bas, run.donem_bit)})"
    errors = 0
    for i, ln in enumerate(todo):
        err = None
        sid = None
        rec: Optional[dict[str, Any]] = None
        try:
            rid = ln.contract_id
            rec = C.find(engine, tenant, ln.crm_id or rid) if (ln.crm_id or rid) else None
            if rec is None and ln.crm_id:
                crm = ln.crm_json or {}
                rec = C.adopt_crm(engine, tenant, preparer, ln.crm_id, {"no": crm.get("no"), "status": crm.get("status") or "yururlukte",
                                                                        "terms": ln.terms_json})
            if rec is None:
                raise RoyaltyError("Sözleşme portalda bulunamadı.")
            if T.diff(ln.terms_json or {}, rec["terms"] or {}):
                raise RoyaltyError("Sözleşme hesaptan sonra değişti; koşuyu yeniden hesaplatın ya da satırı hariç tutun.")
            st = C.save_statement(engine, tenant, preparer, rec["id"], ln.calc_json, note)
            st = C.approve_statement(engine, tenant, approver, st["id"], {})
            sid = st["id"]
        except (T.ContractError, RoyaltyError) as e:
            err = str(e)
        except Exception as e:  # noqa: BLE001 — tek sözleşmenin hatası bütün koşuyu durdurmaz
            log.exception("royalty: onay satırı %s", ln.contract_key)
            err = f"Beklenmeyen hata: {str(e)[:300]}"
        with engine.begin() as c:
            c.execute(LINES.update().where(LINES.c.id == ln.id).values(statement_id=sid, onay_hatasi=err,
                                                                       contract_id=(rec or {}).get("id") if not err else ln.contract_id))
        errors += 1 if err else 0
        if (i + 1) % 100 == 0:
            _progress(engine, run_id, done=i + 1, total=len(todo))
    with engine.begin() as c:
        left = c.execute(sa.select(sa.func.count()).select_from(LINES).where(
            LINES.c.run_id == run_id, LINES.c.durum == "hesaplandi", LINES.c.statement_id.is_(None))).scalar()
        if left:
            c.execute(RUNS.update().where(RUNS.c.id == run_id).values(
                durum="onayda", updated_at=_now(),
                hata=f"{left} sözleşmede hakediş oluşturulamadı (satırlarda nedeni yazıyor). Düzeltip onayı yeniden başlatın ya da "
                     "o satırları gerekçesiyle hariç tutun; oluşan hakedişler tekrar yapılmaz."))
        else:
            c.execute(RUNS.update().where(RUNS.c.id == run_id).values(
                durum="onayli", onay_at=_now(), hata=None, updated_at=_now(),
                ilerleme_json={"step": "Bitti", "done": len(todo), "total": len(todo), "at": _iso(_now())}))
    if not left:
        build_party_statements(engine, tenant, run_id)
    return get_run(engine, tenant, run_id)


# ------------------------------------------------------------------------------------------ hak sahipleri

def party_shares(ln: dict[str, Any]) -> dict[str, float]:
    """Satırdaki her hak sahibinin payı (0–1): hesap satırlarındaki telifinin toplam içindeki oranı; telif sıfırsa
    sözleşmedeki pay, o da yoksa eşit."""
    calc = ln.get("calc") or {}
    parties = ln.get("parties") or []
    by_name: dict[str, float] = {}
    for x in calc.get("lines") or []:
        by_name[x.get("party")] = by_name.get(x.get("party"), 0.0) + float(x.get("royalty") or 0)
    tot = sum(by_name.values())
    out: dict[str, float] = {}
    if tot:
        for p in parties:
            out[p["key"]] = out.get(p["key"], 0.0) + by_name.get(p["name"], 0.0) / tot
        return out
    shares = [float(p.get("share") or 0) for p in parties]
    if sum(shares):
        return {p["key"]: float(p.get("share") or 0) / sum(shares) for p in parties}
    return {p["key"]: 1 / len(parties) for p in parties} if parties else {}


def party_totals(lines_: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Onaylı satırlardan hak sahibi → {ad, tür, e-posta, sözleşmeler, para birimine göre toplam}."""
    out: dict[str, dict[str, Any]] = {}
    for ln in lines_:
        shares = party_shares(ln)
        calc = ln.get("calc") or {}
        cur = calc.get("currency") or ln.get("currency") or "TRY"
        for p in ln.get("parties") or []:
            f = shares.get(p["key"], 0.0)
            acc = out.setdefault(p["key"], {"key": p["key"], "name": p["name"], "type": p.get("type"), "email": p.get("email"),
                                            "contracts": [], "totals": {}})
            acc["email"] = acc["email"] or p.get("email")
            t = acc["totals"].setdefault(cur, {"gross": 0.0, "advance": 0.0, "withholding": 0.0, "net": 0.0})
            part = {k: round(float(calc.get(src) or 0) * f, 2) for k, src in
                    (("gross", "gross"), ("advance", "advanceOffset"), ("withholding", "withholding"), ("net", "net"))}
            for k, v in part.items():
                t[k] = round(t[k] + v, 2)
            acc["contracts"].append({"lineId": ln.get("id"), "no": ln.get("no"), "title": ln.get("title"), "share": round(f, 6),
                                     "currency": cur, **part})
    return out


def _approved_lines(c: sa.engine.Connection, tenant: str, run_id: str) -> list[dict[str, Any]]:
    rows = c.execute(sa.select(LINES).where(LINES.c.run_id == run_id, LINES.c.tenant_id == tenant,
                                            LINES.c.durum == "hesaplandi", LINES.c.statement_id.is_not(None))
                     .order_by(LINES.c.no)).all()
    return [{"id": r.id, "no": r.no, "title": r.baslik, "parties": r.taraflar or [], "calc": r.calc_json or {},
             "currency": r.para, "terms": r.terms_json or {}, "statementId": r.statement_id} for r in rows]


def build_party_statements(engine: sa.engine.Engine, tenant: str, run_id: str) -> int:
    with engine.begin() as c:
        tot = party_totals(_approved_lines(c, tenant, run_id))
        have = {r.party_key for r in c.execute(sa.select(PARTIES.c.party_key).where(PARTIES.c.run_id == run_id)).all()}
        rows = [{"run_id": run_id, "tenant_id": tenant, "party_key": k, "ad": (v["name"] or "")[:300], "tur": v["type"],
                 "eposta": v["email"], "toplam_json": v["totals"], "sozlesme_sayisi": len(v["contracts"]), "durum": "hazir"}
                for k, v in tot.items() if k not in have]
        if rows:
            c.execute(PARTIES.insert(), rows)
    return len(rows)


def _party(r: Any, show_email: bool) -> dict[str, Any]:
    return {"key": r.party_key, "name": r.ad, "type": r.tur, "email": r.eposta if show_email else mask_email(r.eposta),
            "hasEmail": bool(r.eposta), "totals": r.toplam_json or {}, "contracts": r.sozlesme_sayisi, "status": r.durum,
            "channel": r.kanal, "note": r.not_, "sentBy": r.gonderen, "sentAt": _iso(r.gonderim_at), "docHash": r.belge_hash}


def parties(engine: sa.engine.Engine, tenant: str, run_id: str, *, q: str = "", status: str = "", show_email: bool = False,
            page: int = 0) -> dict[str, Any]:
    with engine.connect() as c:
        run = _get_run(c, tenant, run_id)
        rows = c.execute(sa.select(PARTIES).where(PARTIES.c.run_id == run_id, PARTIES.c.tenant_id == tenant)
                         .order_by(PARTIES.c.ad)).all()
    needle = fold(q)
    items = [r for r in rows if (not needle or needle in fold(r.ad)) and (not status or r.durum == status)]
    n = max(0, int(page or 0))
    return {"items": [_party(r, show_email) for r in items[n * PAGE:(n + 1) * PAGE]], "total": len(items), "page": n,
            "pageSize": PAGE, "ready": run.durum == "onayli",
            "sent": sum(1 for r in rows if r.durum == "gonderildi"), "all": len(rows)}


def party_statement_text(run: dict[str, Any], party: dict[str, Any], contracts: list[dict[str, Any]],
                         lines_by_id: dict[int, dict[str, Any]]) -> str:
    """Birleşik telif beyannamesi (metin → Word). Rakamlar hesap sonucundan kopyalanır; model yok."""
    out = [f"# Telif beyannamesi", f"{party['name']}",
           f"Dönem: {period_label(run['periodStart'], run['periodEnd'])} · Koşu {run['no']}", ""]
    out.append("## Özet")
    for cur, t in sorted((party.get("totals") or {}).items()):
        out.append(f"{T.CURRENCIES.get(cur, cur)}: brüt telif {_money(t['gross'], cur)} · avans mahsubu {_money(t['advance'], cur)}"
                   f" · stopaj {_money(t['withholding'], cur)} · ödenecek {_money(t['net'], cur)}")
    out.append("")
    for ct in contracts:
        ln = lines_by_id.get(ct["lineId"]) or {}
        calc = ln.get("calc") or {}
        cur = ct["currency"]
        out.append(f"## {ct['no']} — {ct['title']}")
        body = [f"Payınız: %{T.fmt_num(ct['share'] * 100)}"]
        mine = [x for x in calc.get("lines") or [] if x.get("party") == party["name"]] or calc.get("lines") or []
        for x in mine:
            ret = f", iade {T.fmt_num(x.get('returns'), 0)}" if x.get("returns") else ""
            body.append(f"{x.get('book')}: {T.fmt_num(x.get('quantity'), 0)} adet{ret} · matrah {_money(x.get('base'))}"
                        f" · oran %{T.fmt_num(x.get('rate'))} · telif {_money(x.get('royalty'))}")
        if calc.get("fx"):
            body.append(f"Kur: {T.fmt_num(calc['fx']['rate'], 4)} ({T.day_tr(calc['fx'].get('on'))}, {calc['fx'].get('source')})")
        body.append(f"Brüt {_money(ct['gross'], cur)} · avans mahsubu {_money(ct['advance'], cur)} · stopaj "
                    f"{_money(ct['withholding'], cur)} · ödenecek {_money(ct['net'], cur)}")
        if calc.get("advanceRemaining") is not None:
            body.append(f"Sözleşmede kalan (kazanılmamış) avans: {_money(calc['advanceRemaining'], calc.get('contractCurrency') or cur)}")
        if calc.get("carryOut"):
            body.append(f"Sonraki döneme devreden: {_money(calc['carryOut'], cur)}")
        out.append("\n".join(body))
        out.append("")
    de = run.get("dataEnd")
    out.append("Satış adetleri Logo'daki faturalı satışlardan okunmuştur" + (f"; veri {T.day_tr(de)} gününe kadardır." if de else "."))
    return "\n".join(out)


def party_document(engine: sa.engine.Engine, tenant: str, run_id: str, key: str) -> tuple[bytes, str, str]:
    """(Word baytları, dosya adı, belge özeti). Yalnız onaylı koşudan."""
    run = get_run(engine, tenant, run_id)
    if run["status"] != "onayli":
        raise RoyaltyError("Beyanname yalnız onaylı koşudan üretilir.", 409)
    with engine.connect() as c:
        lines_ = _approved_lines(c, tenant, run_id)
    tot = party_totals(lines_)
    if key not in tot:
        raise RoyaltyError("Hak sahibi bu koşuda yok.", 404)
    p = tot[key]
    text = party_statement_text(run, p, p["contracts"], {ln["id"]: ln for ln in lines_})
    data = D.docx_from_text(text, f"Telif beyannamesi {p['name']}")
    name = re.sub(r"[^\w.-]+", "_", f"{run['no']} beyanname {p['name']}", flags=re.UNICODE).strip("_")[:120] + ".docx"
    digest = hashlib.sha256(text.encode()).hexdigest()
    with engine.begin() as c:
        c.execute(PARTIES.update().where(PARTIES.c.run_id == run_id, PARTIES.c.party_key == key).values(belge_hash=digest))
    return data, name, digest


def statements_zip(engine: sa.engine.Engine, tenant: str, run_id: str) -> tuple[bytes, str]:
    run = get_run(engine, tenant, run_id)
    if run["status"] != "onayli":
        raise RoyaltyError("Beyannameler yalnız onaylı koşudan üretilir.", 409)
    with engine.connect() as c:
        lines_ = _approved_lines(c, tenant, run_id)
    by_id = {ln["id"]: ln for ln in lines_}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        used: set[str] = set()
        for key, p in sorted(party_totals(lines_).items(), key=lambda kv: fold(kv[1]["name"])):
            text = party_statement_text(run, p, p["contracts"], by_id)
            base = re.sub(r"[^\w.-]+", "_", p["name"] or key, flags=re.UNICODE).strip("_")[:80] or "hak_sahibi"
            name, k = base, 2
            while name in used:
                name, k = f"{base}_{k}", k + 1
            used.add(name)
            z.writestr(f"{name}.docx", D.docx_from_text(text, f"Telif beyannamesi {p['name']}"))
    return buf.getvalue(), f"{run['no']}_beyannameler.zip"


def mark_sent(engine: sa.engine.Engine, tenant: str, user: str, run_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """Beyannamenin gönderildiğini kaydeder (gönderimi insan kendi e-postasıyla yapar). `keys`: hak sahipleri."""
    keys = [str(k) for k in (body.get("keys") or []) if k]
    channel = str(body.get("channel") or "eposta")
    if channel not in ("eposta", "posta", "elden"):
        raise RoyaltyError("Geçersiz gönderim kanalı.")
    if not keys:
        raise RoyaltyError("En az bir hak sahibi seçin.")
    note = _text(body.get("note"), 500) or None
    undo = bool(body.get("undo"))
    with engine.begin() as c:
        run = _get_run(c, tenant, run_id)
        if run.durum != "onayli":
            raise RoyaltyError("Koşu onaylı değil.", 409)
        q = PARTIES.update().where(PARTIES.c.run_id == run_id, PARTIES.c.party_key.in_(keys))
        values = ({"durum": "hazir", "kanal": None, "gonderen": None, "gonderim_at": None, "not_": note} if undo else
                  {"durum": "gonderildi", "kanal": channel, "gonderen": user, "gonderim_at": _now(), "not_": note})
        n = c.execute(q.values(**values)).rowcount
    return {"updated": n}


# ------------------------------------------------------------------------------------------ ödeme listesi

def _csv(header: list[str], rows: Iterable[list[Any]]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(header)
    for r in rows:
        w.writerow(["" if v is None else (f"{v:.2f}".replace(".", ",") if isinstance(v, float) else v) for v in r])
    return ("﻿" + buf.getvalue()).encode("utf-8")


def payment_rows(engine: sa.engine.Engine, tenant: str, run_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    run = get_run(engine, tenant, run_id)
    if run["status"] != "onayli":
        raise RoyaltyError("Ödeme listesi onaylı koşudan üretilir.", 409)
    with engine.connect() as c:
        lines_ = _approved_lines(c, tenant, run_id)
        pay = {r.statement_id: r for r in c.execute(sa.select(C.PAYMENTS.c.statement_id, C.PAYMENTS.c.due_on, C.PAYMENTS.c.status)
                                                     .where(C.PAYMENTS.c.tenant_id == tenant, C.PAYMENTS.c.statement_id.in_(
                                                         [ln["statementId"] for ln in lines_] or ["-"]))).all()}
    out = []
    for ln in lines_:
        shares = party_shares(ln)
        calc = ln["calc"]
        cur = calc.get("currency") or ln["currency"] or "TRY"
        p = pay.get(ln["statementId"])
        for pt in ln["parties"]:
            f = shares.get(pt["key"], 0.0)
            gross, adv, wh, net = (round(float(calc.get(k) or 0) * f, 2) for k in ("gross", "advanceOffset", "withholding", "net"))
            out.append({"party": pt["name"], "type": pt.get("type"), "contractNo": ln["no"], "contract": ln["title"],
                        "currency": cur, "share": round(f * 100, 4), "gross": gross, "advance": adv,
                        "withholdingPct": calc.get("withholdingPct"),
                        "withholding": wh, "net": net, "dueOn": p.due_on if p else None, "paymentStatus": p.status if p else None})
    return run, out


def payments_csv(engine: sa.engine.Engine, tenant: str, run_id: str) -> tuple[bytes, str]:
    run, rows = payment_rows(engine, tenant, run_id)
    header = ["Hak sahibi", "Kişi/Firma", "Sözleşme no", "Sözleşme", "Para birimi", "Pay (%)", "Brüt telif", "Avans mahsubu",
              "Stopaj", "Ödenecek net", "Vade", "IBAN (muhasebe doldurur)"]
    data = _csv(header, ([r["party"], {"kisi": "Kişi", "firma": "Firma"}.get(r["type"] or "", ""), r["contractNo"], r["contract"],
                          r["currency"], r["share"], r["gross"], r["advance"], r["withholding"], r["net"], r["dueOn"], ""]
                         for r in rows if r["net"] > 0))
    return data, f"{run['no']}_odeme_listesi.csv"


def withholding_csv(engine: sa.engine.Engine, tenant: str, run_id: str) -> tuple[bytes, str]:
    """Muhtasar için: hak sahibi × para birimi — stopaj matrahı, oran, stopaj."""
    run, rows = payment_rows(engine, tenant, run_id)
    acc: dict[tuple[str, str, Any], dict[str, float]] = {}
    for r in rows:
        k = (r["party"], r["currency"], r["withholdingPct"])
        t = acc.setdefault(k, {"base": 0.0, "wh": 0.0})
        t["base"] += r["net"] + r["withholding"]  # stopaj matrahı = avans ve devir sonrası tutar (M6 hesabı)
        t["wh"] += r["withholding"]
    header = ["Hak sahibi", "Para birimi", "Stopaj matrahı (avans sonrası)", "Stopaj oranı (%)", "Stopaj"]
    data = _csv(header, ([p, cur, round(v["base"], 2), pct, round(v["wh"], 2)] for (p, cur, pct), v in sorted(acc.items(), key=lambda x: fold(x[0][0]))))
    return data, f"{run['no']}_stopaj_ozeti.csv"


# ------------------------------------------------------------------------------------------ avans

def latest_run(c: sa.engine.Connection, tenant: str) -> Any:
    return c.execute(sa.select(RUNS).where(RUNS.c.tenant_id == tenant, RUNS.c.durum.in_(("hesaplandi", "onayda", "onaylaniyor", "onayli")))
                     .order_by(RUNS.c.donem_bit.desc(), RUNS.c.hesap_at.desc())).first()


def advances(engine: sa.engine.Engine, tenant: str, *, risk_years: float, q: str = "", only: str = "") -> dict[str, Any]:
    """Avanslı sözleşmelerin portföyü: son hesaplanan koşudan (şartlar, dönem telifi, kalan avans) + açılış bakiyeleri.
    Yıllık telif hızı = koşunun brüt telifi × (12 / koşu ayı); kalan avans ÷ bu hız > `risk_years` ise «geri dönmesi zor»."""
    ensure(engine)
    with engine.connect() as c:
        run = latest_run(c, tenant)
        opens = openings(c, tenant)
        rows = c.execute(sa.select(LINES.c.id, LINES.c.contract_key, LINES.c.no, LINES.c.baslik, LINES.c.durum,
                                   LINES.c.istisnalar, LINES.c.calc_json, LINES.c.terms_json, LINES.c.taraflar)
                         .where(LINES.c.run_id == run.id)).all() if run else []
    items = []
    months = run_months(run.donem_bas, run.donem_bit) if run else 6
    needle = fold(q)
    for r in rows:
        t = r.terms_json or {}
        adv = float(t.get("advance") or 0)
        if not adv:
            continue
        calc = r.calc_json or {}
        cur = t.get("currency") or "TRY"
        o = opens.get(r.contract_key)
        missing = any(e["code"] == "avans-acilis-yok" for e in r.istisnalar or [])
        remaining = calc.get("advanceRemaining") if calc else None
        gross = float(calc.get("gross") or 0) if calc else 0.0
        yearly = gross * 12 / months if months else 0.0
        years = (float(remaining) / yearly) if remaining and yearly else None
        risk = bool(remaining and remaining > 0 and (not yearly or (years or 0) > risk_years)) and not missing
        item = {"contractKey": r.contract_key, "no": r.no, "title": r.baslik, "currency": cur, "advance": adv,
                "recoupable": t.get("advanceRecoupable", True), "opening": o, "openingMissing": missing,
                "remaining": None if missing else remaining, "periodGross": gross, "yearsToRecoup": round(years, 1) if years else None,
                "risk": risk, "parties": [p.get("name") for p in r.taraflar or []], "lineStatus": r.durum, "lineId": r.id}
        if needle and needle not in fold(" ".join([r.no or "", r.baslik or ""] + item["parties"])):
            continue
        if only == "acilis-yok" and not missing:
            continue
        if only == "risk" and not risk:
            continue
        items.append(item)
    items.sort(key=lambda x: (not x["openingMissing"], not x["risk"], -(x["remaining"] or 0)))
    totals: dict[str, dict[str, float]] = {}
    for x in items:
        t = totals.setdefault(x["currency"], {"advance": 0.0, "remaining": 0.0, "missing": 0, "risk": 0})
        t["advance"] = round(t["advance"] + x["advance"], 2)
        t["remaining"] = round(t["remaining"] + float(x["remaining"] or 0), 2)
        t["missing"] += 1 if x["openingMissing"] else 0
        t["risk"] += 1 if x["risk"] else 0
    return {"run": _run(run) if run else None, "items": items, "totals": totals, "riskYears": risk_years}


def set_advance(engine: sa.engine.Engine, tenant: str, user: str, contract_key: str, body: dict[str, Any]) -> dict[str, Any]:
    """Avans açılış bakiyesi: sözleşmenin o tarihteki kazanılmamış kalan avansı. Önceki girişi geçersiz kılar (geçmişi durur)."""
    ensure(engine)
    key = (contract_key or "").lower()
    if not (_GUID.match(key) or _PID.match(key)):
        raise RoyaltyError("Sözleşme kimliği geçerli değil.")
    reason = _text(body.get("reason"), 1000)
    if not reason:
        raise RoyaltyError("Açılış bakiyesinin kaynağını yazın (ör. «2025 sonu mutabakat dosyası»).")
    remove = bool(body.get("remove"))
    amount = None
    cur = str(body.get("currency") or "TRY")
    as_of = None
    if not remove:
        try:
            amount = T._num(body.get("amount"), "Kalan avans")
            as_of = T._day(body.get("asOf"), "Açılış tarihi")
        except T.ContractError as e:
            raise RoyaltyError(str(e)) from None
        if amount is None or not as_of:
            raise RoyaltyError("Kalan avans tutarını ve hangi tarihteki bakiye olduğunu girin.")
        if cur not in T.CURRENCIES:
            raise RoyaltyError("Geçersiz para birimi.")
        if as_of > today().isoformat():
            raise RoyaltyError("Açılış tarihi ileri bir gün olamaz.")
    with engine.begin() as c:
        c.execute(ADVANCES.update().where(ADVANCES.c.tenant_id == tenant, ADVANCES.c.contract_key == key,
                                          ADVANCES.c.aktif.is_(True)).values(aktif=False))
        c.execute(ADVANCES.insert().values(tenant_id=tenant, contract_key=key, acilis_tutari=amount, para=cur,
                                           acilis_tarihi=as_of or today().isoformat(), kaynak="elle",
                                           gerekce=("Kaldırıldı: " if remove else "") + reason, giren=user, tarih=_now(),
                                           aktif=not remove))
        hist = c.execute(sa.select(ADVANCES).where(ADVANCES.c.tenant_id == tenant, ADVANCES.c.contract_key == key)
                         .order_by(ADVANCES.c.tarih.desc(), ADVANCES.c.id.desc())).all()
    return {"contractKey": key, "history": [{"amount": h.acilis_tutari, "currency": h.para, "asOf": h.acilis_tarihi,
                                             "reason": h.gerekce, "by": h.giren, "at": _iso(h.tarih), "active": bool(h.aktif)} for h in hist]}


def advance_history(engine: sa.engine.Engine, tenant: str, contract_key: str) -> list[dict[str, Any]]:
    ensure(engine)
    with engine.connect() as c:
        hist = c.execute(sa.select(ADVANCES).where(ADVANCES.c.tenant_id == tenant, ADVANCES.c.contract_key == contract_key.lower())
                         .order_by(ADVANCES.c.tarih.desc(), ADVANCES.c.id.desc())).all()
    return [{"amount": h.acilis_tutari, "currency": h.para, "asOf": h.acilis_tarihi, "reason": h.gerekce, "by": h.giren,
             "at": _iso(h.tarih), "active": bool(h.aktif)} for h in hist]


# ------------------------------------------------------------------------------------------ yenilemeler

def renewal_rows(crm_rows: list[dict[str, Any]], decisions: dict[str, Any], on: date) -> list[dict[str, Any]]:
    """CRM satırları + portal kararı. Bitiş tarihi değiştiyse (sözleşme uzatılmış) eski karar geçmiş sayılır."""
    out = []
    for r in crm_rows:
        cid = str(r.get("id") or "").strip("{}").lower()
        end = str(r.get("bit") or "")[:10] or None
        d = decisions.get(cid)
        stale = bool(d and d.bitis and end and d.bitis != end)
        days = (date.fromisoformat(end) - on).days if end else None
        out.append({
            "contractKey": cid, "no": str(r.get("no") or "").strip() or None,
            "kind": T.KINDS.get(T.KIND_FROM_CRM.get(int(r.get("tip_kod") or 0), ""), "Diğer"),
            "paymentType": T.PAYMENT_TYPES.get(T.PAYMENT_FROM_CRM.get(int(r.get("odeme_kod") or 0), ""), None),
            "start": str(r.get("bas") or "")[:10] or None, "end": end, "daysLeft": days,
            "renewEvery": r.get("yenileme_yil"), "renewStart": str(r.get("yen_bas") or "")[:10] or None,
            "renewEnd": str(r.get("yen_bit") or "")[:10] or None, "destroyMonths": r.get("imha_ay"),
            "reportPeriod": r.get("rapor_suresi"), "unpublishedTermination": str(r.get("yayinlanmama_fesih") or "")[:10] or None,
            "advance": r.get("avans"), "currency": T.CURRENCY_FROM_CRM.get(int(r.get("para_kod") or 0) if r.get("para_kod") else 1, "TRY"),
            "author": r.get("yazar"), "translator": r.get("mutercim"), "illustrator": r.get("cizer"),
            "book": r.get("kitap"), "stockCode": r.get("stok"),
            "decision": "bekliyor" if (not d or stale) else d.karar,
            "decisionLabel": RENEWAL_DECISIONS["bekliyor" if (not d or stale) else d.karar],
            "reason": None if stale or not d else d.gerekce, "decidedBy": None if stale or not d else d.karar_veren,
            "decidedAt": None if stale or not d else _iso(d.karar_at), "staleDecision": stale,
            "suggestion": ({"decision": d.oneri_karar, "probability": d.oneri_olasilik, "text": d.oneri_metni,
                            "inputs": d.oneri_girdi, "at": _iso(d.oneri_at)} if d and d.oneri_metni and not stale else None),
        })
    return out


def renewal_decisions(engine: sa.engine.Engine, tenant: str) -> dict[str, Any]:
    ensure(engine)
    with engine.connect() as c:
        return {r.contract_key: r for r in c.execute(sa.select(RENEWALS).where(RENEWALS.c.tenant_id == tenant)).all()}


def _renewal_upsert(c: sa.engine.Connection, tenant: str, key: str, values: dict[str, Any]) -> None:
    cur = c.execute(sa.select(RENEWALS).where(RENEWALS.c.tenant_id == tenant, RENEWALS.c.contract_key == key).with_for_update()).first()
    if cur:
        c.execute(RENEWALS.update().where(RENEWALS.c.id == cur.id).values(**values))
    else:
        c.execute(RENEWALS.insert().values(tenant_id=tenant, contract_key=key, karar=values.pop("karar", "bekliyor"), **values))


def decide_renewal(engine: sa.engine.Engine, tenant: str, user: str, key: str, body: dict[str, Any]) -> dict[str, Any]:
    ensure(engine)
    key = (key or "").lower()
    if not _GUID.match(key):
        raise RoyaltyError("Sözleşme kimliği geçerli değil.")
    karar = str(body.get("decision") or "")
    if karar not in RENEWAL_DECISIONS:
        raise RoyaltyError("Geçersiz karar.")
    reason = _text(body.get("reason"), 2000)
    if karar != "bekliyor" and not reason:
        raise RoyaltyError("Kararın gerekçesini yazın.")
    end = str(body.get("end") or "")[:10] or None
    with engine.begin() as c:
        cur = c.execute(sa.select(RENEWALS).where(RENEWALS.c.tenant_id == tenant, RENEWALS.c.contract_key == key)).first()
        hist = list((cur.gecmis if cur else None) or [])
        if cur and cur.karar != "bekliyor":
            hist.append({"decision": cur.karar, "reason": cur.gerekce, "by": cur.karar_veren, "at": _iso(cur.karar_at), "end": cur.bitis})
        _renewal_upsert(c, tenant, key, {"karar": karar, "gerekce": reason or None, "karar_veren": user, "karar_at": _now(),
                                          "bitis": end, "no": _text(body.get("no"), 120) or (cur.no if cur else None),
                                          "gecmis": hist[-50:]})
    return {"contractKey": key, "decision": karar, "decisionLabel": RENEWAL_DECISIONS[karar], "reason": reason or None,
            "decidedBy": user}


def save_renewal_suggestion(engine: sa.engine.Engine, tenant: str, key: str, end: Optional[str], sug: dict[str, Any]) -> None:
    with engine.begin() as c:
        _renewal_upsert(c, tenant, key, {"oneri_karar": sug.get("decision"), "oneri_olasilik": sug.get("probability"),
                                          "oneri_metni": sug.get("text"), "oneri_girdi": sug.get("inputs"), "oneri_at": _now(),
                                          "bitis": end})


def renewal_prompt(facts: dict[str, Any]) -> str:
    lines_ = [f"- {k}: {v}" for k, v in facts.items() if v not in (None, "", [])]
    return ("Bir yayınevinin telif birimi için sözleşme yenileme kararına gerekçe yazıyorsun. Aşağıdaki olgular "
            "dışında bilgi kullanma, yeni rakam üretme; olgulardaki rakamları aynen kullan. En çok üç kısa Türkçe cümle "
            "yaz; kararı sen vermiyorsun, yayın yönetmenine gerekçe öneriyorsun.\n\nOlgular:\n" + "\n".join(lines_))


# ------------------------------------------------------------------------------------------ haklar

def rights_summary(contracts: list[dict[str, Any]], on: date, licenses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Hak türü başına durum (yürürlükteki Telif Alış sözleşmelerinin hepsinde hak varsa «var»). Kural SEO «Haklar ve CRM»
    ile aynı: `seo_geo.crm.in_force` ve serbest metinli not → «incele»."""
    from semantic_bridge.seo_geo import crm as seo_crm

    live = [c for c in contracts if c.get("kind") == "alis" and seo_crm.in_force(c, on)]
    out = []
    for key, label in S.RIGHT_LABELS.items():
        if not live:
            state, why = ("koruma-disi", "Koruma dışı eser.") if any(c.get("public_domain") for c in contracts) else \
                ("sozlesme-yok", "Yürürlükte telif alış sözleşmesi yok.")
        else:
            miss = [c for c in live if not c["rights"].get(key)]
            if miss:
                state, why = "yok", "Şu sözleşmede yok: " + ", ".join(c.get("no") or "?" for c in miss)
            elif any(c.get("rights_note") for c in live):
                state, why = "incele", "Hak notu var; sözleşmeye bakılmalı."
            else:
                state, why = "var", "Yürürlükteki bütün telif alış sözleşmelerinde var."
        out.append({"key": key, "label": label, "state": state, "why": why})
    sold = [x for x in licenses if x.get("status") in ("imzalandi",) and (not x.get("end") or x["end"] >= on.isoformat())]
    return out + ([{"key": "lisans", "label": "Verilmiş lisanslar", "state": "var" if sold else "yok",
                    "why": ", ".join(f"{x.get('language') or '?'} / {x.get('country') or '?'} → {x.get('buyer')}" for x in sold) or "Yürürlükte verilmiş lisans yok."}])


def _grant(r: Any) -> dict[str, Any]:
    return {"id": r.id, "bookId": r.kitap_id, "stockCode": r.kitap_stok_kodu, "kind": r.hak_turu,
            "kindLabel": GRANT_KINDS.get(r.hak_turu, r.hak_turu), "language": r.dil, "country": r.ulke, "start": r.bas, "end": r.bit,
            "source": r.kaynak, "contractKey": r.contract_key, "note": r.not_, "by": r.giren, "at": _iso(r.tarih)}


def grants(engine: sa.engine.Engine, tenant: str, book_id: str) -> list[dict[str, Any]]:
    ensure(engine)
    with engine.connect() as c:
        rows = c.execute(sa.select(GRANTS).where(GRANTS.c.tenant_id == tenant, GRANTS.c.kitap_id == book_id.lower())
                         .order_by(GRANTS.c.hak_turu, GRANTS.c.dil, GRANTS.c.ulke)).all()
    return [_grant(r) for r in rows]


def _grant_fields(body: dict[str, Any]) -> dict[str, Any]:
    kind = str(body.get("kind") or "")
    if kind not in GRANT_KINDS:
        raise RoyaltyError("Geçersiz hak türü.")
    try:
        start = T._day(body.get("start"), "Başlangıç")
        end = T._day(body.get("end"), "Bitiş")
    except T.ContractError as e:
        raise RoyaltyError(str(e)) from None
    if start and end and end < start:
        raise RoyaltyError("Bitiş başlangıçtan önce olamaz.")
    ck = str(body.get("contractKey") or "").lower() or None
    if ck and not (_GUID.match(ck) or _PID.match(ck)):
        raise RoyaltyError("Sözleşme kimliği geçerli değil.")
    return {"hak_turu": kind, "dil": _text(body.get("language"), 80) or None, "ulke": _text(body.get("country"), 120) or None,
            "bas": start, "bit": end, "contract_key": ck, "not_": str(body.get("note") or "").strip()[:2000] or None,
            "kitap_stok_kodu": _text(body.get("stockCode"), 60) or None}


def save_grant(engine: sa.engine.Engine, tenant: str, user: str, body: dict[str, Any], grant_id: Optional[int] = None) -> dict[str, Any]:
    ensure(engine)
    f = _grant_fields(body)
    with engine.begin() as c:
        if grant_id is None:
            book = str(body.get("bookId") or "").lower()
            if not _GUID.match(book):
                raise RoyaltyError("Kitap kimliği geçerli değil.")
            gid = c.execute(GRANTS.insert().values(tenant_id=tenant, kitap_id=book, kaynak="portal", giren=user, tarih=_now(), **f)
                            ).inserted_primary_key[0]
        else:
            r = c.execute(sa.select(GRANTS).where(GRANTS.c.tenant_id == tenant, GRANTS.c.id == int(grant_id))).first()
            if not r:
                raise RoyaltyError("Hak kaydı bulunamadı.", 404)
            c.execute(GRANTS.update().where(GRANTS.c.id == r.id).values(giren=user, tarih=_now(), **f))
            gid = r.id
        row = c.execute(sa.select(GRANTS).where(GRANTS.c.id == gid)).first()
    return _grant(row)


def delete_grant(engine: sa.engine.Engine, tenant: str, grant_id: int) -> dict[str, Any]:
    with engine.begin() as c:
        r = c.execute(sa.select(GRANTS).where(GRANTS.c.tenant_id == tenant, GRANTS.c.id == int(grant_id))).first()
        if not r:
            raise RoyaltyError("Hak kaydı bulunamadı.", 404)
        c.execute(GRANTS.delete().where(GRANTS.c.id == r.id))
    return _grant(r)


def _license(r: Any) -> dict[str, Any]:
    return {"id": r.id, "bookId": r.kitap_id, "book": r.kitap, "buyer": r.alici_yayinevi, "language": r.dil, "country": r.ulke,
            "advance": r.avans, "rate": r.oran, "currency": r.para, "start": r.bas, "end": r.bit, "status": r.durum,
            "statusLabel": LICENSE_STATUSES.get(r.durum), "collection": r.tahsilat_durumu,
            "collectionLabel": COLLECTION_STATUSES.get(r.tahsilat_durumu or ""), "collected": r.tahsilat_tutari,
            "authorSharePct": r.yazar_payi_yuzde,
            "authorShare": round(float(r.tahsilat_tutari or 0) * float(r.yazar_payi_yuzde or 0) / 100, 2) if r.yazar_payi_yuzde else None,
            "crmContractId": r.crm_contract_id, "note": r.not_, "by": r.giren, "at": _iso(r.tarih),
            "updatedBy": r.guncelleyen, "updatedAt": _iso(r.guncelleme_at)}


def licenses(engine: sa.engine.Engine, tenant: str, *, book_id: str = "", q: str = "", status: str = "") -> list[dict[str, Any]]:
    ensure(engine)
    stmt = sa.select(LICENSES).where(LICENSES.c.tenant_id == tenant)
    if book_id:
        stmt = stmt.where(LICENSES.c.kitap_id == book_id.lower())
    if status:
        stmt = stmt.where(LICENSES.c.durum == status)
    with engine.connect() as c:
        rows = c.execute(stmt.order_by(LICENSES.c.tarih.desc())).all()
    needle = fold(q)
    return [_license(r) for r in rows if not needle or needle in fold(" ".join(str(x or "") for x in (r.kitap, r.alici_yayinevi, r.dil, r.ulke)))]


def _license_fields(body: dict[str, Any], partial: bool) -> dict[str, Any]:
    out: dict[str, Any] = {}

    def has(k: str) -> bool:
        return not partial or k in body
    try:
        if has("book"):
            out["kitap"] = _text(body.get("book"), 400)
            if not out["kitap"]:
                raise RoyaltyError("Kitap adını girin.")
        if has("bookId"):
            b = str(body.get("bookId") or "").lower() or None
            if b and not _GUID.match(b):
                raise RoyaltyError("Kitap kimliği geçerli değil.")
            out["kitap_id"] = b
        if has("buyer"):
            out["alici_yayinevi"] = _text(body.get("buyer"), 300)
            if not out["alici_yayinevi"]:
                raise RoyaltyError("Lisansı alan yayınevini girin.")
        for k, col, n in (("language", "dil", 80), ("country", "ulke", 120)):
            if has(k):
                out[col] = _text(body.get(k), n) or None
        if has("advance"):
            out["avans"] = T._num(body.get("advance"), "Avans")
        if has("rate"):
            out["oran"] = T._num(body.get("rate"), "Oran", hi=100)
        if has("authorSharePct"):
            out["yazar_payi_yuzde"] = T._num(body.get("authorSharePct"), "Yazar payı", hi=100)
        if has("collected"):
            out["tahsilat_tutari"] = T._num(body.get("collected"), "Tahsil edilen")
        if has("currency"):
            cur = str(body.get("currency") or "USD")
            if cur not in T.CURRENCIES:
                raise RoyaltyError("Geçersiz para birimi.")
            out["para"] = cur
        if has("start"):
            out["bas"] = T._day(body.get("start"), "Başlangıç")
        if has("end"):
            out["bit"] = T._day(body.get("end"), "Bitiş")
        if has("status"):
            st = str(body.get("status") or "gorusme")
            if st not in LICENSE_STATUSES:
                raise RoyaltyError("Geçersiz lisans durumu.")
            out["durum"] = st
        if has("collection"):
            cs = str(body.get("collection") or "") or None
            if cs and cs not in COLLECTION_STATUSES:
                raise RoyaltyError("Geçersiz tahsilat durumu.")
            out["tahsilat_durumu"] = cs
        if has("crmContractId"):
            cc = str(body.get("crmContractId") or "").lower() or None
            if cc and not _GUID.match(cc):
                raise RoyaltyError("CRM sözleşme kimliği geçerli değil.")
            out["crm_contract_id"] = cc
        if has("note"):
            out["not_"] = str(body.get("note") or "").strip()[:4000] or None
    except T.ContractError as e:
        raise RoyaltyError(str(e)) from None
    if out.get("bas") and out.get("bit") and out["bit"] < out["bas"]:
        raise RoyaltyError("Bitiş başlangıçtan önce olamaz.")
    return out


def save_license(engine: sa.engine.Engine, tenant: str, user: str, body: dict[str, Any], license_id: Optional[int] = None) -> dict[str, Any]:
    ensure(engine)
    with engine.begin() as c:
        if license_id is None:
            f = _license_fields(body, partial=False)
            lid = c.execute(LICENSES.insert().values(tenant_id=tenant, giren=user, tarih=_now(), **f)).inserted_primary_key[0]
        else:
            r = c.execute(sa.select(LICENSES).where(LICENSES.c.tenant_id == tenant, LICENSES.c.id == int(license_id))).first()
            if not r:
                raise RoyaltyError("Lisans kaydı bulunamadı.", 404)
            f = _license_fields(body, partial=True)
            c.execute(LICENSES.update().where(LICENSES.c.id == r.id).values(guncelleyen=user, guncelleme_at=_now(), **f))
            lid = r.id
        row = c.execute(sa.select(LICENSES).where(LICENSES.c.id == lid)).first()
    return _license(row)


def _note(r: Any) -> dict[str, Any]:
    return {"id": r.id, "contractKey": r.contract_key, "no": r.no, "book": r.kitap, "text": r.metin, "class": r.sinif,
            "classLabel": NOTE_CLASSES.get(r.sinif or ""), "probability": r.olasilik, "margin": r.marj, "method": r.yontem,
            "status": r.durum, "approvedBy": r.onaylayan, "approvedAt": _iso(r.onay_at), "at": _iso(r.tarih)}


def notes(engine: sa.engine.Engine, tenant: str, *, status: str = "", cls: str = "", q: str = "", page: int = 0) -> dict[str, Any]:
    ensure(engine)
    stmt = sa.select(NOTES).where(NOTES.c.tenant_id == tenant)
    if status:
        stmt = stmt.where(NOTES.c.durum == status)
    if cls:
        stmt = stmt.where(NOTES.c.sinif == cls)
    with engine.connect() as c:
        rows = c.execute(stmt.order_by(NOTES.c.durum, NOTES.c.no)).all()
    needle = fold(q)
    items = [r for r in rows if not needle or needle in fold(" ".join(str(x or "") for x in (r.no, r.kitap, r.metin)))]
    n = max(0, int(page or 0))
    counts: dict[str, int] = {}
    for r in rows:
        counts[r.durum] = counts.get(r.durum, 0) + 1
    return {"items": [_note(r) for r in items[n * PAGE:(n + 1) * PAGE]], "total": len(items), "page": n, "pageSize": PAGE,
            "counts": counts}


def note_hash(text: str) -> str:
    return hashlib.sha256(" ".join(str(text or "").split()).encode()).hexdigest()


def pending_notes(engine: sa.engine.Engine, tenant: str, crm_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sınıflanacaklar: yeni ya da metni değişmiş hak açıklamaları (onaylı ve aynı metinli kayıt yeniden sorulmaz)."""
    ensure(engine)
    with engine.connect() as c:
        have = {r.contract_key: r.metin_hash for r in c.execute(sa.select(NOTES.c.contract_key, NOTES.c.metin_hash)
                                                                .where(NOTES.c.tenant_id == tenant)).all()}
    out = []
    for r in crm_rows:
        key = str(r.get("id") or "").strip("{}").lower()
        text = str(r.get("metin") or "").strip()
        if key and text and have.get(key) != note_hash(text):
            out.append({"key": key, "no": r.get("no"), "book": r.get("kitap"), "text": text})
    return out


def save_note(engine: sa.engine.Engine, tenant: str, item: dict[str, Any], choice: dict[str, Any], thresholds: tuple[float, float]) -> None:
    """Sınıf önerisi: olasılık ≥ eşik ve marj ≥ eşik ise «öneri», değilse «incele». Onayı insan verir."""
    p, m = choice.get("probability"), choice.get("margin")
    sure = p is not None and m is not None and p >= thresholds[0] and m >= thresholds[1]
    values = {"no": _text(item.get("no"), 120), "kitap": _text(item.get("book"), 400), "metin": item["text"][:8000],
              "metin_hash": note_hash(item["text"]), "sinif": choice.get("class"), "olasilik": p, "marj": m,
              "yontem": choice.get("method"), "durum": "oneri" if sure else "incele", "onaylayan": None, "onay_at": None,
              "tarih": _now()}
    with engine.begin() as c:
        cur = c.execute(sa.select(NOTES.c.id).where(NOTES.c.tenant_id == tenant, NOTES.c.contract_key == item["key"])).first()
        if cur:
            c.execute(NOTES.update().where(NOTES.c.id == cur.id).values(**values))
        else:
            c.execute(NOTES.insert().values(tenant_id=tenant, contract_key=item["key"], **values))


def approve_note(engine: sa.engine.Engine, tenant: str, user: str, note_id: int, body: dict[str, Any]) -> dict[str, Any]:
    cls = str(body.get("class") or "")
    with engine.begin() as c:
        r = c.execute(sa.select(NOTES).where(NOTES.c.tenant_id == tenant, NOTES.c.id == int(note_id))).first()
        if not r:
            raise RoyaltyError("Hak açıklaması bulunamadı.", 404)
        cls = cls or r.sinif
        if cls not in NOTE_CLASSES:
            raise RoyaltyError("Sınıf seçin.")
        c.execute(NOTES.update().where(NOTES.c.id == r.id).values(sinif=cls, durum="onayli", onaylayan=user, onay_at=_now()))
        row = c.execute(sa.select(NOTES).where(NOTES.c.id == r.id)).first()
    return _note(row)


def note_prompt(text: str) -> str:
    return ("Bir yayınevinin telif sözleşmesindeki serbest metinli hak açıklaması aşağıda. Bu açıklama hangi tür kısıt ya da "
            "şart getiriyor? Bölge kısıtı: belli ülke/dil/bölgeyle sınırlama. Format kısıtı: e-kitap, sesli kitap, baskı türü "
            "gibi biçim sınırlaması. Süre şartı: tarih ya da süreye bağlı şart. Onay şartı: hak sahibinin onayı ya da "
            "incelemesi gereken durum. Ücret şartı: ek ödeme, oran ya da bedel şartı. Diğer: bunların hiçbiri.\n\n"
            f"Açıklama: «{text[:1500]}»")


# ------------------------------------------------------------------------------------------ sözleşme sayfası

def contract_lines(engine: sa.engine.Engine, tenant: str, key: str) -> list[dict[str, Any]]:
    """Bir sözleşmenin dönem koşularındaki satırları (M6 sözleşme sayfasındaki bağlantı için)."""
    ensure(engine)
    k = (key or "").lower()
    with engine.connect() as c:
        rec = c.execute(sa.select(C.RECORDS.c.id, C.RECORDS.c.crm_id).where(
            C.RECORDS.c.tenant_id == tenant, sa.or_(C.RECORDS.c.id == k, C.RECORDS.c.crm_id == k))).first()
        keys = {k} | ({rec.id, rec.crm_id} - {None} if rec else set())
        rows = c.execute(sa.select(LINES.c.id, LINES.c.run_id, LINES.c.durum, LINES.c.istisna_kodu, LINES.c.net, LINES.c.para,
                                   LINES.c.statement_id, RUNS.c.no, RUNS.c.donem_bas, RUNS.c.donem_bit, RUNS.c.durum.label("run_durum"))
                         .join(RUNS, RUNS.c.id == LINES.c.run_id)
                         .where(LINES.c.tenant_id == tenant, LINES.c.contract_key.in_(keys), RUNS.c.durum != "iptal")
                         .order_by(RUNS.c.donem_bas.desc())).all()
    return [{"lineId": r.id, "runId": r.run_id, "runNo": r.no, "label": period_label(r.donem_bas, r.donem_bit),
             "runStatus": r.run_durum, "runStatusLabel": RUN_STATUSES.get(r.run_durum), "status": r.durum,
             "statusLabel": LINE_STATUSES.get(r.durum), "exception": EXCEPTIONS.get(r.istisna_kodu or "", ("",))[0] or None,
             "net": r.net, "currency": r.para, "statementId": r.statement_id} for r in rows]


# ------------------------------------------------------------------------------------------ bildirim kaydı

def notice_once(engine: sa.engine.Engine, tenant: str, kind: str, ref: str) -> bool:
    """Aynı bildirim bir kez: yeni kaydedildiyse True."""
    ensure(engine)
    try:
        with engine.begin() as c:
            c.execute(NOTICES.insert().values(tenant_id=tenant, tur=kind[:40], ref=ref[:80], at=_now()))
        return True
    except sa.exc.IntegrityError:
        return False


def run_exists_for(engine: sa.engine.Engine, tenant: str, a: str, b: str) -> bool:
    with engine.connect() as c:
        return bool(c.execute(sa.select(RUNS.c.id).where(RUNS.c.tenant_id == tenant, RUNS.c.durum != "iptal",
                                                         RUNS.c.donem_bas <= b, RUNS.c.donem_bit >= a)).first())


def workdays_after(d: date, n: int) -> date:
    x = d
    while n > 0:
        x += timedelta(days=1)
        if x.weekday() < 5:
            n -= 1
    return x
