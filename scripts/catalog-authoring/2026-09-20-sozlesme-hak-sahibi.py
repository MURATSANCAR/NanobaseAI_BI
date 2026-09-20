"""Kural C9 düzeltmesi — 2026-09-20. 'sözleşme sahibi = yazar' tanımı yanlıştı; katalogdaki karşılığı geri alınır.

Ölçüm (salt-okunur, CRM prod 192.168.0.28, connector_from_file ile, 2026-09-20):
  NEW_SOZLESMEBASE.new_SozlemeninSahibi → AccountBase aktif 14.829 sözleşmede 36 hesaba gidiyor; ilk sıralar TİMAŞ BASIM
  (11.173 + 1.563 + 147), LM LEYLA İLE MECNUN 510, LACİVERT 493, Mavi Kirpi 172, YUZU KİTAP 107 — grubun kendi şirketleri.
  Dynamics'te alanın adı "Sözleşmedeki Resmi Ad (Timaş Tarafı)", açıklaması "Sözleşmenin Muhatabı Olan Firma ( Bizim Firma)".
  Gerçek hak sahibi taraf kaydında: NEW_SOZLESMETARAFIBASE.new_kisi (8.961) / new_Firma (7.685), 16.442 aktif taraf.

Yapılan: sem_545a9731b346 'sözleşme sahibi' (→ ACCOUNTBASE.Name; eş anlamlı: hak sahibi, sözleşmenin sahibi, yazarlara
göre; 2026-09-18 operatör sertifikası) REDDEDİLİR. Yerine yeni kavram yazılmaz: kolonun doğru kavramı zaten var
(sem_1a084792c6de 'sözleşme sahibi firma' → NEW_SOZLESMEBASE.NEW_SOZLEMENINSAHIBI, eş anlamlı 'bizim firma'), hak sahibi
kavramları da taraf tablosunda duruyor (sem_c1aeac19c1ac 'hak sahibi kişi' → NEW_KISI). Kişi-ya-da-firma birleşimi tek
kolon eşlemesiyle anlatılamaz; onu Kural C9 anlatır.

Kullanım: README'deki systemd-run satırı; --apply yoksa kuru koşu.
"""
import os, sys
sys.path.insert(0, "/data/nanobaseai/bi/frontend/backend")
from semantic_layer.store.catalog_store import open_store
from semantic_layer.models import ConceptStatus, CounterEvidence

WRONG, RIGHT = "sem_545a9731b346", ("sem_1a084792c6de", "sem_c1aeac19c1ac")
WHO = "operator:claude (2026-09-20, doğrudan CRM ölçümü)"
WHY = ("yanlış tanım: new_SozlemeninSahibi yazar/hak sahibi değil, sözleşmeyi imzalayan grup şirketimiz "
       "(alan adı 'Sözleşmedeki Resmi Ad (Timaş Tarafı)'; değerler TİMAŞ Basım, Leyla ile Mecnun, Lacivert…). "
       "Hak sahibi NEW_SOZLESMETARAFIBASE.new_kisi / new_Firma — Kural C9. Kolonun doğru kavramı sem_1a084792c6de.")

st = open_store(os.environ["SEMANTIC_STORE_DSN"])
for cid in (WRONG,) + RIGHT:
    c = st.get_concept(cid)
    print(cid, "|", c.term, "|", c.status, "| synonyms=", list(c.synonyms),
          "|", [(m.entity, m.column) for m in st.list_mappings(cid)])
c = st.get_concept(WRONG)
if c.status == ConceptStatus.REJECTED:
    print("zaten reddedilmiş — yapılacak iş yok")
    sys.exit(0)
print("YAPILACAK:", WRONG, "→ REJECTED |", WHY)
if "--apply" not in sys.argv:
    print("KURU KOŞU — hiçbir şey yazılmadı. Yazmak için --apply; sonra POST /api/v1/semantic/reload ve hızlı kapı.")
    sys.exit(0)
st.add_counter_evidence(CounterEvidence(WRONG, f"human:{WHO}", "HUMAN_REJECT", payload={"reason": WHY, "support": 3}, severity="BLOCKING"))
c = st.update_concept(WRONG, status=ConceptStatus.REJECTED, explain={"human_rejected_by": WHO, "human_reason": WHY}, bump_version=True)
print("SONRA:", c.id, c.term, c.status, "v", c.version)
