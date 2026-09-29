import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Loader2, RefreshCw } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Note, btnGhost, errText } from '../admin/ui';
import { fmtDay, fmtInt, readersApi } from './api';
import { ROOT, ReadersFrame, useMeta } from './parts';
import ReadersHome from './ReadersHome';
import ReaderSearch from './ReaderSearch';
import MergeQueue from './MergeQueue';
import Segments from './Segments';
import Imports from './Imports';
import Exports from './Exports';
import SubjectRequest from './SubjectRequest';

/** H2 Okuyucu veri tabanı. Bölüm adres çubuğunda (/okurlar/ara, /birlestirme, /segmentler, /yuklemeler, /disa-aktarimlar, /kvkk). */
export default function ReadersScreen() {
  const { pathname } = useLocation();
  const here = pathname.replace(/\/+$/, '');
  const qc = useQueryClient();
  const meta = useMeta();
  const me = meta.data?.me;
  const overview = useQuery({ queryKey: ['readers', 'overview'], queryFn: readersApi.overview, enabled: ENGINE_ENABLED, staleTime: 30_000 });

  // Okuma sürerken durum yoklanır; bitince bütün okur görünümleri tazelenir.
  const running = meta.data?.job.running;
  const status = useQuery({
    queryKey: ['readers', 'status'],
    queryFn: readersApi.status,
    enabled: ENGINE_ENABLED && !!running,
    refetchInterval: (q) => (q.state.data && !q.state.data.running ? false : 4000),
  });
  useEffect(() => {
    if (running && status.data && !status.data.running) {
      qc.invalidateQueries({ queryKey: ['readers'] });
      if (status.data.error) toast.error(status.data.error);
      else toast.success('CRM kişi, aday ve İYS kayıtları yeniden okundu.');
    }
  }, [running, status.data, qc]);

  const refresh = useMutation({
    mutationFn: readersApi.refresh,
    onSuccess: (r) => {
      if (!r.started) toast.message('Okuma zaten sürüyor.');
      qc.invalidateQueries({ queryKey: ['readers', 'meta'] });
    },
    onError: (e) => toast.error(errText(e, 'Okuma başlatılamadı.') ?? ''),
  });

  const ov = overview.data;
  const busy = !!running || (status.data?.running ?? false);
  const problems = ov?.sources.filter((s) => s.failing || s.stale) ?? [];
  const aside = (
    <div className="flex flex-col gap-2 rounded-2xl bg-white/70 p-3 text-[12px] font-semibold text-canvas-muted">
      <span>
        {ov?.run.at ? <>Kaynaklar <strong className="text-canvas-ink">{fmtDay(ov.run.at)}</strong> tarihinde okundu.</> : 'Kaynaklar henüz okunmadı.'}
        {problems.length > 0 && <span className="text-red-700"> {problems.map((p) => p.label).join(', ')}: okunamadı ya da eski.</span>}
      </span>
      {busy && <span className="text-canvas-ink">Okunuyor: {status.data?.step ?? meta.data?.job.step ?? '…'}</span>}
      {me?.canMerge && (
        <button type="button" className={btnGhost} onClick={() => refresh.mutate()} disabled={busy || refresh.isPending}>
          {busy || refresh.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <RefreshCw aria-hidden className="h-4 w-4" />}
          Kaynakları yeniden oku
        </button>
      )}
    </div>
  );

  const section = here === ROOT ? <ReadersHome overview={ov} loading={overview.isLoading} error={overview.error} />
    : here.startsWith(`${ROOT}/ara`) ? <ReaderSearch />
    : here.startsWith(`${ROOT}/birlestirme`) ? <MergeQueue />
    : here.startsWith(`${ROOT}/segmentler`) ? <Segments />
    : here.startsWith(`${ROOT}/yuklemeler`) ? <Imports />
    : here.startsWith(`${ROOT}/disa-aktarimlar`) ? <Exports />
    : here.startsWith(`${ROOT}/kvkk`) ? <SubjectRequest />
    : <ReadersHome overview={ov} loading={overview.isLoading} error={overview.error} />;

  return (
    <ReadersFrame
      presence={ov ? `${fmtInt(ov.readers)} tekil okur` : 'Okurlar'}
      aside={aside}
      badges={{ [`${ROOT}/birlestirme`]: ov?.pendingCandidates || null }}
    >
      {!ENGINE_ENABLED && <Note tone="warn">Bu ekranın veri bağlantısı kurulmamış; sayılar açılamaz. Lütfen sistem yöneticinize bildirin.</Note>}
      {meta.error && <Note tone="err">{errText(meta.error, 'Okur veri tabanı açılamadı.')}</Note>}
      {section}
    </ReadersFrame>
  );
}
