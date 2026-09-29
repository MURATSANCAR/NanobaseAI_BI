"""M44 Lojistik ve kargo: ekrandaki her rakamın sorgu bilgisi (ortak sözleşme `provenance.py`).

Rakamlar CRM (sipariş aşamaları, kargo firmasının gönderi kaydı, takip, sevkiyat) ve Logo (sevk, kargo faturası)
okumalarından Python'da hesaplanır. Okumalar beş dakika bellekte tutulur; gösterilen SQL o okumada ÇALIŞAN metnin kendisidir
(`shipping_sources.collect`: şema öneki, koşul, tarih penceresi yerinde; satır, süre ve çalıştığı an ile). Önbellekten gelen
rakamda da okumayı dolduran sorgu görünür. Ağır okumalar (günlük hat, gönderi kaydı) zamanlayıcının 15 dakikalık anlık
görüntüsünden de gelebilir (`semantic_shipping_snapshots`): o zaman ekranda çalışan portal okuması (`kargo.<etiket>.anlik`)
ve kökeni olarak zamanlayıcıda ÇALIŞAN CRM metni görünür. Kişisel kolonlar (alıcı, teslim alan) okuyan sorgu listelenmez; sonuç satırı
hiçbir koşulda kayda girmez. Kargo firmasının kimlik bilgisi kolonları hiçbir sorguda yoktur (`guard` + `clean_sql`).
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

from semantic_bridge import provenance as P
from semantic_bridge import shipping as S
from semantic_bridge.kaynak_ayar import ayar, bind, h

TITLES = {
    "crm_siparis_asama": "Sipariş aşamaları (CRM)", "crm_sevk_sayisi": "Sevk edilen sipariş sayısı (CRM)",
    "crm_kargo_firma": "Kargo firmaları (CRM, yalnız ad ve kod)", "crm_kargo_bilgisi": "Kargo firmasının gönderi kaydı (CRM)",
    "crm_kargo_takip": "Takip bilgisi (CRM)", "crm_sevkiyat": "Sevkiyatlar (CRM)", "crm_sevkiyat_ay": "Ayın sevkiyatları (CRM)",
    "crm_kutulandi_bekleyen": "Kutulanmış siparişler (CRM)", "crm_entegrasyon_hata": "Entegrasyon hatası koşulu (CRM)",
    "crm_takipsiz_sevk": "Takipsiz sevk koşulu (CRM)", "logo_sevk": "Logo sevk irsaliyeleri",
    "logo_fatura_no": "Logo fatura numaraları", "logo_kargo_fatura": "Logo kargo faturaları",
    "logo_kargo_cari_aday": "Logo'da kargo carisi adayları",
    "logo_kargo_gider": "Logo kargo ve nakliye gideri faturaları", "logo_kargo_alici": "Logo pazar yeri alıcılarına irsaliye",
    "logo_kargo_irsaliye": "Logo satış irsaliyeleri (taşıyıcı kodu)", "logo_net_ciro": "Logo net ciro (satış − iade faturası)",
}
TAGS = {"errors": "entegrasyon hatası olanlar", "untracked": "takip numarası olmadan sevk edilenler",
        "boxed": "kutulanıp sevk edilmemiş olanlar", "shipped": "pencerede sevk edilenler", "index": "gönderi kaydı",
        "carriers": "kargo firmaları", "reconcile": "mutabakat ayı", "shipments": "gönderi listesi sayfası",
        "cost": "kargo maliyeti yılı"}

F_SEVK = ("Sevk edilen = pencerede (son N gün, ayar) sevk tarihi olan ve durumu ayardaki «sevk» durumlarından olan CRM "
          "siparişleri; bugün = bugünün sevkleri.")
F_HATA = ("Entegrasyon hatası = pencerede, takip numarası olmayan ve dört kargo entegrasyonundan birinin sonucu ya da mesajı "
          "dolu ama «başarılı» sayılmayan (değer kümesi ayarda) sipariş; iptal, birleştirilmiş, taslak ve etkin olmayan hariç.")
F_SINIF = ("Hata sınıfını Zeki AI atar (kapalı küme; olasılık ve fark eşiğini geçmezse «Sınıflanmadı»); sayı = o sınıftaki "
           "sipariş, olasılık modelin seçime verdiği olasılık.")
F_TAKIPSIZ = ("Takip numarasız sevk = pencerede ayardaki sevk durumlarında olup takip numarası boş olan siparişler (ayardaki "
              "sipariş tipleri hariç).")
F_KUTU = ("Kutulandı, sevk edilmedi = durumu «Kutulandı» olan siparişler; bekleme = bugün − kutulandı tarihi (gün). Eşik "
          "(N gün) ekrandan verilen iş eşiği, yoksa ayar; tarihsiz = kutulandı tarihi boş olanlar.")
F_BEKLEYEN = ("Teslim bekleyen = kargo firmasının gönderi kaydında teslim tarihi olmayan ve iade olmayan gönderiler; yaş = "
              "bugün − kargo irsaliye tarihi, kovalar yaşa göre; eşik ekrandaki iş eşiği ya da ayar. Kayıttaki sayılar metin "
              "olarak durur, ondalık virgülle okunur; okunamayan değer sayılır, tahmin edilmez.")
F_KARNE = ("Firma karnesi (dönem = kargo irsaliye tarihi): gönderi = kayıt sayısı; teslim süresi = teslim − irsaliye günü "
           "(ortanca, ortalama, %90); iade oranı = iade ÷ gönderi; bekleyen = teslimsiz ve iadesiz; hedefi aşan = il hedef "
           "gününü aşan teslim; desi başı = Σ tutar ÷ Σ desi, sevk başı = Σ tutar ÷ Σ sevk adedi, gönderi başı = Σ tutar ÷ "
           "gönderi. Tutar KDV hariçtir (2024 Aras faturalarıyla ölçüldü).")
F_VERI = ("Kargo verisi: kayıt = okunan etkin gönderi kaydı; veri sonu = en son kargo irsaliye tarihi; tarihsiz ve okunamayan "
          "= tarihi ya da sayısı çevrilemeyen kayıt sayısı.")
F_SIPARIS = ("Sipariş satırı: koli = CRM koli adedi; kutulanalı gün = bugün − kutulandı (sevk yoksa); sevke kadar gün = sevk − "
             "sipariş tarihi.")
F_GONDERI = ("Gönderi kartı: kargo kaydı takip numarasıyla siparişe eşlenir; desi, ağırlık, tutar, sevk adedi kargo kaydından "
             "(tutar ve desi yalnız maliyet yetkisiyle); gün = teslim − irsaliye; zaman çizelgesindeki gün farkı = iki aşama "
             "tarihi arası.")
F_MUTABAKAT = ("Mutabakat (ay, kargo irsaliye tarihi): CRM kargo kaydı tutarı firma başına toplam; mükerrer = aynı takip "
               "numarasının ikinci ve sonraki kaydı; Logo = eşlenen kargo carilerinin alınan hizmet faturaları (KDV dahil ve "
               "hariç); fark = Logo − CRM. Sevk: Logo sevk irsaliyesi ↔ CRM sevkiyatı fatura numarasıyla eşleşme oranı.")
F_ADAY = ("Kargo carisi adayı = son 12 ayda alınan hizmet faturası olan ve ünvanında ipucu (ayar ve CRM firma adları) geçen "
          "Logo carileri: fatura sayısı ve KDV hariç toplam.")
F_GIDER = ("Kargo ve nakliye gideri = seçilen yılın Logo alınan hizmet faturalarında (iptal hariç) hizmet kodu ayardaki "
           "kodlardan olan satırların tutarı toplamı; satır tutarı KDV hariçtir. Fatura = bu satırları taşıyan fatura sayısı.")
F_GRUP = ("Tedarikçi grubu: vergi numarası (yoksa T.C. kimlik no) aynı yıl taşıyıcı kodlu satış irsaliyesi kestiğimiz bir alıcı "
          "carininkiyle aynıysa ve o alıcıya yılın taşıyıcı kodlu irsaliyelerinin en az %1'i gitmişse «Pazar yeri» (bize kargo "
          "faturası da kesen müşteri; birkaç gönderilik müşterinin tek seferlik faturası pazar yeri sayılmaz); değilse cari kodu «Kargo firması → Logo "
          "cari kodları» ayarındaysa «Kargo firması»; ikisi de değilse «Nakliye ve diğer». Grup tutarı = gruptaki "
          "tedarikçilerin gideri; pay = tedarikçinin gideri ÷ toplam gider.")
F_CIRO = ("Net ciro = satış faturaları (7, 8, 9) Σ (NETTOTAL − TOTALVAT) − iade faturaları (2, 3) Σ (NETTOTAL − TOTALVAT); "
          "KDV hariç, iptal hariç, ay = fatura tarihinin ayı.")
F_ORAN = "Cironun yüzdesi = kargo ve nakliye gideri ÷ net ciro (yıl ya da ay)."
F_IRSALIYE = ("İrsaliyeli gönderi = satış irsaliyeleri (7, 8; iptal hariç) içinde taşıyıcı kodu dolu olanların sayısı; kodu boş "
              "olanlar (mağaza kasa satışı, kargo yok) ayrıca sayılır, gönderiye girmez.")
F_IRS_BASI = ("Gönderi başı (yaklaşık) = dönemin kargo ve nakliye gideri ÷ dönemin irsaliyeli gönderisi. Faturalar toplu "
              "kesildiği için gider gönderiye bağlanamaz; faturası gecikmiş ay rakamı düşük gösterir.")
F_TASIYICI = ("Taşıyıcı = irsaliyedeki taşıyıcı kodu (harf büyüklüğü ve Türkçe harf farkı yok sayılır); CRM kargo firması "
              "koduyla eşlenip adı alınır, aynı firmaya düşen kodlar tek satırdır. Logo carisi «Kargo firması → Logo cari "
              "kodları» ayarından (firma adıyla ya da kodla). Gider = eşlenen carilerin yıl gideri; irsaliye başı = gider ÷ "
              "taşıyıcının irsaliyesi (yalnız eşlenmişse, yaklaşık). Pazar yerine giden = alıcısı pazar yeri olan irsaliye.")
F_PAZAR = ("Pazar yeri gönderisi başı = pazar yerinin kargo faturası toplamı ÷ o pazar yerinin alıcı carilerine (aynı vergi "
           "numarası) giden taşıyıcı kodlu irsaliye; başka bir tedarikçi carisine eşlenmiş taşıyıcıyla gidenler o "
           "tedarikçinin faturasında olduğundan sayılmaz («başka taşıyıcı»). Yaklaşıktır. Pazar yerlerinin "
           "ortancasından 10 kattan fazla sapan gönderi başı gösterilmez (gider büyük olasılıkla başka hesapta ya da tek "
           "seferlik).")
F_AYLIK = ("Ay: gider fatura tarihine, irsaliye irsaliye tarihine, net ciro fatura tarihine göre; gruplar tedarikçi grubundan, "
           "oran = ayın gideri ÷ ayın net cirosu, taşıyıcı kırılımı = ayın irsaliyesi taşıyıcıya göre.")


class Ship:
    """Uçta toplanan çalıştırmalar → `kargo.*` kaynakları. Aynı dosyanın farklı koşullu metinleri ayrı kayıttır."""

    def __init__(self, engine: Any, tenant: str, runs: Iterable[dict[str, Any]], deps: dict[str, Any]):
        self.engine, self.tenant, self.deps = engine, tenant, deps
        self.k = P.Kaynaklar(as_of=None)
        self.by_tag: dict[str, list[str]] = {}
        seen: dict[str, str] = {}
        count: dict[str, int] = {}
        for r in runs:
            if "AS alici" in r["sql"] or "AS teslim_alan" in r["sql"]:
                continue          # kişisel kolon okuyan tek kayıt sorgusu: rakam kaynağı değil, listelenmez
            if r.get("conn") == "portal":
                self._snapshot(r, seen)
                continue
            if r["sql"] in seen:
                sid = seen[r["sql"]]
            else:
                tag = r.get("tag") or ""
                base = f"kargo.{tag + '.' if tag else ''}{r['name']}"
                count[base] = count.get(base, 0) + 1
                sid = base if count[base] == 1 else f"{base}.{count[base]}"
                conn = "logo" if r["name"].startswith("logo_") else "crm"
                title = TITLES.get(r["name"], r["name"]) + (f" · {TAGS[tag]}" if tag in TAGS else "")
                desc = ""
                if r.get("anlik"):
                    desc = ("Bu okuma anlık görüntüye yazıldı (zamanlayıcı 15 dakikada bir yeniler); ekrandaki rakam bu "
                            "okumadandır, çalıştığı an yanında.")
                elif tag:
                    desc = "Okuma beş dakika bellekte tutulur; ekrandaki rakam bu okumadandır."
                self.k.sorgu(sid, title, conn, r["sql"], database=deps.get("logo_db") if conn == "logo" else deps.get("crm_db"),
                             rows=r.get("rows"), ms=r.get("ms"), ran_at=r.get("at"), description=desc)
                seen[r["sql"]] = sid
            self.by_tag.setdefault(r.get("tag") or r["name"], []).append(sid)

    def _snapshot(self, r: dict[str, Any], seen: dict[str, str]) -> None:
        """Portal anlık görüntü okuması: ekranda çalışan ifade; kökeni zamanlayıcıda çalışan CRM/Logo okuması (aynı etiket;
        görüntü iç içe okumalar taşıyorsa — mutabakattaki gönderi kaydı gibi — `tags`'teki her etiket)."""
        tag = r.get("tag") or ""
        tags = [t for t in (r.get("tags") or [tag]) if t is not None]
        if r["sql"] in seen:
            sid = seen[r["sql"]]
        else:
            sid = f"kargo.{tag}.anlik" if tag else "kargo.anlik"
            origin = [x for t in tags for x in self.by_tag.get(t, [])
                      if x in self.k.sources and self.k.sources[x]["connection"] != "portal"]
            origin = list(dict.fromkeys(origin))
            self.k.sorgu(sid, "Anlık görüntü (portal)" + (f" · {TAGS[tag]}" if tag in TAGS else ""), "portal", r["sql"],
                         rows=r.get("rows"), ms=r.get("ms"), ran_at=r.get("at"), origin=origin,
                         description=(f"CRM/Logo okumasının {r['alindi']} tarihli anlık görüntüsü" if r.get("alindi") else
                                      "CRM/Logo okumasının anlık görüntüsü") + "; zamanlayıcı ya da ilk açılış yazar, ekran "
                                     "kaynağı beklemeden buradan okur. Köken: o okumada çalışan CRM/Logo sorgusu.")
            seen[r["sql"]] = sid
        for t in dict.fromkeys(tags or [tag]):
            lst = self.by_tag.setdefault(t or r["name"], [])
            if sid not in lst:
                lst.append(sid)

    def t(self, *tags: str) -> list[str]:
        out: list[str] = []
        for tg in tags:
            out += [x for x in self.by_tag.get(tg, []) if x not in out]
        return out

    def ops(self) -> str:
        return self.k.portal("kargo.portal.esik", "Kargo iş eşikleri", S.ops_stmt(self.tenant), self.engine,
                             description="Ekrandan verilen eşikler (teslim bekleyen gün, kutulu gün, il hedefleri); kayıt "
                                         "yoksa yönetim ayarındaki varsayılan.")

    def classes(self) -> str:
        return self.k.portal("kargo.portal.sinif", "Hata mesajı sınıfları", S.classes_stmt(self.tenant), self.engine,
                             description="Zeki AI'ın her hata mesajına verdiği sınıf ve olasılık.")

    def settings(self, *keys: str) -> str:
        return ayar(self.k, self.engine, "kargo.ayar." + ".".join(x.lower() for x in keys), keys, "kargo")


def _new(engine: Any, tenant: str, runs: Iterable[dict[str, Any]], deps: dict[str, Any]) -> Ship:
    return Ship(engine, tenant, runs, deps)


# ------------------------------------------------------------------ uçlar


def for_overview(engine: Any, tenant: str, out: dict[str, Any], runs: list[dict[str, Any]], deps: dict[str, Any]) -> P.Kaynaklar:
    x = _new(engine, tenant, runs, deps)
    k = x.k
    win = x.settings("SHIPPING_WINDOW_DAYS")
    hata = h(k, "hata", F_HATA, x.t("errors", "carriers") + [win])
    bind(k, {
        "pencereGun": win,
        "sevk": h(k, "sevk", F_SEVK, x.t("shipped") + [x.settings("SHIPPING_SHIPPED_STATUSES", "SHIPPING_WINDOW_DAYS")]),
        "hata": hata, "hataSiniflari": h(k, "sinif", F_SINIF, [hata, x.classes()]),
        "takipsiz": h(k, "takipsiz", F_TAKIPSIZ, x.t("untracked") + [win]),
        "kutulandi": h(k, "kutu", F_KUTU, x.t("boxed") + [x.ops()]),
        "bekleyen": h(k, "bekleyen", F_BEKLEYEN, x.t("index") + [x.ops()]),
        "kargoVeri": h(k, "veri", F_VERI, x.t("index")),
        "son30": h(k, "karne", F_KARNE + " Son 30 gün = kargo verisinin son gününden geriye 30 gün.", x.t("index")),
    })
    return k


def _orders(x: Ship, prefix: str, tag: str) -> dict[str, Optional[str]]:
    o = h(x.k, f"siparis.{tag}", F_SIPARIS, x.t(tag, "crm_siparis_asama"))
    return {f"{prefix}.kutu": o, f"{prefix}.kutulanaliGun": o, f"{prefix}.sevkeKadarGun": o}


def for_errors(engine: Any, tenant: str, out: dict[str, Any], runs: list[dict[str, Any]], deps: dict[str, Any]) -> P.Kaynaklar:
    x = _new(engine, tenant, runs, deps)
    k = x.k
    hata = h(k, "hata", F_HATA, x.t("errors", "carriers") + [x.settings("SHIPPING_WINDOW_DAYS", "SHIPPING_INTEGRATION_OK_VALUES")])
    f = _orders(x, "items[]", "errors")
    f.update({"toplam": hata, "pencereGun": x.settings("SHIPPING_WINDOW_DAYS"),
              "items[].hatalar[].sinifOlasilik": h(k, "sinif", F_SINIF, [hata, x.classes()])})
    bind(k, f)
    return k


def for_untracked(engine: Any, tenant: str, out: dict[str, Any], runs: list[dict[str, Any]], deps: dict[str, Any]) -> P.Kaynaklar:
    x = _new(engine, tenant, runs, deps)
    f = _orders(x, "items[]", "untracked")
    f.update({"toplam": h(x.k, "takipsiz", F_TAKIPSIZ, x.t("untracked") + [x.settings("SHIPPING_UNTRACKED_STATUSES",
                                                                                         "SHIPPING_UNTRACKED_EXCLUDE_TYPES")]),
              "pencereGun": x.settings("SHIPPING_WINDOW_DAYS")})
    bind(x.k, f)
    return x.k


def for_boxed(engine: Any, tenant: str, out: dict[str, Any], runs: list[dict[str, Any]], deps: dict[str, Any]) -> P.Kaynaklar:
    x = _new(engine, tenant, runs, deps)
    kutu = h(x.k, "kutu", F_KUTU, x.t("boxed") + [x.ops()])
    f = _orders(x, "items[]", "boxed")
    f.update({"toplam": kutu, "esikUstu": kutu, "esikGun": x.ops(), "tarihsiz": kutu})
    bind(x.k, f)
    return x.k


def for_waiting(engine: Any, tenant: str, out: dict[str, Any], runs: list[dict[str, Any]], deps: dict[str, Any]) -> P.Kaynaklar:
    x = _new(engine, tenant, runs, deps)
    b = h(x.k, "bekleyen", F_BEKLEYEN, x.t("index") + [x.ops()])
    bind(x.k, {"toplam": b, "esikUstu": b, "kovalar": b, "firmalar": b, "items[]": b, "esikGun": x.ops(),
               "kargoVeri": h(x.k, "veri", F_VERI, x.t("index"))})
    return x.k


def for_carriers(engine: Any, tenant: str, out: dict[str, Any], runs: list[dict[str, Any]], deps: dict[str, Any]) -> P.Kaynaklar:
    x = _new(engine, tenant, runs, deps)
    c = h(x.k, "karne", F_KARNE, x.t("index") + [x.ops()])
    bind(x.k, {"items[]": c, "toplam": c, "kargoVeri": h(x.k, "veri", F_VERI, x.t("index"))})
    return x.k


def for_reconcile(engine: Any, tenant: str, out: dict[str, Any], runs: list[dict[str, Any]], deps: dict[str, Any]) -> P.Kaynaklar:
    x = _new(engine, tenant, runs, deps)
    m = h(x.k, "mutabakat", F_MUTABAKAT, x.t("index", "reconcile", "logo_kargo_fatura", "logo_sevk", "crm_sevkiyat_ay")
          + [x.settings("SHIPPING_LOGO_CARRIER_CODES")])
    bind(x.k, {"items[]": m, "sevk": m, "toplam": m, "kargoVeri": h(x.k, "veri", F_VERI, x.t("index"))})
    return x.k


def for_candidates(engine: Any, tenant: str, out: dict[str, Any], runs: list[dict[str, Any]], deps: dict[str, Any]) -> P.Kaynaklar:
    x = _new(engine, tenant, runs, deps)
    bind(x.k, {"items[]": h(x.k, "aday", F_ADAY, x.t("logo_kargo_cari_aday") + [x.settings("SHIPPING_LOGO_CARRIER_HINTS")])})
    return x.k


def for_shipments(engine: Any, tenant: str, out: dict[str, Any], runs: list[dict[str, Any]], deps: dict[str, Any]) -> P.Kaynaklar:
    x = _new(engine, tenant, runs, deps)
    bind(x.k, _orders(x, "items[]", "shipments"))       # sayfa okuması «shipments» etiketiyle (bellek/görüntü)
    return x.k


def for_shipment(engine: Any, tenant: str, out: dict[str, Any], runs: list[dict[str, Any]], deps: dict[str, Any]) -> P.Kaynaklar:
    x = _new(engine, tenant, runs, deps)
    k = x.k
    f = _orders(x, "siparis", "crm_siparis_asama")
    g = h(k, "gonderi", F_GONDERI, x.t("index", "crm_kargo_takip", "crm_siparis_asama"))
    f.update({"kargo": g, "zamanCizelgesi": g,
              "hatalar": h(k, "sinif", F_SINIF, x.t("crm_siparis_asama") + [x.classes()]),
              "kargoVeri": h(k, "veri", F_VERI, x.t("index"))})
    bind(k, f)
    return k


def _cost_runs(x: Ship, name: str) -> list[str]:
    """Kargo maliyeti okumasının (`cost` etiketi) bu dosyadan çalışan sorgusu; değer anlık görüntüden geldiyse görüntü
    okuması da (kökeni o sorgular)."""
    return [s for s in x.t("cost") if s.startswith(f"kargo.cost.{name}") or s == "kargo.cost.anlik"]


def for_cost(engine: Any, tenant: str, out: dict[str, Any], runs: list[dict[str, Any]], deps: dict[str, Any]) -> P.Kaynaklar:
    x = _new(engine, tenant, runs, deps)
    k = x.k
    svc = x.settings("SHIPPING_COST_SERVICE_CODES")
    mapc = x.settings("SHIPPING_LOGO_CARRIER_CODES")
    gider_q, alici_q = _cost_runs(x, "logo_kargo_gider"), _cost_runs(x, "logo_kargo_alici")
    irs_q, ciro_q = _cost_runs(x, "logo_kargo_irsaliye"), _cost_runs(x, "logo_net_ciro")
    gider = h(k, "gider", F_GIDER, gider_q + [svc])
    grup = h(k, "grup", F_GRUP, gider_q + alici_q + [svc, mapc])
    ciro = h(k, "ciro", F_CIRO, ciro_q)
    oran = h(k, "oran", F_ORAN, [gider, ciro])
    irs = h(k, "irsaliye", F_IRSALIYE, irs_q)
    basi = h(k, "gonderiBasi", F_IRS_BASI, [gider, irs])
    tas = h(k, "tasiyici", F_TASIYICI, irs_q + alici_q + x.t("carriers") + [gider, grup, mapc])
    pazar = h(k, "pazar", F_PAZAR, alici_q + [grup, mapc])
    aylik = h(k, "aylik", F_AYLIK, [gider, grup, ciro, irs])
    bind(k, {
        "totals.gider": gider, "totals.fatura": gider, "totals.tedarikci": gider,
        "totals.kargo": grup, "totals.pazarYeri": grup, "totals.nakliye": grup,
        "totals.netCiro": ciro, "totals.oran": oran, "totals.irsaliye": irs, "totals.tasiyiciYok": irs,
        "totals.irsaliyeBasi": basi,
        "byMonth[]": aylik, "bySupplier[]": grup, "byCarrier[]": tas, "marketplaces[]": pazar,
    })
    return k


#: Rakam olmayan sayılar: CRM durum/tip kodu, sayfa, Logo belge türü, ayardaki durum kodu listesi, seçilen ve seçilebilen yıl.
NOT_RAKAM = ("items[].durum", "items[].tip", "siparis.durum", "siparis.tip", "sayfa", "sayfaBoyu", "durumlar",
             "sevkiyatlar[].logo.tur", "items[].hatalar[].entegrasyon", "period.yil", "yillar")
