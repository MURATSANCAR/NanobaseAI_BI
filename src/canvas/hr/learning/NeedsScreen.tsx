import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Plus } from 'lucide-react';
import { ENGINE_ENABLED } from '../../engine';
import { Note, Pill, TableWrap, btnGhost, btnPrimary, errText, field, label as labelCls, td, th } from '../../admin/ui';
import Sheet from '../../editorial/studio/reader/Sheet';
import { Block } from '../parts';
import SqlInfo from '../../components/SqlInfo';
import { hrApi, waitJob } from '../hrApi';
import { learningApi, type Info, type Need, type NeedState, type Priority } from './learningApi';
import { EmployeePicker, LearningFrame, fmtDay, useLearningInfo } from './parts';

/** Eğitim ihtiyaçları: çalışan, yönetici ve İK'nın bildirdiği ihtiyaçlar; Zeki AI kataloğa eşler, öncelik ve gerekçe önerir
 *  (kişi bilgisi modele gitmez). Karar İK'nındır. Üstteki sıra, eğitim başına açık/onaylı ihtiyaç sayısıdır. */

export default function NeedsScreen() {
  const info = useLearningInfo();
  const qc = useQueryClient();
  const [state, setState] = useState<NeedState | ''>('acik');
  const [adding, setAdding] = useState(false);
  const [progress, setProgress] = useState<string | null>(null);
  const q = useQuery({ queryKey: ['hr', 'learning', 'needs', state], queryFn: () => learningApi.needs(state), enabled: ENGINE_ENABLED });
  const can = info.data?.can;
  const suggest = useMutation({
    mutationFn: async () => {
      const job = await learningApi.suggestNeeds();
      return waitJob(job.id, (j) => setProgress(j.total ? `${j.progress}/${j.total}` : ''));
    },
    onSuccess: (j) => {
      setProgress(null);
      if (j.state === 'hata') toast.error(j.error ?? 'Öneri çıkarılamadı.');
      else toast.success('Zeki AI önerileri hazır; kararı siz verin.');
      void qc.invalidateQueries({ queryKey: ['hr', 'learning', 'needs'] });
    },
    onError: (e) => {
      setProgress(null);
      toast.error(errText(e, 'Öneri başlatılamadı.'));
    },
  });
  const d = q.data;
  return (
    <LearningFrame
      crumb="Eğitim ve gelişim"
      title="Eğitim ihtiyaçları"
      lead="Çalışanların, yöneticilerin ve İK'nın bildirdiği eğitim ihtiyaçları. Zeki AI her ihtiyacı katalogdaki bir eğitime eşler, öncelik ve tek cümlelik gerekçe önerir; Zeki AI'a kişi adı gitmez. Karar İK'nındır."
      aside={
        can?.manage ? (
          <div className="flex flex-wrap justify-start gap-2 lg:justify-end">
            <button type="button" className={btnGhost} onClick={() => setAdding(true)}><Plus aria-hidden className="h-4 w-4" />İhtiyaç ekle</button>
            {info.data?.modelVar && (
              <button type="button" className={btnPrimary} disabled={suggest.isPending} onClick={() => suggest.mutate()}>
                {suggest.isPending ? `Zeki AI eşliyor… ${progress ?? ''}` : 'Zeki AI’dan öneri al'}
              </button>
            )}
          </div>
        ) : undefined
      }
    >
      {q.error && <Note tone="err">{errText(q.error, 'İhtiyaçlar okunamadı.')}</Note>}
      {d && d.summary.length > 0 && (
        <Block title="Öncelik sırası" help="Hangi eğitim için en çok ihtiyaç var: açık ve onaylı ihtiyaçlar eğitim başına sayılır; önce yüksek öncelikli sayısına, sonra toplama göre sıralanır. «Belirsiz»: önceliği henüz verilmemiş." info={<SqlInfo k={d.kaynaklar} alan="summary" label="İhtiyaç sayıları" />}>
          <TableWrap>
            <thead>
              <tr><th className={th}>Eğitim</th><th className={`${th} text-right`}>Toplam</th><th className={`${th} text-right`}>Yüksek</th><th className={`${th} text-right`}>Orta</th><th className={`${th} text-right`}>Düşük</th><th className={`${th} text-right`}>Belirsiz</th></tr>
            </thead>
            <tbody>
              {d.summary.map((s) => (
                <tr key={s.courseId ?? '-'} className="border-t border-slate-100">
                  <td className={`${td} font-bold`}>{s.courseTitle}</td>
                  {[s.total, s.yuksek, s.orta, s.dusuk, s.belirsiz].map((n, i) => (
                    <td key={i} className={`${td} text-right font-mono tabular-nums`}>{n}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </TableWrap>
        </Block>
      )}
      <Block
        title="İhtiyaç listesi"
        action={
          <select className={`${field} w-auto`} value={state} onChange={(e) => setState(e.target.value as NeedState | '')} aria-label="Durum">
            <option value="">Hepsi</option>
            {info.data && Object.entries(info.data.needStates).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        }
      >
        {!can?.manage && <Note tone="info">İhtiyacın metnini ve kimin bildirdiğini yalnız eğitim yönetimi yetkisi olanlar görür.</Note>}
        {d && d.items.length === 0 && <p className="text-[12px] text-canvas-muted">{state ? 'Bu durumda ihtiyaç yok; durum süzgecini «Hepsi» yapabilirsiniz.' : 'Henüz bildirilmiş eğitim ihtiyacı yok. Çalışanlar «Eğitimlerim» ekranından bildirebilir.'}</p>}
        <ul className="flex flex-col gap-2">
          {d?.items.map((n) => <NeedRow key={n.id} n={n} info={info.data} canDecide={!!can?.manage} />)}
        </ul>
      </Block>
      {adding && info.data && <AddNeed info={info.data} onClose={() => setAdding(false)} />}
    </LearningFrame>
  );
}

function NeedRow({ n, info, canDecide }: { n: Need; info?: Info; canDecide: boolean }) {
  const qc = useQueryClient();
  const courses = useQuery({ queryKey: ['hr', 'learning', 'courses', 'active'], queryFn: () => learningApi.courses(true), enabled: ENGINE_ENABLED && canDecide });
  const [courseId, setCourseId] = useState(n.courseId ?? n.suggestedCourseId ?? '');
  const [priority, setPriority] = useState<Priority | ''>(n.priority ?? '');
  const decide = useMutation({
    mutationFn: (s: NeedState) => learningApi.decideNeed(n.id, { state: s, courseId: courseId || null, priority: priority || null }),
    onSuccess: (r) => {
      toast.success(`İhtiyaç: ${r.stateLabel}`);
      void qc.invalidateQueries({ queryKey: ['hr', 'learning'] });
    },
    onError: (e) => toast.error(errText(e, 'Karar kaydedilemedi.')),
  });
  return (
    <li className="rounded-xl border border-slate-100 bg-white px-3 py-2.5">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="text-[12px] text-canvas-muted">
            {[n.employee?.displayName, n.unitName ?? n.employee?.unitName, n.sourceLabel, fmtDay(n.createdAt)].filter(Boolean).join(' · ')}
          </div>
          {n.text !== undefined && <div className="mt-0.5 break-words text-[13px] font-semibold">{n.text}</div>}
          {n.suggestion && (
            <div className="mt-1.5 rounded-lg bg-canvas-violet/5 px-2.5 py-1.5 text-[12px]">
              <b>Zeki AI önerisi:</b> {n.suggestedCourseTitle ?? 'Katalogda uygun eğitim yok'}
              {n.priorityLabel ? ` · öncelik ${n.priorityLabel.toLocaleLowerCase('tr')}` : ''}
              {typeof n.suggestion.egitim === 'number' ? ` · olasılık %${Math.round(n.suggestion.egitim * 100)}` : ''}
              {n.suggestionReason && <div className="mt-0.5 text-canvas-muted">{n.suggestionReason}</div>}
            </div>
          )}
        </div>
        <Pill tone={n.state === 'acik' ? 'warn' : n.state === 'reddedildi' ? 'muted' : 'ok'}>{n.stateLabel}{n.courseTitle ? ` · ${n.courseTitle}` : ''}</Pill>
      </div>
      {canDecide && n.state !== 'karsilandi' && (
        <div className="mt-2 flex flex-col gap-2 sm:flex-row sm:items-end">
          <label className="flex min-w-0 flex-1 flex-col gap-1">
            <span className={labelCls}>Eğitim</span>
            <select className={field} value={courseId} onChange={(e) => setCourseId(e.target.value)}>
              <option value="">Seçilmedi</option>
              {(courses.data?.items ?? []).map((c) => <option key={c.id} value={c.id}>{c.title}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1 sm:w-[140px]">
            <span className={labelCls}>Öncelik</span>
            <select className={field} value={priority} onChange={(e) => setPriority(e.target.value as Priority | '')}>
              <option value="">—</option>
              {info && Object.entries(info.priorities).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </label>
          <div className="flex flex-wrap gap-2">
            {n.state !== 'onaylandi' && <button type="button" className={btnPrimary} disabled={decide.isPending} onClick={() => decide.mutate('onaylandi')}>Onayla</button>}
            {n.state === 'onaylandi' && <button type="button" className={btnPrimary} disabled={decide.isPending} onClick={() => decide.mutate('karsilandi')}>Karşılandı olarak işaretle</button>}
            {n.state !== 'reddedildi' && <button type="button" className={btnGhost} disabled={decide.isPending} onClick={() => decide.mutate('reddedildi')}>Reddet</button>}
          </div>
        </div>
      )}
    </li>
  );
}

function AddNeed({ info, onClose }: { info: Info; onClose: () => void }) {
  const qc = useQueryClient();
  const units = useQuery({ queryKey: ['hr', 'units'], queryFn: hrApi.units, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const [who, setWho] = useState<string[]>([]);
  const [unitId, setUnitId] = useState('');
  const [text, setText] = useState('');
  const [source, setSource] = useState('ik');
  const save = useMutation({
    mutationFn: async () => {
      if (who.length) {
        for (const id of who) await learningApi.addNeed({ employeeId: id, text, source });
        return who.length;
      }
      await learningApi.addNeed({ unitId, text, source });
      return 1;
    },
    onSuccess: (n) => {
      toast.success(`${n} ihtiyaç kaydedildi.`);
      void qc.invalidateQueries({ queryKey: ['hr', 'learning'] });
      onClose();
    },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.')),
  });
  const sources = Object.entries(info.needSources).filter(([k]) => k !== 'calisan');
  return (
    <Sheet open modal onClose={onClose} title="Eğitim ihtiyacı" subtitle="Kişi seçerseniz her biri için ayrı kayıt açılır; seçmezseniz birim düzeyinde tek kayıt." wide>
      <div className="flex flex-col gap-3 p-4">
        <label className="flex flex-col gap-1">
          <span className={labelCls}>İhtiyaç</span>
          <textarea className={`${field} min-h-[72px]`} value={text} onChange={(e) => setText(e.target.value)}
            placeholder="ör. Yeni sözleşme ekranını kullanamıyor; özet ve takvim adımlarında desteğe ihtiyaç var" />
          <span className="text-[11px] text-canvas-muted">Metne kişi adı, iletişim ya da sağlık bilgisi yazmayın; Zeki AI önerisinde metin kullanılır.</span>
        </label>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Kaynak</span>
            <select className={field} value={source} onChange={(e) => setSource(e.target.value)}>
              {sources.map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Birim (kişi seçilmezse)</span>
            <select className={field} value={unitId} onChange={(e) => setUnitId(e.target.value)} disabled={who.length > 0}>
              <option value="">Seçin</option>
              {(units.data?.items ?? []).map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
            </select>
          </label>
        </div>
        <div className={labelCls}>Kişiler (isteğe bağlı)</div>
        <EmployeePicker value={who} onChange={setWho} />
        <button type="button" className={btnPrimary} disabled={text.trim().length < 5 || (!who.length && !unitId) || save.isPending} onClick={() => save.mutate()}>
          Kaydet
        </button>
      </div>
    </Sheet>
  );
}
