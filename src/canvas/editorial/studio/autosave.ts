import { useEffect, useMemo, useSyncExternalStore } from 'react';
import {
  EngineAuthError, StudioPlanError, studioPlanApi,
  type Plan, type PlanLayout, type PlanPage, type PlanPalette,
} from '../../engine';
import { STORE_QUEUE, heldTabLocks, holdTabLock, idbAll, idbDelete, idbPut } from './deviceStore';
import { applyLayout, mergeOrder, mergePage, mergePalette, same, uid } from './planModel';

/** Sayfa planının otomatik kaydı (sözleşme: «yapılanlar asla kaybolmasın»).
 *
 *  Her düzenleme bir işlem (op) olarak ÖNCE cihazdaki kalıcı depoya (IndexedDB; olmazsa localStorage)
 *  yazılır, sonra sıraya girer; 700 ms sessizlikten sonra sırayla sunucuya gider. Ekrandaki plan her
 *  zaman `sunucunun son bilinen planı + bekleyen işlemler`dir; böylece sunucu yanıtı gelince sayfa
 *  kendiliğinden sunucunun hâline (taşma, uyarı) döner.
 *
 *  - Ağ yoksa / sunucu 5xx ya da meşgulse: sıra cihazda bekler, artan aralıkla (1→30 sn) yeniden denenir;
 *    deneme sayısında tavan yoktur. Bağlantı gelince (`online`) hemen denenir.
 *  - Sayfa yenilenirse: açılışta cihazdaki sıra okunur ve sunucuya yeniden uygulanır. Başka sekmenin
 *    bıraktığı sıra (sekmesi kapanmışsa) devralınır; açık sekmenin sırasına dokunulmaz (Web Locks).
 *  - 409 STALE ya da sunucuda başkasının değişikliği: sunucunun son planı alınır, bekleyen işlemler sayfa
 *    kimliğiyle ve alan alan üç yollu birleştirilir. Aynı alanı iki taraf da değiştirdiyse kullanıcıya
 *    sorulur («benimkini koru / onunkini al»). Hiçbir işlem sessizce atılmaz; kabul edilmeyen işlem sırada
 *    kalır ve kullanıcı «tekrar dene / bu değişikliği bırak» der. */

export type Op =
  | { seq: number; t: number; kind: 'page'; pid: string; page: PlanPage; base: PlanPage | null }
  | { seq: number; t: number; kind: 'palette'; palette: PlanPalette; base: PlanPalette | null }
  | { seq: number; t: number; kind: 'add'; tmp: string; after: string | null; layout: PlanLayout }
  | { seq: number; t: number; kind: 'delete'; pid: string }
  | { seq: number; t: number; kind: 'order'; ids: string[] };

export type Conflict =
  | { kind: 'page'; seq: number; pid: string; mine: PlanPage; theirs: PlanPage | null; index: number }
  | { kind: 'palette'; seq: number; mine: PlanPalette; theirs: PlanPalette };

export type SyncStatus = 'loading' | 'no-plan' | 'saved' | 'saving' | 'offline' | 'busy' | 'error' | 'conflict' | 'auth';

export type SyncState = {
  status: SyncStatus;
  plan: Plan | null;          // ekrandaki plan (sunucu + bekleyen)
  server: Plan | null;        // sunucunun son bilinen planı
  pending: number;
  lastSaved: number | null;
  error: string | null;
  conflict: Conflict | null;
  storage: 'idb' | 'ls' | 'memory';
  canUndo: boolean;
  canRedo: boolean;
  /** Geçici sayfa kimliği sunucu kimliğine döndüğünde (seçim buna göre güncellenir). */
  remap: Record<string, string>;
};

// ------------------------------------------------------------------ cihazdaki kalıcı depo
type Stored = { key: string; job: string; ops: Op[]; savedAt: number };
const LS_PREFIX = 'zeki-studyo-sira:';

async function writeStored(rec: Stored): Promise<'idb' | 'ls' | 'memory'> {
  const empty = rec.ops.length === 0;
  let where: 'idb' | 'ls' | 'memory' = 'memory';
  try {
    await (empty ? idbDelete(STORE_QUEUE, rec.key) : idbPut(STORE_QUEUE, rec));
    where = 'idb';
  } catch { /* localStorage'a düşülür */ }
  try {
    // localStorage ikinci kopya: IndexedDB kapalı/bozuksa tek kopya odur.
    if (empty) localStorage.removeItem(LS_PREFIX + rec.key);
    else if (where !== 'idb') localStorage.setItem(LS_PREFIX + rec.key, JSON.stringify(rec));
    else localStorage.removeItem(LS_PREFIX + rec.key);
    if (where === 'memory' && !empty) where = 'ls';
  } catch { /* kota ya da gizli pencere */ }
  return where;
}

async function readAll(job: string): Promise<Stored[]> {
  const out = new Map<string, Stored>();
  try {
    const all = await idbAll<Stored>(STORE_QUEUE);
    for (const r of all) if (r.job === job) out.set(r.key, r);
  } catch { /* yok */ }
  try {
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i);
      if (!k?.startsWith(LS_PREFIX)) continue;
      const r = JSON.parse(localStorage.getItem(k) || 'null') as Stored | null;
      if (r?.job === job && (!out.has(r.key) || out.get(r.key)!.savedAt < r.savedAt)) out.set(r.key, r);
    }
  } catch { /* yok */ }
  return [...out.values()].sort((a, b) => a.savedAt - b.savedAt);
}

async function removeStored(key: string) {
  try { await idbDelete(STORE_QUEUE, key); } catch { /* yok */ }
  try { localStorage.removeItem(LS_PREFIX + key); } catch { /* yok */ }
}

// ------------------------------------------------------------------ yardımcılar
/** Plan hatası ya da oturum hatası değilse bağlantı sorunudur (ağ yok, zaman aşımı, 5xx'in gövdesiz hâli). */
const isNetwork = (e: unknown) => !(e instanceof StudioPlanError) && !(e instanceof EngineAuthError);

function skeleton(id: string, layout: PlanLayout, d: Plan['page']): PlanPage {
  const empty: PlanPage = { id, chapter: null, layout, art: null, text: null, bubbles: [], figures: [], texts: [], overflow: false };
  return applyLayout(empty, layout, d);
}

/** Sunucu planı + bekleyen işlemler = ekrandaki plan. */
export function applyOps(server: Plan, ops: Op[]): Plan {
  let pages = server.pages.slice();
  let palette = server.palette;
  for (const op of ops) {
    if (op.kind === 'page') {
      const i = pages.findIndex((p) => p.id === op.pid);
      if (i >= 0) pages[i] = op.page;
    } else if (op.kind === 'palette') {
      palette = op.palette;
    } else if (op.kind === 'add') {
      const at = op.after ? pages.findIndex((p) => p.id === op.after) + 1 : 0;
      pages.splice(Math.max(0, at), 0, skeleton(op.tmp, op.layout, server.page));
    } else if (op.kind === 'delete') {
      pages = pages.filter((p) => p.id !== op.pid);
    } else if (op.kind === 'order') {
      const by = new Map(pages.map((p) => [p.id, p]));
      pages = mergeOrder(op.ids, pages.map((p) => p.id)).map((id) => by.get(id)!);
    }
  }
  return { ...server, pages, palette };
}

type Snapshot = { pages: Record<string, PlanPage>; palette: PlanPalette; order: string[] };

// ------------------------------------------------------------------ eşitleyici
export class PlanSync {
  private server: Plan | null = null;
  private ops: Op[] = [];
  private seq = 1;
  private readonly tabKey: string;
  private status: SyncStatus = 'loading';
  private lastSaved: number | null = null;
  private error: string | null = null;
  private conflicts: Conflict[] = [];
  private storage: 'idb' | 'ls' | 'memory' = 'idb';
  private inflight = false;
  private timer: number | null = null;
  private backoff = 0;
  private remap: Record<string, string> = {};
  private undo: Snapshot[] = [];
  private redo: Snapshot[] = [];
  private undoKey = '';
  private undoAt = 0;
  private listeners = new Set<() => void>();
  private snapshot: SyncState;
  private disposed = false;
  private releaseLock: (() => void) | null = null;
  private persistChain: Promise<unknown> = Promise.resolve();

  constructor(readonly job: string) {
    this.tabKey = `${job}:${uid('t')}`;
    this.snapshot = this.build();
  }

  // ---------------------------------------------------------------- abonelik
  subscribe = (fn: () => void) => { this.listeners.add(fn); return () => { this.listeners.delete(fn); }; };
  get = () => this.snapshot;
  private emit() {
    this.snapshot = this.build();
    this.listeners.forEach((f) => f());
  }
  private build(): SyncState {
    const pending = this.ops.length;
    let status = this.status;
    if (status === 'saved' && (pending || this.inflight)) status = 'saving';
    return {
      status: this.conflicts.length ? 'conflict' : status,
      plan: this.server ? applyOps(this.server, this.ops) : null,
      server: this.server,
      pending,
      lastSaved: this.lastSaved,
      error: this.error,
      conflict: this.conflicts[0] ?? null,
      storage: this.storage,
      canUndo: this.undo.length > 0,
      canRedo: this.redo.length > 0,
      remap: { ...this.remap },
    };
  }

  // ---------------------------------------------------------------- yaşam döngüsü
  async init() {
    // Sekme açık kaldıkça kilit tutulur; kapanınca kilit düşer, sırası başka sekmece devralınabilir.
    this.releaseLock = holdTabLock(this.tabKey);
    window.addEventListener('online', this.onOnline);
    await this.adoptOrphans();
    await this.reload();
  }

  dispose() {
    this.disposed = true;
    if (this.timer) window.clearTimeout(this.timer);
    window.removeEventListener('online', this.onOnline);
    this.releaseLock?.();
    this.listeners.clear();
  }

  private onOnline = () => { this.backoff = 0; this.schedule(0); };

  private async adoptOrphans() {
    const recs = await readAll(this.job);
    if (!recs.length) return;
    const held = await heldTabLocks();
    for (const r of recs) {
      if (r.key === this.tabKey || held.has(r.key)) continue;
      for (const op of r.ops) this.ops.push({ ...op, seq: this.seq++ } as Op);
      await removeStored(r.key);
    }
    if (this.ops.length) await this.persist();
  }

  /** Sunucudaki planı okur; bekleyen işlemleri onun üstüne birleştirir. */
  async reload() {
    try {
      const s = await studioPlanApi.get(this.job);
      this.rebase(s);
      if (this.status === 'loading' || this.status === 'no-plan') this.status = 'saved';
      this.emit();
      if (this.ops.length) this.schedule(0);
    } catch (e) {
      if (e instanceof StudioPlanError && e.status === 404 && (e.code === 'NO_PLAN' || !this.server)) {
        this.status = 'no-plan';
        this.error = null;
      } else if (e instanceof EngineAuthError) {
        this.status = 'auth';
      } else {
        this.status = this.server ? 'offline' : 'error';
        this.error = e instanceof Error ? e.message : 'Sayfa planı okunamadı.';
      }
      this.emit();
      if (this.status === 'offline' || (this.status === 'error' && !(e instanceof StudioPlanError))) this.retryLater();
    }
  }

  async freeze() {
    const s = await studioPlanApi.freeze(this.job);
    this.rebase(s);
    this.status = 'saved';
    this.error = null;
    this.emit();
  }

  // ---------------------------------------------------------------- düzenleme
  private pushUndo(key: string) {
    const now = Date.now();
    // Aynı ögenin art arda (ok tuşu, yazma) değişiklikleri tek geri alma adımıdır.
    if (key && key === this.undoKey && now - this.undoAt < 900) { this.undoAt = now; return; }
    const cur = this.snapshot.plan;
    if (!cur) return;
    this.undo.push({ pages: Object.fromEntries(cur.pages.map((p) => [p.id, p])), palette: cur.palette, order: cur.pages.map((p) => p.id) });
    this.redo = [];
    this.undoKey = key;
    this.undoAt = now;
  }

  private enqueue(op: Op, delay = 700) {
    this.ops.push(op);
    this.error = null;
    if (this.status === 'error') this.status = 'saved';
    this.emit();
    void this.persist().then(() => this.schedule(delay));
  }

  setPage(page: PlanPage, undoKey = '') {
    if (!this.server) return;
    this.pushUndo(undoKey || `page:${page.id}:${Date.now()}`);
    this.writePage(page);
  }

  private writePage(page: PlanPage) {
    if (!this.server) return;
    const last = [...this.ops].reverse().find((o) => o.kind === 'page' && o.pid === page.id) as Extract<Op, { kind: 'page' }> | undefined;
    const lastIdx = last ? this.ops.lastIndexOf(last) : -1;
    const tail = lastIdx >= 0 ? this.ops.slice(lastIdx + 1) : [];
    const sending = this.inflight && lastIdx === 0;
    // Aynı sayfanın gönderilmemiş son işlemi, arkasında yapısal işlem yoksa yerinde güncellenir.
    if (last && !sending && tail.every((o) => o.kind === 'page' || o.kind === 'palette')) {
      this.ops[lastIdx] = { ...last, page, t: Date.now() };
      this.emit();
      void this.persist().then(() => this.schedule(700));
      return;
    }
    const base = last ? null : this.server.pages.find((p) => p.id === page.id) ?? null;
    this.enqueue({ seq: this.seq++, t: Date.now(), kind: 'page', pid: page.id, page, base });
  }

  setPalette(palette: PlanPalette, undoKey = '') {
    if (!this.server) return;
    this.pushUndo(undoKey || `palette:${Date.now()}`);
    const lastIdx = this.ops.map((o) => o.kind).lastIndexOf('palette');
    if (lastIdx > 0 || (lastIdx === 0 && !this.inflight)) {
      const last = this.ops[lastIdx] as Extract<Op, { kind: 'palette' }>;
      this.ops[lastIdx] = { ...last, palette, t: Date.now() };
      this.emit();
      void this.persist().then(() => this.schedule(700));
      return;
    }
    this.enqueue({ seq: this.seq++, t: Date.now(), kind: 'palette', palette, base: lastIdx === 0 ? null : this.server.palette });
  }

  /** Yeni sayfa geçici kimlikle hemen görünür; sunucu kimlik verince seçim ve sıra ona döner. */
  addPage(after: string | null, layout: PlanLayout = 'text-only'): string {
    const tmp = uid('tmp_');
    this.pushUndo('');
    this.enqueue({ seq: this.seq++, t: Date.now(), kind: 'add', tmp, after, layout }, 0);
    return tmp;
  }

  deletePage(pid: string) {
    this.pushUndo('');
    const add = this.ops.find((o) => o.kind === 'add' && o.tmp === pid);
    if (add && !(this.inflight && this.ops[0] === add)) {
      // Henüz sunucuya gitmemiş sayfa: ekleme ve düzenlemeleri kullanıcının silme kararıyla birlikte düşer.
      this.ops = this.ops.filter((o) => !((o.kind === 'add' && o.tmp === pid) || (o.kind === 'page' && o.pid === pid)));
      this.emit();
      void this.persist();
      return;
    }
    this.enqueue({ seq: this.seq++, t: Date.now(), kind: 'delete', pid }, 0);
  }

  setOrder(ids: string[]) {
    this.pushUndo('');
    this.enqueue({ seq: this.seq++, t: Date.now(), kind: 'order', ids }, 300);
  }

  undoStep() { this.step(this.undo, this.redo); }
  redoStep() { this.step(this.redo, this.undo); }

  private step(from: Snapshot[], to: Snapshot[]) {
    const snap = from.pop();
    const cur = this.snapshot.plan;
    if (!snap || !cur) return;
    to.push({ pages: Object.fromEntries(cur.pages.map((p) => [p.id, p])), palette: cur.palette, order: cur.pages.map((p) => p.id) });
    this.undoKey = '';
    // Sayfa ekleme/silme geri alınmaz (sürüm geçmişi bunun içindir); içerik, palet ve sıra geri alınır.
    for (const p of cur.pages) {
      const old = snap.pages[p.id];
      if (old && !same(old, p)) this.writePage(old);
    }
    if (!same(snap.palette, cur.palette)) {
      const idx = this.ops.map((o) => o.kind).lastIndexOf('palette');
      if (idx > 0 || (idx === 0 && !this.inflight)) this.ops[idx] = { ...(this.ops[idx] as Extract<Op, { kind: 'palette' }>), palette: snap.palette };
      else this.ops.push({ seq: this.seq++, t: Date.now(), kind: 'palette', palette: snap.palette, base: idx === 0 ? null : this.server!.palette });
    }
    const order = mergeOrder(snap.order, cur.pages.map((p) => p.id));
    if (!same(order, cur.pages.map((p) => p.id))) this.ops.push({ seq: this.seq++, t: Date.now(), kind: 'order', ids: order });
    this.emit();
    void this.persist().then(() => this.schedule(700));
  }

  // ---------------------------------------------------------------- çakışma
  resolve(choice: 'mine' | 'theirs') {
    const c = this.conflicts.shift();
    if (!c || !this.server) return;
    const i = this.ops.findIndex((o) => o.seq === c.seq);
    if (i < 0) { this.emit(); return; }
    const op = this.ops[i];
    if (c.kind === 'palette' && op.kind === 'palette') {
      if (choice === 'mine') this.ops[i] = { ...op, base: c.theirs };
      else this.ops.splice(i, 1);
    } else if (c.kind === 'page' && op.kind === 'page') {
      if (choice === 'theirs') {
        this.ops.splice(i, 1);
      } else if (c.theirs) {
        this.ops[i] = { ...op, base: c.theirs };
      } else {
        // Sayfa sunucuda silinmiş: benimki yeni sayfa olarak eski komşusunun arkasına eklenir.
        const tmp = uid('tmp_');
        const order = this.snapshot.plan?.pages.map((p) => p.id) ?? [];
        const at = order.indexOf(op.pid);
        const live = new Set(this.server.pages.map((p) => p.id));
        const after = order.slice(0, Math.max(0, at)).reverse().find((x) => live.has(x)) ?? null;
        this.ops.splice(i, 1,
          { seq: this.seq++, t: Date.now(), kind: 'add', tmp, after, layout: op.page.layout === 'custom' ? 'text-only' : op.page.layout },
          { seq: this.seq++, t: Date.now(), kind: 'page', pid: tmp, page: { ...op.page, id: tmp }, base: null });
        this.remap[op.pid] = tmp;
      }
    }
    this.emit();
    void this.persist().then(() => { if (!this.conflicts.length) this.schedule(0); });
  }

  /** Kabul edilmeyen (400/404) işlem için: yeniden dene ya da kullanıcının kararıyla bırak. */
  retry() { this.error = null; this.status = 'saved'; this.backoff = 0; this.emit(); this.schedule(0); }
  discardHead() {
    this.ops.shift();
    this.error = null;
    this.status = 'saved';
    this.emit();
    void this.persist().then(() => this.schedule(0));
  }

  /** Sunucu planına bekleyen işlemleri birleştirir; çözülemeyenleri `conflicts`e koyar. */
  private rebase(s: Plan) {
    const old = this.server;
    this.conflicts = [];
    for (const op of this.ops) {
      if (op.kind === 'page') {
        const theirs = s.pages.find((p) => p.id === op.pid) ?? null;
        const isTmp = this.ops.some((o) => o.kind === 'add' && o.tmp === op.pid);
        if (isTmp) continue;
        const base = op.base ?? old?.pages.find((p) => p.id === op.pid) ?? null;
        if (!theirs) {
          this.conflicts.push({ kind: 'page', seq: op.seq, pid: op.pid, mine: op.page, theirs: null, index: -1 });
          continue;
        }
        if (!base || same(base, theirs)) { op.base = theirs; continue; }
        const m = mergePage(base, op.page, theirs);
        if (m.conflict) {
          this.conflicts.push({ kind: 'page', seq: op.seq, pid: op.pid, mine: op.page, theirs, index: s.pages.indexOf(theirs) });
        } else {
          op.page = m.page;
          op.base = theirs;
        }
      } else if (op.kind === 'palette') {
        const base = op.base ?? old?.palette ?? null;
        if (!base || same(base, s.palette)) { op.base = s.palette; continue; }
        const m = mergePalette(base, op.palette, s.palette);
        if (m.conflict) this.conflicts.push({ kind: 'palette', seq: op.seq, mine: op.palette, theirs: s.palette });
        else { op.palette = m.palette; op.base = s.palette; }
      }
    }
    // Sunucuda zaten olmayan sayfanın silinmesi tamamlanmış sayılır.
    this.ops = this.ops.filter((o) => !(o.kind === 'delete' && !s.pages.some((p) => p.id === o.pid)
      && !this.ops.some((a) => a.kind === 'add' && a.tmp === o.pid)));
    this.server = s;
    void this.persist();
  }

  // ---------------------------------------------------------------- gönderim
  private schedule(ms: number) {
    if (this.disposed) return;
    if (this.timer) window.clearTimeout(this.timer);
    this.timer = window.setTimeout(() => { this.timer = null; void this.flush(); }, ms);
  }

  private retryLater() {
    this.backoff = Math.min(30_000, this.backoff ? this.backoff * 2 : 1000);
    this.schedule(this.backoff);
  }

  private persist(): Promise<unknown> {
    // Yazımlar sıralı: eski anlık görüntü yenisinin üstüne yazılmaz.
    this.persistChain = this.persistChain.then(async () => {
      const where = await writeStored({ key: this.tabKey, job: this.job, ops: this.ops, savedAt: Date.now() });
      if (this.ops.length && where !== this.storage) { this.storage = where; this.emit(); }
    });
    return this.persistChain;
  }

  /** Bekleyen işlem var mı (sayfadan çıkarken uyarı için; cihaz deposu yoksa gerekir). */
  unsafeToLeave() { return this.ops.length > 0 && this.storage === 'memory'; }

  /** Sıradakilerin hepsi gidene kadar bekler (sürüme dönme, bölme gibi çevrimiçi işlemlerden önce). */
  async drain(): Promise<boolean> {
    for (let i = 0; this.ops.length && !this.conflicts.length; i++) {
      if (!this.inflight) await this.flush();
      else await new Promise((r) => window.setTimeout(r, 150));
      if (this.status === 'offline' || this.status === 'error' || this.status === 'auth' || this.status === 'busy') return false;
    }
    return this.ops.length === 0;
  }

  /** Sunucu planını baştan okur (örn. figür işi bitince); bekleyenler üstüne birleştirilir. */
  async refresh() {
    if (this.inflight) return;
    try {
      const s = await studioPlanApi.get(this.job);
      if (this.inflight) return;
      this.rebase(s);
      this.emit();
      if (this.ops.length && !this.conflicts.length) this.schedule(0);
    } catch { /* bağlantı yoksa sıradaki gönderim zaten dener */ }
  }

  /** Sürüme dönüldüğünde tarayıcı içi geri al/yinele geçmişi anlamını yitirir. */
  clearUndo() { this.undo = []; this.redo = []; this.undoKey = ''; this.emit(); }

  /** Sunucudan dönen tam planı alır (sürüme dönme, figür silme sonrası). */
  adopt(s: Plan) {
    this.rebase(s);
    this.lastSaved = Date.now();
    this.emit();
  }

  private async flush(): Promise<void> {
    if (this.inflight || this.disposed || !this.server || this.conflicts.length) return;
    this.inflight = true;
    this.emit();
    try {
      while (this.ops.length && !this.conflicts.length && !this.disposed) {
        const op = this.ops[0];
        // Taban denetimi: sayfa yenilendikten sonra yeniden oynatılan işlem, arada sunucuda değişmiş
        // sayfanın üstüne körlemesine yazılmaz.
        if (op.kind === 'page' && op.base) {
          const cur = this.server.pages.find((p) => p.id === op.pid);
          if (!cur || !same(cur, op.base)) {
            const s = await studioPlanApi.get(this.job);
            this.rebase(s);
            this.emit();
            continue;
          }
        }
        await this.send(op);
        this.ops.shift();
        this.backoff = 0;
        this.lastSaved = Date.now();
        this.status = 'saved';
        this.error = null;
        await this.persist();
        this.emit();
      }
    } catch (e) {
      if (e instanceof StudioPlanError && e.status === 409 && e.code === 'STALE') {
        try {
          const s = await studioPlanApi.get(this.job);
          this.rebase(s);
          this.status = 'saved';
          this.inflight = false;
          this.emit();
          if (!this.conflicts.length) this.schedule(0);
          return;
        } catch {
          this.status = 'offline';
          this.retryLater();
        }
      } else if (e instanceof StudioPlanError && e.status === 409) {
        this.status = 'busy';          // üretim sürüyor: sıra bekler
        this.error = e.message;
        this.retryLater();
      } else if (e instanceof StudioPlanError && e.status === 404 && this.ops[0]?.kind === 'page') {
        // Sayfa sunucuda yok: kullanıcıya sorulur (benimki yeni sayfa olur / bırak).
        const op = this.ops[0] as Extract<Op, { kind: 'page' }>;
        this.conflicts.push({ kind: 'page', seq: op.seq, pid: op.pid, mine: op.page, theirs: null, index: -1 });
      } else if (e instanceof StudioPlanError && e.status >= 400 && e.status < 500) {
        this.status = 'error';         // sunucu kabul etmedi; işlem sırada kalır, kullanıcı karar verir
        this.error = e.message;
      } else if (e instanceof EngineAuthError) {
        this.status = 'auth';
        this.error = 'Oturum gerekli; giriş yapınca bekleyen değişiklikler gönderilir.';
        this.retryLater();
      } else if (isNetwork(e) || (e instanceof StudioPlanError && e.status >= 500)) {
        this.status = 'offline';      // ağ yok ya da sunucu yanıt vermiyor: sıra cihazda bekler
        this.retryLater();
      }
    } finally {
      this.inflight = false;
      this.emit();
    }
  }

  private realId(id: string) { return this.remap[id] ?? id; }

  private async send(op: Op) {
    const s = this.server!;
    if (op.kind === 'page') {
      const r = await studioPlanApi.putPage(this.job, s.rev, op.page);
      const pages = s.pages.map((p) => (p.id === op.pid ? r.page ?? op.page : p));
      this.server = { ...s, pages, rev: r.rev, warnings: r.warnings ?? s.warnings };
      for (const o of this.ops) if (o !== op && o.kind === 'page' && o.pid === op.pid && !o.base) o.base = r.page ?? op.page;
    } else if (op.kind === 'palette') {
      const r = await studioPlanApi.palette(this.job, s.rev, op.palette);
      this.server = r;
      for (const o of this.ops) if (o !== op && o.kind === 'palette' && !o.base) o.base = r.palette;
    } else if (op.kind === 'delete') {
      const r = await studioPlanApi.deletePage(this.job, s.rev, op.pid);
      this.server = { ...s, rev: r.rev, pages: s.pages.filter((p) => p.id !== op.pid), warnings: r.warnings ?? s.warnings };
    } else if (op.kind === 'order') {
      const ids = mergeOrder(op.ids.map((x) => this.realId(x)), s.pages.map((p) => p.id));
      this.server = await studioPlanApi.order(this.job, s.rev, ids);
    } else if (op.kind === 'add') {
      const before = new Set(s.pages.map((p) => p.id));
      const after = op.after ? this.realId(op.after) : null;
      const r = await studioPlanApi.addPage(this.job, s.rev, after, op.layout);
      let next: Plan;
      let newId: string | undefined;
      if (Array.isArray(r.pages)) {
        next = { ...s, ...(r as Plan) };
        newId = r.page?.id ?? next.pages.find((p) => !before.has(p.id))?.id;
      } else if (r.page) {
        const pages = s.pages.slice();
        const at = after ? pages.findIndex((p) => p.id === after) + 1 : 0;
        pages.splice(Math.max(0, at), 0, r.page);
        next = { ...s, pages, rev: r.rev, warnings: r.warnings ?? s.warnings };
        newId = r.page.id;
      } else {
        next = await studioPlanApi.get(this.job);
        newId = next.pages.find((p) => !before.has(p.id))?.id;
      }
      this.server = next;
      if (newId) this.remapId(op.tmp, newId);
    }
  }

  private remapId(tmp: string, real: string) {
    this.remap[tmp] = real;
    for (const k of Object.keys(this.remap)) if (this.remap[k] === tmp) this.remap[k] = real;
    this.ops = this.ops.map((o) => {
      if (o.kind === 'page' && o.pid === tmp) {
        return { ...o, pid: real, page: { ...o.page, id: real }, base: o.base ?? this.server!.pages.find((p) => p.id === real) ?? null };
      }
      if (o.kind === 'delete' && o.pid === tmp) return { ...o, pid: real };
      if (o.kind === 'add' && o.after === tmp) return { ...o, after: real };
      if (o.kind === 'order') return { ...o, ids: o.ids.map((x) => (x === tmp ? real : x)) };
      return o;
    });
    for (const u of [...this.undo, ...this.redo]) {
      if (u.pages[tmp]) { u.pages[real] = { ...u.pages[tmp], id: real }; delete u.pages[tmp]; }
      u.order = u.order.map((x) => (x === tmp ? real : x));
    }
  }
}

/** Sekme başına iş başına tek eşitleyici. Ekrandan çıkılınca da yaşar: bekleyen işlemler başka ekrana
 *  geçildiğinde de gönderilmeye devam eder; ekrana dönülünce sunucunun son hâli yeniden okunur. */
const syncs = new Map<string, PlanSync>();
function planSync(job: string): PlanSync {
  let s = syncs.get(job);
  if (!s) {
    s = new PlanSync(job);
    syncs.set(job, s);
    void s.init();
  }
  return s;
}

/** Ekranın kancası; sayfadan çıkarken cihaz deposu hiç yazılamıyorsa (bellekte kaldıysa) uyarır. */
export function usePlanSync(job: string) {
  const sync = useMemo(() => planSync(job), [job]);
  useEffect(() => {
    if (sync.get().status !== 'loading') void sync.refresh();
    const leave = (e: BeforeUnloadEvent) => {
      if (sync.unsafeToLeave()) { e.preventDefault(); e.returnValue = ''; }
    };
    window.addEventListener('beforeunload', leave);
    return () => window.removeEventListener('beforeunload', leave);
  }, [sync]);
  const state = useSyncExternalStore(sync.subscribe, sync.get);
  return { sync, state };
}
