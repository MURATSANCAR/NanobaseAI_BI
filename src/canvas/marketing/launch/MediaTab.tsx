import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Plus, Trash2 } from 'lucide-react';
import { ENGINE_ENABLED } from '../../engine';
import { Loading, Note, Pill, btnGhost, errText, field, label as labelCls } from '../../admin/ui';
import { fmtDay } from '../api';
import { Block } from '../parts';
import { launchApi, type Launch, type LaunchMeta } from './api';

/** Medya yansıması: basın ve web taraması açık olan ortamda o kayıtlar (yalnız okuma, kanal adı ve bağlantıyla), her
 *  ortamda elle kayıt (mecra, başlık, bağlantı, tarih, ton). */

const TONE_PILL: Record<string, 'ok' | 'err' | 'muted'> = { olumlu: 'ok', olumsuz: 'err', notr: 'muted' };

export default function MediaTab({ launch, meta }: { launch: Launch; meta: LaunchMeta }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['launch', 'media', launch.id], queryFn: () => launchApi.media(launch.id), enabled: ENGINE_ENABLED });
  const [add, setAdd] = useState({ mecra: '', baslik: '', url: '', tarih: new Date().toISOString().slice(0, 10), ton: 'notr' });
  const refetch = () => { qc.invalidateQueries({ queryKey: ['launch', 'media', launch.id] }); qc.invalidateQueries({ queryKey: ['launch', 'crm-todo', launch.id] }); };
  const create = useMutation({
    mutationFn: () => launchApi.addMedia(launch.id, add),
    onSuccess: () => { toast.success('Yansıma eklendi.'); setAdd({ ...add, mecra: '', baslik: '', url: '' }); refetch(); },
    onError: (e) => toast.error(errText(e, 'Eklenemedi.') ?? ''),
  });
  const remove = useMutation({
    mutationFn: (id: string) => launchApi.deleteMedia(launch.id, id),
    onSuccess: () => { toast.success('Kayıt silindi.'); refetch(); },
    onError: (e) => toast.error(errText(e, 'Silinemedi.') ?? ''),
  });
  const d = q.data;
  return (
    <Block
      title="Medya yansıması"
      help={d?.webAcik ? 'Basın ve web taramasının bu kitapla eşleşen kayıtları (yalnız ilgili bulunanlar) ve elle girilen yansımalar.' : 'Bu ortamda basın ve web taraması kapalı: yansımalar elle girilir.'}
    >
      {q.error && <Note tone="err">{errText(q.error, 'Yansımalar açılamadı.')}</Note>}
      {q.isLoading && <Loading />}
      {d && (
        <p className="mb-2 text-[12px] font-semibold text-canvas-muted">
          {Object.entries(meta.tones).map(([k, v]) => `${v}: ${d.ton[k] ?? 0}`).join(' · ')}
        </p>
      )}
      {d && d.items.length === 0 && <p className="text-[12.5px] text-canvas-muted">Henüz yansıma yok.</p>}
      <ul className="flex flex-col gap-1.5">
        {d?.items.map((m, i) => (
          <li key={m.id ?? `${m.url}-${i}`} className="flex items-start gap-2 rounded-2xl border border-slate-100 bg-white/80 p-2.5">
            <div className="min-w-0 flex-1">
              {m.url ? (
                <a href={m.url} target="_blank" rel="noreferrer noopener" className="break-words text-[13px] font-semibold leading-snug text-canvas-violet hover:underline">{m.baslik}</a>
              ) : (
                <div className="break-words text-[13px] font-semibold leading-snug">{m.baslik}</div>
              )}
              <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[11px] text-canvas-muted">
                <span>{m.mecra ?? '—'}</span><span>· {fmtDay(m.tarih)}</span>
                {m.tonAdi && <Pill tone={TONE_PILL[m.ton ?? ''] ?? 'muted'}>{m.tonAdi}</Pill>}
                <Pill tone={m.kaynak === 'web' ? 'muted' : 'violet'}>{m.kaynak === 'web' ? 'Basın ve web' : 'Elle'}</Pill>
              </div>
            </div>
            {meta.me.canWrite && m.kaynak === 'elle' && m.id && (
              <button type="button" className={btnGhost} aria-label="Kaydı sil" onClick={() => remove.mutate(m.id as string)}><Trash2 aria-hidden className="h-4 w-4" /></button>
            )}
          </li>
        ))}
      </ul>
      {meta.me.canWrite && (
        <form className="mt-3 grid grid-cols-1 gap-2 rounded-2xl bg-slate-50 p-2.5 sm:grid-cols-[150px_1fr_1fr_150px_130px_auto] sm:items-end"
          onSubmit={(e) => { e.preventDefault(); if (add.baslik.trim()) create.mutate(); }}>
          <label className="flex flex-col gap-1"><span className={labelCls}>Mecra</span>
            <input className={field} value={add.mecra} onChange={(e) => setAdd({ ...add, mecra: e.target.value })} /></label>
          <label className="flex min-w-0 flex-col gap-1"><span className={labelCls}>Başlık</span>
            <input className={field} value={add.baslik} onChange={(e) => setAdd({ ...add, baslik: e.target.value })} /></label>
          <label className="flex min-w-0 flex-col gap-1"><span className={labelCls}>Bağlantı</span>
            <input className={field} inputMode="url" placeholder="https://…" value={add.url} onChange={(e) => setAdd({ ...add, url: e.target.value })} /></label>
          <label className="flex flex-col gap-1"><span className={labelCls}>Tarih</span>
            <input type="date" className={field} value={add.tarih} onChange={(e) => setAdd({ ...add, tarih: e.target.value })} /></label>
          <label className="flex flex-col gap-1"><span className={labelCls}>Ton</span>
            <select className={field} value={add.ton} onChange={(e) => setAdd({ ...add, ton: e.target.value })}>
              {Object.entries(meta.tones).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select></label>
          <button type="submit" className={btnGhost} disabled={!add.baslik.trim() || create.isPending}><Plus aria-hidden className="h-4 w-4" />Ekle</button>
        </form>
      )}
    </Block>
  );
}
