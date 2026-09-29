"""M41 Amazon ve uluslararası platform yönetimi (ilk sürüm: Logo + CRM, yalnız okuma; Amazon hesabına bağlanılmaz).

**Ne okunur** (hepsi yalnız okuma; SQL `channels/sql/*.sql`)
- Amazon cari karnesi: M42 kanal karnesinin Amazon satırı (faturalı satır, onaylı cari eşlemesi) — yeniden hesaplanmaz.
- Konsinye kalan: onaylı Amazon carilerine faturalanmamış satış irsaliyesi (TRCODE 8) − faturalanmamış satış iade
  irsaliyesi (TRCODE 3), kitap bazında (`logo_konsinye_kalan.sql`). Kaç yılın açık irsaliyesi sayılacağı
  `AMAZON_KONSINYE_YIL` (varsayılan 1 = verinin son yılı; yıl devrinde açık irsaliyenin taşınıp taşınmadığı ölçülecek).
- Yurtdışı satış: yurtdışı kanal kodlu (`AMAZON_YURTDISI_KODLARI`) carilere faturalı satış, cari × ülke × döviz × ay;
  döviz tutarı fatura kuruyla (TRRATE); kitap × ülke; yıl başına döviz faturası sayısı.
- CRM: Amazon Konsinye sipariş sayısı (sipariş tipi 14) ve etkin Telif Satış sözleşmeleri (satılmış yabancı haklar).
- Amazon satıcı panelinden indirilen satış raporu M42'nin genel panel dosyası yüklemesiyle gelir (`platform=amazon`).

**Zeki AI** yalnız (a) tek kitap için hedef pazara listeleme / A+ / çeviri brief'i taslağı yazar (hesaba gönderilmez;
denetim `marketing.guard`), (b) pazar değerlendirme kartına rakamsız gerekçe yazar. Rakamlar SQL'den, parametreler
finanstan (`semantic_intl_params`). Karar insanda (`ozellik:amazon.pazar-karar`).
"""
from __future__ import annotations

import json
import logging
import re
import threading
from collections import defaultdict
from datetime import date
from typing import Any, Callable, Optional

import sqlalchemy as sa

from semantic_bridge.channels import mapping as M
from semantic_bridge.channels import platform_common as PC
from semantic_bridge.channels import sources as src
from semantic_bridge.channels import store as S

log = logging.getLogger("semantic.channels.amazon")

PLATFORM = "amazon"
_md = sa.MetaData()

#: Konsinye önbelleği: yıl × cari × kitap (faturalanmamış sevk ve iade irsaliyesi). Her okumada bütünüyle değişir.
CONSIGN = sa.Table(
    "semantic_intl_consignment", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("yil", sa.Integer, primary_key=True),
    sa.Column("cari", sa.String(80), primary_key=True),
    sa.Column("stok_kodu", sa.String(60), primary_key=True),
    sa.Column("sevk", sa.Float, nullable=False),
    sa.Column("iade", sa.Float, nullable=False),
    sa.Column("sevk_tutar", sa.Float, nullable=False),
    sa.Column("ilk", sa.String(10)),
    sa.Column("son", sa.String(10)),
)

#: Yurtdışı satış önbelleği: yıl × ay × cari × ülke × döviz.
INTL = sa.Table(
    "semantic_intl_sales", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("yil", sa.Integer, primary_key=True),
    sa.Column("ay", sa.Integer, primary_key=True),
    sa.Column("cari", sa.String(80), primary_key=True),
    sa.Column("ulke", sa.String(60), primary_key=True),
    sa.Column("doviz", sa.Integer, primary_key=True),
    sa.Column("unvan", sa.String(300)),
    sa.Column("satis_ciro", sa.Float, nullable=False),
    sa.Column("iade_ciro", sa.Float, nullable=False),
    sa.Column("satis_adet", sa.Float, nullable=False),
    sa.Column("iade_adet", sa.Float, nullable=False),
    sa.Column("doviz_net", sa.Float, nullable=False),
    sa.Column("fatura", sa.Integer, nullable=False),
)

INTL_BOOKS = sa.Table(
    "semantic_intl_books", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("yil", sa.Integer, primary_key=True),
    sa.Column("ulke", sa.String(60), primary_key=True),
    sa.Column("stok_kodu", sa.String(60), primary_key=True),
    sa.Column("satis_adet", sa.Float, nullable=False),
    sa.Column("iade_adet", sa.Float, nullable=False),
    sa.Column("satis_ciro", sa.Float, nullable=False),
    sa.Column("iade_ciro", sa.Float, nullable=False),
)

#: Satılmış yabancı haklar (CRM Telif Satış; sözleşme × kitap). Her okumada bütünüyle değişir.
RIGHTS = sa.Table(
    "semantic_intl_rights", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("sozlesme_id", sa.String(60), primary_key=True),
    sa.Column("stok_kodu", sa.String(60), primary_key=True),
    sa.Column("sozlesme_no", sa.String(120)),
    sa.Column("kitap", sa.String(400)),
    sa.Column("ulke", sa.String(200)),
    sa.Column("firmalar", sa.Text),
    sa.Column("yurtdisi_taraf", sa.Boolean),
    sa.Column("bas", sa.String(10)),
    sa.Column("bit", sa.String(10)),
    sa.Column("durum", sa.Integer),
)

#: Uluslararası fiyat ve pazar parametreleri — finans girer (`ozellik:amazon.parametre`).
PARAMS = sa.Table(
    "semantic_intl_params", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("pazar", sa.String(12), primary_key=True),
    sa.Column("ad", sa.String(120), nullable=False),
    sa.Column("ulkeler", sa.Text),                               # Logo cari kartındaki ülke yazımları (virgülle)
    sa.Column("doviz", sa.String(8)),
    sa.Column("kur_kaynagi", sa.String(200)),
    sa.Column("kdv_orani", sa.Float),
    sa.Column("kargo_birim", sa.Float),
    sa.Column("komisyon_orani", sa.Float),
    sa.Column("notu", sa.String(1000)),
    sa.Column("giren", sa.String(120), nullable=False),
    sa.Column("tarih", sa.DateTime(timezone=True), nullable=False),
)

DRAFTS = sa.Table(
    "semantic_intl_drafts", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("stok_kodu", sa.String(60), nullable=False),
    sa.Column("kitap", sa.String(400)),
    sa.Column("pazar", sa.String(12), nullable=False),
    sa.Column("dil", sa.String(40), nullable=False),
    sa.Column("tur", sa.String(12), nullable=False),              # listeleme | aplus | brief
    sa.Column("metin_json", sa.Text, nullable=False),
    sa.Column("dusen_json", sa.Text),                             # denetimde düşen cümleler ve nedeni
    sa.Column("durum", sa.String(12), nullable=False),            # taslak | kullanildi
    sa.Column("yazan", sa.String(120), nullable=False),
    sa.Column("tarih", sa.DateTime(timezone=True), nullable=False),
    sa.Column("guncelleyen", sa.String(120)),
    sa.Column("guncellendi", sa.DateTime(timezone=True)),
)

CARDS = sa.Table(
    "semantic_intl_market_cards", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("pazar", sa.String(12), nullable=False),
    sa.Column("gostergeler_json", sa.Text, nullable=False),
    sa.Column("model_gerekce", sa.Text),
    sa.Column("notu", sa.String(1000)),
    sa.Column("hazirlayan", sa.String(120), nullable=False),
    sa.Column("tarih", sa.DateTime(timezone=True), nullable=False),
    sa.Column("karar", sa.String(12)),                            # None | girilsin | bekle | girilmesin
    sa.Column("karar_notu", sa.String(1000)),
    sa.Column("karar_veren", sa.String(120)),
    sa.Column("karar_tarihi", sa.DateTime(timezone=True)),
)

#: Logo döviz kodları (genel bilgi; bilinmeyen kod «Döviz kodu N» yazar — L_CURRENCYLIST ile ölçülecek).
CURRENCIES = {0: "TL", 160: "TL", 1: "USD", 20: "EUR", 17: "GBP", 11: "CHF", 12: "JPY", 13: "SAR"}
DRAFT_TYPES = {"listeleme": "Listeleme (başlık, açıklama, anahtar kelime)", "aplus": "A+ içerik metni", "brief": "Çeviri / yerelleştirme brief'i"}
DECISIONS = {"girilsin": "Pazara girilsin", "bekle": "Bekle / yeniden değerlendir", "girilmesin": "Girilmesin"}

DRAFT_PROMPT = (
    "Bir Türk yayınevinin kitabı için {pazar} pazarı ({dil} dilinde) {tur_ad} taslağı hazırla.\n"
    "Kurallar: yalnız aşağıdaki kitap bilgisini kullan, bilgi uydurma; «en çok satan» gibi kanıtsız üstünlük iddiası yazma; "
    "fiyat, stok ya da teslim sözü verme; kaynakta olmayan rakam yazma.\n"
    "Cevabı yalnız JSON olarak ver. {sema}\n\nKitap bilgisi:\n{kart}"
)
SCHEMAS = {
    "listeleme": 'Alanlar: {"baslik": "...", "aciklama": "...", "anahtar_kelimeler": ["...", "..."]}',
    "aplus": 'Alanlar: {"moduller": [{"baslik": "...", "metin": "..."}]} — 3 ile 5 kısa bölüm',
    "brief": 'Alanlar: {"hedef_okur": "...", "ton": "...", "dikkat": "...", "ozet": "..."} — çevirmen ve yerelleştirme ekibi için',
}
CARD_PROMPT = ("Bir yayınevinin yeni yurtdışı pazar değerlendirmesi aşağıda (rakamlar tabloda). Genel müdür için 3–5 "
               "cümlelik gerekçe yaz: pazara girmenin lehine ve aleyhine olan noktalar, eksik bilgi. Rakam, yüzde ya da "
               "tutar yazma.\n\n{olgular}")

_ready: set[int] = set()
_lock = threading.Lock()


class AmazonError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def ensure(engine: sa.engine.Engine) -> None:
    with _lock:
        if id(engine) in _ready:
            return
        S.ensure(engine)
        _md.create_all(engine, checkfirst=True)
        _ready.add(id(engine))


def settings(conf: Callable[[str], str]) -> dict[str, Any]:
    """Yönetim → Platform ve kanallar (`AMAZON_*`). Varsayılanlar ölçülmemiş başlangıç değerleridir."""
    ent = (conf("AMAZON_ULKE_TABLOSU") or "new_ulke").strip()
    return {
        "cariAdlari": PC.name_patterns(conf("AMAZON_CARI_ADLARI") or "AMAZON"),
        "yurtdisiKodlari": PC.name_patterns(conf("AMAZON_YURTDISI_KODLARI") or "YURTDIŞI,YURTDISI"),
        "yil": max(1, int(PC.conf_float(conf, "AMAZON_YIL_SAYISI", 2))),
        "konsinyeYil": max(1, int(PC.conf_float(conf, "AMAZON_KONSINYE_YIL", 1))),
        "konsinyeTipi": int(PC.conf_float(conf, "AMAZON_CRM_KONSINYE_TIPI", 14)),
        "ulkeTablosu": ent if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,60}", ent) else "new_ulke",
    }


def currency(code: Any) -> str:
    try:
        c = int(code or 0)
    except (TypeError, ValueError):
        return str(code)
    return CURRENCIES.get(c, f"Döviz kodu {c}")


# ------------------------------------------------------------------ SQL


def konsinye_sql(firm: str, year: int, codes: list[str]) -> str:
    return src._fill("logo_konsinye_kalan", firm=firm, year=year, next=year + 1, codes=src._in(codes))


def yurtdisi_sql(firm: str, year: int, specodes: list[str]) -> str:
    return src._fill("logo_yurtdisi", firm=firm, year=year, next=year + 1, specodes=src._in(specodes))


def yurtdisi_kitap_sql(firm: str, year: int, specodes: list[str]) -> str:
    return src._fill("logo_yurtdisi_kitap", firm=firm, year=year, next=year + 1, specodes=src._in(specodes))


def doviz_sql(firm: str, year: int) -> str:
    return src._fill("logo_doviz", firm=firm, year=year, next=year + 1)


def crm_orders_sql(prefix: str, tip: int, bas: str) -> str:
    return src._fill("crm_amazon_siparis", schema=prefix, tip=int(tip), bas=bas)


def crm_rights_sql(prefix: str) -> str:
    return src._fill("crm_telif_satis", schema=prefix)


def crm_country_sql(prefix: str, entity: str) -> str:
    return src._fill("crm_ulke", schema=prefix, entity=entity)


def crm_book_sql(prefix: str, code: str) -> str:
    return src._fill("crm_kitap_kart", schema=prefix, kod=src.q(code))


def _f(v: Any) -> float:
    return src._f(v)


def _d(v: Any) -> Optional[str]:
    w = PC.when(v)
    return w.date().isoformat() if w else None


def _country(v: Any) -> str:
    return PC.cell(v, 60) or ""


# ------------------------------------------------------------------ okuma


#: Sorgu bilgisi: konsinye, yurtdışı ve hak tablolarını dolduran Logo/CRM sorguları (`semantic_query_origin`).
KOKEN_OKUMA = "amazon.okuma"


def refresh(engine: sa.engine.Engine, tenant: str, logo_file: str, crm_file: str, crm_schema: str, conf: Callable[[str], str],
            step: Callable[[str], None] = lambda s: None) -> dict[str, Any]:
    """Okuma (aşağıda) + sorgu bilgisi: okumada koşan Logo/CRM sorguları «asıl sorgu» olarak saklanır."""
    from semantic_bridge import sorgu_yakala as Y

    ensure(engine)
    q, token = Y.baslat(engine)
    try:
        out = _refresh(engine, tenant, logo_file, crm_file, crm_schema, conf, step)
    finally:
        Y.bitir(token)
    Y.koken_yaz(engine, tenant, KOKEN_OKUMA, q)
    return out


def _refresh(engine: sa.engine.Engine, tenant: str, logo_file: str, crm_file: str, crm_schema: str, conf: Callable[[str], str],
             step: Callable[[str], None] = lambda s: None) -> dict[str, Any]:
    """Logo: adla Amazon carileri, konsinye, yurtdışı satış ve kitaplar, döviz faturası sayısı. CRM: Amazon Konsinye
    siparişleri ve Telif Satış sözleşmeleri. Logo hatası okumayı durdurur (eski önbellek kalır); CRM hatası kayda düşer."""
    from semantic_bridge import eticaret_sources as E

    ensure(engine)
    st = settings(conf)
    step("Logo dönemleri")
    from semantic_bridge import sorgu_yakala as Y

    run = Y.izle(src.runner(logo_file), "logo", Y.db_of(logo_file))
    firms = src.firms_by_year(run)
    latest = firms[max(firms)]
    end = E.read_data_end(run, firms)
    top = end.year if end else max(firms)
    years = [y for y in range(top - st["yil"] + 1, top + 1) if y in firms]
    kyears = [y for y in range(top - st["konsinyeYil"] + 1, top + 1) if y in firms]

    step("Amazon adlı cariler")
    S.meta_set(engine, tenant, "amazon:cariler", {"items": PC.read_name_cariler(run, latest, st["cariAdlari"]),
                                                  "desenler": st["cariAdlari"], "firma": latest})
    codes = PC.approved_codes(engine, tenant, PLATFORM)
    step("Konsinye")
    crows: list[dict[str, Any]] = []
    for y in kyears:
        for i in range(0, len(codes), src.IN_CHUNK):
            for r in run(konsinye_sql(src.bsrc._firm(firms, y), y, codes[i:i + src.IN_CHUNK])):
                sk = PC.cell(r.get("stok_kodu"), 60)
                if sk:
                    crows.append({"yil": y, "cari": PC.cell(r.get("cari"), 80), "stok_kodu": sk, "sevk": _f(r.get("sevk")),
                                  "iade": _f(r.get("iade")), "sevk_tutar": _f(r.get("sevk_tutar")), "ilk": _d(r.get("ilk")),
                                  "son": _d(r.get("son"))})
    S.replace_all(engine, tenant, CONSIGN, crows)

    doviz: dict[str, Any] = {}
    seen_codes = {r["stok_kodu"] for r in crows}
    for y in years:
        firm = src.bsrc._firm(firms, y)
        step(f"{y} yurtdışı satış")
        rows = [{"yil": y, "ay": int(r["ay"]), "cari": PC.cell(r.get("cari"), 80), "ulke": _country(r.get("ulke")),
                 "doviz": int(r.get("doviz") or 0), "unvan": PC.cell(r.get("unvan"), 300) or None,
                 "satis_ciro": _f(r.get("satis_ciro")), "iade_ciro": _f(r.get("iade_ciro")), "satis_adet": _f(r.get("satis_adet")),
                 "iade_adet": _f(r.get("iade_adet")), "doviz_net": _f(r.get("doviz_net")), "fatura": int(r.get("fatura") or 0)}
                for r in run(yurtdisi_sql(firm, y, st["yurtdisiKodlari"]))]
        S.replace_year(engine, tenant, INTL, y, [r for r in rows if r["cari"]])
        step(f"{y} yurtdışı kitaplar")
        books = [{"yil": y, "ulke": _country(r.get("ulke")), "stok_kodu": PC.cell(r.get("stok_kodu"), 60),
                  "satis_adet": _f(r.get("satis_adet")), "iade_adet": _f(r.get("iade_adet")),
                  "satis_ciro": _f(r.get("satis_ciro")), "iade_ciro": _f(r.get("iade_ciro"))}
                 for r in run(yurtdisi_kitap_sql(firm, y, st["yurtdisiKodlari"]))]
        books = [b for b in books if b["stok_kodu"]]
        S.replace_year(engine, tenant, INTL_BOOKS, y, books)
        seen_codes |= {b["stok_kodu"] for b in books}
        step(f"{y} döviz faturaları")
        dv = (run(doviz_sql(firm, y)) or [{}])[0]
        doviz[str(y)] = {"toplam": int(dv.get("toplam") or 0), "satis": int(dv.get("satis") or 0), "satisTl": _f(dv.get("satis_tl"))}
    if seen_codes:
        step("Kitap adları")
        S.upsert_books(engine, tenant, src.read_item_names(run, latest, seen_codes))

    crm_meta: dict[str, Any] = {"error": None}
    try:
        crm = Y.izle(src.runner(crm_file), "crm", Y.db_of(crm_file))
        p = E.prefix(crm_schema)
        step("CRM Amazon siparişleri")
        crm_meta["siparis"] = {str(int(r["yil"])): int(r.get("sayi") or 0)
                               for r in crm(crm_orders_sql(p, st["konsinyeTipi"], f"{min(years or [top])}-01-01")) if r.get("yil")}
        crm_meta["tip"] = st["konsinyeTipi"]
        step("CRM Telif Satış sözleşmeleri")
        names: dict[str, str] = {}
        try:
            names = {PC.cell(r.get("id"), 200).lower(): PC.cell(r.get("ad"), 200) for r in crm(crm_country_sql(p, st["ulkeTablosu"]))}
        except src.SourceError as e:
            crm_meta["ulkeHatasi"] = f"Ülke adları okunamadı ({st['ulkeTablosu']}Base): {str(e)[:160]}"
        rights = _rights_rows(crm(crm_rights_sql(p)), names)
        S.replace_all(engine, tenant, RIGHTS, rights)
        crm_meta["haklar"] = len(rights)
    except src.SourceError as e:
        crm_meta["error"] = str(e)
    S.meta_set(engine, tenant, "amazon:crm", crm_meta)
    out = {"ok": True, "years": years, "konsinyeYillari": kyears, "cariler": codes, "veriSonu": end.isoformat() if end else None,
           "doviz": doviz, "konsinyeSatir": len(crows), "yurtdisiKodlari": st["yurtdisiKodlari"], "crmError": crm_meta["error"]}
    S.meta_set(engine, tenant, "amazon:read", out)
    return out


def _rights_rows(rows: list[dict[str, Any]], names: dict[str, str]) -> list[dict[str, Any]]:
    agg: dict[tuple[str, str], dict[str, Any]] = {}
    for r in rows:
        sid, sk = PC.cell(r.get("id"), 60), PC.cell(r.get("stok_kodu"), 60)
        if not sid:
            continue
        sk = sk or f"#{PC.key_hash(sid, r.get('kitap'))[:12]}"
        a = agg.setdefault((sid, sk), {"sozlesme_id": sid, "stok_kodu": sk, "sozlesme_no": PC.cell(r.get("no"), 120) or None,
                                       "kitap": PC.cell(r.get("kitap")) or None, "firmalar": set(), "yurtdisi_taraf": False,
                                       "bas": _d(r.get("bas")), "bit": _d(r.get("bit")),
                                       "durum": int(r["durum"]) if r.get("durum") is not None else None,
                                       "ulke": None})
        raw = PC.cell(r.get("ulke"), 200)
        if raw:
            a["ulke"] = names.get(raw.lower()) or ("?" if names else raw)
        if r.get("firma"):
            a["firmalar"].add(PC.cell(r.get("firma"), 200))
        if r.get("yon") is not None and int(r["yon"]) == 2:
            a["yurtdisi_taraf"] = True
    out = []
    for a in agg.values():
        a["firmalar"] = ", ".join(sorted(a["firmalar"])) or None
        out.append(a)
    return out


# ------------------------------------------------------------------ görünümler


def _read_meta(engine: sa.engine.Engine, tenant: str) -> dict[str, Any]:
    return S.meta_get(engine, tenant, "amazon:read")


def _need_read(engine: sa.engine.Engine, tenant: str) -> dict[str, Any]:
    m = _read_meta(engine, tenant)
    if not m:
        raise AmazonError("Amazon ve yurtdışı verisi henüz Logo'dan okunmadı; «Veriyi yenile» ile okunur.", 409)
    return m


def consignment(engine: sa.engine.Engine, tenant: str, q: str = "", p: int = 0,
                billed: Optional[dict[str, float]] = None) -> dict[str, Any]:
    m = _need_read(engine, tenant)
    with engine.connect() as c:
        rows = c.execute(sa.select(CONSIGN).where(CONSIGN.c.tenant_id == tenant)).all()
    names = S.book_names(engine, tenant)
    books: dict[str, dict[str, Any]] = {}
    cariler: dict[str, dict[str, float]] = defaultdict(lambda: {"sevk": 0.0, "iade": 0.0, "kalan": 0.0, "kitap": 0})
    for r in rows:
        b = books.setdefault(r.stok_kodu, {"stokKodu": r.stok_kodu, "ad": names.get(r.stok_kodu, ""), "sevk": 0.0, "iade": 0.0,
                                           "sevkTutar": 0.0, "ilk": r.ilk, "son": r.son, "cariler": set()})
        b["sevk"] += r.sevk
        b["iade"] += r.iade
        b["sevkTutar"] += r.sevk_tutar
        b["ilk"] = min(x for x in (b["ilk"], r.ilk) if x) if (b["ilk"] or r.ilk) else None
        b["son"] = max(x for x in (b["son"], r.son) if x) if (b["son"] or r.son) else None
        b["cariler"].add(r.cari)
        cr = cariler[r.cari]
        cr["sevk"] += r.sevk
        cr["iade"] += r.iade
        cr["kalan"] += r.sevk - r.iade
        cr["kitap"] += 1
    items = []
    for b in books.values():
        b["kalan"] = b["sevk"] - b["iade"]
        b["cariler"] = sorted(b["cariler"])
        b["faturalanan"] = (billed or {}).get(b["stokKodu"]) if billed is not None else None
        items.append(b)
    items.sort(key=lambda x: -x["kalan"])
    tot = {"sevk": sum(x["sevk"] for x in items), "iade": sum(x["iade"] for x in items), "kalan": sum(x["kalan"] for x in items),
           "sevkTutar": round(sum(x["sevkTutar"] for x in items), 2), "kitap": len(items)}
    items = PC.search(items, q, ("ad", "stokKodu"))
    return PC.page(items, p, toplam=tot, cariler=[{"cari": k, **v} for k, v in sorted(cariler.items())],
                   yillar=m.get("konsinyeYillari"), eslenenCariler=m.get("cariler") or [], veriSonu=m.get("veriSonu"),
                   faturalananBagli=billed is not None)


def _intl_rows(engine: sa.engine.Engine, tenant: str, years: list[int]) -> list[Any]:
    with engine.connect() as c:
        return c.execute(sa.select(INTL).where(INTL.c.tenant_id == tenant, INTL.c.yil.in_(years))).all()


def _net(r: Any) -> tuple[float, float]:
    return r.satis_ciro - r.iade_ciro, r.satis_adet - r.iade_adet


def international(engine: sa.engine.Engine, tenant: str, yil: Optional[int] = None, ulke: str = "") -> dict[str, Any]:
    """Yurtdışı karne: cari × ülke × döviz (seçilen yıl, geçen yıl kıyaslı), ülke özeti, aylık seyir. TL tutar LINENET;
    döviz tutarı fatura kuruyla. Geçen yıl tam yıl; yıl kısmi ise geçen yılın aynı ayına kadar olan toplam da verilir
    (toplamda, ülkede ve cari satırında `gecenYilAyniDonem`; bu yılla kıyas bununla yapılır)."""
    m = _need_read(engine, tenant)
    years = sorted(int(y) for y in m.get("years") or [])
    if not years:
        raise AmazonError("Okunan yıl yok.", 409)
    y = int(yil or years[-1])
    if y not in years:
        raise AmazonError(f"{y} okunmadı (okunan: {', '.join(map(str, years))}).", 409)
    rows = _intl_rows(engine, tenant, [y, y - 1])
    last_month = max((r.ay for r in rows if r.yil == y), default=12)
    by_key: dict[tuple, dict[str, Any]] = {}
    by_country: dict[str, dict[str, float]] = defaultdict(lambda: {"netCiro": 0.0, "netAdet": 0.0, "gecenYil": 0.0,
                                                                     "gecenYilAyniDonem": 0.0, "cari": 0})
    cur_by_cur: dict[str, float] = defaultdict(float)
    monthly: dict[int, dict[str, float]] = defaultdict(lambda: {"buYil": 0.0, "gecenYil": 0.0})
    cari_countries: dict[str, set[str]] = defaultdict(set)
    for r in rows:
        country = r.ulke or "Ülke yazılmamış"
        if ulke and country != ulke:
            continue
        nc, na = _net(r)
        a = by_key.setdefault((r.cari, country, r.doviz), {"cari": r.cari, "unvan": r.unvan, "ulke": country, "doviz": currency(r.doviz),
                                                           "netCiro": 0.0, "netAdet": 0.0, "dovizNet": 0.0, "fatura": 0, "gecenYil": 0.0,
                                                           "gecenYilAyniDonem": 0.0})
        a["unvan"] = a["unvan"] or r.unvan
        if r.yil == y:
            a["netCiro"] += nc
            a["netAdet"] += na
            a["dovizNet"] += r.doviz_net
            a["fatura"] += r.fatura
            by_country[country]["netCiro"] += nc
            by_country[country]["netAdet"] += na
            cari_countries[country].add(r.cari)
            if r.doviz not in (0, 160):
                cur_by_cur[currency(r.doviz)] += r.doviz_net
            monthly[r.ay]["buYil"] += nc
        else:
            a["gecenYil"] += nc
            by_country[country]["gecenYil"] += nc
            if r.ay <= last_month:
                a["gecenYilAyniDonem"] += nc
                by_country[country]["gecenYilAyniDonem"] += nc
            monthly[r.ay]["gecenYil"] += nc
    items = sorted(by_key.values(), key=lambda x: (-x["netCiro"], -x["gecenYil"]))
    countries = []
    for k, v in by_country.items():
        v["cari"] = len(cari_countries.get(k, ()))
        countries.append({"ulke": k, **{kk: round(vv, 2) if isinstance(vv, float) else vv for kk, vv in v.items()}})
    countries.sort(key=lambda x: -x["netCiro"])
    doviz = (m.get("doviz") or {}).get(str(y), {})
    return {"yil": y, "sonAy": last_month, "yillar": years, "ulke": ulke or None, "items": items, "ulkeler": countries,
            "dovizToplam": {k: round(v, 2) for k, v in cur_by_cur.items()},
            "aylik": [{"ay": mm, **monthly[mm]} for mm in range(1, 13)], "dovizFatura": doviz,
            "toplam": {"netCiro": round(sum(x["netCiro"] for x in countries), 2), "netAdet": sum(x["netAdet"] for x in countries),
                       "gecenYil": round(sum(x["gecenYil"] for x in countries), 2),
                       "gecenYilAyniDonem": round(sum(x["gecenYilAyniDonem"] for x in countries), 2)},
            "kodlar": m.get("yurtdisiKodlari"), "veriSonu": m.get("veriSonu")}


def intl_books(engine: sa.engine.Engine, tenant: str, yil: Optional[int] = None, ulke: str = "", q: str = "", p: int = 0) -> dict[str, Any]:
    m = _need_read(engine, tenant)
    years = sorted(int(x) for x in m.get("years") or [])
    y = int(yil or (years[-1] if years else date.today().year))
    with engine.connect() as c:
        rows = c.execute(sa.select(INTL_BOOKS).where(INTL_BOOKS.c.tenant_id == tenant, INTL_BOOKS.c.yil == y)).all()
    names = S.book_names(engine, tenant)
    agg: dict[str, dict[str, Any]] = {}
    for r in rows:
        country = r.ulke or "Ülke yazılmamış"
        if ulke and country != ulke:
            continue
        a = agg.setdefault(r.stok_kodu, {"stokKodu": r.stok_kodu, "ad": names.get(r.stok_kodu, ""), "netAdet": 0.0, "netCiro": 0.0,
                                         "iadeAdet": 0.0, "ulkeler": defaultdict(float)})
        a["netAdet"] += r.satis_adet - r.iade_adet
        a["netCiro"] += r.satis_ciro - r.iade_ciro
        a["iadeAdet"] += r.iade_adet
        a["ulkeler"][country] += r.satis_adet - r.iade_adet
    items = []
    for a in agg.values():
        a["ulkeler"] = [{"ulke": k, "netAdet": v} for k, v in sorted(a["ulkeler"].items(), key=lambda kv: -kv[1])]
        a["netCiro"] = round(a["netCiro"], 2)
        items.append(a)
    items.sort(key=lambda x: -x["netAdet"])
    return PC.page(PC.search(items, q, ("ad", "stokKodu")), p, yil=y, ulke=ulke or None)


def rights(engine: sa.engine.Engine, tenant: str, q: str = "", ulke: str = "", p: int = 0) -> dict[str, Any]:
    """Satılmış yabancı haklar kitap bazında + o kitabın yurtdışı faturalı net adedi (okunan yıllar). Hak bilgisi olmayan
    kitap için «yurtdışında satılabilir» denmez (analiz §8)."""
    crm = S.meta_get(engine, tenant, "amazon:crm")
    with engine.connect() as c:
        rows = c.execute(sa.select(RIGHTS).where(RIGHTS.c.tenant_id == tenant)).all()
        intl = c.execute(sa.select(INTL_BOOKS.c.stok_kodu, sa.func.sum(INTL_BOOKS.c.satis_adet - INTL_BOOKS.c.iade_adet))
                         .where(INTL_BOOKS.c.tenant_id == tenant).group_by(INTL_BOOKS.c.stok_kodu)).all()
    sold = {k: float(v or 0) for k, v in intl}
    books: dict[str, dict[str, Any]] = {}
    countries: dict[str, int] = defaultdict(int)
    for r in rows:
        b = books.setdefault(r.stok_kodu, {"stokKodu": None if r.stok_kodu.startswith("#") else r.stok_kodu, "kitap": r.kitap,
                                           "sozlesmeler": [], "ulkeler": set(), "firmalar": set()})
        b["sozlesmeler"].append({"id": r.sozlesme_id, "no": r.sozlesme_no, "ulke": r.ulke, "firmalar": r.firmalar, "bas": r.bas,
                                 "bit": r.bit, "yurtdisiTaraf": r.yurtdisi_taraf})
        if r.ulke:
            b["ulkeler"].add(r.ulke)
        for f in (r.firmalar or "").split(", "):
            if f:
                b["firmalar"].add(f)
    items = []
    for b in books.values():
        for u in b["ulkeler"]:
            countries[u] += 1
        b["ulkeler"] = sorted(b["ulkeler"])
        b["firmalar"] = sorted(b["firmalar"])
        b["yurtdisiNetAdet"] = sold.get(b["stokKodu"] or "", 0.0)
        items.append(b)
    if ulke:
        items = [b for b in items if ulke in b["ulkeler"]]
    items.sort(key=lambda x: (-len(x["sozlesmeler"]), M.fold(x["kitap"])))
    items = PC.search(items, q, ("kitap", "stokKodu"))
    return PC.page(items, p, ulkeler=dict(sorted(countries.items(), key=lambda kv: -kv[1])), sozlesme=len({r.sozlesme_id for r in rows}),
                   crmHata=crm.get("error"), ulkeHatasi=crm.get("ulkeHatasi"), okundu=crm.get("_at"))


# ------------------------------------------------------------------ parametreler


def _param_view(r: Any) -> dict[str, Any]:
    return {"pazar": r.pazar, "ad": r.ad, "ulkeler": [x.strip() for x in (r.ulkeler or "").split(",") if x.strip()],
            "doviz": r.doviz, "kurKaynagi": r.kur_kaynagi, "kdvOrani": r.kdv_orani, "kargoBirim": r.kargo_birim,
            "komisyonOrani": r.komisyon_orani, "not": r.notu, "giren": r.giren, "tarih": S.iso(r.tarih)}


def params(engine: sa.engine.Engine, tenant: str) -> list[dict[str, Any]]:
    with engine.connect() as c:
        return [_param_view(r) for r in c.execute(sa.select(PARAMS).where(PARAMS.c.tenant_id == tenant).order_by(PARAMS.c.pazar)).all()]


def _ratio(v: Any, what: str) -> Optional[float]:
    if v is None or v == "":
        return None
    x = PC.num(v)
    if x is None or not 0 <= x < 1:
        raise AmazonError(f"{what} 0 ile 1 arasında oran olmalı (ör. 0,07).")
    return x


def set_params(engine: sa.engine.Engine, tenant: str, user: str, pazar: str, body: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    code = re.sub(r"[^A-Za-z0-9-]", "", pazar or "").upper()[:12]
    if not code:
        raise AmazonError("Pazar kodu gerekli (ör. DE, US, NL).")
    ad = PC.cell(body.get("ad"), 120)
    if not ad:
        raise AmazonError("Pazar adı gerekli.")
    kargo = PC.num(body.get("kargoBirim")) if body.get("kargoBirim") not in (None, "") else None
    if kargo is not None and kargo < 0:
        raise AmazonError("Kargo birim maliyeti eksi olamaz.")
    vals = {"ad": ad, "ulkeler": ", ".join(PC.cell(x, 60) for x in (body.get("ulkeler") or []) if PC.cell(x, 60)) or None,
            "doviz": PC.cell(body.get("doviz"), 8).upper() or None, "kur_kaynagi": PC.cell(body.get("kurKaynagi"), 200) or None,
            "kdv_orani": _ratio(body.get("kdvOrani"), "KDV"), "kargo_birim": kargo,
            "komisyon_orani": _ratio(body.get("komisyonOrani"), "Komisyon"), "notu": PC.cell(body.get("not"), 1000) or None}
    with engine.begin() as c:
        before = c.execute(sa.select(PARAMS).where(PARAMS.c.tenant_id == tenant, PARAMS.c.pazar == code)).first()
        c.execute(PARAMS.delete().where(PARAMS.c.tenant_id == tenant, PARAMS.c.pazar == code))
        c.execute(PARAMS.insert().values(tenant_id=tenant, pazar=code, giren=user, tarih=S.now(), **vals))
        after = c.execute(sa.select(PARAMS).where(PARAMS.c.tenant_id == tenant, PARAMS.c.pazar == code)).first()
    return _param_view(after), {"once": _param_view(before) if before else None, "sonra": _param_view(after)}


def delete_params(engine: sa.engine.Engine, tenant: str, pazar: str) -> None:
    with engine.begin() as c:
        c.execute(PARAMS.delete().where(PARAMS.c.tenant_id == tenant, PARAMS.c.pazar == pazar.upper()))


# ------------------------------------------------------------------ taslaklar


def _draft_view(r: Any) -> dict[str, Any]:
    return {"id": r.id, "stokKodu": r.stok_kodu, "kitap": r.kitap, "pazar": r.pazar, "dil": r.dil, "tur": r.tur,
            "turAd": DRAFT_TYPES.get(r.tur, r.tur), "metin": S.jload(r.metin_json, {}), "dusen": S.jload(r.dusen_json, []),
            "durum": r.durum, "yazan": r.yazan, "tarih": S.iso(r.tarih), "guncelleyen": r.guncelleyen, "guncellendi": S.iso(r.guncellendi)}


def read_book_card(crm_run: src.Runner, crm_schema: str, code: str) -> dict[str, Any]:
    from semantic_bridge import eticaret_sources as E
    from semantic_bridge import sets_sources as ssrc

    rows = crm_run(crm_book_sql(E.prefix(crm_schema), code))
    if not rows:
        raise AmazonError("Bu stok kodunun CRM'de etkin kitap kartı yok.", 404)
    r = rows[0]
    return {k: (ssrc.strip_html(v, 6000) if k in ("spot", "arka_kapak") else PC.cell(v, 1000)) for k, v in r.items()}


def _parse_json(text: str) -> dict[str, Any]:
    t = (text or "").strip()
    a, b = t.find("{"), t.rfind("}")
    if a >= 0 and b > a:
        try:
            v = json.loads(t[a:b + 1])
            if isinstance(v, dict):
                return v
        except ValueError:
            pass
    return {"metin": t}


def _guard_tree(v: Any, sources: list[str], dropped: list[dict[str, str]]) -> Any:
    from semantic_bridge.marketing import guard

    if isinstance(v, str):
        c = guard.check(v, sources)
        dropped.extend(c["dusen"])
        return c["metin"]
    if isinstance(v, list):
        return [x for x in (_guard_tree(i, sources, dropped) for i in v) if x not in ("", None, {}, [])]
    if isinstance(v, dict):
        return {k: _guard_tree(i, sources, dropped) for k, i in v.items()}
    return v


def create_draft(engine: sa.engine.Engine, tenant: str, user: str, llm: Any, card: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    code = PC.cell(body.get("stokKodu"), 60)
    pazar = re.sub(r"[^A-Za-z0-9-]", "", str(body.get("pazar") or "")).upper()[:12]
    dil = PC.cell(body.get("dil"), 40)
    tur = str(body.get("tur") or "listeleme")
    if not code or not pazar or not dil:
        raise AmazonError("Stok kodu, pazar ve dil gerekli.")
    if tur not in DRAFT_TYPES:
        raise AmazonError("Taslak türü listeleme, aplus ya da brief olmalı.")
    if llm is None:
        raise AmazonError("Zeki AI şu an kullanılamıyor.", 503)
    fields = [("Ad", card.get("ad")), ("Ürün adı", card.get("urun_adi")), ("Yazar", card.get("yazar")), ("Çevirmen", card.get("cevirmen")),
              ("Sayfa", card.get("sayfa")), ("Kategori", card.get("kategori")), ("Anahtar kelimeler", card.get("anahtar_kelime")),
              ("Spot", card.get("spot")), ("Arka kapak", card.get("arka_kapak"))]
    kart = "\n".join(f"{k}: {v}" for k, v in fields if v)
    prompt = DRAFT_PROMPT.format(pazar=pazar, dil=dil, tur_ad=DRAFT_TYPES[tur].lower(), sema=SCHEMAS[tur], kart=kart)
    text = llm.chat([{"role": "user", "content": prompt}], max_tokens=1400, temperature=0.3) or ""
    dropped: list[dict[str, str]] = []
    content = _guard_tree(_parse_json(text), [str(v) for _, v in fields if v], dropped)
    if not any(v for v in content.values()):
        raise AmazonError("Zeki AI'ın taslağı denetimden geçmedi; yeniden deneyin.")
    did = S.new_id()
    with engine.begin() as c:
        c.execute(DRAFTS.insert().values(id=did, tenant_id=tenant, stok_kodu=code, kitap=card.get("ad"), pazar=pazar, dil=dil, tur=tur,
                                         metin_json=json.dumps(content, ensure_ascii=False), dusen_json=json.dumps(dropped, ensure_ascii=False),
                                         durum="taslak", yazan=user, tarih=S.now()))
        r = c.execute(sa.select(DRAFTS).where(DRAFTS.c.id == did)).first()
    return _draft_view(r)


def drafts(engine: sa.engine.Engine, tenant: str, stok: str = "", pazar: str = "", p: int = 0) -> dict[str, Any]:
    stmt = sa.select(DRAFTS).where(DRAFTS.c.tenant_id == tenant)
    if stok:
        stmt = stmt.where(DRAFTS.c.stok_kodu == stok)
    if pazar:
        stmt = stmt.where(DRAFTS.c.pazar == pazar.upper())
    with engine.connect() as c:
        rows = [_draft_view(r) for r in c.execute(stmt.order_by(DRAFTS.c.tarih.desc())).all()]
    return PC.page(rows, p, turler=DRAFT_TYPES)


def set_draft_state(engine: sa.engine.Engine, tenant: str, user: str, did: str, durum: str) -> dict[str, Any]:
    if durum not in ("taslak", "kullanildi"):
        raise AmazonError("Durum «taslak» ya da «kullanildi» olmalı.")
    with engine.begin() as c:
        n = c.execute(DRAFTS.update().where(DRAFTS.c.tenant_id == tenant, DRAFTS.c.id == did)
                      .values(durum=durum, guncelleyen=user, guncellendi=S.now())).rowcount
        if not n:
            raise AmazonError("Taslak bulunamadı.", 404)
        return _draft_view(c.execute(sa.select(DRAFTS).where(DRAFTS.c.id == did)).first())


# ------------------------------------------------------------------ pazar değerlendirme kartı


def _card_view(r: Any) -> dict[str, Any]:
    return {"id": r.id, "pazar": r.pazar, "gostergeler": S.jload(r.gostergeler_json, {}), "gerekce": r.model_gerekce, "not": r.notu,
            "hazirlayan": r.hazirlayan, "tarih": S.iso(r.tarih), "karar": r.karar, "kararAd": DECISIONS.get(r.karar or ""),
            "kararNotu": r.karar_notu, "kararVeren": r.karar_veren, "kararTarihi": S.iso(r.karar_tarihi)}


def indicators(engine: sa.engine.Engine, tenant: str, pazar: str, countries: list[str]) -> dict[str, Any]:
    """Pazar göstergeleri: seçilen ülkelerdeki yurtdışı faturalı satış (okunan yıllar), cari sayısı, en çok satan kitaplar,
    bu ülkelere satılmış hak sayısı (ülke adı eşleşmesiyle), finansın parametreleri."""
    m = _need_read(engine, tenant)
    years = sorted(int(x) for x in m.get("years") or [])
    want = {c for c in countries if c}
    if not want:
        raise AmazonError("En az bir ülke seçilmeli (Logo cari kartındaki ülke yazımı).")
    per_year: dict[int, dict[str, float]] = {}
    caris: set[str] = set()
    for r in _intl_rows(engine, tenant, years):
        if (r.ulke or "Ülke yazılmamış") not in want:
            continue
        nc, na = _net(r)
        a = per_year.setdefault(r.yil, {"netCiro": 0.0, "netAdet": 0.0})
        a["netCiro"] += nc
        a["netAdet"] += na
        caris.add(r.cari)
    with engine.connect() as c:
        brows = c.execute(sa.select(INTL_BOOKS).where(INTL_BOOKS.c.tenant_id == tenant, INTL_BOOKS.c.ulke.in_(list(want)))).all()
        rrows = c.execute(sa.select(RIGHTS.c.stok_kodu, RIGHTS.c.ulke).where(RIGHTS.c.tenant_id == tenant)).all()
        prm = c.execute(sa.select(PARAMS).where(PARAMS.c.tenant_id == tenant, PARAMS.c.pazar == pazar)).first()
    names = S.book_names(engine, tenant)
    top: dict[str, float] = defaultdict(float)
    for b in brows:
        top[b.stok_kodu] += b.satis_adet - b.iade_adet
    fw = {M.fold(x) for x in want}
    hak = sorted({r.stok_kodu for r in rrows if r.ulke and any(w and (w in M.fold(r.ulke) or M.fold(r.ulke) in w) for w in fw)})
    return {"pazar": pazar, "ulkeler": sorted(want), "yillar": {str(k): {kk: round(vv, 2) for kk, vv in v.items()} for k, v in sorted(per_year.items())},
            "cariSayisi": len(caris),
            "kitaplar": [{"stokKodu": k, "ad": names.get(k, ""), "netAdet": v} for k, v in sorted(top.items(), key=lambda kv: -kv[1])],
            "hakSatilanKitap": len(hak), "parametre": _param_view(prm) if prm else None, "veriSonu": m.get("veriSonu"),
            "not": "Hak eşleşmesi ülke adının yazımına bağlıdır; ülke adı okunamadıysa sıfır çıkabilir."}


def create_card(engine: sa.engine.Engine, tenant: str, user: str, llm: Any, body: dict[str, Any]) -> dict[str, Any]:
    from semantic_bridge.marketing import guard

    pazar = re.sub(r"[^A-Za-z0-9-]", "", str(body.get("pazar") or "")).upper()[:12]
    if not pazar:
        raise AmazonError("Pazar kodu gerekli.")
    ind = indicators(engine, tenant, pazar, [PC.cell(x, 60) for x in (body.get("ulkeler") or [])])
    gerekce = None
    if llm is not None:
        facts = (f"Pazar: {pazar}. Ülkeler: {', '.join(ind['ulkeler'])}. Yıllara göre yurtdışı faturalı satış var: "
                 f"{'evet' if ind['yillar'] else 'hayır'}. Hak satılmış kitap var: {'evet' if ind['hakSatilanKitap'] else 'hayır'}. "
                 f"Finans parametresi girildi: {'evet' if ind['parametre'] else 'hayır'}.")
        try:
            text = llm.chat([{"role": "user", "content": CARD_PROMPT.format(olgular=facts)}], max_tokens=260, temperature=0.2) or ""
            gerekce = guard.check(re.sub(r"[^\n]*\d[^\n]*\n?", "", text), sources=[facts])["metin"] or None
        except Exception as e:  # noqa: BLE001
            log.warning("amazon: pazar gerekçesi yazılamadı: %s", e)
    cid = S.new_id()
    with engine.begin() as c:
        c.execute(CARDS.insert().values(id=cid, tenant_id=tenant, pazar=pazar, gostergeler_json=json.dumps(ind, ensure_ascii=False, default=str),
                                        model_gerekce=gerekce, notu=PC.cell(body.get("not"), 1000) or None, hazirlayan=user, tarih=S.now()))
        r = c.execute(sa.select(CARDS).where(CARDS.c.id == cid)).first()
    return _card_view(r)


def cards(engine: sa.engine.Engine, tenant: str) -> list[dict[str, Any]]:
    with engine.connect() as c:
        return [_card_view(r) for r in c.execute(sa.select(CARDS).where(CARDS.c.tenant_id == tenant).order_by(CARDS.c.tarih.desc())).all()]


def decide_card(engine: sa.engine.Engine, tenant: str, user: str, cid: str, karar: str, note: Optional[str]) -> dict[str, Any]:
    if karar not in DECISIONS:
        raise AmazonError("Karar girilsin, bekle ya da girilmesin olmalı.")
    with engine.connect() as c:
        r = c.execute(sa.select(CARDS).where(CARDS.c.tenant_id == tenant, CARDS.c.id == cid)).first()
    if r is None:
        raise AmazonError("Kart bulunamadı.", 404)
    if r.karar:
        raise AmazonError("Kart zaten karara bağlandı.", 409)
    if r.hazirlayan.lower() == user.lower():
        raise AmazonError("Kartı hazırlayan kişi karar veremez.", 403)
    if karar != "girilsin" and not note:
        raise AmazonError("Bu karar için gerekçe yazılmalı.")
    with engine.begin() as c:
        c.execute(CARDS.update().where(CARDS.c.tenant_id == tenant, CARDS.c.id == cid)
                  .values(karar=karar, karar_notu=note, karar_veren=user, karar_tarihi=S.now()))
        return _card_view(c.execute(sa.select(CARDS).where(CARDS.c.id == cid)).first())


# ------------------------------------------------------------------ açılış


def overview(engine: sa.engine.Engine, tenant: str, wholesale: dict[str, Any]) -> dict[str, Any]:
    m = _read_meta(engine, tenant)
    crm = S.meta_get(engine, tenant, "amazon:crm")
    out: dict[str, Any] = {"okundu": bool(m), "read": m, "toptan": wholesale, "crm": {k: crm.get(k) for k in ("siparis", "tip", "haklar", "error", "ulkeHatasi")}}
    cands = S.meta_get(engine, tenant, "amazon:cariler")
    view = PC.candidates_view(engine, tenant, PLATFORM, cands.get("items") or [])
    out["adayCariler"] = {"toplam": len(view), "onayli": sum(1 for x in view if x["durum"] == "onayli"),
                          "bekleyen": sum(1 for x in view if x["durum"] in ("listede-yok", "bekliyor", "aday"))}
    if not m:
        return out
    k = consignment(engine, tenant)
    out["konsinye"] = k["toplam"]
    try:
        i = international(engine, tenant)
        out["yurtdisi"] = {"yil": i["yil"], "sonAy": i["sonAy"], **i["toplam"], "ulkeSayisi": len(i["ulkeler"]),
                           "ilkUlkeler": i["ulkeler"][:5], "dovizToplam": i["dovizToplam"], "dovizFatura": i["dovizFatura"]}
    except AmazonError as e:
        out["yurtdisi"] = {"hata": str(e)}
    with engine.connect() as c:
        out["haklar"] = {"kitap": c.execute(sa.select(sa.func.count(sa.distinct(RIGHTS.c.stok_kodu))).where(RIGHTS.c.tenant_id == tenant)).scalar() or 0,
                         "sozlesme": c.execute(sa.select(sa.func.count(sa.distinct(RIGHTS.c.sozlesme_id))).where(RIGHTS.c.tenant_id == tenant)).scalar() or 0}
        out["taslak"] = c.execute(sa.select(sa.func.count()).select_from(DRAFTS).where(DRAFTS.c.tenant_id == tenant)).scalar() or 0
        out["bekleyenKart"] = c.execute(sa.select(sa.func.count()).select_from(CARDS).where(CARDS.c.tenant_id == tenant, CARDS.c.karar.is_(None))).scalar() or 0
    return out
