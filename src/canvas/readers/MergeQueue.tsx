import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Check, X } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, Section, btnGhost, btnPrimary, errText } from '../admin/ui';
import { fmtDay, fmtInt, readersApi, type Candidate, type ReaderSummary } from './api';
import { ConsentPill, ROOT, useMeta } from './parts';
import SqlInfo from '../components/SqlInfo';
import { EmptyHint } from '../components/Explain';

const TABS = [
  { id: 'bekliyor', label: 'Bekleyen' },
  { id: 'ayni', label: 'Aynı kişi' },
  { id: 'farkli', label: 'Farklı kişi' },
] as const;

/** Belirsiz eşleşme kuyruğu: adı ve ili aynı, e-posta/telefonu farklı okur çiftleri. Karar insanın. */
export default function MergeQueue() {
  const [tab, setTab] = useState<(typeof TABS)[number]['id']>('bekliyor');
  const [page, setPage] = useState(0);
  const meta = useMeta();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['readers', 'candidates', tab, page], queryFn: () => readersApi.candidates(tab, page), enabled: ENGINE_ENABLED });
  const decide = useMutation({
    mutationFn: (v: { id: string; karar: 'ayni' | 'farkli' }) => readersApi.decide(v.id, v.karar),
    onSuccess: (r) => {
      toast.success(r.status === 'ayni' ? 'İki okur birleştirildi.' : 'Farklı kişi olarak kaydedildi; bu çift bir daha önerilmez.');
      qc.invalidateQueries({ queryKey: ['readers'] });
    },
    onError: (e) => toast.error(errText(e, 'Karar kaydedilemedi.') ?? ''),
  });
  const canMerge = !!meta.data?.me.canMerge;
  const d = q.data;
  return (
    <Section
      title="Birleştirme kuyruğu"
      help="Aynı e-posta ya da telefonu olan kayıtlar kendiliğinden birleşir. Burada adı ve ili aynı ama iletişim bilgisi farklı çiftler var; aynı kişi mi, değil mi siz karar verirsiniz. Benzerlik puanı sabit kurala göre hesaplanır, kişisel veri Zeki AI'a gönderilmez."
    >
      <div className="flex flex-wrap gap-1" role="tablist">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={tab === t.id}
            onClick={() => { setTab(t.id); setPage(0); }}
            className={`min-h-11 rounded-xl px-3 text-[12.5px] font-extrabold transition-colors duration-150 sm:min-h-9 ${tab === t.id ? 'bg-canvas-violet text-white' : 'bg-slate-100 hover:bg-slate-200'}`}
          >
            {t.label}
          </button>
        ))}
      </div>
      {q.isLoading && <Loading />}
      {q.error && <Note tone="err">{errText(q.error, 'Kuyruk açılamadı.')}</Note>}
      {d && d.items.length === 0 && <EmptyHint title={tab === 'bekliyor' ? 'Karar bekleyen çift yok' : 'Bu durumda çift yok'} why={tab === 'bekliyor' ? 'Yeni aday çiftler her gece kaynaklar okunduktan sonra burada belirir.' : 'Bu duruma karar verilmiş çift henüz yok.'} />}
      <ul className="flex flex-col gap-2">
        {d?.items.map((c) => (
          <PairRow key={c.id} c={c} canMerge={canMerge && tab === 'bekliyor'} busy={decide.isPending && decide.variables?.id === c.id}
            onDecide={(karar) => decide.mutate({ id: c.id, karar })} />
        ))}
      </ul>
      {d && d.total > d.pageSize && (
        <div className="flex items-center justify-between gap-2 text-[12px] font-semibold text-canvas-muted">
          <span className="inline-flex items-center gap-1">{fmtInt(d.page * d.pageSize + 1)}–{fmtInt(Math.min(d.total, (d.page + 1) * d.pageSize))} / {fmtInt(d.total)}<SqlInfo k={d.kaynaklar} alan="total" label="Aday çift sayısı" /></span>
          <div className="flex gap-1">
            <button type="button" className={btnGhost} disabled={page === 0} onClick={() => setPage((p) => p - 1)}>Önceki</button>
            <button type="button" className={btnGhost} disabled={(page + 1) * d.pageSize >= d.total} onClick={() => setPage((p) => p + 1)}>Sonraki</button>
          </div>
        </div>
      )}
    </Section>
  );
}

function PairRow({ c, canMerge, busy, onDecide }: { c: Candidate; canMerge: boolean; busy: boolean; onDecide: (k: 'ayni' | 'farkli') => void }) {
  return (
    <li className="rounded-2xl border border-slate-100 bg-white/80 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap gap-1 text-[11.5px] font-semibold">
          {c.reasons.map((r) => <span key={r} className="rounded-md bg-slate-100 px-1.5 py-0.5">{r}</span>)}
        </div>
        <span className="font-mono text-[11.5px] text-canvas-muted" title="Benzerlik puanı (0–100): yükseldikçe iki kaydın aynı kişi olma ihtimali artar">benzerlik {Math.round(c.score * 100)}</span>
      </div>
      <div className="mt-2 grid gap-2 sm:grid-cols-2">
        <Side r={c.a} />
        <Side r={c.b} />
      </div>
      {canMerge ? (
        <div className="mt-2 flex flex-wrap gap-2">
          <button type="button" className={btnPrimary} disabled={busy} onClick={() => onDecide('ayni')}><Check aria-hidden className="h-4 w-4" />Aynı kişi</button>
          <button type="button" className={btnGhost} disabled={busy} onClick={() => onDecide('farkli')}><X aria-hidden className="h-4 w-4" />Farklı kişi</button>
        </div>
      ) : c.decidedBy ? (
        <p className="mt-2 text-[11.5px] text-canvas-muted">{c.decidedBy} · {fmtDay(c.decidedAt)}</p>
      ) : null}
    </li>
  );
}

function Side({ r }: { r: ReaderSummary }) {
  return (
    <Link to={`${ROOT}/kisi/${r.id}`} className="rounded-xl bg-slate-50 p-2.5 transition-colors duration-150 hover:bg-slate-100">
      <div className="font-mono text-[12px] font-bold">{r.id}</div>
      <div className="text-[11.5px] text-canvas-muted">{(r.sources ?? []).join(' + ')} · {r.age != null ? `${r.age} yaş` : 'yaş yok'} · son temas {fmtDay(r.lastTouch)}</div>
      {r.consent && (
        <div className="mt-1 flex flex-wrap gap-1">
          <ConsentPill prefix="E-posta" status={r.consent.email} />
          <ConsentPill prefix="SMS" status={r.consent.sms} />
        </div>
      )}
    </Link>
  );
}
