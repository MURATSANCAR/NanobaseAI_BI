"""İş kararları 2026-09-20 — K3 (karşılıksız/protesto çek = OLAY okuması) ve K12 (stok devir hızı ≠ CRM satış hızı).

Kavram tanımları müşteri Logo veritabanında salt-okunur doğrulandı (bkz. KARAR.md). Betik ürünün kendi store
API'siyle yazar: `upsert_concept` (+ eşleme), `add_synonym`, `update_concept`, kanıt (`HUMAN_ANNOTATION`,
`EXECUTION`), kalıcılık için `EvidenceEngine.human_certify`; makine onayını `vocabulary.withdraw` geri çeker.

Ne yapar
  K3  «karşılıksız çıkan», «protesto olan/edilen/edildi» = bir OLAYDIR: çek hareketinde (CSTRANS) o duruma düşme
      satırı. İki yeni DIMENSION_VALUE kavramı CSTRANS.STATUS üzerine yazılır (devir satırları ve iptaller koşulla
      dışlanır: DEVIR = 0, CANCELLED = 0 — ikisi de kapının zorlayabildiği `=` biçiminde). Olay ifadeleri bugünkü
      GÜNCEL DURUM kavramlarından (LG_CSCARD.CURRSTAT) çıkarılır; sıfat biçimleri («karşılıksız çek», «protestolu»)
      güncel durum okumasında kalır. Yalın «protesto» da taşınır: çözücü «olan»ı yardımcı fiil sayıp düşürdüğü için
      «protesto olan» soruda «protesto» anahtarıyla okunuyor (ölçüldü); yalın ad işlemin kendisidir, «protestolu» durumdur. İki olay etiketi aynı kolonda olduğu için «veya» birleşimi çalışmaya devam eder.
  K12 «devir hızı» → CRM PRODUCTBASE.NEW_SATISHIZI makine onayı geri çekilir (satış hızı ≠ devir hızı); Logo
      tarafına tek ifadeli, sertifikalı METRIC «stok devir hızı» yazılır: satış adedi / ((açılış devri + güncel stok)/2).

Üç kip
  (varsayılan)            KURU KOŞU: ne yazılacağını basar, hiçbir şey yazmaz.
  --simulate dosya.jsonl… YAZMADAN ölçüm: değişiklik yalnız bellekteki dizine uygulanır (yeni kavramlar eklenir, taşınan
                          eş anlamlılar ve geri çekilen makine onayı dizinden çıkar); sorular köprüyle aynı kurulan
                          çözücüye önce/sonra okutulur, okuması değişenler basılır. (`soru:…` ile elle soru verilebilir.)
  --apply                 yazar (idempotent).

Sunucuda, köprünün ortamıyla (dosya kopyalamadan, stdin'den):
  sudo systemd-run --pipe --wait --collect --quiet -p User=administrator \
     -p EnvironmentFile=/etc/nanobase/semantic-bridge.env -p WorkingDirectory=/data/nanobaseai/bi/frontend/backend \
     -E PYTHONPATH=/data/nanobaseai/bi/frontend/backend /data/nanobaseai/bi/semantic-venv/bin/python - [--apply] < apply.py

Entity adları tarama kapsamına göre değişebildiği için (CSTRANS / LG_CSTRANS) adlar koşu anında tablo kalıbından
okunur; formül ve koşullar o adla kurulur. Kolon profilde yoksa kavram atlanır ve söylenir.
"""
from __future__ import annotations

import json
import sys

WHO = "operator:claude (iş kararı 2026-09-20)"
SRC = "operator:is-karari-2026-09-20"

#: K12 — geri çekilecek MAKİNE onayı (decided_by = otomatik-yoklama): (normalized, ENTITY, KOLON)
WITHDRAW = [("devir hizi", "PRODUCTBASE", "NEW_SATISHIZI")]
WITHDRAW_REASON = ("iş kararı 2026-09-20 (K12): devir hızı ≠ satış hızı. 'devir hızı' stok devir hızıdır (Logo: satış adedi / "
                   "ortalama stok); CRM PRODUCTBASE.NEW_SATISHIZI 'satış hızı'dır. Makine onayı Logo sorusunu CRM'e çekiyordu (Q12).")

#: K3 — olay ifadeleri bugün GÜNCEL DURUM kavramlarının eş anlamlısı; yeni olay kavramına taşınır.
#: (kalıp soneki, kolon, değer kümesi) → o kavramdan çıkarılacak eş anlamlılar (normalize edilerek karşılaştırılır)
MOVE = [
    (("CSCARD", "CURRSTAT", {"11"}), ["karşılıksız çıkan", "karşılıksız çıkan çek"]),
    (("CSCARD", "CURRSTAT", {"5", "7"}), ["protesto", "protesto olan", "protesto edilen", "protesto edildi"]),
]
MOVE_REASON = "iş kararı 2026-09-20 (K3): 'çıkan / olan / edilen' bir olaydır (CSTRANS), güncel durum (CURRSTAT) değil"


def turnover_formula(e: str) -> str:
    """Tek toplama ifadesi (kırılım = malzeme): satış adedi / ((açılış devri + güncel stok) / 2).
    Canlı LG_411'de altın referansla (üç alt sorgulu) ilk 20 kitapta 20/20 birebir (İYİLİK TİMİ 1,0935)."""
    sales = f"SUM(CASE WHEN {e}.TRCODE IN (7, 8, 9) THEN {e}.AMOUNT ELSE 0 END)"
    opening = f"SUM(CASE WHEN {e}.TRCODE = 14 THEN {e}.AMOUNT ELSE 0 END)"
    onhand = f"SUM(CASE WHEN {e}.IOCODE IN (1, 2) THEN {e}.AMOUNT WHEN {e}.IOCODE IN (3, 4) THEN -{e}.AMOUNT ELSE 0 END)"
    return f"{sales} / NULLIF(({opening} + {onhand}) / 2.0, 0)"


def definitions(entity_of, column_of, pattern_of) -> list[dict]:
    """entity_of(sonek) → entity adı | None; column_of(entity, kolon) → profildeki yazımı | None; pattern_of(entity) → kalıp."""
    out: list[dict] = []
    ct, st = entity_of("CSTRANS"), entity_of("STLINE")

    def need(entity, what, cols):
        if not entity:
            return f"profil yok: {what}"
        missing = [c for c in cols if not column_of(entity, c)]
        return f"{entity} profilinde kolon yok: {', '.join(missing)}" if missing else ""

    # ---- K3: olay okuması. DEVIR = 0 ⇔ TRCODE <> 0 (LG_411: 5.751 devir satırının hepsi TRCODE 0, 3.105 hareketin hepsi DEVIR 0);
    #      `TRCODE <> 0` kapının okuyabildiği bir biçim değil, `DEVIR = (0)` öyle.
    skip_ct = need(ct, "…_CSTRANS", ["STATUS", "DEVIR", "CANCELLED", "CSREF", "DATE_"])
    event = [f"{ct}.DEVIR = (0)", f"{ct}.CANCELLED = (0)"] if ct else []
    out.append(dict(
        key="karsiliksiz-cikan-cek", term="karşılıksız çıkan çek", type="DIMENSION_VALUE", entity=ct, pattern=pattern_of(ct),
        column="STATUS", operator="IN", values=["11"], skip=skip_ct, extra={"conditions": event},
        synonyms=["karşılıksız çıkan"],
        reason="iş kararı K3 (2026-09-20): 'karşılıksız çıkan' = dönem içinde karşılıksız işlemi görmüş çek (OLAY): CSTRANS.STATUS = 11, "
               "devir satırı değil (DEVIR = 0), iptal değil; dönem hareket tarihi CSTRANS.DATE_. Canlı LG_411, 2026: 6 müşteri çeki, "
               "6.326.658 ₺ (hepsi sonradan iade edilmiş, CURRSTAT 6 — güncel durum okuması bu yüzden 0 buluyordu). 2021–2025: 35 olay / 35 çek."))
    out.append(dict(
        key="protesto-edilen", term="protesto edilen", type="DIMENSION_VALUE", entity=ct, pattern=pattern_of(ct),
        column="STATUS", operator="IN", values=["5", "7"], skip=skip_ct, extra={"conditions": event},
        synonyms=["protesto", "protesto olan", "protesto edildi", "protesto edilen çek", "protesto edilen senet"],
        reason="iş kararı K3 (2026-09-20): 'protesto olan / edilen' = dönem içinde protesto işlemi görmüş çek/senet (OLAY): "
               "CSTRANS.STATUS IN (5, 7), DEVIR = 0, iptal değil. Canlı: 2026'da olay yok (0); 2021–2024'te 145 olay / 145 kayıt, hepsi müşteri "
               "SENEDİ (DOC 2). 01.01.2026 devir satırlarındaki 83 protestolu senet olay sayılmaz."))

    # ---- K12: stok devir hızı (configs/semantic/knowledge/logo/knowledge/metrics/logo-timas.md → «Stok devir hızı»)
    #      Durum ölçüsü bileşeni taşır (güncel stok = bütün hareketlerin bakiyesi): `state_measure` — varsayılan yıl
    #      eklenmez, güncel kopya tarihsiz okunur (kopya = yıl: 2026 kopyası devirle başlar, satışları 2026'nındır).
    skip_st = need(st, "…_STLINE", ["TRCODE", "IOCODE", "AMOUNT", "LINETYPE", "CANCELLED", "STOCKREF"])
    out.append(dict(
        key="stok-devir-hizi", term="stok devir hızı", type="METRIC", entity=st, pattern=pattern_of(st),
        formula=turnover_formula(st) if st else "", skip=skip_st,
        extra={"func": "RATIO", "grain": st, "aliases": ["stok_devir_hizi", "devir_hizi"], "state_measure": True,
               "conditions": [f"{st}.LINETYPE = (0)", f"{st}.CANCELLED = (0)"] if st else []},
        synonyms=["devir hızı", "stok devir oranı", "stok dönüş hızı"],
        reason="iş kararı K12 (2026-09-20): stok devir hızı = dönem satış adedi (TRCODE 7/8/9) / ortalama stok; ortalama stok = "
               "(dönem başı devir TRCODE 14 + güncel stok bakiyesi) / 2; LINETYPE 0, iptal hariç. Canlı LG_411: altın referansla "
               "20/20 kitapta birebir (İYİLİK TİMİ 148.662 / ((58.273 + 213.633)/2) = 1,0935). Dünkü 0,696 paydada açılış yerine "
               "güncel stoku iki kez almıştı (148.662 / 213.633). CRM NEW_SATISHIZI 'satış hızı'dır, devir hızı değildir."))
    return out


# ------------------------------------------------------------------------------------------------ ortak
def _open():
    from semantic_layer.catalog import one_entity_per_pattern
    from semantic_layer.config import SemanticSettings
    from semantic_layer.store.catalog_store import open_store
    s = SemanticSettings.from_env()
    store = open_store(s.store_dsn, create=False)
    profiles = one_entity_per_pattern(store.list_profiles(s.datasource_id), store.concept_entities(s.tenant_id, s.datasource_id))
    by_entity = {p.entity: p for p in profiles}

    def entity_of(suffix: str):
        """Yıl/firma kopyalı Logo tablosu: kalıbı `…_{sonek}` ile biten profil (LG_{n0}_{n1}_CSTRANS, DBO_LG_{n0}_{n1}_STLINE)."""
        hits = [p for p in profiles if p.table_pattern.upper().endswith("_" + suffix.upper()) and "{N0}" in p.table_pattern.upper()]
        hits.sort(key=lambda p: (not p.table_pattern.upper().startswith("DBO_"), len(p.table_pattern)))
        return hits[0].entity if hits else None

    def column_of(entity: str, column: str):
        p = by_entity.get(entity)
        if p is None:
            return None
        return next((c.name for c in p.columns if c.name.upper() == column.upper()), None)

    def pattern_of(entity):
        p = by_entity.get(entity)
        return p.table_pattern if p else None

    return s, store, profiles, definitions(entity_of, column_of, pattern_of)


def _mapping(d):
    from semantic_layer.models import Mapping
    return Mapping(concept_id="", entity=d["entity"], table_pattern=d["pattern"], column=d.get("column"),
                   operator=d.get("operator"), values=list(d.get("values") or []), formula=d.get("formula"), extra=dict(d.get("extra") or {}))


def _existing(store, s, d):
    from semantic_layer.normalize import normalize_term
    m = _mapping(d)
    for c in store.find_concepts(s.tenant_id, s.datasource_id, normalized_term=normalize_term(d["term"]), semantic_type=d["type"]):
        if any(x.key() == m.key() for x in store.list_mappings(c.id)):
            return c
    return None


def _collisions(store, s, d, moving: set[tuple[str, str]]):
    """Aynı anahtarı bugün taşıyan SERTİFİKALI kavramlar; bu betiğin taşıdığı/geri çektiği (anahtar, kavram) çiftleri ayrı işaretlenir."""
    from semantic_layer.normalize import normalize_term
    index = store.certified_index(s.tenant_id, s.datasource_id)
    hits = []
    for word in [d["term"], *d["synonyms"]]:
        k = normalize_term(word)
        for c, maps in index.get(k) or []:
            hits.append({"anahtar": k, "kavram": c.id, "terim": c.term, "tür": c.semantic_type,
                         "alan": [f"{m.entity}.{m.column or m.formula}" for m in maps][:2],
                         "bu_betik_kaldırıyor": (k, c.id) in moving})
    return hits


def _magnets(store, s, defs) -> dict[str, list[str]]:
    """Yeni anahtarlardaki kelimelerden bugün HİÇBİR sertifikalı anahtarda geçmeyenler (tek-kelime geri düşüşü bunlara tutunur)."""
    from semantic_layer.normalize import normalize_term
    known = {w for key in store.certified_index(s.tenant_id, s.datasource_id) for w in key.split()}
    out: dict[str, list[str]] = {}
    for d in defs:
        if d["skip"]:
            continue
        words = {w for t in [d["term"], *d["synonyms"]] for w in normalize_term(t).split()}
        out[d["term"]] = sorted(w for w in words if w not in known)
    return out


def move_rows(store, s) -> list[dict]:
    """Olay ifadesini bugün eş anlamlı olarak taşıyan GÜNCEL DURUM kavramları (kalıp soneki + kolon + değer kümesiyle bulunur)."""
    from semantic_layer.normalize import normalize_term
    out = []
    index = store.certified_index(s.tenant_id, s.datasource_id)
    for (suffix, column, values), words in MOVE:
        for w in words:
            k = normalize_term(w)
            for c, maps in index.get(k) or []:
                if c.normalized_term == k:
                    continue                                   # kavramın kendi adı: taşınmaz, söylenir
                if any(m.table_pattern.upper().endswith("_" + suffix) and (m.column or "").upper() == column
                       and {str(v) for v in m.values} == values for m in maps):
                    out.append({"anahtar": k, "kavram": c.id, "terim": c.term, "alan": f"{maps[0].entity}.{maps[0].column} IN {sorted(values)}",
                                "işlem": "eş anlamlıyı çıkar (olay kavramına taşındı)"})
    return out


def withdraw_rows(store) -> list[dict]:
    import sqlalchemy as sa
    out = []
    with store.engine.connect() as conn:
        for norm, entity, column in WITHDRAW:
            for r in conn.execute(sa.text("select id, term, normalized, entity, column_name, source, status, decided_by, concept_id "
                                          "from sl_vocabulary where normalized=:n and upper(entity)=:e and upper(column_name)=:c"),
                                  {"n": norm, "e": entity, "c": column}):
                out.append(dict(r._mapping))
    return out


def _withdrawable(r: dict) -> bool:
    return r["status"] == "APPROVED" and r["decided_by"] == "otomatik-yoklama"


def plan(store, s, defs) -> list[dict]:
    from semantic_layer.normalize import normalize_term
    rows = []
    magnets = _magnets(store, s, defs)
    moving = {(m["anahtar"], m["kavram"]) for m in move_rows(store, s)}
    moving |= {(r["normalized"], r["concept_id"]) for r in withdraw_rows(store) if _withdrawable(r)}
    for d in defs:
        if d["skip"]:
            rows.append({"kavram": d["term"], "işlem": "ATLA", "neden": d["skip"]})
            continue
        c = _existing(store, s, d)
        wanted = [normalize_term(x) for x in d["synonyms"]]
        if c is None:
            todo, missing = "YARAT + sertifikala", wanted
        else:
            missing = [x for x in wanted if x not in (c.synonyms or []) and x != c.normalized_term]
            certified = c.status == "CERTIFIED" and (c.explain or {}).get("human_certified_by")
            todo = "DEĞİŞİKLİK YOK" if certified and not missing else ("eş anlamlı ekle" if certified else "sertifikala" + (" + eş anlamlı ekle" if missing else ""))
        rows.append({"kavram": d["term"], "tür": d["type"], "anahtar": normalize_term(d["term"]), "işlem": todo,
                     "varolan": c.id if c else None, "entity": d["entity"], "kalıp": d["pattern"], "kolon": d.get("column"),
                     "operatör": d.get("operator"), "değerler": d.get("values"), "formül": d.get("formula"), "extra": d.get("extra") or {},
                     "eklenecek_eş_anlamlılar": missing,
                     "katalogda_yeni_kelimeler(tek_başına_bu_kavramı_çeker)": magnets.get(d["term"], []),
                     "aynı_anahtarı_taşıyan_sertifikalılar": [h for h in _collisions(store, s, d, moving) if h["kavram"] != (c.id if c else None)],
                     "gerekçe": d["reason"]})
    return rows


def apply_moves(store, s) -> list[dict]:
    """Olay ifadelerini güncel durum kavramlarından çıkar (kavramın kendisi, eşlemesi ve diğer adları yerinde kalır)."""
    from semantic_layer.models import Evidence, EvidenceType
    from semantic_layer.normalize import normalize_term
    done = []
    by_concept: dict[str, list[str]] = {}
    for m in move_rows(store, s):
        by_concept.setdefault(m["kavram"], []).append(m["anahtar"])
    for cid, keys in by_concept.items():
        c = store.get_concept(cid)
        explain = dict(c.explain or {})
        sources = {k: v for k, v in (explain.get("synonym_sources") or {}).items() if k not in keys}
        declared = [k for k in (explain.get("declared_synonyms") or []) if k not in keys]
        store.update_concept(cid, synonyms=[x for x in c.synonyms if normalize_term(x) not in keys],
                             explain={"synonym_sources": sources, "declared_synonyms": declared}, bump_version=True)
        store.add_evidence(Evidence(cid, EvidenceType.HUMAN_ANNOTATION, SRC + ":olay-ifadeleri-tasindi", support_count=1, weight=1.0,
                                    payload={"snippet": MOVE_REASON + ": " + ", ".join(keys), "by": WHO}))
        done.append({"kavram": cid, "çıkarılan": keys})
    return done


def apply(store, s, defs) -> list[dict]:
    from semantic_layer.evidence.engine import EvidenceEngine
    from semantic_layer.models import ConceptStatus, Evidence, EvidenceType
    from semantic_layer.normalize import normalize_term
    engine, done = EvidenceEngine(store), []
    for d in defs:
        if d["skip"]:
            done.append({"kavram": d["term"], "sonuç": "atlandı", "neden": d["skip"]})
            continue
        c, created = store.upsert_concept(s.tenant_id, s.datasource_id, d["term"], d["type"], mapping=_mapping(d),
                                          status=ConceptStatus.CANDIDATE)
        for syn in d["synonyms"]:
            store.add_synonym(c.id, syn)
        c = store.get_concept(c.id)
        sources = dict((c.explain or {}).get("synonym_sources") or {})
        for syn in d["synonyms"]:
            sources.setdefault(normalize_term(syn), {"by": WHO, "source": SRC})
        declared = sorted(set((c.explain or {}).get("declared_synonyms") or []) | {normalize_term(x) for x in d["synonyms"]})
        store.update_concept(c.id, explain={"synonym_sources": sources, "declared_synonyms": declared})
        if created:
            store.add_evidence(Evidence(c.id, EvidenceType.HUMAN_ANNOTATION, SRC, support_count=1, weight=1.0,
                                        payload={"snippet": d["reason"], "by": WHO}))
            store.add_evidence(Evidence(c.id, EvidenceType.EXECUTION, SRC + ":db-dogrulama",
                                        payload={"note": "tanım müşteri veritabanında salt-okunur sorgularla doğrulandı (KARAR.md)"}))
        if c.status != ConceptStatus.CERTIFIED or not (c.explain or {}).get("human_certified_by"):
            engine.human_certify(c.id, WHO, reason=d["reason"])
        done.append({"kavram": d["term"], "id": c.id, "sonuç": "yaratıldı" if created else "vardı; tamamlandı"})
    return done


# ------------------------------------------------------------------------------------------------ bellekte ölçüm
class _WithProposal:
    """Değişiklik YALNIZ bellekteki dizine uygulanır. Anlık görüntü yayını kapatılır: gerçek store'un
    `publish_runtime_snapshot`'ı kendisine verilen dizini sl_catalog_version'a YAZAR."""

    def __init__(self, store, s, defs):
        from semantic_layer.models import Concept
        from semantic_layer.normalize import normalize_term
        self._s, self._base, self._merged, self._extra = store, None, None, []
        self._drop = {(m["anahtar"], m["kavram"]) for m in move_rows(store, s)}
        self._drop |= {(r["normalized"], r["concept_id"]) for r in withdraw_rows(store) if _withdrawable(r)}
        for n, d in enumerate(x for x in defs if not x["skip"]):
            c = Concept(tenant_id=s.tenant_id, datasource_id=s.datasource_id, term=d["term"], normalized_term=normalize_term(d["term"]),
                        semantic_type=d["type"], status="CERTIFIED", confidence=1.0,
                        synonyms=[normalize_term(x) for x in d["synonyms"]], id=f"sem_oneri_{n:02d}",
                        explain={"human_certified_by": WHO})
            m = _mapping(d)
            m.concept_id = c.id
            self._extra.append((c, [m]))

    def __getattr__(self, name):
        return getattr(self._s, name)

    def publish_runtime_snapshot(self, tenant_id, datasource_id, index):
        return 0, "bellekte-olcum"

    def list_evidence(self, concept_id):
        return [] if str(concept_id).startswith("sem_oneri_") else self._s.list_evidence(concept_id)

    def certified_index(self, t, d):
        base = self._s.certified_index(t, d)
        if self._merged is None or self._base is not base:
            merged = {}
            for k, entries in base.items():
                kept = [(c, maps) for c, maps in entries if (k, c.id) not in self._drop]
                if kept:
                    merged[k] = kept
            for c, maps in self._extra:
                for k in dict.fromkeys([c.normalized_term, *c.synonyms]):
                    merged.setdefault(k, []).append((c, maps))
            self._base, self._merged = base, merged
        return self._merged


class _ReadOnly:
    def __init__(self, store):
        self._s = store

    def __getattr__(self, name):
        return getattr(self._s, name)

    def publish_runtime_snapshot(self, tenant_id, datasource_id, index):
        return 0, "bellekte-olcum"


def _reading(res, question):
    from semantic_layer.models import SemanticType
    q = res.resolve(question)
    slots = []
    for sl in list(q.slots) + [g for g in q.group_by if g not in q.slots]:
        m = sl.mapping
        if m is None or not m.entity or sl.semantic_type == SemanticType.DEFAULT_FILTER:
            continue
        how = (sl.explain or {}).get("source") or (sl.explain or {}).get("chosen_by") or ""
        what = m.column or (m.formula or "")[:40]
        if m.values:
            what += f" {m.operator} ({', '.join(map(str, m.values))})"
        slots.append(f"{sl.term} → {sl.semantic_type}:{m.entity}.{what}" + (f" [{sl.status}{' ' + how if how else ''}: {(sl.explain or {}).get('evidence_key', '')}]" if sl.status != "CERTIFIED" else ""))
    return {"slots": sorted(slots), "unresolved": sorted(q.unresolved), "hint": getattr(q, "source_hint", None),
            "state": getattr(q, "state", None), "temporal": [t.primitive for t in q.temporal]}


def resolvers(store, s, profiles, defs):
    from semantic_layer import coverage as coverage_mod
    from semantic_layer.conventions import Conventions
    from semantic_layer.runtime.resolver import SemanticResolver
    from semantic_bridge.app import _default_period, load_project_pairs
    conv = Conventions.from_profiles(profiles)
    if s.project_dir:
        conv.load_equivalences(s.project_dir / "equivalences.yml")
    coverage_mod.apply(profiles, store, s)
    pairs = load_project_pairs(s.project_dir) if s.project_dir else []
    mk = lambda st: SemanticResolver(st, s.tenant_id, s.datasource_id, profiles, default_temporal=_default_period(), conventions=conv, verified_pairs=pairs)
    return mk(_ReadOnly(store)), mk(_WithProposal(store, s, defs)), conv


def simulate(store, s, profiles, defs, files) -> None:
    before, after, _ = resolvers(store, s, profiles, defs)
    cases = [json.loads(l) for f in files if not f.startswith("soru:") for l in open(f, encoding="utf-8") if l.strip()]
    cases += [{"id": "elle", "soru": f[5:]} for f in files if f.startswith("soru:")]
    changed = 0
    for case in cases:
        a, b = _reading(before, case["soru"]), _reading(after, case["soru"])
        if a != b:
            changed += 1
            print(json.dumps({"id": case.get("id"), "kaynak": case.get("kaynak"), "soru": case["soru"], "önce": a, "sonra": b}, ensure_ascii=False), flush=True)
    print(json.dumps({"soru": len(cases), "okuması_değişen": changed}, ensure_ascii=False))


def main() -> int:
    s, store, profiles, defs = _open()
    if "--simulate" in sys.argv:
        files = [a for a in sys.argv[sys.argv.index("--simulate") + 1:] if not a.startswith("--")]
        simulate(store, s, profiles, defs, files)
        return 0
    rows = plan(store, s, defs)
    print(json.dumps({"kip": "UYGULA" if "--apply" in sys.argv else "KURU KOŞU (yazılmadı)", "who": WHO, "plan": rows}, ensure_ascii=False, indent=1, default=str))
    print(json.dumps({"taşınacak_olay_ifadeleri": move_rows(store, s), "gerekçe": MOVE_REASON}, ensure_ascii=False, indent=1, default=str))
    print(json.dumps({"geri_çekilecek_makine_onayları": [
        {**r, "işlem": "geri çek (PROPOSED)" if _withdrawable(r) else "DOKUNMA (kişi kararı ya da zaten geri çekilmiş)"}
        for r in withdraw_rows(store)], "gerekçe": WITHDRAW_REASON}, ensure_ascii=False, indent=1, default=str))
    if "--apply" in sys.argv:
        from semantic_layer import vocabulary
        # Önce kaldır, sonra yaz: aynı anahtar bir an bile iki sertifikalı kavramda durmasın.
        for r in withdraw_rows(store):
            if _withdrawable(r):
                print(json.dumps({"geri_çekildi": vocabulary.withdraw(store, s, r["id"], WITHDRAW_REASON)}, ensure_ascii=False, default=str))
        print(json.dumps({"taşındı": apply_moves(store, s)}, ensure_ascii=False, default=str))
        print(json.dumps({"yazıldı": apply(store, s, defs)}, ensure_ascii=False, indent=1))
        print("Köprü kataloğu en geç 30 sn içinde kendisi yeniden yükler (ensure_fresh); yeniden başlatma gerekmez.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
