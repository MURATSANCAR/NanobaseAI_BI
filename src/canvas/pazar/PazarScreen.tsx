import { useEffect, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Loader2, RefreshCw } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Note, btnGhost, errText } from '../admin/ui';
import { fmtDay, fmtInt, pazarApi } from './api';
import { FreshnessStrip, PazarFrame, ROOT, useMeta } from './parts';
import MarketHome from './MarketHome';
import CompetitorMatrix from './CompetitorMatrix';
import ComparablesScreen from './ComparablesScreen';
import CategoryMap from './CategoryMap';
import ReportsScreen from './ReportsScreen';
import ReportFigures from './ReportFigures';
import BriefEditor from './BriefEditor';

/** M39 Pazar ve rakip. Bölüm adres çubuğunda: /pazar-arastirma, /rakipler, /emsal, /kategori-esleme, /raporlar(/:id),
 *  /ozet/:donem. */
export default function PazarScreen() {
  const { pathname } = useLocation();
  const here = pathname.replace(/\/+$/, '');
  const qc = useQueryClient();
  const meta = useMeta();
  const me = meta.data?.me;
  const overview = useQuery({ queryKey: ['pazar', 'overview'], queryFn: pazarApi.overview, enabled: ENGINE_ENABLED && here === ROOT, staleTime: 30_000 });

  // Kaynak okuması sürerken durum yoklanır; bitince bütün pazar görünümleri tazelenir.
  const running = !!meta.data?.jobs.kaynak.running;
  const status = useQuery({
    queryKey: ['pazar', 'status'],
    queryFn: pazarApi.status,
    enabled: ENGINE_ENABLED && running,
    refetchInterval: (q) => (q.state.data && !q.state.data.kaynak.running ? false : 4000),
  });
  const wasRunning = useRef(false);
  useEffect(() => {
    const now = status.data ? status.data.kaynak.running : running;
    if (wasRunning.current && !now) {
      qc.invalidateQueries({ queryKey: ['pazar'] });
      const err = status.data?.kaynak.error;
      if (err) toast.error(err);
      else toast.success('CRM rakip katalog, Timaş kitapları ve Logo satışları yeniden okundu.');
    }
    wasRunning.current = now;
  }, [running, status.data, qc]);

  const refresh = useMutation({
    mutationFn: pazarApi.refresh,
    onSuccess: (r) => {
      if (!r.started) toast.message('Okuma zaten sürüyor.');
      qc.invalidateQueries({ queryKey: ['pazar', 'meta'] });
    },
    onError: (e) => toast.error(errText(e, 'Yenileme başlatılamadı.') ?? ''),
  });

  const busy = running || status.data?.kaynak.running;
  const snap = overview.data?.snapshot;
  const aside = me?.canMap ? (
    <div className="flex flex-col gap-2 rounded-2xl bg-white/70 p-3 text-[12px] font-semibold text-canvas-muted">
      <span>
        {snap?.at ? <>Kaynaklar <strong className="text-canvas-ink">{fmtDay(snap.at)}</strong> tarihinde okundu.</> : 'Kaynaklar haftada bir (pazartesi sabahı) okunur.'}
        {snap?.errors?.logo && <span className="text-red-700"> Logo okunamadı: {snap.errors.logo}</span>}
      </span>
      {busy && <span className="text-canvas-ink">Okunuyor: {status.data?.kaynak.step ?? meta.data?.jobs.kaynak.step ?? '…'}</span>}
      <button type="button" className={btnGhost} onClick={() => refresh.mutate()} disabled={!!busy || refresh.isPending}>
        {busy || refresh.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <RefreshCw aria-hidden className="h-4 w-4" />}
        Kaynakları yenile
      </button>
    </div>
  ) : undefined;

  const section = here === ROOT ? <MarketHome overview={overview.data} loading={overview.isLoading} error={overview.error} />
    : here.startsWith(`${ROOT}/rakipler`) ? <CompetitorMatrix />
    : here.startsWith(`${ROOT}/emsal`) ? <ComparablesScreen />
    : here.startsWith(`${ROOT}/kategori-esleme`) ? <CategoryMap />
    : here.startsWith(`${ROOT}/raporlar/`) ? <ReportFigures id={decodeURIComponent(here.slice(`${ROOT}/raporlar/`.length))} />
    : here.startsWith(`${ROOT}/raporlar`) ? <ReportsScreen />
    : here.startsWith(`${ROOT}/ozet/`) ? <BriefEditor donem={decodeURIComponent(here.slice(`${ROOT}/ozet/`.length))} />
    : <MarketHome overview={overview.data} loading={overview.isLoading} error={overview.error} />;

  const f = overview.data?.freshness;
  return (
    <PazarFrame
      presence={f?.records ? `${fmtInt(f.records)} rakip kaydı` : 'Pazar ve rakip'}
      aside={aside}
      badges={{
        [`${ROOT}/kategori-esleme`]: overview.data ? (overview.data.mapping.counts.oneri ?? 0) + (overview.data.mapping.counts.belirsiz ?? 0) : null,
        [`${ROOT}/raporlar`]: overview.data?.pendingFigures ?? null,
      }}
    >
      {!ENGINE_ENABLED && <Note tone="warn">Bu ekranın veri bağlantısı kurulmamış; sayılar açılamaz. Lütfen sistem yöneticinize bildirin.</Note>}
      {meta.error && <Note tone="err">{errText(meta.error, 'Pazar ekranı açılamadı.')}</Note>}
      <FreshnessStrip />
      {section}
    </PazarFrame>
  );
}
