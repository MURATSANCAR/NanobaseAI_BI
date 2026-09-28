import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ENGINE_ENABLED } from '../engine';
import { InfoLabel } from '../components/SqlInfo';
import { kaynakOf } from '../components/kaynakOf';
import { Note, Pill, btnGhost, btnPrimary, errText, field, label as labelCls } from '../admin/ui';
import { Pager, Panel } from '../editorial/kit';
import { VERDICT_TONE, fmtAt, mqApi, type FeedbackItem, type Meta, type TriageState } from './api';
import { Empty, SqlBox } from './parts';

/** Kullanıcıların cevaplara verdiği hükümler. Kısmen/Yanlış model ekibinin kuyruğuna düşer: kural bir sınıf önerir,
 *  karar yetkisi olan sınıfı düzeltir ya da kapatır. Sonuç satırları (kişisel veri içerebilir) burada gösterilmez. */
export default function FeedbackQueue({ meta }: { meta: Meta }) {
  const [verdict, setVerdict] = useState('kismen,yanlis');
  const [state, setState] = useState<string>('yeni');
  const [page, setPage] = useState(0);
  const q = useQuery({ queryKey: ['mq', 'queue', verdict, state, page], queryFn: () => mqApi.queue({ verdict, state, page }), enabled: ENGINE_ENABLED });
  return (
    <Panel>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:w-[560px]">
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Hüküm</span>
          <select className={field} value={verdict} onChange={(e) => { setVerdict(e.target.value); setPage(0); }}>
            <option value="kismen,yanlis">Kısmen ve Yanlış</option>
            <option value="yanlis">Yalnız Yanlış</option>
            <option value="kismen">Yalnız Kısmen</option>
            <option value="dogru">Doğru</option>
            <option value="">Hepsi</option>
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Durum</span>
          <select className={field} value={state} onChange={(e) => { setState(e.target.value); setPage(0); }}>
            {Object.entries(meta.triage).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            <option value="">Hepsi</option>
          </select>
        </label>
      </div>
      {!meta.me.canDecide && <div className="mt-2"><Note tone="info">Sınıflama ve kapatma «Geri bildirim ve hata sınıfı kararı» yetkisiyle yapılır.</Note></div>}
      <div className="mt-3 flex flex-col gap-2">
        {/* Sekme rozetindeki sayı (yeni Kısmen/Yanlış) da bu okumadır. */}
        {q.data && (
          <div className="flex justify-end text-[11px] text-canvas-muted">
            <InfoLabel k={kaynakOf(q.data)} alan="items" label="Geri bildirim sayıları">Kayıt ve satır sayıları</InfoLabel>
          </div>
        )}
        {q.isLoading && <Empty>Yükleniyor…</Empty>}
        {q.error && <Note tone="err">{errText(q.error, 'Kuyruk okunamadı.')}</Note>}
        {q.data && !q.data.items.length && <Empty>Bu süzgeçte bildirim yok.</Empty>}
        {q.data?.items.map((f) => <Item key={f.id} f={f} meta={meta} />)}
      </div>
      {q.data && q.data.total > q.data.size && (
        <Pager page={page} pageSize={q.data.size} total={q.data.total} shown={q.data.items.length} loading={q.isLoading} fetching={q.isFetching} onPage={setPage} />
      )}
    </Panel>
  );
}

function Item({ f, meta }: { f: FeedbackItem; meta: Meta }) {
  const qc = useQueryClient();
  const [klass, setKlass] = useState(f.effectiveKlass ?? '');
  const [note, setNote] = useState(f.handleNote ?? '');
  const decide = useMutation({
    mutationFn: (b: { klass?: string; triageState?: TriageState; note?: string }) => mqApi.decide(f.id, b),
    onSuccess: () => {
      toast.success('Kaydedildi.');
      void qc.invalidateQueries({ queryKey: ['mq', 'queue'] });
      void qc.invalidateQueries({ queryKey: ['mq', 'classes'] });
    },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? 'Kaydedilemedi.'),
  });
  const labelOf = (k: string | null) =>
    !k ? '—' : meta.classes.find((c) => c.klass === k)?.label ?? (k === meta.unclassified ? 'Sınıflanamadı' : k);
  const qq = f.query;
  return (
    <article className="rounded-2xl border border-slate-100 bg-white/80 p-3">
      <div className="flex flex-wrap items-center gap-1.5 text-[11.5px] text-canvas-muted">
        <Pill tone={VERDICT_TONE[f.verdict]}>{f.verdictLabel}</Pill>
        <Pill tone={f.triageState === 'kapandi' ? 'muted' : f.triageState === 'siniflandi' ? 'violet' : 'warn'}>{f.triageLabel}</Pill>
        <span className="font-mono tabular-nums">{fmtAt(f.at)}</span>
        <span>· {f.username}</span>
        {f.effectiveKlass && (
          <span>· {labelOf(f.effectiveKlass)}{f.klassSource === 'kural' ? ' (kural önerisi)' : ''}</span>
        )}
      </div>
      <div className="mt-1 break-words text-[13px] font-extrabold leading-snug">{qq?.question ?? 'Soru kaydı bulunamadı'}</div>
      {f.comment && <blockquote className="mt-1 border-l-2 border-canvas-violet/40 pl-2 text-[12px] italic">{f.comment}</blockquote>}
      {qq && (
        <details className="mt-1.5 text-[12px]">
          <summary className="min-h-11 cursor-pointer font-bold text-canvas-muted sm:min-h-0">Verilen cevap</summary>
          <div className="mt-1 flex flex-col gap-1.5">
            <div className="break-words">{qq.answerSummary ?? qq.error ?? '—'}</div>
            <div className="text-[11px] text-canvas-muted">
              {qq.rowCount !== null ? `${qq.rowCount} satır · ` : ''}katalog v{qq.catalogVersion ?? '—'} · {fmtAt(qq.createdAt)}
            </div>
            <SqlBox sql={qq.sql} />
          </div>
        </details>
      )}
      {meta.me.canDecide && f.verdict !== 'dogru' && (
        <div className="mt-2 grid grid-cols-1 gap-2 md:grid-cols-[220px_minmax(0,1fr)_auto] md:items-end">
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Sınıf</span>
            <select className={field} value={klass} onChange={(e) => setKlass(e.target.value)}>
              <option value="">—</option>
              {meta.classes.filter((c) => c.active).map((c) => <option key={c.klass} value={c.klass}>{c.label}</option>)}
              <option value={meta.unclassified}>Sınıflanamadı</option>
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Not</span>
            <input className={field} value={note} maxLength={2000} onChange={(e) => setNote(e.target.value)} placeholder="Ne yapıldı / yapılacak" />
          </label>
          <div className="flex flex-wrap gap-1.5">
            <button type="button" className={btnPrimary} disabled={decide.isPending || !klass}
              onClick={() => decide.mutate({ klass, triageState: 'siniflandi', note })}>Sınıfla</button>
            <button type="button" className={btnGhost} disabled={decide.isPending}
              onClick={() => decide.mutate({ ...(klass ? { klass } : {}), triageState: 'kapandi', note })}>Kapat</button>
          </div>
        </div>
      )}
    </article>
  );
}
