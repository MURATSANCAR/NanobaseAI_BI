"""M38 Müşteri ilişkileri: ekrandaki her rakamın sorgu bilgisi (ortak sözleşme `provenance.py`).

Ekranlar gece turunun yazdığı cari, aksiyon, bulgu, puan ve segment tablolarından okur (`semantic_musteri_*`); gösterilen
SQL uçta çalışan ifadedir (`musteri.*_stmt`). Özet, cari listesi ve veri sağlığı listesi (liste kolonları hazırsa) toplamayı,
süzgeci, sırayı ve sayfayı veritabanında yapar: o zaman gösterilen SQL `overview_sql`/`accounts_page`/`findings_page`'in
çalıştırdığı ifadelerdir. Bu tabloları dolduran Logo/CRM sorguları gece turunda ÇALIŞAN metindir
(firma kopyası, pencere, şema yerinde): tur kaydında (`semantic_musteri_meta` «run».sorgular) saklanır ve köken olarak
gösterilir. Cari ayrıntısı ve aylık grafik Logo/CRM'i canlı okur (5 dk bellek): o istekte çalışan metin gösterilir.
Değer, kayıp riski, segment, aksiyon etkisi ve veri sağlığı puanı Python hesabıdır; formülü girdileriyle yazılır.
Güvenlik taramasının sorguları yalnız kolon adı ve satır sayısı okur; hiçbir değer seçilmez.
"""
from __future__ import annotations

from typing import Any, Optional

import sqlalchemy as sa

from semantic_bridge import field_sales as F
from semantic_bridge import field_sales_kaynak as FK
from semantic_bridge import musteri as M
from semantic_bridge import provenance as P

F_DEGER = ("Değer (Logo günlük faturalı satır, iki yıl kopyası cari koduyla birleşir): net = Σ LINENET satış (7, 8, 9) − "
           "Σ LINENET iade (2, 3). Son 12 ay = kesim − 364 gün … kesim; önceki 12 ay = ondan önceki 365 gün; bu yıl = 1 Ocak … "
           "kesim (kesim = Logo verisinin bittiği gün). Değişim = son 12 ay ÷ önceki 12 ay − 1; iade oranı = iade ÷ satış; "
           "fatura = son 12 aydaki satış faturası sayısı.")
F_ARALIK = ("Olağan alım aralığı = son 24 aydaki ardışık alım günleri arasındaki gün farkının medyanı (en az ayardaki sayıda alım "
            "günü varsa carinin kendi; yoksa aynı kanaldaki carilerin medyanı, o da yoksa bütün carilerin, hiç yoksa ayar). "
            "Son alımdan bu yana = kesim − son alım günü.")


def _risk_text(st: dict[str, Any]) -> str:
    w = "; ".join(f"{lab} {pts}" for _k, pts, lab in M.WEIGHTS)
    return ("Kayıp riski puanı (en çok 100) = Σ ağırlık × oran: aralık = (son alımdan geçen ÷ olağan aralık − 1,5) ÷ 1,5 (kesimden "
            "sonra CRM siparişi varsa yarıya iner); düşüş = (1 − son 12 ay ÷ önceki 12 ay − 0,10) ÷ 0,50 (düşüş %10'u geçerse); "
            "iade = (iade oranı artışı − 0,05) ÷ 0,15; sipariş = (CRM'de son siparişten geçen gün − eşik) ÷ eşik, eşik = en az "
            f"{st.get('orderFloorDays')} gün ya da 2 × olağan aralık. Ağırlıklar: {w}. Düzey: son alımdan geçen ≥ en az "
            f"{st.get('lostMinDays')} gün ya da {st.get('lostMultiple')} × olağan aralık → kayıp; puan ≥ {st.get('riskHigh')} "
            f"yüksek, ≥ {st.get('riskMid')} orta, altı düşük. Rakam modelden gelmez.")


F_SEGMENT = ("Segment = değer dilimi × kanal × eğilim. Değer dilimi: son 12 ay net alıma göre sıralı carilerin birikimli payının "
             "ilk %80'i A, sonraki %15'i B, kalanı C. Eğilim: önceki 12 aya göre %10'dan çok artış büyüyen, düşüş düşen; önceki "
             "12 ayda alımı yoksa yeni. Boyut = segmentteki cari, değer = Σ son 12 ay net, pay = değer ÷ toplam.")
F_ETKI = ("Aksiyon etkisi: aksiyon gününden sonraki 30 ve 90 gün net alım (Logo; kesim pencereyi kapsayınca olgunlaşır); oran = "
          "olgunlaşmış aksiyonlardan sonrasında alım olanların payı; riskli = aksiyon yazıldığında düzeyi yüksek ya da kayıp olan.")
F_SAGLIK = ("Veri sağlığı puanı = 100 × (etkin CRM carisi − bulgusu olan cari) ÷ etkin cari. Bulgular gece turunda CRM okumasından: "
            "Logo bağı yok, olası tekrar kayıt (ad benzerliği; belirsizse Zeki AI kararı), kanal eksik, sahipsiz, ortak hesaba ait, "
            "izin çelişkisi, güvenlik (yalnız kolon adı ve dolu satır sayısı).")


class _Ctx(FK._Ctx):
    def __init__(self, engine: Any, tenant: str, st: Optional[dict[str, Any]] = None):  # noqa: D107
        self.engine, self.tenant, self.st = engine, tenant, st or {}
        self.run = M.meta_get(engine, tenant, "run")
        self.k = P.Kaynaklar(data_end=self.run.get("kesim"), as_of=self.run.get("asof"))
        self._gece = None

    def gece(self) -> dict[str, list[str]]:
        if self._gece is None:
            self._gece = self._add("musteri.gece", self.run.get("sorgular") or [],
                                   "Gece turunda çalıştı; cari, bulgu ve segment tablolarını bu okuma doldurdu.")
        return self._gece

    def cari_origin(self) -> list[str]:
        """Cari satırlarını dolduran gece turu okumaları (köken)."""
        return self.g("crm.kullanicilar", "crm.cariler", "crm.son_siparis", "crm.ziyaret", "logo.donem", "logo.verisonu",
                      "logo.cariler", "logo.gunluk_satis")

    def cariler(self, owner: Optional[str] = None, code: Optional[str] = None, sid: str = "musteri.cariler") -> str:
        return self.portal(sid, "Cari satırları (değer, risk, segment)", M.accounts_stmt(self.tenant, owner, code),
                           "Gece turunda yazılır: temsilci ataması, 12 ay değer, olağan alım aralığı, kayıp riski, segment.",
                           origin=self.cari_origin())

    def aksiyonlar(self, code: str = "", durum: str = "", sid: str = "musteri.aksiyon") -> str:
        return self.portal(sid, "Müşteri aksiyonları", M.actions_stmt(self.tenant, code, durum),
                           "Elle girilir; 30/90 gün sonucu gece turunda Logo alımından yazılır.", origin=self.g("logo.gunluk_satis"))

    def puanlar(self) -> str:
        return self.portal("musteri.saglik_puani", "Günlük veri sağlığı puanı", M.scores_stmt(self.tenant, 400),
                           "Gece turunda yazılır.", origin=self.g("crm.cari_saglik", "crm.tum_kullanicilar", "crm.kisiler"))

    def card_fields(self, prefix: str, ca: str) -> dict[str, str]:
        deger = self.h("deger", F_DEGER, [ca] + self.g("logo.gunluk_satis"))
        aralik = self.h("aralik", F_ARALIK, [ca] + self.g("logo.gunluk_satis"))
        risk = self.h("risk", _risk_text(self.st), [ca] + self.g("logo.gunluk_satis", "crm.son_siparis"))
        p = f"{prefix}." if prefix else ""
        out = {f"{p}net12": deger, f"{p}netOnceki": deger, f"{p}netYil": deger, f"{p}degisim": deger, f"{p}fatura12": deger,
               f"{p}iade12": deger, f"{p}iadeOnceki": deger, f"{p}aralik": aralik, f"{p}gunSonAlim": aralik,
               f"{p}puan": risk, f"{p}nedenler": risk}
        return {prefix: ca, **out} if prefix else out


def _ok(x: _Ctx) -> None:
    if not x.run.get("sorgular"):
        raise P.ProvenanceError("Gece turunun çalışan sorguları kayıtlı değil (bir sonraki turdan sonra görünür).")


# ------------------------------------------------------------------ uçlar


def for_meta(engine: Any, tenant: str, user: str, st: dict[str, Any], out: dict[str, Any]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant, st)
    ay = x.ayar_kaydi("musteri.ayar", ["MUSTERI_RISK_HIGH", "MUSTERI_RISK_MID", "MUSTERI_LOST_MIN_DAYS", "MUSTERI_LOST_MULTIPLE",
                                       "MUSTERI_MIN_PURCHASE_DAYS", "MUSTERI_ORDER_FLOOR_DAYS", "MUSTERI_DEFAULT_INTERVAL_DAYS"], "müşteri riski")
    mine = sa.select(sa.func.count()).select_from(M.ACCOUNTS).where(M.ACCOUNTS.c.tenant_id == tenant, M.ACCOUNTS.c.temsilci == user)
    x.k.alanlar({"me": x.portal("musteri.benim", "Portföyümdeki cari", mine, "Size atanmış cari sayısı (gece turu ataması).",
                                origin=x.g("crm.cariler", "crm.kullanicilar")),
                 "weights": x.h("risk", _risk_text(st), [ay]), "rules": x.h("ayar_risk", "Ayarlar (Yönetim ekranı > ortam > "
                 "varsayılan): yüksek/orta risk eşiği, kayıp için en az gün ve aralık katı, en az alım günü, CRM sipariş eşiği.", [ay]),
                 "run": x.portal("musteri.tur", "Gece turu kaydı", M.meta_stmt(tenant, "run"),
                                 "Tur özeti: cari, atanmış, düzey sayıları, kesim ve o turda çalışan okuma sorguları.",
                                 origin=x.g("logo.donem", "logo.verisonu", "logo.cariler", "crm.cariler")),
                 "reps": x.portal("musteri.temsilciler", "Temsilci başına cari", M.reps_stmt(tenant), "Gece turu ataması.",
                                  origin=x.g("crm.cariler", "crm.kullanicilar"))})
    return x.k


def for_overview(engine: Any, tenant: str, owner: Optional[str], st: dict[str, Any], out: dict[str, Any],
                 stmts: Optional[dict[str, Any]] = None) -> P.Kaynaklar:
    """`stmts` verildiyse (liste kolonları hazır) özet veritabanında toplanmıştır: gösterilen SQL o üç ifadedir."""
    x = _Ctx(engine, tenant, st)
    _ok(x)
    if stmts:
        origin = x.cari_origin()
        kan = x.portal("musteri.kanallar", "Kanal başına cari sayımları ve değer", stmts["kanallar"],
                       "Gece turunun cari satırlarından kanal (Logo özel kod 2) başına: cari, aktif, son 12 ay ve bu yıl net "
                       "toplamı, yüksek ve kayıp riskli cari sayısı (veritabanında toplanır).", origin=origin)
        hot = x.portal("musteri.bakilacak", "Bakılacak ilk 10 cari", stmts["bakilacak"],
                       "Düzeyi yüksek ya da kayıp olan cariler, risk puanı × risk altındaki değer sırasıyla ilk 10.",
                       origin=origin)
        say = x.portal("musteri.bakilacak_sayi", "Bakılacak cari sayısı", stmts["bakilacak_sayi"],
                       "Düzeyi yüksek ya da kayıp olan cari sayısı.", origin=origin)
        ca, kan_in, bak_in = hot, [kan], [say, hot]
    else:
        ca = x.cariler(owner)
        kan_in, bak_in = [ca], [ca]
    kpi = x.h("ozet", "Özet: cari = kapsamdaki cari satırı; aktif = son 12 ayda net alımı ya da faturası olan; son 12 ay ve bu yıl "
              "net = satırların toplamı; riskli = düzeyi yüksek, kayıp = düzeyi kayıp olan cari sayısı. " + F_DEGER,
              kan_in + x.g("logo.gunluk_satis"))
    f = {"kpi": kpi, "kpi.saglik": x.h("saglik", F_SAGLIK, [x.puanlar()]), "kanallar": x.h(
        "kanal", "Kanal (Logo özel kod 2) başına aynı sayımlar: aktif cari, son 12 ay ve bu yıl net, riskli, kayıp.", kan_in),
         "bakilacakToplam": x.h("bakilacak", "Bakılacak = düzeyi yüksek ya da kayıp olan cariler; sıra risk puanı × risk "
                                "altındaki değer (son ve önceki 12 ayın büyüğü); ilk 10 gösterilir, toplam yazılır.", bak_in),
         "aksiyon": x.h("etki", F_ETKI, [x.aksiyonlar()] + x.g("logo.gunluk_satis"))}
    f.update(x.card_fields("bakilacak[]", ca))
    x.k.alanlar(f)
    return x.k


F_LISTE = ("Listede = süzgeçten (kanal, bölge, temsilci, risk, segment, arama) geçen cari; sayfa sayfa gelir (toplam her zaman "
           "yazılır). Toplam net = süzgeçteki carilerin son 12 ay net alımı; riskli = yüksek ya da kayıp düzeyindeki cari sayısı.")


def for_accounts(engine: Any, tenant: str, owner: Optional[str], st: dict[str, Any], out: dict[str, Any],
                 stmts: Optional[dict[str, Any]] = None) -> P.Kaynaklar:
    """`stmts` verildiyse süzgeç, sıra ve sayfa veritabanında koştu: gösterilen SQL sayfa ve toplam ifadeleridir."""
    x = _Ctx(engine, tenant, st)
    _ok(x)
    if stmts:
        origin = x.cari_origin()
        ca = x.portal("musteri.cariler", "Cari satırları (bu sayfa)", stmts["sayfa"],
                      "Gece turunun cari satırları; süzgeç, sıra ve sayfa veritabanında.", origin=origin)
        tot = x.portal("musteri.cariler_toplam", "Süzgeçteki cari sayısı ve toplamlar", stmts["toplam"],
                       "Süzgeçten geçen cari sayısı, son 12 ay net toplamı ve riskli cari sayısı.", origin=origin)
        ins = [tot, ca]
    else:
        ca = x.cariler(owner)
        ins = [ca]
    f = x.card_fields("items[]", ca)
    f["total"] = x.h("liste", F_LISTE, ins)
    f["toplam"] = f["total"]
    x.k.alanlar(f)
    return x.k


def for_account(engine: Any, tenant: str, code: str, st: dict[str, Any], out: dict[str, Any],
                live_reads: list[dict[str, Any]]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant, st)
    _ok(x)
    ca = x.cariler(code=code, sid="musteri.cariler.cari")
    live = x.canli(live_reads)
    f = x.card_fields("", ca)
    fat = live.get("logo.faturalar") or []
    if fat:
        f["faturalar"] = fat[0]
    kit = live.get("logo.kitaplar") or []
    if kit:
        f["kitaplar"] = kit[0] if len(kit) == 1 else x.h("kitaplar", "Kitap başına son 12 ay net adet ve ciro = yıl kopyası "
                                                         "pencerelerindeki okumaların cari koduyla toplamı.", kit)
    sip = live.get("crm.siparisler") or []
    if sip:
        f["siparisler"] = sip[0]
    f["ziyaretler"] = x.ziyaret("musteri.ziyaret", hedef=code, tur="cari")
    f["aksiyonlar"] = x.aksiyonlar(code=code, sid="musteri.aksiyon.cari")
    f["tahsilat"] = x.portal("musteri.saha_sinyal", "Saha tahsilat sinyali (M30 gece turu)",
                             F.portfolio_stmt(tenant, code=code),
                             "Bakiye, vadesi geçmiş (FIFO, yaklaşık), 90+ gün, limit doluluğu, riskte sipariş, çek olayı; saha "
                             "ekranının gece turunda yazılır.")
    x.k.alanlar(f)
    return x.k


def for_monthly(engine: Any, tenant: str, out: dict[str, Any], live_reads: list[dict[str, Any]]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant)
    _ok(x)
    ay = x.canli(live_reads).get("logo.aylik_cari") or []
    if not ay:
        raise P.ProvenanceError("Aylık alım okuması bu istekte kaydedilmedi.")
    x.k.alanlar({"items": x.h("aylik", "Aylık net alım = ay başına Σ LINENET satış (7, 8, 9) − Σ LINENET iade (2, 3); yıl "
                              "kopyası pencereleri cari koduyla birleşir; son 24 ay, kesim ayına kadar.", ay)})
    return x.k


def for_actions(engine: Any, tenant: str, durum: str, musteri: str, out: dict[str, Any]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant)
    a = x.aksiyonlar(code=musteri, durum=durum)
    x.k.alanlar({"items": a, "etki": x.h("etki", F_ETKI, [a] + x.g("logo.gunluk_satis"))})
    return x.k


def for_my_portfolio(engine: Any, tenant: str, user: str, st: dict[str, Any], out: dict[str, Any]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant, st)
    _ok(x)
    ca = x.cariler(user, sid="musteri.cariler.benim")
    f = x.card_fields("items[]", ca)
    f["count"] = x.h("portfoy", "Portföyüm = size atanmış cariler (aramaya uyan); bu hafta aranacak = düzeyi yüksek ya da "
                     "kayıp olanlar; sıra risk puanı × risk altındaki değer.", [ca])
    f["buHafta"] = f["count"]
    f["acikAksiyon"] = x.aksiyonlar(durum="acik", sid="musteri.aksiyon.acik")
    x.k.alanlar(f)
    return x.k


def for_health(engine: Any, tenant: str, tur: str, durum: str, onem: str, security: bool, out: dict[str, Any],
               stmts: Optional[dict[str, Any]] = None) -> P.Kaynaklar:
    """`stmts` verildiyse süzgeç, arama, sıra ve sayfa veritabanında koştu: gösterilen SQL sayfa ve sayım ifadeleridir."""
    x = _Ctx(engine, tenant)
    _ok(x)
    origin = x.g("crm.cari_saglik", "crm.tum_kullanicilar", "crm.son_siparis", "crm.kisiler", "crm.kampanya", "crm.guvenlik",
                 "logo.cari_kodlari")
    desc = "Gece turunda CRM okumasından; işaretler elle (CRM'de düzeltme insanın)."
    if stmts:
        fi = x.portal("musteri.bulgular", "Veri sağlığı bulguları (bu sayfa)", stmts["sayfa"],
                      desc + " Süzgeç, arama, sıra ve sayfa veritabanında.", origin=origin)
        total = x.portal("musteri.bulgular_sayi", "Süzgeçteki bulgu sayısı", stmts["toplam"], desc, origin=origin)
    else:
        fi = x.portal("musteri.bulgular", "Veri sağlığı bulguları", M.findings_stmt(tenant, tur, durum, onem, security),
                      desc, origin=origin)
        total = fi
    sag = x.h("saglik", F_SAGLIK, [x.puanlar()])
    info = x.portal("musteri.saglik_kaydi", "Veri sağlığı tur kaydı", M.meta_stmt(tenant, "health"),
                    "Kişi kaydı veri durumu dağılımı, CRM kanal dağılımı, kişi sayısı, Zeki AI kararları.",
                    origin=x.g("crm.kisiler", "crm.cari_saglik"))
    x.k.alanlar({"items": fi, "total": total, "sayilar": x.portal("musteri.bulgu_sayilari", "Bulgu türü × durum",
                                                               M.finding_counts_stmt(tenant), "Bulgu tablosundan.", origin=[fi]),
                 "puan": sag, "onceki": sag, "veriDurumu": info, "crmKanal": info, "kisi": info, "zeki": info})
    return x.k


def for_score_history(engine: Any, tenant: str, out: dict[str, Any]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant)
    x.k.alanlar({"items": x.h("saglik", F_SAGLIK, [x.puanlar()])})
    return x.k


def for_segments(engine: Any, tenant: str, out: dict[str, Any]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant)
    sg = x.portal("musteri.segmentler", "Segmentler", M.segments_stmt(tenant), "Gece turunda yazılır.",
                  origin=x.g("logo.gunluk_satis"))
    x.k.alanlar({"items": x.h("segment", F_SEGMENT, [sg])})
    return x.k


NOT_RAKAM = ("page", "size", "pages", "run.year")
