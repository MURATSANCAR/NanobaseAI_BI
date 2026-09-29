import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Search, Sparkles } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import SqlInfo from '../components/SqlInfo';
import { Loading, Note, TableWrap, btnGhost, btnPrimary, errText, field, td, th } from '../admin/ui';
import { Kpi, KpiRow } from '../editorial/kit';
import { evApi, fmtDay, fmtInt, fmtPct, type ClassKey, type TypeRow } from './api';
import { ClassPill, EventsFrame } from './parts';

/** CRM etkinlik tipi eşlemesi (ayar): 371 tipin hangisinin fuar / imza günü / söyleşi / okul etkinliği / satış ziyareti /
 *  diğer olduğu insan kararıdır. Zeki AI yalnız öneri yazar (olasılıkla); takvim yalnız onaylanan sınıfı kullanır. */

type Filter = 'karar' | 'oneri' | 'hepsi';

export default function TypeMap() {
  const qc = useQueryClient();
  const meta = useQuery({ queryKey: ['ev', 'meta'], queryFn: evApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const list = useQuery({
    queryKey: ['ev', 'type-map'],
    queryFn: evApi.typeMap,
    enabled: ENGINE_ENABLED,
    refetchInterval: (q) => (q.state.data?.job.state === 'calisiyor' ? 5000 : false),
  });
  const [draft, setDraft] = useState<Record<string, ClassKey | null>>({});
  const [filter, setFilter] = useState<Filter>('karar');
  const [q, setQ] = useState('');
  useEffect(() => setDraft({}), [list.data?.counts.decided]);

  const save = useMutation({
    mutationFn: () => evApi.setTypes(Object.entries(draft).map(([id, c]) => ({ id, class: c }))),
    onSuccess: (r) => {
      toast.success(`${r.changed} tip kaydedildi.`);
      setDraft({});
      qc.invalidateQueries({ queryKey: ['ev'] });
    },
    onError: (e) => toast.error(errText(e, 'Eşleme kaydedilemedi.') ?? ''),
  });
  const suggest = useMutation({
    mutationFn: (all: boolean) => evApi.suggestTypes(all),
    onSuccess: () => {
      toast.success('Zeki AI tipleri sınıflıyor; öneriler geldikçe tabloya düşer.');
      qc.invalidateQueries({ queryKey: ['ev', 'type-map'] });
    },
    onError: (e) => toast.error(errText(e, 'Öneri başlatılamadı.') ?? ''),
  });

  const m = meta.data;
  const d = list.data;
  const rows = useMemo(() => {
    const t = q.trim().toLocaleLowerCase('tr');
    return (d?.items ?? []).filter((r) => {
      if (t && !r.name.toLocaleLowerCase('tr').includes(t)) return false;
      if (filter === 'karar') return !r.class;
      if (filter === 'oneri') return !r.class && !!r.suggested;
      return true;
    });
  }, [d, q, filter]);
  const pending = Object.keys(draft).length;
  const job = d?.job;
  const edit = !!m?.me.canEdit;

  const acceptAll = () => {
    const next = { ...draft };
    rows.forEach((r) => {
      if (!r.class && r.suggested) next[r.id] = r.suggested;
    });
    setDraft(next);
  };

  return (
    <EventsFrame
      crumb="Fuar ve etkinlik"
      title="CRM etkinlik tipi eşlemesi"
      lead="CRM'deki etkinlik tiplerinin hangisinin fuar, imza günü, söyleşi, okul etkinliği ya da satış ziyareti olduğu burada belirlenir. Zeki AI öneri yazar; karar sizin. Takvim ve sonuç raporu yalnız onaylanan eşlemeyi kullanır."
      source="CRM etkinlik tipi"
      presence={d ? `${d.counts.decided}/${d.counts.total} karar` : '…'}
      aside={edit ? (
        <div className="flex flex-wrap gap-2 lg:justify-end">
          <button type="button" className={btnGhost} disabled={suggest.isPending || job?.state === 'calisiyor'} onClick={() => suggest.mutate(false)}>
            <Sparkles aria-hidden className="h-4 w-4" />
            {job?.state === 'calisiyor' ? `Zeki AI sınıflıyor ${job.done ?? 0}/${job.total ?? '…'}` : 'Zeki AI önerisi al'}
          </button>
          <button type="button" className={btnPrimary} disabled={!pending || save.isPending} onClick={() => save.mutate()}>
            {pending ? `${pending} kararı kaydet` : 'Kaydet'}
          </button>
        </div>
      ) : undefined}
    >
      {list.isLoading && <Loading />}
      {list.error && <Note tone="err">{errText(list.error, 'Tipler okunamadı.')}</Note>}
      {job?.state === 'hata' && <Note tone="warn">{job.error}</Note>}
      {job?.state === 'bitti' && job.result && (
        <Note tone="info">Son öneri turu: {job.result.asked} tip soruldu{job.result.unsure ? `, ${job.result.unsure} tipte Zeki AI seçim yapamadı` : ''}.</Note>
      )}
      {d && m && (
        <>
          <KpiRow>
            <Kpi label="Karar bekleyen" value={fmtInt(d.counts.total - d.counts.decided)} help="Sınıfı belirlenmemiş tip" active={filter === 'karar'} onClick={() => setFilter('karar')} info={<SqlInfo k={d.kaynaklar} alan="counts" label="Karar bekleyen" />}
              explain="Hangi sınıfa (fuar, imza günü, söyleşi…) girdiğine henüz karar verilmemiş CRM etkinlik tipleri. Bu tiplerin kayıtları takvimde «Sınıfsız» görünür." />
            <Kpi label="Öneri hazır" value={fmtInt(d.counts.suggested)} help="Zeki AI önerisi olan, karar bekleyen" active={filter === 'oneri'} onClick={() => setFilter('oneri')} info={<SqlInfo k={d.kaynaklar} alan="counts" label="Öneri hazır" />} />
            <Kpi label="Karar verilen" value={fmtInt(d.counts.decided)} help="Takvimde kullanılan eşleme" active={filter === 'hepsi'} onClick={() => setFilter('hepsi')} info={<SqlInfo k={d.kaynaklar} alan="counts" label="Karar verilen" />} />
            <Kpi label="Toplam tip" value={fmtInt(d.counts.total)} help="CRM etkinlik tipi (etkin ve etkin olmayan)" info={<SqlInfo k={d.kaynaklar} alan="items" label="Toplam tip, kayıt sayısı ve öneri olasılığı" />} />
          </KpiRow>
          <section className="glass-panel rounded-2xl p-3 shadow-glass-float sm:rounded-3xl sm:p-4">
            <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-center">
              <span className="relative flex flex-1 items-center">
                <Search aria-hidden className="pointer-events-none absolute left-3 h-4 w-4 text-canvas-muted" />
                <input className={`${field} pl-9`} value={q} placeholder="Tip adı" onChange={(e) => setQ(e.target.value)} />
              </span>
              {edit && filter !== 'hepsi' && rows.some((r) => !r.class && r.suggested) && (
                <button type="button" className={btnGhost} onClick={acceptAll}>Görünen önerileri seç</button>
              )}
            </div>
            <TableWrap>
              <thead>
                <tr>
                  <th className={th}>Tip</th>
                  <th className={`${th} text-right`}>Kayıt</th>
                  <th className={th}>Son</th>
                  <th className={th}>Zeki AI önerisi</th>
                  <th className={th}>Sınıf (karar)</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r: TypeRow) => {
                  const cur = r.id in draft ? draft[r.id] : r.class;
                  return (
                    <tr key={r.id} className={`border-t border-slate-100 ${r.id in draft ? 'bg-amber-50/60' : ''}`}>
                      <td className={td}><div className="max-w-[320px] truncate font-bold">{r.name}</div>{!r.active && <div className="text-[10.5px] text-canvas-muted">CRM'de etkin değil</div>}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(r.count)}</td>
                      <td className={`${td} whitespace-nowrap text-[11.5px]`}>{fmtDay(r.last)}</td>
                      <td className={td}>
                        {r.suggested ? (
                          <span className="inline-flex items-center gap-1.5">
                            <ClassPill cls={r.suggested} label={m.classes[r.suggested]} suggested />
                            <span className="font-mono text-[10.5px] tabular-nums text-canvas-muted">{fmtPct(r.suggestedProb)}</span>
                          </span>
                        ) : <span className="text-canvas-muted">—</span>}
                      </td>
                      <td className={td}>
                        {edit ? (
                          <select aria-label={`${r.name} sınıfı`} value={cur ?? ''} onChange={(e) => setDraft((x) => ({ ...x, [r.id]: (e.target.value || null) as ClassKey | null }))}
                            className="min-h-9 rounded-lg border border-slate-200 bg-white px-2 text-base font-bold sm:text-[12px]">
                            <option value="">Karar yok</option>
                            {(Object.entries(m.classes) as Array<[ClassKey, string]>).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                          </select>
                        ) : cur ? <ClassPill cls={cur} label={m.classes[cur]} /> : <span className="text-canvas-muted">karar yok</span>}
                        {r.decidedBy && <div className="mt-0.5 text-[10.5px] text-canvas-muted">{r.decidedBy} · {fmtDay(r.decidedAt?.slice(0, 10))}</div>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </TableWrap>
            {rows.length === 0 && <p className="py-4 text-[12.5px] text-canvas-muted">Bu süzgeçte tip yok.</p>}
          </section>
        </>
      )}
    </EventsFrame>
  );
}
