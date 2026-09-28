import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Plus } from 'lucide-react';
import { ENGINE_ENABLED } from '../../engine';
import { Note, Pill, TableWrap, btnGhost, btnPrimary, errText, field, label as labelCls, td, th } from '../../admin/ui';
import Sheet from '../../editorial/studio/reader/Sheet';
import { NAV } from '../../nav/navModel';
import { Block, Tabs } from '../parts';
import SqlInfo, { InfoLabel } from '../../components/SqlInfo';
import { hrApi } from '../hrApi';
import { fmtMoney, learningApi, localToIso, type Course, type Delivery, type Info, type Kind, type SessionState } from './learningApi';
import { EmployeePicker, LearningFrame, fmtWhen, useLearningInfo } from './parts';

/** Katalog ve oturumlar: eğitim kartı (tür, biçim, süre, geçerlilik, maliyet, zorunlu eğitimin birimleri, ZEKİ ekranı) ve
 *  oturum listesi. Düzenleme `ik.egitim-yonet` ister; diğerleri okur. */

export default function CoursesScreen() {
  const info = useLearningInfo();
  const can = info.data?.can;
  const [tab, setTab] = useState<'oturum' | 'katalog'>('oturum');
  const [edit, setEdit] = useState<Course | 'new' | null>(null);
  const [newSession, setNewSession] = useState(false);
  return (
    <LearningFrame
      crumb="Eğitim ve gelişim"
      title="Katalog ve oturumlar"
      lead="Eğitim kartları ve oturumlar. Zorunlu eğitimin yenileme periyodu işyerinin tehlike sınıfına bağlıdır; kartta «geçerlilik süresi» olarak girilir, sistemde sabit değildir."
      aside={
        can?.manage ? (
          <div className="flex flex-wrap justify-start gap-2 lg:justify-end">
            <button type="button" className={btnGhost} onClick={() => setEdit('new')}><Plus aria-hidden className="h-4 w-4" />Eğitim kartı</button>
            <button type="button" className={btnPrimary} onClick={() => setNewSession(true)}><Plus aria-hidden className="h-4 w-4" />Oturum</button>
          </div>
        ) : undefined
      }
    >
      <Tabs tabs={[{ key: 'oturum', label: 'Oturumlar' }, { key: 'katalog', label: 'Katalog' }] as const} value={tab} onChange={setTab} />
      {tab === 'oturum' ? <SessionList info={info.data} /> : <CourseList onEdit={can?.manage ? setEdit : undefined} />}
      {info.data && edit && <CourseSheet info={info.data} course={edit === 'new' ? null : edit} onClose={() => setEdit(null)} />}
      {info.data && newSession && <SessionSheet onClose={() => setNewSession(false)} />}
    </LearningFrame>
  );
}

function CourseList({ onEdit }: { onEdit?: (c: Course) => void }) {
  const q = useQuery({ queryKey: ['hr', 'learning', 'courses'], queryFn: () => learningApi.courses(), enabled: ENGINE_ENABLED });
  if (q.error) return <Note tone="err">{errText(q.error, 'Katalog okunamadı.')}</Note>;
  const items = q.data?.items ?? [];
  return (
    <Block title="Eğitim kataloğu" help={`${items.length} eğitim`} info={<SqlInfo k={q.data?.kaynaklar} alan="items[]" label="Eğitim kataloğu" />}>
      {q.isLoading && <p className="text-[12px] text-canvas-muted">Yükleniyor…</p>}
      {q.data && items.length === 0 && <p className="text-[12px] text-canvas-muted">Katalog boş. İlk kartı «Eğitim kartı» ile ekleyin.</p>}
      {items.length > 0 && (
        <TableWrap>
          <thead>
            <tr><th className={th}>Eğitim</th><th className={th}>Tür</th><th className={th}>Biçim</th><th className={th}>Geçerlilik</th><th className={th}><InfoLabel k={q.data?.kaynaklar} alan="items[]" label="Kişi başı maliyet">Kişi başı</InfoLabel></th><th className={th}>Kapsam</th><th className={th} /></tr>
          </thead>
          <tbody>
            {items.map((c) => (
              <tr key={c.id} className={`border-t border-slate-100 ${c.active ? '' : 'opacity-60'}`}>
                <td className={`${td} font-bold`}>{c.title}{c.provider ? <div className="text-[11px] font-normal text-canvas-muted">{c.provider}</div> : null}</td>
                <td className={td}><Pill tone={c.kind === 'zorunlu' ? 'err' : c.kind === 'zeki' ? 'violet' : 'muted'}>{c.kindLabel}</Pill></td>
                <td className={td}>{c.deliveryLabel}{c.durationHours ? ` · ${c.durationHours} sa` : ''}</td>
                <td className={td}>{c.validityDays ? `${c.validityDays} gün` : 'Süresiz'}</td>
                <td className={`${td} font-mono tabular-nums`}>{fmtMoney(c.costPerPerson)}</td>
                <td className={td}>{c.kind === 'zorunlu' ? (c.requiredUnitNames.length ? c.requiredUnitNames.join(', ') : 'Bütün çalışanlar') : '—'}</td>
                <td className={`${td} text-right`}>{onEdit && <button type="button" className={btnGhost} onClick={() => onEdit(c)}>Düzenle</button>}</td>
              </tr>
            ))}
          </tbody>
        </TableWrap>
      )}
    </Block>
  );
}

function SessionList({ info }: { info?: Info }) {
  const [state, setState] = useState<SessionState | ''>('planli');
  const q = useQuery({ queryKey: ['hr', 'learning', 'sessions', state], queryFn: () => learningApi.sessions(state), enabled: ENGINE_ENABLED });
  const items = q.data?.items ?? [];
  return (
    <Block
      title="Oturumlar"
      info={<SqlInfo k={q.data?.kaynaklar} alan="items[]" label="Oturum katılım sayıları" />}
      action={
        <select className={`${field} w-auto`} value={state} onChange={(e) => setState(e.target.value as SessionState | '')} aria-label="Durum">
          <option value="">Hepsi</option>
          {info && Object.entries(info.sessionStates).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
      }
    >
      {q.error && <Note tone="err">{errText(q.error, 'Oturumlar okunamadı.')}</Note>}
      {q.data && items.length === 0 && <p className="text-[12px] text-canvas-muted">Bu durumda oturum yok.</p>}
      <ul className="flex flex-col gap-2">
        {items.map((s) => (
          <li key={s.id}>
            <Link to={`/ik/egitim/oturum/${s.id}`} className="flex min-h-11 flex-wrap items-center justify-between gap-2 rounded-xl border border-slate-100 bg-white px-3 py-2 outline-none transition-transform duration-150 ease-out hover:border-canvas-violet/40 focus-visible:ring-2 focus-visible:ring-canvas-violet active:scale-[0.99]">
              <div className="min-w-0">
                <div className="text-[13px] font-extrabold">{s.courseTitle}</div>
                <div className="text-[11.5px] text-canvas-muted">{[fmtWhen(s.startsAt), s.location, s.trainer].filter(Boolean).join(' · ')}</div>
              </div>
              <div className="flex flex-wrap items-center gap-1.5">
                <Pill tone="muted">{s.counts.approved} katılımcı</Pill>
                {s.counts.pending > 0 && <Pill tone="warn">{s.counts.pending} onay bekliyor</Pill>}
                {s.state === 'yapildi' && <Pill tone="ok">{s.counts.completed} tamamladı</Pill>}
                <Pill tone={s.state === 'planli' ? 'violet' : s.state === 'iptal' ? 'muted' : 'ok'}>{s.stateLabel}</Pill>
              </div>
            </Link>
          </li>
        ))}
      </ul>
    </Block>
  );
}

const ROUTES = NAV.filter((g) => g.id !== 'kampus').flatMap((g) => g.items.map((i) => ({ id: i.id, label: `${g.label} › ${i.label}` })));

function CourseSheet({ info, course, onClose }: { info: Info; course: Course | null; onClose: () => void }) {
  const qc = useQueryClient();
  const units = useQuery({ queryKey: ['hr', 'units'], queryFn: hrApi.units, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const [f, setF] = useState({
    title: course?.title ?? '', kind: (course?.kind ?? 'gelisim') as Kind, delivery: (course?.delivery ?? 'ic') as Delivery,
    durationHours: course?.durationHours?.toString() ?? '', validityDays: course?.validityDays?.toString() ?? '',
    costPerPerson: course?.costPerPerson?.toString() ?? '', provider: course?.provider ?? '', moduleRoute: course?.moduleRoute ?? '',
    requiredUnits: course?.requiredUnits ?? [], description: course?.description ?? '', active: course?.active ?? true,
  });
  const set = <K extends keyof typeof f>(k: K, v: (typeof f)[K]) => setF((x) => ({ ...x, [k]: v }));
  const save = useMutation({
    mutationFn: () => {
      const body = {
        ...f,
        durationHours: f.durationHours === '' ? null : Number(f.durationHours.replace(',', '.')),
        validityDays: f.validityDays === '' ? null : Number(f.validityDays),
        costPerPerson: f.costPerPerson === '' ? null : Number(f.costPerPerson.replace(',', '.')),
        moduleRoute: f.kind === 'zeki' ? f.moduleRoute || null : null,
        requiredUnits: f.kind === 'zorunlu' ? f.requiredUnits : [],
      };
      return course ? learningApi.updateCourse(course.id, body) : learningApi.createCourse(body);
    },
    onSuccess: () => {
      toast.success('Eğitim kartı kaydedildi.');
      void qc.invalidateQueries({ queryKey: ['hr', 'learning'] });
      onClose();
    },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.')),
  });
  return (
    <Sheet open modal onClose={onClose} title={course ? 'Eğitim kartı' : 'Yeni eğitim kartı'} wide>
      <div className="flex flex-col gap-3 p-4">
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Eğitimin adı</span>
          <input className={field} value={f.title} onChange={(e) => set('title', e.target.value)} />
        </label>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Tür</span>
            <select className={field} value={f.kind} onChange={(e) => set('kind', e.target.value as Kind)}>
              {Object.entries(info.kinds).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Biçim</span>
            <select className={field} value={f.delivery} onChange={(e) => set('delivery', e.target.value as Delivery)}>
              {Object.entries(info.delivery).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Süre (saat)</span>
            <input className={field} inputMode="decimal" value={f.durationHours} onChange={(e) => set('durationHours', e.target.value)} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Geçerlilik (gün)</span>
            <input className={field} inputMode="numeric" value={f.validityDays} onChange={(e) => set('validityDays', e.target.value)} placeholder="Boş: süresiz" />
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Kişi başı maliyet (₺)</span>
            <input className={field} inputMode="decimal" value={f.costPerPerson} onChange={(e) => set('costPerPerson', e.target.value)} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Eğitmen / hizmet firması</span>
            <input className={field} value={f.provider} onChange={(e) => set('provider', e.target.value)} />
          </label>
        </div>
        {f.kind === 'zorunlu' && (
          <fieldset className="flex flex-col gap-1">
            <legend className={labelCls}>Uygulanan birimler (hiçbiri seçilmezse bütün çalışanlar)</legend>
            <div className="flex flex-wrap gap-1.5">
              {(units.data?.items ?? []).filter((u) => u.active).map((u) => {
                const on = f.requiredUnits.includes(u.id);
                return (
                  <button key={u.id} type="button" aria-pressed={on}
                    onClick={() => set('requiredUnits', on ? f.requiredUnits.filter((x) => x !== u.id) : [...f.requiredUnits, u.id])}
                    className={`min-h-11 rounded-xl px-3 text-[12px] font-bold transition-transform duration-150 ease-out active:scale-[0.97] sm:min-h-9 ${on ? 'bg-canvas-violet text-white' : 'bg-slate-100 text-canvas-ink hover:bg-slate-200'}`}>
                    {u.name}
                  </button>
                );
              })}
            </div>
          </fieldset>
        )}
        {f.kind === 'zeki' && (
          <label className="flex flex-col gap-1">
            <span className={labelCls}>İlgili ekran</span>
            <select className={field} value={f.moduleRoute} onChange={(e) => set('moduleRoute', e.target.value)}>
              <option value="">Seçin</option>
              {ROUTES.map((r) => <option key={r.id} value={r.id}>{r.label}</option>)}
            </select>
          </label>
        )}
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Açıklama</span>
          <textarea className={`${field} min-h-[80px]`} value={f.description} onChange={(e) => set('description', e.target.value)} />
        </label>
        {course && (
          <label className="flex min-h-11 items-center gap-2 text-[12.5px] font-bold">
            <input type="checkbox" className="h-4 w-4 accent-canvas-violet" checked={f.active} onChange={(e) => set('active', e.target.checked)} />
            Etkin (pasif eğitime oturum açılmaz, zorunlu eğitim durumuna girmez)
          </label>
        )}
        <button type="button" className={btnPrimary} disabled={!f.title.trim() || save.isPending} onClick={() => save.mutate()}>
          {save.isPending ? 'Kaydediliyor…' : 'Kaydet'}
        </button>
      </div>
    </Sheet>
  );
}

function SessionSheet({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const courses = useQuery({ queryKey: ['hr', 'learning', 'courses', 'active'], queryFn: () => learningApi.courses(true), enabled: ENGINE_ENABLED });
  const [courseId, setCourseId] = useState('');
  const [starts, setStarts] = useState('');
  const [ends, setEnds] = useState('');
  const [location, setLocation] = useState('');
  const [trainer, setTrainer] = useState('');
  const [capacity, setCapacity] = useState('');
  const [people, setPeople] = useState<string[]>([]);
  const save = useMutation({
    mutationFn: () => learningApi.createSession({
      courseId, startsAt: localToIso(starts), endsAt: localToIso(ends) || undefined, location, trainer,
      capacity: capacity ? Number(capacity) : null, employeeIds: people,
    }),
    onSuccess: (s) => {
      toast.success('Oturum açıldı.');
      void qc.invalidateQueries({ queryKey: ['hr', 'learning'] });
      onClose();
      navigate(`/ik/egitim/oturum/${s.id}`);
    },
    onError: (e) => toast.error(errText(e, 'Oturum açılamadı.')),
  });
  return (
    <Sheet open modal onClose={onClose} title="Yeni oturum" subtitle="Seçtiğiniz kişiler onaylı katılımcı olarak eklenir; sonra da eklenebilir." wide>
      <div className="flex flex-col gap-3 p-4">
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Eğitim</span>
          <select className={field} value={courseId} onChange={(e) => setCourseId(e.target.value)}>
            <option value="">Seçin</option>
            {(courses.data?.items ?? []).map((c) => <option key={c.id} value={c.id}>{c.title} · {c.kindLabel}</option>)}
          </select>
        </label>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Başlangıç</span>
            <input type="datetime-local" className={field} value={starts} onChange={(e) => setStarts(e.target.value)} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Bitiş</span>
            <input type="datetime-local" className={field} value={ends} onChange={(e) => setEnds(e.target.value)} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Yer</span>
            <input className={field} value={location} onChange={(e) => setLocation(e.target.value)} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Eğitmen</span>
            <input className={field} value={trainer} onChange={(e) => setTrainer(e.target.value)} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Kontenjan (bilgi)</span>
            <input className={field} inputMode="numeric" value={capacity} onChange={(e) => setCapacity(e.target.value)} />
          </label>
        </div>
        <div className={labelCls}>Katılımcılar</div>
        <EmployeePicker value={people} onChange={setPeople} />
        <button type="button" className={btnPrimary} disabled={!courseId || !starts || save.isPending} onClick={() => save.mutate()}>
          {save.isPending ? 'Kaydediliyor…' : 'Oturumu aç'}
        </button>
      </div>
    </Sheet>
  );
}
