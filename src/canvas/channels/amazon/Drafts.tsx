import { useState } from 'react';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Check, Copy, Loader2, Sparkles } from 'lucide-react';
import { ENGINE_ENABLED } from '../../engine';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText, field, fmtDate, label as labelCls } from '../../admin/ui';
import { Pager, Panel } from '../../editorial/kit';
import { amazonApi, type Draft } from './api';
import { AmazonFrame, useAmazonMeta } from './parts';

const FIELD_NAMES: Record<string, string> = {
  baslik: 'Başlık', aciklama: 'Açıklama', anahtar_kelimeler: 'Anahtar kelimeler', moduller: 'A+ bölümleri', hedef_okur: 'Hedef okur',
  ton: 'Ton', dikkat: 'Dikkat edilecekler', ozet: 'Özet', metin: 'Metin',
};

function show(v: unknown): string {
  if (Array.isArray(v)) return v.map((x) => (typeof x === 'object' && x ? Object.values(x as Record<string, unknown>).join(': ') : String(x))).join('\n');
  if (v && typeof v === 'object') return Object.values(v as Record<string, unknown>).map(String).join('\n');
  return String(v ?? '');
}

function DraftCard({ d }: { d: Draft }) {
  const qc = useQueryClient();
  const mark = useMutation({
    mutationFn: () => amazonApi.setDraft(d.id, d.durum === 'taslak' ? 'kullanildi' : 'taslak'),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['amazon', 'drafts'] }),
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  const text = Object.entries(d.metin).map(([k, v]) => `${FIELD_NAMES[k] ?? k}:\n${show(v)}`).join('\n\n');
  return (
    <div className="rounded-2xl bg-white/70 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <div className="font-extrabold">{d.kitap ?? d.stokKodu} · {d.pazar} · {d.dil}</div>
          <div className="text-[12px] text-canvas-muted">{d.turAd} · {d.yazan} · {fmtDate(d.tarih)}</div>
        </div>
        <Pill tone={d.durum === 'kullanildi' ? 'ok' : 'violet'}>{d.durum === 'kullanildi' ? 'Kullanıldı' : 'Taslak'}</Pill>
      </div>
      <dl className="mt-2 flex flex-col gap-2 text-[12.5px]">
        {Object.entries(d.metin).map(([k, v]) => (
          <div key={k}>
            <dt className={labelCls}>{FIELD_NAMES[k] ?? k}</dt>
            <dd className="whitespace-pre-line leading-snug">{show(v)}</dd>
          </div>
        ))}
      </dl>
      {d.dusen.length > 0 && <p className="mt-2 text-[11.5px] text-amber-800">{d.dusen.length} cümle denetimden geçmedi ve çıkarıldı (kaynaksız rakam, kanıtsız iddia ya da uydurma alıntı).</p>}
      <div className="mt-2 flex flex-wrap gap-2">
        <button type="button" className={btnGhost} onClick={() => navigator.clipboard?.writeText(text).then(() => toast.success('Kopyalandı.'), () => toast.error('Kopyalanamadı.'))}>
          <Copy aria-hidden className="h-4 w-4" />Kopyala
        </button>
        <button type="button" className={btnGhost} onClick={() => mark.mutate()} disabled={mark.isPending}>
          <Check aria-hidden className="h-4 w-4" />{d.durum === 'taslak' ? 'Kullanıldı olarak işaretle' : 'Taslağa geri al'}
        </button>
      </div>
    </div>
  );
}

export default function AmazonDrafts() {
  const meta = useAmazonMeta();
  const m = meta.data;
  const qc = useQueryClient();
  const [form, setForm] = useState({ stokKodu: '', pazar: 'DE', dil: 'Almanca', tur: 'listeleme' });
  const [page, setPage] = useState(0);
  const list = useQuery({ queryKey: ['amazon', 'drafts', page], queryFn: () => amazonApi.drafts({ page }), enabled: ENGINE_ENABLED, placeholderData: keepPreviousData });
  const create = useMutation({
    mutationFn: () => amazonApi.createDraft(form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['amazon', 'drafts'] });
      toast.success('Taslak hazır. Amazon hesabına gönderilmedi.');
    },
    onError: (e) => toast.error(errText(e, 'Taslak yazılamadı.') ?? ''),
  });
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value }));
  return (
    <AmazonFrame
      title="Listeleme taslakları"
      lead="Tek kitap için hedef pazarda başlık, açıklama ve anahtar kelime, A+ metni ya da çeviri brief'i. Zeki AI CRM kitap kartından yazar; denetimden geçmeyen cümle çıkarılır. Hesaba koymak insanın işidir."
    >
      {m && !m.modelReady && <Note tone="warn">Zeki AI şu an kullanılamıyor.</Note>}
      {m?.me.canDraft && (
        <Panel>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-[1.2fr_0.6fr_0.8fr_1fr_auto] lg:items-end">
            <label className="flex flex-col gap-1"><span className={labelCls}>Stok kodu</span><input className={field} value={form.stokKodu} onChange={set('stokKodu')} placeholder="Logo / CRM stok kodu" /></label>
            <label className="flex flex-col gap-1"><span className={labelCls}>Pazar</span><input className={field} value={form.pazar} onChange={set('pazar')} maxLength={12} /></label>
            <label className="flex flex-col gap-1"><span className={labelCls}>Dil</span><input className={field} value={form.dil} onChange={set('dil')} maxLength={40} /></label>
            <label className="flex flex-col gap-1"><span className={labelCls}>Tür</span>
              <select className={field} value={form.tur} onChange={set('tur')}>
                {Object.entries(m.draftTypes).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </label>
            <button type="button" className={btnPrimary} onClick={() => create.mutate()} disabled={create.isPending || !form.stokKodu.trim() || !form.pazar.trim() || !form.dil.trim()}>
              {create.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Sparkles aria-hidden className="h-4 w-4" />}
              Taslak yaz
            </button>
          </div>
        </Panel>
      )}
      {list.error && <Note tone="err">{errText(list.error, 'Taslaklar açılamadı.')}</Note>}
      {list.isLoading ? <Loading /> : list.data && (
        <Panel>
          {!list.data.total ? <Note tone="info">Henüz taslak yok.</Note> : (
            <div className="flex flex-col gap-2">
              {list.data.items.map((d) => <DraftCard key={d.id} d={d} />)}
            </div>
          )}
          <Pager page={list.data.page} pageSize={list.data.pageSize} total={list.data.total} shown={list.data.items.length} loading={list.isLoading} fetching={list.isFetching} onPage={setPage} />
        </Panel>
      )}
    </AmazonFrame>
  );
}
