import collections,ctypes,hashlib,io,json,unicodedata
import pypdfium2 as pdfium
from pypdfium2 import raw
from pypdf._cmap import _parse_to_unicode
from pathlib import Path
from fontTools.ttLib import TTFont
from fontTools.pens.recordingPen import DecomposingRecordingPen
from pypdf import PdfReader

source_pdf=Path('/data/artifacts/94747e819a760fef5e3cef39bb3284c543e217923e2560a3e5719e1060774e50/original.pdf')
reference=TTFont('/reference/CaveatBrush-Regular.ttf')
def outlines(font):
 glyphs=font.getGlyphSet();upm=font['head'].unitsPerEm;result={}
 for name in font.getGlyphOrder():
  pen=DecomposingRecordingPen(glyphs);glyphs[name].draw(pen)
  if not pen.value:continue
  payload=[upm,font['hmtx'][name][0],pen.value]
  result[name]=hashlib.sha256(json.dumps(payload,separators=(',',':')).encode()).hexdigest()
 return result
reference_shapes=outlines(reference);by_shape=collections.defaultdict(list)
labels=collections.defaultdict(set)
for code,name in reference.getBestCmap().items():
 if unicodedata.category(chr(code)) not in ('Co','Cs','Cn'):labels[name].add(code)
edges=[]
if 'GSUB' in reference:
 for lookup in reference['GSUB'].table.LookupList.Lookup:
  for subtable in lookup.SubTable:
   kind=lookup.LookupType
   if kind==7:kind=subtable.ExtensionLookupType;subtable=subtable.ExtSubTable
   if kind==1:edges.extend(subtable.mapping.items())
   if kind==3:edges.extend((source,target) for source,targets in subtable.alternates.items() for target in targets)
for _ in range(len(reference.getGlyphOrder())):
 changed=False
 for source,target in edges:
  before=len(labels[target]);labels[target].update(labels[source]);changed|=len(labels[target])!=before
 if not changed:break
for name,fingerprint in reference_shapes.items():
 by_shape[fingerprint]=sorted(set(by_shape[fingerprint])|labels[name])
reader=PdfReader(source_pdf);results=[];seen=set();font_mappings={}
for page_number in range(44,49):
 fonts=reader.pages[page_number-1]['/Resources']['/Font']
 for key,obj in fonts.items():
  font=obj.get_object();desc=font.get('/DescendantFonts')
  if not desc:continue
  descendant=desc[0].get_object();descriptor=descendant['/FontDescriptor']
  if '/FontFile2' not in descriptor:continue
  data=descriptor['/FontFile2'].get_data();identity=hashlib.sha256(data).hexdigest()
  if identity in seen:continue
  seen.add(identity);tt=TTFont(io.BytesIO(data));shape_map=outlines(tt);matches=[]
  for gid,name in enumerate(tt.getGlyphOrder()):
   fingerprint=shape_map.get(name)
   matches.append({'glyph_id':gid,'outline_sha256':fingerprint,'candidate_codepoints':by_shape.get(fingerprint,[])})
  parsed,_=_parse_to_unicode(font);mapping={}
  assert descendant.get('/CIDToGIDMap')=='/Identity','UNSUPPORTED_CID_MAP'
  by_gid={m['glyph_id']:m for m in matches}
  for encoded,decoded in parsed.items():
   if isinstance(encoded,str) and len(encoded)==1 and isinstance(decoded,str) and len(decoded)==1 and unicodedata.category(decoded)=='Co':
    mapping[ord(decoded)]=by_gid.get(ord(encoded),{}).get('candidate_codepoints',[])
  font_mappings[str(font['/BaseFont']).lstrip('/')]=mapping
  results.append({'page_first_seen':page_number,'font':str(font['/BaseFont']),'font_sha256':identity,'glyphs':len(matches),'matches':matches,'to_unicode':font['/ToUnicode'].get_data().decode('latin1'),'cid_to_gid':'IDENTITY' if descendant.get('/CIDToGIDMap')=='/Identity' else 'STREAM' if descendant.get('/CIDToGIDMap') else 'ABSENT'})
page_results=[]
for page_number in range(44,49):
 items=[]
 def visit(fragment,cm,tm,font,size):
  name=str((font or {}).get('/BaseFont','')).lstrip('/')
  for character in fragment:
   if unicodedata.category(character) not in ('Co','Cs'):continue
   code=ord(character);candidates=font_mappings.get(name,{}).get(code,[])
   items.append({'original_codepoint':code,'candidates':candidates,'font':name})
 reader.pages[page_number-1].extract_text(visitor_text=visit)
 page_results.append({'page':page_number,'private_characters':len(items),'uniquely_mapped':sum(len(i['candidates'])==1 for i in items),'unmapped':sum(not i['candidates'] for i in items),'ambiguous':sum(len(i['candidates'])>1 for i in items),'characters':items})
print(json.dumps({'reference_sha256':hashlib.sha256(Path('/reference/CaveatBrush-Regular.ttf').read_bytes()).hexdigest(),'source_sha256':hashlib.sha256(source_pdf.read_bytes()).hexdigest(),'fonts':results,'page_results':page_results,'source_writes':0,'automatic_acceptance':False}))
