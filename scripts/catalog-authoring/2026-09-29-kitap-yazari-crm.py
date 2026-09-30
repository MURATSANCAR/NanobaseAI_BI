"""ZEKI-54 (2026-09-29): "… kanal kitap adı yazar ve yayınevi" — yazar yalnız CRM'de, katalogda karşılığı yok.

Logo'da yazar alanı YOK (canlı ölçüm 2026-09-29: sys.sql_modules'ta YAZAR geçen görünüm 0; ITEMS SPECODE..SPECODE5 /
PRODUCERCODE boş ya da yayınevi). Kitabın yazarı CRM eser katılım kaydıdır (editorial.py / author_growth.py ile aynı bağ):
    new_eserkatilimBase e  (statecode = 0)
      e.new_katilimciTipi  → new_katilimcitipiBase.new_name = N'Yazar'
      e.new_Katilimsaglayan → ContactBase.ContactId      (ad: ContactBase.FullName)
      e.new_Kitap           → new_kitapBase.new_kitapId  (Logo bağı: new_kitapBase.new_StokKodu = LG_ITEMS.CODE)

Bu betik:
  1) CRM'de (salt okunur) tanımı ölçer: etkin «Yazar» katılımı, kitap/kişi sayısı, stok kodu dolu kitap; Logo'da (salt okunur)
     o stok kodlarının ITEMS.CODE ile eşleşme oranı. İki kaynak ayrı sunucu: iki ayrı sorgu, eşleşme bellekte.
  2) Kataloğun iki sunuculu plan için ihtiyaç duyduğu ölçülmüş bağı denetler: NEW_KITAPBASE.NEW_STOKKODU ↔ ITEMS.CODE
     (`cross_source`). Yoksa yazmaz; keşif komutunu basar (backend/scripts/discover_cross_links.py → apply_cross_links.py).
  3) --apply ile COLUMN kavramı yazar: «kitap yazarı» → CONTACTBASE.FULLNAME, koşul/yol mapping.extra'da; human_certify.
     Eş anlamlılar: «kitabın yazarı», «yazar adı». Çıplak «yazar» eş anlamlısı YALNIZ --kisa-ad ile eklenir: aynı kelime
     sözleşme sorularında hak sahibidir (Kural C9: new_sozlesmetarafiBase kişi/firma) ve tek kelimelik eş anlamlı o soruları
     bu kavrama çekebilir. --kisa-ad'dan sonra hızlı kapı (resolver-gate.py set100) ve set1000'de «yazar» geçen sorular
     önce/sonra karşılaştırılmadan canlıda bırakılmaz.

Plan KAPALI kurulumda (müşteri VM'i) bu kavram soruyu iki sunucuya taşımaz: çözümleyici kolon rolündeki öteki-sunucu
terimini cevaba almaz ve cümleyle söyler (resolver._omit_column). Plan AÇIK kurulumda iki sunuculu plan yazarı bu
kavram + ölçülmüş stok kodu bağıyla okuyabilir.

Koşu (köprünün ortamıyla, test sunucusunda; README'deki satır):
    sudo systemd-run --pipe --wait --collect -p User=administrator \\
      -p EnvironmentFile=/etc/nanobase/semantic-bridge.env \\
      -E PYTHONPATH=/data/nanobaseai/bi/frontend/backend \\
      /data/nanobaseai/bi/semantic-venv/bin/python - [--apply] [--kisa-ad] < scripts/catalog-authoring/2026-09-29-kitap-yazari-crm.py
Sonra: POST /api/v1/semantic/reload → resolver-gate.py set100.jsonl → answer-gate.py --only <yazar soruları>.
Kuru koşu varsayılan.
"""
import datetime
import os
import sys

sys.path.insert(0, "/data/nanobaseai/bi/frontend/backend")
from semantic_layer.evidence.engine import EvidenceEngine
from semantic_layer.models import ConceptStatus, Evidence, EvidenceType, Mapping, SemanticType
from semantic_layer.normalize import normalize_term
from semantic_layer.profiler.connectors import connector_from_file
from semantic_layer.store.catalog_store import open_store

WHO = "operator:claude (ZEKI-54, 2026-09-29)"
TENANT, DS = os.environ.get("SEMANTIC_TENANT_ID", "default"), os.environ.get("SEMANTIC_DATASOURCE_ID", "logo")
TERM = "kitap yazarı"
SYNONYMS = ["kitabın yazarı", "yazar adı"]
SHORT = ["yazar", "yazarı"]
CRM = (os.environ.get("CRM_SCHEMA") or "Timas_MSCRM.dbo").rstrip(".") + "."
CRM_FILE = os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json")
LOGO_FILE = os.environ.get("SEMANTIC_CONNECTION_FILE", "")
APPLY, SHORT_NAME = "--apply" in sys.argv, "--kisa-ad" in sys.argv


def rows(conn, sql, limit=200000):
    _cols, out, _trunc = conn.execute(sql, limit)
    return [r if isinstance(r, dict) else dict(zip([c["name"] for c in _cols], r)) for r in out]


# ------------------------------------------------------------------ 1) ölçüm (salt okunur)
crm = connector_from_file(CRM_FILE)
base = (f" FROM {CRM}new_eserkatilimBase e"
        f" JOIN {CRM}new_katilimcitipiBase t ON t.new_katilimcitipiId = e.new_katilimciTipi"
        f" JOIN {CRM}ContactBase k ON k.ContactId = e.new_Katilimsaglayan"
        f" JOIN {CRM}new_kitapBase b ON b.new_kitapId = e.new_Kitap"
        f" WHERE e.statecode = 0 AND b.statecode = 0 AND t.new_name = N'Yazar'")
m = rows(crm, "SELECT COUNT(*) AS katilim, COUNT(DISTINCT e.new_Kitap) AS kitap, COUNT(DISTINCT e.new_Katilimsaglayan) AS yazar,"
              " COUNT(DISTINCT CASE WHEN LTRIM(RTRIM(ISNULL(b.new_StokKodu, ''))) <> '' THEN e.new_Kitap END) AS stoklu_kitap" + base)[0]
print("CRM «Yazar» katılımı:", m)
multi = rows(crm, "SELECT COUNT(*) AS n FROM (SELECT e.new_Kitap" + base + " GROUP BY e.new_Kitap HAVING COUNT(DISTINCT e.new_Katilimsaglayan) > 1) x")[0]
print("birden çok yazarlı kitap:", multi, "→ kitap bazında yazar kırılımı satırı çoğaltır; ölçü önce kitap/stok koduna indirilmeli")
codes = {str(r["kod"]).strip() for r in rows(crm, "SELECT DISTINCT LTRIM(RTRIM(b.new_StokKodu)) AS kod" + base
                                                   + " AND LTRIM(RTRIM(ISNULL(b.new_StokKodu, ''))) <> ''") if r.get("kod")}
if LOGO_FILE:
    logo = connector_from_file(LOGO_FILE)
    firm = os.environ.get("SEMANTIC_LOGO_ITEMS_TABLE", "LG_411_ITEMS")
    items = {str(r["kod"]).strip() for r in rows(logo, f"SELECT DISTINCT LTRIM(RTRIM(CODE)) AS kod FROM dbo.{firm}")}
    hit = len(codes & items)
    print(f"Logo {firm}: CRM yazarlı stok kodu {len(codes)}, ITEMS.CODE ile eşleşen {hit} (%{100 * hit / max(1, len(codes)):.1f})")
else:
    print("SEMANTIC_CONNECTION_FILE yok: Logo eşleşmesi ölçülmedi")

# ------------------------------------------------------------------ 2) katalog: profiller ve ölçülmüş bağ
st = open_store(os.environ["SEMANTIC_STORE_DSN"])
profs = {(p.entity or "").upper(): p for p in st.list_profiles(DS)}
need = ["CONTACTBASE", "NEW_ESERKATILIMBASE", "NEW_KATILIMCITIPIBASE", "NEW_KITAPBASE"]
missing = [e for e in need if e not in profs]
print("profiller:", {e: (profs[e].table_pattern if e in profs else "YOK") for e in need})
bridge = [r for r in (profs["NEW_KITAPBASE"].relationships or []) if isinstance(r, dict) and r.get("cross_source")] if "NEW_KITAPBASE" in profs else []
stok = [r for r in bridge if str(r.get("column", "")).upper() == "NEW_STOKKODU" and str(r.get("ref_column", "")).upper() == "CODE"]
print("ölçülmüş stok kodu bağı:", stok or "YOK")
if not stok:
    print("  → önce ölç ve yaz (iki bağlantı, salt okunur keşif):\n"
          "    python -m scripts.discover_cross_links --out /var/tmp/kitaplinks --connection <logo.json> --connection <crm.json> \\\n"
          "      --oracle NEW_KITAPBASE.new_StokKodu=LG_ITEMS.CODE\n"
          "    python backend/scripts/apply_cross_links.py /var/tmp/kitaplinks/apply_plan.json [--apply]")
existing = [c for c in st.find_concepts(TENANT, DS, normalized_term=normalize_term(TERM), limit=20)]
short = [c for t in SHORT for c in st.find_concepts(TENANT, DS, normalized_term=normalize_term(t), limit=20)]
print("var olan:", [(c.id, c.term, c.semantic_type, c.status) for c in existing + short])
if missing:
    raise SystemExit(f"profil eksik ({', '.join(missing)}): kavram yazılmaz — önce CRM taraması")

# ------------------------------------------------------------------ 3) kavram
cond = ["NEW_ESERKATILIMBASE.STATECODE IN (0)", "NEW_KITAPBASE.STATECODE IN (0)", "NEW_KATILIMCITIPIBASE.NEW_NAME IN ('Yazar')"]
path = ("NEW_KITAPBASE.NEW_KITAPID = NEW_ESERKATILIMBASE.NEW_KITAP; "
        "NEW_ESERKATILIMBASE.NEW_KATILIMSAGLAYAN = CONTACTBASE.CONTACTID; "
        "NEW_ESERKATILIMBASE.NEW_KATILIMCITIPI = NEW_KATILIMCITIPIBASE.NEW_KATILIMCITIPIID; "
        "Logo: NEW_KITAPBASE.NEW_STOKKODU = ITEMS.CODE")
mapping = Mapping(concept_id="", entity="CONTACTBASE", table_pattern=profs["CONTACTBASE"].table_pattern, column="FULLNAME",
                  operator="COLUMN", extra={"conditions": cond, "path": path, "grain": "NEW_ESERKATILIMBASE"})
syn = SYNONYMS + (SHORT if SHORT_NAME else [])
print("YAZILACAK:", TERM, "→ CONTACTBASE.FULLNAME |", cond, "| yol:", path, "| eş:", syn)
if not APPLY:
    raise SystemExit("KURU KOŞU — yazılmadı. Uygulamak için: --apply (çıplak «yazar» için ayrıca --kisa-ad)")

now = datetime.datetime.now(datetime.timezone.utc).isoformat()
c, created = st.upsert_concept(TENANT, DS, TERM, SemanticType.COLUMN, mapping=mapping, status=ConceptStatus.CANDIDATE)
if not created:
    st.replace_mappings(c.id, [mapping])
for s in syn:
    st.add_synonym(c.id, s)
cur = st.get_concept(c.id)
ex = dict(cur.explain or {})
src = dict(ex.get("synonym_sources") or {})
for s in syn:
    src[normalize_term(s)] = {"by": WHO, "source": "ZEKI-54: kitabın yazarı CRM eser katılımıdır", "at": now}
st.update_concept(c.id, explain={"synonym_sources": src,
                                 "declared_synonyms": sorted(set(ex.get("declared_synonyms") or []) | {normalize_term(s) for s in syn}),
                                 "definition": "Kitabın yazarı: etkin eser katılımı, rol «Yazar», kişi adı ContactBase.FullName. " + path})
st.add_evidence(Evidence(c.id, EvidenceType.HUMAN_ANNOTATION, "operator:2026-09-29:kitap-yazari", support_count=1, weight=1.0,
                         payload={"snippet": f"yazar = eser katılımı rol Yazar (ölçüm: {m})", "by": WHO}))
EvidenceEngine(st).human_certify(c.id, WHO, reason="ZEKI-54: yazar yalnız CRM'de; tanım editorial.py/author_growth.py ile aynı bağ, canlı ölçüldü")
c = st.get_concept(c.id)
print("YAZILDI:", c.id, c.term, c.status, c.synonyms)
