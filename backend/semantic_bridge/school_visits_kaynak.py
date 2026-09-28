"""M31 Okul tanıtım ve ziyaret: ekrandaki her rakamın sorgu bilgisi (ortak sözleşme `provenance.py`).

Okul listesi, profil, CRM ziyaretleri, siparişler, bayiler, kitaplar ve Logo stok/fiyat/bayi satışı bellekteki okumadan
gelir (`school_visits_sources.Source.read`); gösterilen SQL o okumada ÇALIŞAN metindir (şema, firma kopyası ve pencere
yerinde), satır sayısı, süre ve okuma anıyla (`snap["sorgular"]`). Portal kayıtları (ziyaret raporu, plan, bayi bağı,
katalog, bağlam yüklemesi) uçta çalışan ifadedir (`school_visits.*_stmt`). Öncelik puanı, sayaçlar ve dönem raporu
Python hesabıdır; formülü girdileriyle yazılır. Kişisel veri: SQL metni gösterilir, sonuç satırı kayda girmez.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Iterable, Optional

from semantic_bridge import kaynak_ayar as KA
from semantic_bridge import provenance as P
from semantic_bridge import school_visits as SV

TITLES = {
    "okullar": ("CRM ziyaret yerleri (okullar)", "Etkin ziyaret yerleri: öğrenci/öğretmen/derslik sayısı, kademe, tür, il/ilçe, sahip."),
    "ziyaretler": ("CRM okul ziyaretleri", "Okul ziyareti tipli bütün etkinlikler (tarih süzgeçsiz): durum, gün, katılımcı, satılan."),
    "bayi_gecmisi": ("CRM ortak ziyaret (okul–bayi)", "«Cari ile ziyaret» etkinliklerinde okul × aracı bayi sayısı ve son gün."),
    "siparisler": ("CRM okul örneği / okul satışı siparişleri", "Okul örneği, öğretmen örneği ve okul satışı siparişleri (geçmiş başlangıcından)."),
    "bayiler": ("CRM bayi ve kitapçılar", "Etkin bayi/kitapçı kartları; ilçe birincil adresten."),
    "kitaplar": ("CRM kitap kartları", "Sınıf/yaş işaretleri, sayfa, perakende fiyat; yayından kalkanlar hariç."),
    "kullanicilar": ("CRM kullanıcıları", "Temsilci adı ve hesabı (kapsam ve ekrandaki ad için)."),
    "ilceler": ("CRM ilçe listesi", "İlçe endeksini CRM ilçesiyle eşlemek için."),
    "donemler": ("Logo dönem listesi", "Yıl başına firma kopyası (LG_211 = 2021–2025, LG_411 = 2026)."),
    "stok": ("Logo stok bakiyesi", "Güncel kopyada stok kodu başına giriş − çıkış (tarih süzgeçsiz)."),
    "fiyat": ("Logo satış fiyat listesi", "Bugün geçerli TL satış fiyatları; genel liste = cari özel kodu boş."),
    "cariler": ("Logo cari kartları", "Bayinin Logo kaydı (telefon, şehir)."),
    "bayi_satisi": ("Logo bayi × kitap faturalı satış", "Faturalı net adet (7,8,9 satış − 2,3 iade), yıl kopyası başına."),
    "bayi_aylik": ("Logo bayi × ay faturalı satış", "Ay başına faturalı net adet ve net ciro (LINENET), yıl kopyası başına."),
}

NOT_RAKAM = ("page", "pageSize", "items[].calendar", "school.kurumTipiKod", "school.kademeKod", "school.kurumTuruKod",
             "school.okulTuruKod", "school.grades[]", "grades[]", "size", "priceCap", "items[].logicalref",
             "candidates[].logicalref", "links[].logicalref")


class _Ctx:
    def __init__(self, engine: Any, tenant: str, model: Optional[SV.Model], crm_db: Optional[str], logo_db: Optional[str]):
        self.engine, self.tenant, self.m = engine, tenant, model
        self.dbs = {"crm": crm_db, "logo": logo_db}
        snap = model.snap if model is not None else {}
        self.k = P.Kaynaklar(data_end=snap.get("asOf"), as_of=snap.get("asOf"))
        self._reads: dict[str, list[dict[str, Any]]] = {}
        for q in snap.get("sorgular") or []:
            self._reads.setdefault(q.get("key") or "diger", []).append(q)
        self._done: dict[str, list[str]] = {}

    # -- okumada çalışan CRM/Logo metni
    def read(self, key: str) -> list[str]:
        if key in self._done:
            return self._done[key]
        qs = self._reads.get(key) or []
        title, desc = TITLES.get(key, (key, ""))
        ids = []
        for i, q in enumerate(qs, 1):
            sid = f"okul.{key}" if len(qs) == 1 else f"okul.{key}.{i}"
            conn = q.get("conn") if q.get("conn") in ("crm", "logo") else "crm"
            try:
                ids.append(self.k.sorgu(sid, title if len(qs) == 1 else f"{title} ({i})", conn, q.get("sql") or "",
                                        database=q.get("db") or self.dbs.get(conn), rows=q.get("rows"), ms=q.get("dbMs"),
                                        ran_at=q.get("at"), description=desc))
            except P.ProvenanceError:
                continue
        self._done[key] = ids
        return ids

    def reads(self, *keys: str) -> list[str]:
        out: list[str] = []
        for k in keys:
            out += self.read(k)
        return out

    def one(self, key: str) -> Optional[str]:
        ids = self.read(key)
        return ids[0] if ids else None

    # -- portal tabloları
    def portal(self, sid: str, title: str, stmt: Any, desc: str, origin: Iterable[str] = ()) -> str:
        if sid in self.k.sources:
            return sid
        return self.k.portal(sid, title, stmt, self.engine, description=desc, origin=origin)

    def context(self) -> str:
        return self.portal("okul.baglam", "Yüklenen bağlam (ilçe endeksi, akademik takvim)", SV.context_stmt(self.tenant),
                           "Etkin yüklemenin satırları; dosyadan yüklenir (kaynak adı ve tarihi kayıtta).",
                           origin=self.read("ilceler"))

    def last_visits(self) -> str:
        return self.portal("okul.portal_son", "Portalda son ziyaret", SV.last_visits_stmt(self.tenant),
                           "Okul başına portalda «yapıldı» işaretli son ziyaret.")

    def links(self, sid: str = "okul.baglar", state: Optional[str] = None, school: Optional[str] = None) -> str:
        return self.portal(sid, "Okul–bayi eşleşmeleri", SV.links_stmt(self.tenant, school=school, state=state),
                           "Öneri, onaylı ve reddedilen bağlar; aday puanı öneri anındaki kural puanı.",
                           origin=self.reads("bayiler", "bayi_gecmisi"))

    def visits(self, sid: str, **kw: Any) -> str:
        return self.portal(sid, "Portal ziyaret raporları", SV.visits_stmt(self.tenant, **kw),
                           "Ortak saha ziyaret tablosu (tür okul) + okul ayrıntısı; gizli notun metni yalnız yazana gider.")

    def plans(self, sid: str, **kw: Any) -> str:
        return self.portal(sid, "Haftalık ziyaret planı", SV.plans_stmt(self.tenant, **kw),
                           "Plan satırları; puan ve gerekçe öneri anında yazılır.")

    # -- hesaplar
    def puan(self) -> str:
        if "puan" in self.k.formulas:
            return "hesap:puan"
        st = (self.m.settings if self.m else {}) or {}
        w = st.get("weights") or SV.DEFAULT_WEIGHTS
        wt = ", ".join(f"{SV.WEIGHT_LABELS[k]} {v:g}" for k, v in w.items())
        text = ("Öncelik puanı = Σ ağırlık × oran (oran 0–1). Öğrenci sayısı: okulun öğrencisi ÷ aynı kurum tipindeki okulların "
                "90. yüzdelik öğrenci sayısı. Son ziyaret (CRM tamamlanan ve portal «yapıldı» ziyaretinin en yenisi): hiç yok 1, "
                "365 günden eski 0,8, 180 günden eski 0,4, daha yeni 0. Geçmiş: son 2 yılda okul satışı 1, yalnız örnek 2/3, yok 0. "
                "Kademe: kademeye uygun ve stokta kitap varsa 1. Bölge: ilçe endeksinin en düşük–en yüksek arasındaki konumu. "
                "Tür: kurum türü kodu 2 ya da 3 ise 1. Bayi: onaylı bağlı bayi varsa 1. "
                f"Ağırlıklar (ayar SCHOOLS_PRIORITY_WEIGHTS): {wt}. Rakam modelden gelmez.")
        ins = self.reads("okullar", "ziyaretler", "siparisler", "kitaplar", "stok") + [self.context(), self.last_visits(), self.links()]
        return self.k.hesap("puan", text, ins)

    def uygun(self) -> str:
        if "uygun" in self.k.formulas:
            return "hesap:uygun"
        ms = ((self.m.settings if self.m else {}) or {}).get("minStock", 1)
        return self.k.hesap("uygun", "Uygun ve stokta kitap = CRM kitap kartında okulun sınıf/yaş kademesinden en az biri işaretli "
                            f"ve Logo stok bakiyesi en az {ms:g} olan kitap sayısı (ayar SCHOOLS_CATALOG_MIN_STOCK).",
                            self.reads("kitaplar", "stok"))

    def ayar(self) -> str:
        if "ayar" in self.k.formulas:
            return "hesap:ayar"
        st = (self.m.settings if self.m else {}) or {}
        keys = ("planSize", "catalogSize", "revisitDays", "dealerMonths", "conversionMonths", "historyFrom")
        src = KA.ayar(self.k, self.engine, "okul.ayar", ["SCHOOLS_WEEKLY_PLAN_SIZE", "SCHOOLS_CATALOG_SIZE",
                      "SCHOOLS_REVISIT_DAYS", "SCHOOLS_DEALER_MONTHS", "SCHOOLS_CONVERSION_MONTHS", "SCHOOLS_HISTORY_FROM",
                      "SCHOOLS_PRIORITY_WEIGHTS"], "okul tanıtım")
        return self.k.hesap("ayar", "Ayarlar (Yönetim ekranı > ortam > varsayılan): " + ", ".join(
            f"{k} {st.get(k)}" for k in keys) + "; öncelik ağırlıkları SCHOOLS_PRIORITY_WEIGHTS.", [src])


def _snap_ok(x: _Ctx) -> None:
    """Okuma kaydı olmayan (eski) okumada sorgu bilgisi kurulmaz; ekranda «hazırlanamadı» görünür, yeniden okuma düzeltir."""
    if x.m is None or not x.m.snap.get("sorgular"):
        raise P.ProvenanceError("Okumanın çalışan sorguları kayıtlı değil (okuma yenilenince gelir).")


# ------------------------------------------------------------------ uçlar


def for_meta(engine: Any, tenant: str, model: Optional[SV.Model], out: dict[str, Any], crm_db: Optional[str] = None,
             logo_db: Optional[str] = None) -> P.Kaynaklar:
    x = _Ctx(engine, tenant, model, crm_db, logo_db)
    ayar = x.ayar()
    f = {"weights": ayar, "settings": ayar, "uploads": x.context()}
    okul = x.read("okullar")
    if okul:  # okuma kaydı yoksa (eski okuma) okul sayısı bağlanmaz; girdisiz hesap kurulmaz
        f["status"] = x.k.hesap("okul_sayisi", "Okul sayısı = CRM ziyaret yerleri okumasında etkin, kurum tipi ayardaki "
                                "(SCHOOLS_KURUM_TIPLERI) ve adı/ili okunabilen kayıt sayısı.", okul)
    x.k.alanlar(f)
    return x.k


def for_list(engine: Any, tenant: str, model: SV.Model, out: dict[str, Any], crm_db: Optional[str] = None,
             logo_db: Optional[str] = None) -> P.Kaynaklar:
    x = _Ctx(engine, tenant, model, crm_db, logo_db)
    _snap_ok(x)
    puan = x.puan()
    rules = ", ".join(model.settings.get("owners") or []) or "—"
    sayac = x.k.hesap("sayac", "Listede = süzgeçten (il, ilçe, kademe, tür, en az puan, ad araması) geçen okul sayısı; "
                      "kapsamınızdaki okul = CRM'de sahibi, ilin temsilcisi ya da okulda ziyaret sorumlusu olduğunuz "
                      f"(kural SCHOOLS_OWNER_RULES: {rules}) ve portalda ziyaret/plan yazdığınız okullar.",
                      x.reads("okullar", "ziyaretler") + [x.visits("okul.portal_ziyaret"), x.plans("okul.plan")])
    x.k.alanlar({"items[]": puan, "items[].score": puan, "items[].students": x.one("okullar") or puan,
                 "total": sayac, "mineCount": sayac})
    return x.k


def for_card(engine: Any, tenant: str, model: SV.Model, sid: str, out: dict[str, Any], crm_db: Optional[str] = None,
             logo_db: Optional[str] = None) -> P.Kaynaklar:
    x = _Ctx(engine, tenant, model, crm_db, logo_db)
    _snap_ok(x)
    puan = x.puan()
    okul = x.one("okullar")
    ziy = x.one("ziyaretler")
    crm = x.k.hesap("crm_ziyaret", "CRM'de tamamlanan okul ziyareti = ziyaret yeri bu okula bağlı ve durumu «tamamlandı» olan "
                    "etkinlik sayısı; «okul adı eşleşmesiyle» = ziyaret yeri boş, serbest okul adı (aynı ilde) bu okula "
                    "eşlenen etkinlikler (kural ya da Zeki AI kararı, portalda saklı).",
                    x.read("ziyaretler") + [x.portal("okul.ad_eslesme", "Okul adı eşleşme kararları", SV.matches_stmt(tenant),
                                                     "CRM'deki serbest okul adı → ziyaret yeri kararları.")])
    pv = x.visits("okul.portal_ziyaret", school=sid)
    gizli = x.k.hesap("gizli", "Başka temsilcilerin raporu = bu okulun portal ziyaretlerinden sahibi siz olmayanların sayısı "
                      "(herkesinkini görme yetkisi yoksa listeden çıkarılır).", [pv])
    f = {"school": okul, "score": puan, "parts": puan, "crmVisits": ziy, "crmDoneLinked": crm, "crmDoneByName": crm,
         "portalVisits": pv, "hiddenOthers": gizli, "orders": x.one("siparisler"),
         "links": x.links("okul.baglar.okul", school=sid), "plans": x.plans("okul.plan.okul", school=sid),
         "calendar": x.context(), "fittingBooks": x.uygun(),
         "catalogs": x.portal("okul.kataloglar", "Hazırlanan kataloglar", SV.catalogs_stmt(tenant, sid),
                              "Kitap sayısı = kayıttaki kitap listesinin uzunluğu; uygun toplam hazırlandığı andaki.",
                              origin=x.reads("kitaplar", "stok"))}
    x.k.alanlar({k: v for k, v in f.items() if v})
    return x.k


def for_plan(engine: Any, tenant: str, model: SV.Model, week: date, who: Optional[str], out: dict[str, Any],
             crm_db: Optional[str] = None, logo_db: Optional[str] = None) -> P.Kaynaklar:
    x = _Ctx(engine, tenant, model, crm_db, logo_db)
    _snap_ok(x)
    pl = x.plans("okul.plan", week=week, owner=who)
    since = datetime(week.year, week.month, week.day, tzinfo=SV.TZ)
    pv = x.visits("okul.portal_ziyaret", owner=who, since=since)
    say = x.k.hesap("plan_sayac", "Planlı = haftanın iptal edilmemiş plan satırları; gidildi = plan sahibinin aynı hafta o "
                    "okula portalda «yapıldı» ya da CRM'de tamamlanan ziyareti olan satırlar.", [pl, pv] + x.read("ziyaretler"))
    x.k.alanlar({"items[]": pl, "items[].students": x.one("okullar") or pl, "items[].score": x.puan(),
                 "done": say, "planned": say,
                 "nextSteps": x.visits("okul.portal_ziyaret.sahip", owner=who), "calendar": x.context()})
    return x.k


def for_queue(engine: Any, tenant: str, model: SV.Model, out: dict[str, Any], crm_db: Optional[str] = None,
              logo_db: Optional[str] = None) -> P.Kaynaklar:
    x = _Ctx(engine, tenant, model, crm_db, logo_db)
    _snap_ok(x)
    q = x.links("okul.baglar.oneri", state="oneri")
    x.k.alanlar({"items[]": q, "total": q})
    return x.k


def for_dealers(engine: Any, tenant: str, model: SV.Model, sid: str, out: dict[str, Any], crm_db: Optional[str] = None,
                logo_db: Optional[str] = None) -> P.Kaynaklar:
    x = _Ctx(engine, tenant, model, crm_db, logo_db)
    _snap_ok(x)
    risk = x.portal("okul.saha_sinyal", "Saha bayi sinyalleri (risk)", "SELECT logo_clientref, risk_doluluk, k_90p, asof "
                    "FROM semantic_field_signals ORDER BY asof",
                    "Limit doluluğu ve 90 günü aşan borç; uyarı içindir, puandan düşülmez.")
    aday = x.k.hesap("bayi_aday", "Aday puanı = aynı ilçe 40 + 40 × (bu kademeye uygun kitaplardan son "
                     f"{model.settings['dealerMonths']} ayda faturalı net adet ÷ adaylar arasında en çok satanın adedi) + geçmiş "
                     "ortak ziyaret (bu okulda 10, ilçede 5) + ağ dengesi 10 ÷ (1 + bağlı okul sayısı ÷ 5). Kademe satışı = "
                     "bayinin Logo satışında kitap kartı bu okulun kademesine uyan kitapların net adedi.",
                     x.reads("bayiler", "bayi_satisi", "bayi_gecmisi", "kitaplar", "cariler") + [x.links(), risk])
    x.k.alanlar({"links": x.links("okul.baglar.okul", school=sid), "candidates": aday, "months": x.ayar()})
    return x.k


def for_catalog(engine: Any, tenant: str, model: SV.Model, out: dict[str, Any], crm_db: Optional[str] = None,
                logo_db: Optional[str] = None) -> P.Kaynaklar:
    x = _Ctx(engine, tenant, model, crm_db, logo_db)
    _snap_ok(x)
    sec = x.k.hesap("katalog", "Katalog = kademeye uygun ve stokta kitaplardan fiyat üst sınırına uyanlar; sıra ildeki bayilerin "
                    "son satış penceresindeki faturalı net adedi (çok satan önce), sonra ad. Fiyat = Logo'da bugün geçerli "
                    "genel TL liste fiyatı (yoksa CRM perakende fiyatı); stok = Logo stok bakiyesi. Toplam = süzgece uyan "
                    "bütün kitaplar (kesilmeden).", x.reads("kitaplar", "stok", "fiyat", "bayi_satisi", "bayiler"))
    x.k.alanlar({"total": sec, "items[]": sec, "items[].stock": x.one("stok") or sec,
                 "items[].price": sec, "items[].regionSales": sec, "items[].pages": x.one("kitaplar") or sec})
    return x.k


def for_visits(engine: Any, tenant: str, model: SV.Model, sid: str, out: dict[str, Any], crm_db: Optional[str] = None,
               logo_db: Optional[str] = None) -> P.Kaynaklar:
    x = _Ctx(engine, tenant, model, crm_db, logo_db)
    _snap_ok(x)
    x.k.alanlar({"portal": x.visits("okul.portal_ziyaret", school=sid), "crm": x.one("ziyaretler")})
    return x.k


def for_visit(engine: Any, tenant: str, vid: str, out: dict[str, Any]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant, None, None, None)
    ref = x.visits("okul.portal_ziyaret", vid=vid)
    x.k.alanlar({"books": ref})
    return x.k


def for_context(engine: Any, tenant: str, model: Optional[SV.Model], out: dict[str, Any], crm_db: Optional[str] = None,
                logo_db: Optional[str] = None) -> P.Kaynaklar:
    x = _Ctx(engine, tenant, model, crm_db, logo_db)
    c = x.context()
    rng = x.k.hesap("endeks_aralik", "Endeks aralığı = yüklü ilçe endekslerinin en düşüğü ve en yükseği; CRM'de bulunamayan = "
                    "ilçesi CRM ilçe listesiyle eşleşmeyen satır.", [c])
    x.k.alanlar({"uploads": c, "calendar": c, "districts": c, "range": rng})
    return x.k


def for_term(engine: Any, tenant: str, model: SV.Model, out: dict[str, Any], a: date, b: date, who: Optional[str],
             crm_db: Optional[str] = None, logo_db: Optional[str] = None) -> P.Kaynaklar:
    x = _Ctx(engine, tenant, model, crm_db, logo_db)
    _snap_ok(x)
    pl = x.plans("okul.plan.donem", since=a, until=b, owner=who)
    pv = x.visits("okul.portal_ziyaret.donem", owner=who)
    ziy = x.read("ziyaretler")
    donem = f"{a.isoformat()} – {b.isoformat()}"
    k = model.settings["conversionMonths"]
    f = {
        "plans": x.k.hesap("t_plan", f"Dönem ({donem}) planı: planlı = iptal edilmemiş plan satırı; onaylı = durumu onaylı; "
                           "gerçekleşen = plan sahibinin aynı hafta o okula portalda «yapıldı» ya da CRM'de tamamlanan "
                           "ziyareti olan plan; oran = gerçekleşen ÷ planlı.", [pl, pv] + ziy),
        "visits": x.k.hesap("t_ziyaret", f"Ziyaret: portal = dönemde «yapıldı» portal raporu; CRM = dönemde tamamlanan CRM okul "
                            "ziyareti (ziyaret yeri bağlı ya da okul adıyla eşlenen); ziyaret edilen okul = ikisinden en az "
                            "birinin olduğu okul sayısı.", [pv] + ziy),
        "orders": x.k.hesap("t_siparis", "Okul siparişleri: dönemde açılan (CRM oluşturma günü) okul örneği / öğretmen örneği / "
                            "okul satışı siparişlerinin tip başına sayısı ve indirimli toplam tutarı (siparişte okul ve "
                            "temsilci alanı yok; il süzgeci firmanın ilinden).", x.read("siparisler")),
        "samples": x.k.hesap("t_ornek", "Örnekten satışa: firma adı okul adıyla eşleşen siparişlerde, dönemde örnek giden okul "
                             "sayısı ve bunlardan ilk örnekten sonra okul satışı açılanların sayısı.", x.read("siparisler")),
        "conversion": x.k.hesap("t_donusum", f"Ziyaretten sonra bayide satış: ziyaret edilen okulların onaylı bayileri; ilk "
                                f"ziyaret ayından önceki {k} ay ile sonraki {k} ayın faturalı net satış adedi (bütün kitaplar); "
                                "sonrası büyükse arttı, küçükse azaldı. Sonraki pencere dolmayan bayi «bekliyor».",
                                x.read("bayi_aylik") + [x.links(), pv] + ziy),
        "byIl": x.k.hesap("t_il", "İl bazında: ildeki okul sayısı (CRM ziyaret yerleri), dönemde ziyaret edilen okul sayısı, "
                          "oran = ziyaret edilen ÷ okul.", x.read("okullar") + [pv] + ziy),
        "byOwner": x.k.hesap("t_temsilci", "Temsilci: dönemde planlı okul, gerçekleşen plan, portalda «yapıldı» rapor sayısı.",
                             [pl, pv]),
    }
    x.k.alanlar(f)
    return x.k
