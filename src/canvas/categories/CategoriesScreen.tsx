import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Loader2, RefreshCw } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Note, btnGhost, errText } from '../admin/ui';
import { categoriesApi, fmtDay } from './api';
import { CategoriesFrame, ROOT, useMeta } from './parts';
import CategoriesHome from './CategoriesHome';
import ProfileQueue from './ProfileQueue';
import TreeEditor from './TreeEditor';
import Findings from './Findings';
import CrmDiff from './CrmDiff';
import TagsTab from './TagsTab';

/** H1 Kategori ağacı. Bölüm adres çubuğunda (/kategori-agaci/kuyruk, /agac, /tutarsizlik, /crm-farki, /etiketler). */
export default function CategoriesScreen() {
  const { pathname } = useLocation();
  const here = pathname.replace(/\/+$/, '');
  const qc = useQueryClient();
  const meta = useMeta();
  const me = meta.data?.me;
  const overview = useQuery({ queryKey: ['categories', 'overview'], queryFn: categoriesApi.overview, enabled: ENGINE_ENABLED, staleTime: 30_000 });

  // Kaynak okuması sürerken durum yoklanır; bitince bütün kategori görünümleri tazelenir.
  const running = overview.data?.job.running || meta.data?.job.running;
  const status = useQuery({
    queryKey: ['categories', 'status'],
    queryFn: categoriesApi.status,
    enabled: ENGINE_ENABLED && !!running,
    refetchInterval: (q) => (q.state.data && !q.state.data.running ? false : 4000),
  });
  useEffect(() => {
    if (running && status.data && !status.data.running) {
      qc.invalidateQueries({ queryKey: ['categories'] });
      if (status.data.error) toast.error(status.data.error);
      else toast.success('CRM, Logo ve site kategorileri yeniden okundu.');
    }
  }, [running, status.data, qc]);

  const refresh = useMutation({
    mutationFn: categoriesApi.refresh,
    onSuccess: (r) => {
      if (!r.started) toast.message('Okuma zaten sürüyor.');
      qc.invalidateQueries({ queryKey: ['categories', 'overview'] });
    },
    onError: (e) => toast.error(errText(e, 'Yenileme başlatılamadı.') ?? ''),
  });

  const ov = overview.data;
  const aside = (
    <div className="flex flex-col gap-2 rounded-2xl bg-white/70 p-3 text-[12px] font-semibold text-canvas-muted">
      <span>
        {ov?.sync.at ? <>Kaynaklar <strong className="text-canvas-ink">{fmtDay(ov.sync.at)}</strong> tarihinde okundu.</> : 'Kaynaklar henüz okunmadı.'}
        {ov?.priority.end && <> Satış önceliği Logo'da {fmtDay(ov.priority.end)}'e kadar ({ov.priority.months} ay).</>}
        {ov?.sync.logo?.error && <span className="text-red-700"> Logo okunamadı: {ov.sync.logo.error}</span>}
      </span>
      {running && <span className="text-canvas-ink">Okunuyor: {status.data?.step ?? ov?.job.step ?? '…'}</span>}
      {me?.canPropose && (
        <button type="button" className={btnGhost} onClick={() => refresh.mutate()} disabled={!!running || refresh.isPending}>
          {running || refresh.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <RefreshCw aria-hidden className="h-4 w-4" />}
          Kaynakları yenile
        </button>
      )}
    </div>
  );

  const section = here === ROOT ? <CategoriesHome overview={ov} loading={overview.isLoading} error={overview.error} />
    : here.startsWith(`${ROOT}/kuyruk`) ? <ProfileQueue />
    : here.startsWith(`${ROOT}/agac`) ? <TreeEditor />
    : here.startsWith(`${ROOT}/tutarsizlik`) ? <Findings />
    : here.startsWith(`${ROOT}/crm-farki`) ? <CrmDiff />
    : here.startsWith(`${ROOT}/etiketler`) ? <TagsTab />
    : <CategoriesHome overview={ov} loading={overview.isLoading} error={overview.error} />;

  return (
    <CategoriesFrame
      presence={ov ? `${new Intl.NumberFormat('tr-TR').format(ov.activeBooks)} aktif kitap` : 'Kategori ağacı'}
      aside={aside}
      badges={{ [`${ROOT}/kuyruk`]: ov?.mine.pending || null, [`${ROOT}/tutarsizlik`]: ov?.findings.open || null, [`${ROOT}/crm-farki`]: ov?.crmDiff.stale || null }}
    >
      {!ENGINE_ENABLED && <Note tone="warn">Zeki AI bağlantısı bu derlemede tanımlı değil.</Note>}
      {meta.error && <Note tone="err">{errText(meta.error, 'Kategori ağacı açılamadı.')}</Note>}
      {section}
    </CategoriesFrame>
  );
}
