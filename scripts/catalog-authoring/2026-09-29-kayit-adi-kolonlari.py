"""Kaydın ADI olan kolonları işaretler (`record_label`) — tam kapı 2026-09-29, sınıf K5 (C015 / Q11).

Sorun: «iade oranı en yüksek müşteriler» müşteri ADINA göre gruplanıyor; canlıda aynı adı taşıyan iki cari tek
satır oldu (2.401 / 2.402) ve ikisinin sevk ve iadesi tek oranda toplandı. İş kararı (bilgi belgesi C015): kart
bazında anahtarla grupla. Derleyici (compiler.DeterministicCompiler._card_keys) bir kırılım kolonunun eşlemesinde
`record_label: true` görürse kartın anahtarını (olgudan karta giden ilişkinin hedef kolonu) GROUP BY'a ekler; model
istemi de o kolonu «kaydın adı; anahtarıyla birlikte grupla» diye gösterir.

Neden işaret, neden tahmin değil: aynı kolon tipi hem kaydın adı (CLCARD.DEFINITION_) hem bir nitelik
(«şehir», «segment», «tür metni») olabilir. Niteliğe göre kırılımda anahtar eklemek cevabı kart kart böler. Hangi
kolonun kaydın adı olduğunu katalog zaten söylüyor: KAYDI ANAN kelime (varlık sözlüğü, `entity_terms`: «müşteri»
→ CLCARD) aynı zamanda o kolonun COLUMN kavramının adı ya da eş anlamlısıysa, kolon o kaydın adıdır. Ek şartlar,
profilden: metin tipi, sayılabilir küçük bir kod kümesi değil (enum değil), birincil anahtar ya da gizli değil.

  kuru koşu (varsayılan): adayları ve elenenleri basar, yazmaz.
  --apply              adayların eşlemesine `record_label: true` yazar (idempotent), kanıt notu ekler, `semantic_audit`.
  --only terim,terim   yalnız bu kavram terimleri (normalleştirilmiş ya da yazıldığı gibi).
  --exclude terim,…    bunları atla.

Koşu (sunucuda, köprünün ortamıyla):

    sudo systemd-run --pipe --wait --collect -p User=administrator \\
      -p EnvironmentFile=/etc/nanobase/semantic-bridge.env \\
      -E PYTHONPATH=/data/nanobaseai/bi/frontend/backend \\
      /data/nanobaseai/bi/semantic-venv/bin/python - [--apply] < betik.py

Sonra: köprü kataloğu 60 sn içinde tazeler → resolver-gate (okuma değişmemeli; yalnız eşleme ek alanı) →
answer-gate --only Q11,Q29,Q43 → tam kapı.
"""
from __future__ import annotations

import argparse
import dataclasses
import os
import sys

for p in ("/data/nanobaseai/bi/frontend/backend", os.environ.get("PYTHONPATH", "")):   # PYTHONPATH en önde
    if p:
        while p in sys.path:
            sys.path.remove(p)
        sys.path.insert(0, p)

from semantic_layer.config import SemanticSettings  # noqa: E402
from semantic_layer.models import Evidence, EvidenceType, SemanticType  # noqa: E402
from semantic_layer.normalize import normalize_term  # noqa: E402
from semantic_layer.store.catalog_store import open_store  # noqa: E402

WHO = "operator:claude (tam kapı 2026-09-29, iş kararı C015)"
_TEXT = ("char", "varchar", "nvarchar", "nchar", "text", "ntext", "string")


def _bare(entity: str) -> str:
    e = (entity or "").upper()
    return e[3:] if e.startswith("LG_") else e


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--only", default="")
    ap.add_argument("--exclude", default="")
    a = ap.parse_args()
    only = {normalize_term(x) for x in a.only.split(",") if x.strip()}
    exclude = {normalize_term(x) for x in a.exclude.split(",") if x.strip()}

    s = SemanticSettings.from_env()
    st = open_store(os.environ["SEMANTIC_STORE_DSN"], create=False)
    index = st.certified_index(s.tenant_id, s.datasource_id)
    words_of: dict[str, set[str]] = {}
    for ent, terms in st.entity_terms(s.tenant_id, s.datasource_id).items():
        words_of.setdefault(_bare(ent), set()).update(normalize_term(t) for t in terms)
    profiles: dict[str, object] = {}
    for p in st.list_profiles(s.datasource_id):
        profiles.setdefault(p.entity.upper(), p)
        profiles.setdefault(_bare(p.entity), p)

    seen: set[str] = set()
    picked: list[tuple] = []
    dropped: dict[str, int] = {}

    def drop(why: str) -> None:
        dropped[why] = dropped.get(why, 0) + 1

    for _, senses in index.items():
        for c, maps in senses:
            if c.semantic_type != SemanticType.COLUMN or c.id in seen:
                continue
            seen.add(c.id)
            names = {c.normalized_term, *(normalize_term(x) for x in (c.synonyms or []) if x)}
            if (only and not names & only) or names & exclude:
                continue
            for m in maps:
                if not m.column or m.values or m.formula:
                    drop("kolon eşlemesi değil")
                    continue
                prof = profiles.get(m.entity.upper()) or profiles.get(_bare(m.entity))
                col = prof.column(m.column) if prof is not None else None
                if col is None:
                    drop("profilde kolon yok")
                    continue
                if col.is_primary_key or col.sensitive:
                    drop("anahtar ya da gizli kolon")
                    continue
                if not str(col.data_type or "").lower().startswith(_TEXT):
                    drop("metin değil")
                    continue
                if col.is_enum():
                    drop("kod kümesi (nitelik)")
                    continue
                named_by = names & words_of.get(_bare(m.entity), set())
                if not named_by:
                    drop("kayıt adıyla anılmıyor (nitelik)")
                    continue
                if (m.extra or {}).get("record_label"):
                    drop("zaten işaretli")
                    continue
                picked.append((c, m, sorted(named_by)))

    print(f"katalog: {s.tenant_id}/{s.datasource_id} · COLUMN kavramı {len(seen)} · aday {len(picked)}")
    for c, m, named_by in picked:
        print(f"  ADAY  {c.id}  '{c.term}' → {m.entity}.{m.column}  (kaydı anan kelime: {', '.join(named_by)})")
    for why, n in sorted(dropped.items(), key=lambda x: -x[1]):
        print(f"  elendi: {why}: {n}")
    if not a.apply:
        print("KURU KOŞU — yazılmadı. Listeyi okuyun; yanlış aday varsa --exclude ile çıkarın, sonra --apply.")
        return 0

    for c, m, named_by in picked:
        new = [dataclasses.replace(x, extra={**(x.extra or {}), "record_label": True})
               if (x.entity, (x.column or "").upper()) == (m.entity, (m.column or "").upper()) else x
               for x in st.list_mappings(c.id)]
        st.replace_mappings(c.id, new)
        st.add_evidence(Evidence(c.id, EvidenceType.HUMAN_ANNOTATION, "operator:2026-09-29:kayit-adi", support_count=1,
                                 weight=1.0, payload={"snippet": f"{m.entity}.{m.column} kaydın adıdır ('{', '.join(named_by)}' "
                                                                 f"kaydı anar); kırılımda kart anahtarıyla gruplanır (C015)",
                                                      "by": WHO}))
        print("YAZILDI:", c.id, c.term, f"{m.entity}.{m.column}")
    try:
        from semantic_bridge import admin

        admin.audit(st.engine, "operator:claude", "update", "catalog_concept", s.datasource_id,
                    f"kaydın adı olan kolonlar işaretlendi ({len(picked)})",
                    {"concepts": [c.id for c, _, _ in picked], "flag": "record_label", "rule": "entity_terms ∩ COLUMN adı"})
    except Exception as e:  # noqa: BLE001
        print("UYARI: değişiklik kaydı yazılamadı:", e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
