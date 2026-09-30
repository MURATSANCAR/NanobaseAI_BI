"""M37 Okur topluluğu: ekrandaki her rakamın sorgu bilgisi (ortak sözleşme `provenance.py`).

Okur sayıları (envanter, izin çelişkisi, ilgi alanı okur sayısı, segment büyüklüğü) M37'nin değil H2 okur veri tabanının
işidir: `readers_core.Provider` H2'nin okur profillerinden sayar. Gösterilen SQL, H2 profillerini okuyan portal okumasıdır;
profilleri dolduran CRM sorguları okuma turunun kaydettiği çalışmış metinleriyle `origin`dir (`readers_kaynak.origins`).
Gece anlık görüntüsü, segment, program ve yorum durumu M37'nin kendi portal tablolarıdır (semantic_okur_*).

KİŞİSEL VERİ: yalnız SQL metni ve satır sayısı kayda girer; okur satırı, ad, e-posta, telefon hiçbir zaman.
Yorum listesi sitenin yorum servisinden anlık okunur (SQL değil); o kısım hesap metninde açıklanır.
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

from semantic_bridge import okur as O
from semantic_bridge import okur_sources as src
from semantic_bridge import pazarlama_kaynak as PK
from semantic_bridge import provenance as P
from semantic_bridge import readers as R
from semantic_bridge import readers_core as RC
from semantic_bridge import readers_kaynak as RK

#: Rakam olmayan sayılar: ayarlar, sürüm, yıl listesi (seçim kutusu), yıl.
NOT_RAKAM = ("ayarlar", "surum", "items[].surum", "yil", "yillar", "hassasAcik")

F_ENVANTER = ("Okur envanteri okur veri tabanının etkin profillerinden sayılır: kaynak başına kayıt = o kaynakta kaydı olan "
              "etkin okur (bir okur birden çok kaynaktaysa her satırda sayılır); KVKK onaylı / e-posta izinli / SMS izinli = "
              "kanal başına son geçerli izin kanıtı «izinli» olan; İYS onaylı = İYS kaynağından «izinli» kanıtı olan; ilgi "
              "alanı dolu = en az bir ilgi alanı olan; 18 yaş altı olası = doğum yılından; toplam ve tekil = etkin okur "
              "sayısı. Oranlar = sayı ÷ satırın kaydı. Tazelik = kaynak başına son başarılı okuma.")
F_IZIN = ("İzin çelişkisi (hedef 0): aynı okurda aynı kanal için hem «izinli» hem «ret» kanıtı olan okur sayısı, kanal "
          "başına; ortak iletişim bilgisi = aynı e-posta/telefonu taşıyıp doğum yılları 12+ yıl ayrışan okur. Toplam = "
          "türlerin toplamı. Önceki ölçüm = bugünden önceki son gece anlık görüntüsünün toplamı.")
F_EGILIM = ("Aylık eğilim gece anlık görüntülerinden: gün başına kaynak satırlarının toplamı (okur kaydı, KVKK onaylı, "
            "İYS onaylı, e-posta izinli, SMS izinli) ve izin çelişkisi toplamı; ekranda her ayın son ölçümü.")
F_SEGMENT = ("Segment büyüklüğü okur veri tabanının segment motoruyla sayılır: toplam = kuralı sağlayan etkin okur; izinli = "
             "en az bir kanaldan dışa aktarılabilen (izin + yaş + KVKK kuralı); e-posta / SMS = o kanala aktarılabilen. Son "
             "ölçüm ve ölçüm geçmişi = segment tablosuna ve günlük ölçüm tablosuna yazılan sayım (üye listesi saklanmaz).")
F_PROGRAM = ("Program takvimi portal kaydından: kalan gün = program tarihi − bugün; katılımcı = programa elle girilen sayı; "
             "bağlı segmentin toplam / izinli sayısı = segmentin son ölçümü; toplam = süzgeçteki program sayısı.")
F_ILGI = ("İlgi alanı başına okur = okur veri tabanında o ilgi alanı işaretli etkin okur sayısı; olasılık = gece çağrışım "
          "sınıflamasının (Zeki AI) verdiği özel nitelikli çağrışım olasılığı ya da insan kararı; sayılar = işaret "
          "türü başına ilgi alanı sayısı.")
F_YORUM = ("Yorum sayıları sitenin yorum listesinden anlık okunur (site servisi; SQL değil, kısa süreli bellek önbelleği) ve "
           "portal yorum durumu tablosuyla birleşir: sitede cevabı olan «cevaplandı», portalda taslağı olan «taslak», "
           "gerisi «cevapsız»; toplam = yorum sayısı. Puan = yorumun sitedeki puanı. SEO özeti = gece SEO eşitlemesinin "
           "yorum toplamı ve yorumlu ürün sayısı.")
F_YORUM_GECE = ("Gece özeti = son gece turunda sitenin yorum listesiyle portal yorum durumunun birleşiminden sayılan cevapsız, "
                "taslak, cevaplandı ve toplam yorum (portal meta kaydı).")
F_ETKINLIK = ("Geçmiş etkinlikler CRM etkinlik kartlarından (başlangıç tarihi seçilen yılda): toplam = kayıt sayısı; durum "
              "başına sayı; katılımcı ve satılan kitap = yalnız «Tamamlandı» kayıtların toplamı; katılımcısı boş = tamamlanan "
              "ama katılımcı girilmemiş kayıt; tip / il / yazar kırılımı = tamamlananların etkinlik, katılımcı ve satılan "
              "toplamı.")


def _new(engine: Any, tenant: str) -> P.Kaynaklar:
    return P.Kaynaklar(as_of=R.last_run(engine, tenant).get("at"))


def _core(k: P.Kaynaklar, engine: Any, tenant: str) -> list[str]:
    """H2 okur profilleri ve izin kanıtları (portal) + onları dolduran CRM sorguları (origin)."""
    return RK._profiles(k, engine, tenant, RK.origins(k, engine, tenant))


def _envanter(k: P.Kaynaklar, engine: Any, tenant: str, core: list[str]) -> str:
    sync = k.portal("okur.tur", "Okuma turu ve kaynak tazeliği", R.sync_stmt(tenant), engine)
    iys = k.portal("okur.iys", "İYS kaynağından izinli okurlar", RC.iys_ok_stmt(tenant), engine,
                   description="Okur verisi değişmedikçe (okuma turu damgası) süreç belleğinden; yalnız okur kimliği sayılır.")
    return k.hesap("envanter", F_ENVANTER, core + [iys, sync])


def _celiski(k: P.Kaynaklar, engine: Any, tenant: str) -> str:
    return k.portal("okur.izin.celiski", "Kanal başına izin çelişkisi (etkin okur)", RC.conflicts_stmt(tenant), engine,
                    description="Okur × kanal başına hem «izinli» hem «ret» kanıtı; okur verisi değişmedikçe süreç belleğinden.")


def _trend(k: P.Kaynaklar, engine: Any, tenant: str, since: Optional[str], until: Optional[str]) -> str:
    q, cq = O.trend_stmts(tenant, since, until)
    ins = [k.portal("topluluk.egilim", "Gece envanter anlık görüntüleri (gün başına toplam)", q, engine),
           k.portal("topluluk.egilim.izin", "Gece izin çelişkisi anlık görüntüleri (gün başına toplam)", cq, engine)]
    return k.hesap("egilim", F_EGILIM, ins)


def _programs(k: P.Kaynaklar, engine: Any, tenant: str, stmt: Any, seg_ids: Iterable[str], title: str) -> str:
    ins = [k.portal("topluluk.program", title, stmt, engine)]
    ids = [i for i in seg_ids if i]
    if ids:
        ins.append(k.portal("topluluk.program.segment", "Programa bağlı segmentlerin son ölçümü",
                            O.seg_brief_stmt(tenant, ids), engine))
    return k.hesap("program", F_PROGRAM, ins)


def _flags(k: P.Kaynaklar, engine: Any, tenant: str) -> str:
    return k.portal("topluluk.ilgi.isaret", "İlgi alanı çağrışım işaretleri", O.flags_stmt(tenant), engine)


def for_overview(engine: Any, tenant: str, out: dict[str, Any], since: str) -> P.Kaynaklar:
    k = _new(engine, tenant)
    core = _core(k, engine, tenant)
    inv = _envanter(k, engine, tenant, core)
    prev = k.portal("topluluk.izin.onceki", "Önceki gece izin çelişkisi toplamı",
                    O.consent_previous_stmt(tenant, O.today().isoformat()), engine)
    izin = k.hesap("izin", F_IZIN, core + [_celiski(k, engine, tenant), prev])
    segs = k.portal("topluluk.segment.say", "Durum başına segment sayısı", O.segment_counts_stmt(tenant), engine)
    progs = out.get("yaklasanProgramlar") or []
    prog = _programs(k, engine, tenant, O.due_programs_stmt(tenant, 30), (p.get("segmentId") for p in progs),
                     "Önümüzdeki 30 gündeki programlar")
    yorum = k.hesap("yorum.gece", F_YORUM_GECE, [k.portal("topluluk.yorum.ozet", "Gece yorum özeti",
                                                          O.meta_stmt(tenant, "yorum_ozet"), engine)])
    k.alanlar({"envanter": inv, "izin": izin, "segmentSayilari": segs, "yaklasanProgramlar": prog, "yorum": yorum,
               "egilim": _trend(k, engine, tenant, since, None)})
    return k


def for_consent(engine: Any, tenant: str) -> P.Kaynaklar:
    k = _new(engine, tenant)
    core = _core(k, engine, tenant)
    prev = k.portal("topluluk.izin.onceki", "Önceki gece izin çelişkisi toplamı",
                    O.consent_previous_stmt(tenant, O.today().isoformat()), engine)
    ref = k.hesap("izin", F_IZIN, core + [_celiski(k, engine, tenant), prev])
    k.alanlar({"items": ref, "toplam": ref, "onceki": prev})
    return k


def for_inventory(engine: Any, tenant: str, since: Optional[str], until: Optional[str]) -> P.Kaynaklar:
    k = _new(engine, tenant)
    k.alan("noktalar", _trend(k, engine, tenant, since, until))
    return k


def for_categories(engine: Any, tenant: str) -> P.Kaynaklar:
    k = _new(engine, tenant)
    ref = k.hesap("ilgi", F_ILGI, _core(k, engine, tenant) + [_flags(k, engine, tenant)])
    k.alanlar({"items": ref, "sayilar": ref})
    return k


def for_segments(engine: Any, tenant: str, durum: str) -> P.Kaynaklar:
    k = _new(engine, tenant)
    ls = k.portal("topluluk.segment", "Segmentler ve son ölçümleri", O.segments_stmt(tenant, durum), engine)
    say = k.portal("topluluk.segment.say", "Durum başına segment sayısı", O.segment_counts_stmt(tenant), engine)
    k.alanlar({"items": k.hesap("segment", F_SEGMENT, [ls] + _core(k, engine, tenant)), "total": ls,
               "durumSayilari": say})
    return k


def for_segment(engine: Any, tenant: str, sid: str) -> P.Kaynaklar:
    k = _new(engine, tenant)
    seg = k.portal("topluluk.segment.kart", "Segment ve son ölçümü", O.segment_stmt(tenant, sid), engine)
    sz = k.portal("topluluk.segment.olcum", "Segmentin günlük ölçümleri", O.segment_sizes_stmt(sid), engine)
    pr = k.portal("topluluk.segment.program", "Segmente bağlı programlar", O.segment_programs_stmt(tenant, sid), engine)
    ref = k.hesap("segment", F_SEGMENT, [seg, sz] + _core(k, engine, tenant))
    k.alanlar({"sonOlcum": ref, "olcumler": sz, "programlar": pr, "kvkk": k.hesap("ilgi", F_ILGI, [_flags(k, engine, tenant)])})
    return k


def for_rule_preview(engine: Any, tenant: str) -> P.Kaynaklar:
    k = _new(engine, tenant)
    ref = k.hesap("segment", F_SEGMENT + " Kaydedilmemiş kural: sayım anlık, hiçbir tabloya yazılmaz.", _core(k, engine, tenant))
    k.alanlar({"olcum": ref, "kvkk": k.hesap("ilgi", F_ILGI, [_flags(k, engine, tenant)])})
    return k


def for_programs(engine: Any, tenant: str, out: dict[str, Any], filters: tuple[str, str, str, str]) -> P.Kaynaklar:
    k = _new(engine, tenant)
    items = out.get("items") or []
    ref = _programs(k, engine, tenant, O.programs_stmt(tenant, *filters), (p.get("segmentId") for p in items),
                    "Program takvimi")
    k.alanlar({"items": ref, "total": ref})
    return k


def for_program(engine: Any, tenant: str, pid: str, out: dict[str, Any]) -> P.Kaynaklar:
    k = _new(engine, tenant)
    ref = _programs(k, engine, tenant, O.program_stmt(tenant, pid), [out.get("segmentId") or ""], "Program kaydı")
    k.alanlar({"kalanGun": ref, "katilimci": ref, "segment": ref})
    return k


def for_events(runs: list[dict[str, Any]], schema: str, year: int, exclude: bool, types: list[str]) -> P.Kaynaklar:
    """Geçmiş etkinlikler: CRM'de çalışan iki sorgu (yıl listesi ve seçilen yılın etkinlikleri) çalıştığı metinle."""
    k = P.Kaynaklar()
    stats = {r["sql"]: r for r in runs}
    ys, es = src.event_years_sql(schema, exclude), src.events_sql(schema, year, exclude, types)

    def one(id_: str, title: str, sql: str, period: Optional[str] = None) -> str:
        r = stats.get(sql) or {}
        return k.sorgu(id_, title, "crm", sql, database=PK.crm_db(), rows=r.get("rows"), ms=r.get("dbMs"),
                       ran_at=r.get("at"), period=period,
                       description="CRM etkinlik kartları; okur kişisi seçilmez (yazar ve kitap adı yazara/kitaba aittir).")
    years = one("topluluk.etkinlik.yil", "Etkinlik yılları", ys)
    ev = one("topluluk.etkinlik", f"{year} etkinlikleri", es, str(year))
    ref = k.hesap("etkinlik", F_ETKINLIK, [ev])
    k.alanlar({"toplam": ref, "durumlar": ref, "tamamlanan": ref, "katilimci": ref, "satilan": ref, "katilimciBos": ref,
               "tipler": ref, "iller": ref, "yazarlar": ref, "etkinlikler": ev, "yillar": years})
    return k


def for_reviews(engine: Any, tenant: str, product_ids: list[str]) -> P.Kaynaklar:
    k = P.Kaynaklar()
    ins = [k.portal("topluluk.yorum.durum", "Portal yorum durumu ve taslaklar", O.review_status_stmt(tenant), engine)]
    ids = [i for i in product_ids if i]
    if ids:
        try:
            ins.append(k.portal("topluluk.yorum.urun", "Yorumlanan ürünlerin adı (SEO deposu)",
                                src.product_names_stmt(tenant, ids), engine))
        except ImportError:
            pass
    seo = None
    try:
        seo = k.portal("topluluk.yorum.seo", "SEO gece yorum özeti", src.seo_reviews_stmt(tenant), engine)
    except ImportError:
        pass
    ref = k.hesap("yorum", F_YORUM, ins + ([seo] if seo else []))
    k.alanlar({"items": ref, "sayilar": ref, "seo": seo or ref})
    return k
