/** Kitap Tasarım Stüdyosu — e-kitap bölümü (aynı sayfa planından EPUB: sabit sayfa ya da akışkan). */
export { default as EpubSection } from './EpubSection';
export { default as EpubPreview } from './EpubPreview';
export { default as AltTextList } from './AltTextList';
export { epubApi, useEpub, isbnOk } from './api';
export type { AltItem, EpubCheck, EpubResult, EpubView, EpubWant } from './api';
