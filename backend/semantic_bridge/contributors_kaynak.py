"""Kişiler (`/kisiler`: yazar, çevirmen, çizer ve serbest çalışanlar): ekrandaki her rakamın sorgu bilgisi.

Liste, rol sayıları ve kişi ayrıntısı istek anında CRM'deki eser katılım kayıtlarından okunur (`editorial.contributors_*`,
`person_*`). Gösterilen SQL o istekte ÇALIŞAN metindir (`sorgu_kaydi.RunLog`: çalıştırıcının fiziksel metni, satır,
süre, hesaplandığı an); `*_sql(...)` işlevi aynı argümanlarla yeniden kurulup kayıtla eşlenir, eşleşmezse kaynak açılmaz.
Kişisel veri: kişi adı ve özgeçmiş sonuç satırıdır, kayda girmez; yalnız SQL metni ve satır sayısı.
"""
from __future__ import annotations

import os
from typing import Any, Optional

from semantic_bridge import editorial as E
from semantic_bridge import provenance as P
from semantic_bridge.sorgu_kaydi import RunLog

PFX = "kisiler."
#: Rakam olmayan sayılar: sayfa ve sayfa boyu; çalıştırıcının «hesaplandığı an» damgası.
NOT_RAKAM = ("page", "pageSize", "db.computedAt")

F_KATKI = ("Kişi = CRM eser katılım kaydı (new_eserkatilimBase, etkin) olan kişi (ContactBase), seçili rollerle "
           "(new_katilimcitipiBase.new_name). Eser = kişinin katkı verdiği farklı kitap sayısı; son 12 ayda = kaydı son 12 ayda "
           "açılmış farklı kitap; son 12 ayda çalışan = son 12 ayda en az bir yeni eser kaydı olan kişi; eser katkısı = kişi "
           "başına eser sayılarının toplamı. Kapasite, puan ve müsaitlik CRM'de tutulmadığı için hesaplanmaz.")
F_KISI_BASI = "Kişi başına eser = eser katkısı / kişi sayısı (bir ondalık)."
F_OKUMA = "Okuma süresi = listenin CRM sorgusunun milisaniyesi (sonuç önbellekten verildiyse ilk çalıştığı an)."
F_SAYAC = "Sayı = listedeki satır sayısı (sorgunun döndürdüğü kayıtların tamamı; satır sınırı aşılırsa ekranda yazar)."


def crm_db() -> Optional[str]:
    return P.connection_database(os.environ.get("SEMANTIC_CRM_CONNECTION_FILE",
                                                "/data/nanobaseai/bi/secrets/crm-mssql-connection.json"))


def _roles_text(roles: list[str]) -> str:
    clean = [r for r in roles if r and r.strip()]
    return ", ".join(clean) if clean else "—"


def for_contributors(out: dict[str, Any], log: RunLog, schema: str, roles: list[str], page: int, q: str = "",
                     order: str = "son") -> P.Kaynaklar:
    k = P.Kaynaklar()
    db = crm_db()
    rt = _roles_text(roles)
    head = log.sorgu(k, PFX + "sayim", "Süzgece uyan kişi, son 12 ayda çalışan, eser katkısı", "crm",
                     E.contributors_count_sql(schema, roles, q), database=db,
                     description=f"Roller: {rt}" + (f"; ad araması «{q.strip()}»" if q.strip() else "") + ".")
    lst = log.sorgu(k, PFX + "liste", "Kişi listesi (bu sayfa)", "crm", E.contributors_list_sql(schema, roles, page, q, order),
                    database=db, description=f"Sayfa başına {E.PAGE_SIZE} kişi; sayfa {int(page) + 1}. Sıra: "
                    + {"eser": "en çok eser", "ad": "ada göre"}.get(order, "son çalışan") + ".")
    ids = [c["id"] for c in out.get("items") or [] if c.get("id")]
    rol = log.sorgu(k, PFX + "roller", "Sayfadaki kişilerin rol başına eser sayısı", "crm",
                    E.contributor_roles_sql(schema, ids), database=db) if ids else None
    fields: dict[str, str] = {}
    if head:
        ref = k.hesap("katki", F_KATKI, [head])
        fields.update({"total": ref, "activePeople": ref, "contributions": ref,
                       "kisiBasinaEser": k.hesap("kisiBasi", F_KISI_BASI, [ref])})
    if lst:
        fields["items[]"] = k.hesap("liste", F_KATKI, [x for x in (lst, rol) if x])
        fields["db"] = k.hesap("okuma", F_OKUMA, [lst])
    if rol:
        fields["items[].roles"] = rol
    k.alanlar(fields)
    return k


def for_roles(out: dict[str, Any], log: RunLog, schema: str) -> P.Kaynaklar:
    k = P.Kaynaklar()
    src = log.sorgu(k, PFX + "rolSayilari", "Rol başına katılım kaydı ve kişi sayısı", "crm", E.role_facet_sql(schema),
                    database=crm_db(), description="Rol süzgecindeki «(N)» = o rolde eser kaydı olan farklı kişi.")
    if src:
        k.alanlar({"items[]": src, "db": src})
    return k


def for_person(out: dict[str, Any], log: RunLog, schema: str, contact_id: str) -> P.Kaynaklar:
    k = P.Kaynaklar()
    db = crm_db()
    works = log.sorgu(k, PFX + "eserler", "Kişinin eser katılımları", "crm", E.person_works_sql(schema, contact_id),
                      database=db, description="Kitap ve rol; en yeniden eskiye.")
    contracts = log.sorgu(k, PFX + "sozlesmeler", "Kişinin taraf olduğu sözleşmeler", "crm",
                          E.person_contracts_sql(schema, contact_id), database=db,
                          description="Sözleşme no, durum, başlangıç/bitiş, telif oranı (new_Telif), ödeme payı.")
    projects = log.sorgu(k, PFX + "projeler", "Kişinin olası yazar olduğu projeler", "crm",
                         E.person_projects_sql(schema, contact_id), database=db)
    fields: dict[str, str] = {}
    for key, src in (("works[]", works), ("contracts[]", contracts), ("projects[]", projects)):
        if src:
            fields[key] = src
    sayac = {"eser": works, "sozlesme": contracts, "proje": projects}
    for key, src in sayac.items():
        if src:
            fields[f"sayac.{key}"] = k.hesap(f"sayac.{key}", F_SAYAC, [src])
    if works:
        fields["db"] = works
    k.alanlar(fields)
    return k
