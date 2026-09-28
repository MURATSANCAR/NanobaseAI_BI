"""M12 Üretim yönetimi: ekrandaki her rakamın sorgu bilgisi (ortak sözleşme `provenance.py`).

Kartlar CRM üretim kartından, gerçekleşen üretim Logo üretim emri + emre bağlı giriş fişlerinden, baskı bedeli Logo'daki
matbaa baskı faturasından okunur; okuma 5 dakikada bir yenilenir ve diskte kalır (`production.Source`). Ekrandaki rakamın
asıl SQL'i o okumada ÇALIŞAN metindir — firma/dönem kopyası (LG_211 = 2021–2025, LG_411 = 2026 …) ve geçmiş penceresinin
başı yerinde, satır ve süreyle — okuma kaydında saklanır (`snap["queries"]`). Kayıt yoksa (bu sürümden önceki okuma)
kaynak açılmaz ve açıklama «ilk yenilemeden sonra görünür» der; firma kopyası tahmin edilmez.

Portalda girilen tarih, hedef yayın tarihi, kalite, not, onay ve matbaa teklifi elle girilir: uçta çalışan portal
ifadesi (`production_store.entries_stmt` / `quotes_stmt`). Ayarlar Yönetim ekranından (semantic_settings). Sayımlar,
süreler, gecikme, matbaa puanı ve geriye takvim Python'da hesaplanır: formül metniyle.
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

import sqlalchemy as sa

from semantic_bridge import provenance as P
from semantic_bridge import production_store as store

PFX = "uretim."
#: Rakam olmayan sayılar: sayfa, sayfa boyu, CRM seçenek kodu (üretim tipi).
NOT_RAKAM = ("page", "pageSize", "items[].kindCode", "kindCode")

SETTING_KEYS = ("PRODUCTION_FILES_DAY", "PRODUCTION_FILES_MONTHS_BEFORE", "PRODUCTION_ESCALATE_DAYS", "PRODUCTION_STALE_DAYS",
                "PRODUCTION_NEW_PRINTS_DAYS", "PRODUCTION_HISTORY_FROM")

F_KART = ("Üretim kartı = CRM üretim kartı (etkin, geçmiş penceresinin başından sonra açılmış, e-kitap türü ve e-kitap "
          "aşamaları hariç) + Logo üretim emri (emrin 1. açıklamasındaki üretim no ile; boşsa stok kodu ve kartın zaman "
          "penceresindeki en erken emir) + emre bağlı üretimden giriş fişleri (TRCODE 13; PRODSTAT 1 planlanan, 0 gerçek) + "
          "Logo'daki matbaa baskı faturası satırları (hizmet «Komple Baskı Giderleri», satır özel kodu = stok kodu, kart "
          "penceresinde) + portal kayıtları. Kart penceresi: kart açılışından 7 gün önce başlar, aynı stok kodlu bir sonraki "
          "kartın penceresinde biter. Gerçekleşen tarih önceliği Logo > CRM > portal (portal yalnız boşu doldurur); baskı "
          "tekrarı kartında kart açılışından 30 günden eski CRM «gerçekleşen» tarihi önceki baskınındır, sayılmaz. Baskı "
          "çıkışı = ilk gerçek giriş fişi; depo girişi = gerçek girişlerin toplamı emrin planlanan adedine ulaştığı gün "
          "(ulaşmadan emir kapandıysa son giriş). Depoya giren adet = Σ gerçek giriş AMOUNT.")
F_PLAN = ("Plan: portalda hedef yayın tarihi girildiyse geriye doğru takvim; yoksa CRM «üretime teslim» (dosya) ve «baskı "
          "tarihi» (ayın 1'iyse ayın son gününe kadar) tarihleri, depo için Logo'daki planlanan giriş fişi (yoksa baskı planı + "
          "ölçülen baskı→depo süresi), matbaa seçimi için dosya planı − ölçülen matbaa→dosya süresi. Gecikme (gün) = bugün − "
          "planlanan gün, gerçekleşmemiş adımda; sonraki adım gerçekleştiyse öncekiler gecikme sayılmaz. Gecikme ayardaki "
          "günü aşınca «yöneticiye çıktı». Aşama = gerçekleşen en ileri adım; iptal aşamalı CRM kartı «iptal»; son plan "
          "tarihi ayardaki günden eski ve depoya girmemiş kart «kapanmamış eski kart».")
F_OZET = ("Toplam = okunan üretim kartı sayısı. Süren = aşaması «depoya girdi», «iptal» ya da «eski» olmayan kart. "
          "Gecikmede = sürenlerden gecikmesi olan; yöneticiye çıkan = bunlardan gecikmesi ayardaki günü aşan. 14 gün içinde = "
          "gecikmesi olmayan, planlı ama gerçekleşmemiş bir adımı bugünden 14 gün içinde olan süren kart. Depoya girdi = "
          "gerçekleşen depo girişi son 30 günde olan kart. Aşama sayıları = aşama başına kart. Logo eşleşmesi = Logo üretim "
          "emri bağlanan kart sayısı.")
F_SURE = ("Ölçülen süre (gün) = iki adımı da gerçekleşmiş kartlarda sonraki − önceki adım gününün ortancası; «çoğu» = "
          "çeyrekler (p25–p75); örnek = ölçülen kart sayısı. 20 örnekten az ise süre ölçülemedi sayılır (plana yazılmaz). "
          "Sonraki adımı öncekinden önce girilmiş kart süreye katılmaz, ayrıca sayılır.")
F_SABLON = ("CRM takviminin ara tarihleri (grafik teslimi, son tarih, dosya teslimi, dağılım): yeni kitap kartlarında plan "
            "tarihinin CRM baskı tarihine uzaklığının ortancası (gün), çeyrekler ve örnek sayısı; 20 örnekten az ise yazılmaz.")
F_MATBAA = ("Matbaa başına (iptal ve eski kartlar hariç): iş = kart sayısı; süren = depoya girmemiş; zamanında = baskı çıkışı "
            "(yoksa depo girişi) planlanan baskı gününden geç değil / ölçülen kart; dosya → depo = gerçekleşen dosya "
            "teslimiyle depo girişi arasındaki gün farkının ortancası; birim fiyat = kartların adet başı baskı bedelinin (Logo "
            "baskı faturası Σ tutar / Σ adet) ortancası, son 12 ayda açılan kartlardan; eğilim = (son 12 ay − önceki 12 ay) / "
            "önceki 12 ay; kalite = portalda «sorunsuz» işaretlenen / işaretlenen kart. Puan (0–100) = zamanında teslim 50 "
            "(oran bütün matbaaların oranına 10 iş ağırlığıyla çekilir) + fiyat 30 (birim fiyat bütün matbaaların ortancasından "
            "ucuz ya da eşitse tam, iki katında sıfır) + kalite 20; ölçülemeyen parça yarım puan alır. Fiyat ortancası = "
            "matbaaların birim fiyatlarının ortancası.")
F_ONERI = ("Matbaa seçim raporu: teklif veren matbaalar önce (son teklifin adet başı fiyatı puana girer), sonra puanı en "
           "yüksekler; ilk 3. Puan ve gerekçedeki sayılar matbaa performansı hesabıyla aynıdır.")
F_BEDEL = ("Baskı bedeli = kartın penceresine düşen matbaa baskı faturası satırlarının Σ LINENET'i; faturalanan adet = Σ "
           "AMOUNT; adet başı baskı = bedel / adet; faturayı kesen = tutarı en büyük cari.")
F_TAKVIM = ("Geriye takvim: dosya teslimi = yayın ayından «ay önce» ayarı kadar önceki ayın «dosya günü»; baskı çıkışı en geç "
            "yayın ayının son günü; matbaa seçimi = dosya − ölçülen matbaa→dosya süresi; depo = baskı + ölçülen baskı→depo "
            "süresi; beklenen baskı = dosya + ölçülen dosya→baskı süresi. CRM ara tarihleri = yayın ayının 1'i + ölçülen "
            "uzaklık. Süresi ölçülemeyen adım boş kalır.")
F_OKUMA = "Okuma süresi = kaynak okumasının CRM ve Logo kısmının milisaniyesi (okumanın kendisi aşağıdaki sorgulardır)."
F_AYAR = ("Ayar Yönetim ekranından (semantic_settings); girilmeyen ayar ortam değerinden ya da varsayılandan gelir: dosya günü "
          "15, ay önce 1, yöneticiye çıkış 7 gün, eski kart 180 gün, yeni çıkanlar 30 gün, geçmiş penceresi iki yıl önceki "
          "1 Ocak.")
F_ELLE = "Ekrandan elle girilir (portal tablosu); hesap yok."

NO_READ = (" Bu okumanın sorgu kaydı yok (kayıt tutmayan önceki sürümün okuması); çalışan CRM/Logo sorguları ilk "
           "yenilemeden sonra görünür.")


def _title(q: dict[str, Any]) -> tuple[str, str, Optional[str]]:
    """Okuma sorgusunun başlığı, açıklaması, dönemi (etiketten)."""
    tag = str(q.get("tag") or "")
    firm, period = q.get("firm"), q.get("period")
    fp = f"Logo firma {firm}" + (f" · dönem {period}" if period and not tag.startswith("logo.emirler") else "")
    if tag == "crm.kartlar":
        return ("CRM üretim kartları", "Etkin üretim kartları (new_UretimBase), kitap, sorumlu editör ve grafiker; bütün CRM "
                "tarihleri. Geçmiş penceresinin başından beri açılan kartlar.", None)
    if tag == "crm.secenekler":
        return ("CRM seçenek etiketleri (matbaa, aşama, kart türü…)", "Üretim kartının seçenek listesi kolonlarının Türkçe "
                "etiketleri (StringMap).", None)
    if tag == "logo.tablolar":
        return ("Logo üretim emri tablosu olan firmalar", "Dönem tanımında olup üretim emri tablosu olmayan firma okunmaz.", None)
    if tag == "logo.donemler":
        return ("Logo firma/dönem kopyaları", "Geçmiş penceresine düşen firma ve dönemler (L_CAPIPERIOD); her yıl ayrı firma "
                "kopyasıdır (211 = 2021–2025, 411 = 2026).", None)
    if tag.startswith("logo.emirler"):
        return (f"Logo üretim emirleri · firma {firm}", "Üretim emirleri (PRODORD): planlanan adet, açıklama 1 = CRM üretim no.", fp)
    if tag.startswith("logo.girisler"):
        return (f"Logo üretimden giriş fişleri · firma {firm}", "Emre bağlı üretimden giriş fişlerinin ana ürün satırı "
                "(TRCODE 13; PRODSTAT 1 planlanan, 0 gerçek giriş).", fp)
    if tag.startswith("logo.faturalar"):
        return (f"Logo matbaa baskı faturaları · firma {firm}", "Alınan hizmet faturası (TRCODE 4), hizmet «Komple Baskı "
                "Giderleri»; satır özel kodu kitabın stok kodu, miktarı basılan adet, tutarı baskı bedeli.", fp)
    return ("Okuma sorgusu", "", None)


class _Ctx:
    def __init__(self, engine: Any, tenant: str, snap: Optional[dict[str, Any]]):
        self.engine, self.tenant, self.snap = engine, tenant, snap or {}
        # Veri sonu: Logo'daki son GERÇEK depo girişi (planlanan giriş fişleri ileri tarihlidir).
        real = [str(r.get("tarih"))[:10] for r in self.snap.get("receipts") or []
                if int(r.get("ps") or 0) == 0 and r.get("tarih") is not None]
        self.k = P.Kaynaklar(as_of=self.snap.get("at"), data_end=max(real) if real else None)
        self._reads: Optional[dict[str, str]] = None

    # ---- kaynaklar
    def reads(self) -> dict[str, str]:
        """Okumada çalışan CRM/Logo sorguları → etiket: kayıt kimliği (bir kez kaydedilir)."""
        if self._reads is not None:
            return self._reads
        self._reads = {}
        for q in self.snap.get("queries") or []:
            tag = str(q.get("tag") or "")
            if not q.get("sql") or not tag:
                continue
            title, desc, period = _title(q)
            conn = q.get("conn") if q.get("conn") in ("logo", "crm") else "crm"
            try:
                self._reads[tag] = self.k.sorgu(
                    f"{PFX}okuma.{tag}", title, conn, q["sql"], database=q.get("database"), rows=q.get("rows"),
                    ms=q.get("dbMs"), ran_at=q.get("at"), period=period,
                    description=(desc + " Okuma 5 dakikada bir yenilenir; sonuç satırları kayda girmez.").strip())
            except P.ProvenanceError:
                continue
        return self._reads

    def ids(self, *prefixes: str) -> list[str]:
        return [sid for tag, sid in self.reads().items() if not prefixes or any(tag.startswith(p) for p in prefixes)]

    def note(self) -> str:
        return "" if self.reads() else NO_READ

    def portal(self, sid: str, title: str, stmt: Any, desc: str, origin: Iterable[str] = ()) -> str:
        sid = PFX + sid
        if sid in self.k.sources:
            return sid
        return self.k.portal(sid, title, stmt, self.engine, description=desc, origin=origin)

    def entries(self, cid: Optional[str] = None) -> str:
        return self.portal("kayitlar" + (".kart" if cid else ""), "Portal kayıtları (tarih, hedef yayın, kalite, not, onay)",
                           store.entries_stmt(self.tenant, [cid] if cid else None),
                           "CRM'de olmayan ya da CRM'e yazılamayan kayıtlar (semantic_production_entries); elle girilir, "
                           "kimin girdiği yazar. " + F_ELLE)

    def quotes(self, cid: Optional[str] = None) -> str:
        return self.portal("teklifler" + (".kart" if cid else ""), "Matbaa teklifleri",
                           store.quotes_stmt(self.tenant, [cid] if cid else None),
                           "Karta girilen matbaa teklifleri: adet başı fiyat, toplam, teslim günü (semantic_production_quotes). "
                           + F_ELLE)

    def settings(self) -> str:
        from semantic_bridge import admin as ADM

        src = self.portal("ayarlar", "Üretim ayarları (ekrandan girilenler)",
                          sa.select(ADM.SETTINGS.c.key, ADM.SETTINGS.c.value).where(ADM.SETTINGS.c.key.in_(SETTING_KEYS)),
                          "Yönetim ekranında girilen üretim ayarları.")
        return self.k.hesap("ayar", F_AYAR, [src])

    # ---- hesaplar
    def cards(self) -> str:
        if "kart" in self.k.formulas:
            return "hesap:kart"
        ins = self.ids() + [self.entries(), self.settings()]
        return self.k.hesap("kart", F_KART + " " + F_PLAN + self.note(), ins)

    def cost(self) -> str:
        if "bedel" in self.k.formulas:
            return "hesap:bedel"
        return self.k.hesap("bedel", F_BEDEL + self.note(), self.ids("logo.faturalar", "crm.kartlar") or [self.cards()])

    def logo_qty(self) -> str:
        if "depoAdet" in self.k.formulas:
            return "hesap:depoAdet"
        return self.k.hesap("depoAdet", "Depoya giren adet = kartın Logo üretim emrine bağlı gerçek giriş fişlerinin Σ AMOUNT'u "
                            "(PRODSTAT 0)." + self.note(), self.ids("logo.emirler", "logo.girisler", "crm.kartlar") or [self.cards()])

    def leads(self) -> str:
        return self.k.hesap("sure", F_SURE, [self.cards()])

    def template(self) -> str:
        return self.k.hesap("sablon", F_SABLON + self.note(), self.ids("crm.kartlar") or [self.cards()])

    def printers(self) -> str:
        return self.k.hesap("matbaa", F_MATBAA, [self.cards(), self.cost(), self.entries()])


def _numeric(v: Any) -> bool:
    return bool(P.numeric_paths(v)) if isinstance(v, (dict, list)) else isinstance(v, (int, float)) and not isinstance(v, bool)


def _rest(out: dict[str, Any], fields: dict[str, str], ref: str) -> dict[str, str]:
    """Açıkça yazılmamış rakam taşıyan üst anahtarlar genel kart hesabına bağlanır (yeni alan kaynaksız kalmasın)."""
    for key, v in out.items():
        if key != "kaynaklar" and key not in fields and key not in NOT_RAKAM and _numeric(v):
            fields[key] = ref
    return fields


def for_overview(engine: Any, tenant: str, out: dict[str, Any], snap: Optional[dict[str, Any]]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant, snap)
    k = x.k
    cards = x.cards()
    ozet = k.hesap("ozet", F_OZET + " " + F_PLAN, [cards, x.settings()])
    fields = {key: ozet for key in ("total", "open", "late", "escalated", "dueSoon", "doneRecent", "byStage", "logoMatched")}
    fields.update({
        "leads": x.leads(), "template": x.template(),
        "logo": k.hesap("logo", "Logo'da okunan firmalar ve son gerçek depo girişi (PRODSTAT 0 giriş fişlerinin en büyük "
                        "tarihi), son üretim emri tarihi." + x.note(), x.ids("logo.") or [cards]),
        "db": k.hesap("okuma", F_OKUMA + x.note(), x.ids() or [cards]),
    })
    k.alanlar(_rest(out, fields, cards))
    return k


def for_list(engine: Any, tenant: str, out: dict[str, Any], snap: Optional[dict[str, Any]]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant, snap)
    cards = x.cards()
    liste = x.k.hesap("liste", "Liste süzgeçleri (durum: süren = depoya girmemiş, iptal ve eski olmayan; gecikmede; depoya girdi; "
                      "eski; hepsi · matbaa · baskı türü · ürün · arama) uçta uygulanır; sıra en büyük gecikme, sonra en yakın "
                      "plan günü. «/ N» süzgece uyan kart sayısıdır; sayfa başına 50 kart gösterilir.", [cards])
    fields = {"items[]": cards, "items[].delays": cards, "items[].price": x.cost(), "items[].unitPrice": x.cost(),
              "items[].costQty": x.cost(), "items[].logoQty": x.logo_qty(), "total": liste}
    x.k.alanlar(_rest(out, fields, cards))
    return x.k


def for_delays(engine: Any, tenant: str, out: dict[str, Any], snap: Optional[dict[str, Any]]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant, snap)
    cards = x.cards()
    gec = x.k.hesap("gecikme", "Gecikmeler: gecikmesi olan bütün kartlar, en büyük gecikmeye göre. Yöneticiye çıkan = gecikmesi "
                    "ayardaki günü aşan kart, sorumluda = aşmayan (ekrandaki iki grubun sayısı). " + F_PLAN, [cards, x.settings()])
    fields = {"items[]": gec, "items[].price": x.cost(), "items[].unitPrice": x.cost(), "items[].costQty": x.cost(),
              "items[].logoQty": x.logo_qty(), "escalateDays": x.settings(),
              "sayac.yonetici": gec, "sayac.sorumlu": gec}
    x.k.alanlar(_rest(out, fields, gec))
    return x.k


def for_printers(engine: Any, tenant: str, out: dict[str, Any], snap: Optional[dict[str, Any]]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant, snap)
    m = x.printers()
    x.k.alanlar(_rest(out, {"items[]": m, "priceRef": m}, m))
    return x.k


def for_detail(engine: Any, tenant: str, cid: str, out: dict[str, Any], snap: Optional[dict[str, Any]]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant, snap)
    k = x.k
    cards = x.cards()
    crm = x.ids("crm.kartlar")
    crm_ref = k.hesap("crmKart", f"CRM üretim kartının kendi alanları (new_UretimId = '{cid}'): kesin baskı adedi "
                      "(new_kesinlesenbaskiadeti; boşsa net baskı adedi), önerilen adet, kesinleşen satış fiyatı, baskı no. "
                      "Okumada bütün kartlar okunur; bu kartın satırı bu kimliktir." + x.note(), crm or [cards])
    firm = str(((out.get("logoOrders") or [{}])[0] or {}).get("firm") or "")
    orders = x.ids(f"logo.emirler.{firm}") if firm else []
    receipts = x.ids(f"logo.girisler.{firm}") if firm else []
    emir = k.hesap("emir", "Karta bağlanan Logo üretim emri: " + ("üretim no ile" if out.get("logoMatch") == "no" else
                   "stok kodu ve kartın zaman penceresiyle") + " eşlendi; planlanan adet PLNAMOUNT. Giriş fişleri emre bağlı "
                   "üretimden giriş fişleri (planlanan / gerçek)." + x.note(), orders + receipts or [cards])
    oneri = k.hesap("oneri", F_ONERI + " " + F_MATBAA, [x.printers(), x.quotes(cid)])
    fields = {
        "qty": crm_ref, "qtySuggested": crm_ref, "coverPrice": crm_ref, "printNo": crm_ref,
        "price": x.cost(), "unitPrice": x.cost(), "costQty": x.cost(), "logoCosts[]": x.cost(),
        "logoQty": x.logo_qty(), "logoOrders[]": emir, "logoReceipts[]": emir,
        "delays": cards, "plan": cards, "actual": cards,
        "quotes[]": x.quotes(cid), "entries[]": x.entries(cid), "suggestions[]": oneri,
    }
    k.alanlar(_rest(out, fields, cards))
    return k


def for_calendar(engine: Any, tenant: str, out: dict[str, Any], snap: Optional[dict[str, Any]]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant, snap)
    cards = x.cards()
    ayar = x.settings()
    tak = x.k.hesap("takvim", F_TAKVIM, [x.leads(), x.template(), ayar])
    fields = {"rule": ayar, "leads": "hesap:sure", "template": "hesap:sablon", "plan": tak, "expected": tak, "extra": tak}
    x.k.alanlar(_rest(out, fields, cards))
    return x.k


def for_meta(engine: Any, tenant: str, out: dict[str, Any], snap: Optional[dict[str, Any]]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant, snap)
    ayar = x.settings()
    fields = {"settings": ayar}
    if x.ids("crm.secenekler"):
        fields["printers"] = x.ids("crm.secenekler")[0]
    x.k.alanlar(_rest(out, fields, ayar))
    return x.k
