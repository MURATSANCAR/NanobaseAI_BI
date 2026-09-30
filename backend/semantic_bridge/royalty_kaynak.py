"""M54 Telif dönemi ve haklar: ekrandaki her rakamın sorgu bilgisi (ortak sözleşme `provenance.py`).

Kaynak kimliklerinin öneki: telif dönemi `telif.`, haklar `haklar.`.

- **Koşu rakamları** (kapsam, durum sayıları, ödenecek toplamlar, satır hesabı, avans portföyü, beyanname, ödeme
  listesi) portal tablolarındadır (semantic_royalty_*); gösterilen SQL uçta çalışan ifadedir (`royalty.*_stmt`).
  Tabloyu dolduran asıl CRM/Logo sorguları koşunun hesabında ÇALIŞAN metindir: hesap işi her sorguyu (metin, satır,
  süre, an) koşunun kapsam kaydına yazar (`royalty.run_queries`) ve burada `origin` olur. Bu değişiklikten önce
  hesaplanmış koşuda kayıt yoktur; açıklama bunu söyler (yeniden hesaplatınca görünür).
- **Yenilemeler, hak kartı, kitap arama** istek anında CRM'den okunur; o istekte çalışan metin kaydedilir.
- **Zeki AI önerisi** (yenileme gerekçesi, hak açıklaması sınıfı): «i» yalnız önerinin dayandığı olguların sorgusunu
  gösterir; öneri rakam üretmez.

Kişisel veri: SQL metni gösterilir, sonuç satırı (ad, e-posta, tutar) kayda girmez.
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

from semantic_bridge import contracts_kaynak as CK
from semantic_bridge import provenance as P
from semantic_bridge import royalty as RY
from semantic_bridge import royalty_sources as S

# ------------------------------------------------------------------ formüller

F_KAPSAM = ("Kapsam = CRM'de etkin (statecode = 0) Telif Alış (tip 5) sözleşmelerinden ödeme şekli satıştan ya da satıştan "
            "kademeli (Yönetim ayarı ROYALTY_CRM_PAYMENT_TYPES, varsayılan 2, 7) ve durumu yürürlükte (ROYALTY_CRM_STATUSES, "
            "varsayılan 100000000 Aktif - Sözleşme, 100000007 Aktif - Yenileme) olanlar + portalda açılmış, yürürlükteki "
            "satıştan ödemeli sözleşmeler. Her sözleşme bir satırdır; «CRM N» kapsam sorgusundaki sözleşme sayısı, «portal N» "
            "yalnız portalda açılmış olanlardır.")
F_SAYAC = ("Hesaplandı / İstisna / Hariç = koşu satırlarının durumuna göre sayısı. İstisna: hesabın güvenle yapılamadığı "
           "sözleşme (açık istisna kodu); hariç: gerekçesiyle ya da kendiliğinden (dönem dışı, portal durumu) dışarıda. "
           "Nedene göre sayı = açık (kabul edilmemiş) istisna kodu olan satır sayısı. İstisnalar sekmesinin rozeti aynı sayıdır.")
F_M54 = (" Dönem koşusunun ek kuralları: satış sözleşmenin başladığı aydan itibaren sayılır; avanslı sözleşmede önceki onaylı "
         "hakediş yoksa ve sözleşme dönemden önce başladıysa avans açılış bakiyesi (kazanılmamış kalan avans, tarihli) "
         "girilmeden satır istisnadır; açılış girildiyse etkin avans = açılış + açılış tarihinden önceki onaylı hakedişlerde "
         "düşülen. Sözleşmede stopaj oranı yoksa ve taraflar yalnız kişiyse Yönetim ayarındaki varsayılan stopaj "
         "(ROYALTY_WITHHOLDING_PCT) uygulanır. Kademeli ödemede birikim sözleşme başından okunur (Logo satış görünümlerinin "
         "başladığı yıldan öncesi yoksa kabul edilebilir istisna).")
F_SATIR = CK.F_HAKEDIS + F_M54
F_TOPLAM = ("Ödenecek (para birimi) = «hesaplandı» satırlarının net toplamı; brüt, avans mahsubu ve stopaj aynı satırların "
            "toplamı; sözleşme sayısı bu satırların sayısıdır. Satır hesabı: " + F_SATIR)
F_KUR = ("Dönem sonu kuru: koşuda elle girildiyse o; girilmediyse TCMB'nin dönem sonu günündeki (ya da en çok 10 gün geriye "
         "önceki iş günündeki) döviz alış kuru, tcmb.gov.tr günlük kur dosyasından. Bulunamazsa o para birimindeki sözleşme "
         "istisnadır.")
F_ILERLEME = ("İlerleme: hesap ya da onay işinin yazdığı adım ve işlenen / toplam sözleşme sayısı (her adımda ve 250 "
              "sözleşmede bir yazılır).")
F_KOSULAR = "Koşu listesi: bütün koşular, dönem başına göre yeniden eskiye (tavan yok)."
F_SATIRLAR = ("Satır listesi: koşunun satırları; durum, istisna nedeni ve arama süzgeci uçta uygulanır, «N satır» süzgeçten "
              "geçen satır sayısıdır (sayfa 50 satır). Net = satırın ödenecek neti; hesabı olmayan satırda boştur.")
F_HAK_SAHIBI = ("Beyanname onaylı koşudan hazırlanır: her onaylı satırın brüt, avans mahsubu, stopaj ve neti taraflara, "
                "satırın hesabındaki taraf telifinin toplam içindeki payıyla (telif sıfırsa sözleşmedeki pay, o da yoksa eşit) "
                "bölünür ve hak sahibi başına toplanır; sözleşme sayısı hak sahibinin payı olan onaylı satır sayısıdır. Hak "
                "sahibi / gönderildi / bekleyen = bütün hak sahipleri ve gönderim kaydına göre sayısı; yüzde = gönderilen ÷ "
                "bütün. Liste süzgeci (ad, durum) uçta uygulanır.")
F_ODEME_LISTESI = ("Ödeme listesi: onaylı her satır × taraf; tutar = satır tutarı × taraf payı (beyannamedeki pay kuralı). "
                   "Toplam (para birimi) = satırların toplamı; «N ödeme» = neti sıfırdan büyük satır sayısı. Vade ve ödeme "
                   "durumu sözleşmenin ödeme takviminden (onayda oluşan hakediş ödemesi).")
F_AVANS = ("Avans portföyü son hesaplanan koşudan: avans = sözleşmedeki avans; kalan = koşudaki hesabın mahsuptan sonra kalan "
           "(kazanılmamış) avansı (açılışı girilmemişse boş); dönem telifi = satırın brüt telifi. Yıllık telif hızı = dönem "
           "telifi × 12 ÷ koşunun ay sayısı; kapanma ≈ kalan ÷ yıllık hız (yıl). «Geri dönmesi zor» = kalan > 0 ve (hız yok "
           "ya da kapanma > risk yılı; Yönetim ayarı ROYALTY_ADVANCE_RISK_YEARS, varsayılan 3) ve açılışı girilmiş. "
           "Toplamlar para birimine göre: verilen ve kalan avans toplamı, açılışı girilmemiş ve geri dönmesi zor sözleşme "
           "sayısı. Açılış bakiyesi elle girilir.")
F_ACILIS = ("Avans açılış bakiyesi elle girilir: tutar (o tarihte telifle kapanmamış kalan avans), tarih, gerekçe ve giren; "
            "yeni giriş öncekini geçersiz kılar, geçmiş durur.")
F_YENILEME = ("Yenilemeler: CRM'de etkin, süreli ve bitişi seçilen pencerede (bugün ile bugün + N gün arası; «bitişi geçmiş» "
              "seçiminde bugünden önce) olan bütün tür sözleşmeler. Kalan gün = bitiş − bugün. Yenilenme sıklığı, yayınlanmazsa fesih süresi "
              "ve avans CRM kartından. Karar portalda girilir; bitiş CRM'de değiştiyse eski karar geçersiz sayılır. Sayılar: "
              "penceredeki sözleşme sayısı (süzgeçten sonra) ve karara göre sayılar (süzgeçten önce).")
F_ONERI = ("Zeki AI önerisi yalnız olgulara dayanır. Olgular: CRM sözleşme kartı (bitiş, yenilenme sıklığı) ve kitapların "
           "stok kodları; Logo satış görünümlerinden son 36 ay net satış adedi ve net tutarı ile son 12 ay net adedi (veri "
           "sonunun ayından geriye, iade düşülür); portal koşusundaki kalan avans. Olasılık, modelin kapalı küme seçiminde "
           "(Yenile / Bırak / Yeniden müzakere) seçtiği karara verdiği olasılıktır; metinde olgularda bulunmayan sayı "
           "düşürülür (düşen sayı adedi). Öneri karar değildir.")
F_KOSU_SOZLESME = "Bu sözleşmenin iptal edilmemiş dönem koşularındaki satırları: satır durumu ve ödenecek net."
F_HAK_KARTI = ("Hak kartı: CRM'de kitaba bağlı etkin Telif Alış ve Telif Satış sözleşmeleri (hak bitleriyle), tarafları ve "
               "seçim listesi etiketleri istek anında okunur. Başlıktaki sayı = o türdeki sözleşme sayısı. Hak durumu: "
               "yürürlükteki bütün telif alış sözleşmelerinde hak işaretliyse «var», birinde yoksa «yok», hak notu varsa "
               "«incele».")
F_HAK_KAYDI = "Dil ve ülke hakları portalda elle girilir (hak türü, dil, ülke, başlangıç, bitiş, kaynak sözleşme)."
F_LISANS = ("Verilen lisanslar elle girilir (avans, telif oranı, tahsil edilen, yazar payı %). Yazar payı tutarı = tahsil "
            "edilen × yazar payı % ÷ 100. «N lisans» = süzgeçten (durum, arama) geçen kayıt sayısı.")
F_HARITA = ("Hak haritası: açıklamadan birebir alıntıyla çıkarılan dil, ülke, format, bitiş ve münhasırlık; durum sayısı = "
            "durum başına harita. Harita işi ilerlemesi = işlenen / toplam açıklama. Haritayı telif uzmanı onaylar.")
F_NOTLAR = ("Hak açıklamaları: CRM'de serbest metinli hak açıklaması (new_haklaraciklama) olan etkin Telif Alış sözleşmeleri; "
            "sınıfı Zeki AI kapalı küme seçimiyle önerir (olasılık ≥ 0,70 ve marj ≥ 0,30 ise «öneri», değilse «incele»), "
            "telif uzmanı onaylar. Yüzde = önerilen sınıfın olasılığı. Durum sayıları (İncelenecek, öneri, onaylı) süzgeçten "
            "önce bütün açıklamalardan; sınıflama işi ilerlemesi = sorulan / toplam açıklama. Aynı tablo dijital yayın "
            "ekranının gece okumasıyla da dolar; metin değişince yeniden sorulur.")
F_AYAR = ("Telif dönemi ayarları (Yönetim ekranı; girilmeyen ortam değerinden ya da varsayılandan): hakediş dönemi ay sayısı "
          "(ROYALTY_PERIOD_MONTHS, 6), varsayılan stopaj % (ROYALTY_WITHHOLDING_PCT, boş), yenileme uyarı günleri "
          "(ROYALTY_RENEWAL_DAYS, 90/60/30), avans risk yılı (ROYALTY_ADVANCE_RISK_YEARS, 3).")

AYAR_KEYS = ("ROYALTY_PERIOD_MONTHS", "ROYALTY_WITHHOLDING_PCT", "ROYALTY_RENEWAL_DAYS", "ROYALTY_ADVANCE_RISK_YEARS",
             "ROYALTY_CRM_STATUSES", "ROYALTY_CRM_PAYMENT_TYPES")

#: Rakam olmayan sayılar: sayfa ve sayfa boyu, sürüm, CRM durum / ödeme şekli kodları (kimlik), Logo'da eksik yıllar
#: (yıl), süzgecin gün penceresi (seçilen değer), kayıt kimlikleri.
NOT_RAKAM = ("page", "pageSize", "version", "items[].version", "scope.statuses", "scope.paymentCodes", "items[].scope.statuses",
             "items[].scope.paymentCodes", "summary.missingYears", "items[].summary.missingYears", "days",
             "run.version", "run.scope.statuses", "run.scope.paymentCodes", "run.summary.missingYears")


# ------------------------------------------------------------------ ortak


class _Ctx:
    def __init__(self, engine: Any, tenant: str, dbs: Optional[dict[str, Optional[str]]] = None):
        self.engine, self.tenant = engine, tenant
        self.dbs = dbs or {}
        self.k = P.Kaynaklar()

    def portal(self, sid: str, title: str, stmt: Any, desc: str, origin: Iterable[str] = ()) -> str:
        if sid in self.k.sources:
            return sid
        return self.k.portal(sid, title, stmt, self.engine, description=desc, origin=list(origin))

    def run_origin(self, run_id: str) -> tuple[list[str], str]:
        """Koşunun hesabında çalışan CRM/Logo sorguları (kimlikler) ve açıklamaya eklenecek not."""
        logged = RY.run_queries(self.engine, self.tenant, run_id)
        ids = CK.kaydet(self.k, "telif.hesap", logged, self.dbs,
                        description="Koşu hesaplanırken çalıştı; sonuç koşu satırlarına yazıldı.")
        note = "" if ids else (" Bu koşu, hesapta çalışan sorgunun saklanmasından önce hesaplandı; yeniden hesaplatınca "
                               "asıl CRM/Logo sorgusu burada görünür.")
        return ids, note

    def run_src(self, run_id: str) -> tuple[str, list[str]]:
        ids, note = self.run_origin(run_id)
        r = self.portal("telif.kosu", "Telif dönemi koşusu", RY.run_stmt(self.tenant, run_id),
                        "Koşunun dönemi, durumu, özeti (kapsam, durum sayıları, para birimi toplamları, kur), ilerlemesi." + note,
                        origin=ids)
        return r, ids

    def settings(self) -> str:
        return CK.settings_src(self.k, self.engine, "telif.ayar", "Telif dönemi ayarları", AYAR_KEYS,
                               "Yönetim ekranında girilen telif ayarları; girilmeyen ortam değerinden ya da varsayılandan.")


def _dbs(logo_db: Optional[str], crm_db: Optional[str]) -> dict[str, Optional[str]]:
    return {"logo": logo_db, "crm": crm_db}


# ------------------------------------------------------------------ telif dönemi


def for_meta(engine: Any, tenant: str, out: dict[str, Any]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant)
    f = x.k.hesap("ayar", F_AYAR, [x.settings()])
    x.k.alanlar({"periodMonths": f, "withholdingPct": f, "renewalDays": f, "riskYears": f})
    return x.k


def for_runs(engine: Any, tenant: str, out: dict[str, Any]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant)
    r = x.portal("telif.kosular", "Telif dönemi koşuları", RY.runs_stmt(tenant), F_KOSULAR)
    x.k.alanlar({"items[]": x.k.hesap("kosular", F_KOSULAR + " " + F_KAPSAM + " " + F_SAYAC, [r])})
    return x.k


def for_run(engine: Any, tenant: str, run_id: str, out: dict[str, Any], logo_db: Optional[str],
            crm_db: Optional[str]) -> P.Kaynaklar:
    """`GET /api/v1/royalty/runs/{id}`: kapsam, durum sayıları, istisna nedenleri, ödenecek toplamlar, kur, ilerleme."""
    x = _Ctx(engine, tenant, _dbs(logo_db, crm_db))
    k = x.k
    r, ids = x.run_src(run_id)
    ln = x.portal("telif.satirlar", "Koşu satırları", RY.lines_stmt(tenant, run_id),
                  "Her sözleşmenin satırı: durum, istisnalar, karar, tutarlar (ozet bu satırlardan sayılır).", origin=ids)
    kapsam = k.hesap("kapsam", F_KAPSAM, [r] + ids)
    sayac = k.hesap("sayac", F_SAYAC, [r, ln])
    k.alanlar({
        "summary.lines": kapsam, "summary.crmScope": kapsam, "summary.portalOnly": kapsam, "scope": kapsam,
        "summary.counts": sayac, "summary.reasons": sayac, "sayac.istisna": sayac,
        "summary.totals": k.hesap("toplam", F_TOPLAM, [r, ln]),
        "summary.fx": k.hesap("kur", F_KUR, [r]),
        "summary.withholdingPct": k.hesap("stopaj", F_AYAR, [x.settings(), r]),
        "summary": r, "progress": k.hesap("ilerleme", F_ILERLEME, [r]), "options": k.hesap(
            "secenek", "Koşuda elle girilen dönem sonu kurları (para birimi → 1 birim = TL). " + F_KUR, [r]),
    })
    return k


def for_lines(engine: Any, tenant: str, run_id: str, out: dict[str, Any], status: str, logo_db: Optional[str],
              crm_db: Optional[str]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant, _dbs(logo_db, crm_db))
    _, ids = x.run_src(run_id)
    ln = x.portal("telif.satirlar", "Koşu satırları", RY.lines_stmt(tenant, run_id, status),
                  "Süzgeçteki durumla okunur; istisna nedeni ve arama uçta uygulanır.", origin=ids)
    f = x.k.hesap("satirlar", F_SATIRLAR + " Satır hesabı: " + F_SATIR, [ln] + ids)
    x.k.alanlar({"items[]": f, "total": f})
    return x.k


def for_line(engine: Any, tenant: str, run_id: str, line_id: int, out: dict[str, Any], logo_db: Optional[str],
             crm_db: Optional[str]) -> P.Kaynaklar:
    """Satırın hesabı (adet, matrah, brüt, avans, stopaj, net, kitap × taraf satırları)."""
    x = _Ctx(engine, tenant, _dbs(logo_db, crm_db))
    _, ids = x.run_src(run_id)
    ln = x.portal("telif.satir", "Koşu satırı", RY.line_stmt(tenant, run_id, line_id),
                  "Satırın hesabı (calc), şartları ve CRM kopyası; hesap anında yazıldı.", origin=ids)
    inputs = [ln] + ids
    with engine.connect() as c:
        opens = c.execute(RY.openings_stmt(tenant).where(RY.ADVANCES.c.contract_key == str(out.get("contractKey") or ""))).first()
    if opens is not None or (out.get("calc") or {}).get("advanceBasis"):
        inputs.append(x.portal("telif.acilis", "Avans açılış bakiyesi",
                               RY.openings_stmt(tenant).where(RY.ADVANCES.c.contract_key == str(out.get("contractKey") or "")),
                               F_ACILIS))
    f = x.k.hesap("satir", F_SATIR, inputs)
    x.k.alanlar({name: f for name, v in out.items() if name != "kaynaklar" and P.numeric_paths(v)})
    return x.k


def for_parties(engine: Any, tenant: str, run_id: str, out: dict[str, Any]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant)
    p = x.portal("telif.hakSahipleri", "Hak sahibi beyannameleri", RY.parties_stmt(tenant, run_id),
                 "Onayda onaylı satırlardan kurulur: hak sahibi, para birimine göre toplam, sözleşme sayısı, gönderim kaydı.")
    a = x.portal("telif.onayliSatirlar", "Onaylı koşu satırları", RY.approved_lines_stmt(tenant, run_id),
                 "Hakedişi oluşmuş satırlar: hesabın taraf satırları payı belirler.")
    f = x.k.hesap("hakSahibi", F_HAK_SAHIBI, [p, a])
    x.k.alanlar({"items[]": f, "total": f, "sent": f, "all": f})
    return x.k


def for_payments(engine: Any, tenant: str, run_id: str, out: dict[str, Any]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant)
    a = x.portal("telif.onayliSatirlar", "Onaylı koşu satırları", RY.approved_lines_stmt(tenant, run_id),
                 "Hakedişi oluşmuş satırlar (tutarlar ve taraf payı bunların hesabından).")
    with engine.connect() as c:
        sids = [r.statement_id for r in c.execute(RY.approved_lines_stmt(tenant, run_id)).all() if r.statement_id]
    p = x.portal("telif.odemeSatirlari", "Hakediş ödemeleri (vade, durum)", RY.run_payments_stmt(tenant, sids),
                 "Onayda sözleşmenin ödeme takvimine düşen hakediş ödemeleri.")
    f = x.k.hesap("odemeListesi", F_ODEME_LISTESI, [a, p])
    x.k.alanlar({"items[]": f, "totals": f})
    return x.k


def for_advances(engine: Any, tenant: str, out: dict[str, Any], logo_db: Optional[str] = None,
                 crm_db: Optional[str] = None) -> P.Kaynaklar:
    x = _Ctx(engine, tenant, _dbs(logo_db, crm_db))
    lr = x.portal("telif.sonKosu", "Son hesaplanan koşu", RY.latest_run_stmt(tenant),
                  "Hesaplandı, onayda ya da onaylı koşulardan dönem sonu en yeni olan (portföy bu koşudan).")
    inputs = [lr, x.portal("telif.acilislar", "Avans açılış bakiyeleri", RY.openings_stmt(tenant), F_ACILIS), x.settings()]
    run = out.get("run") or {}
    if run.get("id"):
        ids, note = x.run_origin(run["id"])
        inputs.append(x.portal("telif.avansSatirlari", f"{run.get('no') or 'Koşu'} satırları (avans)",
                               RY.advance_lines_stmt(run["id"]), "Satırın şartları (avans) ve hesabı (kalan avans, brüt telif)."
                               + note, origin=ids))
    f = x.k.hesap("avans", F_AVANS, inputs)
    x.k.alanlar({"items[]": f, "totals": f, "riskYears": f, "run": lr})
    return x.k


def for_advance_history(engine: Any, tenant: str, key: str, out: dict[str, Any]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant)
    h = x.portal("telif.acilisGecmisi", "Avans açılışı geçmişi", RY.advance_history_stmt(tenant, key), F_ACILIS)
    x.k.alanlar({"history[]": x.k.hesap("acilis", F_ACILIS, [h])})
    return x.k


def for_renewals(engine: Any, tenant: str, out: dict[str, Any], log: CK.Kayit, crm_db: Optional[str],
                 logo_db: Optional[str] = None) -> P.Kaynaklar:
    """Yenilemeler: CRM penceresi (istekte çalışan metin), portal kararları, kayıtlı Zeki AI önerileri."""
    x = _Ctx(engine, tenant, _dbs(logo_db, crm_db))
    k = x.k
    ids = CK.kaydet(k, "telif.crm.yenileme", log.items, x.dbs, description="Yenileme listesi açılırken çalıştı.")
    d = x.portal("telif.yenilemeKararlari", "Yenileme kararları", RY.renewals_stmt(tenant),
                 "Portalda girilen karar, gerekçe, kayıtlı öneri (elle ya da Zeki AI önerisi).")
    f = k.hesap("yenileme", F_YENILEME, ids + [d])
    fields = {"items[]": f, "total": f, "counts": f, "items[].suggestion": k.hesap("oneri", F_ONERI, [d])}
    decisions = RY.renewal_decisions(engine, tenant)
    for it in out.get("items") or []:
        if not it.get("suggestion"):
            continue
        row = decisions.get(it["contractKey"])
        logged = ((row.oneri_girdi or {}) if row is not None else {}).get("_sorgular") or []
        if logged:
            sids = CK.kaydet(k, f"telif.oneri.{it['contractKey'][:8]}", logged, x.dbs,
                             description="Önerinin olguları okunurken çalıştı.")
            fields[f"items[].suggestion:{it['contractKey']}"] = k.hesap(f"oneri:{it['contractKey']}", F_ONERI, sids + [d])
    k.alanlar(fields)
    return k


def for_suggest(engine: Any, tenant: str, out: dict[str, Any], log: CK.Kayit, logo_db: Optional[str],
                crm_db: Optional[str]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant, _dbs(logo_db, crm_db))
    ids = CK.kaydet(x.k, "telif.oneri", log.items, x.dbs, description="Önerinin olguları okunurken çalıştı.")
    lr = x.portal("telif.sonKosu", "Son hesaplanan koşu (kalan avans)", RY.latest_run_stmt(tenant),
                  "Kazanılmamış avans olgusu bu koşunun satırındandır.")
    f = x.k.hesap("oneri", F_ONERI, ids + [lr])
    x.k.alanlar({"probability": f, "dropped": f, "inputs": f})
    return x.k


def for_contract_lines(engine: Any, tenant: str, key: str, out: dict[str, Any]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant)
    with engine.connect() as c:
        keys = RY.contract_keys(c, tenant, key)
    s = x.portal("telif.sozlesmeSatirlari", "Sözleşmenin koşu satırları", RY.contract_lines_stmt(tenant, keys), F_KOSU_SOZLESME)
    x.k.alanlar({"items[]": x.k.hesap("sozlesmeKosulari", F_KOSU_SOZLESME + " Satır hesabı: " + F_SATIR, [s])})
    return x.k


# ------------------------------------------------------------------ haklar


def for_search(log: CK.Kayit, crm_db: Optional[str], out: dict[str, Any]) -> P.Kaynaklar:
    k = P.Kaynaklar()
    ids = CK.kaydet(k, "haklar.crm.arama", log.items, {"crm": crm_db}, description="Kitap aramasında yazılan metinle çalıştı.")
    f = k.hesap("arama", CK.F_ARAMA, ids)
    k.alanlar({"items[]": f, "total": f, "shown": f})
    return k


def for_book(engine: Any, tenant: str, book_id: str, out: dict[str, Any], log: CK.Kayit, crm_db: Optional[str]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant, {"crm": crm_db})
    k = x.k
    ids = CK.kaydet(k, "haklar.crm.kart", log.items, x.dbs, description="Hak kartı açılırken çalıştı.")
    bid = str((out.get("book") or {}).get("id") or book_id).lower()
    g = x.portal("haklar.haklar", "Dil ve ülke hakları", RY.grants_stmt(tenant, bid), F_HAK_KAYDI)
    lic = x.portal("haklar.lisanslar", "Verilen lisanslar (bu kitap)", RY.licenses_stmt(tenant, book_id=bid), F_LISANS)
    kart = k.hesap("kart", F_HAK_KARTI, ids + [lic])
    k.alanlar({"contracts[]": kart, "summary": kart, "sayac.alis": kart, "sayac.satis": kart, "grants[]": g,
               "licenses[]": k.hesap("lisans", F_LISANS, [lic])})
    return k


def for_licenses(engine: Any, tenant: str, out: dict[str, Any], *, book: str = "", status: str = "") -> P.Kaynaklar:
    x = _Ctx(engine, tenant)
    lic = x.portal("haklar.lisanslar", "Verilen lisanslar", RY.licenses_stmt(tenant, book_id=book, status=status),
                   "Süzgeçteki durumla okunur; arama uçta uygulanır.")
    f = x.k.hesap("lisans", F_LISANS, [lic])
    x.k.alanlar({"items[]": f, "total": f})
    return x.k


def for_notes(engine: Any, tenant: str, out: dict[str, Any], *, status: str = "", cls: str = "", prefix: str = "",
              crm_db: Optional[str] = None, last_read: Optional[dict[str, Any]] = None) -> P.Kaynaklar:
    """Hak açıklamaları: portal tablosu (Zeki AI sınıfı, onay) + tabloyu dolduran CRM okuması."""
    x = _Ctx(engine, tenant, {"crm": crm_db})
    k = x.k
    origin: list[str] = []
    if prefix:
        if last_read:
            origin = CK.kaydet(k, "haklar.crm.aciklamalar", [last_read], x.dbs,
                               description="Son «Zeki AI ile sınıfla» işi başlarken çalıştı; yeni ya da metni değişen "
                                           "açıklamalar sorulur.")
        else:
            origin = [k.sorgu("haklar.crm.aciklamalar.1", "CRM hak açıklamaları", "crm", S.notes_sql(prefix), database=crm_db,
                              description="«Zeki AI ile sınıfla» işi başlarken bu metin çalışır (parametresi yok). Hizmet "
                                          "açıldığından beri bu ekranda sınıflama çalışmadı; satır sayısı ve an kayıtlı değil "
                                          "(tablo dijital yayın gece okumasıyla da dolar).")]
    n = x.portal("haklar.aciklamalar", "Hak açıklamaları ve sınıfları", RY.notes_stmt(tenant, status=status, cls=cls),
                 "Sınıf, olasılık, marj, durum, onay (Zeki AI önerisi; onayı telif uzmanı verir).", origin=origin)
    allq = x.portal("haklar.aciklamaSayilari", "Hak açıklamaları (durum sayıları için hepsi)", RY.notes_stmt(tenant),
                    "Durum sayıları süzgeçten önce bütün açıklamalardan.", origin=origin)
    f = k.hesap("aciklama", F_NOTLAR, [n, allq] + origin)
    from semantic_bridge import rights_map as RM

    hm = x.portal("haklar.haritaSayilari", "Hak haritası durum sayıları", RM.counts_stmt(tenant),
                  "Yapılandırılmış hak haritası: durum başına harita sayısı.")
    fm = k.hesap("haritaSayi", F_HARITA, [hm])
    k.alanlar({"items[]": f, "total": f, "counts": f, "job": f, "mapCounts": fm, "mapJob": fm})
    return k
