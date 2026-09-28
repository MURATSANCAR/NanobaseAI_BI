"""M28 Kurumsal ilişkiler: ekrandaki her rakamın sorgu bilgisi (ortak sözleşme `provenance.py`).

Kişi, kurum, hediye, proje ve temas sayıları portal tablolarından (semantic_rel_*); CRM okumaları (kişi / kurum arama,
ziyaret yeri istatistiği, roller, kitaplar, tanıtım sipariş toplamları, proje siparişleri) `public_affairs_sources`
üreticileriyle çalışan metin; sonucu önceki okumaya bağlı olan proje raporu sorguları okuma sırasında kaydedilen metinle.

KİŞİSEL VERİ: kişi kartı (ad, e-posta, telefon, notlar) kişisel veridir; yalnız SQL metni kayda girer, satır asla.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Iterable, Optional

from semantic_bridge import pazarlama_kaynak as PK
from semantic_bridge import provenance as P
from semantic_bridge import public_affairs as PA
from semantic_bridge import public_affairs_sources as src
from semantic_bridge import relations_core as core

NOT_RAKAM = ("settings", "page", "pageSize", "stageIndex", "items[].stageIndex", "projects[].stageIndex", "kurumTipi",
             "items[].kurumTipi", "items[].role", "role", "crmOrderStatus", "crmOrderType", "items[].crmOrderStatus",
             "items[].crmOrderType", "gifts[].crmOrderStatus", "gifts[].crmOrderType", "year", "heat.meta")

F_PEOPLE = ("Kişi listesi: temas zamanı gelen = önceliğin temas günü (kritik / normal, ayar) aşılmış kart; ısı = son temas "
            "notlarının sayısı ve yakınlığından kural puanı, son temasın üzerinden geçen gün; açık adım = yapılmamış «sıradaki "
            "adım»; son hediye = iptal dışı son hediye satırı; sayılar = bütün etkin kartlar üzerinden toplam / zamanı gelen / kritik.")
F_HOME = F_PEOPLE + (" Açık projeler aşama başına; geciken = sıradaki adım günü geçmiş, sessiz = 30 gündür olay yok; bu ayın "
                     "hediye programı durum başına, kitap ve kişi sayısı; geciken adım = günü geçmiş yapılmamış adım.")
F_GIFTS = ("Hediye programı: durum başına satır; kitap / kişi = iptal dışı satırlardaki farklı kitap ve kişi; CRM sipariş durumu "
           "gece CRM'den eşitlenir.")
F_PROJECTS = ("Projeler: aşama başına sayı; bütçe ve erişim (okul, öğrenci, kitap, katılımcı) karta girilen değerler; geciken = "
              "sıradaki adım günü geçmiş açık proje.")
F_REACH = ("Proje erişim raporu: hedef kurumlar CRM ziyaret yeri kartlarından (öğrenci, öğretmen sayısı), dağıtılan kitap = "
           "projeye yazılmış CRM sipariş numaralarının satır adetleri toplamı; katılım elle girilen değer.")
F_REPORT = ("Etki raporu (yıl): etkin kişi, kritik, kamu görevlisi, alan başına kişi; yıldaki temas notu, temas edilen kişi / "
            "kurum; hediye durumları, gönderilen kitap ve kişi, geri dönüş, aynı kişiye aynı kitap; projeler aşama başına ve "
            "erişim toplamı (vazgeçilen hariç). CRM satırı = tanıtım gönderimi sipariş tipleri başına sipariş ve kitap adedi.")
F_ORGS = "Kurum listesi: kurum başına etkin kişi kartı ve açık proje sayısı."


def _schema() -> str:
    from semantic_bridge import admin as admin_mod

    return admin_mod.conf("CRM_SCHEMA") or "Timas_MSCRM.dbo"


def _crm(k: P.Kaynaklar, id_: str, title: str, sql: str, desc: str = "") -> str:
    return k.sorgu(id_, title, "crm", sql, database=PK.crm_db(), description=desc)


def _people(k: P.Kaynaklar, engine: Any, tenant: str, archived: bool = False) -> list[str]:
    pq, nq, fq, oq = PA.people_stmts(tenant, archived)
    return [k.portal("ki.kisi", "Kişi kartları", pq, engine, description="Ad, e-posta, telefon kişisel veri; yalnız sorgu."),
            k.portal("ki.not", "Temas notları", nq, engine), k.portal("ki.alan", "Alanlar", fq, engine),
            k.portal("ki.kurum", "Kurumlar", oq, engine),
            k.portal("ki.hediye.son", "Kişi başına son hediye", PA.last_gifts_stmt(tenant), engine)]


def _projects(k: P.Kaynaklar, engine: Any, tenant: str) -> list[str]:
    pq, oq, eq = PA.projects_stmts(tenant)
    return [k.portal("ki.proje", "Projeler", pq, engine), k.portal("ki.kurum", "Kurumlar", oq, engine),
            k.portal("ki.proje.olay", "Proje başına son olay", eq, engine)]


def _gifts(k: P.Kaynaklar, engine: Any, tenant: str, month: str = "", status: str = "", person: str = "") -> list[str]:
    gq, pq = PA.gifts_stmts(tenant, month, status, person)
    return [k.portal("ki.hediye", "Hediye satırları", gq, engine), k.portal("ki.hediye.kisi", "Hediye kişileri", pq, engine)]


def for_home(engine: Any, tenant: str) -> P.Kaynaklar:
    k = P.Kaynaklar(as_of=core.now())
    ins = _people(k, engine, tenant) + _projects(k, engine, tenant) + _gifts(k, engine, tenant, PA.month_of()) + [
        k.portal("ki.adim", "Geciken sıradaki adım", PA.late_steps_stmt(tenant, core.now()), engine)]
    ref = k.hesap("ana", F_HOME, ins)
    for f in ("due", "dueTotal", "peopleCounts", "projects", "projectStages", "lateProjects", "quietProjects", "gifts",
              "giftBooks", "giftPeople", "waitingApproval", "lateSteps"):
        k.alan(f, ref)
    return k


def for_people(engine: Any, tenant: str, archived: bool) -> P.Kaynaklar:
    k = P.Kaynaklar(as_of=core.now())
    ref = k.hesap("kisi", F_PEOPLE, _people(k, engine, tenant, archived))
    k.alanlar({"items": ref, "total": ref, "counts": ref})
    return k


def for_person(engine: Any, tenant: str, pid: str, crm_contact: Optional[str]) -> P.Kaynaklar:
    k = P.Kaynaklar(as_of=core.now())
    pq, oq, nq, gq = PA.person_stmts(tenant, pid)
    ins = [k.portal("ki.kisi", "Kişi kartı", pq, engine), k.portal("ki.kurum", "Kurumlar", oq, engine),
           k.portal("ki.not", "Kişinin temas notları", nq, engine), k.portal("ki.hediye", "Kişinin hediyeleri", gq, engine)]
    ref = k.hesap("kart", F_PEOPLE, ins)
    k.alanlar({"heat": ref, "dueDays": ref, "timeline": ins[2], "gifts": ins[3]})
    if crm_contact:
        k.alan("crm", _crm(k, "ki.crm.kisi", "CRM kişi kartı", src.contact_sql(_schema(), crm_contact),
                           "CRM kişisi (kişisel veri; yalnız sorgu)."))
    return k


def for_orgs(engine: Any, tenant: str, archived: bool) -> P.Kaynaklar:
    k = P.Kaynaklar()
    oq, pq, jq = PA.orgs_list_stmts(tenant, archived)
    ref = k.hesap("kurum", F_ORGS, [k.portal("ki.kurum", "Kurum kartları", oq, engine),
                                    k.portal("ki.kurum.kisi", "Kurum başına kişi", pq, engine),
                                    k.portal("ki.kurum.proje", "Kurum başına açık proje", jq, engine)])
    k.alanlar({"items": ref, "total": ref})
    return k


def for_org(engine: Any, tenant: str, oid: str, place_id: Optional[str]) -> P.Kaynaklar:
    k = P.Kaynaklar(as_of=core.now())
    people = k.hesap("kisi", F_PEOPLE, _people(k, engine, tenant))
    projects = k.hesap("proje", F_PROJECTS, _projects(k, engine, tenant))
    k.alanlar({"people": people, "projects": projects,
               "timeline": k.portal("ki.kurum.not", "Kurum notları", PA.org_notes_stmt(tenant, oid), engine)})
    if place_id:
        k.alan("crm", _crm(k, "ki.crm.yer", "CRM ziyaret yeri (öğrenci, öğretmen, kitap)", src.places_by_id_sql(_schema(), [place_id])))
    return k


def for_crm_contacts(q: str, role: Optional[int], page: int) -> P.Kaynaklar:
    k = P.Kaynaklar()
    ref = _crm(k, "ki.crm.kisiler", "CRM kişi araması (toplam aynı sorgunun pencere sayımı)", src.contacts_sql(_schema(), q, role, page),
               "Aranan değer kişi adı olabilir; sorgu yalnız metin olarak gösterilir, sonuç satırı kayda girmez.")
    k.alanlar({"items": ref, "total": ref})
    return k


def for_crm_places(q: str, kurum_tipi: Optional[int], il: str, page: int) -> P.Kaynaklar:
    k = P.Kaynaklar()
    ref = _crm(k, "ki.crm.yerler", "CRM ziyaret yeri araması", src.places_sql(_schema(), q, kurum_tipi, il, page))
    k.alanlar({"items": ref, "total": ref})
    return k


def for_city_stats(il: str, kurum_tipi: int) -> P.Kaynaklar:
    k = P.Kaynaklar()
    ref = _crm(k, "ki.crm.il", "İl istatistiği (kurum, öğrenci)", src.city_stats_sql(_schema(), il, kurum_tipi))
    k.alanlar({"places": ref, "students": ref, "studentsUnknown": ref})
    return k


def for_roles() -> P.Kaynaklar:
    k = P.Kaynaklar()
    k.alanlar({"personRoles": _crm(k, "ki.crm.rol", "CRM kişi rolleri ve kullanımı", src.person_roles_sql(_schema())),
               "decisionMakers": _crm(k, "ki.crm.karar", "«Karar Veren» etkin kişi sayısı", src.decision_makers_sql(_schema()))})
    return k


def for_crm_books(q: str, page: int, month: str) -> P.Kaynaklar:
    k = P.Kaynaklar()
    if month:
        y, m = (int(x) for x in month.split("-"))
        sql = src.books_published_sql(_schema(), date(y, m, 1), date(y + (m == 12), m % 12 + 1, 1))
        ref = _crm(k, "ki.crm.kitap.ay", "Ayın ilk baskı kitapları (CRM)", sql)
    else:
        ref = _crm(k, "ki.crm.kitap", "CRM kitap araması", src.books_sql(_schema(), q, page))
    k.alanlar({"items": ref, "total": ref})
    return k


def for_gifts(engine: Any, tenant: str, month: str, status: str, person: str) -> P.Kaynaklar:
    k = P.Kaynaklar()
    ref = k.hesap("hediye", F_GIFTS, _gifts(k, engine, tenant, month, status, person))
    k.alanlar({"items": ref, "total": ref, "counts": ref, "books": ref, "people": ref})
    return k


def for_gift_suggest(engine: Any, tenant: str, runs: Iterable[dict[str, Any]]) -> P.Kaynaklar:
    k = P.Kaynaklar()
    crm = PK.kayitli(k, runs, "ki.crm.oneri", None, description="Öneri için çalışan CRM okuması (kitap, kişi etiketleri).")
    ins = crm + _people(k, engine, tenant) + [k.portal("ki.hediye.tum", "Kişi başına hediyeler", PA.gifts_stmts(tenant)[0], engine)]
    ref = k.hesap("oneri", "Hediye önerisi kuraldır: kitabın konusu / hedef kitlesi ile kişinin alanı, ilgi alanları ve CRM "
                           "etiketleri örtüşmesi puanlanır; aynı kitap daha önce gönderildiyse ve son hediyenin üzerinden ayardaki "
                           "gün geçmediyse düşülür; gerekçe her satırda.", ins)
    k.alanlar({"items": ref, "total": ref, "books": ref, "people": ref})
    return k


def for_projects(engine: Any, tenant: str) -> P.Kaynaklar:
    k = P.Kaynaklar(as_of=core.now())
    ref = k.hesap("proje", F_PROJECTS, _projects(k, engine, tenant))
    k.alanlar({"items": ref, "total": ref, "stages": ref})
    return k


def for_project(engine: Any, tenant: str, pid: str) -> P.Kaynaklar:
    k = P.Kaynaklar()
    pq, eq, oq = PA.project_stmts(tenant, pid)
    ref = k.hesap("proje", F_PROJECTS, [k.portal("ki.proje", "Proje", pq, engine), k.portal("ki.proje.olay", "Olaylar", eq, engine),
                                        k.portal("ki.kurum", "Kurumlar", oq, engine)])
    for f in ("budget", "reachSchools", "reachStudents", "reachBooks", "reachParticipants", "books", "events"):
        k.alan(f, ref)
    return k


def for_project_report(engine: Any, tenant: str, pid: str, runs: Iterable[dict[str, Any]]) -> P.Kaynaklar:
    k = P.Kaynaklar(as_of=core.now())
    crm = PK.kayitli(k, runs, "ki.crm.proje", None, description="Proje raporu için çalışan CRM okuması.")
    pq, eq, oq = PA.project_stmts(tenant, pid)
    ref = k.hesap("erisim", F_REACH, crm + [k.portal("ki.proje", "Proje", pq, engine)])
    k.alanlar({"facts": ref, "places": ref})
    for f in ("budget", "reachSchools", "reachStudents", "reachBooks", "reachParticipants", "books"):
        k.alan(f"project.{f}", ref)
    return k


def for_report(engine: Any, tenant: str, year: int, types: Iterable[int], excluded: Iterable[int]) -> P.Kaynaklar:
    k = P.Kaynaklar(as_of=core.now())
    pq, nq, gq, jq = PA.report_stmts(tenant, year)
    ins = [k.portal("ki.rapor.kisi", "Etkin kişiler", pq, engine), k.portal("ki.rapor.not", "Yıldaki temas notları", nq, engine),
           k.portal("ki.rapor.hediye", "Yıldaki hediyeler", gq, engine), k.portal("ki.rapor.proje", "Projeler", jq, engine),
           k.portal("ki.alan", "Alanlar", PA.fields_stmt(tenant), engine)]
    ref = k.hesap("rapor", F_REPORT, ins)
    k.alanlar({"people": ref, "contacts": ref, "gifts": ref, "projects": ref})
    try:
        k.alan("crm", _crm(k, "ki.crm.tanitim", "Tanıtım gönderimi sipariş toplamları (CRM)",
                           src.promo_totals_sql(_schema(), year, list(types), list(excluded))))
    except Exception:  # noqa: BLE001 — ayar boşsa üretici hata verir
        pass
    return k
