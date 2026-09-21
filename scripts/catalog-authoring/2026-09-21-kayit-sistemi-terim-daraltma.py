"""Kayıt sistemi ilkesi — sözlük düzeltmesi, 2026-09-21.

İlke (ürün sahibi, 2026-09-21): gerçekleşmiş finansal olayın kayıt sistemi Logo ERP'dir. CRM'deki aynı
adlı alan çoğu zaman bir işarettir — bir onay kutusu ya da başka sistemin belge numarasının kopyası —
olayın kendisi değildir. Aşağıdaki iki kavram bu ayrımı bozuyordu; ikisi de insan değil, gece yoklaması
("otomatik-yoklama") tarafından sertifikalanmıştı ve adları taşıdıkları kolondan çok daha geniştir.

Ölçüm (salt-okunur, müşteri Logo DB, 2026-09-21):
  LG_411_01_INVOICE, 2026, TRCODE IN (2,3,7,8,9), CANCELLED = 0 → 73.660 fatura (iptal dahil 73.701).
  Katalogda bu zaten hazır: sem_442e64e4a773 'fatura sayısı' METRIC/CERTIFIED →
  COUNT(INVOICE.LOGICALREF), extra.conditions = ["INVOICE.TRCODE IN (2,3,7,8,9)"].

Yapılacak (iki madde, ikisi de kavram silmez — yalnız adı daraltır):

1) sem_e52bd82ebaf1 'fatura girişi' → NEW_REKLAMPLANIBASE.NEW_FATURASIGIRILDI (reklam planı üstünde bir
   onay kutusu). Makinenin türettiği iki eş anlamlısı olayın kendi adıdır ve her fatura sorusunu bu
   kolona çekiyor: 'fatur kesilt' (fatura kesildi) ve 'faturalant mi' (faturalandı mı). Eş anlamlılar
   kaldırılır; kavramın kendi adı ("fatura girişi") kolonun anlamını zaten doğru veriyor.

2) sem_859302325110 'kesilen fatura' → NEW_SEVKIYATBASE.NEW_FATURANUMARASI. Kolon, sevkiyat kaydının
   üstüne yazılmış fatura NUMARASIdır — başka sistemin anahtarının kopyası, fatura olayı değil. Kavram
   'sevkiyattaki fatura numarası' diye yeniden adlandırılır; eski ad eş anlamlı olarak KALMAZ (adı
   geri alınıyor, çünkü yanlıştı).

İkisi de human_certify ile imzalanır ki gece motoru eski adı geri getirmesin.

Not: bu betik sınıfı tek başına kapatmaz — kapatan şey çözücü yamasıdır (patch.diff: "kaç X" sorusu,
katalogda X için sertifikalı bir COUNT ölçüsü varsa onu okur). Bu betik, kalan "fatura kesildi /
faturalandı mı" gibi sayım sözcüğü içermeyen okumaları düzeltir.

Kullanım (README'deki satır; --apply yoksa KURU koşudur):

    sudo systemd-run --pipe --wait --collect -p User=administrator \
      -p EnvironmentFile=/etc/nanobase/semantic-bridge.env \
      -E PYTHONPATH=/data/nanobaseai/bi/frontend/backend \
      /data/nanobaseai/bi/semantic-venv/bin/python - [--apply] < apply.py
"""
import os
import sys

sys.path.insert(0, "/data/nanobaseai/bi/frontend/backend")
from semantic_layer.store.catalog_store import open_store  # noqa: E402

WHO = "operator:claude (kayıt sistemi ilkesi, 2026-09-21)"

FLAG = "sem_e52bd82ebaf1"     # 'fatura girişi' → NEW_REKLAMPLANIBASE.NEW_FATURASIGIRILDI
FLAG_DROP = ["fatur kesilt", "faturalant mi"]
FLAG_WHY = ("NEW_FATURASIGIRILDI reklam planı üstünde bir onay kutusudur: 'fatura girildi mi'. "
            "'fatura kesildi' / 'faturalandı mı' kesilen faturanın kendisini adlandırır ve o olay "
            "Logo'dadır (INVOICE). Makinenin türettiği bu iki eş anlamlı kaldırıldı — kayıt sistemi "
            "ilkesi: gerçekleşmiş finansal olay Logo'da, CRM'deki karşılığı bir işarettir.")

COPY = "sem_859302325110"     # 'kesilen fatura' → NEW_SEVKIYATBASE.NEW_FATURANUMARASI
COPY_NEW_TERM = "sevkiyattaki fatura numarası"
COPY_WHY = ("NEW_FATURANUMARASI sevkiyat kaydına yazılmış fatura NUMARASIdır — Logo'daki belgenin "
            "numara kopyası, faturanın kendisi değil. 'kesilen fatura' adı bütün fatura sorularını "
            "CRM'e çekiyordu; ad kolonun gerçek anlamına daraltıldı.")

st = open_store(os.environ["SEMANTIC_STORE_DSN"])

print("=== ÖNCE")
for cid in (FLAG, COPY):
    c = st.get_concept(cid)
    if c is None:
        print(cid, "yok — katalog değişmiş, betik gözden geçirilmeli")
        sys.exit(1)
    print(f"{cid} | {c.term!r} | {c.semantic_type} {c.status} v{c.version} | eş anlamlı={list(c.synonyms)} "
          f"| {[(m.entity, m.column) for m in st.list_mappings(cid)]}")

flag = st.get_concept(FLAG)
copy = st.get_concept(COPY)
keep = [s for s in flag.synonyms if s not in FLAG_DROP]
drop = [s for s in flag.synonyms if s in FLAG_DROP]
todo = []
if drop:
    todo.append(f"{FLAG}: eş anlamlı {drop} kaldırılacak → kalan {keep}; human_certify({WHO})")
if copy.term != COPY_NEW_TERM:
    todo.append(f"{COPY}: ad {copy.term!r} → {COPY_NEW_TERM!r} (eski ad eş anlamlı olarak kalmaz); human_certify({WHO})")

print("\n=== YAPILACAK")
for line in todo or ["yapılacak iş yok — katalog zaten düzeltilmiş"]:
    print(" -", line)
if not todo:
    sys.exit(0)
print("\nGEREKÇE 1:", FLAG_WHY)
print("GEREKÇE 2:", COPY_WHY)

if "--apply" not in sys.argv:
    print("\nKURU KOŞU — hiçbir şey yazılmadı. Yazmak için --apply; sonra POST /api/v1/semantic/reload "
          "ve resolver-gate.py (yalnız fatura okumaları değişmeli).")
    sys.exit(0)

from semantic_layer.evidence.engine import EvidenceEngine  # noqa: E402
eng = EvidenceEngine(st)
if drop:
    st.update_concept(FLAG, synonyms=keep, bump_version=True)
    eng.human_certify(FLAG, WHO, FLAG_WHY)
if copy.term != COPY_NEW_TERM:
    st.rename_concept(COPY, COPY_NEW_TERM)
    eng.human_certify(COPY, WHO, COPY_WHY)

print("\n=== SONRA")
for cid in (FLAG, COPY):
    c = st.get_concept(cid)
    print(f"{cid} | {c.term!r} | {c.status} v{c.version} | eş anlamlı={list(c.synonyms)}")
