"""Uyarılar: ekrandaki her rakamın sorgu bilgisi (ortak sözleşme `provenance.py`).

Kural bir sorudur; her kontrolde köprü soruyu çözüp Logo/CRM'de koşturur. «Son değer» o koşunun FİZİKSEL SQL'inden
gelir (`alerts._check` → `last_db_json.physicalSql`); beklenen aralık geçmiş 24 ayın gün gün okumasından
(`expected_json.fiziksel`). Eşik, durum ve sayaçlar kural tablosundan (semantic_alert_rules) okunur.
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

from semantic_bridge import alerts as A
from semantic_bridge import provenance as P
from semantic_bridge import soru_kaynak as SK

F_DEGER = ("Son değer = kuralın sorusunun son kontrolde koşan SQL'inin döndürdüğü tek sayı (kolon seçildiyse o kolon). "
           "Koşul ve eşik kuralda yazılıdır; «eşik aşıldı» = son değer koşulu sağlıyor. Sunucu etkin kuralları 15 "
           "dakikada bir kontrol eder.")
F_DEGER_YOK = (" Bu kuralın son ölçümü, çalışan SQL'i kaydetmeye başlamadan önce yapıldı; SQL bir sonraki kontrolde "
               "yazılır.")
F_ARALIK = ("Beklenen aralık = geçmiş 24 ayın aynı penceresindeki değerlerden (gün gün okuma), mevsim ayıklanarak "
            "medyan ± hassasiyet × yayılım; günde bir hesaplanır. Model kullanılmaz.")
F_SAYAC = ("Kural sayacı = sizin kurallarınızın sayısı; eşiği aşan = durumu «eşik aşıldı» olan etkin kurallar "
           "(menüdeki Uyarılar rozeti de bu sayıdır); ölçülemedi = son kontrolü hata veren kurallar.")
F_KONTROL = ("Kontrol özeti: kontrol edilen = ölçülen kural sayısı; eşiği aşan = son değeri koşulu sağlayan; bildirilen "
             "= e-postası giden; ölçülemedi = hata veren kurallar. Her kuralın değeri kendi sorgusundan.")


def range_sources(k: P.Kaynaklar, rng: Optional[dict[str, Any]], prefix: str, logo_db: Optional[str],
                  crm_db: Optional[str]) -> list[str]:
    """Beklenen aralığın geçmiş okumaları (fiziksel SQL); yoksa boş liste."""
    out = []
    for i, x in enumerate((rng or {}).get("fiziksel") or [], 1):
        if (x or {}).get("sql"):
            out.append(SK.calisan(k, f"{prefix}.gecmis{i}", "Beklenen aralık · gün gün geçmiş", physical_sql=x["sql"],
                                  logo_db=logo_db, crm_db=crm_db, rows=x.get("rows"), ms=x.get("ms"),
                                  ran_at=x.get("at"),
                                  description="Geçmiş 24 ayın gün gün değeri; aralık bu satırlardan hesaplanır."))
    return out


def _rule_refs(k: P.Kaynaklar, rule: dict[str, Any], base: str, logo_db: Optional[str], crm_db: Optional[str]) -> str:
    db = rule.get("last_db") or {}
    refs, text = [base], F_DEGER
    if db.get("physicalSql") or db.get("parts"):
        refs.append(SK.calisan(k, f"uyari.{rule['id']}", f"Kuralın sorusu · {str(rule.get('title') or '')[:80]}",
                               physical_sql=db.get("physicalSql"), parts=db.get("parts"), logo_db=logo_db,
                               crm_db=crm_db, rows=db.get("rows"), ms=db.get("dbMs"), ran_at=db.get("computedAt")))
    elif rule.get("last_value") is not None:
        text += F_DEGER_YOK
    hist = range_sources(k, rule.get("expected"), f"uyari.{rule['id']}", logo_db, crm_db)
    if hist:
        refs += hist
        text += " " + F_ARALIK
    return k.hesap(f"kural:{rule['id']}", text, refs)


def for_list(engine: Any, tenant: str, ds: str, owner: Optional[str], out: dict[str, Any],
             logo_db: Optional[str], crm_db: Optional[str]) -> P.Kaynaklar:
    k = P.Kaynaklar()
    base = k.portal("portal.uyari.kurallar", "Uyarı kuralları", A.list_stmt(tenant, ds, owner), engine,
                    rows=len(out.get("alerts") or []),
                    description="Kuralların soru, koşul, eşik, son değer ve durumları (semantic_alert_rules).")
    fields = {"alerts": k.hesap("sayac", F_SAYAC, [base])}
    for rule in out.get("alerts") or []:
        fields[f"alerts[]:{rule['id']}"] = _rule_refs(k, rule, base, logo_db, crm_db)
    k.alanlar(fields)
    return k


def for_check(engine: Any, tenant: str, ds: str, owner: Optional[str], out: dict[str, Any],
              logo_db: Optional[str], crm_db: Optional[str]) -> P.Kaynaklar:
    rules = A.list_rules(engine, tenant, ds, owner)
    k = for_list(engine, tenant, ds, owner, {"alerts": rules}, logo_db, crm_db)
    refs = ["portal.uyari.kurallar"] + [f"hesap:kural:{r['id']}" for r in rules]
    ref = k.hesap("kontrol", F_KONTROL, refs)
    k.alanlar({"checked": ref, "triggered": ref, "notified": ref, "errors": ref})
    return k


def for_suggest(out: dict[str, Any], logo_db: Optional[str], crm_db: Optional[str]) -> P.Kaynaklar:
    """Yeni kural formundaki eşik önerisi ve beklenen aralık."""
    k = P.Kaynaklar()
    hist = range_sources(k, out, "oneri", logo_db, crm_db)
    if not hist:
        raise P.ProvenanceError("Beklenen aralık hesaplanamadı; gösterilecek sorgu yok.")
    ref = k.hesap("oneri", F_ARALIK + " Öneri: «büyüktür» kuralında aralığın üstü, «küçüktür» kuralında altı.", hist)
    # Cevabın rakam taşıyan her anahtarı (alt, üst, merkez, değer, öneri, nokta sayısı…) bu hesaptan.
    k.alanlar({key: ref for key, v in out.items() if P.numeric_paths({key: v})})
    return k


#: Uyarı cevaplarında rakam olmayan sayılar (hassasiyet katsayısı kural ayarıdır ama eşik kolonunda durur → kapsanır).
NOT_RAKAM: Iterable[str] = ()
