"""M24 Katalog ve e-bülten: ekrandaki her rakamın sorgu bilgisi (ortak sözleşme `provenance.py`).

Kitap rakamları (fiyat, stok, stok ay, satış hızı, yıllık adet, özel gün bağı) kitap havuzundan gelir; havuz
`semantic_catalog_meta` içinde saklanan bir görüntüdür ve CRM kitap kartları + Baskı Öneri tanımıyla Logo stok/satış
hızı + T-soft ürün eşitlemesinden kurulur (`catalogs_api.build_pool`, `timas-catalog.timer`). Gösterilen SQL uçta
çalışan portal okumasıdır; havuzu kuran CRM/Logo sorguları (kaydedilmiş çalışmış metinler) ve T-soft eşitleme okuması
`origin`dir. Segment sayacı kişisel veriye dayanır: SQL metni gösterilir, sonuç satırı kayda girmez (yalnız sayı).
Bülten sonuçları elle girilen (ya da CRM kampanyasından okunan) sayılardır.
"""
from __future__ import annotations

from typing import Any, Optional

from semantic_bridge import catalogs as C
from semantic_bridge import catalogs_sources as S
from semantic_bridge import newsletters as N
from semantic_bridge import pazarlama_kaynak as PK
from semantic_bridge import provenance as P

POOL_KEY = "pool"
POOL_SQL_KEY = "pool_sql"

NOT_RAKAM = ("ayarlar", "total", "page", "pageSize", "agirliklar", "kitaplar[].sira", "items[].sira", "segment",
             "kitaplar[].yasBas", "kitaplar[].yasBit", "items[].yasBas", "items[].yasBit", "havuz.kitap", "sayfa")

F_KITAP = ("Kitap rakamları havuzdan: fiyat = ayardaki kaynak (CRM kitap kartı, Logo satış fiyatı ya da T-soft); stok = Logo "
           "depo stoku (Baskı Öneri görünümü); stok ay = stok ÷ aylık satış hızı; satış hızı ve yıllık adet = Baskı Öneri "
           "tanımıyla son 12 ay faturalı net adet. «Dayanak» kolonları kitap kataloğa eklendiğindeki değerdir.")
F_UYARI = ("Uyarılar havuzun bugünkü verisiyle kuralla hesaplanır: fiyat dayanağından farklı, stok kritik (ayardaki ay altı), "
           "satıştan kalkmış, kapak ya da metin eksik; kritik = kritik düzeyli uyarı sayısı.")
F_ADAY = ("Aday puanı = süzgece uyan kitapların ağırlıklı bileşenleri (satış hızı sırası, stok yeterliliği, yenilik, özel gün "
          "bağı; bültende ilgi eşleşmesi) × 100; elenen = satıştan kalkmış ya da stoğu olmayan kitap sayısı; toplam süzgece "
          "uyan bütün kitaplar.")
F_SEGMENT = ("Segment sayısı (yalnız sayı, kişi listesi yok): süzgece uyan etkin kişi; izinli = toplu e-postaya ve e-postaya izin "
             "veren, İYS onayı olan, e-posta adresi dolu (ayara göre KVKK onayı da); dağılım izinsizlerin nedenleri.")
F_SONUC = ("Bülten sonucu elle girilir ya da bağlı CRM kampanyasından okunur: gönderilen, açılan, tıklanan; açılma oranı = "
           "açılan ÷ gönderilen, tıklama oranı = tıklanan ÷ gönderilen; toplam = sonucu olan bültenlerin Σ'ı.")
F_LISTE = "Katalog başına kitap, öne çıkan, kritik ve bilgi uyarısı sayısı katalog kitaplarının kayıtlarından."


def pool_sources(k: P.Kaynaklar, engine: Any, tenant: str, logo_db: Optional[str]) -> list[str]:
    """Havuz görüntüsü okuması ve onu kuran asıl sorgular."""
    runs = (C.meta_get(engine, tenant, POOL_SQL_KEY)[0] or {}).get("items") or []
    org = PK.kayitli(k, runs, "katalog.havuz", logo_db, description="Kitap havuzunu kuran okuma.")
    org.append(k.portal("katalog.tsoft", "T-soft ürün eşitlemesi (fiyat, görsel, bağlantı)", S.tsoft_stmt(tenant), engine,
                        description="SEO modülünün gece T-soft eşitlemesi; T-soft'a yazılmaz."))
    return [k.portal("katalog.havuz", "Kitap havuzu görüntüsü", C.meta_stmt(tenant, POOL_KEY), engine, origin=org,
                     description="Havuz bir kez okunur ve saklanır (semantic_catalog_meta); zamanlayıcı ve «Kaynaktan yenile» tazeler.")]


def for_meta(engine: Any, tenant: str, logo_db: Optional[str]) -> P.Kaynaklar:
    k = P.Kaynaklar()
    pool = pool_sources(k, engine, tenant, logo_db)
    pend = [k.portal("katalog.onayda", "Onay bekleyen kataloglar", C.pending_stmt(tenant), engine),
            k.portal("bulten.onayda", "Onay bekleyen bültenler", N.pending_stmt(tenant), engine)]
    ref = k.hesap("havuz", "Havuz sayıları: kitap, fiyatı kaynaklar arasında farklı kitap, T-soft ürünü; özel gün başına bağlı "
                           "kitap sayısı.", pool)
    k.alanlar({"havuz": ref, "ozelGunler": ref, "hedefler": ref, "ilgiAlanlari": ref, "bekleyen": pend[0],
               "bekleyen.bultenOnayda": pend[1], "sonKosu": ref})
    return k


def for_catalogs(engine: Any, tenant: str, out: dict[str, Any], durum: str) -> P.Kaynaklar:
    k = P.Kaynaklar()
    ls = k.portal("katalog.liste", "Kataloglar", C.catalogs_stmt(tenant, durum), engine)
    cnt = k.portal("katalog.sayac", "Katalog kitapları (sayaç)", C.item_counts_stmt([x["id"] for x in out.get("items") or []]), engine)
    k.alanlar({"items[]": k.hesap("liste", F_LISTE, [ls, cnt])})
    return k


def for_catalog(engine: Any, tenant: str, cid: str, logo_db: Optional[str]) -> P.Kaynaklar:
    k = P.Kaynaklar()
    row = k.portal("katalog.kayit", "Katalog kaydı", C.catalog_stmt(tenant, cid), engine)
    its = k.portal("katalog.kitap", "Katalog kitapları", C.items_stmt(cid), engine)
    pool = pool_sources(k, engine, tenant, logo_db)
    kit = k.hesap("kitap", F_KITAP, [its] + pool)
    k.alanlar({"kitaplar[]": kit, "kitaplar[].uyarilar": k.hesap("uyari", F_UYARI, [its] + pool),
               "kitaplar[].kritik": "hesap:uyari", "ozet": k.hesap("ozet", "Özet = katalog kitaplarının sayıları (öne çıkan, "
                                                                          "kritik uyarı, fiyatsız, kapaksız).", [its, row] + pool),
               "havuz": pool[0]})
    return k


def for_candidates(engine: Any, tenant: str, logo_db: Optional[str]) -> P.Kaynaklar:
    k = P.Kaynaklar()
    pool = pool_sources(k, engine, tenant, logo_db)
    ref = k.hesap("aday", F_ADAY + " " + F_KITAP, pool)
    k.alanlar({"items[]": ref, "total": ref, "elenen": ref, "havuz": pool[0], "ozelGun": ref})
    return k


def for_newsletters(engine: Any, tenant: str, out: dict[str, Any], durum: str) -> P.Kaynaklar:
    k = P.Kaynaklar()
    ids = [x["id"] for x in out.get("items") or []]
    ls = k.portal("bulten.liste", "Bültenler", N.newsletters_stmt(tenant, durum), engine,
                  description="İzinli okur sayısı son segment sayımında yazıldı (sayım sorgusu bülten ekranında).")
    cnt = k.portal("bulten.sayac", "Bülten kitapları (sayaç)", N.item_counts_stmt(ids), engine)
    res = k.portal("bulten.sonuc", "Bülten sonuçları", N.results_stmt(ids), engine)
    k.alanlar({"items[]": k.hesap("liste", "Kitap sayısı bülten kitaplarından; izinli okur son segment sayımından. "
                                           + F_SONUC, [ls, cnt, res]),
               "items[].sonuc": k.hesap("sonuc", F_SONUC, [res])})
    return k


def for_newsletter(engine: Any, tenant: str, nid: str, out: dict[str, Any], schema: str, logo_db: Optional[str]) -> P.Kaynaklar:
    k = P.Kaynaklar()
    row = k.portal("bulten.kayit", "Bülten kaydı (son segment sayımı)", N.newsletter_stmt(tenant, nid), engine)
    seg = N.normalize_segment(out.get("segment"))
    cfg = N.settings()
    try:
        cnt = k.sorgu("bulten.segment", "Segment sayımı (yalnız sayılar)", "crm",
                      N.segment_sql(S.prefix(schema), seg, cfg["requireKvkk"], C.today()), database=PK.crm_db(),
                      description="Kişi kolonu seçilmez; sonuç tek satır sayıdır. Kayıttaki sayı son sayım anınındır.")
    except Exception:  # noqa: BLE001 — şema geçersizse yalnız kayıt
        cnt = None
    its = k.portal("bulten.kitap", "Bülten kitapları", N.nl_items_stmt(nid), engine)
    res = k.portal("bulten.sonuc", "Bülten sonuçları", N.own_results_stmt(nid), engine)
    pool = pool_sources(k, engine, tenant, logo_db)
    k.alanlar({"segmentBuyuklugu": k.hesap("segment", F_SEGMENT, [row] + ([cnt] if cnt else [])),
               "segmentDagilim": "hesap:segment", "kitaplar[]": k.hesap("kitap", F_KITAP, [its] + pool),
               "sonuclar[]": k.hesap("sonuc", F_SONUC, [res]), "dusen": row})
    return k


def for_segment(schema: str, seg: dict[str, Any]) -> P.Kaynaklar:
    k = P.Kaynaklar()
    cfg = N.settings()
    cnt = k.sorgu("bulten.segment", "Segment sayımı (yalnız sayılar)", "crm",
                  N.segment_sql(S.prefix(schema), seg, cfg["requireKvkk"], C.today()), database=PK.crm_db(), rows=1,
                  description="Kişi kolonu seçilmez; sonuç tek satır sayıdır.")
    ref = k.hesap("segment", F_SEGMENT, [cnt])
    k.alanlar({"izinli": ref, "aday": ref, "izinsiz": ref, "dagilim": ref})
    return k


def for_suggest_nl(engine: Any, tenant: str, logo_db: Optional[str]) -> P.Kaynaklar:
    return for_candidates(engine, tenant, logo_db)


def for_report(engine: Any, tenant: str, out: dict[str, Any], schema: str) -> P.Kaynaklar:
    k = P.Kaynaklar()
    rows = k.portal("bulten.rapor", "Gönderilmiş bültenler", N.report_stmt(tenant), engine)
    res = k.portal("bulten.sonuc", "Bülten sonuçları", N.results_stmt([x["id"] for x in out.get("items") or []]), engine)
    fields = {"items[]": k.hesap("sonuc", F_SONUC, [rows, res]), "toplam": "hesap:sonuc"}
    if out.get("crm") is not None:
        p = S.prefix(schema)
        crm = [k.sorgu("bulten.crm.kampanya", "CRM kampanyaları", "crm", S.campaigns_sql(p), database=PK.crm_db(),
                       description="Kampanya kartındaki gönderim, okunan, tıklanan, kara liste sayıları."),
               k.sorgu("bulten.crm.gonderim", "CRM kampanya gönderimleri (kampanya başına sayı)", "crm", S.sends_sql(p),
                       database=PK.crm_db(), description="Kişi kolonu seçilmez; kampanya başına sayılar.")]
        fields["crm[]"] = k.hesap("crm", "CRM kampanya sayıları kampanya kartından ve gönderim kayıtlarının sayımından.", crm)
    k.alanlar(fields)
    return k
