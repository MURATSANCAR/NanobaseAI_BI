"""M23 İşbirlikleri: ekrandaki her rakamın sorgu bilgisi (ortak sözleşme `provenance.py`).

Pano, kayıt defteri, aday sırası, işbirliği kartı, ödeme listesi ve rapor portal tablolarından (semantic_influencer_*);
CRM okumaları (kitap kartı, tanıtım gönderimi siparişleri, geçmiş influencer harcaması, sosyal kullanıcı adlı kişiler)
`influencers_sources` üreticileriyle çalışan metin.

KİŞİSEL VERİ: içerik üreticisinin adı, e-postası, ücreti kişisel / gizli veridir; yalnız SQL metni kayda girer.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

from semantic_bridge import influencers as I
from semantic_bridge import influencers_sources as src
from semantic_bridge import pazarlama_kaynak as PK
from semantic_bridge import provenance as P

NOT_RAKAM = ("me", "settings", "no", "items[].no", "columns[].items[].no", "closedRecent[].no", "collabs[].no", "yas",
             "profile.yas", "book.yas", "items[].collabNo")

F_BOARD = ("Pano: açık işbirlikleri aşama sütununda (kapananlar ayrı, son 30 gün); onay bekleyen = onay gerektiren türde "
           "onaylanmamış teklif; bağlantısı geciken = yayın tarihi geçmiş, bağlantısı girilmemiş; yakında yayın = 7 gün içinde; "
           "bu ay = dönem günü bu ayda olan vazgeçilmemiş işbirliği, harcama = onaylı (ya da onay gerektirmeyen) ücret toplamı, "
           "bütçe = ayardaki aylık bütçe; hatırlatmalar = bugünün kuralları (yayın, bağlantı, onay, bütçe eşiği, ödeme günü, "
           "takipçi sıçraması).")
F_PEOPLE = ("Kayıt defteri: kişi başına hesaplar ve son ölçüm (takipçi, gönderi, ortalama beğeni/yorum); takipçi = hesapların "
            "son ölçüm toplamı; işbirliği / açık işbirliği sayısı; ilişki puanı = geçmiş işbirliklerinden kural; sıçrama = "
            "45 gün içinde ayardaki yüzdeyi aşan takipçi artışı; ücret aralığı yalnız yetkiliye.")
F_PERSON = F_PEOPLE + (" Kart toplamları: yayında = yayın aşamasına geçmiş; etkileşim ve harcama vazgeçilmemiş işbirliklerinden; "
                       "etkileşim başı maliyet = harcama ÷ etkileşim. Tanıtım gönderimi = karta yazılmış CRM sipariş numaraları.")
F_CAND = ("Aday sırası: kitap profili (CRM tür, raf, hedef kitle, hedef yaş) ile kişinin konu / yaş grubu / platform eşleşmesi, "
          "geçmiş performans (etkileşim / takipçi), ilişki puanı, ücret–bütçe uyumu kuralla puanlanır; sıraya girmeyenler "
          "gerekçesiyle ayrı.")
F_COLLAB = ("İşbirliği kartı: aşama, tarihler, ücret (yetkiliye), erişim / etkileşim (elle girilen), olaylar, taslaklar (denetimde "
            "düşen cümle sayısı), ödeme satırı.")
F_BOOK = "Kitabın işbirlikleri: yayında = yayın aşamasına geçmiş; etkileşim ve erişim vazgeçilmemiş işbirliklerinin toplamı."
F_PAY = ("Ödeme listesi: açık satırlar (hazır, onaylı) her zaman, ödenenler ödeme günü seçilen ayda; toplamlar durum başına tutar "
         "toplamı.")
F_REPORT = ("Rapor: dönem günü (yayın, yoksa planlanan yayın, yoksa kayıt günü) dönemde olan vazgeçilmemiş işbirlikleri; yayında, "
            "erişim, etkileşim, harcama (ücret toplamı), etkileşim başı maliyet = harcama ÷ etkileşim, açıklaması eksik = yayında "
            "olup reklam açıklaması işaretlenmemiş; kişi ve kitap kırılımı. CRM satırı = pazarlama bütçe modülünde mecra "
            "«Influencer» kayıtları (ayrı; portal toplamına eklenmez).")


def _schema() -> str:
    from semantic_bridge import admin as admin_mod

    return admin_mod.conf("CRM_SCHEMA") or "Timas_MSCRM.dbo"


def _crm(k: P.Kaynaklar, id_: str, title: str, sql: str, desc: str = "") -> str:
    return k.sorgu(id_, title, "crm", sql, database=PK.crm_db(), description=desc)


def _people(k: P.Kaynaklar, engine: Any, tenant: str, ids: Optional[list[str]] = None) -> list[str]:
    pq, aq, sq, cq = I.people_stmts(tenant, ids)
    return [k.portal("isb.kisi", "İçerik üreticileri", pq, engine,
                     description="Ad, e-posta, ücret aralığı kişisel / gizli veri; yalnız sorgu gösterilir."),
            k.portal("isb.hesap", "Hesaplar", aq, engine), k.portal("isb.olcum", "Hesap ölçümleri", sq, engine),
            k.portal("isb.isbirligi", "İşbirlikleri", cq, engine)]


def for_board(engine: Any, tenant: str) -> P.Kaynaklar:
    k = P.Kaynaklar(as_of=I._today())
    b = k.portal("isb.pano", "İşbirlikleri (kişi adıyla)", I.board_stmt(tenant), engine)
    rq, oq, sq, nq = I.reminders_stmts(tenant, I._today())
    rem = [k.portal("isb.hat.acik", "Açık işbirlikleri", rq, engine), k.portal("isb.hat.odeme", "Açık ödeme satırı sayısı", oq, engine),
           k.portal("isb.hat.harcama", "Onaylı harcama satırları", sq, engine),
           k.portal("isb.hat.olcum", "Son 60 gün hesap ölçümleri", nq, engine)]
    ref = k.hesap("pano", F_BOARD, [b] + rem)
    k.alanlar({"columns": ref, "open": ref, "closedRecent": ref, "waitingApproval": ref, "linkLate": ref, "publishSoon": ref,
               "month": ref, "reminders": ref})
    return k


def for_people(engine: Any, tenant: str) -> P.Kaynaklar:
    k = P.Kaynaklar()
    ref = k.hesap("kisi", F_PEOPLE, _people(k, engine, tenant))
    k.alanlar({"items": ref, "total": ref})
    return k


def for_person(engine: Any, tenant: str, pid: str, order_nos: list[str]) -> P.Kaynaklar:
    k = P.Kaynaklar()
    ins = _people(k, engine, tenant, [pid]) + [k.portal("isb.odeme", "Kişinin ödeme satırları",
                                                        I.person_payouts_stmt(tenant, pid), engine)]
    crm = None
    if order_nos:
        try:
            crm = _crm(k, "isb.tanitim", "Tanıtım gönderimi siparişleri (CRM)", src.promo_orders_sql(_schema(), order_nos))
        except Exception:  # noqa: BLE001 — geçersiz numara üreticide elenir
            crm = None
    ref = k.hesap("kart", F_PERSON, ins + ([crm] if crm else []))
    k.alanlar({"accounts": ref, "snapshots": ins[2], "jumps": ref, "relation": ref, "collabs": ref, "totals": ref,
               "crmOrders": crm or ref, "feeMin": ref, "feeMax": ref})
    return k


def for_crm_summary() -> P.Kaynaklar:
    k = P.Kaynaklar()
    ref = _crm(k, "isb.crm.ozet", "Sosyal kullanıcı adı olan CRM kişileri", src.social_summary_sql(_schema()))
    k.alanlar({"kisi": ref, "yazar": ref})
    return k


def for_candidates(engine: Any, tenant: str, kitap: str, book_id: Optional[str]) -> P.Kaynaklar:
    k = P.Kaynaklar()
    book = _crm(k, "isb.kitap", "Kitap kartı ve profili (CRM)", src.book_sql(_schema(), kitap))
    ref = k.hesap("aday", F_CAND, [book] + _people(k, engine, tenant))
    k.alanlar({"items": ref, "excluded": ref, "profile": book, "book": book, "weights": ref, "total": ref})
    if book_id:
        k.alan("collabs", k.portal("isb.kitap.isb", "Kitabın işbirlikleri", I.book_collabs_stmt(tenant, book_id.lower()), engine))
    return k


def for_book_collabs(engine: Any, tenant: str, bid: str) -> P.Kaynaklar:
    k = P.Kaynaklar()
    ref = k.hesap("kitap", F_BOOK, [k.portal("isb.kitap.isb", "Kitabın işbirlikleri",
                                             I.book_collabs_stmt(tenant, str(bid).strip().strip("{}").lower()), engine)])
    k.alanlar({"items": ref, "published": ref, "engagement": ref, "reach": ref})
    return k


def for_collab(engine: Any, tenant: str, cid: str) -> P.Kaynaklar:
    k = P.Kaynaklar()
    cq, eq, dq, pq = I.collab_stmts(tenant, cid)
    ins = [k.portal("isb.kart", "İşbirliği", cq, engine), k.portal("isb.kart.olay", "Olaylar", eq, engine),
           k.portal("isb.kart.taslak", "Taslaklar", dq, engine), k.portal("isb.kart.odeme", "Ödeme satırı", pq, engine)]
    ref = k.hesap("isbirligi", F_COLLAB, ins)
    k.alanlar({"fee": ref, "reach": ref, "engagement": ref, "drafts": ins[2], "payout": ins[3], "events": ins[1],
               "daysToPublish": ref, "cpe": ref})
    return k


def for_payouts(engine: Any, tenant: str, month: str) -> P.Kaynaklar:
    k = P.Kaynaklar()
    m0, m1 = I.payout_month(month)
    ref = k.hesap("odeme", F_PAY, [k.portal("isb.odeme.liste", "Ödeme satırları", I.payouts_stmt(tenant, m0, m1), engine)])
    k.alanlar({"items": ref, "totals": ref})
    return k


def for_report(engine: Any, tenant: str, a: date, b: date, with_crm: bool) -> P.Kaynaklar:
    k = P.Kaynaklar(as_of=I._today())
    ref = k.hesap("rapor", F_REPORT, [k.portal("isb.rapor", "Vazgeçilmemiş işbirlikleri", I.report_stmt(tenant), engine)])
    k.alanlar({"total": ref, "people": ref, "books": ref, "items": ref})
    if with_crm:
        k.alan("crm", _crm(k, "isb.crm.harcama", "Geçmiş influencer harcaması (CRM pazarlama bütçe modülü)",
                           src.crm_spend_sql(_schema(), a, b)))
    return k
