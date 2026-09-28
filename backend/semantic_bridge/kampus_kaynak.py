"""Kampüs (`/`): kartlardaki sayıların sorgu bilgisi (ortak sözleşme `provenance.py`).

Rehber CRM'den (SystemUser) okunur, AD ile kesişir, 5 dakika bellekte tutulur; kişinin kendi alanları portal tablosunda.
Zil, kutlama, oda, eğitim ve ajanda sayaçları portal tablolarından; ajandanın CRM etkinlikleri ayrıca CRM'den okunur.
Uçta koşan portal okumaları `sorgu_izi` ile yakalanır; CRM metni okumanın yapıldığı fonksiyonla aynı değerlerle kurulur.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

from semantic_bridge import provenance as P

AD_DIS = "Etki alanı dizini (Active Directory): etkin hesaplar ve son giriş"

F_REHBER = ("Rehber: kişi = CRM'de etkin, etkileşimli kullanıcı ∩ AD'de etkin hesap (son giriş eşik gün içinde); birim "
            "sayısı = rehberdeki farklı birim adları; kat listesi kişilerin profilindeki kat bilgisinden. Liste 5 dakika "
            "bellekte tutulur.")
F_ZIL = "Onay bekleyen sayısı: onayınızı bekleyen kayıtların sayımı."
F_KUTLAMA = "Kutlamalar: size gelen, görülmemiş kutlama sayısı ve son 30 günün kayıtları; alkış duvarı son kayıtlar."
F_ODA = "Toplantı odaları: şu an boş/dolu = şimdiki saatte rezervasyonu olmayan/olan oda sayısı."
F_EGITIM = "Eğitimlerim: sizi bekleyen anket = doldurulmamış eğitim geri bildirimi sayısı."
F_AJANDA = ("Ajanda: sizin önemli günleriniz, görevleriniz ve CRM etkinlikleri; «+N kayıt daha» = ilk 5'ten sonraki kayıt "
            "sayısı.")


def people_sources(k: P.Kaynaklar, schema: str, crm_db: Optional[str], last: dict[str, Any], rows: int,
                   at: Any) -> list[str]:
    """Rehberin CRM okuması (köprünün son koştuğu metin; bellekteyse ilk okumanın zamanı) + AD."""
    from semantic_bridge import people as PE

    sql = last.get("sql") or PE.directory_sql(schema)
    ids = [k.sorgu("crm.rehber", "CRM kullanıcı rehberi", "crm", sql, database=crm_db, rows=last.get("rows", rows),
                   ms=last.get("ms"), ran_at=last.get("at") or at,
                   description="Liste 5 dakika bellekte tutulur; süre ve zaman ilk okumanındır.")]
    ids.append(k.hesap("ad", "AD'de etkin olmayan ya da uzun süredir giriş yapmayan hesaplar rehbere girmez.", dis=AD_DIS))
    return ids


def agenda_sources(k: P.Kaynaklar, schema: str, frm: date, to: date, crm_db: Optional[str]) -> list[str]:
    from semantic_bridge import events_sources as ES

    return [k.sorgu("crm.ajanda", "CRM etkinlikleri (ajanda aralığı)", "crm", ES.events_sql(schema, frm, to),
                    database=crm_db, description="Başlangıcı ajanda aralığında olan etkin etkinlikler.")]
