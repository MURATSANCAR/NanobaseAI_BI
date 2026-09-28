"""M46 Bütçe: ekrandaki her rakamın sorgu bilgisi (ortak sözleşme `provenance.py`).

Her uç için bir `for_<uç>()` işlevi: cevabın rakamlarını hangi sorgu ve hangi hesabın ürettiğini yazar. Portal
tablosundan (semantic_budget_*) okunan rakamda gösterilen SQL, uçta çalıştırılan ifadenin kendisidir (`budget.*_stmt`);
tabloyu dolduran asıl Logo/CRM sorgusu `origin` olarak eklenir (hangi firma kopyası, kaç satır, ne zaman okundu).
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

from semantic_bridge import budget as B
from semantic_bridge import budget_sources as src
from semantic_bridge import provenance as P

# ------------------------------------------------------------------ formüller (ekranda okunur metin)

F_NET = ("Net ciro = Σ LINENET (satış: TRCODE 7, 8, 9) − Σ LINENET (iade: TRCODE 2, 3); yalnız faturalı "
         "(INVOICEREF ≠ 0) malzeme satırları (LINETYPE 0), iptaller hariç. Net adet aynı kuralla Σ AMOUNT.")
F_GIDER = ("Gerçekleşen gider = 7 ile başlayan hesaplarda borç − alacak (muhasebe fiş satırı); yansıtma hesapları "
           "(7x1) ve dönem sonu kapanış satırları hariç. Departman = masraf merkezi; rakamla başlayan merkezler "
           "«kitap ve ürün bazlı merkezler» satırında toplanır.")
F_PLAN_TOPLAM = ("Hedef net ciro = Σ kitap hedef cirosu + Σ (ek başlık × başlık başına ciro). Hedef net adet aynı "
                 "kuralla. Brüt kâr = Σ ciro × marj; hedef brüt marj = brüt kâr ÷ hedef ciro. Departman bütçesi = "
                 "Σ aylık gider bütçesi. Kitap sayısı planda adıyla hedefi olan kitaplardır.")
F_PARAM = ("Plan parametreleri (hacim büyümesi, fiyat artışı, marj değişimi, gider artışı, uyarı eşiği ve kapsamı) "
           "ve taban dönemi (pencere, aylık satış dağılımı) planla birlikte saklanır; öneri bu değerlerle kuruldu.")
F_ONERI = ("Öneri (kurala göre, model yok): backlist taban adet = taban dönemindeki net adet (plan yılı verinin "
           "ötesindeyse ve kitap baskı önerisinin 12 aylık satış tahmininde varsa tahminin p50 toplamı); hedef adet = "
           "taban × (1 + hacim büyümesi); birim fiyat = taban net birim fiyat × (1 + fiyat artışı); marj = kitabın "
           "maliyetli satırlarındaki marj (yoksa yayınevinin, o da yoksa şirketin) + marj değişimi. Yeni kitap: "
           "yayınevi kohortunun satışta geçen ay başına net adet ortalaması × plan yılındaki satış ayı sayısı × "
           "(1 + hacim büyümesi).")
F_BEKLENEN = ("Beklenen (bugüne) = yıllık hedef × Σ (ay payı × o aydan geçen pay). Ay payı taban döneminin aylık "
              "satış dağılımıdır (yeni kitapta yayın ayından itibaren yeniden ölçeklenir); geçen pay verinin bittiği "
              "güne kadar (ay içinde gün oranı).")
F_GERCEK = "Gerçekleşen = plan yılındaki net ciro ve net adet (kitap başına)."
F_ORAN = ("Oran = gerçekleşen ÷ beklenen (ciro hedefi yoksa adetle). Eşik altı «sapma», %100 ve üstü «iyi», arası "
          "«izle»; beklenen sıfırsa «başlamadı».")
F_MARJ = "Gerçekleşen marj = 1 − maliyet ÷ maliyetli ciro; maliyet = Σ AMOUNT × OUTCOST, yalnız OUTCOST ≠ 0 satırlar."
F_SIRKET = ("Şirket satışı: hedef = kitap hedefleri + yeni kitap programı; beklenen = kitapların beklenen toplamı + "
            "program cirosu × geçen pay; gerçekleşen = plandaki kitapların gerçekleşeni + planda olmayan kitapların "
            "satışı (157 ile başlayan ticari ürünler hariç). Oran ve durum yukarıdaki kuralla.")
F_KITAP_HEDEF = "Kitap hedefleri: yalnız planda adıyla hedefi olan kitapların hedef, beklenen ve gerçekleşen toplamı."
F_HEDEF_DISI = ("Hedef dışı satış = planda olmayan kitapların plan yılı net cirosu ve net adedi (157 ticari ürün "
                "hariç); kitap = bu stok kodlarının sayısı.")
F_DURUM = ("Kitap durumu sayıları: her plan kitabının oranı eşiğe göre sınıflanır (sapma / izle / iyi / başlamadı); "
           "sayı o sınıftaki kitap sayısıdır.")
F_KAPSAM = ("Uyarı kapsamı: hedef cirosu büyükten küçüğe sıralanınca toplamın kapsam payını oluşturan kitaplar "
            "(payı geçen kitap dahil); sapma = bunlardan eşik altında kalanlar.")
F_AYLAR = ("Aylık hedef = plan toplam cirosu × taban döneminin o aya düşen payı. Aylık gerçekleşen = o ayın net "
           "cirosu (157 ticari ürün hariç), yalnız verisi başlamış aylar. «Geçen» o aydan geçen pay.")
F_GECEN = "Yılın geçen payı = Σ (her aydan geçen pay) ÷ 12; eşik plan parametresidir (varsayılan %80)."
F_DEPT = ("Departman kullanımı = gerçekleşen gider ÷ dönem bütçesi; dönem bütçesi = Σ (aylık bütçe × o aydan geçen "
          "pay). ≥ %100 aşım, ≥ %90 sınırda. Bu ay kullanımı = bu ayın gideri ÷ (bu ayın bütçesi × geçen pay).")
F_PROGRAM = ("Yeni kitap programı: yayınevi başına beklenen başlık = taban döneminde çıkan başlık sayısı; bilinen = "
             "CRM'de adıyla planlanmış olanlar (kitap hedefi olarak); ek başlık = beklenen − bilinen. Adet = ek başlık × "
             "başlık başına adet; ciro = ek başlık × başlık başına ciro (kohortun yayınevi ortalaması).")
F_TABAN = ("Taban dönemi (senaryo karşılaştırması): pencere içindeki net ciro ve net adet (157 ticari ürün hariç), "
           "gider = pencere içindeki departman gideri toplamı.")
F_UYARI = ("Uyarılar saatlik denetimde yazılır. Satış uyarısı (kitap, yayınevi, şirket): beklenen ve gerçekleşen "
           "izlemedeki kuralla, oran = gerçekleşen ÷ beklenen, fark = beklenen − gerçekleşen. Gider uyarısı: beklenen = "
           "dönem bütçesi, gerçekleşen = gider, oran = kullanım, fark = gerçekleşen − dönem bütçesi.")


# ------------------------------------------------------------------ ortak kaynaklar


def _year_span(start: int, end: int) -> tuple[int, int]:
    return B.from_index(start)[0], B.from_index(end - 1)[0]


def logo_sources(k: P.Kaynaklar, engine: Any, years: Iterable[int], logo_db: Optional[str]) -> tuple[list[str], list[str]]:
    """Portal tablolarını dolduran Logo sorguları: yıl başına satış ve gider (hangi firma kopyasıyla okunduysa o)."""
    sales, exp = [], []
    for y in sorted({int(x) for x in years}):
        m = B.meta_get(engine, f"sales:{y}")
        if m.get("firm"):
            sales.append(k.sorgu(
                f"logo.satis.{y}", f"Logo satış satırları · {y}", "logo", src.sales_sql(m["firm"], y), database=logo_db,
                rows=m.get("rows"), ms=m.get("dbMs"), ran_at=m.get("_at"), period=f"{y} · Logo firma {m['firm']}",
                description="Kitap (stok kodu) × ay: net adet, net ciro, maliyet ve maliyetli ciro. Sonuç portal "
                            "tablosuna (semantic_budget_sales_actuals) yazılır; ekrandaki gerçekleşen bu tablodan okunur."))
        e = B.meta_get(engine, f"expense:{y}")
        firm = e.get("firm") or m.get("firm")
        if e and firm:
            exp.append(k.sorgu(
                f"logo.gider.{y}", f"Logo gider satırları · {y}", "logo", src.expense_sql(firm, y), database=logo_db,
                rows=e.get("rows"), ms=e.get("dbMs"), ran_at=e.get("_at"), period=f"{y} · Logo firma {firm}",
                description="Masraf merkezi × ana gider hesabı × ay. Sonuç portal tablosuna (semantic_budget_expense_actuals) "
                            "yazılır."))
    return sales, exp


def _data_end_source(k: P.Kaynaklar, engine: Any, logo_db: Optional[str]) -> Optional[str]:
    end = B.data_end(engine)
    if not end:
        return None
    m = B.meta_get(engine, f"sales:{end.year}")
    if not m.get("firm"):
        return None
    de = B.meta_get(engine, "data_end")
    return k.sorgu("logo.verisonu", "Logo veri sonu", "logo", src.data_end_sql(m["firm"]), database=logo_db,
                   ran_at=de.get("_at"), description="Son faturalı satış satırının tarihi; beklenen ve gerçekleşen bu güne "
                                                     "kadar hesaplanır.")


def _plan_sources(k: P.Kaynaklar, engine: Any, tenant: str, plan_id: str, suffix: str = "") -> dict[str, str]:
    st = B.totals_stmts(plan_id)
    return {
        "plan": k.portal(f"portal.plan{suffix}", "Plan kaydı", B.plan_stmt(tenant, plan_id), engine,
                         description="Plan başlığı, durumu, parametreleri ve taban dönemi (semantic_budget_plans)."),
        "segment": k.portal(f"portal.toplam.kitap{suffix}", "Plan toplamı · kitap hedefleri", st["segment"], engine,
                            description="Segment (yeni / backlist) başına kitap sayısı, hedef adet, ciro ve brüt kâr."),
        "program": k.portal(f"portal.toplam.program{suffix}", "Plan toplamı · yeni kitap programı", st["program"], engine,
                            description="Ek başlık, ek başlık × başlık başına adet / ciro / brüt kâr."),
        "gider": k.portal(f"portal.toplam.gider{suffix}", "Plan toplamı · departman bütçesi", st["gider"], engine,
                          description="Departman × hesap aylık bütçeleri; yıllık toplamı ekranda."),
    }


def _new(engine: Any) -> P.Kaynaklar:
    return P.Kaynaklar(data_end=B.data_end(engine))


# ------------------------------------------------------------------ uçlar


def _per_plan_totals(k: P.Kaynaklar, engine: Any, tenant: str, items: list[dict[str, Any]],
                     list_source: str) -> dict[str, str]:
    """Plan listesinde her planın toplamı kendi sorgularından: satıra özel anahtar `items[].totals:<plan>`
    (ön yüz `row={plan.id}`), yanında bütün planları kapsayan genel anahtar."""
    fields: dict[str, str] = {}
    every = [list_source]
    for p in items:
        ids = _plan_sources(k, engine, tenant, p["id"], f":{p['id']}")
        mine = [ids["plan"], ids["segment"], ids["program"], ids["gider"]]
        every += mine
        fields[f"items[].totals:{p['id']}"] = k.hesap(f"planToplam:{p['id']}", F_PLAN_TOPLAM, mine)
        fields[f"items[].params:{p['id']}"] = k.hesap(f"parametre:{p['id']}", F_PARAM, [ids["plan"]])
        fields[f"items[].basis:{p['id']}"] = f"hesap:parametre:{p['id']}"
    fields["items[].totals"] = k.hesap("planToplam", F_PLAN_TOPLAM, every)
    fields["items[].params"] = k.hesap("parametre", F_PARAM, [list_source])
    fields["items[].basis"] = "hesap:parametre"
    return fields


def for_plans(engine: Any, tenant: str, year: Optional[int], out: dict[str, Any]) -> P.Kaynaklar:
    """`GET /plans`: plan başına toplam (ekrandaki dört KPI)."""
    k = _new(engine)
    k.portal("portal.planlar", "Plan listesi", B.plans_stmt(tenant, year), engine,
             description="Yılın planları: senaryo, sürüm, durum, parametreler (semantic_budget_plans).")
    k.alanlar(_per_plan_totals(k, engine, tenant, out.get("items") or [], "portal.planlar"))
    return k


def for_tracking(engine: Any, tenant: str, out: dict[str, Any], logo_db: Optional[str]) -> Optional[P.Kaynaklar]:
    plan = out.get("plan")
    if not plan:
        return None
    k = _new(engine)
    k.alanlar(tracking_fields(k, engine, tenant, plan["id"], int(plan["year"]), logo_db))
    return k


def tracking_fields(k: P.Kaynaklar, engine: Any, tenant: str, plan_id: str, year: int,
                    logo_db: Optional[str]) -> dict[str, str]:
    """İzlemenin kaynak kayıtları; alan yolu → kaynak. M45 bütçe–gerçekleşme ve özet kartı da bunu kullanır."""
    plan = {"id": plan_id, "year": year}
    sales, exp = logo_sources(k, engine, [year], logo_db)
    de = _data_end_source(k, engine, logo_db)
    ids = _plan_sources(k, engine, tenant, plan["id"])
    books = k.portal("portal.planKitap", "Plan kitap hedefleri", B.plan_books_stmt(plan["id"]), engine,
                     description="Plandaki her kitabın hedef adedi, cirosu, marjı, segmenti, yayınevi ve ilk yayını.")
    ys, ye = _year_span(B.month_index(year, 1), B.month_index(year, 13))
    act = k.portal("portal.satis", f"Gerçekleşen satış · {year}", B.sales_stmt(ys, ye), engine, origin=sales,
                   description="Kitap × ay net adet ve ciro (Logo'dan okunmuş hâli). Plan dışı kitaplar da buradan.")
    month = k.portal("portal.satisAy", f"Ay ay net ciro · {year}", B.month_sales_stmt(year), engine, origin=sales,
                     description="Şirket ay ay net cirosu, 157 ile başlayan ticari ürünler hariç.")
    depts = k.portal("portal.departman", "Departman bütçesi satırları", B.depts_stmt(plan["id"]), engine,
                     description="Departman × hesap aylık bütçeleri.")
    gider = k.portal("portal.gider", f"Gerçekleşen gider · {year}", B.expenses_stmt(ys, ye), engine, origin=exp,
                     description="Departman × hesap × ay gider (Logo'dan okunmuş hâli).")
    base = [ids["plan"], books] + ([de] if de else [])
    beklenen = k.hesap("beklenen", F_BEKLENEN, base)
    gercek = k.hesap("gercek", F_NET + " " + F_GERCEK, [act])
    oran = k.hesap("oran", F_ORAN, [beklenen, gercek])
    return {
        "plan.totals": k.hesap("planToplam", F_PLAN_TOPLAM, [ids["plan"], ids["segment"], ids["program"], ids["gider"]]),
        "plan.params": k.hesap("parametre", F_PARAM, [ids["plan"]]),
        "plan.basis": "hesap:parametre",
        "sirket": k.hesap("sirket", F_SIRKET, [books, act, ids["program"], beklenen, oran]),
        "kitapHedefleri": k.hesap("kitapHedefleri", F_KITAP_HEDEF, [books, act, beklenen, oran]),
        "program": k.hesap("program", F_PROGRAM + " Beklenen = program cirosu × geçen pay.", [ids["program"], ids["plan"]]),
        "hedefDisi": k.hesap("hedefDisi", F_NET + " " + F_HEDEF_DISI, [act, books]),
        "durumlar": k.hesap("durumlar", F_DURUM, [books, act, oran]),
        "uyariKapsam": k.hesap("uyariKapsam", F_KAPSAM, [books, ids["plan"]]),
        "segmentler[]": k.hesap("grup", "Segment ve yayınevi satırı: o gruptaki plan kitaplarının hedef, beklenen ve "
                                        "gerçekleşen toplamı; oran ve durum aynı kuralla.", [books, act, beklenen, oran]),
        "yayinevleri[]": "hesap:grup",
        "aylar[]": k.hesap("aylar", F_AYLAR, [ids["plan"], ids["segment"], ids["program"], month]),
        "gider": k.hesap("gider", F_GIDER + " " + F_DEPT, [depts, gider]),
        "gecenPay": k.hesap("gecenPay", F_GECEN, [ids["plan"]] + ([de] if de else [])),
        "esik": "hesap:gecenPay",
    }


def for_books(engine: Any, tenant: str, plan_id: str, out: dict[str, Any], logo_db: Optional[str], *, segment: str = "",
              q: str = "", yayinevi: str = "", sort: str = "ciro") -> P.Kaynaklar:
    k = _new(engine)
    with engine.connect() as c:
        row = B._plan_row(c, tenant, plan_id)
    plan = k.portal("portal.plan", "Plan kaydı", B.plan_stmt(tenant, plan_id), engine,
                    description="Plan parametreleri ve taban dönemi.")
    books = k.portal("portal.kitaplar", "Kitap hedefleri (süzgeçle)",
                     B.books_stmt(row.id, segment=segment, q=q, yayinevi=yayinevi, sort=sort), engine,
                     description="Listede görünen kitapların hedef satırları (semantic_budget_book_targets).")
    fields: dict[str, str] = {
        "items[].adet": k.hesap("hedef", "Hedef adet, ciro ve marj planda saklanan değerdir (öneriden gelir ya da elle "
                                         "düzeltilmiştir); brüt kâr = hedef ciro × marj.", [books]),
        "items[].ciro": "hesap:hedef", "items[].marj": "hesap:hedef", "items[].brutKar": "hesap:hedef",
        "items[].oneri": k.hesap("oneri", F_ONERI, [books, plan]),
    }
    if (out.get("izleme") or {}).get("asof"):
        year = int(row.year)
        sales, _ = logo_sources(k, engine, [year], logo_db)
        de = _data_end_source(k, engine, logo_db)
        ys, ye = _year_span(B.month_index(year, 1), B.month_index(year, 13))
        act = k.portal("portal.satis", f"Gerçekleşen satış · {year}", B.sales_stmt(ys, ye), engine, origin=sales,
                       description="Kitap × ay net adet, ciro, maliyet (Logo'dan okunmuş hâli).")
        beklenen = k.hesap("beklenen", F_BEKLENEN, [books, plan] + ([de] if de else []))
        gercek = k.hesap("gercek", F_NET + " " + F_GERCEK, [act])
        oran = k.hesap("oran", F_ORAN, [beklenen, gercek])
        fields.update({
            "items[].izleme.beklenenAdet": beklenen, "items[].izleme.beklenenCiro": beklenen,
            "items[].izleme.gercekAdet": gercek, "items[].izleme.gercekCiro": gercek,
            "items[].izleme.gercekMarj": k.hesap("gercekMarj", F_MARJ, [act]),
            "items[].izleme.oranAdet": oran, "items[].izleme.oranCiro": oran,
            "izleme": k.hesap("gecenPay", F_GECEN, [plan] + ([de] if de else [])),
        })
    k.alanlar(fields)
    return k


def for_program(engine: Any, tenant: str, plan_id: str) -> P.Kaynaklar:
    k = _new(engine)
    with engine.connect() as c:
        row = B._plan_row(c, tenant, plan_id)
    prog = k.portal("portal.program", "Yeni kitap programı", B.program_stmt(row.id), engine,
                    description="Yayınevi başına beklenen, bilinen ve ek başlık; başlık başına adet, ciro, marj.")
    k.alanlar({"items[]": k.hesap("program", F_PROGRAM, [prog])})
    return k


def for_departments(engine: Any, tenant: str, plan_id: str, out: dict[str, Any], logo_db: Optional[str]) -> P.Kaynaklar:
    k = _new(engine)
    with engine.connect() as c:
        row = B._plan_row(c, tenant, plan_id)
    depts = k.portal("portal.departman", "Departman bütçesi satırları", B.depts_stmt(row.id), engine,
                     description="Departman × hesap aylık bütçe; öneri = taban döneminin aynı ayı × (1 + gider artışı).")
    fields = {"items[].aylar": k.hesap("butce", "Aylık bütçe planda saklanır (öneri: taban döneminin aynı takvim ayı "
                                                "gideri × (1 + gider artışı), ya da elle); yıllık = Σ aylık.", [depts]),
              "items[].yillik": "hesap:butce", "items[].oneri": "hesap:butce"}
    if out.get("asof"):
        year = int(row.year)
        _, exp = logo_sources(k, engine, [year], logo_db)
        ys, ye = _year_span(B.month_index(year, 1), B.month_index(year, 13))
        act = k.portal("portal.gider", f"Gerçekleşen gider · {year}", B.expenses_stmt(ys, ye), engine, origin=exp,
                       description="Departman × hesap × ay gider (Logo'dan okunmuş hâli).")
        g = k.hesap("giderGercek", F_GIDER, [act])
        fields.update({"items[].izleme.gercek": g, "items[].izleme.gercekAylar": g,
                       "items[].izleme.butceDonem": k.hesap("kullanim", F_DEPT, [depts, act]),
                       "items[].izleme.kullanim": "hesap:kullanim", "items[].izleme.buAyKullanim": "hesap:kullanim"})
    k.alanlar(fields)
    return k


def for_compare(engine: Any, tenant: str, year: int, out: dict[str, Any], logo_db: Optional[str]) -> P.Kaynaklar:
    k = _new(engine)
    k.portal("portal.planlar", "Yılın planları (arşiv hariç)", B.plans_stmt(tenant, year, without_archive=True), engine,
             description="Karşılaştırılan planlar.")
    fields = _per_plan_totals(k, engine, tenant, out.get("items") or [], "portal.planlar")
    end = B.data_end(engine)
    if out.get("taban") and end:
        w = B.window(int(year), end)
        sales, exp = logo_sources(k, engine, w["years"], logo_db)
        ys, ye = _year_span(w["start"], w["end"])
        act = k.portal("portal.satis", f"Taban dönemi satışları · {w['label']}", B.sales_stmt(ys, ye), engine,
                       origin=sales, description="Pencere içindeki aylar hesapta süzülür.")
        gid = k.portal("portal.gider", f"Taban dönemi giderleri · {w['label']}", B.expenses_stmt(ys, ye), engine,
                       origin=exp, description="Pencere içindeki aylar hesapta süzülür.")
        fields["taban"] = k.hesap("taban", F_NET + " " + F_TABAN, [act, gid])
    k.alanlar(fields)
    return k


def for_deviations(engine: Any, tenant: str, year: int, *, status: str = "acik", kind: str = "", scope: str = "",
                   module: str = "") -> P.Kaynaklar:
    k = _new(engine)
    a = k.portal("portal.uyarilar", "Bütçe uyarıları", B.deviations_stmt(tenant, year, status=status, kind=kind,
                                                                           scope=scope, module=module), engine,
                 description="Saatlik denetimin yazdığı uyarılar (semantic_budget_alerts).")
    k.alanlar({"items[]": k.hesap("uyari", F_UYARI, [a])})
    return k


#: Rakam olmayan sayılar (yıl, sürüm, sayfa, ay numarası): kapsam denetiminde atlanır.
NOT_RAKAM = ("year", "years", "total", "page", "pageSize", "items[].year", "items[].version", "plan.year",
             "plan.version", "aylar[].ay", "aylar[].gecen")
