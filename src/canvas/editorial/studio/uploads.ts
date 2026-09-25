import { useEffect, useMemo, useSyncExternalStore } from 'react';
import { EngineAuthError, StudioPlanError, studioPlanApi, type PhotoUpload } from '../../engine';
import { STORE_PHOTO, heldTabLocks, holdTabLock, idbAll, idbDelete, idbPut } from './deviceStore';
import { uid } from './planModel';

/** Fotoğraf yükleme sırası. Dosya seçilir seçilmez cihazdaki depoya (IndexedDB) yazılır ve yükleme
 *  bitene kadar orada kalır; bağlantı koparsa artan aralıkla (1→30 sn, deneme sayısında tavan yok)
 *  yeniden denenir, sayfa yenilenirse kaldığı yerden sıraya girer. Sunucunun kabul etmediği dosya
 *  (tür, boyut) açık hatayla listede kalır; kullanıcı «Kaldır» demeden silinmez. */

export type UploadItem = {
  key: string;
  job: string;
  tab: string;
  name: string;
  type: string;
  size: number;
  page: string | null;
  at: number;
  status: 'waiting' | 'uploading' | 'retrying' | 'failed' | 'done';
  sent: number;
  error: string | null;
  /** Cihaz deposuna yazılamadıysa dosya yalnız bellekte durur (sekme kapanırsa kaybolur; ekran uyarır). */
  stored: boolean;
  result?: PhotoUpload;
};
type Rec = Omit<UploadItem, 'status' | 'sent' | 'error' | 'stored' | 'result'> & { blob: Blob };

export const PHOTO_TYPES = ['image/jpeg', 'image/png', 'image/webp', 'image/heic', 'image/heif'];
const EXT = /\.(jpe?g|png|webp|heic|heif)$/i;

class PhotoUploads {
  private items: UploadItem[] = [];
  private blobs = new Map<string, Blob>();
  private listeners = new Set<() => void>();
  private snap: UploadItem[] = [];
  private running = false;
  private backoff = 0;
  private timer: number | null = null;
  private readonly tab = uid('u');
  onDone: ((r: PhotoUpload, item: UploadItem) => void) | null = null;

  constructor(readonly job: string) {
    holdTabLock(`${job}:${this.tab}`);
    window.addEventListener('online', () => { this.backoff = 0; this.kick(0); });
    void this.adopt();
  }

  subscribe = (f: () => void) => { this.listeners.add(f); return () => { this.listeners.delete(f); }; };
  get = () => this.snap;
  private emit() { this.snap = this.items.map((i) => ({ ...i })); this.listeners.forEach((f) => f()); }

  /** Kapanmış sekmelerden kalan yarım yüklemeler devralınır. */
  private async adopt() {
    try {
      const held = await heldTabLocks();
      const recs = (await idbAll<Rec>(STORE_PHOTO)).filter((r) => r.job === this.job && !held.has(`${r.job}:${r.tab}`));
      for (const r of recs) {
        if (this.items.some((i) => i.key === r.key)) continue;
        this.blobs.set(r.key, r.blob);
        this.items.push({ ...r, tab: this.tab, status: 'waiting', sent: 0, error: null, stored: true });
        await idbPut(STORE_PHOTO, { ...r, tab: this.tab });
      }
      if (recs.length) { this.emit(); this.kick(0); }
    } catch { /* depo yok: devralınacak bir şey de yok */ }
  }

  async add(files: File[], page: string | null, limitMb: number | null) {
    for (const f of files) {
      const key = uid('f');
      const item: UploadItem = { key, job: this.job, tab: this.tab, name: f.name || 'fotograf', type: f.type, size: f.size, page,
        at: Date.now(), status: 'waiting', sent: 0, error: null, stored: false };
      if (!(PHOTO_TYPES.includes(f.type) || EXT.test(f.name))) {
        item.status = 'failed';
        item.error = 'Bu dosya türü yüklenemez. JPEG, PNG, WebP ya da HEIC seçin.';
      } else if (limitMb && f.size > limitMb * 1024 * 1024) {
        item.status = 'failed';
        item.error = `Dosya ${(f.size / 1048576).toLocaleString('tr-TR', { maximumFractionDigits: 1 })} MB; bir fotoğraf en çok ${limitMb} MB olabilir.`;
      } else {
        this.blobs.set(key, f);
        try {
          await idbPut(STORE_PHOTO, { key, job: this.job, tab: this.tab, name: item.name, type: f.type, size: f.size, page, at: item.at, blob: f } satisfies Rec);
          item.stored = true;
        } catch { /* bellekte kalır; ekran «cihaza kaydedilemedi» der */ }
      }
      this.items.push(item);
    }
    this.emit();
    this.kick(0);
  }

  remove(key: string) {
    this.items = this.items.filter((i) => i.key !== key);
    this.blobs.delete(key);
    void idbDelete(STORE_PHOTO, key).catch(() => undefined);
    this.emit();
  }

  retry(key: string) {
    const it = this.items.find((i) => i.key === key);
    if (it && this.blobs.has(key)) { it.status = 'waiting'; it.error = null; this.emit(); this.kick(0); }
  }

  private kick(ms: number) {
    if (this.timer) window.clearTimeout(this.timer);
    this.timer = window.setTimeout(() => { this.timer = null; void this.run(); }, ms);
  }

  private async run() {
    if (this.running) return;
    this.running = true;
    try {
      for (;;) {
        const it = this.items.find((i) => i.status === 'waiting' || i.status === 'retrying');
        if (!it) break;
        const blob = this.blobs.get(it.key);
        if (!blob) { it.status = 'failed'; it.error = 'Dosya bu cihazda bulunamadı; yeniden seçin.'; this.emit(); continue; }
        it.status = 'uploading';
        it.sent = 0;
        this.emit();
        try {
          const r = await studioPlanApi.uploadPhoto(this.job, blob, it.name, it.page, (sent) => { it.sent = sent; this.emit(); });
          it.status = 'done';
          it.sent = it.size;
          it.result = r;
          this.backoff = 0;
          this.blobs.delete(it.key);
          await idbDelete(STORE_PHOTO, it.key).catch(() => undefined);
          this.emit();
          this.onDone?.(r, it);
          const done = it.key;
          window.setTimeout(() => { this.items = this.items.filter((x) => x.key !== done); this.emit(); }, 4000);
        } catch (e) {
          if (e instanceof StudioPlanError && e.status >= 400 && e.status < 500 && e.status !== 409) {
            it.status = 'failed';
            it.error = e.message;
            this.emit();
            continue;
          }
          // Ağ yok, oturum düştü, sunucu meşgul ya da yanıt vermiyor: dosya cihazda bekler, yeniden denenir.
          it.status = 'retrying';
          it.error = e instanceof EngineAuthError ? 'Oturum gerekli; giriş yapınca yükleme sürer.'
            : e instanceof StudioPlanError && e.status === 409 ? e.message : 'Bağlantı yok; yeniden denenecek.';
          this.emit();
          this.backoff = Math.min(30_000, this.backoff ? this.backoff * 2 : 1000);
          this.kick(this.backoff);
          break;
        }
      }
    } finally {
      this.running = false;
    }
  }
}

const uploads = new Map<string, PhotoUploads>();
export function usePhotoUploads(job: string, onDone: (r: PhotoUpload, item: UploadItem) => void) {
  const u = useMemo(() => {
    let x = uploads.get(job);
    if (!x) { x = new PhotoUploads(job); uploads.set(job, x); }
    return x;
  }, [job]);
  useEffect(() => { u.onDone = onDone; }, [u, onDone]);
  const items = useSyncExternalStore(u.subscribe, u.get);
  return { uploads: u, items };
}
