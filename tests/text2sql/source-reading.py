"""Kaynak okuması ölçümü (yazmaz): `kaynak` etiketli her soru köprüyle aynı kurulan çözücüye süreç
içinde okutulur; soru başına hangi slot hangi veritabanına gitti ve slot makine onaylı bir sözlük
kelimesinden mi geldi, JSONL olarak basılır. Model yok, VPN yok.

    source-reading.py i/n [--hide-auto | --hide-single | --hide-rule] sorular.jsonl… > parça-i.jsonl

Bir sözlük kuralını kataloğa yazmadan önce sınamak için: `--hide-*` makine onaylı kelimeleri YALNIZ
bellekte gizler (hepsi / tek kelimelikler / `vocabulary_probe.not_for_a_machine`'in reddettikleri).
Köprü tek işçili olduğu için HTTP yerine süreç içi çözücü kullanılır (1.100 soru, 30 parça ≈ 2 dk;
30 parçadan fazlası ve eşzamanlı başka iş Postgres bağlantı sınırını doldurur). Sunucuda koşar:
systemd-run --property=EnvironmentFile=/etc/nanobase/semantic-bridge.env ile. Karşılaştırma:
source-reading-report.py. İlk kullanım 2026-09-19 (günlükte)."""
import json, sys, sqlalchemy as sa
from semantic_layer.catalog import one_entity_per_pattern
from semantic_layer.config import SemanticSettings
from semantic_layer.conventions import Conventions
from semantic_layer.normalize import normalize_term
from semantic_layer.runtime.resolver import SemanticResolver
from semantic_layer.store.catalog_store import open_store
from semantic_layer.models import SemanticType
from semantic_layer import coverage as coverage_mod
from semantic_bridge.app import _default_period, load_project_pairs

i, n = map(int, sys.argv[1].split("/"))
hide = "--hide-auto" in sys.argv or "--hide-single" in sys.argv or "--hide-rule" in sys.argv
by_rule = "--hide-rule" in sys.argv
single_only = "--hide-single" in sys.argv
files = [a for a in sys.argv[2:] if not a.startswith("--")]
s = SemanticSettings.from_env()
store = open_store(s.store_dsn, create=False)
with store.engine.connect() as c:
    auto = {(r[0], r[1]) for r in c.execute(sa.text("select concept_id, normalized from sl_vocabulary where status='APPROVED' and decided_by='otomatik-yoklama'"))}
autoc = {k[0] for k in auto}
autokeys = {}
if by_rule:
    from semantic_layer import vocabulary_probe as P
    _profiles = one_entity_per_pattern(store.list_profiles(s.datasource_id), store.concept_entities(s.tenant_id, s.datasource_id))
    with store.engine.connect() as c:
        _rows = [dict(r._mapping) for r in c.execute(sa.text("select * from sl_vocabulary where status='APPROVED' and decided_by='otomatik-yoklama'"))]
    for r in _rows:
        if P.not_for_a_machine({**r, "generator_note": None}, _profiles):
            autokeys.setdefault(r["normalized"], set()).add(r["concept_id"])
for cid, norm in ([] if by_rule else auto):
    if single_only and len(norm.split()) > 1: continue
    autokeys.setdefault(norm, set()).add(cid)

class Hidden:
    """Makine onaylı kelime anahtarları dizinden çıkar; kavramın kendi adı ve diğer eş anlamlıları kalır."""
    def __init__(self, st): self._s, self._v, self._m = st, None, None
    def __getattr__(self, name): return getattr(self._s, name)
    def certified_index(self, t, d):
        base = self._s.certified_index(t, d)
        if self._m is None or self._v is not base:
            m = {}
            for k, entries in base.items():
                drop = autokeys.get(k) or set()
                kept = [(c, maps) for c, maps in entries if not (c.id in drop and c.normalized_term != k)]
                if kept: m[k] = kept
            self._v, self._m = base, m
        return self._m

st = Hidden(store) if hide else store
profiles = one_entity_per_pattern(store.list_profiles(s.datasource_id), store.concept_entities(s.tenant_id, s.datasource_id))
conv = Conventions.from_profiles(profiles)
if s.project_dir: conv.load_equivalences(s.project_dir / "equivalences.yml")
coverage_mod.apply(profiles, store, s)
pairs = load_project_pairs(s.project_dir) if s.project_dir else []
res = SemanticResolver(st, s.tenant_id, s.datasource_id, profiles, default_temporal=_default_period(), conventions=conv, verified_pairs=pairs)
cases = [json.loads(l) for f in files for l in open(f) if l.strip()]
for k, case in enumerate(cases):
    if k % n != i: continue
    try:
        q = res.resolve(case["soru"])
    except Exception as ex:
        print(json.dumps({"id": case["id"], "kaynak": case.get("kaynak"), "soru": case["soru"], "error": str(ex)}, ensure_ascii=False), flush=True); continue
    slots = []
    for sl in list(q.slots) + list(q.group_by):
        m = sl.mapping
        if m is None or not m.entity or sl.semantic_type == SemanticType.DEFAULT_FILTER: continue
        cid = sl.concept_id or ""
        slots.append({"term": sl.term, "type": sl.semantic_type, "field": f"{m.entity}.{m.column or ''}",
                      "src": "crm" if res._source_of(m.entity) else "logo", "words": sl.span[1] - sl.span[0],
                      "autoTerm": (cid, normalize_term(sl.term or "")) in auto, "autoConcept": cid in autoc})
    print(json.dumps({"id": case["id"], "kaynak": case.get("kaynak"), "soru": case["soru"], "hint": getattr(q, "source_hint", None),
                      "slots": slots, "unresolved": list(q.unresolved)}, ensure_ascii=False), flush=True)
