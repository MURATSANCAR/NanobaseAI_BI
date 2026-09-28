"""DYK kurul göstergelerinin sağlayıcıları: diğer modüllerin onaylı çıktıları köprü içinden okunur.

**Yeniden hesap yok.** Her sağlayıcı ilgili modülün kendi hesap işlevini ya da hazır tablosunu çağırır (HTTP değil,
aynı süreç): M45 `finance.summary`, M46 `budget.tracking` / `budget.deviations`, M47 `risk.summary` / `risk.reports`,
M59 `dealers.summary` (günlük skor tablosu), M50 `model_quality.bi_row` (karne satırı), M48 `it_ops.status`, M6
`editorial.summary` (CRM sözleşme sayacı), M39 `pazar.approved_brief`. Böylece kurul üyesinin kaynak sayfaların yetkisine
ihtiyacı olmaz; kurul yalnız özeti görür, kaynak ekrana bağlantı yalnız o sayfanın yetkisi olana açılır (ön yüz).

Sağlayıcı sözleşmesi: `PROVIDERS[ad](ctx) -> {gösterge_kodu: sonuç}`; bir sağlayıcı birden çok göstergeyi tek çağrıda
doldurur (ör. M45 özet kartları). Sonuç alanları:
`durum` ok | kaynak_yok | hata, `deger`, `hedef`, `onceki`, `oncekiEtiket`, `veriSonGunu` (ISO gün), `kaynak` (ekranda
okunan modül adı), `ekran` (kaynak rota), `renk` (kaynak modülün kendi eşiğiyle verdiği renk; yoksa None), `not`,
`ayrinti` (küçük sözlük). «Kaynak yok» göstergesi sayı taşımaz (`deger` None) ve renksizdir.

Sağlayıcısı olmayan gösterge (`saglayici` None) her ölçümde `kaynak_yok` olur: modül geldikçe buraya bir sağlayıcı
eklenir, kataloğun `saglayici` alanı güncellenir.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Optional

log = logging.getLogger("semantic.kurul.sources")


@dataclass
class Ctx:
    engine: Any
    tenant: str
    conf: Callable[..., str]
    today: date
    datasource: Callable[[], str] = lambda: "default"
    #: CRM sözleşme sayacı için (şema, run_sql). Yoksa M6 göstergesi «kaynak yok».
    crm: Optional[Callable[[], tuple[str, Callable[[str], dict[str, Any]]]]] = None
    memo: dict[str, Any] = field(default_factory=dict)


# ------------------------------------------------------------------ bölümler ve hazır katalog

#: Panelin bölüm sırası. Gösterge kataloğundaki `bolum` bu anahtarlardan biridir.
BOLUMLER: dict[str, str] = {
    "finans": "Finans ve bütçe",
    "satis": "Satış ve bayi",
    "editorya": "Yayın ve editörya",
    "stok": "Stok ve üretim",
    "pazarlama": "Pazarlama",
    "risk": "Risk ve uyum",
    "ik": "İnsan kaynakları",
    "zeki": "ZEKİ projesi",
}

#: Hazır gösterge tanımları. Eşikler **boş** gelir: eşik gösterge sahibinin/yöneticinin kararıdır (`PATCH indicators`);
#: eşik yokken renk yalnız kaynak modülün kendi kuralından gelir (bütçe durumu, sistem durumu tonu, bütçe kalemi aşımı).
LIBRARY: list[dict[str, Any]] = [
    # Finans (M45) — Logo muhasebe ve faturalı satış satırının M45 anlık görüntüsü.
    {"kod": "net_satis", "bolum": "finans", "ad": "Net satış (yıl başından)", "saglayici": "m45", "birim": "tl", "yon": "azalis_kotu",
     "aciklama": "Faturalı satış satırları, satır iskontosu ve iade düşülmüş; karşılaştırma geçen yılın aynı dönemi.", "sira": 10},
    {"kod": "brut_kar_marji", "bolum": "finans", "ad": "Brüt kâr marjı (maliyeti işlenmiş satış)", "saglayici": "m45",
     "birim": "yuzde", "yon": "azalis_kotu",
     "aciklama": "Maliyeti Logo'da işlenmiş satırlarda (net − maliyet) ÷ net; maliyetsiz satış marja katılmaz.", "sira": 20},
    {"kod": "faaliyet_gideri", "bolum": "finans", "ad": "Faaliyet giderleri (yıl başından)", "saglayici": "m45", "birim": "tl",
     "yon": "artis_kotu", "aciklama": "Muhasebe hesap eşlemesiyle Ar-Ge, pazarlama-satış-dağıtım ve genel yönetim giderleri.", "sira": 30},
    {"kod": "kasa_banka", "bolum": "finans", "ad": "Kasa ve banka", "saglayici": "m45", "birim": "tl", "yon": "azalis_kotu",
     "aciklama": "Veri son günü itibarıyla 100 + 102 hesap bakiyesi.", "sira": 40},
    {"kod": "vadesi_gecmis_alacak", "bolum": "finans", "ad": "Vadesi geçmiş alacak", "saglayici": "m45", "birim": "tl",
     "yon": "artis_kotu", "aciklama": "13 haftalık nakit tablosunun vade dağılımı (FIFO yaklaşımı).", "sira": 50},
    {"kod": "butce_satis", "bolum": "finans", "ad": "Satış hedefine göre gerçekleşme", "saglayici": "m46", "birim": "yuzde",
     "yon": "azalis_kotu", "aciklama": "Yürürlükteki bütçe planında bugüne beklenen ciroya göre gerçekleşen (renk bütçe modülünün eşiği).",
     "sira": 60},
    {"kod": "butce_gider", "bolum": "finans", "ad": "Gider bütçesi kullanımı", "saglayici": "m46", "birim": "yuzde",
     "yon": "artis_kotu", "aciklama": "Departman bütçesinin döneme düşen payına göre gerçekleşen gider.", "sira": 70},
    {"kod": "butce_sapma", "bolum": "finans", "ad": "Açık bütçe sapması", "saglayici": "m46", "birim": "adet", "yon": "artis_kotu",
     "aciklama": "Bütçe modülünün açık sapma uyarıları (satış ve gider).", "sira": 80},
    # Satış ve bayi (M59) — günlük bayi risk turu.
    {"kod": "bayi_vadesi_gecmis", "bolum": "satis", "ad": "Bayi alacağında vadesi geçmiş", "saglayici": "m59", "birim": "tl",
     "yon": "artis_kotu", "aciklama": "Bayi ve kitapçı carilerinde vadesi geçmiş bakiye; karşılaştırma ~30 gün önceki gün.", "sira": 10},
    {"kod": "bayi_yogunlasma", "bolum": "satis", "ad": "Alacakta ilk 10 cari payı", "saglayici": "m59", "birim": "yuzde",
     "yon": "artis_kotu", "aciklama": "Pozitif bakiyeli carilerde en büyük 10 carinin payı.", "sira": 20},
    {"kod": "bayi_d_segment", "bolum": "satis", "ad": "Yüksek riskli (D) bayi", "saglayici": "m59", "birim": "adet",
     "yon": "artis_kotu", "aciklama": "Günlük skorda D segmentindeki etkin cari sayısı; karşılaştırma ~30 gün önce (bugünkü kuralla).",
     "sira": 30},
    # Yayın ve editörya (M6).
    {"kod": "sozlesme_bitecek", "bolum": "editorya", "ad": "Süresi yaklaşan sözleşme", "saglayici": "m6", "birim": "adet",
     "yon": "artis_kotu", "aciklama": "CRM'de yürürlükteki ve belirlenen gün içinde biten yazar sözleşmeleri.", "sira": 10},
    # Henüz bağlanmamış alanlar: gri durur.
    {"kod": "stok_riski", "bolum": "stok", "ad": "Stok riski", "saglayici": None, "birim": "adet", "yon": "artis_kotu",
     "aciklama": "Bitecek ve fazla stok özetinin kurul sağlayıcısı sonraki sürümde bağlanacak.", "sira": 10},
    {"kod": "pazarlama_plani", "bolum": "pazarlama", "ad": "Pazarlama planı gerçekleşmesi", "saglayici": None, "birim": "yuzde",
     "yon": "azalis_kotu", "aciklama": "Pazarlama planlarının kurul sağlayıcısı sonraki sürümde bağlanacak.", "sira": 10},
    {"kod": "ik_saglik", "bolum": "ik", "ad": "İK ve organizasyon sağlığı", "saglayici": None, "birim": "adet", "yon": "artis_kotu",
     "aciklama": "İnsan kaynakları modüllerinin kurul özeti sonraki sürümde bağlanacak.", "sira": 10},
    # Risk ve uyum (M47).
    {"kod": "risk_kritik", "bolum": "risk", "ad": "Kritik bantta risk", "saglayici": "m47", "birim": "adet", "yon": "artis_kotu",
     "aciklama": "Risk kaydında canlı ve olasılık × etki puanı kritik bantta olan riskler.", "sira": 10},
    {"kod": "risk_kirmizi_gosterge", "bolum": "risk", "ad": "Kırmızı risk göstergesi", "saglayici": "m47", "birim": "adet",
     "yon": "artis_kotu", "aciklama": "Risk göstergelerinden (KRI) kırmızı eşiği aşanlar.", "sira": 20},
    {"kod": "risk_geciken_aksiyon", "bolum": "risk", "ad": "Geciken risk aksiyonu", "saglayici": "m47", "birim": "adet",
     "yon": "artis_kotu", "aciklama": "Termini geçmiş, açık risk aksiyonları.", "sira": 30},
    # ZEKİ projesi (M50, M48).
    {"kod": "zeki_cevaplama", "bolum": "zeki", "ad": "Zeki AI cevaplama oranı", "saglayici": "m50", "birim": "yuzde",
     "yon": "azalis_kotu", "aciklama": "Son pencerede sorulan sorulardan veriyle cevaplananların payı (Zeki AI kalitesi karnesi).",
     "sira": 10},
    {"kod": "zeki_saglam", "bolum": "zeki", "ad": "Doğrulanmış sorularda sağlam", "saglayici": "m50", "birim": "yuzde",
     "yon": "azalis_kotu", "aciklama": "Son kalite koşusunda referansla doğrulanmış soruların sağlam kalan payı.", "sira": 20},
    {"kod": "sistem_acik_olay", "bolum": "zeki", "ad": "Açık sistem olayı", "saglayici": "m48", "birim": "adet", "yon": "artis_kotu",
     "aciklama": "Sistem durumu ekranındaki açık kopma ve veri eskiliği olayları (renk sistem durumunun kendi tonu).", "sira": 30},
    {"kod": "logo_veri_gecikmesi", "bolum": "zeki", "ad": "Logo verisinin yaşı", "saglayici": "m48", "birim": "gun",
     "yon": "artis_kotu", "aciklama": "Bugün ile Logo'daki son fatura günü arasındaki gün.", "sira": 40},
]
BY_CODE: dict[str, dict[str, Any]] = {g["kod"]: g for g in LIBRARY}

SOURCE_NAMES: dict[str, tuple[str, str]] = {  # sağlayıcı → (ekranda kaynak adı, kaynak ekran rotası)
    "m45": ("Finansal raporlar (M45)", "/finansal-raporlar"),
    "m46": ("Bütçe ve hedefler (M46)", "/butce?sekme=izleme"),
    "m47": ("Risk ve uyum (M47)", "/risk-uyum"),
    "m59": ("Bayi riski (M59)", "/bayi-risk"),
    "m6": ("Telif ve sözleşme (M6)", "/telif-sozlesme"),
    "m50": ("Zeki AI kalitesi (M50)", "/zeki-kalite"),
    "m48": ("Sistem durumu (M48)", "/sistem-durumu"),
}


class SourceError(RuntimeError):
    pass


# ------------------------------------------------------------------ sonuç yardımcıları


def _ok(prov: str, deger: Optional[float], **kw: Any) -> dict[str, Any]:
    name, screen = SOURCE_NAMES.get(prov, (prov, None))
    return {"durum": "ok", "deger": None if deger is None else float(deger), "hedef": kw.get("hedef"), "onceki": kw.get("onceki"),
            "oncekiEtiket": kw.get("oncekiEtiket"), "veriSonGunu": kw.get("veriSonGunu"), "kaynak": name, "ekran": screen,
            "renk": kw.get("renk"), "not": kw.get("not"), "ayrinti": kw.get("ayrinti") or {}}


def gray(prov: Optional[str], note: str) -> dict[str, Any]:
    name, screen = SOURCE_NAMES.get(prov or "", (None, None))
    return {"durum": "kaynak_yok", "deger": None, "hedef": None, "onceki": None, "oncekiEtiket": None, "veriSonGunu": None,
            "kaynak": name, "ekran": screen, "renk": None, "not": note, "ayrinti": {}}


def failed(prov: Optional[str], message: str) -> dict[str, Any]:
    out = gray(prov, message)
    out["durum"] = "hata"
    return out


def _pct(v: Optional[float]) -> Optional[float]:
    return None if v is None else round(float(v) * 100, 4)


def _day(v: Any) -> Optional[str]:
    if v in (None, ""):
        return None
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    return str(v)[:10]


def _codes(prov: str) -> list[str]:
    return [g["kod"] for g in LIBRARY if g["saglayici"] == prov]


def _all(prov: str, res: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {k: dict(res) for k in _codes(prov)}


# ------------------------------------------------------------------ M45 Finansal raporlar


def m45(ctx: Ctx) -> dict[str, dict[str, Any]]:
    from semantic_bridge import finance as F

    F.ensure(ctx.engine)
    s = F.summary(ctx.engine, ctx.tenant, with_cash=True)
    if not s.get("hazir"):
        return _all("m45", gray("m45", "Finansal raporların Logo okuması henüz yapılmadı."))
    end = s.get("veriSonu")
    cards = {c["id"]: c for c in s.get("cards") or []}
    out: dict[str, dict[str, Any]] = {}

    def card(cid: str, kod: str, missing: str, *, pct: bool = False) -> None:
        c = cards.get(cid)
        if not c or (c.get("value") is None and c.get("ratio") is None):
            out[kod] = gray("m45", missing)
            return
        val = _pct(c.get("ratio")) if pct else c.get("value")
        if val is None:
            out[kod] = gray("m45", missing)
            return
        out[kod] = _ok("m45", val, onceki=c.get("compare") if not pct else None, oncekiEtiket=c.get("compareLabel") if not pct else None,
                       veriSonGunu=end, ayrinti={"yaklasik": bool(c.get("yaklasik")), "aciklama": c.get("note"),
                                                          "donem": s.get("donem")})
        if c.get("yaklasik"):
            out[kod]["not"] = "Yaklaşık: " + (c.get("note") or "")

    card("net-satis", "net_satis", "Net satış kartı henüz hazır değil.")
    card("brut-kar", "brut_kar_marji", "Maliyeti işlenmiş satış yok; marj hesaplanamadı.", pct=True)
    card("faaliyet", "faaliyet_gideri", "Bu yılın muhasebe fişleri okunmadı.")
    card("nakit", "kasa_banka", "Kasa ve banka bakiyesi okunmadı.")
    card("vadesi-gecmis", "vadesi_gecmis_alacak", "13 haftalık nakit tablosu henüz hazırlanmadı.")
    # M45'in CFO onaylı son aylık yorumu (Zeki AI taslağı + insan onayı) net satış göstergesinin ayrıntısına eklenir.
    try:
        yorum = F.approved_comment(ctx.engine, ctx.tenant)
    except Exception as e:  # noqa: BLE001 — yorum okunamazsa gösterge düşmez
        log.info("kurul: M45 aylık yorumu okunamadı: %s", e)
        yorum = None
    if yorum and isinstance((out.get("net_satis") or {}).get("ayrinti"), dict):
        out["net_satis"]["ayrinti"]["aylikYorum"] = yorum
    return out


# ------------------------------------------------------------------ M46 Bütçe ve hedefler

_BUDGET_COLOR = {"iyi": "yesil", "izle": "sari", "sapma": "kirmizi"}


def m46(ctx: Ctx) -> dict[str, dict[str, Any]]:
    from semantic_bridge import budget as B

    B.ensure(ctx.engine)
    end = B.data_end(ctx.engine)
    year = end.year if end else ctx.today.year
    tr = B.tracking(ctx.engine, ctx.tenant, year)
    if not tr.get("plan"):
        return _all("m46", gray("m46", f"{year} için yürürlükte (onaylı) bütçe planı yok."))
    if not tr.get("asof") or not tr.get("sirket"):
        return _all("m46", gray("m46", "Bütçe gerçekleşmesi henüz Logo'dan okunmadı."))
    asof = _day(tr["asof"])
    sirket = tr["sirket"]
    out: dict[str, dict[str, Any]] = {}
    if sirket.get("oran") is None:
        out["butce_satis"] = gray("m46", "Bugüne beklenen ciro sıfır; oran hesaplanmadı.")
    else:
        out["butce_satis"] = _ok("m46", _pct(sirket["oran"]), hedef=100.0, veriSonGunu=asof, renk=_BUDGET_COLOR.get(sirket.get("durum")),
                                 ayrinti={"gercekCiro": sirket.get("gercekCiro"), "beklenenCiro": sirket.get("beklenenCiro"),
                                          "hedefCiro": sirket.get("hedefCiro"), "esik": tr.get("esik"), "durum": sirket.get("durum"),
                                          "plan": (tr.get("plan") or {}).get("title"), "yil": year})
    gider = tr.get("gider") or {}
    if gider.get("kullanim") is None:
        out["butce_gider"] = gray("m46", "Departman bütçesinin döneme düşen payı yok.")
    else:
        renk = "kirmizi" if gider.get("asim") else "sari" if gider.get("yaklasti") else "yesil"
        out["butce_gider"] = _ok("m46", _pct(gider["kullanim"]), hedef=100.0, veriSonGunu=asof, renk=renk,
                                 ayrinti={"gercek": gider.get("gercek"), "butceDonem": gider.get("butceDonem"),
                                          "asanKalem": gider.get("asim"), "yaklasanKalem": gider.get("yaklasti")})
    dev = B.deviations(ctx.engine, ctx.tenant, year, status="acik")
    out["butce_sapma"] = _ok("m46", float(dev.get("total") or 0), veriSonGunu=asof,
                             ayrinti={"ilk": [{"ad": a.get("label"), "tur": a.get("kind"), "oran": a.get("ratio")}
                                             for a in (dev.get("items") or [])[:5]]})
    return out


# ------------------------------------------------------------------ M47 Risk ve uyum


def _risk_summary(ctx: Ctx) -> dict[str, Any]:
    if "m47" not in ctx.memo:
        from semantic_bridge import risk as R
        from semantic_bridge import risk_sources as RS

        R.ensure(ctx.engine)
        ind = R.indicators(ctx.engine, ctx.tenant, set(RS.BY_CODE))
        ctx.memo["m47"] = (R.summary(ctx.engine, ctx.tenant, "", True, ind), ind)
    return ctx.memo["m47"]


def m47(ctx: Ctx) -> dict[str, dict[str, Any]]:
    sm, _ind = _risk_summary(ctx)
    n = sm.get("sayilar") or {}
    today = ctx.today.isoformat()
    out: dict[str, dict[str, Any]] = {}
    if not n.get("canli") and not sm.get("ilk10"):
        out["risk_kritik"] = gray("m47", "Risk kaydında canlı risk yok; kayıt kullanılmaya başlanınca dolar.")
        out["risk_geciken_aksiyon"] = gray("m47", "Risk kaydında canlı risk yok.")
    else:
        out["risk_kritik"] = _ok("m47", float(n.get("kritik") or 0), veriSonGunu=today,
                                 ayrinti={"canli": n.get("canli"), "puansiz": sm.get("puansiz")})
        out["risk_geciken_aksiyon"] = _ok("m47", float(len(sm.get("gecikenAksiyon") or [])), veriSonGunu=today,
                                          ayrinti={"yaklasan": len(sm.get("yaklasanAksiyon") or [])})
    if not n.get("gosterge"):
        out["risk_kirmizi_gosterge"] = gray("m47", "Risk göstergesi tanımlı değil.")
    else:
        out["risk_kirmizi_gosterge"] = _ok("m47", float(n.get("kirmizi") or 0), veriSonGunu=today,
                                           ayrinti={"gosterge": n.get("gosterge"), "esiksiz": n.get("esiksiz"),
                                                    "kirmizi": [g.get("ad") for g in sm.get("kirmiziGosterge") or []]})
    return out


def risk_numbers(ctx: Ctx) -> Optional[dict[str, Any]]:
    """Paket için risk sayıları (kayıt hiç kullanılmıyorsa None)."""
    try:
        sm, _ = _risk_summary(ctx)
    except Exception as e:  # noqa: BLE001
        log.warning("kurul: risk özeti okunamadı: %s", e)
        return None
    return sm.get("sayilar")


def risk_briefing(ctx: Ctx) -> Optional[dict[str, Any]]:
    """M47'nin en son **onaylı** çeyreklik brifingi (taslak kurula gitmez)."""
    from semantic_bridge import risk as R

    R.ensure(ctx.engine)
    for r in R.reports(ctx.engine, ctx.tenant)["items"]:
        if r.get("durum") == "onayli":
            d = R.report(ctx.engine, ctx.tenant, r["id"])
            return {"id": d["id"], "donem": d["donem"], "metin": d.get("metin"), "onaylayan": d.get("onaylayan"),
                    "onayZamani": d.get("onayZamani"), "girdiHash": d.get("girdiHash")}
    return None


# ------------------------------------------------------------------ M39 Pazar araştırması


def market_brief(ctx: Ctx) -> Optional[dict[str, Any]]:
    """M39'un son onaylı aylık pazar özeti (onaylayan kurul paketine gönderdi)."""
    from semantic_bridge import pazar as P

    P.ensure(ctx.engine)
    b = P.approved_brief(ctx.engine, ctx.tenant)
    if not b:
        return None
    return {"id": b["id"], "donem": b["donem"], "donemAd": b.get("donemAd"), "metin": b.get("taslak"),
            "onaylayan": b.get("onaylayan"), "onaylandiAt": b.get("onaylandiAt"),
            "kaynakSayisi": len(b.get("kaynaklar") or [])}


# ------------------------------------------------------------------ M59 Bayi riski


def m59(ctx: Ctx) -> dict[str, dict[str, Any]]:
    from semantic_bridge import dealers as D

    D.ensure(ctx.engine)
    gun = D.latest_day(ctx.engine, ctx.tenant)
    if not gun:
        return _all("m59", gray("m59", "Bayi riski günlük turu henüz koşmadı."))
    rows = D.day_rows(ctx.engine, ctx.tenant, gun, None)
    rule = D.rule_body(D.active_rule(ctx.engine, ctx.tenant, D.settings_from(ctx.conf)))
    g30, _raw = D.previous_raw(ctx.engine, ctx.tenant, (date.fromisoformat(gun) - timedelta(days=30)).isoformat(), on_or_before=True)
    month_ago = D.day_rows(ctx.engine, ctx.tenant, g30, None) if g30 else []
    s = D.summary(rows, month_ago, rule)
    prev = D.summary(month_ago, [], rule) if month_ago else None
    run = D.meta_get(ctx.engine, ctx.tenant, "run") or {}
    end = _day(run.get("agingAsof") or run.get("dataEnd") or gun)
    label = f"{g30} günü" if g30 else None

    def d_count(dist: Optional[dict[str, dict[str, int]]]) -> Optional[float]:
        if not dist:
            return None
        return float(sum(int((v or {}).get("D") or 0) for v in dist.values()))

    out = {
        "bayi_vadesi_gecmis": _ok("m59", s.get("vadesiGecmis"), onceki=(prev or {}).get("vadesiGecmis"), oncekiEtiket=label,
                                  veriSonGunu=end, ayrinti={"gun": gun, "bakiye": s.get("bakiye"), "kovalar": s.get("kovalar"),
                                                            "cari": s.get("cari"), "aktif": s.get("aktif")}),
        "bayi_d_segment": _ok("m59", d_count(s.get("segment")), onceki=d_count(s.get("segment30")), oncekiEtiket=label,
                              veriSonGunu=end, ayrinti={"gun": gun, "kural": rule.get("surum"), "segment": s.get("segment")}),
    }
    if s.get("yogunlasma10") is None:
        out["bayi_yogunlasma"] = gray("m59", "Pozitif bakiyeli cari yok.")
    else:
        out["bayi_yogunlasma"] = _ok("m59", _pct(s["yogunlasma10"]),
                                     onceki=_pct((prev or {}).get("yogunlasma10")) if prev else None, oncekiEtiket=label,
                                     veriSonGunu=end, ayrinti={"gun": gun})
    return out


# ------------------------------------------------------------------ M6 Sözleşmeler (CRM)


def m6(ctx: Ctx) -> dict[str, dict[str, Any]]:
    if ctx.crm is None:
        return {"sozlesme_bitecek": gray("m6", "CRM bağlantısı bu kurulumda tanımlı değil.")}
    from semantic_bridge import editorial as E

    schema, run = ctx.crm()
    try:
        warn = int(str(ctx.conf("EDITORIAL_CONTRACT_WARN_DAYS", "60") or "60"))
    except ValueError:
        warn = 60
    s = E.summary(schema, run, warn)
    return {"sozlesme_bitecek": _ok("m6", float(s.get("expiring") or 0), veriSonGunu=ctx.today.isoformat(),
                                    ayrinti={"gun": warn, "yururlukte": s.get("active"), "yenilemede": s.get("renewal"),
                                                        "toplam": s.get("total")})}


# ------------------------------------------------------------------ M50 Zeki AI kalitesi


def m50(ctx: Ctx) -> dict[str, dict[str, Any]]:
    from semantic_bridge import model_quality as MQ
    from semantic_bridge import model_quality_sources as MS

    MQ.ensure(ctx.engine)
    try:
        days = max(1, min(3650, int(str(ctx.conf("MODEL_QUALITY_WINDOW_DAYS", "30") or "30"))))
    except ValueError:
        days = 30
    now, since = MS.window(days)
    trend_since = min(since, now - timedelta(days=28))
    runs = MS.last_finished(ctx.engine, ctx.tenant)
    row = MQ.bi_row(MS.query_rows(ctx.engine, ctx.tenant, ctx.datasource(), trend_since),
                    MS.feedback_rows(ctx.engine, ctx.tenant, trend_since), runs, now=now, since=since)
    last = _day(row.get("lastMeasured"))
    out: dict[str, dict[str, Any]] = {}
    metrics = {m["key"]: m for m in row.get("metrics") or []}
    q = metrics.get("questions", {}).get("value") or 0
    rate = metrics.get("answeredRate", {}).get("value")
    if not q or rate is None:
        out["zeki_cevaplama"] = gray("m50", f"Son {days} günde soru sorulmadı.")
    else:
        out["zeki_cevaplama"] = _ok("m50", _pct(rate), veriSonGunu=last,
                                    ayrinti={"soru": q, "gun": days, "yanlis": metrics.get("wrong", {}).get("value")})
    p = row.get("primary")
    if not p or p.get("value") is None:
        out["zeki_saglam"] = gray("m50", "Doğrulanmış soru setinin bitmiş koşusu yok.")
    else:
        out["zeki_saglam"] = _ok("m50", _pct(p["value"]), veriSonGunu=_day(p.get("at")),
                                 ayrinti={"oran": p.get("detail"), "bozulan": p.get("broken"), "duzelen": p.get("fixed")})
    return out


# ------------------------------------------------------------------ M48 Sistem durumu

_TONE_COLOR = {"ok": "yesil", "warn": "sari", "err": "kirmizi"}


def m48(ctx: Ctx) -> dict[str, dict[str, Any]]:
    from semantic_bridge import it_ops as I

    I.ensure(ctx.engine)
    st = I.status(ctx.engine, ctx.tenant, I.settings(ctx.conf))
    tone = (st.get("summary") or {}).get("tone")
    out: dict[str, dict[str, Any]] = {}
    if tone == "unknown":
        out["sistem_acik_olay"] = gray("m48", "Sistem denetimleri henüz ölçülmedi.")
    else:
        out["sistem_acik_olay"] = _ok("m48", float(len(st.get("open") or [])), veriSonGunu=ctx.today.isoformat(),
                                      renk=_TONE_COLOR.get(tone), ayrinti={"ozet": (st.get("summary") or {}).get("text")})
    ring = next((r for r in st.get("rings") or [] if r.get("id") == "logo"), None)
    end = _day((ring or {}).get("dataEnd"))
    if not end:
        out["logo_veri_gecikmesi"] = gray("m48", "Logo halkasının veri son günü henüz ölçülmedi.")
    else:
        out["logo_veri_gecikmesi"] = _ok("m48", float((ctx.today - date.fromisoformat(end)).days), veriSonGunu=end,
                                         ayrinti={"halka": (ring or {}).get("state")})
    return out


PROVIDERS: dict[str, Callable[[Ctx], dict[str, dict[str, Any]]]] = {
    "m45": m45, "m46": m46, "m47": m47, "m59": m59, "m6": m6, "m50": m50, "m48": m48,
}


def measure(ctx: Ctx, indicators: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Katalogdaki göstergelerin güncel değeri. Sağlayıcı başına bir çağrı; biri düşerse yalnız onun göstergeleri
    «hata» olur, ölçüm sürer."""
    by_prov: dict[Optional[str], list[str]] = {}
    for g in indicators:
        by_prov.setdefault(g.get("saglayici") or None, []).append(g["kod"])
    out: dict[str, dict[str, Any]] = {}
    for prov, codes in by_prov.items():
        fn = PROVIDERS.get(prov or "")
        if fn is None:
            for k in codes:
                out[k] = gray(prov, "Bu göstergenin kaynağı henüz bağlanmadı (modül ya da kurul sağlayıcısı yok).")
            continue
        try:
            res = fn(ctx)
        except Exception as e:  # noqa: BLE001 — bir modül düşerse panel düşmez
            log.warning("kurul: %s sağlayıcısı okunamadı: %s", prov, e)
            res = {k: failed(prov, f"Kaynak şu an okunamadı: {str(e)[:200]}") for k in codes}
        for k in codes:
            out[k] = res.get(k) or gray(prov, "Kaynak modül bu göstergeyi döndürmedi.")
    return out


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
