"""CRM varlık ve alanlarının Türkçe görünen adları — CRM'in kendi meta verisinden (kullanıcı isteği 2026-09-29).

Ekranda ham CRM adı (`new_HaberMecrasName`, `new_kitapBase`) kuralla bölününce Türkçe harfi atılmış şema adı yanlış
çıkıyordu («Haber mecras ad»). Doğru ad CRM'de zaten var: CRM kişinin formda gördüğü etiketi `MetadataSchema`
şemasında tutar (`LocalizedLabel`, 1055 Türkçe; yoksa 1033). Bu modül o etiketleri okur; ön yüz (`readableName`)
kuraldan önce buna bakar. Veri değil şema okunur; CRM'e yazma yoktur.

- Anahtar mantıksal ad (küçük harf). Aynı alan adı birden çok varlıkta farklı etiketle geçebilir: en sık etiket
  genel anahtara, her biri ayrıca `varlık.alan` anahtarına yazılır.
- Katmanlı çözüm kaydında (yönetilen çözümler) aynı bileşenin birden çok satırı olabilir: etkin satır
  `OverwriteTime = 1900-01-01` olandır.
- Bağlantı (lookup) alanının CRM'in kendiliğinden eklediği «…name» eşinin çoğunda etiket yoktur
  (`new_habermecrasiname`); ön yüz sonu atıp bağlantı alanının etiketini kullanır.
- Harita 6 saatte bir tazelenir; CRM okunamazsa son harita kalır, hiç yoksa boş döner (ön yüz kurala düşer).
"""
from __future__ import annotations

import logging
import re
import threading
import time
from collections import Counter, defaultdict
from typing import Any, Callable, Optional

log = logging.getLogger("semantic.crm_names")

TTL = 6 * 3600
LANGS = (1055, 1033)          # Türkçe, yoksa İngilizce

ENTITY_SQL = """
SELECT e.LogicalName AS ad, l.Label AS etiket, l.LanguageId AS dil
FROM MetadataSchema.Entity e
JOIN MetadataSchema.LocalizedLabel l ON l.ObjectId = e.EntityId AND l.ObjectColumnName = 'LocalizedName'
WHERE e.OverwriteTime = '1900-01-01' AND l.OverwriteTime = '1900-01-01' AND l.LanguageId IN (1055, 1033)
""".strip()

ATTRIBUTE_SQL = """
SELECT e.LogicalName AS varlik, a.LogicalName AS ad, l.Label AS etiket, l.LanguageId AS dil
FROM MetadataSchema.Attribute a
JOIN MetadataSchema.Entity e ON e.EntityId = a.EntityId AND e.OverwriteTime = '1900-01-01'
JOIN MetadataSchema.LocalizedLabel l ON l.ObjectId = a.AttributeId AND l.ObjectColumnName = 'DisplayName'
WHERE a.OverwriteTime = '1900-01-01' AND l.OverwriteTime = '1900-01-01' AND l.LanguageId IN (1055, 1033)
""".strip()


def _clean(label: Any) -> str:
    return " ".join(str(label or "").split())


_PREFIXED = re.compile(r"^[a-z][a-z0-9]{1,7}_")


def build(entity_rows: list[dict[str, Any]], attribute_rows: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    """Satırlar → {"entities": {ad: etiket}, "attributes": {ad: etiket, "varlık.ad": etiket}}. Türkçe etiket önce gelir.
    Alanlardan yalnız önekli olanlar (`new_`, `obs_`, `address1_`…) gönderilir: ekran yalnız onları CRM adı sayar
    (bütün harita 390 KB, önekliler 186 KB — 2026-09-29 ölçümü)."""
    attribute_rows = [r for r in attribute_rows if _PREFIXED.match(str(r.get("ad") or "").lower())]

    def pick(rows: list[dict[str, Any]], key: Callable[[dict[str, Any]], str]) -> dict[str, str]:
        best: dict[str, tuple[int, str]] = {}
        for r in rows:
            k, lab = key(r), _clean(r.get("etiket"))
            if not k or not lab:
                continue
            rank = LANGS.index(int(r.get("dil") or 0)) if int(r.get("dil") or 0) in LANGS else len(LANGS)
            if k not in best or rank < best[k][0]:
                best[k] = (rank, lab)
        return {k: v for k, (_, v) in best.items()}

    entities = pick(entity_rows, lambda r: str(r.get("ad") or "").lower())
    qualified = pick(attribute_rows, lambda r: f"{str(r.get('varlik') or '').lower()}.{str(r.get('ad') or '').lower()}")
    # Genel anahtar: alanın bütün varlıklardaki (dil seçilmiş) etiketlerinden en sık olanı; eşitlikte kısa olan.
    votes: dict[str, Counter] = defaultdict(Counter)
    for q, lab in qualified.items():
        votes[q.split(".", 1)[1]][lab] += 1
    attributes = {a: sorted(c.items(), key=lambda kv: (-kv[1], len(kv[0]), kv[0]))[0][0] for a, c in votes.items()}
    attributes.update({q: lab for q, lab in qualified.items() if lab != attributes.get(q.split(".", 1)[1])})
    return {"entities": entities, "attributes": attributes}


class CrmNames:
    """Bellekte tutulan harita; ilk istek okur, sonra `TTL` dolunca arkada tazelenir."""

    def __init__(self, run: Callable[[str], list[dict[str, Any]]]):
        self._run = run
        self._lock = threading.Lock()
        self._data: Optional[dict[str, Any]] = None
        self._at = 0.0
        self._busy = False

    def _load(self) -> None:
        try:
            data = build(self._run(ENTITY_SQL), self._run(ATTRIBUTE_SQL))
            with self._lock:
                self._data = {**data, "version": str(int(time.time()))}
                self._at = time.time()
            log.info("crm adları: %d varlık, %d alan", len(data["entities"]), len(data["attributes"]))
        except Exception as e:  # noqa: BLE001 — CRM kapalıysa ekran kurala düşer
            log.warning("crm adları okunamadı: %s", str(e)[:300])
            with self._lock:
                self._at = time.time() - TTL + 600      # 10 dk sonra yeniden dene
        finally:
            with self._lock:
                self._busy = False

    def get(self) -> dict[str, Any]:
        with self._lock:
            fresh = self._data is not None and time.time() - self._at < TTL
            first = self._data is None and not self._busy and time.time() - self._at >= TTL
            stale = self._data is not None and not fresh and not self._busy
            if first or stale:
                self._busy = True
        if first:
            self._load()
        elif stale:
            threading.Thread(target=self._load, name="crm-names", daemon=True).start()
        with self._lock:
            return self._data or {"entities": {}, "attributes": {}, "version": "0"}
