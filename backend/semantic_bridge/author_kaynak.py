"""M7 Yazar ilişkileri (`/yazar-iliskileri`, `/kisiler` kişi ayrıntısındaki «İlişki»): her rakamın sorgu bilgisi.

- Kart, randevu ve görüşme notu portal tablolarındadır (elle girilir): uçta çalışan ifade (`author_relations.*_stmt`).
- Isı puanı, sadakat, aşama sayıları, «ilgi bekleyen» Python'da hesaplanır: formül metni (sabitler modülden okunur).
- Isı haritası, aday havuzu ve gelişim 5 dakikada bir hazırlanan CRM/Logo okumasından gelir (`author_snapshots`):
  asıl SQL o hazırlıkta ÇALIŞAN metindir (Logo yıllık satış görünümü yıl yıl), hazırlık kaydında saklanır. Kayıt yoksa
  (kayıt tutmayan önceki sürüm) köken boş kalır ve açıklama «ilk yenilemeden sonra görünür» der.
- İstek anında `run` ile okunan CRM (havuz canlı yolu, benzer kişi) `sorgu_kaydi.RunLog` ile: çalıştırıcının fiziksel
  metni, satır, süre, an.
- Model metni (öneri) rakam üretmez: «i» önerinin dayandığı olguların kaydını (girdi, portal) gösterir.
Kişisel veri (ad, iletişim, not metni) sonuç satırıdır, kayda girmez; yalnız SQL metni ve satır sayısı.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable, Optional

import sqlalchemy as sa

from semantic_bridge import author_copurchase as CP
from semantic_bridge import author_growth as G
from semantic_bridge import author_relations as R
from semantic_bridge import author_reminders as M
from semantic_bridge import provenance as P
from semantic_bridge.contributors_kaynak import crm_db
from semantic_bridge.sorgu_kaydi import RunLog, kaydet

PFX = "yazar."
#: Rakam olmayan sayılar: sayfa, sayfa boyu, istek parametresi olan gün penceresi, yıl, hazırlık durumu (saniye,
#: yenileme aralığı: süre bilgisi), çapraz yazar eşikleri (modül sabiti; formül metninde yazar), hakediş sözleşme no.
NOT_RAKAM = ("page", "pageSize", "days", "snapshot", "newBooksByYear[].year", "sales.years[].year", "minOrders", "minLift")

F_ELLE = "Ekrandan elle girilir (portal tablosu); hesap yok."
NO_READ = (" Bu hazırlığın sorgu kaydı yok (kayıt tutmayan önceki sürüm); çalışan CRM/Logo sorguları ilk yenilemeden "
           "sonra görünür.")


def f_isi() -> str:
    h = R.meta()["heat"]
    return (f"Isı puanı (0–100, yalnız insan temasından): yakınlık en çok {h['recencyMax']} (son görüşmeden bu yana "
            f"{h['recencyDays']} günde sıfırlanır; CRM'deki son iz — yazar adına yeni eser kaydı ya da başlayan sözleşme — "
            f"son görüşmeden yeniyse yakınlık ondan), sıklık: son {h['months']} ayda her görüşme {h['frequencyEach']} (en çok "
            f"{h['frequencyMax']}), ton: son üç görüşme en çok {h['toneMax']} (olumlu tam, nötr ya da tonsuz yarım, olumsuz 0). "
            "0–33 soğuk, 34–66 ılık, 67–100 sıcak; hiç görüşme ve iz yoksa «temas yok». Aylık hücre = o ayda yapılan "
            "görüşme sayısı; son 12 ayda görüşme = bunların toplamı; son görüşme = en son yapılan görüşmeden bu yana gün.")


def f_sadakat() -> str:
    L = G.LOYALTY
    return (f"Sadakat (0–100, yalnız CRM'den): birlikte geçen her yıl {L['yearEach']} (en çok {L['yearsMax']}), yazar olarak "
            f"her kitap {L['bookEach']} (en çok {L['booksMax']}), son 24 ayda yeni eser ya da sözleşme {L['recent24']} "
            f"(24–48 ay {L['recent48']}), yürürlükte sözleşme {L['active']}, birden çok sözleşme {L['returning']}. İlk ve son "
            "iz = yazar rolüyle eser kaydı ya da sözleşme başlangıcının en eskisi / en yenisi. 70 ve üstü bağlı, 40–69 "
            "düzenli, altı zayıf bağ.")


F_ILGI = ("«İlgi bekleyen»: sözleşmesi uyarı günü içinde biten ve 60 gündür görüşülmeyen yazar, notu girilmemiş geçmiş "
          "randevu, tarihi geçmiş sıradaki adım. Uyarı günü ayardan (EDITORIAL_CONTRACT_WARN_DAYS, varsayılan 60).")
F_HARITA = ("Isı haritası satırları: yürürlükte sözleşmesi olan yazarlar (CRM) ∪ kartı olan herkes (arşiv hariç). Hücre = o "
            "ayda yapılan görüşme; yeşil nokta = o ay CRM'de yazar adına yeni eser ya da başlayan sözleşme (sayısı). Bant "
            "sayıları ve «/ N» süzgece (kapsam, arama) uyan satırlardan; sayfa başına 50 satır gösterilir.")
F_KART = ("Aday kartı: aşama, sorumlu, görüşme sayısı (yapılan), açık adım (kapanmamış sıradaki adım). Aşama sayıları = "
          "arşivde olmayan kartlar aşamaya göre; «yazar» aşaması havuza girmez. «N aday kartı» = süzgece uyan kart.")
F_HAVUZ_TOPLAM = "Havuzdaki aday = aşama sayılarının toplamı, «vazgeçildi» hariç."
F_AJANDA = ("Randevular: ufka (bugün + gün penceresi) kadar planlanan randevular ve kapanmamış sıradaki adımı olan "
            "görüşmeler; «benim» = yazdığım, katılımcısı olduğum ya da kartın sorumlusu olduğum. Önümüzdeki = başlangıcı "
            "şimdiden sonra; notu eksik = başlangıcı geçmiş, hâlâ «planlandı»; açık adım = yapılmış görüşmenin kapanmamış "
            "sıradaki adımı, geciken = tarihi bugünden önce. Bu hafta = önümüzdeki 7 gün içindeki randevular.")
F_OZET = ("Sabah özeti (kişi başına): bugün ve yarın başlayacak randevular, notu girilmemiş geçmiş randevular (yazan "
          "kişiye), tarihi bugüne gelmiş kapanmamış sıradaki adımlar. Sayı = her grubun satır sayısı.")
F_HAVUZ = ("Aday havuzu (CRM): geçmiş penceresinden sonra açılan projelerde «olası yazar» olarak girilmiş, henüz yazar rolüyle "
           "eser kaydı olmayan kişiler; proje = kişinin bu projelerinin sayısı, son = en yeni projenin açılışı. Reddedilen/"
           "iptal projeler yalnız işaretlenince sayılır. «/ N» süzgece uyan kişi; sayfa başına 50.")
F_CAPRAZ = ("Birlikte alınan yazarlar: e-ticaret siparişleri (T-soft, gece eşitlemesi; müşteri bilgisi okunmaz) × CRM "
            "kitap → yazar eşlemesi (barkod). Bir siparişte farklı kitaplarıyla geçen iki yazar bir kez sayılır; iptal/iade "
            f"sayılmaz. Eşik: en az {CP.MIN_ORDERS} ortak sipariş ve lift = ortak × toplam sipariş / (A'nın × B'nin sipariş "
            f"sayısı) ≥ {CP.MIN_LIFT}. Pay = ortak / bu yazarın siparişi; fazla = ortak × (1 − 1/lift); sıra fazlaya göre.")
F_SATIS = ("Satış (Logo): yazarın CRM kitaplarının stok ve e-kitap stok kodlarıyla Logo yıllık satış görünümleri, faturalı "
           "satır, iade düşülmüş (adet ve net tutar eksi), 157 kodları ve bedelsiz satır dışarıda (hakediş ve Baskı önerisiyle "
           "aynı kural). Son 12 ay = veri sonunun ayı dahil son 12 ay; önceki 12 ay ondan önceki; değişim % = (son − önceki) "
           "/ önceki × 100 (±10 eşiği artış/düşüş). Yıllık ve aylık diziler aynı satırlardan.")
F_KITAP = ("Kitaplar: CRM'de yazar rolüyle eser kaydı olan kitaplar; adet/tutar/iade = kitabın kodlarıyla Logo satışı (aynı "
           "kural). Stok kodu olan = stok ya da e-kitap stok kodu dolu. Yeni kitap (yıl) = ilk yayın tarihi (yoksa eser kaydı) "
           "o yıl olan kitap sayısı.")
F_HAKEDIS = ("Telif: M6'da bu yazarın CRM sözleşmelerine bağlı sözleşme kayıtlarının iptal edilmemiş hakedişleri (sözleşme "
             "oranıyla orada hesaplanır; burada tahmin üretilmez). Sözleşme sayısı = CRM'de yazarın taraf olduğu sözleşmeler.")
F_OKUR = ("Okur sesi: sitedeki yorum özeti (kitap barkodu = ürün barkodu; onaylı yorum sayısı, puanlı sayısı, ortalama = Σ puan "
          "/ puanlı, yıldız dağılımı) ve açıksa basın ve web taramasında yazarın anıldığı haberlerin tonu (etikete göre sayı).")
F_ONERI = ("Öneri metnini Zeki AI yazar; metindeki her sayı önerinin girdisindeki olgularla (satış, kitaplar, sadakat, ilişki "
           "ısısı, okur, son notlar) karşılaştırılır, tutmayan cümle çıkarılır. Girdi öneri kaydıyla birlikte saklanır; "
           "girdideki sayılar gelişim ve ilişki hesaplarındandır.")


class _Ctx:
    def __init__(self, engine: Any, tenant: str, logo_db: Optional[str] = None):
        self.engine, self.tenant = engine, tenant
        self.dbs = {"crm": crm_db(), "logo": logo_db}
        self.k = P.Kaynaklar()

    def portal(self, sid: str, title: str, stmt: Any, desc: str, origin: Iterable[str] = ()) -> str:
        sid = PFX + sid
        if sid in self.k.sources:
            return sid
        return self.k.portal(sid, title, stmt, self.engine, description=desc, origin=origin)

    def crm_text(self, sid: str, title: str, sql: str, desc: str) -> str:
        """CRM metni (istekte ya da gece turunda çalışan; sonuç saklanmaz)."""
        sid = PFX + sid
        if sid in self.k.sources:
            return sid
        return self.k.sorgu(sid, title, "crm", sql, database=self.dbs["crm"], description=desc)

    # ---- portal
    def cards(self, archived: bool = False) -> str:
        return self.portal("kartlar" + (".arsiv" if archived else ""), "Yazar kartları", R.cards_stmt(self.tenant, archived),
                           "İlişki kartları: aşama, sorumlu, CRM kişisi (semantic_author_cards). " + F_ELLE)

    def meetings(self) -> str:
        return self.portal("gorusmeler", "Randevu ve görüşmeler", R.live_meetings_stmt(self.tenant),
                           "İptal edilmemiş randevu ve görüşme notları (semantic_author_meetings). " + F_ELLE)

    def settings(self) -> str:
        from semantic_bridge import admin as ADM

        src = self.portal("ayar", "Sözleşme uyarı günü (ekrandan girilen)",
                          sa.select(ADM.SETTINGS.c.key, ADM.SETTINGS.c.value).where(
                              ADM.SETTINGS.c.key.in_(("EDITORIAL_CONTRACT_WARN_DAYS", "AUTHOR_POOL_SINCE"))),
                          "Yönetim ekranında girilen ayar; girilmeyen ayar ortam değerinden ya da varsayılandan (60 gün, "
                          "havuz başlangıcı 2024-01-01) gelir.")
        return self.k.hesap("ayar", F_ILGI, [src])

    # ---- hazırlık (anlık görüntü) kaydı
    def prepared(self, queries: Optional[dict[str, Any]], tags: Iterable[str] = ()) -> dict[str, str]:
        """Hazırlıkta çalışan CRM sorguları (etiket → kayıt) ve Logo yıllık satış sorguları («satis.<yıl>»)."""
        out: dict[str, str] = {}
        want = set(tags)
        q = queries or {}
        titles = {"sozlesmeliYazarlar": "CRM: yürürlükte sözleşmesi olan yazarlar",
                  "olaylar": "CRM: son 12 ayda yazar olayları (yeni eser, başlayan sözleşme)",
                  "sadakat": "CRM: yazarların sadakat izi (ilk/son iz, kitap, sözleşme)",
                  "kitaplar": "CRM: yazar rolüyle bütün kitaplar (stok kodu, barkod)",
                  "havuz": "CRM: olası yazarların projeleri (aday havuzu)"}
        for it in q.get("crm") or []:
            tag = str(it.get("tag") or "")
            if want and tag not in want:
                continue
            try:
                out[tag] = kaydet(self.k, f"{PFX}hazirlik.{tag}", titles.get(tag, "CRM hazırlık sorgusu"), "crm", it,
                                  database=self.dbs["crm"],
                                  description="Hazırlıkta (5 dakikada bir, «Yenile» ile hemen) çalıştı; sonuç satırları "
                                              "kayda girmez.")
            except P.ProvenanceError:
                continue
        if not want or "satis" in want:
            for it in q.get("sales") or []:
                y = it.get("year")
                try:
                    out[f"satis.{y}"] = kaydet(self.k, f"{PFX}hazirlik.satis.{y}", f"Logo satış · {y}", "logo", it,
                                               database=self.dbs["logo"], period=f"{y} · Logo yıllık satış görünümü",
                                               description="Hazırlıkta çalıştı: stok kodu × ay × satış/iade (içinde "
                                                           "bulunulan yıl her turda, geçmiş yıllar günde bir).")
                except P.ProvenanceError:
                    continue
            de = q.get("dataEnd")
            if de and de.get("sql"):
                try:
                    out["satis.verisonu"] = self.k.sorgu(f"{PFX}hazirlik.verisonu", "Logo satışının son fatura günü", "logo",
                                                         de["sql"], database=self.dbs["logo"], ran_at=de.get("at"))
                except P.ProvenanceError:
                    pass
        return out

    def note(self, got: dict[str, str]) -> str:
        return "" if got else NO_READ


# ---------------------------------------------------------------- kartlar, ajanda, özet


def for_cards(engine: Any, tenant: str, out: dict[str, Any], archived: bool = False) -> P.Kaynaklar:
    x = _Ctx(engine, tenant)
    k = x.k
    cards, ms = x.cards(archived), x.meetings()
    isi = k.hesap("isi", f_isi(), [ms])
    ref = k.hesap("kart", F_KART, [cards, ms, isi])
    k.alanlar({"items[]": ref, "items[].heat": isi, "total": ref, "stages": ref,
               "havuzToplam": k.hesap("havuzToplam", F_HAVUZ_TOPLAM, [ref])})
    return k


def for_agenda(engine: Any, tenant: str, out: dict[str, Any]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant)
    k = x.k
    cards = x.portal("kartlarHepsi", "Yazar kartları (arşiv dahil)", R.all_cards_stmt(tenant), F_ELLE)
    hz = datetime.fromisoformat(out["horizon"]) if out.get("horizon") else R.agenda_horizon(R._now(), out.get("days") or 30)
    ms = x.portal("ajanda", "Ajandanın randevu ve adımları", R.agenda_meetings_stmt(tenant, hz),
                  "Ufka kadar planlanan randevular ve kapanmamış sıradaki adımlar (semantic_author_meetings). " + F_ELLE)
    ref = k.hesap("ajanda", F_AJANDA, [cards, ms])
    k.alanlar({"upcoming[]": ms, "missingNotes[]": ms, "openSteps[]": ms,
               "sayac.hafta": ref, "sayac.notEksik": ref, "sayac.gecikenAdim": ref, "sayac.onumuzdeki": ref,
               "sayac.adim": ref})
    return k


def for_reminders_me(engine: Any, tenant: str, out: dict[str, Any]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant)
    today = R._now().astimezone(R.TZ).date()
    cards = x.portal("kartlar", "Yazar kartları", R.cards_stmt(tenant), F_ELLE)
    ms = x.portal("ozet", "Özetin randevu ve adımları", M.digest_meetings_stmt(tenant, today),
                  "Planlanan randevular ve tarihi bugüne gelmiş kapanmamış sıradaki adımlar.")
    x.k.alanlar({"today": x.k.hesap("ozet", F_OZET, [cards, ms])})
    return x.k


# ---------------------------------------------------------------- aday havuzu


def for_pool_snapshot(engine: Any, tenant: str, out: dict[str, Any], queries: Optional[dict[str, Any]]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant)
    k = x.k
    got = x.prepared(queries, ["havuz"])
    ids = [i.get("crmContactId") for i in out.get("items") or [] if i.get("crmContactId")]
    ins = list(got.values())
    if ids:
        ins.append(x.portal("havuzKartlari", "Havuzdaki kişilerin kartları", R.cards_of_stmt(tenant, ids),
                            "Bu sayfadaki CRM kişilerinin ilişki kartı (kartı var işareti)."))
    ref = k.hesap("havuz", F_HAVUZ + x.note(got), ins or [x.cards()])
    k.alanlar({"items[]": ref, "total": ref})
    return k


def for_pool_live(engine: Any, tenant: str, out: dict[str, Any], log: RunLog, schema: str, since: str, page: int,
                  q: str = "", closed: bool = False) -> P.Kaynaklar:
    x = _Ctx(engine, tenant)
    k = x.k
    db = x.dbs["crm"]
    head = log.sorgu(k, PFX + "havuz.sayim", "CRM: olası yazar sayısı", "crm", R.pool_count_sql(schema, since, q, closed),
                     database=db, description="Hazırlık bitmeden istekte canlı çalıştı.")
    lst = log.sorgu(k, PFX + "havuz.liste", "CRM: olası yazarlar (bu sayfa)", "crm",
                    R.pool_list_sql(schema, since, page, q, closed), database=db,
                    description=f"Sayfa başına {R.PAGE_SIZE}; sayfa {int(page) + 1}.")
    ids = [i["crmContactId"] for i in out.get("items") or [] if i.get("crmContactId")]
    prj = log.sorgu(k, PFX + "havuz.projeler", "CRM: sayfadaki kişilerin projeleri", "crm",
                    R.pool_projects_sql(schema, since, ids), database=db) if ids else None
    ins = [s for s in (head, lst, prj) if s]
    if ids:
        ins.append(x.portal("havuzKartlari", "Havuzdaki kişilerin kartları", R.cards_of_stmt(tenant, ids),
                            "Bu sayfadaki CRM kişilerinin ilişki kartı."))
    if ins:
        ref = k.hesap("havuz", F_HAVUZ, ins)
        fields = {"items[]": ref, "total": ref}
        if lst:
            fields["db"] = lst
        k.alanlar(fields)
    return k


# ---------------------------------------------------------------- ısı haritası


def for_heatmap(engine: Any, tenant: str, schema: str, out: dict[str, Any], queries: Optional[dict[str, Any]]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant)
    k = x.k
    cards, ms = x.cards(), x.meetings()
    if queries is not None:
        got = x.prepared(queries, ["sozlesmeliYazarlar", "olaylar", "sadakat"])
        note = x.note(got)
    else:
        months = out.get("months") or R.month_keys()
        live = ("Hazırlık bitmeden canlı çalıştı (tam sonuç); aynı sorgunun sonucu hazırlık aralığı (5 dk) kadar süreç "
                "içi bellekten verilir, «Verileri yenile» kaynağı bekler.")
        got = {"sozlesmeliYazarlar": x.crm_text("canli.sozlesmeliYazarlar", "CRM: yürürlükte sözleşmesi olan yazarlar",
                                                R.contracted_authors_sql(schema), live),
               "olaylar": x.crm_text("canli.olaylar", "CRM: son 12 ayda yazar olayları",
                                     R.crm_events_sql(schema, months[0] + "-01"), live),
               "sadakat": x.crm_text("canli.sadakat", "CRM: yazarların sadakat izi", G.loyalty_sql(schema), live)}
        note = ""
    isi = k.hesap("isi", f_isi() + note, [ms] + ([got["olaylar"]] if "olaylar" in got else []))
    sad = k.hesap("sadakat", f_sadakat() + note, [got["sadakat"]] if "sadakat" in got else [cards])
    crm_ev = got.get("olaylar")
    crm_au = got.get("sozlesmeliYazarlar")
    ayar = x.settings()
    ref = k.hesap("harita", F_HARITA + " " + F_ILGI + note, [cards, ms, isi, ayar] + [s for s in (crm_au, crm_ev) if s])
    fields = {"items[]": ref, "items[].heat": isi, "items[].loyalty": sad, "total": ref, "bands": ref,
              "attention": ref, "warnDays": ayar}
    if crm_ev:
        fields.update({"items[].crm": crm_ev, "items[].crmBooks": crm_ev, "items[].crmContracts": crm_ev})
    if crm_au:
        fields["items[].contracts"] = crm_au
    k.alanlar(fields)
    return k


# ---------------------------------------------------------------- kart paneli


def _trace(x: _Ctx, schema: str, contact_id: Optional[str]) -> list[str]:
    if not contact_id:
        return []
    return [x.crm_text("iz", "CRM: yazarın son izi (son eser kaydı, son başlayan sözleşme)", R.crm_trace_sql(schema, contact_id),
                       "Kart açılırken istekte çalıştı; yakınlık payına son iz olarak girer.")]


def for_card(engine: Any, tenant: str, schema: str, out: dict[str, Any]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant)
    k = x.k
    card = x.portal("kart", "Yazar kartı", R.card_stmt(tenant, out["id"]), F_ELLE)
    ms = x.portal("kart.gorusmeler", "Kartın randevu ve görüşmeleri", R.card_meetings_stmt(out["id"]),
                  "İptal edilenler zaman çizelgesinde görünür, ısıya girmez. " + F_ELLE)
    isi = k.hesap("isi", f_isi(), [ms] + _trace(x, schema, out.get("crmContactId")))
    k.alanlar({"heat": isi, "timeline[]": ms, "kart": card})
    return k


def for_by_crm(engine: Any, tenant: str, schema: str, contact_id: str, out: dict[str, Any]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant)
    k = x.k
    cid = R._guid(contact_id)
    card = x.portal("kart", "CRM kişisinin kartı", R.card_by_crm_stmt(tenant, cid), F_ELLE)
    ins = [card]
    c = out.get("card") or {}
    if c.get("id"):
        ms = x.portal("kart.gorusmeler", "Kartın randevu ve görüşmeleri", R.card_meetings_stmt(c["id"]), F_ELLE)
        ins.append(ms)
        k.alan("timeline[]", ms)
    isi = k.hesap("isi", f_isi(), ins + _trace(x, schema, cid))
    k.alan("heat", isi)
    return k


def for_similar(out: dict[str, Any], log: RunLog, schema: str, name: str) -> P.Kaynaklar:
    k = P.Kaynaklar()
    try:
        asked = R.similar_sql(schema, name)
    except R.RelationError:
        return k
    src = log.sorgu(k, PFX + "benzer", "CRM: aynı adlı kişiler", "crm", asked, database=crm_db(),
                    description="Adın her sözcüğü geçen etkin CRM kişileri; ilk 20 kişi döner, toplam «COUNT(*) OVER ()».")
    if src:
        k.alan("crmTotal", src)
    return k


def for_related(engine: Any, tenant: str, schema: str, contact_id: str, page: int, out: dict[str, Any]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant)
    k = x.k
    cid = (contact_id or "").strip().lower()
    orders = x.portal("siparisler", "E-ticaret siparişleri (eşitlenmiş)", CP.orders_stmt(tenant),
                      "Gece turunda T-soft siparişlerinden yalnız sipariş no, gün, durum saklanır; müşteri bilgisi okunmaz.")
    lines = x.portal("siparisSatirlari", "Sipariş satırlarının barkodu", CP.lines_stmt(tenant),
                     "Kitap → yazar eşlemesi barkodla.")
    books = x.crm_text("kitapYazar", "CRM: barkod → kitap ve yazar", CP.book_authors_sql(schema),
                       "Gece turunda çalışır (çapraz yazar hesabı).")
    st = CP.related_stmts(tenant, cid, page)
    origin = [orders, lines, books]
    total = x.portal("capraz.toplam", "Birlikte alınan yazar sayısı", st["total"], "semantic_author_copurchase.", origin)
    rows = x.portal("capraz.liste", "Birlikte alınan yazarlar (bu sayfa)", st["rows"],
                    f"Sayfa başına {CP.PAGE_SIZE}; beklenenden fazla ortak siparişe göre.", origin)
    own = x.portal("capraz.kendi", "Yazarın kendi sipariş sayısı", st["own"], "semantic_author_copurchase.", origin)
    run = x.portal("capraz.tur", "Son başarılı gece turu", CP.last_run_stmt(tenant),
                   "Okunan sipariş, eşleşen satır, çift sayısı (semantic_author_copurchase_runs).")
    ref = k.hesap("capraz", F_CAPRAZ, [rows, total, own])
    k.alanlar({"items[]": ref, "total": total, "authorOrders": own, "run": run})
    return k


# ---------------------------------------------------------------- gelişim ve öneri


def for_growth(engine: Any, tenant: str, schema: str, contact_id: str, out: dict[str, Any],
               queries: Optional[dict[str, Any]], logo_file: Optional[str]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant, P.connection_database(logo_file))
    k = x.k
    meta = out.pop("_sorgular", None) or {}
    k.data_end = P._iso(out.get("dataEnd"))
    prepared = bool(out.get("preparedAt"))
    live_crm: dict[str, str] = {}
    for it in meta.get("crm") or []:
        asked = it.get("asked") or ""
        tag = ("sozlesmeler" if asked == G.contracts_sql(schema, contact_id) else
               "kitaplar" if asked == G.books_sql(schema, contact_id) else
               "sadakat" if asked == G.loyalty_sql(schema, contact_id) else None)
        if not tag:
            continue
        try:
            live_crm[tag] = kaydet(k, f"{PFX}gelisim.{tag}", {"sozlesmeler": "CRM: yazarın sözleşmeleri",
                                                              "kitaplar": "CRM: yazarın kitapları",
                                                              "sadakat": "CRM: yazarın sadakat izi"}[tag], "crm", it,
                                   database=x.dbs["crm"], description="Gelişim hesabında çalıştı.")
        except P.ProvenanceError:
            continue
    note = ""
    if prepared:
        got = x.prepared(queries, ["kitaplar", "sadakat", "satis"])
        books = [got["kitaplar"]] if "kitaplar" in got else []
        loyal = [got["sadakat"]] if "sadakat" in got else []
        sales = [v for key, v in got.items() if key.startswith("satis.")]
        note = x.note(got)
    else:
        books = [live_crm["kitaplar"]] if "kitaplar" in live_crm else []
        loyal = [live_crm["sadakat"]] if "sadakat" in live_crm else []
        cache = x.portal("gelisim.sakli", "Saklı gelişim hesabı (12 saat)", G.growth_cache_stmt(tenant, contact_id),
                         "Hazırlık bitmeden canlı okunan yazarın hesabı 12 saat saklanır.")
        sales = [cache]
        note = (" Hazırlık bitmeden canlı okundu: Logo satış sorgusu bu yolda kaydedilmez; ilk hazırlıktan sonra "
                "hazırlıkta çalışan yıllık satış sorguları görünür.")
    fallback = books or loyal or sales or list(live_crm.values())
    if not fallback:
        return k
    kitap_ref = k.hesap("kitaplar", F_KITAP + note, books or fallback)
    satis_ref = k.hesap("satis", F_SATIS + note, (sales + books) or fallback)
    fields: dict[str, str] = {
        "books[]": k.hesap("kitapSatis", F_KITAP + " " + F_SATIS + note, (books + sales) or fallback),
        "booksTotal": kitap_ref, "booksWithCode": kitap_ref, "newBooksByYear[]": kitap_ref,
        "sales": satis_ref,
        "loyalty": k.hesap("sadakat", f_sadakat() + note, loyal or fallback),
    }
    roy_in = [live_crm["sozlesmeler"]] if "sozlesmeler" in live_crm else []
    ids = meta.get("contractIds") or []
    if ids:
        try:
            st = G.statements_stmts(tenant, ids)
            roy_in.append(x.portal("gelisim.hakedis", "M6 hakedişleri", st["statements"],
                                   "Yazarın CRM sözleşmelerine bağlı sözleşme kayıtlarının iptal edilmemiş hakedişleri."))
        except Exception:  # noqa: BLE001 — hakediş modülü bu ortamda yoksa bölüm boştur
            pass
    fields["royalty"] = k.hesap("telif", F_HAKEDIS, roy_in or fallback)
    eans = meta.get("eans") or []
    okur: list[str] = []
    if eans:
        try:
            okur.append(x.portal("gelisim.yorum", "Sitedeki yorum özeti", G.reviews_stmts(tenant, eans)["reviews"],
                                 "Yazarın kitaplarının barkoduyla eşleşen ürünlerin yorum sayaçları (gece eşitlemesi)."))
        except Exception:  # noqa: BLE001
            pass
    if out.get("readers", {}).get("web") is not None:
        try:
            okur.append(x.portal("gelisim.web", "Basın ve web taramasında ton", G.web_tone_stmt(tenant, R._guid(contact_id)),
                                 "Yazarın anıldığı haberler, etikete göre sayı."))
        except Exception:  # noqa: BLE001
            pass
    fields["readers"] = k.hesap("okur", F_OKUR + ("" if okur else " Yazarın kitaplarında barkod olmadığından yorum ve ton "
                                                         "okunmadı; sayılar 0."), okur or books or fallback)
    k.alanlar(fields)
    return k


def for_advice(engine: Any, tenant: str, contact_id: str, out: dict[str, Any], key: str = "advice") -> P.Kaynaklar:
    """GET: cevap {"advice": {...}}; POST: cevap önerinin kendisi (`key=""`)."""
    x = _Ctx(engine, tenant)
    k = x.k
    src = x.portal("oneri", "Son öneri kaydı ve girdisi", G.latest_advice_stmt(tenant, contact_id),
                   "Önerinin metni ve dayandığı olgular (girdi) birlikte saklanır (semantic_author_advice).")
    ref = k.hesap("oneri", F_ONERI, [src])
    if key:
        k.alan(key, ref)
    else:
        k.alanlar({name: ref for name, v in out.items() if name != "kaynaklar" and P.numeric_paths({name: v})})
    return k
