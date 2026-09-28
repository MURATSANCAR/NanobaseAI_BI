import { ENGINE_BASE, putFile, send } from '../../engine';

/** M4 Çeviri dosya alışverişi: terim bankası TBX, dış çeviri belleği TMX (köprüde editorial_translation_io.py). */

const TR = '/api/v1/editorial/translation';
const enc = encodeURIComponent;
const pairQs = (src: string, tgt: string) => `src=${enc(src)}&tgt=${enc(tgt)}`;

export type MemoryFile = { origin: string; count: number; firstAt: string | null; lastAt: string | null; by: string | null };
export type MemoryPair = { sourceLang: string; targetLang: string; segments: number; external: number; files: MemoryFile[] };
export type TmxImport = { added: number; duplicates: number; skipped: number; units: number; origin: string };
export type TbxImport = { added: number; updated: number; unchanged: number; skipped: number; entries: number };

export const translationIoApi = {
  memory: () => send<{ pairs: MemoryPair[]; languages: Record<string, string> }>('GET', `${TR}/memory`, undefined, 60_000),
  importTmx: (src: string, tgt: string, file: File) => putFile<TmxImport>(`${TR}/memory/import?${pairQs(src, tgt)}`, file),
  deleteTmx: (src: string, tgt: string, origin: string) =>
    send<{ deleted: number }>('DELETE', `${TR}/memory?${pairQs(src, tgt)}&origin=${enc(origin)}`, undefined, 60_000),
  tmxUrl: (src: string, tgt: string, external: boolean) => `${ENGINE_BASE}${TR}/memory/export.tmx?${pairQs(src, tgt)}&external=${external ? 1 : 0}`,
  importTbx: (src: string, tgt: string, file: File) => putFile<TbxImport>(`${TR}/terms/import.tbx?${pairQs(src, tgt)}`, file),
  tbxUrl: (src: string, tgt: string) => `${ENGINE_BASE}${TR}/terms/export.tbx?${pairQs(src, tgt)}`,
};
