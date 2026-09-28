"""M16 Lansman: ekrandaki her rakamın sorgu bilgisi (ortak sözleşme `provenance.py`).

Lansman rakamları iki katmandır: günlük okuma işi (`launch_track.refresh`, saatlik CRM + günlük Logo) CRM sipariş,
dağılım, açık sipariş, bekleyen ürün, sipariş anındaki stok; Logo faturalı satış, depo stoku ve emsallerin ilk günlerini
okuyup `semantic_mkt_launch_daily` gün satırlarına ve lansman özetine yazar; ekran bu tablolardan okur. Gösterilen SQL
uçta çalışan portal okumasıdır (`launch.*_stmt`); okuma işinin çalıştırdığı CRM/Logo metinleri (özette saklanan,
değerleri yerinde) `origin`dir.
"""
from __future__ import annotations

from typing import Any, Optional

from semantic_bridge import pazarlama_kaynak as PK
from semantic_bridge import provenance as P
from semantic_bridge.marketing import core as C
from semantic_bridge.marketing import launch as L
from semantic_bridge.marketing import launch_sources as S

NOT_RAKAM = ("gun", "seri[].d", "items[].gun", "items[].rakam.gun", "review.gun", "review.rakam.gun", "materials[].surum",
             "lansman.gun")

#: Özetteki SQL anahtarı → (bağlantı, başlık, açıklama)
ORIGINS = {
    "siparis": ("crm", "CRM sipariş satırları (gün gün)", "Stok kodu × İstanbul günü: sipariş adedi, satır, dağılım ve sevk "
                "adedi. Sayılmayan sipariş durumları hariç. Birlikte okunan açık lansmanların hepsi için tek okuma."),
    "dagilim": ("crm", "CRM dağılım siparişleri", "Pencere boyunca dağılım siparişi (sipariş tipi 2): adet, sipariş, bayi."),
    "acikSiparis": ("crm", "CRM açık sipariş", "Baskı Öneri ile aynı açık sipariş tanımı, lansman kitaplarıyla süzülmüş."),
    "bekleyenUrun": ("crm", "CRM bekleyen ürün", "CRM «Bekleyen Ürün» kayıtları (durum 1)."),
    "siparisAnindakiStok": ("crm", "CRM sipariş anındaki depo stoku", "Kitabın en son siparişindeki depo stoku (yedek sinyal)."),
    "fatura": ("logo", "Logo faturalı satış (gün gün)", "Önce stok kodları kayıt numarasına çevrilir, sonra faturalı satış "
               "satırları (TRCODE 7/8/9 satış, 2/3 iade eksi; net ciro = LINENET) gün kırılımıyla. Yıl başına ayrı firma."),
    "depo": ("logo", "Logo depo stoku", "Baskı Öneri ile aynı depo görünümü; kitap eşlemesi okumadan sonra yapılır."),
    "emsal": ("logo", "Logo emsal kitapların ilk günleri", "Emsal kitabın ilk satış gününden itibaren faturalı net adet (gün gün)."),
}

F_SERI = ("Gün satırı = okuma işinin yazdığı değer: sipariş, dağılım, sevk (CRM, İstanbul günü); faturalı net adet ve ciro "
          "(Logo, veri sonuna kadar); hedef payı = yürürlükteki bütçe planında o ayın kitap hedefi ÷ ayın gün sayısı; açık "
          "sipariş, bekleyen ürün, depo = o günün anlık okuması. Birikimli = yayın gününden o güne Σ.")
F_TOPLAM = ("Toplamlar = yayın gününden bugüne (ilk 7 / 30 gün) Σ sipariş, Σ faturalı adet ve ciro, Σ hedef payı; emsal "
            "ortalaması = emsallerin ilk 7 / 30 gün faturalı net adedinin ortalaması (yalnız o süreyi tamamlamış emsaller).")
F_SINYAL = ("Sinyal (kural, model yok): hedef payına oran = faturalı satış ÷ Logo verisinin kapsadığı günlerin hedef payı "
            "(Logo verisi yoksa sipariş ÷ hedef payı); eşik altı kırmızı, eşik ile %100 arası sarı. Açık sipariş > depo "
            "stoku ya da yayından sonra dağılım yoksa kırmızı. Depo = CRM en son sipariş anındaki stok Logo verisinden "
            "yeniyse o, değilse Logo depo görünümü.")
F_DAGILIM = "Dağılım = lansman penceresinde dağılım tipli siparişlerin adedi; bayi = farklı cari sayısı; sipariş = farklı sipariş."
F_GUN = "D+N = bugün − yayın günü (gün); geciken madde = bugünden önce tarihli, bekleyen kontrol listesi maddesi."
F_ETKINLIK = ("Etkinlik toplamı = CRM'de kitaba bağlı etkinlikler + portalda elle girilenler; tamamlanan = CRM durumu "
              "«Tamamlandı» ya da elle kayıt; katılımcı, satılan, gelir, gider tamamlananların toplamı (portalda girilen "
              "sonuç CRM değerinin yerine geçer).")
F_RAPOR = ("Değerlendirme tablosu değerlendirme günü hazırlanıp saklanır: her satır günlük tablodan (pencere içindeki Σ) ya "
           "da okuma özetinden (dağılım, açık sipariş, depo, emsal ortalaması); oranlar = pay ÷ payda; etkinlik, medya ve "
           "kontrol listesi sayıları kendi kayıtlarından. Zeki AI metni bu tablodaki rakamı aynen kullanır.")
F_MEDYA = "Medya sayıları = portalda girilen yansımalar + (açıksa) basın-web taramasının kitaba bağlı haberleri, tona göre."
F_RISK = ("Risk bayrağı (kural): stok çatışması ya da dağılım yoksa ya da iki neden birden varsa yüksek; hedef payı eşik "
          "altı, emsal eğrisinin altında kalan satış ya da yayından N gün sonra sipariş yoksa dikkat.")


def origins(k: P.Kaynaklar, full: dict[str, Any], logo_db: Optional[str]) -> list[str]:
    sq = ((full.get("ozet") or {}).get("sql")) or {}
    ids: list[str] = []
    for key, (conn, title, desc) in ORIGINS.items():
        v = sq.get(key)
        texts = [x for x in (v if isinstance(v, list) else [v]) if x]
        for i, t in enumerate(texts):
            try:
                ids.append(k.sorgu(f"lansman.{key}.{i + 1}", title, conn, t, description=desc,
                                   database=PK.crm_db() if conn == "crm" else logo_db,
                                   ran_at=(full.get("okuma") if conn == "crm" else None)))
            except P.ProvenanceError:
                continue
    return ids


def _hedef(k: P.Kaynaklar, engine: Any, tenant: str, full: dict[str, Any]) -> list[str]:
    ys = sorted({int(y) for y in ((full.get("ozet") or {}).get("hedef") or {}) if str(y).isdigit()})
    y0 = PK.year_of(full.get("yayinGunu"))
    if not ys and y0:
        ys = [y0]
    return PK.hedefler(k, engine, tenant, {y: [full["stokKodu"]] for y in ys}, prefix="lansman.butce") if full.get("stokKodu") else []


def _base(k: P.Kaynaklar, engine: Any, tenant: str, full: dict[str, Any], logo_db: Optional[str]) -> dict[str, Any]:
    org = origins(k, full, logo_db)
    lid = full["id"]
    row = k.portal("lansman.kayit", "Lansman kaydı ve okuma özeti", L.launch_stmt(tenant, lid), engine, origin=org,
                   description="Lansman özeti (semantic_mkt_launches): sinyal, dağılım, emsal, hedef, uyarılar; okuma işi yazar.")
    days = k.portal("lansman.gunluk", "Lansman gün satırları", L.days_stmt(lid), engine, origin=org,
                    description="Gün gün sipariş, dağılım, sevk, faturalı adet ve ciro, hedef payı, açık sipariş, depo "
                                "(semantic_mkt_launch_daily).")
    hedef = _hedef(k, engine, tenant, full)
    return {"org": org, "row": row, "days": days, "hedef": hedef}


def for_launch(engine: Any, tenant: str, full: dict[str, Any], logo_db: Optional[str]) -> P.Kaynaklar:
    k = P.Kaynaklar(data_end=((full.get("ozet") or {}).get("veriSonuLogo")))
    b = _base(k, engine, tenant, full, logo_db)
    tasks = k.portal("lansman.madde", "Kontrol listesi", L.launch_tasks_stmt(full["id"], full["planId"]), engine)
    rev = k.portal("lansman.degerlendirme", "Değerlendirmeler", L.reviews_stmt(full["id"]), engine, origin=[b["days"]])
    plan = k.portal("lansman.plan", "Pazarlama planı (hedef anlık görüntüsü)", L.launch_plan_stmt(full["planId"]), engine)
    sinyal = k.hesap("sinyal", F_SINYAL, [b["days"], b["row"]] + b["hedef"])
    k.alanlar({"sinyal": sinyal, "ozet": sinyal, "gun": k.hesap("gun", F_GUN, [b["row"], tasks]), "tasks[]": tasks,
               "reviews[]": k.hesap("rapor", F_RAPOR, [rev, b["days"]]), "plan": k.hesap("hedef", PK.F_HEDEF, [plan] + b["hedef"]),
               "renk": sinyal})
    return k


def for_tracking(engine: Any, tenant: str, full: dict[str, Any], logo_db: Optional[str]) -> P.Kaynaklar:
    k = P.Kaynaklar(data_end=((full.get("ozet") or {}).get("veriSonuLogo")))
    b = _base(k, engine, tenant, full, logo_db)
    seri = k.hesap("seri", F_SERI, [b["days"]] + b["hedef"])
    sinyal = k.hesap("sinyal", F_SINYAL, [b["days"], b["row"]] + b["hedef"])
    dist = [x for x in b["org"] if x.startswith("lansman.dagilim.")] or [b["row"]]
    k.alanlar({"seri[]": seri, "toplam": k.hesap("toplam", F_TOPLAM, [b["days"], b["row"]] + b["hedef"]), "sinyal": sinyal,
               "depo": sinyal, "dagilim": k.hesap("dagilim", F_DAGILIM, dist + [b["row"]]), "emsal": "hesap:toplam",
               "hedef": k.hesap("hedef", PK.F_HEDEF, b["hedef"] or [b["row"]]), "lansman": k.hesap("gun", F_GUN, [b["row"]])})
    return k


def for_events(engine: Any, full: dict[str, Any], schema: str) -> P.Kaynaklar:
    k = P.Kaynaklar()
    ins = [k.portal("lansman.etkinlik.portal", "Portalda girilen etkinlik sonuçları", L.events_stmt(full["id"]), engine,
                    description="Katılımcı, satılan, gelir, gider (yalnız sayı; katılımcının kişisel verisi alınmaz).")]
    if full.get("crmKitapId"):
        try:
            ins.insert(0, k.sorgu("lansman.etkinlik.crm", "CRM kitaba bağlı etkinlikler", "crm", S.events_sql(schema, full["crmKitapId"]),
                                  database=PK.crm_db(), description="Katılımcı kişisel verisi okunmaz, yalnız sayı."))
        except S.SourceError:
            pass
    ref = k.hesap("etkinlik", F_ETKINLIK, ins)
    k.alanlar({"items[]": ref, "toplam": ref})
    return k


def for_media(engine: Any, full: dict[str, Any]) -> P.Kaynaklar:
    k = P.Kaynaklar()
    m = k.portal("lansman.medya", "Portalda girilen medya yansımaları", L.media_stmt(full["id"]), engine)
    ref = k.hesap("medya", F_MEDYA, [m])
    k.alanlar({"items[]": ref, "ton": ref})
    return k


def for_crm_todo(engine: Any, full: dict[str, Any], schema: str) -> P.Kaynaklar:
    k = for_events(engine, full, schema)
    m = k.portal("lansman.medya", "Portalda girilen medya yansımaları", L.media_stmt(full["id"]), engine)
    k.alanlar({"items[]": k.hesap("todo", "CRM'e işlenecek = portalda girilen etkinlik sonucu ve medya kaydı (CRM'de yok ya "
                                          "da farklı).", [m, "hesap:etkinlik"])})
    return k


def for_reviews(engine: Any, tenant: str, full: dict[str, Any], logo_db: Optional[str]) -> P.Kaynaklar:
    k = P.Kaynaklar(data_end=((full.get("ozet") or {}).get("veriSonuLogo")))
    b = _base(k, engine, tenant, full, logo_db)
    rev = k.portal("lansman.degerlendirme", "Değerlendirme kayıtları (rakam tablosu)", L.reviews_stmt(full["id"]), engine,
                   origin=[b["days"], b["row"]], description="D+7 / D+30 rakam tablosu hazırlandığı anda saklanır "
                                                            "(semantic_mkt_launch_reviews).")
    ev = k.portal("lansman.etkinlik.portal", "Portalda girilen etkinlik sonuçları", L.events_stmt(full["id"]), engine)
    md = k.portal("lansman.medya", "Portalda girilen medya yansımaları", L.media_stmt(full["id"]), engine)
    ref = k.hesap("rapor", F_RAPOR, [rev, b["days"], b["row"], ev, md] + b["hedef"])
    k.alanlar({"items[]": ref, "review": ref})
    return k


def for_list(engine: Any, tenant: str, out: dict[str, Any], **filters: Any) -> P.Kaynaklar:
    k = P.Kaynaklar()
    ls = k.portal("lansman.liste", "Lansmanlar", L.list_stmt(tenant, **filters), engine,
                  description="Lansman kayıtları ve okuma özetleri (sinyal, renk, uyarılar).")
    ids = [x["id"] for x in out.get("items") or []]
    od = k.portal("lansman.geciken", "Geciken kontrol listesi maddeleri", L.overdue_stmt(ids, C.today().isoformat()), engine)
    k.alanlar({"items[]": k.hesap("liste", F_GUN + " " + F_SINYAL, [ls, od]), "items[].risk": k.hesap("risk", F_RISK, [ls]),
               "total": "hesap:liste"})
    return k


def for_today(engine: Any, tenant: str) -> P.Kaynaklar:
    k = P.Kaynaklar()
    t = k.portal("lansman.bugun", "Bugünün ve geciken maddeler", L.today_stmt(tenant, C.today().isoformat()), engine)
    ref = k.hesap("bugun", "Bugün ve daha önce tarihli, bekleyen kontrol listesi maddeleri (açık lansmanlarda); gün farkı "
                           "= madde tarihi − yayın günü.", [t])
    k.alanlar({"items[]": ref, "total": ref})
    return k
