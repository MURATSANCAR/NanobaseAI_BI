"""«Etkinlik ve fuar gideri» — Logo defterinde, hesap planından tanımlı genel bir ölçü (tam kapı 2026-09-29, K7 / B064).

Karar (koordinatör, kullanıcı altın kararlarını bıraktı; ilke: gerçekleşmiş finansal olayın kayıt sistemi Logo'dur):
etkinliklere harcanan para Logo defterinde, etkinlik ve fuar gider hesaplarındadır. CRM `new_ToplamEtkinlikGideri`
yalnız 2015–16'da 28 kayıtta dolu (9.275 ₺) — eksik alan; toplam harcama sorusuna cevap değildir.

Tanım (hesap planı alt hesapları; soruya özel değil, TDHP'nin 7'li gider sınıfından seçilmiş hesap listesi):
    740.03        Fuar Organizasyon
    760.44.444–6  Fuar/Stand kira, satınalma, kurulum
    760.45        Fuar Giderleri (451 kira, 452 kurulum, 453 yol/yemek/konaklama)
    760.47.470    Organizasyon, Etkinlik, İmza Günü vb.
    760.47.477    Fuar yol/konaklama
    770.44.444    (yönetim gideri altında fuar/stand)
    770.47.472    Stand, Fuar, Sergi ve İmza
  tutar = Σ(DEBIT − CREDIT), EMFLINE, iptal hariç; ana hesap koşulu KEBIRCODE IN (740, 760, 770) (kapının ve derleyicinin
  okuduğu biçim), alt hesap kapsamı formülde (LIKE koşul olarak okunamıyor — tahsilat ölçüsündeki yöntem).
  Canlı ölçüm (koordinatör, LG_411_01_EMFLINE): 2026 = 4.831.871,56 ₺, 1.079 satır; en büyük 760.47.470 = 3.405.000,92.
  Yansıtma fişi HARİÇ (koordinatör ölçümü 2026-09-29): 2025'te 1.387 satır, hepsi fiş türü 4, borç = alacak, net 0 —
  kapanış fiş türüyle ayrılamıyor. Aralık alacaklarının karşı hesabı 711/731/761/771/781: yıl sonu yansıtma/kapanış kaydı
  (~7,2 Mn). Yıl içi alacaklar (karşı hesap 120 müşteriye yansıtılan gider, 320 tedarikçi iadesi) gerçek düzeltmedir, düşülür.
  Tanım: aynı fişte (ACCFICHEREF) ACCOUNTCODE LIKE '7_1%' satırı olan fiş ölçüden tamamen çıkar — katalog eşlemesinin
  genel «hariç grup» koşulu (`extra.exclude_groups`; derleyici NOT EXISTS yazar, kapı arar). 2026'da yansıtma yok.

Bütçe: etkinlik bütçesi hiçbir kaynakta yok (Kural C21, bilgi paketi 2026-09-29'da güncellendi): cevap toplamı verir,
bütçenin tanımlı olmadığını söyler.

Aynı anahtar: CRM'deki «etkinlik giderleri» kavramı (NEW_ETKINLIKBASE.new_ToplamEtkinlikGideri) bu ölçünün eş
anlamlılarıyla (etkinlik gideri/giderleri) çakışıyor; bir anahtar iki ölçüye giderse çözücü ikisini de seçemez. CRM kavramı
DARALTILIR: eşlemesi aynı kalır, terimi «crm etkinlik kartı gideri», çakışan eş anlamlıları çıkarılır. Etkinlik/yazar
bazında kırılım (yalnız CRM kartında var) o adla ve bilgi paketi Kural C10 ile okunur.

  kuru koşu (varsayılan)   ne yazılacağını, çakışan kavramları ve daraltmayı basar; yazmaz.
  --olc                    Logo'da (SEMANTIC_CONNECTION_FILE, salt okuma) bu yıl ve geçen yıl, yansıtma fişi hariç ve dahil.
  --apply                  yazar (idempotent; human_certify), CRM kavramını daraltır, semantic_audit'e yazar.

Koşu (sunucuda, köprünün ortamıyla):

    sudo systemd-run --pipe --wait --collect -p User=administrator \\
      -p EnvironmentFile=/etc/nanobase/semantic-bridge.env \\
      -E PYTHONPATH=/data/nanobaseai/bi/frontend/backend \\
      /data/nanobaseai/bi/semantic-venv/bin/python - [--olc] [--apply] < betik.py

Sonra: katalog 60 sn içinde tazelenir → resolver-gate (beklenen fark B064 ve «etkinlik gideri» geçen sorular, ör. A044)
→ answer-gate --only Q63,Q49 → tam kapı.
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

WHO = "operator:claude (tam kapı 2026-09-29, kayıt sistemi Logo)"
SRC = "operator:2026-09-29:etkinlik-fuar-gideri"
TERM = "etkinlik ve fuar gideri"
ACCOUNTS = ["740.03", "760.44.444", "760.44.445", "760.44.446", "760.45", "760.47.470", "760.47.477", "770.44.444", "770.47.472"]
MAIN = sorted({int(a.split(".")[0]) for a in ACCOUNTS})
SYNONYMS = ["etkinlik gideri", "etkinlik giderleri", "etkinlik harcaması", "etkinlik harcamaları",
            "fuar gideri", "fuar giderleri", "fuar harcaması", "organizasyon gideri", "imza günü gideri"]
CRM_NEW_TERM = "crm etkinlik kartı gideri"
REF = 4831871.56


def _open():
    from semantic_layer.catalog import one_entity_per_pattern
    from semantic_layer.config import SemanticSettings
    from semantic_layer.store.catalog_store import open_store
    s = SemanticSettings.from_env()
    st = open_store(s.store_dsn, create=False)
    profiles = one_entity_per_pattern(st.list_profiles(s.datasource_id), st.concept_entities(s.tenant_id, s.datasource_id))
    em = next((p for p in profiles if p.table_pattern.upper() == "LG_{N0}_{N1}_EMFLINE"), None)
    return s, st, profiles, em


#: Yansıtma fişi: aynı fişte bir 7x1 yansıtma hesabı satırı (711, 721, … 791). Genel «hariç grup» koşulu.
REFLECTION = {"key": "ACCFICHEREF", "column": "ACCOUNTCODE", "like": ["7_1%"],
              "why": "yansıtma/kapanış fişi (aynı fişte 7x1 yansıtma hesabı satırı)"}


def _mapping(em):
    from semantic_layer.models import Mapping
    e = em.entity
    scope = " OR ".join(f"{e}.ACCOUNTCODE LIKE '{a}%'" for a in ACCOUNTS)
    conds = [f"{e}.CANCELLED IN (0)", f"{e}.KEBIRCODE IN ({', '.join(str(k) for k in MAIN)})"]
    return Mapping(concept_id="", entity=e, table_pattern=em.table_pattern,
                   formula=f"SUM(CASE WHEN ({scope}) THEN {e}.DEBIT - {e}.CREDIT ELSE 0 END)",
                   extra={"func": "SUM", "aliases": ["toplam_etkinlik_gideri"], "verb_bridge": False, "conditions": conds,
                          "exclude_groups": [dict(REFLECTION)]})


def _crm_collisions(st, s, em):
    """Bu ölçünün anahtarlarını taşıyan, EMFLINE dışı sertifikalı ölçüler (CRM etkinlik kartı gideri)."""
    from semantic_layer.normalize import normalize_term
    index = st.certified_index(s.tenant_id, s.datasource_id)
    keys = {normalize_term(x) for x in [TERM, *SYNONYMS]}
    out = {}
    for k in keys:
        for c, maps in index.get(k) or []:
            if any((m.entity or "").upper() == em.entity.upper() for m in maps):
                continue
            out.setdefault(c.id, (c, maps, set()))[2].add(k)
    return list(out.values())


def _measure() -> None:
    """Ölçünün tanımıyla (yansıtma fişi hariç) bu yıl ve geçen yıl; karşılaştırma için yansıtma dahil de."""
    from semantic_layer.profiler.connectors import connector_from_file
    conn = connector_from_file(os.environ["SEMANTIC_CONNECTION_FILE"])
    scope = " OR ".join(f"L.ACCOUNTCODE LIKE '{a}%'" for a in ACCOUNTS)
    likes = " OR ".join(f"Y.{REFLECTION['column']} LIKE '{p}'" for p in REFLECTION["like"])
    for firm, year in (("411", "YEAR(GETDATE())"), ("211", "YEAR(GETDATE())-1")):
        refl = (f"EXISTS (SELECT 1 FROM LG_{firm}_01_EMFLINE Y WHERE Y.{REFLECTION['key']} = L.{REFLECTION['key']} "
                f"AND ({likes}))")
        sql = (f"SELECT SUM(CASE WHEN NOT {refl} THEN L.DEBIT-L.CREDIT ELSE 0 END) AS olcu, "
               f"SUM(CASE WHEN NOT {refl} THEN 1 ELSE 0 END) AS olcu_satir, "
               f"SUM(CASE WHEN NOT {refl} THEN L.CREDIT ELSE 0 END) AS olcu_alacak, "
               f"SUM(L.DEBIT-L.CREDIT) AS yansitma_dahil, COUNT(*) AS tum_satir "
               f"FROM LG_{firm}_01_EMFLINE L WHERE L.CANCELLED=0 AND YEAR(L.DATE_)={year} AND ({scope})")
        try:
            rows = conn.execute(sql, 10)[1]
        except Exception as e:  # noqa: BLE001
            print(f"LG_{firm}: okunamadı: {str(e)[:200]}")
            continue
        print(f"LG_{firm} ({year}) yansıtma fişi hariç (ölçü) / dahil:", rows[0] if rows else None)
    print(f"beklenen: bu yıl ölçü = {REF:,.2f}; geçen yıl ölçü ≠ 0 (borç − yıl içi 120/320 düzeltmeleri)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--olc", action="store_true")
    a = ap.parse_args()
    s, st, _, em = _open()
    if em is None:
        print("profil yok: LG_{n0}_{n1}_EMFLINE — yazılmadı")
        return 2
    missing = [c for c in ("ACCOUNTCODE", "KEBIRCODE", "DEBIT", "CREDIT", "CANCELLED", "DATE_", "ACCFICHEREF") if em.column(c) is None]
    if missing:
        print(f"{em.entity} profilinde kolon yok: {missing} — yazılmadı")
        return 2
    m = _mapping(em)
    print(f"ÖLÇÜ  '{TERM}' → {m.entity}: {m.formula}\n      koşullar {m.extra['conditions']}\n"
          f"      hariç grup {m.extra['exclude_groups']}\n      eş anlamlılar {SYNONYMS}")
    crm = _crm_collisions(st, s, em)
    for c, maps, keys in crm:
        where = ", ".join(str(x.entity) + "." + str(x.column or (x.formula or "")[:50]) for x in maps)
        print(f"DARALT {c.id} '{c.term}' ({where}) çakışan anahtarlar {sorted(keys)} → terim '{CRM_NEW_TERM}', "
              "çakışan eş anlamlılar çıkar; eşleme aynı")
    if a.olc:
        _measure()
    if not a.apply:
        print(f"KURU KOŞU — yazılmadı. Referans (koordinatör, 2026): {REF:,.2f} ₺. Yazmak için --apply.")
        return 0

    from semantic_layer.evidence.engine import EvidenceEngine
    from semantic_layer.models import ConceptStatus, Evidence, EvidenceType, SemanticType
    from semantic_layer.normalize import normalize_term
    reason = ("etkinlik ve fuar gideri = Logo defteri EMFLINE Σ(borç − alacak), iptal hariç, hesaplar " + ", ".join(ACCOUNTS)
              + "; aynı fişte 7x1 yansıtma satırı olan fiş (yıl sonu yansıtma/kapanış) hariç"
              + f"; 2026 = {REF:,.2f} ₺ (1.079 satır). Kayıt sistemi Logo; CRM new_ToplamEtkinlikGideri eksik alan (28 kayıt, 9.275 ₺). "
              "Etkinlik bütçesi hiçbir kaynakta yok (Kural C21).")
    # 1) CRM kavramını daralt (eşleme aynı kalır)
    for c, maps, keys in crm:
        if c.term != CRM_NEW_TERM:
            st.rename_concept(c.id, CRM_NEW_TERM)
        c2 = st.get_concept(c.id)
        keep = [x for x in (c2.synonyms or []) if normalize_term(x) not in keys]
        ex = dict(c2.explain or {})
        ex["narrowed_from"] = {"term": c.term, "by": WHO, "reason": "anahtar Logo 'etkinlik ve fuar gideri' ölçüsüne verildi (kayıt sistemi Logo)"}
        st.update_concept(c.id, synonyms=keep, explain=ex)
        print("DARALTILDI:", c.id, st.get_concept(c.id).term)
    # 2) Logo ölçüsünü yaz ve sertifikala
    c, created = st.upsert_concept(s.tenant_id, s.datasource_id, TERM, SemanticType.METRIC, mapping=m, status=ConceptStatus.CANDIDATE)
    if not created and all(dict(x.extra or {}) != dict(m.extra) or x.formula != m.formula for x in st.list_mappings(c.id)):
        st.replace_mappings(c.id, [m])
    for syn in SYNONYMS:
        st.add_synonym(c.id, syn)
    if created:
        st.add_evidence(Evidence(c.id, EvidenceType.HUMAN_ANNOTATION, SRC, support_count=1, weight=1.0,
                                 payload={"snippet": reason, "by": WHO}))
    c = st.get_concept(c.id)
    if c.status != ConceptStatus.CERTIFIED or not (c.explain or {}).get("human_certified_by"):
        EvidenceEngine(st).human_certify(c.id, WHO, reason=reason)
    print("YAZILDI:", c.id, st.get_concept(c.id).term, st.get_concept(c.id).status, "| yeni:", created)
    try:
        from semantic_bridge import admin

        admin.audit(st.engine, "operator:claude", "update", "catalog_concept", s.datasource_id,
                    "etkinlik ve fuar gideri (Logo) yazıldı; CRM etkinlik kartı gideri daraltıldı",
                    {"concept": c.id, "narrowed": [x[0].id for x in crm], "accounts": ACCOUNTS, "exclude_groups": [REFLECTION]})
    except Exception as e:  # noqa: BLE001
        print("UYARI: değişiklik kaydı yazılamadı:", e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
