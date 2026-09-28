"""M16 D+7 / D+30 lansman değerlendirmesi: rakam tablosu (SQL; model yok), Zeki AI özeti ve en çok üç öneri (rakamı
aynen kullanır, yeni rakam yazamaz — `guard.check` tabloda olmayan sayıyı içeren cümleyi düşürür), PDF.

Karar (bütçeyi artır / aynı kalsın / kes / diğer) ve gerekçesi insanındır (`ozellik:pazarlama.plan-onay`); karar plan
geçmişine de yazılır. Ciro satırları yalnız `ozellik:pazarlama.butce-gor` olana gösterilir ve modele hiç verilmez.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any, Optional

from semantic_bridge.marketing import core as C
from semantic_bridge.marketing import guard as G
from semantic_bridge.marketing import launch as L

PRODUCT = "Zeki AI"
AY = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]


def tr_num(v: Any, digits: int = 0) -> str:
    if v is None:
        return "—"
    s = f"{float(v):,.{digits}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def tr_day(v: Optional[str]) -> str:
    if not v:
        return "—"
    d = date.fromisoformat(v[:10])
    return f"{d.day} {AY[d.month - 1]} {d.year}"


def _sum(rows: list[dict[str, Any]], f: str) -> Optional[float]:
    vals = [r[f] for r in rows if r.get(f) is not None]
    return round(sum(vals), 2) if vals else None


def _pct(a: Optional[float], b: Optional[float]) -> Optional[float]:
    return round(a / b * 100, 1) if a is not None and b else None


def numbers(full: dict[str, Any], days: list[dict[str, Any]], gun: int, events: dict[str, Any], media: dict[str, int],
            today: Optional[date] = None) -> dict[str, Any]:
    """D..D+gun−1 rakam tablosu. Her satır günlük tablodan (`semantic_mkt_launch_daily`) ya da kaynak okumasından; SQL
    metinleri `sql` altında."""
    pub = full["yayinGunu"]
    p = date.fromisoformat(pub)
    end = p + timedelta(days=gun - 1)
    e_iso = end.isoformat()
    win = [d for d in days if pub <= d["gun"] <= e_iso]
    pre = [d for d in days if d["gun"] < pub]
    logo_end = next((d.get("veri_sonu_logo") for d in reversed(days) if d.get("veri_sonu_logo")), None)
    cov = [d for d in win if logo_end and d["gun"] <= logo_end]
    oz = full.get("ozet") or {}
    em = oz.get("emsal") or {}
    dist = oz.get("dagilim") or {}
    sig = full.get("sinyal") or {}
    rows: list[dict[str, Any]] = []

    def add(key: str, ad: str, deger: Any, birim: str, kaynak: str, para: bool = False) -> None:
        rows.append({"anahtar": key, "ad": ad, "deger": deger, "birim": birim, "kaynak": kaynak, "para": para})

    siparis, fatura = _sum(win, "siparis_adet"), _sum(cov, "fatura_net_adet")
    hedef, hedef_cov = _sum(win, "hedef_payi_adet"), _sum(cov, "hedef_payi_adet")
    emsal = em.get("ort7") if gun == 7 else em.get("ort30")
    add("siparis", f"Sipariş, ilk {gun} gün", siparis, "adet", "CRM sipariş satırı (sipariş satış değildir)")
    add("onSiparis", "Yayından önceki sipariş", _sum(pre, "siparis_adet"), "adet", "CRM sipariş satırı")
    add("dagilim", "Dağılım siparişi", dist.get("adet"), "adet", "CRM sipariş tipi Dağılım")
    add("dagilimBayi", "Dağılım alan bayi", dist.get("bayi"), "bayi", "CRM sipariş tipi Dağılım")
    add("fatura", f"Faturalı net satış, ilk {gun} gün (Logo verisinin kapsadığı günler)", fatura, "adet", "Logo faturalı satış")
    add("ciro", f"Faturalı net ciro, ilk {gun} gün", _sum(cov, "fatura_net_ciro"), "TL", "Logo faturalı satış (LINENET)", para=True)
    add("kapsanan", "Logo verisinin kapsadığı gün", len(cov), "gün", f"Logo veri sonu {tr_day(logo_end)}")
    add("hedef", f"Hedef payı, ilk {gun} gün", hedef, "adet", "Bütçe ve hedefler (aylık hedef ÷ ayın gün sayısı)")
    add("oranFatura", "Faturalı satış / hedef payı (kapsanan günler)", _pct(fatura, hedef_cov), "%", "hesap")
    add("oranSiparis", f"Sipariş / hedef payı, ilk {gun} gün", _pct(siparis, hedef), "%", "hesap")
    add("emsal", f"Emsal kitapların ilk {gun} gün ortalaması", emsal, "adet", "Logo faturalı satış, emsalin ilk satış gününden")
    add("emsalSayisi", "Emsal kitap sayısı", len([x for x in em.get("items") or [] if x.get("ilk7" if gun == 7 else "ilk30") is not None]),
        "kitap", "M15 karnesi")
    add("oranEmsal", "Faturalı satış / emsal ortalaması", _pct(fatura, emsal) if len(cov) >= gun else None, "%", "hesap")
    add("bekleyen", "Açık sipariş (son okuma)", sig.get("bekleyen"), "adet", "CRM açık sipariş (Baskı Öneri tanımı)")
    dep = sig.get("depo") or {}
    add("depo", f"Depo stoku ({dep.get('kaynakAdi') or 'okunamadı'})", dep.get("deger"), "adet", dep.get("kaynakAdi") or "—")
    t = events.get("toplam") or {}
    add("etkinlik", "Tamamlanan etkinlik", t.get("tamamlanan"), "etkinlik", "CRM etkinlik + portal kaydı")
    add("katilimci", "Etkinlik katılımcısı", t.get("katilimci"), "kişi", "CRM etkinlik + portal kaydı")
    add("satilan", "Etkinlikte satılan kitap", t.get("satilan"), "adet", "CRM etkinlik + portal kaydı")
    for k, lab in L.TONES.items():
        add(f"medya-{k}", f"Medya yansıması ({lab.lower()})", media.get(k, 0), "kayıt", "Medya sekmesi")
    tasks = [x for x in full.get("tasks") or [] if x.get("tarih") and x["tarih"] <= e_iso]
    done = [x for x in tasks if x["durum"] == "yapildi"]
    add("madde", "Yapılan madde", len(done), "madde", "Kontrol listesi")
    add("maddeToplam", "Bu güne kadarki madde", len(tasks), "madde", "Kontrol listesi")
    # Kaynak sorguları (okuma anındaki çalışmış metinler); ekranda gösterilen sorgu bilgisi `kaynak_lansman.for_reviews`.
    sql = dict(oz.get("sql") or {})
    return {"gun": gun, "pencere": {"bas": pub, "bit": e_iso}, "satirlar": rows, "veriSonuLogo": logo_end,
            "eksikGun": max(0, (end - (today or C.today())).days) if (today or C.today()) < end else 0,
            "yapilmayan": [{"is": x["is"], "tarih": x["tarih"], "durum": x["durum"]} for x in tasks if x["durum"] != "yapildi"],
            "sql": sql, "hazirlanma": C.iso(C.now())}


def redact(rakam: dict[str, Any]) -> dict[str, Any]:
    return {**rakam, "satirlar": [{**r, "deger": None} if r.get("para") else r for r in rakam.get("satirlar") or []]}


def facts(full: dict[str, Any], rakam: dict[str, Any]) -> list[str]:
    """Modele verilen olgu listesi: ciro satırları hariç (bütçe görme yetkisi olmayana da gösterilecek metin)."""
    out = [f"Yayın günü: {tr_day(full['yayinGunu'])}", f"Değerlendirme: ilk {rakam['gun']} gün",
           f"Logo veri sonu: {tr_day(rakam.get('veriSonuLogo'))}"]
    for r in rakam["satirlar"]:
        if r.get("para") or r.get("deger") is None:
            continue
        v = r["deger"]
        out.append(f"{r['ad']}: {'%' + tr_num(v, 1) if r['birim'] == '%' else tr_num(v, 0 if float(v).is_integer() else 1) + ' ' + r['birim']}")
    return out


SYSTEM = ("Sen TİMAŞ Yayınları pazarlama ekibine lansman değerlendirmesi yazan Zeki AI'sın. Türkçe yaz. Yalnız verilen "
          "rakam tablosunu kullan; tabloda olmayan hiçbir sayı yazma, yeni hesap ya da yüzde üretme. Sipariş satış değildir: "
          "siparişi ve faturalı satışı ayrı söyle. Logo verisi yayın gününden önce bittiyse satış hakkında kesin yargı "
          "verme. Kanıtsız üstünlük iddiası ve teknoloji, model ya da yazılım adı yazma. Başlık ekleme.")


def draft_text(llm: Any, full: dict[str, Any], rakam: dict[str, Any], claims: list[str]) -> tuple[Optional[str], list[str], dict[str, Any]]:
    """İki paragraf özet + en çok üç öneri. Denetimden geçmeyen cümle düşer (sayısı kayıtta)."""
    fx = facts(full, rakam)
    undone = [x["is"] for x in rakam.get("yapilmayan") or []]
    prompt = (f"Kitap: {full['baslik']}\nRakam tablosu:\n" + "\n".join(f"- {f}" for f in fx)
              + ("\nYapılmayan kontrol listesi maddeleri:\n" + "\n".join(f"- {u}" for u in undone) if undone else "")
              + "\n\nÖnce lansmanın durumunu iki paragrafta özetle. Sonra «ÖNERİLER:» satırını yaz ve altına en fazla üç öneri "
                "yaz; her öneri «- » ile başlayan tek satır olsun. Bütçe kararı insanındır: öneride karar verme, seçeneği "
                "gerekçesiyle söyle.")
    raw = str(llm.chat([{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}], max_tokens=1200) or "").strip()
    parts = re.split(r"(?im)^\s*[*#]*\s*öneriler\s*[*:]*\s*:?\s*$|ÖNERİLER\s*:", raw, maxsplit=1)
    body = parts[0].strip()
    sug_raw = parts[1] if len(parts) > 1 else ""
    sources = [full["baslik"], *undone]
    res = G.check(body, sources, fx, claims)
    sugs: list[str] = []
    dropped = list(res["dusen"])
    for ln in sug_raw.splitlines():
        s = ln.strip().lstrip("-•*").strip()
        if not s:
            continue
        r = G.check(s, sources, fx, claims)
        dropped += r["dusen"]
        if r["metin"]:
            sugs.append(r["metin"])
        if len(sugs) == 3:
            break
    return (res["metin"] or None), sugs, {"dusen": dropped, "dusenSayisi": len(dropped)}


def report_pdf(full: dict[str, Any], reviews: list[dict[str, Any]], show_money: bool, user: str = "") -> bytes:
    try:
        from fpdf import FPDF
    except ImportError as e:  # pragma: no cover
        raise C.MarketingError("PDF üretici sunucuda kurulu değil.", 503) from e
    from semantic_bridge.editorial_export import _fold, _resolve_fonts

    regular, bold = _resolve_fonts()
    fam = "Body" if regular else "Helvetica"
    T = (lambda s: str(s or "")) if regular else (lambda s: _fold(str(s or "")))
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_title(T(f"Lansman raporu · {full['baslik']}"))
    pdf.set_author(PRODUCT)
    pdf.set_creator(PRODUCT)
    pdf.set_margins(14, 14, 14)
    pdf.set_auto_page_break(auto=True, margin=14)
    if regular:
        pdf.add_font(fam, "", str(regular))
        pdf.add_font(fam, "B", str(bold or regular))
    pdf.add_page()
    W = pdf.w - pdf.l_margin - pdf.r_margin

    def para(s: str, size: float = 9.5, style: str = "", gap: float = 1.5) -> None:
        pdf.set_font(fam, style, size)
        pdf.multi_cell(W, size * 0.5, T(s), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(gap)

    def row(cells: list[tuple[str, float]], style: str = "") -> None:
        pdf.set_font(fam, style, 8.5)
        for txt, w in cells:
            t = T(txt)
            while pdf.get_string_width(t) > w - 1.5 and len(t) > 1:
                t = t[:-2] + "…" if len(t) > 2 else t[:-1]
            pdf.cell(w, 5.5, t, border="B")
        pdf.ln(5.5)

    para("Timaş Yayınları · lansman değerlendirmesi", 8.5)
    para(full["baslik"], 15, "B", 1)
    para(f"{full['id']} · stok kodu {full['stokKodu']} · yayın günü {tr_day(full['yayinGunu'])} ({full.get('yayinGunuKaynakAdi') or '—'}) · "
         f"{full.get('durumAdi')}", 9)
    if not reviews:
        para("Henüz değerlendirme raporu yok (D+7 ve D+30 sabahı hazırlanır).")
    for rv in reviews:
        rk = rv["rakam"] if show_money else redact(rv["rakam"])
        pdf.ln(2)
        para(f"İlk {rv['gun']} gün ({tr_day(rk['pencere']['bas'])} – {tr_day(rk['pencere']['bit'])})", 12, "B", 1)
        row([("Ölçü", 104), ("Değer", 34), ("Kaynak", 44)], "B")
        for r in rk["satirlar"]:
            if r.get("para") and not show_money:
                continue
            v = r["deger"]
            val = "—" if v is None else ("%" + tr_num(v, 1) if r["birim"] == "%" else f"{tr_num(v, 0 if float(v).is_integer() else 1)} {r['birim']}")
            row([(r["ad"], 104), (val, 34), (r["kaynak"], 44)])
        if rv.get("ozet"):
            para("Zeki AI özeti", 10, "B", 0.5)
            para(rv["ozet"], 9)
        if rv.get("oneriler"):
            para("Öneriler", 10, "B", 0.5)
            for s in rv["oneriler"]:
                para(f"• {s}", 9, "", 0.5)
        if rv.get("karar"):
            para(f"Karar: {rv.get('kararAdi')} — {rv.get('gerekce') or ''} ({rv.get('kararVeren')}, {tr_day(rv.get('kararZamani'))})", 9.5, "B")
        else:
            para("Karar henüz kaydedilmedi.", 9)
        und = rk.get("yapilmayan") or []
        if und:
            para("Yapılmayan maddeler: " + "; ".join(u["is"] for u in und), 8.5)
    pdf.ln(3)
    para("Sipariş sinyali CRM'den (sipariş satış değildir); faturalı satış Logo'dan, veri sonuna kadar. Hedef payı: bütçe ve "
         "hedefler modülünün aylık hedefi ÷ ayın gün sayısı.", 8)
    para(f"Hazırlayan: {user or full.get('sahip') or '—'} · {PRODUCT}", 8)
    return bytes(pdf.output())


def digest_text(items: list[dict[str, Any]], link: str) -> Optional[str]:
    """Günlük tek özet: D−7 açık madde, bugün yayında olanlar, hedef payının altında kalanlar, stok uyarısı, hazır raporlar."""
    if not items:
        return None
    lines = ["ZEKİ pazarlama · lansman özeti", ""]
    for it in items:
        lines.append(f"• {it['baslik']} ({it['id']}, yayın {tr_day(it['yayinGunu'])}): " + " ".join(it["notlar"]))
    if link:
        lines += ["", f"Lansmanlar: {link}"]
    lines += ["", "Portal hiçbir dış kanala kendiliğinden gönderim yapmaz; yayın ve gönderim ekibindir."]
    return "\n".join(lines)
