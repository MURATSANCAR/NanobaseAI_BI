/** Cihazdaki kalıcı depo (IndexedDB). İki depo: `sira` (gönderilmemiş plan düzenlemeleri) ve `foto`
 *  (yüklemesi bitmemiş fotoğraf dosyaları). Her çağrı hata verebilir (gizli pencere, kota, kapalı site
 *  verisi); çağıran try/catch ile localStorage'a ya da belleğe düşer. */

const DB_NAME = 'zeki-studyo-sayfa';
export const STORE_QUEUE = 'sira';
export const STORE_PHOTO = 'foto';

let dbPromise: Promise<IDBDatabase | null> | null = null;
function db(): Promise<IDBDatabase | null> {
  if (dbPromise) return dbPromise;
  dbPromise = new Promise((resolve) => {
    try {
      if (typeof indexedDB === 'undefined') return resolve(null);
      const req = indexedDB.open(DB_NAME, 2);
      req.onupgradeneeded = () => {
        for (const s of [STORE_QUEUE, STORE_PHOTO]) {
          if (!req.result.objectStoreNames.contains(s)) req.result.createObjectStore(s, { keyPath: 'key' });
        }
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => resolve(null);
      req.onblocked = () => resolve(null);
    } catch {
      resolve(null);
    }
  });
  return dbPromise;
}

export function idbTx<T>(store: string, mode: IDBTransactionMode, fn: (s: IDBObjectStore) => IDBRequest<T> | null): Promise<T | undefined> {
  return db().then((d) => new Promise<T | undefined>((resolve, reject) => {
    if (!d) return reject(new Error('idb yok'));
    try {
      const tx = d.transaction(store, mode);
      const req = fn(tx.objectStore(store));
      let out: T | undefined;
      if (req) req.onsuccess = () => { out = req.result; };
      tx.oncomplete = () => resolve(out);
      tx.onerror = () => reject(tx.error ?? new Error('idb yazılamadı'));
      tx.onabort = () => reject(tx.error ?? new Error('idb iptal'));
    } catch (e) {
      reject(e);
    }
  }));
}

export async function idbAll<T>(store: string): Promise<T[]> {
  return ((await idbTx<T[]>(store, 'readonly', (s) => s.getAll() as IDBRequest<T[]>)) ?? []);
}
export async function idbPut(store: string, value: unknown) {
  await idbTx(store, 'readwrite', (s) => s.put(value));
}
export async function idbDelete(store: string, key: string) {
  await idbTx(store, 'readwrite', (s) => s.delete(key));
}

// ------------------------------------------------------------------ sekme kilidi (Web Locks)
/** Açık sekme kendi kaydını kilitle tutar; sekme kapanınca kilit düşer ve kaydı başka sekme devralabilir.
 *  Tarayıcıda Web Locks yoksa kilit tutulamaz; o durumda bütün kayıtlar devralınabilir sayılır. */
type LockManagerLike = {
  request: (name: string, cb: () => Promise<void>) => Promise<void>;
  query: () => Promise<{ held?: { name?: string }[] }>;
};
const locks = (): LockManagerLike | null =>
  (typeof navigator !== 'undefined' && (navigator as unknown as { locks?: LockManagerLike }).locks) || null;
const LOCK = 'zeki-studyo-sekme:';

export function holdTabLock(key: string): () => void {
  let release: () => void = () => undefined;
  const lm = locks();
  if (lm) void lm.request(LOCK + key, () => new Promise<void>((res) => { release = res; })).catch(() => undefined);
  return () => release();
}

export async function heldTabLocks(): Promise<Set<string>> {
  const lm = locks();
  if (!lm) return new Set();
  try {
    const q = await lm.query();
    return new Set((q.held ?? []).map((h) => (h.name ?? '').replace(LOCK, '')));
  } catch {
    return new Set();
  }
}
