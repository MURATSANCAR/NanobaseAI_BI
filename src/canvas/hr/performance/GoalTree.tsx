import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Plus } from 'lucide-react';
import { ENGINE_ENABLED } from '../../engine';
import { Loading, Note, btnGhost, errText, field } from '../../admin/ui';
import { Block, HrFrame } from '../parts';
import GoalSheet from './GoalSheet';
import { GoalRow } from './parts';
import { perfApi, thisYear, type Goal, type Level } from './perfApi';

/** M56 Hedef ağacı: şirket → birim → kişi. Herkes kendi zincirini görür; İK ve dönem yöneticisi hepsini. Üst hedefe bağlı
 *  olmayan birim/kişi hedefleri ayrı listede işaretli. */

export default function GoalTree() {
  const meta = useQuery({ queryKey: ['hr', 'perf', 'meta'], queryFn: perfApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const [year, setYear] = useState(thisYear());
  const q = useQuery({ queryKey: ['hr', 'perf', 'goals', 'year', year], queryFn: () => perfApi.goals({ year }), enabled: ENGINE_ENABLED });
  const [open, setOpen] = useState<{ id: string | null; level: Level; parent?: string | null } | null>(null);
  const goals = q.data?.items ?? [];
  const byParent = useMemo(() => {
    const m = new Map<string, Goal[]>();
    goals.forEach((g) => {
      const k = g.parentGoalId ?? '';
      m.set(k, [...(m.get(k) ?? []), g]);
    });
    return m;
  }, [goals]);
  const ids = new Set(goals.map((g) => g.id));
  const roots = goals.filter((g) => g.level === 'sirket');
  // Görebildiği ama üstü görünmeyen (ya da bağlanmamış) birim/kişi hedefleri.
  const loose = goals.filter((g) => g.level !== 'sirket' && (!g.parentGoalId || !ids.has(g.parentGoalId)));
  const can = meta.data?.me.can;
  const years = [Number(thisYear()) + 1, Number(thisYear()), Number(thisYear()) - 1].map(String);

  const Node = ({ g, depth }: { g: Goal; depth: number }) => (
    <li className="flex flex-col gap-1.5" style={{ paddingLeft: depth ? Math.min(depth, 3) * 12 : 0 }}>
      <GoalRow g={g} showOwner onOpen={() => setOpen({ id: g.id, level: g.level })} />
      {(byParent.get(g.id) ?? []).length > 0 && (
        <ul className="flex flex-col gap-1.5 border-l-2 border-canvas-violet/15 pl-2">
          {(byParent.get(g.id) ?? []).map((c) => <Node key={c.id} g={c} depth={depth + 1} />)}
        </ul>
      )}
    </li>
  );

  return (
    <HrFrame
      crumb="Hedefler"
      title="Hedef ağacı"
      lead="Şirket hedeflerinden birim ve kişi hedeflerine iniş. Kişi hedefini sahibi ve yönetici zinciri görür; birim ve şirket hedefleri herkese açıktır. Üst hedefe bağlanmamış hedefler ayrıca listelenir."
      aside={
        <div className="flex flex-wrap items-center justify-start gap-2 lg:justify-end">
          <select className={`${field} w-auto`} value={year} onChange={(e) => setYear(e.target.value)} aria-label="Yıl">
            {years.map((y) => <option key={y} value={y}>{y}</option>)}
          </select>
          {can?.goalApprove && <button type="button" className={btnGhost} onClick={() => setOpen({ id: null, level: 'sirket' })}><Plus aria-hidden className="h-4 w-4" />Şirket hedefi</button>}
          {(can?.goalApprove || (can?.goalWrite && (meta.data?.me.managedUnits.length ?? 0) > 0)) && (
            <button type="button" className={btnGhost} onClick={() => setOpen({ id: null, level: 'birim' })}><Plus aria-hidden className="h-4 w-4" />Birim hedefi</button>
          )}
        </div>
      }
    >
      {q.error && <Note tone="err">{errText(q.error, 'Hedefler okunamadı.')}</Note>}
      {q.isLoading && <Loading />}
      {q.data && !goals.length && <Note tone="info">{year} için hedef yok.</Note>}
      {roots.length > 0 && (
        <Block title="Şirket hedefleri">
          <ul className="flex flex-col gap-2">{roots.map((g) => <Node key={g.id} g={g} depth={0} />)}</ul>
        </Block>
      )}
      {loose.length > 0 && (
        <Block title="Üst hedefe bağlanmamış" help="Bu hedefler şirket hedefine bağlanmamış (ya da bağlı olduğu hedef sizin görebileceğiniz bir hedef değil). Hedef kartından Zeki AI hizalama önerisi alabilirsiniz.">
          <ul className="flex flex-col gap-2">{loose.map((g) => <Node key={g.id} g={g} depth={0} />)}</ul>
        </Block>
      )}
      {open && meta.data && (
        <GoalSheet key={`${open.id}-${open.level}`} goalId={open.id} init={{ level: open.level, period: year, unitId: meta.data.me.managedUnits[0] ?? null }}
          meta={meta.data} parents={goals} onClose={() => setOpen(null)} />
      )}
    </HrFrame>
  );
}
