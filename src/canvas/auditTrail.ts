import { ENGINE_BASE } from './engine';

/**
 * Denetim izinin ekran katmanı (köprü: `backend/semantic_bridge/audit_trail.py`).
 *
 * Kişinin açtığı sayfa, bastığı düğme/bağlantı/sekme/menü ve seçtiği seçenek etiketiyle toplanır, birkaç saniyede bir
 * toplu gönderilir; sayfa kapanırken `sendBeacon` ile. Yazılan serbest metin (alan içeriği) alınmaz: gönderilen her
 * metin — promt, form — köprünün istek kaydında gövdesiyle durur. Parola alanı hiçbir şekilde okunmaz.
 *
 * Kişi sunucuda oturumdan belirlenir; buradan ad gönderilmez. Bir öğeyi kayıttan çıkarmak için `data-audit-ignore`.
 */

type UiEvent = {
  type: 'view' | 'click' | 'change' | 'leave';
  t: number;
  page: string;
  label?: string;
  el?: string;
  value?: string;
  checked?: boolean;
  href?: string;
  section?: string;
};

const URL_ = `${ENGINE_BASE}/api/v1/audit/ui`;
const FLUSH_MS = 4000;

let queue: UiEvent[] = [];
let timer: number | undefined;
let lastPage = '';
let started = false;

const page = () => location.pathname + location.search;
const squash = (s: string | null | undefined) => (s ?? '').replace(/\s+/g, ' ').trim();

function push(e: Omit<UiEvent, 't' | 'page'> & { page?: string }) {
  queue.push({ t: Date.now(), page: e.page ?? page(), ...e });
  if (timer === undefined) timer = window.setTimeout(flush, FLUSH_MS);
}

function flush(beacon = false) {
  if (timer !== undefined) {
    window.clearTimeout(timer);
    timer = undefined;
  }
  if (!queue.length) return;
  const events = queue;
  queue = [];
  const body = JSON.stringify({ events });
  if (beacon && navigator.sendBeacon) {
    if (navigator.sendBeacon(URL_, new Blob([body], { type: 'application/json' }))) return;
  }
  fetch(URL_, { method: 'POST', credentials: 'include', keepalive: true, headers: { 'Content-Type': 'application/json' }, body }).catch(() => {
    // Ağ yoksa olaylar bir sonraki gönderimde denenir; oturum yoksa (401) bırakılır.
    queue = events.concat(queue);
  });
}

function view() {
  const p = page();
  if (p === lastPage) return;
  lastPage = p;
  push({ type: 'view', page: p, label: document.title || undefined });
}

/** Öğenin ekranda okunan adı: erişilebilir ad → başlık → görünen metin → simge düğmesinde ipucu. */
function nameOf(el: Element): string {
  const aria = el.getAttribute('aria-label');
  if (aria) return squash(aria);
  const labelled = el.getAttribute('aria-labelledby');
  if (labelled) {
    const t = squash(labelled.split(/\s+/).map((id) => document.getElementById(id)?.textContent).join(' '));
    if (t) return t;
  }
  const text = squash((el as HTMLElement).innerText ?? el.textContent);
  if (text) return text;
  const title = el.getAttribute('title');
  if (title) return squash(title);
  const img = el.querySelector('img[alt], svg[aria-label]');
  return squash(img?.getAttribute('alt') ?? img?.getAttribute('aria-label') ?? '');
}

/** Olayın geçtiği bölüm: en yakın başlıklı bölge (aynı adlı düğmeler — «Sil» — hangi kartta basıldı). */
function sectionOf(el: Element): string | undefined {
  const region = el.closest('[aria-label]:not(button):not(a), section, [role="dialog"], form, li, tr');
  if (!region) return undefined;
  const own = region.getAttribute('aria-label');
  if (own && region !== el) return squash(own);
  const h = region.querySelector('h1, h2, h3, h4, [role="heading"], legend, caption, td, th');
  const t = squash(h?.textContent);
  return t || undefined;
}

const CLICKABLE = 'button, a[href], [role="button"], [role="menuitem"], [role="menuitemcheckbox"], [role="menuitemradio"], [role="tab"], [role="option"], [role="switch"], [role="checkbox"], [role="link"], summary';

function onClick(ev: MouseEvent) {
  const target = ev.target as Element | null;
  const el = target?.closest?.(CLICKABLE);
  if (!el || el.closest('[data-audit-ignore]')) return;
  const label = nameOf(el);
  const href = el instanceof HTMLAnchorElement ? el.getAttribute('href') ?? undefined : undefined;
  const pressed = el.getAttribute('aria-pressed') ?? el.getAttribute('aria-checked') ?? el.getAttribute('aria-selected');
  push({
    type: 'click',
    label: label || undefined,
    el: el.getAttribute('role') ?? el.tagName.toLowerCase(),
    href,
    section: sectionOf(el),
    ...(pressed != null ? { value: pressed } : {}),
  });
}

function onChange(ev: Event) {
  const el = ev.target as HTMLInputElement | HTMLSelectElement | null;
  if (!el || el.closest('[data-audit-ignore]')) return;
  const labelText =
    squash(el.getAttribute('aria-label')) ||
    squash((el as HTMLInputElement).labels?.[0]?.textContent) ||
    squash(el.getAttribute('name')) ||
    squash(el.getAttribute('placeholder'));
  if (el instanceof HTMLSelectElement) {
    const chosen = Array.from(el.selectedOptions).map((o) => squash(o.textContent)).join(', ');
    push({ type: 'change', el: 'select', label: labelText || undefined, value: chosen, section: sectionOf(el) });
    return;
  }
  if (el instanceof HTMLInputElement) {
    if (el.type === 'checkbox' || el.type === 'radio') {
      push({ type: 'change', el: el.type, label: labelText || squash(el.value) || undefined, checked: el.checked, section: sectionOf(el) });
    } else if (el.type === 'file') {
      push({ type: 'change', el: 'file', label: labelText || undefined, value: Array.from(el.files ?? []).map((f) => `${f.name} (${f.size} bayt)`).join(', '), section: sectionOf(el) });
    } else if (el.type === 'date' || el.type === 'month' || el.type === 'week' || el.type === 'time' || el.type === 'range' || el.type === 'color') {
      push({ type: 'change', el: el.type, label: labelText || undefined, value: el.value, section: sectionOf(el) });
    }
    // Serbest metin, parola, e-posta, sayı: içerik alınmaz (gönderilirse istek kaydında görünür).
  }
}

/** Uygulama açılışında bir kez. Yönlendirici `history` ile gezindiği için o çağrılar sarılır. */
export function startAuditTrail() {
  if (started || typeof window === 'undefined') return;
  started = true;
  for (const fn of ['pushState', 'replaceState'] as const) {
    const orig = history[fn];
    history[fn] = function (this: History, ...args: Parameters<History['pushState']>) {
      const out = orig.apply(this, args);
      queueMicrotask(view);
      return out;
    } as History['pushState'];
  }
  window.addEventListener('popstate', view);
  document.addEventListener('click', onClick, { capture: true });
  document.addEventListener('change', onChange, { capture: true });
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') flush(true);
  });
  window.addEventListener('pagehide', () => {
    push({ type: 'leave' });
    flush(true);
  });
  view();
}
