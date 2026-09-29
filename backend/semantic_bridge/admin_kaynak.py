"""Yönetim ekranı (Portal ayarları): her rakamın sorgu bilgisi (ortak sözleşme `provenance.py`).

Sayaçların hepsi portal tablolarından (semantic_reports, semantic_alert_rules, semantic_board_cards, semantic_audit,
semantic_access_*, sl_query_log, sl_concept, sl_schema_profile) okunur; gösterilen SQL uçta çalışan ifadenin kendisidir.
Rol üyelik sayıları üye görüntüsünden gelir; görüntüyü dolduran asıl okuma CRM rolleri için CRM SQL'i, AD grupları için
etki alanı dizini okumasıdır (SQL'i yoktur, adıyla yazılır). Soru izlemede her sorunun kendi SQL'i: veritabanında koşan
fiziksel metin (sonuçla birlikte saklanır).
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

from semantic_bridge import access as AC
from semantic_bridge import admin as AD
from semantic_bridge import alerts as A
from semantic_bridge import alerts_kaynak as AK
from semantic_bridge import bulletins as BU
from semantic_bridge import provenance as P
from semantic_bridge import reports as R
from semantic_bridge import reports_kaynak as RK
from semantic_bridge import soru_kaynak as SK

AD_DIS = "Etki alanı dizini (Active Directory) okuması, 15 dakikada bir üye görüntüsüne yazılır"
AYAR_DIS = "Yönetim ekranı ayarı: yönetici hesapları listesi ve yönetici grubu üyeleri"


def _profiles_stmt(ds: str) -> Any:
    import sqlalchemy as sa
    from semantic_layer.store import schema as S

    return sa.select(S.sl_schema_profile).where(S.sl_schema_profile.c.datasource_id == ds).order_by(
        S.sl_schema_profile.c.table_name)


def _profiles_source(k: P.Kaynaklar, engine: Any, ds: str) -> str:
    base = k.portal("portal.katalog.profiller", "Katalog tablo profilleri", _profiles_stmt(ds), engine,
                    description="Köprü açılışta ve katalog yenilenince tablo profillerini bu okumayla belleğe alır; "
                                "satır sayıları gece katalog taramasının Logo ve CRM'den ölçtüğü değerlerdir.")
    return k.hesap("profiller", "Tablo sayısı = katalogdaki tablo profilleri (yıl ve firma kopyaları ayrı tablo); "
                                "satır sayısı taramanın son ölçümü.", [base])


# ------------------------------------------------------------------ genel durum


def for_overview(engine: Any, store: Any, tenant: str, ds: str, out: dict[str, Any]) -> P.Kaynaklar:
    k = P.Kaynaklar()
    rep = k.portal("portal.yonetim.raporlar", "Planlı raporlar (herkesin)", R.list_stmt(tenant, ds, None), engine)
    al = k.portal("portal.yonetim.uyarilar", "Uyarı kuralları (herkesin)", A.list_stmt(tenant, ds, None), engine)
    cards = k.portal("portal.yonetim.kartlar", "Pano kartları (herkesin)", AD.all_cards_stmt(tenant, ds), engine)
    us = AD.users_stmts(tenant, ds)
    people = [k.portal(f"portal.yonetim.kisi.{n}", t, us[n], engine) for n, t in
              (("cards", "Kişi başına pano kartı"), ("reports", "Kişi başına planlı rapor"),
               ("actions", "Kişi başına kayıtlı işlem"))]
    cat = k.portal("portal.katalog.durum", "Katalog terimleri (durum başına)", store.status_counts_stmt(tenant, ds),
                   engine, description="Sertifikalı terim sayısı = durumu CERTIFIED olan kavramlar.")
    adm = k.hesap("yoneticiler", "Yönetici = yönetim ayarındaki hesaplar ve yönetici grubunun son görüntüsü.",
                  dis=AYAR_DIS)
    k.alanlar({
        "counts.reports": k.hesap("raporlar", "Planlı rapor = bütün planlar; etkin = durumu etkin; hatalı = son "
                                              "çalışması başarısız.", [rep]),
        "counts.reportsActive": "hesap:raporlar", "counts.reportsFailed": "hesap:raporlar",
        "counts.alerts": k.hesap("uyarilar", "Uyarı = bütün kurallar; etkin = durumu etkin; tetiklendi = son "
                                             "kontrolde eşiği aşan.", [al]),
        "counts.alertsActive": "hesap:uyarilar", "counts.alertsTriggered": "hesap:uyarilar",
        "counts.cards": k.hesap("kartlar", "Pano kartı = bütün kişilerin kartları; hatalı = son koşusu hata veren.",
                                [cards]),
        "counts.cardsFailed": "hesap:kartlar",
        "counts.users": k.hesap("kisiler", "Kişi = kartı, planı ya da kayıtlı işlemi olan her hesap (yöneticiler "
                                           "dahil).", people + [adm]),
        "counts.admins": adm,
        "engine.catalog": cat,
        "engine.profiles": _profiles_source(k, engine, ds),
    })
    return k


#: Genel durumda rakam olmayan sayılar: son değişiklikler listesi (kayıt numarası ve değişikliğin ayrıntısı; ekran
#: bunları sayı olarak değil kaydın metni olarak gösterir).
OVERVIEW_NOT_RAKAM = ("recent",)


# ------------------------------------------------------------------ listeler


def for_reports(engine: Any, tenant: str, ds: str, items: list[dict[str, Any]], logo_db: Optional[str],
                crm_db: Optional[str]) -> P.Kaynaklar:
    return RK.for_list(engine, tenant, ds, None, items, logo_db, crm_db, key="items")


def for_alerts(engine: Any, tenant: str, ds: str, items: list[dict[str, Any]], logo_db: Optional[str],
               crm_db: Optional[str]) -> P.Kaynaklar:
    return AK.for_list(engine, tenant, ds, None, {"alerts": items}, logo_db, crm_db, key="items")


def for_users(engine: Any, tenant: str, ds: str) -> P.Kaynaklar:
    k = P.Kaynaklar()
    us = AD.users_stmts(tenant, ds)
    ins = [k.portal(f"portal.yonetim.kisi.{n}", t, us[n], engine) for n, t in
           (("cards", "Kişi başına pano kartı"), ("reports", "Kişi başına planlı rapor"),
            ("actions", "Kişi başına kayıtlı işlem (değişiklik kaydı, sistem hariç)"))]
    k.alan("items", k.hesap("kisi", "Kişi başına: pano kartı sayısı, planlı rapor sayısı, kayıtlı işlem sayısı; son "
                                    "görülme bu üçünün en yenisi.", ins))
    return k


# ------------------------------------------------------------------ soru izleme


def for_prompt_overview(engine: Any, stmts: dict[str, Any], out: dict[str, Any]) -> P.Kaynaklar:
    k = P.Kaynaklar()
    days = out.get("sinceDays")
    total = k.portal("portal.soru.toplam", f"Sorular · son {days} gün", stmts["total"], engine)
    ans = k.portal("portal.soru.cevaplanan", f"Cevaplanan · son {days} gün", stmts["answered"], engine,
                   description="Koşturulmuş ve hata vermemiş sorular.")
    todo = k.portal("portal.soru.duzeltilecek", "Düzeltilecek işaretli", stmts["todo"], engine)
    ref = k.hesap("ozet", "Toplam = dönemdeki sorular; cevaplanan = koşturulmuş ve hatasız; başarısız = toplam − "
                          "cevaplanan; düzeltilecek = inceleyenin «düzeltilecek» işaretlediği.", [total, ans, todo])
    k.alanlar({key: ref for key, v in out.items() if P.numeric_paths({key: v}) and key != "sinceDays"})
    return k


def for_prompt_list(engine: Any, stmt: Any, out: dict[str, Any]) -> P.Kaynaklar:
    k = P.Kaynaklar()
    base = k.portal("portal.soru.liste", "Soru kayıtları", stmt, engine, rows=len(out.get("items") or []),
                    description="Her sorunun kaydı: satır sayısı ve süre soru koşarken yazılır (sonuç satırı değil).")
    k.alanlar({"items": k.hesap("liste", "Satır = sorunun döndürdüğü satır sayısı; süre = sorunun baştan sona "
                                         "cevaplanma süresi (ms). İkisi de soru kaydında saklıdır.", [base])})
    return k


def for_prompt(engine: Any, stmt: Any, row: dict[str, Any], logo_db: Optional[str],
               crm_db: Optional[str]) -> P.Kaynaklar:
    k = P.Kaynaklar()
    base = k.portal("portal.soru.kayit", "Soru kaydı", stmt, engine,
                    description="Sorunun kaydı ve saklanan tam sonucu (sl_query_log).")
    res = row.get("result") or {}
    refs, text = [base], ("Sonuç tablosu ve satır sayısı soru koşarken saklanan tam sonuçtan; aşağıdaki SQL o koşuda "
                          "veritabanında koşan metindir.")
    if res.get("physicalSql"):
        refs.append(SK.calisan(k, "soru.kosu", "Sorunun veritabanında koşan SQL'i", physical_sql=res["physicalSql"],
                               logo_db=logo_db, crm_db=crm_db, rows=res.get("totalRows"), ms=res.get("dbMs"),
                               ran_at=row.get("createdAt")))
    else:
        text += (" Bu soru, koşan metin kaydedilmeye başlamadan önce soruldu; kayıttaki SQL çözülmemiş (katalog "
                 "adlarıyla) metindir ve SSMS'te doğrudan koşmaz.")
    ref = k.hesap("soru", text, refs)
    k.alanlar({key: ref for key, v in row.items() if P.numeric_paths({key: v})})
    return k


#: Soru kaydında rakam olmayan sayılar: katalog sürüm numarası.
PROMPT_NOT_RAKAM = ("catalogVersion", "items[].catalogVersion", "nextOffset")


# ------------------------------------------------------------------ yetkiler


def _role_sources(k: P.Kaynaklar, engine: Any, tenant: str, directory: Any, crm_db: Optional[str]) -> list[str]:
    st = AC.role_stmts(tenant)
    ids = [k.portal("portal.yetki.roller", "Roller", st["roles"], engine),
           k.portal("portal.yetki.izinler", "Rol başına sayfa ve özellik izinleri", st["perms"], engine),
           k.portal("portal.yetki.baglar", "Rol bağları (AD grubu, OU, CRM rolü, kişi)", st["bindings"], engine)]
    origin = []
    try:
        if directory is not None:
            origin.append(k.sorgu("crm.yetki.rol-uyeleri", "CRM rol üyeleri", "crm", directory.crm_role_members_sql(),
                                  database=crm_db, description="Üye görüntüsünü dolduran CRM okuması (15 dakikada bir)."))
    except Exception:  # noqa: BLE001 — CRM şeması tanımlı değilse köken AD'den ibarettir
        pass
    ids.append(k.portal("portal.yetki.uyeler", "Bağ başına üye görüntüsü", st["members"], engine, origin=origin,
                        description="AD grubu, OU ve CRM rolü üyelerinin son okuması; üye sayısı bu listeden."))
    ids.append(k.hesap("ad", "AD grubu ve OU üyeleri etki alanı dizininden okunur.", dis=AD_DIS))
    return ids


def for_roles(engine: Any, tenant: str, directory: Any, crm_db: Optional[str]) -> P.Kaynaklar:
    k = P.Kaynaklar()
    ins = _role_sources(k, engine, tenant, directory, crm_db)
    k.alan("items", k.hesap("roller", "Rol başına: sayfa sayısı = rolün izinlerindeki sayfalar ÷ katalogdaki bütün "
                                      "sayfalar; bağ sayısı = rolün bağları; kişi = bağların üye sayılarının toplamı "
                                      "(kişi bağı 1 sayılır).", ins))
    return k


def for_subjects(kind: str, out: dict[str, Any], directory: Any, crm_db: Optional[str]) -> P.Kaynaklar:
    k = P.Kaynaklar()
    if kind == "crm_role" and directory is not None:
        roles = k.sorgu("crm.yetki.roller", "CRM kök rolleri", "crm", directory.crm_roles_sql(), database=crm_db)
        mem = k.sorgu("crm.yetki.rol-uyeleri", "CRM rol üyeleri", "crm", directory.crm_role_members_sql(),
                      database=crm_db, description="Etkin, giriş yapabilen kullanıcılar; 5 dakika bellekte tutulur.")
        ref = k.hesap("aday", "Aday başına kişi = rolü taşıyan etkin CRM kullanıcısı sayısı.", [roles, mem])
    else:
        ref = k.hesap("aday", "Aday başına kişi = grubun/OU'nun etkin üye sayısı (iç içe gruplar dahil).", dis=AD_DIS)
    k.alan("items", ref)
    return k


def for_members(kind: str, out: dict[str, Any], directory: Any, crm_db: Optional[str]) -> P.Kaynaklar:
    k = P.Kaynaklar()
    if kind == "crm_role" and directory is not None:
        mem = k.sorgu("crm.yetki.rol-uyeleri", "CRM rol üyeleri", "crm", directory.crm_role_members_sql(),
                      database=crm_db, description="Etkin, giriş yapabilen kullanıcılar; 5 dakika bellekte tutulur.")
        ref = k.hesap("uye", "Rolü taşıyan etkin CRM kullanıcıları; ad ve birim AD kişi listesinden.", [mem])
    else:
        ref = k.hesap("uye", "Bağın etkin üyeleri: grupta iç içe gruplar, birimde alt birimler dahil.", dis=AD_DIS)
    k.alanlar({"count": ref, "items": ref})
    return k


def for_explain(engine: Any, tenant: str, out: dict[str, Any], directory: Any, crm_db: Optional[str]) -> P.Kaynaklar:
    k = P.Kaynaklar()
    ins = _role_sources(k, engine, tenant, directory, crm_db)
    ref = k.hesap("kisi", "Kişinin rolleri: bağlı olduğu AD grupları, OU'su, CRM rolleri ve kişi bağlarından; sayfa "
                          "sayısı rollerin izinlerinin birleşimi.", ins)
    k.alanlar({key: ref for key, v in out.items() if P.numeric_paths({key: v})})
    return k


def for_entities(engine: Any, tenant: str, ds: str, out: dict[str, Any]) -> P.Kaynaklar:
    import sqlalchemy as sa

    k = P.Kaynaklar()
    prof = _profiles_source(k, engine, ds)
    over = k.portal("portal.yetki.varlik-alanlari", "Yöneticinin atadığı veri alanları",
                    sa.select(AC.ENTITY_DOMAINS.c.entity, AC.ENTITY_DOMAINS.c.domain).where(
                        AC.ENTITY_DOMAINS.c.tenant_id == tenant), engine)
    ref = k.hesap("alan", "Varlık başına satır = varlığın bütün tablolarının (yıl ve firma kopyaları) satır toplamı; "
                          "tablo = kopya sayısı; alan sayaçları = o alana düşen varlık sayısı (atanmamış dahil). Alan "
                          "yönetici atamasından, yoksa kaynağa göre kuraldan.", [prof, over])
    k.alanlar({"items": ref, "counts": ref})
    return k


# ------------------------------------------------------------------ sesli bülten


def for_bulletins(engine: Any, tenant: str, out: dict[str, Any]) -> P.Kaynaklar:
    k = P.Kaynaklar()
    base = k.portal("portal.bulten", "Sesli bültenler", BU.listing_stmt(tenant, published_only=False), engine,
                    rows=len(out.get("items") or []))
    k.alanlar({"items": k.hesap("bulten", "Kayıt = bütün bültenler; yayında = durumu yayında olanlar; süre ve boyut "
                                          "ses dosyasından (yüklemede ölçülür).", [base]),
               "maxMb": k.hesap("sinir", "Yükleme sınırı yönetim ayarıdır (MB).", dis="Yönetim ekranı ayarı")})
    return k


def for_jobs(engine: Any, tenant: str, out: dict[str, Any]) -> P.Kaynaklar:
    k = P.Kaynaklar()
    base = k.portal("portal.bulten.isler", "Seslendirme işleri (son 20)", BU.jobs_stmt(tenant), engine,
                    rows=len(out.get("items") or []))
    k.alan("items", k.hesap("is", "Karakter = seslendirilecek metnin uzunluğu (iş kurulurken sayılır); durum "
                                  "seslendirme servisinden eşitlenir.", [base]))
    return k


NOT_RAKAM: Iterable[str] = ("items[].episode",)
