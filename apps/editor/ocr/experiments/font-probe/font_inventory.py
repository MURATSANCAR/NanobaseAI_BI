import collections,ctypes,json,unicodedata
from pathlib import Path
import pypdfium2 as pdfium
from pypdfium2 import raw
source=Path('/data/artifacts/94747e819a760fef5e3cef39bb3284c543e217923e2560a3e5719e1060774e50/original.pdf')
output=[]
with pdfium.PdfDocument(source) as document:
 pages=len(document)
 for number in range(pages):
  page=document[number];text=page.get_textpage()
  try:
    fonts=collections.Counter();total=text.count_chars()
    for i in range(total):
     code=raw.FPDFText_GetUnicode(text.raw,i)
     if code>0x10ffff or unicodedata.category(chr(code)) in ('Co','Cs') or code==0xfffd:
      flags=ctypes.c_int();length=raw.FPDFText_GetFontInfo(text.raw,i,None,0,ctypes.byref(flags))
      buffer=ctypes.create_string_buffer(length) if length else None
      if length:raw.FPDFText_GetFontInfo(text.raw,i,buffer,length,ctypes.byref(flags))
      name=buffer.value.decode('utf-8','replace') if buffer else 'UNKNOWN'
      fonts[name]+=1
    if fonts:output.append({'page':number+1,'total_characters':total,'corrupt_by_font':dict(fonts)})
  finally:
   text.close();page.close()
print(json.dumps({'source_pages':pages,'corrupt_pages':output,'source_writes':0},ensure_ascii=False))
