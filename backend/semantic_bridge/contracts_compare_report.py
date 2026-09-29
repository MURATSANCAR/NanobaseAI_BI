"""Sözleşme karşılaştırma — Word raporları (dış kütüphane yok, WordprocessingML elle).

- **Sözleşme raporu**: kıyas grubu, farklı maddeler (değer, emsal medyanı ve aralığı, durum, gerekçe, inceleme), standart
  pozisyon ihlalleri, şekil eksikleri, özgün notlar, aynı hak sahibinin önceki sözleşmesinden farklar.
- **Belge farkı raporu**: madde madde durum; değişen maddede eklenen kelime yeşil altı çizili, çıkan kırmızı üstü çizili,
  şablon alanı mor. Rakamlar uç cevabının aynısıdır (rapor yeniden hesaplamaz).
"""
from __future__ import annotations

import io
import zipfile
from datetime import datetime, timezone
from typing import Any, Iterable, Optional
from xml.sax.saxutils import escape

W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def _run(text: str, *, bold: bool = False, color: Optional[str] = None, strike: bool = False, underline: bool = False,
         shade: Optional[str] = None, size: Optional[int] = None) -> str:
    props = []
    if bold:
        props.append("<w:b/>")
    if color:
        props.append(f'<w:color w:val="{color}"/>')
    if strike:
        props.append("<w:strike/>")
    if underline:
        props.append('<w:u w:val="single"/>')
    if shade:
        props.append(f'<w:shd w:val="clear" w:color="auto" w:fill="{shade}"/>')
    if size:
        props.append(f'<w:sz w:val="{size}"/>')
    rpr = f"<w:rPr>{''.join(props)}</w:rPr>" if props else ""
    return f'<w:r>{rpr}<w:t xml:space="preserve">{escape(text)}</w:t></w:r>'


def _p(runs: Iterable[str] | str, *, style: Optional[str] = None, space_after: int = 80) -> str:
    body = runs if isinstance(runs, str) else "".join(runs)
    pstyle = '<w:pStyle w:val="%s"/>' % style if style else ""
    ppr = f'<w:pPr>{pstyle}<w:spacing w:after="{space_after}"/></w:pPr>'
    return f"<w:p>{ppr}{body}</w:p>"


def _h(text: str, level: int = 1) -> str:
    return _p([_run(text, bold=True, size=32 if level == 1 else 26)], space_after=120)


def _table(header: list[str], rows: list[list[str | list[str]]]) -> str:
    border = ('<w:tblBorders>' + "".join(f'<w:{b} w:val="single" w:sz="4" w:space="0" w:color="BFBFBF"/>'
                                         for b in ("top", "left", "bottom", "right", "insideH", "insideV")) + '</w:tblBorders>')

    def cell(v: str | list[str], bold: bool = False) -> str:
        content = v if isinstance(v, list) else [_run(str(v), bold=bold)]
        return f'<w:tc><w:tcPr><w:tcW w:w="0" w:type="auto"/></w:tcPr>{_p(content, space_after=0)}</w:tc>'

    out = [f'<w:tbl><w:tblPr><w:tblW w:w="5000" w:type="pct"/>{border}</w:tblPr>']
    out.append("<w:tr>" + "".join(cell(h, True) for h in header) + "</w:tr>")
    for r in rows:
        out.append("<w:tr>" + "".join(cell(v) for v in r) + "</w:tr>")
    out.append("</w:tbl>")
    return "".join(out) + _p([], space_after=120)


def _package(body: str, title: str) -> bytes:
    doc = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {W}><w:body>{body}'
           '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134" '
           'w:header="709" w:footer="709" w:gutter="0"/></w:sectPr></w:body></w:document>')
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    core = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><cp:coreProperties '
            'xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            f'<dc:title>{escape(title)}</dc:title><dc:creator>Zeki AI</dc:creator>'
            f'<dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created></cp:coreProperties>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml",
                   '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                   '<Default Extension="xml" ContentType="application/xml"/>'
                   '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
                   '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/></Types>')
        z.writestr("_rels/.rels",
                   '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
                   '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
                   '</Relationships>')
        z.writestr("word/document.xml", doc)
        z.writestr("docProps/core.xml", core)
    return buf.getvalue()


def _stamp() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%d.%m.%Y %H:%M")


DEVIATING = ("yuksek", "dusuk", "nadir", "nadir-madde", "eksik")


def contract_docx(d: dict[str, Any]) -> bytes:
    s = d["subject"]
    c = d["criteria"]
    body = [_h(f"Sözleşme karşılaştırma raporu — {s['no']}")]
    body.append(_p([_run(s.get("baslik") or "", bold=True)]))
    body.append(_p([_run(" · ".join(str(x) for x in (s.get("yazar"), s.get("tip"), s.get("odeme"), s.get("para"), s.get("bolum"),
                                                        s.get("bas")) if x))]))
    body.append(_p([_run(f"Hazırlandı: {_stamp()} · CRM görüntüsü: {(d.get('gorunum') or {}).get('okunduAn') or '—'}", color="666666")]))
    body.append(_h("Kıyas grubu", 2))
    dims = "; ".join(f"{b['ad']}: {b['deger'] or '—'}" for b in c["boyutlar"])
    body.append(_p([_run(f"{dims}; {c['donem']['ad']}: {c['donem']['deger']}. Emsal: {c['emsal']} anlaşma "
                         f"({c['sozlesme']} CRM kaydı).")]))
    if c.get("gevsetilen"):
        body.append(_p([_run("Emsal az olduğu için gevşetilen ölçüt: " + ", ".join(c["gevsetilen"]) + ".", color="9C5700")]))
    if c.get("kur"):
        body.append(_p([_run(c["kur"], color="666666")]))
    rows = []
    for g in d["groups"]:
        for cl in g["clauses"]:
            if cl["status"] not in DEVIATING:
                continue
            spread = (f"medyan {cl.get('medyanAd') or '—'}; %10–%90 {cl.get('p10Ad') or '—'} – {cl.get('p90Ad') or '—'}"
                      if cl.get("medyanAd") else ", ".join(f"{t['ad']} {round((t.get('pay') or 0) * 100, 1)}%" for t in cl.get("enSik") or []))
            rv = cl.get("inceleme")
            rows.append([cl["label"], cl["valueLabel"], spread, [_run(cl["statusLabel"], bold=True, color="C00000")],
                         cl.get("reason") or "", (rv or {}).get("statusLabel", "") + (f" — {rv.get('note')}" if rv and rv.get("note") else "")])
    body.append(_h(f"Farklı maddeler ({len(rows)})", 2))
    body.append(_table(["Madde", "Bu sözleşme", "Emsal", "Durum", "Gerekçe", "İnceleme"], rows) if rows
                else _p([_run("Bütün maddeler emsalle uyumlu.")]))
    viol = [x for x in d.get("pozisyon") or [] if not x["ok"]]
    if d.get("pozisyon") is not None:
        body.append(_h(f"Standart pozisyon ihlalleri ({len(viol)})", 2))
        body.append(_table(["Kural", "Düzey", "Bu sözleşme", "Gerekçe"],
                           [[x["rule"], [_run(x.get("levelLabel") or x["level"], bold=x["level"] == "kirmizi",
                                              color="C00000" if x["level"] == "kirmizi" else "9C5700")], x["value"], x.get("reason") or ""]
                            for x in viol]) if viol else _p([_run("Onaylı kurallara aykırılık yok.")]))
    fails = [x for x in d.get("sekil") or [] if not x["ok"]]
    body.append(_h(f"Şekil denetimi ({len(fails)} eksik)", 2))
    body.append(_table(["Şart", "Eksik", "Dayanak"], [[x["label"], x.get("detail") or "", x["law"]] for x in fails]) if fails
                else _p([_run("Eksik yok.")]))
    notes = [t for t in d.get("texts") or [] if t["status"] != "kalip"]
    if notes:
        body.append(_h("Serbest metinli maddeler", 2))
        body.append(_table(["Alan", "Metin", "Durum"], [[t["label"], t["text"], t["statusLabel"]] for t in notes]))
    h = d.get("history") or {}
    if h.get("onceki"):
        body.append(_h(f"Aynı hak sahibinin önceki sözleşmesinden farklar ({h['onceki']['no']})", 2))
        body.append(_table(["Madde", "Önceki", "Bu sözleşme"], [[x["label"], str(x["old"] or "—"), str(x["new"] or "—")]
                                                             for x in h.get("degisen") or []]) if h.get("degisen")
                    else _p([_run("Maddeler aynı.")]))
    body.append(_p([_run("Kararlar sayımdır (emsal sayısı ve eşik); yapay zekâ tahmini değildir. Şekil denetimi hukuki görüş "
                         "değildir. CRM'e hiçbir şey yazılmamıştır.", color="666666")]))
    return _package("".join(body), f"Sözleşme karşılaştırma {s['no']}")


def _diff_runs(ops: list[dict[str, str]]) -> list[str]:
    out = []
    for i, o in enumerate(ops):
        sp = " " if i < len(ops) - 1 else ""
        if o["op"] == "eq":
            out.append(_run(o["text"] + sp))
        elif o["op"] == "ins":
            out.append(_run(o["text"], color="006100", underline=True, shade="E2F0D9"))
            out.append(_run(sp))
        elif o["op"] == "del":
            out.append(_run(o["text"], color="C00000", strike=True, shade="FBE3E3"))
            out.append(_run(sp))
        else:
            out.append(_run(o["text"] or "—", color="5B2C83", shade="EDE4F7"))
            out.append(_run(sp))
    return out


LABEL = {"ayni": "Aynı", "degismis": "Değişmiş", "yeri-degismis": "Yeri değişmiş", "eklenmis": "Yalnız incelenen belgede",
         "cikarilmis": "Yalnız karşılaştırılanda"}


def diff_docx(d: dict[str, Any], only_diff: bool = True) -> bytes:
    a, b = d["a"], d["b"]
    body = [_h("Belge karşılaştırma raporu"),
            _p([_run("İncelenen: ", bold=True), _run(a.get("title") or "")]),
            _p([_run("Karşılaştırılan: ", bold=True), _run(b.get("title") or "")]),
            _p([_run(f"Hazırlandı: {_stamp()} · Metin kişisel verileri maskelenmiş hâliyle.", color="666666")]),
            _p([_run(" · ".join(f"{LABEL[k]} {v}" for k, v in d["sayim"].items()))]),
            _p([_run("Yeşil altı çizili: yalnız incelenen belgede · kırmızı üstü çizili: yalnız karşılaştırılanda · mor: şablon "
                     "alanının doldurulduğu yer.", color="666666")])]
    t = d.get("turler") or {}
    names = d.get("turAdlari") or {}
    if t.get("yalnizB"):
        body.append(_p([_run("Karşılaştırılanda olup incelenende bulunmayan madde türleri: ", bold=True),
                        _run(", ".join(names.get(x, x) for x in t["yalnizB"]), color="C00000")]))
    rows = []
    for r in d["maddeler"]:
        if only_diff and r["durum"] == "ayni":
            continue
        cl = r.get("a") or r.get("b") or {}
        title = " · ".join(x for x in (f"Madde {cl.get('no')}" if cl.get("no") else None, cl.get("baslik"), cl.get("turAd")) if x) or "—"
        text = _diff_runs(r["fark"]) if r.get("fark") else [_run(cl.get("metin") or "")]
        rows.append([title, [_run(LABEL[r["durum"]], bold=True)], text])
    body.append(_table(["Madde", "Durum", "Metin"], rows) if rows else _p([_run("Farklı madde yok.")]))
    return _package("".join(body), "Belge karşılaştırma")


__all__ = ["contract_docx", "diff_docx"]
