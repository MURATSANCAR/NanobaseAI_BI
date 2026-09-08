/**
 * Bağımlılıksız XLSX yazıcı — sonuç setini gerçek bir Excel dosyasına çevirir.
 *
 * Neden kütüphane yok: kokpit statik derleniyor ve derleme sunucuda yapılıyor; tek bir aktarma
 * düğmesi için 1 MB'lık bir bağımlılık eklemek derlemeyi de dağıtımı da riske sokar. Dosya bir ZIP
 * (sıkıştırmasız/"stored" girdiler) ve birkaç XML parçası; ikisi de burada elle yazılıyor.
 *
 * Biçim kararları: başlık satırı dondurulmuş ve süzgeçli, sayılar gerçek sayı hücresi (metin değil)
 * ve binlik ayraçlı, tarihler gerçek tarih hücresi, satırlar zebra. İkinci sayfada sorunun kendisi,
 * üretilen SQL ve satır sayısı durur — dosyayı üç ay sonra açan, rakamın nereden geldiğini görsün.
 */

export type SheetColumn = { key: string; label: string };

export type XlsxDoc = {
  /** Uzantısız dosya adı. */
  fileBase: string;
  columns: SheetColumn[];
  rows: Record<string, unknown>[];
  question?: string;
  sql?: string;
  /** "Sorgu" sayfasına eklenecek serbest satırlar (ör. satır sayısı, kesilme uyarısı). */
  meta?: { label: string; value: string }[];
};

// ------------------------------------------------------------------ hücre tipleri

type Kind = 'text' | 'int' | 'float' | 'date' | 'datetime';

const RE_DATE = /^\d{4}-\d{2}-\d{2}$/;
const RE_DATETIME = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?/;

function isBlank(v: unknown): boolean {
  return v == null || v === '';
}

/** Kolonun tamamına bakılır: karışık içerik metin sayılır, yoksa tek bir biçim tüm kolona uygulanır. */
function columnKind(rows: Record<string, unknown>[], key: string): Kind {
  let seen = 0;
  let numbers = 0;
  let integers = 0;
  let dates = 0;
  let datetimes = 0;
  for (const r of rows) {
    const v = r[key];
    if (isBlank(v)) continue;
    seen++;
    if (typeof v === 'number' && Number.isFinite(v)) {
      numbers++;
      if (Number.isInteger(v)) integers++;
    } else if (typeof v === 'string') {
      if (RE_DATE.test(v)) dates++;
      else if (RE_DATETIME.test(v)) datetimes++;
    }
  }
  if (seen === 0) return 'text';
  if (numbers === seen) return integers === seen ? 'int' : 'float';
  if (dates === seen) return 'date';
  if (datetimes === seen) return 'datetime';
  return 'text';
}

/** Excel seri numarası: 1899-12-30'dan itibaren gün sayısı (1900 artık yıl hatası dahil). */
function serialFromIso(s: string): number | null {
  const m = RE_DATETIME.exec(s);
  if (m) {
    const ms = Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], m[6] ? +m[6] : 0);
    return Number.isFinite(ms) ? ms / 86_400_000 + 25569 : null;
  }
  if (RE_DATE.test(s)) {
    const ms = Date.UTC(+s.slice(0, 4), +s.slice(5, 7) - 1, +s.slice(8, 10));
    return Number.isFinite(ms) ? ms / 86_400_000 + 25569 : null;
  }
  return null;
}

function cellText(v: unknown): string {
  if (v == null) return '';
  if (typeof v === 'boolean') return v ? 'Evet' : 'Hayır';
  if (typeof v === 'object') return JSON.stringify(v);
  return String(v);
}

// ------------------------------------------------------------------ XML

const XML_HEAD = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>';

function esc(s: string): string {
  // XML 1.0'da geçersiz kontrol karakterleri dosyayı bozar; Excel "onarılamaz içerik" der.
  return s
    .replace(/[\x00-\x08\x0b\x0c\x0e-\x1f]/g, '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/** 0 → A, 25 → Z, 26 → AA */
function colName(i: number): string {
  let s = '';
  let n = i;
  do {
    s = String.fromCharCode(65 + (n % 26)) + s;
    n = Math.floor(n / 26) - 1;
  } while (n >= 0);
  return s;
}

function textCell(ref: string, style: number, value: string): string {
  return value === ''
    ? `<c r="${ref}" s="${style}"/>`
    : `<c r="${ref}" s="${style}" t="inlineStr"><is><t xml:space="preserve">${esc(value)}</t></is></c>`;
}

function numCell(ref: string, style: number, value: number): string {
  return `<c r="${ref}" s="${style}"><v>${value}</v></c>`;
}

// Stil indeksleri (styles.xml içindeki cellXfs sırasıyla aynı olmalı).
const S = {
  base: 0,
  header: 1,
  text: 2,
  textZebra: 3,
  int: 4,
  intZebra: 5,
  float: 6,
  floatZebra: 7,
  date: 8,
  dateZebra: 9,
  datetime: 10,
  datetimeZebra: 11,
  title: 12,
  label: 13,
  muted: 14,
  wrap: 15,
  mono: 16,
} as const;

const KIND_STYLE: Record<Kind, [number, number]> = {
  text: [S.text, S.textZebra],
  int: [S.int, S.intZebra],
  float: [S.float, S.floatZebra],
  date: [S.date, S.dateZebra],
  datetime: [S.datetime, S.datetimeZebra],
};

function stylesXml(): string {
  const font = (extra: string) => `<font>${extra}<name val="Calibri"/><family val="2"/></font>`;
  return `${XML_HEAD}
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<numFmts count="4"><numFmt numFmtId="164" formatCode="#,##0.00"/><numFmt numFmtId="165" formatCode="#,##0"/><numFmt numFmtId="166" formatCode="dd.mm.yyyy"/><numFmt numFmtId="167" formatCode="dd.mm.yyyy hh:mm"/></numFmts>
<fonts count="6">${font('<sz val="11"/><color rgb="FF2A1912"/>')}${font('<b/><sz val="11"/><color rgb="FFFFFFFF"/>')}${font('<b/><sz val="11"/><color rgb="FF2A1912"/>')}${font('<sz val="10"/><color rgb="FF7C6259"/>')}${font('<b/><sz val="14"/><color rgb="FFB34630"/>')}<font><sz val="10"/><color rgb="FF2A1912"/><name val="Consolas"/><family val="3"/></font></fonts>
<fills count="4"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FFB34630"/><bgColor indexed="64"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFFBF3EF"/><bgColor indexed="64"/></patternFill></fill></fills>
<borders count="2"><border><left/><right/><top/><bottom/><diagonal/></border><border><left/><right/><top/><bottom style="thin"><color rgb="FFEAD9CE"/></bottom><diagonal/></border></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="17">
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf>
<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1"/>
<xf numFmtId="0" fontId="0" fillId="3" borderId="1" xfId="0" applyFill="1" applyBorder="1"/>
<xf numFmtId="165" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1"/>
<xf numFmtId="165" fontId="0" fillId="3" borderId="1" xfId="0" applyNumberFormat="1" applyFill="1" applyBorder="1"/>
<xf numFmtId="164" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1"/>
<xf numFmtId="164" fontId="0" fillId="3" borderId="1" xfId="0" applyNumberFormat="1" applyFill="1" applyBorder="1"/>
<xf numFmtId="166" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1"/>
<xf numFmtId="166" fontId="0" fillId="3" borderId="1" xfId="0" applyNumberFormat="1" applyFill="1" applyBorder="1"/>
<xf numFmtId="167" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1"/>
<xf numFmtId="167" fontId="0" fillId="3" borderId="1" xfId="0" applyNumberFormat="1" applyFill="1" applyBorder="1"/>
<xf numFmtId="0" fontId="4" fillId="0" borderId="0" xfId="0" applyFont="1"/>
<xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1"/>
<xf numFmtId="0" fontId="3" fillId="0" borderId="0" xfId="0" applyFont="1"/>
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>
<xf numFmtId="0" fontId="5" fillId="0" borderId="0" xfId="0" applyFont="1" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>
</cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>`;
}

function dataSheetXml(columns: SheetColumn[], rows: Record<string, unknown>[]): string {
  const kinds = columns.map((c) => columnKind(rows, c.key));
  const widths = columns.map((c, i) => {
    let w = c.label.length + 4;
    for (const r of rows) {
      const v = r[c.key];
      const len = kinds[i] === 'float' || kinds[i] === 'int' ? cellText(v).length + 2 : cellText(v).length;
      if (len > w) w = len;
    }
    return Math.min(56, Math.max(11, w + 2));
  });
  const last = colName(Math.max(0, columns.length - 1));
  const dim = `A1:${last}${rows.length + 1}`;

  const head =
    `<row r="1" ht="24" customHeight="1">` +
    columns.map((c, i) => textCell(`${colName(i)}1`, S.header, c.label)).join('') +
    '</row>';

  const body = rows
    .map((r, ri) => {
      const zebra = ri % 2 === 1 ? 1 : 0;
      const cells = columns
        .map((c, ci) => {
          const ref = `${colName(ci)}${ri + 2}`;
          const style = KIND_STYLE[kinds[ci]][zebra];
          const v = r[c.key];
          if (isBlank(v)) return `<c r="${ref}" s="${style}"/>`;
          if (kinds[ci] === 'int' || kinds[ci] === 'float') return numCell(ref, style, Number(v));
          if (kinds[ci] === 'date' || kinds[ci] === 'datetime') {
            const serial = serialFromIso(String(v));
            return serial == null ? textCell(ref, style, cellText(v)) : numCell(ref, style, serial);
          }
          return textCell(ref, style, cellText(v));
        })
        .join('');
      return `<row r="${ri + 2}">${cells}</row>`;
    })
    .join('');

  return `${XML_HEAD}
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<dimension ref="${dim}"/>
<sheetViews><sheetView tabSelected="1" workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/><selection pane="bottomLeft" activeCell="A2" sqref="A2"/></sheetView></sheetViews>
<sheetFormatPr defaultRowHeight="15"/>
<cols>${widths.map((w, i) => `<col min="${i + 1}" max="${i + 1}" width="${w}" customWidth="1"/>`).join('')}</cols>
<sheetData>${head}${body}</sheetData>
${rows.length > 0 ? `<autoFilter ref="${dim}"/>` : ''}
</worksheet>`;
}

function infoSheetXml(doc: XlsxDoc, rowCount: number): string {
  const lines: string[] = [];
  let r = 1;
  const put = (cells: string) => {
    lines.push(`<row r="${r}">${cells}</row>`);
    r++;
  };
  const pair = (label: string, value: string) =>
    put(textCell(`A${r}`, S.label, label) + textCell(`B${r}`, S.wrap, value));

  put(textCell(`A${r}`, S.title, 'Sorgu künyesi'));
  r++; // boş satır
  if (doc.question) pair('Soru', doc.question);
  pair('Aktarma tarihi', new Date().toLocaleString('tr-TR'));
  pair('Satır sayısı', String(rowCount));
  pair('Kolonlar', doc.columns.map((c) => c.label).join(', '));
  for (const m of doc.meta ?? []) pair(m.label, m.value);
  if (doc.sql) {
    r++;
    put(textCell(`A${r}`, S.label, 'Üretilen SQL'));
    for (const line of doc.sql.split('\n')) put(textCell(`A${r}`, S.mono, line));
  }
  put(textCell(`A${r}`, S.muted, 'Timaş Finans · NanobaseAI semantik motor'));

  return `${XML_HEAD}
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<sheetViews><sheetView workbookViewId="0"/></sheetViews>
<sheetFormatPr defaultRowHeight="15"/>
<cols><col min="1" max="1" width="22" customWidth="1"/><col min="2" max="2" width="92" customWidth="1"/></cols>
<sheetData>${lines.join('')}</sheetData>
</worksheet>`;
}

// ------------------------------------------------------------------ ZIP (stored)

const CRC_TABLE = (() => {
  const t = new Uint32Array(256);
  for (let i = 0; i < 256; i++) {
    let c = i;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    t[i] = c >>> 0;
  }
  return t;
})();

function crc32(buf: Uint8Array): number {
  let c = 0xffffffff;
  for (let i = 0; i < buf.length; i++) c = CRC_TABLE[(c ^ buf[i]) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

type Bytes = Uint8Array<ArrayBuffer>;

/** Ham deflate — tarayıcının kendi sıkıştırıcısıyla. Yoksa girdi olduğu gibi saklanır: 40 bin
 *  satırlık bir rapor sıkıştırılmadan 20 MB, sıkıştırılınca 3 MB; ama sıkıştırma yoksa da dosya
 *  geçerli olmalı. */
async function deflateRaw(data: Bytes): Promise<Bytes | null> {
  const CS = (globalThis as { CompressionStream?: new (f: string) => TransformStream }).CompressionStream;
  if (!CS) return null;
  try {
    const stream = new Blob([data]).stream().pipeThrough(new CS('deflate-raw'));
    return new Uint8Array(await new Response(stream).arrayBuffer()) as Bytes;
  } catch {
    return null;
  }
}

async function zip(entries: { name: string; data: Bytes }[]): Promise<Blob> {
  const enc = new TextEncoder();
  const parts: Bytes[] = [];
  const central: Bytes[] = [];
  let offset = 0;
  for (const e of entries) {
    const name = enc.encode(e.name);
    const crc = crc32(e.data);                       // CRC her zaman sıkıştırılmamış veri üzerinden
    const packed = await deflateRaw(e.data);
    const body = packed && packed.length < e.data.length ? packed : e.data;
    const method = body === e.data ? 0 : 8;
    const local = new Uint8Array(30 + name.length);
    const lv = new DataView(local.buffer);
    lv.setUint32(0, 0x04034b50, true);
    lv.setUint16(4, 20, true);
    lv.setUint16(6, 0x0800, true); // ad UTF-8
    lv.setUint16(8, method, true);
    lv.setUint16(12, 0x0021, true); // 1980-01-01
    lv.setUint32(14, crc, true);
    lv.setUint32(18, body.length, true);
    lv.setUint32(22, e.data.length, true);
    lv.setUint16(26, name.length, true);
    local.set(name, 30);
    parts.push(local, body);

    const cd = new Uint8Array(46 + name.length);
    const cv = new DataView(cd.buffer);
    cv.setUint32(0, 0x02014b50, true);
    cv.setUint16(4, 20, true);
    cv.setUint16(6, 20, true);
    cv.setUint16(8, 0x0800, true);
    cv.setUint16(10, method, true);
    cv.setUint16(14, 0x0021, true);
    cv.setUint32(16, crc, true);
    cv.setUint32(20, body.length, true);
    cv.setUint32(24, e.data.length, true);
    cv.setUint16(28, name.length, true);
    cv.setUint32(42, offset, true);
    cd.set(name, 46);
    central.push(cd);
    offset += local.length + body.length;
  }
  const centralSize = central.reduce((s, c) => s + c.length, 0);
  const end = new Uint8Array(22);
  const ev = new DataView(end.buffer);
  ev.setUint32(0, 0x06054b50, true);
  ev.setUint16(8, entries.length, true);
  ev.setUint16(10, entries.length, true);
  ev.setUint32(12, centralSize, true);
  ev.setUint32(16, offset, true);
  return new Blob([...parts, ...central, end], {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  });
}

// ------------------------------------------------------------------ dosya adı

const TR_MAP: Record<string, string> = {
  ç: 'c', Ç: 'c', ğ: 'g', Ğ: 'g', ı: 'i', İ: 'i', ö: 'o', Ö: 'o', ş: 's', Ş: 's', ü: 'u', Ü: 'u', â: 'a', î: 'i', û: 'u',
};

/** Sorudan dosya adı: "e-ticaret raporu istiyorum, 1. kolon kanal…" → "e-ticaret-raporu-kanal-2026-09-08" */
export function questionToFileBase(question: string, when: Date = new Date()): string {
  const slug = (question || '')
    .replace(/[çÇğĞıİöÖşŞüÜâîû]/g, (c) => TR_MAP[c] ?? c)
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/(^-|-$)/g, '');
  // Kesme kelime ortasından olmasın: 48 karakteri aşan ad son tam kelimede biter.
  let head = slug;
  if (head.length > 48) {
    head = head.slice(0, 48);
    const cut = head.lastIndexOf('-');
    if (cut > 16) head = head.slice(0, cut);
  }
  const d = `${when.getFullYear()}-${String(when.getMonth() + 1).padStart(2, '0')}-${String(when.getDate()).padStart(2, '0')}`;
  return `${head || 'sorgu-sonucu'}-${d}`;
}

// ------------------------------------------------------------------ giriş noktası

/** Belgeyi kurar ve tarayıcıya indirtir. Dönen değer: indirilen dosya adı. */
export async function downloadXlsx(doc: XlsxDoc): Promise<string> {
  const enc = new TextEncoder();
  const file = (name: string, xml: string) => ({ name, data: enc.encode(xml) });
  const entries = [
    file(
      '[Content_Types].xml',
      `${XML_HEAD}<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/><Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/></Types>`,
    ),
    file(
      '_rels/.rels',
      `${XML_HEAD}<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/></Relationships>`,
    ),
    file(
      'docProps/core.xml',
      `${XML_HEAD}<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><dc:title>${esc(doc.question || 'Sorgu sonucu')}</dc:title><dc:creator>Timaş Finans</dc:creator><cp:lastModifiedBy>Timaş Finans</cp:lastModifiedBy><dcterms:created xsi:type="dcterms:W3CDTF">${new Date().toISOString().slice(0, 19)}Z</dcterms:created></cp:coreProperties>`,
    ),
    file(
      'xl/workbook.xml',
      `${XML_HEAD}<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Sonuç" sheetId="1" r:id="rId1"/><sheet name="Sorgu" sheetId="2" r:id="rId2"/></sheets></workbook>`,
    ),
    file(
      'xl/_rels/workbook.xml.rels',
      `${XML_HEAD}<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>`,
    ),
    file('xl/styles.xml', stylesXml()),
    file('xl/worksheets/sheet1.xml', dataSheetXml(doc.columns, doc.rows)),
    file('xl/worksheets/sheet2.xml', infoSheetXml(doc, doc.rows.length)),
  ];

  const name = `${doc.fileBase}.xlsx`;
  const url = URL.createObjectURL(await zip(entries));
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 5_000);
  return name;
}
