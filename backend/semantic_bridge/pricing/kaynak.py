"""M9 Fiyatlama: ekrandaki her rakamın sorgu bilgisi (ortak sözleşme `semantic_bridge/provenance.py`).

Fiyatlama ekranı Logo'ya her istekte gitmez; rakamlar arka planda kurulan anlık görüntüden (`snapshot.json`) okunur.
Görüntü kurulurken çalışan SQL'ler görüntüde saklanır (`snap["sql"][kaynak]`, Logo yıl kopyası başına bir metin); sorgu
bilgisi bu çalışmış metinleri verir — şablon değil, firma kodu ve tarih aralığı yerine konmuş hâli. Onay akışı
(analiz, teklif, varsayılan) portal tablolarından (semantic_pricing_*) okunur; gösterilen SQL uçta çalışan ifadedir.
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

from semantic_bridge import provenance as P
from semantic_bridge.pricing import sources as SRC
from semantic_bridge.pricing import store as S

F_BASKI = ("Baskı birim fiyatı c(Q) = a + b ÷ Q: «a» adet başına değişen kısım (baskı, cilt), «b» baskıya bir kez "
           "giren hazırlık. Emsal kitapların son 12 aydaki matbaa faturalarından (Komple Baskı Giderleri satırı, KDV "
           "hariç tutar ÷ basılan adet) sayfa başına ölçülür, kitabın sayfa sayısıyla çarpılır.")
F_KAGIT = ("Kâğıt (adet başına) = iç sayfa kg × son 6 ayın ortalama ₺/kg + kapak kartonu kg × ₺/kg; kg = sayfa × ebat "
           "× gramaj; fire ve kapak alanı katsayısı varsayımdır. ₺/kg = alış tutarı ÷ kg (15001 kartları).")
F_TELIF = ("Telif (adet başına) = oran × taban; taban «kapak» = P ÷ (1 + KDV), «net» = net birim gelir. Oran, taban, "
           "doğuş (satış/baskı) ve avans CRM'deki yürürlükteki sözleşmeden.")
F_ISKONTO = ("Kanal iskontosu = 1 − Σ net (VATMATRAH) ÷ Σ iskonto öncesi (TOTAL), son 12 ay kitap satış satırları, müşteri "
             "grubuna göre; ağırlıklı iskonto kanal payına (ya da seçilen kanal karmasına) göre.")
F_DAGITIM = "Dağıtım gideri oranı = son 12 ayın «Satış Nakliye Giderleri» hizmet tutarı ÷ kitap net satışı."
F_NET = ("Net satış = Σ VATMATRAH (TRCODE 7, 8, 9) − Σ VATMATRAH (TRCODE 2, 3), faturalı malzeme satırları; Logo birim "
         "maliyeti = Σ AMOUNT × OUTCOST ÷ maliyeti işlenmiş adet; kâr = net − maliyet; marj = kâr ÷ net.")
F_SENARYO = ("Senaryo: birim maliyet = c(Q) + sabit giderler ÷ Q; net birim gelir N = P ÷ (1 + KDV) × (1 − iskonto); "
             "başabaş satış adedi S* = (Q·c(Q) + F) ÷ (N·(1 − t) − R); kâr = satılan × (N − R − t·N) − Q·c(Q) − F; "
             "marj = kâr ÷ net gelir. Hedef marja göre fiyat P = (Q·c + F′)·(1 + KDV) ÷ (S·(1 − d)(1 − t − m) − r·k·A), "
             "5 ₺'ye yukarı yuvarlanır.")
F_EMSAL = ("Emsal kitaplar: son 12 ayda Logo'da baskı faturası olan, sayfa sayısı ±%20 içinde (ve cilt şekli aynı) "
           "kitaplar; fiyat çeyrekleri CRM kapak fiyatından, birim maliyet çeyrekleri Logo birim maliyetinden.")
F_GERCEK = ("Gerçekleşen: basılan adet ve baskı bedeli matbaa faturalarından; satılan adet, net satış ve Logo birim "
            "maliyeti satış satırlarından; kapak fiyatı CRM'den; maliyet ÷ fiyat = Logo birim maliyeti ÷ (kapak ÷ "
            "(1 + KDV)). " + F_NET)
F_KARSILASTIR = ("Eski kitap karşılaştırması: güncel fiyat = CRM kitap kartındaki KDV dahil kapak fiyatı. Bizim hesap = «Kitap "
                 "hesabı»nda kitap seçildiğinde çıkan önerilen kapak fiyatı, bütün kitaplar için aynı zincirle: CRM + Logo "
                 "öneri girdileri, basım Excel'indeki maliyet formu (baskı adedi son CRM üretim kaydından, kâğıt Logo "
                 "alışından, kur fiyat listesindeki seçime göre Logo faturalarından ya da elle), serbest çalışan tutarları ve "
                 "elle girilen pazar fiyatları; öneri = hedef marjı tutan maliyet alt sınırı ile emsal ortancasının büyüğü "
                 "(KDV dahil, 5 ₺'ye yukarı). Fark = bizim hesap − güncel fiyat; % = bizim hesap ÷ güncel fiyat − 1. «Yeni» = "
                 "ilk yayını (yoksa ilk matbaa faturası) son 12 ayda. Satış (2 yıl) = bu yıl ve geçen yılın Logo faturalı "
                 "satış adedi.")
F_ONAY = "Analiz ve teklifler portalda saklanır; rakamlar hesaplandığı andaki sonuçtur (sürümüyle)."


def _dbs(logo_db: Optional[str], crm_db: Optional[str], connection: str) -> Optional[str]:
    return logo_db if connection == "logo" else crm_db


def snap_sources(k: P.Kaynaklar, snap: Optional[dict[str, Any]], ids: Iterable[str], logo_db: Optional[str] = None,
                 crm_db: Optional[str] = None) -> list[str]:
    """Görüntüyü dolduran sorgular: kaynak başına, her Logo kopyası için çalışan metin ayrı kayıt."""
    if not snap:
        return []
    executed = snap.get("sql") or {}
    stats = snap.get("sources") or {}
    out: list[str] = []
    for sid in ids:
        s = SRC.BY_ID.get(sid)
        runs = executed.get(sid) or []
        if sid == "logo_kopya":
            title, conn, desc = "Logo yıl kopyaları", "logo", "Fatura tablosu olan Logo firma kopyaları ve tarih aralıkları."
        elif s:
            title, conn, desc = s.title, s.connection, s.description
        else:
            continue
        st = stats.get(sid) or {}
        for i, text in enumerate(runs):
            rid = f"fiyatlama.{sid}.{i}" if len(runs) > 1 else f"fiyatlama.{sid}"
            if rid in k.sources:
                out.append(rid)
                continue
            out.append(k.sorgu(rid, title + (f" ({i + 1}/{len(runs)})" if len(runs) > 1 else ""), conn, text,
                               database=_dbs(logo_db, crm_db, conn), rows=st.get("rows") if len(runs) == 1 else None,
                               ms=st.get("ms") if len(runs) == 1 else None, ran_at=snap.get("asOf"),
                               data_end=snap.get("dataEnd"), description=desc + (
                                   f" Toplam {st.get('rows')} satır, {len(runs)} çalıştırma." if len(runs) > 1 and st else "")))
    return out


def _new(snap: Optional[dict[str, Any]]) -> P.Kaynaklar:
    return P.Kaynaklar(data_end=(snap or {}).get("dataEnd"), as_of=(snap or {}).get("asOf"))


def for_sources(snap: Optional[dict[str, Any]], logo_db: Optional[str], crm_db: Optional[str]) -> P.Kaynaklar:
    """`/sources` (Veri sekmesi): bütün kaynaklar, çalışmış metinleriyle."""
    k = _new(snap)
    fields: dict[str, str] = {}
    every: list[str] = []
    for sid in ["logo_kopya"] + [s.id for s in SRC.SOURCES]:
        ids = snap_sources(k, snap, [sid], logo_db, crm_db)
        if not ids:
            continue
        every += ids
        # satıra özel: her kaynağın bütün yıl kopyası çalıştırmaları (ekran `row={s.id}`)
        fields[f"sources[]:{sid}"] = k.hesap(f"kaynak:{sid}", "Görüntü kurulurken bu kaynak için çalışan sorgular "
                                                              "(Logo yıl kopyası başına bir metin).", ids)
    if every:
        fields["sources[]"] = k.hesap("veri", "Fiyatlama verisini kuran sorguların tamamı (satır ve süre: son kurulum).",
                                      every)
        fields["copies"] = "hesap:veri"
    k.alanlar(fields)
    return k


def for_overview(engine: Any, tenant: str, snap: Optional[dict[str, Any]], out: dict[str, Any], logo_db: Optional[str],
                 crm_db: Optional[str]) -> P.Kaynaklar:
    k = _new(snap)
    fields: dict[str, str] = {}
    d = k.portal("portal.fiyat.varsayilan", "Varsayılanlar", S.defaults_stmt(tenant), engine,
                 description="Hedef marj, dağıtım/genel gider oranı, satış oranı, adet senaryoları, kanal karması.")
    a = k.portal("portal.fiyat.analizler", "Fiyat analizleri", S.analyses_stmt(tenant), engine,
                 description="Arşiv dışı analizler; durum sayıları aynı tablodan.")
    fields["defaults"] = k.hesap("varsayilan", "Portalda saklanan varsayılanlar (ekrandan değiştirilir).", [d])
    fields["counts"] = k.hesap("sayilar", "Durum başına analiz sayısı; onayınızı bekleyen = sizin rolünüzün onayı "
                                          "eksik ve sizin göndermediğiniz analizler.", [a])
    fields["toApprove"] = "hesap:sayilar"
    if snap:
        kop = snap_sources(k, snap, ["logo_kopya"], logo_db, crm_db)
        kanal = snap_sources(k, snap, ["logo_kanal"], logo_db, crm_db)
        kagit = snap_sources(k, snap, ["logo_kagit"], logo_db, crm_db)
        nakliye = snap_sources(k, snap, ["logo_nakliye"], logo_db, crm_db)
        kitap = snap_sources(k, snap, ["crm_kitap"], logo_db, crm_db)
        baski = snap_sources(k, snap, ["logo_baski"], logo_db, crm_db)
        fields.update({
            "measured.copies": k.hesap("kopya", "Okunan Logo yıl kopyaları (firma) ve fatura tarih aralıkları.", kop),
            "measured.channels": k.hesap("kanal", F_ISKONTO, kanal),
            "measured.discount": "hesap:kanal",
            "measured.paper": k.hesap("kagit", F_KAGIT, kagit),
            "measured.distribution": k.hesap("dagitim", F_DAGITIM, nakliye + kanal),
            "measured.books": k.hesap("kitapSayisi", "CRM'de stok kodu 152 ile başlayan etkin kitap kartı sayısı.", kitap),
            "measured.printedBooks": k.hesap("baskiSayisi", "Matbaa baskı faturası olan kitap sayısı ve fatura sayısı.",
                                             baski),
            "measured.printInvoices": "hesap:baskiSayisi",
        })
    k.alanlar(fields)
    return k


def for_book(engine: Any, tenant: str, snap: dict[str, Any], out: dict[str, Any], logo_db: Optional[str],
             crm_db: Optional[str]) -> P.Kaynaklar:
    k = _new(snap)
    kitap = snap_sources(k, snap, ["crm_kitap", "crm_secenek"], logo_db, crm_db)
    baski = snap_sources(k, snap, ["logo_baski"], logo_db, crm_db)
    crm_baski = snap_sources(k, snap, ["crm_baski", "crm_secenek"], logo_db, crm_db)
    satis = snap_sources(k, snap, ["logo_satis"], logo_db, crm_db)
    fields = {
        "book": k.hesap("kitap", "Kitap künyesi (sayfa, fiyat, KDV) ve yürürlükteki sözleşmenin telif koşulu CRM'den. "
                                 + F_TELIF, kitap),
        "prints[]": k.hesap("baskilar", "Matbaa faturaları: fatura + kitap başına basılan adet, KDV hariç tutar; birim = "
                                        "tutar ÷ adet.", baski),
        "crmPrints[]": k.hesap("crmBaski", "CRM üretim kayıtları: kesinleşen adet ve fiyat, sayfa, gramaj, renk.", crm_baski),
        "salesByYear[]": k.hesap("yillik", F_NET, satis),
        "total": "hesap:yillik",
        "spec": k.hesap("teknik", "Teknik özellik: sayfa CRM kitap kartından (yoksa son üretim kaydından), gramaj ve cilt "
                                  "son üretim kaydından, KDV kitap kartından.", kitap + crm_baski),
    }
    sug = suggested_fields(k, snap, logo_db, crm_db, engine, tenant)
    for key, ref in sug.items():
        fields[f"suggested.{key}" if key else "suggested"] = ref
    book_id = (out.get("book") or {}).get("id")
    fl_in = list(kitap)
    q_in = list(crm_baski)
    try:
        from semantic_bridge import pricing as PR
        from semantic_bridge import production_store as PST

        if book_id:
            fl_in.append(k.portal("portal.fiyat.serbest", "Serbest çalışan iş paketleri (bu kitap)",
                                  PR.freelance_stmt(tenant, book_id), engine,
                                  description="Serbest çalışanlar ekranında bu kitaba açılmış, iptal olmayan görevler."))
        cards = [p["id"] for p in out.get("crmPrints") or [] if p.get("id")]
        if cards:
            q_in.append(k.portal("portal.fiyat.teklifler", "Matbaa teklifleri (Üretim ekranı)",
                                 PST.quotes_stmt(tenant, cards), engine,
                                 description="Kitabın CRM üretim kayıtlarına girilen matbaa teklifleri (elle girilir); "
                                             "listenin tamamı gösterilir."))
    except Exception:  # noqa: BLE001 — M8/M12 tabloları yoksa kaynak da yok
        pass
    fields["freelance"] = k.hesap("serbest", "Kitaba bağlı serbest çalışan (çeviri, grafik, redaksiyon) iş paketleri: "
                                             "tutar = birim × birim fiyat, maliyet kalemine göre toplanır.", fl_in)
    fields["quotes[]"] = k.hesap("teklifler", "Üretim modülündeki matbaa teklifleri (kitabın CRM baskılarıyla eşleşen); "
                                              "birim = teklif birim fiyatı, yoksa toplam ÷ baskı adedi.", q_in)
    if book_id:
        an = k.portal("portal.fiyat.kitapAnaliz", "Bu kitabın analizleri", S.analyses_stmt(tenant, book=book_id), engine,
                      description="Arşiv dışı analizler.")
        mk = k.portal("portal.fiyat.pazar", "Pazar fiyatları (elle)", S.market_stmt(tenant, book=book_id), engine,
                      description="Rakip/kanal fiyatları, elle girilir.")
        fields["analyses[]"] = k.hesap("analizler", F_ONAY, [an])
        fields["market[]"] = k.hesap("pazar", "Elle girilen pazar fiyatları.", [mk])
    k.alanlar(fields)
    return k


def suggested_fields(k: P.Kaynaklar, snap: dict[str, Any], logo_db: Optional[str], crm_db: Optional[str],
                     engine: Any = None, tenant: str = "") -> dict[str, str]:
    """`suggested_inputs` çıktısının alanları (alan adı → kaynak). Boş anahtar bütün çıktıyı kapsar. Satış oranı ve
    hedef marj portalda saklanan varsayılanlardandır."""
    fields: dict[str, str] = {}
    if engine is not None:
        d = k.portal("portal.fiyat.varsayilan", "Varsayılanlar", S.defaults_stmt(tenant), engine,
                     description="Hedef marj, satış oranı, dağıtım oranı (ölçülemezse), kanal karması.")
        fields["sellThrough"] = k.hesap("varsayilan", "Portalda saklanan varsayılanlar (ekrandan değiştirilir).", [d])
        fields["targetMargin"] = "hesap:varsayilan"
    baski = snap_sources(k, snap, ["logo_baski", "crm_kitap", "crm_baski"], logo_db, crm_db)
    kagit = snap_sources(k, snap, ["logo_kagit"], logo_db, crm_db)
    kitap = snap_sources(k, snap, ["crm_kitap", "crm_secenek"], logo_db, crm_db)
    kanal = snap_sources(k, snap, ["logo_kanal"], logo_db, crm_db)
    nakliye = snap_sources(k, snap, ["logo_nakliye"], logo_db, crm_db)
    satis = snap_sources(k, snap, ["logo_satis"], logo_db, crm_db)
    baskiRef = k.hesap("oneri.baski", F_BASKI + " Adet başına baskı = a + kâğıt.", baski + kagit)
    return fields | {
        "": k.hesap("oneri", "Hesap girdileri için veriden öneri; her alanın kaynağı alanın yanında yazılı.",
                    baski + kagit + kitap + kanal + nakliye),
        "printPerCopy": baskiRef, "printService": baskiRef, "printSetup": baskiRef,
        "paper": k.hesap("oneri.kagit", F_KAGIT, kagit),
        "royaltyRate": k.hesap("oneri.telif", F_TELIF, kitap), "advance": "hesap:oneri.telif",
        "advanceForeign": "hesap:oneri.telif", "vat": k.hesap("oneri.kdv", "KDV oranı CRM kitap kartından.", kitap),
        "discount": k.hesap("oneri.iskonto", F_ISKONTO, kanal),
        "variableRate": k.hesap("oneri.dagitim", F_DAGITIM, nakliye + kanal),
        "comparables": k.hesap("emsal", F_EMSAL, baski + satis),
    }


def for_suggest(engine: Any, tenant: str, snap: dict[str, Any], logo_db: Optional[str], crm_db: Optional[str]) -> P.Kaynaklar:
    k = _new(snap)
    k.alanlar({key: ref for key, ref in suggested_fields(k, snap, logo_db, crm_db, engine, tenant).items() if key})
    return k


def for_comparables(snap: dict[str, Any], logo_db: Optional[str], crm_db: Optional[str]) -> P.Kaynaklar:
    k = _new(snap)
    ref = k.hesap("emsal", F_EMSAL + " Sayfa başına baskı eğrisi: emsallerin (adet, birim ÷ sayfa) noktalarına a + b ÷ Q "
                                     "uydurulur.", snap_sources(k, snap, ["logo_baski", "crm_kitap", "crm_baski", "logo_satis"],
                                                               logo_db, crm_db))
    k.alanlar({"rows[]": ref, "price": ref, "pricePerPage": ref, "printCurvePerPage": ref, "unitCost": ref, "count": ref,
               "pages": ref, "band": ref})
    return k


def for_calc(snap: Optional[dict[str, Any]], logo_db: Optional[str], crm_db: Optional[str]) -> P.Kaynaklar:
    k = _new(snap)
    ins = snap_sources(k, snap, ["logo_kanal", "logo_baski", "crm_kitap"], logo_db, crm_db)
    if not ins:
        # görüntü yoksa hesap yalnız ekrandaki girdilerle yapılır; kaynak = girdiler (sorgu yok)
        return k
    sen = k.hesap("senaryo", F_SENARYO + " Girdiler ekrandaki değerlerdir (öneriden gelir ya da elle).", ins)
    k.alanlar({"scenarios[]": sen, "floors[]": sen, "recommendation": k.hesap("tavsiye", F_SENARYO + " Tavsiye: "
               "emsal ve pazar fiyatlarının çeyrekleri içinde, hedef marjı tutan en düşük fiyat.", ins),
               "channels[]": k.hesap("kanalMatrisi", "Kanal matrisi: her kanalın ölçülmüş iskontosuyla net birim gelir, "
                                     "telif, değişken gider, birim maliyet, katkı ve marj. " + F_ISKONTO, ins),
               "summary": sen, "comparables": k.hesap("emsal", F_EMSAL, ins), "marketCount": sen, "inputs": sen})
    return k


def for_actuals(snap: dict[str, Any], logo_db: Optional[str], crm_db: Optional[str]) -> P.Kaynaklar:
    k = _new(snap)
    ref = k.hesap("gerceklesen", F_GERCEK, snap_sources(k, snap, ["logo_baski", "logo_satis", "crm_kitap"], logo_db, crm_db))
    k.alanlar({"rows[]": ref, "count": ref, "net": ref, "printCost": ref, "printed": ref, "sold": ref, "margin": ref,
               "gosterilen": k.hesap("gosterilen", "Gösterilen = bu sayfada listelenen kitap satırı sayısı; «Kitap» kutusu "
                                                   "süzgece uyan bütün kitapların sayısıdır (ekranda sayılır).", [ref])})
    return k


def for_compare(snap: dict[str, Any], logo_db: Optional[str], crm_db: Optional[str], engine: Any = None,
                tenant: Optional[str] = None) -> P.Kaynaklar:
    k = _new(snap)
    ref = k.hesap("karsilastir", F_KARSILASTIR + " " + F_FORM + " " + F_SENARYO + " " + F_EMSAL,
                  snap_sources(k, snap, ["crm_kitap", "crm_baski", "crm_secenek", "logo_baski", "logo_kagit", "logo_kur",
                                         "logo_satis", "logo_kanal", "logo_nakliye"], logo_db, crm_db))
    kunye = k.hesap("kunye", "Stok, son baskı tarihi/adedi ve kapak-cilt notu CRM kitap kartından; cilt, renk ve iç kâğıt "
                             "gramajı kitabın son CRM üretim kaydından; son fiyat değişimi Logo satış satırlarında ay başına en "
                             "çok geçen birim fiyatın değiştiği ilk gün; telif oranları ve tek ödeme kitaba bağlı yürürlükteki "
                             "sözleşmelerden (türde birden çok sözleşme varsa en yenisi, tek ödeme toplanır).",
                    snap_sources(k, snap, ["crm_kitap", "crm_baski", "crm_sozlesme", "logo_fiyat"], logo_db, crm_db))
    merdiven = k.hesap("merdiven", "Emsal merdiveni (Fiyat Çalışması Excel'indeki «Mak Fiyat» pivotu): aynı yayınevi × ebat × "
                                   "renk × cilt grubundaki kitapların sayfa sayısı başına en yüksek güncel kapak fiyatı. Kitabın "
                                   "merdiven fiyatı, sayfa sayısı kendisininkine eşit ya da altındaki en yakın basamak.", [ref, kunye])
    alanlar: dict[str, Any] = {
        "rows[]": ref, "count": ref, "total": ref, "counts": ref, "avgDiffPct": ref, "kur": ref, "targetMargin": ref,
        "newHidden": ref, "logoKur": ref, "kunye": kunye, "groups[]": merdiven, "ladder": merdiven,
        "seconds": k.hesap("hazirlik", "Karşılaştırmanın son hesaplanma süresi (saniye) ve başladığı an; yalnız hesap "
                                     "durumunu anlatır.", [ref]), "startedAt": "hesap:hazirlik",
        "secim": k.hesap("secim", "Seçilen = tabloda işaretlenen kitap sayısı; ortalama değişim = seçilen kitapların "
                                  "fark yüzdelerinin aritmetik ortalaması (ekranda hesaplanır).", [ref])}
    src = [ref]
    if engine is not None and tenant:
        import sqlalchemy as sa
        src.insert(0, k.portal("portal.fiyat.eski-yeni", "Eski kitap yeni fiyatları (elle)",
                               sa.select(S.BACKLIST_PRICES).where(S.BACKLIST_PRICES.c.tenant_id == tenant), engine,
                               description="Kullanıcının kitap başına yazdığı yeni kapak fiyatı; CRM'e yazılmaz."))
    yeni = k.hesap("yeni", "Yeni fiyat elle yazılır; artış = yeni ÷ güncel − 1, zamlı birim fiyat = yeni ÷ sayfa. Yeni fiyat "
                           "yazılan = süzgece uyan kitaplardan yeni fiyatı olanlar, ortalama artış onların aritmetik ortalaması.", src)
    alanlar.update({"entered": yeni, "avgNewPct": yeni, "yeni": yeni})
    k.alanlar(alanlar)
    return k


def for_analyses(engine: Any, tenant: str, *, status: str = "", q: str = "") -> P.Kaynaklar:
    k = P.Kaynaklar()
    a = k.portal("portal.fiyat.analizler", "Fiyat analizleri", S.analyses_stmt(tenant, status=status or None, q=q), engine,
                 description="Analiz başlığı, aşaması, durumu ve kaydedilen sonuç özeti.")
    ref = k.hesap("analizler", F_ONAY + " Özet: seçilen fiyat ve adetteki birim maliyet, başabaş, marj. " + F_SENARYO, [a])
    k.alanlar({"items[]": ref, "counts": ref})
    return k


def for_analysis(engine: Any, tenant: str, aid: str) -> P.Kaynaklar:
    k = P.Kaynaklar()
    a = k.portal("portal.fiyat.analiz", "Fiyat analizi", S.analysis_stmt(tenant, aid), engine,
                 description="Girdiler, teknik özellik ve kaydedilen hesap sonucu.")
    m = k.portal("portal.fiyat.pazar", "Pazar fiyatları (elle)", S.market_stmt(tenant, analysis_id=aid), engine,
                 description="Bu analize girilen rakip/kanal fiyatları.")
    ref = k.hesap("analiz", F_ONAY + " " + F_SENARYO, [a])
    k.alanlar({"inputs": ref, "result": ref, "specs": ref, "chosenPrice": ref, "chosenQty": ref,
               "market[]": k.hesap("pazar", "Elle girilen pazar fiyatları.", [m])})
    return k


def for_proposals(engine: Any, tenant: str, pid: Optional[str] = None) -> P.Kaynaklar:
    k = P.Kaynaklar()
    stmt = S.proposal_stmt(tenant, pid) if pid else S.proposals_stmt(tenant)
    p = k.portal("portal.fiyat.teklif", "Fiyat revizyonu teklifleri", stmt, engine,
                 description="Teklif anında eski kitap karşılaştırmasından seçilen kitaplar ve hesabın girdileri (sunucuda hesaplanmış).")
    ref = k.hesap("teklif", F_ONAY + " " + F_KARSILASTIR, [p])
    k.alanlar({"items[]": ref, "params": ref, "count": ref})
    return k


NOT_RAKAM = ("status", "version", "items[].version", "status", "total", "offset", "limit", "sinceYear", "stages", "approvers",
             "required", "me", "fixedLabels", "measured.warnings", "suggested.qtys")


F_FORM = ("Maliyet formu (TİMAŞ basım Excel'iyle aynı hesap): kâğıt tabakası = (adet + fire) × sayfa ÷ verim; kg = en × boy × "
          "gramaj ÷ 10.000 × tabaka ÷ 1.000; iç baskı = ⌈sayfa ÷ forma sayfası⌉ × renk kalıp × kalıp bedeli (3.000 adet "
          "üstü her 1.000 adete ek bedel); kapak baskı, selofan, lak, cilt ve işçilikler fiyat listesinden; telif = kapak fiyatı × "
          "basılan adet × oran; dolaylı gider = toplam × oran; birim maliyet = genel toplam ÷ adet; kâr = kapak fiyatı × "
          "(1 − yayınevi iskontosu) − birim maliyet; kâr % = toplam kâr ÷ genel toplam.")
F_TARIFE = ("Matbaa ve malzeme fiyat listesi: matbaa kalem fiyatları, Logo'da alışı olmayan kâğıdın ton fiyatı (€/$), vade farkı, kur, fire payları, dolaylı gider oranı ve "
            "yayınevi vadeli iskontoları. İlk hâli TİMAŞ basım Excel'lerinden (14.09.2026) alındı; Fiyatlama → Veri ve "
            "varsayımlar → Matbaa ve malzeme fiyat listesi'nden değiştirilir.")


def for_form(engine: Any, tenant: str, snap: Optional[dict[str, Any]], out: dict[str, Any], logo_db: Optional[str],
             crm_db: Optional[str]) -> P.Kaynaklar:
    k = _new(snap)
    t = k.portal("portal.fiyat.form_tarife", "Matbaa ve malzeme fiyat listesi", S.form_tariff_stmt(tenant), engine,
                 description="Portalda değiştirilmiş fiyat listesi; satır yoksa basım Excel'inden alınan ilk fiyatlar kullanılır.")
    tarife = k.hesap("formTarife", F_TARIFE, [t])
    ins = [t]
    kagit = snap_sources(k, snap, ["logo_kagit"], logo_db, crm_db) if snap else []
    kur = snap_sources(k, snap, ["logo_kur"], logo_db, crm_db) if snap else []
    logo_used = out.get("paperSource") == "logo"
    if logo_used:
        ins += kagit
    fields = {"summary": k.hesap("form", F_FORM + (" Kâğıt ₺/kg Logo'daki son 6 ayın alış faturalarından (aynı cins ve "
                                                    "gramaj, kg ağırlıklı); alışı olmayan kâğıtta fiyat listesi." if logo_used else " Kâğıt fiyatı fiyat listesinden."), ins),
              "tariff": tarife, "vade": tarife}
    fields["lines[]"] = "hesap:form"
    fields["prices[]"] = k.hesap("formKagit", "Kâğıt birim fiyatı. Fiyat listesi: ton fiyatı × (1 + vade farkı) × kur ÷ 1.000. "
                                             "Logo: son 6 ayın 15001 kâğıt kartı alışları, tutar ÷ kg.", [t] + kagit)
    fields["kur"] = k.hesap("formKur", "Kur: ekranda yazılan; boşsa Logo'da o dövizle kesilen son faturaların kuru, o da "
                                       "yoksa fiyat listesindeki kur.", [t] + kur)
    k.alanlar(fields)
    return k


# ------------------------------------------------------------------ dağıtımcı kataloğundan pazar fiyatı


def _dagitim_kaynak(k: P.Kaynaklar) -> tuple[str, str]:
    """Portal tablosunu dolduran Başarı ve D&R okumaları (M39, her gün; güncel hâl portalda tutulur)."""
    from semantic_bridge import pazar_dagitim as PD

    b = k.sorgu("pazar.dagitim.basari", "Başarı Dağıtım kataloğu", "logo", PD.SQL_BASARI,
                description="Başarı'nın güncel kataloğu; her gün okunur, portalda güncel hâli tutulur.")
    d = k.sorgu("pazar.dagitim.dr", "D&R kataloğu", "logo", PD.SQL_DR,
                description="D&R'nin güncel kataloğu (liste ve satış fiyatı, site durumu); her gün okunur.")
    return b, d


def _kategori_listesi(k: P.Kaynaklar, engine: Any, tenant: str, tarih: str, b: str) -> str:
    from datetime import date as _date

    from semantic_bridge.pricing import dagitim as DG

    return k.portal("portal.fiyat.dagitimKategori", "Başarı kategorileri (TİMAŞ dışı)",
                    DG.categories_stmt(tenant, _date.fromisoformat(tarih)), engine,
                    description="Son görüntüde fiyatlı, TİMAŞ grubu dışı başlık sayısı, kategori başına.", origin=[b])


def for_distributor(engine: Any, tenant: str, out: dict[str, Any]) -> P.Kaynaklar:
    """`/distributor`: kategori kümesi (portal), kitabın kendi Başarı kaydı ve kategori listesi; hesap `dagitim.py`."""
    from datetime import date as _date

    from semantic_bridge.pricing import dagitim as DG

    src = out.get("kaynak") or {}
    k = P.Kaynaklar(data_end=src.get("basari"))
    b, d = _dagitim_kaynak(k)
    kat = out.get("kategori") or {}
    ins = [b, d]
    fields: dict[str, str] = {}
    if src.get("basari"):
        kat_ins = [_kategori_listesi(k, engine, tenant, src["basari"], b)]
        if out.get("kod"):
            kat_ins.append(k.portal("portal.fiyat.dagitimKendi", "Kitabın kendi Başarı kaydı",
                                    DG.own_stmt(tenant, out["kod"]), engine,
                                    description="Logo barkodu ↔ stok kodu eşleşmesiyle kitabın Başarı başlığı.", origin=[b]))
        fields["kategori"] = k.hesap("dagitim.kategori", DG.F_KATEGORI, kat_ins)
        if kat.get("secili"):
            tb = _date.fromisoformat(src["basari"])
            td = _date.fromisoformat(src["dr"]) if src.get("dr") else None
            ins = [k.portal("portal.fiyat.dagitim", "Dağıtımcı kataloğu: kategori kümesi",
                            DG.rows_stmt(tenant, kat["secili"], tb, td), engine,
                            description="Seçilen kategorideki TİMAŞ dışı, fiyatlı başlıklar ve aynı barkodun D&R satırı; "
                                        "sayfa, kapak ve basım yılı süzgeçleri bu satırlar üstünde uygulanır.",
                            origin=[b, d])]
    f = k.hesap("dagitim", DG.F_DAGITIM, ins)
    fields.update({"tum": f, "sonYillar": f, "suzgec": f, "kume": f})
    k.alanlar(fields)
    return k


def for_distributor_categories(engine: Any, tenant: str, out: dict[str, Any]) -> P.Kaynaklar:
    k = P.Kaynaklar(data_end=out.get("tarih"))
    b, _ = _dagitim_kaynak(k)
    ins = [b] + ([_kategori_listesi(k, engine, tenant, out["tarih"], b)] if out.get("tarih") else [])
    k.alanlar({"items[]": k.hesap("dagitim.kategoriler", "Başlık sayısı = son Başarı görüntüsünde TİMAŞ grubu dışı, "
                                                         "liste fiyatı sıfırdan büyük başlıklar; üst kategori satırı "
                                                         "alt kategorilerinin toplamıdır.", ins)})
    return k
