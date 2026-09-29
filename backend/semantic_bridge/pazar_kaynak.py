"""Pazar ve rakip araştırması: ekrandaki her rakamın sorgu bilgisi (ortak sözleşme `provenance.py`).

Ekran haftalık anlık görüntüden okur (`timas-pazar.timer` → `pazar_api.sync()` → `pazar.apply_snapshot()`): uçta koşan
portal okumaları `sorgu_izi` ile yakalanır; tabloyu dolduran asıl CRM ve Logo sorguları `origin` olarak eklenir. CRM
metni anlık görüntüde saklanan şema ve tanıtım kesimiyle, Logo metni okunan yıl, firma kopyası ve kesim günüyle aynı
fonksiyonlardan (`pazar_sources.*_sql`) yeniden kurulur — tabloyu dolduran metnin aynısıdır. Sektör raporundan gelen
rakamın SQL'i yoktur: rakam tablosunun okuması + yüklenen raporun sayfası.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

from semantic_bridge import pazar as PZ
from semantic_bridge import pazar_sources as src
from semantic_bridge import provenance as P

F_OZET = ("Özet: TİMAŞ net ciro = Logo faturalı satış satırlarının net tutarı (iade eksi), yılbaşından veri sonuna; "
          "büyüme = bu dönem ÷ geçen yılın aynı dönemi − 1. Rakip kayıt, yayınevi ve emsal bağı sayıları CRM rakip "
          "kitap kayıtlarından; eşlenmiş rakip = kategorisi onaylı rakip kayıtları ÷ bütün rakip kayıtları; onaylı "
          "pazar rakamı = yüklenen sektör raporlarından onaylanan rakamlar; yıl başına rakip kayıt CRM oluşturma yılına göre.")
F_IC = ("TİMAŞ iç göstergeleri: seçilen boyutta (kategori, yayınevi ya da kanal) net ciro ve adet, önceki yıl aynı dönem, "
        "büyüme = bu yıl ÷ önceki yıl − 1, adet büyümesi aynı hesap, TİMAŞ içi pay = satırın cirosu ÷ toplam ciro; "
        "toplam satırı sütun toplamı. Kanal = cari kartın özel kodu 2.")
F_MATRIS = ("Rakip matrisi: yayınevi başına fiyatlı kitap sayısı, medyan fiyat, fiyat bandı (1. ve 3. çeyrek), medyan "
            "sayfa, sayfa başı fiyat = fiyat ÷ sayfa (medyan), son N günde eklenen kitap ve cilt dağılımı; TİMAŞ medyan "
            "fiyatı aynı kategorideki TİMAŞ kitaplarından; fiyat konumu = TİMAŞ medyanı ÷ rakip medyanı − 1.")
F_RAKIP = "Yayınevi kitapları: fiyat ve sayfa CRM rakip kitap kaydındaki değerlerdir (anlık görüntü)."
F_EMSAL = ("Emsal: aday kitaplar anlık görüntüden kelime ve kategori benzerliğiyle süzülür, benzemeyenleri model eler "
           "(sayı üretmez); kart başına fiyat ve sayfa CRM kaydından, yılbaşından net adet ve ciro Logo satışından.")
F_ESLEME = ("Kategori eşlemesi: onaylı kapsam = onaylı eşlemelerin kayıt sayısı ÷ bütün rakip kayıtları; durum sayaçları "
            "eşleme tablosundan; satırdaki kayıt sayısı o CRM kategorisindeki rakip kitap sayısı.")
F_RAPOR = ("Sektör raporları: sayfa sayısı ve çıkarım ilerlemesi yüklenen dosyanın işlenişinden; onaylı/bekleyen/atılan "
           "rakam sayıları rakam kayıtlarından. Rakamlar raporun kendisinden okunur (sayfa numarasıyla); SQL'i yoktur.")
F_OZETYAZI = ("Aylık özet: metindeki her sayı özetin dayandığı olgulardan (onaylı pazar rakamları, TİMAŞ iç göstergeleri) "
              "gelir ve yazımdan sonra olgularla denetlenir; model sayı üretmez.")
F_TAZELIK = ("Tazelik: rakip kayıt sayısı, son oluşturma ve değişiklik günü CRM rakip kitap kayıtlarından; «N gün önce» "
             "bugünden farkı; eşik gün ayardır.")

F_RAKIP_BASARI = ("Yayınevi kitapları: fiyat (liste fiyatı), sayfa, kapak ve dağıtımcı stoğu Başarı Dağıtım kataloğunun son "
                  "görüntüsünden; yalnız TİMAŞ grubu dışındaki başlıklar.")
F_ESLEME_BASARI = ("Kategori eşlemesi (Başarı): onaylı kapsam = onaylı eşlemelerin başlık sayısı ÷ Başarı kataloğundaki TİMAŞ "
                   "grubu dışı başlıklar; satırdaki sayı o Başarı kategorisindeki (üst > alt) başlık sayısı, son görüntüden.")
F_TAZELIK_BASARI = ("Tazelik (Başarı): katalog tarihi kaynağın kendi tarihidir; başlık sayısı son görüntüdeki TİMAŞ grubu dışı "
                    "başlıklar; «N gün önce» bugünden farkı; eşik gün ayardır.")


def texts(kaynak: str) -> dict[str, str]:
    """Seçilen rakip kaynağına göre formül metinleri."""
    if kaynak == "basari":
        return {"rakip": F_RAKIP_BASARI, "esleme": F_ESLEME_BASARI, "tazelik": F_TAZELIK_BASARI,
                "matris": F_MATRIS + " Rakip satırları Başarı Dağıtım kataloğundan (liste fiyatı).",
                "emsal": F_EMSAL.replace("CRM kaydından", "rakipte Başarı kataloğundan, TİMAŞ'ta CRM kaydından")}
    return {"rakip": F_RAKIP, "esleme": F_ESLEME, "tazelik": F_TAZELIK, "matris": F_MATRIS, "emsal": F_EMSAL}


def origin_basari(k: P.Kaynaklar, engine: Any, tenant: str) -> list[str]:
    """Başarı kataloğunu dolduran asıl okuma (dağıtımcı turunun sorgusu, kaynağın kendi tarihiyle)."""
    from semantic_bridge import pazar_dagitim as D

    cat = PZ.basari_catalog(engine, tenant)
    if not cat["tarih"]:
        return [k.hesap("basari-bekliyor", "Başarı Dağıtım kataloğu henüz okunmadı; dağıtımcı katalogları her sabah okunur.",
                        dis="Başarı Dağıtım kataloğu")]
    return [k.sorgu("pazar.dagitim.basari", "Başarı Dağıtım kataloğu", "logo", D.SQL_BASARI, rows=cat["satir"],
                    ran_at=cat["okundu"], data_end=cat["tarih"],
                    description="Başarı'nın güncel kataloğu; her gün okunur, yalnız değişen satır saklanır. Rakip olarak "
                                "son görüntüdeki TİMAŞ grubu dışı başlıklar kullanılır.")]


RAPOR_DIS = "Yüklenen sektör raporu (PDF, Excel ya da CSV); rakam raporun ilgili sayfasından"


def origin(k: P.Kaynaklar, engine: Any, tenant: str, logo_db: Optional[str], crm_db: Optional[str], *,
           crm: bool = True, logo: bool = True, basari: bool = False, crm_rakip: Optional[bool] = None) -> list[str]:
    """Anlık görüntüyü dolduran asıl CRM ve Logo sorguları (kayıt kimlikleri). `basari`: rakip kaynağı Başarı
    kataloğudur — CRM rakip kitap ve emsal bağı okumaları yerine Başarı okuması yazılır (TİMAŞ kitapları CRM'den).
    `crm_rakip`: iki kaynak birlikteyse (eşleme listesi «tümü») CRM rakip okuması da yazılır."""
    if crm_rakip is None:
        crm_rakip = not basari
    snap = PZ.meta_get(engine, tenant, "snapshot", {}) or {}
    ids: list[str] = origin_basari(k, engine, tenant) if basari else []
    ok = snap.get("okuma") or {}
    if crm and ok.get("crmSchema"):
        rows = ok.get("crmRows") or {}
        at = snap.get("at")
        for key, title, sql in (
                ("competitors", "CRM rakip kitapları", src.competitors_sql(ok["crmSchema"], int(ok.get("blurbChars") or 0))),
                ("ownBooks", "CRM TİMAŞ kitapları", src.own_books_sql(ok["crmSchema"], int(ok.get("blurbChars") or 0))),
                ("links", "CRM emsal bağları", src.links_sql(ok["crmSchema"])),
                ("kitaplik", "CRM kitaplık listesi", src.kitaplik_sql(ok["crmSchema"]))):
            if not crm_rakip and key in ("competitors", "links"):
                continue
            ids.append(k.sorgu(f"crm.pazar.{key}", title, "crm", sql, database=crm_db, rows=rows.get(key), ran_at=at,
                               description="Haftalık anlık görüntüyü dolduran okuma (tam yenileme)."))
    own = snap.get("ownSales") or {}
    if logo and own.get("dataEnd") and own.get("firms"):
        end = date.fromisoformat(str(own["dataEnd"])[:10])
        for y in own.get("years") or []:
            firm = (own.get("firms") or {}).get(str(y))
            if not firm:
                continue
            cut = src.cut_day(int(y), end)
            ids.append(k.sorgu(f"logo.pazar.stok.{y}", f"Logo satış · stok kodu · {y}", "logo",
                               src.item_sales_sql(firm, int(y), cut), database=logo_db, ran_at=snap.get("ownSalesAt"),
                               period=f"{y} · Logo firma {firm}", data_end=own.get("dataEnd"),
                               description="İç göstergeler ve emsal satışı bu okumadan (anlık görüntü)."))
            ids.append(k.sorgu(f"logo.pazar.kanal.{y}", f"Logo satış · kanal · {y}", "logo",
                               src.channel_sales_sql(firm, int(y), cut), database=logo_db, ran_at=snap.get("ownSalesAt"),
                               period=f"{y} · Logo firma {firm}", data_end=own.get("dataEnd")))
    if not ids:
        ids.append(k.hesap("okuma-bekliyor", "Anlık görüntünün asıl okuması bu sürümden önce yapıldı; CRM ve Logo "
                                             "sorguları bir sonraki haftalık yenilemede (ya da «Şimdi yenile») yazılır.",
                           dis="Haftalık pazar anlık görüntüsü"))
    return ids
