import { useCallback } from 'react';
import { useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query';
import { ENGINE_ENABLED, prefsApi } from '../engine';

/**
 * Menünün kişiye ait durumu: son açılan ekranlar.
 * Doğrusu sunucudaki kişi tercihidir (`semantic_user_prefs`, anahtar `nav:state`); başka bilgisayardan
 * girilince aynı menü gelir. Tarayıcı yalnız önbellek tutar: ilk boyamada sunucu cevabı gelene kadar
 * titremesin diye.
 */

export type RecentEntry = { to: string; label: string; group: string; at: number };
export type NavState = {
  recent?: RecentEntry[];
};

/** «Son açılanlar» bir yakınlık listesidir: en yeni 12 farklı ekran tutulur (eskisi düşer); komut paleti
 *  hepsini gösterir, ekranda «son 12» yazar. */
export const RECENT_KEEP = 12;

export const NAV_PREF_KEY = 'nav:state';
const LS_KEY = 'timas.nav:state';
const QK = ['prefs', NAV_PREF_KEY] as const;

/** Kayıtlı menü durumunu bugünkü biçime indirger. Eski sürümler `collapsed` ve alan kimliğiyle `open`
 *  ({ kayitlar: true } gibi) tutuyordu; menü artık alan açıp kapamıyor, bu alanlar sessizce düşer. Bozuk
 *  «son açılan» satırı da düşer: kayıt ne olursa olsun menü çalışır. */
export function cleanNavState(raw: unknown): NavState {
  if (!raw || typeof raw !== 'object') return {};
  const list = (raw as { recent?: unknown }).recent;
  if (!Array.isArray(list)) return {};
  const recent = list.filter(
    (r): r is RecentEntry =>
      !!r && typeof r === 'object' && typeof r.to === 'string' && r.to.startsWith('/') && typeof r.label === 'string' && typeof r.at === 'number',
  );
  return { recent: recent.map((r) => ({ to: r.to, label: r.label, group: typeof r.group === 'string' ? r.group : '', at: r.at })).slice(0, RECENT_KEEP) };
}

/** Aynı adres bir kez tutulur, en yeni başa gelir. */
export function pushRecent(list: RecentEntry[] | undefined, entry: RecentEntry): RecentEntry[] {
  return [entry, ...(list ?? []).filter((r) => r.to !== entry.to)].slice(0, RECENT_KEEP);
}

function readLocal(): NavState | undefined {
  try {
    const raw = window.localStorage.getItem(LS_KEY);
    return raw ? cleanNavState(JSON.parse(raw)) : undefined;
  } catch {
    return undefined;
  }
}

function writeLocal(s: NavState) {
  try {
    window.localStorage.setItem(LS_KEY, JSON.stringify(s));
  } catch {
    /* gizli sekme / dolu depo: önbellek yazılamazsa sunucu kaydı yine geçerli */
  }
}

// Kabuk her ekranda yeniden kurulur; yazma zamanlayıcısı modül düzeyinde durur ki geçişte kaybolmasın.
let saveTimer: number | undefined;
let pending: NavState | null = null;

function scheduleSave(value: NavState) {
  if (!ENGINE_ENABLED) return;
  pending = value;
  window.clearTimeout(saveTimer);
  saveTimer = window.setTimeout(() => {
    const v = pending;
    pending = null;
    if (v) prefsApi.put(NAV_PREF_KEY, v).catch((e) => console.warn('menü tercihi kaydedilemedi', e));
  }, 800);
}

// Sunucu kaydı gelmeden yapılan değişiklikler (ilk ekrandaki «son açılan» kaydı) sırada
// bekler; kayıt gelince onun üstüne sırayla uygulanır. Yoksa boş önbellekle başlayan yeni bir cihaz
// sunucudaki tercihi ezerdi, ya da geç gelen eski cevap yeni değişikliği silerdi.
let loaded = !ENGINE_ENABLED;
let queued: Array<(s: NavState) => NavState> = [];

export function updateNavState(qc: QueryClient, fn: (s: NavState) => NavState) {
  const cur = (qc.getQueryData<NavState>(QK) ?? readLocal() ?? {}) as NavState;
  const next = cleanNavState(fn(cleanNavState(cur)));
  qc.setQueryData(QK, next);
  writeLocal(next);
  if (loaded) scheduleSave(next);
  else queued.push(fn);
}

export function useNavState(): { state: NavState; update: (fn: (s: NavState) => NavState) => void } {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: QK,
    queryFn: async () => {
      let r: Awaited<ReturnType<typeof prefsApi.get<NavState>>>;
      try {
        r = await prefsApi.get<NavState>(NAV_PREF_KEY);
      } catch (e) {
        // Kayıt okunamadı (oturum yok, köprü kapalı): menü önbellekle çalışır, sonraki değişiklik yazılmayı dener.
        loaded = true;
        queued = [];
        throw e;
      }
      let v: NavState = cleanNavState(r.value);
      const replay = queued;
      queued = [];
      loaded = true;
      for (const fn of replay) v = fn(v);
      writeLocal(v);
      if (replay.length) scheduleSave(v);
      return v;
    },
    enabled: ENGINE_ENABLED,
    staleTime: Infinity,
    retry: false,
    placeholderData: readLocal,
  });
  const update = useCallback((fn: (s: NavState) => NavState) => updateNavState(qc, fn), [qc]);
  return { state: q.data ?? {}, update };
}
