"""Adım 2 — muhasebe sözlüğü: defter (EMFLINE) üstünde, hesap planının kendi kebir koduyla kapsanan ölçüler.

Sorun (ölçüldü, tests/text2sql/reports/muhasebe100-rapor-2026-09-21.md): muhasebecinin çekirdek terimlerinin hiçbiri
katalogda sertifikalı değildi; muhasebe soruları defter yerine yan tablolara (çek kartı, STLINE, fatura TOTALVAT) gidiyordu.

Tasarım: her kavram Tek Düzen Hesap Planı'nın bir ANA HESABINA (kebir) bağlı bir ölçüdür.
  · Kapsam `EMFLINE.KEBIRCODE IN (<kod>)` koşuludur, formüle LIKE gömülmez. Ölçüldü: LG_411 ve LG_211
    EMFLINE'ın 246.404 / tüm satırlarında KEBIRCODE = LEFT(ACCOUNTCODE,3), hepsi sayısal. IN koşulu hem
    deterministik derleyicinin (`_pred_key_sql`) hem kapının (`_condition_holds`) okuduğu biçimdir; LIKE
    ikisinin de okuyamadığı biçimdi (bugünkü 'gider' ölçüsü bu yüzden hiç deterministik derlenmiyor).
  · Bakiye (bilanço hesabı) ölçüleri `state_measure`: dönemsiz okunur (açılış fişi dahil), çözücü onlara
    varsayılan yıl koymaz, kapı dönem/işlem türü filtresi altında hesaplanmalarını reddeder.
  · Aktif hesap bakiyesi Σ(borç − alacak), pasif hesap bakiyesi Σ(alacak − borç); gelir hesabı Σ(alacak − borç),
    gider/indirim hesabı Σ(borç − alacak). Yön hesabın sınıfından gelir (TDHP), soruya göre değişmez.
  · Tek kelime YOK: her anahtar en az iki kelimelik öbek ('banka' / 'kdv' / 'borç' / 'bakiye' çıplak verilmedi).

Kipler:
  (varsayılan)       KURU KOŞU: ne yazılacağını, çakışmaları ve katalogda yeni kelimeleri basar.
  --simulate f.jsonl YAZMADAN ölçüm: kavramlar yalnız bellekteki dizine eklenir; soruların çözücü okuması
                     önce/sonra karşılaştırılır.
  --apply            yazar (idempotent; human_certify ile, gece motoru geri almasın) + NARROW terim daraltması.

Sunucuda, köprünün ortamıyla:
  sudo systemd-run --pipe --wait --collect --quiet -p User=administrator \
     -p EnvironmentFile=/etc/nanobase/semantic-bridge.env -p WorkingDirectory=/data/nanobaseai/bi/frontend/backend \
     -E PYTHONPATH=/data/nanobaseai/bi/frontend/backend /data/nanobaseai/bi/semantic-venv/bin/python - [--apply] < apply.py
"""
from __future__ import annotations

import json
import sys

WHO = "operator:claude (muhasebe sözlüğü, 2026-09-21)"
SRC = "operator:adim2-muhasebe-sozluk"

#: Terimi daraltılacak makine (rule-miner) kavramları — eşlemeye DOKUNULMAZ, yalnız terim.
#: 'hesaplanan kdv' bugün INVOICE.TOTALVAT kolonuna bağlı; o kolon alış faturasında da dolu (indirilecek KDV'dir),
#: yani 'hesaplanan' adı kolonu anlatmıyor. Muhasebede 'Hesaplanan KDV' 391 hesabının adıdır. Kolon kavramı
#: 'fatura kdv tutarı' adıyla kalır; boşalan anahtarı 391 ölçüsü alır.
NARROW = [("sem_05eccc74b5ac", "fatura kdv tutarı"),
          # 'genel yönetim giderleri' (rule-miner) = EMFLINE.KEBIRCODE IN (770) SÜZGECİ; aynı anahtarı ölçü alır.
          ("sem_74e0e6368285", "genel yönetim giderleri hesabı")]
NARROW_REASON = (
    "'hesaplanan kdv' (rule-miner) INVOICE.TOTALVAT kolonuna bağlı. Canlı LG_411 2026: satış faturası (7,8,9) TOTALVAT "
    "4.490.682,10; alış faturası (1,4) TOTALVAT 61.198.805,28 — kolon her iki yönün KDV'sini taşır, 'hesaplanan' değil. "
    "Muhasebede 'Hesaplanan KDV' = 391 hesabı (2026 alacak 5.046.473,87). Eşleme aynı kalır, terim 'fatura kdv tutarı'. "
    "'genel yönetim giderleri' (rule-miner) EMFLINE.KEBIRCODE IN (770) süzgeci; tek başına ölçüsüz kaldığında soru "
    "'gider' ölçüsüne (7'li hesapların tamamı, LIKE — deterministik derlenemiyor) düşüyor ve 65.335.626,98 dönüyordu "
    "(muhasebe100 M081; doğrusu 54.138.183,67). Süzgeç 'genel yönetim giderleri hesabı' adıyla kalır; anahtarı 770 ölçüsü alır.")


def definitions(entity_of, column_of) -> list[dict]:
    out: list[dict] = []
    em = entity_of("LG_{n0}_{n1}_EMFLINE")
    skip = ("profil yok: LG_{n0}_{n1}_EMFLINE" if not em else
            ", ".join(c for c in ("KEBIRCODE", "DEBIT", "CREDIT", "CANCELLED", "DATE_") if not column_of(em, c)))
    skip = (f"{em} profilinde kolon yok: {skip}" if em and skip else skip)

    def add(key, term, code, side, *, state, synonyms, ref, why=""):
        codes = code if isinstance(code, (list, tuple)) else [code]
        expr = {"borç-alacak": f"{em}.DEBIT - {em}.CREDIT", "alacak-borç": f"{em}.CREDIT - {em}.DEBIT",
                "borç": f"{em}.DEBIT", "alacak": f"{em}.CREDIT"}[side]
        # verb_bridge: false — hesap adı sabit bir addır, bir fiilin adı değil ('alınan çekler', 'hesaplanan kdv',
        # 'ödenecek vergiler' ortaçla başlar). Çözücü fiil köprüsünü (alınmış/hesaplar/ödediğimiz → bu ölçü) kurmaz;
        # ölçü kendi kelimeleriyle bulunur. (backend/semantic_layer/runtime/resolver.py `_metric_keys_for_root`)
        extra = {"func": "SUM", "aliases": [key.replace("-", "_")], "verb_bridge": False,
                 "conditions": [f"{em}.CANCELLED IN (0)", f"{em}.KEBIRCODE IN ({', '.join(str(c) for c in codes)})"]}
        if state:
            extra["state_measure"] = True
        out.append({"key": key, "term": term, "type": "METRIC", "entity": em, "pattern": "LG_{n0}_{n1}_EMFLINE",
                    "formula": f"SUM({expr})" if em else "", "extra": extra, "synonyms": synonyms, "skip": skip,
                    "ref": ref,
                    "reason": (f"tanım: {term} = Σ({side}) yevmiye satırları (EMFLINE, iptal hariç), ana hesap "
                               f"{'/'.join(str(c) for c in codes)} (KEBIRCODE; LG_411'de 246.404/246.404 satırda "
                               f"LEFT(ACCOUNTCODE,3) ile aynı). "
                               + ("Bilanço hesabı: bakiye dönemsiz okunur (açılış fişi dahil). " if state else "Dönem akışıdır. ")
                               + f"Bağımsız referans (muhasebe100 {ref[0]}): {ref[1]:,.2f}; aynı tanım canlıda aynı değeri verdi. "
                               + why + "İş teyidi bekliyor.")})

    # ------------------------------------------------------------------ bilanço: bakiyeler (state)
    add("banka-hesaplari-bakiyesi", "banka hesapları bakiyesi", 102, "borç-alacak", state=True,
        synonyms=["bankalar hesabı bakiyesi", "banka bakiyesi", "bankalardaki bakiye"],
        ref=("M003", 252437313.15),
        why="Banka MODÜLÜ (BNFLINE) okuması 'bankalara giren/çıkan' için ayrı kalır; bu ölçü yalnız bakiye öbeklerini taşır. "
            "'bankalar hesabı' öbeği bilerek YOK: kökü 'banka hesabı' ile aynı ('kaç banka hesabımız var' sayım sorusunu çekiyordu, ölçüldü). ")
    add("alinan-cekler-hesabi-bakiyesi", "alınan çekler hesabı bakiyesi", 101, "borç-alacak", state=True,
        synonyms=["alınan çekler hesabı", "alınan çekler bakiyesi"],
        ref=("M011", 301342806.67),
        why="Çek KARTLARI (CSCARD) toplamı değildir; o, çeklerin durum sorularında (portföy, tahsil, ciro) kalır. ")
    add("diger-hazir-degerler-bakiyesi", "diğer hazır değerler bakiyesi", 108, "borç-alacak", state=True,
        synonyms=["diğer hazır değerler", "diğer hazır değerler hesabı"],
        ref=("M012", 12052843.01))
    add("alicilar-hesabi-bakiyesi", "alıcılar hesabı bakiyesi", 120, "borç-alacak", state=True,
        synonyms=["alıcılar hesabı", "alıcılar bakiyesi", "ticari alacaklar bakiyesi"],
        ref=("M004", 136057227.70),
        why="Müşteri BAZINDA bakiye (cari hesap, CLFLINE) bu ölçü değildir: 'müşteri bakiyesi' öbeği bilerek verilmedi. ")
    add("saticilar-hesabi-bakiyesi", "satıcılar hesabı bakiyesi", 320, "alacak-borç", state=True,
        synonyms=["satıcılar hesabı", "satıcılar bakiyesi", "satıcı borçları", "ticari borçlar bakiyesi"],
        ref=("M005", 55348004.80),
        why="Pasif hesap: bakiye alacak − borç. Tedarikçi BAZINDA borç (cari) bu ölçü değildir. ")
    add("odenecek-vergi-ve-fonlar-bakiyesi", "ödenecek vergi ve fonlar bakiyesi", 360, "alacak-borç", state=True,
        synonyms=["ödenecek vergiler", "ödenecek vergi hesabı", "ödenecek vergiler bakiyesi"],
        ref=("M066", 9049793.39),
        why="'ve' içeren öbek anahtarı hiç eşleşmez (soru n-gramı durak sözcükte kesilir), bu yüzden 'ödenecek vergi ve fonlar' "
            "yazımı eş anlamlı olarak verilmedi. ")
    # ------------------------------------------------------------------ akışlar (dönemli)
    add("yurtici-satislar-hesabi", "yurtiçi satışlar hesabı", 600, "alacak-borç", state=False,
        synonyms=["yurtiçi satışlar", "yurt içi satışlar", "yurt içi satışlar hesabı"],
        ref=("M009", 910058749.55),
        why="Gelir hesabı: alacak − borç (2026'da borç 0). Fatura/satır cirosu (KPI 'net ciro') ayrı kalır. ")
    add("satistan-iadeler-hesabi", "satıştan iadeler hesabı", 610, "borç-alacak", state=False,
        synonyms=[],
        ref=("M071", 71032970.66),
        why="'satış iadesi' / 'satıştan iadeler' (kök: 'satis iade') bugün INVOICE/STLINE TRCODE 2,3 süzgecine bağlı "
            "(3 kavram) — bilerek alınmadı; ölçü yalnız 'satıştan iadeler hesabı' öbeğini taşır. ")
    add("satis-iskontolari", "satış iskontoları", 611, "borç-alacak", state=False,
        synonyms=["satış iskontoları hesabı", "satış iskontosu tutarı"],
        ref=("M072", 2831545.02),
        why="Sonradan verilen iskontolar (611). Fatura satırı iskontosu (STLINE LINETYPE 2, 747,9 Mn) ayrıdır. ")
    add("hesaplanan-kdv", "hesaplanan kdv", 391, "alacak", state=False,
        synonyms=["hesaplanan kdv hesabı", "hesaplanan kdv toplamı"],
        ref=("M060", 5046473.87),
        why="391 alacak hareketleri; borç tarafı aylık KDV mahsubudur, alınmaz. 2026'da 391'e açılış kaydı yok (ölçüldü). ")
    add("indirilecek-kdv", "indirilecek kdv", 191, "borç", state=False,
        synonyms=["indirilecek kdv hesabı", "indirilecek kdv toplamı"],
        ref=("M061", 65211493.80),
        why="191 borç hareketleri; alacak tarafı aylık mahsuptur. 2026'da 191'e açılış kaydı yok (ölçüldü). ")
    add("pazarlama-gideri", "pazarlama satış dağıtım gideri", 760, "borç-alacak", state=False,
        synonyms=["pazarlama gideri", "pazarlama giderleri", "pazarlama satış dağıtım giderleri"],
        ref=("M080", 242392016.63),
        why="761 yansıtma hesabı hariç (yansıtma dahil net 37,5 Mn olurdu). ")
    add("genel-yonetim-gideri", "genel yönetim gideri", 770, "borç-alacak", state=False,
        synonyms=["yönetim gideri", "yönetim giderleri"],
        ref=("M081", 54138183.67),
        why="771 yansıtma hariç. 'genel' soru n-gramında durak sözcüktür (STOPWORDS): 'genel …' ile başlayan anahtar hiç "
            "eşleşmez; bu yüzden soruda okunan öbek 'yönetim gideri/giderleri'dir. Aynı kebir koduna bağlı rule-miner "
            "SÜZGECİ 'genel yönetim giderleri hesabı' adına daraltılır (NARROW; anahtarı zaten ölüydü, etkisi yok). ")
    return out


# ------------------------------------------------------------------------------------------------ ortak
def _open():
    from semantic_layer.catalog import one_entity_per_pattern
    from semantic_layer.config import SemanticSettings
    from semantic_layer.store.catalog_store import open_store
    s = SemanticSettings.from_env()
    store = open_store(s.store_dsn, create=False)
    profiles = one_entity_per_pattern(store.list_profiles(s.datasource_id),
                                      store.concept_entities(s.tenant_id, s.datasource_id))
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
                   operator=d.get("operator"), values=list(d.get("values") or []), formula=d.get("formula"),
                   extra=dict(d.get("extra") or {}))


def _existing(store, s, d):
    from semantic_layer.normalize import normalize_term
    m = _mapping(d)
    for c in store.find_concepts(s.tenant_id, s.datasource_id, normalized_term=normalize_term(d["term"]),
                                 semantic_type=d["type"]):
        if any(x.key() == m.key() for x in store.list_mappings(c.id)):
            return c
    return None


def _collisions(store, s, d):
    from semantic_layer.normalize import normalize_term
    index = store.certified_index(s.tenant_id, s.datasource_id)
    narrowed = {cid for cid, _ in NARROW}
    hits = []
    for word in [d["term"], *d["synonyms"]]:
        for c, maps in index.get(normalize_term(word)) or []:
            hits.append({"anahtar": normalize_term(word), "kavram": c.id, "terim": c.term, "tür": c.semantic_type,
                         "daraltılıyor": c.id in narrowed,
                         "alan": [f"{m.entity}.{m.column or (m.formula or '')[:40]}" for m in maps][:2]})
    return hits


def _magnets(store, s, defs) -> dict[str, list[str]]:
    from semantic_layer.normalize import normalize_term
    known = {w for key in store.certified_index(s.tenant_id, s.datasource_id) for w in key.split()}
    out: dict[str, list[str]] = {}
    for d in defs:
        if d["skip"]:
            continue
        words = {w for t in [d["term"], *d["synonyms"]] for w in normalize_term(t).split()}
        out[d["term"]] = sorted(w for w in words if w not in known)
    return out


def narrow_rows(store) -> list[dict]:
    out = []
    for cid, new_term in NARROW:
        c = store.get_concept(cid)
        if c is None:
            out.append({"kavram": cid, "işlem": "YOK (kavram bulunamadı)"})
            continue
        maps = [f"{m.entity}.{m.column} {m.operator} {m.values}" for m in store.list_mappings(cid)]
        by = (c.explain or {}).get("human_certified_by")
        out.append({"kavram": cid, "şimdiki_terim": c.term, "yeni_terim": new_term, "tür": c.semantic_type,
                    "eşleme": maps, "sertifikalayan": by,
                    "işlem": ("DEĞİŞİKLİK YOK (zaten daraltılmış)" if c.term == new_term else
                              "DOKUNMA (kişi kararı)" if by and not str(by).startswith(("otomatik", "rule-miner"))
                              else "terimi daralt (eşleme aynı kalır)")})
    return out


def _extra_drift(store, c, d) -> bool:
    """Aynı formüllü eşleme var ama extra'sı (koşullar, state_measure, verb_bridge) istenenden farklı."""
    want = _mapping(d)
    for m in store.list_mappings(c.id):
        if m.key() == want.key():
            return dict(m.extra or {}) != dict(want.extra or {})
    return False


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
        drift = False
        if c is None:
            todo, missing = "YARAT + sertifikala", wanted
        else:
            missing = [x for x in wanted if x not in (c.synonyms or []) and x != c.normalized_term]
            drift = _extra_drift(store, c, d)
            certified = c.status == "CERTIFIED" and (c.explain or {}).get("human_certified_by")
            parts = ([] if certified else ["sertifikala"]) + (["eş anlamlı ekle"] if missing else []) \
                + (["eşleme extra güncelle"] if drift else [])
            todo = " + ".join(parts) or "DEĞİŞİKLİK YOK"
        rows.append({"kavram": d["term"], "tür": d["type"], "anahtar": normalize_term(d["term"]), "işlem": todo,
                     "varolan": c.id if c else None, "entity": d["entity"], "kalıp": d["pattern"],
                     "formül": d.get("formula"), "extra": d.get("extra") or {}, "eklenecek_eş_anlamlılar": missing,
                     "referans": d["ref"],
                     "katalogda_yeni_kelimeler": magnets.get(d["term"], []),
                     "aynı_anahtarı_taşıyan_sertifikalılar": [h for h in _collisions(store, s, d)
                                                             if h["kavram"] != (c.id if c else None)],
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
        c, created = store.upsert_concept(s.tenant_id, s.datasource_id, d["term"], d["type"],
                                          mapping=_mapping(d), status=ConceptStatus.CANDIDATE)
        for syn in d["synonyms"]:
            store.add_synonym(c.id, syn)
        if not created and _extra_drift(store, c, d):
            store.replace_mappings(c.id, [_mapping(d)])
        c = store.get_concept(c.id)
        sources = dict((c.explain or {}).get("synonym_sources") or {})
        for syn in d["synonyms"]:
            sources.setdefault(normalize_term(syn), {"by": WHO, "source": SRC})
        declared = sorted(set((c.explain or {}).get("declared_synonyms") or [])
                          | {normalize_term(x) for x in d["synonyms"]})
        store.update_concept(c.id, explain={"synonym_sources": sources, "declared_synonyms": declared})
        if created:
            store.add_evidence(Evidence(c.id, EvidenceType.HUMAN_ANNOTATION, SRC, support_count=1, weight=1.0,
                                        payload={"snippet": d["reason"], "by": WHO}))
            store.add_evidence(Evidence(c.id, EvidenceType.EXECUTION, SRC + ":db-dogrulama",
                                        payload={"note": f"tanım müşteri veritabanında salt-okunur sorguyla çalıştırıldı; "
                                                         f"bağımsız referansla ({d['ref'][0]}: {d['ref'][1]:,.2f}) aynı"}))
        if c.status != ConceptStatus.CERTIFIED or not (c.explain or {}).get("human_certified_by"):
            engine.human_certify(c.id, WHO, reason=d["reason"])
        done.append({"kavram": d["term"], "id": c.id, "sonuç": "yaratıldı" if created else "vardı; tamamlandı"})
    return done


def apply_narrow(store) -> list[dict]:
    out = []
    for row in narrow_rows(store):
        if not str(row.get("işlem", "")).startswith("terimi daralt"):
            out.append(row)
            continue
        cid, new_term = row["kavram"], row["yeni_terim"]
        store.rename_concept(cid, new_term)
        c = store.get_concept(cid)
        ex = dict(c.explain or {})
        ex["narrowed_from"] = {"term": row["şimdiki_terim"], "by": WHO, "reason": NARROW_REASON}
        store.update_concept(cid, explain=ex)
        out.append({**row, "sonuç": "daraltıldı"})
    return out


# ------------------------------------------------------------------------------------------------ bellekte ölçüm
class _WithProposal:
    """Önerilen kavramlar YALNIZ bellekteki dizine eklenir; NARROW terimleri yalnız bellekte taşınır.
    Anlık görüntü yayını kapatılır: gerçek store'un `publish_runtime_snapshot`'ı dizini sl_catalog_version'a YAZAR."""

    def __init__(self, store, s, defs, narrow=True):
        from semantic_layer.models import Concept
        from semantic_layer.normalize import normalize_term
        self._s, self._base, self._merged, self._extra, self._narrow = store, None, None, [], narrow
        for n, d in enumerate(x for x in defs if not x["skip"]):
            c = Concept(tenant_id=s.tenant_id, datasource_id=s.datasource_id, term=d["term"],
                        normalized_term=normalize_term(d["term"]), semantic_type=d["type"],
                        status="CERTIFIED", confidence=1.0,
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
            from semantic_layer.normalize import normalize_term
            merged = _baseline(base)
            if self._narrow:
                for cid, new_term in NARROW:
                    moved = []
                    for k in list(merged):
                        keep = [(c, mm) for c, mm in merged[k] if c.id != cid]
                        if len(keep) != len(merged[k]):
                            moved += [(c, mm) for c, mm in merged[k] if c.id == cid]
                            merged[k] = keep
                            if not keep:
                                merged.pop(k, None)
                    if moved:
                        merged.setdefault(normalize_term(new_term), []).append(moved[0])
            for c, maps in self._extra:
                for k in dict.fromkeys([c.normalized_term, *c.synonyms]):
                    merged.setdefault(k, []).append((c, maps))
            self._base, self._merged = base, merged
        return self._merged


#: NARROW'dan önceki terimler — kavram kataloğa yazılmışsa ölçümün 'önce' tarafı bunlarla kurulur.
_ORIGINAL_TERMS = {"sem_05eccc74b5ac": "hesaplanan kdv", "sem_74e0e6368285": "genel yönetim giderleri"}


def _baseline(index):
    """Bu betiğin HENÜZ yazılmadığı katalog: bu betiğin yazdığı kavramlar (imza WHO) çıkarılır, daraltılan
    terimler eski anahtarlarına geri konur. Kavramlar kataloğa yazılmış olsa bile önce/sonra ölçümü doğru kalır."""
    from semantic_layer.normalize import normalize_term
    merged, moved = {}, []
    for k, senses in index.items():
        keep = []
        for c, maps in senses:
            if (c.explain or {}).get("human_certified_by") == WHO and c.id not in _ORIGINAL_TERMS:
                continue
            if c.id in _ORIGINAL_TERMS and k != normalize_term(_ORIGINAL_TERMS[c.id]) and k == c.normalized_term:
                moved.append((c, maps))
                continue
            keep.append((c, maps))
        if keep:
            merged[k] = keep
    for c, maps in moved:
        merged.setdefault(normalize_term(_ORIGINAL_TERMS[c.id]), []).append((c, maps))
    return merged


class _ReadOnly:
    """'Önce' tarafı: bu betiğin kavramları olmadan (bkz. _baseline). Yayın kapalı."""

    def __init__(self, store):
        self._s, self._base, self._merged = store, None, None

    def __getattr__(self, name):
        return getattr(self._s, name)

    def publish_runtime_snapshot(self, tenant_id, datasource_id, index):
        return 0, "bellekte-olcum"

    def certified_index(self, t, d):
        base = self._s.certified_index(t, d)
        if self._merged is None or self._base is not base:
            self._base, self._merged = base, _baseline(base)
        return self._merged


def _reading(res, question):
    from semantic_layer.models import SemanticType
    q = res.resolve(question)
    slots = []
    for sl in list(q.slots) + [g for g in q.group_by if g not in q.slots]:
        m = sl.mapping
        if m is None or not m.entity or sl.semantic_type == SemanticType.DEFAULT_FILTER:
            continue
        slots.append(f"{sl.term} → {sl.semantic_type}:{m.entity}.{m.column or (m.formula or '')[:40]}")
    return {"slots": sorted(slots), "unresolved": sorted(q.unresolved),
            "hint": getattr(q, "source_hint", None), "state": getattr(q, "state", None)}


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
    mk = lambda st: SemanticResolver(st, s.tenant_id, s.datasource_id, profiles,
                                     default_temporal=_default_period(), conventions=conv, verified_pairs=pairs)
    before, after = mk(_ReadOnly(store)), mk(_WithProposal(store, s, defs))
    cases = [json.loads(l) for f in files for l in open(f, encoding="utf-8") if l.strip()]
    changed = 0
    for case in cases:
        a, b = _reading(before, case["soru"]), _reading(after, case["soru"])
        if a != b:
            changed += 1
            print(json.dumps({"id": case.get("id"), "soru": case["soru"], "önce": a, "sonra": b}, ensure_ascii=False), flush=True)
    print(json.dumps({"soru": len(cases), "okuması_değişen": changed}, ensure_ascii=False))


def main() -> int:
    if "--harness" in sys.argv:          # ölçüm düzeneği bu dosyayı kütüphane olarak okur
        return 0
    s, store, profiles, defs = _open()
    if "--simulate" in sys.argv:
        files = [a for a in sys.argv[sys.argv.index("--simulate") + 1:] if not a.startswith("--")]
        simulate(store, s, profiles, defs, files)
        return 0
    print(json.dumps({"kip": "UYGULA" if "--apply" in sys.argv else "KURU KOŞU (yazılmadı)", "who": WHO,
                      "plan": plan(store, s, defs), "terimi_daraltılacak": narrow_rows(store),
                      "daraltma_gerekçesi": NARROW_REASON}, ensure_ascii=False, indent=1, default=str))
    if "--apply" in sys.argv:
        print(json.dumps({"daraltıldı": apply_narrow(store)}, ensure_ascii=False, indent=1, default=str))
        print(json.dumps({"yazıldı": apply(store, s, defs)}, ensure_ascii=False, indent=1))
        print("Köprü kataloğu en geç 30 sn içinde kendisi yeniden yükler (ensure_fresh); yeniden başlatma gerekmez.")
    return 0


if __name__ == "__main__":
    main()
