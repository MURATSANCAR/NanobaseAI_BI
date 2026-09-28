import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { ENGINE_ENABLED } from '../engine';
import { canOpenRoute, usePageAccess } from '../useAdmin';
import { fmtMinutes, itOpsApi } from './api';
import SqlInfo from '../components/SqlInfo';
import { kaynakOf } from '../components/kaynakOf';

/** Kampüs üst şeridi: bir halka kopukken herkese tek cümle («Logo verisi şu an gelmiyor»). Ayrıntı yok; Sistem durumu
 *  sayfası rolünde olan kişi için bağlantı. Kopuk halka yoksa hiçbir şey çizilmez. */
export default function OutageStrip() {
  const pages = usePageAccess();
  const q = useQuery({ queryKey: ['itops', 'banner'], queryFn: itOpsApi.banner, enabled: ENGINE_ENABLED, refetchInterval: 120_000, retry: false });
  const items = q.data?.items ?? [];
  if (!items.length) return null;
  const now = Date.now();
  const text = items
    .map((i) => `${i.label} (${fmtMinutes(Math.max(0, Math.round((now - new Date(i.since).getTime()) / 60000)))})`)
    .join(', ');
  const canSee = canOpenRoute(pages, '/sistem-durumu');
  return (
    <div role="status" className="mx-auto mb-2 flex w-full max-w-[1720px] flex-wrap items-center gap-x-2 gap-y-1 rounded-2xl border border-red-100 bg-red-50 px-3 py-2 text-[12.5px] font-bold text-red-800">
      <span aria-hidden className="h-2 w-2 shrink-0 rounded-full bg-red-500" />
      <span className="min-w-0 flex-1">
        Bazı veriler şu an gelmiyor: {text}. Durum BT tarafından izleniyor.
        <SqlInfo k={kaynakOf(q.data)} alan="_hepsi" label="Kesinti süresi" className="ml-1 text-red-800" />
      </span>
      {canSee && (
        <Link to="/sistem-durumu" className="shrink-0 underline underline-offset-2">Sistem durumu</Link>
      )}
    </div>
  );
}
