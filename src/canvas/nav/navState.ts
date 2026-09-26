import { useCallback } from 'react';
import { useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query';
import { ENGINE_ENABLED, prefsApi } from '../engine';
import type { NavGroupId } from './navModel';

/**
 * Menünün kişiye ait durumu: panel daraltılmış mı, gruplu listede hangi grup açık, son açılan ekranlar.
 * Doğrusu sunucudaki kişi tercihidir (`semantic_user_prefs`, anahtar `nav:state`); başka bilgisayardan
 * girilince aynı menü gelir. Tarayıcı yalnız önbellek tutar: ilk boyamada sunucu cevabı gelene kadar
 * titremesin diye.
 */

export type RecentEntry = { to: string; label: string; group: string; at: number };
export type NavState = {
  collapsed?: boolean;
  open?: Partial<Record<NavGroupId, boolean>>;
  recent?: RecentEntry[];
};

/** «Son açılanlar» bir yakınlık listesidir: en yeni 12 farklı ekran tutulur (eskisi düşer). Panel bunların
 *  ilk 4'ünü gösterir (dar alanda okunur kalsın), komut paleti 12'sinin hepsini; ekranda «son 12» yazar. */
export const RECENT_KEEP = 12;
export const RECENT_PANEL = 4;

export const NAV_PREF_KEY = 'nav:state';
const LS_KEY = 'timas.nav:state';
const QK = ['prefs', NAV_PREF_KEY] as const;

/** Aynı adres bir kez tutulur, en yeni başa gelir. */
export function pushRecent(list: RecentEntry[] | undefined, entry: RecentEntry): RecentEntry[] {
  return [entry, ...(list ?? []).filter((r) => r.to !== entry.to)].slice(0, RECENT_KEEP);
}

function readLocal(): NavState | undefined {
  try {
    const raw = window.localStorage.getItem(LS_KEY);
    return raw ? (JSON.parse(raw) as NavState) : undefined;
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

// Sunucu kaydı gelmeden yapılan değişiklikler (ilk ekrandaki «son açılan» kaydı, erken daraltma) sırada
// bekler; kayıt gelince onun üstüne sırayla uygulanır. Yoksa boş önbellekle başlayan yeni bir cihaz
// sunucudaki tercihi ezerdi, ya da geç gelen eski cevap yeni değişikliği silerdi.
let loaded = !ENGINE_ENABLED;
let queued: Array<(s: NavState) => NavState> = [];

export function updateNavState(qc: QueryClient, fn: (s: NavState) => NavState) {
  const cur = (qc.getQueryData<NavState>(QK) ?? readLocal() ?? {}) as NavState;
  const next = fn(cur);
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
      let v: NavState = r.value ?? {};
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
