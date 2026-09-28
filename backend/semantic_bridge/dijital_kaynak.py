"""M36 Dijital yayın ve e-kitap: ekrandaki her rakamın sorgu bilgisi (ortak sözleşme `provenance.py`).

Katalog, fırsat, hak riski ve kitap ayrıntısı `semantic_dijital_titles`'tan okunur; tabloyu gece okuması (her gece
04:00 ya da «Yeniden oku») CRM, Logo ve Kitap Tasarım Stüdyosu'ndan doldurur. Gösterilen portal SQL'i uçta çalışan
ifadenin kendisidir (`dijital.*_stmt`); tabloyu dolduran asıl sorgu (`origin`) okumada ÇALIŞAN CRM/Logo metnidir —
firma kopyası, tarih penceresi ve şema yerinde, satır ve süreyle — okuma bitince `semantic_dijital_meta` «sorgular»
kaydına yazılır (`dijital.logged`). Kayıt yoksa (bu sürümden önceki okuma) köken boş kalır ve açıklama bunu söyler.

Platform durumu, hak kararı, dijital fiyat ve platform tanımı elle girilir (portal SQL'i + «elle girilir»). Dijital
satış yüklenen platform raporundan gelir: portal SQL'i + hesap metninde raporun dosya adı ve platformu.
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

import sqlalchemy as sa

from semantic_bridge import dijital as D
from semantic_bridge import provenance as P

PFX = "dijital."

#: Okumada çalışan sorgu etiketleri (`dijital_sources.query_tag`) → hangi kolonları doldurduğu.
BOOKS = ("crm.kitaplar", "crm.etiket.")
RIGHTS = ("crm.sozlesmeler", "crm.taraflar")
COUNTS = ("crm.sozlesmeSayilari",)
PROD = ("crm.uretim",)
HIST = ("crm.gecmis",)
LOGO = ("logo.",)
ALL = BOOKS + RIGHTS + PROD + HIST + LOGO

F_OKUMA = ("Kitap satırları gece okumasında (her gece 04:00 ya da «Yeniden oku») CRM, Logo ve Kitap Tasarım Stüdyosu'ndan "
           "okunup semantic_dijital_titles tablosuna yazılır; ekran bu tablodan okur. Okumada çalışan sorgular kökende. "
           "Okunamayan kaynağın kolonları bir önceki okumadan kalır (ekrandaki okuma notunda yazar).")
F_HAK = ("Hak kararı (kitap × biçim): kitaba bağlı yürürlükteki bütün Telif Alış sözleşmelerinde (CRM, sözleşme tipi 5) "
         "biçimin bayrağı (e-kitap new_EKitap, sesli new_SesliKitapHakki) varsa «hak var»; biri eksikse «eksik»; yürürlükte "
         "sözleşme yoksa «hak yok» (koruma dışı eserse «koruma dışı»); bayraklar tam ama hak notu (new_haklaraciklama) varsa "
         "telif birimi karar verene kadar «incelenmeli». İnternette gösterim hakkı (new_iletimhakki) ayrı bayraktır. Telif "
         "Satış sözleşmeleri hak kontrolüne girmez. Telif hak haritası bağlıysa karar oradan gelir.")
F_12AY = ("Basılı son 12 ay: Logo faturalı satış satırı (iptal değil, stok satırı, faturaya bağlı; TRCODE 7/8/9 satış, 2/3 "
          "iade eksi), veri sonunun ayı dahil son 12 takvim ayı, her yıl kendi firma kopyasından; adet = Σ AMOUNT, ciro = "
          "Σ LINENET, kitabın stok koduyla. Logo e-kitap = aynı sorgudan CRM'deki e-kitap stok koduyla kesilen faturalar.")
F_DIJITALDE = ("Dijitalde (e-kitap) = CRM'de e-kitap stok kodu dolu ya da bir e-kitap platformunda «yüklendi/yayında» "
               "işaretli (platform durumu elle ya da onaylı rapordan girilir). Sesli = aynı adlı sesli kitap kartı ya da sesli "
               "platformda «yüklendi/yayında».")
F_FIRSAT = ("Fırsat: kitap tipli kart ∧ biçimin hakkı var ya da kısıtlı ∧ o biçimde kayıt yok ∧ son 12 ay basılı net adet ≥ "
            "eşik ∧ yayın durumu satış dışı değil (sesli adayda ayrıca tür süzgeci). Puan = kitap tipli kartlar arasında basılı "
            "adedin yüzdelik sırası (0–100). Gerekçe cümlesindeki sayılar aynı okumadandır; model yok.")
F_RISK = ("Hak riski: e-kitap hakkı eksik/yok/incelenmeli iken dijitalde görünen (e-kitap stok kodu, platform kaydı ya da "
          "Logo'da e-kitap faturası) ya da sesli hakkı sorunlu iken sesli sürümü olan kitap. Telif kararı bekleyen = dijitalde "
          "olmayan ama hakkı «incelenmeli» kalan kitap.")
F_NOT = ("Hak notu ön okuması Zeki AI sınıflamasıdır (telif modülüyle ortak tablo); olasılık sınıflamanın güvenidir, yalnız "
         "sıralama için kullanılır; hak kararı telif biriminindir.")
F_ELLE = "Ekrandan elle girilir (portal tablosu); hesap yok."
F_SATIS = ("Dijital satış: onaylı platform satış raporlarının veri satırları (yüklenen Excel/CSV dosyası; kişisel veri "
           "kolonları yüklemede atıldı, «toplam» satırı toplama girmez). Net (TL) = satırın net tutarı × onayda girilen kur "
           "(TRY için 1; modül kur varsaymaz). Aylık = dönem × platform Σ adet, Σ net TL, satır sayısı; kitap kırılımı yalnız "
           "kitaba eşlenmiş satırlar; eşleşmeyen satır atılmaz, açık iş olarak listelenir.")
F_LOGO_EKITAP = ("Logo'daki e-kitap faturaları: gece okumasındaki Logo satış sorgusunun, CRM'de e-kitap stok kodu olan "
                 "kartlara düşen satırları ay ay (adet = Σ AMOUNT, ciro = Σ LINENET); sonuç semantic_dijital_meta «logo» "
                 "kaydında. Platform raporlarıyla toplanmaz: aynı satış iki kaynakta da olabilir.")
F_ESLEME = ("Kurallı eşleme: e-ISBN, e-kitap barkodu, ISBN, barkod, e-kitap stok kodu, stok kodu (anahtar tek kitaba gidiyorsa). "
            "Kalan satırlarda adaylar ad ve yazar sözcük örtüşmesiyle (benzerlik 0–1); olasılık Zeki AI kapalı küme seçiminin "
            "güvenidir. Hiçbir öneri kendiliğinden onaylanmaz.")


def _num_keys(out: dict[str, Any], ref: str, skip: Iterable[str] = ()) -> dict[str, str]:
    sk = set(skip)
    return {k: ref for k, v in out.items() if k not in sk and k != "kaynaklar" and P.numeric_paths({k: v})}


def _read_title(tag: str) -> tuple[str, Optional[str]]:
    """Saklı okuma sorgusunun başlığı ve dönemi (etiketten)."""
    parts = tag.split(".")
    if tag == "logo.donem":
        return "Logo yıl → firma kopyası (dönem tanımları)", None
    if tag == "logo.verisonu":
        return "Logo satış verisinin son günü", None
    if tag.startswith("logo.satis."):
        firm = parts[2] if len(parts) > 2 else "?"
        start = parts[3] if len(parts) > 3 else ""
        return f"Logo faturalı satış · firma {firm}", f"{start[:4] or '?'} · Logo firma {firm} · {start} başlangıçlı pencere"
    titles = {"crm.gecmis": "CRM kitap geçmişi (baskı sayısı, kapak)",
              "crm.uretim": "CRM üretim kartı: e-kitap aşaması",
              "crm.taraflar": "CRM Telif Alış sözleşme tarafları",
              "crm.sozlesmeSayilari": "CRM Telif Alış sözleşme sayıları (e-kitap, sesli, internette gösterim, hak notu)",
              "crm.sozlesmeler": "CRM kitaba bağlı Telif Alış sözleşmeleri ve dijital hak alanları",
              "crm.kitaplar": "CRM kitap kartları ve dijital kimlik alanları"}
    if tag.startswith("crm.etiket."):
        return f"CRM seçenek etiketleri · {parts[2] if len(parts) > 2 else ''}", None
    return titles.get(tag, "Okuma sorgusu"), None


class _Ctx:
    def __init__(self, engine: Any, tenant: str, logo_db: Optional[str] = None, crm_db: Optional[str] = None):
        self.engine, self.tenant, self.dbs = engine, tenant, {"logo": logo_db, "crm": crm_db}
        self.logo_meta = D.meta_get(engine, tenant, "logo")
        self.k = P.Kaynaklar(data_end=self.logo_meta.get("veriSonu"))
        self._reads: Optional[list[tuple[str, str]]] = None

    def portal(self, sid: str, title: str, stmt: Any, desc: str, origin: Iterable[str] = ()) -> str:
        sid = PFX + sid
        if sid in self.k.sources:
            return sid
        return self.k.portal(sid, title, stmt, self.engine, description=desc, origin=origin)

    def reads(self) -> list[tuple[str, str]]:
        """Son okumada çalışan CRM/Logo sorguları → (etiket, kayıt kimliği). Bir kez kaydedilir."""
        if self._reads is not None:
            return self._reads
        self._reads = []
        meta = D.meta_get(self.engine, self.tenant, "sorgular")
        seen: set[str] = set()
        for q in meta.get("items") or []:
            sql, tag = q.get("sql") or "", str(q.get("tag") or "diger")
            if not sql or sql in seen:
                continue
            seen.add(sql)
            conn = q.get("conn") if q.get("conn") in ("logo", "crm") else "crm"
            sid = f"{PFX}okuma.{tag}"
            n = 2
            while sid in self.k.sources:
                sid, n = f"{PFX}okuma.{tag}.{n}", n + 1
            title, period = _read_title(tag)
            try:
                self.k.sorgu(sid, title, conn, sql, database=self.dbs.get(conn), rows=q.get("rows"), ms=q.get("dbMs"),
                             ran_at=q.get("at"), period=period,
                             description="Gece okumasında (ya da «Yeniden oku» ile) çalıştı; sonucu semantic_dijital_titles "
                                         "tablosuna ve okuma kaydına yazıldı.")
            except P.ProvenanceError:
                continue
            self._reads.append((tag, sid))
        return self._reads

    def origin(self, *prefixes: str) -> list[str]:
        want = tuple(prefixes) or ALL
        return [sid for tag, sid in self.reads() if tag.startswith(want)]

    def no_origin_note(self) -> str:
        return "" if self.reads() else " Okuma sorguları bu sürümden sonraki ilk okumada kaydedilir; o zamana kadar köken boş."

    # ---------------------------------------------------------------- ortak kaynaklar

    def titles_src(self, sid: str, title: str, stmt: Any, desc: str) -> str:
        return self.portal(sid, title, stmt, desc + self.no_origin_note(), origin=self.origin(*ALL))

    def platforms(self) -> str:
        return self.portal("platformlar", "Platform tanımları", D.platforms_stmt(self.tenant), F_ELLE)

    def listings(self) -> str:
        return self.portal("platformDurumu", "Platform durum kayıtları", D.listings_stmt(self.tenant),
                           "Kitap × platform durumu (elle ya da onaylı rapordan); her çift için son satır geçerli.")

    def decisions(self) -> str:
        return self.portal("hakKararlari", "Telif biriminin hak kararları", D.decisions_stmt(self.tenant),
                           "Hak notlu sözleşmeye verilen karar (elle girilir); notun metni değişirse yeniden sorulur.")

    def logo_src(self) -> str:
        return self.portal("logoOkuma", "Logo okumasının özeti (veri sonu, pencere, e-kitap satışı)",
                           D.meta_stmt(self.tenant, "logo"),
                           "Gece okumasında Logo satış sorgusundan çıkarılan veri sonu, 12 ay penceresi ve e-kitap stok "
                           "kodlarının ay ay satışı." + self.no_origin_note(), origin=self.origin(*LOGO, "crm.kitaplar"))

    def settings(self, st: dict[str, Any]) -> str:
        from semantic_bridge import admin as ADM

        keys = sorted(k for k in D.DEFAULTS if k.startswith("DIJITAL_"))
        src = self.portal("ayarlar", "Dijital yayın ayarları (ekrandan girilenler)",
                          sa.select(ADM.SETTINGS.c.key, ADM.SETTINGS.c.value).where(ADM.SETTINGS.c.key.in_(keys)),
                          "Yönetim ekranında (Dijital yayın ve e-kitap) girilen ayarlar; girilmeyen ayar ortam değerinden ya da "
                          "varsayılandan gelir.")
        text = (f"Fırsat eşiği: son 12 ay basılı adet ≥ {st['oppMinQty']:g} (DIJITAL_OPP_MIN_QTY, varsayılan "
                f"{D.DEFAULTS['DIJITAL_OPP_MIN_QTY']}); sesli aday eşiği ≥ {st['audioMinQty']:g} (DIJITAL_AUDIO_MIN_QTY); sesli "
                f"tür süzgeci: {', '.join(st['audioGenres']) or 'yok (bütün türler)'}; eşleme önerisi onay eşiği "
                f"{st['matchMinProb']:g}; rapor dosyası en çok {st['importMaxMb']} MB.")
        return self.k.hesap("ayar", text, [src])


# ---------------------------------------------------------------- göstergeler


KPI = {
    "kitap": ("Kitap kartı", "Kitap tipli CRM kartı sayısı (ayar DIJITAL_BOOK_TYPES; varsayılan 1 = Kitap).", BOOKS),
    "dijitalde": ("Dijitalde (e-kitap)", "Kitap tipli kartlardan " + F_DIJITALDE, BOOKS),
    "hakliDijitalYok": ("Hakkı var, dijitalde yok", "Kitap tipli, e-kitap hakkı var / kısıtlı / koruma dışı ve e-kitap kaydı "
                                                    "yok. " + F_HAK, BOOKS + RIGHTS),
    "firsat": ("E-kitap fırsatı", F_FIRSAT, ALL),
    "sesliFirsat": ("Sesli kitap adayı", F_FIRSAT, ALL),
    "hakRiski": ("Hak riski", F_RISK + " " + F_HAK, BOOKS + RIGHTS + LOGO),
    "incele": ("Karar bekleyen", "E-kitap ya da sesli hakkı «incelenmeli» (hak notu var, telif kararı yok ya da not değişti).",
               RIGHTS),
    "ekitapKaydi": ("E-kitap kartı", "CRM «Ekitap» tipli kart (new_Tip 8).", BOOKS),
    "sesliKaydi": ("Sesli kitap kartı", "CRM sesli kitap tipli kart (ayar DIJITAL_AUDIO_TYPES).", BOOKS),
    "epubCrmEvet": ("CRM E-Pub «Evet»", "CRM kitap kartında E-Pub Durumu Evet (new_EPubDurumu = 1).", BOOKS),
    "epubStudyoHazir": ("Stüdyoda e-kitap hazır", "Kitap Tasarım Stüdyosu'nda e-kitabı hazır (stüdyo iş listesinden, SQL "
                                                  "yok; gece okumasında satıra yazılır).", ()),
    "yeniBaski": ("Yeni baskı / kapak", "Dijital sürümü olan kitapta pencere içinde (ayar DIJITAL_EDITION_DAYS) baskı sayısı "
                                        "arttı ya da kapak adresi değişti (CRM kitap geçmişi), dijital sürümün son "
                                        "güncellemesinden sonra.", HIST + BOOKS),
    "crmIslenecek": ("CRM'e işlenecek", "Açık kayıt: stüdyodaki e-ISBN CRM'dekinden farklı, stüdyoda hazır e-kitapta CRM E-Pub "
                                        "Durumu «Hayır», ya da platformda yayında ama e-kitap stok kodu yok. Portal CRM'e "
                                        "yazmaz; CRM'e işlenince gece okumasında kapanır.", BOOKS),
}
#: Göstergeye elle girilen hangi kayıtlar etki eder.
KPI_MANUAL = {"dijitalde": ("listings",), "hakliDijitalYok": ("listings", "decisions"), "hakRiski": ("listings", "decisions"),
              "incele": ("decisions",), "firsat": ("listings", "decisions"), "sesliFirsat": ("listings", "decisions"),
              "yeniBaski": ("listings",), "crmIslenecek": ("listings",)}


def _kpi(x: _Ctx, st: dict[str, Any], key: str) -> str:
    """Göstergenin sayım kaydı ve hesabı (`hesap:kpi.<anahtar>`)."""
    ref = f"hesap:kpi.{key}"
    if ref[6:] in x.k.formulas:
        return ref
    title, text, prefixes = KPI[key]
    stmt = D.overview_stmts(x.tenant, st)[key]
    sid = x.portal(f"kpi.{key}", f"Gösterge sayımı · {title}", stmt,
                   ("Açık kayıtlar (semantic_dijital_crm_pending)." if key == "crmIslenecek" else "Kitap satırları sayımı.")
                   + x.no_origin_note(), origin=x.origin(*prefixes) if prefixes else ())
    extra = [getattr(x, m)() for m in KPI_MANUAL.get(key, ())]
    return x.k.hesap(f"kpi.{key}", text + " Sayı gösterge sorgusunun sonucudur.", [sid] + extra)


def for_overview(engine: Any, tenant: str, st: dict[str, Any], out: dict[str, Any], logo_db: Optional[str] = None,
                 crm_db: Optional[str] = None) -> P.Kaynaklar:
    x = _Ctx(engine, tenant, logo_db, crm_db)
    k = x.k
    fields = {f"kpi.{key}": _kpi(x, st, key) for key in KPI}
    fields["kpi"] = k.hesap("kpi", F_OKUMA, [f"hesap:kpi.{key}" for key in KPI])
    fields["kart.dijitalde"] = k.hesap("kart.dijitalde", "Kart: dijitalde olan kitap tipli kart ÷ bütün kitap tipli kartlar "
                                                         "(yardım satırı). " + F_DIJITALDE, ["hesap:kpi.dijitalde", "hesap:kpi.kitap"])
    fields["kart.hakliDijitalYok"] = k.hesap("kart.hakliDijitalYok", "Kart: hakkı olup dijitalde olmayan kitap; yardım satırı "
                                                                     "bunlardan fırsat listesinde olanlar. " + F_FIRSAT,
                                             ["hesap:kpi.hakliDijitalYok", "hesap:kpi.firsat"])
    fields["kart.hakRiski"] = k.hesap("kart.hakRiski", "Kart ve «Hak riski» sekme rozeti: hak riski olan kitap; yardım satırı "
                                                       "telif kararı bekleyen kitap. " + F_RISK,
                                      ["hesap:kpi.hakRiski", "hesap:kpi.incele"])
    dist = [x.portal(f"hakDagilimi.{b}", f"Hak kararı dağılımı · {D.FORMATS[b]}", D.rights_dist_stmt(tenant, st, b),
                     "Kitap tipli kartlarda karar başına kitap sayısı." + x.no_origin_note(), origin=x.origin(*BOOKS, *RIGHTS))
            for b in ("ekitap", "sesli")]
    fields["hakDagilimi"] = k.hesap("hakDagilimi", F_HAK, dist + [x.decisions()])
    last = x.portal("sonRapor", "En son onaylı platform satış raporu", D.last_report_stmt(tenant),
                    "Onaylı raporlar dönemden geriye; ilk satır kartta. Rapor dosyası Dijital satış › Raporlar'da yüklenir.")
    fields["sonRapor"] = k.hesap("sonRapor", "Son satış raporu = onaylı raporların en büyük dönemi ve platformu.", [last, x.platforms()])
    counts = x.portal("sozlesmeSayilari", "Sözleşme sayıları (son okuma)", D.meta_stmt(tenant, "crm_counts"),
                      "Gece okumasında CRM'den okunan sözleşme düzeyi sayılar." + x.no_origin_note(), origin=x.origin(*COUNTS))
    fields["sozlesme"] = k.hesap("sozlesme", "Sözleşme düzeyi sayılar (kitaba bağlı olmayanlar dahil): yürürlük durumundaki Telif "
                                             "Alış (tip 5) sözleşmeleri; e-kitap (new_EKitap), sesli (new_SesliKitapHakki), "
                                             "internette gösterim (new_iletimhakki) hakkı olanlar; hak notu olanlar bütün "
                                             "durumlarda.", [counts])
    fields["logo"] = k.hesap("logo", F_12AY, [x.logo_src()])
    ref = x.portal("okuma", "Son okumanın özeti", D.meta_stmt(tenant, "refresh"),
                   "Okuma işinin kendi kaydı: süre (sn), kitap, yazılan / güncellenen / silinen satır, CRM'e işlenecek eklenen / "
                   "kapanan, notlar.")
    fields["okuma"] = k.hesap("okuma", "Okuma özeti: okuma işinin yazdığı sayaçlar (süre saniye, kitap sayısı, tablo satırı "
                                       "değişiklikleri). " + F_OKUMA, [ref] + [sid for _, sid in x.reads()])
    fields["ayarlar"] = x.settings(st)
    k.alanlar(fields)
    return k


def for_meta(engine: Any, tenant: str, st: dict[str, Any], out: dict[str, Any]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant)
    ref = x.portal("okuma", "Son okumanın özeti", D.meta_stmt(tenant, "refresh"), "Okuma işinin kendi kaydı.")
    x.k.alanlar({"ayarlar": x.settings(st),
                 "okuma": x.k.hesap("okuma", "Okuma özeti: okuma işinin yazdığı sayaçlar (süre saniye, kitap sayısı, tablo "
                                             "satırı değişiklikleri); «sürüyor» bayrağı köprünün bellek durumudur.", [ref])})
    return x.k


# ---------------------------------------------------------------- katalog, fırsat, risk


def _title_fields(x: _Ctx, rows_src: str, prefix: str) -> dict[str, str]:
    """Kitap satırındaki rakamlar (liste satırı ya da ayrıntı): basılı 12 ay, fiyatlar, fırsat puanları."""
    k = x.k
    logo = x.origin(*LOGO)
    s12 = k.hesap("basili12", F_12AY + (" Okuma kaydı yok: " + x.no_origin_note().strip() if not logo else ""),
                  [rows_src] + logo)
    fiyat = k.hesap("basiliFiyat", "Basılı liste fiyatı = CRM kitap kartındaki KDV dahil fiyat (new_kdvdahilfiyat), gece "
                                   "okumasında satıra yazılır.", [rows_src] + x.origin("crm.kitaplar"))
    dij = k.hesap("dijitalFiyat", "Dijital fiyat kararı " + F_ELLE[0].lower() + F_ELLE[1:] + " Platformlara gönderilmez.",
                  [rows_src])
    puan = k.hesap("puan", F_FIRSAT, [rows_src] + x.origin(*ALL))
    out = {f"{prefix}basili12Adet": s12, f"{prefix}basili12Ciro": s12, f"{prefix}logoDijital12Adet": s12,
           f"{prefix}logoDijital12Ciro": s12, f"{prefix}basiliFiyat": fiyat, f"{prefix}dijitalFiyat": dij,
           f"{prefix}firsatPuani": puan, f"{prefix}sesliFirsatPuani": puan, f"{prefix}puan": puan}
    out[prefix.rstrip(".") or "satir"] = k.hesap("satir", F_OKUMA + " " + F_HAK, [rows_src, x.platforms(), x.listings()])
    return out


def for_titles(engine: Any, tenant: str, st: dict[str, Any], out: dict[str, Any], *, hak: str = "", durum: str = "", q: str = "",
               tur: str = "kitap", platform: int = 0, page: int = 0, logo_db: Optional[str] = None,
               crm_db: Optional[str] = None) -> P.Kaynaklar:
    x = _Ctx(engine, tenant, logo_db, crm_db)
    k = x.k
    total_stmt, rows_stmt, _ = D.titles_query(engine, tenant, st, hak=hak, durum=durum, q=q, tur=tur, platform=platform, page=page)
    rows = x.titles_src("katalog", "Katalog satırları (bu sayfa)", rows_stmt,
                        f"Süzgeçteki kitaplar, son 12 ay basılı adede göre; sayfa {D.PAGE} satır (tavan değil, sayfalama).")
    total = x.portal("katalogToplam", "Süzgeçteki kitap sayısı", total_stmt, "Sayfalamadan bağımsız toplam.")
    fields = _title_fields(x, rows, "items[].")
    fields["total"] = k.hesap("toplam", "Süzgeçteki kitap sayısı = sayım sorgusunun sonucu; listede sayfa başına "
                                        f"{D.PAGE} satır görünür.", [total] + ([x.listings()] if platform else []))
    k.alanlar(fields)
    return k


def for_opportunities(engine: Any, tenant: str, st: dict[str, Any], out: dict[str, Any], *, tur: str = "ekitap", q: str = "",
                      page: int = 0, logo_db: Optional[str] = None, crm_db: Optional[str] = None) -> P.Kaynaklar:
    x = _Ctx(engine, tenant, logo_db, crm_db)
    k = x.k
    total_stmt, stmt = D.opportunities_stmts(tenant, tur=tur, q=q, page=page)
    rows = x.titles_src("firsatlar", f"{D.FORMATS[tur]} fırsatları (bu sayfa)", stmt,
                        f"Fırsat puanı dolu kitaplar, son 12 ay basılı adede göre; sayfa {D.PAGE} satır.")
    total = x.portal("firsatToplam", f"{D.FORMATS[tur]} fırsatı sayısı", total_stmt, "Aramaya uyan fırsatların tamamı.")
    fields = _title_fields(x, rows, "items[].")
    fields["total"] = k.hesap("toplam", "Fırsat sayısı = sayım sorgusunun sonucu; CSV bütün satırları verir.", [total])
    fields["esik"] = k.hesap("esik", "Listeye giriş eşiği ve tür süzgeci ayardır; puan ve gerekçe gece okumasında bu eşikle "
                                     "yazılır. " + F_FIRSAT, [x.settings(st), rows])
    k.alanlar(fields)
    return k


def for_rights_risks(engine: Any, tenant: str, st: dict[str, Any], out: dict[str, Any], logo_db: Optional[str] = None,
                     crm_db: Optional[str] = None) -> P.Kaynaklar:
    x = _Ctx(engine, tenant, logo_db, crm_db)
    k = x.k
    rows = x.titles_src("hakRiskiSatirlari", "Hakkı eksik / yok / incelenmeli kitaplar", D.risk_rows_stmt(tenant),
                        "Risk ve karar bekleyen ayrımı satırda yapılır (dijitalde görünüyor mu).")
    notes = x.portal("hakNotuOkumasi", "Hak notu ön okuması", D.note_reads_stmt(tenant), F_NOT)
    satir = k.hesap("hakRiski", F_RISK + " " + F_HAK + " Sıra: ön okuma «kısıtlıyor» diyenler önce, sonra basılı adet.",
                    [rows, notes, x.listings(), x.decisions()])
    badge = _kpi(x, st, "hakRiski")
    fields = {"risk[]": satir, "incele[]": satir}
    cols = {c: v for c, v in _title_fields(x, rows, "").items() if c != "satir"}
    fields.update({f"{p}[].{c}": v for p in ("risk", "incele") for c, v in cols.items()})
    fields["sayac.risk"] = k.hesap("sayac.risk", "«Dijitalde, hakkı sorunlu (N)» = risk satırı sayısı (ekranda sayılır); "
                                                 "katalogdaki «Hak riski» kartı ve sekme rozeti aynı kuralın sayım sorgusudur.",
                                   [satir, badge])
    fields["sayac.incele"] = k.hesap("sayac.incele", "«Telif kararı bekleyen hak notları (N)» = dijitalde olmayıp hakkı "
                                                     "«incelenmeli» kalan kitap sayısı (ekranda sayılır).", [satir])
    k.alanlar(fields)
    return k


def for_pending(engine: Any, tenant: str, st: dict[str, Any], durum: str, out: dict[str, Any]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant)
    k = x.k
    lst = x.portal("crmIslenecek", "CRM'e işlenecek kayıtlar", D.pending_stmt(tenant, durum),
                   "Gece okumasında açılır, CRM'e işlenince kapanır (portal CRM'e yazmaz).")
    names = x.portal("crmIslenecekKitaplar", "Kayıtların kitap adı ve stok kodu", D.pending_titles_stmt(tenant, durum),
                     "Katalog satırlarından.")
    badge = _kpi(x, st, "crmIslenecek")
    k.alanlar({"items[]": k.hesap("crmIslenecek", KPI["crmIslenecek"][1], [lst, names]),
               "sayac": k.hesap("sayac", "Listedeki kayıt sayısı (ekranda sayılır). «CRM'e işlenecek» sekme rozeti açık kayıt "
                                         "sayısının gösterge sorgusudur (Açık süzgecinde aynı sayı).", [lst, badge])})
    return k


def for_platforms(engine: Any, tenant: str, out: dict[str, Any]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant)
    x.k.alanlar({"items[]": x.k.hesap("platform", "Platform tanımı elle girilir; rapor günü = ay kapanışından kaç gün sonra "
                                                  "satış raporu beklendiği (finans hatırlatması).", [x.platforms()])})
    return x.k


# ---------------------------------------------------------------- kitap ayrıntısı


def for_title(engine: Any, tenant: str, kitap_id: str, out: dict[str, Any], logo_db: Optional[str] = None,
              crm_db: Optional[str] = None) -> P.Kaynaklar:
    x = _Ctx(engine, tenant, logo_db, crm_db)
    k = x.k
    kid = str(out.get("kitapId") or kitap_id)
    row = x.titles_src("kitap", "Kitap satırı", D.title_stmt(tenant, kid), "Kitabın katalog satırı (bütün kolonlar).")
    fields = _title_fields(x, row, "")
    fields.pop("satir", None)
    fields["platformlar"] = k.hesap("platformDurumu", "Platform çipleri: her platform için son durum kaydı (elle ya da onaylı "
                                                      "rapordan); kayıt yoksa «bilinmiyor».", [x.platforms(), x.listings()])
    notes = x.portal("hakNotuOkumasi", "Hak notu ön okuması", D.note_reads_stmt(tenant), F_NOT)
    fields["sozlesmeler"] = k.hesap("sozlesmeler", F_HAK + " " + F_NOT, [row, notes] + x.origin(*RIGHTS))
    fields["kararlar"] = k.hesap("kararlar", "Telif biriminin kararları " + F_ELLE[0].lower() + F_ELLE[1:], [x.decisions()])
    hist = x.portal("platformGecmisi", "Kitabın platform durum geçmişi", D.listing_history_stmt(tenant, kid),
                    "Bütün kayıtlar yeniden eskiye (elle ya da onaylı rapordan); platform fiyatı elle girilir.")
    fields["platformGecmisi"] = k.hesap("platformGecmisi", "Platform geçmişi: her durum kaydı bir satır (sayısı başlıkta); "
                                                           "fiyat kaydı giren kişinin yazdığı platform fiyatıdır.", [hist, x.platforms()])
    pend = x.portal("kitapCrmIslenecek", "Kitabın CRM'e işlenecek kayıtları", D.title_pending_stmt(tenant, kid),
                    KPI["crmIslenecek"][1])
    fields["crmIslenecek"] = pend
    fields["oran"] = k.hesap("oran", "Dijital / basılı = dijital fiyat kararı ÷ basılı liste fiyatı (CRM, KDV dahil), yüzde "
                                     "olarak yuvarlanır (ekranda hesaplanır).", [fields["dijitalFiyat"], fields["basiliFiyat"]])
    if "satis" in out:
        ts = x.portal("kitapSatis", "Kitabın onaylı rapor satışları", D.title_sales_stmt(tenant, kid),
                      "Onaylı platform raporlarında bu kitaba eşlenmiş satırlar, dönem × platform.")
        fields["satis.platform"] = k.hesap("kitapSatis", F_SATIS, [ts, x.platforms()])
        fields["satis.logo"] = k.hesap("kitapLogoEkitap", F_LOGO_EKITAP, [x.logo_src()])
    k.alanlar(fields)
    return k


# ---------------------------------------------------------------- satış ve rapor yükleme


def _report_names(x: _Ctx, platform: int = 0) -> tuple[str, str]:
    """Onaylı rapor dosyaları: kayıt + hesap metninde adları (dosyadan gelen rakamın kaynak adı)."""
    stmt = D.committed_imports_stmt(x.tenant, platform)
    sid = x.portal("onayliRaporlar", "Onaylı platform raporları (dosyalar)", stmt,
                   "Satış panosunun satırlarını taşıyan yüklemeler: platform, dönem, dosya adı, onaylayan, kur.")
    plats = D._platforms(x.engine, x.tenant)
    with x.engine.connect() as c:
        rows = c.execute(stmt).all()
    names = [f"{plats[r.platform_id].ad if r.platform_id in plats else r.platform_id} {r.donem} ({r.dosya_adi or 'adsız dosya'})"
             for r in rows]
    shown = "; ".join(names) if names else "henüz onaylı rapor yok"
    return sid, f"Kaynak dosyalar: {shown}."


def for_sales(engine: Any, tenant: str, out: dict[str, Any], *, donem: str = "", platform: int = 0,
              logo_db: Optional[str] = None, crm_db: Optional[str] = None) -> P.Kaynaklar:
    x = _Ctx(engine, tenant, logo_db, crm_db)
    k = x.k
    q = D.sales_stmts(tenant, donem, platform)
    files, names = _report_names(x, platform)
    sel = f" Süzgeç: dönem {donem or 'hepsi'}, platform {platform or 'hepsi'}."
    ay = x.portal("satisAylik", "Aylık dijital satış (dönem × platform)", q["aylik"], "Onaylı rapor satırları." + sel)
    kb = x.portal("satisKitap", "Kitap kırılımı", q["kitaplar"], "Kitaba eşlenmiş satırlar." + sel)
    op = x.portal("satisEslesmeyen", "Eşleşmeyen açık satırlar", q["eslesmeyen"], "Kitaba eşlenmemiş satırlar (açık iş)." + sel)
    cards = x.titles_src("satisKitapKartlari", "Satışı olan kitapların katalog satırı", q["kitapKartlari"],
                         "Ad, stok kodu, hedef kitle ve son 12 ay basılı adet.")
    satis = k.hesap("satis", F_SATIS + " " + names, [ay, files, x.platforms()])
    kitap = k.hesap("satisKitap", F_SATIS + " " + names, [kb, cards, files])
    s12 = k.hesap("basili12", F_12AY, [cards] + x.origin(*LOGO))
    acik = k.hesap("eslesmeyen", "Eşleşmeyen satır: onaylı raporda kitaba eşlenmemiş veri satırı; Raporlar sekmesinde eşlenir. "
                                 + F_ESLEME + " " + names, [op, files])
    logo = k.hesap("logoEkitap", F_LOGO_EKITAP + (f" Dönem süzgeci: {donem}." if donem else ""), [x.logo_src()])
    oran = k.hesap("oran", "Dijital / basılı, hedef kitle başına: Σ dijital adet (kitap kırılımı, seçili dönem) ÷ Σ aynı "
                           "kitapların son 12 ay basılı adedi (Logo, gece okuması); basılı 0 ise boş.", [kitap, s12])
    fields = {"aylik[]": satis, "kitaplar[]": kitap, "kitaplar[].basili12Adet": s12, "eslesmeyen[]": acik,
              "logoEkitap[]": logo, "logoPencere": logo, "dijitalBasiliOran[]": oran,
              "toplam.net": k.hesap("toplam.net", "Dijital gelir = aylık satırların Σ net TL (ekranda toplanır).", [satis]),
              "toplam.adet": k.hesap("toplam.adet", "Dijital adet = aylık satırların Σ adet (ekranda toplanır).", [satis]),
              "sayac.kitap": k.hesap("sayac.kitap", "Kitap sayısı = kitap kırılımının satır sayısı.", [kitap]),
              "sayac.eslesmeyen": k.hesap("sayac.eslesmeyen", "Eşleşmeyen satır sayısı (ekranda sayılır).", [acik]),
              "toplam.logoAdet": k.hesap("toplam.logoAdet", "Logo e-kitap faturası = Logo e-kitap aylarının Σ adet (ekranda "
                                                            "toplanır). " + F_LOGO_EKITAP, [logo])}
    fields["kart.adet"] = k.hesap("kart.adet", "Kart: Σ adet; yardım satırı kitap kırılımının satır sayısı.",
                                  ["hesap:toplam.adet", "hesap:sayac.kitap"])
    k.alanlar(fields)
    return k


def for_imports(engine: Any, tenant: str, out: dict[str, Any]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant)
    src = x.portal("raporlar", "Yüklenen raporlar", D.imports_stmt(tenant), "Yüklemeler (önizleme, onaylı, iptal), yeniden eskiye.")
    x.k.alanlar({"items[]": x.k.hesap("raporlar", "Rapor satırı: yüklenen dosyanın (Excel/CSV) platformu, dönemi ve dosya adı "
                                                  "kayıtta. Satır / eşleşen / açık sayıları rapor satırlarından her değişiklikte "
                                                  "yeniden sayılır (toplam satırı eşleşme sayısına girmez); kur onayda girilir.",
                                      [src, x.platforms()])})
    return x.k


def for_import(engine: Any, tenant: str, iid: str, out: dict[str, Any]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant)
    k = x.k
    imp = x.portal("rapor", "Rapor yüklemesi", D.import_stmt(tenant, iid),
                   "Platform, dönem, dosya adı, yükleyen, satır sayaçları, kolon eşlemesi, kurlar, eşleme işinin durumu.")
    rows = x.portal("raporSatirlari", "Raporun satırları", D.import_rows_stmt(iid),
                    "Dosyadaki her dolu satır (boş satır yazılmaz; kişisel veri kolonları yüklemede atıldı).")
    names = x.portal("raporKitaplari", "Eşlenen kitapların adı", D.import_titles_stmt(tenant, iid), "Katalog satırlarından.")
    src_name = (f"Kaynak dosya: {out.get('dosya') or 'adsız dosya'} ({out.get('platform') or 'platform'} · {out.get('donem') or ''}"
                f", yükleyen {out.get('yukleyen') or '—'}).")
    sayac = k.hesap("sayac", "Satır = yazılan satır sayısı (toplam satırı dahil, işaretli); eşleşen / açık = kitaba eşlenmiş / "
                             "eşlenmemiş veri satırı; boş satır sayılır ama yazılmaz. " + src_name, [imp, rows])
    toplam = k.hesap("toplamlar", "Para birimi başına: veri satırı sayısı, Σ adet, Σ net, Σ brüt (toplam satırı hariç). "
                                  + src_name, [rows])
    fields = {key: sayac for key in ("satir", "eslesen", "eslesmeyen", "bosSatir", "ozetSatir")}
    fields.update({
        "toplamlar": toplam,
        "kurlar": k.hesap("kurlar", "Kur onayda kullanıcıdan alınır (1 birim = N TL); TRY için 1. Net TL = net × kur.", [imp]),
        "eslestirme": k.hesap("eslestirme", "Zeki AI eşleme önerisi işinin durumu: biten / toplam satır, modele sorulan satır, "
                                            "süre (sn).", [imp]),
        "satirlar[]": k.hesap("satirlar", "Satır: adet, brüt ve net tutar dosyadan (sayı biçimi okunarak); net TL onaydan sonra "
                                          "net × kur. " + src_name, [rows, names]),
        "satirlar[].olasilik": k.hesap("olasilik", F_ESLEME, [rows]),
        "satirlar[].adaylar": "hesap:olasilik",
    })
    k.alanlar(fields)
    return k


#: Rakam olmayan sayılar: CRM tip kodu, kimlikler, satır numarası, sayfa, kolon numarası, zaman damgası.
NOT_RAKAM = ("tip", "items[].tip", "risk[].tip", "incele[].tip", "platformlar[].platformId", "items[].platformlar[].platformId",
             "risk[].platformlar[].platformId", "incele[].platformlar[].platformId", "crmIslenecek[].id", "items[].id",
             "items[].platformId", "platformId", "page", "pageSize", "satirlar[].id", "satirlar[].sira", "kolonlar",
             "eslesmeyen[].id", "eslesmeyen[].sira", "aylik[].platformId", "okuma.since", "eslestirme.basladi")
