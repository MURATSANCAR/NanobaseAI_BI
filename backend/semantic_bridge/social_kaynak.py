"""M22 Sosyal medya: ekrandaki her rakamın sorgu bilgisi (ortak sözleşme `provenance.py`).

Gönderi, hesap, ölçü ve içe aktarma sayıları portal tablolarından (semantic_social_*); CRM okumaları (kitap arama ve
kartı, marka kartları, özel günler ve kitap bağları, yeni kitaplar, hak açıklaması) `social_sources` üreticileriyle çalışan
metin; çok satan backlist bütçe modülünün Logo satış önbelleğinden (asıl Logo sorgusu origin).
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Optional

from semantic_bridge import pazarlama_kaynak as PK
from semantic_bridge import provenance as P
from semantic_bridge import social as S
from semantic_bridge import social_sources as src

NOT_RAKAM = ("page", "pageSize", "gun", "settings", "backlist.page", "backlist.pageSize", "yil")

F_CAL = ("Takvim: aralıktaki gönderiler (paylaşım zamanı aralıkta); durum sayıları = durum başına gönderi; tarihsiz = "
         "paylaşım zamanı boş fikir/taslak/onayda/onaylı gönderi; onay bekleyen = bütün tarihlerde «onayda» olan.")
F_OPP = ("Fırsatlar: özel günler CRM'den (hareketli günler kodda tanımlı), kalan gün = başlangıç − bugün, kitap sayısı = güne "
         "bağlı CRM kitabı, takvimde = pencerede gönderisi olan; yeni kitaplar = CRM ilk yayın tarihi ay başı ile pencere sonu "
         "arasında; çok satan backlist = son 12 tam ay (veri sonunun ayı dahil) net adet, ilk yayını eski ve uzun süredir "
         "gönderisi olmayan kitaplar adede göre; basın = son N günde olumlu/nötr etiketli haber.")
F_REPORT = ("Ay raporu: ölçüler gün sütununa göre ayda; etkileşim = beğeni + yorum + paylaşım + kaydetme; oran = etkileşim ÷ "
            "erişim; gönderi başına = etkileşim ÷ ölçüsü olan gönderi; takipçi = hesabın aydaki son ölçüsü; gönderi sayıları "
            "paylaşım zamanına göre; onay süresi = gönderme ile onay arasındaki saatlerin medyanı.")
F_POST = ("Gönderi: karakter ve etiket sayısı metinden, sınır platform ayarından; içgörü = gün başına ölçü satırı (dosya ya da "
          "elle); Zeki AI seçeneklerinde düşen cümle = kaynakta olmayan alıntı / rakam / kanıtsız iddia taşıyan cümle; tür "
          "olasılığı = Zeki AI tür sınıflaması.")
F_IMPORT = "İçe aktarma: dosyadaki satır, gönderi bağlantısıyla eşleşen satır ve ölçü toplamları (dosya özeti)."


def _schema() -> str:
    from semantic_bridge import admin as admin_mod

    return admin_mod.conf("CRM_SCHEMA") or "Timas_MSCRM.dbo"


def _crm(k: P.Kaynaklar, id_: str, title: str, sql: str) -> str:
    return k.sorgu(id_, title, "crm", sql, database=PK.crm_db())


def _crm_saved(k: P.Kaynaklar, engine: Any, tenant: str, key: str, at: Any, id_: str, title: str,
               sqls: list[tuple[str, str, str]]) -> str:
    """Portal tablosunda saklanan CRM okuması: ekranın çalıştırdığı okuma (semantic_social_meta) + onu dolduran CRM
    sorguları (köken, okuma anıyla)."""
    origin = [k.sorgu(sid, stitle, "crm", sql, database=PK.crm_db(), ran_at=at) for sid, stitle, sql in sqls]
    return k.portal(id_, f"{title} (saklanan CRM okuması)", S.meta_stmt(tenant, key), engine, origin=origin,
                    description="CRM okuması portal tablosunda saklanır; ekran bunu okur. Bir saatten eskiyse ya da «Verileri "
                                "yenile» basılınca arkada yeniden okunur, her sabah 07:00 turunda yenilenir.")


def _posts(k: P.Kaynaklar, engine: Any, tenant: str, id_: str, title: str, **kw: Any) -> str:
    return k.portal(id_, title, S.posts_stmt(tenant, **kw), engine)


def for_accounts(engine: Any, tenant: str) -> P.Kaynaklar:
    k = P.Kaynaklar()
    k.alanlar({"total": k.portal("sosyal.hesap", "Tanımlı hesaplar", S.accounts_stmt(tenant), engine)})
    return k


def for_brands(engine: Any, tenant: str, saved: Optional[dict[str, Any]] = None) -> P.Kaynaklar:
    k = P.Kaynaklar()
    if saved is not None and "crm.marka" in saved:
        b = _crm_saved(k, engine, tenant, "crm.marka", saved["crm.marka"], "sosyal.marka.kayit", "CRM marka kartları",
                       [("sosyal.marka", "CRM marka kartları", src.brands_sql(_schema()))])
    else:
        b = _crm(k, "sosyal.marka", "CRM marka kartları", src.brands_sql(_schema()))
    a = k.portal("sosyal.hesap", "Tanımlı hesaplar (eklenmiş işareti)", S.accounts_stmt(tenant), engine)
    ref = k.hesap("marka", "Marka sayısı = CRM marka kartı; Instagram dolu = kullanıcı adı yazılı kart; ekli = tanımlı hesaplarda "
                           "aynı kullanıcı adı olan.", [b, a])
    k.alanlar({"items": ref, "instagramDolu": ref, "marka": ref})
    return k


def for_search(q: str, page: int) -> P.Kaynaklar:
    k = P.Kaynaklar()
    ref = _crm(k, "sosyal.ara", "Kitap araması (CRM; toplam aynı sorgunun pencere sayımı)", src.search_sql(_schema(), q, page))
    k.alanlar({"items": ref, "total": ref})
    return k


def for_content(engine: Any, tenant: str, stok: str, kitap_id: Optional[str]) -> P.Kaynaklar:
    k = P.Kaynaklar()
    sch = _schema()
    ids = [_crm(k, "sosyal.kitap", "Kitap kartı ve metinleri (CRM)", src.book_sql(sch, stok))]
    if kitap_id:
        ids.append(_crm(k, "sosyal.hak", "Telif hak açıklaması (CRM)", src.rights_sql(sch, kitap_id)))
    posts = _posts(k, engine, tenant, "sosyal.gonderi", "Kitabın gönderileri", stok=stok)
    k.alanlar({"kitap": ids[0], "haklar": ids[-1], "gonderiler": posts,
               "gorseller": k.hesap("gorsel", "Görseller kitap tasarım stüdyosunun sosyal görselleri ve içerik arşivinin onaylı "
                                              "varlıklarıdır (dosya listesi; SQL yok).", [ids[0]])})
    return k


def for_calendar(engine: Any, tenant: str, start: date, end: date, account: str) -> P.Kaynaklar:
    k = P.Kaynaklar()
    ins = [_posts(k, engine, tenant, "sosyal.takvim", "Aralıktaki gönderiler", frm=start, to=end, account=account),
           _posts(k, engine, tenant, "sosyal.tarihsiz", "Tarihsiz fikir ve taslaklar", unscheduled=True, account=account,
                  status="fikir,taslak,onayda,onayli"),
           _posts(k, engine, tenant, "sosyal.onayda", "Onay bekleyen gönderiler", status="onayda")]
    ref = k.hesap("takvim", F_CAL, ins)
    k.alanlar({"items": ins[0], "counts": ref, "total": ref, "unscheduled": ins[1], "onayBekleyen": ins[2]})
    return k


def for_opportunities(engine: Any, tenant: str, ref_day: date, days: int, logo_db: Optional[str],
                      saved: Optional[dict[str, Any]] = None) -> P.Kaynaklar:
    """`saved`: uçta okunan saklanan CRM kayıtları (anahtar → okuma anı); verilmişse gösterilen okuma o kayıttır."""
    from semantic_bridge import budget as B

    k = P.Kaynaklar(as_of=S.now())
    sch = _schema()
    saved = saved or {}
    days_sqls = [("sosyal.ozelgun", "Özel günler (CRM)", src.days_sql(sch)),
                 ("sosyal.ozelgun.kitap", "Özel gün – kitap bağları (CRM)", src.links_sql(sch))]
    if "crm.ozelgun" in saved:
        crm = [_crm_saved(k, engine, tenant, "crm.ozelgun", saved["crm.ozelgun"], "sosyal.ozelgun.kayit",
                          "Özel günler ve kitap bağları", days_sqls)]
    else:
        crm = [_crm(k, sid, title, sql) for sid, title, sql in days_sqls]
    posts = _posts(k, engine, tenant, "sosyal.gonderi", "Takvimdeki gönderiler", status="fikir,taslak,onayda,onayli,yayinlandi")
    start = ref_day.replace(day=1)
    end = max(ref_day + timedelta(days=days), (start + timedelta(days=32)).replace(day=1) - timedelta(days=1))
    if "crm.yeni" in saved:
        key, at = saved["crm.yeni"]
        nb = _crm_saved(k, engine, tenant, key, at, "sosyal.yeni.kayit", "Yeni kitaplar",
                        [("sosyal.yeni", "Yeni kitaplar (CRM)", src.new_books_sql(sch, start, end))])
    else:
        nb = _crm(k, "sosyal.yeni", "Yeni kitaplar (CRM)", src.new_books_sql(sch, start, end))
    back: list[str] = []
    try:
        de = B.data_end(engine)
    except Exception:  # noqa: BLE001 — bütçe modülü kurulu değil
        de = None
    if de:
        lo, hi = S.month_window(de)
        sq, iq = src.backlist_stmts(lo, hi)
        back = [PK.butce_satis(k, engine, "sosyal.backlist", "Son 12 ay kitap başına net adet", sq,
                               range(lo // 12, hi // 12 + 1), logo_db),
                k.portal("sosyal.kunye", "Kitap künyesi (ilk yayın, durum)", iq, engine)]
        v = PK.veri_sonu(k, engine, logo_db)
        back += [v] if v else []
    press: list[str] = []
    try:
        press = [k.portal("sosyal.basin", "Basında çıkan haberler", src.press_stmt(tenant, ref_day - timedelta(days=days)), engine)]
    except Exception:  # noqa: BLE001 — web taraması tablosu yok
        press = []
    ref = k.hesap("firsat", F_OPP, crm + [posts, nb] + back + press)
    k.alanlar({"ozelGunler": ref, "yeniKitaplar": ref, "backlist": ref, "basin": ref})
    return k


def for_posts(engine: Any, tenant: str, **kw: Any) -> P.Kaynaklar:
    k = P.Kaynaklar()
    ref = _posts(k, engine, tenant, "sosyal.gonderi", "Gönderiler", **kw)
    k.alanlar({"items": ref, "total": ref})
    return k


def for_post(engine: Any, tenant: str, pid: str, account_id: Optional[str]) -> P.Kaynaklar:
    k = P.Kaynaklar()
    ins = [k.portal("sosyal.gonderi", "Gönderi", S.post_stmt(tenant, pid), engine)]
    if account_id:
        ins.append(k.portal("sosyal.hesap", "Gönderinin hesabı", S.account_stmt(account_id), engine))
    met = k.portal("sosyal.olcu", "Gönderinin gün başına ölçüleri", S.metrics_stmt(tenant, pid), engine)
    ref = k.hesap("gonderi", F_POST, ins + [met])
    k.alanlar({"olcumler": met, "draft": ref, "kindProb": ref, "uyarilar": ref, "assets": ref})
    return k


def for_events(engine: Any, pid: str) -> P.Kaynaklar:
    k = P.Kaynaklar()
    k.alan("items", k.portal("sosyal.olay", "Gönderi geçmişi", S.events_stmt(pid), engine))
    return k


def for_jobs(engine: Any, tenant: str, pid: str) -> P.Kaynaklar:
    k = P.Kaynaklar()
    k.alan("items", k.portal("sosyal.is", "Gönderinin Zeki AI işleri", S.jobs_stmt(tenant, post_id=pid), engine))
    return k


def for_imports(engine: Any, tenant: str) -> P.Kaynaklar:
    k = P.Kaynaklar()
    ref = k.hesap("aktarma", F_IMPORT, [k.portal("sosyal.aktarma", "İçe aktarmalar", S.imports_stmt(tenant), engine)])
    k.alanlar({"items": ref, "total": ref})
    return k


def for_report(engine: Any, tenant: str, month: str) -> P.Kaynaklar:
    k = P.Kaynaklar(as_of=S.now())
    aq, mq, pq, kq = S.report_stmts(tenant, month)
    ins = [k.portal("sosyal.rapor.hesap", "Hesaplar", aq, engine),
           k.portal("sosyal.rapor.olcu", "Aydaki ölçü satırları", mq, engine),
           k.portal("sosyal.rapor.gonderi", "Aya planlanan gönderiler", pq, engine),
           k.portal("sosyal.rapor.tur", "Ölçüsü olan gönderilerin türü", kq, engine)]
    ref = k.hesap("rapor", F_REPORT, ins)
    job = k.portal("sosyal.rapor.yorum", "Rapor yorumu işi", S.jobs_stmt(tenant, hedef=month), engine)
    k.alanlar({"toplam": ref, "olcuSatiri": ins[1], "gonderiliOlcu": ref, "hesaplar": ref, "turler": ref,
               "gonderiDurum": ref, "gonderiSayisi": ins[2], "onaySuresiSaat": ref, "onaySayisi": ref, "yorum": job})
    return k
