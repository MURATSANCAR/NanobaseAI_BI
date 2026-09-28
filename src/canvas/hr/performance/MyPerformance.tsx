import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Plus } from 'lucide-react';
import { ENGINE_ENABLED } from '../../engine';
import SqlInfo from '../../components/SqlInfo';
import { Loading, Note, Pill, btnPrimary, errText } from '../../admin/ui';
import { fmtDay, fmtDateTime } from '../hrApi';
import { Block, HrFrame } from '../parts';
import GoalSheet from './GoalSheet';
import { GoalRow } from './parts';
import { REVIEW_TONE, perfApi, thisYear } from './perfApi';

/** M56 Performansım: hedeflerim ve bağlı oldukları üst hedef, açık görevlerim (öz değerlendirme, yorum, check-in),
 *  değerlendirmelerim ve hakkımda üretilen iş kayıtları özeti (KVKK md. 11: hakkımda kullanılan veriyi görürüm). */

export default function MyPerformance() {
  const meta = useQuery({ queryKey: ['hr', 'perf', 'meta'], queryFn: perfApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const me = useQuery({ queryKey: ['hr', 'perf', 'me'], queryFn: perfApi.me, enabled: ENGINE_ENABLED });
  const tree = useQuery({ queryKey: ['hr', 'perf', 'goals', 'year', thisYear()], queryFn: () => perfApi.goals({ year: thisYear() }), enabled: ENGINE_ENABLED });
  const [open, setOpen] = useState<string | 'new' | null>(null);
  const d = me.data;
  return (
    <HrFrame
      crumb="Performansım"
      title="Performansım"
      lead="Hedefleriniz ve şirket hedefine bağı, çeyrek check-in'leri, değerlendirmeleriniz ve hakkınızda hazırlanan iş kayıtları özeti. Burada gördüğünüz her şey yöneticinizin gördüğüyle aynıdır; puanı sistem değil yöneticiniz verir."
      aside={d?.employee ? (
        <div className="flex justify-start lg:justify-end">
          <button type="button" className={btnPrimary} onClick={() => setOpen('new')}><Plus aria-hidden className="h-4 w-4" />Yeni hedef</button>
        </div>
      ) : undefined}
    >
      {me.error && <Note tone="err">{errText(me.error, 'Performans kaydınız okunamadı.')}</Note>}
      {me.isLoading && <Loading />}
      {d && !d.employee && <Note tone="info">Çalışan kaydınız henüz yok. İnsan Kaynakları çalışan kaydınızı açınca hedef ve değerlendirmeleriniz burada görünür.</Note>}
      {d?.employee && (
        <>
          <div className="text-[12.5px] text-canvas-muted">{d.employee.displayName} · {d.employee.unitName ?? 'Birimsiz'} · Yöneticiniz: {d.employee.managerName ?? 'kayıtlı değil'}</div>
          {d.tasks.length > 0 && (
            <Block title="Sizi bekleyenler">
              <ul className="flex flex-col gap-1.5">
                {d.tasks.map((t, i) => (
                  <li key={i}>
                    {t.reviewId ? (
                      <Link to={`/ik/performansim/degerlendirme/${t.reviewId}`} className="flex min-h-11 flex-wrap items-center gap-2 rounded-xl bg-white/80 px-3 py-2 text-[13px] font-semibold transition-colors duration-150 hover:bg-white">
                        <span className="min-w-0 flex-1 break-words">{t.label}</span>
                        {t.daysLeft !== null && <Pill tone={t.daysLeft <= 3 ? 'err' : 'warn'}>{t.daysLeft < 0 ? 'süresi geçti' : `${t.daysLeft} gün`}</Pill>}
                      </Link>
                    ) : (
                      <button type="button" onClick={() => setOpen(t.goalId ?? null)} className="flex min-h-11 w-full flex-wrap items-center gap-2 rounded-xl bg-white/80 px-3 py-2 text-left text-[13px] font-semibold transition-colors duration-150 hover:bg-white">
                        <span className="min-w-0 flex-1 break-words">{t.label}</span>
                        {t.daysLeft !== null && <Pill tone="muted">dönem sonu {fmtDay(t.due)}</Pill>}
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            </Block>
          )}
          <Block title="Hedeflerim" help="Hedefe dokunarak ayrıntı, check-in ve revizyon talebi. Taslak hedef onaya gönderilince yöneticinize düşer." info={<SqlInfo k={d.kaynaklar} alan="goals" label="Hedef değeri ve ilerleme" />}>
            {!d.goals.length && <div className="py-3 text-center text-[12px] text-canvas-muted">Henüz hedefiniz yok.</div>}
            <ul className="flex flex-col gap-1.5">
              {d.goals.map((g) => <li key={g.id}><GoalRow g={g} onOpen={() => setOpen(g.id)} /></li>)}
            </ul>
          </Block>
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2 lg:gap-4">
            <Block title="Değerlendirmelerim">
              {!d.reviews.length && <div className="py-3 text-center text-[12px] text-canvas-muted">Değerlendirme dönemi yok.</div>}
              <ul className="flex flex-col gap-1.5">
                {d.reviews.map((r) => (
                  <li key={r.id}>
                    <Link to={`/ik/performansim/degerlendirme/${r.id}`} className="flex min-h-11 flex-wrap items-center gap-2 rounded-xl bg-white/80 px-3 py-2 text-[13px] transition-colors duration-150 hover:bg-white">
                      <span className="min-w-0 flex-1 break-words font-bold">{r.cycleName}</span>
                      <Pill tone={REVIEW_TONE[r.state]}>{r.stateLabel}</Pill>
                    </Link>
                  </li>
                ))}
              </ul>
            </Block>
            <Block title="Hakkımdaki iş kayıtları özeti" help="Yöneticiniz ya da İK değerlendirme için bilgi amaçlı özet hazırladığında burada görünür. Puan değildir." info={<SqlInfo k={d.kaynaklar} alan="workSummaries" label="İş kayıtları özeti" />}>
              {!d.workSummaries.length && <div className="py-3 text-center text-[12px] text-canvas-muted">Hazırlanmış özet yok.</div>}
              <ul className="flex flex-col gap-1.5">
                {d.workSummaries.map((w) => (
                  <li key={w.id} className="rounded-xl bg-white/80 px-3 py-2 text-[12.5px]">
                    <div className="text-[11.5px] text-canvas-muted">{fmtDay(w.periodStart)} – {fmtDay(w.periodEnd)} · {w.generatedBy} · {fmtDateTime(w.generatedAt)}</div>
                    <div className="mt-0.5 break-words">{w.text}</div>
                  </li>
                ))}
              </ul>
            </Block>
          </div>
        </>
      )}
      {open !== null && meta.data && d?.employee && (
        <GoalSheet
          key={open}
          goalId={open === 'new' ? null : open}
          init={{ level: 'kisi', ownerEmployeeId: d.employee.id, period: thisYear() }}
          meta={meta.data}
          parents={tree.data?.items ?? []}
          onClose={() => setOpen(null)}
        />
      )}
    </HrFrame>
  );
}
