"""2. adım — parti 1: kavramı olmayan Logo tablolarına, çürütmeden geçmiş aday kavramlar.

Parti: LG_SHIPINFO/SHIPINFO, OCCUPATION, EMUHACC, POLINE, SRVCARD, FAREGIST, INVDEF.
Her aday önce KIRILMAYA çalışıldı (bkz. ADAYLAR.md): kolon gerçekten dolu mu, sayı başka bir
tablodan da çıkıyor mu (çift sayma), terim bugün başka bir kavrama mı bağlı. Kırılanlar bu dosyada
YOK — yalnız gerekçeleriyle ADAYLAR.md'de duruyorlar.

Kipler (h4 betiğiyle aynı):
  (varsayılan)             KURU KOŞU: ne yazılacağını ve çakışmaları basar, hiçbir şey yazmaz.
  --simulate dosya.jsonl…  YAZMADAN ölçüm: adaylar yalnız bellekteki dizine eklenir, sorular
                           köprüyle aynı kurulan çözücüye önce/sonra okutulur, değişen basılır.
  --apply                  yazar (idempotent; human_certify ile, gece motoru geri almasın).
  --narrow-sabit-kiymet    AYRI İŞ KARARI (varsayılan kapalı): 'sabit kiymet' DIMENSION_VALUE
                           kavramının (STLINE.LINETYPE IN (8), rule-miner) terimini
                           'sabit kıymet satırı' yapar — 'hizmet satırı' (LINETYPE 4) ile aynı
                           kalıp. Mapping'e DOKUNMAZ. Gerekçe: bkz. ADAYLAR.md §FAREGIST.

Sunucuda, köprünün ortamıyla (dosya kopyalamadan, stdin'den):
  sudo systemd-run --pipe --wait --collect --quiet -p User=administrator \
     -p EnvironmentFile=/etc/nanobase/semantic-bridge.env -p WorkingDirectory=/data/nanobaseai/bi/frontend/backend \
     -E PYTHONPATH=/data/nanobaseai/bi/frontend/backend /data/nanobaseai/bi/semantic-venv/bin/python - [--apply] < apply.py
"""
from __future__ import annotations

import json
import sys

WHO = "operator:claude (parti 1, 2026-09-21)"
SRC = "operator:adim2-parti1-logo-kapsam"

#: --narrow-sabit-kiymet: terimi daraltılacak kavram (mapping'e dokunulmaz).
NARROW = [("sem_6e4f6a20811d", "sabit kıymet satırı")]
NARROW_REASON = (
    "'sabit kıymet' bugün STLINE.LINETYPE IN (8) üstünde bir DIMENSION_VALUE (rule-miner). Kolon eşlemesi "
    "DOĞRU ama terim fazla geniş: canlıda (LG_411) LINETYPE=8 yalnız 60 satır / 3.469.868 ₺; sabit kıymetlerin "
    "kendisi FAREGIST'te (1.079 kayıt / 99.504.559 ₺ giriş maliyeti). 'Sabit kıymetlerimiz ne kadar' sorusu "
    "bugün 3,5 Mn ₺ döner. LINETYPE=4 kardeşi zaten 'hizmet satırı' adını taşıyor; aynı kalıp uygulanır."
)


def definitions(entity_of, column_of) -> list[dict]:
    """entity_of(kalıp) → entity adı | None; column_of(entity, kolon) → profildeki yazımı | None."""
    out: list[dict] = []
    sh = entity_of("VW_{n0}_SHIPINFO")          # teslimat bilgisi görünümü (CARI_* ile hazır bağlı)
    oc = entity_of("LG_{n0}_OCCUPATION")
    ea = entity_of("LG_{n0}_EMUHACC")
    pl = entity_of("LG_{n0}_POLINE")
    sv = entity_of("LG_{n0}_SRVCARD")
    fa = entity_of("LG_{n0}_FAREGIST")

    def need(entity, pattern, cols):
        if not entity:
            return f"profil yok: {pattern}"
        missing = [c for c in cols if not column_of(entity, c)]
        return f"{entity} profilinde kolon yok: {', '.join(missing)}" if missing else ""

    def add(**d):
        d.setdefault("synonyms", [])
        d.setdefault("extra", {})
        out.append(d)

    # ---------------------------------------------------------------- LG_SHIPINFO / SHIPINFO
    # Kavramlar bilerek GÖRÜNÜM entity'sine (SHIPINFO) yazılır: 'gönderim şehri' (sem_8361970a8cc5)
    # zaten orada. Taban tabloya (LG_SHIPINFO) yazmak aynı veriyi iki entity'ye bölerdi
    # ("entity adı tarama kapsamına bağlı" hatasının aynısı).
    skip_sh = need(sh, "VW_{n0}_SHIPINFO", ["LOGICALREF", "CITY", "TOWN", "COUNTRY", "CLIENTREF"])
    # ÇÜRÜTME: 'teslimat bilgisi' / 'teslimat bilgileri' anahtarı (teslimat bilk) bugün CRM'de
    # sem_1eefa73533f8 'ürün teslim bilgisi' (ACCOUNTBASE.NEW_URUNTESLIMBILGISI) üstünde. Aynı anahtarda
    # iki sertifikalı kavram çözücüyü ikileme sokardı → terim 'teslimat kartı'na çekildi.
    add(key="teslimat-karti", term="teslimat kartı", type="ENTITY", entity=sh,
        pattern="VW_{n0}_SHIPINFO", skip=skip_sh,
        synonyms=["teslimat adresi kartı", "sevkiyat adresi kartı"],
        reason="tanım: teslimat kartı = Logo SHIPINFO kartı (fatura/irsaliye/siparişin gideceği adres). "
               "Canlı LG_411: 370.630 kart, 238.287 farklı cari. Fatura 69.577/81.801, irsaliye 72.517/101.695, "
               "sipariş 48.685/48.687 kayıtta SHIPINFOREF dolu. İş teyidi bekliyor.")
    add(key="teslimat-ilcesi", term="teslimat ilçesi", type="COLUMN", entity=sh,
        pattern="VW_{n0}_SHIPINFO", column="TOWN", operator="COLUMN", skip=skip_sh,
        synonyms=["teslimat ilçeleri"],
        reason="tanım: teslimat ilçesi = SHIPINFO.TOWN. Canlı LG_411: 365.752/370.630 dolu (%98,7). "
               "'teslimat semt' anahtarı CRM'e (NEW_ONLINESIPARISBASE.NEW_SEMT), 'gönderim ilçesi' ise "
               "sem_9b82ace134ba'ya (NEW_ONLINESIPARISBASE.NEW_ILCE) bağlı olduğu için o iki öbek bilerek "
               "kullanılmadı. İş teyidi bekliyor.")
    add(key="teslimat-ulkesi", term="teslimat ülkesi", type="COLUMN", entity=sh,
        pattern="VW_{n0}_SHIPINFO", column="COUNTRY", operator="COLUMN", skip=skip_sh,
        synonyms=["teslimat ülkeleri"],
        reason="tanım: teslimat ülkesi = SHIPINFO.COUNTRY. Canlı LG_411: 370.416/370.630 dolu (%99,9). "
               "'gönderim ülkesi' öbeği sem_0e5a598a8503'e (NEW_ONLINESIPARISBASE.NEW_ULKE) bağlı olduğu "
               "için verilmedi. İş teyidi bekliyor.")

    # ---------------------------------------------------------------- OCCUPATION
    # Süre ölçüleri ÇÜRÜTÜLDÜ (ADAYLAR.md): planlanan süre DISPLINE.PLNDURATION'ın birebir kopyası
    # (8.848.628 = 8.848.628 → çift sayma), gerçekleşen sürenin birimi doğrulanamadı.
    # Geriye yalnız entity kalır; ölçü yazılmaz.
    skip_oc = need(oc, "LG_{n0}_OCCUPATION", ["LOGICALREF", "PRODORDREF", "DISPLINEREF", "OCCSTATUS"])
    add(key="kaynak-kullanimi", term="üretimde kaynak kullanımı", type="ENTITY", entity=oc,
        pattern="LG_{n0}_OCCUPATION", skip=skip_oc,
        synonyms=["kaynak kullanım kaydı", "üretim kaynak kullanımı"],
        reason="tanım: üretimde kaynak kullanımı = OCCUPATION kaydı; iş emri satırının (DISPLINEREF) "
               "kaynak kırılımı. Canlı LG_411: 32.937 kayıt, 1.221 üretim emri, 21 çalışan (EMPREF), "
               "OCCTYPE hepsi 4 (işgücü), TOOLREF hepsi 0. SÜRE ÖLÇÜSÜ BİLEREK YOK: planlanan süre "
               "DISPLINE.PLNDURATION ile birebir aynı (8.848.628), gerçekleşen sürenin birimi "
               "doğrulanamadı. İş teyidi bekliyor.")

    # ---------------------------------------------------------------- EMUHACC
    skip_ea = need(ea, "LG_{n0}_EMUHACC", ["LOGICALREF", "CODE", "DEFINITION_", "LEVEL_"])
    add(key="muhasebe-hesabi", term="muhasebe hesabı", type="ENTITY", entity=ea,
        pattern="LG_{n0}_EMUHACC", skip=skip_ea,
        synonyms=["muhasebe hesapları", "muhasebe hesap planı", "genel muhasebe hesabı"],
        reason="tanım: muhasebe hesabı = Logo EMUHACC hesap planı kartı; yevmiye satırına "
               "EMFLINE.ACCOUNTREF = EMUHACC.LOGICALREF ile bağlanır. Canlı LG_411: 1.374 hesap "
               "(CODE ve DEFINITION_ %100 dolu), 3 seviye, 23'ü kullanım dışı; EMFLINE'ın 246.404 "
               "satırının %100'ünde ACCOUNTREF dolu. İş teyidi bekliyor.")
    add(key="muhasebe-hesap-kodu", term="muhasebe hesap kodu", type="COLUMN", entity=ea,
        pattern="LG_{n0}_EMUHACC", column="CODE", operator="COLUMN", skip=skip_ea,
        synonyms=["muhasebe hesap kodları", "genel muhasebe hesap kodu"],
        reason="tanım: muhasebe hesap kodu = EMUHACC.CODE (tekdüzen hesap planı kodu, ör. 102.01.001). "
               "Canlı LG_411: 1.374/1.374 dolu; 1–9 ana grubunun hepsi var. İş teyidi bekliyor.")
    add(key="muhasebe-hesap-adi", term="muhasebe hesap adı", type="COLUMN", entity=ea,
        pattern="LG_{n0}_EMUHACC", column="DEFINITION_", operator="COLUMN", skip=skip_ea,
        synonyms=["muhasebe hesap adları", "muhasebe hesap açıklaması"],
        reason="tanım: muhasebe hesap adı = EMUHACC.DEFINITION_. Canlı LG_411: 1.374/1.374 dolu "
               "(ör. 'Y.İçi TL Alıcılar', 'Portföydeki Çekler'). İş teyidi bekliyor.")

    # ---------------------------------------------------------------- POLINE
    # 'üretim emri planlanan üretim miktarı' ÇÜRÜTÜLDÜ: LINETYPE=4 toplamı (8.848.628) PRODORD.PLNAMOUNT
    # toplamıyla birebir aynı → çift sayma.
    skip_pl = need(pl, "LG_{n0}_POLINE", ["LOGICALREF", "PRODORDREF", "LINETYPE", "AMOUNT", "ITEMREF"])
    add(key="uretim-emri-satiri", term="üretim emri satırı", type="ENTITY", entity=pl,
        pattern="LG_{n0}_POLINE", skip=skip_pl,
        synonyms=["üretim emri satırları", "üretim emri kalemi"],
        reason="tanım: üretim emri satırı = POLINE; emrin (PRODORDREF) malzeme ve mamul kalemleri. "
               "Canlı LG_411: 4.491 satır / 1.221 emir; LINETYPE 0 = sarf edilecek malzeme (3.270 satır), "
               "LINETYPE 4 = üretilecek mamul (1.221 satır). Başlık kavramı 'baskı' (PRODORD) sertifikalı; "
               "bu kavram bilerek yalnız 'üretim emri satırı' öbeğini taşır, 'üretim emri' öbeğini DEĞİL. "
               "İş teyidi bekliyor.")
    add(key="uretim-emri-planlanan-malzeme", term="üretim emri planlanan malzeme miktarı", type="METRIC",
        entity=pl, pattern="LG_{n0}_POLINE", column="AMOUNT", skip=skip_pl,
        formula=(f"SUM({pl}.AMOUNT)" if pl else ""),
        extra={"func": "SUM", "grain": pl, "aliases": ["uretim_emri_planlanan_malzeme"],
               "conditions": ([f"{pl}.LINETYPE IN (0)"] if pl else []),
               **({"link": f"{pl}.PRODORDREF = PRODORD.LOGICALREF"} if pl else {})},
        synonyms=["üretim emri malzeme planı", "üretim emrinde planlanan malzeme"],
        reason="tanım: üretim emrinin PLANLANAN malzeme miktarı = Σ POLINE.AMOUNT, LINETYPE=0. Canlı LG_411: "
               "7.769.499,91. FİİLİ sarftan ayrıdır ('çekilen malzeme' = STLINE TRCODE 12/IOCODE 4, "
               "20.211.220,23) — bu yüzden 'sarf miktarı / malzeme sarfı' eş anlamlıları BİLEREK verilmedi "
               "(o anahtarlar sem_761633159662'ye bağlı). İş teyidi bekliyor.")

    # ---------------------------------------------------------------- SRVCARD
    skip_sv = need(sv, "LG_{n0}_SRVCARD", ["LOGICALREF", "CODE", "DEFINITION_", "CARDTYPE"])
    add(key="hizmet-karti", term="hizmet kartı", type="ENTITY", entity=sv,
        pattern="LG_{n0}_SRVCARD", skip=skip_sv,
        synonyms=["hizmet kartları", "hizmet tanımı"],
        reason="tanım: hizmet kartı = Logo SRVCARD; fatura/irsaliyenin hizmet satırına "
               "STLINE.STOCKREF = SRVCARD.LOGICALREF (STLINE.LINETYPE = 4) ile bağlanır. Canlı LG_411: "
               "232 kart (204 alınan, 26 verilen), 108'i 2026'da kullanılmış, 19.905 hizmet satırı / "
               "305.014.447 ₺ net. DİKKAT: 'hizmet kartı' anahtarı bugün sem_77a33538f993'e "
               "(COSTDISTLN.SRVREF, otomatik-yoklama) bağlı — kuru koşu çakışmayı basar. İş teyidi bekliyor.")
    add(key="hizmet-karti-adi", term="hizmet kartı adı", type="COLUMN", entity=sv,
        pattern="LG_{n0}_SRVCARD", column="DEFINITION_", operator="COLUMN", skip=skip_sv,
        synonyms=["hizmet kartı açıklaması", "hizmet adı"],
        reason="tanım: hizmet kartı adı = SRVCARD.DEFINITION_. Canlı LG_411: 230/232 dolu "
               "(ör. 'Komple Baskı Giderleri' 64.150.247 ₺, 'Yazarların Telif Ücreti' 51.528.186 ₺). "
               "İş teyidi bekliyor.")
    add(key="hizmet-karti-kodu", term="hizmet kartı kodu", type="COLUMN", entity=sv,
        pattern="LG_{n0}_SRVCARD", column="CODE", operator="COLUMN", skip=skip_sv,
        synonyms=["hizmet kodu"],
        reason="tanım: hizmet kartı kodu = SRVCARD.CODE (muhasebe hesabıyla aynı düzen, ör. 730.38.381). "
               "Canlı LG_411: 232/232 dolu. İş teyidi bekliyor.")
    add(key="alinan-hizmet-karti", term="alış hizmet kartı", type="DIMENSION_VALUE", entity=sv,
        pattern="LG_{n0}_SRVCARD", column="CARDTYPE", operator="IN", values=["1"], skip=skip_sv,
        synonyms=["gider hizmet kartı"],
        reason="tanım: alış hizmet kartı = SRVCARD.CARDTYPE = 1 (alınan hizmet, gider tarafı). Canlı LG_411: 204 kart; "
               "2026 hizmet satırlarının 15.296'sı / 293.622.955 ₺ bu tarafta. 'alinan hizmet' anahtarı "
               "INVOICE.TRCODE'a bağlı; ayrıca 'alınan hizmet kartı' yazımı set1000/K0832'de «onayı alınmadan» "
               "olumsuzluk etiketini düşürüyordu (ölçüldü) → terim 'alış …' köküne çekildi. İş teyidi bekliyor.")
    add(key="verilen-hizmet-karti", term="satış hizmet kartı", type="DIMENSION_VALUE", entity=sv,
        pattern="LG_{n0}_SRVCARD", column="CARDTYPE", operator="IN", values=["2"], skip=skip_sv,
        synonyms=["gelir hizmet kartı"],
        reason="tanım: satış hizmet kartı = SRVCARD.CARDTYPE = 2 (verilen hizmet, gelir tarafı). Canlı LG_411: 26 kart; "
               "2026 hizmet satırlarının 4.609'u / 11.391.492 ₺ bu tarafta. İş teyidi bekliyor.")

    # ---------------------------------------------------------------- FAREGIST
    skip_fa = need(fa, "LG_{n0}_FAREGIST", ["LOGICALREF", "INVALUE", "ACCUMDEPR", "DEPRRATE",
                                            "REGDEFINITION", "CANCELLED", "DATEIN", "CRDREF"])
    cancelled = [f"{fa}.CANCELLED IN (0)"] if fa else []
    add(key="sabit-kiymet-kaydi", term="sabit kıymet kaydı", type="ENTITY", entity=fa,
        pattern="LG_{n0}_FAREGIST", skip=skip_fa,
        synonyms=["sabit kıymet kayıtları", "demirbaş kaydı", "demirbaş kayıtları"],
        reason="tanım: sabit kıymet kaydı = Logo FAREGIST; bir demirbaşın tek bir alım/aktarım kaydı. "
               "Canlı LG_411: 1.079 kayıt, 4'ü iptal, 15 sabit kıymet kartına (ITEMS.CARDTYPE = 4, ör. "
               "'ARSALAR', 'TİCARİ TAŞITLAR', 'BİLGİSAYARLAR') CRDREF ile bağlı; DATEIN 1991–2026. "
               "İş teyidi bekliyor.")
    add(key="sabit-kiymet-giris-maliyeti", term="sabit kıymet giriş maliyeti", type="METRIC", entity=fa,
        pattern="LG_{n0}_FAREGIST", column="INVALUE", skip=skip_fa,
        formula=(f"SUM({fa}.INVALUE)" if fa else ""),
        extra={"func": "SUM", "grain": fa, "aliases": ["sabit_kiymet_giris_maliyeti"], "conditions": cancelled},
        synonyms=["demirbaş alım bedeli", "sabit kıymet alım bedeli", "demirbaş giriş maliyeti"],
        reason="tanım: sabit kıymet giriş maliyeti = Σ FAREGIST.INVALUE, iptaller hariç (CANCELLED = 0). "
               "Canlı LG_411: 99.504.558,83 ₺ (iptal dâhil), 1.055/1.079 kayıtta dolu; en büyük kalemler "
               "ARSALAR 39.471.576 ₺, TİCARİ TAŞITLAR 17.478.619 ₺. 'sabit kıymet' TEK BAŞINA eş anlamlı "
               "olarak VERİLMEDİ: o anahtar bugün STLINE.LINETYPE IN (8) üstünde. İş teyidi bekliyor.")
    # ÇÜRÜTME (set1000/K0807): terim 'birikmiş amortisman' iken 'birikmis' kelimesi katalogda YENİ
    # olduğu için çözücünün fiil-kökü geri düşüşü «… talebi birikmiş?» sorusunu bu ölçüye bağladı.
    # Terim 'sabit kıymet amortismanı'na çekildi, 'birikmis' anahtarı hiç yaratılmıyor.
    add(key="birikmis-amortisman", term="sabit kıymet amortismanı", type="METRIC", entity=fa,
        pattern="LG_{n0}_FAREGIST", column="ACCUMDEPR", skip=skip_fa,
        formula=(f"SUM({fa}.ACCUMDEPR)" if fa else ""),
        extra={"func": "SUM", "grain": fa, "aliases": ["birikmis_amortisman"], "conditions": cancelled},
        synonyms=["toplam amortisman", "demirbaş amortismanı", "sabit kıymet amortisman tutarı"],
        reason="tanım: sabit kıymet amortismanı (birikmiş amortisman) = Σ FAREGIST.ACCUMDEPR, iptaller hariç. Canlı LG_411: "
               "32.553.265,68 ₺, 1.016/1.079 kayıtta dolu. Tek kelimelik 'amortisman' eş anlamlı olarak "
               "VERİLMEDİ (tek kelime kuralı); 'birikmiş amortisman' öbeği de VERİLMEDİ (set1000/K0807 "
               "ölçümü: 'birikmis' kökü fiil köprüsüne yem oluyordu). İş teyidi bekliyor.")
    add(key="amortisman-orani", term="amortisman oranı", type="COLUMN", entity=fa,
        pattern="LG_{n0}_FAREGIST", column="DEPRRATE", operator="COLUMN", skip=skip_fa,
        synonyms=["amortisman oranları", "demirbaş amortisman oranı"],
        reason="tanım: amortisman oranı = FAREGIST.DEPRRATE (% / yıl). Canlı LG_411: 1.059/1.079 kayıtta "
               "sıfırdan farklı; ör. taşıtlar %20 (5 yıl), binalar %2 (50 yıl), arsalar 0 "
               "(amortismana tâbi değil). İş teyidi bekliyor.")
    add(key="sabit-kiymet-kayit-aciklamasi", term="sabit kıymet kayıt açıklaması", type="COLUMN", entity=fa,
        pattern="LG_{n0}_FAREGIST", column="REGDEFINITION", operator="COLUMN", skip=skip_fa,
        synonyms=["demirbaş açıklaması", "sabit kıymet açıklaması"],
        reason="tanım: sabit kıymet kayıt açıklaması = FAREGIST.REGDEFINITION. Canlı LG_411: 1.061/1.079 "
               "dolu (ör. '34KVM635 FORD TRANSİT'). İş teyidi bekliyor.")
    add(key="sabit-kiymet-alim-tarihi", term="sabit kıymet alım tarihi", type="COLUMN", entity=fa,
        pattern="LG_{n0}_FAREGIST", column="DATEIN", operator="COLUMN", skip=skip_fa,
        synonyms=["demirbaş alım tarihi", "sabit kıymet giriş tarihi"],
        reason="tanım: sabit kıymet alım tarihi = FAREGIST.DATEIN. Canlı LG_411: 1.079/1.079 dolu, "
               "1991-01-01 – 2026-08-12; 2026'da 58 kayıt / 2.748.461 ₺. İş teyidi bekliyor.")

    # ---------------------------------------------------------------- INVDEF — aday YOK (hepsi çürütüldü)
    # LG_411_INVDEF 3.980.876 satır = 146 ambar × 29.066 malzeme, ama MINLEVEL / MAXLEVEL / SAFELEVEL /
    # ABCCODE / LOCATIONREF / PERCLOSEDATE kolonlarının TAMAMI sıfır-boş (LG_211 kopyasında da aynı).
    # Tabloda tek bilgi INVENNO+ITEMREF çifti, o da 'ambar' (STLINE.SOURCEINDEX) ile zaten karşılanıyor.
    # Boş kolona kavram üretilmez → bu tablodan hiçbir aday çıkmadı.

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
    """Aynı anahtarı (terim ya da eş anlamlı) bugün taşıyan SERTİFİKALI kavramlar: çözücüde kim kazanır sorusu."""
    from semantic_layer.normalize import normalize_term
    index = store.certified_index(s.tenant_id, s.datasource_id)
    hits = []
    for word in [d["term"], *d["synonyms"]]:
        for c, maps in index.get(normalize_term(word)) or []:
            hits.append({"anahtar": normalize_term(word), "kavram": c.id, "terim": c.term,
                         "tür": c.semantic_type,
                         "alan": [f"{m.entity}.{m.column or (m.formula or '')[:40]}" for m in maps][:2]})
    return hits


def _magnets(store, s, defs) -> dict[str, list[str]]:
    """Yeni anahtarlardaki kelimelerden bugün HİÇBİR sertifikalı anahtarda geçmeyenler: çözücünün
    tek-kelime geri düşüşü böyle bir kelimeyi, soruda tek başına geçtiğinde, doğrudan buraya bağlar."""
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
                    "işlem": "DOKUNMA (kişi kararı)" if by and not str(by).startswith(("otomatik", "rule-miner"))
                             else "terimi daralt (eşleme aynı kalır)"})
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
            todo = ("DEĞİŞİKLİK YOK" if certified and not missing
                    else ("eş anlamlı ekle" if certified
                          else "sertifikala" + (" + eş anlamlı ekle" if missing else "")))
        rows.append({"kavram": d["term"], "tür": d["type"], "anahtar": normalize_term(d["term"]), "işlem": todo,
                     "varolan": c.id if c else None, "entity": d["entity"], "kalıp": d["pattern"],
                     "kolon": d.get("column"), "değerler": d.get("values"), "formül": d.get("formula"),
                     "extra": d.get("extra") or {}, "eklenecek_eş_anlamlılar": missing,
                     "katalogda_yeni_kelimeler(tek_başına_bu_kavramı_çeker)": magnets.get(d["term"], []),
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
                                        payload={"note": "tanım müşteri veritabanında salt-okunur sorgularla "
                                                         "doğrulandı ve çürütme adımından geçti (ADAYLAR.md)"}))
        if c.status != ConceptStatus.CERTIFIED or not (c.explain or {}).get("human_certified_by"):
            engine.human_certify(c.id, WHO, reason=d["reason"])
        done.append({"kavram": d["term"], "id": c.id, "sonuç": "yaratıldı" if created else "vardı; tamamlandı"})
    return done


def apply_narrow(store) -> list[dict]:
    out = []
    from semantic_layer.normalize import normalize_term
    for row in narrow_rows(store):
        if not str(row.get("işlem", "")).startswith("terimi daralt"):
            out.append(row)
            continue
        cid, new_term = row["kavram"], row["yeni_terim"]
        c = store.get_concept(cid)
        ex = dict(c.explain or {})
        ex["narrowed_from"] = {"term": c.term, "by": WHO, "reason": NARROW_REASON}
        store.update_concept(cid, term=new_term, normalized_term=normalize_term(new_term), explain=ex)
        out.append({**row, "sonuç": "daraltıldı"})
    return out


# ------------------------------------------------------------------------------------------------ bellekte ölçüm
class _WithProposal:
    """Önerilen kavramlar YALNIZ bellekteki dizine eklenir. Anlık görüntü yayını kapatılır: gerçek store'un
    `publish_runtime_snapshot`'ı kendisine verilen dizini sl_catalog_version'a YAZAR."""

    def __init__(self, store, s, defs):
        from semantic_layer.models import Concept
        from semantic_layer.normalize import normalize_term
        self._s, self._base, self._merged, self._extra = store, None, None, []
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
            merged = {k: list(v) for k, v in base.items()}
            if "--narrow-sabit-kiymet" in sys.argv:
                from semantic_layer.normalize import normalize_term
                for cid, new_term in NARROW:
                    for k in list(merged):
                        kept = [(c, mm) for c, mm in merged[k] if c.id != cid]
                        moved = [(c, mm) for c, mm in merged[k] if c.id == cid]
                        if moved:
                            merged[k] = kept
                            if not kept:
                                merged.pop(k, None)
                            merged.setdefault(normalize_term(new_term), []).extend(moved)
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
        slots.append(f"{sl.term} → {sl.semantic_type}:{m.entity}.{m.column or (m.formula or '')[:40]}"
                     + (f" [{sl.status}{' ' + how if how else ''}: {(sl.explain or {}).get('evidence_key', '')}]"
                        if sl.status != "CERTIFIED" else ""))
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
    cases = [json.loads(l) for f in files if not f.startswith("soru:")
             for l in open(f, encoding="utf-8") if l.strip()]
    cases += [{"id": "elle", "soru": f[5:]} for f in files if f.startswith("soru:")]
    changed = 0
    for case in cases:
        a, b = _reading(before, case["soru"]), _reading(after, case["soru"])
        if a != b:
            changed += 1
            print(json.dumps({"id": case.get("id"), "kaynak": case.get("kaynak"), "soru": case["soru"],
                              "önce": a, "sonra": b}, ensure_ascii=False), flush=True)
    print(json.dumps({"soru": len(cases), "okuması_değişen": changed}, ensure_ascii=False))


def main() -> int:
    s, store, profiles, defs = _open()
    if "--simulate" in sys.argv:
        files = [a for a in sys.argv[sys.argv.index("--simulate") + 1:] if not a.startswith("--")]
        simulate(store, s, profiles, defs, files)
        return 0
    rows = plan(store, s, defs)
    print(json.dumps({"kip": "UYGULA" if "--apply" in sys.argv else "KURU KOŞU (yazılmadı)", "who": WHO,
                      "plan": rows}, ensure_ascii=False, indent=1, default=str))
    if "--narrow-sabit-kiymet" in sys.argv:
        print(json.dumps({"terimi_daraltılacak": narrow_rows(store), "gerekçe": NARROW_REASON},
                         ensure_ascii=False, indent=1, default=str))
    if "--apply" in sys.argv:
        if "--narrow-sabit-kiymet" in sys.argv:
            print(json.dumps({"daraltıldı": apply_narrow(store)}, ensure_ascii=False, indent=1, default=str))
        print(json.dumps({"yazıldı": apply(store, s, defs)}, ensure_ascii=False, indent=1))
        print("Köprü kataloğu en geç 30 sn içinde kendisi yeniden yükler (ensure_fresh); "
              "yeniden başlatma gerekmez.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
