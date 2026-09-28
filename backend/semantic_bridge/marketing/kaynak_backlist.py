"""M17 Backlist: ekrandaki her rakamın sorgu bilgisi (ortak sözleşme `provenance.py`).

Backlist rakamları gece hesabının (`backlist.build`, `timas-marketing-backlist.timer`) yazdığı tablolardan okunur:
kitap satırı (12/12 ay, değişim, stok, tükenme, tahmin, marj, bileşen yüzdelikleri), 36 ay seri, kampanya etkisi ve CRM
eşleşmeleri. Ekranda gösterilen SQL uçta çalışan portal okumasıdır (`backlist.*_stmt`); tabloyu dolduran asıl sorgular
(Logo depo stoku, yıl yıl Logo satışı — bütçe modülünün önbelleği ya da bu modülün geçmiş yıl okuması —, CRM kitap
kartı, özel gün, bağ, yazarın yeni kitabı, kampanya) gece hesabının kaydettiği çalışmış metinlerle `origin`dir.
"""
from __future__ import annotations

from typing import Any, Optional

import sqlalchemy as sa

from semantic_bridge import budget as B
from semantic_bridge import budget_sources as bsrc
from semantic_bridge import pazarlama_kaynak as PK
from semantic_bridge import provenance as P
from semantic_bridge.marketing import backlist as BL
from semantic_bridge.marketing import books as BK
from semantic_bridge.marketing import core as C

NOT_RAKAM = ("page", "pageSize", "hafta", "yillar", "items[].surum", "items[].kitaplar[].sira", "items[].planlar[].surum",
             "planlar[].surum", "agirlik")

SQL_NAMES = {
    "stok": ("logo", "Logo depo stoku", "Baskı Öneri ile aynı depo stoku görünümü."),
    "crmKitap": ("crm", "CRM kitap kartları", "Hedef kitle, yaş / sınıf, türler, e-kitap alanları, satış durumu."),
    "crmGun": ("crm", "CRM özel günleri", "Özel günlerin tarih bilgisi; sıradaki ve geçen yılki gerçekleşme hesaplanır."),
    "crmGunBag": ("crm", "CRM kitap × özel gün bağları", "Kitaba bağlı özel günler."),
    "crmYazar": ("crm", "CRM yazarın yeni kitabı", "Backlist kitabının yazarının yakında çıkan yeni kitabı."),
    "crmKampanya": ("crm", "CRM kampanyaları ve ürünleri", "Kampanya etkisi için kampanya penceresi, iskonto, planlanan ve "
                    "gerçekleşen ciro."),
}

F_SATIR = ("Kitap satırı gece hesabında yazılır: son 12 / önceki 12 tam ay net adet ve değişim (son ÷ önceki − 1), son 12 ay "
           "net ciro, marj = 1 − maliyet ÷ maliyetli ciro; stok = Logo depo stoku; tükenme (ay) = stok ÷ (son 12 ay adet ÷ "
           "12); tahmin 12 ay = Baskı Öneri tahmin servisinin 12 aylık p50 toplamı (servis önbelleği); hedef durumu ve açık "
           "sapma bütçe modülünden.")
F_ENDEKS = ("Uyku endeksi = bileşen yüzdeliklerinin ağırlıklı ortalaması (ağırlıklar ekrandaki; bileşen yüzdeliği backlist "
            "kümesi içinde sıra). Bileşenler ve formül ekranın «Endeks» açıklamasında.")
F_KPI = ("Sayılar kümenin tamamından: açık sapma = bütçe modülünde açık satış sapması olan kitap; stokta = depo stoku > 0; "
         "yaklaşan özel gün = gündem penceresinde bağlı özel günü olan; planlı = arşiv dışı bir backlist aktivasyon planında "
         "geçen. «Toplam» süzgeçten geçen, «hepsi» kümedeki kitap sayısı.")
F_SERI = "Aylık seri = kitabın ay ay Logo faturalı net adedi ve net cirosu (son 36 tam ay)."
F_ETKI = ("Kampanya etkisi (ay düzeyi): kampanya başlangıç ayından önceki 3 ay, kampanya ayları, bitişten sonraki 2 ay Logo "
          "net adedi; aylık ortalama değişim = (kampanya adedi ÷ kampanya ay sayısı) ÷ (önceki 3 ay ÷ 3) − 1. Planlanan ve "
          "gerçekleşen ciro CRM kampanya kartından. Nedensellik iddiası değildir.")
F_GUNDEM = ("Gündem: önümüzdeki haftalardaki özel günler (CRM bağı), yazarı yeni kitap çıkaran kitaplar ve konu eşleşmeleri; "
            "kitap başına stok ve tükenme kitap satırından, geçen yıl aynı ay adet aylık seriden; eşleşme skoru Zeki AI'ın "
            "kapalı küme kararındaki güven (satış rakamı değildir).")
F_AKTIVASYON = "Aktivasyon planı bütçesi = planın kanal ve bütçe satırlarının toplamı; kitaplar planın kitap listesinden."


def origins(k: P.Kaynaklar, engine: Any, tenant: str, logo_db: Optional[str]) -> list[str]:
    """Gece hesabının okuduğu asıl sorgular (kaydedilmiş çalışmış metinler)."""
    meta = C.meta_get(engine, tenant, "backlist")
    ids: list[str] = []
    for key, (conn, title, desc) in SQL_NAMES.items():
        text = (meta.get("sql") or {}).get(key)
        if not text:
            continue
        try:
            ids.append(k.sorgu(f"backlist.{key}", title, conn, text, description=desc, ran_at=meta.get("_at"),
                               database=PK.crm_db() if conn == "crm" else logo_db))
        except P.ProvenanceError:
            continue
    for y, how in sorted((meta.get("yillar") or {}).items()):
        yi = int(y)
        if how == "m46":
            ids.append(PK.butce_satis(k, engine, f"backlist.butce.{yi}", f"Bütçe modülünün satış önbelleği · {yi}",
                                      sa.select(B.SALES).where(B.SALES.c.year == yi), [yi], logo_db))
        elif how == "logo":
            pm = C.meta_get(engine, tenant, f"backlist-sales:{yi}")
            if pm.get("firm"):
                ids.append(k.portal(f"backlist.gecmis.{yi}", f"Geçmiş yıl satış önbelleği · {yi}", BL.past_stmt(yi), engine,
                                    origin=[k.sorgu(f"backlist.logo.satis.{yi}", f"Logo satış satırları · {yi}", "logo",
                                                    bsrc.sales_sql(pm["firm"], yi), database=logo_db, rows=pm.get("rows"),
                                                    ran_at=pm.get("_at"), period=f"{yi} · Logo firma {pm['firm']}")]))
    hy = meta.get("hedefYil")
    if hy:
        ids.append(k.portal(f"backlist.sapma.{hy}", f"Açık satış sapmaları · {hy}",
                            B.deviations_stmt(tenant, int(hy), status="acik", kind="satis", scope="kitap"), engine,
                            description="Bütçe modülünün açık kitap satış sapmaları (tutar ve durum)."))
        try:
            with engine.connect() as c:
                plan = c.execute(B.approved_stmt(tenant, int(hy))).first()
        except sa.exc.SQLAlchemyError:
            plan = None
        if plan is not None:
            ids.append(k.portal(f"backlist.hedef.{hy}", f"Backlist kitap hedefleri · {hy}",
                                sa.select(B.BOOKS).where(B.BOOKS.c.plan_id == plan.id, B.BOOKS.c.segment == "backlist")
                                .order_by(B.BOOKS.c.ciro.desc(), B.BOOKS.c.stok_kodu), engine,
                                description="Yürürlükteki bütçe planının backlist segmenti (küme ve hedef)."))
    return ids


def _rows(k: P.Kaynaklar, engine: Any, tenant: str, logo_db: Optional[str]) -> str:
    return k.portal("backlist.satir", "Backlist kitap satırları", BL.rows_stmt(tenant), engine,
                    origin=origins(k, engine, tenant, logo_db),
                    description="Gece hesabının yazdığı kitap satırları (semantic_mkt_backlist_rows).")


def _new(engine: Any, tenant: str) -> P.Kaynaklar:
    m = C.meta_get(engine, tenant, "backlist")
    return P.Kaynaklar(data_end=m.get("veriSonu"), as_of=m.get("_at"))


def for_list(engine: Any, tenant: str, out: dict[str, Any], logo_db: Optional[str]) -> P.Kaynaklar:
    k = _new(engine, tenant)
    rows = _rows(k, engine, tenant, logo_db)
    plans = k.portal("backlist.planli", "Kitapların backlist planları", _by_codes_stmt(tenant), engine,
                     description="Arşiv dışı backlist aktivasyon planlarında geçen kitaplar.")
    satir = k.hesap("satir", F_SATIR, [rows])
    k.alanlar({"items[]": satir, "items[].endeks": k.hesap("endeks", F_ENDEKS, [rows]), "items[].bilesen": "hesap:endeks",
               "kpi": k.hesap("kpi", F_KPI, [rows, plans]), "total": "hesap:kpi", "hepsi": "hesap:kpi",
               "gunler[]": "hesap:kpi", "run": satir})
    return k


def _by_codes_stmt(tenant: str, codes: Optional[list[str]] = None):
    cond = [C.PLANS.c.tenant_id == tenant, C.PLANS.c.kind == "backlist", C.PLANS.c.durum != "arsiv"]
    if codes:
        cond.append(BK.PLAN_BOOKS.c.stok_kodu.in_(codes))
    return (sa.select(BK.PLAN_BOOKS.c.stok_kodu, BK.PLAN_BOOKS.c.rol, C.PLANS.c.id, C.PLANS.c.kind, C.PLANS.c.durum,
                      C.PLANS.c.baslik, C.PLANS.c.yayin_tarihi, C.PLANS.c.surum)
            .select_from(BK.PLAN_BOOKS.join(C.PLANS, C.PLANS.c.id == BK.PLAN_BOOKS.c.plan_id)).where(*cond)
            .order_by(C.PLANS.c.id.desc()))


def for_detail(engine: Any, tenant: str, code: str, logo_db: Optional[str]) -> P.Kaynaklar:
    k = _new(engine, tenant)
    org = origins(k, engine, tenant, logo_db)
    row = k.portal("backlist.kitap", "Kitap satırı", BL.row_stmt(tenant, code), engine, origin=org)
    ser = k.portal("backlist.seri", "Aylık seri", BL.series_stmt(tenant, code), engine, origin=org)
    eff = k.portal("backlist.etki", "Kampanya etkileri", BL.effects_code_stmt(tenant, code), engine, origin=org)
    mts = k.portal("backlist.eslesme", "CRM ve konu eşleşmeleri", BL.matches_code_stmt(tenant, code), engine, origin=org)
    satir = k.hesap("satir", F_SATIR, [row])
    k.alanlar({"adetSon12": satir, "adetOnceki12": satir, "degisim": satir, "ciroSon12": satir, "marj": satir, "stok": satir,
               "tukenmeAy": satir, "tahmin12": satir, "m46": satir, "endeks": k.hesap("endeks", F_ENDEKS, [row]),
               "endeksVarsayilan": "hesap:endeks", "bilesen": "hesap:endeks", "seri[]": k.hesap("seri", F_SERI, [ser]),
               "kampanyalar[]": k.hesap("etki", F_ETKI, [eff]), "eslesmeler[]": k.hesap("gundem", F_GUNDEM, [mts]),
               "planlar[]": mts})
    return k


def for_agenda(engine: Any, tenant: str, out: dict[str, Any], logo_db: Optional[str]) -> P.Kaynaklar:
    k = _new(engine, tenant)
    org = origins(k, engine, tenant, logo_db)
    mts = k.portal("backlist.eslesme", "CRM ve konu eşleşmeleri", BL.matches_stmt(tenant), engine, origin=org)
    with engine.connect() as c:
        codes = sorted({m.stok_kodu for m in c.execute(BL.matches_stmt(tenant)).all()})
    rows = k.portal("backlist.satir", "Eşleşen kitapların satırları", BL.rows_in_stmt(tenant, codes), engine, origin=org)
    ser = k.portal("backlist.seri", "Eşleşen kitapların aylık serisi", BL.series_in_stmt(tenant, codes), engine, origin=org)
    ref = k.hesap("gundem", F_GUNDEM, [mts, rows, ser])
    k.alanlar({"gunler[]": ref, "yazarlar[]": ref, "konular[]": ref})
    return k


def for_effects(engine: Any, tenant: str, yil: Optional[int], only_backlist: bool, logo_db: Optional[str]) -> P.Kaynaklar:
    k = _new(engine, tenant)
    org = origins(k, engine, tenant, logo_db)
    eff = k.portal("backlist.etki", "Kampanya etkileri", BL.effects_stmt(tenant, yil, only_backlist), engine, origin=org)
    ref = k.hesap("etki", F_ETKI, [eff])
    k.alanlar({"items[]": ref, "total": ref})
    return k


def for_activations(engine: Any, tenant: str, out: dict[str, Any], durum: str = "", include_archive: bool = False) -> P.Kaynaklar:
    k = P.Kaynaklar()
    plans = k.portal("backlist.aktivasyon", "Backlist aktivasyon planları",
                     C.plans_stmt(tenant, kind="backlist", durum=durum, include_archive=include_archive), engine,
                     description="Plan başlığı, durum, bütçe toplamı (satır toplamı).")
    ids = [p["id"] for p in out.get("items") or []]
    extra = [plans]
    for pid in ids:
        extra.append(k.portal(f"backlist.aktivasyon.satir:{pid}", f"Plan satırları · {pid}", C.lines_stmt(pid), engine))
        extra.append(k.portal(f"backlist.aktivasyon.kitap:{pid}", f"Plan kitapları · {pid}", BK.of_stmt(pid), engine))
    ref = k.hesap("aktivasyon", F_AKTIVASYON, extra)
    k.alanlar({"items[]": ref, "total": ref})
    return k


def for_plan_books(engine: Any, plan_id: str) -> P.Kaynaklar:
    k = P.Kaynaklar()
    k.alanlar({"items[]": k.portal("backlist.plan.kitap", "Planın kitapları", BK.of_stmt(plan_id), engine)})
    return k
