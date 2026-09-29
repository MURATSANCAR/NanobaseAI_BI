import { createElement, type ReactElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import ExpressionEditor from './narration/ExpressionEditor';
import NarrationSection from './narration/NarrationSection';
import SocialTab from './marketing/SocialTab';
import AgeReportEntry from './age/AgeReport';
import ComparePanel from './diff/ComparePanel';
import type { ExpressionView } from './narration/expressionApi';
import type { NarrationOverview } from './narration/api';
import type { MarketingView } from './marketing/api';
import type { AgeView } from './age/api';
import type { Diff, VersionJob } from './reader/api';

/** Stüdyonun yetki kapısı ön yüzde: yazma/üretim düğmeleri `tasarim.uret`, indirmeler `veri.disa-aktar` ister
 *  (köprü de aynı kuralla 403 verir). Canlıda kısıtlı rol olmadığı için burada `useCan` sahtelenir; bileşenler sunucu
 *  tarafı çizimle (tarayıcısız, FileDrop.test.ts kalıbı) izinli ve izinsiz çizilir. Veri sorgu önbelleğine elle konur,
 *  ağ çağrısı yapılmaz (fetch sahte: çağrılırsa test düşer). */

const perms = vi.hoisted(() => ({ keys: new Set<string>() }));
vi.mock('../../useAdmin', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../useAdmin')>()),
  useCan: (feature: string) => perms.keys.has(feature),
}));
// Yaş raporu yan sayfada (diyalog) açılır; kapalı diyalog sunucu çiziminde içeriğini göstermez. Sahte diyalog
// içeriği her zaman çizer; sorgu bilgisi düğmesi (kendi diyaloğu) bu testin konusu değil.
vi.mock('@base-ui/react/dialog', async () => {
  const { createElement: h, Fragment } = await import('react');
  type P = { children?: unknown; className?: string };
  const pass = ({ children }: P) => h(Fragment, null, children as never);
  const box = (tag: string) => ({ children, className }: P) => h(tag, { className }, children as never);
  return { Dialog: { Root: pass, Portal: pass, Backdrop: () => null, Popup: box('div'), Trigger: box('button'),
    Title: box('h2'), Description: box('p'), Close: box('button') } };
});
vi.mock('../../components/SqlInfo', () => ({ default: () => null }));

const EDIT = 'tasarim.uret';
const EXPORT = 'veri.disa-aktar';
const as = (...keys: string[]) => { perms.keys = new Set(keys); };

const fetchSpy = vi.fn(() => Promise.reject(new Error('testte ağ yok')));
// Yönlendirici sunucu çiziminde her seferinde «useLayoutEffect does nothing on the server» uyarısı basar; beklenen,
// testin konusu değil. Başka her hata olduğu gibi görünür.
const consoleError = console.error;
beforeEach(() => {
  vi.stubGlobal('fetch', fetchSpy);
  vi.spyOn(console, 'error').mockImplementation((...args: unknown[]) => {
    if (typeof args[0] === 'string' && args[0].includes('useLayoutEffect does nothing on the server')) return;
    consoleError(...args);
  });
});
afterEach(() => {
  expect(fetchSpy).not.toHaveBeenCalled();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  perms.keys = new Set();
});

function html(el: ReactElement, seed: [unknown[], unknown][] = []): string {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });
  for (const [key, data] of seed) qc.setQueryData(key, data);
  return renderToStaticMarkup(createElement(MemoryRouter, null, createElement(QueryClientProvider, { client: qc }, el)));
}

// ---------------------------------------------------------------- İfade: öneri düğmesi, cümleye dokunma
const expression: ExpressionView = {
  page: 'p1', no: 1, suggested: null, narration: null,
  labels: [{ id: 'notr', label: 'Nötr', note: '' }],
  sentences: [{ key: 's1', block: 'b1', i: 0, kind: 'para', speaker: null, voice: 'anlatici-kadin', text: 'Kedi uyudu.',
    words: ['Kedi', 'uyudu'], label: 'notr', emphasis: [], source: null, by: null, at: null, probs: null, dropped: false }],
};
const exprHtml = () => html(createElement(ExpressionEditor, { jobId: 'j1', pid: 'p1', canVoice: true, busy: false }),
  [[['studio', 'narration', 'j1', 'expression', 'p1'], expression]]);

describe('İfade düzenleyici', () => {
  it('düzenleme yetkisiyle öneri düğmesi var, cümle açılır', () => {
    as(EDIT);
    const h = exprHtml();
    expect(h).toContain('Zeki AI ile öner');
    expect(h).toContain('aria-controls="ifade-panel-s1"');
    expect(h).toContain('dokunup değiştirebilirsiniz');
  });

  it('yetkisiz kişi cümleleri etiketiyle okur: öneri düğmesi yok, cümle düğmesi pasif', () => {
    as(EXPORT);
    const h = exprHtml();
    expect(h).toContain('Kedi uyudu.');
    expect(h).toContain('Nötr');
    expect(h).not.toContain('Zeki AI ile öner');
    expect(h).not.toContain('aria-controls="ifade-panel-s1"');
    expect(h).toMatch(/<button type="button" disabled=""/);
  });
});

// ---------------------------------------------------------------- Sosyal medya: diz, onayla, sil, indir
const signed = { by: 'editör', at: 1 };
const marketing = {
  quotes: [],
  social: {
    items: [
      { id: 's_00000001', template: 'kare', visual: 'cover', source: 'kapak', headline: '', effect: 'plain', color: null,
        quote: null, w: 1080, h: 1080, draft: false, by: 'editör', at: 1, approved: signed },
      { id: 's_00000002', template: 'kare', visual: 'cover', source: 'kapak', headline: '', effect: 'plain', color: null,
        quote: null, w: 1080, h: 1080, draft: false, by: 'editör', at: 1, approved: null },
    ],
    sources: [{ key: 'kapak', label: 'Kapak', kind: 'cover', draft: false }],
    palette: ['#223344'],
    templates: [{ key: 'kare', label: 'Kare', w: 1080, h: 1080 }],
    effects: ['plain'],
    draft_note: '',
  },
} as unknown as MarketingView;
const socialHtml = () => html(createElement(SocialTab, { jobId: 'j1', v: marketing, refresh: () => undefined }));

describe('Sosyal medya görselleri', () => {
  it('iki yetkiyle: diz, onayla/onayı geri al, sil, tek tek ve toplu indirme', () => {
    as(EDIT, EXPORT);
    const h = socialHtml();
    expect(h).toContain('Görseli diz');
    expect(h).toContain('Onayı geri al');
    expect(h).toContain('>Onayla<');
    expect(h).toContain('aria-label="Görseli sil"');
    expect(h).toContain('social/s_00000001?download=1');
    expect(h).not.toContain('social/s_00000002?download=1');      // onaysız görsel indirilmez
    expect(h).toContain('social/zip');
  });

  it('yalnız görüntüleme: görseller görünür, hiçbir yazma ya da indirme düğmesi yok', () => {
    as();
    const h = socialHtml();
    expect(h).toContain('social/s_00000001?w=520');
    expect(h).toContain('Görseller (2)');
    for (const t of ['Görseli diz', 'Onayı geri al', '>Onayla<', 'Görseli sil', '?download=1', 'social/zip']) {
      expect(h).not.toContain(t);
    }
  });

  it('yalnız dışa aktarma: onaylı görsel indirilir, dizme/onay/silme yok', () => {
    as(EXPORT);
    const h = socialHtml();
    expect(h).toContain('social/s_00000001?download=1');
    expect(h).toContain('social/zip');
    for (const t of ['Görseli diz', 'Onayı geri al', '>Onayla<', 'Görseli sil']) expect(h).not.toContain(t);
  });

  it('yalnız düzenleme: dizme ve onay var, indirme yok', () => {
    as(EDIT);
    const h = socialHtml();
    expect(h).toContain('Görseli diz');
    expect(h).toContain('aria-label="Görseli sil"');
    expect(h).not.toContain('?download=1');
    expect(h).not.toContain('social/zip');
  });
});

// ---------------------------------------------------------------- Yaş raporu: raporu çıkar, PDF indir
const ageEmpty: AgeView = { status: { state: 'none' }, report: null, sources: {}, checklist: [] };
const ageDone = {
  status: { state: 'done' }, sources: {}, checklist: [],
  report: {
    verdict: { level: 'uygun', label: 'Hedef yaşa uygun', reasons: [] }, stale: false, text_source: 'plan',
    band: [5, 8], band_source: 'profil', at: 1, by: 'editör', findings: [], words: [], checks: [],
    word_stats: { reference: false },
  },
} as unknown as AgeView;
const ageHtml = (view: AgeView) => html(createElement(AgeReportEntry, { jobId: 'j1' }), [[['studio', 'age', 'j1'], view]]);

describe('Yaş uygunluğu raporu', () => {
  it('rapor yokken «Raporu çıkar» yalnız düzenleme yetkisiyle', () => {
    as(EDIT);
    expect(ageHtml(ageEmpty)).toContain('Raporu çıkar');
    as(EXPORT);
    const h = ageHtml(ageEmpty);
    expect(h).not.toContain('Raporu çıkar');
    expect(h).toContain('üretim yetkisi olan biri çıkarır');
  });

  it('rapor varken PDF yalnız dışa aktarma yetkisiyle, yenileme yalnız düzenleme yetkisiyle', () => {
    as(EDIT, EXPORT);
    let h = ageHtml(ageDone);
    expect(h).toContain('Raporu yenile');
    expect(h).toContain('PDF indir');
    expect(h).toContain('/age/pdf');
    as(EDIT);
    h = ageHtml(ageDone);
    expect(h).toContain('Raporu yenile');
    expect(h).not.toContain('PDF indir');
    as();
    h = ageHtml(ageDone);
    expect(h).toContain('Hedef yaşa uygun');                     // rapor okunur
    expect(h).not.toContain('Raporu yenile');
    expect(h).not.toContain('PDF indir');
  });
});

// ---------------------------------------------------------------- Sesli okuma: seslendir, insan kaydı
const narration = {
  available: true,
  voices: [{ id: 'anlatici-kadin', label: 'Kadın anlatıcı', note: 'sıcak, sakin', group: 'anlatici' }],
  groups: { anlatici: 'Anlatıcı' },
  settings: { narrator: 'anlatici-kadin', characters: {}, source: 'editor' },
  speakers: [],
  pages: [{ id: 'p1', no: 1, status: 'missing', duration: null, estimated: false, words: 12 }],
  summary: { done: 0, stale: 0, missing: 1, empty: 0, duration: 0 },
  job: null,
  lexicon: { job: [], publisher: [] },
  plan_auto: null,
  recordings: { rights_text: '', upload_mb: 500, extensions: ['.wav'], items: [] },
} as unknown as NarrationOverview;
const narrationHtml = () => html(createElement(NarrationSection, { jobId: 'j1' }), [[['studio', 'narration', 'j1'], narration]]);

describe('Sesli okuma', () => {
  it('düzenleme yetkisiyle seslendir, sayfayı yeniden üret ve insan kaydı yükle düğmeleri', () => {
    as(EDIT);
    const h = narrationHtml();
    expect(h).toContain('Seslendir (1 sayfa)');
    expect(h).toContain('İnsan kaydı yükle');
    expect(h).toContain('Yeniden üret');
    expect(h).not.toMatch(/<fieldset disabled=""/);
  });

  it('yetkisiz kişi sayfaları görür; seslendirme, insan kaydı ve ses seçimi kapalı', () => {
    as(EXPORT);
    const h = narrationHtml();
    expect(h).toContain('Sayfa sayfa dinle');
    expect(h).toContain('s. 1');
    expect(h).not.toContain('Seslendir (1 sayfa)');
    expect(h).not.toContain('İnsan kaydı yükle');
    expect(h).not.toContain('Yeniden üret');
    expect(h).toMatch(/<fieldset disabled=""/);
  });
});

// ---------------------------------------------------------------- Sürüm farkı: değişiklik raporu
const versions: { job: string; jobs: VersionJob[] } = {
  job: 'j1',
  jobs: [{ id: 'j1', self: true, title: null, created_at: null, created_by: null, current: 2, pages: 3,
    revs: [{ rev: 1, at: '2026-09-29T10:00:00', by: 'editör', what: '' }, { rev: 2, at: '2026-09-29T11:00:00', by: 'editör', what: '' }] }],
};
const info = (rev: number, current: boolean) => ({ key: `j1:${current ? 'current' : rev}`, job: 'j1', rev, current, at: null, by: null,
  label: current ? 'Şimdiki hâli' : `Sürüm ${rev}`, pages: 3, title: null });
const diff: Diff = { a: info(1, false), b: info(2, true), pages: [], counts: { changed: 0, added: 0, removed: 0, same: 0 },
  words: { ins: 0, del: 0 }, global: [], page: null };
const compareHtml = () => html(createElement(ComparePanel, { job: 'j1', goTo: () => undefined }), [
  [['studio', 'versions', 'j1'], versions],
  [['studio', 'versions', 'compare', 'j1', 'j1:1', 'j1:current'], diff],
]);

describe('Sürüm farkı', () => {
  it('değişiklik raporu yalnız dışa aktarma yetkisiyle; karşılaştırma herkese açık', () => {
    as(EXPORT);
    let h = compareHtml();
    expect(h).toContain('Değişiklik raporunu indir (PDF)');
    expect(h).toContain('versions/report?a=j1%3A1&amp;b=j1%3Acurrent');
    as(EDIT);
    h = compareHtml();
    expect(h).toContain('Değişmeyen sayfaları da aç');
    expect(h).toContain('Sürüm 1 → Şimdiki hâli');
    expect(h).not.toContain('Değişiklik raporunu indir');
    expect(h).not.toContain('versions/report');
  });
});
