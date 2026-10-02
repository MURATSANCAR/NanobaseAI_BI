import { useSyncExternalStore } from 'react';
import { EngineAuthError, bookReadApi, type BookReadMode } from '../engine';
import { STORE_BOOK, heldTabLocks, holdTabLock, idbAll, idbDelete, idbPut } from './studio/deviceStore';

/** Kitap okutma yükleme sırası — sayfadan bağımsız, portal boyunca yaşar (tek örnek).
 *
 *  Kişi PDF'leri bırakır ve istediği sayfaya geçer: yükleme arka planda sürer, her sayfada köşedeki gösterge
 *  (BookUploadDock) ilerlemeyi yazar. Dosya seçilir seçilmez cihazdaki depoya (IndexedDB) da yazılır; sekme
 *  kapanır ya da sayfa yenilenirse portal yeniden açıldığında yükleme kaldığı yerden (dosyanın başından) sürer.
 *  Aynı anda tek dosya gider. Bağlantı koparsa, oturum düşerse ya da sunucu meşgulse dosya bekler ve artan
 *  aralıkla (1→60 sn, deneme sayısında tavan yok) yeniden denenir. Yalnız sunucunun kalıcı reddi (dosya PDF değil,
 *  çok büyük, yetki yok) satırda sade cümleyle kalır; kişi kaldırana kadar silinmez. Sunucuya ulaşan dosya
 *  buradan düşer; oradan sonrası (gönderim, sıra, okuma) köprüde ve GPU'da, tarayıcıdan bağımsızdır. */

export type BookUpload = {
  key: string;
  tab: string;
  name: string;
  title: string;
  size: number;
  at: number;
  status: 'waiting' | 'uploading' | 'retrying' | 'failed';
  /** Gönderilen oran (0–1). */
  share: number;
  error: string | null;
  /** Cihaz deposuna yazılamadıysa dosya yalnız bellekte durur (sekme kapanırsa kaybolur; ekran uyarır). */
  stored: boolean;
  /** Kitap Eczanesi'nden: arşiv kipi ve kategori (yoksa tam okuma). */
  mode?: BookReadMode;
};
type Rec = Pick<BookUpload, 'key' | 'tab' | 'name' | 'title' | 'size' | 'at' | 'mode'> & { blob: Blob };

const uid = () => `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
/** Yeniden denenebilir: bağlantı yok (0), zaman aşımı, çok istek, sunucu/kapı hatası. 4xx'in geri kalanı kalıcıdır. */
const transient = (status: number) => status === 0 || status === 401 || status === 408 || status === 429 || status >= 500;

class BookUploads {
  private items: BookUpload[] = [];
  private blobs = new Map<string, Blob>();
  private listeners = new Set<() => void>();
  private sentListeners = new Set<() => void>();
  private snap: BookUpload[] = [];
  private running = false;
  private backoff = 0;
  private timer: number | null = null;
  private readonly tab = `kitap:${uid()}`;

  constructor() {
    holdTabLock(this.tab);
    window.addEventListener('online', () => {
      this.backoff = 0;
      this.kick(0);
    });
    // Yüklenmemiş ve cihaza yazılamamış dosya varken sekme kapatılırsa tarayıcı uyarır (dosya yalnız bellekte).
    window.addEventListener('beforeunload', (e) => {
      if (this.items.some((i) => !i.stored && i.status !== 'failed')) e.preventDefault();
    });
    void this.adopt();
  }

  subscribe = (f: () => void) => {
    this.listeners.add(f);
    return () => {
      this.listeners.delete(f);
    };
  };
  get = () => this.snap;
  /** Bir dosya sunucuya ulaşınca (liste tazelensin diye). */
  onSent(f: () => void) {
    this.sentListeners.add(f);
    return () => {
      this.sentListeners.delete(f);
    };
  }
  private emit() {
    this.snap = this.items.map((i) => ({ ...i }));
    this.listeners.forEach((f) => f());
  }

  /** Kapanmış sekmelerden kalan yüklemeler devralınır (açık sekmenin kaydı kilitli, ona dokunulmaz). */
  private async adopt() {
    try {
      const held = await heldTabLocks();
      const recs = (await idbAll<Rec>(STORE_BOOK)).filter((r) => !held.has(r.tab));
      for (const r of recs) {
        if (this.items.some((i) => i.key === r.key)) continue;
        this.blobs.set(r.key, r.blob);
        this.items.push({ key: r.key, tab: this.tab, name: r.name, title: r.title, size: r.size, at: r.at, status: 'waiting', share: 0, error: null, stored: true, mode: r.mode });
        await idbPut(STORE_BOOK, { ...r, tab: this.tab } satisfies Rec);
      }
      if (recs.length) {
        this.emit();
        this.kick(0);
      }
    } catch {
      /* cihaz deposu yok: devralınacak bir şey de yok */
    }
  }

  /** Dosyalar sıraya girer. `title` yalnız tek dosyada kullanılır (toplu yüklemede ad dosyadan). `mode`: Kitap
   *  Eczanesi'nin arşiv kipi (cihaz deposunda da durur; sekme kapanıp açılınca aynı kiple gider). */
  async add(files: File[], title: string, mode?: BookReadMode) {
    const one = files.length === 1 ? title.trim() : '';
    for (const f of files) {
      const item: BookUpload = { key: uid(), tab: this.tab, name: f.name || 'kitap.pdf', title: one, size: f.size, at: Date.now(), status: 'waiting', share: 0, error: null, stored: false, mode };
      this.blobs.set(item.key, f);
      this.items.push(item);
      this.emit();
      try {
        await idbPut(STORE_BOOK, { key: item.key, tab: this.tab, name: item.name, title: item.title, size: item.size, at: item.at, mode, blob: f } satisfies Rec);
        item.stored = true;
      } catch {
        /* bellekte kalır; ekran «sekmeyi kapatmayın» der */
      }
      this.emit();
      this.kick(0);
    }
  }

  remove(key: string) {
    this.items = this.items.filter((i) => i.key !== key);
    this.blobs.delete(key);
    void idbDelete(STORE_BOOK, key).catch(() => undefined);
    this.emit();
  }

  private kick(ms: number) {
    if (this.timer) window.clearTimeout(this.timer);
    this.timer = window.setTimeout(() => {
      this.timer = null;
      void this.run();
    }, ms);
  }

  private async run() {
    if (this.running) return;
    this.running = true;
    try {
      for (;;) {
        const it = this.items.find((i) => i.status === 'waiting' || i.status === 'retrying');
        if (!it) break;
        const blob = this.blobs.get(it.key);
        if (!blob) {
          it.status = 'failed';
          it.error = 'Dosya bu cihazda bulunamadı; yeniden seçin.';
          this.emit();
          continue;
        }
        it.status = 'uploading';
        it.share = 0;
        it.error = null;
        this.emit();
        try {
          await bookReadApi.upload(new File([blob], it.name, { type: 'application/pdf' }), it.title, (share) => {
            it.share = share;
            this.emit();
          }, it.mode);
          this.backoff = 0;
          this.items = this.items.filter((x) => x.key !== it.key);
          this.blobs.delete(it.key);
          await idbDelete(STORE_BOOK, it.key).catch(() => undefined);
          this.emit();
          this.sentListeners.forEach((f) => f());
        } catch (e) {
          const status = e instanceof EngineAuthError ? 401 : ((e as { status?: number }).status ?? 0);
          if (!transient(status)) {
            // Kalıcı ret: satır bu oturumda cümlesiyle kalır; dosya cihaz deposundan silinir, yenilemede yeniden gönderilmez.
            it.status = 'failed';
            it.error = e instanceof Error ? e.message : 'Dosya yüklenemedi.';
            this.blobs.delete(it.key);
            await idbDelete(STORE_BOOK, it.key).catch(() => undefined);
            this.emit();
            continue;
          }
          // Bağlantı yok, oturum düştü, sunucu meşgul: dosya bekler, yeniden denenir.
          it.status = 'retrying';
          it.error = status === 401 ? 'Oturum gerekli; giriş yapınca yükleme sürer.' : 'Bağlantı bekleniyor; kendiliğinden yeniden denenecek.';
          this.emit();
          this.backoff = Math.min(60_000, this.backoff ? this.backoff * 2 : 1000);
          this.kick(this.backoff);
          break;
        }
      }
    } finally {
      this.running = false;
    }
  }
}

let instance: BookUploads | null = null;
/** Tek örnek: ilk kullanan (köşedeki gösterge, portal açılır açılmaz) kurar; kapanmış sekmeden kalanı devralır. */
export function bookUploads(): BookUploads {
  if (!instance) instance = new BookUploads();
  return instance;
}

export function useBookUploads() {
  const u = bookUploads();
  const items = useSyncExternalStore(u.subscribe, u.get);
  return { uploads: u, items };
}
