"""M8 Serbest çalışanlar (`/serbest-calisanlar`): ekrandaki her rakamın sorgu bilgisi (ortak sözleşme `provenance.py`).

Kişi, paket, görev, teslim, hakediş ve yazışma kendi portal tablolarımızdadır (`semantic_freelance_*`; ekrandan elle
girilir). Gösterilen SQL uçta çalışan ifadenin kendisidir (`freelance.*_stmt`). Sayılar, tutarlar (miktar × birim
ücret), zamanında teslim oranı, kapasite doluluğu ve öneri Python'da hesaplanır: formül metniyle.

Kişinin Logo hareketleri istek anında Logo'dan okunur (`freelance_logo`, cari kartın özel kodu ÇİZER, MÜTERCİM,
TASHİH-DİZ…; yalnız 2026 kopyası LG_411): gösterilen SQL o istekte ÇALIŞAN metindir (`sorgu_kaydi.RunLog`).
Kişisel veri (ad, e-posta, telefon, cari adı) sonuç satırıdır, kayda girmez; yalnız SQL metni ve satır sayısı.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from semantic_bridge import freelance as F
from semantic_bridge import freelance_logo as L
from semantic_bridge import provenance as P
from semantic_bridge.sorgu_kaydi import RunLog

PFX = "serbest."
#: Rakam olmayan sayılar: hakediş belge numarası (kimlik), Logo yıl kopyası, Logo hareket türü kodu, teslim sürümü ve
#: dosya boyutu (bayt), rol tanımındaki birim başına saat (modülün kodda sabit ilk önerisi, veri değil).
NOT_RAKAM = ("no", "items[].no", "payouts[].no", "year", "lines[].trcode", "roles[].hoursPerUnit",
             "tasks[].deliveries[].version", "tasks[].deliveries[].bytes", "portfolio[].bytes")

F_ELLE = "Ekrandan elle girilir (portal tablosu); hesap yok."
F_GOREV = ("Görev durumu: atanmadı, atandı, çalışıyor, teslim (inceleme bekliyor), revizyon, kabul edildi, iptal. Süren = "
           "atandı + çalışıyor + revizyon; termini geçen = sürenlerden termini bugünden önce olan.")
F_OZET = ("Atanmayı bekleyen = iptal edilmemiş paketlerde durumu «atanmadı» görev; süren iş = atandı/çalışıyor/revizyon; "
          "termini geçti = sürenlerden termini bugünden önce; teslim incelemesi = durumu «teslim» (kabul ya da revizyon "
          "bekleyen) görev. Aktif/pasif kişi = kişi kaydının durumu.")
F_ODENECEK = ("Ödenecek = kabul edilmiş, hakedişe girmemiş görevlerin Σ (miktar × birim ücret); iptal edilen paketler "
              "hariç. Tutarlar anlaşılan brüt ücrettir (KDV hariç); ödeme Logo'da yapılır.")
F_HAKEDIS = ("Hakediş başına sayı ve Σ toplam, duruma göre (taslak, onay bekliyor, onaylandı, ödendi; silinen taslak "
             "sayılmaz). Hakediş toplamı oluşturulduğu anki satır tutarlarıyla dondurulur.")
F_OKUNMAMIS = ("Okunmamış ileti = başkasının yazdığı (sistem satırı hariç) iletilerden, kişinin o yazışmayı en son açtığı "
               "andan sonra gelenler; toplam = bütün yazışmaların okunmamışları.")
F_KISI = ("Kişi istatistiği (iptal olmayan görevlerinden): süren = atandı/çalışıyor/revizyon; bekleyen = teslim; "
          "tamamlanan = kabul edildi; geciken = sürenlerden termini geçen; zamanında = ilk teslimi terminde ya da önce "
          "(İstanbul günü) olan / termini ve teslimi olan görev; ortalama revizyon = kabul edilenlerin revizyon sayısı "
          "ortalaması; ödenecek = kabul edilmiş, hakedişe girmemiş görevlerin Σ (miktar × birim ücret).")
F_PAKET = ("Paket satırı: görev sayısı ve duruma göre sayılar (iptal görevler hariç), tutar = Σ (miktar × birim ücret), "
           "geciken = sürenlerden termini geçen görev. «N paket» süzgece (durum, arama) uyan paket sayısıdır.")
F_TUTAR = "Görev tutarı = miktar × birim ücret (kuruşa yuvarlanır)."
F_KAPASITE = ("Kapasite (haftalık, saat) = kişinin haftalık saati × o haftadaki çalışılabilir iş günü / 5 (müsait olmadığı "
              "günler düşülür; içinde bulunulan haftada yalnız kalan günler). Yük = süren görevlerin tahmini saati, "
              "başlangıç–termin arasındaki kalan iş günlerine eşit dağıtılır; termini geçmiş iş bugüne yazılır. Doluluk = "
              "yük / kapasite (kapasite 0 iken yük varsa aşırı yük). Kişi satırındaki süren ve geciken iş = elindeki süren "
              "görevler ve bunlardan termini geçenler.")
F_ATANMAMIS = "Atanmayı bekleyen = açık paketlerde durumu «atanmadı» görev sayısı ve Σ tahmini saat."
F_ONERI = ("Öneri: rolü uyan aktif kişiler; boş saat = görev aralığındaki (başlangıç–termin, termin yoksa 14 gün) iş "
           "günlerinde kapasite − mevcut yük; sığar = boş saat ≥ görevin tahmini saati. Sıra: sığanlar önce, sonra boş saat "
           "çok, sonra zamanında teslim oranı yüksek (geçmiş teslimlerden). Birden çok görevde önerilen kişinin yükü "
           "sonraki göreve eklenir. İlk 5 aday gösterilir; sayılar gerekçe cümlesindekilerle aynıdır.")
F_ODENECEK_GRUP = ("Kişi başına ödenecek: kabul edilmiş, hakedişe girmemiş görevler; toplam = Σ görev tutarı (miktar × "
                   "birim ücret).")
F_LOGO = ("Logo'daki hareketler: cari kartın 2026 hareketleri (LG_411_01_CLFLINE, iptal olmayan). Alacak = SIGN 1 satırları "
          "Σ AMOUNT (alınan hizmet faturası, serbest meslek makbuzu, açılış), borç = SIGN 0 satırları Σ AMOUNT (ödeme, "
          "virman); bakiye = alacak − borç (pozitifse bizim borcumuz). Sorgu yılın bütün hareketlerini okur (sayı tavanı "
          "yok); okuma güvenlik sınırı aşılırsa toplam gösterilmez, ekranda nedeni yazar.")


def bagla_out(out: Any, build: Callable[[Any], Optional[P.Kaynaklar]]) -> Any:
    """Uçta tek satır: `return K.bagla_out(fl_mod.x(...), lambda out: K.for_x(..., out))`."""
    return P.bagla(out, lambda: build(out))


def _numeric(key: str, v: Any) -> bool:
    """Anahtarın altında rakam olmayan (NOT_RAKAM) dışında bir sayı var mı."""
    return bool(P.uncovered_numbers({key: v}, NOT_RAKAM))


def _rest(out: Any, fields: dict[str, str], ref: str) -> dict[str, str]:
    """Açıkça yazılmamış rakam taşıyan üst anahtarlar genel hesaba bağlanır (yeni alan kaynaksız kalmasın)."""
    if isinstance(out, dict):
        for key, v in out.items():
            if key != "kaynaklar" and key not in fields and _numeric(key, v):
                fields[key] = ref
    return fields


class _Ctx:
    def __init__(self, engine: Any, tenant: str):
        self.engine, self.tenant = engine, tenant
        self.k = P.Kaynaklar()

    def portal(self, sid: str, title: str, stmt: Any, desc: str) -> str:
        sid = PFX + sid
        if sid in self.k.sources:
            return sid
        return self.k.portal(sid, title, stmt, self.engine, description=desc)

    def unread(self, user: str, threads: Any, what: str) -> str:
        reads = self.portal(f"okunma.{what}", "Yazışmaların son okunma anı", F.unread_reads_stmt(self.tenant, user, threads),
                            f"Oturumdaki kişinin ({user}) yazışmaları en son açtığı an (semantic_freelance_reads).")
        msgs = self.portal(f"iletiler.{what}", "Başkasının yazdığı iletiler", F.unread_messages_stmt(self.tenant, user, threads),
                           "Sistem satırı hariç, oturumdaki kişinin yazmadığı iletiler (semantic_freelance_messages).")
        return self.k.hesap(f"okunmamis.{what}", F_OKUNMAMIS, [reads, msgs])


# ---------------------------------------------------------------- özet


def for_overview(engine: Any, tenant: str, user: str, out: dict[str, Any]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant)
    k = x.k
    people = x.portal("ozet.kisiler", "Kişi sayısı (aktif / pasif)", F.ov_people_stmt(tenant),
                      "Serbest çalışan kayıtları duruma göre (semantic_freelance_people). " + F_ELLE)
    tasks = x.portal("ozet.gorevler", "İptal edilmemiş paketlerin görevleri", F.ov_tasks_stmt(tenant),
                     "Görev durumu, termin, hakediş bağı, miktar ve birim ücret (semantic_freelance_tasks).")
    pays = x.portal("ozet.hakedisler", "Hakediş sayısı ve toplamı (duruma göre)", F.ov_payouts_stmt(tenant),
                    "semantic_freelance_payouts; silinen taslak hariç.")
    fields = {
        "people": k.hesap("kisiler", "Aktif / pasif kişi = kişi kaydının durumuna göre sayı.", [people]),
        "tasks": k.hesap("gorevler", F_OZET + " " + F_GOREV, [tasks]),
        "payable": k.hesap("odenecek", F_ODENECEK, [tasks]),
        "payouts": k.hesap("hakedisler", F_HAKEDIS, [pays]),
        "unread": x.unread(user, F.all_threads(tenant), "hepsi"),
    }
    k.alanlar(_rest(out, fields, "hesap:gorevler"))
    return k


# ---------------------------------------------------------------- kişiler


def for_people(engine: Any, tenant: str, out: dict[str, Any], status: str = "") -> P.Kaynaklar:
    x = _Ctx(engine, tenant)
    k = x.k
    people = x.portal("kisiler", "Serbest çalışan kayıtları", F.people_stmt(tenant, status),
                      "Kişi kartı: roller, haftalık saat, birim ücretler, durum (semantic_freelance_people). " + F_ELLE)
    tasks = x.portal("kisiGorevleri", "Kişilerin görevleri", F.people_tasks_stmt(tenant),
                     "Kişisi olan, iptal olmayan görevler: kişi istatistiği bunlardan hesaplanır.")
    stats = k.hesap("kisiIstatistik", F_KISI, [tasks])
    k.alanlar(_rest(out, {
        "items[]": people, "items[].stats": stats,
        "total": k.hesap("kisiSayisi", "«N kişi» = durum süzgecindeki kayıtlardan rol ve arama (ad, e-posta, şehir, üslup) "
                         "süzgecine uyanların sayısı.", [people]),
    }, people))
    return k


def for_person(engine: Any, tenant: str, person_id: str, out: dict[str, Any]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant)
    k = x.k
    person = x.portal("kisi", "Kişi kartı", F.person_stmt(tenant, person_id),
                      "Haftalık saat, birim ücretler, müsait olmadığı günler (semantic_freelance_people). " + F_ELLE)
    tasks = x.portal("kisi.gorevler", "Kişinin görevleri", F.person_tasks_stmt(person_id),
                     "İptal olmayan görevler ve paket adı; en yakın termin önce.")
    pays = x.portal("kisi.hakedisler", "Kişinin hakedişleri", F.person_payouts_stmt(person_id),
                    "Silinen taslak hariç; toplam oluşturulduğu andaki satır tutarlarıyla dondurulmuştur.")
    files = x.portal("kisi.portfolyo", "Portfolyo dosyaları", F.person_files_stmt(person_id), "Yüklenen görsel ve PDF'ler.")
    stats = k.hesap("kisiIstatistik", F_KISI, [tasks])
    tutar = k.hesap("gorevTutari", F_TUTAR + " " + F_GOREV, [tasks])
    k.alanlar(_rest(out, {
        "weeklyHours": person, "rates": person, "away": person, "stats": stats, "tasks[]": tutar, "payouts[]": pays,
        "portfolio[]": files,
        "sayac.suren": k.hesap("sayac.suren", "Süren işler = durumu atandı, çalışıyor, teslim ya da revizyon olan görev "
                               "sayısı; geçmiş işler = diğerleri (kabul edildi, atanmadı).", [tasks]),
        "sayac.hakedis": k.hesap("sayac.hakedis", "Hakediş sayısı = listedeki hakediş belgesi sayısı.", [pays]),
        "sayac.portfolyo": k.hesap("sayac.portfolyo", "Portfolyo = yüklenen dosya sayısı.", [files]),
    }, person))
    return k


# ---------------------------------------------------------------- paketler


def for_packages(engine: Any, tenant: str, user: str, out: dict[str, Any], status: str = "acik") -> P.Kaynaklar:
    x = _Ctx(engine, tenant)
    k = x.k
    pkgs = x.portal("paketler", "İş paketleri", F.packages_stmt(tenant, status),
                    "Paket: başlık, kitap, rol, termin, durum (semantic_freelance_packages). " + F_ELLE)
    tasks = x.portal("paketGorevleri", "Paketlerin görevleri", F.packages_tasks_stmt(tenant, status),
                     "Süzgeçteki paketlerin bütün görevleri; iptal görevler sayılmaz.")
    ref = k.hesap("paket", F_PAKET + " " + F_TUTAR + " " + F_GOREV, [pkgs, tasks])
    k.alanlar(_rest(out, {"items[]": ref, "items[].unread": x.unread(user, F.packages_threads(tenant, status), "paket"),
                          "total": ref}, ref))
    return k


def for_package(engine: Any, tenant: str, package_id: str, out: dict[str, Any]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant)
    k = x.k
    pkg = x.portal("paket", "İş paketi", F.package_stmt(tenant, package_id), F_ELLE)
    tasks = x.portal("paket.gorevler", "Paketin görevleri", F.package_tasks_stmt(package_id),
                     "Miktar, birim, birim ücret, tahmini saat, termin, durum, revizyon sayısı. " + F_ELLE)
    dels = x.portal("paket.teslimler", "Görevlerin teslimleri", F.package_deliveries_stmt(package_id),
                    "Dosya ya da bağlantı teslimleri, sürüm ve karar (semantic_freelance_deliveries).")
    tutar = k.hesap("gorevTutari", F_TUTAR + " " + F_GOREV, [tasks])
    k.alanlar(_rest(out, {"tasks[]": tutar, "tasks[].deliveries": dels,
                          "toplam": k.hesap("paketToplam", "Paket özeti (iptal olmayan görevlerden): bitti = kabul edilen görev / görev "
                                            "sayısı; toplam = Σ görev tutarı (miktar × birim ücret); tahmini = Σ tahmini saat.",
                                            [tasks])}, pkg))
    return k


# ---------------------------------------------------------------- kapasite ve öneri


def for_capacity(engine: Any, tenant: str, out: dict[str, Any]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant)
    k = x.k
    people = x.portal("kapasite.kisiler", "Aktif kişiler", F.active_people_stmt(tenant),
                      "Haftalık saat ve müsait olmadığı günler. " + F_ELLE)
    tasks = x.portal("kapasite.gorevler", "Süren görevler", F.capacity_tasks_stmt(tenant),
                     "Durumu atandı, çalışıyor ya da revizyon olan görevler: tahmini saat, başlangıç, termin.")
    una = x.portal("kapasite.atanmamis", "Atanmayı bekleyen görevler", F.unassigned_stmt(tenant),
                   "Açık paketlerde kişisi olmayan görev sayısı ve Σ tahmini saat.")
    ref = k.hesap("kapasite", F_KAPASITE, [people, tasks])
    k.alanlar(_rest(out, {
        "people[]": ref, "unassigned": k.hesap("atanmamis", F_ATANMAMIS, [una]),
        "sayac.kisi": k.hesap("sayac.kisi", "Aktif kişi = kapasite tablosundaki (rol süzgecine uyan) aktif kişi sayısı.", [people]),
        "sayac.asiri": k.hesap("sayac.asiri", "Kapasitesinin üstünde = gösterilen haftalardan en az birinde doluluğu 1'i "
                               "aşan kişi sayısı. " + F_KAPASITE, [ref]),
    }, ref))
    return k


def for_suggest(engine: Any, tenant: str, task_ids: list[str], out: dict[str, Any]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant)
    k = x.k
    tasks = [x.portal(f"oneri.gorev.{i + 1}", "Önerilen görev", F.task_stmt(tenant, tid), "Seçilen görev (rol, saat, aralık).")
             for i, tid in enumerate(task_ids[:200])]
    people = x.portal("oneri.kisiler", "Aktif kişiler", F.active_people_stmt(tenant), "Roller, haftalık saat, müsait olmadığı günler.")
    active = x.portal("oneri.sureni", "Kişilerin süren görevleri", F.suggest_active_stmt(tenant), "Mevcut yük.")
    hist = x.portal("oneri.gecmis", "Kişilerin geçmiş teslimleri", F.suggest_history_stmt(tenant),
                    "Zamanında teslim oranı bunlardan (ilk teslim ≤ termin).")
    ref = k.hesap("oneri", F_ONERI + " " + F_KAPASITE, tasks + [people, active, hist])
    k.alanlar(_rest(out, {"items[]": ref}, ref))
    return k


# ---------------------------------------------------------------- hakediş


def for_payable(engine: Any, tenant: str, out: dict[str, Any]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant)
    src = x.portal("odenecek", "Ödenecek işler", F.payable_stmt(tenant),
                   "Kabul edilmiş, hakedişe girmemiş görevler; kişi adıyla (semantic_freelance_tasks + packages + people).")
    ref = x.k.hesap("odenecekGrup", F_ODENECEK_GRUP + " " + F_TUTAR, [src])
    x.k.alanlar(_rest(out, {"items[]": ref}, ref))
    return x.k


def for_payouts(engine: Any, tenant: str, out: dict[str, Any], status: str = "", person_id: str = "") -> P.Kaynaklar:
    x = _Ctx(engine, tenant)
    src = x.portal("hakedisler", "Hakedişler", F.payouts_stmt(tenant, status, person_id),
                   "Hakediş belgeleri: durum, toplam, ödeme tarihi (semantic_freelance_payouts).")
    ref = x.k.hesap("hakedisToplam", "Durum başına Σ toplam = listedeki hakedişlerin toplamı, duruma göre. " + F_HAKEDIS, [src])
    x.k.alanlar(_rest(out, {"items[]": src, "totals": ref}, src))
    return x.k


def for_payout(engine: Any, tenant: str, payout_id: str, out: dict[str, Any]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant)
    head = x.portal("hakedis", "Hakediş belgesi", F.payout_stmt(tenant, payout_id), F_HAKEDIS)
    lines = x.portal("hakedis.satirlar", "Hakediş satırları", F.payout_lines_stmt(payout_id),
                     "Satırlar hakediş oluşturulduğu anki miktar, birim ücret ve tutarla dondurulur (semantic_freelance_payout_lines).")
    x.k.alanlar(_rest(out, {"total": head, "lines[]": lines}, head))
    return x.k


# ---------------------------------------------------------------- yazışma


def for_inbox(engine: Any, tenant: str, user: str, out: dict[str, Any]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant)
    last = x.portal("yazismalar", "Yazışma başına son ileti ve ileti sayısı", F.inbox_stmt(tenant),
                    "semantic_freelance_messages; sistem satırı da son hareket sayılır.")
    unread = x.unread(user, F.all_threads(tenant), "hepsi")
    x.k.alanlar(_rest(out, {"items[]": last, "items[].unread": unread, "unread": unread}, last))
    return x.k


# ---------------------------------------------------------------- Logo


def for_logo(out: dict[str, Any], log: RunLog, code: str, logo_file: Optional[str]) -> P.Kaynaklar:
    k = P.Kaynaklar()
    db = P.connection_database(logo_file)
    period = f"{L.YEAR} · Logo firma {L.FIRM}"
    card = log.sorgu(k, PFX + "logo.kart", "Logo cari kartı", "logo", L.card_sql(code), database=db, period=period,
                     description="Kişi kartındaki Logo cari kodu; özel kod (ÇİZER, MÜTERCİM, TASHİH-DİZ…) serbest çalışan "
                     "ödemesini ayırır.")
    lines = log.sorgu(k, PFX + "logo.hareketler", "Logo cari hareketleri · 2026", "logo", L.lines_sql(code), database=db,
                      period=period, description="Cari kartın 2026 hareketlerinin tamamı (fatura, makbuz, ödeme), en yeniden eskiye.")
    ins = [s for s in (card, lines) if s]
    if ins:
        ref = k.hesap("logoHareket", F_LOGO, ins)
        fields = {"lines[]": lines or ref, "credit": ref, "debit": ref, "balance": ref, "db": ref}
        k.alanlar(_rest(out, fields, ref))
    return k
