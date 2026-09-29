import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Archive, Download, RotateCcw } from 'lucide-react';
import { ENGINE_ENABLED } from '../../engine';
import { Loading, Note, Pill, btnGhost, errText } from '../../admin/ui';
import { Img } from '../../editorial/studio/shared';
import Sheet from '../../editorial/studio/reader/Sheet';
import Frame from './Frame';
import { STATE_TONE, creativeApi, fmtDay, type Asset } from './api';
import BriefPanel from './BriefPanel';
import VisualPanel from './VisualPanel';
import TextPanel from './TextPanel';
import { ApprovalLine, Checks, DraftBadge } from './parts';
import { invalidateCreative, useCreativeMeta } from './useMeta';

/** Talep ekranı: solda brief ve kaynaklar, ortada görsel varyantlar (biçim × varyant), sağda metin varyantları.
 *  Süren üretim varken ekran 2 sn'de bir tazelenir; iş bitince yoklama durur. Telefonda sütunlar alt alta. */

function Versions({ a, onClose }: { a: Asset | null; onClose: () => void }) {
  const v = useQuery({ queryKey: ['creative', 'versions', a?.id], queryFn: () => creativeApi.versions(a!.id), enabled: ENGINE_ENABLED && !!a });
  return (
    <Sheet open={!!a} onClose={onClose} title="Sürümler" subtitle={a ? `Varyant ${a.varyant} · ${a.formatAdi ?? ''}` : undefined}>
      {v.isLoading && <Loading />}
      <ul className="flex flex-col gap-2">
        {v.data?.items.map((x) => (
          <li key={x.id} className={`flex flex-col gap-1.5 rounded-xl border p-2.5 ${x.guncel ? 'border-canvas-violet/40 bg-white' : 'border-slate-200 bg-slate-50'}`}>
            <div className="flex flex-wrap items-center justify-between gap-1">
              <span className="text-[12px] font-extrabold">v{x.surum}{x.guncel ? ' · güncel' : ''}</span>
              <span className="text-[11px] text-canvas-muted">{x.olusturan} · {fmtDay(x.olusturma)}</span>
            </div>
            {x.tur === 'gorsel'
              ? <Img src={creativeApi.fileUrl(x.id, 360)} alt={`v${x.surum}`} fallback="görsel" className="mx-auto max-h-48 w-auto rounded-lg object-contain" />
              : <p className="whitespace-pre-line text-[12.5px] leading-snug">{x.metin}</p>}
            {x.tur === 'metin' && <Checks c={x.dogrulama} />}
            <ApprovalLine a={x} />
            {x.taslakLisans && <DraftBadge />}
          </li>
        ))}
      </ul>
    </Sheet>
  );
}

export default function RequestScreen() {
  const { id = '' } = useParams();
  const qc = useQueryClient();
  const meta = useCreativeMeta();
  const q = useQuery({
    queryKey: ['creative', 'request', id],
    queryFn: () => creativeApi.request(id),
    enabled: ENGINE_ENABLED && !!id,
    refetchInterval: (query) => (query.state.data?.isler.some((j) => j.durum === 'suruyor') ? 2000 : false),
  });
  const [versions, setVersions] = useState<Asset | null>(null);
  const r = q.data;
  const me = meta.data?.me;
  const state = useMutation({
    mutationFn: (durum: string) => creativeApi.update(id, { durum }),
    onSuccess: () => { toast.success('Talep durumu değişti.'); return invalidateCreative(qc); },
    onError: (e) => toast.error(errText(e, 'Değiştirilemedi.') ?? ''),
  });
  const approved = r?.varliklar.filter((a) => a.onayli).length ?? 0;
  const drafts = r?.varliklar.filter((a) => a.onayli && a.taslakLisans).length ?? 0;

  const aside = r ? (
    <div className="flex flex-wrap items-center gap-2 lg:justify-end">
      <Pill tone={STATE_TONE[r.durum]}>{r.durumAdi}</Pill>
      {approved > 0 && (
        <a className={btnGhost} href={creativeApi.zipUrl(r.id)}><Download className="h-4 w-4" aria-hidden />Onaylı paket ({approved}, zip)</a>
      )}
      {(me?.talep || me?.uret) && (r.durum === 'arsiv' || r.durum === 'reddedildi' ? (
        <button type="button" className={btnGhost} disabled={state.isPending} onClick={() => state.mutate('yeniden')}><RotateCcw className="h-4 w-4" aria-hidden />Yeniden aç</button>
      ) : (
        <button type="button" className={btnGhost} disabled={state.isPending} onClick={() => { if (window.confirm('Talep arşive kaldırılsın mı? Varlıklar arşivde kalır.')) state.mutate('arsiv'); }}>
          <Archive className="h-4 w-4" aria-hidden />Arşive kaldır
        </button>
      ))}
    </div>
  ) : null;

  return (
    <Frame
      crumb="Görsel ve metin"
      title={r?.kitapAdi ?? id}
      back={{ to: '/pazarlama/icerik', label: 'Görsel ve metin' }}
      detail={r ? `${r.id} · ${r.kitapAdi}` : undefined}
      source="Stüdyo pazarlama kiti + CRM kitap kartı"
      lead={r ? (
        <span>
          Bu talebin brief'i, görselleri ve metinleri; her biri onaydan geçtikten sonra indirilebilir.{' '}
          <span className="font-mono font-bold">{r.id}</span> · {r.kanalAdi} · termin {fmtDay(r.termin)} · isteyen {r.isteyenAd || r.isteyen}
          {r.studioKind === 'kitap' ? ' · stüdyodaki kitap işiyle' : ''}
        </span>
      ) : undefined}
      aside={aside}
    >
      {!ENGINE_ENABLED && <Note tone="warn">Veri bağlantısı kurulu değil; bu ekran şu an veri gösteremez. Sistem yöneticinize haber verin.</Note>}
      {q.isLoading && <Loading />}
      {q.error && <Note tone="err">{errText(q.error, 'Talep okunamadı.')}</Note>}
      {drafts > 0 && (
        <Note tone="warn">{drafts} onaylı görselde Zeki AI ile çizilmiş resim var: ticari kullanım izni gelene kadar yayına hazır sayılmaz, dosya adı TASLAK- ile iner.</Note>
      )}
      {r && (
        <div className="grid min-w-0 gap-3 xl:grid-cols-[minmax(0,320px)_minmax(0,1fr)_minmax(0,420px)] xl:items-start lg:gap-4">
          <BriefPanel r={r} meta={meta.data} />
          <VisualPanel r={r} meta={meta.data} onVersions={setVersions} />
          <TextPanel r={r} meta={meta.data} onVersions={setVersions} />
        </div>
      )}
      <Versions a={versions} onClose={() => setVersions(null)} />
    </Frame>
  );
}
