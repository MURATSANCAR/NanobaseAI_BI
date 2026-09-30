"""Aşama 0 — pazar yeri satış modeli tespiti (Trendyol, Amazon TR). Kullanıcı kararı 2026-09-29: model tahmin edilmez,
Logo'dan (ve CRM'den) salt okuma ile ölçülür; ekranda «Bu kanalın satış modeli: … (kanıt: …)» yazar. Belirsizse ekran
bunu söyler. Karar metni ve kurallar `docs/analiz/trendyol-amazon-satis-modeli.md` › «Kararlar» ve §6.

**Pazar yeri carisi nasıl bulunur (koda sabit cari adı/kodu yok):**
1. M42 cari eşlemesinde bu platforma bağlı (onaylı ya da aday) cari kodları (`semantic_channel_accounts`);
2. kanal kodu (özel kod 2) bütünüyle bu platforma bağlanmışsa o kanaldaki cariler (`kanal-platform:<kod>` ayarı);
3. unvanında platformun adı ya da Yönetim ayarındaki adlar (`TRENDYOL_CARI_ADLARI` / `AMAZON_CARI_ADLARI`,
   `CHANNEL_PLATFORM_HINTS`) kelime sınırıyla geçen ve başka platformu işaret etmeyen cariler (`mapping.name_candidate`);
4. panel sipariş numarası Logo faturasında bulunursa (Aşama 1 okuması) o faturaların türü ve cari sayısı ayrıca kanıttır.

**Sınıflama (kural; eşikler Yönetim ayarı):**
- *konsinye izi*: bu carilere `PAZARYERI_KONSINYE_GUN` günden eski faturalanmamış satış irsaliyesi ya da sevkten bu kadar
  günden geç faturalanmış sevk;
- *toptan izi*: bu carilere toptan satış faturası (TRCODE 8);
- *kendi mağaza izi*: bu carilere perakende satış faturası (TRCODE 7), belge alanında platform adı geçen perakende
  fatura ya da pazar yeri carisi sayısından çok farklı cariye kesilmiş fatura, panel siparişinin tüketici faturasında
  bulunması, ya da satış faturası olmadan platformdan alınan hizmet faturası (komisyon);
- tek iz → o model (iz `PAZARYERI_GUCLU_AY` farklı ayda görülürse «güçlü», yoksa «zayıf»); konsinye + toptan → konsinye
  (konsinye sattıkça toptan faturayla kapanır); kendi mağaza + toptan/konsinye → belirsiz («karma»); iz yok → belirsiz.

Rakamları SQL üretir; model (LLM) kullanılmaz. Okuma ham toplamları `semantic_channel_meta` › `model:<platform>` altına
yazar, sınıflama her istekte bu toplamlardan yapılır (ayar değişince yeniden okuma gerekmez). Okumada koşan Logo/CRM
sorguları «asıl sorgu» olarak `model.<platform>` anahtarıyla saklanır (sorgu bilgisi).
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, timedelta
from typing import Any, Callable, Iterable, Optional

import sqlalchemy as sa

from semantic_bridge.channels import mapping as M
from semantic_bridge.channels import platform_common as PC
from semantic_bridge.channels import sources as src
from semantic_bridge.channels import store as S

log = logging.getLogger("semantic.channels.pazaryeri_model")

PLATFORMS = ("trendyol", "amazon")
MODELS = {
    "kendi-magaza": "Kendi mağaza (pazar yeri satıcısıyız; tüketiciye biz faturalıyoruz)",
    "toptan": "Toptan (platform bizden faturayla satın alıyor)",
    "konsinye": "Konsinye (malı gönderiyoruz, sattıkça faturalıyoruz)",
    "belirsiz": "Belirsiz",
}
#: Logo belge türü adları (Logo'nun standart kodları; bilinmeyen kod «Tür N» yazar).
FATURA_TURU = {1: "Mal alım", 2: "Perakende satış iadesi", 3: "Toptan satış iadesi", 4: "Alınan hizmet", 6: "Alım iadesi",
               7: "Perakende satış", 8: "Toptan satış", 9: "Verilen hizmet", 13: "Alınan fiyat farkı", 14: "Verilen fiyat farkı"}
CARI_HAREKET = {1: "Nakit tahsilat", 2: "Nakit ödeme", 3: "Borç dekontu", 4: "Alacak dekontu", 5: "Virman", 6: "Kur farkı",
                12: "Özel işlem", 14: "Açılış", 20: "Gelen havale", 21: "Gönderilen havale", 31: "Satınalma faturası",
                32: "Perakende satış iade faturası", 33: "Toptan satış iade faturası", 34: "Alınan hizmet faturası",
                36: "Satınalma iade faturası", 37: "Perakende satış faturası", 38: "Toptan satış faturası",
                39: "Verilen hizmet faturası", 41: "Verilen vade farkı", 42: "Alınan vade farkı", 43: "Alınan fiyat farkı",
                44: "Verilen fiyat farkı", 61: "Çek girişi", 62: "Senet girişi", 63: "Çek çıkışı", 64: "Senet çıkışı",
                70: "Kredi kartı fişi", 71: "Kredi kartı iade fişi"}
MODUL = {4: "Fatura", 5: "Cari fiş", 6: "Çek/senet", 7: "Banka", 10: "Kasa", 61: "Kredi kartı"}

#: Kesinti ve hakediş kalemleri: hizmet kartı adı ya da ekstre işlem tipi/açıklamasından kural (sıra önemli: «satış
#: komisyonu» komisyondur, «satış iadesi» iadedir). Kelimeler Türkçe harfleri sadeleştirilmiş, küçük harf.
KALEMLER: list[tuple[str, str, tuple[str, ...]]] = [
    ("stopaj", "Stopaj / tevkifat", ("stopaj", "tevkifat", "withholding")),
    ("komisyon", "Komisyon", ("komisyon", "commission", "referral", "prim")),
    ("iade", "İade", ("iade", "return", "refund")),
    ("odeme", "Ödeme / transfer", ("odeme", "transfer", "havale", "payment", "disbursement", "payout")),
    ("kargo", "Kargo ve gönderim", ("kargo", "shipping", "fba", "fulfil", "lojistik", "gonderi", "tasima", "nakliye")),
    ("hizmet", "Platform hizmet bedeli", ("hizmet bedeli", "platform hizmet", "service fee", "islem bedeli", "subscription",
                                          "abonelik", "hizmet ucreti")),
    ("reklam", "Reklam", ("reklam", "advertis", "sponsor", "tanitim")),
    ("ceza", "Ceza", ("ceza", "penalt", "gecikme bedeli", "tedarik edememe")),
    ("vergi", "KDV / vergi", ("kdv", "vergi", "tax")),
    ("indirim", "İndirim / kupon", ("indirim", "kupon", "coupon", "promosyon", "promotion", "kampanya")),
    ("satis", "Satış", ("satis", "sale", "order", "principal", "siparis", "itemprice")),
]
KALEM_AD = {k: a for k, a, _ in KALEMLER} | {"diger": "Diğer", "net-hakedis": "Net hakediş (dosyadaki)"}
KESINTI = ("komisyon", "kargo", "hizmet", "stopaj", "reklam", "ceza", "diger")


def kalem(text: Any) -> str:
    f = M.fold(text)
    for key, _, words in KALEMLER:
        if any(w in f for w in words):
            return key
    return "diger"


def kesinti_kalem(text: Any) -> str:
    """Alış tarafı hizmet satırı (Logo) için kalem: gider olmayan sınıf (satış, ödeme, iade…) «diğer» sayılır —
    «Satış Nakliye Giderleri» kargodur, satış değil."""
    k = kalem(text)
    return k if k in KESINTI else "diger"


def label(table: dict[int, str], code: Any) -> str:
    try:
        c = int(code)
    except (TypeError, ValueError):
        return str(code)
    return table.get(c, f"Tür {c}")


def settings(conf: Callable[[str], str]) -> dict[str, Any]:
    """Yönetim → Platform ve kanallar (`PAZARYERI_*`, `MUTABAKAT_*`). Başlangıç değerleri ölçülmemiştir."""
    f = lambda k, d: PC.conf_float(conf, k, d)  # noqa: E731
    return {
        "yil": max(1, int(f("PAZARYERI_MODEL_YIL", 2))),
        "konsinyeGun": max(1, int(f("PAZARYERI_KONSINYE_GUN", 30))),
        "gucluAy": max(1, int(f("PAZARYERI_GUCLU_AY", 3))),
        "baskinPay": min(1.0, max(0.5, f("PAZARYERI_BASKIN_PAY", 0.9))),
        "toleransGun": max(0, int(f("MUTABAKAT_TOLERANS_GUN", 15))),
        "tutarTolerans": max(0.0, f("MUTABAKAT_TUTAR_TOLERANS", 1.0)),
    }


def _dedup(xs: Iterable[str]) -> list[str]:
    seen, out = set(), []
    for x in xs:
        k = M.fold(x)
        if x and x.strip() and k not in seen:
            seen.add(k)
            out.append(x.strip())
    return out


def name_rules(conf: Callable[[str], str], platform: str) -> dict[str, Any]:
    """Aranacak adlar: platformun kendi adı (kapalı platform listesi) + Yönetim ayarları. Koda sabit cari adı yok."""
    from semantic_bridge.channels import amazon as A
    from semantic_bridge.channels import trendyol as T

    own = (T.settings(conf) if platform == "trendyol" else A.settings(conf))["cariAdlari"]
    hints = {k: list(v) for k, v in M.settings(conf)["hints"].items()}
    hints[platform] = _dedup(list(hints.get(platform, [])) + list(own))
    return {"desenler": _dedup([M.PLATFORMS[platform]] + hints[platform]), "hints": hints}


def mapped_codes(engine: sa.engine.Engine, tenant: str, platform: str) -> dict[str, str]:
    """M42 eşlemesinde bu platforma bağlı cariler: kod → durum (onayli | aday)."""
    with engine.connect() as c:
        rows = c.execute(sa.select(S.ACCOUNTS.c.logo_cari_kodu, S.ACCOUNTS.c.durum)
                         .where(S.ACCOUNTS.c.tenant_id == tenant, S.ACCOUNTS.c.platform == platform,
                                S.ACCOUNTS.c.durum.in_(("onayli", "aday")))).all()
    return {r[0]: r[1] for r in rows}


# ------------------------------------------------------------------ SQL


def _like(col: str, patterns: Iterable[str]) -> list[str]:
    return [f"{col} LIKE {src.q('%' + p + '%')}" for p in patterns]


def cariler_sql(firm: str, patterns: list[str], codes: list[str], kanallar: list[str]) -> str:
    parts = _like("C.DEFINITION_", patterns)
    if codes:
        parts.append(f"C.CODE IN ({src._in(codes)})")
    if kanallar:
        parts.append(f"C.SPECODE2 IN ({src._in(kanallar)})")
    return src._fill("mp_cariler", firm=firm, kosul=" OR ".join(parts) or "1 = 0")


def _span(name: str, firm: str, bas: date, bit: date, codes: list[str], **kw: Any) -> str:
    return src._fill(name, firm=firm, bas=bas.isoformat(), bit=bit.isoformat(), codes=src._in(codes), **kw)


BELGE_ALANLARI = ("DOCODE", "SPECODE", "CYPHCODE", "GENEXP1", "GENEXP2", "GENEXP3", "GENEXP4")


def belge_metni_sql(firm: str, bas: date, bit: date, patterns: list[str]) -> str:
    kosul = " OR ".join(x for f in BELGE_ALANLARI for x in _like(f"F.{f}", patterns)) or "1 = 0"
    return src._fill("mp_belge_metni", firm=firm, bas=bas.isoformat(), bit=bit.isoformat(), kosul=kosul)


def crm_firma_sql(p: str, bas: date, patterns: list[str]) -> str:
    return src._fill("mp_crm_firma", p=p, bas=bas.isoformat(), kosul=" OR ".join(_like("a.Name", patterns)) or "1 = 0")


def crm_tip_sql(p: str) -> str:
    return src._fill("mp_crm_siparis_tipi", p=p)


# ------------------------------------------------------------------ okuma


def koken(platform: str) -> str:
    return f"model.{platform}"


def meta_key(platform: str) -> str:
    return f"model:{platform}"


def _i(v: Any) -> int:
    try:
        return int(float(v or 0))
    except (TypeError, ValueError):
        return 0


def _chunks(xs: list[str]) -> Iterable[list[str]]:
    for i in range(0, len(xs), src.IN_CHUNK):
        yield xs[i:i + src.IN_CHUNK]


def discover(run: src.Runner, engine: sa.engine.Engine, tenant: str, platform: str, conf: Callable[[str], str],
             firms: Iterable[str]) -> dict[str, dict[str, Any]]:
    """Pazar yeri carileri (kural 1–3). Kod → {kod, unvan, kanal, kartTuru, kurallar}."""
    rules = name_rules(conf, platform)
    mapped = mapped_codes(engine, tenant, platform)
    kanallar = sorted(k for k, v in M.kanal_map(engine, tenant).items() if v == platform)
    eticaret = {M.fold(x) for x in M.settings(conf)["specodes"]}
    cards: dict[str, dict[str, Any]] = {}
    for firm in dict.fromkeys(firms):
        for r in run(cariler_sql(firm, rules["desenler"], sorted(mapped), kanallar)):
            code = PC.cell(r.get("cari_kodu"), 80)
            if not code:
                continue
            unvan = PC.cell(r.get("unvan"), 300) or None
            kanal = PC.cell(r.get("kanal"), 60) or None
            why = []
            if code in mapped:
                why.append("esleme-onayli" if mapped[code] == "onayli" else "esleme-aday")
            if kanal and kanal in kanallar:
                why.append("kanal")
            if M.name_candidate({"unvan": unvan}, rules["hints"]) == platform:
                why.append("ad")
            if not why:
                continue
            c = cards.setdefault(code, {"kod": code, "unvan": unvan, "kanal": kanal, "kartTuru": _i(r.get("kart_turu")) or None,
                                        "kurallar": [], "hesapDisi": None})
            c["kurallar"] = sorted(set(c["kurallar"]) | set(why))
            # Yalnız adı tutan, kanal kodu e-ticaret dışında (kitapçı, yurtdışı, diğer…) olan cari: aynı adı taşıyan başka
            # işletme ya da kapsam dışı (S3: yurtdışı) — listelenir, kanıta girmez. Eşleme/kanal kuralı bunu geçersiz kılar.
            c["hesapDisi"] = (f"kanal kodu {kanal} (e-ticaret değil)" if c["kurallar"] == ["ad"] and kanal
                              and M.fold(kanal) not in eticaret else None)
    return cards


def counted(cards: dict[str, dict[str, Any]]) -> list[str]:
    """Kanıta giren cariler (hesap dışı olanlar hariç)."""
    return sorted(k for k, c in cards.items() if not c.get("hesapDisi"))


def refresh(engine: sa.engine.Engine, tenant: str, platform: str, logo_file: str, crm_file: str, crm_schema: str,
            conf: Callable[[str], str], step: Callable[[str], None] = lambda s: None) -> dict[str, Any]:
    from semantic_bridge import sorgu_yakala as Y

    if platform not in PLATFORMS:
        raise ValueError("Bilinmeyen platform.")
    S.ensure(engine)
    q, token = Y.baslat(engine)
    try:
        out = _measure(engine, tenant, platform, logo_file, crm_file, crm_schema, conf, step)
    finally:
        Y.bitir(token)
    Y.koken_yaz(engine, tenant, koken(platform), q)
    return {"ok": True, "cari": len([c for c in out["cariler"] if not c.get("hesapDisi")]), "veriSonu": out["veriSonu"], "crmHata": (out.get("crm") or {}).get("hata")}


def _measure(engine: sa.engine.Engine, tenant: str, platform: str, logo_file: str, crm_file: str, crm_schema: str,
             conf: Callable[[str], str], step: Callable[[str], None]) -> dict[str, Any]:
    from semantic_bridge import eticaret_sources as E
    from semantic_bridge import sorgu_yakala as Y

    st = settings(conf)
    rules = name_rules(conf, platform)
    run = Y.izle(src.runner(logo_file), "logo", Y.db_of(logo_file))
    step("Logo dönemleri")
    firms = src.firms_by_year(run)
    if not firms:
        raise src.SourceError("Logo'da dönem bulunamadı.")
    end = E.read_data_end(run, firms) or date.today()
    years = [y for y in range(end.year - st["yil"] + 1, end.year + 1) if y in firms]
    bas, bit = date(min(years), 1, 1), end + timedelta(days=1)
    eski = end - timedelta(days=st["konsinyeGun"])
    step("Pazar yeri carileri")
    cards = discover(run, engine, tenant, platform, conf, [firms[y] for y in years])
    codes = counted(cards)
    raw: dict[str, list[dict[str, Any]]] = {k: [] for k in ("faturalar", "hizmetler", "hareketler", "sevk", "gecikme",
                                                            "doluluk", "belgeMetni")}
    for y in years:
        firm = firms[y]
        a, b = max(bas, date(y, 1, 1)), min(bit, date(y + 1, 1, 1))
        if a >= b:
            continue
        step(f"{y} belge metni")
        for r in run(belge_metni_sql(firm, a, b, rules["desenler"])):
            raw["belgeMetni"].append({"yil": y, "ay": _i(r.get("ay")), "tur": _i(r.get("tur")), "kanal": PC.cell(r.get("kanal"), 60) or None,
                                      "fatura": _i(r.get("fatura")), "cari": _i(r.get("cari")), "tutar": src._f(r.get("tutar"))})
        if not codes:
            continue
        for part in _chunks(codes):
            step(f"{y} fatura türleri")
            for r in run(_span("mp_fatura_turu", firm, a, b, part)):
                raw["faturalar"].append({"yil": y, "ay": _i(r.get("ay")), "cari": PC.cell(r.get("cari"), 80), "tur": _i(r.get("tur")),
                                         "fatura": _i(r.get("fatura")), "tutar": src._f(r.get("tutar")), "doviz": _i(r.get("doviz"))})
            step(f"{y} hizmet satırları")
            for r in run(_span("mp_hizmet", firm, a, b, part)):
                raw["hizmetler"].append({"yil": y, "ay": _i(r.get("ay")), "cari": PC.cell(r.get("cari"), 80), "tur": _i(r.get("tur")),
                                         "hizmetKodu": PC.cell(r.get("hizmet_kodu"), 60), "hizmet": PC.cell(r.get("hizmet"), 200),
                                         "satir": _i(r.get("satir")), "tutar": src._f(r.get("tutar"))})
            step(f"{y} cari hareketleri")
            for r in run(_span("mp_cari_hareket", firm, a, b, part)):
                raw["hareketler"].append({"yil": y, "ay": _i(r.get("ay")), "cari": PC.cell(r.get("cari"), 80), "modul": _i(r.get("modul")),
                                          "tur": _i(r.get("tur")), "yon": _i(r.get("yon")), "hareket": _i(r.get("hareket")),
                                          "tutar": src._f(r.get("tutar"))})
            step(f"{y} faturalanmamış sevk")
            for r in run(_span("mp_sevk", firm, a, b, part, eski=eski.isoformat())):
                raw["sevk"].append({"yil": y, "ay": _i(r.get("ay")), "cari": PC.cell(r.get("cari"), 80), "tur": _i(r.get("tur")),
                                    "satir": _i(r.get("satir")), "adet": src._f(r.get("adet")), "eskiSatir": _i(r.get("eski_satir")),
                                    "eskiAdet": src._f(r.get("eski_adet"))})
            step(f"{y} sevk → fatura gecikmesi")
            for r in run(_span("mp_fatura_gecikme", firm, a, b, part, gun=st["konsinyeGun"])):
                raw["gecikme"].append({"yil": y, "cari": PC.cell(r.get("cari"), 80), "satir": _i(r.get("satir")),
                                       "gecSatir": _i(r.get("gec_satir")), "gecAdet": src._f(r.get("gec_adet")),
                                       "enUzunGun": _i(r.get("en_uzun_gun")), "gecAy": _i(r.get("gec_ay"))})
            step(f"{y} belge alanları")
            for r in run(_span("mp_anahtar_doluluk", firm, a, b, part)):
                raw["doluluk"].append({"yil": y, "tur": _i(r.get("tur")), "fatura": _i(r.get("fatura")),
                                       **{f.lower(): _i(r.get(f.lower())) for f in BELGE_ALANLARI + ("DOCTRACKINGNR",)}})
    crm: dict[str, Any] = {"hata": None, "firmalar": [], "tipler": {}}
    try:
        step("CRM firma kartları")
        crun = Y.izle(src.runner(crm_file), "crm", Y.db_of(crm_file))
        p = E.prefix(crm_schema)
        crm["tipler"] = {str(r.get("kod")): PC.cell(r.get("ad"), 120) for r in crun(crm_tip_sql(p)) if r.get("kod") is not None}
        firms_crm: dict[str, dict[str, Any]] = {}
        for r in crun(crm_firma_sql(p, bas, rules["desenler"])):
            ad = PC.cell(r.get("ad"), 200)
            if not ad or M.name_candidate({"unvan": ad}, rules["hints"]) != platform:
                continue
            f = firms_crm.setdefault(ad, {"ad": ad, "logoRef": PC.cell(r.get("logicalref"), 40) or None, "siparis": {}})
            if r.get("tip") is not None and _i(r.get("sayi")):
                key = f"{_i(r.get('tip'))}"
                f["siparis"][key] = f["siparis"].get(key, 0) + _i(r.get("sayi"))
        crm["firmalar"] = sorted(firms_crm.values(), key=lambda x: x["ad"])
    except src.SourceError as e:
        crm["hata"] = str(e)
    out = {"platform": platform, "veriSonu": end.isoformat(), "yillar": years, "bas": bas.isoformat(), "bit": end.isoformat(),
           "eskiSevkTarihi": eski.isoformat(), "desenler": rules["desenler"], "cariler": [cards[c] for c in sorted(cards)],
           "ayarlar": {"konsinyeGun": st["konsinyeGun"], "yil": st["yil"]}, "crm": crm, **raw}
    S.meta_set(engine, tenant, meta_key(platform), out)
    return out


# ------------------------------------------------------------------ sınıflama


def _months(rows: Iterable[dict[str, Any]], ok: Callable[[dict[str, Any]], bool]) -> int:
    return len({(r.get("yil"), r.get("ay")) for r in rows if ok(r)})


def _n(v: float) -> str:
    return f"{int(round(v)):,}".replace(",", ".")


def _tl(v: float) -> str:
    return f"{v:,.0f}".replace(",", ".") + " ₺"


def classify(raw: dict[str, Any], st: dict[str, Any], panel: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Ham ölçümden sınıf, kanıt satırları, kesinti ve hakediş bulgusu. `panel`: Aşama 1 okumasının eşleşme özeti."""
    names = {c["kod"]: c.get("unvan") or c["kod"] for c in raw.get("cariler") or []}
    cards = [c for c in raw.get("cariler") or [] if not c.get("hesapDisi")]
    fat = raw.get("faturalar") or []

    def cnt(turs: set[int]) -> int:
        return sum(r["fatura"] for r in fat if r["tur"] in turs)

    def amt(turs: set[int]) -> float:
        return sum(r["tutar"] for r in fat if r["tur"] in turs)

    def who(turs: set[int]) -> str:
        cs = sorted({r["cari"] for r in fat if r["tur"] in turs and r["fatura"]})
        shown = ", ".join(names.get(c, c) for c in cs[:3])
        return shown + (f" ve {len(cs) - 3} cari daha" if len(cs) > 3 else "")

    t8, t7, t4 = cnt({8}), cnt({7}), cnt({4})
    kanit: list[dict[str, Any]] = []
    izler: dict[str, dict[str, Any]] = {k: {"var": False, "ay": 0, "kanit": []} for k in ("toptan", "konsinye", "kendi-magaza")}

    def add(model: str, kural: str, metin: str, sayi: float, ay: int) -> None:
        e = {"model": model, "kural": kural, "metin": metin, "sayi": sayi}
        kanit.append(e)
        iz = izler[model]
        iz["var"] = True
        iz["ay"] = max(iz["ay"], ay)
        iz["kanit"].append(e)

    donem = f"{raw.get('bas', '')[:4]}–{raw.get('bit', '')[:4]}" if raw.get("bas") else ""
    if t8:
        add("toptan", "toptan-fatura", f"{who({8})} carisine {donem} döneminde {_n(t8)} toptan satış faturası ({_tl(amt({8}))})",
            t8, _months(fat, lambda r: r["tur"] == 8 and r["fatura"] > 0))
    sevk = raw.get("sevk") or []
    eski = sum(r["eskiSatir"] for r in sevk if r["tur"] == 8)
    if eski:
        add("konsinye", "eski-acik-sevk",
            f"{raw.get('eskiSevkTarihi', '')} tarihinden eski, faturalanmamış {_n(eski)} satış irsaliyesi satırı "
            f"({_n(sum(r['eskiAdet'] for r in sevk if r['tur'] == 8))} adet)", eski,
            _months(sevk, lambda r: r["tur"] == 8 and r["eskiSatir"] > 0))
    gec = raw.get("gecikme") or []
    late = sum(r["gecSatir"] for r in gec)
    if late:
        gun = (raw.get("ayarlar") or {}).get("konsinyeGun", st["konsinyeGun"])
        add("konsinye", "gec-faturalanan-sevk",
            f"sevkten {gun} günden geç faturalanan {_n(late)} satış satırı ({_n(sum(r['gecAdet'] for r in gec))} adet; en uzun "
            f"{max(r['enUzunGun'] for r in gec)} gün)", late, max((r["gecAy"] for r in gec), default=0))
    if t7:
        add("kendi-magaza", "perakende-fatura", f"{who({7})} carisine {_n(t7)} perakende satış faturası ({_tl(amt({7}))})", t7,
            _months(fat, lambda r: r["tur"] == 7 and r["fatura"] > 0))
    bm = raw.get("belgeMetni") or []
    b7 = sum(r["fatura"] for r in bm if r["tur"] == 7)
    bcari = max((r["cari"] for r in bm if r["tur"] in (7, 8)), default=0)
    if b7 or bcari > max(1, len(cards)):
        add("kendi-magaza", "belge-metni",
            f"belge alanında platform adı geçen {_n(sum(r['fatura'] for r in bm if r['tur'] in (7, 8)))} satış faturası; bir ayda "
            f"en çok {_n(bcari)} farklı cariye", b7 or bcari, _months(bm, lambda r: r["tur"] in (7, 8) and r["fatura"] > 0))
    if panel and panel.get("eslesenFatura"):
        diff_cari = panel.get("farkliCari") or 0
        if panel.get("perakende") or diff_cari > max(1, len(cards)):
            add("kendi-magaza", "panel-siparis",
                f"panel siparişlerinden {_n(panel.get('eslesenSiparis') or 0)} tanesi Logo'da faturalı bulundu; faturalar "
                f"{_n(diff_cari)} farklı cariye, {_n(panel.get('perakende') or 0)} tanesi perakende", panel["eslesenFatura"],
                panel.get("ay") or 0)
        elif panel.get("toptan"):
            add("toptan", "panel-siparis",
                f"panel siparişlerinden {_n(panel.get('eslesenSiparis') or 0)} tanesi pazar yeri carisinin toptan faturasında bulundu",
                panel["eslesenFatura"], panel.get("ay") or 0)
    if t4 and not t8 and not t7:
        add("kendi-magaza", "hizmet-faturasi",
            f"satış faturası yokken {who({4})} carisinden {_n(t4)} alınan hizmet faturası (platform aracı: komisyon/hizmet)", t4,
            _months(fat, lambda r: r["tur"] == 4 and r["fatura"] > 0))

    # Baskınlık: kendi mağaza izi ile toptan/konsinye izi birlikteyse satış tutarları karşılaştırılır; biri toplamın
    # `PAZARYERI_BASKIN_PAY`ından (0,9) fazlasıysa öteki «yan iz» olur (ör. mağaza carisine düzeltme için kesilmiş birkaç
    # toptan fatura modeli karma yapmaz). Tutarı ölçülemeyen iz (panel, yalnız hizmet faturası) karşılaştırılmaz.
    w_kendi = max(amt({7}), sum(r["tutar"] for r in bm if r["tur"] == 7))
    w_toptan = amt({8})
    yan: list[str] = []
    if izler["kendi-magaza"]["var"] and (izler["toptan"]["var"] or izler["konsinye"]["var"]) and w_kendi > 0 and w_toptan > 0:
        share = w_kendi / (w_kendi + w_toptan)
        minor = (["toptan", "konsinye"] if share >= st["baskinPay"] else ["kendi-magaza"] if share <= 1 - st["baskinPay"] else [])
        for k in minor:
            if izler[k]["var"]:
                izler[k].update(var=False, yan=True, pay=round(share if k == "kendi-magaza" else 1 - share, 4))
                pct = f"{100 * izler[k]['pay']:.1f}".replace(".", ",")
                yan.append(f"{MODELS[k].split(' (')[0].lower()} (satış tutarının %{pct}'i)")
    on = [k for k, v in izler.items() if v["var"]]
    neden = None
    if on == ["toptan"] or on == ["konsinye"] or on == ["kendi-magaza"]:
        model = on[0]
    elif set(on) == {"toptan", "konsinye"}:
        model = "konsinye"
    elif not on:
        model = "belirsiz"
        if not cards and not (panel or {}).get("eslesenFatura"):
            neden = ("Logo'da bu platforma bağlanan cari bulunamadı (ad, eşleme ve kanal kuralı) ve panel siparişi Logo "
                     "faturasında bulunmadı. Cari farklı adla açılmışsa Cari eşleme ekranında platforma bağlayın.")
        else:
            neden = "Pazar yeri carisi var ama ölçülen dönemde satış, sevk ya da hizmet faturası yok."
    else:
        model = "belirsiz"
        neden = "Birden fazla modelin izi var (karma): " + ", ".join(MODELS[k].split(" (")[0].lower() for k in on) + "."
    guven = None
    if model != "belirsiz":
        guven = "guclu" if izler[model]["ay"] >= st["gucluAy"] else "zayif"
    main = izler[model]["kanit"] if model in izler else kanit
    if model == "konsinye" and izler["toptan"]["var"]:
        main = izler["konsinye"]["kanit"] + izler["toptan"]["kanit"]
    ad = MODELS[model].split(" (")[0]
    if model == "belirsiz":
        cumle = f"Bu kanalın satış modeli belirsiz: {neden}" + (
            " (kanıt: " + "; ".join(e["metin"] for e in kanit[:3]) + ")" if kanit else "")
    else:
        cumle = f"Bu kanalın satış modeli: {ad} (kanıt: " + "; ".join(e["metin"] for e in main[:3]) + ")"
        if yan:
            cumle += "; yan iz: " + ", ".join(yan)
        if guven == "zayif":
            cumle += f". Kanıt {st['gucluAy']} aydan az dönemde görüldü; zayıf."
    return {"model": model, "modelAd": MODELS[model], "guven": guven, "cumle": cumle, "neden": neden, "kanit": kanit, "yanIz": yan,
            "izler": izler, "kesinti": _kesinti(raw), "hakedis": _hakedis(raw), "cariler": _cari_rows(raw),
            "belgeMetni": _belge_rows(bm), "doluluk": _doluluk(raw), "crm": _crm(raw)}


def _kesinti(raw: dict[str, Any]) -> dict[str, Any]:
    cards = [c for c in raw.get("cariler") or [] if not c.get("hesapDisi")]
    rows = [r for r in raw.get("hizmetler") or [] if r["tur"] in (1, 4)]
    agg: dict[tuple[str, str, str], dict[str, Any]] = {}
    for r in rows:
        k = kesinti_kalem(r["hizmet"])
        a = agg.setdefault((k, r["hizmetKodu"], r["hizmet"]), {"kalem": k, "kalemAd": KALEM_AD[k], "hizmetKodu": r["hizmetKodu"],
                                                                "hizmet": r["hizmet"], "satir": 0, "tutar": 0.0})
        a["satir"] += r["satir"]
        a["tutar"] += r["tutar"]
    items = sorted(agg.values(), key=lambda x: (x["kalem"] == "diger", -x["tutar"]))
    known = [x for x in items if x["kalem"] != "diger"]
    other = sum(x["tutar"] for x in items if x["kalem"] == "diger")
    if not cards:
        cumle = "Kesinti Logo'da aranamadı: bu platforma bağlanan cari bulunamadı."
    elif not known:
        cumle = ("Kesinti Logo'da bulunamadı: pazar yeri carilerinden alınan faturalarda komisyon, kargo, hizmet bedeli, reklam "
                 "ya da stopaj hizmet satırı yok. Kesinti cari bağı olmayan muhasebe fişiyle giriyor ya da hiç girilmiyor "
                 "olabilir; uydurulmaz.")
    else:
        cumle = (f"Kesinti Logo'da platformdan alınan hizmet faturası olarak kayıtlı: {len(known)} hizmet kartı, toplam "
                 f"{_tl(sum(x['tutar'] for x in known))} (KDV hariç).")
        if other:
            cumle += f" Aynı carilerden kesinti olmayabilecek diğer alımlar: {_tl(other)}."
    return {"bulundu": bool(known), "cumle": cumle, "kalemler": items,
            "toplam": round(sum(x["tutar"] for x in known), 2), "diger": round(other, 2)}


def _hakedis(raw: dict[str, Any]) -> dict[str, Any]:
    agg: dict[tuple[int, int, int], dict[str, Any]] = {}
    for r in raw.get("hareketler") or []:
        if r["modul"] == 4:
            continue
        a = agg.setdefault((r["modul"], r["tur"], r["yon"]), {"modul": r["modul"], "modulAd": label(MODUL, r["modul"]), "tur": r["tur"],
                                                              "turAd": label(CARI_HAREKET, r["tur"]), "yon": "alacak" if r["yon"] == 1 else "borç",
                                                              "hareket": 0, "tutar": 0.0})
        a["hareket"] += r["hareket"]
        a["tutar"] += r["tutar"]
    items = sorted(agg.values(), key=lambda x: -x["tutar"])
    tahsil = [x for x in items if x["yon"] == "alacak"]
    if not [c for c in raw.get("cariler") or [] if not c.get("hesapDisi")]:
        cumle = "Tahsilat Logo'da aranamadı: bu platforma bağlanan cari bulunamadı."
    elif not tahsil:
        cumle = "Pazar yeri carilerinde fatura dışı alacak hareketi (havale, virman, dekont) bulunamadı."
    else:
        top = max(tahsil, key=lambda x: x["tutar"])
        cumle = (f"Para pazar yeri carilerine çoğunlukla «{top['turAd']}» ({top['modulAd']}) olarak geliyor: {_n(top['hareket'])} "
                 f"hareket, {_tl(top['tutar'])}.")
    return {"bulundu": bool(tahsil), "cumle": cumle, "hareketler": items}


def _cari_rows(raw: dict[str, Any]) -> list[dict[str, Any]]:
    by: dict[str, dict[str, Any]] = {}
    for c in raw.get("cariler") or []:
        by[c["kod"]] = {**c, "faturalar": {}, "acikSevk": 0, "gecFaturalanan": 0}
    for r in raw.get("faturalar") or []:
        c = by.get(r["cari"])
        if c is None:
            continue
        f = c["faturalar"].setdefault(str(r["tur"]), {"turAd": label(FATURA_TURU, r["tur"]), "fatura": 0, "tutar": 0.0})
        f["fatura"] += r["fatura"]
        f["tutar"] += r["tutar"]
    for r in raw.get("sevk") or []:
        if r["cari"] in by and r["tur"] == 8:
            by[r["cari"]]["acikSevk"] += r["satir"]
    for r in raw.get("gecikme") or []:
        if r["cari"] in by:
            by[r["cari"]]["gecFaturalanan"] += r["gecSatir"]
    return sorted(by.values(), key=lambda c: -sum(f["tutar"] for f in c["faturalar"].values()))


def _belge_rows(bm: list[dict[str, Any]]) -> list[dict[str, Any]]:
    agg: dict[tuple[int, Optional[str]], dict[str, Any]] = {}
    for r in bm:
        a = agg.setdefault((r["tur"], r["kanal"]), {"tur": r["tur"], "turAd": label(FATURA_TURU, r["tur"]), "kanal": r["kanal"],
                                                    "fatura": 0, "enCokCariAy": 0, "tutar": 0.0})
        a["fatura"] += r["fatura"]
        a["tutar"] += r["tutar"]
        a["enCokCariAy"] = max(a["enCokCariAy"], r["cari"])
    return sorted(agg.values(), key=lambda x: -x["fatura"])


def _doluluk(raw: dict[str, Any]) -> list[dict[str, Any]]:
    agg: dict[int, dict[str, Any]] = {}
    fields = [f.lower() for f in BELGE_ALANLARI + ("DOCTRACKINGNR",)]
    for r in raw.get("doluluk") or []:
        a = agg.setdefault(r["tur"], {"tur": r["tur"], "turAd": label(FATURA_TURU, r["tur"]), "fatura": 0, **{f: 0 for f in fields}})
        a["fatura"] += r["fatura"]
        for f in fields:
            a[f] += r.get(f, 0)
    return sorted(agg.values(), key=lambda x: x["tur"])


def _crm(raw: dict[str, Any]) -> dict[str, Any]:
    c = raw.get("crm") or {}
    tips = c.get("tipler") or {}
    firms = []
    for f in c.get("firmalar") or []:
        firms.append({**f, "siparis": [{"tip": k, "ad": tips.get(k) or f"Tip {k}", "sayi": v} for k, v in sorted(f["siparis"].items())]})
    return {"hata": c.get("hata"), "firmalar": firms}


def view(engine: sa.engine.Engine, tenant: str, platform: str, conf: Callable[[str], str],
         panel: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Ekran: ham ölçüm okunmadıysa `okundu: False` ve neden; okunduysa sınıf ve kanıtlar."""
    if platform not in PLATFORMS:
        raise ValueError("Bilinmeyen platform.")
    raw = S.meta_get(engine, tenant, meta_key(platform))
    st = settings(conf)
    base = {"platform": platform, "platformAd": M.PLATFORMS[platform], "modeller": MODELS,
            "ayarlar": {k: st[k] for k in ("yil", "konsinyeGun", "gucluAy")}, "desenler": name_rules(conf, platform)["desenler"]}
    if not raw:
        return {**base, "okundu": False, "model": "belirsiz", "modelAd": MODELS["belirsiz"], "guven": None,
                "cumle": "Bu kanalın satış modeli henüz ölçülmedi: «Logo'dan ölç» düğmesi Logo ve CRM'i salt okuma ile tarar.",
                "kanit": [], "cariler": []}
    out = classify(raw, st, panel)
    return {**base, "okundu": True, "okumaZamani": raw.get("_at"), "veriSonu": raw.get("veriSonu"), "donem": {"bas": raw.get("bas"),
            "bit": raw.get("bit"), "yillar": raw.get("yillar")}, "okunanDesenler": raw.get("desenler"), "panel": panel, **out}
