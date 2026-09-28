"""M59 Bayi riski ve performans: ekrandaki her rakamın sorgu bilgisi (ortak sözleşme `provenance.py`).

Ekranlar günlük turun yazdığı skor satırlarından okur (`semantic_dealer_scores`, `_series`); gösterilen SQL uçta çalışan
ifadedir (`dealers.*_stmt`). Tabloyu dolduran Logo/CRM sorguları günlük turda ÇALIŞAN metindir (firma kopyası, pencere,
şema yerinde): tur kaydında (`semantic_dealer_meta` «run».sorgular) saklanır ve köken olarak gösterilir. Skor, segment,
eğilim, limit önerisi ve pano toplamları Python hesabıdır; formül yürürlükteki kural sürümünün ağırlık ve eşikleriyle
yazılır. Kaynak okuması M30 ile ortaktır (`field_sales.recording`).
"""
from __future__ import annotations

from typing import Any, Optional

from semantic_bridge import dealers as D
from semantic_bridge import field_sales_kaynak as FK
from semantic_bridge import provenance as P

F_SERI = ("12 ay serisi (Logo aylık, iki yıl kopyası cari koduyla toplanır): satış = Σ LINENET (7, 8, 9), iade = Σ LINENET "
          "(2, 3), net = satış − iade, iade oranı = iade ÷ satış, düzensizlik = aylık satışın değişim katsayısı (std ÷ ortalama), "
          "aktif ay = satışı olan ay sayısı, büyüme = son 6 ay net ÷ önceki 6 ay net − 1, tahsilat süresi (yaklaşık) = bakiye ÷ "
          "(12 ay net ÷ 365).")
F_PAY = "Pay = carinin 12 ay net alımı ÷ kapsamdaki bütün carilerin 12 ay net alımı (anahtar hesap ayrımında kullanılır)."


def _skor_text(rule: dict[str, Any]) -> str:
    w = rule.get("agirliklar") or {}
    e = rule.get("esikler") or {}
    lab = {k: lab for k, lab, _ in D.COMPONENTS}
    parts = "; ".join(f"{lab[k]} {w.get(k, 0)} — {h}" for k, _l, h in D.COMPONENTS)
    st, an = e.get("standart") or {}, e.get("anahtar") or {}
    return (f"Risk skoru (kural sürüm {rule.get('surum')}) = Σ ağırlık × bileşen (0–1): {parts}. Segment: standart grupta "
            f"A < {st.get('A')}, B < {st.get('B')}, C < {st.get('C')}, üstü D; anahtar hesapta A < {an.get('A')}, B < {an.get('B')}, "
            f"C < {an.get('C')}. Eğilim: bugünkü skor − 30 gün önceki girdinin bugünkü kuralla skoru, ±{e.get('egilimEsik')} "
            "puandan büyükse kötüleşiyor/iyileşiyor. Önceki segment = önceki turun girdisi bugünkü kuralla. Hareketsiz cari "
            "(bakiye yok, 12 ayda satış yok) segmentsiz. Rakam modelden gelmez.")


def _limit_text(rule: dict[str, Any]) -> str:
    L = rule.get("limit") or {}
    return (f"Limit önerisi (kural sürüm {rule.get('surum')}): D segmenti, limit girilmiş ve risk limitin altında → limit mevcut "
            f"riske indirilir; A segmenti, doluluk ≥ %{round(float(L.get('artisDoluluk') or 0) * 100)} ve son 6 ay önceki 6 "
            f"aydan küçük değil → %{round(float(L.get('artisOrani') or 0) * 100)} artırılır; A/B segmenti, CRM'de limit yok ve "
            f"12 ayda net alım var → aylık ortalama net alım × {L.get('yeniLimitAy')} ay. Tutar {L.get('yuvarlama')} ₺ adıma "
            "yuvarlanır. Onaylanan öneri CRM'e insan eliyle işlenir.")


class _Ctx(FK._Ctx):
    def __init__(self, engine: Any, tenant: str):  # noqa: D107 — M30 bağlamı, bayi tur kaydıyla
        self.engine, self.tenant = engine, tenant
        self.run = D.meta_get(engine, tenant, "run")
        self.k = P.Kaynaklar(data_end=self.run.get("dataEnd"), as_of=self.run.get("gun"))
        self._gece = None
        self.gun = D.latest_day(engine, tenant)
        self._rule: Optional[dict[str, Any]] = None

    def gece(self) -> dict[str, list[str]]:
        if self._gece is None:
            self._gece = self._add("bayi.gece", self.run.get("sorgular") or [],
                                   "Günlük turda çalıştı; skor satırlarını ve 12 ay serisini bu okuma doldurdu.")
        return self._gece

    def rule(self) -> dict[str, Any]:
        if self._rule is None:
            self._rule = D.rule_body(D.active_rule(self.engine, self.tenant))
        return self._rule

    def kural(self) -> str:
        return self.portal("bayi.kural", "Yürürlükteki risk kuralı", D.rules_stmt(self.tenant, "yururlukte"),
                           "Ağırlık, eşik, kapsam ve limit kuralı; elle girilir, iki gözle yürürlüğe girer.")

    def skorlar(self, bmt: Optional[str] = None, code: Optional[str] = None, gun: Optional[str] = None,
                sid: str = "bayi.skorlar") -> str:
        return self.portal(sid, "Günlük skor satırları", D.scores_stmt(self.tenant, gun or self.gun, bmt, code),
                           "Cari başına bakiye/yaşlandırma, 12 ay alım, çek, CRM risk ve limit, skor, segment, eğilim; "
                           "günlük turda yazılır.",
                           origin=self.g("crm.kullanicilar", "crm.cariler", "crm.riskli_siparis", "crm.cari_bayrak",
                                         "logo.donem", "logo.verisonu", "logo.cariler", "logo.yaslandirma", "logo.cek",
                                         "logo.odeme", "logo.aylik_satis", "logo.aylik_odeme"))

    def tur_(self) -> str:
        return self.portal("bayi.tur", "Günlük tur kaydı", D.meta_stmt(self.tenant, "run"),
                           "Tur özeti: kapsamdaki cari, atanmış, hareketsiz, kural sürümü, veri sonu ve o turda çalışan "
                           "okuma sorguları.", origin=self.g("logo.donem", "logo.verisonu", "logo.cariler", "crm.cariler"))

    def skor_h(self, sc: str) -> str:
        return self.h("skor", _skor_text(self.rule()), [sc, self.kural()])

    def row_fields(self, prefix: str, sc: str) -> dict[str, str]:
        """`dealers.dealer_row` biçimindeki satır."""
        yas = self.h("yaslandirma", FK.F_YASLANDIRMA, [sc] + self.g("logo.yaslandirma"))
        seri = self.h("seri", F_SERI, [sc] + self.g("logo.aylik_satis", "logo.aylik_odeme"))
        rsk = self.h("risk", FK.F_RISK, [sc] + self.g("crm.cariler", "crm.riskli_siparis", "crm.cari_bayrak"))
        cek = self.h("cek", FK.F_CEK, [sc] + self.g("logo.cek"))
        skor = self.skor_h(sc)
        p = f"{prefix}." if prefix else ""
        out = {f"{p}bakiye": yas, f"{p}vadesiGecmis": yas, f"{p}k90": yas, f"{p}net12": seri, f"{p}iadeOrani": seri,
               f"{p}riskDoluluk": rsk, f"{p}siparisRiskte": rsk, f"{p}cekOlay": cek, f"{p}skor": skor, f"{p}skor30": skor,
               f"{p}neden": skor}
        return {prefix: sc, **out} if prefix else out


def _ok(x: _Ctx) -> None:
    if not x.run.get("sorgular"):
        raise P.ProvenanceError("Günlük turun çalışan sorguları kayıtlı değil (bir sonraki turdan sonra görünür).")


# ------------------------------------------------------------------ uçlar


def for_meta(engine: Any, tenant: str, user: str, out: dict[str, Any]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant)
    x.k.alanlar({"me": x.skorlar(bmt=user, sid="bayi.skorlar.benim"), "rule": x.kural(), "run": x.tur_(),
                 "bmts": x.h("temsilci_cari", "Temsilci başına cari = günün skor satırlarında temsilciye atanmış cari sayısı.",
                             [x.skorlar()])})
    return x.k


def for_summary(engine: Any, tenant: str, owner: Optional[str], g30: Optional[str], out: dict[str, Any]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant)
    _ok(x)
    sc = x.skorlar(owner)
    pano = x.h("pano", "Pano: cari = günün skor satırları (kapsam); aktif = hareketsiz olmayan; bakiye, vadesi geçmiş, "
               "kovalar, gelmemiş, plansız = satırların toplamı (FIFO, yaklaşık); kova cari = o kovada alacağı olan cari "
               "sayısı; ilk 10 cari payı = en büyük 10 pozitif bakiyenin toplam pozitif bakiyeye payı; riske takılı sipariş = "
               "Σ CRM riskte sipariş; sorunlu = CRM'de «Sorunlu Müşteri»; çek olaylı cari = 12 ayda karşılıksız ya da protesto "
               "olan cari sayısı. " + FK.F_YASLANDIRMA, [sc] + x.g("logo.yaslandirma", "crm.cari_bayrak", "logo.cek"))
    f = {k: pano for k in ("cari", "aktif", "hareketsiz", "bakiye", "vadesiGecmis", "kovalar", "kovaCari", "plansiz",
                           "gelmemis", "yogunlasma10", "siparisRiskte", "sorunlu", "cekOlayCari")}
    f["segment"] = x.skor_h(sc)
    if g30:
        sc30 = x.skorlar(owner, gun=g30, sid="bayi.skorlar.30g")
        f["segment30"] = x.h("segment30", "30 gün önceki dağılım = o günün ham girdileri bugünkü kuralla yeniden puanlanır "
                             "(kural değişince herkes birden kötüleşmiş görünmesin). " + _skor_text(x.rule()), [sc30, x.kural()])
    f.update(x.row_fields("kotulesenler[]", sc))
    f.update(x.row_fields("egilimKotu[]", sc))
    f["limitBekleyen"] = x.portal("bayi.oneri.bekleyen", "Onay bekleyen limit önerileri", D.proposals_stmt(tenant, "oneri"),
                                  "Kuraldan çıkan öneriler; satış müdürü onaylar.")
    f["limitBekleyen[].onerilen"] = x.h("limit", _limit_text(x.rule()), [f["limitBekleyen"], sc, x.kural()])
    x.k.alanlar(f)
    return x.k


def for_list(engine: Any, tenant: str, owner: Optional[str], out: dict[str, Any]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant)
    _ok(x)
    sc = x.skorlar(owner)
    f = x.row_fields("items[]", sc)
    f["count"] = x.h("liste", "Listede = süzgeçten (segment, kanal, il, temsilci, arama, grup, eğilim, durum) geçen cari sayısı; "
                     "sayfa sayfa gelir (toplam her zaman yazılır); vadesi geçmiş toplam = süzgeçteki carilerin toplamı (FIFO, "
                     "yaklaşık).", [sc])
    f["vadesiGecmis"] = f["count"]
    x.k.alanlar(f)
    return x.k


def for_limits(engine: Any, tenant: str, out: dict[str, Any], durum: str, code: str) -> P.Kaynaklar:
    x = _Ctx(engine, tenant)
    pr = x.portal("bayi.oneri", "Limit önerileri", D.proposals_stmt(tenant, durum, code),
                  "Kuraldan çıkan öneri; mevcut limit/risk öneri anında CRM'den (günlük tur) kopyalanır.",
                  origin=x.g("crm.cariler", "crm.cari_bayrak"))
    x.k.alanlar({"items": pr, "items[].onerilen": x.h("limit", _limit_text(x.rule()), [pr, x.kural()]),
                 "count": pr})
    return x.k


def for_rules(engine: Any, tenant: str, out: dict[str, Any]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant)
    x.k.alanlar({"items": x.portal("bayi.kurallar", "Risk kuralı sürümleri", D.rules_stmt(tenant),
                                   "Ağırlık, eşik, kapsam ve limit kuralı; elle girilir, iki gözle yürürlüğe girer.")})
    return x.k


def for_preview(engine: Any, tenant: str, rid: str, owner: Optional[str], out: dict[str, Any]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant)
    sc = x.skorlar(owner)
    import sqlalchemy as sa

    taslak = x.portal("bayi.kural.taslak", "Önizlenen kural sürümü", sa.select(D.RULES).where(
        D.RULES.c.tenant_id == tenant, D.RULES.c.id == rid), "Taslak kural (elle girilir).")
    h = x.h("onizleme", "Önizleme: bugünkü skor satırlarının ham girdileri taslak kuralla yeniden puanlanır (Logo'ya gidilmez); "
            "mevcut = bugünkü segment dağılımı, taslak = taslak kuralla dağılım, değişen = segmenti değişen cariler (eski/yeni "
            "skor), kapsam dışı = taslağın kapsamına girmeyen cari sayısı.", [sc, taslak, x.kural()])
    x.k.alanlar({"mevcut": h, "taslak": h, "degisen": h, "kapsamDisi": h})
    return x.k


def for_actions(engine: Any, tenant: str, out: dict[str, Any], code: str = "", durum: str = "", sahip: str = "") -> P.Kaynaklar:
    x = _Ctx(engine, tenant)
    a = x.portal("bayi.aksiyon", "Bayi aksiyonları", D.actions_stmt(tenant, code, durum, sahip), "Elle girilir.")
    x.k.alanlar({"items": a, "count": a})
    return x.k


def for_card(engine: Any, tenant: str, code: str, out: dict[str, Any]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant)
    _ok(x)
    sc = x.skorlar(code=code, sid="bayi.skorlar.cari")
    f = x.row_fields("", sc)
    yas = x.h("yaslandirma", FK.F_YASLANDIRMA, [sc] + x.g("logo.yaslandirma"))
    seri = x.h("seri", F_SERI, [sc] + x.g("logo.aylik_satis", "logo.aylik_odeme"))
    rsk = x.h("risk", FK.F_RISK, [sc] + x.g("crm.cariler", "crm.riskli_siparis", "crm.cari_bayrak"))
    cek = x.h("cek", FK.F_CEK, [sc] + x.g("logo.cek"))
    f.update({"bilesenler": x.skor_h(sc), "kovalar": yas, "gelmemis": yas, "plansiz": yas,
              "satis12": seri, "iade12": seri, "buyume6": seri, "dso": seri, "duzensizlik": seri, "aktifAy": seri,
              "odeme12": x.h("odeme", FK.F_ODEME, [sc] + x.g("logo.odeme")), "karsiliksiz": cek, "protesto": cek,
              "cekTutar": cek, "limit": rsk, "siparisRisktetutar": rsk, "pay": x.h("pay", F_PAY, [sc]),
              "seri": x.portal("bayi.seri", "12 ay aylık seri", D.series_stmt(tenant, code), "Günlük turda yazılır.",
                               origin=x.g("logo.aylik_satis", "logo.aylik_odeme")),
              "oneriler": x.portal("bayi.oneri.cari", "Limit önerileri", D.proposals_stmt(tenant, code=code),
                                   "Kuraldan çıkan öneri."),
              "aksiyonlar": x.portal("bayi.aksiyon.cari", "Bayi aksiyonları", D.actions_stmt(tenant, code), "Elle girilir."),
              "ziyaretler": x.ziyaret("bayi.ziyaret", hedef=code, tur="cari")})
    f["oneriler[].onerilen"] = x.h("limit", _limit_text(x.rule()), [f["oneriler"], sc, x.kural()])
    f["ziyaretSayisi"] = f["ziyaretler"]
    x.k.alanlar(f)
    return x.k


def for_aging(engine: Any, tenant: str, code: str, out: dict[str, Any]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant)
    _ok(x)
    sc = x.skorlar(code=code, sid="bayi.skorlar.cari")
    yas = x.h("yaslandirma", FK.F_YASLANDIRMA, [sc] + x.g("logo.yaslandirma"))
    x.k.alanlar({k: yas for k in ("bakiye", "gelmemis", "plansiz", "vadesiGecmis", "kovalar")})
    return x.k


def for_history(engine: Any, tenant: str, code: str, since: str, out: dict[str, Any], live_reads: list[dict[str, Any]]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant)
    _ok(x)
    live = x.canli(live_reads)
    f = {"skor": x.portal("bayi.gecmis", "Skor geçmişi", D.history_stmt(tenant, code, since),
                          "Gün gün skor, segment, kural sürümü, vadesi geçmiş, bakiye (günlük tur).",
                          origin=x.g("logo.yaslandirma", "logo.aylik_satis")),
         "seri": x.portal("bayi.seri", "12 ay aylık seri", D.series_stmt(tenant, code), "Günlük turda yazılır.",
                          origin=x.g("logo.aylik_satis", "logo.aylik_odeme"))}
    rg = live.get("crm.risk_gecmisi") or live.get("crm.siparisler") or []
    if rg:
        f["crmRisk"] = rg[0]
    x.k.alanlar(f)
    return x.k


def for_brief(engine: Any, tenant: str, code: str, out: dict[str, Any]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant)
    _ok(x)
    sc = x.skorlar(code=code, sid="bayi.skorlar.cari")
    x.k.alanlar({"metin": x.h("brif", "Risk brifi Zeki AI'ın ya da kuralın yazdığı metindir; her sayı olgulardan (bakiye, vadesi "
                              "geçmiş, 90+ gün, son ödeme, 12 ay net alım ve iade, çek olayı, CRM limit/risk, riskte sipariş, "
                              "eğilim, son görüşme notu) gelir, olgularda olmayan sayı varsa kural brifi gösterilir.",
                              [sc, x.ziyaret("bayi.ziyaret", hedef=code, tur="cari")])})
    return x.k


def for_notes(engine: Any, tenant: str, code: str, out: dict[str, Any]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant)
    z = x.ziyaret("bayi.ziyaret", hedef=code, tur="cari")
    x.k.alanlar({"items": z, "count": z})
    return x.k


NOT_RAKAM = ("page", "size", "kural", "kuralSurum", "calendar.year", "items[].kuralSurum", "oneriler[].kuralSurum",
             "limitBekleyen[].kuralSurum", "skor[].kural")

