"""M6 Sözleşmeler: şablon alanları, metin doldurma ve Word (.docx) belgesi.

Şablon iki biçimde durabilir:
- **Metin şablonu** (portalda yazılır): `# ` ile başlayan satır başlık, boş satırla ayrılan bloklar paragraf.
- **Word şablonu** (hukuk biriminin kendi .docx dosyası yüklenir): biçim olduğu gibi kalır, yalnız `{{alan}}`
  yer tutucuları doldurulur. Word bir yer tutucuyu birkaç parçaya (run) bölebildiği için yer tutucu taşıyan
  paragrafın metni ilk parçaya toplanır; o paragrafın içindeki karışık biçim (ör. yarısı kalın) bu yüzden tek
  biçime iner. Yer tutucusuz paragraflara dokunulmaz.

Word dosyası dış kütüphane olmadan (zip + WordprocessingML) yazılır ve okunur.
"""
from __future__ import annotations

import io
import re
import zipfile
from datetime import date
from typing import Any, Optional
from xml.sax.saxutils import escape

from semantic_bridge import contracts_terms as T

PLACEHOLDER = re.compile(r"\{\{\s*([a-z0-9_.]+)\s*\}\}")

#: Şablonda kullanılabilen alanlar: anahtar → açıklama. Ekrandaki «Alanlar» listesi buradan gelir.
FIELDS: dict[str, str] = {
    "sozlesme_no": "Sözleşme numarası",
    "sozlesme_adi": "Sözleşme adı",
    "sozlesme_turu": "Sözleşme türü (Telif alış …)",
    "yayinevi": "Yayınevi tarafı (imzalayan şirketimiz)",
    "hak_sahibi": "İlk tarafın adı",
    "taraflar": "Bütün taraflar ve payları",
    "kitap": "İlk kitabın adı",
    "kitaplar": "Bütün kitaplar",
    "isbn": "İlk kitabın ISBN'i",
    "odeme_sekli": "Ödeme şekli",
    "telif_esasi": "Telif esası (net/brüt)",
    "telif_karton": "Karton kapak telif oranı",
    "telif_sert": "Sert kapak telif oranı",
    "telif_ekitap": "E-kitap telif oranı",
    "telif_sesli": "Sesli kitap telif oranı",
    "telif_yurtdisi": "Yurtdışı satış telif oranı",
    "telif_oranlari": "Bütün telif oranları (liste)",
    "kademeler": "Kademeli oranlar",
    "iskonto": "Telif hesaplama iskontosu",
    "para_birimi": "Para birimi",
    "avans": "Avans tutarı",
    "avans_yazi": "Avans tutarının yazıyla yazılışı",
    "tek_odeme": "Tek ödeme tutarı",
    "tek_odeme_yazi": "Tek ödeme tutarının yazıyla yazılışı",
    "stopaj": "Stopaj oranı",
    "baslangic": "Başlangıç tarihi",
    "bitis": "Bitiş tarihi (süresizse «süresiz»)",
    "sure_yil": "Süre (yıl)",
    "hakedis_donemi": "Hakediş dönemi (ay)",
    "odeme_vadesi": "Ödeme vadesi (gün)",
    "ilk_baski": "İlk baskı adedi",
    "bolge": "Bölge",
    "dil": "Dil",
    "haklar": "Devredilen haklar (liste)",
    "notlar": "Notlar",
    "bugun": "Belgenin üretildiği gün",
    "zeyilname_no": "Zeyilname numarası (yalnız zeyilnamede)",
    "zeyilname_tarihi": "Zeyilnamenin yürürlük tarihi",
    "zeyilname_konusu": "Zeyilnamenin konusu",
    "zeyilname_gerekcesi": "Zeyilnamenin gerekçesi",
    "zeyilname_degisiklikler": "Değişen maddeler: eski → yeni (liste)",
    "hakedis_donem": "Hakediş dönemi (başlangıç – bitiş)",
    "hakedis_adet": "Dönemdeki satış/baskı adedi",
    "hakedis_matrah": "Telif matrahı",
    "hakedis_brut": "Brüt telif",
    "hakedis_avans_mahsup": "Avanstan düşülen",
    "hakedis_stopaj": "Stopaj tutarı",
    "hakedis_net": "Ödenecek net tutar",
    "hakedis_net_yazi": "Ödenecek net tutarın yazıyla yazılışı",
    "hakedis_satirlar": "Kitap/taraf satırları (liste)",
}

TARGETS = {"sozlesme": "Sözleşme", "zeyilname": "Zeyilname", "hakedis": "Hakediş bildirimi"}


def values(no: Optional[str], t: dict[str, Any], *, addendum: Optional[dict[str, Any]] = None,
           statement: Optional[dict[str, Any]] = None, today: Optional[date] = None) -> dict[str, str]:
    """Şablon alanlarının bu sözleşmedeki değerleri (metin olarak)."""
    cur = t.get("currency") or "TRY"
    rates = t.get("rates") or {}
    parties = t.get("parties") or []
    books = t.get("books") or []
    rights = [T.RIGHT_KEYS[k] for k, v in (t.get("rights") or {}).items() if v and k in T.RIGHT_KEYS]
    v = {
        "sozlesme_no": no or "—",
        "sozlesme_adi": t.get("title") or "—",
        "sozlesme_turu": T.KINDS.get(t.get("kind"), "—"),
        "yayinevi": t.get("company") or "—",
        "hak_sahibi": parties[0]["name"] if parties else "—",
        "taraflar": T.show("parties", parties),
        "kitap": books[0]["title"] if books else "—",
        "kitaplar": T.show("books", books),
        "isbn": (books[0].get("isbn") if books else None) or "—",
        "odeme_sekli": T.PAYMENT_TYPES.get(t.get("paymentType"), "—"),
        "telif_esasi": T.BASES.get(t.get("basis"), "—"),
        **{f"telif_{k}": T.show(f"rates.{k}", rates.get(k)) for k in T.RATE_KEYS},
        "telif_oranlari": "\n".join(f"{T.RATE_KEYS[k]}: %{T.fmt_num(r)}" for k, r in rates.items() if k in T.RATE_KEYS) or "—",
        "kademeler": T.show("tiers", t.get("tiers") or []),
        "iskonto": T.show("discountPct", t.get("discountPct")),
        "para_birimi": T.CURRENCIES.get(cur, cur),
        "avans": T.money(t.get("advance"), cur),
        "avans_yazi": T.money_words(t.get("advance"), cur),
        "tek_odeme": T.money(t.get("flatFee"), cur),
        "tek_odeme_yazi": T.money_words(t.get("flatFee"), cur),
        "stopaj": T.show("withholdingPct", t.get("withholdingPct")),
        "baslangic": T.day_tr(t.get("start")),
        "bitis": "süresiz" if t.get("openEnded") else T.day_tr(t.get("end")),
        "sure_yil": T.fmt_num(t["years"]) if t.get("years") else "—",
        "hakedis_donemi": str(t.get("periodMonths") or "—"),
        "odeme_vadesi": str(t.get("paymentDays") if t.get("paymentDays") is not None else "—"),
        "ilk_baski": T.fmt_num(t["printRun"], 0) if t.get("printRun") else "—",
        "bolge": t.get("territory") or "—",
        "dil": t.get("language") or "—",
        "haklar": "\n".join(rights) or "—",
        "notlar": t.get("notes") or "—",
        "bugun": T.day_tr((today or date.today()).isoformat()),
    }
    if addendum:
        v.update({
            "zeyilname_no": addendum.get("no") or "—",
            "zeyilname_tarihi": T.day_tr(addendum.get("effectiveOn")),
            "zeyilname_konusu": addendum.get("title") or "—",
            "zeyilname_gerekcesi": addendum.get("reason") or "—",
            "zeyilname_degisiklikler": "\n".join(
                f"{c['label']}: {T.show(c['field'], c.get('old'), cur)} → {T.show(c['field'], c.get('new'), cur)}"
                for c in addendum.get("changes") or []) or "—",
        })
    if statement:
        scur = statement.get("currency") or cur
        v.update({
            "hakedis_donem": f"{T.day_tr(statement.get('periodStart'))} – {T.day_tr(statement.get('periodEnd'))}",
            "hakedis_adet": T.fmt_num(statement.get("quantity") or 0, 0),
            "hakedis_matrah": T.money(statement.get("base"), scur),
            "hakedis_brut": T.money(statement.get("gross"), scur),
            "hakedis_avans_mahsup": T.money(statement.get("advanceOffset"), scur),
            "hakedis_stopaj": T.money(statement.get("withholding"), scur),
            "hakedis_net": T.money(statement.get("net"), scur),
            "hakedis_net_yazi": T.money_words(statement.get("net"), scur),
            "hakedis_satirlar": "\n".join(
                f"{ln.get('book')} · {ln.get('party')}: {T.fmt_num(ln.get('quantity') or 0, 0)} adet, "
                f"%{T.fmt_num(ln.get('rate') or 0)} → {T.money(ln.get('royalty'), scur)}"
                for ln in statement.get("lines") or []) or "—",
        })
    return v


def fill(text: str, vals: dict[str, str]) -> tuple[str, list[str]]:
    """Yer tutucuları doldurur; tanınmayan ya da bu belgede değeri olmayan alanlar yerinde kalır ve döner."""
    missing: list[str] = []

    def sub(m: re.Match) -> str:
        key = m.group(1)
        if key in vals:
            return vals[key]
        missing.append(key)
        return m.group(0)

    return PLACEHOLDER.sub(sub, text or ""), sorted(set(missing))


def placeholders(text: str) -> list[str]:
    return sorted(set(PLACEHOLDER.findall(text or "")))


# ------------------------------------------------------------------------------------------ Word yazımı

_CT = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
</Types>"""
_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
</Relationships>"""
_DOC_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""
_STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:cs="Calibri"/><w:sz w:val="22"/><w:lang w:val="tr-TR"/></w:rPr></w:rPrDefault>
<w:pPrDefault><w:pPr><w:spacing w:after="120" w:line="276" w:lineRule="auto"/><w:jc w:val="both"/></w:pPr></w:pPrDefault></w:docDefaults>
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>
<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:pPr><w:jc w:val="center"/><w:spacing w:after="240"/></w:pPr><w:rPr><w:b/><w:sz w:val="30"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:pPr><w:keepNext/><w:spacing w:before="240" w:after="120"/><w:jc w:val="left"/></w:pPr><w:rPr><w:b/><w:sz w:val="24"/></w:rPr></w:style>
</w:styles>"""


def _core(title: str) -> str:
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>' + escape(title) + '</dc:title>'
            '<dc:creator>Zeki AI</dc:creator></cp:coreProperties>')


def _para(text: str, style: Optional[str] = None) -> str:
    ppr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    runs = []
    for i, line in enumerate(text.split("\n")):
        if i:
            runs.append("<w:r><w:br/></w:r>")
        runs.append(f'<w:r><w:t xml:space="preserve">{escape(line)}</w:t></w:r>')
    return f"<w:p>{ppr}{''.join(runs)}</w:p>"


def blocks(text: str) -> list[tuple[str, str]]:
    """Metin şablonu → [(tür, metin)]: 'title' ilk `# ` başlığı, 'h' diğer başlıklar, 'p' paragraf."""
    out: list[tuple[str, str]] = []
    buf: list[str] = []

    def flush():
        if buf:
            out.append(("p", "\n".join(buf).strip()))
            buf.clear()

    for line in (text or "").replace("\r\n", "\n").split("\n"):
        if line.startswith("# "):
            flush()
            out.append(("title" if not any(k == "title" for k, _ in out) else "h", line[2:].strip()))
        elif line.startswith("## "):
            flush()
            out.append(("h", line[3:].strip()))
        elif not line.strip():
            flush()
        else:
            buf.append(line.rstrip())
    flush()
    return [b for b in out if b[1]]


def docx_from_text(text: str, title: str) -> bytes:
    style = {"title": "Title", "h": "Heading1", "p": None}
    body = "".join(_para(t, style[k]) for k, t in blocks(text))
    doc = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
           + body +
           '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
           '<w:pgMar w:top="1418" w:right="1418" w:bottom="1418" w:left="1418" w:header="709" w:footer="709" w:gutter="0"/>'
           '</w:sectPr></w:body></w:document>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _CT)
        z.writestr("_rels/.rels", _RELS)
        z.writestr("word/_rels/document.xml.rels", _DOC_RELS)
        z.writestr("word/styles.xml", _STYLES)
        z.writestr("word/document.xml", doc)
        z.writestr("docProps/core.xml", _core(title))
    return buf.getvalue()


# ------------------------------------------------------------------------------------------ Word şablonu

_P = re.compile(r"<w:p[ >].*?</w:p>|<w:p/>", re.S)
_T = re.compile(r"(<w:t(?: [^>]*)?>)(.*?)(</w:t>)", re.S)
_PARTS = re.compile(r"^word/(document|header\d*|footer\d*)\.xml$")
MAX_DOCX = 15 * 1024 * 1024


def _unxml(s: str) -> str:
    return s.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&apos;", "'").replace("&amp;", "&")


def check_docx(data: bytes) -> list[str]:
    """Yüklenen dosya gerçekten Word belgesi mi; içindeki yer tutucular."""
    if len(data) > MAX_DOCX:
        raise T.ContractError("Word dosyası 15 MB sınırını aşıyor.", 413)
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names = z.namelist()
            if "word/document.xml" not in names:
                raise T.ContractError("Dosya bir Word (.docx) belgesi değil.")
            if any(n.lower().endswith("vbadata.xml") or n.lower().endswith(".bin") for n in names):
                raise T.ContractError("Makro içeren Word dosyası kabul edilmez; .docx olarak kaydedip yükleyin.")
            text = "".join(_plain_xml(z.read(n).decode("utf-8", "replace")) for n in names if _PARTS.match(n))
    except zipfile.BadZipFile:
        raise T.ContractError("Dosya bir Word (.docx) belgesi değil.") from None
    return placeholders(text)


def _plain_xml(xml: str) -> str:
    return "\n".join("".join(_unxml(m.group(2)) for m in _T.finditer(p.group(0))) for p in _P.finditer(xml))


def docx_text(data: bytes) -> str:
    """Word şablonunun düz metni (önizleme ve arama için)."""
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        return _plain_xml(z.read("word/document.xml").decode("utf-8", "replace"))


def _fill_part(xml: str, vals: dict[str, str], missing: set[str]) -> str:
    def para(m: re.Match) -> str:
        p = m.group(0)
        runs = list(_T.finditer(p))
        if not runs:
            return p
        joined = "".join(_unxml(r.group(2)) for r in runs)
        if "{{" not in joined:
            return p
        filled, miss = fill(joined, vals)
        missing.update(miss)
        if filled == joined:
            return p
        lines = filled.split("\n")
        first = escape(lines[0]) + "".join(f"</w:t><w:br/><w:t xml:space=\"preserve\">{escape(x)}" for x in lines[1:])
        out, last = [], 0
        for i, r in enumerate(runs):
            out.append(p[last:r.start()])
            open_tag = r.group(1) if "xml:space" in r.group(1) else r.group(1).replace("<w:t", '<w:t xml:space="preserve"', 1)
            out.append(open_tag + (first if i == 0 else "") + r.group(3))
            last = r.end()
        out.append(p[last:])
        return "".join(out)

    return _P.sub(para, xml)


def docx_fill(data: bytes, vals: dict[str, str]) -> tuple[bytes, list[str]]:
    missing: set[str] = set()
    src = zipfile.ZipFile(io.BytesIO(data))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as out:
        for item in src.infolist():
            raw = src.read(item.filename)
            if _PARTS.match(item.filename):
                raw = _fill_part(raw.decode("utf-8"), vals, missing).encode("utf-8")
            out.writestr(item, raw)
    return buf.getvalue(), sorted(missing)
