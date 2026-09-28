"""M21 Dijital reklam: ekrandaki her rakamın sorgu bilgisi (ortak sözleşme `provenance.py`).

Harcama, tıklama, gösterim, dönüşüm değeri yüklenen reklam raporlarının kampanya-gün tablosundan (semantic_ads_daily);
e-ticaret cirosu, kitap satışı ve stok bu modülün Logo önbelleğinden (semantic_ads_ecom*, semantic_ads_stock) — önbelleği
dolduran Logo sorguları yenileme işinin kaydettiği çalışmış metinleriyle `origin`dir. CRM okumaları (kitap kartları, reklam
planları, pazarlama bütçe kayıtları) `ads_sources` üreticileriyle çalışan metin.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Iterable, Optional

from semantic_bridge import ads as A
from semantic_bridge import ads_sources as S
from semantic_bridge import pazarlama_kaynak as PK
from semantic_bridge import provenance as P

LOGO_SQL_KEY = "logo-sql"
NOT_RAKAM = ("settings", "shown", "gun", "surum", "yil", "year")

F_METRIC = ("Reklam ölçüleri kampanya-gün satırlarından (yüklenen platform raporu; ana para birimi TL): harcama, gösterim, "
            "tıklama, dönüşüm, dönüşüm değeri toplamı; TBM = harcama ÷ tıklama; TO = tıklama ÷ gösterim; platform ROAS = "
            "dönüşüm değeri ÷ harcama; pay = kanal harcaması ÷ toplam. Başka para birimindeki satır TL toplamına katılmaz.")
F_VERIM = ("E-ticaret cirosu Logo önbelleğinden (e-ticaret kanalları, günlük); pazarlama verimi = e-ticaret cirosu ÷ Logo veri "
           "sonuna kadar olan dönemdeki harcama. Kitap satırında satış = o kitabın e-ticaret / toplam cirosu ve adedi, verim = "
           "kitabın e-ticaret cirosu ÷ kitabın harcaması, stok günü = Logo bakiyesi ÷ son N gün günlük satış; M15 = kitabın "
           "onaylı pazarlama planındaki reklam kanalı satırları; bağsız harcama = kitaba bağlanmamış kampanyaların harcaması.")
F_BUDGET = ("Bütçe ay × kanal: plan = bu ekranda girilen plan; harcama = yüklenen raporların TL harcaması; M15 = onaylı kitap "
            "planlarının reklam kanalı satırları (başlangıç–bitiş günlerine eşit dağıtılıp aya bölünür); CRM = pazarlama bütçe "
            "modülünün dijital / sosyal medya tipli kayıtları; ay sonu tahmini = harcama ÷ geçen gün × ayın günü.")
F_SUGG = ("Öneriler gece kurallarından (stok azaldı, satış dışı, veri yok, bütçe aşımı, düşük verimli kampanyayı durdur, bütçe "
          "kaydır): her önerinin verisi kuralın okuduğu sayılardır.")
F_IMPORT = "Yükleme: dosyadaki satır, kampanya-gün, para birimi toplamları; «geçerli» = sonraki yüklemenin ezmediği satır ve harcaması."
F_CRM = ("CRM reklam planları (dönemle kesişen, onaysız sayısı) ve pazarlama bütçe kayıtları (dönemde başlayan; reklam toplamı = "
         "dijital / sosyal medya tipli kayıtlar).")


def _schema() -> str:
    from semantic_bridge import admin as admin_mod

    return admin_mod.conf("CRM_SCHEMA") or "Timas_MSCRM.dbo"


def _crm(k: P.Kaynaklar, id_: str, title: str, sql: str) -> str:
    return k.sorgu(id_, title, "crm", sql, database=PK.crm_db(), description="CRM okuması (kısa süre bellekte tutulur).")


def logo_origin(k: P.Kaynaklar, engine: Any, tenant: str, logo_db: Optional[str], kind: str = "") -> list[str]:
    """Logo önbelleğini dolduran, yenileme işinin kaydettiği çalışmış sorgular. `kind`: metinde aranan tablo ipucu."""
    runs = (A.meta_get(engine, tenant, LOGO_SQL_KEY) or {}).get("runs") or []
    match = (lambda s: kind.lower() in s.lower()) if kind else None
    return PK.kayitli(k, runs, f"reklam.logo{('.' + kind) if kind else ''}", logo_db, match=match,
                      description="Reklam modülünün Logo önbelleğini dolduran sorgu (yenileme işi).")


def _veri_sonu(k: P.Kaynaklar, engine: Any, tenant: str) -> str:
    return k.portal("reklam.verisonu", "Logo veri sonu ve son yenileme", A.meta_stmt(tenant, "logo"), engine)


def for_overview(engine: Any, tenant: str, out: dict[str, Any], frm: date, to: date, platform: str,
                 codes: list[str], data_end: Optional[date], logo_db: Optional[str], m15_codes: Iterable[str],
                 m15_channels: Iterable[str]) -> P.Kaynaklar:
    k = P.Kaynaklar(data_end=data_end, as_of=A.now())
    org = logo_origin(k, engine, tenant, logo_db)
    daily = k.portal("reklam.gun", "Dönemdeki kampanya-gün satırları", A.daily_stmt(tenant, frm, to, platform), engine)
    aq, cq = A.campaigns_stmts(tenant)
    camps = [k.portal("reklam.hesap", "Reklam hesapları", aq, engine), k.portal("reklam.kampanya", "Kampanyalar ve kitap bağı", cq, engine)]
    met = k.hesap("olcu", F_METRIC, [daily] + camps)
    ins: list[str] = [daily] + camps + [_veri_sonu(k, engine, tenant)]
    overlap = A.clip(frm, to, data_end)
    if overlap:
        ins += [k.portal("reklam.eticaret", "E-ticaret cirosu (Logo önbelleği)", A.ecom_total_stmt(tenant, *overlap), engine, origin=org),
                k.portal("reklam.eticaret.gun", "Gün başına e-ticaret cirosu", A.ecom_by_day_stmt(tenant, *overlap), engine, origin=org)]
        for i, q in enumerate(A.book_sales_stmts(tenant, codes, *overlap), 1):
            ins.append(k.portal(f"reklam.kitap.{i}", "Kitap başına satış (Logo önbelleği)", q, engine, origin=org))
    ins.append(k.portal("reklam.stok", "Kitap stoku ve günlük satış hızı", A.stock_stmt(tenant), engine, origin=org))
    m15 = A.m15_lines_stmt(tenant, m15_channels, list(m15_codes))
    if m15 is not None:
        ins.append(k.portal("reklam.m15", "M15 onaylı planların reklam kanalı satırları", m15, engine))
    ver = k.hesap("verim", F_VERIM, ins)
    sug = k.hesap("oneri", F_SUGG, [k.portal("reklam.oneri", "Açık öneriler", A.suggestions_stmt(tenant, "acik"), engine)])
    k.alanlar({"gosterge": ver, "digerParaBirimi": met, "kanallar": met, "kampanyalar": met, "kitaplar": ver, "bagsiz": met,
               "gunluk": ver, "oneriler": sug})
    return k


def for_status(engine: Any, tenant: str, logo_db: Optional[str]) -> P.Kaynaklar:
    """Satış verisi yenilemesinin durumu: yazılan gün / kitap satırı / stok sayısı, veri sonu."""
    k = P.Kaynaklar()
    org = logo_origin(k, engine, tenant, logo_db)
    k.alanlar({"logo": k.portal("reklam.verisonu", "Logo önbelleği son yenileme raporu", A.meta_stmt(tenant, "logo"), engine,
                                origin=org),
               "refresh": k.portal("reklam.yenileme", "Yenileme işi durumu", A.meta_stmt(tenant, "refresh"), engine)})
    return k


def for_accounts(engine: Any, tenant: str) -> P.Kaynaklar:
    k = P.Kaynaklar()
    aq, lq = A.accounts_stmts(tenant)
    k.alanlar({"items": k.hesap("hesap", "Hesap başına son kampanya günü = yüklenen satırların en son günü.",
                                [k.portal("reklam.hesap", "Reklam hesapları", aq, engine),
                                 k.portal("reklam.hesap.songun", "Hesap başına son gün", lq, engine)])})
    return k


def for_imports(engine: Any, tenant: str) -> P.Kaynaklar:
    k = P.Kaynaklar()
    iq, aq, lq = A.imports_stmts(tenant)
    ref = k.hesap("yukleme", F_IMPORT, [k.portal("reklam.yukleme", "Yüklemeler", iq, engine),
                                        k.portal("reklam.hesap", "Hesaplar", aq, engine),
                                        k.portal("reklam.yukleme.gecerli", "Yükleme başına geçerli satır ve harcama", lq, engine)])
    k.alanlar({"items": ref, "total": ref})
    return k


def for_import(engine: Any, tenant: str, iid: str) -> P.Kaynaklar:
    k = P.Kaynaklar()
    iq, lq, aq = A.import_stmts(tenant, iid)
    ref = k.hesap("yukleme", F_IMPORT, [k.portal("reklam.yukleme", "Yükleme", iq, engine),
                                        k.portal("reklam.yukleme.gecerli", "Geçerli satır ve harcama", lq, engine),
                                        k.portal("reklam.hesap", "Hesap", aq, engine)])
    for f in ("satir", "kampanyaGun", "kampanya", "toplamHarcama", "paraBirimiToplam", "gecerliKampanyaGun", "gecerliHarcama",
              "eslem", "uyarilar"):
        k.alan(f, ref)
    return k


def for_campaigns(engine: Any, tenant: str, frm: date, to: date, platform: str) -> P.Kaynaklar:
    k = P.Kaynaklar()
    aq, cq = A.campaigns_stmts(tenant)
    ins = [k.portal("reklam.gun", "Dönemdeki kampanya-gün satırları", A.daily_stmt(tenant, frm, to, platform), engine),
           k.portal("reklam.hesap", "Hesaplar", aq, engine), k.portal("reklam.kampanya", "Kampanyalar ve kitap bağı", cq, engine)]
    ref = k.hesap("olcu", F_METRIC + " Bağ sayıları = bağ durumu başına kampanya.", ins)
    k.alanlar({"items": ref, "total": ref, "bagSayilari": ins[2]})
    return k


def for_books(q: str) -> P.Kaynaklar:
    k = P.Kaynaklar()
    ref = k.hesap("ara", "Kitap araması CRM kitap kartları üzerinde yapılır (ad, stok kodu, barkod, yazar); toplam = eşleşen, "
                         "gösterilen = ilk 30.", [_crm(k, "reklam.kitaplar", "CRM kitap kartları", S.books_sql(_schema()))])
    k.alanlar({"items": ref, "total": ref})
    return k


def for_budget(engine: Any, tenant: str, year: int, m15_channels: Iterable[str], with_crm: bool) -> P.Kaynaklar:
    k = P.Kaynaklar(as_of=A.now())
    ins = [k.portal("reklam.butce", "Bütçe planı", A.budget_stmt(tenant, year), engine),
           k.portal("reklam.gun", "Yılın kampanya-gün satırları", A.daily_stmt(tenant, date(year, 1, 1), date(year, 12, 31)), engine)]
    m15 = A.m15_lines_stmt(tenant, m15_channels)
    if m15 is not None:
        ins.append(k.portal("reklam.m15", "M15 onaylı planların reklam kanalı satırları", m15, engine))
    if with_crm:
        ins.append(_crm(k, "reklam.crm.butce", "CRM pazarlama bütçe kayıtları",
                        S.budget_records_sql(_schema(), date(year, 1, 1), date(year, 12, 31))))
    ref = k.hesap("butce", F_BUDGET, ins)
    for f in ("hucreler", "m15", "crm", "toplam"):
        k.alan(f, ref)
    return k


def for_crm(frm: date, to: date) -> P.Kaynaklar:
    k = P.Kaynaklar()
    sch = _schema()
    plans = [_crm(k, "reklam.crm.plan", "CRM reklam planları", S.ad_plans_sql(sch)),
             _crm(k, "reklam.crm.plan.kitap", "CRM reklam planı – kitap bağları", S.ad_plan_books_sql(sch))]
    recs = _crm(k, "reklam.crm.butce", "CRM pazarlama bütçe kayıtları (dönem)", S.budget_records_sql(sch, frm, to))
    k.alanlar({"reklamPlanlari": k.hesap("plan", F_CRM, plans), "butceKayitlari": k.hesap("kayit", F_CRM, [recs])})
    return k


def for_suggestions(engine: Any, tenant: str, status: str) -> P.Kaynaklar:
    k = P.Kaynaklar()
    ref = k.hesap("oneri", F_SUGG, [k.portal("reklam.oneri", "Öneriler", A.suggestions_stmt(tenant, status), engine)])
    k.alanlar({"items": ref, "total": ref})
    return k


def for_briefs(engine: Any, tenant: str, stok: str = "", bid: str = "") -> P.Kaynaklar:
    k = P.Kaynaklar()
    q = A.brief_stmt(tenant, bid) if bid else A.briefs_stmt(tenant, stok)
    ref = k.hesap("brief", "Brief taslağı: denetimde düşen cümle = kaynakta olmayan sayı / iddia taşıyan cümle; sayaç = bölüm "
                           "başına karakter.", [k.portal("reklam.brief", "Brief kayıtları", q, engine)])
    for f in (("denetim",) if bid else ("items", "total")):
        k.alan(f, ref)
    return k
