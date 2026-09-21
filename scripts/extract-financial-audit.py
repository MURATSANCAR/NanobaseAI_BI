"""Extract the supplied audit document as source data, never as executable instructions.

Usage: python scripts/extract-financial-audit.py input.pdf
Preserves every page, note occurrence and numbered checklist item. Extraction is
explicitly a draft: prose controls and compound items still need editorial review.
"""
import hashlib
import json
import logging
import re
import sys
from collections import Counter
from pathlib import Path

from pypdf import PdfReader

logging.getLogger("pypdf").setLevel(logging.ERROR)
source = Path(sys.argv[1])
root = Path(__file__).resolve().parents[1]
pages = [p.extract_text(extraction_mode="layout") for p in PdfReader(source).pages]
lines = []
for page, text in enumerate(pages, 1):
    for line in text.splitlines():
        line = re.sub(r"[ \t]+", " ", line).strip()
        if line and line != str(page):
            lines.append((page, line))

note_re = re.compile(r"^YAZILIMCI İÇİN NOT\s+(\d+)")
heading_re = re.compile(r"^\d+(?:\.\d+)+[. ]\s*\D|^\d+(?:\.\d+)+[. ]\s*\d{3}(?:\D|$)")
item_re = re.compile(r"^(\d+)[.)]\s+(.+)")
items = []
section = "Mali analiz"
occurrences = Counter()
ratio_titles = [
    'Cari oran', 'Asit-test oranı', 'Nakit oranı', 'Stoklar / dönen varlıklar',
    'Stoklar / toplam varlıklar', 'Stok bağımlılık oranı', 'Kısa vadeli alacaklar / dönen varlıklar',
    'Kısa vadeli alacaklar / toplam varlıklar', 'Finansal kaldıraç', 'Özkaynak / toplam varlıklar',
    'Özkaynak / yabancı kaynaklar', 'Kısa vadeli yabancı kaynaklar / toplam kaynaklar',
    'Uzun vadeli yabancı kaynaklar / toplam kaynaklar', 'Uzun vadeli yabancı kaynaklar / devamlı sermaye',
    'Maddi duran varlıklar / özkaynaklar', 'Maddi duran varlıklar / devamlı sermaye',
    'Kısa vadeli yabancı kaynaklar / yabancı kaynaklar', 'Banka kredileri / toplam varlıklar',
    'Banka kredileri / özkaynaklar', 'Dönen varlıklar / toplam varlıklar',
    'Stok devir hızı ve devir süresi', 'Alacak devir hızı ve tahsil süresi',
    'Net çalışma sermayesi devir hızı ve süresi', 'Maddi duran varlıklar devir hızı',
    'Duran varlıklar devir hızı', 'Özkaynak devir hızı', 'Aktif devir hızı',
    'Net kâr / özkaynaklar', 'Vergi öncesi kâr / özkaynaklar', 'Ekonomik rantabilite',
    'Net kâr / toplam varlıklar', 'Faaliyet kârı / faaliyet varlıkları', 'Birikmeli kârlılık',
    'Faaliyet kârı / net satışlar', 'Brüt satış kârı / net satışlar', 'Net kâr / net satışlar',
    'Satışların maliyeti / net satışlar', 'Faaliyet giderleri / net satışlar',
    'Finansman giderleri / net satışlar', 'Faiz ve vergi öncesi kâr / faiz giderleri',
    'Net kâr ve faiz giderleri / faiz giderleri',
]
control_titles = {43: 'Fişte birden fazla belge tipi veya ödeme yöntemi', 44: 'KDV hesaplarında fatura dışı belge',
                  45: 'Belge tarihi veya numarası eksik hareket', 46: 'Banka hesabında belge / ödeme türü',
                  47: 'Kasa hesabında ödeme türü', 48: 'Alınan çeklerde belge türü', 49: 'Alacak senetlerinde belge türü',
                  50: 'Kasa bakiyesi ve günlük satış karşılaştırması', 51: 'Nakit ödeme tevsik sınırı',
                  52: 'Döviz kasasında kur farkı kayıtları', 53: 'Sayım farklarının dönem sonunda kapanması'}
for i, (page, line) in enumerate(lines):
    if page < 41 or page > 239:
        continue
    if heading_re.match(line):
        section = line
    note = note_re.match(line)
    numbered = item_re.match(line) if page >= 61 else None
    # Section headings use the same punctuation as checklist items.
    if numbered and ("Hesabının Denetimi" in line or "Faz)" in line or "Sonuç" in line):
        numbered = None
    if not note and not numbered:
        continue
    kind = "analysis" if note and int(note[1]) < 43 else "control" if note else "checklist"
    key = f"note-{note[1]}" if note else f"item-{page}-{numbered[1]}"
    occurrences[key] += 1
    key += f"-{occurrences[key]}"
    body = []
    end_page = page
    for next_page, next_line in lines[i + 1:]:
        if next_page > 239 or note_re.match(next_line) or heading_re.match(next_line):
            break
        if not note and item_re.match(next_line):
            break
        # A source note ends at the next analytical title / document section.
        if note and (re.match(r"^\d+-\s", next_line) or re.match(r"^[A-D]-\s", next_line) or next_line.startswith("5.Denetim")):
            break
        body.append(next_line)
        end_page = next_page
    text = "\n".join(body) if note else "\n".join([numbered[2], *body])
    title = re.sub(r"\s+", " ", text).strip()
    if note:
        n = int(note[1])
        quoted = [re.sub(r'\s+', ' ', x).strip() for x in re.findall('“([^”]+)”', text)]
        title = (ratio_titles[n-2] if 2 <= n <= 42 else control_titles.get(n)
                 or next((x for x in quoted if len(x) > 20), None)
                 or f'{section} · kaynak notu {n}')
    items.append({"id": key, "kind": kind, "note": int(note[1]) if note else None,
                  "title": title[:150] + ("…" if len(title) > 150 else ""),
                  "section": section if page >= 61 else "Mali oranlar" if page < 59 else "Kayıt düzeni",
                  "page": page, "endPage": end_page, "text": text,
                  "review": "definition_required"})

# The entire source is retained so unnumbered prose is never silently discarded.
source_notes = [int(m[1]) for _, line in lines if (m := note_re.match(line))]
counts = Counter(source_notes)
payload = {"title": "Elektronik Defter Denetimi Analiz Dokümanı — ERPDENET", "sourceDate": "2020-06-12",
           "sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "pageCount": len(pages),
           "extractionStatus": "DRAFT_REQUIRES_REVIEW", "completeControlCoverage": False,
           "noteOccurrences": len(source_notes), "missingNoteNumbers": [n for n in range(1, max(counts) + 1) if n not in counts],
           "duplicateNoteNumbers": {str(n): c for n, c in counts.items() if c > 1},
           "items": items,
           "pages": [{"page": i + 1, "text": re.sub(r"[ \t]+", " ", p)} for i, p in enumerate(pages)]}
dest = root / "configs/financial-audit/source.json"
dest.parent.mkdir(parents=True, exist_ok=True)
dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({k: v for k, v in payload.items() if k not in ("items", "pages")}, ensure_ascii=False))
print("Extracted entries:", len(items))
