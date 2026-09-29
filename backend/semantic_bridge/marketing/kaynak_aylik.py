"""M18 Aylık pazarlama planı ve satış föyü: ekrandaki her rakamın sorgu bilgisi (ortak sözleşme `provenance.py`).

Ay ekranı (`/months/{dönem}`), çakışmalar, hedef açığı paneli, ay geçmişi, föy listesi ve tek föy. Ay planının kalemleri
taslak kurulurken kaynaklardan yazılır (CRM yeni kitaplar, özel günler, kampanyalar, bölge hedefleri; M15/M17 onaylı plan
satırları; bütçe planının ay hedefi); ekranda gösterilen SQL kalem tablosunun okumasıdır, kalemi dolduran CRM ve portal
sorguları `origin`dir. Önceki ay gerçekleşmesi bütçe modülünün Logo satış önbelleğinden; föy fiyat karşılaştırması
Logo'dan (çalışmış metin föy okumasında kaydedilir).
"""
from __future__ import annotations

from typing import Any, Optional

from semantic_bridge import pazarlama_kaynak as PK
from semantic_bridge import provenance as P
from semantic_bridge.marketing import core as C
from semantic_bridge.marketing import foy as F
from semantic_bridge.marketing import monthly as M
from semantic_bridge.marketing import monthly_gaps as MG
from semantic_bridge.marketing import plans as PL
from semantic_bridge.marketing import sources as S

NOT_RAKAM = ("surum", "plan.surum", "plan.lines[].sira", "plan.materials[].surum", "items[].sira", "hedef.year",
             "hedef.version", "total", "zorunlu")

F_KALEM = ("Ay planı kalemleri taslak kurulurken kaynaklardan yazılır: yayın günü bu aya düşen CRM yeni kitapları, onaylı "
           "yeni kitap ve backlist planlarının bu aya düşen kanal satırları (tutar satırdan), CRM özel günleri (bağlı kitap "
           "sayısı), CRM kampanyaları (planlanan / gerçekleşen ciro, ürün sayısı, iskonto); yeni kitapta bu ayın hedefi "
           "(bütçe planı), CRM bölge hedefi ve açık sapma uyarısı. Elle eklenen ve düzeltilen kalemler korunur.")
F_SAYILAR = "Kalem sayıları = ay planı kalemlerinin türe göre sayısı; çakışma = çakışma işareti olan kalem sayısı."
F_HEDEF = ("Ay hedefi = yürürlükteki bütçe planında her kitabın yıllık hedefinin bu aya düşen payı (taban döneminin aylık "
           "dağılımı), segment (yeni / backlist) başına toplam; pay = segment cirosu ÷ ay toplamı.")
F_ONCEKI = ("Önceki ay hedefe oran = önceki ayda hedefi olan kitapların gerçekleşen net cirosu ÷ aynı kitapların o ayki "
            "hedefi (segment başına ve toplam). Gerçekleşen Logo faturalı satış (bütçe modülünün önbelleği); şirket cirosu "
            "o ayın bütün kitaplarının net cirosu (157 ile başlayan ticari ürünler hariç).")
F_ISLER = "Önceki ay işleri = onaylı pazarlama planlarının o aya düşen işleri, duruma göre sayı (yapıldı / toplam)."
F_BUTCE = ("Bütçe önerisi: çerçeve (elle, aylık bütçe ayarı ya da oran × ay hedef cirosu) segment ağırlıklarına bölünür; "
           "ağırlık = segmentin hedef payı × (1 + hedefin altında kalınan pay, önceki ay oranından); kanal payı geçmiş CRM "
           "pazarlama harcamasından. Onaylanan tutar elle girilir; toplam = Σ tutar (onaylı yoksa öneri).")
F_FOY = ("Föy sayıları = dönemin föy kayıtlarından: toplam (ay dışı hariç), onaylı, onayda, eksik alanlı, uyumsuz (engelleyen "
         "CRM–Logo farkı), eski (CRM değişti), hazır (eksik ve uyumsuz değil).")
F_CAKISMA = "Çakışma: aynı hafta aynı kitaplıkta iki lansman ya da üst üste binen kampanya kalemleri."
F_ACIK = ("Hedefin altında = bütçe modülünün açık kitap sapma uyarıları (bu modüle açılmış; eşik ve hesap orada): oran = "
          "gerçekleşen ÷ beklenen, eksik = beklenen − gerçekleşen. Planlı = ayın kalemlerinde ya da bu aya düşen, "
          "atlanmamış pazarlama planı işlerinde stok kodu olan kitap. Liste = hedefin altında olup planlı olmayanlar.")
F_UYUMSUZ = ("Uyumsuzluk: CRM KDV dahil fiyatı Logo fiyatından (ayardaki tanım: satış satırı ya da satış fiyat listesi) "
             "tolerans üstü farklıysa, taslak / kapak fiyatı KDV dahil fiyattan farklıysa, barkod ISBN'den farklı ya da "
             "geçersizse. Değerler föy CRM'den okunurken yazıldı.")


def _crm_month(k: P.Kaynaklar, schema: str, donem: str, items: list[dict[str, Any]]) -> list[str]:
    first, last = M.bounds(donem)
    db = PK.crm_db()
    ids = [k.sorgu("aylik.crm.yeni", "CRM yeni kitaplar (yayın günü bu ay)", "crm", S.new_books_sql(schema, first, last),
                   database=db, period=M.label(donem)),
           k.sorgu("aylik.crm.ozelgun", "CRM özel günleri ve bağlı kitap sayısı", "crm", S.all_special_days_sql(schema),
                   database=db),
           k.sorgu("aylik.crm.kampanya", "CRM kampanyaları (ay ile kesişen)", "crm", S.campaigns_sql(schema, first, last),
                   database=db, period=M.label(donem),
                   description="Planlanan ve gerçekleşen ciro, ek / net iskonto, ürün sayısı kampanya kartından.")]
    y, m = int(donem[:4]), int(donem[5:7])
    yv = S.REGION_TARGET_YEAR.get(y)
    codes = sorted({x["stokKodu"] for x in items if x.get("tur") == "yeni" and x.get("kaynak") == "crm-kitap" and x.get("stokKodu")})
    if yv is not None and codes:
        for i in range(0, len(codes), 500):
            ids.append(k.sorgu(f"aylik.crm.bolge.{i // 500 + 1}", "CRM bölge satış hedefleri (bu ay)", "crm",
                               S.region_targets_sql(schema, yv, m, codes[i:i + 500]), database=db, period=M.label(donem),
                               description="Yalnız bilgi: bütçe planı hedefiyle ilişkisi ölçülmedi."))
    return ids


def for_month(engine: Any, tenant: str, schema: str, v: dict[str, Any], logo_db: Optional[str]) -> P.Kaynaklar:
    donem = v["donem"]
    prev = v.get("onceki") or M.shift(donem, -1)
    k = P.Kaynaklar(data_end=PL.data_end(engine))
    plan = v.get("plan")
    items = v.get("items") or []
    crm = _crm_month(k, schema, donem, items)
    m15 = k.portal("aylik.m15", "Onaylı yeni kitap ve backlist planları", C.plans_stmt(tenant, durum="onayli"), engine,
                   description="Bu aya düşen kanal satırları (tutar) kaleme alınır; satırlar her planın satır tablosundan.")
    y = int(donem[:4])
    hedef = PK.hedefler(k, engine, tenant, {y: []}, prefix="aylik.butce")
    dev = k.portal("aylik.sapma", f"Açık kitap sapma uyarıları · {y}", _dev_stmt(tenant, y), engine,
                   description="Bütçe modülünün açık sapma uyarıları (bu modüle açılmış): oran, eksik ciro.")
    origin = crm + [m15, dev] + hedef
    fields: dict[str, str] = {}
    if plan:
        pid = plan["id"]
        head = k.portal("aylik.plan", "Ay planı kaydı", C.plan_stmt(tenant, pid), engine,
                        description="Plan başlığı, durumu, bütçe çerçevesi ve toplamı (semantic_mkt_plans).")
        kalem = k.portal("aylik.kalem", "Ay planı kalemleri", M.items_stmt(pid), engine, origin=origin,
                         description="Takvim kalemleri: tür, kaynak, hafta, kanal, bütçe, ayrıntı (semantic_mkt_month_items).")
        butce = k.portal("aylik.butce", "Ay bütçesi (segment × kanal)", M.budget_stmt(pid), engine,
                         description="Öneri, onaylanan, hedef payı, önceki ay oranı (semantic_mkt_month_budget).")
        lines = k.portal("aylik.plan.satir", "Ay planı bütçe satırları", C.lines_stmt(pid), engine)
        fields.update({"plan": k.hesap("plan", "Plan bütçesi = Σ bütçe satırı tutarı; çerçeve " + F_BUTCE_KISA, [head, lines]),
                       "items[]": k.hesap("kalem", F_KALEM, [kalem]),
                       "cakismaSayisi": k.hesap("cakisma", F_CAKISMA + " " + F_SAYILAR, [kalem]),
                       "sayilar": "hesap:cakisma",
                       "budget[]": k.hesap("butce", F_BUTCE, [butce] + hedef)})
    fields["hedef"] = k.hesap("hedef", F_HEDEF, hedef or [m15])
    py = int(prev[:4])
    pm = int(prev[5:7])
    act = PK.butce_satis(k, engine, "aylik.onceki.gercek", f"Önceki ay gerçekleşmesi · {M.label(prev)}",
                         M.month_actuals_stmt(py, pm), [py], logo_db)
    ptg = PK.hedefler(k, engine, tenant, {py: []}, prefix="aylik.onceki.butce") if py != y else hedef
    isler = k.portal("aylik.onceki.isler", f"Önceki ay işleri · {M.label(prev)}", M.task_stats_stmt(tenant, prev), engine,
                     description="Onaylı planların o aya düşen işleri, durum × kanal sayısı.")
    onceki = k.hesap("onceki", F_ONCEKI, [act] + ptg)
    fields.update({"oncekiAy": onceki, "oncekiAy.isler": k.hesap("isler", F_ISLER, [isler])})
    foy = k.portal("aylik.foy", "Dönemin satış föyleri", F.month_stmt(tenant, donem), engine,
                   description="Föy durumu, eksik alanlar ve uyumsuzluklar (semantic_mkt_foy).")
    fields["foy"] = k.hesap("foy", F_FOY, [foy])
    k.alanlar(fields)
    return k


F_BUTCE_KISA = "(elle, aylık bütçe ayarı ya da oran × ay hedef cirosu)."


def _dev_stmt(tenant: str, year: int):
    from semantic_bridge import budget as B

    return B.deviations_stmt(tenant, year, status="acik", scope="kitap", module="M18")


def for_conflicts(engine: Any, tenant: str, plan_id: str) -> P.Kaynaklar:
    k = P.Kaynaklar()
    kalem = k.portal("aylik.kalem", "Ay planı kalemleri", M.items_stmt(plan_id), engine)
    ref = k.hesap("cakisma", F_CAKISMA + " Toplam = çakışma işareti olan kalem sayısı.", [kalem])
    k.alanlar({"items[]": ref, "total": ref})
    return k


def for_gaps(engine: Any, tenant: str, donem: str) -> P.Kaynaklar:
    k = P.Kaynaklar(data_end=PL.data_end(engine))
    y = int(donem[:4])
    dev = k.portal("aylik.sapma", f"Açık kitap sapma uyarıları · {y}", _dev_stmt(tenant, y), engine,
                   description="Bütçe modülünün açık sapma uyarıları (bu modüle açılmış).")
    ins = [dev]
    h = M.find_plan(engine, tenant, donem)
    if h:
        ins.append(k.portal("aylik.kalem", "Ay planı kalemleri", M.items_stmt(h["id"]), engine))
    ins.append(k.portal("aylik.isler", "Bu aya düşen plan işleri (stok kodlu)", MG.planned_tasks_stmt(tenant, donem), engine))
    ref = k.hesap("acik", F_ACIK, ins)
    k.alanlar({"items[]": ref, "hedefAlti": ref, "planli": ref, "plansiz": ref, "paragrafDusen": ref})
    return k


def for_month_events(engine: Any, plan_id: str) -> P.Kaynaklar:
    k = P.Kaynaklar()
    k.alanlar({"items[]": k.portal("aylik.gecmis", "Ay planı geçmişi", C.events_stmt(plan_id), engine)})
    return k


def _logo_price(k: P.Kaynaklar, logo: Any, codes: list[str], logo_db: Optional[str],
                runs: Optional[list[dict[str, Any]]] = None) -> list[str]:
    """`runs`: eşitleme kaydındaki çalışmış Logo SQL'leri (verilmezse bu süreçte kaydedilenler)."""
    ids = []
    if runs is None:
        runs = logo.runs_for(codes) if logo is not None else []
    for i, r in enumerate(runs):
        try:
            ids.append(k.sorgu(f"foy.logo.fiyat.{i + 1}", "Logo fiyatı (föy karşılaştırması)", "logo", r["sql"],
                               database=logo_db, rows=r.get("rows"), ms=r.get("dbMs"), ran_at=r.get("at"),
                               description="Föy fiyatının Logo karşılığı (ayardaki fiyat tanımıyla)."))
        except P.ProvenanceError:
            continue
    return ids


F_ESITLEME = ("Eşitleme kaydı: günlük pazarlama turunda (bu ay ve gelecek ay), «CRM'den yenile»de ya da dönem ilk açıldığında "
              "CRM ve Logo okunur, föyler yazılır; bu kayıt o okumanın zamanını, kitap künyesini (yazar, yayınevi, kitaplık, "
              "yayın günü, sorumlu), notlarını ve çalışmış Logo sorgularını tutar. Ekran istek anında CRM'e ve Logo'ya gitmez.")


def _sync_origin(k: P.Kaynaklar, schema: str, donem: str, sync: dict[str, Any], logo_db: Optional[str]) -> list[str]:
    """Eşitlemede çalışmış CRM/Logo sorguları: yeni kitaplar (ay aralığı), föy alanları (eşitlenen kodlar, sıralı, 500'lük
    parçalar — `Crm.foy_books` ile aynı bölme) ve kayıttaki Logo SQL metinleri (satır, süre, an ile)."""
    first, last = M.bounds(donem)
    ids = [k.sorgu("foy.crm.yeni", "CRM yeni kitaplar (yayın günü bu ay)", "crm", S.new_books_sql(schema, first, last),
                   database=PK.crm_db(), period=M.label(donem))]
    codes = sorted(sync.get("kitap") or {})
    for i in range(0, len(codes), 500):
        ids.append(k.sorgu(f"foy.crm.alan.{i // 500 + 1}", "CRM föy alanları", "crm", S.foy_books_sql(schema, codes[i:i + 500]),
                           database=PK.crm_db(), description="Künye, fiyat, barkod, hedef kitle ve tanıtım metinleri."))
    ids += _logo_price(k, None, codes, logo_db, runs=list(sync.get("logo") or []))
    return ids


def for_foy_list(engine: Any, tenant: str, schema: str, out: dict[str, Any], logo: Any, logo_db: Optional[str],
                 sync: Optional[dict[str, Any]] = None) -> P.Kaynaklar:
    """`sync`: dönemin eşitleme kaydı (`foy.read_sync`); verilirse köken onda çalışmış CRM/Logo sorgularıdır."""
    donem = out["donem"]
    k = P.Kaynaklar(data_end=PL.data_end(engine))
    first, last = M.bounds(donem)
    if sync:
        origin = _sync_origin(k, schema, donem, sync, logo_db)
        origin.append(k.portal("foy.esitleme", "Föy eşitleme kaydı (son CRM/Logo okuması)", F.sync_stmt(tenant, donem), engine,
                               origin=list(origin), description=F_ESITLEME))
    else:
        codes = sorted({r["stokKodu"] for r in out.get("items") or [] if r.get("stokKodu")})
        origin = [k.sorgu("foy.crm.yeni", "CRM yeni kitaplar (yayın günü bu ay)", "crm", S.new_books_sql(schema, first, last),
                          database=PK.crm_db(), period=M.label(donem))]
        for i in range(0, len(codes), 500):
            origin.append(k.sorgu(f"foy.crm.alan.{i // 500 + 1}", "CRM föy alanları", "crm", S.foy_books_sql(schema, codes[i:i + 500]),
                                  database=PK.crm_db(), description="Künye, fiyat, barkod, hedef kitle ve tanıtım metinleri."))
        origin += _logo_price(k, logo, codes, logo_db)
    foy = k.portal("foy.liste", "Dönemin satış föyleri", F.month_stmt(tenant, donem), engine, origin=origin,
                   description="Föyler CRM'den okunurken yazılır; eksik alan ve uyumsuzluk o an hesaplanır (semantic_mkt_foy).")
    ref = k.hesap("foy", F_FOY, [foy])
    k.alanlar({"kpi": ref, "items[]": k.hesap("uyumsuz", F_UYUMSUZ, [foy]),
               "gonderimler[]": k.portal("foy.gonderim", "Föy paketi gönderimleri", F.sends_stmt(tenant, donem), engine)})
    return k


def for_foy(engine: Any, tenant: str, schema: str, out: dict[str, Any], logo: Any, logo_db: Optional[str],
            sync: Optional[dict[str, Any]] = None) -> P.Kaynaklar:
    """`sync`: föy eşitleme kaydından okunduysa (CRM'e gidilmedi) o kayıt; köken eşitlemede çalışmış sorgulardır."""
    stok, donem = out["stokKodu"], out.get("donem")
    k = P.Kaynaklar(data_end=PL.data_end(engine))
    if sync and donem:
        origin = _sync_origin(k, schema, donem, sync, logo_db)
        origin.append(k.portal("foy.esitleme", "Föy eşitleme kaydı (yayın günü kaynağı, sorumlu)", F.sync_stmt(tenant, donem),
                               engine, origin=list(origin), description=F_ESITLEME))
    else:
        origin = [k.sorgu("foy.crm.alan", "CRM föy alanları", "crm", S.foy_books_sql(schema, [stok]), database=PK.crm_db(),
                          description="Künye, fiyat, barkod, hedef kitle ve tanıtım metinleri."),
                  k.sorgu("foy.crm.kitap", "CRM kitap kartı (yayın günü)", "crm", S.book_sql(schema, stok), database=PK.crm_db())]
        origin += _logo_price(k, logo, [stok], logo_db)
    row = k.portal("foy.kayit", "Föy kaydı", F.row_stmt(tenant, stok, donem), engine, origin=origin,
                   description="Föy alanları (kaynağıyla), eksikler, uyumsuzluklar, onay (semantic_mkt_foy).")
    alan = k.hesap("alan", "Föy alanları CRM kitap kartından (kaynağı her alanda yazılı) ya da elle girildi.", [row])
    k.alanlar({"alanlar[]": alan, "uyumsuzluk[]": k.hesap("uyumsuz", F_UYUMSUZ, [row]), "logo": "hesap:uyumsuz",
               "engelleyen": "hesap:uyumsuz", "crmTodo[]": alan})
    return k
