"""Veri sözlüğü, Onaylar, Eş anlamlılar: ekrandaki sayıların sorgu bilgisi (ortak sözleşme `provenance.py`).

Terim, aday ve eş anlamlı sayıları katalog deposundan (sl_concept, sl_mapping, sl_evidence, sl_vocabulary,
sl_schema_annotation) okunur; uç çalışırken koşan okumalar `sorgu_izi` ile yakalanır (gösterilen = çalışan). Tablo satır
sayıları ve değer dağılımları tablo profillerinden gelir: profiller köprü açılışında ve katalog yenilenince belleğe
alınır, değerleri gece katalog taramasının Logo/CRM ölçümüdür.
"""
from __future__ import annotations

from typing import Any, Iterable

from semantic_bridge import admin_kaynak as ADK
from semantic_bridge import provenance as P
from semantic_bridge import sorgu_izi as IZ

TARAMA = "Gece katalog taraması (Logo ve CRM tablo profilleri; satır sayısı ve değer dağılımı ölçümü)"

F_TERIM = "Terim sayısı = listelenen kavramlar (durum süzgeciyle); süzgeç sonrası sayı ekranda arama ile daralır."
F_TABLO = ("Tablo sayısı ve satır sayısı tablo profillerinden (yıl ve firma kopyaları tek kalıp altında toplanır); "
           "eksik alan = açıklaması ne kaynakta ne de yazılı açıklamada olan kolon; öneri = bekleyen açıklama önerisi.")
F_ADAY = ("Aday sayısı = onay bekleyen kavramlar; destek sayıları kavramın kanıt kayıtlarından; değer başına satır "
          "profilde ölçülen değer dağılımından.")
F_ES = "Öneri, onaylı ve alan sayıları eş anlamlı kayıtlarından (durum başına sayım ve alan başına gruplama)."
F_BOSLUK = "Alan sayısı = açıklaması olmayan kolonlar (tablo profilleri + yazılı açıklamalar)."


def for_catalog(engine: Any, ds: str, ran: list, out: dict[str, Any], *, title: str, text: str,
                profiles: bool = False, skip: Iterable[str] = ()) -> P.Kaynaklar:
    k = P.Kaynaklar()
    ids = IZ.kaydet(k, ran, engine, "portal.katalog.okuma", title,
                    description="Bu ekran açılırken katalog deposunda koşan okuma.")
    if profiles:
        ids.append(ADK._profiles_source(k, engine, ds))
        ids.append(k.hesap("tarama", "Satır sayıları ve değer dağılımları taramanın ölçümüdür.", dis=TARAMA))
    if not ids:
        raise P.ProvenanceError("Bu ekranın okuması yakalanamadı.")
    ref = k.hesap("katalog", text, ids)
    skipped = set(skip)
    k.alanlar({key: ref for key, v in out.items() if key not in skipped and P.numeric_paths({key: v})})
    return k
