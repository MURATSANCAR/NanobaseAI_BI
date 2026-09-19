"""h4 — katalog sözlük boşluğu: iş istasyonu süreleri (Logo üretim) ve hedef dağılım dengesizliği (CRM).

Kavram tanımları gerçek veritabanında doğrulandı (bkz. ONERI.md). Bu betik ürünün kendi store API'siyle
yazar: `upsert_concept` (+ eşleme), `add_synonym`, kanıt (`HUMAN_ANNOTATION`, `EXECUTION`) ve kalıcılık için
`EvidenceEngine.human_certify` — gece motoru insan kararını geri almaz.

`--withdraw-generic`: iki MAKİNE onaylı genel öbeği («gerçekleşen süre», «planlanan süre» → CRM plan sorumluları)
ürünün `vocabulary.withdraw` akışıyla geri çeker (İŞ KARARI; varsayılan kapalı).

Üç kip (hepsine `--include-optional` eklenebilir: «süre sapması» gibi İŞ KARARI bekleyen eş anlamlılar da girer):
  (varsayılan)            KURU KOŞU: ne yazılacağını basar, hiçbir şey yazmaz.
  --simulate dosya.jsonl… YAZMADAN ölçüm: kavramlar yalnız bellekteki dizine eklenir, sorular köprüyle aynı
                          kurulan çözücüye önce/sonra okutulur, okuması değişen sorular basılır.
  --apply                 yazar (idempotent: aynı terim+tür+eşleme varsa yeniden yaratmaz, eksik eş anlamlıyı ekler).

Sunucuda, köprünün ortamıyla (dosya kopyalamadan, stdin'den):
  sudo systemd-run --pipe --wait --collect --quiet -p User=administrator \
     -p EnvironmentFile=/etc/nanobase/semantic-bridge.env -p WorkingDirectory=/data/nanobaseai/bi/frontend/backend \
     -E PYTHONPATH=/data/nanobaseai/bi/frontend/backend /data/nanobaseai/bi/semantic-venv/bin/python - [--apply] < apply.py

Entity adları tarama kapsamına göre değişebildiği için (ITEMS / LG_ITEMS) adlar koşu anında tablo
kalıbından okunur; formüller o adla kurulur. Kolonlar profilde yoksa kavram atlanır ve söylenir.
"""
from __future__ import annotations

import json
import sys

WHO = "operator:claude (iş teyidi bekliyor)"
SRC = "operator:h4-katalog-boslugu"

#: `--withdraw-generic` ile geri çekilecek MAKİNE onaylı genel öbekler (decided_by = otomatik-yoklama): iki kaynakta
#: da geçerli sıradan bir öbek tek bir CRM kolonuna bağlanmış, Logo üretim sorusunu CRM'e çekiyor. Ürünün kendi
#: `vocabulary.withdraw` akışı kullanılır: satır PROPOSED'a döner, karar bir kişiye kalır; kişi yazdıysa reddedilir.
WITHDRAW = [("gerceklesen sure", "NEW_PLANSORUMLULARIBASE", "NEW_TAMAMLANANISSURESI"),
            ("planlanan sure", "NEW_PLANSORUMLULARIBASE", "NEW_TOPLAMSURESI")]
WITHDRAW_REASON = ("genel öbek iki kaynakta da geçerli (Logo üretim DISPLINE.ACTDURATION/PLNDURATION de 'gerçekleşen/planlanan "
                   "süre'dir); makine onayı Logo sorusunu CRM'e çekti (C011). Karar bir kişinin.")

MONTHS = ["new_ocak", "new_subat", "new_Mart", "new_Nisan", "new_mayis", "new_Haziran",
          "new_Temmuz", "new_agustos", "new_eylul", "new_Ekim", "new_kasim", "new_aralik"]


def cv_formula(e: str, cols: list[str]) -> str:
    """12 sütunun değişim katsayısı, CROSS APPLY olmadan tek bir toplama ifadesi olarak (kırılım = ürün):
    ort = ΣS/12, örneklem varyansı = (ΣS² − (ΣS)²/12)/11, CV = √var / ort;  S = ay sütununun grup toplamı.
    Canlı veride STDEV/AVG referansıyla 3.429/3.429 üründe birebir (en büyük fark 0,0)."""
    s = [f"SUM(ISNULL(CAST({e}.{c} AS FLOAT), 0))" for c in cols]
    total = "(" + " + ".join(s) + ")"
    squares = "(" + " + ".join(f"POWER({x}, 2)" for x in s) + ")"
    return f"SQRT(({squares} - POWER({total}, 2) / 12.0) / 11.0) / NULLIF({total} / 12.0, 0)"


def definitions(entity_of, column_of) -> list[dict]:
    """entity_of(kalıp) → entity adı | None; column_of(entity, kolon) → profildeki yazımı | None."""
    out: list[dict] = []
    ws, dl, sh = entity_of("LG_{n0}_WORKSTAT"), entity_of("LG_{n0}_DISPLINE"), entity_of("NEW_SATISHEDEFLERIBASE")

    def need(entity, pattern, cols):
        if not entity:
            return f"profil yok: {pattern}"
        missing = [c for c in cols if not column_of(entity, c)]
        return f"{entity} profilinde kolon yok: {', '.join(missing)}" if missing else ""

    # ---- Q10: iş istasyonu (WORKSTAT) — «masraf merkezi → EMCENTER.DEFINITION_» ile aynı kalıp
    out.append(dict(
        key="is-istasyonu", term="iş istasyonu", type="COLUMN", entity=ws, pattern="LG_{n0}_WORKSTAT",
        column="NAME", operator="COLUMN", skip=need(ws, "LG_{n0}_WORKSTAT", ["NAME", "CODE", "LOGICALREF"]),
        synonyms=["iş istasyonları", "iş istasyonu adı", "üretim istasyonu"],
        reason="tanım: iş istasyonu = Logo üretim WORKSTAT kartı (ad NAME, kod CODE); operasyon satırına "
               "DISPLINE.WSREF = WORKSTAT.LOGICALREF ile bağlanır. Canlı (LG_411): 56 kart (42 aktif), 2026'da 21'i "
               "kullanılmış, yetim WSREF 0. İş teyidi bekliyor."))
    out.append(dict(
        key="is-istasyonu-kodu", term="iş istasyonu kodu", type="COLUMN", entity=ws, pattern="LG_{n0}_WORKSTAT",
        column="CODE", operator="COLUMN", skip=need(ws, "LG_{n0}_WORKSTAT", ["CODE"]), synonyms=[],
        reason="tanım: iş istasyonu kodu = WORKSTAT.CODE. İş teyidi bekliyor."))

    # ---- Q10: operasyon süreleri (DISPLINE). Birim DAKİKA (RUNTIME 65536 = Logo saat kodlamasında 1 dk;
    #      1.221/1.221 satırda PLNDURATION = planlanan adet × 1 dk). Formül ham birimi toplar; saate çevirme
    #      cevabın işi (÷60) — birim varsayımı formüle gömülmez.
    #      Adlar bilerek «operasyon …» / «iş istasyonu …» ile başlar: çözücünün fiil köprüsü bir ölçü anahtarının
    #      İLK kelimesine, tek-kelime geri düşüşü anahtardaki NADİR kelimeye tutunur. «planlanan …», «gerçekleşen …»,
    #      «üretim …», «… sapması», «fiili …» ile kurulan anahtarlar ölçümde başka soruları kaptı (ONERI.md §5).
    done = [f"{dl}.ACTDURATION > (0)"] if dl else []
    link = f"{dl}.WSREF = {ws}.LOGICALREF" if dl and ws else ""
    skip_dl = need(dl, "LG_{n0}_DISPLINE", ["PLNDURATION", "ACTDURATION", "WSREF", "LINESTATUS"])
    base = {"func": "SUM", "grain": dl, "unit": "dakika", **({"link": link} if link else {})}
    out.append(dict(
        key="operasyon-gerceklesen-suresi", term="operasyon gerçekleşen süresi", type="METRIC", entity=dl,
        pattern="LG_{n0}_DISPLINE", column="ACTDURATION", formula=f"SUM({dl}.ACTDURATION)", skip=skip_dl,
        extra={**base, "aliases": ["gerceklesen_sure_dk"], "conditions": done},
        synonyms=["iş istasyonu gerçekleşen süresi", "iş istasyonlarının gerçekleşen süresi"],
        reason="tanım: operasyon gerçekleşen süresi = Σ DISPLINE.ACTDURATION (dakika), yalnız gerçekleşeni dolu "
               "operasyonlar (ACTDURATION > 0 ⇔ LINESTATUS 3 tamamlandı: 1.200/1.221; kalan 21 satır LINESTATUS 1, "
               "ACTDUEDATE boş). İş teyidi bekliyor: birim ve 'geçen ay' tarih alanı."))
    out.append(dict(
        key="operasyon-planlanan-suresi", term="operasyon planlanan süresi", type="METRIC", entity=dl,
        pattern="LG_{n0}_DISPLINE", column="PLNDURATION", formula=f"SUM({dl}.PLNDURATION)", skip=skip_dl,
        extra={**base, "aliases": ["planlanan_sure_dk"], "conditions": []},
        synonyms=["iş istasyonu planlanan süresi", "iş istasyonlarının planlanan süresi"],
        reason="tanım: operasyon planlanan süresi = Σ DISPLINE.PLNDURATION (dakika; 1.221/1.221 satırda dolu, "
               "= üretim emrinin planlanan adedi × 1 dk). İş teyidi bekliyor."))
    out.append(dict(
        key="operasyon-sure-farki", term="operasyon süre farkı", type="METRIC", entity=dl,
        pattern="LG_{n0}_DISPLINE", formula=f"SUM({dl}.ACTDURATION - {dl}.PLNDURATION)", skip=skip_dl,
        extra={**base, "aliases": ["sure_farki_dk"], "conditions": done},
        synonyms=["iş istasyonu süre farkı", "iş istasyonlarının süre farkı"],
        optional_synonyms=["süre sapması", "operasyon süre sapması", "iş istasyonu süre sapması"],
        reason="tanım: süre farkı (sapma) = Σ (ACTDURATION − PLNDURATION), yalnız tamamlanan operasyonlar (devam edenler "
               "gerçekleşen 0 ile eksi sapma üretirdi). Ağustos 2026, ACTDUEDATE: 77 operasyon / 10 istasyon, "
               "plan 11.545 sa, gerçekleşen 11.757 sa, sapma +212,5 sa. İş teyidi bekliyor."))

    # ---- Q36: hedefin aylara dağılımının dengesizliği = değişim katsayısı (Kural C2)
    skip_sh = need(sh, "NEW_SATISHEDEFLERIBASE", MONTHS + ["statecode", "new_stokkarti"])
    cols = [column_of(sh, c) or c for c in MONTHS] if sh else MONTHS
    out.append(dict(
        key="dengesizlik-katsayisi", term="dengesizlik katsayısı", type="METRIC", entity=sh,
        pattern="NEW_SATISHEDEFLERIBASE", formula=cv_formula(sh, cols) if sh else "", skip=skip_sh,
        extra={"func": "RATIO", "undated": True, "aliases": ["dengesizlik", "degisim_katsayisi"],
               "conditions": [f"{sh}.statecode IN (0)"] if sh else []},
        synonyms=["dengesiz", "dengesizlik", "dengesiz dağılım", "dengesizlik oranı"],
        reason="tanım (Kural C2): dengesizlik = 12 aylık hedefin değişim katsayısı (örneklem std. sapma / ortalama), "
               "kırılım düzeyinde ay ay toplanarak; yıllık toplamı 0 olan ürün NULL döner (dışlanır). Kapalı biçim, "
               "STDEV/AVG referansıyla 2026'da 3.429/3.429 üründe birebir; en yüksek 3,4641 (= √12, 44 ürün eşit). "
               "İş teyidi bekliyor: ölçü seçimi (CV) ve yıl kapsamı."))
    if "--include-optional" in sys.argv:
        for d in out:
            d["synonyms"] = list(d["synonyms"]) + list(d.get("optional_synonyms") or [])
    return out


# ------------------------------------------------------------------------------------------------ ortak
def _open():
    from semantic_layer.catalog import one_entity_per_pattern
    from semantic_layer.config import SemanticSettings
    from semantic_layer.store.catalog_store import open_store
    s = SemanticSettings.from_env()
    store = open_store(s.store_dsn, create=False)
    profiles = one_entity_per_pattern(store.list_profiles(s.datasource_id), store.concept_entities(s.tenant_id, s.datasource_id))
    by_pattern: dict[str, object] = {}
    for p in profiles:
        by_pattern.setdefault(p.table_pattern.upper(), p)
    by_entity = {p.entity: p for p in profiles}

    def entity_of(pattern: str):
        p = by_pattern.get(pattern.upper())
        return p.entity if p else None

    def column_of(entity: str, column: str):
        p = by_entity.get(entity)
        if p is None:
            return None
        return next((c.name for c in p.columns if c.name.upper() == column.upper()), None)

    return s, store, profiles, definitions(entity_of, column_of)


def _mapping(d):
    from semantic_layer.models import Mapping
    return Mapping(concept_id="", entity=d["entity"], table_pattern=d["pattern"], column=d.get("column"),
                   operator=d.get("operator"), values=[], formula=d.get("formula"), extra=dict(d.get("extra") or {}))


def _existing(store, s, d):
    from semantic_layer.normalize import normalize_term
    m = _mapping(d)
    for c in store.find_concepts(s.tenant_id, s.datasource_id, normalized_term=normalize_term(d["term"]), semantic_type=d["type"]):
        if any(x.key() == m.key() for x in store.list_mappings(c.id)):
            return c
    return None


def _collisions(store, s, d):
    """Aynı anahtarı (terim ya da eş anlamlı) bugün taşıyan SERTİFİKALI kavramlar: çözücüde kim kazanır sorusu."""
    from semantic_layer.normalize import normalize_term
    index = store.certified_index(s.tenant_id, s.datasource_id)
    hits = []
    for word in [d["term"], *d["synonyms"]]:
        for c, maps in index.get(normalize_term(word)) or []:
            hits.append({"anahtar": normalize_term(word), "kavram": c.id, "terim": c.term, "tür": c.semantic_type,
                         "alan": [f"{m.entity}.{m.column or m.formula}" for m in maps][:2]})
    return hits


def _magnets(store, s, defs) -> dict[str, list[str]]:
    """Yeni anahtarlardaki kelimelerden bugün HİÇBİR sertifikalı anahtarda geçmeyenler: çözücünün tek-kelime geri
    düşüşü (`_backoff`) böyle bir kelimeyi, soruda tek başına geçtiğinde, doğrudan bu kavrama bağlar."""
    from semantic_layer.normalize import normalize_term
    known = {w for key in store.certified_index(s.tenant_id, s.datasource_id) for w in key.split()}
    out: dict[str, list[str]] = {}
    for d in defs:
        if d["skip"]:
            continue
        words = {w for t in [d["term"], *d["synonyms"]] for w in normalize_term(t).split()}
        out[d["term"]] = sorted(w for w in words if w not in known)
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


def plan(store, s, defs) -> list[dict]:
    from semantic_layer.normalize import normalize_term
    rows = []
    magnets = _magnets(store, s, defs)
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
                     "formül": d.get("formula"), "extra": d.get("extra") or {}, "eklenecek_eş_anlamlılar": missing,
                     "katalogda_yeni_kelimeler(tek_başına_bu_kavramı_çeker)": magnets.get(d["term"], []),
                     "aynı_anahtarı_taşıyan_sertifikalılar": [h for h in _collisions(store, s, d) if h["kavram"] != (c.id if c else None)],
                     "gerekçe": d["reason"]})
    return rows


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
                                        payload={"note": "tanım müşteri veritabanında salt-okunur sorgularla doğrulandı (ONERI.md)"}))
        if c.status != ConceptStatus.CERTIFIED or not (c.explain or {}).get("human_certified_by"):
            engine.human_certify(c.id, WHO, reason=d["reason"])
        done.append({"kavram": d["term"], "id": c.id, "sonuç": "yaratıldı" if created else "vardı; tamamlandı"})
    return done


# ------------------------------------------------------------------------------------------------ bellekte ölçüm
class _WithProposal:
    """Önerilen kavramlar YALNIZ bellekteki dizine eklenir. Anlık görüntü yayını kapatılır: gerçek store'un
    `publish_runtime_snapshot`'ı kendisine verilen dizini sl_catalog_version'a YAZAR."""

    def __init__(self, store, s, defs):
        from semantic_layer.models import Concept
        from semantic_layer.normalize import normalize_term
        self._s, self._base, self._merged, self._extra = store, None, None, []
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
            merged = {k: list(v) for k, v in base.items()}
            if "--withdraw-generic" in sys.argv:
                for norm, entity, column in WITHDRAW:
                    kept = [(c, maps) for c, maps in merged.get(norm, []) if c.normalized_term == norm or not any(
                        m.entity.upper() == entity and (m.column or "").upper() == column for m in maps)]
                    if kept:
                        merged[norm] = kept
                    else:
                        merged.pop(norm, None)
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
        slots.append(f"{sl.term} → {sl.semantic_type}:{m.entity}.{m.column or (m.formula or '')[:40]}" + (f" [{sl.status}{' ' + how if how else ''}: {(sl.explain or {}).get('evidence_key', '')}]" if sl.status != "CERTIFIED" else ""))
    return {"slots": sorted(slots), "unresolved": sorted(q.unresolved), "hint": getattr(q, "source_hint", None),
            "state": getattr(q, "state", None)}


def simulate(store, s, profiles, defs, files) -> None:
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
    before, after = mk(_ReadOnly(store)), mk(_WithProposal(store, s, defs))
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
    if "--withdraw-generic" in sys.argv:
        rows_w = withdraw_rows(store)
        print(json.dumps({"geri_çekilecek_makine_onayları": [
            {**r, "işlem": "geri çek (PROPOSED)" if r["status"] == "APPROVED" and r["decided_by"] == "otomatik-yoklama" else "DOKUNMA (kişi kararı ya da zaten geri çekilmiş)"}
            for r in rows_w], "gerekçe": WITHDRAW_REASON}, ensure_ascii=False, indent=1, default=str))
    if "--apply" in sys.argv:
        if "--withdraw-generic" in sys.argv:
            from semantic_layer import vocabulary
            for r in withdraw_rows(store):
                if r["status"] == "APPROVED" and r["decided_by"] == "otomatik-yoklama":
                    print(json.dumps({"geri_çekildi": vocabulary.withdraw(store, s, r["id"], WITHDRAW_REASON)}, ensure_ascii=False, default=str))
        print(json.dumps({"yazıldı": apply(store, s, defs)}, ensure_ascii=False, indent=1))
        print("Köprü kataloğu en geç 30 sn içinde kendisi yeniden yükler (ensure_fresh); yeniden başlatma gerekmez.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
