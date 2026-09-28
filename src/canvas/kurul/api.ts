import { ENGINE_BASE, ENGINE_ENABLED, EngineAuthError, EngineForbiddenError, freshHeaders } from '../engine';
import { httpErrorText } from '../httpError';
import type { Kaynaklar } from '../components/sqlInfo';

/** DYK Danışma ve yönetim kurulu ekranlarının köprü uçları: /api/v1/kurul/*. Rakamların hepsi köprüden gelir;
 *  ön yüz hiçbir göstergeyi hesaplamaz, yalnız biçimler. */

export type Color = 'yesil' | 'sari' | 'kirmizi' | 'esik_yok';
export type IndState = 'ok' | 'kaynak_yok' | 'hata' | 'olculmedi';
export type Unit = 'tl' | 'yuzde' | 'adet' | 'gun';

export type Me = {
  username: string; display: string; canPrepare: boolean; canFreeze: boolean; canCatalog: boolean; canComment: boolean;
  canAction: boolean; canExport: boolean;
};

export type KurulMeta = {
  bolumler: Record<string, string>; birimler: Record<Unit, string>; yonler: Record<string, string>; renkler: Record<Color, string>;
  toplantiTurleri: Record<string, string>; toplantiDurumlari: Record<string, string>; gundemTurleri: Record<string, string>;
  aksiyonDurumlari: Record<string, string>; paketDurumlari: Record<string, string>; ozetDurumlari: Record<string, string>;
  yorumDurumlari: Record<string, string>; kanallar: Record<string, string>; saglayicilar: Record<string, string>;
  ayarlar: { company: string; staleHours: number; actionWarnDays: number; commentRemindDays: number; historyMonths: number };
  me: Me; modelVar: boolean;
};

export type IndicatorDef = {
  kod: string; bolum: string; bolumAdi: string; ad: string; aciklama: string | null; saglayici: string | null; birim: Unit;
  birimAdi: string; yon: 'artis_kotu' | 'azalis_kotu'; yonAdi: string; esikSari: number | null; esikKirmizi: number | null;
  hedefKaynagi: string | null; sahip: string | null; sahipEposta: string | null; sira: number; aktif: boolean; surum: number;
  guncelleyen: string | null; guncelleme: string | null;
};

export type Trend = { yon: 'yukari' | 'asagi' | 'sabit'; iyi: boolean | null; oran: number | null };

export type CommentLite = { metin: string; yazan: string; onaylayan: string | null; onaylandi: string | null; kaynak: 'insan' | 'zeki' };

export type Indicator = IndicatorDef & {
  durum: IndState; deger: number | null; degerMetin: string | null; degerKisa: string | null; hedef: number | null;
  onceki: number | null; oncekiEtiket: string | null; egilim: Trend | null; renk: Color | null; renkAdi: string | null;
  renkKaynagi: 'esik' | 'kaynak' | null; veriSonGunu: string | null; kaynak: string | null; ekran: string | null; not: string | null;
  olcum: string | null; ayrinti: Record<string, unknown>; renkDegisti: string | null; oncekiRenk: Color | null;
  yorum: CommentLite | null; yorumBekliyor: boolean;
};

export type Panel = {
  donem: string; donemAdi: string; donemler: string[];
  bolumler: Array<{ id: string; ad: string; gostergeler: Indicator[] }>;
  kritik: Indicator[];
  sayilar: { toplam: number; hazir: number; gri: number; hata: number; kirmizi: number; sari: number; yorumsuzRenkli: number };
  enEskiVeri: string | null; olcum: { at: string; donem: string; sayi: number; gri: number; hata: number } | null; olcumSuruyor: boolean;
  /** Sorgu bilgisi: her kutunun ölçüm zinciri (`bolumler[].gostergeler[]:<kod>`), sayaçlar, son ölçüm. */
  kaynaklar?: Kaynaklar;
};

export type Comment = {
  id: string; kod: string; donem: string; metin: string | null; durum: 'hazirlaniyor' | 'taslak' | 'onayli' | 'hata'; durumAdi: string;
  kaynak: 'insan' | 'zeki'; yazan: string; yazildi: string | null; onaylayan: string | null; onaylandi: string | null; hata: string | null;
};

export type IndicatorDetail = {
  gosterge: Indicator; donem: string; donemAdi: string;
  seri: Array<{ donem: string; deger: number | null; renk: Color | null; hedef: number | null; durum: IndState }>;
  yorumlar: Comment[];
  kaynaklar?: Kaynaklar;
};

export type AgendaItem = { sira?: number; baslik: string; tur: 'karar' | 'bilgi'; turAdi?: string; sunan: string | null; sureDk: number | null; ekRef: string | null };

export type Action = {
  id: string; kararId: string; toplantiId: string; eylem: string; sahip: string | null; sahipEposta: string | null; termin: string | null;
  kalanGun: number | null; durum: 'acik' | 'tamamlandi' | 'iptal'; durumAdi: string; gecikti: boolean; sonNot: string | null;
  olusturan: string; olusturma: string | null; guncelleyen: string | null; guncelleme: string | null; tamamlanma: string | null;
  karar?: string; toplanti?: string; toplantiTarihi?: string;
};

export type Decision = {
  id: string; toplantiId: string; gundemSira: number | null; metin: string; oyOzeti: string | null; yazan: string; tarih: string | null;
  guncelleyen: string | null; guncelleme: string | null; aksiyonlar: Action[];
};

export type PackageBrief = {
  id: string; toplantiId: string; surum: number; durum: 'taslak' | 'donduruldu' | 'dagitildi'; durumAdi: string;
  ozetDurum: 'yok' | 'hazirlaniyor' | 'taslak' | 'onayli' | 'hata'; ozetDurumAdi: string; derleyen: string; derleme: string | null;
  donduran: string | null; dondurma: string | null; pdfVar: boolean; pdfSha256: string | null; icerikSha256: string;
  toplanti?: string; toplantiTarihi?: string;
};

export type Meeting = {
  id: string; tur: 'yonetim' | 'danisma'; turAdi: string; baslik: string; tarih: string; saat: string | null; yer: string | null;
  durum: 'planlandi' | 'yapildi' | 'iptal'; durumAdi: string; katilimcilar: string[]; notlar: string | null; olusturan: string;
  olusturma: string | null; guncelleyen: string | null; guncelleme: string | null;
  paketSurum?: number | null; paketDondu?: boolean; kararSayisi?: number; kalanGun?: number;
  gundem?: AgendaItem[]; kararlar?: Decision[]; paketler?: PackageBrief[];
  kaynaklar?: Kaynaklar;
};

export type PackageIndicator = {
  kod: string; ad: string; durum: IndState; deger: number | null; degerMetin: string | null; hedefMetin: string | null;
  oncekiMetin: string | null; oncekiEtiket: string | null; egilim: Trend | null; renk: Color | null; renkAdi: string | null;
  birim: Unit; veriSonGunu: string | null; kaynak: string | null; not: string | null; sahip: string | null; yorum: CommentLite | null;
};

export type PackageContent = {
  kapak: {
    sirket: string; toplanti: Pick<Meeting, 'id' | 'baslik' | 'tur' | 'turAdi' | 'tarih' | 'saat' | 'yer'>; katilimcilar: string[];
    derleme: string; donem: string; donemAdi: string; veriSonGunleri: Record<string, string>; enEskiVeri: string | null;
  };
  gostergeler: Array<{ id: string; ad: string; gostergeler: PackageIndicator[] }>;
  sayilar: Panel['sayilar'];
  kritik: Array<{ ad: string; degerMetin: string | null; sahip: string | null; yorum: string | null }>;
  eksikYorum: Array<{ kod: string; ad: string; sahip: string | null }>;
  gundem: AgendaItem[];
  oncekiKararlar: Array<{ toplanti: string; tarih: string; karar: string; aksiyonlar: Array<{ eylem: string; sahip: string | null; termin: string | null; durum: string; gecikti: boolean; sonNot: string | null }> }>;
  aksiyonOzeti: { acik: number; geciken: number };
  risk: { sayilar: Record<string, number> | null; brifing: { donem: string; metin: string | null; onaylayan: string | null; onayZamani: string | null } | null };
  pazar: { donem: string; donemAd: string | null; metin: string | null; onaylayan: string | null; onaylandiAt: string | null } | null;
};

export type Package = PackageBrief & {
  icerik: PackageContent; ozetMetin: string | null; ozetKaynak: 'zeki' | 'insan' | null; ozetNot: string | null;
  ozetOnaylayan: string | null; ozetOnay: string | null;
  dagitim: Array<{ id: string; alici: string; uyeId: string | null; kanal: string; kanalAdi: string; gonderen: string; zaman: string | null; sonuc: string | null }>;
  olguDisiSayilar?: string[];
  kaynaklar?: Kaynaklar;
};

export type Member = {
  id: string; ad: string; eposta: string | null; adHesabi: string | null; kurul: 'yonetim' | 'danisma'; kurulAdi: string;
  gorev: string | null; aktif: boolean; guncelleyen: string | null; guncelleme: string | null;
};

export type Job = { id: string; tur: string; durum: 'calisiyor' | 'bitti' | 'hata'; sonuc: Record<string, unknown>; hata: string | null; kaynaklar?: Kaynaklar };

export type AgendaSuggestion = { baslik: string; tur: 'karar' | 'bilgi'; neden: string; kod?: string; sunan?: string | null; ayrinti: string[] };

export type MinuteSuggestion = { gundemSira: number | null; metin: string; aksiyonlar: Array<{ eylem: string; sahipAdayi: string | null; terminAdayi: string | null }> };

const B = '/api/v1/kurul';

async function fail(res: Response): Promise<never> {
  const j = (await res.json().catch(() => null)) as { detail?: { message?: string } | string } | null;
  const msg = typeof j?.detail === 'string' ? j.detail : j?.detail?.message;
  if (res.status === 401) throw new EngineAuthError();
  if (res.status === 403) throw new EngineForbiddenError(msg || 'Bu işleme yetkiniz yok.');
  throw new Error(msg || httpErrorText(res.status));
}

async function send<T>(method: string, path: string, body?: unknown, timeoutMs = 120_000): Promise<T> {
  if (!ENGINE_ENABLED) throw new Error('Bu kurulumda veri bağlantısı tanımlı değil.');
  const res = await fetch(`${ENGINE_BASE}${B}${path}`, {
    method,
    credentials: 'include',
    headers: { ...(method === 'GET' ? freshHeaders() : {}), ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (!res.ok) return fail(res);
  return (await res.json()) as T;
}

const qs = (o: Record<string, string | number | boolean | undefined | null>) => {
  const p = new URLSearchParams();
  Object.entries(o).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '' && v !== false) p.set(k, String(v));
  });
  const s = p.toString();
  return s ? `?${s}` : '';
};
const enc = encodeURIComponent;

export const kurulApi = {
  meta: () => send<KurulMeta>('GET', '/meta'),
  panel: (donem?: string) => send<Panel>('GET', `/panel${qs({ donem })}`, undefined, 180_000),
  refresh: () => send<{ started: boolean }>('POST', '/refresh'),
  indicators: () => send<{ items: IndicatorDef[]; kaynaklar?: Kaynaklar }>('GET', '/indicators'),
  indicator: (kod: string, donem?: string) => send<IndicatorDetail>('GET', `/indicators/${enc(kod)}${qs({ donem })}`),
  updateIndicator: (kod: string, b: Partial<Pick<IndicatorDef, 'ad' | 'aciklama' | 'esikSari' | 'esikKirmizi' | 'sahip' | 'sahipEposta' | 'sira' | 'aktif' | 'yon' | 'hedefKaynagi'>>) =>
    send<IndicatorDef>('PATCH', `/indicators/${enc(kod)}`, b),
  addComment: (kod: string, donem: string, metin: string) => send<Comment>('POST', `/indicators/${enc(kod)}/comments`, { donem, metin }),
  draftComment: (kod: string, donem: string) => send<Job & { yorumId: string }>('POST', `/indicators/${enc(kod)}/comments/draft`, { donem }),
  editComment: (id: string, metin: string) => send<Comment>('PATCH', `/comments/${enc(id)}`, { metin }),
  approveComment: (id: string) => send<Comment>('POST', `/comments/${enc(id)}/approve`),
  deleteComment: (id: string) => send<{ ok: boolean }>('DELETE', `/comments/${enc(id)}`),
  meetings: () => send<{ items: Meeting[]; siradaki: Meeting | null; kaynaklar?: Kaynaklar }>('GET', '/meetings'),
  meeting: (id: string) => send<Meeting>('GET', `/meetings/${enc(id)}`),
  createMeeting: (b: Partial<Meeting>) => send<Meeting>('POST', '/meetings', b),
  updateMeeting: (id: string, b: Partial<Meeting>) => send<Meeting>('PATCH', `/meetings/${enc(id)}`, b),
  setAgenda: (id: string, items: AgendaItem[]) => send<{ items: AgendaItem[] }>('PUT', `/meetings/${enc(id)}/agenda`, { items }),
  suggestAgenda: (id: string) => send<{ items: AgendaSuggestion[]; kaynaklar?: Kaynaklar }>('GET', `/meetings/${enc(id)}/agenda/suggest`),
  addDecision: (id: string, b: { metin: string; gundemSira?: number | null; oyOzeti?: string; aksiyonlar?: Array<{ eylem: string; sahip?: string; sahipEposta?: string; termin?: string }> }) =>
    send<Decision>('POST', `/meetings/${enc(id)}/decisions`, b),
  updateDecision: (id: string, b: { metin?: string; oyOzeti?: string; gundemSira?: number | null }) => send<Decision>('PATCH', `/decisions/${enc(id)}`, b),
  deleteDecision: (id: string) => send<{ ok: boolean }>('DELETE', `/decisions/${enc(id)}`),
  addAction: (did: string, b: { eylem: string; sahip?: string; sahipEposta?: string; termin?: string }) => send<Action>('POST', `/decisions/${enc(did)}/actions`, b),
  actions: (p: { durum?: string; mine?: boolean }) => send<{ items: Action[]; total: number; geciken: number; kaynaklar?: Kaynaklar }>('GET', `/actions${qs(p)}`),
  updateAction: (id: string, b: Partial<{ durum: string; sonNot: string; eylem: string; sahip: string; sahipEposta: string; termin: string }>) =>
    send<Action>('PATCH', `/actions/${enc(id)}`, b),
  draftMinutes: (id: string, notlar?: string) => send<Job>('POST', `/meetings/${enc(id)}/minutes/draft`, notlar === undefined ? {} : { notlar }),
  compile: (id: string) => send<Package>('POST', `/meetings/${enc(id)}/packages`, undefined, 300_000),
  packages: () => send<{ items: PackageBrief[]; kaynaklar?: Kaynaklar }>('GET', '/packages'),
  pkg: (id: string) => send<Package>('GET', `/packages/${enc(id)}`),
  draftSummary: (id: string) => send<Job>('POST', `/packages/${enc(id)}/summary/draft`),
  editSummary: (id: string, ozetMetin: string) => send<Package>('PATCH', `/packages/${enc(id)}`, { ozetMetin }),
  approveSummary: (id: string) => send<Package>('POST', `/packages/${enc(id)}/summary/approve`),
  freeze: (id: string) => send<Package>('POST', `/packages/${enc(id)}/freeze`, undefined, 300_000),
  distribute: (id: string, uyeler: string[]) => send<Package>('POST', `/packages/${enc(id)}/distribute`, { uyeler }),
  pdfUrl: (id: string) => `${ENGINE_BASE}${B}/packages/${enc(id)}/document.pdf`,
  members: () => send<{ items: Member[] }>('GET', '/members'),
  saveMember: (id: string | null, b: Partial<Member>) => (id ? send<Member>('PATCH', `/members/${enc(id)}`, b) : send<Member>('POST', '/members', b)),
  deleteMember: (id: string) => send<{ ok: boolean }>('DELETE', `/members/${enc(id)}`),
  job: (id: string) => send<Job>('GET', `/jobs/${enc(id)}`),
};

/** Arka plan işini bitene kadar yoklar (en çok ~10 dk). */
export async function waitJob(id: string): Promise<Job> {
  for (let i = 0; i < 300; i += 1) {
    const j = await kurulApi.job(id);
    if (j.durum !== 'calisiyor') return j;
    await new Promise((r) => setTimeout(r, 2000));
  }
  throw new Error('İş uzun sürdü; birazdan yeniden bakın.');
}

/* ------------------------------------------------------------------ biçim */

const num1 = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 1 });
const money0 = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 0 });
const dayFmt = new Intl.DateTimeFormat('tr-TR', { day: '2-digit', month: 'short', year: 'numeric' });
const dtFmt = new Intl.DateTimeFormat('tr-TR', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });

export function fmtValue(v: number | null | undefined, birim: Unit): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return '—';
  if (birim === 'tl') return `${money0.format(v)} ₺`;
  if (birim === 'yuzde') return `%${num1.format(v)}`;
  if (birim === 'gun') return `${money0.format(v)} gün`;
  return num1.format(v);
}

export function fmtDay(v: string | null | undefined): string {
  if (!v) return '—';
  const d = new Date(v.length <= 10 ? `${v}T00:00:00` : v);
  return Number.isNaN(d.getTime()) ? v : dayFmt.format(d);
}

export function fmtTime(v: string | null | undefined): string {
  if (!v) return '—';
  const d = new Date(v);
  return Number.isNaN(d.getTime()) ? v : dtFmt.format(d);
}

export function fmtLeft(n: number | null | undefined): string {
  if (n === null || n === undefined) return 'termin yok';
  if (n === 0) return 'bugün';
  return n > 0 ? `${n} gün kaldı` : `${-n} gün geçti`;
}

/** Renk yalnız renkle verilmez: her tonun adı ve simgesi var (renk körlüğü, gri tonlu baskı). */
export const COLOR_STYLE: Record<Color | 'gri' | 'hata', { dot: string; ring: string; text: string; label: string; glyph: string }> = {
  kirmizi: { dot: 'bg-red-500', ring: 'ring-red-200', text: 'text-red-700', label: 'Dikkat', glyph: '!' },
  sari: { dot: 'bg-amber-500', ring: 'ring-amber-200', text: 'text-amber-800', label: 'İzlenmeli', glyph: '~' },
  yesil: { dot: 'bg-emerald-500', ring: 'ring-emerald-100', text: 'text-emerald-700', label: 'Yolunda', glyph: '✓' },
  esik_yok: { dot: 'bg-slate-300', ring: 'ring-slate-100', text: 'text-slate-600', label: 'Eşik yok', glyph: '·' },
  gri: { dot: 'bg-slate-200', ring: 'ring-slate-100', text: 'text-slate-500', label: 'Kaynak yok', glyph: '–' },
  hata: { dot: 'bg-slate-400', ring: 'ring-slate-200', text: 'text-slate-600', label: 'Okunamadı', glyph: '?' },
};

export function styleOf(g: { durum: IndState; renk: Color | null }) {
  if (g.durum === 'hata') return COLOR_STYLE.hata;
  if (g.durum !== 'ok') return COLOR_STYLE.gri;
  return COLOR_STYLE[g.renk ?? 'esik_yok'];
}

/** «1.234,5» ya da «1234.5» → sayı; boşsa null. */
export function parseNum(s: string): number | null {
  const t = s.trim().replace(/\s/g, '').replace(/₺|%/g, '');
  if (!t) return null;
  const norm = t.includes(',') ? t.replace(/\./g, '').replace(',', '.') : (t.match(/\./g) ?? []).length > 1 ? t.replace(/\./g, '') : t;
  const n = Number(norm);
  return Number.isFinite(n) ? n : null;
}

export function currentDonem(d = new Date()): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}
