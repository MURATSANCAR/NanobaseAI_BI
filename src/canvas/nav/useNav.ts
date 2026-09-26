import { createContext, useContext, useMemo } from 'react';
import { useLocation } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ENGINE_ENABLED, alertsApi, webApi } from '../engine';
import { useNavRole } from '../useAdmin';
import { matchActive, visibleNav, type NavGroup, type NavItem, type NavRole, type VisibleGroup } from './navModel';
import { useNavState, type NavState } from './navState';

export type NavData = {
  role: NavRole;
  groups: VisibleGroup[];
  active: { group: NavGroup; item: NavItem } | null;
  alertCount: number;
  state: NavState;
  update: (fn: (s: NavState) => NavState) => void;
};

/** Menünün bütün verisi: rol, ortam bayrağı, etkin öğe, uyarı sayısı ve kişinin menü tercihi. */
export function useNavData(): NavData {
  const role = useNavRole();
  // Basın ve web yalnız ortamda açıksa görünür; durum gelene kadar gizli (müşteri ortamında kapalı).
  const web = useQuery({
    queryKey: ['editorial', 'web', 'status'],
    queryFn: webApi.status,
    enabled: ENGINE_ENABLED,
    staleTime: 10 * 60_000,
    retry: false,
  });
  // Uyarılar ekranıyla aynı anahtar: sayı ekrandaki listeyle hep aynı.
  const alerts = useQuery({
    queryKey: ['zeki-uyarilar'],
    queryFn: alertsApi.list,
    enabled: ENGINE_ENABLED,
    staleTime: 60_000,
    retry: false,
  });
  const loc = useLocation();
  const { state, update } = useNavState();
  const groups = useMemo(
    () => visibleNav({ isAdmin: role.isAdmin, isEditor: role.isEditor }, { webWatch: web.data?.enabled === true }),
    [role.isAdmin, role.isEditor, web.data?.enabled],
  );
  const active = useMemo(() => matchActive(groups, loc.pathname, loc.search), [groups, loc.pathname, loc.search]);
  const alertCount = (alerts.data?.alerts ?? []).filter((a) => a.status === 'active' && a.state === 'triggered').length;
  return { role, groups, active, alertCount, state, update };
}

export type NavUi = {
  openPalette: () => void;
  openModules: () => void;
  openProfile: () => void;
};

export const NavUiContext = createContext<NavUi>({ openPalette: () => {}, openModules: () => {}, openProfile: () => {} });
export const useNavUi = () => useContext(NavUiContext);

/** "Deniz Kaya" → "DK"; hesap adı ise ilk iki harf. */
export const initials = (name: string) => {
  const parts = name.trim().split(/[\s._@-]+/).filter(Boolean);
  const s = parts.length >= 2 ? parts[0][0] + parts[parts.length - 1][0] : (parts[0] ?? '?').slice(0, 2);
  return s.toLocaleUpperCase('tr');
};

export const roleLabel = (r: NavRole) => (r.isAdmin ? 'Yönetici' : r.isEditor ? 'Editör' : 'Kullanıcı');

/** ⌘K Mac'te, Ctrl K diğerlerinde. */
export const paletteKey = () =>
  typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent) ? '⌘K' : 'Ctrl K';

/** Göreli zaman: "az önce", "12 dk önce", "dün 16:40", "3 gün önce". */
export function ago(at: number, now = Date.now()): string {
  const s = Math.max(0, Math.round((now - at) / 1000));
  if (s < 60) return 'az önce';
  const m = Math.round(s / 60);
  if (m < 60) return `${m} dk önce`;
  const h = Math.round(m / 60);
  const d = new Date(at);
  const hm = d.toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' });
  const today = new Date(now);
  const yest = new Date(now - 86_400_000);
  if (d.toDateString() === today.toDateString()) return h <= 1 ? '1 saat önce' : `${h} saat önce`;
  if (d.toDateString() === yest.toDateString()) return `dün ${hm}`;
  return `${Math.max(2, Math.round(h / 24))} gün önce`;
}
