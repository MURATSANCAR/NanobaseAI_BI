"""M52 Tedarik ve baskı: ekrandaki her rakamın sorgu bilgisi (ortak sözleşme `provenance.py`).

Rakamlar `supply.Source` okumasından (üretim kartları + CRM teknik alanlar + Logo tedarikçi/fatura/giriş; gece
`timas-supply.timer` ve arka plan tazelemesi son okuma tablosuna `semantic_supply_reads` yazar, uç oradan okur —
`tedarik.portal.okuma`, kökeni Logo/CRM sorguları) ve portal kayıtlarından (kapasite, öneri, eşleme, fatura bağı) gelir. Gösterilen Logo/CRM
SQL'i o okumada ÇALIŞAN metnin kendisidir (`snap["runs"]`: firma kopyası, CRM şeması, pencere başı yerinde; satır, süre
ve an ile) — `/sources` panelinin eski şablon metni yerine. Okunmamış kaynağın kaydı açılmaz. Borç hesabı FIFO
yaklaşımıyla Python'da yapılır; formül metni bunu söyler.
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

import sqlalchemy as sa

from semantic_bridge import provenance as P
from semantic_bridge import supply as S
from semantic_bridge import supply_sources as src
from semantic_bridge import supply_store as store
from semantic_bridge.kaynak_ayar import ayar, bind, h

# ------------------------------------------------------------------ formüller

F_KART = ("Üretim kartları üretim modülünden gelir (CRM baskı kartı; gerçekleşen baskı ve depo tarihleri Logo'dan). "
          "Açık kart = aşaması hazırlık, matbaa seçildi ya da matbaada olan; adet = kesinleşen baskı adedi.")
F_YUK = ("Baskı yükü = açık üretim kartlarının matbaa × plan baskı ayı toplamı: iş sayısı, adet ve forma yükü (forma × "
         "adet; forma CRM üretim kartı teknik alanından). Planı geçmiş ama baskıdan çıkmamış kart «gecikmiş», baskı ayı "
         "olmayan «tarihsiz» sütununda; ufuk dışı = ufuktan sonraki aylara düşen kart sayısı. Geçen yıl = aynı ay baskıdan "
         "çıkan iş ve adet.")
F_ESIK = ("Hücre durumu: kapasite girilmişse oran = yük ÷ kapasite, oran ≥ eşik «kapasite aşımı»; kapasite yoksa "
          "referans = matbaanın son 12 ayda baskıdan çıkan en yüksek aylık yükü, üstü «referansın üstü»; ikisi de yoksa "
          "ölçülemedi. Çakışma sayısı = aşım ya da referans üstü hücre sayısı.")
F_KAGIT = ("Kağıt ihtiyacı = açık kartların parça başına kağıt ihtiyacı (CRM üretim kartı teknik alanları: kapak, iç "
           "sayfa, şömiz…; ölçü ayardan: brüt = fire dahil, ya da net) kağıt cinsi × baskı ayı toplamı, kg. Gramaj ve "
           "ebat adı CRM kağıt cinsi kaydından. Dolu/boş = kağıt alanı girilmiş/girilmemiş kart sayısı.")
F_KAGIT_FIYAT = ("Kağıt fiyatı = kağıtçı carilerinden mal alış satırları (Logo): ay başına birim fiyat = tutar ÷ miktar; "
                 "ortalama = Σ tutar ÷ Σ miktar, ilk ve son ay birim fiyatı, değişim = son ÷ ilk − 1.")
F_BORC = (S.FIFO_NOTE + " Bakiye = alacak − borç (bu yılın Logo firması, yıl başından); vadesi geçmiş, vadesi gelmemiş, "
          "vade planı olmayan ve gün kovaları açık tutarın vade gününe göre dağılımıdır (yaşlandırma tarihi ayardan).")
F_ALIS = "Alış = tedarikçinin alış faturaları (TRCODE 1, 4) NETTOTAL (KDV dahil): bu yıl, son 12 ay ve fatura sayısı."
F_KARNE = ("Karne = üretim modülünün matbaa ölçümü: iş, açık ve biten, zamanında teslim oranı (plan depo tarihine göre), "
           "dosya → depo gün ortancası, adet başı baskı bedeli (baskı faturası ÷ basılan adet) ve eğilimi, kalite oranı.")
F_ACIK_IS = ("Açık iş = tedarikçiye eşlenmiş CRM matbaalarının açık kart sayısı; tür = özel kod (ayar) ya da baskı "
             "faturası kesmiş olmak.")
F_ESLESME = ("Matbaa ↔ cari eşlemesi: CRM matbaası için baskı faturalarında en çok görülen cari; pay ve iş sayısı bu "
             "oylamadandır (eşik ayarda). Elle yapılan eşleme önceliklidir.")
F_OZELKOD = "Özel kod dağılımı = tedarikçi carilerinin (ayardaki önekle başlayan) özel kodu başına cari sayısı."
F_ODEME = ("Ödeme takvimi = FIFO ile açık kalan vade satırlarından önümüzdeki gün içinde vadesi gelenler (açık tutar, plan "
           "tutarı, gün); haftalık = haftanın pazartesisine göre toplam; vadesi geçmiş = tedarikçi başına açık vadesi "
           "geçmiş tutar. " + S.FIFO_NOTE)
F_FATURASIZ = ("Faturası görünmeyen kart = depoya girmiş ama bekleme süresi dolduğu hâlde baskı faturası bağlanmamış kart; "
               "bekleyen gün = bugün − depo girişi. Bekleme süresi = kartlarda ölçülen fatura gecikmesinin ortancası "
               "(ölçüm yoksa ayar).")
F_KARTSIZ = ("Kartı görünmeyen fatura = son 12 ayın baskı faturası satırı (Komple Baskı Giderleri, satır özel kodu = stok "
             "kodu) hiçbir karta bağlanmamış; aday puanı kitap, adet ve tarih yakınlığından; tutar KDV hariç.")
F_AYLIK = "Aylık = matbaa × ay depoya giren adet (kartlar) ve faturalanan adet (baskı faturası); fark = depo − fatura."
F_MALIYET = ("Adet başı baskı bedeli = kartın baskı faturası tutarı (KDV hariç) ÷ basılan adet; grup = seçilen kırılım "
             "(cilt, sayfa bandı, baskı tipi, matbaa). Ağırlıklı birim = Σ tutar ÷ Σ adet, ortanca = kart birimlerinin "
             "ortancası, 100 sayfa başı = birim ÷ sayfa × 100, iş = kart sayısı; eğilim = son yarı ÷ önceki yarı − 1.")
F_GELEN = ("Depo girişi: gerçekleşen = Logo üretimden giriş fişleri (TRCODE 13, IOCODE 1, gerçek giriş) ay başına adet "
           "ve fiş sayısı; planlanan = açık kartların plan depo ayı başına adet ve iş; planı geçmiş = plan depo tarihi "
           "geçmiş, girişi görünmeyen kartlar.")
F_PLAN = ("Yayın planı girdisi = Baskı Öneri raporunun «Baskı Tekrar» listesi (öneri seviyesi, önerilen adet, tükenme, "
          "stok) + onaylı ilk baskı kararları (adet, yayın ayı); açık üretim kartı olan kitap atlanır. Toplam adet = "
          "listelerin önerilen adet toplamı.")
F_DEGISIKLIK = ("Plan değişiklikleri = CRM plan değişikliği kayıtları (pencere başından): sebep başına sayı, açık kartlarda "
                "değişiklik sayısı, kartı bulunamayan kayıt.")
F_ONERI = ("Öneriler gece işinin yazdığı portal kayıtlarıdır (yük dengeleme, kağıt siparişi, eskalasyon, şartname); "
           "içindeki rakamlar yazıldığı anki okumadandır. Metni Zeki AI yazdıysa sayıları olgularla denetlenmiştir.")
F_KAPASITE = "Kapasite = elle girilen matbaa × ay (ya da her ay) adet ve forma kapasitesi; giren ve tarih kayıtta."
F_M9 = ("Kart satırındaki birim maliyet (M9): onaylı fiyat analizindeki birim maliyet → Logo gerçekleşen (maliyeti "
        "girilmiş satış satırlarının en son yılı) → bilinmiyor.")
F_KART_TUTAR = ("Kart satırındaki birim fiyat ve fatura tutarı = kartın baskı faturası (Komple Baskı Giderleri) tutarı "
                "(KDV hariç) ve ÷ basılan adet.")
F_DB = "Okuma süresi (ms): üretim kartları, CRM teknik alanlar ve Logo okumasının son süresi."


def _sid(run_id: str) -> str:
    return "tedarik." + run_id.replace(":", ".")


_TITLES = {sid: (conn, title, desc) for sid, conn, title, desc in src.SOURCES}


class Supply:
    """Bir okumanın kaynak kayıtları: çalışan kaynaklar `tedarik.*` kimliğiyle."""

    def __init__(self, engine: Any, tenant: str, snap: Optional[dict[str, Any]], deps: dict[str, Any],
                 runs: Optional[dict[str, dict[str, Any]]] = None):
        self.engine, self.tenant, self.deps = engine, tenant, deps
        snap = snap or {}
        self.snap = snap
        self.k = P.Kaynaklar(data_end=((snap.get("logo") or {}).get("dataEnd")), as_of=snap.get("at"))
        self.ids: dict[str, str] = {}
        for rid, r in sorted({**(snap.get("runs") or {}), **(runs or {})}.items()):
            base, _, firm = rid.partition(":")
            conn, title, desc = _TITLES.get(base, ("logo", base, ""))
            self.ids[rid] = self.k.sorgu(
                _sid(rid), title + (f" · Logo firma {firm}" if firm else ""), conn, r["sql"],
                database=deps.get("logo_db") if conn == "logo" else deps.get("crm_db"), rows=r.get("rows"), ms=r.get("ms"),
                ran_at=r.get("at"), period=f"Logo firma {firm}" if firm else None,
                description=(desc + " Sorgu gece turunda ya da arka plan tazelemesinde çalışır, sonucu son tedarik okuması "
                             "tablosunda tutulur (çalıştığı an satırda).").strip())
        snap_ids = [v for rid, v in self.ids.items() if rid in (snap.get("runs") or {})]
        if snap_ids:
            # Ucun çalıştırdığı portal okuması: son okuma tablosu; kökeni yukarıdaki Logo/CRM sorguları.
            self.k.portal("tedarik.portal.okuma", "Son tedarik okuması", store.read_stmt(tenant), engine, origin=snap_ids,
                          description="Gece turunun ya da arka plan tazelemesinin yazdığı son okuma (üretim kartları, CRM "
                                      "teknik alanlar, Logo tedarikçi ve fatura). Uç kaynağı beklemez, bu satırı okur.")

    def s(self, *bases: str) -> list[str]:
        """Okunmuş kaynaklar; firma kopyası başına okunan kaynakta hepsi."""
        out: list[str] = []
        for b in bases:
            out += [v for key, v in self.ids.items() if key == b or key.startswith(b + ":")]
        return out

    # -- dış ve portal kaynaklar

    def m12(self) -> Optional[str]:
        prod = self.deps.get("production")
        try:
            from datetime import date

            from semantic_bridge import production

            snap = prod.source.peek()
            if not snap:
                return None
            text = production.crm_cards_sql(prod.source._schema(), date.fromisoformat(str(snap["since"])[:10]))
            return self.k.sorgu("tedarik.uretim.kartlar", "Üretim kartları (CRM)", "crm", text, database=self.deps.get("crm_db"),
                                rows=len(snap.get("cards") or []), ms=snap.get("crmMs"), ran_at=snap.get("at"),
                                description="Üretim modülünün baskı kartları (aşama, matbaa, plan ve gerçekleşen tarihler).")
        except Exception:  # noqa: BLE001 — üretim okuması yoksa kayıt açılmaz
            return None

    def cards(self) -> list[Optional[str]]:
        return [self.m12()] + self.s("crm_kart_teknik")

    def capacity(self) -> str:
        return self.k.portal("tedarik.portal.kapasite", "Matbaa kapasitesi", store.capacity_stmt(self.tenant), self.engine,
                             description="Elle girilen matbaa × ay kapasitesi (adet, forma).")

    def suggestions(self, tur: str = "", durum: str = "") -> str:
        return self.k.portal("tedarik.portal.oneriler" + (f".{tur}" if tur else "") + (f".{durum}" if durum else ""),
                             "Tedarik önerileri", store.suggestions_stmt(self.tenant, tur, durum), self.engine,
                             description="Gece işinin yazdığı öneriler ve kararları.")

    def links(self) -> str:
        return self.k.portal("tedarik.portal.faturaBag", "Fatura ↔ kart bağları", store.links_stmt(self.tenant), self.engine,
                             description="Onaylanan, reddedilen ve önerilen fatura satırı ↔ üretim kartı bağları.")

    def supmap(self) -> str:
        return self.k.portal("tedarik.portal.eslesme", "Matbaa ↔ cari eşlemeleri (elle)", store.supplier_map_stmt(self.tenant),
                             self.engine, description="Elle yapılan CRM matbaası ↔ Logo carisi eşlemeleri.")

    def settings(self, *keys: str) -> str:
        return ayar(self.k, self.engine, "tedarik.ayar." + ".".join(x.lower() for x in keys), keys, "tedarik")

    def report(self) -> list[str]:
        """Baskı Öneri raporunun son okumasında çalışan sorgular (rapor önbelleğindeki çalışan metin)."""
        fn = self.deps.get("report_data")
        if not fn:
            return []
        try:
            from semantic_bridge.management import baski_oneri as BO

            data = fn() or {}
        except Exception:  # noqa: BLE001
            return []
        meta = {x[0]: x for x in BO.SOURCES}
        out = []
        for sid, st in sorted((data.get("sourceStats") or {}).items()):
            if not st.get("sql") or sid not in meta or st.get("skipped"):
                continue
            conn = meta[sid][1] if meta[sid][1] in ("logo", "crm") else "logo"
            try:
                out.append(self.k.sorgu(f"tedarik.baskiOneri.{sid}", f"Baskı Öneri · {meta[sid][2]}", conn, st["sql"],
                                        database=self.deps.get("logo_db") if conn == "logo" else self.deps.get("crm_db"),
                                        rows=st.get("rows"), ms=st.get("dbMs"), ran_at=data.get("asOf"),
                                        description=meta[sid][3]))
            except P.ProvenanceError:
                continue
        return out

    def decisions(self) -> Optional[str]:
        """Onaylı ilk baskı kararları (M10 kaydı; `ilk_baski_api.list_decisions(status="onaylandi")` ile aynı ifade)."""
        if not self.deps.get("decisions"):
            return None
        try:
            from semantic_bridge.management import ilk_baski_api as FP

            D = FP.DECISIONS
            stmt = (sa.select(D).where(D.c.tenant_id == self.tenant).where(D.c.status == "onaylandi")
                    .order_by(D.c.created_at.desc()))
            return self.k.portal("tedarik.portal.ilkBaski", "Onaylı ilk baskı kararları", stmt, self.engine,
                                 description="İlk baskı adedi ve yayın ayı kararları.")
        except Exception:  # noqa: BLE001
            return None

    # -- hesap kümeleri

    def yuk(self) -> Optional[str]:
        return h(self.k, "yuk", F_KART + " " + F_YUK, self.cards() + [self.capacity()])

    def esik(self) -> Optional[str]:
        return h(self.k, "esik", F_ESIK, ["hesap:yuk" if "yuk" in self.k.formulas else None, self.capacity(),
                                           self.settings("SUPPLY_OVERLOAD_RATIO")])

    def plan(self) -> Optional[str]:
        return h(self.k, "plan", F_PLAN, self.report() + [self.decisions(), self.m12()])

    def degisiklik(self) -> Optional[str]:
        return h(self.k, "degisiklik", F_DEGISIKLIK, self.s("crm_plan_degisiklik", "crm_secenekler") + [self.m12()])

    def kagit(self) -> Optional[str]:
        return h(self.k, "kagit", F_KART + " " + F_KAGIT, self.cards() + self.s("crm_kagit_cins"))

    def kagit_fiyat(self) -> Optional[str]:
        return h(self.k, "kagitFiyat", F_KAGIT_FIYAT, self.s("logo_kagit_alis_satir"))

    def borc(self) -> Optional[str]:
        return h(self.k, "borc", F_BORC, self.s("logo_tedarikci_cari", "logo_tedarikci_vade"))

    def alis(self) -> Optional[str]:
        return h(self.k, "alis", F_ALIS, self.s("logo_alis_fatura", "logo_tedarikci_faturalar"))

    def karne(self) -> Optional[str]:
        return h(self.k, "karne", F_KART + " " + F_KARNE, self.cards() + self.s("logo_baski_faturasi"))

    def eslesme(self) -> Optional[str]:
        return h(self.k, "eslesme", F_ESLESME, self.s("logo_baski_faturasi") + [self.m12(), self.supmap()])

    def faturasiz(self) -> Optional[str]:
        return h(self.k, "faturasiz", F_KART + " " + F_FATURASIZ, self.cards() + [self.links(), self.settings("SUPPLY_UNBILLED_GRACE_DAYS")])

    def kartsiz(self) -> Optional[str]:
        return h(self.k, "kartsiz", F_KARTSIZ, self.s("logo_baski_faturasi") + [self.links(), self.m12()])

    def maliyet(self) -> Optional[str]:
        return h(self.k, "maliyet", F_MALIYET, self.cards() + self.s("crm_secenekler", "logo_baski_faturasi"))

    def gelen(self) -> Optional[str]:
        return h(self.k, "gelen", F_KART + " " + F_GELEN, self.s("logo_uretim_giris") + [self.m12()])

    def odeme(self) -> Optional[str]:
        return h(self.k, "odeme", F_ODEME, self.s("logo_tedarikci_cari", "logo_tedarikci_vade") + [self.supmap()])

    def db(self) -> Optional[str]:
        return h(self.k, "db", F_DB, list(self.ids.values()) + [self.m12()])


def _new(engine: Any, tenant: str, snap: Optional[dict[str, Any]], deps: dict[str, Any], runs=None) -> Supply:
    return Supply(engine, tenant, snap, deps, runs)


# ------------------------------------------------------------------ uçlar


def for_overview(engine: Any, tenant: str, snap: dict[str, Any], out: dict[str, Any], deps: dict[str, Any]) -> P.Kaynaklar:
    x = _new(engine, tenant, snap, deps)
    k = x.k
    yuk = x.yuk()
    f: dict[str, Optional[str]] = {
        "yuk": yuk, "yuk.satirlar[].hucreler": yuk, "yuk.satirlar[].referans": x.esik(),
        "cakisma": h(k, "cakisma", F_ESIK, [yuk, x.capacity()]), "cakismaAsim": "hesap:cakisma" if yuk else None,
        "kagit": x.kagit(), "plan": x.plan(), "oneri": h(k, "oneri", F_ONERI, [x.suggestions(durum="bekliyor")]),
        "db": x.db(),
    }
    if "odeme30" in out:
        f["odeme30"] = x.odeme()
    if "faturasiz" in out:
        f["faturasiz"] = h(k, "faturasizOzet", F_FATURASIZ + " " + F_KARTSIZ, [x.faturasiz(), x.kartsiz()])
    if "maliyet" in out:
        f["maliyet"] = x.maliyet()
    bind(k, f)
    return k


def for_load(engine: Any, tenant: str, snap: dict[str, Any], out: dict[str, Any], deps: dict[str, Any], *,
             cost: bool) -> P.Kaynaklar:
    x = _new(engine, tenant, snap, deps)
    k = x.k
    yuk = x.yuk()
    f: dict[str, Optional[str]] = {
        "satirlar": yuk, "toplam": yuk, "ufukDisi": yuk, "satirlar[].referans": x.esik(),
        "oranEsigi": x.settings("SUPPLY_OVERLOAD_RATIO"), "cakismalar": h(k, "cakisma", F_ESIK, [yuk, x.capacity()]),
        "plan": x.plan(), "degisiklikler": x.degisiklik(),
    }
    if cost:
        f["satirlar[].hucreler"] = h(k, "yukMaliyet", F_YUK + " " + F_KART_TUTAR + " " + F_M9,
                                     [yuk] + x.s("logo_baski_faturasi"))
    bind(k, f)
    return k


def for_paper(engine: Any, tenant: str, snap: dict[str, Any], out: dict[str, Any], deps: dict[str, Any]) -> P.Kaynaklar:
    x = _new(engine, tenant, snap, deps)
    kg = x.kagit()
    f: dict[str, Optional[str]] = {"satirlar": kg, "cinsler": kg, "kapsam": kg, "kagitsizKartlar": kg, "toplamKg": kg}
    if out.get("fiyat") is not None:
        f["fiyat"] = x.kagit_fiyat()
    bind(x.k, f)
    return x.k


def for_suppliers(engine: Any, tenant: str, snap: dict[str, Any], out: dict[str, Any], deps: dict[str, Any]) -> P.Kaynaklar:
    x = _new(engine, tenant, snap, deps)
    k = x.k
    borc, alis = x.borc(), x.alis()
    f: dict[str, Optional[str]] = {
        "items[].acikIs": h(k, "acikIs", F_ACIK_IS, x.cards() + [x.supmap()] + x.s("logo_cari_ozel_kod")),
        "items[].karne": x.karne(), "eslesme": x.eslesme(), "eslesmeyen": "hesap:eslesme" if "eslesme" in k.formulas else None,
        "ozelKodlar": h(k, "ozelKod", F_OZELKOD, x.s("logo_cari_ozel_kod")),
    }
    for key in ("bakiye", "vadesiGecmis", "plansiz", "gelmemis", "kovalar", "gelecek", "katalogVadesiGecmis"):
        f[f"items[].{key}"] = borc
    for key in ("alisBuYil", "alis12", "fatura12"):
        f[f"items[].{key}"] = alis
    bind(k, f)
    return k


def for_supplier(engine: Any, tenant: str, snap: dict[str, Any], out: dict[str, Any], deps: dict[str, Any],
                 runs: dict[str, dict[str, Any]]) -> P.Kaynaklar:
    x = _new(engine, tenant, snap, deps, runs)
    k = x.k
    card_cost = h(k, "kartTutar", F_KART + " " + F_KART_TUTAR, x.cards() + x.s("logo_baski_faturasi"))
    bind(k, {"yaslandirma": x.borc(), "alis": x.alis(),
             # Turda okunan bütün tedarikçi faturaları (cari süzgeci sayfada); tur okuyamadıysa sayfanın tek cari sorgusu.
             "faturalar": h(k, "faturalar", F_ALIS + " Liste: son 12 ayın faturaları, tutar ve KDV satır satır.",
                            x.s("logo_tedarikci_faturalar", "logo_tedarikci_faturalar_tumu")),
             "acikIsler": card_cost, "bitenIsler": card_cost, "karne": x.karne()})
    return k


def for_payments(engine: Any, tenant: str, snap: dict[str, Any], out: dict[str, Any], deps: dict[str, Any]) -> P.Kaynaklar:
    x = _new(engine, tenant, snap, deps)
    o = x.odeme()
    bind(x.k, {"satirlar": o, "haftalik": o, "toplam": o, "vadesiGecmis": o, "vadesiGecmisToplam": o})
    return x.k


def for_unbilled(engine: Any, tenant: str, snap: dict[str, Any], out: dict[str, Any], deps: dict[str, Any]) -> P.Kaynaklar:
    x = _new(engine, tenant, snap, deps)
    k = x.k
    fz = x.faturasiz()
    bind(k, {"kartlar": fz, "bekleme": fz, "faturalar": x.kartsiz(),
             "aylik": h(k, "aylik", F_KART + " " + F_AYLIK, x.cards() + x.s("logo_baski_faturasi") + [x.supmap()])})
    return k


def for_cost(engine: Any, tenant: str, snap: dict[str, Any], out: dict[str, Any], deps: dict[str, Any]) -> P.Kaynaklar:
    x = _new(engine, tenant, snap, deps)
    bind(x.k, {"gruplar": x.maliyet(), "kagit": x.kagit_fiyat()})
    return x.k


def for_incoming(engine: Any, tenant: str, snap: dict[str, Any], out: dict[str, Any], deps: dict[str, Any]) -> P.Kaynaklar:
    x = _new(engine, tenant, snap, deps)
    g = x.gelen()
    f: dict[str, Optional[str]] = {"gecmis": g, "plan": g, "planiGecmis": g}
    if out.get("depo"):
        f["depo"] = h(x.k, "depo", "Depo kapasitesi ve stok = depo ve stok modülünün beyanı (ayar ve Logo bakiyesi).", [g])
    bind(x.k, f)
    return x.k


def for_suggestions(engine: Any, tenant: str, out: dict[str, Any], *, tur: str, durum: str) -> P.Kaynaklar:
    x = _new(engine, tenant, None, {})
    bind(x.k, {"items[]": h(x.k, "oneri", F_ONERI, [x.suggestions(tur, durum)])})
    return x.k


def for_capacity(engine: Any, tenant: str, out: dict[str, Any]) -> P.Kaynaklar:
    x = _new(engine, tenant, None, {})
    bind(x.k, {"items[]": h(x.k, "kapasite", F_KAPASITE, [x.capacity()])})
    return x.k


def for_sources(engine: Any, tenant: str, snap: Optional[dict[str, Any]], deps: dict[str, Any]) -> P.Kaynaklar:
    """`/sources`: son okumada çalışan bütün sorgular (şablon değil)."""
    x = _new(engine, tenant, snap, deps)
    ids = list(x.ids.values()) + [i for i in [x.m12()] if i]
    if ids:
        bind(x.k, {"sources[]": h(x.k, "veri", "Tedarik verisini kuran sorguların tamamı (satır ve süre: son okuma).", ids)})
    return x.k


#: Rakam olmayan sayılar: Logo yılı, sayfa, gün penceresi (kişinin seçtiği), kart kimliği dışı kodlar.
NOT_RAKAM = ("logo.yil", "gun", "items[].tur", "faturalar[].tur", "yaslandirma.acikSatir[].satir")
