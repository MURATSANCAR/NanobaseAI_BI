import { useState, type ReactNode } from 'react';
import { useSearchParams } from 'react-router-dom';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { Download, Loader2, Sparkles } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import SqlInfo from '../components/SqlInfo';
import { Loading, Note, btnGhost, btnPrimary, errText, field, label as labelCls } from '../admin/ui';
import { Kpi, KpiRow } from '../editorial/kit';
import { isoDay, prApi } from './api';
import { Block, Empty, PrFrame } from './parts';

/** Dönem raporu: gönderim ve dönüş, kayıtlı yansıma (ton, mecra türü, kitap, mecra), CRM arşivi ayrı. Sayılar
 *  doğrudan kayıtlardan; Zeki AI yalnız yorum yazar. Erişim/tiraj rakamı yoktur (hiçbir kaynakta tutulmuyor). */

const lastWeek = () => {
  const t = new Date();
  const dow = (t.getDay() + 6) % 7;
  const start = new Date(t.getFullYear(), t.getMonth(), t.getDate() - dow - 7);
  const end = new Date(start.getFullYear(), start.getMonth(), start.getDate() + 6);
  return [isoDay(start), isoDay(end)];
};

export default function PrReport() {
  const [params, setParams] = useSearchParams();
  const [d0, d1] = lastWeek();
  const frm = params.get('bas') || d0;
  const to = params.get('bit') || d1;
  const [withComment, setWithComment] = useState(false);
  const set = (k: string, v: string) => {
    const p = new URLSearchParams(params);
    if (v) p.set(k, v);
    else p.delete(k);
    setParams(p, { replace: true });
    setWithComment(false);
  };
  const meta = useQuery({ queryKey: ['pr', 'meta'], queryFn: prApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const rep = useQuery({ queryKey: ['pr', 'report', frm, to], queryFn: () => prApi.report(frm, to), enabled: ENGINE_ENABLED, placeholderData: keepPreviousData });
  const comment = useQuery({ queryKey: ['pr', 'report-comment', frm, to], queryFn: () => prApi.report(frm, to, true), enabled: ENGINE_ENABLED && withComment, staleTime: 10 * 60_000 });
  const m = meta.data;
  const r = rep.data;
  const pct = (v: number | null) => (v === null ? '—' : new Intl.NumberFormat('tr-TR', { style: 'percent', maximumFractionDigits: 0 }).format(v));

  return (
    <PrFrame
      crumb="Rapor"
      title="Yansıma raporu"
      lead="Varsayılan dönem geçen hafta (pazartesi–pazar). Haftalık özet Yönetim ayarındaki günde e-postayla da gider."
      source="Portal kayıtları + CRM arşivi"
      presence={r ? `${r.coverage.total} yansıma` : '…'}
      aside={
        <div className="flex flex-col gap-2">
          <div className="grid grid-cols-2 gap-2">
            <label className="flex flex-col gap-1">
              <span className={labelCls}>Başlangıç</span>
              <input type="date" className={field} value={frm} onChange={(e) => set('bas', e.target.value)} />
            </label>
            <label className="flex flex-col gap-1">
              <span className={labelCls}>Bitiş</span>
              <input type="date" className={field} value={to} onChange={(e) => set('bit', e.target.value)} />
            </label>
          </div>
          {m?.me.canExport && (
            <div className="flex gap-1.5">
              <a className={`${btnGhost} flex-1`} href={prApi.pdfUrl(frm, to)}><Download aria-hidden className="h-4 w-4" /> PDF</a>
              <a className={`${btnGhost} flex-1`} href={prApi.xlsxUrl(frm, to)}><Download aria-hidden className="h-4 w-4" /> Excel</a>
            </div>
          )}
        </div>
      }
    >
      {rep.isLoading && <Loading />}
      {rep.error && <Note tone="err">{errText(rep.error, 'Rapor açılamadı.')}</Note>}
      {r && m && (
        <>
          <KpiRow>
            <Kpi label="Gönderim" value={r.sends.total.toLocaleString('tr-TR')} help="Dönemde gönderilen (e-posta, kargo, elden, telefon)" info={<SqlInfo k={r.kaynaklar} alan="sends" label="Gönderim" />} />
            <Kpi label="Dönüş" value={r.sends.answered.toLocaleString('tr-TR')} help={`Cevap ya da haber · oran ${pct(r.sends.answerRate)}`} info={<SqlInfo k={r.kaynaklar} alan="sends" label="Dönüş" />} />
            <Kpi label="Kayıtlı yansıma" value={r.coverage.total.toLocaleString('tr-TR')} help={r.pendingCandidates ? `${r.pendingCandidates} aday onay bekliyor` : 'Yayın tarihine göre'} info={<SqlInfo k={r.kaynaklar} alan="coverage" label="Kayıtlı yansıma" />} />
            <Kpi label="CRM arşivi" value={r.archive.total === null ? '—' : r.archive.total.toLocaleString('tr-TR')} help={r.archive.note ?? 'Aynı dönemde CRM haber kaydı'} info={<SqlInfo k={r.kaynaklar} alan="archive" label="CRM arşivi" />} />
          </KpiRow>

          <Block
            title="Dönemin özeti"
            help="Zeki AI yalnız yukarıdaki sayıları yorumlar; listede olmayan sayı yazan cümle düşer."
            action={!withComment && m.modelReady ? (
              <button type="button" className={btnPrimary} onClick={() => setWithComment(true)}>
                <Sparkles aria-hidden className="h-4 w-4" /> Zeki AI yorumu
              </button>
            ) : null}
          >
            {!m.modelReady && <Empty>Zeki AI modeli bu kurulumda bağlı değil.</Empty>}
            {withComment && comment.isLoading && <p className="flex items-center gap-2 text-[12.5px] text-canvas-muted"><Loader2 aria-hidden className="h-4 w-4 animate-spin" /> Yorum yazılıyor…</p>}
            {comment.data?.comment?.metin && <p className="whitespace-pre-line text-[13px] leading-snug">{comment.data.comment.metin}</p>}
            {comment.data && !comment.data.comment?.metin && <Empty>Denetimden geçen cümle kalmadı; sayılar aşağıda.</Empty>}
          </Block>

          <div className="grid grid-cols-1 gap-3 lg:grid-cols-3 lg:gap-4">
            <Dist title="Gönderim durumu" rows={r.sends.byStatus} labels={m.sendStatuses as Record<string, string>} info={<SqlInfo k={r.kaynaklar} alan="sends" label="Gönderim durumu" />} />
            <Dist title="Yansıma tonu" rows={r.coverage.byTone} labels={{ ...m.tones, belirsiz: 'Belirsiz' }} info={<SqlInfo k={r.kaynaklar} alan="coverage" label="Yansıma tonu" />} />
            <Dist title="Mecra türü" rows={r.coverage.byOutletType} labels={{ ...m.outletTypes, belirsiz: 'Belirsiz' }} info={<SqlInfo k={r.kaynaklar} alan="coverage" label="Mecra türü" />} />
          </div>
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2 lg:gap-4">
            <Ranked title="En çok haber alan kitaplar" rows={r.coverage.books.map((b) => ({ name: b.title ?? '—', count: b.count }))} info={<SqlInfo k={r.kaynaklar} alan="coverage" label="Kitaplar" />} />
            <Ranked title="Mecralar" rows={r.coverage.outlets} info={<SqlInfo k={r.kaynaklar} alan="coverage" label="Mecralar" />} />
          </div>
        </>
      )}
    </PrFrame>
  );
}

function Dist({ title, rows, labels, info }: { title: string; rows: Record<string, number>; labels: Record<string, string>; info?: ReactNode }) {
  const total = Object.values(rows).reduce((a, b) => a + b, 0);
  const items = Object.entries(rows).sort((a, b) => b[1] - a[1]);
  return (
    <Block title={title} info={info}>
      {items.length === 0 && <Empty>Kayıt yok.</Empty>}
      <ul className="flex flex-col gap-1.5">
        {items.map(([k, n]) => (
          <li key={k} className="flex flex-col gap-1">
            <span className="flex justify-between text-[12.5px]">
              <span className="font-semibold">{labels[k] ?? k}</span>
              <span className="font-mono font-bold tabular-nums">{n.toLocaleString('tr-TR')}</span>
            </span>
            <span className="h-1.5 overflow-hidden rounded-full bg-slate-100" aria-hidden>
              <span className="block h-full rounded-full bg-canvas-violet" style={{ width: `${total ? (n / total) * 100 : 0}%` }} />
            </span>
          </li>
        ))}
      </ul>
    </Block>
  );
}

function Ranked({ title, rows, info }: { title: string; rows: Array<{ name: string; count: number }>; info?: ReactNode }) {
  return (
    <Block title={title} info={info}>
      {rows.length === 0 && <Empty>Kayıt yok.</Empty>}
      <ol className="flex flex-col divide-y divide-slate-100">
        {rows.map((x, i) => (
          <li key={`${x.name}-${i}`} className="flex justify-between gap-2 py-1.5 text-[12.5px]">
            <span className="min-w-0 break-words">{x.name}</span>
            <span className="font-mono font-bold tabular-nums">{x.count.toLocaleString('tr-TR')}</span>
          </li>
        ))}
      </ol>
    </Block>
  );
}
