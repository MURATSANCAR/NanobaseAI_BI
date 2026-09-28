"""M59 Kitapçı/bayi risk ve performans: kapsam, açıklanabilir günlük risk skoru, A/B/C/D segment, eğilim, limit önerisi,
aksiyon, brif önbelleği ve sürümlü kural.

**Akış.** Günlük tur (`run-due?tur=gunluk`, 06:00) CRM'den temsilci ↔ cari atamasını, limit/risk ve riske takılan
siparişleri, Logo'dan bakiye/FIFO yaşlandırma, çek olayı, 12 aylık satış/iade/ödeme serisini okur (M30 kaynak
fonksiyonlarıyla, `dealers_sources.py`); yürürlükteki kural sürümüyle her kapsam içi cari için bir skor satırı yazar
(`semantic_dealer_scores`, gün başına; aynı gün yeniden koşarsa o günün satırları değişir, geçmiş kalır).

**Skor (kural, model yok).** Altı bileşen 0–1 arası normalize edilir, kural sürümündeki ağırlıkla (toplam 100) çarpılıp
toplanır: ödeme gecikmesi (FIFO, yaşa göre ağırlıklı — yaklaşık), çek/senet olayı, iade oranı, CRM limit doluluğu, sipariş
düzensizliği (aylık alım değişkenliği), tahsilat süresi (DSO yaklaşımı). Her bileşen ekranda rakamıyla yazılır; «neden D»
sorusu bileşenlerle cevaplanır. Segment eşikleri grup başınadır: **anahtar hesap** (zincir, e-ticaret, dağıtıcı ya da
kapsam cirosunun belirli payından büyük) küçük kitapçıyla aynı eşikle kırmızı gösterilmez.

**Eğilim ve kötüleşme.** Ham girdiler günlük saklanır; önceki gün ve ~30 gün önceki girdiler **bugünkü kural** ile
yeniden puanlanır — kural değişince herkes birden «kötüleşmiş» görünmez. Segmenti bir önceki tura göre düşen cari
temsilcisine portal bildirimi olur (M30 bildirim tablosu).

**Yazma.** CRM'e ve Logo'ya hiçbir şey yazılmaz. Limit önerisi kuraldan çıkar (rakamı kural üretir; Zeki AI yalnız
gerekçe cümlesi yazar, cümledeki her sayı olgularda geçmek zorunda); onaylanan öneri «CRM'e işlenecek» listesinde kalır,
CRM'e insan işler. Ziyaret notu M30/M31 ortak tablosuna (`semantic_saha_ziyaret`, `tur='cari'`) yazılır; M59 ayrı not
tablosu açmaz. Okul ↔ bayi eşleştirmesi M31'dedir (`semantic_school_dealer_links`).
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import threading
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Optional
from zoneinfo import ZoneInfo

import sqlalchemy as sa

from semantic_bridge import dealers_sources as dsrc
from semantic_bridge import field_sales as F
from semantic_bridge import field_sales_sources as fsrc
from semantic_bridge.field_sales_sources import SourceError, day, guid, num, opt_num, text

log = logging.getLogger("semantic.dealers")
TZ = ZoneInfo("Europe/Istanbul")
_md = sa.MetaData()
_lock = threading.Lock()
_ready: set[int] = set()


class DealerError(RuntimeError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


# ------------------------------------------------------------------ tablolar

RULES = sa.Table(
    "semantic_dealer_rules", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("surum", sa.Integer, nullable=False),
    sa.Column("durum", sa.String(12), nullable=False),             # taslak | onayda | yururlukte | arsiv
    sa.Column("agirliklar_json", sa.Text, nullable=False),
    sa.Column("esikler_json", sa.Text, nullable=False),
    sa.Column("kapsam_json", sa.Text, nullable=False),
    sa.Column("limit_json", sa.Text, nullable=False),
    sa.Column("gerekce", sa.Text),
    sa.Column("hazirlayan", sa.String(120), nullable=False),
    sa.Column("olusturma", sa.DateTime(timezone=True), nullable=False),
    sa.Column("gonderen", sa.String(120)),
    sa.Column("gonderim", sa.DateTime(timezone=True)),
    sa.Column("onaylayan", sa.String(120)),
    sa.Column("onay_zamani", sa.DateTime(timezone=True)),
    sa.Column("karar_notu", sa.Text),
    sa.UniqueConstraint("tenant_id", "surum", name="uq_semantic_dealer_rules_surum"),
)
SCORES = sa.Table(
    "semantic_dealer_scores", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("gun", sa.String(10), primary_key=True),
    sa.Column("logo_code", sa.String(40), primary_key=True),
    sa.Column("logo_clientref", sa.Integer),
    sa.Column("crm_account_id", sa.String(40)),
    sa.Column("unvan", sa.String(300)),
    sa.Column("kanal", sa.String(60)),                             # Logo CLCARD.SPECODE2 (kapsam buna bakar)
    sa.Column("il", sa.String(100)),
    sa.Column("bmt", sa.String(120), index=True),                  # AD hesabı (M30 ataması)
    sa.Column("bmt_ad", sa.String(200)),
    sa.Column("grup", sa.String(10)),                              # standart | anahtar
    sa.Column("bakiye", sa.Float), sa.Column("gelmemis", sa.Float), sa.Column("plansiz", sa.Float),
    sa.Column("k_1_30", sa.Float), sa.Column("k_31_60", sa.Float), sa.Column("k_61_90", sa.Float), sa.Column("k_90p", sa.Float),
    sa.Column("vadesi_gecmis", sa.Float),
    sa.Column("satis_12ay", sa.Float), sa.Column("iade_12ay", sa.Float), sa.Column("net_12ay", sa.Float),
    sa.Column("pay", sa.Float), sa.Column("buyume_6ay", sa.Float),
    sa.Column("iade_orani", sa.Float), sa.Column("dso", sa.Float), sa.Column("duzensizlik", sa.Float),
    sa.Column("aktif_ay", sa.Integer), sa.Column("son_fatura", sa.String(10)),
    sa.Column("son_odeme", sa.String(10)), sa.Column("odeme_12ay", sa.Float),
    sa.Column("karsiliksiz", sa.Integer), sa.Column("protesto", sa.Integer), sa.Column("cek_tutar", sa.Float),
    sa.Column("limit_toplam", sa.Float), sa.Column("risk_toplam", sa.Float), sa.Column("risk_doluluk", sa.Float),
    sa.Column("limit_json", sa.Text),
    sa.Column("siparis_riskte", sa.Integer), sa.Column("siparis_riskte_tutar", sa.Float),
    sa.Column("sorunlu", sa.Boolean),
    sa.Column("hareketsiz", sa.Boolean, nullable=False, default=False),
    sa.Column("skor", sa.Float), sa.Column("segment", sa.String(1)), sa.Column("bilesen_json", sa.Text),
    sa.Column("onceki_segment", sa.String(1)), sa.Column("skor_30g", sa.Float), sa.Column("egilim", sa.String(12)),
    sa.Column("kural_surum", sa.Integer, nullable=False),
    sa.Column("veri_son_gunu", sa.String(10)), sa.Column("yaslandirma_gunu", sa.String(10)),
    sa.Column("fingerprint", sa.String(64), nullable=False),
    sa.Index("ix_semantic_dealer_scores_code", "tenant_id", "logo_code", "gun"),
)
SERIES = sa.Table(
    "semantic_dealer_series", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("logo_code", sa.String(40), primary_key=True),
    sa.Column("gun", sa.String(10), nullable=False),
    sa.Column("seri_json", sa.Text, nullable=False),               # son 12 ay: satış, iade, fatura, ödeme
)
PROPOSALS = sa.Table(
    "semantic_dealer_limit_proposals", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("logo_code", sa.String(40), nullable=False),
    sa.Column("unvan", sa.String(300)),
    sa.Column("crm_account_id", sa.String(40)),
    sa.Column("bmt", sa.String(120)),
    sa.Column("gun", sa.String(10), nullable=False),
    sa.Column("segment", sa.String(1)), sa.Column("skor", sa.Float),
    sa.Column("mevcut_json", sa.Text, nullable=False),              # CRM anlık limit/risk
    sa.Column("degisim", sa.String(10), nullable=False),            # azalt | artir | tanimla
    sa.Column("onerilen_toplam", sa.Float, nullable=False),
    sa.Column("gerekce_kural", sa.Text, nullable=False),
    sa.Column("gerekce_metin", sa.Text),
    sa.Column("gerekce_kaynak", sa.String(10)),                     # kural | zeki
    sa.Column("kural_surum", sa.Integer, nullable=False),
    sa.Column("durum", sa.String(12), nullable=False),              # oneri | onayli | red | crm_islendi | gecersiz
    sa.Column("olusturma", sa.DateTime(timezone=True), nullable=False),
    sa.Column("karar_veren", sa.String(120)), sa.Column("karar_at", sa.DateTime(timezone=True)), sa.Column("karar_notu", sa.Text),
    sa.Column("crm_isleyen", sa.String(120)), sa.Column("crm_islendi_at", sa.DateTime(timezone=True)),
    sa.Index("ix_semantic_dealer_limit_proposals_code", "tenant_id", "logo_code"),
)
ACTIONS = sa.Table(
    "semantic_dealer_actions", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("logo_code", sa.String(40), nullable=False),
    sa.Column("unvan", sa.String(300)),
    sa.Column("tur", sa.String(10), nullable=False),                # ziyaret | arama | limit | diger
    sa.Column("sahip", sa.String(120), nullable=False),
    sa.Column("termin", sa.String(10)),
    sa.Column("durum", sa.String(10), nullable=False),              # acik | yapildi | iptal
    sa.Column("notu", sa.Text),
    sa.Column("olusturan", sa.String(120), nullable=False),
    sa.Column("olusturma", sa.DateTime(timezone=True), nullable=False),
    sa.Column("guncelleyen", sa.String(120)), sa.Column("guncelleme", sa.DateTime(timezone=True)),
    sa.Index("ix_semantic_dealer_actions_code", "tenant_id", "logo_code"),
)
BRIEFS = sa.Table(
    "semantic_dealer_briefs", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("logo_code", sa.String(40), primary_key=True),
    sa.Column("gun", sa.String(10), nullable=False),
    sa.Column("girdi_hash", sa.String(64), nullable=False),
    sa.Column("metin", sa.Text, nullable=False),
    sa.Column("maddeler_json", sa.Text, nullable=False),
    sa.Column("kaynak", sa.String(10), nullable=False),             # zeki | kural
    sa.Column("model_is", sa.String(80)),
    sa.Column("olusturan", sa.String(120)),
    sa.Column("olusturma", sa.DateTime(timezone=True), nullable=False),
)
META = sa.Table(
    "semantic_dealer_meta", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("key", sa.String(60), primary_key=True),
    sa.Column("value_json", sa.Text, nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)


def ensure(engine: sa.engine.Engine) -> None:
    with _lock:
        if id(engine) in _ready:
            return
        _md.create_all(engine, checkfirst=True)
        F.ensure(engine)              # ortak ziyaret ve bildirim tabloları (M30)
        _ready.add(id(engine))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def today() -> date:
    return datetime.now(TZ).date()


def _iso(v: Any) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, datetime):
        return (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).isoformat()
    return str(v)


def _j(s: Any, default: Any) -> Any:
    try:
        return json.loads(s) if s else default
    except (TypeError, ValueError):
        return default


def _dump(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, default=str)


def _new_id() -> str:
    return uuid.uuid4().hex


def _row(r: Any) -> dict[str, Any]:
    return dict(r._mapping)


fold = F.fold
tr_money = F._tr_money
short_money = F.short_money


def meta_get(engine: sa.engine.Engine, tenant: str, key: str) -> dict[str, Any]:
    with engine.connect() as c:
        row = c.execute(sa.select(META).where(META.c.tenant_id == tenant, META.c.key == key)).first()
    return {**_j(row.value_json, {}), "_at": _iso(row.updated_at)} if row else {}


def meta_set(engine: sa.engine.Engine, tenant: str, key: str, value: dict[str, Any]) -> None:
    with engine.begin() as c:
        cond = (META.c.tenant_id == tenant, META.c.key == key)
        if c.execute(sa.select(META.c.key).where(*cond)).first():
            c.execute(META.update().where(*cond).values(value_json=_dump(value), updated_at=_now()))
        else:
            c.execute(META.insert().values(tenant_id=tenant, key=key, value_json=_dump(value), updated_at=_now()))


# ------------------------------------------------------------------ ayarlar


def settings_from(conf: Callable[..., str]) -> dict[str, Any]:
    """Ayarlar ekran/ortamdan (`admin.conf`). Ölçülmemiş varsayımlar burada parametredir; kaynak ayarları (cari kodu
    öneki, ödeme TRCODE'ları, CRM şeması, atamada süzülen servis hesabı) M30 ile ortaktır ki iki ekran aynı carileri
    aynı temsilciye bağlasın."""
    field = F.settings_from(conf)
    return {
        "codePrefix": field["codePrefix"], "excludedOwners": field["excludedOwners"],
        "paymentTrcodes": field["paymentTrcodes"], "schema": field["schema"],
        # «Bugün» = Logo veri son günü (donmuş kopyada her vade «geçmiş» görünmesin); `bugun` ile takvim günü.
        "agingAsof": (conf("DEALERS_AGING_ASOF", "veri-sonu") or "veri-sonu").strip(),
        "channels": [x.strip() for x in (conf("DEALERS_CHANNELS", "KITAPCI,BAYI,DAGITICI,ZINCIR,E-TICARET") or "").split(",") if x.strip()],
        "keyChannels": [x.strip() for x in (conf("DEALERS_KEY_CHANNELS", "ZINCIR,E-TICARET,DAGITICI") or "").split(",") if x.strip()],
        "morningRecipients": [x.strip() for x in (conf("DEALERS_MORNING_RECIPIENTS", "") or "").replace(";", ",").split(",") if "@" in x],
        "historyDays": _int(conf("DEALERS_HISTORY_DAYS", "730"), 730, 30, 3650),
    }


def _int(v: Any, default: int, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(str(v))))
    except (TypeError, ValueError):
        return default


# ------------------------------------------------------------------ kural

#: Bileşenler: (anahtar, ekrandaki ad, ne ölçer). Ağırlıklar kural sürümünde.
COMPONENTS: list[tuple[str, str, str]] = [
    ("gecikme", "Ödeme gecikmesi", "Bakiyenin yaşa göre ağırlıklı vadesi geçmiş payı (1–30 ×1, 31–60 ×2, 61–90 ×3, 90+ ×4; "
                                   "FIFO yaklaşımı — Logo'da ödeme kapama yok)"),
    ("cek", "Çek/senet olayı", "Son 12 ayda karşılıksız (×1) ve protestolu (× kuraldaki katsayı) çek/senet"),
    ("iade", "İade oranı", "Son 12 ay iade ÷ satış (faturalı satır), kuraldaki tavana oranla"),
    ("limit", "Limit doluluğu", "CRM toplam risk ÷ toplam risk limiti; eşiğin üstü puanlanır. Limit girilmemişse 0"),
    ("duzensizlik", "Sipariş düzensizliği", "Son 12 ayın aylık satış tutarı değişkenliği (değişim katsayısı), tavana oranla"),
    ("tahsilat_suresi", "Tahsilat süresi", "Bakiye ÷ günlük ortalama net satış (DSO yaklaşımı); hedef günü aşan kısım"),
]
COMPONENT_KEYS = [k for k, _, _ in COMPONENTS]
SEGMENTS = ["A", "B", "C", "D"]
SEGMENT_LABEL = {"A": "A · düşük risk", "B": "B · izlenir", "C": "C · dikkat", "D": "D · yüksek risk"}
RULE_STATES = {"taslak": "Taslak", "onayda": "Onay bekliyor", "yururlukte": "Yürürlükte", "arsiv": "Arşiv"}
PROPOSAL_STATES = {"oneri": "Onay bekliyor", "onayli": "Onaylandı — CRM'e işlenecek", "red": "Reddedildi",
                   "crm_islendi": "CRM'e işlendi", "gecersiz": "Koşul kalktı"}
CHANGE_LABEL = {"azalt": "Limiti düşür", "artir": "Limiti artır", "tanimla": "Limit tanımla"}
ACTION_KINDS = {"ziyaret": "Ziyaret", "arama": "Arama", "limit": "Limit", "diger": "Diğer"}
ACTION_STATES = {"acik": "Açık", "yapildi": "Yapıldı", "iptal": "İptal"}
TREND_LABEL = {"kotulesiyor": "Kötüleşiyor", "iyilesiyor": "İyileşiyor", "yatay": "Yatay"}


def default_rule(settings: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Başlangıç kuralı (analiz §14). Kanal listeleri ayardan (Logo özel kod 2 değerleri ölçülecek)."""
    st = settings or {}
    return {
        "agirliklar": {"gecikme": 35, "cek": 20, "iade": 15, "limit": 10, "duzensizlik": 10, "tahsilat_suresi": 10},
        "esikler": {"standart": {"A": 20, "B": 40, "C": 60}, "anahtar": {"A": 25, "B": 45, "C": 65},
                    "iadeTavan": 0.40, "duzensizlikTavan": 2.0, "dsoHedef": 90, "dsoAralik": 180,
                    "limitEsik": 0.5, "protestoKatsayi": 0.5, "egilimEsik": 5},
        "kapsam": {"kanallar": st.get("channels") or ["KITAPCI", "BAYI", "DAGITICI", "ZINCIR", "E-TICARET"],
                   "anahtarKanallar": st.get("keyChannels") or ["ZINCIR", "E-TICARET", "DAGITICI"],
                   "anahtarPay": 0.02, "bosKanal": False},
        "limit": {"artisOrani": 0.20, "artisDoluluk": 0.80, "yeniLimitAy": 2, "yuvarlama": 1000},
    }


def _f(v: Any, what: str, lo: float, hi: float) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise DealerError(f"{what} sayı olmalı.", 422) from None
    if not (lo <= x <= hi) or x != x:
        raise DealerError(f"{what} {lo:g} ile {hi:g} arasında olmalı.", 422)
    return x


def validate_rule(body: dict[str, Any], base: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Kural gövdesini doğrular ve tamamlar (eksik alan `base`'ten). Ağırlıklar tam sayı ve toplam 100; eşikler artan."""
    base = base or default_rule()
    w_in = {**base["agirliklar"], **(body.get("agirliklar") or {})}
    w = {}
    for k in COMPONENT_KEYS:
        v = _f(w_in.get(k, 0), f"«{dict((a, b) for a, b, _ in COMPONENTS)[k]}» ağırlığı", 0, 100)
        if v != int(v):
            raise DealerError("Ağırlıklar tam sayı olmalı.", 422)
        w[k] = int(v)
    if sum(w.values()) != 100:
        raise DealerError(f"Ağırlıkların toplamı 100 olmalı (şu an {sum(w.values())}).", 422)
    e_in = {**base["esikler"], **(body.get("esikler") or {})}
    e: dict[str, Any] = {}
    for grp, name in (("standart", "Standart"), ("anahtar", "Anahtar hesap")):
        g = {**base["esikler"][grp], **(e_in.get(grp) or {})}
        a, b, c = (_f(g.get(x), f"{name} {x} eşiği", 0, 100) for x in ("A", "B", "C"))
        if not a < b < c:
            raise DealerError(f"{name} eşikleri artan olmalı (A < B < C).", 422)
        e[grp] = {"A": a, "B": b, "C": c}
    e["iadeTavan"] = _f(e_in.get("iadeTavan"), "İade tavanı", 0.01, 1)
    e["duzensizlikTavan"] = _f(e_in.get("duzensizlikTavan"), "Düzensizlik tavanı", 0.1, 10)
    e["dsoHedef"] = _f(e_in.get("dsoHedef"), "Tahsilat süresi hedefi", 0, 720)
    e["dsoAralik"] = _f(e_in.get("dsoAralik"), "Tahsilat süresi aralığı", 1, 720)
    e["limitEsik"] = _f(e_in.get("limitEsik"), "Limit doluluk eşiği", 0, 0.99)
    e["protestoKatsayi"] = _f(e_in.get("protestoKatsayi"), "Protesto katsayısı", 0, 1)
    e["egilimEsik"] = _f(e_in.get("egilimEsik"), "Eğilim eşiği", 0, 100)
    k_in = {**base["kapsam"], **(body.get("kapsam") or {})}

    def names(v: Any) -> list[str]:
        items = v if isinstance(v, list) else str(v or "").split(",")
        return sorted({str(x).strip().upper() for x in items if str(x).strip()})

    kapsam = {"kanallar": names(k_in.get("kanallar")), "anahtarKanallar": names(k_in.get("anahtarKanallar")),
              "anahtarPay": _f(k_in.get("anahtarPay"), "Anahtar hesap payı", 0, 1), "bosKanal": bool(k_in.get("bosKanal"))}
    if not kapsam["kanallar"] and not kapsam["bosKanal"]:
        raise DealerError("Kapsamda en az bir kanal olmalı.", 422)
    l_in = {**base["limit"], **(body.get("limit") or {})}
    lim = {"artisOrani": _f(l_in.get("artisOrani"), "Limit artış oranı", 0, 2),
           "artisDoluluk": _f(l_in.get("artisDoluluk"), "Artış için doluluk", 0, 1),
           "yeniLimitAy": _f(l_in.get("yeniLimitAy"), "Yeni limit (ay)", 0.25, 24),
           "yuvarlama": _f(l_in.get("yuvarlama"), "Yuvarlama", 1, 1_000_000)}
    return {"agirliklar": w, "esikler": e, "kapsam": kapsam, "limit": lim}


def _rule_out(r: dict[str, Any]) -> dict[str, Any]:
    return {"id": r["id"], "surum": r["surum"], "durum": r["durum"], "durumAd": RULE_STATES.get(r["durum"], r["durum"]),
            "agirliklar": _j(r["agirliklar_json"], {}), "esikler": _j(r["esikler_json"], {}), "kapsam": _j(r["kapsam_json"], {}),
            "limit": _j(r["limit_json"], {}), "gerekce": r.get("gerekce"), "hazirlayan": r["hazirlayan"],
            "olusturma": _iso(r.get("olusturma")), "gonderen": r.get("gonderen"), "gonderim": _iso(r.get("gonderim")),
            "onaylayan": r.get("onaylayan"), "onayZamani": _iso(r.get("onay_zamani")), "kararNotu": r.get("karar_notu")}


def rule_body(r: dict[str, Any]) -> dict[str, Any]:
    """Kural çıktısından skor fonksiyonunun beklediği gövde."""
    return {"surum": r["surum"], "agirliklar": r["agirliklar"], "esikler": r["esikler"], "kapsam": r["kapsam"], "limit": r["limit"]}


def list_rules(engine: sa.engine.Engine, tenant: str) -> list[dict[str, Any]]:
    with engine.connect() as c:
        rows = [_row(r) for r in c.execute(sa.select(RULES).where(RULES.c.tenant_id == tenant).order_by(RULES.c.surum.desc()))]
    return [_rule_out(r) for r in rows]


def get_rule(engine: sa.engine.Engine, tenant: str, rid: str) -> dict[str, Any]:
    with engine.connect() as c:
        r = c.execute(sa.select(RULES).where(RULES.c.tenant_id == tenant, RULES.c.id == rid)).first()
    if r is None:
        raise DealerError("Kural sürümü bulunamadı.", 404)
    return _rule_out(_row(r))


def active_rule(engine: sa.engine.Engine, tenant: str, settings: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Yürürlükteki kural. Hiç kural yoksa başlangıç kuralı «sürüm 1» olarak yürürlüğe girer (hazırlayan: sistem) —
    günlük skor kuralsız kalmasın; değişiklik sonraki sürümlerde iki gözle olur."""
    with engine.connect() as c:
        r = c.execute(sa.select(RULES).where(RULES.c.tenant_id == tenant, RULES.c.durum == "yururlukte")
                      .order_by(RULES.c.surum.desc())).first()
    if r is not None:
        return _rule_out(_row(r))
    body = default_rule(settings)
    row = {"id": _new_id(), "tenant_id": tenant, "surum": 1, "durum": "yururlukte",
           "agirliklar_json": _dump(body["agirliklar"]), "esikler_json": _dump(body["esikler"]),
           "kapsam_json": _dump(body["kapsam"]), "limit_json": _dump(body["limit"]),
           "gerekce": "Başlangıç kuralı (analiz belgesi M59 §14); ağırlık ve eşikler gerçek veriyle ölçülüp yeni sürümle değişir.",
           "hazirlayan": "sistem", "olusturma": _now(), "onaylayan": "sistem", "onay_zamani": _now()}
    with engine.begin() as c:
        if c.execute(sa.select(RULES.c.id).where(RULES.c.tenant_id == tenant)).first() is not None:
            raise DealerError("Yürürlükte bayi risk kuralı yok; onay bekleyen sürümü onaylayın.", 409)
        c.execute(RULES.insert().values(**row))
    return _rule_out(row)


def create_rule(engine: sa.engine.Engine, tenant: str, user: str, body: dict[str, Any], base: dict[str, Any]) -> dict[str, Any]:
    vals = validate_rule(body, base)
    with engine.begin() as c:
        n = c.execute(sa.select(sa.func.max(RULES.c.surum)).where(RULES.c.tenant_id == tenant)).scalar() or 0
        row = {"id": _new_id(), "tenant_id": tenant, "surum": int(n) + 1, "durum": "taslak",
               "agirliklar_json": _dump(vals["agirliklar"]), "esikler_json": _dump(vals["esikler"]),
               "kapsam_json": _dump(vals["kapsam"]), "limit_json": _dump(vals["limit"]),
               "gerekce": (text(body.get("gerekce")) or "")[:2000] or None, "hazirlayan": user, "olusturma": _now()}
        c.execute(RULES.insert().values(**row))
    return _rule_out(row)


def edit_rule(engine: sa.engine.Engine, tenant: str, user: str, rid: str, body: dict[str, Any]) -> dict[str, Any]:
    cur = get_rule(engine, tenant, rid)
    if cur["durum"] != "taslak":
        raise DealerError("Yalnız taslak kural değiştirilir; yürürlükteki için yeni sürüm açın.", 409)
    if cur["hazirlayan"] != user:
        raise DealerError("Taslağı hazırlayan değiştirir.", 403)
    vals = validate_rule(body, rule_body(cur))
    upd = {"agirliklar_json": _dump(vals["agirliklar"]), "esikler_json": _dump(vals["esikler"]),
           "kapsam_json": _dump(vals["kapsam"]), "limit_json": _dump(vals["limit"])}
    if "gerekce" in body:
        upd["gerekce"] = (text(body.get("gerekce")) or "")[:2000] or None
    with engine.begin() as c:
        c.execute(RULES.update().where(RULES.c.id == rid).values(**upd))
    return get_rule(engine, tenant, rid)


def submit_rule(engine: sa.engine.Engine, tenant: str, user: str, rid: str) -> dict[str, Any]:
    cur = get_rule(engine, tenant, rid)
    if cur["durum"] != "taslak":
        raise DealerError("Yalnız taslak onaya gönderilir.", 409)
    if not (cur.get("gerekce") or "").strip():
        raise DealerError("Onaya göndermeden önce değişikliğin gerekçesini yazın.", 422)
    with engine.begin() as c:
        c.execute(RULES.update().where(RULES.c.id == rid).values(durum="onayda", gonderen=user, gonderim=_now()))
    return get_rule(engine, tenant, rid)


def decide_rule(engine: sa.engine.Engine, tenant: str, user: str, rid: str, approve: bool, note: Optional[str]) -> dict[str, Any]:
    """İki göz: hazırlayan ve onaya gönderen onaylayamaz. Onayda önceki yürürlükteki arşive iner."""
    cur = get_rule(engine, tenant, rid)
    if cur["durum"] != "onayda":
        raise DealerError("Bu kural onay beklemiyor.", 409)
    if user in (cur["hazirlayan"], cur.get("gonderen")):
        raise DealerError("Kuralı hazırlayan ya da onaya gönderen onaylayamaz (iki göz).", 403)
    if not approve and not (note or "").strip():
        raise DealerError("Geri çevirme nedenini yazın.", 422)
    with engine.begin() as c:
        if approve:
            c.execute(RULES.update().where(RULES.c.tenant_id == tenant, RULES.c.durum == "yururlukte").values(durum="arsiv"))
            c.execute(RULES.update().where(RULES.c.id == rid).values(durum="yururlukte", onaylayan=user, onay_zamani=_now(),
                                                                    karar_notu=(note or None)))
        else:
            c.execute(RULES.update().where(RULES.c.id == rid).values(durum="taslak", karar_notu=note, gonderen=None, gonderim=None))
    return get_rule(engine, tenant, rid)


# ------------------------------------------------------------------ skor (saf; test edilir)


def weighted_overdue(r: dict[str, Any]) -> float:
    return F.weighted_overdue(r)


def in_scope(kanal: Optional[str], rule: dict[str, Any]) -> bool:
    k = rule["kapsam"]
    if not (kanal or "").strip():
        return bool(k.get("bosKanal"))
    return fold(kanal.strip()) in {fold(x) for x in k.get("kanallar") or []}


def group_of(raw: dict[str, Any], rule: dict[str, Any]) -> str:
    k = rule["kapsam"]
    if raw.get("kanal") and fold(raw["kanal"]) in {fold(x) for x in k.get("anahtarKanallar") or []}:
        return "anahtar"
    share = opt_num(raw.get("pay"))
    if share is not None and k.get("anahtarPay") and share >= float(k["anahtarPay"]):
        return "anahtar"
    return "standart"


def components(raw: dict[str, Any], rule: dict[str, Any]) -> list[dict[str, Any]]:
    """Her bileşenin 0–1 değeri, puanı ve rakamlı açıklaması. Değeri olmayan bileşen 0 puan alır ve nedeni yazılır."""
    e, w = rule["esikler"], rule["agirliklar"]
    out: list[dict[str, Any]] = []

    def add(key: str, value: float, note: str) -> None:
        v = max(0.0, min(1.0, value))
        out.append({"key": key, "deger": round(v, 4), "agirlik": w.get(key, 0), "puan": round(w.get(key, 0) * v, 1), "aciklama": note})

    bal = num(raw.get("bakiye"))
    over = num(raw.get("vadesi_gecmis"))
    if bal > 0:
        add("gecikme", weighted_overdue(raw) / (4 * bal),
            f"Vadesi geçmiş {short_money(over)} (90+ gün {short_money(num(raw.get('k_90p')))}), bakiye {short_money(bal)} — yaklaşık")
    else:
        add("gecikme", 0, "Açık bakiye yok" if bal == 0 else f"Alacaklı bakiye {short_money(bal)}")
    kk, pr = int(num(raw.get("karsiliksiz"))), int(num(raw.get("protesto")))
    add("cek", kk + float(e["protestoKatsayi"]) * pr,
        f"Karşılıksız {kk}, protesto {pr} (12 ay)" + (f", {short_money(num(raw.get('cek_tutar')))}" if kk or pr else ""))
    ratio = opt_num(raw.get("iade_orani"))
    add("iade", (ratio or 0) / float(e["iadeTavan"]),
        f"İade oranı %{round(ratio * 100)} (tavan %{round(float(e['iadeTavan']) * 100)})" if ratio is not None else "12 ayda satış yok")
    fill = opt_num(raw.get("risk_doluluk"))
    lo = float(e["limitEsik"])
    add("limit", ((fill - lo) / (1 - lo)) if fill is not None else 0,
        f"Limit %{round(fill * 100)} dolu (eşik %{round(lo * 100)})" if fill is not None else "CRM'de limit girilmemiş")
    cv = opt_num(raw.get("duzensizlik"))
    add("duzensizlik", (cv or 0) / float(e["duzensizlikTavan"]),
        f"Aylık alım değişkenliği {cv:.2f} ({int(num(raw.get('aktif_ay')))}/12 ay alım)".replace(".", ",") if cv is not None
        else "12 ayda alım yok")
    dso = opt_num(raw.get("dso"))
    add("tahsilat_suresi", ((dso - float(e["dsoHedef"])) / float(e["dsoAralik"])) if dso is not None else 0,
        f"Tahsilat süresi ~{round(dso)} gün (hedef {round(float(e['dsoHedef']))}) — yaklaşık" if dso is not None
        else "Hesaplanamadı (net satış ya da bakiye yok)")
    return out


def segment_of(score: float, group: str, rule: dict[str, Any]) -> str:
    t = rule["esikler"].get(group) or rule["esikler"]["standart"]
    if score < float(t["A"]):
        return "A"
    if score < float(t["B"]):
        return "B"
    if score < float(t["C"]):
        return "C"
    return "D"


def evaluate(raw: dict[str, Any], rule: dict[str, Any]) -> dict[str, Any]:
    """Tek carinin skoru, segmenti, grubu ve bileşenleri. Hareketsiz cari (bakiye yok, 12 ayda satış yok) segmentsiz."""
    comps = components(raw, rule)
    score = round(min(100.0, sum(c["puan"] for c in comps)), 1)
    grp = group_of(raw, rule)
    idle = bool(raw.get("hareketsiz"))
    return {"skor": None if idle else score, "segment": None if idle else segment_of(score, grp, rule), "grup": grp,
            "bilesenler": sorted(comps, key=lambda c: -c["puan"])}


def trend(score: Optional[float], past: Optional[float], threshold: float) -> Optional[str]:
    if score is None or past is None:
        return None
    d = score - past
    return "kotulesiyor" if d >= threshold else "iyilesiyor" if d <= -threshold else "yatay"


def worse(seg: Optional[str], prev: Optional[str]) -> bool:
    return bool(seg and prev and SEGMENTS.index(seg) > SEGMENTS.index(prev))


#: Parmak izine giren ham alanlar (aynı gün + aynı kural + aynı girdi → aynı parmak izi).
RAW_FIELDS = ["bakiye", "gelmemis", "plansiz", "k_1_30", "k_31_60", "k_61_90", "k_90p", "vadesi_gecmis", "satis_12ay",
              "iade_12ay", "net_12ay", "pay", "buyume_6ay", "iade_orani", "dso", "duzensizlik", "aktif_ay", "son_fatura",
              "son_odeme", "odeme_12ay", "karsiliksiz", "protesto", "cek_tutar", "limit_toplam", "risk_toplam",
              "risk_doluluk", "siparis_riskte", "siparis_riskte_tutar", "sorunlu", "kanal", "hareketsiz"]


def fingerprint(raw: dict[str, Any], rule_version: int, gun: str) -> str:
    body = {"gun": gun, "kural": rule_version, **{k: raw.get(k) for k in RAW_FIELDS}}
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()


def series_stats(months: dict[str, dict[str, Any]], keys: list[str]) -> dict[str, Any]:
    """12 aylık seriden: satış, iade, net, iade oranı, düzensizlik (aylık satışın değişim katsayısı), aktif ay,
    son 6 ayın önceki 6 aya büyümesi, ödeme toplamı."""
    sat = [num((months.get(k) or {}).get("satis")) for k in keys]
    iad = [num((months.get(k) or {}).get("iade")) for k in keys]
    pay = [num((months.get(k) or {}).get("odeme")) for k in keys]
    s, i = sum(sat), sum(iad)
    active = sum(1 for x in sat if x > 0)
    cv = None
    if s > 0:
        mean = s / len(sat)
        var = sum((x - mean) ** 2 for x in sat) / len(sat)
        cv = round(math.sqrt(var) / mean, 4)
    half = len(keys) // 2
    net = [a - b for a, b in zip(sat, iad)]
    prev6, last6 = sum(net[:half]), sum(net[half:])
    growth = round(last6 / prev6 - 1, 4) if prev6 > 0 else None
    return {"satis_12ay": round(s, 2), "iade_12ay": round(i, 2), "net_12ay": round(s - i, 2),
            "iade_orani": round(i / s, 4) if s > 0 else None, "duzensizlik": cv, "aktif_ay": active,
            "buyume_6ay": growth, "odeme_seri_12ay": round(sum(pay), 2)}


def dso_of(balance: float, net_12m: float) -> Optional[float]:
    """Tahsilat süresi yaklaşımı: bakiye ÷ (12 ay net satış ÷ 365). Bakiye ya da net satış yoksa hesaplanmaz."""
    if balance <= 0 or net_12m <= 0:
        return None
    return round(balance / (net_12m / 365.0), 1)


# ------------------------------------------------------------------ günlük tur: okuma ve kurma


def read_all(source: F.Source, settings: dict[str, Any], now: Optional[date] = None) -> dict[str, Any]:
    """Günlük turun okuması: CRM (kullanıcı, cari + limit/risk, bayraklar, riske takılan sipariş) ve Logo (cari listesi,
    FIFO yaşlandırma, çek olayı, son ödeme, 12 ay aylık seri). Biri düşerse hata (yarım skor yazılmaz)."""
    now = now or today()
    schema, pre = settings["schema"], settings["codePrefix"]
    codes = tuple(settings["paymentTrcodes"])

    def crm_part(run):
        return {"users": fsrc.lower_keys(run(fsrc.crm_users_sql(schema))),
                "accounts": fsrc.lower_keys(run(fsrc.crm_accounts_sql(schema))),
                "riskOrders": fsrc.lower_keys(run(fsrc.crm_risk_orders_sql(schema))),
                "flags": dsrc.read_account_flags(run, schema)}

    crm = source.crm(crm_part)

    def logo_part(run):
        cal = F.logo_calendar(run, now)
        f, pf, year = cal["firm"], cal["prevFirm"], cal["year"]
        end = date.fromisoformat(cal["dataEnd"]) if cal["dataEnd"] else now
        asof = end if settings["agingAsof"] == "veri-sonu" else now
        firms = [x for x in (pf, f) if x]
        start = dsrc.window_start(end, 12)
        return {"cal": cal, "agingAsof": asof.isoformat(), "end": end.isoformat(),
                "clients": fsrc.read_rows(run, fsrc.clients_sql(f, pre)),
                "aging": fsrc.read_aging(run, f, year, asof, pre),
                "cheques": fsrc.read_cheque_events(run, firms, end - timedelta(days=365), pre),
                "payments": dsrc.read_last_payments(run, firms, end - timedelta(days=365), codes, pre),
                "monthly": dsrc.read_monthly(run, [x for x in firms if x != pf or start.year < year], start, end, codes, pre)}

    logo = source.logo(logo_part)
    return {"crm": crm, "logo": logo, "now": now.isoformat()}


def build(data: dict[str, Any], settings: dict[str, Any], rule: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Okunan veriden kapsam içi carilerin ham satırları ve skorları (saf; test edilir). Kapsam Logo özel kod 2'ye
    (`SPECODE2`) bakar: kabul testindeki doğrudan sayımla aynı küme; temsilcisi olmayan cari de listede kalır."""
    crm, logo = data["crm"], data["logo"]
    assigned = F.assign(crm["accounts"], crm["users"], settings["excludedOwners"])
    rows = F.match_clients(assigned, logo["clients"])
    risk_orders = {guid(r.get("account_id")): r for r in crm["riskOrders"]}
    flags = crm.get("flags") or {}
    keys = dsrc.month_keys(date.fromisoformat(logo["end"]), 12)
    scoped = [r for r in rows if in_scope(r.get("logo_kanal"), rule)]
    stats = {r["logo_code"]: series_stats(logo["monthly"].get(r["logo_code"]) or {}, keys) for r in scoped}
    total_net = sum(max(0.0, s["net_12ay"]) for s in stats.values())
    out = []
    for r in scoped:
        code = r["logo_code"]
        ag = logo["aging"].get(r["logo_clientref"], {})
        st = stats[code]
        ch = logo["cheques"].get(code) or {}
        pay = logo["payments"].get(code) or {}
        acc = r.get("_crm") or {}
        risk = fsrc.risk_of(acc) if acc else {}
        fl = flags.get(r.get("crm_account_id") or "") or {}
        ro = risk_orders.get(r.get("crm_account_id")) if r.get("crm_account_id") else None
        bal = round(num(ag.get("bakiye")), 2)
        raw = {
            "logo_code": code, "logo_clientref": r["logo_clientref"], "crm_account_id": r.get("crm_account_id"),
            "unvan": r.get("unvan"), "kanal": r.get("logo_kanal"), "il": r.get("il"),
            "bmt": r.get("ad_hesap"), "bmt_ad": r.get("temsilci_ad"),
            "bakiye": bal, "gelmemis": ag.get("gelmemis", 0.0), "plansiz": ag.get("plansiz", 0.0),
            "k_1_30": ag.get("k_1_30", 0.0), "k_31_60": ag.get("k_31_60", 0.0), "k_61_90": ag.get("k_61_90", 0.0),
            "k_90p": ag.get("k_90p", 0.0), "vadesi_gecmis": ag.get("vadesi_gecmis", 0.0),
            "satis_12ay": st["satis_12ay"], "iade_12ay": st["iade_12ay"], "net_12ay": st["net_12ay"],
            "pay": round(max(0.0, st["net_12ay"]) / total_net, 6) if total_net > 0 else None,
            "buyume_6ay": st["buyume_6ay"], "iade_orani": st["iade_orani"], "duzensizlik": st["duzensizlik"],
            "aktif_ay": st["aktif_ay"], "dso": dso_of(bal, st["net_12ay"]),
            "son_fatura": (logo["monthly"].get(code) or {}).get("_son"),
            "son_odeme": pay.get("son"), "odeme_12ay": round(num(pay.get("toplam")), 2),
            "karsiliksiz": int(num(ch.get("karsiliksiz_adet"))), "protesto": int(num(ch.get("protesto_adet"))),
            "cek_tutar": round(num(ch.get("karsiliksiz_tutar")) + num(ch.get("protesto_tutar")), 2),
            "limit_toplam": risk.get("limit_toplam"), "risk_toplam": risk.get("risk_toplam"),
            "risk_doluluk": risk.get("risk_doluluk"),
            "limit_json": _dump({**risk, **fl}) if (risk or fl) else None,
            "siparis_riskte": int(num(ro.get("adet"))) if ro else 0,
            "siparis_riskte_tutar": round(num(ro.get("tutar")), 2) if ro else 0.0,
            "sorunlu": bool(fl.get("sorunlu")) if fl else None,
            "hareketsiz": abs(bal) < 0.01 and st["satis_12ay"] <= 0,
            "seri": [{"ay": k, **{x: round(num(((logo["monthly"].get(code) or {}).get(k) or {}).get(x)), 2)
                                  for x in ("satis", "iade", "odeme")},
                      "fatura": int(num(((logo["monthly"].get(code) or {}).get(k) or {}).get("fatura")))} for k in keys],
        }
        out.append(raw)
    info = {"dataEnd": logo["cal"].get("dataEnd"), "agingAsof": logo["agingAsof"], "year": logo["cal"]["year"],
            "firm": logo["cal"]["firm"], "prevFirm": logo["cal"].get("prevFirm"), "clients": len(rows), "scope": len(out),
            "kanallar": rule["kapsam"]["kanallar"], "assigned": sum(1 for x in out if x["bmt"]),
            "idle": sum(1 for x in out if x["hareketsiz"])}
    return out, info


def _raw_from_row(r: dict[str, Any]) -> dict[str, Any]:
    return {k: r.get(k) for k in RAW_FIELDS}


def previous_raw(engine: sa.engine.Engine, tenant: str, before: str, on_or_before: bool = False) -> tuple[Optional[str], dict[str, dict[str, Any]]]:
    """`before` gününden önceki (ya da o gün dahil) en yakın kayıtlı günün ham satırları."""
    cond = SCORES.c.gun <= before if on_or_before else SCORES.c.gun < before
    with engine.connect() as c:
        g = c.execute(sa.select(sa.func.max(SCORES.c.gun)).where(SCORES.c.tenant_id == tenant, cond)).scalar()
        if not g:
            return None, {}
        rows = [_row(r) for r in c.execute(sa.select(SCORES).where(SCORES.c.tenant_id == tenant, SCORES.c.gun == g))]
    return g, {r["logo_code"]: _raw_from_row(r) for r in rows}


def score_rows(raws: list[dict[str, Any]], rule: dict[str, Any], gun: str, prev: dict[str, dict[str, Any]],
               past30: dict[str, dict[str, Any]], data_end: Optional[str], aging_day: Optional[str]) -> list[dict[str, Any]]:
    """Ham satırlara skor, segment, eğilim (30 gün önceki girdi bugünkü kuralla), önceki segment (önceki tur girdisi
    bugünkü kuralla) ve parmak izi ekler."""
    out = []
    thr = float(rule["esikler"]["egilimEsik"])
    for raw in raws:
        ev = evaluate(raw, rule)
        code = raw["logo_code"]
        p = evaluate(prev[code], rule) if code in prev else None
        p30 = evaluate(past30[code], rule) if code in past30 else None
        row = {k: v for k, v in raw.items() if k != "seri"}
        row.update({"gun": gun, "grup": ev["grup"], "skor": ev["skor"], "segment": ev["segment"],
                    "bilesen_json": _dump(ev["bilesenler"]),
                    "onceki_segment": p["segment"] if p else None, "skor_30g": p30["skor"] if p30 else None,
                    "egilim": trend(ev["skor"], p30["skor"] if p30 else None, thr),
                    "kural_surum": int(rule["surum"]), "veri_son_gunu": data_end, "yaslandirma_gunu": aging_day,
                    "fingerprint": fingerprint(raw, int(rule["surum"]), gun)})
        out.append(row)
    return out


def write_day(engine: sa.engine.Engine, tenant: str, gun: str, rows: list[dict[str, Any]], raws: list[dict[str, Any]]) -> None:
    """O günün skor satırlarını ve güncel seriyi tek işlemde değiştirir (okuyan yarım gün görmez)."""
    cols = {c.name for c in SCORES.c}
    with engine.begin() as c:
        c.execute(SCORES.delete().where(SCORES.c.tenant_id == tenant, SCORES.c.gun == gun))
        for i in range(0, len(rows), 1000):
            part = [{**{k: v for k, v in r.items() if k in cols}, "tenant_id": tenant} for r in rows[i:i + 1000]]
            if part:
                c.execute(SCORES.insert(), part)
        c.execute(SERIES.delete().where(SERIES.c.tenant_id == tenant))
        for i in range(0, len(raws), 1000):
            part = [{"tenant_id": tenant, "logo_code": r["logo_code"], "gun": gun, "seri_json": _dump(r["seri"])}
                    for r in raws[i:i + 1000]]
            if part:
                c.execute(SERIES.insert(), part)


# ------------------------------------------------------------------ okuma (ekran)


def latest_day(engine: sa.engine.Engine, tenant: str) -> Optional[str]:
    with engine.connect() as c:
        return c.execute(sa.select(sa.func.max(SCORES.c.gun)).where(SCORES.c.tenant_id == tenant)).scalar()


def day_rows(engine: sa.engine.Engine, tenant: str, gun: Optional[str], bmt: Optional[str]) -> list[dict[str, Any]]:
    """Bir günün satırları. `bmt` None = herkes (yetkili)."""
    if not gun:
        return []
    q = sa.select(SCORES).where(SCORES.c.tenant_id == tenant, SCORES.c.gun == gun)
    if bmt is not None:
        q = q.where(SCORES.c.bmt == bmt)
    with engine.connect() as c:
        return [_row(r) for r in c.execute(q)]


def one(engine: sa.engine.Engine, tenant: str, code: str) -> Optional[dict[str, Any]]:
    gun = latest_day(engine, tenant)
    if not gun:
        return None
    with engine.connect() as c:
        r = c.execute(sa.select(SCORES).where(SCORES.c.tenant_id == tenant, SCORES.c.gun == gun, SCORES.c.logo_code == code)).first()
    return _row(r) if r else None


def scoped(engine: sa.engine.Engine, tenant: str, user: str, code: str, all_scope: bool) -> dict[str, Any]:
    row = one(engine, tenant, code)
    if row is None:
        raise DealerError("Bu cari bayi riski listesinde yok (günlük tur henüz koşmadı, cari kapsam dışında ya da kod yanlış).", 404)
    if not all_scope and (row.get("bmt") or "") != user:
        raise DealerError("Bu cari size atanmış değil; yalnız kendi carilerinizi görürsünüz.", 403)
    return row


def dealer_row(r: dict[str, Any]) -> dict[str, Any]:
    """Liste satırının ekrana giden biçimi (kişisel veri yok)."""
    comps = _j(r.get("bilesen_json"), [])
    return {
        "code": r["logo_code"], "unvan": r.get("unvan"), "kanal": r.get("kanal"), "il": r.get("il"),
        "bmt": r.get("bmt"), "bmtAd": r.get("bmt_ad"), "grup": r.get("grup"),
        "bakiye": r.get("bakiye"), "vadesiGecmis": r.get("vadesi_gecmis"), "k90": r.get("k_90p"),
        "net12": r.get("net_12ay"), "iadeOrani": r.get("iade_orani"), "riskDoluluk": r.get("risk_doluluk"),
        "limitGirilmemis": r.get("limit_toplam") in (None, 0) and bool(r.get("crm_account_id")),
        "skor": r.get("skor"), "segment": r.get("segment"), "oncekiSegment": r.get("onceki_segment"),
        "egilim": r.get("egilim"), "skor30": r.get("skor_30g"), "hareketsiz": bool(r.get("hareketsiz")),
        "sorunlu": bool(r.get("sorunlu")), "siparisRiskte": r.get("siparis_riskte") or 0,
        "cekOlay": int(num(r.get("karsiliksiz"))) + int(num(r.get("protesto"))),
        "sonOdeme": r.get("son_odeme"), "sonFatura": r.get("son_fatura"),
        "neden": [{"key": c["key"], "puan": c["puan"], "aciklama": c["aciklama"]} for c in comps if c.get("puan", 0) > 0][:3],
    }


def filter_rows(rows: list[dict[str, Any]], *, segment: str = "", kanal: str = "", il: str = "", bmt: str = "",
                q: str = "", grup: str = "", egilim: str = "", hareketsiz: Optional[bool] = None) -> list[dict[str, Any]]:
    out = rows
    if segment:
        segs = {s.strip().upper() for s in segment.split(",") if s.strip()}
        out = [r for r in out if (r.get("segment") or "") in segs]
    if kanal:
        out = [r for r in out if fold(r.get("kanal") or "") == fold(kanal)]
    if il:
        out = [r for r in out if fold(r.get("il") or "") == fold(il)]
    if bmt:
        out = [r for r in out if (r.get("bmt") or "") == bmt.lower() or (bmt == "-" and not r.get("bmt"))]
    if grup:
        out = [r for r in out if r.get("grup") == grup]
    if egilim:
        out = [r for r in out if r.get("egilim") == egilim]
    if hareketsiz is not None:
        out = [r for r in out if bool(r.get("hareketsiz")) == hareketsiz]
    if q.strip():
        needle = fold(q)
        out = [r for r in out if needle in fold(f"{r.get('unvan') or ''} {r['logo_code']} {r.get('il') or ''}")]
    return out


ORDERS = {
    "skor": lambda r: (-(r.get("skor") if r.get("skor") is not None else -1), (r.get("unvan") or "").lower()),
    "vadesi": lambda r: (-num(r.get("vadesi_gecmis")), (r.get("unvan") or "").lower()),
    "bakiye": lambda r: (-num(r.get("bakiye")), (r.get("unvan") or "").lower()),
    "ciro": lambda r: (-num(r.get("net_12ay")), (r.get("unvan") or "").lower()),
    "ad": lambda r: ((r.get("unvan") or "").lower(),),
}


def summary(rows: list[dict[str, Any]], month_ago: list[dict[str, Any]], rule: dict[str, Any]) -> dict[str, Any]:
    """Pano: segment dağılımı (bugün ve ~30 gün önce, ikisi de bugünkü kuralla), vadesi geçmiş ve kovalar, kötüleşenler,
    yoğunlaşma (ilk 10 cari bakiye payı), riske takılı sipariş ve sorunlu müşteri sayısı."""
    def dist(rs: list[dict[str, Any]], recompute: bool) -> dict[str, dict[str, int]]:
        d = {g: {s: 0 for s in SEGMENTS} for g in ("standart", "anahtar")}
        for r in rs:
            if r.get("hareketsiz"):
                continue
            seg, grp = (evaluate(_raw_from_row(r), rule)["segment"], group_of(_raw_from_row(r), rule)) if recompute else (r.get("segment"), r.get("grup"))
            if seg:
                d.setdefault(grp or "standart", {s: 0 for s in SEGMENTS})[seg] += 1
        return d

    active = [r for r in rows if not r.get("hareketsiz")]
    worse_rows = sorted([r for r in active if worse(r.get("segment"), r.get("onceki_segment"))],
                        key=lambda r: -(r.get("skor") or 0))
    trend_rows = sorted([r for r in active if r.get("egilim") == "kotulesiyor"], key=lambda r: -(r.get("skor") or 0))
    pos = sorted((num(r.get("bakiye")) for r in rows if num(r.get("bakiye")) > 0), reverse=True)
    tot = sum(pos)
    return {
        "cari": len(rows), "aktif": len(active), "hareketsiz": len(rows) - len(active),
        "segment": dist(rows, False), "segment30": dist(month_ago, True) if month_ago else None,
        "bakiye": round(sum(num(r.get("bakiye")) for r in rows), 2),
        "vadesiGecmis": round(sum(num(r.get("vadesi_gecmis")) for r in rows), 2),
        "kovalar": {k: round(sum(num(r.get(k)) for r in rows), 2) for k, _ in F.BUCKETS},
        "kovaCari": {k: sum(1 for r in rows if num(r.get(k)) > 0) for k, _ in F.BUCKETS},
        "plansiz": round(sum(num(r.get("plansiz")) for r in rows), 2),
        "yogunlasma10": round(sum(pos[:10]) / tot, 4) if tot > 0 else None,
        "siparisRiskte": sum(int(num(r.get("siparis_riskte"))) for r in rows),
        "sorunlu": sum(1 for r in rows if r.get("sorunlu")),
        "cekOlayCari": sum(1 for r in rows if num(r.get("karsiliksiz")) or num(r.get("protesto"))),
        "kotulesenler": [dealer_row(r) for r in worse_rows],
        "egilimKotu": [dealer_row(r) for r in trend_rows],
    }


def score_history(engine: sa.engine.Engine, tenant: str, code: str, since: str) -> list[dict[str, Any]]:
    q = sa.select(SCORES.c.gun, SCORES.c.skor, SCORES.c.segment, SCORES.c.kural_surum, SCORES.c.vadesi_gecmis, SCORES.c.bakiye) \
        .where(SCORES.c.tenant_id == tenant, SCORES.c.logo_code == code, SCORES.c.gun >= since).order_by(SCORES.c.gun)
    with engine.connect() as c:
        return [{"gun": g, "skor": s, "segment": seg, "kural": k, "vadesiGecmis": v, "bakiye": b} for g, s, seg, k, v, b in c.execute(q)]


def series(engine: sa.engine.Engine, tenant: str, code: str) -> list[dict[str, Any]]:
    with engine.connect() as c:
        r = c.execute(sa.select(SERIES.c.seri_json).where(SERIES.c.tenant_id == tenant, SERIES.c.logo_code == code)).first()
    return _j(r[0], []) if r else []


def bmts(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    acc: dict[str, dict[str, Any]] = {}
    for r in rows:
        if not r.get("bmt"):
            continue
        cur = acc.setdefault(r["bmt"], {"hesap": r["bmt"], "ad": r.get("bmt_ad") or r["bmt"], "cari": 0})
        cur["cari"] += 1
    return sorted(acc.values(), key=lambda x: (x["ad"] or "").lower())


# ------------------------------------------------------------------ limit önerisi (kural)


def _round(v: float, step: float, up: bool = False) -> float:
    """Kuraldaki adıma yuvarlar (en az bir adım). `up`: yukarı — limit mevcut riskin altına inmesin."""
    step = max(1.0, float(step))
    return float(max(step, (math.ceil(v / step) if up else round(v / step)) * step))


def limit_proposal(r: dict[str, Any], rule: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Kural (rakamı kural üretir, satış müdürü onaylar, CRM'e insan işler):
    - D segmenti, limit girilmiş ve risk limitin altında → limit mevcut riske indirilir (yeni açık hesap açılmaz).
    - A segmenti, doluluk ≥ artış eşiği ve son 6 ay önceki 6 aydan küçük değil → limit artış oranı kadar artırılır.
    - A/B segmenti, CRM'de limit girilmemiş ve 12 ayda net alım var → aylık ortalama net alım × kuraldaki ay kadar tanımlanır.
    C segmenti ve hareketsiz cari için öneri yok. CRM eşi olmayan cari için öneri yok (limit CRM'de tutulur)."""
    if r.get("hareketsiz") or not r.get("crm_account_id") or not r.get("segment"):
        return None
    L = rule["limit"]
    seg, lim, risk, fill = r["segment"], opt_num(r.get("limit_toplam")), opt_num(r.get("risk_toplam")), opt_num(r.get("risk_doluluk"))
    step = float(L["yuvarlama"])
    monthly = num(r.get("net_12ay")) / 12
    head = f"Segment {seg} (skor {r.get('skor')})."
    if seg == "D" and lim and lim > 0 and risk is not None and 0 <= risk < lim:
        new = _round(risk, step, up=True) if risk > 0 else 0.0
        if new >= lim:
            return None
        return {"degisim": "azalt", "onerilen": new,
                "gerekce": f"{head} Toplam limit {tr_money(lim)}, risk {tr_money(risk)}. Kural: D segmentinde limit mevcut "
                           f"riske indirilir, yeni açık hesap açılmaz → {tr_money(new)}."}
    if seg == "A" and lim and lim > 0 and fill is not None and fill >= float(L["artisDoluluk"]):
        g = opt_num(r.get("buyume_6ay"))
        if g is not None and g < 0:
            return None
        new = _round(lim * (1 + float(L["artisOrani"])), step)
        return {"degisim": "artir", "onerilen": new,
                "gerekce": f"{head} Limit %{round(fill * 100)} dolu (eşik %{round(float(L['artisDoluluk']) * 100)}), son 6 ay "
                           f"alımı önceki 6 aydan düşük değil. Kural: limit %{round(float(L['artisOrani']) * 100)} artırılır → {tr_money(new)}."}
    if seg in ("A", "B") and not lim and monthly > 0:
        new = _round(monthly * float(L["yeniLimitAy"]), step)
        return {"degisim": "tanimla", "onerilen": new,
                "gerekce": f"{head} CRM'de toplam limit girilmemiş. 12 ay aylık ortalama net alım {tr_money(round(monthly, 2))}. "
                           f"Kural: {L['yeniLimitAy']:g} aylık alım kadar limit tanımlanır → {tr_money(new)}."}
    return None


def _proposal_out(r: dict[str, Any]) -> dict[str, Any]:
    return {"id": r["id"], "code": r["logo_code"], "unvan": r.get("unvan"), "bmt": r.get("bmt"), "gun": r["gun"],
            "segment": r.get("segment"), "skor": r.get("skor"), "mevcut": _j(r.get("mevcut_json"), {}),
            "degisim": r["degisim"], "degisimAd": CHANGE_LABEL.get(r["degisim"], r["degisim"]),
            "onerilen": r["onerilen_toplam"], "gerekceKural": r["gerekce_kural"], "gerekceMetin": r.get("gerekce_metin"),
            "gerekceKaynak": r.get("gerekce_kaynak"), "kuralSurum": r["kural_surum"], "durum": r["durum"],
            "durumAd": PROPOSAL_STATES.get(r["durum"], r["durum"]), "olusturma": _iso(r.get("olusturma")),
            "kararVeren": r.get("karar_veren"), "kararAt": _iso(r.get("karar_at")), "kararNotu": r.get("karar_notu"),
            "crmIsleyen": r.get("crm_isleyen"), "crmIslendiAt": _iso(r.get("crm_islendi_at"))}


def sync_proposals(engine: sa.engine.Engine, tenant: str, rows: list[dict[str, Any]], rule: dict[str, Any], gun: str) -> dict[str, Any]:
    """Günün satırlarından öneri: aynı cari için açık öneri aynıysa dokunulmaz; farklıysa eskisi «koşul kalktı» olur ve
    yenisi açılır; kural artık önermiyorsa açık öneri «koşul kalktı» olur. Karara bağlanmış öneriye dokunulmaz."""
    with engine.connect() as c:
        open_ = {r.logo_code: _row(r) for r in c.execute(sa.select(PROPOSALS).where(PROPOSALS.c.tenant_id == tenant, PROPOSALS.c.durum == "oneri"))}
    new_ids, dropped = [], 0
    with engine.begin() as c:
        for r in rows:
            p = limit_proposal(r, rule)
            cur = open_.pop(r["logo_code"], None)
            if cur and p and cur["degisim"] == p["degisim"] and abs(cur["onerilen_toplam"] - p["onerilen"]) < 0.5:
                continue
            if cur:
                c.execute(PROPOSALS.update().where(PROPOSALS.c.id == cur["id"]).values(durum="gecersiz", karar_at=_now(),
                                                                                       karar_notu="Kural artık bu öneriyi vermiyor."))
                dropped += 1
            if p:
                pid = _new_id()
                mevcut = {**_j(r.get("limit_json"), {}), "limit_toplam": r.get("limit_toplam"), "risk_toplam": r.get("risk_toplam"),
                          "risk_doluluk": r.get("risk_doluluk")}
                c.execute(PROPOSALS.insert().values(
                    id=pid, tenant_id=tenant, logo_code=r["logo_code"], unvan=r.get("unvan"), crm_account_id=r.get("crm_account_id"),
                    bmt=r.get("bmt"), gun=gun, segment=r.get("segment"), skor=r.get("skor"), mevcut_json=_dump(mevcut),
                    degisim=p["degisim"], onerilen_toplam=p["onerilen"], gerekce_kural=p["gerekce"], gerekce_kaynak="kural",
                    kural_surum=int(rule["surum"]), durum="oneri", olusturma=_now()))
                new_ids.append(pid)
        for cur in open_.values():            # kapsamdan çıkan cari
            c.execute(PROPOSALS.update().where(PROPOSALS.c.id == cur["id"]).values(durum="gecersiz", karar_at=_now(),
                                                                                   karar_notu="Cari bugünkü listede yok."))
            dropped += 1
    return {"new": new_ids, "dropped": dropped}


def list_proposals(engine: sa.engine.Engine, tenant: str, *, durum: str = "", code: str = "", bmt: Optional[str] = None) -> list[dict[str, Any]]:
    q = sa.select(PROPOSALS).where(PROPOSALS.c.tenant_id == tenant)
    if durum:
        q = q.where(PROPOSALS.c.durum.in_([x for x in durum.split(",") if x]))
    if code:
        q = q.where(PROPOSALS.c.logo_code == code)
    if bmt is not None:
        q = q.where(PROPOSALS.c.bmt == bmt)
    with engine.connect() as c:
        rows = [_row(r) for r in c.execute(q.order_by(PROPOSALS.c.olusturma.desc()))]
    return [_proposal_out(r) for r in rows]


def get_proposal(engine: sa.engine.Engine, tenant: str, pid: str) -> dict[str, Any]:
    with engine.connect() as c:
        r = c.execute(sa.select(PROPOSALS).where(PROPOSALS.c.tenant_id == tenant, PROPOSALS.c.id == pid)).first()
    if r is None:
        raise DealerError("Limit önerisi bulunamadı.", 404)
    return _row(r)


def proposal_by_id(engine: sa.engine.Engine, pid: str) -> Optional[dict[str, Any]]:
    """Günlük turun kendi açtığı öneri (kimlik turdan gelir; kiracı süzgeci gerekmez)."""
    with engine.connect() as c:
        r = c.execute(sa.select(PROPOSALS).where(PROPOSALS.c.id == pid)).first()
    return _row(r) if r else None


def decide_proposal(engine: sa.engine.Engine, tenant: str, user: str, pid: str, approve: bool, note: Optional[str]) -> dict[str, Any]:
    cur = get_proposal(engine, tenant, pid)
    if cur["durum"] != "oneri":
        raise DealerError("Bu öneri karar beklemiyor.", 409)
    if not approve and not (note or "").strip():
        raise DealerError("Reddetme nedenini yazın.", 422)
    vals = {"durum": "onayli" if approve else "red", "karar_veren": user, "karar_at": _now(), "karar_notu": (note or None)}
    with engine.begin() as c:
        c.execute(PROPOSALS.update().where(PROPOSALS.c.id == pid).values(**vals))
    return _proposal_out({**cur, **vals})


def crm_done(engine: sa.engine.Engine, tenant: str, user: str, pid: str) -> dict[str, Any]:
    """Onaylı önerinin CRM'e elle işlendiğinin kaydı (portal CRM'e yazmaz; işleyen kişi ve zaman tutulur)."""
    cur = get_proposal(engine, tenant, pid)
    if cur["durum"] != "onayli":
        raise DealerError("Yalnız onaylı öneri «CRM'e işlendi» diye işaretlenir.", 409)
    vals = {"durum": "crm_islendi", "crm_isleyen": user, "crm_islendi_at": _now()}
    with engine.begin() as c:
        c.execute(PROPOSALS.update().where(PROPOSALS.c.id == pid).values(**vals))
    return _proposal_out({**cur, **vals})


def set_proposal_text(engine: sa.engine.Engine, pid: str, textv: str) -> None:
    with engine.begin() as c:
        c.execute(PROPOSALS.update().where(PROPOSALS.c.id == pid).values(gerekce_metin=textv[:2000], gerekce_kaynak="zeki"))


def proposal_prompt(p: dict[str, Any]) -> str:
    return ("Bir kitap bayisinin kredi limiti için kuraldan çıkan öneri ve gerekçesi aşağıda. Satış müdürü için tek, kısa, "
            "Türkçe bir gerekçe cümlesi yaz. Yalnız verilen rakamları aynen kullan; yeni rakam, oran ya da tarih yazma. "
            "Skor müşteriye söylenmez, cümle iç kullanım içindir.\n\n"
            f"ÖNERİ: {CHANGE_LABEL.get(p['degisim'], p['degisim'])}\nKURAL GEREKÇESİ: {p['gerekce_kural']}")


# ------------------------------------------------------------------ aksiyon


def _action_out(r: dict[str, Any]) -> dict[str, Any]:
    return {"id": r["id"], "code": r["logo_code"], "unvan": r.get("unvan"), "tur": r["tur"], "turAd": ACTION_KINDS.get(r["tur"], r["tur"]),
            "sahip": r["sahip"], "termin": r.get("termin"), "durum": r["durum"], "durumAd": ACTION_STATES.get(r["durum"], r["durum"]),
            "notu": r.get("notu"), "olusturan": r["olusturan"], "olusturma": _iso(r.get("olusturma")),
            "guncelleyen": r.get("guncelleyen"), "guncelleme": _iso(r.get("guncelleme"))}


_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _day_arg(v: Any, what: str) -> Optional[str]:
    if v in (None, ""):
        return None
    s = str(v).strip()[:10]
    if not _DAY.match(s):
        raise DealerError(f"{what} YYYY-AA-GG olmalı.", 422)
    try:
        date.fromisoformat(s)
    except ValueError:
        raise DealerError(f"{what} geçerli bir tarih değil.", 422) from None
    return s


def add_action(engine: sa.engine.Engine, tenant: str, user: str, row: dict[str, Any], body: dict[str, Any], can_assign: bool) -> dict[str, Any]:
    tur = str(body.get("tur") or "ziyaret")
    if tur not in ACTION_KINDS:
        raise DealerError("Aksiyon türü ziyaret, arama, limit ya da diger olmalı.", 422)
    owner = (text(body.get("sahip")) or user).lower()
    if owner != user and not can_assign:
        raise DealerError("Başkasına aksiyon atamak bütün bayileri görme yetkisi ister.", 403)
    rec = {"id": _new_id(), "tenant_id": tenant, "logo_code": row["logo_code"], "unvan": row.get("unvan"), "tur": tur,
           "sahip": owner[:120], "termin": _day_arg(body.get("termin"), "Termin"), "durum": "acik",
           "notu": ((text(body.get("notu")) or "")[:2000] or None), "olusturan": user, "olusturma": _now()}
    with engine.begin() as c:
        c.execute(ACTIONS.insert().values(**rec))
    return _action_out(rec)


def update_action(engine: sa.engine.Engine, tenant: str, user: str, aid: str, body: dict[str, Any], manage: bool) -> tuple[dict[str, Any], dict[str, Any]]:
    with engine.connect() as c:
        r = c.execute(sa.select(ACTIONS).where(ACTIONS.c.tenant_id == tenant, ACTIONS.c.id == aid)).first()
    if r is None:
        raise DealerError("Aksiyon bulunamadı.", 404)
    cur = _row(r)
    if user not in (cur["sahip"], cur["olusturan"]) and not manage:
        raise DealerError("Aksiyonu sahibi ya da açan değiştirir.", 403)
    vals: dict[str, Any] = {}
    if "durum" in body:
        if body["durum"] not in ACTION_STATES:
            raise DealerError("Durum acik, yapildi ya da iptal olmalı.", 422)
        vals["durum"] = body["durum"]
    if "termin" in body:
        vals["termin"] = _day_arg(body.get("termin"), "Termin")
    if "notu" in body:
        vals["notu"] = (text(body.get("notu")) or "")[:2000] or None
    diff = {k: {"eski": cur.get(k), "yeni": v} for k, v in vals.items() if cur.get(k) != v}
    vals.update(guncelleyen=user, guncelleme=_now())
    with engine.begin() as c:
        c.execute(ACTIONS.update().where(ACTIONS.c.id == aid).values(**vals))
    return _action_out({**cur, **vals}), diff


def list_actions(engine: sa.engine.Engine, tenant: str, *, codes: Optional[set[str]], viewer: str, code: str = "",
                 durum: str = "", sahip: str = "") -> list[dict[str, Any]]:
    """Aksiyonlar. `codes` verilirse (kapsamlı kişi) yalnız o cariler ve kişinin kendi aksiyonları."""
    q = sa.select(ACTIONS).where(ACTIONS.c.tenant_id == tenant)
    if code:
        q = q.where(ACTIONS.c.logo_code == code)
    if durum:
        q = q.where(ACTIONS.c.durum == durum)
    if sahip:
        q = q.where(ACTIONS.c.sahip == sahip.lower())
    with engine.connect() as c:
        rows = [_row(r) for r in c.execute(q.order_by(ACTIONS.c.durum, ACTIONS.c.termin.is_(None), ACTIONS.c.termin, ACTIONS.c.olusturma.desc()))]
    if codes is not None:
        rows = [r for r in rows if r["logo_code"] in codes or viewer in (r["sahip"], r["olusturan"])]
    return [_action_out(r) for r in rows]


# ------------------------------------------------------------------ risk brifi (olgular, kural brifi, model denetimi)


def facts_of(r: dict[str, Any], visits: list[dict[str, Any]]) -> list[str]:
    """Brifin olgu cümleleri (modelin tek girdisi; brifteki her sayı buradan gelmek zorunda). Skor müşteriye söylenmez."""
    f = [f"Bakiye: {tr_money(num(r.get('bakiye')))}; vadesi geçmiş (yaklaşık, FIFO): {tr_money(num(r.get('vadesi_gecmis')))}; "
         f"90 günü geçen: {tr_money(num(r.get('k_90p')))}."]
    if r.get("son_odeme"):
        f.append(f"Son ödeme: {r['son_odeme']}.")
    else:
        f.append("Son 12 ayda ödeme kaydı yok.")
    f.append(f"Son 12 ay net alım: {tr_money(num(r.get('net_12ay')))}"
             + (f"; iade oranı %{round(num(r.get('iade_orani')) * 100)}." if r.get("iade_orani") is not None else "."))
    kk, pr = int(num(r.get("karsiliksiz"))), int(num(r.get("protesto")))
    if kk or pr:
        f.append(f"Son 12 ayda {kk} karşılıksız, {pr} protestolu çek/senet.")
    if r.get("limit_toplam"):
        f.append(f"CRM toplam limit {tr_money(num(r.get('limit_toplam')))}, risk {tr_money(num(r.get('risk_toplam')))}"
                 + (f" (%{round(num(r.get('risk_doluluk')) * 100)} dolu)." if r.get("risk_doluluk") is not None else "."))
    elif r.get("crm_account_id"):
        f.append("CRM'de limit girilmemiş.")
    if int(num(r.get("siparis_riskte"))):
        f.append(f"{int(num(r.get('siparis_riskte')))} sipariş risk onayı bekliyor ({tr_money(num(r.get('siparis_riskte_tutar')))}).")
    if r.get("sorunlu"):
        f.append("CRM'de «Sorunlu Müşteri» olarak işaretli.")
    if r.get("egilim"):
        f.append(f"Risk eğilimi (30 gün): {TREND_LABEL.get(r['egilim'], r['egilim']).lower()}.")
    last = next((v for v in visits if v.get("notu") and not v.get("gizli") and not v.get("gizliNot")), None)
    if last:
        f.append(f"Son görüşme notu ({(last.get('gerceklesen') or last.get('planlanan') or '')[:10]}): {last['notu'][:200]}")
    return f


#: Kural brifinin «konuşulacaklar» şablonları (bileşen → madde); model yoksa ya da denetimden geçmezse bunlar gösterilir.
TALK = {
    "gecikme": "Vadesi geçmiş alacak için ödeme tarihini ve tutarını netleştirin.",
    "cek": "Karşılıksız/protestolu çek-senet olayını ve yeni ödemenin güvencesini konuşun.",
    "iade": "İade oranının nedenini (stok fazlası, yanlış ürün, kampanya) sorun.",
    "limit": "Limit dolu: yeni sipariş öncesi ödeme ya da ek güvence konuşun.",
    "duzensizlik": "Alım düzensiz: düzenli sipariş planı ve raf durumunu konuşun.",
    "tahsilat_suresi": "Tahsilat süresi uzun: vade şartlarını hatırlatın.",
}


def rule_brief(r: dict[str, Any], visits: list[dict[str, Any]]) -> tuple[str, list[str]]:
    facts = facts_of(r, visits)
    comps = [c for c in _j(r.get("bilesen_json"), []) if c.get("puan", 0) > 0]
    items = [TALK[c["key"]] for c in comps if c["key"] in TALK][:3]
    if len(items) < 3:
        items += [x for x in ("Yeni çıkan ve sezonluk kitapları, sipariş ihtiyacını konuşun.",
                              "Rafta dönmeyen ürün ve iade beklentisini sorun.",
                              "Bir sonraki ziyaret tarihini kararlaştırın.") if x not in items][: 3 - len(items)]
    return " ".join(facts[:4]), items


def brief_prompt(facts: list[str]) -> str:
    return ("Aşağıda saha temsilcisinin ziyaret edeceği bir kitapçı/bayinin olguları var. Telefonda okunacak kısa bir risk "
            "brifi yaz. Biçim tam olarak şöyle olsun:\nÖZET: <en fazla 5 kısa Türkçe cümle: ödeme durumu, alım ve iade, risk "
            "işaretleri>\nKONUŞULACAKLAR:\n- <madde 1>\n- <madde 2>\n- <madde 3>\n\nYalnız verilen rakamları aynen kullan; "
            "yeni rakam, oran ya da tarih yazma, hesap yapma. Risk puanını ya da segmenti yazma. Yaklaşık olan tutarı "
            "«yaklaşık» diye an.\n\nOLGULAR:\n- " + "\n- ".join(facts))


_ITEM = re.compile(r"^\s*(?:[-•*]|\d+[.)])\s*(.+)$")


def parse_brief(textv: str) -> tuple[str, list[str]]:
    """Model çıktısından özet ve maddeler; biçim tutmazsa ('', [])."""
    s = (textv or "").strip()
    m = re.search(r"ÖZET\s*:\s*(.+?)(?:\n\s*KONUŞULACAKLAR\s*:|$)", s, flags=re.S | re.I)
    k = re.search(r"KONUŞULACAKLAR\s*:\s*(.+)$", s, flags=re.S | re.I)
    if not m or not k:
        return "", []
    items = []
    for line in k.group(1).splitlines():
        mm = _ITEM.match(line)
        if mm and mm.group(1).strip():
            items.append(mm.group(1).strip())
    return re.sub(r"\s+", " ", m.group(1)).strip(), items[:3]


def numbers_ok(textv: str, facts: Iterable[str]) -> bool:
    return F.numbers_ok(textv, facts)


def input_hash(facts: list[str]) -> str:
    return hashlib.sha256(_dump(facts).encode("utf-8")).hexdigest()


def cached_brief(engine: sa.engine.Engine, tenant: str, code: str) -> Optional[dict[str, Any]]:
    with engine.connect() as c:
        r = c.execute(sa.select(BRIEFS).where(BRIEFS.c.tenant_id == tenant, BRIEFS.c.logo_code == code)).first()
    return _row(r) if r else None


def save_brief(engine: sa.engine.Engine, tenant: str, code: str, gun: str, h: str, metin: str, items: list[str],
               kaynak: str, model: str, user: str) -> None:
    with engine.begin() as c:
        c.execute(BRIEFS.delete().where(BRIEFS.c.tenant_id == tenant, BRIEFS.c.logo_code == code))
        c.execute(BRIEFS.insert().values(tenant_id=tenant, logo_code=code, gun=gun, girdi_hash=h, metin=metin,
                                         maddeler_json=_dump(items), kaynak=kaynak, model_is=model[:80], olusturan=user,
                                         olusturma=_now()))


# ------------------------------------------------------------------ dışa aktarma ve sabah e-postası


CSV_HEAD = ["Cari kodu", "Unvan", "Kanal", "İl", "Temsilci", "Grup", "Segment", "Skor", "Önceki segment", "Eğilim",
            "Bakiye", "Vadesi geçmiş (yaklaşık)", "1-30", "31-60", "61-90", "90+", "12 ay net alım", "İade oranı",
            "Tahsilat süresi (gün, yaklaşık)", "Karşılıksız", "Protesto", "CRM toplam limit", "CRM toplam risk", "Doluluk",
            "Riske takılı sipariş", "Sorunlu müşteri", "Son ödeme", "Son fatura", "Hareketsiz", "Kural sürümü", "Veri son günü"]


def csv_text(rows: list[dict[str, Any]]) -> str:
    import csv
    import io

    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(CSV_HEAD)
    for r in rows:
        w.writerow([r["logo_code"], r.get("unvan"), r.get("kanal"), r.get("il"), r.get("bmt_ad") or r.get("bmt"), r.get("grup"),
                    r.get("segment"), r.get("skor"), r.get("onceki_segment"), TREND_LABEL.get(r.get("egilim") or "", ""),
                    r.get("bakiye"), r.get("vadesi_gecmis"), r.get("k_1_30"), r.get("k_31_60"), r.get("k_61_90"), r.get("k_90p"),
                    r.get("net_12ay"), r.get("iade_orani"), r.get("dso"), r.get("karsiliksiz"), r.get("protesto"),
                    r.get("limit_toplam"), r.get("risk_toplam"), r.get("risk_doluluk"), r.get("siparis_riskte"),
                    "evet" if r.get("sorunlu") else "", r.get("son_odeme"), r.get("son_fatura"),
                    "evet" if r.get("hareketsiz") else "", r.get("kural_surum"), r.get("veri_son_gunu")])
    return "﻿" + buf.getvalue()


def morning_text(s: dict[str, Any], pending: int, gun: str, data_end: Optional[str], link: str = "") -> str:
    seg = s["segment"]
    lines = [f"Bayi riski — {gun} (Logo verisi {data_end or '—'} tarihine kadar)", "",
             "Segment (standart): " + ", ".join(f"{k} {seg['standart'][k]}" for k in SEGMENTS),
             "Segment (anahtar hesap): " + ", ".join(f"{k} {seg['anahtar'][k]}" for k in SEGMENTS),
             f"Vadesi geçmiş (yaklaşık): {tr_money(s['vadesiGecmis'])} · 90+ gün {tr_money(s['kovalar']['k_90p'])}",
             f"Onay bekleyen limit önerisi: {pending} · riske takılı sipariş: {s['siparisRiskte']}", ""]
    if s["kotulesenler"]:
        lines.append(f"Segmenti düşen bayiler ({len(s['kotulesenler'])}):")
        lines += [f"• {x['unvan'] or x['code']}: {x['oncekiSegment']} → {x['segment']} · vadesi geçmiş {tr_money(num(x['vadesiGecmis']))}"
                  for x in s["kotulesenler"]]
    else:
        lines.append("Segmenti düşen bayi yok.")
    lines += ["", "Vadesi geçmiş tutarlar yaklaşıktır (Logo'da ödeme kapama yok; FIFO). Skor bir sınıflandırmadır, kredi kararı değildir."]
    if link:
        lines.append(link)
    return "\n".join(lines)
