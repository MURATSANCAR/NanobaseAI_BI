"""M43 Depo ve stok: ekrandaki her rakamın sorgu bilgisi (ortak sözleşme `provenance.py`).

Rakamlar `stock.Service` okumasından (Logo + CRM; gece `timas-stock.timer` ve arka plan tazelemesi son okuma tablosuna
`semantic_stock_reads` yazar, uç oradan okur — `stok.portal.okuma`, kökeni Logo/CRM sorguları) kurulan modelden gelir. Gösterilen Logo/CRM SQL'i o okumada ÇALIŞAN metnin kendisidir (`raw["runs"]`: firma, yıl kopyası, CRM
şeması, tarih penceresi yerinde; satır, süre ve çalıştığı an ile). Okunmamış kaynağın kaydı açılmaz. Portal okumaları
(eşik, öneri, gece fotoğrafı, maliyet) uçta çalışan ifadenin kendisidir (`stock_store.*_stmt`).
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

from semantic_bridge import provenance as P
from semantic_bridge import stock_sources as src
from semantic_bridge import stock_store as store
from semantic_bridge.kaynak_ayar import ayar, bind, h

# ------------------------------------------------------------------ formüller

F_BAKIYE = ("Logo stok bakiyesi = güncel yıl kopyasında giriş (IOCODE 1, 2) − çıkış (IOCODE 3, 4), malzeme satırı "
            "(LINETYPE 0), iptaller hariç, tarih süzgeci yok; ambar = SOURCEINDEX. Planlanan üretimden giriş fişi "
            "(PRODSTAT 1) ayara göre hariç. Ayardaki öneklerle başlayan ticari ürün kodları listede yok.")
F_DAGITIM = ("Dağıtımcıda = stok kodunun Logo barkoduyla eşleşen Başarı ve D&R başlığı, son görüntü. İşaret: Logo "
             "stoğu varken Başarı «Baskısı Yok» ya da «Temin Edilemiyor» diyorsa «baskısı yok görünüyor»; «Satışta» ama "
             "Başarı deposu 0 ise «tükenmiş». Çıkış endeksi = son kesintisiz görüntü dizisinde Başarı deposundaki stok "
             "düşüşlerinin toplamı; kitapçılara çıkıştır, okura satış değildir.")
F_TOPLAM = "Toplam stok = bakiyesi sıfırdan büyük kitapların Logo bakiyesi toplamı; kitap sayısı = bu kitapların sayısı."
F_HIZ = ("Aylık satış hızı ve yıllık satış = Baskı Öneri raporunun satış hızı sorgusu (yıllık satış görünümleri, aynı "
         "ağırlıklandırma) — iki ekranda aynı sayı.")
F_GUN = ("Kaç gün yeter = Logo bakiyesi ÷ (aylık satış hızı ÷ 30); satışı yoksa boş, stok yoksa 0. Tahmini tükenme = "
         "Logo verisinin son günü + gün. Tükenme (ay) ve baskı önerisi Baskı Öneri'nin bölme ve etiket kuralıyla.")
F_KRITIK = ("Baskı süresi + güvenlik günü: baskı süresi = ayar, yoksa üretim kartlarında ölçülen gerçekleşen sürelerin "
            "ortanca toplamı (matbaa belirleme → dosya → baskı → depo girişi), o da yoksa 45 gün; güvenlik günü = "
            "kitabın onaylı eşiği, yoksa ayar. Kaç gün yeter bu toplamın altındaysa baskı uyarısı.")
F_DURUM = ("Durum: stokta yok (bakiye ≤ 0, satışı var) · bitecek (gün ≤ «N günde bitecek» ya da baskı süresi + güvenlik "
           "gününün altında) · hareketsiz (pencerede hiç hareket yok) · satışı yok · fazla (gün > fazla stok eşiği) · "
           "yeterli · pasif (stok ve satış yok). Sayı = o durumdaki kitap sayısı.")
F_CRM_RAF = "CRM raf = kitabın bütün raflarındaki seri/lot kalan miktarı (new_kalanmiktar) toplamı; raf sayısı = kayıt sayısı."
F_RAF = "Raf satırı = seri/lot kalan miktarı, ürün × raf × depo (CRM)."
F_FARK = ("Fark = CRM raf kalanı − Logo bakiyesi (|fark| < 0,5 yok sayılır). Kök neden: CRM'de raf yoksa «CRM'de raf "
          "kaydı yok», Logo'da kayıt yoksa «Logo'da hareket yok»; Logo'ya aktarılmamış hareketin net miktarı farka "
          "eşitse «açıklıyor», farkı küçültüyorsa «kısmen», değilse sayım adayı. Sayaç = o sınıftaki kitap sayısı.")
F_AKTARIM_URUN = "Logo'ya geçmemiş (kitap) = CRM'de Logo'ya aktarılmamış etkin malzeme hareketlerinin net miktarı ve fiş sayısı."
F_AKTARIM = ("Aktarım listesi = CRM'de Logo'ya aktarılmamış etkin malzeme hareketi fişleri; mesajı dolu olan «hata», boş "
             "olan «bekliyor». Yaş = bugün − fiş tarihi (yoksa oluşturma). Satır ve miktar fişin kendi toplamı.")
F_AKTARIM_SINIF = ("Hata nedeni sınıfını Zeki AI atar (kapalı küme, olasılık ve fark eşiğini geçmezse «Sınıflanmadı»); "
                   "sayı = o sınıftaki hata fişi sayısı; olasılık modelin seçime verdiği olasılıktır.")
F_BEKLEYEN_CRM = "Bekleyen sipariş (CRM) = Baskı Öneri raporunun CRM açık sipariş sorgusu (B2C ve iki iç cari hariç)."
F_BEKLEYEN_LOGO = "Bekleyen sipariş (Logo) = açık satış siparişi satırlarında (TRCODE 1, kapanmamış) sipariş − sevk edilen miktar."
F_BEKLEYEN_URUN = "Bekleyen ürün talebi = CRM'de stok yokken açılan açık talep satırlarının adedi ve kayıt sayısı."
F_DEVIR = "Stok devir hızı = katalogdaki sertifikalı ölçü, birebir (Logo)."
F_HAREKET = ("Son 12 ay net satış = pencere içindeki faturalı satış satırları (TRCODE 7, 8, 9) − iadeler (2, 3); pencere "
             "Logo'nun her yıl kopyasında ayrı okunur ve toplanır. Son hareket = penceredeki son stok satırının tarihi.")
F_EOS = "Mevcut rapordaki depo stoku = Baskı Öneri raporunun depo stoku kaynağı (karşılaştırma için)."
F_URETIM = ("Açık üretim kartı = üretim modülünün kartları (CRM proje/baskı kartı), aşaması hazırlık, matbaa seçildi, "
            "matbaada ya da yolda olanlar; adet ve baskı no karttan.")
F_TAHMIN = ("Satış tahmini = Baskı Öneri ile ortak gece tahmininin aylık orta değeri (p50, aralık varsa p10/p90); 30/60/90 "
            "gün = tahminin ilk 1/2/3 ayının toplamı. Tahminin girdisi kitabın aylık satış geçmişidir.")
F_ESIK = ("Onaylı eşik = güvenlik günü ve yeniden sipariş noktası (portal kaydı, onaylayan ve tarihiyle); yeniden sipariş "
          "noktasının altında «RSP altında».")
F_ESIK_ONERI = ("Eşik önerisi = yeniden sipariş noktası ⌈aylık satış hızı ÷ 30 × (baskı süresi + güvenlik günü)⌉ adet; "
                "güvenlik günü ayardan. Satışı olmayan kitapta öneri yok. Rakam hesaptır, model üretmez.")
F_MALIYET = ("Stok değeri = Logo bakiyesi × birim maliyet (bakiyesi sıfırdan büyük kitaplarda). Birim maliyet önceliği: "
             "onaylı fiyat analizindeki birim maliyet → Logo'da gerçekleşen (maliyeti girilmiş satış satırlarının en son "
             "yılı, maliyet ÷ maliyetli adet) → yoksa bilinmiyor ve toplama girmez. Maliyetli/maliyetsiz = kitap sayısı.")
F_ONERI = ("Öneri satırındaki rakamlar gece işinin öneriyi yazdığı andaki stok okumasından (bakiye, satış hızı, gün, "
           "baskı süresi, bekleyen sipariş) dondurulmuştur; bitecek önerisi kurala göre, fazla stok yönünü Zeki AI seçer.")
F_GECMIS = "Geçmiş = her gece işinde yazılan fotoğraf: o günün Logo bakiyesi, CRM rafı ve aylık satış hızı."
F_DEPO_HATTI = ("Depo hattı (CRM sipariş aşama tarihleri): aşama sayısı = o aşamadaki sipariş; aşamada geçen süre = şimdi − "
                "aşamanın başladığı an (saat); ortanca ve en eski bu sürelerin ortancası ve en büyüğü. Aşama süreleri = "
                "penceredeki sevk edilmiş siparişlerde iki aşama tarihi arasındaki saat (ortanca) ve sipariş sayısı.")
F_KISI = ("Toplayan başına = pencerede sevk edilmiş, pusula ve kutulandı tarihi olan siparişlerde pusula → kutulandı süresi "
          "(ortanca saat) ve sipariş sayısı; yalnız depo hattı kişi yetkisiyle.")
F_KOLI = "Koli = CRM siparişindeki koli sayısı."


def _sid(run_id: str) -> str:
    return "stok." + run_id.replace(":", ".").replace("baski-oneri.", "baskiOneri.")


_TITLES = {sid: (title, desc) for sid, _conn, title, desc in src.SOURCES}
_TITLES["logo_veri_sonu"] = ("Logo veri sonu", "Son faturalı satış satırının tarihi; tükenme tarihi bu günden sayılır.")


class Stock:
    """Bir okumanın kaynak kayıtları: çalışan kaynaklar `stok.*` kimliğiyle."""

    def __init__(self, engine: Any, tenant: str, m: dict[str, Any], logo_db: Optional[str], crm_db: Optional[str],
                 m12: Any = None, costs: Any = None):
        self.engine, self.tenant, self.m, self.m12, self.costs = engine, tenant, m, m12, costs
        self.k = P.Kaynaklar(data_end=m.get("dataEnd"), as_of=m.get("readAt"))
        self.ids: dict[str, str] = {}
        runs: dict[str, dict[str, Any]] = m.get("runs") or {}
        for rid in sorted(runs):
            r = runs[rid]
            base, _, year = rid.partition(":") if not rid.startswith("baski-oneri:") else (rid, "", "")
            conn = "crm" if base.startswith("crm_") or base == "baski-oneri:crm_bekleyen_siparis" else "logo"
            title, desc = _TITLES.get(base, (base, ""))
            if year:
                title = f"{title} · {year}"
            self.ids[rid] = self.k.sorgu(
                _sid(rid), title, conn, r["sql"], database=logo_db if conn == "logo" else crm_db, rows=r.get("rows"),
                ms=r.get("ms"), ran_at=r.get("at"), period=f"Logo {year} kopyası" if year else None,
                description=(desc + " Sorgu gece turunda ya da arka plan tazelemesinde çalışır, sonucu son stok okuması "
                             "tablosunda tutulur; ekrandaki rakam bu okumadandır (çalıştığı an satırda).").strip())
        if self.ids:
            # Ucun çalıştırdığı portal okuması: son okuma tablosu; kökeni yukarıdaki Logo/CRM sorguları.
            self.k.portal("stok.portal.okuma", "Son stok okuması", store.read_stmt(tenant), engine,
                          origin=list(self.ids.values()),
                          description="Gece turunun ya da arka plan tazelemesinin yazdığı son Logo + CRM okuması (kiracı "
                                      "başına tek satır). Uç kaynağı beklemez, bu satırı okur.")

    def s(self, *run_ids: str) -> list[str]:
        """Okunmuş kaynakların kimlikleri (okunmayanlar atlanır). `logo_hareket` bütün yıl kopyalarını verir."""
        out: list[str] = []
        for rid in run_ids:
            if rid == "logo_hareket":
                out += [v for key, v in self.ids.items() if key.startswith("logo_hareket:")]
            elif rid in self.ids:
                out.append(self.ids[rid])
        return out

    # -- portal ve dış kaynaklar

    def thresholds(self) -> str:
        return self.k.portal("stok.portal.esikler", "Onaylı güvenlik stoku eşikleri", store.thresholds_stmt(self.tenant, "onayli"),
                             self.engine, description="Kitap başına yürürlükteki (onaylı, depo belirtilmemiş) eşik: "
                                                      "güvenlik günü ve yeniden sipariş noktası.")

    def dagitim(self) -> Optional[str]:
        """Dağıtımcı ve perakende katalogları: kaynak sorguları (Logo sunucusundaki ayrı veritabanı) ve köprü tablosu."""
        if not self.m.get("dagitim"):
            return None
        from semantic_bridge import pazar_dagitim as D

        b = self.k.sorgu("stok.dagitim.basari", "Başarı Dağıtım kataloğu", "logo", D.SQL_BASARI,
                         description="Başarı'nın güncel kataloğu (kaynak kendi üstüne yazar); gece görüntüsüyle saklanır.")
        r = self.k.sorgu("stok.dagitim.dr", "D&R kataloğu", "logo", D.SQL_DR,
                         description="D&R Prefix kataloğu: Prefix B2B stoğu ve D&R/İdefix site stoğu ayrı okunur.")
        T, K = D.TITLES.c, D.BARKOD.c
        j = D.TITLES.join(D.BARKOD, D.sa.and_(K.tenant_id == T.tenant_id, K.barkod == T.barkod))
        stmt = D.sa.select(T.kaynak, T.barkod, K.stok_kodu, T.stok, T.site_stok, T.fiyat, T.iskonto, T.dr_fiyat, T.durum,
                           T.son_gorulme, T.timas).select_from(j).where(T.tenant_id == self.tenant)
        p = self.k.portal("stok.portal.dagitim", "Dağıtımcı başlıkları (son görüntü)", stmt, self.engine,
                          description="Barkodu TİMAŞ'ın Logo barkoduyla eşleşen Başarı ve D&R başlıkları.", origin=[b, r])
        return h(self.k, "dagitim", F_DAGITIM, [p])

    def settings(self, *keys: str) -> str:
        sid = "stok.ayar" + ("." + ".".join(x.lower() for x in keys) if keys else "")
        return ayar(self.k, self.engine, sid, keys or ("STOCK_RUNOUT_DAYS", "STOCK_SAFETY_DAYS", "STOCK_LEAD_DAYS",
                                                               "STOCK_EXCESS_DAYS", "STOCK_DEAD_DAYS", "STOCK_PICK_DAYS",
                                                               "STOCK_EXCLUDE_PLANNED", "STOCK_EXCLUDE_PREFIXES"), "stok")

    def m12_cards(self) -> Optional[str]:
        """Üretim kartlarını dolduran CRM sorgusu (üretim modülünün son okuması)."""
        svc = self.m12
        if svc is None:
            return None
        try:
            from datetime import date

            from semantic_bridge import production

            snap = svc.source.peek()
            if not snap:
                return None
            text = production.crm_cards_sql(svc.source._schema(), date.fromisoformat(str(snap["since"])[:10]))
            crm_db = None
            for sid, s in self.k.sources.items():
                if s["connection"] == "crm":
                    crm_db = s["database"]
                    break
            return self.k.sorgu("stok.uretim.kartlar", "Üretim kartları (CRM)", "crm", text, database=crm_db,
                                rows=len(snap.get("cards") or []), ms=snap.get("crmMs"), ran_at=snap.get("at"),
                                description="Üretim modülünün baskı kartları; açık kart ve baskı süresi ölçümü buradan.")
        except Exception:  # noqa: BLE001 — üretim okuması yoksa kayıt açılmaz
            return None

    def cost(self, codes: Iterable[str], logo_db: Optional[str]) -> list[str]:
        """Birim maliyet sağlayıcısının okumaları: onaylı analizler (portal) + fiyatlama görüntüsünün Logo satış sorgusu."""
        prov = self.costs
        codes = sorted({c for c in codes if c})
        if prov is None or not codes:
            return []
        out: list[str] = []
        try:
            from semantic_bridge.pricing import cost_provider as CP

            engine, tenant = prov._engine(), prov._tenant()
            out.append(self.k.portal("stok.maliyet.onayli", "Onaylı fiyat analizleri (birim maliyet)",
                                     CP.approved_costs_stmt(tenant, codes), engine,
                                     description="Kitabın onaylı fiyat analizindeki birim maliyet; aşama ve son onay anı "
                                                 "önceliği belirler."))
            with engine.connect() as c:
                ids = [r[0] for r in c.execute(CP.approved_costs_stmt(tenant, codes)).all()]
            if ids:
                out.append(self.k.portal("stok.maliyet.imza", "Onay imzaları", CP.approval_times_stmt(ids), engine,
                                         description="Onaylı analiz sürümlerinin son onay imzası (tarih ve öncelik)."))
        except Exception:  # noqa: BLE001
            pass
        try:
            from semantic_bridge.pricing import kaynak as PK

            snap = prov._snap()
            out += PK.snap_sources(self.k, snap, ["logo_satis"], logo_db)
        except Exception:  # noqa: BLE001
            pass
        return out

    # -- alan kümeleri

    def item_fields(self, prefix: str, *, cost_codes: Optional[Iterable[str]] = None, logo_db: Optional[str] = None,
                    extra: bool = True) -> dict[str, Optional[str]]:
        """Kitap satırının bütün rakamları (`prefix` = «items[]», «bugun.bitecek.items[]», kart için «»)."""
        k, s = self.k, self.s
        p = (prefix + ".") if prefix else ""
        bak = h(k, "bakiye", F_BAKIYE, s("logo_bakiye", "logo_ambarlar"))
        hiz = h(k, "hiz", F_HIZ, s("baski-oneri:logo_satis_hizi"))
        gun = h(k, "gun", F_GUN, [bak, hiz] + s("logo_veri_sonu"))
        kritik = h(k, "kritik", F_KRITIK, [self.thresholds(), self.settings(), self.m12_cards()])
        crm = h(k, "crmRaf", F_CRM_RAF, s("crm_raf_stok"))
        urun = h(k, "aktarimUrun", F_AKTARIM_URUN, s("crm_aktarim_urun"))
        out: dict[str, Optional[str]] = {
            f"{p}bakiye": bak, f"{p}ambarlar": bak,
            f"{p}satisHizi": hiz, f"{p}yillikSatis": hiz,
            f"{p}gun": gun, f"{p}tukenmeAy": gun,
            f"{p}kritikGun": kritik,
            f"{p}crmRaf": crm, f"{p}rafSayisi": crm,
            f"{p}fark": h(k, "fark", F_FARK, [bak, crm, urun]),
            f"{p}aktarimBekleyen": urun, f"{p}aktarimFis": urun,
            f"{p}bekleyenCrm": h(k, "bekleyenCrm", F_BEKLEYEN_CRM, s("baski-oneri:crm_bekleyen_siparis")),
            f"{p}bekleyenLogo": h(k, "bekleyenLogo", F_BEKLEYEN_LOGO, s("logo_orfline_bekleyen")),
            f"{p}bekleyenUrun": h(k, "bekleyenUrun", F_BEKLEYEN_URUN, s("crm_bekleyen_urun")),
            f"{p}devirHizi": h(k, "devir", F_DEVIR, s("logo_devir")),
            f"{p}netSatis12": h(k, "hareket", F_HAREKET, s("logo_hareket")),
            f"{p}eosStok": h(k, "eos", F_EOS, s("baski-oneri:logo_depo_stok")),
            f"{p}uretim": h(k, "uretim", F_URETIM, [self.m12_cards()]),
            f"{p}uretimSayisi": "hesap:uretim" if "uretim" in k.formulas else None,
            f"{p}tahmin": h(k, "tahmin", F_TAHMIN, [hiz]),
            f"{p}tahminAralik": "hesap:tahmin" if "tahmin" in k.formulas else None,
            f"{p}esik": h(k, "esik", F_ESIK, [self.thresholds()]),
            f"{p}yenidenSiparisNoktasi": "hesap:esik",
            f"{p}dagitim": self.dagitim(),
        }
        if cost_codes is not None:
            m = h(k, "maliyet", F_MALIYET, [bak] + self.cost(cost_codes, logo_db))
            out[f"{p}birimMaliyet"] = m
            out[f"{p}stokDegeri"] = m
        return {path: ref for path, ref in out.items() if ref}

    def transfer_fields(self, prefix: str) -> dict[str, Optional[str]]:
        k = self.k
        t = h(k, "aktarim", F_AKTARIM, self.s("crm_aktarim_hatasi"))
        return {f"{prefix}.yasGun": t, f"{prefix}.satir": t, f"{prefix}.miktar": t,
                f"{prefix}.sinifOlasilik": h(k, "aktarimSinif", F_AKTARIM_SINIF, [t])}


def _new(engine: Any, tenant: str, m: dict[str, Any], deps: dict[str, Any]) -> Stock:
    return Stock(engine, tenant, m, deps.get("logo_db"), deps.get("crm_db"), deps.get("m12"), deps.get("costs"))


def _page(k: P.Kaynaklar, prefix: str, ref: Optional[str]) -> dict[str, Optional[str]]:
    """Sayfa toplamı («N kayıt»): listenin kendi hesabından."""
    return {f"{prefix}total": ref}


# ------------------------------------------------------------------ uçlar


def for_overview(engine: Any, tenant: str, m: dict[str, Any], out: dict[str, Any], deps: dict[str, Any]) -> P.Kaynaklar:
    st = _new(engine, tenant, m, deps)
    k = st.k
    f = st.item_fields("bugun.bitecek.items[]")
    f.update({key.replace("bugun.bitecek.items[]", "bugun.fark.items[]"): v for key, v in f.items()})
    bak = f.get("bugun.bitecek.items[].bakiye")
    durum = h(k, "durum", F_DURUM, [bak, f.get("bugun.bitecek.items[].satisHizi"), f.get("bugun.bitecek.items[].kritikGun"),
                                    f.get("bugun.bitecek.items[].netSatis12"), st.settings()])
    tr = st.transfer_fields("bugun.aktarim.items[]")
    t = tr.get("bugun.aktarim.items[].satir")
    f.update(tr)
    f.update({
        "toplamStok": h(k, "toplam", F_TOPLAM, [bak]), "stokluKitap": "hesap:toplam" if bak else None,
        "stoksuzAktif": durum, "durumlar": durum, "fazla": durum, "hareketsiz": durum, "satissiz": durum,
        "bitecek": durum, "bugun.bitecek.total": durum, "kartsizKritik": h(k, "kartsiz", F_URETIM + " Sayı = bitecek "
                                                                             "listesinde baskı uyarısı olup açık kartı olmayan kitap.",
                                                                    [durum, st.m12_cards()]),
        "bitecekGun": st.settings("STOCK_RUNOUT_DAYS"), "baskiSuresi": f.get("bugun.bitecek.items[].kritikGun"),
        "aktarimHatasi": t, "aktarimBekleyen": t, "bugun.aktarim.total": t,
        "farkliKitap": f.get("bugun.fark.items[].fark"), "bugun.fark.total": f.get("bugun.fark.items[].fark"),
    })
    if out.get("deger") is not None:
        codes = [i["stokKodu"] for i in m["items"] if i["bakiye"] > 0]
        f["deger"] = h(k, "maliyet", F_MALIYET, [bak] + st.cost(codes, deps.get("logo_db")))
    bind(k, f)
    return k


def for_items(engine: Any, tenant: str, m: dict[str, Any], out: dict[str, Any], deps: dict[str, Any]) -> P.Kaynaklar:
    st = _new(engine, tenant, m, deps)
    codes = [i["stokKodu"] for i in out.get("items") or []] if any("stokDegeri" in i for i in out.get("items") or []) else None
    f = st.item_fields("items[]", cost_codes=codes, logo_db=deps.get("logo_db"))
    f["total"] = h(st.k, "liste", "Liste = süzgece (durum, yayınevi, ambar, arama) uyan kitaplar; toplam kitap sayısı, "
                                  "sayfa başına 50 satır. Durum kuralı: " + F_DURUM, [f.get("items[].bakiye"),
                                                                                       f.get("items[].satisHizi")])
    bind(st.k, f)
    return st.k


def for_running_out(engine: Any, tenant: str, m: dict[str, Any], out: dict[str, Any], deps: dict[str, Any]) -> P.Kaynaklar:
    st = _new(engine, tenant, m, deps)
    codes = [i["stokKodu"] for i in out.get("items") or []] if any("stokDegeri" in i for i in out.get("items") or []) else None
    f = st.item_fields("items[]", cost_codes=codes, logo_db=deps.get("logo_db"))
    f.update({
        "total": h(st.k, "bitecek", "Bitecekler = satışı olan ve kaç gün yeter ≤ seçilen gün ya da baskı süresi + güvenlik "
                                    "gününün altına inen kitaplar (en önce biten başta). " + F_GUN,
                   [f.get("items[].gun"), f.get("items[].kritikGun")]),
        "gun": st.settings("STOCK_RUNOUT_DAYS"), "baskiSuresi": f.get("items[].kritikGun"),
        "guvenlikGun": f.get("items[].kritikGun"),
    })
    bind(st.k, f)
    return st.k


def for_excess(engine: Any, tenant: str, m: dict[str, Any], out: dict[str, Any], deps: dict[str, Any]) -> P.Kaynaklar:
    st = _new(engine, tenant, m, deps)
    k = st.k
    rows_cost = out.get("deger") is not None
    codes = [i["stokKodu"] for i in m["items"] if i["bakiye"] > 0 and i["durum"] in ("fazla", "olu", "satissiz")] \
        if rows_cost else None
    f = st.item_fields("items[]", cost_codes=codes, logo_db=deps.get("logo_db"))
    ex = h(k, "fazla", "Fazla ve hareketsiz stok = bakiyesi olan ve durumu fazla (gün > fazla stok eşiği), hareketsiz "
                       "(pencerede hareket yok) ya da satışı yok olan kitaplar; toplam adet = bakiyeleri toplamı. "
                       "Eritme yönünü (kampanya / set / bekle) Zeki AI seçer; yön bir rakam değildir.",
           [f.get("items[].bakiye"), f.get("items[].netSatis12"), f.get("items[].gun"), st.settings()])
    sug = k.portal("stok.portal.oneriFazla", "Açık fazla stok önerileri", store.suggestions_stmt(tenant, tur="fazla"), engine,
                   description="Gece işinin yazdığı açık öneriler (hedef modül ve gerekçe).")
    f.update({"total": ex, "toplamAdet": ex, "fazlaGun": st.settings("STOCK_EXCESS_DAYS", "STOCK_DEAD_DAYS"),
              "items[].oneri": h(k, "oneri", F_ONERI, [sug])})
    if rows_cost:
        f["deger"] = f.get("items[].stokDegeri")
    bind(k, f)
    return k


def for_diff(engine: Any, tenant: str, m: dict[str, Any], out: dict[str, Any], deps: dict[str, Any]) -> P.Kaynaklar:
    st = _new(engine, tenant, m, deps)
    f = st.item_fields("items[]")
    f.update({"total": f.get("items[].fark"), "siniflar": f.get("items[].fark")})
    bind(st.k, f)
    return st.k


def for_transfer_errors(engine: Any, tenant: str, m: dict[str, Any], out: dict[str, Any], deps: dict[str, Any]) -> P.Kaynaklar:
    st = _new(engine, tenant, m, deps)
    f = st.transfer_fields("items[]")
    t = f.get("items[].satir")
    cls = st.k.portal("stok.portal.mesajSinifi", "Hata mesajı sınıfları", store.meta_stmt(tenant, "mesaj-sinifi"), engine,
                      description="Gece işinde Zeki AI'ın her hata mesajına verdiği sınıf ve olasılık.")
    f.update({"total": t, "hata": t, "bekliyor": t,
              "siniflar": h(st.k, "aktarimSinifSay", F_AKTARIM_SINIF, [t, cls])})
    f["items[].sinifOlasilik"] = "hesap:aktarimSinifSay" if f.get("siniflar") else None
    bind(st.k, f)
    return st.k


def for_pick_line(engine: Any, tenant: str, m: dict[str, Any], out: dict[str, Any], deps: dict[str, Any]) -> P.Kaynaklar:
    st = _new(engine, tenant, m, deps)
    k = st.k
    hat = h(k, "hat", F_DEPO_HATTI, st.s("crm_depo_hatti"))
    f: dict[str, Optional[str]] = {"asamalar": hat, "sureler": hat, "acik.items[].asamaSaat": hat, "acik.total": hat,
                                   "acik.items[].koli": h(k, "koli", F_KOLI, st.s("crm_depo_hatti")),
                                   "pencereGun": st.settings("STOCK_PICK_DAYS")}
    if "kisiler" in out:
        f["kisiler"] = h(k, "kisi", F_KISI, st.s("crm_depo_hatti"))
    bind(k, f)
    return k


def for_item(engine: Any, tenant: str, m: dict[str, Any], out: dict[str, Any], deps: dict[str, Any]) -> P.Kaynaklar:
    st = _new(engine, tenant, m, deps)
    k = st.k
    code = out.get("stokKodu")
    f = st.item_fields("", cost_codes=[code] if "stokDegeri" in out else None, logo_db=deps.get("logo_db"))
    f.update({
        "raflar": h(k, "raf", F_RAF, st.s("crm_raf_stok", "crm_depo")),
        "uretimKartlari": f.get("uretim"),
        "esikler": k.portal("stok.portal.esikKitap", "Kitabın eşik kayıtları", store.thresholds_stmt(tenant, "", [code]), engine,
                            description="Taslak, onaylı, reddedilmiş ve arşivlenmiş eşikler."),
        "esikOnerisi": h(k, "esikOneri", F_ESIK_ONERI, [f.get("satisHizi"), f.get("kritikGun"),
                                                      st.settings("STOCK_SAFETY_DAYS", "STOCK_LEAD_DAYS")]),
        "oneriler": h(k, "oneri", F_ONERI, [k.portal("stok.portal.oneriKitap", "Kitabın önerileri",
                                                     store.suggestions_stmt(tenant, durum="", stok=code), engine,
                                                     description="Bitecek ve fazla stok önerileri, kararlarıyla.")]),
        "gecmis": h(k, "gecmis", F_GECMIS, [k.portal("stok.portal.gecmis", "Gece fotoğrafları", store.snapshots_stmt(tenant, code),
                                                     engine, description="Kitabın günlük Logo bakiyesi, CRM rafı ve satış hızı.",
                                                     origin=st.s("logo_bakiye", "crm_raf_stok",
                                                                 "baski-oneri:logo_satis_hizi"))]),
        "baskiSuresi": f.get("kritikGun"),
    })
    bind(k, f)
    return k


def for_thresholds(engine: Any, tenant: str, m: Optional[dict[str, Any]], out: dict[str, Any], durum: str,
                   deps: dict[str, Any]) -> P.Kaynaklar:
    if durum == "oneri" and m is not None:
        st = _new(engine, tenant, m, deps)
        k = st.k
        f = st.item_fields("items[]")
        prop = h(k, "esikOneri", F_ESIK_ONERI, [f.get("items[].satisHizi"), f.get("items[].kritikGun"),
                                                st.settings("STOCK_SAFETY_DAYS", "STOCK_LEAD_DAYS")])
        bind(k, {"items[].yenidenSiparisAdet": prop, "items[].guvenlikGun": prop, "items[].baskiSuresi": prop,
                 "items[].bakiye": f.get("items[].bakiye"), "items[].satisHizi": f.get("items[].satisHizi"),
                 "items[].gun": f.get("items[].gun"), "baskiSuresi": f.get("items[].kritikGun"), "total": prop})
        return k
    k = P.Kaynaklar(data_end=(m or {}).get("dataEnd"))
    r = k.portal("stok.portal.esikKayit", "Eşik kayıtları", store.thresholds_stmt(tenant, durum), engine,
                 description="Güvenlik stoku eşikleri (seçili durum): güvenlik günü, yeniden sipariş noktası, depo.")
    bind(k, {"items[]": k.hesap("esikKayit", F_ESIK, [r]), "total": "hesap:esikKayit"})
    return k


def for_suggestions(engine: Any, tenant: str, out: dict[str, Any], *, tur: str, durum: str, hedef: str,
                    runs_m: Optional[dict[str, Any]], deps: dict[str, Any]) -> P.Kaynaklar:
    k = P.Kaynaklar(data_end=(runs_m or {}).get("dataEnd"))
    origin: list[str] = []
    if runs_m is not None:
        st = Stock(engine, tenant, runs_m, deps.get("logo_db"), deps.get("crm_db"))
        k = st.k
        origin = st.s("logo_bakiye", "baski-oneri:logo_satis_hizi", "logo_hareket")
    r = k.portal("stok.portal.oneriler", "Stok önerileri", store.suggestions_stmt(tenant, tur=tur, durum=durum, hedef=hedef),
                 engine, origin=origin, description="Gece işinin yazdığı bitecek ve fazla stok önerileri (sayfa başına 50).")
    bind(k, {"items[]": k.hesap("oneri", F_ONERI, [r]), "total": "hesap:oneri"})
    return k


#: Rakam olmayan sayılar: sayfa, kod alanları, okuma anı (zaman damgası), ambar/depo no, CRM durum kodları.
NOT_RAKAM = (
    "page", "pageSize", "okuma", "items[].ambarlar[].no", "ambarlar[].no", "bugun.bitecek.page",
    "bugun.bitecek.pageSize", "bugun.aktarim.page", "bugun.aktarim.pageSize", "bugun.fark.page", "bugun.fark.pageSize",
    "bugun.bitecek.items[].ambarlar[].no", "bugun.fark.items[].ambarlar[].no", "items[].islemTuru", "items[].islemTipi",
    "items[].durum", "bugun.aktarim.items[].islemTuru", "bugun.aktarim.items[].islemTipi", "bugun.aktarim.items[].durum",
    "acik.page", "acik.pageSize", "items[].depoNo", "esikler[].depoNo", "raflar[].depoNo", "hareketPenceresi",
    "tahminBaslangic",
)
