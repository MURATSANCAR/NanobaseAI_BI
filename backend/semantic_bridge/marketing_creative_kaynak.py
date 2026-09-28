"""M19 Görsel ve metin (içerik ve tasarım talepleri): ekrandaki her rakamın sorgu bilgisi (sözleşme `provenance.py`).

Sayaçların hepsi portal tablolarından (semantic_mkt_creative_*): talep, varlık (görsel/metin sürümü), üretim işi.
Gösterilen SQL uçta çalışan ifadedir (`marketing_creative.*_stmt`). Kitap araması CRM'e gider (çalışan metin). Üretimin
kendisi (görsel dizme, metin taslağı) rakam üretmez; «atlandı / kaydedilmedi» sayıları iş kaydının sonucundandır.
"""
from __future__ import annotations

from typing import Any

from semantic_bridge import marketing_creative as S
from semantic_bridge import marketing_creative_sources as SRC
from semantic_bridge import pazarlama_kaynak as PK
from semantic_bridge import provenance as P

NOT_RAKAM = ("page", "pageSize", "items[].surum", "items[].varyant", "items[].genislik", "items[].yukseklik",
             "varliklar[].surum", "varliklar[].varyant", "varliklar[].genislik", "varliklar[].yukseklik")

F_SAYAC = ("Talep sayaçları: güncel varlıklardan görsel / metin sayısı; onaylı = mesaj onayı almış ve reddedilmemiş, "
           "bekleyen = mesaj onayı yok ve reddedilmemiş, reddedilen, taslak lisanslı.")
F_OZET = ("Yeni talep = son 24 saatte açılan talep; tasarım onayı = tasarım onayı bekleyen güncel görsel; mesaj onayı = mesaj "
          "onayı bekleyen metin ya da tasarım onaylı görsel (tasarımı onaylayan kişi hariç); termini yakın = termini 2 gün "
          "içinde, onaylanmamış talep.")
F_LISTE = ("Pano: süzgeçten geçen talepler (sayfa 30); sütun sayısı = o durumdaki talep; biçim ve metin türü sayısı talepte "
           "seçilenler. Toplam sorgunun tamamıdır.")
F_BEKLEYEN = "Onaylı pazarlama planlarında henüz talebe dönüşmemiş görsel ve metin materyalleri (sayı = liste uzunluğu)."
F_IS = "Üretim işi sonucu: atlanan biçim ve kaydedilmeyen varyant sayıları işin kaydından (sınır ya da alıntı denetimi)."


def for_summary(engine: Any, tenant: str, user: str, trace: dict[str, Any]) -> P.Kaynaklar:
    k = P.Kaynaklar()
    q = S.summary_stmts(tenant, user, trace["since"], trace["soon"])
    ids = {n: k.portal(f"icerik.ozet.{n}", t, q[n], engine) for n, t in (
        ("yeni", "Son 24 saatte açılan talepler"), ("termin", "Termini yakın talepler"),
        ("tasarim", "Tasarım onayı bekleyen görseller"), ("mesaj", "Mesaj onayı bekleyen varlıklar"),
        ("bana", "Bana atanan açık talepler"))}
    k.alanlar({"yeniTalep": k.hesap("yeni", F_OZET, [ids["yeni"]]), "tasarimBekleyen": k.hesap("tasarim", F_OZET, [ids["tasarim"]]),
               "mesajBekleyen": k.hesap("mesaj", F_OZET, [ids["mesaj"]]), "bana": ids["bana"],
               "terminiYaklasan": k.hesap("termin", F_OZET, [ids["termin"]])})
    return k


def for_requests(engine: Any, tenant: str, out: dict[str, Any], page: int, **filters: Any) -> P.Kaynaklar:
    k = P.Kaynaklar()
    st = S.requests_stmt(tenant, **filters)
    lst = k.portal("icerik.talep", "Talepler (bu sayfa)", S.requests_page_stmt(st, page), engine,
                   description="Süzgeçli talep listesinin bu sayfası (toplam sayı aynı süzgecin sayımıdır).")
    ids = [r["id"] for r in out.get("items") or []]
    ins = [lst]
    if ids:
        ins.append(k.portal("icerik.varlik.sayac", "Taleplerin güncel varlıkları", S.counts_stmt(tenant, ids), engine))
    k.alanlar({"items[]": k.hesap("liste", F_LISTE, ins), "items[].sayilar": k.hesap("sayac", F_SAYAC, ins),
               "total": "hesap:liste"})
    return k


def for_pending(engine: Any, tenant: str) -> P.Kaynaklar:
    k = P.Kaynaklar()
    ref = k.hesap("bekleyen", F_BEKLEYEN, [k.portal("icerik.bekleyen", "Onaylı planların görsel/metin materyalleri",
                                                    S.pending_stmt(tenant), engine)])
    k.alanlar({"items[]": ref})
    return k


def for_request(engine: Any, tenant: str, rid: str, history: bool) -> P.Kaynaklar:
    k = P.Kaynaklar()
    req = k.portal("icerik.talep", "Talep kaydı", S.request_stmt(tenant, rid), engine)
    ast = k.portal("icerik.varlik", "Talebin varlıkları", S.assets_stmt(tenant, rid, history), engine)
    cnt = k.portal("icerik.varlik.sayac", "Talebin güncel varlıkları (sayaç)", S.counts_stmt(tenant, [rid]), engine)
    job = k.portal("icerik.is", "Üretim işleri", S.jobs_stmt(tenant, rid), engine)
    k.alanlar({"sayilar": k.hesap("sayac", F_SAYAC, [cnt]), "varliklar[]": ast, "isler[]": k.hesap("is", F_IS, [job]),
               "kapak": req})
    return k


def for_archive(engine: Any, tenant: str, page: int, **filters: Any) -> P.Kaynaklar:
    k = P.Kaynaklar()
    st, col = S.archive_stmt(tenant, **filters)
    ref = k.portal("icerik.arsiv", "Varlık arşivi (bu sayfa)",
                   st.order_by(col.desc(), S.ASSETS.c.id).offset(max(0, int(page)) * S.PAGE_SIZE).limit(S.PAGE_SIZE), engine,
                   description="Süzgeçli arşiv (yalnız güncel sürümler); toplam aynı süzgecin sayımıdır.")
    k.alanlar({"items[]": ref, "total": k.hesap("arsiv", "Toplam = süzgece uyan güncel varlık sayısı.", [ref])})
    return k


def for_books(schema: str, q: str, page: int) -> P.Kaynaklar:
    k = P.Kaynaklar()
    ref = k.sorgu("icerik.crm.ara", "CRM kitap araması", "crm", SRC.search_sql(schema, q, page), database=PK.crm_db(),
                  description="Ad, stok kodu ya da ISBN ile arama; toplam = COUNT(*) OVER () (bütün eşleşenler).")
    k.alanlar({"items[]": ref, "total": ref})
    return k
