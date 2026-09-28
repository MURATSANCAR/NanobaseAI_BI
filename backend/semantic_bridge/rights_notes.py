"""Ortak hak açıklaması sınıflaması: CRM Telif Alış sözleşmesinin serbest metinli `new_haklaraciklama` alanı.

Aynı alan önceden iki modülde ayrı ayrı modele soruluyordu: M54 telif «hangi kısıt» (bölge/format/süre/onay/ücret/diğer)
ve M36 dijital «dijitali kısıtlıyor mu». Çift maliyet ve çelişen sonuç (biri «format kısıtı», öbürü «kısıtlamıyor")
çıkıyordu. Artık **tek soru, tek tablo**:

- Tablo: `semantic_royalty_notes` (`royalty.NOTES`), anahtar (kiracı, sözleşme kimliği küçük harf, süslü parantezsiz).
  Metin özeti (`metin_hash`) saklanır; **metin değişince yeniden sorulur**, değişmedikçe hiçbir modül yeniden sormaz.
  İnsan onayı (`onayli`, telif ekranı) aynı satırdadır; iki modül de onu okur.
- Soru: telifin kapalı küme sorusu (`royalty.note_prompt`, `royalty.NOTE_CLASSES`), yalnız LLM kapısının `choose`
  ucuyla (olasılık + marj). Eşik altı «incele».
- Metin: iki modül de aynı biçimde temizler (`canonical`: HTML etiketi/varlığı ve boşluk), yoksa aynı not iki özetle
  saklanıp modüller birbirinin sonucunu geçersiz sayardı.
- Dijital okuma bu sınıftan türetilir (`digital_effect`): bölge/format/süre/onay → «dijitali kısıtlıyor», diğer →
  «kısıtlamıyor», ücret şartı ya da eşik altı → «belirsiz» (dağıtımı yasaklamaz ama telif birimi bakmalı; sessizce
  «kısıtlamıyor» denmez). Karar yine telif birimindedir; bu yalnız sıralama ve ön okumadır.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Callable, Iterable, Optional

import sqlalchemy as sa

from semantic_bridge import royalty as RY
from semantic_bridge.seo_geo import crm as seo_crm

log = logging.getLogger("semantic.rights_notes")

#: llm-choose belgesinin «öneri» eşiği (olasılık, marj); altı «incele».
THRESHOLDS = (0.70, 0.30)
DIGITAL_RESTRICTS = frozenset({"bolge", "format", "sure", "onay"})
DIGITAL_CLEAR = frozenset({"diger"})


def canonical(text: Any) -> str:
    """İki modülün de hash'lediği ve modele verdiği tek metin biçimi."""
    return seo_crm.clean(text) or ""


def key(contract_id: Any) -> str:
    return str(contract_id or "").strip().strip("{}").lower()


def pending(engine: sa.engine.Engine, tenant: str, rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sorulacaklar: yeni ya da metni değişmiş notlar. `rows`: {id, no, kitap, metin} (CRM satırı biçimi)."""
    clean = []
    seen: set[str] = set()
    for r in rows:
        k, text = key(r.get("id")), canonical(r.get("metin"))
        if not k or not text or k in seen:
            continue
        seen.add(k)
        clean.append({"id": k, "no": r.get("no"), "kitap": r.get("kitap"), "metin": text})
    return RY.pending_notes(engine, tenant, clean)


def classify(engine: sa.engine.Engine, tenant: str, items: list[dict[str, Any]], llm: Any, *,
             budget_sec: Optional[float] = None, stop_on_error: bool = False,
             progress: Optional[Callable[[bool], None]] = None) -> dict[str, Any]:
    """`pending` çıktısını kapalı küme seçimle sınıflar ve ortak tabloya yazar. Süre bütçesi biterse kalan sonraki
    koşuya kalır (sessiz tavan değil: kalan sayısı döner)."""
    labels = list(RY.NOTE_CLASSES.values())
    back = {v: k for k, v in RY.NOTE_CLASSES.items()}
    t0, done, failed = time.monotonic(), 0, 0
    for it in items:
        if budget_sec is not None and time.monotonic() - t0 > budget_sec:
            break
        try:
            ch = llm.choose(RY.note_prompt(it["text"]), labels)
        except Exception as e:  # noqa: BLE001 — model yoksa kalan sonraki denemeye
            log.warning("hak açıklaması sınıflanamadı: %s", e)
            failed += 1
            if progress:
                progress(False)
            if stop_on_error:
                break
            continue
        RY.save_note(engine, tenant, it, {"class": back.get(ch.choice or ""), "probability": ch.probability,
                                          "margin": getattr(ch, "margin", None), "method": getattr(ch, "method", None)},
                     THRESHOLDS)
        done += 1
        if progress:
            progress(True)
    return {"okunan": done, "kalan": len(items) - done, "hata": failed}


def digital_effect(cls: Optional[str], status: Optional[str]) -> Optional[str]:
    """Ortak sınıftan M36'nın «kisitliyor / kisitlamiyor / belirsiz» okuması. İnsan onayı eşikten bağımsız geçerlidir."""
    if not cls:
        return None
    if status == "incele":
        return "belirsiz"
    if cls in DIGITAL_RESTRICTS:
        return "kisitliyor"
    if cls in DIGITAL_CLEAR:
        return "kisitlamiyor"
    return "belirsiz"


def reads(engine: sa.engine.Engine, tenant: str) -> dict[str, dict[str, Any]]:
    """Kiracının bütün sınıflanmış notları: anahtar → {metin, sinif, olasilik, durum, dijital}."""
    RY.ensure(engine)
    n = RY.NOTES.c
    with engine.connect() as c:
        rows = c.execute(sa.select(n.contract_key, n.metin, n.sinif, n.olasilik, n.durum).where(n.tenant_id == tenant)).all()
    return {r.contract_key: {"metin": r.metin, "sinif": r.sinif, "olasilik": r.olasilik, "durum": r.durum,
                             "dijital": digital_effect(r.sinif, r.durum)} for r in rows}
