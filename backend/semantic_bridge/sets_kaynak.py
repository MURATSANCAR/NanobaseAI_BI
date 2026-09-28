"""M53 Set, hediye ve promosyon: ekrandaki her rakamın sorgu bilgisi (ortak sözleşme `provenance.py`).

Ekrandaki rakamlar köprünün set tablolarından (semantic_mkt_set_*) okunur; tabloları yenileme işi (`sets.Refresher`,
`timas-marketing-sets.timer`) CRM ve Logo'dan doldurur. Gösterilen SQL uçta çalışan portal okumasıdır (`sets.*_stmt`,
kod listeleri 500'lük parçalarla — her parça ayrı ifade); yenileme işinin çalıştırdığı CRM/Logo metinleri (kaydedilmiş,
değerleri yerinde) `origin`dir. Maliyet M9 birim maliyetinden ya da ayara göre Logo son maliyetli satırdan.
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

from semantic_bridge import pazarlama_kaynak as PK
from semantic_bridge import provenance as P
from semantic_bridge import sets as S
from semantic_bridge import sets_sources as SRC

NOT_RAKAM = ("page", "pageSize", "settings", "giftTiers", "kademeler", "items[].secenekler[].no", "secenekler[].no",
             "items[].kademeler", "status.startedAt", "status.finishedAt", "finishedAt", "startedAt", "last.sn",
             "items[].bilesenler[].kaynak")

F_SET = ("Set satırı: bileşen sayısı ve liste toplamı = Σ bileşen liste fiyatı × adet (KDV dahil; liste fiyatı ayardaki "
         "kaynaktan: CRM ya da Logo satış fiyat listesi); indirim = 1 − set fiyatı ÷ liste toplamı; net gelir = set fiyatının "
         "bileşenlere liste payıyla dağıtılıp her birinin KDV'si düşülmüş toplamı; marj = net gelir − Σ birim maliyet × adet − "
         "ambalaj; marj oranı = marj ÷ net gelir. Stok = Logo stok bakiyesi (giriş − çıkış); son 12 ay = setin kendi stok "
         "koduyla faturalı net adet ve net ciro (bileşenin tek satışıyla toplanmaz).")
F_OZET = ("Sayılar bütün setlerden: set = hepsi; satışta; son 12 ayda satışsız = satıştaki setlerden net satışı olmayan; marj "
          "bilinmiyor = kapanmamış ve marjı hesaplanamayan (bileşende maliyet yok); onay / kart bekleyen; taslak ve öneri.")
F_ONERI = ("Öneri (kurala göre): birlikte alım çiftleri, aynı yazar / dizi, yaş bandı ve tema kümelerinden; önerilen fiyat = "
           "liste toplamı × (1 − mevcut CRM setlerinin medyan indirimi); medyan yeterli örnek yoksa uygulanmaz. Bileşen "
           "stok ve 12 ay satışı kitap tablosundan.")
F_INDIRIM = "Medyan indirim = CRM'deki fiyatı tam setlerde (1 − set fiyatı ÷ liste toplamı) değerlerinin medyanı; n = set sayısı."
F_CIFT = ("Birlikte alım çifti = aynı B2C siparişinde birlikte geçen iki kitap; sipariş = ortak sipariş sayısı; birliktelik "
          "oranı (lift) = ortak sipariş ÷ (A siparişi × B siparişi ÷ toplam B2C sipariş).")
F_TEKLIF = ("Hediye teklifi: seçenekler teklif kurulurken hesaplanır — kişi başı bütçeye sığan ve stoğu kişi sayısına yeten "
            "setler, kitap paketleri ve tek kitaplar; birim net = birim liste × (1 − adet kademesi indirimi); toplam net = "
            "birim net × kişi; bütçe farkı = bütçe − birim net; marj yukarıdaki kuralla.")
F_PROMO = ("Promosyon ürünleri: 157 önekli Logo kartları ve CRM promosyon / pazarlama materyali kartları; stok = Logo stok "
           "bakiyesi; son 12 ay adet ve ciro = faturalı satış; stoğu yok = bakiye ≤ 0; 157 cirosu = ticari ürünlerin toplamı.")
F_SERI = "Aylık seriler: setin ve bileşenlerinin ay ay faturalı net adet ve ciro; seriler ayrı okunur, toplanmaz."
F_YENILEME = ("Yenileme işi sayıları (okunan CRM seti, kitap, Logo reçete, satış satırı, promosyon, birlikte alım çifti ve "
              "B2C sipariş sayısı) son okumanın kaydıdır.")


def origins(k: P.Kaynaklar, engine: Any, logo_db: Optional[str]) -> list[str]:
    runs = (S.meta_get(engine, "sql").get("items") or []) + (S.meta_get(engine, "basket").get("sql") or [])
    return PK.kayitli(k, runs, "set.kaynak", logo_db, description="Set tablolarını dolduran yenileme işinin okuması.")


def _new(engine: Any) -> P.Kaynaklar:
    end = S.data_end(engine)
    return P.Kaynaklar(data_end=end)


def _chunked(k: P.Kaynaklar, engine: Any, id_: str, title: str, fn: Any, keys: Iterable[str], origin: list[str],
             *extra: Any) -> list[str]:
    ids = []
    parts = S.chunks(keys)
    for n, part in enumerate(parts, 1):
        ids.append(k.portal(f"{id_}.{n}" if len(parts) > 1 else id_, title + (f" · parça {n}" if len(parts) > 1 else ""),
                            fn(part, *extra), engine, origin=origin))
    return ids


def _set_sources(k: P.Kaynaklar, engine: Any, rows_stmt: Any, set_ids: list[str], codes: list[str], comp_codes: list[str],
                 logo_db: Optional[str]) -> list[str]:
    org = origins(k, engine, logo_db)
    ids = [k.portal("set.setler", "Setler", rows_stmt, engine, origin=org,
                    description="Set kayıtları: fiyat, liste toplamı, net gelir, maliyet, marj (semantic_mkt_sets).")]
    ids += _chunked(k, engine, "set.bilesen", "Set bileşenleri", S.items_stmt, set_ids, org)
    a, b = S.window12(S.data_end(engine))
    ids += _chunked(k, engine, "set.satis12", f"Son 12 ay satış ({a} – {b})", S.sales12_stmt, codes, org, a, b)
    ids += _chunked(k, engine, "set.kitap", "Kitap ve stok kartları", S.books_stmt, list(codes) + list(comp_codes), org)
    return ids


def for_list(engine: Any, tenant: str, out: dict[str, Any], logo_db: Optional[str]) -> P.Kaynaklar:
    k = _new(engine)
    with engine.connect() as c:
        rows = c.execute(S.sets_stmt(tenant)).all()
    ids = _set_sources(k, engine, S.sets_stmt(tenant), [r.id for r in rows], [r.stok_kodu for r in rows if r.stok_kodu], [],
                       logo_db)
    ref = k.hesap("set", F_SET, ids)
    k.alanlar({"items[]": ref, "summary": k.hesap("ozet", F_OZET, ids), "total": "hesap:ozet"})
    return k


def for_set(engine: Any, tenant: str, set_id: str, out: dict[str, Any], logo_db: Optional[str]) -> P.Kaynaklar:
    """Set kartı, düzenleyici önizlemesi (fiyat hesabı) ve açılacak kart listesi: cevabın her alanı set hesabına bağlı."""
    k = _new(engine)
    sid = set_id
    comp = [i.get("stok") for i in out.get("bilesenler") or [] if i.get("stok")]
    codes = [out["stokKodu"]] if out.get("stokKodu") else []
    ids = _set_sources(k, engine, S.set_stmt(tenant, sid), [sid], codes, comp, logo_db)
    ref = k.hesap("set", F_SET, ids)
    for key in out:
        if key not in ("kaynaklar",):
            k.alan(key, ref)
    return k


def for_effect(engine: Any, tenant: str, out: dict[str, Any], set_codes: list[str], logo_db: Optional[str]) -> P.Kaynaklar:
    k = _new(engine)
    ref = k.hesap("seri", F_SERI, [k.portal("set.seri", "Aylık satış serileri", S.series_stmt(set_codes), engine,
                                            origin=origins(k, engine, logo_db))])
    k.alanlar({"seriler": ref})
    return k


def for_suggestions(engine: Any, out: dict[str, Any], logo_db: Optional[str]) -> P.Kaynaklar:
    k = _new(engine)
    org = origins(k, engine, logo_db)
    sg = k.portal("set.oneri", "Set önerileri", S.sugg_stmt(), engine, origin=org)
    codes = sorted({b["stok"] for s in out.get("items") or [] for b in s.get("bilesenler") or [] if b.get("stok")})
    books = _chunked(k, engine, "set.kitap", "Bileşen kitapları", S.books_stmt, codes, org)
    disc = k.portal("set.indirim", "CRM setlerinin fiyatı ve liste toplamı", S.discount_stmt(), engine, origin=org)
    k.alanlar({"items[]": k.hesap("oneri", F_ONERI, [sg, disc] + books), "total": sg,
               "indirim": k.hesap("indirim", F_INDIRIM, [disc]), "meta": sg})
    return k


def for_meta(engine: Any, logo_db: Optional[str]) -> P.Kaynaklar:
    k = _new(engine)
    org = origins(k, engine, logo_db)
    disc = k.portal("set.indirim", "CRM setlerinin fiyatı ve liste toplamı", S.discount_stmt(), engine, origin=org)
    pack = [x for x in org if "paketleme" in (k.sources[x]["sql"].lower())] or org
    days = [x for x in org if "ozelgun" in (k.sources[x]["sql"].lower())] or org
    k.alanlar({"discount": k.hesap("indirim", F_INDIRIM, [disc]),
               "packaging": k.hesap("ambalaj", "Ambalaj birim maliyeti CRM «Paketleme» kaydından.", pack or [disc]),
               "seasons": k.hesap("sezon", "Sezon: CRM özel gününün sıradaki tarihi; kalan gün = tarih − bugün.", days or [disc]),
               "alerts": k.hesap("uyari", "Uyarılar yenileme sonunda kuralla yazılır (stok, sezon, marj eşiği).", [disc]),
               "status": k.hesap("yenileme", F_YENILEME + " " + F_CIFT, org or [disc])})
    return k


def for_status(engine: Any, logo_db: Optional[str]) -> P.Kaynaklar:
    k = _new(engine)
    org = origins(k, engine, logo_db) or [k.portal("set.kitap.tum", "Kitap ve stok kartları", S.all_books_stmt(), engine)]
    ref = k.hesap("yenileme", F_YENILEME, org)
    bs = PK.kayitli(k, S.meta_get(engine, "basket").get("sql") or [], "set.sepet", logo_db)
    k.alanlar({"last": ref, "basket": k.hesap("sepet", F_CIFT, bs or org)})
    return k


def for_books(engine: Any, logo_db: Optional[str]) -> P.Kaynaklar:
    k = _new(engine)
    ref = k.portal("set.kitap.tum", "Kitap ve stok kartları", S.all_books_stmt(), engine, origin=origins(k, engine, logo_db),
                   description="Arama bu tablonun tamamında yapılır (ad, stok kodu, yazar); 12 ay satışa göre sıralı.")
    k.alanlar({"items[]": ref, "total": ref})
    return k


def for_pairs(engine: Any, out: dict[str, Any], logo_db: Optional[str]) -> P.Kaynaklar:
    k = _new(engine)
    bs = PK.kayitli(k, S.meta_get(engine, "basket").get("sql") or [], "set.sepet", logo_db,
                    description="B2C sipariş satırlarından birlikte alım (taslak, iptal, bedelsiz satırlar hariç).")
    pr = k.portal("set.cift", "Birlikte alım çiftleri", S.pairs_stmt(), engine, origin=bs)
    ref = k.hesap("cift", F_CIFT, [pr])
    k.alanlar({"items[]": ref, "total": ref, "meta": ref})
    return k


def for_offers(engine: Any, tenant: str) -> P.Kaynaklar:
    k = P.Kaynaklar()
    of = k.portal("set.teklif", "Hediye teklifleri", S.offers_stmt(tenant), engine)
    ref = k.hesap("teklif", F_TEKLIF, [of])
    k.alanlar({"items[]": ref, "total": of, "summary": of})
    return k


def for_offer(engine: Any, tenant: str, out: dict[str, Any], logo_db: Optional[str]) -> P.Kaynaklar:
    k = _new(engine)
    org = origins(k, engine, logo_db)
    of = k.portal("set.teklif", "Hediye teklifi", S.offer_stmt(tenant, out["id"]), engine,
                  description="Seçenekler teklif kurulurken yazıldı (semantic_mkt_gift_offers).")
    qty = int(out.get("adet") or 1)
    gb = k.portal("set.teklif.kitap", "Seçenek adayı kitaplar (stoğu kişi sayısına yeten)", S.gift_books_stmt(qty), engine,
                  origin=org)
    gs = k.portal("set.teklif.set", "Seçenek adayı satıştaki setler", S.gift_sets_stmt(tenant), engine, origin=org)
    ref = k.hesap("teklif", F_TEKLIF, [of, gb, gs])
    for key in out:
        if key != "kaynaklar":
            k.alan(key, ref)
    return k


def for_accounts(schema: str, q: str, page: int) -> P.Kaynaklar:
    k = P.Kaynaklar()
    ref = k.sorgu("set.crm.firma", "CRM firma araması", "crm", SRC.crm_account_search_sql(schema, q, page * 50, 50),
                  database=PK.crm_db(), description="Firma adı ya da cari kodu; toplam = COUNT(*) OVER () (bütün eşleşenler).")
    k.alanlar({"items[]": ref, "total": ref})
    return k


def for_history(schema: str, account_id: str) -> P.Kaynaklar:
    k = P.Kaynaklar()
    ref = k.sorgu("set.crm.hediye", "Firmaya geçmiş hediye talepleri", "crm", SRC.crm_gift_history_sql(schema, account_id),
                  database=PK.crm_db(), description="Yalnız talep no, tutar, tarih, durum (kişi bilgisi seçilmez).")
    k.alanlar({"items[]": ref})
    return k


def for_promo(engine: Any, logo_db: Optional[str]) -> P.Kaynaklar:
    k = _new(engine)
    pr = k.portal("set.promo", "Promosyon ürünleri", S.promo_stmt(), engine, origin=origins(k, engine, logo_db))
    ref = k.hesap("promo", F_PROMO, [pr])
    k.alanlar({"items[]": ref, "summary": ref, "total": ref})
    return k
