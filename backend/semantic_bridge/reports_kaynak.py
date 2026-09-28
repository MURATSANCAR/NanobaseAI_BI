"""Planlı raporlar: ekrandaki her rakamın sorgu bilgisi (ortak sözleşme `provenance.py`).

Plan bir sorudur; her çalışmada soru yeniden çözülür ve köprü fiziksel SQL'i Logo/CRM'de tam koşturur. O koşunun
fiziksel metni, satır sayısı ve süresi plan kaydına yazılır (`last_db_json`); «Son kullanılan SQL» ve «i» bunu
gösterir. Önizleme (Excel taslağı) soru cevabının kendi fiziksel SQL'inden.
"""
from __future__ import annotations

from typing import Any, Optional

from semantic_bridge import provenance as P
from semantic_bridge import reports as R
from semantic_bridge import soru_kaynak as SK

F_PLAN = ("Son çalışma: satır sayısı ve dosya, planın sorusunun o çalışmada koşan SQL'inden (bütün satırlar, tavan "
          "yok). Gizli kolon sayısı planın kolon düzeninden (kişinin gizlediği kolonlar).")
F_ESKI = " Bu planın son çalışması, çalışan SQL'i kaydetmeye başlamadan önce yapıldı; bir sonraki çalışmada yazılır."
F_SAYAC = "Plan sayısı = sizin planlarınız; etkin = durumu «etkin» olanlar."
F_ONIZLEME = ("Önizleme: sorunun cevabının ilk 50 satırı; satır sayısı sorgunun döndürdüğü toplamdır, dosyaya tamamı "
              "yazılır. Gizli kolon sayısı kolon düzeninden.")

#: Rakam olmayan sayılar: haftanın günü, ayın günü (zamanlama ayarı).
NOT_RAKAM = ("reports[].weekday", "reports[].monthday", "weekday", "monthday")


def _plan_ref(k: P.Kaynaklar, rep: dict[str, Any], base: str, logo_db: Optional[str], crm_db: Optional[str]) -> str:
    db = rep.get("lastDb") or {}
    refs, text = [base], F_PLAN
    if db.get("physicalSql"):
        refs.append(SK.calisan(k, f"rapor.{rep['id']}", f"Planın sorusu · {str(rep.get('title') or '')[:80]}",
                               physical_sql=db["physicalSql"], logo_db=logo_db, crm_db=crm_db, rows=db.get("rows"),
                               ms=db.get("dbMs"), ran_at=db.get("computedAt"),
                               description="Son çalışmada koşan metin; dosyadaki bütün satırlar bundan."))
    elif rep.get("lastRunAt"):
        text += F_ESKI
    return k.hesap(f"plan:{rep['id']}", text, refs)


def for_list(engine: Any, tenant: str, ds: str, user: Optional[str], reports: list[dict[str, Any]],
             logo_db: Optional[str], crm_db: Optional[str], *, key: str = "reports") -> P.Kaynaklar:
    k = P.Kaynaklar()
    base = k.portal("portal.raporlar", "Planlı raporlar", R.list_stmt(tenant, ds, user), engine, rows=len(reports),
                    description="Planlar, zamanlamaları ve son çalışmaları (semantic_reports).")
    fields = {key: k.hesap("sayac", F_SAYAC, [base])}
    for rep in reports:
        fields[f"{key}[]:{rep['id']}"] = _plan_ref(k, rep, base, logo_db, crm_db)
    k.alanlar(fields)
    return k


def for_report(engine: Any, tenant: str, ds: str, user: Optional[str], rep: dict[str, Any],
               logo_db: Optional[str], crm_db: Optional[str]) -> P.Kaynaklar:
    """Tek plan cevabı (çalıştır): planın bütün rakamları kendi sorgusundan."""
    k = P.Kaynaklar()
    base = k.portal("portal.raporlar", "Planlı raporlar", R.list_stmt(tenant, ds, user), engine,
                    description="Planlar, zamanlamaları ve son çalışmaları (semantic_reports).")
    ref = _plan_ref(k, rep, base, logo_db, crm_db)
    k.alanlar({key: ref for key, v in rep.items() if P.numeric_paths({key: v})})
    return k


def for_preview(out: dict[str, Any], answer: dict[str, Any], logo_db: Optional[str],
                crm_db: Optional[str]) -> P.Kaynaklar:
    """Excel taslağı önizlemesi: cevabın fiziksel SQL'i (tamamı dosyaya aynı metinle yazılır)."""
    k = P.Kaynaklar(as_of=answer.get("computedAt"))
    q = SK.calisan(k, "onizleme", "Raporun sorusu", physical_sql=answer.get("physicalSql"), logo_db=logo_db,
                   crm_db=crm_db, rows=answer.get("totalRows"), ms=answer.get("dbMs"), ran_at=answer.get("computedAt"),
                   parts=answer.get("dbParts") if answer.get("federated") else None)
    ref = k.hesap("onizleme", F_ONIZLEME, [q])
    k.alanlar({key: ref for key, v in out.items() if P.numeric_paths({key: v})})
    return k
