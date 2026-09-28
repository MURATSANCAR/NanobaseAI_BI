"""İhale risk koşulu işaretleme (`/ihale/:id`): şartname metnindeki ceza, teminat, teslim süresi, numune, yerli malı
gibi koşullar **şartnameden birebir alıntıyla** işaretlenir.

Akış (şartname özetiyle aynı dosya, aynı metin okuyucu `tenders.document_text`):

1. **Aday cümle (kural):** metin cümlelere bölünür; risk sözcüğü geçen her cümle adaydır (sözcük listesi `KEYWORDS`,
   genel ihale sözlüğü; ihaleye ya da kuruma özel değildir). Şartname özetinin «kritik koşullar» maddeleri de aday olur
   (alıntıları özet sırasında denetlenmişti; burada yeniden denetlenir). Aday sayısında tavan yok; hepsi işlenir.
2. **Alıntı denetimi:** alıntı (cümle) şartname metninde aynen geçmeli (`tenders.fold` ile); geçmeyen düşer ve sayılır.
   Alıntı dışında model metni yazılmaz: kategori kapalı kümeden seçilir, değer üretilmez.
3. **Kapalı küme seçim (Zeki AI):** her aday için `choose` → kategori ya da «riskli koşul değil»; olasılık ve marj eşiğin
   altındaysa «incelenecek» kalır ve kural ipucu gösterilir. Model yoksa kural ipucu «kurala göre» diye yazılır.

İnsan her işareti «engel / engel değil / bilgi» diye karara bağlar; karar aynı alıntı için yeniden işaretlemede korunur.
Kuruma, EKAP'a ya da başka bir yere hiçbir şey gönderilmez.
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Optional

import sqlalchemy as sa

from semantic_bridge import tenders as T

log = logging.getLogger("semantic.tenders.risk")

RISKS = sa.Table(
    "semantic_tender_risks", T._md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tender_id", sa.String(32), nullable=False, index=True),
    sa.Column("sira", sa.Integer, nullable=False),
    sa.Column("kategori", sa.String(20)),            # CATEGORIES anahtarı; «incelenecek»te kural ipucu
    sa.Column("alinti", sa.Text, nullable=False),
    sa.Column("kaynak", sa.String(10), nullable=False),   # zeki | kural | incele
    sa.Column("ipucu", sa.String(20)),               # kuralın önerdiği kategori
    sa.Column("olasilik", sa.Float),
    sa.Column("marj", sa.Float),
    sa.Column("karar", sa.String(12)),               # engel | engel-degil | bilgi (insan)
    sa.Column("karar_notu", sa.String(500)),
    sa.Column("karar_veren", sa.String(120)),
    sa.Column("karar_zamani", sa.DateTime(timezone=True)),
    sa.Column("dosya", sa.String(300)),
    sa.Column("zaman", sa.DateTime(timezone=True), nullable=False),
)

CATEGORIES = {"ceza": "Ceza / gecikme cezası", "teminat": "Teminat", "teslim-suresi": "Teslim süresi",
              "numune": "Numune", "yerli-mali": "Yerli malı / yerli istekli", "teslim-yeri": "Teslim yeri / nakliye",
              "odeme": "Ödeme koşulu", "fesih": "Fesih / yasaklama", "yeterlik": "Yeterlik / belge şartı",
              "diger": "Diğer risk"}
NONE_LABEL = "Riskli koşul değil"
DECISIONS = {"engel": "Bizim için engel", "engel-degil": "Engel değil", "bilgi": "Bilgi — dikkat"}
#: llm-choose belgesinin «öneri» eşiği; altı «incelenecek».
THRESHOLDS = (0.70, 0.30)

#: Kategori → cümlede aranan sözcük kökleri (`tenders.fold` biçiminde). Sıra önemli: ilk tutan kategori ipucudur.
KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("ceza", ("ceza", "cezai", "gecikme cezasi", "gunluk ceza", "binde", "kesinti yapilir")),
    ("yerli-mali", ("yerli mali", "yerli malli", "yerli istekli", "yerli urun", "fiyat avantaji")),
    ("numune", ("numune", "ornek urun", "tanitim numunesi")),
    ("teminat", ("teminat", "teminat mektubu", "kesin teminat", "gecici teminat")),
    ("teslim-yeri", ("teslim yeri", "nakliye", "tasima", "yerinde teslim", "depoya teslim", "montaj", "istif")),
    ("teslim-suresi", ("teslim suresi", "gun icinde", "takvim gunu", "is gunu icinde", "teslim edilecek", "sure uzatimi")),
    ("odeme", ("odeme", "hakedis", "fatura tarihinden", "muayene kabul")),
    ("fesih", ("fesih", "feshedilir", "ihaleden yasak", "yasaklama", "sozlesme iptal")),
    ("yeterlik", ("is deneyim", "yetkili satici", "yetkili bayi", "kalite belgesi", "iso", "tse", "sertifika",
                  "yeterlik")),
]
_SENT = re.compile(r"(?<=[.;!?])\s+(?=\S)|\n\s*\n|\n(?=\s*(?:\d+[.)-]|[a-zçğıöşü][.)]|-|•))")
MAX_QUOTE = 800
_ABBR = frozenset({"iso", "tse"})


def ensure(engine: sa.engine.Engine) -> None:
    T.ensure(engine)
    RISKS.create(engine, checkfirst=True)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ------------------------------------------------------------------------------------------ saf işlevler

def sentences(text: str) -> list[str]:
    out = []
    for s in _SENT.split(text or ""):
        s = " ".join(s.split())
        if len(s) >= 12:
            out.append(s)
    return out


def hint(sentence: str) -> Optional[str]:
    f = T.fold(sentence)
    for cat, words in KEYWORDS:
        # Sözcük başı zorunlu (ekli biçim tutar: «cezası»); kısaltmada sözcük sonu da («isot…» tutmasın).
        if any(re.search(r"(?<![a-z0-9])" + re.escape(w) + (r"(?![a-z])" if w in _ABBR else ""), f) for w in words):
            return cat
    return None


def quote_ok(quote: str, text_fold: str) -> bool:
    q = T.fold(quote)
    return len(q) >= 8 and q in text_fold


def candidates(text: str, summary: Optional[dict[str, Any]] = None) -> tuple[list[dict[str, Any]], int]:
    """Aday alıntılar (tekrarsız) ve alıntısı metinde bulunamadığı için düşen özet maddesi sayısı. Uzun cümle
    (tablo satırı) `MAX_QUOTE` karakterde parçalanır; her parça yine metnin kendisidir."""
    tf = T.fold(text)
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    dropped = 0

    def add(quote: str, cat: Optional[str], origin: str) -> None:
        k = T.fold(quote)
        if k in seen:
            return
        seen.add(k)
        out.append({"alinti": quote, "ipucu": cat, "kaynakTur": origin})

    for s in sentences(text):
        parts = [s] if len(s) <= MAX_QUOTE else [s[i:i + MAX_QUOTE] for i in range(0, len(s), MAX_QUOTE)]
        for p in parts:
            cat = hint(p)
            if cat and quote_ok(p, tf):
                add(p, cat, "metin")
    for k in (summary or {}).get("kosullar") or []:
        q = str((k or {}).get("kaynak") or "").strip()
        if not q:
            continue
        if not quote_ok(q, tf):
            dropped += 1
            continue
        add(q, hint(q) or hint(str(k.get("deger") or "")) or "diger", "ozet")
    return out, dropped


def prompt(quote: str) -> str:
    return ("Bir yayınevi kamu ihalesine teklif verecek. Aşağıdaki şartname cümlesi teklif veren için hangi tür riskli "
            "koşulu getiriyor? Ceza: gecikme ya da eksik teslim cezası, kesinti. Teminat: geçici/kesin teminat şartı. "
            "Teslim süresi: süre ya da takvim şartı. Numune: numune ya da örnek ürün istenmesi. Yerli malı: yerli malı, "
            "yerli istekli ya da fiyat avantajı şartı. Teslim yeri: yer, nakliye, montaj, istif. Ödeme koşulu: ödeme "
            "zamanı ya da şekli. Fesih: fesih, yasaklama, iptal. Yeterlik: iş deneyimi, yetkili satıcılık, belge ve "
            "sertifika şartı. Diğer risk: bunların dışında risk. Riskli koşul değil: bilgi cümlesi.\n\n"
            f"Cümle: «{quote[:MAX_QUOTE]}»")


def classify(items: list[dict[str, Any]], choose: Optional[Callable[[str, list[str]], Any]],
             progress: Optional[Callable[[int, int], None]] = None) -> list[dict[str, Any]]:
    """Her aday için kategori. Model «riskli koşul değil» derse ve eminse aday düşer; emin değilse incelenecek kalır."""
    labels = [*CATEGORIES.values(), NONE_LABEL]
    back = {v: k for k, v in CATEGORIES.items()}
    out = []
    total = len(items)
    for n, it in enumerate(items, start=1):
        row = {**it, "kategori": it["ipucu"], "kaynak": "kural", "olasilik": None, "marj": None}
        if choose is not None:
            try:
                ch = choose(prompt(it["alinti"]), labels)
                p, m = ch.probability, getattr(ch, "margin", None)
                sure = ch.choice is not None and p is not None and m is not None and p >= THRESHOLDS[0] and m >= THRESHOLDS[1]
                row.update(olasilik=p, marj=m)
                if sure and ch.choice == NONE_LABEL:
                    if progress:
                        progress(n, total)
                    continue
                if sure and ch.choice in back:
                    row.update(kategori=back[ch.choice], kaynak="zeki")
                else:
                    row.update(kaynak="incele")
            except Exception as e:  # noqa: BLE001 — model cevap vermezse kural ipucu, incelenecek
                log.info("ihale risk: model cevap vermedi: %s", e)
                row.update(kaynak="incele")
        out.append(row)
        if progress:
            progress(n, total)
    return out


# ------------------------------------------------------------------------------------------ kayıt

def save(engine: sa.engine.Engine, tid: str, rows: list[dict[str, Any]], file_name: str) -> dict[str, Any]:
    """İhalenin işaretlerini yenisiyle değiştirir; aynı alıntıya verilmiş insan kararı korunur."""
    ensure(engine)
    with engine.begin() as c:
        old = {T.fold(r.alinti): r for r in c.execute(sa.select(RISKS).where(RISKS.c.tender_id == tid))}
        c.execute(RISKS.delete().where(RISKS.c.tender_id == tid))
        for i, r in enumerate(rows, start=1):
            prev = old.get(T.fold(r["alinti"]))
            c.execute(RISKS.insert().values(
                id=uuid.uuid4().hex, tender_id=tid, sira=i, kategori=r["kategori"], alinti=r["alinti"][:MAX_QUOTE * 2],
                kaynak=r["kaynak"], ipucu=r.get("ipucu"), olasilik=r.get("olasilik"), marj=r.get("marj"),
                karar=prev.karar if prev else None, karar_notu=prev.karar_notu if prev else None,
                karar_veren=prev.karar_veren if prev else None, karar_zamani=prev.karar_zamani if prev else None,
                dosya=(file_name or "")[:300], zaman=_now()))
    return {"isaret": len(rows), "kategoriler": {k: sum(1 for r in rows if r["kategori"] == k) for k in CATEGORIES}}


def _out(r: Any) -> dict[str, Any]:
    return {"id": r.id, "sira": r.sira, "kategori": r.kategori, "kategoriAdi": CATEGORIES.get(r.kategori or ""),
            "alinti": r.alinti, "kaynak": r.kaynak, "ipucu": r.ipucu, "olasilik": r.olasilik, "marj": r.marj,
            "karar": r.karar, "kararAdi": DECISIONS.get(r.karar or ""), "kararNotu": r.karar_notu,
            "kararVeren": r.karar_veren, "kararZamani": T._iso(r.karar_zamani), "dosya": r.dosya, "zaman": T._iso(r.zaman)}


def listing(engine: sa.engine.Engine, tenant: str, tid: str) -> dict[str, Any]:
    ensure(engine)
    with engine.connect() as c:
        T._tender_row(c, tenant, tid)
        rows = [_out(r) for r in c.execute(sa.select(RISKS).where(RISKS.c.tender_id == tid).order_by(RISKS.c.sira))]
    return {"items": rows, "kategoriler": CATEGORIES, "kararlar": DECISIONS,
            "engel": sum(1 for r in rows if r["karar"] == "engel"), "kararsiz": sum(1 for r in rows if not r["karar"])}


def decide(engine: sa.engine.Engine, tenant: str, user: str, tid: str, rid: str, body: dict[str, Any]) -> dict[str, Any]:
    karar = body.get("karar")
    if karar not in (*DECISIONS, None, ""):
        raise T.TenderError("Karar «engel», «engel-degil» ya da «bilgi» olmalı.", 422)
    kategori = body.get("kategori")
    if kategori not in (*CATEGORIES, None, ""):
        raise T.TenderError("Bilinmeyen kategori.", 422)
    ensure(engine)
    with engine.begin() as c:
        T._tender_row(c, tenant, tid)
        r = c.execute(sa.select(RISKS).where(RISKS.c.tender_id == tid, RISKS.c.id == rid)).first()
        if r is None:
            raise T.TenderError("İşaret bulunamadı.", 404)
        values: dict[str, Any] = {"karar": karar or None, "karar_notu": (str(body.get("not") or "")[:500] or None),
                                  "karar_veren": user if karar else None, "karar_zamani": _now() if karar else None}
        if kategori:
            values["kategori"] = kategori
        c.execute(RISKS.update().where(RISKS.c.id == rid).values(**values))
        row = c.execute(sa.select(RISKS).where(RISKS.c.id == rid)).first()
    return _out(row)
