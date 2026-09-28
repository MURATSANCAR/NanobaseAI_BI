"""M27 Fuar ve etkinlik: ekrandaki her rakamın sorgu bilgisi (ortak sözleşme `provenance.py`).

Kart, görev, gider, kitap, ödül sayıları portal tablolarından (semantic_events_*, semantic_awards*); CRM etkinlikleri,
tipleri, siparişleri, kitap ve yazar listeleri `events_sources` üreticileriyle çalışan metin; Logo fuar satışı, stok ve
veri sonu sorguları çalıştığı metinle (fuar satışında okuma işinin kaydettiği metin, diğerlerinde önbellekteki yıl → firma
eşlemesiyle aynı üretici). Fuar sonucu kaydedildiyse kaydedilmiş hesap ve kaydedilen sorgu metni gösterilir.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Iterable, Optional

from semantic_bridge import events as E
from semantic_bridge import events_sources as src
from semantic_bridge import pazarlama_kaynak as PK
from semantic_bridge import provenance as P

NOT_RAKAM = ("settings", "page", "pageSize", "year", "sort", "tasks[].sort", "crmMs", "window.tailDays", "shown",
             "result.window", "fair.tasks[].sort")

F_CAL = ("Takvim: portal fuar/etkinlik kartları + CRM etkinlikleri (başlangıcı yılda, etkin); CRM tipi portal eşlemesiyle "
         "sınıflanır, eşlenmemiş tip sayısı ayrı. Ay başına kayıt = o ayda başlayan kart + etkinlik.")
F_FAIR = ("Kart: başlangıca gün = başlangıç − bugün; hazırlık = tamamlanan / toplam görev (geciken = son günü geçmiş); gider = "
          "portal gider satırları toplamı, bütçe = onaylanan bütçe; kitap sayısı ve stoku yetersiz = planlanan > stok.")
F_UPCOMING = ("Yaklaşanlar: bitmemiş kartlar, son tarihi gelmemiş ödüller (kalan gün, başvuru sayısı), son 14 günün hatırlatmaları, "
              "son günü geçmiş açık görevler (gecikme günü).")
F_SUGGEST = ("Kitap önerisi: temel dönemde (önceki fuar ya da geçen yılın aynı günleri) fuar kanalındaki satış adedi × ayardaki "
             "katsayı; stok yetersiz = önerilen > Logo stoku; yeni çıkanlar (son N ay) temel satışı yoksa ayardaki katsayıyla eklenir.")
F_RESULT = ("Fuar sonucu: fuar günleri + ayardaki kuyruk günleri boyunca fuar kanalındaki (ya da karttaki carilerin) faturalı satış "
            "satırları: satış − iade, net ciro = satır net tutarı; geçen yıla göre = temel dönemin aynı hesabına göre değişim; "
            "gider = portal gider satırları + CRM etkinlik gideri; 1 ₺ gidere satış = net ciro ÷ toplam gider; satış oranı = "
            "planlanan kitaplardan satılan ÷ planlanan; siparişler = CRM fuar / etkinlik / imza siparişleri (tip başına).")
F_TYPES = ("Tip eşlemesi: CRM etkinlik tipleri (etkin etkinlik sayısı, son başlangıç) + portal eşlemesi; öneri olasılığı = Zeki AI "
           "sınıflamasının olasılığı; sayılar = toplam / karar verilen / öneri hazır tip.")
F_AWARDS = "Ödül defteri: kalan gün = son başvuru − bugün; başvuru sayısı ve durumları portal kaydından."


def _schema() -> str:
    from semantic_bridge import admin as admin_mod

    return admin_mod.conf("CRM_SCHEMA") or "Timas_MSCRM.dbo"


def _crm(k: P.Kaynaklar, id_: str, title: str, sql: str) -> str:
    return k.sorgu(id_, title, "crm", sql, database=PK.crm_db(), description="CRM okuması (kısa süre bellekte tutulur).")


def _logo(k: P.Kaynaklar, id_: str, title: str, sql: str, desc: str = "") -> str:
    return k.sorgu(id_, title, "logo", sql, database=PK.logo_db(), description=desc)


def _fairs(k: P.Kaynaklar, engine: Any, tenant: str, year: Optional[int]) -> list[str]:
    fq, tq, cq, bq = E.fairs_stmts(tenant, year)
    return [k.portal("etk.kart", "Fuar / etkinlik kartları", fq, engine), k.portal("etk.gorev", "Görevler", tq, engine),
            k.portal("etk.gider", "Giderler", cq, engine), k.portal("etk.kitap.say", "Kart başına kitap", bq, engine)]


def _detail(k: P.Kaynaklar, engine: Any, tenant: str, fid: str) -> str:
    fq, tq, cq, bq, aq = E.fair_detail_stmts(tenant, fid)
    return k.hesap("kart", F_FAIR, [k.portal("etk.kart", "Kart", fq, engine), k.portal("etk.gorev", "Görevler", tq, engine),
                                    k.portal("etk.gider", "Giderler", cq, engine), k.portal("etk.kitap", "Kitaplar", bq, engine),
                                    k.portal("etk.yazar", "Yazar programı", aq, engine)])


def detail_fields(k: P.Kaynaklar, ref: str, prefix: str = "") -> None:
    for f in ("daysLeft", "tasksTotal", "tasksDone", "tasksLate", "prep", "costTotal", "books", "budgetPlanned",
              "resultSummary", "tasks", "costs", "costByKind", "bookList", "authors", "result"):
        k.alan(f"{prefix}{f}", ref)


def for_calendar(engine: Any, tenant: str, year: int) -> P.Kaynaklar:
    k = P.Kaynaklar()
    ins = _fairs(k, engine, tenant, year) + [
        _crm(k, "etk.crm", "CRM etkinlikleri (yıl)", src.events_sql(_schema(), date(year, 1, 1), date(year + 1, 1, 1))),
        k.portal("etk.tip", "Tip eşlemesi", E.type_map_stmt(tenant), engine)]
    ref = k.hesap("takvim", F_CAL, ins)
    for f in ("months", "fairs", "events", "totals", "unmappedTypes"):
        k.alan(f, ref)
    return k


def for_upcoming(engine: Any, tenant: str) -> P.Kaynaklar:
    k = P.Kaynaklar()
    aq, nq, rq, lq = E.upcoming_stmts(tenant, E.today())
    ins = _fairs(k, engine, tenant, None) + [k.portal("etk.odul", "Ödüller", aq, engine),
                                             k.portal("etk.basvuru.say", "Ödül başına başvuru", nq, engine),
                                             k.portal("etk.hatirlatma", "Hatırlatmalar", rq, engine),
                                             k.portal("etk.geciken", "Geciken görevler", lq, engine)]
    ref = k.hesap("yaklasan", F_UPCOMING + " " + F_FAIR, ins)
    k.alanlar({"fairs": ref, "awards": ref, "lateTasks": ref, "reminders": ref})
    return k


def for_crm_events(engine: Any, tenant: str, frm: date, to: date) -> P.Kaynaklar:
    k = P.Kaynaklar()
    ev = _crm(k, "etk.crm", "CRM etkinlikleri (dönem)", src.events_sql(_schema(), frm, to))
    ref = k.hesap("crm", "Katılımcı, satılan kitap, gider CRM etkinlik kartındaki alanlardır; toplam = süzgeçten geçen kayıt.",
                  [ev, k.portal("etk.tip", "Tip eşlemesi", E.type_map_stmt(tenant), engine)])
    k.alanlar({"items": ref, "total": ref})
    return k


def for_type_map(engine: Any, tenant: str) -> P.Kaynaklar:
    k = P.Kaynaklar()
    ref = k.hesap("tip", F_TYPES, [_crm(k, "etk.crm.tip", "CRM etkinlik tipleri ve kullanımı", src.types_sql(_schema())),
                                   k.portal("etk.tip", "Tip eşlemesi", E.type_map_stmt(tenant), engine)])
    k.alanlar({"items": ref, "counts": ref, "job": ref})
    return k


def for_fairs(engine: Any, tenant: str, year: Optional[int]) -> P.Kaynaklar:
    k = P.Kaynaklar()
    k.alan("items", k.hesap("kart", F_FAIR, _fairs(k, engine, tenant, year)))
    return k


def for_fair(engine: Any, tenant: str, fid: str) -> P.Kaynaklar:
    k = P.Kaynaklar()
    detail_fields(k, _detail(k, engine, tenant, fid))
    return k


def for_suggest(engine: Any, tenant: str, fid: str, source: Any, sales_sql: Iterable[str]) -> P.Kaynaklar:
    k = P.Kaynaklar(as_of=E._now())
    ins = [_logo(k, f"etk.logo.fuar.{i}", "Temel dönem fuar kanalı satışı (Logo)", s, "Okuma işinin çalıştırdığı metin.")
           for i, s in enumerate(sales_sql, 1)]
    firms = source.firms()
    if firms:
        ins.append(_logo(k, "etk.logo.stok", "Logo stok bakiyesi", src.stock_sql(firms[max(firms)])))
    ins += [_crm(k, "etk.crm.kitap", "CRM kitap kartları", src.books_sql(_schema())),
            _crm(k, "etk.crm.kitap.yazar", "Kitap yazarları", src.book_authors_sql(_schema()))]
    ref = k.hesap("oneri", F_SUGGEST, ins)
    k.alan("counts", ref)
    detail_fields(k, _detail(k, engine, tenant, fid), "detail.")
    return k


def for_result(engine: Any, tenant: str, fid: str, source: Any, r: dict[str, Any], fair_row: dict[str, Any]) -> P.Kaynaklar:
    k = P.Kaynaklar(data_end=r.get("dataEnd"), as_of=r.get("computedAt"))
    ins = [_logo(k, f"etk.logo.sonuc.{i}", "Fuar günleri fuar kanalı satışı (Logo)", s, "Sonuç hesaplanırken çalışan metin.")
           for i, s in enumerate(r.get("sql") or [], 1)]
    ins += [_logo(k, f"etk.logo.temel.{i}", "Temel dönem satışı (Logo)", s, "Sonuç hesaplanırken çalışan metin.")
            for i, s in enumerate(r.get("sqlOnceki") or [], 1)]
    firms = source.firms()
    if firms:
        ins.append(_logo(k, "etk.logo.verisonu", "Logo veri sonu", src.data_end_sql(firms[max(firms)])))
    st = E.settings()
    a, b = E.result_window(fair_row, st["resultTailDays"])
    try:
        ins.append(_crm(k, "etk.crm.siparis", "CRM fuar / etkinlik / imza siparişleri",
                        src.orders_sql(_schema(), a, b, st["orderTypes"], st["orderExcluded"])))
    except src.SourceError:
        pass
    ids = src.guids(E._json_list(fair_row.get("crm_event_ids_json")))
    for i in range(0, len(ids), src.IN_CHUNK):
        ins.append(_crm(k, f"etk.crm.etkinlik.{i // src.IN_CHUNK + 1}", "Karta bağlı CRM etkinlikleri",
                        src.events_by_id_sql(_schema(), ids[i:i + src.IN_CHUNK])))
    ins += [k.portal("etk.gider", "Portal giderleri", E.fair_costs_stmt(fid), engine),
            k.portal("etk.kitap", "Planlanan kitaplar", E.planned_books_stmt(fid), engine)]
    ref = k.hesap("sonuc", F_RESULT, ins)
    for f in ("netCiro", "netAdet", "kitapSayisi", "books", "clients", "unsoldPlanned", "plannedTotal", "sellThrough", "prev",
              "orders", "orderCount", "orderTotal", "crmEvents", "katilimci", "crmSatilan", "costs", "toplamGider", "butce",
              "butceFarki", "roi"):
        k.alan(f"result.{f}", ref)
    detail_fields(k, _detail(k, engine, tenant, fid), "fair.")
    return k


def for_lookup_books() -> P.Kaynaklar:
    k = P.Kaynaklar()
    ref = k.hesap("ara", "Kitap araması CRM kitap kartlarında (ad, stok kodu, yazar); toplam = eşleşen, gösterilen = ilk sayfa.",
                  [_crm(k, "etk.crm.kitap", "CRM kitap kartları", src.books_sql(_schema())),
                   _crm(k, "etk.crm.kitap.yazar", "Kitap yazarları", src.book_authors_sql(_schema()))])
    k.alanlar({"items": ref, "total": ref})
    return k


def for_lookup_authors() -> P.Kaynaklar:
    k = P.Kaynaklar()
    ref = _crm(k, "etk.crm.yazar", "CRM yazar kişileri", src.authors_sql(_schema()))
    k.alanlar({"items": ref, "total": ref})
    return k


def for_clients(source: Any, channel: str) -> Optional[P.Kaynaklar]:
    firms = source.firms()
    if not firms:
        return None
    k = P.Kaynaklar()
    k.alan("items", _logo(k, "etk.logo.cari", "Fuar kanalı carileri (Logo)", src.channel_clients_sql(firms[max(firms)], channel)))
    return k


def for_author_events(engine: Any, tenant: str, cid: str, year: int) -> P.Kaynaklar:
    k = P.Kaynaklar()
    ref = _crm(k, "etk.crm.yazar.etkinlik", "Yazarın etkinlikleri (CRM)",
               src.author_events_sql(_schema(), cid, date(year, 1, 1), date(year + 1, 1, 1)))
    k.alanlar({"items": ref, "total": ref})
    return k


def for_awards(engine: Any, tenant: str) -> P.Kaynaklar:
    k = P.Kaynaklar()
    aq, eq = E.awards_stmts(tenant)
    k.alan("items", k.hesap("odul", F_AWARDS, [k.portal("etk.odul", "Ödüller", aq, engine),
                                               k.portal("etk.basvuru", "Başvurular", eq, engine)]))
    return k

