import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createElement, type ReactNode } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';
import { UPLOAD_FEATURES } from './fileDropRules';

/** Kullanıcı: «okuma yaptığımız ekranlarda upload da olacaktır ama sunucuda göremedim». Yükleme kodda vardı ama bir
 *  eser/iş seçilmeden ya da yetkisiz kişide hiç görünmüyordu. Bu test iki şeyi bağlar:
 *  1) Belge okuyan ana ekranlar (redaksiyon, son okuma, çeviri) liste boşken, hiçbir şey seçmeden yükleme alanını çizer.
 *  2) Bütün arayüzde dosya girişi yalnız ortak yükleme alanından geçer (tür/boyut yazılı, sürükle-bırak, yetki kilidi). */

// Kabuk (menü, sohbet, üst şerit) bu testin konusu değil; yalnız ekranın kendi içeriği çizilir.
vi.mock('../stitch/Shell', () => ({
  default: ({ children }: { children: ReactNode }) => children,
  ZoomStage: ({ children }: { children: ReactNode }) => children,
  useShellZoom: () => 1,
  ZOOM_MIN: 0.5,
  ZOOM_MAX: 2,
}));

const SRC = fileURLToPath(new URL('../../', import.meta.url));

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((n) => {
    const p = join(dir, n);
    if (statSync(p).isDirectory()) return walk(p);
    return /\.tsx?$/.test(n) && !/\.test\.tsx?$/.test(n) ? [p] : [];
  });
}

async function renderAt(path: string, load: () => Promise<{ default: () => ReactNode }>) {
  const { default: Screen } = await load();
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return renderToStaticMarkup(
    createElement(QueryClientProvider, { client: qc }, createElement(MemoryRouter, { initialEntries: [path] }, createElement(Screen))),
  );
}

describe('belge okuyan ekranlarda yükleme ilk görünümde', () => {
  it('Redaksiyon: eser listesi boşken metin yükleme alanı ve «yeni eser dosya adından» hedefi görünür', async () => {
    const h = await renderAt('/redaksiyon', () => import('../editorial/RedactionScreen'));
    expect(h).toContain('data-filedrop');
    expect(h).toContain('Metin dosyası yükle');
    expect(h).toContain('Kabul edilen: DOCX, PDF, TXT, MD · en çok 120 MB');
    expect(h).toContain('Yeni eser dosyası (adı dosya adından)');
    expect(h).toContain('Yukarıdaki yükleme alanına dosyayı bırakın');
  });

  it('Son okuma: hiçbir şey seçmeden belge inceleme yükleme alanı ve prova seçeneği görünür', async () => {
    const h = await renderAt('/son-okuma', () => import('../editorial/ProofScreen'));
    expect(h).toContain('data-filedrop');
    expect(h).toContain('Belge yükle ve incelet');
    expect(h).toContain('Baskı provası');
    expect(h).toContain('Kabul edilen: DOC, DOCX, PDF, ODT, RTF, TXT, MD');
  });

  it('Çeviri: iş listesi boşken kaynak metin yükleme alanı (yeni iş dosya adından) ve dil çifti görünür', async () => {
    const h = await renderAt('/ceviri', () => import('../editorial/translation/TranslationScreen'));
    expect(h).toContain('data-filedrop');
    expect(h).toContain('Kaynak metni yükle (yeni çeviri işi)');
    expect(h).toContain('Kaynak dil');
    expect(h).toContain('Hedef dil');
  });
});

describe('bütün dosya girişleri ortak yükleme alanından geçer', () => {
  const files = walk(SRC);

  it('FileDrop dışında hiçbir ekranda çıplak dosya girişi yok', () => {
    const raw = files
      .filter((p) => !p.endsWith(join('components', 'FileDrop.tsx')))
      // Sesli not: mikrofon açılamayan telefonda ses kaydedicisinden dosya seçimi (belge değil, kayıt).
      .filter((p) => !p.endsWith(join('voice', 'VoiceNoteButton.tsx')))
      .filter((p) => /type=["']file["']/.test(readFileSync(p, 'utf-8')))
      .map((p) => relative(SRC, p));
    expect(raw).toEqual([]);
  });

  it('yükleme bekleyen her ekran ortak alanı kullanır', () => {
    const screens = [
      'canvas/editorial/RedactionScreen.tsx', // WorkUpload
      'canvas/editorial/WorkPicker.tsx',
      'canvas/editorial/DocumentReview.tsx',
      'canvas/editorial/translation/TranslationScreen.tsx',
      'canvas/editorial/translation/MemoryBank.tsx',
      'canvas/editorial/translation/TermBank.tsx',
      'canvas/editorial/applications/ApplicationsScreen.tsx',
      'canvas/editorial/applications/ApplicationScreen.tsx',
      'canvas/editorial/contracts/TemplatesScreen.tsx',
      'canvas/editorial/studio/StudioHome.tsx',
      'canvas/tenders/TenderDetail.tsx',
      'canvas/tenders/DocumentsVault.tsx',
      'canvas/pazar/ReportsScreen.tsx',
      'canvas/dijital/ImportWizard.tsx',
      'canvas/channels/Channel.tsx',
      'canvas/channels/trendyol/Imports.tsx',
      'canvas/channels/amazon/AmazonHome.tsx',
      'canvas/readers/Imports.tsx',
      'canvas/ads/AdsImport.tsx',
      'canvas/social/SocialReport.tsx',
      'canvas/schools/ContextUpload.tsx',
      'canvas/hr/recruit/RecruitBoard.tsx',
      'canvas/marketing/creative/BrandKit.tsx',
    ];
    const uses = /<(FileDrop|FilePick|FileButton|WorkUpload|UploadStep)\b/;
    const missing = screens.filter((s) => !uses.test(readFileSync(join(SRC, s), 'utf-8')));
    expect(missing).toEqual([]);
  });

  it('yetkisiz kişiden yükleme gizlenmez: eski «rolünüzde yok» notları yerine kilitli alan', () => {
    const hidden = files
      .map((p) => [relative(SRC, p), readFileSync(p, 'utf-8')] as const)
      .filter(([, s]) => /(Belge yükleme yetkiniz yok|Rapor yükleme rolünüzde yok|Dosya yükleme rolünüzde yok|İçe aktarma yetkiniz yok|Yükleme yetkisi rolünüzde yok)/.test(s))
      .map(([p]) => p);
    expect(hidden).toEqual([]);
  });

  it('kullanılan her yükleme yetkisinin adı tanımlı (kilitli alanda «gereken yetki» boş kalmaz)', () => {
    const used = new Set<string>();
    for (const p of files) {
      const s = readFileSync(p, 'utf-8');
      if (!/<(FileDrop|FilePick|FileButton)\b/.test(s)) continue;
      for (const m of s.matchAll(/feature="([a-z0-9.-]+)"/g)) used.add(m[1]);
    }
    expect(used.size).toBeGreaterThan(10);
    expect([...used].filter((k) => !(k in UPLOAD_FEATURES))).toEqual([]);
  });
});
