import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Loading, Note, errText, nf } from '../../admin/ui';
import { Block } from '../parts';
import SqlInfo from '../../components/SqlInfo';
import { perfApi } from './perfApi';

/** M56 Kalibrasyon: birim × yöneticinin verdiği genel puan dağılımı. Sistem puan üretmez; bir birimin herkese en yüksek
 *  puanı vermesi burada görünür. Kişi adları yalnız bu yetkide; toplantıda perdeye «Adları gizle» ile yalnız dağılım yansır. */
export default function Calibration({ cycleId }: { cycleId: string }) {
  const q = useQuery({ queryKey: ['hr', 'perf', 'calibration', cycleId], queryFn: () => perfApi.calibration(cycleId) });
  const [names, setNames] = useState(false);
  if (q.error) return <Note tone="err">{errText(q.error, 'Kalibrasyon okunamadı.')}</Note>;
  if (!q.data) return <Loading />;
  const d = q.data;
  const max = Math.max(1, ...d.units.flatMap((u) => u.counts), ...d.overall);
  const Bars = ({ counts }: { counts: number[] }) => (
    <div className="flex h-16 items-end gap-1" aria-hidden>
      {counts.map((c, i) => (
        <div key={i} className="flex flex-1 flex-col items-center justify-end gap-0.5">
          <div className="w-full rounded-t-md bg-canvas-violet/70" style={{ height: `${(c / max) * 100}%`, minHeight: c ? 3 : 0 }} />
        </div>
      ))}
    </div>
  );
  return (
    <div className="flex flex-col gap-3">
      <Block title={`Şirket geneli · ${nf.format(d.n)} değerlendirme${d.mean !== null ? ` · ortalama ${nf.format(d.mean)}` : ''}`}
        info={<SqlInfo k={d.kaynaklar} alan="overall" label="Şirket geneli dağılım ve ortalama" />}
        action={<label className="flex min-h-11 items-center gap-2 text-[12.5px] font-bold sm:min-h-0"><input type="checkbox" checked={names} onChange={(e) => setNames(e.target.checked)} />Adları göster</label>}>
        <Bars counts={d.overall} />
        <div className="mt-1 grid grid-cols-5 gap-1 text-center text-[10.5px] leading-tight text-canvas-muted">
          {d.labels.map((l, i) => <div key={l}>{l}<div className="font-mono text-[11px] font-bold text-canvas-ink">{d.overall[i]}</div></div>)}
        </div>
      </Block>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
        {d.units.map((u) => (
          <Block key={u.unitName} title={u.unitName} help={`${u.n} değerlendirme${u.mean !== null ? ` · ortalama ${nf.format(u.mean)}` : ''}`} info={<SqlInfo k={d.kaynaklar} alan="units" label={`${u.unitName} · dağılım`} />}>
            <Bars counts={u.counts} />
            <table className="sr-only"><tbody>{u.counts.map((c, i) => <tr key={i}><td>{d.labels[i]}</td><td>{c}</td></tr>)}</tbody></table>
            {names && (
              <ul className="mt-2 flex flex-col gap-0.5 text-[12px]">
                {u.people.map((p) => <li key={p.reviewId} className="flex justify-between gap-2"><span className="break-words">{p.name}</span><span className="shrink-0 font-mono">{p.score} · {p.managerName ?? '—'}</span></li>)}
              </ul>
            )}
          </Block>
        ))}
      </div>
      {!d.units.length && <Note tone="info">Henüz teslim edilmiş yönetici değerlendirmesi yok.</Note>}
    </div>
  );
}
