"""M33 İhale takibi: ekrandaki her rakamın sorgu bilgisi (ortak sözleşme `provenance.py`).

İhale, kalem, belge, karar ve sonuç kayıtları portal tablolarındadır (elle, dosyadan ya da ilandan girilir); gösterilen
SQL uçta çalışan ifadenin kendisidir (`tenders.*_stmt`). Kalemin stoku ve Logo fiyatı eşleştirme anında Logo'dan okunup
satıra yazılır: asıl SQL o anda ÇALIŞAN metindir, eşleştirme işinin sonucunda saklanır (`tenders.read_jobs_stmt`).
Kamu satışları bellek önbelleğindeki son okumadır; çalışan Logo/CRM sorguları okuma sonucuyla birlikte tutulur.
"""
from __future__ import annotations

import json
from typing import Any, Iterable, Optional

from semantic_bridge import provenance as P
from semantic_bridge import tenders as T

F_KALAN = "Kalan gün = son teklif tarihi − bugün (takvim günü); eksi ise geçti."
F_LISTE = ("İlan satırı: yaklaşık tutar ve teminat ilandan (elle ya da dosyadan girilir); kalem sayısı = ihalenin kalem "
           "satırları, eşleşen = eşleşme durumu «eşleşti» olanlar. " + F_KALAN)
F_SAYAC = ("Açık ihale = durumu açık olanlar; 7 gün içinde son tarih = açık ihalelerden kalan günü 0–7 olanlar; onay bekleyen "
           "= karar kaydı «onayda» olanlar; kazanılan / kaybedilen = durum sayıları (ekranda sayılır).")
F_TOPLAM = ("Teklif tablosu: yalnız eşleşmiş, adedi ve birim teklif fiyatı olan kalemler toplanır; satır tutarı = adet × "
            "birim teklif (kuruşa yuvarlanır); KDV = satır tutarı × kalemin KDV oranı; genel toplam = ara toplam + KDV; liste "
            "toplamı = adet × KDV hariç liste fiyatı; fiyat oranı = ara toplam ÷ liste toplamı; tahmini marj = (gelir − adet × "
            "birim maliyet) ÷ gelir, yalnız maliyeti bilinen kalemlerde. Stok yetersiz = eşleşen kalemde stok < adet.")
F_KALEM = ("Kalem: adet ilandan/dosyadan; stok ve Logo fiyatı eşleştirme anında Logo'dan okundu (stok = giriş − çıkış, "
           "planlanan üretim girişi hariç; fiyat = bugün geçerli TL satış listesi, genel liste önce); liste fiyatı CRM KDV "
           "dahil fiyat (ayara göre Logo); birim teklif = KDV hariç liste × fiyat oranı (ya da elle); tutar = adet × birim "
           "teklif; marj = (birim teklif − birim maliyet) ÷ birim teklif. Eşleşme olasılığı Zeki AI seçiminin güvenidir; "
           "eşik altı öneri insan onayına kalır.")
F_PUAN = ("Uygunluk puanı (0–100) = ağırlıklı ortalama: eşleşen kalem payı, eşleşenlerde stoğu yeten pay, hazır zorunlu "
          "belge payı, süre (kalan gün ÷ tam süre gün, en çok 1). Ölçülemeyen parça dışarıda; ağırlıklar ayardır.")
F_ORAN = ("Fiyat oranı önerisi = geçmiş sonuçlarda kazanan fiyat ÷ aynı kalemlerin liste toplamı, ortanca (aynı kurum "
          "türünde yeterli sonuç varsa o, yoksa bütün sonuçlar; yetersizse 1).")
F_SONUC = ("Sonuç ekranı: sonuç kayıtları elle girilir (kazanan, kazanan fiyat, bizim teklif, liste toplamı); kazanan ÷ "
           "liste oranı satırda hesaplanır; kurum türü özeti = sonuç ve kazanılan sayısı, oranların ortancası.")
F_KAMU = ("Kamu satışı: faturalı satış satırı (iade eksi), net ciro = Σ LINENET, adet = Σ AMOUNT, fatura = farklı fatura "
          "sayısı; kamu = Logo satış kanalı (CLCARD.SPECODE2) ya da CRM'de kamu kurumu rolü işaretli cari. İl, kaynak ve "
          "toplam satırları bu cari satırlarından toplanır.")
F_KARAR = ("Karar özeti rakamları kayıttan ve teklif tablosundan (model yok); geçmiş = aynı kurumun ve kurum türünün sonuç "
           "sayısı, kazanılan, kazanan ÷ liste oranı ortancası. Zeki AI metni yalnız bu rakamları kullanır.")
F_BELGE = "Belge geçerlilik tarihi elle girilir; kalan gün = geçerlilik − bugün; uyarı günü ayardır."
F_OLASILIK = "İlanın kitap/yayın alımı olma olasılığı: Zeki AI seçiminin güveni (model sınıflaması); rakam başka hesaba girmez."


def _num_keys(out: dict[str, Any], ref: str, skip: Iterable[str] = ()) -> dict[str, str]:
    sk = set(skip)
    return {k: ref for k, v in out.items() if k not in sk and k != "kaynaklar" and P.numeric_paths({k: v})}


class _Ctx:
    def __init__(self, engine: Any, tenant: str, logo_db: Optional[str] = None, crm_db: Optional[str] = None):
        self.engine, self.tenant, self.dbs = engine, tenant, {"logo": logo_db, "crm": crm_db}
        self.k = P.Kaynaklar()

    def portal(self, sid: str, title: str, stmt: Any, desc: str, origin: Iterable[str] = ()) -> str:
        if sid in self.k.sources:
            return sid
        return self.k.portal(sid, title, stmt, self.engine, description=desc, origin=origin)

    def reads(self, prefix: str, reads: list[dict[str, Any]], desc: str, ran_at: Any = None) -> list[str]:
        """Saklanmış çalışan sorgular (bağlantı, metin, satır, süre) → kayıtlar; aynı metin bir kez."""
        ids, seen = [], set()
        for q in reads or []:
            sql = q.get("sql") or ""
            if not sql or sql in seen:
                continue
            seen.add(sql)
            conn = q.get("conn") if q.get("conn") in ("logo", "crm") else "logo"
            try:
                ids.append(self.k.sorgu(f"{prefix}.{len(ids) + 1}", _title(sql, conn), conn, sql, database=self.dbs.get(conn),
                                        rows=q.get("rows"), ms=q.get("dbMs"), ran_at=q.get("at") or ran_at,
                                        description=desc))
            except P.ProvenanceError:
                continue
        return ids


def _title(sql: str, conn: str) -> str:
    s = sql.upper()
    for key, t in (("L_CAPIPERIOD", "Logo yıl → firma kopyası"), ("PRCLIST", "Logo geçerli satış fiyatı"),
                   ("STFICHE", "Logo stok bakiyesi"), ("UNITBARCODE", "Logo barkodları"), ("_ITEMS WHERE", "Logo malzeme kartları"),
                   ("NEW_KITAP", "CRM kitap kataloğu"), ("NEW_KURUMROLU IN (2,3,4)", "CRM kurum rolü sayıları"),
                   ("ACCOUNTBASE", "CRM kamu kurumları"), ("CLCARD", "Logo kamu satışları")):
        if key in s:
            return t
    return "Logo sorgusu" if conn == "logo" else "CRM sorgusu"


def for_list(engine: Any, tenant: str, filters: dict[str, Any]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant)
    t = x.portal("ihale.ilanlar", "İhale kayıtları (süzgeçle)", T.tenders_stmt(tenant, **filters),
                 "Listelenen ihaleler; arama metni uçta süzülür (sayı tavanı yok).")
    n = x.portal("ihale.kalemSayilari", "İhale başına kalem ve eşleşen sayısı", T.item_counts_stmt(), "Kalem satırları.")
    p = x.portal("ihale.onayda", "Onay bekleyen kararlar", T.pending_stmt(), "Karar kaydı «onayda» olan ihaleler.")
    s = x.portal("ihale.durumlar", "Bütün ihalelerin durumu ve ili", T.status_counts_stmt(tenant), "Durum sayıları ve il listesi.")
    liste = x.k.hesap("liste", F_LISTE, [t, n, p])
    x.k.alanlar({"items[]": liste, "total": liste, "durumSayilari": x.k.hesap("durumSayilari", "Durum başına ihale sayısı "
                                                                                           "(süzgeçsiz).", [s]),
                 "sayac.acik": x.k.hesap("sayac", F_SAYAC, [t, s, p]), "sayac.yediGun": "hesap:sayac",
                 "sayac.onayBekleyen": "hesap:sayac", "sayac.kazanilan": "hesap:sayac"})
    return x.k


def for_calendar(engine: Any, tenant: str, out: dict[str, Any]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant)
    ins = [x.portal("ihale.ilanlarHepsi", "İhale kayıtları", T.tenders_stmt(tenant), "Son teklif ve teminat iade tarihleri."),
           x.portal("ihale.belgeler", "Şirket belge arşivi", T.documents_stmt(tenant), "Belge geçerlilik tarihleri (elle)."),
           x.portal("ihale.ihaleBelgeleri", "İhaleye özel belgeler", T.calendar_checks_stmt(tenant),
                    "Kontrol listesindeki geçerlilik tarihleri."),
           x.portal("ihale.onayda", "Onay bekleyen kararlar", T.pending_stmt(), "Karar kaydı «onayda».")]
    ref = x.k.hesap("takvim", "Takvim: son teklif (açık ihale), teminat iadesi, belge ve ihaleye özel belge geçerliliği; "
                              f"penceresi {out.get('gun')} gün. " + F_KALAN + " «N tarih» satır sayısıdır.", ins)
    x.k.alanlar({"items[]": ref})
    return x.k


def for_results(engine: Any, tenant: str, out: dict[str, Any]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant)
    r = x.portal("ihale.sonuclar", "İhale sonuçları", T.results_stmt(tenant), "Elle girilen sonuç kayıtları ve ihale bilgisi.")
    ref = x.k.hesap("sonuc", F_SONUC, [r])
    x.k.alanlar({"items[]": ref, "ozet[]": ref})
    return x.k


def for_documents(engine: Any, tenant: str, out: dict[str, Any]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant)
    d = x.portal("ihale.belgeler", "Şirket belge arşivi", T.documents_stmt(tenant), "Belge adı, türü, geçerlilik (elle).")
    ref = x.k.hesap("belge", F_BELGE, [d])
    x.k.alanlar({"items[]": ref, "uyariGun": ref})
    return x.k


def for_checklist(engine: Any, tenant: str, tid: str) -> P.Kaynaklar:
    x = _Ctx(engine, tenant)
    c = x.portal("ihale.kontrol", "Belge kontrol listesi", T.checklist_stmt(tid), "Kalem, zorunluluk, durum, geçerlilik.")
    d = x.portal("ihale.belgeler", "Şirket belge arşivi", T.documents_stmt(tenant), "Bağlı belgenin geçerliliği.")
    x.k.alanlar({"items[]": x.k.hesap("kontrol", F_BELGE + " Bağlı arşiv belgesinin geçerliliği satırın tarihi yoksa kullanılır; "
                                                           "süresi geçmiş belge «geçersiz».", [c, d])})
    return x.k


def match_reads(engine: Any, tid: str) -> tuple[list[dict[str, Any]], Any]:
    """Son eşleştirme işinin ve sonrasındaki elle eşleştirmelerin çalışan sorguları (en yeni önce)."""
    reads: list[dict[str, Any]] = []
    at = None
    with engine.connect() as c:
        for r in c.execute(T.read_jobs_stmt(tid)):
            res = json.loads(r.sonuc_json or "{}") if r.sonuc_json else {}
            reads.extend(res.get("sorgular") or [])
            at = at or r.bitis
            if r.tur == "eslestirme":
                break  # daha eskisi bu eşleştirmeyle ezildi
    return reads, at


def for_detail(engine: Any, tenant: str, tid: str, out: dict[str, Any], logo_db: Optional[str],
               crm_db: Optional[str]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant, logo_db, crm_db)
    k = x.k
    t = x.portal("ihale.ihale", "İhale kaydı", T.tender_stmt(tenant, tid),
                 "İlan bilgisi (yaklaşık tutar, teminat, son teklif), fiyat oranı, uygunluk, Zeki AI sınıflama ve özet.")
    reads, at = match_reads(engine, tid)
    origin = x.reads("ihale.okuma", reads, "Eşleştirme anında çalıştı; stok, fiyat ya da katalog satıra yazıldı.", at)
    jobs = x.portal("ihale.okumaIsleri", "Stok/fiyat okuyan işler", T.read_jobs_stmt(tid),
                    "Eşleştirme ve elle eşleştirme işleri; çalışan SQL'ler iş sonucunda saklı.", origin=origin)
    items = x.portal("ihale.kalemler", "İhale kalemleri", T.items_stmt(tid), "Kalem satırları: adet, eşleşme, stok, fiyat, "
                                                                            "maliyet (satıra yazılmış hâli).", origin=[jobs])
    checks = x.portal("ihale.kontrol", "Belge kontrol listesi", T.checklist_stmt(tid), "Zorunlu belgeler ve durumu.")
    docs = x.portal("ihale.belgeler", "Şirket belge arşivi", T.documents_stmt(tenant), "Belge geçerliliği.")
    dec = x.portal("ihale.kararlar", "Karar geçmişi", T.decisions_stmt(tid), "Öneri, onay, teklif toplamı, fiyat oranı.")
    res = x.portal("ihale.sonuc", "Sonuç kaydı", T.results_stmt(tenant, tid), "Kazanan, kazanan fiyat, liste toplamı (elle).")
    hist = x.portal("ihale.sonuclar", "Geçmiş sonuçlar", T.results_stmt(tenant), "Aynı kurum ve kurum türünün sonuçları.")
    kalem = k.hesap("kalem", F_KALEM, [items, jobs] + origin)
    toplam = k.hesap("toplam", F_TOPLAM, [kalem])
    fields = _num_keys(out, k.hesap("ihale", "İlan bilgisi elle, dosyadan ya da ilandan girilir. " + F_KALAN, [t]),
                       skip=("kalemler", "toplamlar", "kontrolListesi", "kararlar", "sonuc", "kararOzeti", "uygunluk",
                             "uygunlukPuani", "fiyatOrani", "kitapIlani", "ayarlar", "isler", "dosyalar", "ozet"))
    fields.update({
        "kalemler[]": kalem, "toplamlar": toplam,
        "uygunlukPuani": k.hesap("puan", F_PUAN, [items, checks, docs, t]), "uygunluk": "hesap:puan",
        "fiyatOrani": k.hesap("oran", F_ORAN + " Kayıtlı oran elle değiştirilmiş olabilir; kaynağı satırda yazılı.", [t, hist]),
        "kitapIlani": k.hesap("olasilik", F_OLASILIK, [t]),
        "kontrolListesi[]": k.hesap("kontrol", F_BELGE, [checks, docs]),
        "kararlar[]": k.hesap("karar", "Karar geçmişi: öneride dondurulan teklif toplamı ve fiyat oranı.", [dec]),
        "sonuc": k.hesap("sonuc", F_SONUC, [res]),
        "kararOzeti": k.hesap("kararOzeti", F_KARAR, [t, toplam, checks, hist]),
        "ayarlar": k.hesap("ayar", "Eşleştirme eşikleri ve aday sayısı ayardır (Yönetim).", [t]),
        "isler[]": jobs,
        "dosyalar[]": x.portal("ihale.dosyalar", "İhale dosyaları", T.files_stmt(tid), "Yüklenen dosyalar (boyut, bayt)."),
        "ozet": k.hesap("ozet", "Şartname özeti Zeki AI'ındır; her sayı kaynak cümlesiyle birlikte saklanır ve metinde "
                                "geçtiği denetlenir.", [t]),
    })
    k.alanlar(fields)
    return k


def for_public_sales(out: dict[str, Any], logo_db: Optional[str], crm_db: Optional[str]) -> P.Kaynaklar:
    x = _Ctx(None, "", logo_db, crm_db)
    ids = x.reads("ihale.kamu", out.get("sorgular") or [], f"Kamu satışları okuması ({out.get('year')} · Logo firma "
                                                           f"{out.get('firm')}); sonuç 10 dakika bellekte tutulur.",
                  out.get("okunma"))
    if not ids:
        raise P.ProvenanceError("Kamu satışı okumasının sorguları saklanmamış (eski önbellek); «yenile» ile görünür.")
    ref = x.k.hesap("kamu", F_KAMU, ids)
    x.k.alanlar({**_num_keys(out, ref, skip=("year",)), "rows[]": ref, "iller[]": ref})
    return x.k


def for_catalog_search(cat: Any, logo_db: Optional[str], crm_db: Optional[str]) -> P.Kaynaklar:
    x = _Ctx(None, "", logo_db, crm_db)
    ids = x.reads("ihale.katalog", getattr(cat, "sorgular", None) or [], "Katalog okuması (30 dakika bellekte).")
    if not ids:
        raise P.ProvenanceError("Katalog sorguları saklanmamış.")
    x.k.alanlar({"items[]": x.k.hesap("benzerlik", "Benzerlik = aranan metinle kitap adının sözcük örtüşmesi (seyrek sözcük "
                                                    "ağırlıklı, 0–1); ISBN ya da stok kodu tam eşleşmesi 1.", ids)})
    return x.k


#: Rakam olmayan sayılar: yıl, sıra no, kimlik.
NOT_RAKAM = ("year", "gun", "kalemler[].sira", "kontrolListesi[].sira", "items[].sira", "items[].ref", "rows[].ref",
             "rows[].crmRol", "items[].crmRol")
