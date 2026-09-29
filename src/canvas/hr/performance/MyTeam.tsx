import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Plus } from 'lucide-react';
import { ENGINE_ENABLED } from '../../engine';
import SqlInfo from '../../components/SqlInfo';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText } from '../../admin/ui';
import Sheet from '../../editorial/studio/reader/Sheet';
import { fmtDay, fmtDateTime } from '../hrApi';
import { Block, HrFrame } from '../parts';
import GoalSheet from './GoalSheet';
import { GoalRow } from './parts';
import { REVIEW_TONE, perfApi, thisYear, type PerfMeta, type TeamPerson } from './perfApi';
import { Explain } from '../../components/Explain';

/** M56 Ekibim: yalnız yönetici zincirimdeki kişiler (kayıttaki yönetici bağı). Hedef ilerlemesi, eksik check-in, onay
 *  bekleyen hedef ve revizyon, değerlendirme durumu. Kişi kartı açılınca erişim kaydına yazılır. */

export default function MyTeam() {
  const meta = useQuery({ queryKey: ['hr', 'perf', 'meta'], queryFn: perfApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const [direct, setDirect] = useState(false);
  const team = useQuery({ queryKey: ['hr', 'perf', 'team', direct], queryFn: () => perfApi.team(direct), enabled: ENGINE_ENABLED });
  const [person, setPerson] = useState<TeamPerson | null>(null);
  const d = team.data;
  return (
    <HrFrame
      crumb="Ekibim"
      title="Ekibim"
      lead="Kayıtta yöneticisi olduğunuz kişiler ve onların ekipleri. Başka ekiplerin kaydı burada görünmez; bir kişinin kartını açmanız İK erişim kaydına yazılır."
      aside={
        <div className="flex justify-start gap-2 lg:justify-end">
          <button type="button" className={direct ? btnPrimary : btnGhost} onClick={() => setDirect(!direct)} aria-pressed={direct}>Yalnız doğrudan bağlılar</button>
        </div>
      }
    >
      {team.error && <Note tone="err">{errText(team.error, 'Ekip okunamadı.')}</Note>}
      {team.isLoading && <Loading />}
      {d && !d.me && <Note tone="info">Çalışan kaydınız yok; ekip kayıttaki yönetici bağından kurulur.</Note>}
      {d?.me && !d.people.length && <Note tone="info">Kayıtta size bağlı çalışan yok. Yönetici bağları İK'nın «Çalışan ve KVKK kayıtları» ekranından girilir.</Note>}
      {d && d.people.length > 0 && (
        <div className="flex items-center gap-1 px-1 text-[11px] font-semibold text-canvas-muted">
          Hedef, ilerleme ve değerlendirme sayıları <SqlInfo k={d.kaynaklar} alan="people" label="Ekip sayıları" />
          <Explain label="Kişi kartındaki işaretler">
            <span className="block"><b>ort. %:</b> kişinin hedeflerindeki son ilerleme kayıtlarının ortalaması.</span>
            <span className="block"><b>Onay bekliyor:</b> kişinin onayınıza gönderdiği hedefler.</span>
            <span className="block"><b>Revizyon:</b> kişinin değişiklik istediği hedefler.</span>
            <span className="block"><b>Check-in yok:</b> bu dönem hiç ilerleme kaydı girilmemiş hedefler.</span>
            <span className="block"><b>Dolaylı:</b> size değil, ekibinizdeki bir yöneticiye bağlı kişi.</span>
          </Explain>
        </div>
      )}
      {d && d.people.length > 0 && (
        <ul className="grid grid-cols-1 gap-2 md:grid-cols-2 xl:grid-cols-3">
          {d.people.map((p) => (
            <li key={p.id}>
              <button type="button" onClick={() => setPerson(p)} className="glass-panel flex w-full flex-col gap-1.5 rounded-2xl p-3 text-left shadow-glass-float transition-transform duration-150 ease-out active:scale-[0.98]">
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="min-w-0 flex-1 break-words text-[14px] font-extrabold">{p.name}</span>
                  {!p.direct && <Pill tone="muted">dolaylı · {p.managerName}</Pill>}
                </div>
                <div className="text-[11.5px] text-canvas-muted">{p.title || '—'} · {p.unitName ?? 'Birimsiz'}</div>
                <div className="flex flex-wrap gap-1.5 text-[11.5px]">
                  <Pill tone="violet">{p.goals} hedef{p.avgProgress !== null ? ` · ort. %${p.avgProgress}` : ''}</Pill>
                  {p.pendingApproval > 0 && <Pill tone="warn">{p.pendingApproval} onay bekliyor</Pill>}
                  {p.openRevisions > 0 && <Pill tone="warn">{p.openRevisions} revizyon</Pill>}
                  {p.noCheckin > 0 && <Pill tone="err">{p.noCheckin} hedefte check-in yok</Pill>}
                  {p.reviews.map((r) => <Pill key={r.id} tone={REVIEW_TONE[r.state]}>{r.stateLabel}</Pill>)}
                </div>
              </button>
            </li>
          ))}
        </ul>
      )}
      {d?.gaps && d.gaps.length > 0 && (
        <Block title={`Yöneticisi kayıtlı olmayan ${d.gaps.length} çalışan`} info={<SqlInfo k={d.kaynaklar} alan="gaps" label="Yöneticisi kayıtlı olmayan çalışan" />} help="Bu kişiler hiçbir yöneticinin «Ekibim»inde görünmez ve değerlendirme dönemine yöneticisiz girer. Yönetici bağını «Çalışan ve KVKK kayıtları»ndan girin.">
          <ul className="grid grid-cols-1 gap-1 text-[12.5px] sm:grid-cols-2 lg:grid-cols-3">
            {d.gaps.map((x) => <li key={x.id} className="break-words">{x.name} <span className="text-canvas-muted">· {x.unitName ?? 'Birimsiz'}</span></li>)}
          </ul>
        </Block>
      )}
      {person && meta.data && <PersonSheet p={person} canWrite={meta.data.me.can.goalWrite} meta={meta.data} onClose={() => setPerson(null)} />}
    </HrFrame>
  );
}

function PersonSheet({ p, canWrite, meta, onClose }: { p: TeamPerson; canWrite: boolean; meta: PerfMeta; onClose: () => void }) {
  const q = useQuery({ queryKey: ['hr', 'perf', 'person', p.id], queryFn: () => perfApi.person(p.id) });
  const tree = useQuery({ queryKey: ['hr', 'perf', 'goals', 'year', thisYear()], queryFn: () => perfApi.goals({ year: thisYear() }) });
  const [goal, setGoal] = useState<string | 'new' | null>(null);
  const d = q.data;
  return (
    <Sheet open modal wide onClose={onClose} title={p.name} subtitle={`${p.title || '—'} · ${p.unitName ?? 'Birimsiz'}`}>
      {q.error && <Note tone="err">{errText(q.error, 'Kişi kartı okunamadı.')}</Note>}
      {!d && !q.error && <Loading />}
      {d && (
        <div className="flex flex-col gap-4">
          <div>
            <div className="mb-1 flex items-center justify-between gap-2">
              <div className="flex items-center gap-1 text-[13px] font-extrabold">Hedefler<SqlInfo k={d.kaynaklar} alan="goals" label="Hedef değeri ve ilerleme" /></div>
              {canWrite && <button type="button" className={btnGhost} onClick={() => setGoal('new')}><Plus aria-hidden className="h-4 w-4" />Hedef ekle</button>}
            </div>
            {!d.goals.length && <div className="text-[12px] text-canvas-muted">Bu kişinin {thisYear()} için hedefi yok.{canWrite ? ' «Hedef ekle» ile ekleyebilirsiniz.' : ''}</div>}
            <ul className="flex flex-col gap-1.5">{d.goals.map((g) => <li key={g.id}><GoalRow g={g} onOpen={() => setGoal(g.id)} /></li>)}</ul>
          </div>
          <div>
            <div className="mb-1 text-[13px] font-extrabold">Değerlendirmeler</div>
            {!d.reviews.length && <div className="text-[12px] text-canvas-muted">Bu kişi için açılmış değerlendirme yok.</div>}
            <ul className="flex flex-col gap-1.5">
              {d.reviews.map((r) => (
                <li key={r.id}>
                  <Link to={`/ik/ekibim/degerlendirme/${r.id}`} className="flex min-h-11 flex-wrap items-center gap-2 rounded-xl bg-slate-50 px-3 py-2 text-[13px] transition-colors duration-150 hover:bg-slate-100">
                    <span className="min-w-0 flex-1 font-bold">{r.cycleName}</span>
                    {r.mine && <Pill tone="violet">değerlendiren sizsiniz</Pill>}
                    <Pill tone={REVIEW_TONE[r.state]}>{r.stateLabel}</Pill>
                  </Link>
                </li>
              ))}
            </ul>
          </div>
          {d.workSummaries && d.workSummaries.length > 0 && (
            <div>
              <div className="mb-1 flex items-center gap-1 text-[13px] font-extrabold">İş kayıtları özetleri<SqlInfo k={d.kaynaklar} alan="workSummaries" label="İş kayıtları özeti" /></div>
              <ul className="flex flex-col gap-1.5">
                {d.workSummaries.map((w) => (
                  <li key={w.id} className="rounded-xl bg-slate-50 px-3 py-2 text-[12.5px]">
                    <div className="text-[11.5px] text-canvas-muted">{fmtDay(w.periodStart)} – {fmtDay(w.periodEnd)} · {fmtDateTime(w.generatedAt)}{w.shownToEmployeeAt ? ' · çalışan gördü' : ''}</div>
                    <div className="break-words">{w.text}</div>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
      {goal !== null && (
        <GoalSheet key={goal} goalId={goal === 'new' ? null : goal} init={{ level: 'kisi', ownerEmployeeId: p.id, period: thisYear() }}
          meta={meta} parents={tree.data?.items ?? []} onClose={() => { setGoal(null); void q.refetch(); }} />
      )}
    </Sheet>
  );
}
