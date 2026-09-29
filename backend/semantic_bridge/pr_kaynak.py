"""M20 Basın ilişkileri: ekrandaki her rakamın sorgu bilgisi (ortak sözleşme `provenance.py`).

CRM okumaları (ayın kitapları, kitap kartı ve yazarları, kitap araması, medya kişileri, haber arşivi, tanıtım gönderimi
siparişleri) `pr_sources` içindeki aynı SQL üreticileriyle, aynı değerlerle kaydedilir; CRM okuması bellekte tutulur
(10 dakikadan eskiyse arkada yeniden okunur), gösterilen metin o okumanın metnidir. Portal okumaları (PR dosyası, gönderim, yansıma, kişi katmanı)
`pr.py`'deki ifade işlevlerinden derlenir.

KİŞİSEL VERİ: medya kişilerinin e-posta ve telefonu kişisel veridir; yalnız SQL metni kayda girer, satır asla.
"""
from __future__ import annotations

from typing import Any

from semantic_bridge import pazarlama_kaynak as PK
from semantic_bridge import pr as PR
from semantic_bridge import pr_sources as S
from semantic_bridge import provenance as P

NOT_RAKAM = ("page", "pageSize", "version", "items[].version", "pending[].version", "kits[].version", "openKit.version",
             "m15Release.surum", "settings")

F_HOME = ("Ayın kitapları CRM kitap kartlarından (ilk baskı tarihi seçilen ayda); dosyası yok = PR dosyası olmayan kitap; "
          "onay bekleyen = «onayda» dosya; cevap bekleyen = takip günü geçmiş, dönüşsüz gönderim; son 30 gün yansıma = "
          "yayın günü son 30 gün içinde kayıtlı yansıma; aday = onay bekleyen yansıma adayı. Kitap satırındaki gönderim / "
          "gönderilen / yansıma = dosya başına portal sayısı.")
F_KITS = ("PR dosyaları portal kaydından; gönderim = dosyadaki satır sayısı, gönderilen = gönderildi / cevap / haber / olumsuz / "
          "cevapsız durumundaki satır; yansıma = o kitaba bağlı kayıtlı yansıma sayısı.")
F_BOOK = ("Kitap kartı CRM'den; arşiv haberi = CRM haber arşivinde bu kitaba bağlı kayıt; tanıtım gönderimi = CRM tanıtım "
          "siparişlerinin (sipariş tipi 12) bu stok koduna ait satırları, toplam adet = satır adetlerinin toplamı.")
F_KIT = ("PR dosyası: gönderim listesi, dosyanın kitabına bağlı yansımalar (reddedilen hariç) ve son iş; düşen cümle = "
         "taslağın sayı denetiminde notlarda / kartta geçmeyen sayıyı taşıdığı için atılan cümle.")
F_SUGGEST = ("Öneri puanı kuraldır: yazarın kitapları hakkında haber ×3, aynı kitaplık ×2, aynı hedef kitle ×1 (CRM haber "
             "arşivi), konu etiketi eşleşmesi ×2, portalda yansıma ×1, dönüş ×1, olumsuz −1, son bir yılda temas +1; toplam = "
             "süzgeçten geçen kişi sayısı.")
F_CONTACTS = ("Medya kişileri CRM rollerinden + portal katmanı (elle eklenen kişi, konu etiketi, haberdar olmak istemiyor); "
              "haber sayısı = CRM arşivinde muhabir ya da görüşülen olarak geçtiği haber; geçmiş = portal gönderim ve "
              "yansıma sayısı, son temas; toplam = süzgeçten geçen kişi, tümü = bütün kişiler.")
F_COVERAGE = ("Yansımalar portal kaydından (elle, tarama adayı) + CRM haber arşivi (salt okuma); süzgeç (dönem, kitap, kaynak, "
              "ton, arama, kişi) hesapta; durum sayıları = bütün portal yansımalarının durum başına sayısı; ton olasılığı = "
              "ton sınıflamasının olasılığı.")
F_REPORT = ("Dönem raporu: gönderim = gönderim günü dönemde olan satır (durum ve kanal başına); dönüş = cevap + haber, oran = "
            "dönüş ÷ gönderim; yansıma = yayın günü (yoksa kayıt günü) dönemde olan kayıtlı yansıma (ton, mecra türü, kaynak, "
            "mecra, kitap, yazar kırılımı); CRM arşivi = haber tarihi dönemde olan CRM kaydı; aday = onay bekleyen yansıma.")


def _schema() -> str:
    from semantic_bridge import admin as admin_mod

    return admin_mod.conf("CRM_SCHEMA") or "Timas_MSCRM.dbo"


def _crm(k: P.Kaynaklar, id_: str, title: str, sql: str, desc: str = "") -> str:
    return k.sorgu(id_, title, "crm", sql, database=PK.crm_db(),
                   description=desc or "CRM okuması bellekte tutulur: 10 dakikadan eskiyse eldeki gösterilir ve arkada "
                                       "yeniden okunur; «Yenile» kaynağı bekler.")


def _archive(k: P.Kaynaklar, crm: Any) -> list[str]:
    sch = _schema()
    base = getattr(crm, "archive_path", None) == "temel-tablo"
    head = S.archive_base_sql(sch) if base else S.archive_sql(sch)
    return [_crm(k, "pr.arsiv", "CRM haber arşivi" + (" (temel tablo)" if base else ""), head),
            _crm(k, "pr.arsiv.kitap", "CRM haber–kitap bağları", S.archive_books_sql(sch))]


def _contacts(k: P.Kaynaklar, engine: Any, tenant: str, crm: Any) -> list[str]:
    roles = list(crm.roles() or [])
    return [_crm(k, "pr.kisi", "CRM medya kişileri", S.media_contacts_sql(_schema(), roles),
                 "CRM medya kişileri (e-posta ve telefon kişisel veri; yalnız sorgu gösterilir)."),
            k.portal("pr.kisi.katman", "Portal kişi katmanı", PR.overlays_stmt(tenant), engine)] + _archive(k, crm)


def _kits(k: P.Kaynaklar, engine: Any, tenant: str, prefix: str, title: str, **kw: Any) -> list[str]:
    q = PR.list_kits_stmts(tenant, **kw)
    if q is None:
        return []
    return [k.portal(f"{prefix}", title, q[0], engine),
            k.portal(f"{prefix}.gonderim", "Dosya başına gönderim ve gönderilen", q[1], engine),
            k.portal(f"{prefix}.yansima", "Kitap başına kayıtlı yansıma", q[2], engine)]


def _history(k: P.Kaynaklar, engine: Any, tenant: str) -> list[str]:
    sq, cq = PR.history_stmts(tenant)
    return [k.portal("pr.gecmis.gonderim", "Kişi başına gönderimler", sq, engine),
            k.portal("pr.gecmis.yansima", "Kişi başına kayıtlı yansıma", cq, engine)]


def for_home(engine: Any, tenant: str, crm: Any, frm: Any, to: Any, book_ids: list[str]) -> P.Kaynaklar:
    k = P.Kaynaklar(as_of=PR.now())
    books = _crm(k, "pr.ay", "Ayın kitapları (CRM)", S.month_books_sql(_schema(), frm, to))
    kits = _kits(k, engine, tenant, "pr.dosya", "Ayın kitaplarının PR dosyaları", books=book_ids)
    pend = _kits(k, engine, tenant, "pr.onayda", "Onay bekleyen dosyalar", status="onayda")
    over = k.portal("pr.geciken", "Takip günü geçmiş gönderimler", PR.overdue_stmt(tenant), engine)
    cov = k.portal("pr.yansima", "Kayıtlı yansımalar", PR.coverage_stmt(tenant, "kayitli"), engine)
    cand = k.portal("pr.aday", "Yansıma adayları", PR.coverage_stmt(tenant, "aday"), engine)
    ref = k.hesap("ana", F_HOME, [books] + kits + pend + [over, cov, cand])
    k.alanlar({"kpi": ref, "books": ref, "pending": k.hesap("dosya", F_KITS, pend), "overdue": over,
               "recentCoverage": cov})
    return k


def for_search(q: str, page: int) -> P.Kaynaklar:
    k = P.Kaynaklar()
    rows_sql, count_sql = S.book_search_sql(_schema(), q, page)
    ids = [_crm(k, "pr.ara.say", "Kitap araması: toplam", count_sql), _crm(k, "pr.ara", "Kitap araması: bu sayfa", rows_sql)]
    k.alanlar({"total": ids[0], "items": ids[1]})
    return k


def for_book(engine: Any, tenant: str, crm: Any, book: dict[str, Any]) -> P.Kaynaklar:
    k = P.Kaynaklar(as_of=PR.now())
    sch = _schema()
    bid = str(book.get("kitapId") or "")
    card = [_crm(k, "pr.kitap", "Kitap kartı (CRM)", S.book_sql(sch, bid)),
            _crm(k, "pr.kitap.yazar", "Kitabın yazarları (CRM)", S.book_authors_sql(sch, bid))]
    arc = _archive(k, crm)
    promo = []
    if book.get("stokKodu"):
        try:
            promo = [_crm(k, "pr.tanitim", "Tanıtım gönderimi siparişleri (CRM)", S.promo_orders_sql(sch, book["stokKodu"]))]
        except S.SourceError:
            promo = []
    kits = _kits(k, engine, tenant, "pr.dosya", "Kitabın PR dosyaları", books=[bid])
    ref = k.hesap("kitap", F_BOOK, card + arc + promo)
    kref = k.hesap("dosya", F_KITS, kits) if kits else ref
    k.alanlar({"book": card[0], "archive": ref, "promoOrders": ref, "promoTotal": ref, "kits": kref, "openKit": kref})
    return k


def for_kits(engine: Any, tenant: str, status: str) -> P.Kaynaklar:
    k = P.Kaynaklar()
    ref = k.hesap("dosya", F_KITS, _kits(k, engine, tenant, "pr.dosya", "PR dosyaları", status=status))
    k.alanlar({"items": ref, "total": ref})
    return k


def for_kit(engine: Any, tenant: str, kit: dict[str, Any]) -> P.Kaynaklar:
    k = P.Kaynaklar()
    kid = kit["id"]
    ins = [k.portal("pr.dosya", "PR dosyası", PR.kit_stmt(tenant, kid), engine),
           k.portal("pr.dosya.gonderim", "Gönderim listesi", PR.kit_sends_stmt(kid), engine),
           k.portal("pr.dosya.yansima", "Dosyanın yansımaları", PR.kit_coverage_stmt(tenant, kid, kit.get("crmBookId")), engine),
           k.portal("pr.dosya.is", "Son iş", PR.kit_job_stmt(kid), engine),
           k.portal("pr.kisi.katman", "Portal kişi katmanı (haberdar olmak istemiyor)", PR.overlays_stmt(tenant), engine)]
    ref = k.hesap("dosya", F_KIT, ins)
    k.alanlar({"sends": ins[1], "coverage": ins[2], "job": ins[3], "draft": ref, "sources": ref, "assets": ref})
    return k


def for_events(engine: Any, tenant: str, ref: str) -> P.Kaynaklar:
    k = P.Kaynaklar()
    k.alan("items", k.portal("pr.olay", "Değişiklik kaydı", PR.events_stmt(tenant, ref), engine))
    return k


def for_suggest(engine: Any, tenant: str, crm: Any, kit: dict[str, Any]) -> P.Kaynaklar:
    k = P.Kaynaklar()
    sch = _schema()
    bid = kit.get("crmBookId") or ""
    ins = (_contacts(k, engine, tenant, crm) + _history(k, engine, tenant)
           + [_crm(k, "pr.kitap", "Kitap kartı (CRM)", S.book_sql(sch, bid)),
              k.portal("pr.dosya.gonderim", "Dosyadaki kişiler (listede olan çıkarılır)", PR.kit_sends_stmt(kit["id"]), engine)])
    ref = k.hesap("oneri", F_SUGGEST, ins)
    k.alanlar({"items": ref, "total": ref})
    return k


def for_contacts(engine: Any, tenant: str, crm: Any) -> P.Kaynaklar:
    k = P.Kaynaklar()
    ref = k.hesap("kisi", F_CONTACTS, _contacts(k, engine, tenant, crm) + _history(k, engine, tenant))
    k.alanlar({"items": ref, "total": ref, "all": ref})
    return k


def for_contact(engine: Any, tenant: str, crm: Any, key: str) -> P.Kaynaklar:
    k = P.Kaynaklar()
    ref = k.hesap("kisi", F_CONTACTS, _contacts(k, engine, tenant, crm) + _history(k, engine, tenant))
    sends = k.portal("pr.kisi.gonderim", "Kişiye gönderimler", PR.sends_of_contact_stmt(tenant, key), engine)
    cov = k.portal("pr.yansima", "Kayıtlı yansımalar", PR.coverage_stmt(tenant, "kayitli"), engine)
    ev = k.portal("pr.olay", "Değişiklik kaydı", PR.events_stmt(tenant, key), engine)
    k.alanlar({"contact": ref, "history": ref, "archive": ref, "sends": sends, "coverage": cov, "events": ev})
    return k


def for_coverage(engine: Any, tenant: str, crm: Any, state: str, with_archive: bool) -> P.Kaynaklar:
    k = P.Kaynaklar()
    rows = k.portal("pr.yansima", "Yansımalar", PR.coverage_stmt(tenant, state), engine)
    allr = k.portal("pr.yansima.hepsi", "Bütün yansımalar (durum sayısı)", PR.coverage_stmt(tenant, ""), engine)
    ref = k.hesap("yansima", F_COVERAGE, [rows] + (_archive(k, crm) if with_archive else []))
    k.alanlar({"items": ref, "total": ref, "counts": k.hesap("durum", F_COVERAGE, [allr])})
    return k


def for_report(engine: Any, tenant: str, crm: Any) -> P.Kaynaklar:
    k = P.Kaynaklar(as_of=PR.now())
    sq, cq, pq = PR.report_stmts(tenant)
    ins = [k.portal("pr.rapor.gonderim", "Gönderilmiş satırlar", sq, engine),
           k.portal("pr.rapor.yansima", "Kayıtlı yansımalar", cq, engine)]
    pend = k.portal("pr.rapor.aday", "Aday yansıma sayısı", pq, engine)
    ref = k.hesap("rapor", F_REPORT, ins + _archive(k, crm))
    k.alanlar({"sends": ref, "coverage": ref, "archive": ref, "pendingCandidates": pend, "comment": ref})
    return k

