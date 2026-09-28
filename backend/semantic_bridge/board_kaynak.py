"""Kişisel pano: ekrandaki her rakamın sorgu bilgisi (ortak sözleşme `provenance.py`).

Kartın saklı SQL'i mantıksaldır (katalog adları); her koşuda köprü onu fiziksel SQL'e çevirip Logo/CRM'de koşturur.
Sonuç kartla birlikte saklanır (semantic_board_cards.result_json) ve o koşunun fiziksel metni de yanına yazılır
(`board._store_result`). Kartın «i»si o metni gösterir; pano açılınca sorgu yeniden koşmaz.
"""
from __future__ import annotations

from typing import Any, Optional

from semantic_bridge import board as B
from semantic_bridge import provenance as P
from semantic_bridge import soru_kaynak as SK

F_KART = ("Kartın rakamları (KPI değeri, grafik serileri, tablo kolonları, satır sayısı) kartın sorusunun son "
          "koşusundan gelir; aşağıdaki SQL köprünün veritabanında koşturduğu metindir. Sonuç kartla birlikte saklanır, "
          "pano açılınca sorgu yeniden koşmaz; «Yenile», saatlik ya da günlük zamanlayıcı yeniler.")
F_ESKI = (" Bu kartın son sonucu, çalışan SQL'i kaydetmeye başlamadan önce alındı; kart bir kez yenilenince SQL "
          "burada görünür.")
F_BOS = " Kart henüz hiç koşmadı."
F_FARK = (" «Ne değişti»: bu sonuç bir önceki sonuçla satır satır karşılaştırılır (kodla); anlatım yalnız bu farkı "
          "söyler, sayı üretmez.")
F_SAYAC = "Kart sayısı = panonuzdaki kartlar; her kartın rakamları kendi sorgusundan."

#: Kart yerleşimi ve zaman damgası rakam değildir.
NOT_RAKAM = ("cards[].x", "cards[].y", "cards[].w", "cards[].h", "cards[].z", "cards[].result.at",
             "cards[].result.computedAt")


def _card_ref(k: P.Kaynaklar, c: dict[str, Any], base: Optional[str], logo_db: Optional[str],
              crm_db: Optional[str]) -> str:
    res = c.get("result") or {}
    refs, text = [base] if base else [], F_KART
    if res.get("physicalSql"):
        refs.append(SK.calisan(k, f"pano.{c['id']}", f"Kart · {str(c.get('title') or '')[:80]}",
                               physical_sql=res["physicalSql"], logo_db=logo_db, crm_db=crm_db,
                               rows=res.get("totalRows"), ms=res.get("dbMs"), ran_at=res.get("computedAt")))
    else:
        text += F_ESKI if res else F_BOS
    if res.get("fark"):
        text += F_FARK
    if not refs:
        raise P.ProvenanceError("Kartın sorgu kaydı yok.")
    return k.hesap(f"kart:{c['id']}", text, refs)


def for_cards(engine: Any, tenant: str, ds: str, user: str, cards: list[dict[str, Any]], logo_db: Optional[str],
              crm_db: Optional[str]) -> P.Kaynaklar:
    k = P.Kaynaklar()
    base = k.portal("portal.pano", "Pano kartları ve son sonuçları", B.list_stmt(tenant, ds, user), engine,
                    rows=len(cards), description="Kartlarınız, yerleşimleri ve saklı son sonuçları (semantic_board_cards).")
    fields = {"cards": k.hesap("sayac", F_SAYAC, [base])}
    for c in cards:
        fields[f"cards[]:{c['id']}"] = _card_ref(k, c, base, logo_db, crm_db)
    k.alanlar(fields)
    return k


def for_run(card_id: str, out: dict[str, Any], logo_db: Optional[str], crm_db: Optional[str]) -> P.Kaynaklar:
    """Tek kart koşusu (`/board/cards/{id}/run`): dönen sonuç o koşunun fiziksel SQL'inden."""
    k = P.Kaynaklar()
    ref = _card_ref(k, {"id": card_id, "title": "", "result": out}, None, logo_db, crm_db)
    k.alanlar({key: ref for key, v in out.items() if key not in ("at",) and P.numeric_paths({key: v})})
    return k
