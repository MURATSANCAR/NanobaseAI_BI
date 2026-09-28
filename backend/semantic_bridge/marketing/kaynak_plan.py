"""M15 Yeni kitap pazarlama planı: ekrandaki her rakamın sorgu bilgisi (ortak sözleşme `provenance.py`).

Uç başına `for_<uç>()`: yeni kitap listesi, kitap karnesi, emsal adayları, plan (KPI, kanal/bütçe satırları, takvim,
materyaller), plan geçmişi ve «CRM'e işlenecek» listesi. Portal okumasında gösterilen SQL uçta çalışan ifadenin
kendisidir (`core.*_stmt`, `plans.*_stmt`); karne önbelleğinden gelen rakamda karneyi kuran CRM sorguları, bütçe
modülünün Logo satış önbelleği ve ilk baskı tahmininin veri kümesi `origin` olarak eklenir.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

from semantic_bridge import pazarlama_kaynak as PK
from semantic_bridge import provenance as P
from semantic_bridge.marketing import core as C
from semantic_bridge.marketing import plans as PL
from semantic_bridge.marketing import sources as S

#: Rakam olmayan sayılar (yıl, sürüm, sıra, sayfa).
NOT_RAKAM = ("page", "pageSize", "surum", "items[].plan.surum", "hedef.year", "hedef.version", "kitap.yas",
             "lines[].sira", "materials[].surum", "items[].sira", "emsal.tahmin.guven", "yazar.yillar[].yil",
             "hedef.aylik[].ay")

F_KALAN = "Kalan gün = yayın günü − bugün. Yayın günü CRM'deki üç tarihten ayardaki öncelik sırasıyla seçilir (kitap kartı ilk baskı, proje yayın tarihi, üretim depo girişi / dağılım planı); planda elle girildiyse o."
F_KPI_PLANSIZ = "Planı yok = yayın gününe 0 ile «plansız uyarı günü» arasında kalan ve pazarlama planı açılmamış kitap sayısı."
F_KPI_ONAYDA = "Onay bekleyen = aralıktaki kitaplardan son sürüm planı «onay bekliyor» durumunda olanların sayısı."
F_KPI_MATERYAL = ("Materyali eksik = yayına «materyal uyarı günü» ya da daha az kalan ve zorunlu materyal türlerinden en az biri "
                  "onaylı olmayan planların sayısı.")
F_KPI_HEDEF = ("Hedefi değişen = plandaki hedef anlık görüntüsü (plan, sürüm, adet, ciro) yürürlükteki bütçe planındaki "
               "değerden farklı olan (arşivde olmayan) planların sayısı.")
F_PLAN_BUTCE = "Plan bütçesi = planın kanal ve bütçe satırlarındaki tutarların toplamı (Σ satır tutarı)."
F_LISTE = ("Liste: yayın günü seçilen aralıkta olan CRM yeni kitap kartları, süzgeçlerden (durum, yayınevi, arama, «bana "
           "düşenler») geçenler; «toplam» süzgeçten geçen, «hepsi» aralıktaki bütün kitap sayısı. Sayfa 100 satır; sorgu "
           "satır kesmez.")
F_MATERYAL_SAY = "Onaylı materyal = planın «onaylı» durumdaki materyal sayısı / bütün materyal sayısı."
F_CERCEVE = ("Bütçe çerçevesi: (1) plan sahibinin elle girdiği tutar; yoksa (2) CRM proje kartındaki «Toplam Pazarlama "
             "Bütçesi» (önce kurul sonucu); yoksa (3) oran × kitabın hedef net cirosu. Oran yönetim ayarıysa odur; değilse "
             "son tam yılın pazarlama masraf merkezi gideri ÷ aynı yılın şirket net cirosu.")
F_ORAN = "Satır toplamının hedef ciroya oranı = Σ satır tutarı ÷ plandaki hedef net ciro."
F_ZEKI = ("Emsal kontrolü olasılığı Zeki AI'ın kapalı küme kararındaki güvendir (evet / hayır / belirsiz); satış rakamı "
          "değildir. «Düşen cümle» denetimde kaynaksız rakam, bulunamayan alıntı ya da kanıtsız iddia yüzünden atılan "
          "cümle sayısıdır.")
F_EMSAL = ("Emsal satışı = ilk baskı tahmini veri kümesinde kitabın ilk yayın ayından itibaren aylık net adedi (satış − "
           "iade); ilk 3 / 6 / 12 ay = ilk N ayın toplamı (N ay gözlenmemişse boş). Emsaller: CRM kitap kartındaki emsal "
           "bağı ve ilk baskı tahmininin benzerlik puanıyla seçtiği kitaplar.")
F_TAHMIN = ("İlk baskı tahmini: emsallerin ilk 6 / 12 ay satışından ölçeklenen tahmin (baz senaryo ve bant), önerilen ilk "
            "baskı = baskı kuralı adımına yuvarlanmış öneri. Hesap ilk baskı tahmini ekranınınkiyle aynıdır.")
F_YAZAR = ("Yazarın diğer kitapları: kitap bilgisi tablosunda yazar adı ortak olan kitaplar; yıllık net adet ve net ciro "
           "Logo faturalı satış önbelleğinden (Σ adet, Σ ciro, kitap × yıl); toplam satırı = Σ kitaplar. İlk 12 ay ilk "
           "baskı tahmini veri kümesinden.")
F_KARNE = ("Karne kitap başına saklanan anlık görüntüdür («Karneyi yenile» ile yeniden kurulur). Künye, fiyat, sayfa, CRM "
           "bütçe alanları, rakip kitaplar ve özel günler karne kurulurken CRM'den okundu.")
F_ADAY = ("Emsal adayları anlamca yakınlık sırasıdır (puan gösterilmez); ilk 3 / 6 / 12 ay satış sütunları emsal "
          "tablosuyla aynı kaynaktan: ilk baskı tahmini veri kümesi (Logo aylık net satış, iade düşülmüş).")
F_TODO = ("CRM'e işlenecek: onaylı materyalin metni CRM kitap kartındaki alandan farklıysa; her bütçe satırı (tutar "
          "satırdan); proje kartındaki toplam bütçe plan toplamından farklıysa (plan toplamı = Σ satır tutarı).")


def _plans_source(k: P.Kaynaklar, engine: Any, tenant: str, codes: list[str]) -> str:
    return k.portal("mkt.planlar", "Kitapların pazarlama planları", C.plans_stmt(tenant, kind="yeni", stok=codes), engine,
                    description="Portalda açılmış yeni kitap planları (semantic_mkt_plans): durum, sürüm, sahip, hedef "
                                "anlık görüntüsü, plan bütçesi (satır toplamı).")


def for_new_books(engine: Any, tenant: str, schema: str, st: dict[str, Any], out: dict[str, Any], trace: dict[str, Any],
                  frm: date, to: date) -> P.Kaynaklar:
    k = P.Kaynaklar(data_end=PL.data_end(engine))
    crm = k.sorgu("mkt.crm.yeni", "CRM yeni kitap kartları (yayın günü aralıkta)", "crm", S.new_books_sql(schema, frm, to),
                  database=PK.crm_db(), period=f"{frm.isoformat()} – {to.isoformat()}",
                  description="Kitap kartı ilk baskı tarihi, bağlı proje yayın tarihi ya da ilk baskının üretim tarihleri "
                              "aralıkta olan etkin kitaplar; künye ve pazarlama sorumlusu.")
    codes = list(trace.get("codes") or [])
    plans = _plans_source(k, engine, tenant, codes) if codes else None
    ids = [x for x in trace.get("planIds") or []]
    mats = k.portal("mkt.materyal", "Planların materyalleri", C.materials_stmt(ids), engine,
                    description="Planların materyal kayıtları (semantic_mkt_materials); eksik materyal buradan.") if ids else None
    tg = PK.hedefler(k, engine, tenant, {int(y): v for y, v in (trace.get("byYear") or {}).items()}, prefix="mkt.butce")
    base = [x for x in (crm, plans, mats) if x]
    liste = k.hesap("liste", F_LISTE, base)
    kalan = k.hesap("kalan", F_KALAN, [crm] + ([plans] if plans else []))
    hedef = k.hesap("hedef", PK.F_HEDEF, tg or [crm])
    fields = {"items[]": liste, "total": liste, "hepsi": liste, "items[].kalanGun": kalan, "items[].hedef": hedef,
              "kpi.plansiz": k.hesap("kpiPlansiz", F_KPI_PLANSIZ, base),
              "kpi.onayda": k.hesap("kpiOnayda", F_KPI_ONAYDA, base),
              "kpi.materyalEksik": k.hesap("kpiMateryal", F_KPI_MATERYAL, base),
              "kpi.hedefDegisti": k.hesap("kpiHedef", F_KPI_HEDEF, base + tg)}
    if plans:
        fields["items[].plan"] = k.hesap("planButce", F_PLAN_BUTCE, [plans])
    k.alanlar(fields)
    return k


def _card_sources(k: P.Kaynaklar, engine: Any, tenant: str, schema: str, state: Any, card_: dict[str, Any],
                  logo_db: Optional[str]) -> dict[str, list[str]]:
    kitap = card_.get("kitap") or {}
    stok = kitap.get("stokKodu") or ""
    crm = [k.sorgu("mkt.crm.kitap", "CRM kitap kartı ve proje kartı", "crm", S.book_sql(schema, stok), database=PK.crm_db(),
                   description="Künye, kapak fiyatı, sayfa, yayın tarihleri, proje kartının pazarlama bütçe alanları ve "
                               "pazarlama metinleri.")]
    if kitap.get("kitapId"):
        try:
            crm.append(k.sorgu("mkt.crm.rakip", "CRM rakip kitaplar", "crm", S.rivals_sql(schema, kitap["kitapId"]),
                               database=PK.crm_db(), description="Kitap kartına bağlı «Rakip Kitap» kayıtları."))
            crm.append(k.sorgu("mkt.crm.ozelgun", "CRM özel gün bağları", "crm", S.special_days_sql(schema, kitap["kitapId"]),
                               database=PK.crm_db(), description="Kitaba bağlı özel günler."))
        except S.SourceError:
            pass
    karne = k.portal("mkt.karne", "Kitap karnesi (saklanan görüntü)", C.card_stmt(tenant, stok), engine, origin=crm,
                     description="Karne kitap başına saklanır (semantic_mkt_cards); aşağıdaki sorgularla kuruldu.")
    pub = (card_.get("yayin") or {}).get("tarih")
    y = PK.year_of(pub)
    hedef = PK.hedefler(k, engine, tenant, {y: [stok]}, prefix="mkt.butce") if y else []
    m10 = PK.ilk_baski(k, state, prefix="mkt.ilkbaski")
    yz = card_.get("yazar") or {}
    codes = sorted({x.get("stokKodu") for x in yz.get("items") or [] if x.get("stokKodu")})
    yazar = []
    if codes:
        yazar.append(k.portal("mkt.yazar.kitap", "Kitap bilgisi (yazar eşleşmesi)", PL.author_books_stmt(), engine,
                              description="Bütçe modülünün kitap bilgisi tablosu (CRM kitap kartından): yazar adı ortak kitaplar."))
        years = [int(t["yil"]) for t in yz.get("yillar") or [] if t.get("yil")]
        yazar.append(PK.butce_satis(k, engine, "mkt.yazar.satis", "Yazarın kitaplarının yıllık satışı",
                                    PL.author_sales_stmt(codes), years, logo_db))
    return {"crm": crm, "karne": [karne], "hedef": hedef, "m10": m10, "yazar": yazar}


def for_card(engine: Any, tenant: str, schema: str, state: Any, card_: dict[str, Any], logo_db: Optional[str]) -> P.Kaynaklar:
    k = P.Kaynaklar(data_end=(card_.get("veriSonu") or {}).get("logo"), as_of=card_.get("asof"))
    s = _card_sources(k, engine, tenant, schema, state, card_, logo_db)
    karne = s["karne"][0]
    kart = k.hesap("karne", F_KARNE, [karne])
    emsal = k.hesap("emsal", F_EMSAL, [karne] + s["m10"])
    k.alanlar({
        "kitap": kart, "crmButce": kart, "rakipler": kart, "ozelGunler": kart,
        "hedef": k.hesap("hedef", PK.F_HEDEF, [karne] + s["hedef"]),
        "emsal": emsal, "emsal.tahmin": k.hesap("tahmin", F_TAHMIN, [karne] + s["m10"]),
        "yazar": k.hesap("yazar", F_YAZAR, [karne] + s["yazar"] + s["m10"]),
    })
    return k


def for_emsal_candidates(state: Any, out: dict[str, Any]) -> P.Kaynaklar:
    k = P.Kaynaklar()
    m10 = PK.ilk_baski(k, state, prefix="mkt.ilkbaski")
    if not m10:
        raise P.ProvenanceError("İlk baskı tahmini görüntüsünde çalışmış sorgu kaydı yok.")
    k.alanlar({"items[]": k.hesap("aday", F_ADAY, m10)})
    return k


def _plan_sources(k: P.Kaynaklar, engine: Any, tenant: str, plan_id: str) -> dict[str, str]:
    return {
        "plan": k.portal("mkt.plan", "Plan kaydı", C.plan_stmt(tenant, plan_id), engine,
                         description="Plan başlığı, durumu, yayın günü, hedef anlık görüntüsü (plan açılırken bütçe planından), "
                                     "bütçe çerçevesi ve dayanağı, Zeki AI önerisinin kaydı (semantic_mkt_plans)."),
        "lines": k.portal("mkt.plan.satir", "Kanal ve bütçe satırları", C.lines_stmt(plan_id), engine,
                          description="Kanal, tutar, tarih ve gerekçe (semantic_mkt_plan_lines)."),
        "tasks": k.portal("mkt.plan.takvim", "Takvim işleri", C.tasks_stmt(plan_id), engine,
                          description="Yayın gününe göre gün farkı, tarih, durum (semantic_mkt_plan_tasks)."),
        "mats": k.portal("mkt.plan.materyal", "Materyaller", C.materials_stmt([plan_id]), engine,
                         description="Materyal türü, durumu, sürümü ve denetim sonucu (semantic_mkt_materials)."),
    }


def _ratio_sources(k: P.Kaynaklar, engine: Any, plan: dict[str, Any], logo_db: Optional[str]) -> list[str]:
    oran = ((plan.get("butceCerceveKaynak") or {}).get("oran") or {})
    y = oran.get("yil")
    if oran.get("kaynak") != "veri" or not y:
        return []
    st_ = PL.dept_ratio_stmts(int(y))
    gider = k.portal("mkt.oran.gider", f"Pazarlama masraf merkezi gideri · {y}", st_["gider"], engine,
                     origin=PK.logo_gider(k, engine, [int(y)], logo_db),
                     description="Bütçe modülünün Logo gider önbelleği; pazarlama masraf merkezlerinin satırları toplanır.")
    ciro = PK.butce_satis(k, engine, "mkt.oran.ciro", f"Şirket net cirosu · {y}", st_["ciro"], [int(y)], logo_db)
    return [gider, ciro]


def for_plan(engine: Any, tenant: str, plan: dict[str, Any], logo_db: Optional[str]) -> P.Kaynaklar:
    k = P.Kaynaklar(data_end=PL.data_end(engine))
    s = _plan_sources(k, engine, tenant, plan["id"])
    oran = _ratio_sources(k, engine, plan, logo_db)
    toplam = k.hesap("butceToplam", F_PLAN_BUTCE, [s["lines"], s["plan"]])
    k.alanlar({
        "yayinTarihi": k.hesap("kalan", F_KALAN, [s["plan"]]),
        "hedef": k.hesap("hedef", PK.F_HEDEF + " Plandaki değer plan açıldığındaki anlık görüntüdür.", [s["plan"]]),
        "butceToplam": toplam,
        "butceCerceve": k.hesap("cerceve", F_CERCEVE, [s["plan"]] + oran),
        "butceCerceveKaynak": "hesap:cerceve",
        "lines[]": s["lines"], "lines": s["lines"],
        "oran": k.hesap("oran", F_ORAN, [s["lines"], s["plan"]]),
        "tasks[]": s["tasks"], "tasks": s["tasks"],
        "materials[]": s["mats"], "materials": k.hesap("materyal", F_MATERYAL_SAY, [s["mats"]]),
        "zeki": k.hesap("zeki", F_ZEKI, [s["plan"]]),
    })
    return k


def for_events(engine: Any, plan_id: str) -> P.Kaynaklar:
    k = P.Kaynaklar()
    ev = k.portal("mkt.plan.gecmis", "Plan geçmişi", C.events_stmt(plan_id), engine,
                  description="Plan üzerindeki her işlem: kim, ne zaman, eski ve yeni değer (semantic_mkt_plan_events).")
    k.alanlar({"items[]": ev})
    return k


def for_todo(engine: Any, tenant: str, plan: dict[str, Any], card_: Optional[dict[str, Any]]) -> P.Kaynaklar:
    k = P.Kaynaklar()
    s = _plan_sources(k, engine, tenant, plan["id"])
    ins = [s["lines"], s["mats"], s["plan"]]
    if plan.get("stokKodu"):
        ins.append(k.portal("mkt.karne", "Kitap karnesi (saklanan görüntü)", C.card_stmt(tenant, plan["stokKodu"]), engine,
                            description="CRM'deki metin ve proje bütçesi karşılaştırma için karneden."))
    k.alanlar({"items[]": k.hesap("todo", F_TODO, ins)})
    return k
