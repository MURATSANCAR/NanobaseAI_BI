"""M32 Kurumsal satış ve B2B: ekrandaki her rakamın sorgu bilgisi (ortak sözleşme `provenance.py`).

Kurum alımları, kitap kartı (stok, fiyat, bayi satışı), bayi tablosu, tema bağları ve hacim indirimi geçmişi köprünün
`semantic_corp_*` tablolarındadır; tabloları gece okuması (her gece 04:00 ya da «Verileri yenile») Logo ve CRM'den
doldurur. Gösterilen portal SQL'i uçta çalışan ifadenin kendisidir (`corporate_sales.*_stmt`); tabloyu dolduran asıl
sorgu (`origin`) okumada ÇALIŞAN Logo/CRM metnidir — yıl kopyası (LG_211 = 2021–2025, LG_411 = 2026; eşleme
`L_CAPIPERIOD`), tarih penceresi ve kanal yerinde, satır ve süreyle — okuma bitince `semantic_corp_meta` «sorgular»
kaydına yazılır (`corporate_sales.logged`). Kayıt yoksa (bu sürümden önceki okuma) köken boş kalır ve açıklama bunu söyler.

Fırsat, teklif, tema kararı ve hatırlatma durumu portal kaydıdır (elle girilir ya da kuralla üretilir). Teklif
tutarları, büyüme, pipeline değeri ve bayi günü Python'da ya da ön yüzde hesaplanır: formülü `hesap` olarak yazılır.
Bayi ayrıntısı Logo'dan anlık okunur: o istekte çalışan metin gösterilir.
"""
from __future__ import annotations

import re
from typing import Any, Iterable, Optional

import sqlalchemy as sa

from semantic_bridge import corporate_sales as C
from semantic_bridge import corporate_sales_sources as src
from semantic_bridge import provenance as P

PFX = "kurumsal."

#: Okuma adımlarının etiketleri (`corporate_sales.Refresher.run` → `logged`): hangi tabloyu doldurduğu.
DONEM = ("donem", "veriSonu")
T_SALES = ("kurumSatis",) + DONEM
T_ACCOUNTS = ("kurumCari", "crmKurum", "kurumSatis") + DONEM
T_BOOKS = ("stok", "fiyat", "bayiKitap", "maliyet", "crmKitap") + DONEM
T_THEMES = ("crmTema",)
T_VOCAB = ("crmTemaAdlari",)
T_VOLUME = ("hacim",) + DONEM
T_DEALERS = ("bayiFatura", "bayiSatis", "crmB2b", "crmWeb") + DONEM

TITLES = {
    "donem": "Logo yıl → firma kopyası (dönem tanımları)",
    "veriSonu": "Logo satış verisinin son günü (güncel yıl kopyası)",
    "kurumCari": "Logo kurum carileri (özel kod 2 = kurum kanalı)",
    "crmKurum": "CRM kurum kartları: temsilci, kurum rolü, e-posta izni",
    "hacim": "Logo kurum faturaları: fatura başına adet, brüt ve net (hacim indirimi geçmişi)",
    "stok": "Logo stok bakiyesi ve bu yıl net satış adedi",
    "fiyat": "Logo bugün geçerli TL satış fiyat listeleri",
    "bayiKitap": "Logo bayi kanalında kitap başına net adet (son ve önceki dönem)",
    "maliyet": "Logo son maliyetli satış satırı (tahmini birim maliyet)",
    "crmKitap": "CRM kitap kartları (yazar, kitaplık, yaş, özet)",
    "crmTema": "CRM kitap ↔ tema bağları",
    "crmTemaAdlari": "CRM tema adları",
    "bayiFatura": "Logo bayi kanalı satış faturaları",
    "bayiSatis": "Logo bayi kanalı net ciro",
    "crmB2b": "CRM B2B portal siparişleri (bayi başına sayı)",
    "crmWeb": "CRM bayi web kullanıcısı sayısı",
    "bayiAyrinti": "Logo bayinin kitap karması (anlık okuma)",
}

F_NET = ("Net ciro = Σ LINENET (TRCODE 7/8/9 satış) − Σ LINENET (TRCODE 2/3 iade); faturalı satış satırı (LINETYPE 0, "
         "iptal değil, INVOICEREF ≠ 0); kanal = cari özel kodu 2 (CLCARD.SPECODE2). Her yıl kendi Logo firma kopyasından "
         "okunur ve cari koduyla birleştirilir; satış faturası sayısı fatura başlığından (TRCODE 7/8/9, iptal değil).")
F_DONEM = ("Dönem: Logo verisinin bittiği aydan önceki tam aylar (veri Ocak'ta bitiyorsa Ocak); bu yıl = Ocak–o ay, geçen "
           "yıl aynı dönem = geçen yılın aynı ayları.")
F_BUYUME = "Büyüme % = bu yıl dönem cirosu ÷ geçen yıl aynı dönem cirosu − 1; geçen yıl 0 ise yazılmaz (ekranda hesaplanır)."
F_FIRSAT = ("Açık fırsat = aşaması Aday, Görüşüldü, Teklif ya da Karar olan fırsatlar (bütün ekibi görme yetkisi yoksa yalnız "
            "sizinkiler); tahmini = Σ fırsatın elle girilen tahmini değeri.")
F_HATIRLATMA = ("Hatırlatma: bu ay ve başlangıcı bugünden hatırlatma günü (ayar) içinde olan aylar için, geçen yıl aynı ayda "
                "KURUM kanalında net alımı (> 0) olan her kurum bir hatırlatma olur; tutar ve adet geçen yılın o ayındaki net "
                "ciro ve net adettir (hatırlatma üretilirken kurum alım tablosundan yazılır). Toplam = Σ geçen yıl tutarı "
                "(listedeki durum süzgeciyle).")
F_BAYI = ("Bayi = gece okumasında (veri sonuna göre) son 12 ayda en az bir satış faturası olan bayi kanalı carisi. Gün = Logo "
          "verisinin bittiği gün − son satış faturası günü; sipariş vermeyen (sessiz) = gün ≥ eşik (ayar ya da ekrandaki gün), "
          "diğerleri aktif. 12 ay fatura = satış faturası sayısı; 12 ay net ciro = net ciro tanımı; sınıf: 12 ay cirosu "
          "büyükten küçüğe sıralanır, önceki bayilerin birikimli payı %80'in altındaysa A, %95'in altındaysa B, sonrası C. "
          "B2B sipariş = CRM'de son N gün (ayar) B2B portal siparişi sayısı; B2B kullanıcı = etkin web kullanıcısı sayısı "
          "(CRM okunamadıysa boş). Liste süzgeçleri (durum, sınıf, kanal, arama) uçta uygulanır.")
F_TEKLIF = ("Kalem: liste fiyatı Logo'da bugün geçerli TL satış listesinden (cariye bağlı olmayan liste, küçük öncelik, en yeni "
            "başlangıç), yoksa CRM fiyatı, elle girilmişse o; indirim kalemde girilir, girilmezse hacim kuralı; net birim = "
            "liste × (1 − indirim); tutar = net birim × adet; liste tutarı = liste × adet; stok = kitap kartındaki Logo stok "
            "bakiyesi. Toplam liste = Σ liste tutarı; teklif tutarı = Σ tutar; indirim oranı = 1 − teklif tutarı ÷ toplam "
            "liste; toplam maliyet = Σ birim maliyet × adet (maliyeti bilinen kalemler); marj = (maliyetli kalemlerin tutarı − "
            "toplam maliyet) ÷ maliyetli kalemlerin tutarı; maliyet kapsamı = maliyetli kalemlerin tutarı ÷ teklif tutarı. Onay "
            "gerekir: bir kalemin indirimi onay eşiğini aşarsa ya da marj alt sınırın altındaysa. Tutarlar teklif kaydedildiği "
            "andaki kitap kartı, maliyet ve kurallarla hesaplanıp teklif kaydına yazılır.")
F_TASLAK = ("Kaydedilmemiş değişiklikte ekranda: tutar = liste fiyatı × (1 − indirim) × adet; liste fiyatıyla = Σ liste × "
            "adet; teklif tutarı = Σ tutar; indirim = 1 − teklif tutarı ÷ liste fiyatıyla. Kaydedince fiyat listesi ve "
            "kurallarla yeniden hesaplanır.")
F_HACIM = ("Önerilen indirim: ayarda hacim kademesi varsa toplam adedin geçtiği en yüksek kademenin oranı; yoksa son 12 ayın "
           "KURUM kanalı faturalarında aynı adet aralığındaki gerçekleşen iskontonun ortancası (fatura başına 1 − Σ LINENET ÷ "
           "Σ TOTAL); aralıkta en az N fatura (ayar) yoksa öneri 0. Elle girilen indirim kuralın önüne geçer.")
F_PAKET = ("Aday = seçilen temalardan birinde onaylı etiketi olan (CRM bağı ya da onaylanmış öneri/elle), stoğu paket sayısına "
           "yeten, bugün geçerli Logo satış fiyatı olan kitap (yaş verilmişse yaş aralığı örtüşen); elenen sayıları bu üç "
           "kuraldan. Sıra: bu yılın net satış adedi (büyükten küçüğe). Her alternatif önceki alternatiflerde kullanılmamış "
           "kitaplarla, paket başı bütçeye sığacak biçimde sırayla doldurulur. Paket net = Σ kalemin net birimi; paket liste "
           "= Σ liste fiyatı; eksik = istenen kitap sayısı − seçilen; toplamlar teklif hesabıyla aynı (adet = paket sayısı).")
F_GIRDI = ("Paket sayısı, paketteki kitap sayısı, bütçe ve yaş ekrandan girilir; paket başı bütçe = toplam bütçe ÷ paket sayısı "
           "(bütçe «paket başı» girildiyse kendisi).")
F_KAZANMA = ("Kapanan = aşaması Kazanıldı ya da Kaybedildi olan fırsatlar (yetkiye göre); kazanma oranı = kazanılan ÷ kapanan; "
             "kazanılan değer = Σ kazanılan fırsatların değeri (kabul edilen teklifte teklif tutarı); nedenler = kaybedilen "
             "fırsatların neden sınıfına göre sayısı (neden elle seçilir ya da Zeki AI önerisidir).")
F_SUTUN = ("Aşama sütunu: sayı = o aşamadaki fırsat; değer = Σ (son teklif sürümünün teklif tutarı, teklif yoksa elle girilen "
           "tahmini değer). Fırsat kartındaki tutar aynı kuraldır. Yaklaşan = açık aşamada, karar tarihi bugünden 7 gün "
           "içinde ya da geçmiş olanlar.")
F_KALAN = "Kalan gün = karar tarihi − bugün (takvim günü); eksi ise geçti (ekranda hesaplanır)."
F_KITAP = ("Kitap kartı (gece okuması): stok = Logo stok bakiyesi (güncel yıl kopyası, IOCODE 1/2 giriş − 3/4 çıkış, tarihsiz); "
           "bu yıl adet = güncel kopyada faturalı net satış adedi; liste fiyatı = bugün geçerli TL satış listesi (cariye bağlı "
           "olmayan liste önce, sonra küçük öncelik, sonra en yeni); bayi son / önceki = bayi kanalında son N gün ve ondan "
           "önceki N gün net adet (ayar); ad, yazar, kitaplık, yaş CRM kitap kartından.")
F_ONECIKAN = (F_KITAP + " Liste: stokta (> 0) ve bayi kanalında son N günde satan kitaplar; değişim = son ÷ önceki − 1 "
              "(önceki 0 ise yok); yeni = ilk yayın tarihi veri sonundan 120 gün içinde.")
F_AYRINTI = ("Bayinin son 12 ayı (veri sonuna göre): kitap başına net adet (Σ AMOUNT, iade eksi) ve net ciro, Logo'dan anlık "
             "okunur (her yıl kendi firma kopyasından, cari koduyla); kitaplık = CRM kitap kartındaki kitaplık, kitaplık başına "
             "Σ adet, Σ ciro ve kitap sayısı.")
F_EKSIK = ("Eksik tamamla = bayi kanalında son N günde satan, stokta olan ve bu bayinin 12 ayda almadığı kitaplar; adet = bayi "
           "kanalında son N gün net adedi (kitap kartından).")
F_TEMA = ("Tema durum sayıları = tema etiketi (kitap × tema) sayısı, duruma göre; liste = seçilen durumda en az bir etiketi olan "
          "kitaplar (100 satırlık sayfa, toplam ayrıca). CRM bağları doğrudan onaylıdır; öneriler Zeki AI kapalı küme "
          "seçimidir (olasılık seçimin güvenidir), insan onaylayana kadar öneridir. Stok kitap kartındaki Logo bakiyesidir.")
F_KURUM = ("Kurumlar: Logo'da özel kod 2 = kurum kanalı olan cariler ve CRM kurum kartları (rol ya da kanal KURUM); tutarlar "
           "kurum alım tablosundan kurum başına: dönem (bu yıl), geçen yıl aynı dönem, geçen yıl tamamı, toplam ciro ve fatura "
           "sayısı; son alım = son satış faturası günü. Liste 100 satırlık sayfalardır; toplam ayrıca. Segment sayıları = kurum "
           "kartlarının segmentine göre sayı (segment CRM kurum rolünden, Zeki AI önerisinden ya da elle).")
F_YIL = ("Yıl × ay tablosu: kurum alım tablosundaki aylık net ciro; yıl toplamı = Σ ay; adet = Σ net adet; fatura = Σ satış "
         "faturası; en çok alım yapılan ay = bütün yıllarda ay başına Σ pozitif net ciro en büyük olan ay.")
F_ONAY = ("Onay kuyruğu: durumu «Onay bekliyor» olan teklifler (gönderim sırasıyla); tutar teklif kaydındaki teklif tutarı, "
          "neden onay kurallarından (indirim eşiği, marj alt sınırı).")
F_ELLE = "Ekrandan elle girilir (portal kaydı); hesap yok."


def _num_keys(out: dict[str, Any], ref: str, skip: Iterable[str] = ()) -> dict[str, str]:
    sk = set(skip)
    return {k: ref for k, v in (out or {}).items() if k not in sk and k != "kaynaklar" and P.numeric_paths({k: v})}


_FIRM = re.compile(r"LG_(\d{3})_")
_WIN = re.compile(r"DATE_ >= '(\d{4}-\d{2}-\d{2})' AND \w+\.DATE_ < '(\d{4}-\d{2}-\d{2})'")


def _read_title(tag: str, sql: str) -> tuple[str, Optional[str]]:
    title = TITLES.get(tag, "Okuma sorgusu")
    up = sql.upper()
    if tag in ("kurumSatis", "bayiFatura", "bayiSatis", "bayiAyrinti"):
        title += " · satış faturası sayısı" if "_01_INVOICE AS I" in up else " · net ciro ve adet"
    if tag == "crmKitap" and "POWERBIKITAP" in up:
        title = "CRM kitap raporu: yazar ve liste fiyatı"
    firm = _FIRM.search(sql)
    win = _WIN.search(sql)
    period = None
    if firm:
        period = f"Logo firma {firm.group(1)}" + (f" · {win.group(1)} – {win.group(2)} (bitiş hariç)" if win else "")
    return title, period


class _Ctx:
    def __init__(self, engine: Any, logo_db: Optional[str] = None, crm_db: Optional[str] = None):
        self.engine, self.dbs = engine, {"logo": logo_db, "crm": crm_db}
        self.k = P.Kaynaklar(data_end=C.data_end(engine))
        self._reads: Optional[list[tuple[str, str]]] = None

    def portal(self, sid: str, title: str, stmt: Any, desc: str, origin: Iterable[str] = ()) -> str:
        sid = PFX + sid
        if sid in self.k.sources:
            return sid
        return self.k.portal(sid, title, stmt, self.engine, description=desc, origin=origin)

    def reads(self) -> list[tuple[str, str]]:
        """Son okumada çalışan Logo/CRM sorguları → (etiket, kayıt kimliği). Bir kez kaydedilir; aynı metin bir kez."""
        if self._reads is not None:
            return self._reads
        self._reads = []
        seen: set[str] = set()
        count: dict[str, int] = {}
        for q in C.meta_get(self.engine, "sorgular").get("items") or []:
            sql, tag = q.get("sql") or "", str(q.get("tag") or "diger")
            if not sql or sql in seen:
                continue
            seen.add(sql)
            count[tag] = count.get(tag, 0) + 1
            conn = q.get("conn") if q.get("conn") in ("logo", "crm") else "logo"
            title, period = _read_title(tag, sql)
            try:
                sid = self.k.sorgu(f"{PFX}okuma.{tag}.{count[tag]}", title, conn, sql, database=self.dbs.get(conn),
                                   rows=q.get("rows"), ms=q.get("dbMs"), ran_at=q.get("at"), period=period,
                                   description="Gece okumasında (ya da «Verileri yenile» ile) çalıştı; sonucu köprünün "
                                               "kurumsal satış tablolarına yazıldı.")
            except P.ProvenanceError:
                continue
            self._reads.append((tag, sid))
        return self._reads

    def origin(self, tags: Iterable[str]) -> list[str]:
        want = set(tags)
        return [sid for tag, sid in self.reads() if tag in want]

    def note(self, tags: Iterable[str]) -> str:
        return "" if self.origin(tags) else (" Okuma sorguları bu sürümden sonraki ilk okumada (gece 04:00 ya da «Verileri "
                                             "yenile») kaydedilir; o zamana kadar köken boş.")

    def cached(self, sid: str, title: str, stmt: Any, desc: str, tags: Iterable[str]) -> str:
        """Gece okumasının doldurduğu tablo: portal SQL'i + köken (okumada çalışan Logo/CRM metni)."""
        tags = tuple(tags)
        return self.portal(sid, title, stmt, desc + self.note(tags), origin=self.origin(tags))

    # ---------------------------------------------------------------- ortak kaynaklar

    def data_end(self) -> str:
        return self.cached("veriSonu", "Logo veri sonu (okuma kaydı)", C.meta_stmt("data_end"),
                           "Gece okumasında Logo'nun son satış faturası günü; gün ve dönem hesapları buna göre.", DONEM)

    def sales(self, code: Optional[str] = None) -> str:
        if code is None:
            return self.cached("kurumAlim", "Kurum alım tablosu (cari × yıl × ay)", C.sales_stmt(),
                               "KURUM kanalı carilerinin aylık net ciro, adet ve satış faturası sayısı (son yıllar, ayar).",
                               T_SALES)
        return self.cached("kurumAlimTek", "Kurumun aylık alımları", C.sales_stmt(code),
                           "Bu kurumun KURUM kanalındaki aylık net ciro, adet ve satış faturası sayısı.", T_SALES)

    def books(self, codes: Optional[list[str]] = None, sid: str = "kitaplar", title: str = "Kitap kartları") -> str:
        return self.cached(sid, title, C.books_stmt(codes), "Stok, bu yıl adet, liste fiyatı, bayi satışı ve CRM bilgisi "
                                                            "(gece okumasında yazılır).", T_BOOKS)

    def settings(self, st: dict[str, Any]) -> str:
        from semantic_bridge import admin as ADM

        keys = sorted(C.DEFAULTS)
        s = self.portal("ayarlar", "Kurumsal satış ayarları (ekrandan girilenler)",
                        sa.select(ADM.SETTINGS.c.key, ADM.SETTINGS.c.value).where(ADM.SETTINGS.c.key.in_(keys)),
                        "Yönetim ekranında (Kurumsal satış ve B2B) girilen ayarlar; girilmeyen ayar ortam değerinden ya da "
                        "varsayılandan gelir.")
        tiers = "; ".join(f"{lo} adet ve üstü %{r * 100:g}" for lo, r in st.get("volumeTiers") or []) or "yok (geçmiş ortancası)"
        text = (f"Ayarlar: kurum kanalı {st['channel']}; bayi kanalları {', '.join(st['dealerChannels'])}; kurum geçmişi "
                f"{st['historyYears']} yıl; teklif onay eşiği indirim "
                f"{'yok' if st['discountApprovalPct'] is None else '%' + format(st['discountApprovalPct'], 'g')}, en düşük marj "
                f"{'yok' if st['marginMinPct'] is None else '%' + format(st['marginMinPct'], 'g')}; hacim kademeleri {tiers}; hacim aralıkları {st['volumeBuckets']}, en az "
                f"{st['volumeMinN']} fatura; hatırlatma {st['reminderLeadDays']} gün önce; sipariş vermeyen bayi "
                f"{st['silentDays']} gün; B2B penceresi {st['b2bDays']} gün; öne çıkan kitap penceresi {st['highlightDays']} "
                f"gün; paket alternatifi {st['alternatives']}; teklif geçerliliği {st['quoteValidDays']} gün; birim maliyet "
                f"kaynağı {src.COST_SOURCES.get(st['costSource'], st['costSource'])}.")
        return self.k.hesap("ayar", text, [s])

    def volume(self) -> str:
        return self.cached("hacimGecmisi", "Hacim indirimi geçmişi (okuma kaydı)", C.meta_stmt("volume"),
                           "Son 12 ayın kurum faturalarında adet aralığı başına fatura sayısı ve gerçekleşen iskonto "
                           "ortancası (gece okumasında hesaplanır).", T_VOLUME)

    def costs(self, st: dict[str, Any], codes: list[str], tenant: str) -> tuple[list[str], str]:
        """Birim maliyetin kaynağı (ayar CORP_COST_SOURCE) → kayıtlar ve hesap metni."""
        source = st.get("costSource") or "m9"
        if source == "logo":
            ids = [self.cached("maliyetLogo", "Kitap kartındaki Logo son maliyeti", C.logo_costs_stmt(codes or ["-"]),
                               "Gece okumasında kitabın en son maliyeti girilmiş satış satırından yazılır (tahmini).",
                               ("maliyet",) + DONEM)]
            return ids, ("Birim maliyet: Logo'da kitabın en son maliyeti girilmiş satış satırının birim maliyeti (OUTCOST), "
                         "«tahmini» etiketiyle; bulunmayan kalemde maliyet bilinmiyor.")
        if source == "m9":
            from semantic_bridge.pricing import store as PS

            ids = [self.portal("maliyetM9", "Onaylı fiyat analizleri (birim maliyet)", PS.analyses_stmt(tenant, status="onaylandi"),
                               "Kitabın onaylanmış fiyat analizindeki birim maliyet (kesin aşama tahmininin önüne geçer, "
                               "sonra en son onaylanan).")]
            prov = getattr(src._COST_PROVIDER, "__self__", None)
            snap = None
            if prov is not None and hasattr(prov, "_snap"):
                snap = prov._snap()
            if snap:
                from semantic_bridge.pricing.kaynak import snap_sources

                ids += snap_sources(self.k, snap, ["logo_satis"], self.dbs.get("logo"), self.dbs.get("crm"))
            return ids, ("Birim maliyet fiyatlama modülünden: önce kitabın onaylı fiyat analizindeki birim maliyet, yoksa "
                         "fiyatlamanın Logo görüntüsündeki gerçekleşen maliyet (maliyeti girilmiş satışların en son yılı, "
                         "Σ adet × OUTCOST ÷ maliyetli adet); ikisi de yoksa maliyet bilinmiyor, uydurulmaz.")
        return [], "Birim maliyet kullanılmaz (ayar); marj hesaplanmaz."


# ---------------------------------------------------------------- genel


def for_meta(engine: Any, st: dict[str, Any], out: dict[str, Any], logo_db: Optional[str], crm_db: Optional[str]) -> P.Kaynaklar:
    x = _Ctx(engine, logo_db, crm_db)
    k = x.k
    ayar = x.settings(st)
    vol = x.volume()
    names = x.cached("temaAdlari", "CRM tema adları (okuma kaydı)", C.meta_stmt("crm_themes"),
                     "Tema kapalı listesi = ayardaki temalar + CRM'deki etkin temalar.", T_VOCAB)
    refresh = x.portal("okumaDurumu", "Son okuma kaydı", C.meta_stmt("refresh"),
                       "Son okumanın sonucu: yazılan satır sayıları, uyarılar, süre (saniye).")
    k.alanlar({
        "settings": ayar, "volumeTiers": ayar,
        "volume": k.hesap("hacim", F_HACIM, [vol, ayar]),
        "status": k.hesap("okuma", "Okuma durumu: sürüyor mu, adım, son okumanın yazdığı satır sayıları ve süresi.", [refresh]),
        "vocabularyCount": k.hesap("temaSayisi", "Tema kapalı listesindeki tema sayısı = ayardaki temalar ∪ CRM'deki etkin "
                                                 "temalar (harf katlamasıyla tekilleştirilir; ekranda sayılır).", [names, ayar]),
    })
    return k


def for_summary(engine: Any, tenant: str, st: dict[str, Any], out: dict[str, Any], logo_db: Optional[str],
                crm_db: Optional[str]) -> P.Kaynaklar:
    x = _Ctx(engine, logo_db, crm_db)
    k = x.k
    end = x.data_end()
    w = out.get("window")
    ytd = (x.cached("kurumCiroDonem", "Kurum cirosu: bu yıl ve geçen yılın aynı ayları",
                    C.ytd_sales_stmt(w), "Kurum alım tablosunun dönem satırları (yıl, ay, net ciro).", T_SALES)
           if w else x.sales())
    ciro = k.hesap("kurumCiro", F_NET + " " + F_DONEM + " Kart = Σ bu yıl dönem net cirosu; geçen yıl aynı dönem = Σ geçen "
                                                       "yılın aynı ayları.", [ytd, end])
    accs = x.cached("kurumSayisi", "Kurum kartı sayısı", C.accounts_count_stmt(tenant),
                    "Logo kurum carileri ve CRM kurum kartları (gece okumasında birleştirilir).", T_ACCOUNTS)
    opps = x.portal("acikFirsatlar", "Açık fırsatlar", C.open_opps_stmt(tenant), "Fırsatlar elle açılır ya da hatırlatmadan; "
                                                                                 "tahmini değer elle girilir.")
    pend = x.portal("onayBekleyenSayi", "Onay bekleyen teklif sayısı", C.pending_quotes_count_stmt(tenant),
                    "Teklif kayıtları (portal); durum onay kurallarıyla belirlenir.")
    themes = x.cached("temaOnerisiSayi", "Onay bekleyen tema önerisi sayısı", C.theme_suggestions_count_stmt(),
                      "Zeki AI'ın kitaplara önerdiği, henüz onaylanmamış temalar.", T_THEMES)
    months = C.reminder_months(C.today(), st["reminderLeadDays"])
    rem = _reminders(x, tenant, months, "acik")
    dealers = x.cached("bayiler", "Bayi tablosu", C.dealers_stmt(), "Bayi kanalı carileri: son satış faturası, 12 ay fatura ve "
                                                                     "ciro, sınıf, B2B sayıları.", T_DEALERS)
    ayar = x.settings(st)
    k.alanlar({
        "kurumCiro": ciro, "kurumCiroGecenYil": ciro,
        "kurumCiroBuyume": k.hesap("buyume", F_BUYUME, [ciro]),
        "kurumSayisi": accs,
        "acikFirsat": k.hesap("firsat", F_FIRSAT, [opps]), "acikFirsatDeger": "hesap:firsat",
        "onayBekleyen": pend,
        "temaOnerisi": k.hesap("temaOnerisi", F_TEMA, [themes]),
        "hatirlatma": k.hesap("hatirlatma", F_HATIRLATMA + " Kart ve sekme rozeti = açık hatırlatma sayısı.", [rem, ayar]),
        "hatirlatmaTutar": "hesap:hatirlatma",
        "sessizBayi": k.hesap("bayi", F_BAYI + " Kart: sipariş vermeyen bayi sayısı ve bütün bayi sayısı.", [dealers, end, ayar]),
        "bayi": "hesap:bayi",
    })
    return k


def _reminders(x: _Ctx, tenant: str, months: list[str], durum: str) -> str:
    """Hatırlatma listesi: portal kaydı; kökeni onu üreten okuma (geçen yılın o ayındaki kurum alım satırları)."""
    gen = []
    for ym in months:
        y, m = int(ym[:4]), int(ym[5:])
        gen.append(x.cached(f"hatirlatmaKaynagi.{ym}", f"Hatırlatmayı üreten okuma · {ym}", C.reminder_sales_stmt(y - 1, m),
                            f"Geçen yılın aynı ayında ({y - 1}-{m:02d}) net alımı olan kurumlar; hatırlatma üretilirken "
                            f"tutar ve adet buradan yazılır.", T_SALES))
    return x.portal("hatirlatmalar", "Dönemsel hatırlatmalar", C.reminders_stmt(tenant, months, durum),
                    "Hatırlatma kayıtları (her okumada üretilir; durum elle değişir).", origin=gen)


# ---------------------------------------------------------------- kurumlar


def for_accounts(engine: Any, tenant: str, out: dict[str, Any], *, q: str = "", segment: str = "", temsilci: str = "",
                 logo_db: Optional[str] = None, crm_db: Optional[str] = None) -> P.Kaynaklar:
    x = _Ctx(engine, logo_db, crm_db)
    k = x.k
    accs = x.cached("kurumlar", "Kurum kartları", C.accounts_stmt(tenant, q=q, segment=segment, temsilci=temsilci),
                    "Logo kurum carileri ve CRM kurum kartları (ekrandaki arama ve segment süzgeciyle).", T_ACCOUNTS)
    sales = x.sales()
    end = x.data_end()
    seg = x.cached("segmentSayilari", "Segment başına kurum sayısı", C.segment_counts_stmt(tenant),
                   "Süzgeç kutusundaki sayılar.", T_ACCOUNTS)
    ref = k.hesap("kurumlar", F_KURUM + " " + F_NET + " " + F_DONEM, [accs, sales, end])
    k.alanlar({"items[]": ref, "total": ref, "segments": seg})
    return k


def for_account(engine: Any, tenant: str, ref: str, out: dict[str, Any], logo_db: Optional[str] = None,
                crm_db: Optional[str] = None) -> P.Kaynaklar:
    x = _Ctx(engine, logo_db, crm_db)
    k = x.k
    code = out.get("logoKod") or ""
    acc = x.cached("kurum", "Kurum kartı", C.account_stmt(tenant, ref), "Logo carisi ve CRM kurum kartı (gece okumasında "
                                                                        "birleştirilir); iskonto Logo cari kartından.", T_ACCOUNTS)
    sales = x.sales(code)
    end = x.data_end()
    opps = x.portal("kurumFirsatlari", "Kurumun fırsatları", C.account_opps_stmt(tenant, ref), F_ELLE)
    rems = x.portal("kurumHatirlatmalari", "Kurumun hatırlatmaları", C.account_reminders_stmt(tenant, code),
                    "Hatırlatma üretilirken geçen yılın o ayındaki net ciro ve adet yazılır.", origin=[sales])
    ozet = k.hesap("kurum", F_NET + " " + F_DONEM + " Kurum: bu yıl dönem, geçen yıl aynı dönem, geçen yıl, toplam ciro ve "
                                                     "fatura sayısı kurumun aylık alım satırlarından.", [acc, sales, end])
    fields = _num_keys(out, ozet, skip=("yillar", "firsatlar", "hatirlatmalar", "window", "enCokAy", "logoRef"))
    fields.update({
        "buyume": k.hesap("buyume", F_BUYUME, [ozet]),
        "yillar[]": k.hesap("yillar", F_YIL, [sales]), "enCokAy": "hesap:yillar",
        "firsatlar[]": k.hesap("firsatlar", "Fırsatın değeri elle girilen tahmini değerdir; kabul edilen teklifte teklif "
                                             "tutarı yazılır.", [opps]),
        "hatirlatmalar[]": k.hesap("hatirlatmalar", F_HATIRLATMA, [rems]),
    })
    k.alanlar(fields)
    return k


# ---------------------------------------------------------------- kitaplar, temalar, paket


def for_books(engine: Any, q: str, page: int, out: dict[str, Any], logo_db: Optional[str] = None,
              crm_db: Optional[str] = None) -> P.Kaynaklar:
    x = _Ctx(engine, logo_db, crm_db)
    k = x.k
    total_stmt, rows_stmt = C.book_search_stmts(q, page)
    note = "" if len((q or "").strip()) >= 2 else " Arama 2 harften kısaysa sorgu çalışmaz, liste boş döner."
    rows = x.cached("kitapArama", "Kitap arama (ad, stok kodu, yazar)", rows_stmt,
                    "Bu yıl satış adedine göre sıralı, 100 satırlık sayfa." + note, T_BOOKS)
    total = x.portal("kitapAramaToplam", "Aramaya uyan kitap sayısı", total_stmt, "Sayfalamanın toplamı." + note)
    codes = [i.get("stokKodu") for i in out.get("items") or [] if i.get("stokKodu")]
    th = x.cached("kitapTemalari", "Kitapların tema etiketleri", C.themes_stmt(codes or ["-"]), "CRM bağı, öneri ya da elle.",
                  T_THEMES)
    k.alanlar({"items[]": k.hesap("kitap", F_KITAP, [rows, th]), "total": total})
    return k


def for_themes(engine: Any, st: dict[str, Any], out: dict[str, Any], *, durum: str = "", q: str = "", tema: str = "",
               logo_db: Optional[str] = None, crm_db: Optional[str] = None) -> P.Kaynaklar:
    x = _Ctx(engine, logo_db, crm_db)
    k = x.k
    codes_src = x.cached("temaKitaplari", "Seçilen durumda etiketi olan kitaplar", C.theme_codes_stmt(durum, q, tema),
                         "Stok kodları; sayfa uçta 100 satır olarak kesilir, toplam bu sorgunun satır sayısıdır.", T_THEMES)
    codes = [i.get("stokKodu") for i in out.get("items") or [] if i.get("stokKodu")]
    books = x.books(codes or ["-"], "temaSayfasiKitaplar", "Sayfadaki kitapların kartı")
    tags = x.cached("temaSayfasiEtiketler", "Sayfadaki kitapların tema etiketleri", C.themes_stmt(codes or ["-"]),
                    "CRM bağı, Zeki AI önerisi (olasılıkla) ya da elle.", T_THEMES)
    counts = x.cached("temaSayilari", "Tema etiketi sayıları (duruma göre)", C.theme_counts_stmt(),
                      "Öneri, onaylı ve reddedilen etiket sayıları.", T_THEMES)
    ref = k.hesap("temalar", F_TEMA + " " + F_KITAP, [codes_src, books, tags])
    k.alanlar({"items[]": ref, "total": codes_src, "counts": k.hesap("temaSayilari", F_TEMA, [counts])})
    return k


def for_packages(engine: Any, tenant: str, st: dict[str, Any], out: dict[str, Any], logo_db: Optional[str] = None,
                 crm_db: Optional[str] = None) -> P.Kaynaklar:
    x = _Ctx(engine, logo_db, crm_db)
    k = x.k
    ayar = x.settings(st)
    vol = x.volume()
    tags = x.cached("paketTemalari", "Onaylı tema etiketleri", C.approved_themes_stmt(),
                    "CRM bağı ya da onaylanmış öneri/elle etiket; seçilen temaya uyum Türkçe harf katlamasıyla uçta süzülür.",
                    T_THEMES)
    books = x.cached("paketAdaylari", "Onaylı temalı kitapların kartı", C.approved_books_stmt(),
                     "Stok, liste fiyatı, bu yıl adet, yaş aralığı.", T_BOOKS)
    alt_codes = sorted({l["stok"] for a in out.get("alternatifler") or [] for l in a.get("kalemler") or [] if l.get("stok")})
    cost_ids, cost_text = x.costs(st, alt_codes, tenant)
    hacim = k.hesap("hacim", F_HACIM, [vol, ayar])
    aday = k.hesap("aday", F_PAKET, [tags, books, ayar])
    fields = {
        "kisi": k.hesap("girdi", F_GIRDI, [ayar]), "kitapSayisi": "hesap:girdi", "paketBasiButce": "hesap:girdi",
        "indirim": hacim, "indirimDayanak": hacim,
        "adaySayisi": aday, "elenen": aday,
        "alternatifler[]": k.hesap("paket", F_PAKET + " " + F_TEKLIF + " " + cost_text, [aday, hacim] + cost_ids),
    }
    for a in out.get("alternatifler") or []:
        codes = [l["stok"] for l in a.get("kalemler") or [] if l.get("stok")]
        lines = x.books(codes or ["-"], f"paketKitaplari.{a['no']}", f"Alternatif {a['no']}: kalemlerin kitap kartı")
        fields[f"alternatifler[]:{a['no']}"] = k.hesap(f"paket{a['no']}", F_PAKET + " " + F_TEKLIF + " " + cost_text,
                                                       [lines, aday, hacim] + cost_ids)
    k.alanlar(fields)
    return k


# ---------------------------------------------------------------- fırsatlar ve teklifler


def for_opportunities(engine: Any, tenant: str, out: dict[str, Any], *, asama: str = "", sahip: str = "", q: str = "",
                      acik: bool = False) -> P.Kaynaklar:
    x = _Ctx(engine)
    k = x.k
    opps = x.portal("firsatlar", "Fırsatlar", C.opps_stmt(tenant, asama=asama, sahip=sahip, q=q, acik=acik),
                    "Fırsat kayıtları (elle; ekranın süzgeciyle). Görme yetkisi (sahip) uçta süzülür.")
    pend = x.portal("onayBekleyenFirsat", "Onay bekleyen teklifi olan fırsatlar", C.pending_opps_stmt(tenant),
                    "Onayda duran teklif sürümleri.")
    heads = x.portal("teklifBasliklari", "Teklif sürümleri", C.quote_heads_stmt(tenant),
                     "Fırsat başına en büyük sürüm «son teklif»tir; tutar teklif kaydındaki teklif tutarı.")
    col = k.hesap("sutun", F_SUTUN, [opps, heads, pend])
    k.alanlar({"items[]": col, "columns[]": col, "yaklasan[]": col, "kalanGun": k.hesap("kalanGun", F_KALAN, [opps])})
    return k


def for_pipeline_summary(engine: Any, tenant: str, out: dict[str, Any]) -> P.Kaynaklar:
    x = _Ctx(engine)
    closed = x.portal("kapananFirsatlar", "Kapanmış fırsatlar", C.closed_opps_stmt(tenant),
                      "Kazanıldı ya da Kaybedildi; neden sınıfı elle ya da Zeki AI önerisi.")
    ref = x.k.hesap("kazanma", F_KAZANMA, [closed])
    x.k.alanlar({**_num_keys(out, ref), "nedenler[]": ref})
    return x.k


def _quote_codes(quotes: Iterable[dict[str, Any]]) -> list[str]:
    return sorted({l.get("stok") for qd in quotes for l in qd.get("kalemler") or [] if l.get("stok")})


def for_opportunity(engine: Any, tenant: str, st: dict[str, Any], opp_id: str, out: dict[str, Any],
                    logo_db: Optional[str] = None, crm_db: Optional[str] = None) -> P.Kaynaklar:
    x = _Ctx(engine, logo_db, crm_db)
    k = x.k
    opp = x.portal("firsat", "Fırsat kaydı", C.opp_stmt(tenant, opp_id), "Tahmini değer elle girilir; kabul edilen teklifte "
                                                                         "teklif tutarı yazılır.")
    quotes = x.portal("teklifler", "Fırsatın teklif sürümleri", C.opp_quotes_stmt(tenant, opp_id),
                      "Kalemler, tutarlar ve onay nedenleri kaydedildiği andaki hesapla saklı (kalemler_json).")
    teklif = _quote_hesap(x, st, tenant, out.get("teklifler") or [], quotes)
    k.alanlar({
        "deger": k.hesap("deger", "Fırsat değeri elle girilir; kabul edilen teklifte teklif tutarı yazılır.", [opp]),
        "teklifler[]": teklif,
        "teklifler[].taslak": k.hesap("taslak", F_TASLAK, [teklif]),
        "kalanGun": k.hesap("kalanGun", F_KALAN, [opp]),
    })
    return k


def _quote_hesap(x: _Ctx, st: dict[str, Any], tenant: str, quotes: list[dict[str, Any]], quotes_src: str) -> str:
    codes = _quote_codes(quotes)
    ins = [quotes_src]
    if codes:
        ins.append(x.books(codes, "teklifKitaplari", "Teklifteki kitapların bugünkü kartı"))
    cost_ids, cost_text = x.costs(st, codes, tenant)
    return x.k.hesap("teklif", F_TEKLIF + " " + cost_text + " Kitap kartı bugünkü hâlidir; teklifteki değerler kayıt anındaki hâldir.",
                     ins + cost_ids + [x.settings(st)])


def for_quote(engine: Any, tenant: str, st: dict[str, Any], qid: str, out: dict[str, Any], logo_db: Optional[str] = None,
              crm_db: Optional[str] = None) -> P.Kaynaklar:
    x = _Ctx(engine, logo_db, crm_db)
    k = x.k
    q = x.portal("teklif", "Teklif kaydı", C.quote_stmt(tenant, qid), "Kalemler ve tutarlar kaydedildiği andaki hesapla saklı.")
    opp = x.portal("teklifFirsati", "Teklifin fırsatı", C.opp_stmt(tenant, out.get("firsatId") or ""), F_ELLE)
    teklif = _quote_hesap(x, st, tenant, [out], q)
    fields = _num_keys(out, teklif, skip=("firsat", "surum"))
    fields.update({"kalemler[]": teklif, "firsat": k.hesap("deger", "Fırsat değeri elle girilir; kabul edilen teklifte teklif "
                                                                     "tutarı yazılır.", [opp]),
                   "taslak": k.hesap("taslak", F_TASLAK, [teklif])})
    k.alanlar(fields)
    return k


def for_approvals(engine: Any, tenant: str, out: dict[str, Any]) -> P.Kaynaklar:
    x = _Ctx(engine)
    s = x.portal("onayKuyrugu", "Onay bekleyen teklifler", C.approval_queue_stmt(tenant),
                 "Teklif kaydı + fırsatın kurumu, adı ve sahibi.")
    x.k.alanlar({"items[]": x.k.hesap("onay", F_ONAY + " " + F_TEKLIF, [s])})
    return x.k


def for_reminders(engine: Any, tenant: str, st: dict[str, Any], out: dict[str, Any], durum: str = "") -> P.Kaynaklar:
    x = _Ctx(engine)
    k = x.k
    months = list(out.get("aylar") or [])
    rem = _reminders(x, tenant, months, durum)
    reps = x.portal("hatirlatmaTemsilci", "Kurum temsilcisi", C.reminder_reps_stmt(tenant), "Kurum kartından temsilci ve bağ.")
    ayar = x.settings(st)
    ref = k.hesap("hatirlatma", F_HATIRLATMA, [rem, reps, ayar])
    k.alanlar({"items[]": ref, "toplamGecenYil": ref, "leadDays": ayar})
    return k


# ---------------------------------------------------------------- bayi paneli


def for_dealers(engine: Any, st: dict[str, Any], out: dict[str, Any], logo_db: Optional[str] = None,
                crm_db: Optional[str] = None) -> P.Kaynaklar:
    x = _Ctx(engine, logo_db, crm_db)
    k = x.k
    d = x.cached("bayiler", "Bayi tablosu", C.dealers_stmt(), "Bayi kanalı carileri: son satış faturası, 12 ay fatura ve ciro, "
                                                              "sınıf, B2B sayıları.", T_DEALERS)
    end = x.data_end()
    meta = x.cached("bayiOkuma", "Bayi okuması (B2B penceresi, CRM okundu mu)", C.meta_stmt("dealers"),
                    "B2B sipariş penceresi (gün) ve CRM'in okunup okunmadığı.", ("crmB2b", "crmWeb"))
    ayar = x.settings(st)
    ref = k.hesap("bayi", F_BAYI, [d, end, meta, ayar])
    k.alanlar({"items[]": ref, "total": ref, "counts": ref, "gun": ref, "b2b": meta})
    return k


def for_dealer(engine: Any, st: dict[str, Any], code: str, out: dict[str, Any], ran: list[dict[str, Any]],
               logo_db: Optional[str] = None, crm_db: Optional[str] = None) -> P.Kaynaklar:
    x = _Ctx(engine, logo_db, crm_db)
    k = x.k
    live: list[str] = []
    seen: set[str] = set()
    for q in ran or []:
        sql = q.get("sql") or ""
        if not sql or sql in seen:
            continue
        seen.add(sql)
        title, period = _read_title("bayiAyrinti", sql)
        live.append(k.sorgu(f"{PFX}bayiAyrinti.{len(live) + 1}", title, "logo", sql, database=logo_db, rows=q.get("rows"),
                            ms=q.get("dbMs"), ran_at=q.get("at"), period=period,
                            description="Bu ekran açılırken Logo'dan anlık okundu (sonuç saklanmaz)."))
    row = x.cached("bayi", "Bayi kaydı", C.dealers_stmt(code), "Unvan, kanal, il, son satış faturası (gece okuması).", T_DEALERS)
    books = x.books(None, "kitaplar", "Kitap kartları (kitaplık, stok, bayi satışı)")
    end = x.data_end()
    mix = k.hesap("karma", F_AYRINTI, live + [books, row, end])
    k.alanlar({"kitaplik[]": mix, "alinan[]": mix,
               "eksik[]": k.hesap("eksik", F_EKSIK + " " + F_KITAP, [books] + live + [x.settings(st)])})
    return k


def for_highlights(engine: Any, st: dict[str, Any], out: dict[str, Any], logo_db: Optional[str] = None,
                   crm_db: Optional[str] = None) -> P.Kaynaklar:
    x = _Ctx(engine, logo_db, crm_db)
    k = x.k
    s = x.cached("oneCikanlar", "Öne çıkarılacak kitaplar", C.highlights_stmt(),
                 "Stokta ve bayi kanalında son dönemde satan kitap kartları, bayi satışına göre sıralı.", T_BOOKS)
    end = x.data_end()
    ref = k.hesap("onecikan", F_ONECIKAN, [s, end, x.settings(st)])
    k.alanlar({"items[]": ref, "total": ref, "gun": ref})
    return k


#: Rakam olmayan sayılar: yıl, ay sayısı (dönem penceresi), sayfa, sürüm, kimlik.
NOT_RAKAM = ("window", "page", "pageSize", "logoRef", "items[].logoRef", "items[].sonTeklif.surum", "yaklasan[].sonTeklif.surum",
             "teklifler[].surum", "surum", "items[].surum", "yillar[].yil", "firsat.surum")
