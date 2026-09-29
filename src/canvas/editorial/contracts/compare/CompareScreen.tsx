import { Link, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ChevronLeft, Loader2, RefreshCw } from 'lucide-react';
import { Note, btnGhost } from '../../../admin/ui';
import { ENGINE_ENABLED } from '../../../engine';
import { ModuleFrame } from '../../kit';
import { Tabs, errMsg, stamp } from '../ui';
import { compareApi } from './api';
import ScanTab from './ScanTab';
import ContractTab from './ContractTab';
import DocsTab from './DocsTab';
import PositionsTab from './PositionsTab';

type Tab = 'tarama' | 'sozlesme' | 'belge' | 'pozisyon';

/**
 * Sözleşme karşılaştırma: bir sözleşmenin maddeleri geçmiş sözleşmelerle (emsal), serbest metinli özel maddeler ve
 * belge metni madde madde. Kararlar sayımdır (model yok); CRM'e yazılmaz. Sekme ve seçili sözleşme adreste durur
 * (`?sekme=sozlesme&sozlesme=<kimlik>`), bağlantı paylaşılabilir.
 */
export default function CompareScreen() {
  const [params, setParams] = useSearchParams();
  const tab = (['tarama', 'sozlesme', 'belge', 'pozisyon'].includes(params.get('sekme') ?? '') ? params.get('sekme') : 'tarama') as Tab;
  const key = params.get('sozlesme') ?? '';
  const qc = useQueryClient();
  // CRM yeniden okunurken 5 sn'de bir bakılır; okuma bitince görüntünün anı değişir, sekmelerin sorguları bu anla
  // anahtarlandığı için kendiliğinden yenilenir.
  const meta = useQuery({
    queryKey: ['contracts', 'compare', 'meta'],
    queryFn: compareApi.meta,
    enabled: ENGINE_ENABLED,
    staleTime: 60_000,
    refetchInterval: (q) => (q.state.data?.gorunum.yenileniyor ? 5_000 : false),
  });
  const refresh = useMutation({
    mutationFn: compareApi.refresh,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['contracts', 'compare', 'meta'] }),
  });
  const view = meta.data?.gorunum;
  const busy = refresh.isPending || !!view?.yenileniyor;

  const go = (next: Tab, contract?: string) =>
    setParams((p) => {
      const n = new URLSearchParams(p);
      n.set('sekme', next);
      if (contract !== undefined) n.set('sozlesme', contract);
      return n;
    });

  return (
    <ModuleFrame
      route="/telif-sozlesme/karsilastirma"
      crumb="Sözleşmeler"
      title="Sözleşme karşılaştırma"
      lead="Her sözleşmenin maddeleri benzer geçmiş sözleşmelerle kıyaslanır: emsalden yüksek ya da düşük oran, nadir hak, eksik madde, sözleşmeye özgü not. Belgeler madde madde karşılaştırılır. CRM'e yazılmaz."
      source="CRM sözleşmeleri"
      presence={view?.okunduAn ? `CRM okundu: ${stamp(view.okunduAn)}` : 'Kaynak: CRM'}
      aside={
        <div className="flex flex-wrap items-center justify-start gap-1.5 lg:justify-end">
          <Link to="/telif-sozlesme" className={btnGhost}>
            <ChevronLeft aria-hidden className="h-4 w-4" />
            Sözleşmeler
          </Link>
          <button
            type="button"
            className={btnGhost}
            disabled={busy}
            onClick={() => refresh.mutate()}
            title="CRM sözleşmelerini yeniden oku (yaklaşık 15 saniye)"
          >
            {busy ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <RefreshCw aria-hidden className="h-4 w-4" />}
            {busy ? 'CRM okunuyor' : 'CRM\'i yeniden oku'}
          </button>
        </div>
      }
    >
      {!ENGINE_ENABLED && <Note tone="warn">ZEKİ AI bağlantısı bu derlemede tanımlı değil.</Note>}
      {meta.error && <Note tone="err">{errMsg(meta.error)}</Note>}
      {meta.isLoading && (
        <Note tone="info">CRM sözleşmeleri okunuyor; ilk açılışta 15–30 saniye sürebilir, sonra görüntü saklanır.</Note>
      )}
      {meta.data && meta.data.kur.okunan < meta.data.kur.ay && (
        <Note tone="info">
          {`TL tutarlar dolara çevrilerek kıyaslanır; kurların ${meta.data.kur.okunan}/${meta.data.kur.ay} ayı okundu${meta.data.kur.okunuyor ? ', kalanı arka planda okunuyor' : ''}. Kuru okunmamış aydaki tutar kıyasa girmez.`}
        </Note>
      )}
      <Tabs
        value={tab}
        onChange={(v) => go(v)}
        items={[
          { id: 'tarama', label: 'Olağan dışı sözleşmeler' },
          { id: 'sozlesme', label: 'Sözleşme incele' },
          { id: 'belge', label: 'Belge karşılaştırma' },
          { id: 'pozisyon', label: 'Standart pozisyonlar' },
        ]}
      />
      {meta.data && tab === 'tarama' && <ScanTab meta={meta.data} onOpen={(id) => go('sozlesme', id)} />}
      {meta.data && tab === 'sozlesme' && <ContractTab meta={meta.data} contractKey={key} onPick={(id) => go('sozlesme', id)} />}
      {meta.data && tab === 'belge' && <DocsTab meta={meta.data} />}
      {meta.data && tab === 'pozisyon' && <PositionsTab meta={meta.data} />}
    </ModuleFrame>
  );
}
