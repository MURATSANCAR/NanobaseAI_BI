"""M30 Saha satış ve tahsilat: ekrandaki her rakamın sorgu bilgisi (ortak sözleşme `provenance.py`).

Ekranlar gece turunun yazdığı portföy + sinyal tablolarından okur (`semantic_field_portfolio`, `_signals`); gösterilen
SQL uçta çalışan ifadedir (`field_sales.portfolio_stmt` …). Bu tabloları dolduran asıl Logo/CRM sorguları gece turunda
ÇALIŞAN metindir (firma kopyası, pencere, şema yerinde): tur kaydında (`semantic_field_meta` «run».sorgular) saklanır ve
köken olarak gösterilir. Brifing ve tahsilat listesi CRM/Logo'yu canlı okur (5 dk bellek): o istekte çalışan (ya da
belleği dolduran) metin doğrudan gösterilir. Yaşlandırma, hedef, öncelik puanı, sayaçlar Python hesabıdır; formülü
girdileriyle yazılır. Kişisel veri: SQL metni gösterilir, sonuç satırı kayda girmez.
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

from semantic_bridge import field_sales as F
from semantic_bridge import field_sales_sources as src
from semantic_bridge import kaynak_ayar as KA
from semantic_bridge import provenance as P

TITLES = {
    "crm.kullanicilar": "CRM kullanıcıları (temsilci, BMT bayrağı)",
    "crm.cariler": "CRM cariler (sahip, il temsilcisi, risk ve limitler, yıl hedefi)",
    "crm.riskli_siparis": "CRM riske takılan açık siparişler",
    "crm.tahsilat": "CRM tahsilat onay akışı",
    "crm.ziyaret": "CRM cari ziyaretleri",
    "crm.siparisler": "CRM carinin son siparişleri",
    "crm.siparis_durum": "CRM sipariş durum adları",
    "logo.donem": "Logo dönem (yıl kopyası) listesi",
    "logo.verisonu": "Logo veri sonu (son faturalı satış günü)",
    "logo.cariler": "Logo müşteri carileri",
    "logo.yaslandirma": "Logo bakiye ve FIFO yaşlandırma",
    "logo.odeme": "Logo cari ödemeleri (12 ay)",
    "logo.son_odeme": "Logo carinin son ödemeleri",
    "logo.satis": "Logo faturalı satış ve iade (cari başına)",
    "logo.cek": "Logo karşılıksız / protestolu çek-senet",
    "logo.faturalar": "Logo carinin son faturaları",
    "logo.kitaplar": "Logo carinin kitap başına alımı",
    "logo.benzer": "Logo benzer carilerin kitap alımı",
    "logo.yeni_kitap": "Logo yeni çıkan kitaplar (ilk faturalı satış)",
    "logo.satilmis": "Logo önceki yıl satılmış kitaplar",
    "logo.saha_ziyaret": "Saha uygulaması ziyaretleri",
    "logo.saha_tahsilat": "Saha uygulaması tahsilatları",
    "crm.cari_bayrak": "CRM cari bayrakları (sorunlu müşteri, kredi askıda, vade günü, ek limit)",
    "crm.risk_gecmisi": "CRM carinin risk onay geçmişi",
    "logo.aylik_satis": "Logo cari × ay faturalı satış ve iade",
    "logo.aylik_odeme": "Logo cari × ay ödeme",
    "crm.kullanici_eposta": "CRM kullanıcı kurum e-postası",
    "crm.tum_kullanicilar": "CRM bütün kullanıcılar (etkin/kapalı)",
    "crm.son_siparis": "CRM cari başına son sipariş",
    "crm.cari_saglik": "CRM cari veri sağlığı kolonları",
    "crm.kisiler": "CRM kişi kayıtları (izin, veri durumu)",
    "crm.guvenlik": "CRM güvenlik taraması (yalnız kolon adı ve dolu satır sayısı)",
    "crm.cari_sayisi": "CRM etkin cari sayısı",
    "crm.kampanya": "CRM kampanya gönderimleri",
    "logo.gunluk_satis": "Logo cari × gün faturalı satış ve iade",
    "logo.aylik_cari": "Logo carinin aylık alımı",
    "logo.cari_kodlari": "Logo bütün cari kodları",
}

F_YASLANDIRMA = ("Bakiye = yıl başından cari hareketi borç − alacak (müşteri carisi, kod 120…). Vadesi geçmiş (yaklaşık, "
                 "FIFO): bakiye carinin en yeni vade satırlarından geriye dağıtılır, eski satırlar ödenmiş sayılır; açık kalan "
                 "pay yaşına göre 1–30 / 31–60 / 61–90 / 90+ gün kovasına girer; vadesi gelmemiş ayrı; vade planına "
                 "dağıtılamayan bakiye «plansız». Logo'da ödeme kapama kullanılmadığı için yaklaşıktır.")
F_SATIS = ("Net alım = faturalı satır (LINETYPE 0, fatura bağlı, iptal değil) Σ LINENET satış (7, 8, 9) − Σ LINENET iade "
           "(2, 3). Yıl başından = bu yılın kopyasında 1 Ocak – veri sonu; geçen yılın aynı dönemi = önceki yılın kopyasında "
           "1 Ocak – veri sonunun bir yıl öncesi; geçen yıl toplam = önceki yılın tamamı; iade oranı = iade ÷ satış.")
F_HEDEF = ("Cari hedefi: yürürlükteki bütçe planı varsa planın toplam hedef cirosu carilere önceki yıl net alım payıyla dağıtılır "
           "(toplam korunur); beklenen = yıllık hedef × planın aylık dağılımıyla bugüne kadar geçen pay. Plan yoksa CRM cari yıl "
           "hedefi (ölçeği tutarlıysa), beklenen takvim günü oranıyla. Hedef açığı = 1 − yıl başından net alım ÷ beklenen; "
           "hedef oranı = Σ yıl başından ÷ Σ beklenen (hedefi olan carilerde).")
F_RISK = (f"Limit doluluğu = CRM toplam risk ÷ CRM toplam limit; limit {src.MIN_REAL_LIMIT:,.0f} ₺'nin altındaysa yer tutucu "
          "sayılır, doluluk yazılmaz. Riskte sipariş = CRM'de risk onayına takılmış açık sipariş sayısı.").replace(",", ".")
F_CEK = ("Çek/senet olayı = son 12 ayda karşılıksız çıkan (CSTRANS durum 11) ya da protesto edilen (5, 7) müşteri çek/senedi "
         "sayısı, çek başına bir kez; iki yıl kopyası toplanır.")
F_ODEME = ("Son ödeme = cari hareketinde alacak satırı (ayardaki ödeme türleri: FIELD_PAYMENT_TRCODES) en son tarihi; 12 ay "
           "ödeme = aynı satırların son 365 gündeki toplamı (iki yıl kopyası).")


def _puan_text() -> str:
    w = ", ".join(f"{lab.split(' (')[0]} {pts}" for _k, pts, lab in F.WEIGHTS)
    return ("Öncelik puanı = en çok 100; bileşen başına ağırlık × oran (0–1). Gecikme: yaşa göre ağırlıklı vadesi geçmiş "
            "(1–30 ×1, 31–60 ×2, 61–90 ×3, 90+ ×4) tutarının portföy içindeki yüzdelik sırası; 90+ gün alacak var; son 12 ayda "
            "çek/senet olayı; limit doluluğu %50'nin üstünde (doluluk − 0,5) ÷ 0,5; sipariş riske takılı; ödeme sözü geçti ve "
            "sonrasında ödeme yok; son 30 günde reddedilen tahsilat; hedef açığı %5'in üstünde; satış geçen yılın aynı "
            "döneminin %5'ten fazla gerisinde; son ziyaret ziyaret döngüsünden eski ((gün − döngü) ÷ döngü); müdür önceliği. "
            f"Ağırlıklar: {w}. Rakam modelden gelmez.")


class _Ctx:
    def __init__(self, engine: Any, tenant: str):
        self.engine, self.tenant = engine, tenant
        self.run = F.meta_get(engine, tenant, "run")
        self.k = P.Kaynaklar(data_end=self.run.get("dataEnd"), as_of=self.run.get("asof"))
        self._gece: Optional[dict[str, list[str]]] = None

    # -- okumada çalışan CRM/Logo metni
    def _add(self, prefix: str, reads: Iterable[dict[str, Any]], desc: str) -> dict[str, list[str]]:
        by: dict[str, list[str]] = {}
        seen: dict[str, str] = {}
        for q in reads or []:
            sql = q.get("sql") or ""
            if not sql:
                continue
            tag = q.get("key") or src.query_tag(sql)
            if sql in seen:
                continue
            base = tag.split(".")[0] + "." + tag.split(".")[1] if tag.count(".") >= 1 else tag
            title = TITLES.get(base, "Okuma")
            rest = tag[len(base):].strip(".")
            sid = f"{prefix}.{tag}"
            n = 2
            while sid in self.k.sources:
                sid = f"{prefix}.{tag}.{n}"
                n += 1
            conn = q.get("conn") if q.get("conn") in ("crm", "logo") else ("logo" if tag.startswith("logo") else "crm")
            try:
                self.k.sorgu(sid, title + (f" ({rest.replace('.', ' · ')})" if rest else ""), conn, sql, database=q.get("db"),
                             rows=q.get("rows"), ms=q.get("dbMs"), ran_at=q.get("at"), description=desc)
            except P.ProvenanceError:
                continue
            seen[sql] = sid
            by.setdefault(base, []).append(sid)
        return by

    def gece(self) -> dict[str, list[str]]:
        if self._gece is None:
            self._gece = self._add("saha.gece", self.run.get("sorgular") or [],
                                   "Gece turunda çalıştı; portföy ve sinyal tablosunu bu okuma doldurdu.")
        return self._gece

    def g(self, *bases: str) -> list[str]:
        out: list[str] = []
        for b in bases:
            out += self.gece().get(b, [])
        return out

    def canli(self, reads: Iterable[dict[str, Any]], desc: str = "Bu istekte çalıştı (ya da 5 dakikalık belleği doldurdu).") -> dict[str, list[str]]:
        return self._add("saha.canli", reads, desc)

    # -- portal
    def portal(self, sid: str, title: str, stmt: Any, desc: str, origin: Iterable[str] = ()) -> str:
        if sid in self.k.sources:
            return sid
        return self.k.portal(sid, title, stmt, self.engine, description=desc, origin=origin)

    def sinyal(self, owner: Optional[str] = None, code: Optional[str] = None, sid: str = "saha.sinyal") -> str:
        return self.portal(sid, "Portföy ve gece sinyalleri", F.portfolio_stmt(self.tenant, owner, code),
                           "Temsilci ↔ cari ataması, bakiye/yaşlandırma, satış, ödeme, çek, risk, hedef; gece turunda yazılır.",
                           origin=self.g("crm.kullanicilar", "crm.cariler", "crm.riskli_siparis", "crm.ziyaret", "logo.donem",
                                         "logo.verisonu", "logo.cariler", "logo.yaslandirma", "logo.odeme", "logo.satis",
                                         "logo.cek", "logo.saha_ziyaret", "logo.saha_tahsilat"))

    def tur(self) -> str:
        return self.portal("saha.tur", "Gece turu kaydı", F.meta_stmt(self.tenant, "run"),
                           "Tur özeti: cari sayısı, atanmış cari, yıl ve firma kopyası, veri sonu, hedef kaynağı ve o turda "
                           "çalışan okuma sorguları.", origin=self.g("logo.donem", "logo.verisonu", "crm.cariler", "logo.cariler"))

    def ziyaret(self, sid: str = "saha.ziyaret", **kw: Any) -> str:
        return self.portal(sid, "Saha ziyaretleri ve ödeme sözleri", F.visits_stmt(self.tenant, **kw),
                           "Ortak ziyaret tablosu (M30/M31); temsilci girer.")

    # -- hesaplar
    def h(self, name: str, text: str, inputs: Iterable[str]) -> str:
        if name in self.k.formulas:
            return f"hesap:{name}"
        return self.k.hesap(name, text, list(dict.fromkeys(i for i in inputs if i)))

    def card_fields(self, prefix: str, sig: str, extra: Iterable[str] = ()) -> dict[str, str]:
        """Müşteri kartı (liste satırı) rakamları."""
        ex = list(extra)
        yas = self.h("yaslandirma", F_YASLANDIRMA, [sig] + self.g("logo.yaslandirma"))
        sat = self.h("satis", F_SATIS, [sig] + self.g("logo.satis"))
        hed = self.h("hedef", F_HEDEF, [sig] + self.g("logo.satis", "crm.cariler"))
        rsk = self.h("risk", F_RISK, [sig] + self.g("crm.cariler", "crm.riskli_siparis"))
        cek = self.h("cek", F_CEK, [sig] + self.g("logo.cek"))
        puan = self.h("puan", _puan_text(), [sig, self.ziyaret(), self.portal(
            "saha.oncelik", "Müdür öncelikleri", F.overrides_stmt(self.tenant), "Elle girilir (müdür).")] + ex)
        return {f"{prefix}": sig, f"{prefix}.bakiye": yas, f"{prefix}.vadesiGecmis": yas, f"{prefix}.kovalar": yas,
                f"{prefix}.plansiz": yas, f"{prefix}.ytd": sat, f"{prefix}.gecenYil": sat, f"{prefix}.hedefBeklenen": hed,
                f"{prefix}.hedefAcigi": hed, f"{prefix}.riskDoluluk": rsk, f"{prefix}.siparisRiskte": rsk,
                f"{prefix}.cekOlay": cek, f"{prefix}.puan": puan, f"{prefix}.gerekce": puan}

    def ayar_kaydi(self, sid: str, keys: list[str], what: str) -> str:
        """Ayar kaydı okuması (`admin.settings_stmt`, çalışan ifade); ayardan gelen rakamların kaynağı."""
        if sid in self.k.sources:
            return sid
        return KA.ayar(self.k, self.engine, sid, keys, what)

    def ayar(self) -> str:
        src_ = self.ayar_kaydi("saha.ayar", ["FIELD_VISIT_CYCLE_DAYS", "FIELD_COLLECTION_DAYS", "FIELD_PENDING_WARN_HOURS",
                                             "FIELD_PLAN_MAX_INSTALLMENTS", "FIELD_SIMILAR_MIN", "FIELD_NEW_BOOK_DAYS",
                                             "FIELD_AGING_ASOF", "FIELD_CUSTOMER_TARGET_SOURCE"], "saha")
        return self.h("ayar", "Ayarlar (Yönetim ekranı > ortam > varsayılan): ziyaret döngüsü, tahsilat penceresi, onay bekleme "
                      "uyarı saati, en çok taksit, benzer cari eşiği, yeni kitap penceresi, yaşlandırma günü, hedef kaynağı; "
                      "öncelik ağırlıkları kodda sabit (ekranda yazılı).", [src_])


def _ok(x: _Ctx) -> None:
    if not x.run.get("sorgular"):
        raise P.ProvenanceError("Gece turunun çalışan sorguları kayıtlı değil (bir sonraki turdan sonra görünür).")


# ------------------------------------------------------------------ uçlar


def for_meta(engine: Any, tenant: str, user: str, out: dict[str, Any]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant)
    import sqlalchemy as sa

    mine = sa.select(sa.func.count()).select_from(F.PORTFOLIO).where(F.PORTFOLIO.c.tenant_id == tenant, F.PORTFOLIO.c.ad_hesap == user)
    x.k.alanlar({"me": x.portal("saha.benim", "Portföyümdeki cari sayısı", mine, "Size atanmış cari sayısı (gece turu ataması).",
                                origin=x.g("crm.cariler", "crm.kullanicilar")),
                 "reps": x.portal("saha.temsilciler", "Temsilci başına cari", F.reps_stmt(tenant), "Gece turu ataması.",
                                  origin=x.g("crm.cariler", "crm.kullanicilar")),
                 "run": x.tur(), "weights": x.ayar(), "settings": x.ayar()})
    return x.k


def for_today(engine: Any, tenant: str, owner: Optional[str], out: dict[str, Any], live_reads: list[dict[str, Any]],
              user: str) -> P.Kaynaklar:
    x = _Ctx(engine, tenant)
    _ok(x)
    sig = x.sinyal(owner)
    tah = x.canli(live_reads).get("crm.tahsilat", [])
    kpi = x.h("bugun_kpi", "Vadesi geçmiş ve 90+ gün = kapsamdaki carilerin yaşlandırma kovaları toplamı (FIFO, yaklaşık); cari = kapsamdaki cari sayısı; hedef oranı = Σ yıl başından net alım ÷ Σ beklenen (hedefi olan "
              "carilerde).", [sig] + x.g("logo.yaslandirma", "logo.satis"))
    bek = x.h("onay_bekleyen", "Onay bekleyen = CRM'de durumu «Onay Bekliyor» olan tahsilat kaydı sayısı ve tutar toplamı "
              "(kapsam: kaydın sahibi temsilci).", tah + x.g("crm.kullanicilar"))
    f = x.card_fields("items[]", sig, tah)
    f.update({f"planned[].musteri{k[7:]}": v for k, v in x.card_fields("items[]", sig, tah).items()})
    f.update({"kpi": kpi, "kpi.onayBekleyen": bek, "kpi.onayBekleyenTutar": bek,
              "total": x.h("liste_sayisi", "Listede = kapsamdaki cariler (aramaya uyan); sıra öncelik puanına göre, sayfa sayfa "
                           "gelir (kesilmez).", [sig]),
              "planned": x.ziyaret("saha.ziyaret.bugun", owner=owner, tur="cari")})
    x.k.alanlar(f)
    return x.k


def for_morning(engine: Any, tenant: str, owner: Optional[str], out: dict[str, Any], live_reads: list[dict[str, Any]]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant)
    _ok(x)
    sig = x.sinyal(owner)
    tah = x.canli(live_reads).get("crm.tahsilat", [])
    x.k.alanlar({"metin": x.h("sabah", "Sabah brifi Zeki AI'ın ya da kuralın yazdığı metindir; içindeki her sayı «Bugün» "
                              "listesinin olgularından (vadesi geçmiş, 90+ gün, onay bekleyen, bugün planlanan ziyaret, "
                              "öncelik sırasındaki ilk üç cari) gelir, olgularda olmayan sayı varsa kural metni gösterilir.",
                              [sig, x.ziyaret("saha.ziyaret.bugun", owner=owner, tur="cari")] + tah)})
    return x.k


def for_portfolio(engine: Any, tenant: str, owner: Optional[str], out: dict[str, Any]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant)
    _ok(x)
    sig = x.sinyal(owner)
    f = x.card_fields("items[]", sig)
    f["count"] = x.h("portfoy_sayisi", "Portföydeki cari sayısı (aramaya uyan).", [sig])
    x.k.alanlar(f)
    return x.k


def for_collections(engine: Any, tenant: str, owner: Optional[str], out: dict[str, Any]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant)
    _ok(x)
    sig = x.sinyal(owner)
    f = x.card_fields("items[]", sig)
    kova = x.h("kova_toplam", "Kova toplamı = vadesi geçmiş alacağı olan carilerin o kovadaki tutarlarının toplamı; müşteri "
               "sayısı ve toplam seçili kovada. " + F_YASLANDIRMA, [sig] + x.g("logo.yaslandirma"))
    f.update({"totals": kova, "count": kova, "total": kova})
    x.k.alanlar(f)
    return x.k


def for_crm_collections(engine: Any, tenant: str, out: dict[str, Any], live_reads: list[dict[str, Any]]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant)
    tah = x.canli(live_reads)
    t = tah.get("crm.tahsilat", [])
    if not t:
        raise P.ProvenanceError("CRM tahsilat okuması bu istekte kaydedilmedi.")
    lab = x.portal("saha.red_etiket", "Reddedilme nedeni etiketleri", F.labels_stmt(), "Serbest metin nedeni Zeki AI'ın kapalı kümeye sınıflaması (olasılıkla).",
                   origin=t)
    oz = x.h("tahsilat_ozet", "Kayıt sayısı ve tutar = seçili durumdaki CRM tahsilat kayıtlarının sayısı ve Σ tutar (reddedilen: "
             "son N gün); nedenler = kayıt başına CRM red sebebi ya da Zeki AI etiketi sayımı; yaş = şimdi − oluşturma (saat).",
             t + [lab])
    x.k.alanlar({"items[]": t[0], "items[].yasSaat": oz, "items[].zekiEtiket": lab, "count": oz, "total": oz, "reasons": oz,
                 "warnHours": x.ayar()})
    return x.k


def for_brief(engine: Any, tenant: str, code: str, out: dict[str, Any], live_reads: list[dict[str, Any]]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant)
    _ok(x)
    sig = x.sinyal(code=code, sid="saha.sinyal.cari")
    live = x.canli(live_reads)
    L = lambda *b: [i for k in b for i in live.get(k, [])]  # noqa: E731
    yas = x.h("yaslandirma", F_YASLANDIRMA, [sig] + x.g("logo.yaslandirma"))
    sat = x.h("satis", F_SATIS, [sig] + x.g("logo.satis"))
    hed = x.h("hedef", F_HEDEF, [sig] + x.g("logo.satis", "crm.cariler"))
    rsk = x.h("risk", F_RISK, [sig] + x.g("crm.cariler", "crm.riskli_siparis"))
    cek = x.h("cek", F_CEK, [sig] + x.g("logo.cek"))
    ode = x.h("odeme", F_ODEME, [sig] + x.g("logo.odeme"))
    zv = x.ziyaret("saha.ziyaret.cari", hedef=code, tur="cari")
    puan = x.h("puan", _puan_text(), [sig, zv, x.portal("saha.oncelik", "Müdür öncelikleri", F.overrides_stmt(tenant),
                                                        "Elle girilir (müdür).")] + L("crm.tahsilat"))
    f: dict[str, str] = {"signals": sig, "puan": puan, "gerekce": puan}
    for k in ("bakiye", "vadesi_gecmis", "gelmemis", "plansiz", "k_1_30", "k_31_60", "k_61_90", "k_90p"):
        f[f"signals.{k}"] = yas
    for k in ("ytd_net_ciro", "gecen_yil_ayni_donem", "gecen_yil_tam", "iade_orani"):
        f[f"signals.{k}"] = sat
    for k in ("hedef_beklenen", "hedef_acigi", "hedef_yil"):
        f[f"signals.{k}"] = hed
    for k in ("risk_toplam", "limit_toplam", "risk_doluluk", "siparis_riskte"):
        f[f"signals.{k}"] = rsk
    for k in ("karsiliksiz_olay_12ay", "protesto_olay_12ay", "cek_olay_tutar"):
        f[f"signals.{k}"] = cek
    f["signals.odeme_12ay"] = ode
    fat = L("logo.faturalar")
    if fat:
        f["faturalar"] = fat[0]
    son = L("logo.son_odeme")
    f["odemeler"] = son[0] if son else ode
    sip = L("crm.siparisler")
    if sip:
        f["siparisler"] = sip[0]
    tah = L("crm.tahsilat")
    if tah:
        f["tahsilatlar"] = tah[0]
    f["sahaTahsilat"] = x.g("logo.saha_tahsilat")[0] if x.g("logo.saha_tahsilat") else sig
    kit = L("logo.kitaplar")
    budget = x.portal("saha.butce_satis", "Kitabın önceki yıl net adedi (bütçe gerçekleşme önbelleği)",
                      F.book_prev_totals_stmt(int(x.run.get("year") or 0) - 1),
                      "Bütçe modülünün gerçekleşme önbelleği (aynı satış satırı tanımı).")
    f["hedefKitaplar"] = x.h("kitap_acigi", "Kitap hedef açığı = carinin önceki yıl bu kitaptaki adet payı (carinin adedi ÷ "
                             "kitabın bütün carilere adedi) × kitabın yürürlükteki bütçe planındaki yıllık hedef adedi × aylık "
                             "dağılımla geçen pay − carinin bu yılki adedi; açık ciro = açık adet × planın birim cirosu. "
                             "Yalnız açığı 0,5 adetten büyük kitaplar.", kit + [budget])
    f["oneriler"] = x.h("oneri", "Öneri = bu carinin 24 ayda almadığı, aynı şehir ve kanaldaki benzer carilerden en az ayardaki "
                        "sayıda carinin aldığı kitaplar (kaç cari aldı, ciro) ve ilk faturalı satışı ayardaki gün içinde olan "
                        "yeni kitaplar; sıra benzer cari sayısı, sonra ciro. Liste kesilmez.",
                        kit + L("logo.benzer", "logo.yeni_kitap", "logo.satilmis"))
    f["ziyaretler"] = zv
    f["odemePlanlari"] = x.portal("saha.odeme_plani.cari", "Ödeme planı önerileri", F.plans_stmt(tenant, code=code),
                                  "Temsilci girer, müdür onaylar; Logo/CRM'e yazılmaz.")
    f["sozGecti"] = x.h("soz", "Söz geçti = bu cariye girilen, tarihi bugünden önce olan en son ödeme sözü; Logo'daki son "
                        "ödeme sözün tarihinden önceyse (ya da yoksa) geçmiş sayılır.", [zv, sig] + x.g("logo.odeme"))
    x.k.alanlar(f)
    return x.k


def for_visits(engine: Any, tenant: str, out: dict[str, Any], **kw: Any) -> P.Kaynaklar:
    x = _Ctx(engine, tenant)
    x.k.alanlar({"items": x.ziyaret("saha.ziyaret", **kw)})
    return x.k


def for_plans(engine: Any, tenant: str, out: dict[str, Any], durum: str = "", code: str = "") -> P.Kaynaklar:
    x = _Ctx(engine, tenant)
    pl = x.portal("saha.odeme_plani", "Ödeme planı önerileri", F.plans_stmt(tenant, durum, code),
                  "Temsilci girer (öneri: vadesi geçmiş tutar ayardaki en çok taksite eşit bölünür), müdür onaylar; "
                  "Logo/CRM'e yazılmaz.")
    x.k.alanlar({"items": pl, "items[].taksitToplam": x.h("taksit_toplam", "Taksit toplamı = planın taksit tutarlarının "
                                                          "toplamı; ekranda vadesi geçmiş tutarla farkı yazılır.", [pl])})
    return x.k


def for_overrides(engine: Any, tenant: str, out: dict[str, Any]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant)
    x.k.alanlar({"items": x.portal("saha.oncelik", "Müdür öncelikleri", F.overrides_stmt(tenant), "Elle girilir (müdür).")})
    return x.k


def for_weekly(engine: Any, tenant: str, owner: Optional[str], start: str, out: dict[str, Any],
               live_reads: list[dict[str, Any]]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant)
    _ok(x)
    sig = x.sinyal(owner)
    zv = x.ziyaret("saha.ziyaret.hafta", tur="cari", since=start)
    tah = x.canli(live_reads).get("crm.tahsilat", [])
    x.k.alanlar({"items": x.h("haftalik", "Temsilci başına: cari sayısı; yıl başından net alım, geçen yılın aynı dönemi, "
                              "büyüme = yıl başından ÷ geçen yıl − 1; hedef oranı = Σ yıl başından ÷ Σ beklenen (hedefi olan "
                              "carilerde); vadesi geçmiş ve 90+ gün toplamı (FIFO, yaklaşık); çek/senet olayı; onay bekleyen "
                              "CRM tahsilatı (sayı, tutar) ve hafta içinde reddedilen; hafta içinde «yapıldı» ziyaret ve not "
                              "sayısı. " + F_SATIS, [sig, zv] + tah + x.g("logo.satis", "logo.yaslandirma"))})
    return x.k


NOT_RAKAM = ("offset", "items[].durum", "odemeler[].tur")
