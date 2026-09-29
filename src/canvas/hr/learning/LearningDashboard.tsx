import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ENGINE_ENABLED } from '../../engine';
import { Note, Pill, TableWrap, btnGhost, btnPrimary, errText, field, label as labelCls, td, th } from '../../admin/ui';
import { Kpi, KpiRow } from '../../editorial/kit';
import Sheet from '../../editorial/studio/reader/Sheet';
import { Block } from '../parts';
import SqlInfo, { InfoLabel } from '../../components/SqlInfo';
import type { Kaynaklar } from '../../components/sqlInfo';
import { fmtMoney, learningApi, localToIso, pct, type CertCheck, type Info, type StatusRow } from './learningApi';
import { ReadingBadge, ReadingNote } from '../../components/ReadingBadge';
import { LearningFrame, StatusPill, fmtDay, fmtWhen, useLearningInfo } from './parts';

/** Eğitim panosu (İK): sayaçlar, dolmuş/dolacak zorunlu eğitimler (kişi listesi yalnız `ik.egitim-yonet`), seçilenlerle
 *  tek adımda oturum, birim × eğitim tamamlanma, doğrulama bekleyen belgeler ve eğitim gideri (`ik.egitim-butce`). */

export default function LearningDashboard() {
  const info = useLearningInfo();
  const dash = useQuery({ queryKey: ['hr', 'learning', 'dashboard'], queryFn: learningApi.dashboard, enabled: ENGINE_ENABLED });
  const can = info.data?.can;
  const c = dash.data?.counters;
  return (
    <LearningFrame
      crumb="Eğitim ve gelişim"
      title="Eğitim panosu"
      lead="Zorunlu eğitimlerin son tarihleri, oturumlar ve tamamlanma. Durum, doğrulanmış en son sertifikadan hesaplanır; geçerlilik süresi eğitim kartında İK'nın girdiği süredir."
    >
      {!ENGINE_ENABLED && <Note tone="warn">Bu kurulumda veri bağlantısı tanımlı değil.</Note>}
      {dash.error && <Note tone="err">{errText(dash.error, 'Pano okunamadı.')}</Note>}
      {c && (
        <>
          <KpiRow>
            <Kpi label="Süresi dolmuş" value={String(c.overdue + c.never)} help={`Dolmuş ${c.overdue} · hiç almamış ${c.never}`} info={<SqlInfo k={dash.data?.kaynaklar} alan="counters" label="Süresi dolmuş" />} />
            <Kpi label="Dolacak" value={c.expiring === null ? '—' : String(c.expiring)}
              help={c.alertDays ? `${c.alertDays} gün içinde` : 'Uyarı günü ayarlanmadı (Portal ayarları → İnsan kaynakları)'} info={<SqlInfo k={dash.data?.kaynaklar} alan="counters" label="Dolacak" />} />
            <Kpi label="Bu ay oturum" value={String(c.sessionsThisMonth)} help={c.awaitingClose ? `${c.awaitingClose} oturumun yoklaması kapatılmadı` : 'Planlı oturumlar'} info={<SqlInfo k={dash.data?.kaynaklar} alan="counters" label="Bu ay oturum" />} />
            <Kpi label="Tamamlanma" value={pct(c.completionRate)} help={`${c.completed} / ${c.enrolled} onaylı katılım`} info={<SqlInfo k={dash.data?.kaynaklar} alan="counters" label="Tamamlanma" />} />
          </KpiRow>
          <div className="flex flex-wrap items-center gap-1.5">
            <SqlInfo k={dash.data?.kaynaklar} alan="counters" label="Bekleyen onay, belge, anket ve ihtiyaç" />
            <Pill tone={c.pendingApprovals ? 'warn' : 'muted'}>Onay bekleyen katılım {c.pendingApprovals}</Pill>
            <Pill tone={c.unverifiedCertificates ? 'warn' : 'muted'}>Doğrulama bekleyen belge {c.unverifiedCertificates}</Pill>
            <Pill tone="muted">Yanıtlanmamış anket {c.pendingFeedback}</Pill>
            <Pill tone={c.openNeeds ? 'violet' : 'muted'}>Açık ihtiyaç {c.openNeeds}</Pill>
          </div>
        </>
      )}
      {dash.data && info.data && (can?.manage && dash.data.attention ? <Attention rows={dash.data.attention} info={info.data} k={dash.data.kaynaklar} /> : <ByUnit rows={dash.data.attentionByUnit} k={dash.data.kaynaklar} />)}
      {dash.data && (
        <Block title="Birim × eğitim tamamlanma" help="İptal edilmemiş oturumlardaki onaylı katılımlardan tamamlananların payı." info={<SqlInfo k={dash.data.kaynaklar} alan="matrix" label="Birim × eğitim tamamlanma" />}>
          {dash.data.matrix.length === 0 ? (
            <p className="text-[12px] text-canvas-muted">Henüz oturum kaydı yok.</p>
          ) : (
            <TableWrap>
              <thead>
                <tr><th className={th}>Birim</th><th className={th}>Eğitim</th><th className={`${th} text-right`}>Katılım</th><th className={`${th} text-right`}>Tamamlanan</th><th className={`${th} text-right`}>Oran</th></tr>
              </thead>
              <tbody>
                {dash.data.matrix.map((m) => (
                  <tr key={`${m.unitId}:${m.courseId}`} className="border-t border-slate-100">
                    <td className={td}>{m.unitName}</td>
                    <td className={td}>{m.courseTitle}</td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{m.enrolled}</td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{m.completed}</td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{pct(m.rate)}</td>
                  </tr>
                ))}
              </tbody>
            </TableWrap>
          )}
        </Block>
      )}
      {can?.manage && <Unverified />}
      {can?.budget && <SpendPanel info={info.data} />}
    </LearningFrame>
  );
}

function ByUnit({ rows, k }: { rows: { unitName: string; doldu: number; hic_yok: number; dolacak: number }[]; k?: Kaynaklar }) {
  if (!rows.length) return null;
  return (
    <Block title="Zorunlu eğitim — birim özeti" help="Kişi listesi eğitim yönetimi yetkisiyle görünür." info={<SqlInfo k={k} alan="attentionByUnit" label="Birim özeti" />}>
      <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {rows.map((r) => (
          <li key={r.unitName} className="rounded-xl bg-white/80 px-3 py-2">
            <div className="text-[13px] font-bold">{r.unitName}</div>
            <div className="mt-1 flex flex-wrap gap-1.5">
              {r.doldu > 0 && <Pill tone="err">Dolmuş {r.doldu}</Pill>}
              {r.hic_yok > 0 && <Pill tone="err">Hiç almamış {r.hic_yok}</Pill>}
              {r.dolacak > 0 && <Pill tone="warn">Dolacak {r.dolacak}</Pill>}
            </div>
          </li>
        ))}
      </ul>
    </Block>
  );
}

function Attention({ rows, info, k }: { rows: StatusRow[]; info: Info; k?: Kaynaklar }) {
  const navigate = useNavigate();
  const [course, setCourse] = useState('');
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [open, setOpen] = useState(false);
  const courses = useMemo(() => [...new Map(rows.map((r) => [r.courseId, r.courseTitle])).entries()], [rows]);
  const shown = course ? rows.filter((r) => r.courseId === course) : rows;
  const key = (r: StatusRow) => `${r.courseId}:${r.employeeId}`;
  const toggle = (r: StatusRow) =>
    setPicked((p) => {
      const n = new Set(p);
      if (n.has(key(r))) n.delete(key(r));
      else n.add(key(r));
      return n;
    });
  const pickedRows = rows.filter((r) => picked.has(key(r)));
  const pickedCourses = new Set(pickedRows.map((r) => r.courseId));
  return (
    <Block
      title="Dolmuş ve dolacak zorunlu eğitimler"
      help="Kişileri seçip tek adımda oturum açın. Planlı oturumu olan kişi işaretlidir."
      info={<SqlInfo k={k} alan="attention" label="Dolmuş ve dolacak eğitimler" />}
      action={
        <>
          {info.can.export && (
            <>
              <button type="button" className={btnGhost} onClick={() => void learningApi.exportExpiring().catch((e) => toast.error(errText(e, 'İndirilemedi.')))}>
                CSV indir
              </button>
              <button type="button" className={btnGhost} onClick={() => void learningApi.exportExpiringXlsx().catch((e) => toast.error(errText(e, 'İndirilemedi.')))}>
                Excel indir
              </button>
            </>
          )}
          <button type="button" className={btnPrimary} disabled={pickedCourses.size !== 1} onClick={() => setOpen(true)}
            title={pickedCourses.size > 1 ? 'Tek bir eğitimin kişilerini seçin' : undefined}>
            Seçilenlerle oturum aç ({pickedRows.length})
          </button>
        </>
      }
    >
      {rows.length === 0 ? (
        <Note tone="ok">Süresi dolmuş ya da dolacak zorunlu eğitim yok.</Note>
      ) : (
        <>
          <label className="mb-2 flex flex-col gap-1 sm:w-[360px]">
            <span className={labelCls}>Eğitim</span>
            <select className={field} value={course} onChange={(e) => setCourse(e.target.value)}>
              <option value="">Bütün zorunlu eğitimler ({rows.length})</option>
              {courses.map(([id, t]) => (
                <option key={id} value={id}>{t}</option>
              ))}
            </select>
          </label>
          <TableWrap>
            <thead>
              <tr>
                <th className={th}><span className="sr-only">Seç</span></th>
                <th className={th}>Çalışan</th><th className={th}>Birim</th><th className={th}>Eğitim</th><th className={th}>Durum</th>
                <th className={th}>Son geçerlilik</th><th className={th}>Planlı oturum</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((r) => (
                <tr key={key(r)} className="border-t border-slate-100">
                  <td className={td}>
                    <input type="checkbox" className="h-4 w-4 accent-canvas-violet" aria-label={`${r.displayName} seç`} checked={picked.has(key(r))} onChange={() => toggle(r)} />
                  </td>
                  <td className={`${td} font-bold`}>{r.displayName}</td>
                  <td className={td}>{r.unitName ?? '—'}</td>
                  <td className={td}>{r.courseTitle}</td>
                  <td className={td}><StatusPill status={r.status} label={r.statusLabel} /></td>
                  <td className={`${td} whitespace-nowrap`}>{r.expiresOn ? `${fmtDay(r.expiresOn)}${r.daysLeft !== null ? ` (${r.daysLeft} gün)` : ''}` : '—'}</td>
                  <td className={`${td} whitespace-nowrap`}>{r.plannedAt ? fmtWhen(r.plannedAt) : '—'}</td>
                </tr>
              ))}
            </tbody>
          </TableWrap>
        </>
      )}
      <NewSessionSheet
        open={open}
        courseId={[...pickedCourses][0] ?? ''}
        courseTitle={pickedRows[0]?.courseTitle ?? ''}
        employeeIds={pickedRows.map((r) => r.employeeId)}
        onClose={() => setOpen(false)}
        onDone={(id) => {
          setPicked(new Set());
          navigate(`/ik/egitim/oturum/${id}`);
        }}
      />
    </Block>
  );
}

export function NewSessionSheet({ open, courseId, courseTitle, employeeIds, onClose, onDone }: {
  open: boolean; courseId: string; courseTitle: string; employeeIds: string[]; onClose: () => void; onDone: (id: string) => void;
}) {
  const qc = useQueryClient();
  const [starts, setStarts] = useState('');
  const [ends, setEnds] = useState('');
  const [location, setLocation] = useState('');
  const [trainer, setTrainer] = useState('');
  const save = useMutation({
    mutationFn: () => learningApi.createSession({ courseId, startsAt: localToIso(starts), endsAt: localToIso(ends) || undefined, location, trainer, employeeIds }),
    onSuccess: (s) => {
      toast.success('Oturum açıldı.');
      void qc.invalidateQueries({ queryKey: ['hr', 'learning'] });
      onClose();
      onDone(s.id);
    },
    onError: (e) => toast.error(errText(e, 'Oturum açılamadı.')),
  });
  return (
    <Sheet open={open} modal onClose={onClose} title="Oturum aç" subtitle={`${courseTitle}${employeeIds.length ? ` · ${employeeIds.length} kişi onaylı katılımcı olarak eklenir` : ''}`}>
      <div className="flex flex-col gap-3 p-4">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Başlangıç</span>
            <input type="datetime-local" className={field} value={starts} onChange={(e) => setStarts(e.target.value)} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Bitiş</span>
            <input type="datetime-local" className={field} value={ends} onChange={(e) => setEnds(e.target.value)} />
          </label>
        </div>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Yer</span>
          <input className={field} value={location} onChange={(e) => setLocation(e.target.value)} placeholder="Toplantı odası ya da çevrimiçi bağlantı" />
        </label>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Eğitmen</span>
          <input className={field} value={trainer} onChange={(e) => setTrainer(e.target.value)} placeholder="İç eğitmen ya da hizmet firması" />
        </label>
        <button type="button" className={btnPrimary} disabled={!courseId || !starts || save.isPending} onClick={() => save.mutate()}>
          {save.isPending ? 'Kaydediliyor…' : 'Oturumu aç'}
        </button>
      </div>
    </Sheet>
  );
}

function Unverified() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['hr', 'learning', 'certs', 'unverified'], queryFn: () => learningApi.certificates('', true), enabled: ENGINE_ENABLED });
  const refresh = () => void qc.invalidateQueries({ queryKey: ['hr', 'learning'] });
  const verify = useMutation({
    mutationFn: learningApi.verifyCertificate,
    onSuccess: () => {
      toast.success('Belge doğrulandı.');
      refresh();
    },
    onError: (e) => toast.error(errText(e, 'Doğrulanamadı.')),
  });
  const del = useMutation({
    mutationFn: learningApi.deleteCertificate,
    onSuccess: () => {
      toast.success('Belge silindi.');
      refresh();
    },
    onError: (e) => toast.error(errText(e, 'Silinemedi.')),
  });
  const [checks, setChecks] = useState<Record<string, CertCheck>>({});
  const check = useMutation({
    mutationFn: learningApi.checkCertificate,
    onSuccess: (r) => setChecks((m) => ({ ...m, [r.id]: r })),
    onError: (e) => toast.error(errText(e, 'Belge okunamadı.')),
  });
  const items = q.data?.items ?? [];
  if (!items.length) return null;
  return (
    <Block title="Doğrulama bekleyen belgeler" help="Çalışanların yüklediği belgeler doğrulanınca zorunlu eğitim durumuna sayılır.">
      <ul className="flex flex-col divide-y divide-slate-100">
        {items.map((c) => (
          <li key={c.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
            <div className="min-w-0">
              <div className="text-[13px] font-bold">{c.employee?.displayName ?? '—'} · {c.title}</div>
              <div className="text-[11.5px] text-canvas-muted">{fmtDay(c.issuedOn)} · {c.expiresOn ? `geçerlilik ${fmtDay(c.expiresOn)}` : 'süresiz'}</div>
            </div>
            <div className="flex flex-wrap gap-2">
              {c.hasFile && (
                <button type="button" className={btnGhost} onClick={() => void learningApi.certificateFile(c.id, c.fileName ?? 'belge').catch((e) => toast.error(errText(e, 'İndirilemedi.')))}>
                  Belgeyi aç
                </button>
              )}
              {c.hasFile && (
                <button type="button" className={btnGhost} disabled={check.isPending} onClick={() => check.mutate(c.id)}>
                  {check.isPending && check.variables === c.id ? 'Okunuyor…' : 'Belgeyi oku ve karşılaştır'}
                </button>
              )}
              <button type="button" className={btnPrimary} disabled={verify.isPending} onClick={() => verify.mutate(c.id)}>Doğrula</button>
              <button type="button" className={btnGhost} disabled={del.isPending} onClick={() => del.mutate(c.id)}>Reddet ve sil</button>
            </div>
            {checks[c.id] && <CertCheckResult r={checks[c.id]} />}
          </li>
        ))}
      </ul>
    </Block>
  );
}

/** Belgeden okuma sonucu: kayıttaki değer belgede birebir geçiyor mu (kurala göre; karar İK'nın). */
function CertCheckResult({ r }: { r: CertCheck }) {
  return (
    <div className="w-full rounded-xl bg-slate-50 px-3 py-2 text-[12px]">
      <ul className="flex flex-col gap-1">
        {r.alanlar.map((a) => (
          <li key={a.alan} className="flex flex-wrap items-center gap-1.5">
            <span className="font-semibold">{a.alan}</span>
            <span className="text-canvas-muted">{a.deger ?? '—'}</span>
            {a.bulundu === null ? <Pill tone="muted">kayıtta yok</Pill> : a.bulundu ? <Pill tone="ok">belgede var</Pill> : <Pill tone="warn">belgede bulunamadı</Pill>}
            <ReadingBadge okuma={a.okuma} guven={a.guven} sayfa={a.sayfa} esik={r.okuma.esik} />
            {a.cevre && <q className="block w-full break-words text-[11px] italic text-canvas-muted">{a.cevre}</q>}
          </li>
        ))}
      </ul>
      <ReadingNote reading={r.okuma} />
      <p className="mt-1 text-[11px] text-canvas-muted">{r.yontem}</p>
    </div>
  );
}

const MONTHS = ['Oca', 'Şub', 'Mar', 'Nis', 'May', 'Haz', 'Tem', 'Ağu', 'Eyl', 'Eki', 'Kas', 'Ara'];

function SpendPanel({ info }: { info?: Info }) {
  const qc = useQueryClient();
  const [year, setYear] = useState(new Date().getFullYear());
  const [amount, setAmount] = useState('');
  const [showAccounts, setShowAccounts] = useState(false);
  const spend = useQuery({ queryKey: ['hr', 'learning', 'spend', year], queryFn: () => learningApi.spend(year), enabled: ENGINE_ENABLED, retry: false });
  const accounts = useQuery({ queryKey: ['hr', 'learning', 'spend-accounts', year], queryFn: () => learningApi.spendAccounts(year), enabled: ENGINE_ENABLED && showAccounts, retry: false });
  const save = useMutation({
    mutationFn: () => learningApi.putBudget(year, Number(amount.replace(/\./g, '').replace(',', '.')), ''),
    onSuccess: () => {
      toast.success('Bütçe kaydedildi.');
      setAmount('');
      void qc.invalidateQueries({ queryKey: ['hr', 'learning', 'spend', year] });
    },
    onError: (e) => toast.error(errText(e, 'Bütçe kaydedilemedi.')),
  });
  const s = spend.data;
  const acc = accounts.data;
  const years = Array.from({ length: 6 }, (_, i) => new Date().getFullYear() - i);
  return (
    <Block
      title="Eğitim gideri ve bütçe"
      help="Gerçekleşen, Logo muhasebe fişlerinden (iptal değil, dönem sonu kapanışı hariç) seçilen eğitim gider hesaplarının borç − alacak toplamıdır."
      action={
        <select className={`${field} w-auto`} value={year} onChange={(e) => setYear(Number(e.target.value))} aria-label="Yıl">
          {years.map((y) => <option key={y} value={y}>{y}</option>)}
        </select>
      }
    >
      {info && !info.accountsConfigured && (
        <Note tone="info">Eğitim gider hesapları henüz seçilmedi. Aşağıdaki listeden Mali İşler'le birlikte seçip Portal ayarları → İnsan kaynakları → «Eğitim gider hesapları» alanına yazın.</Note>
      )}
      {spend.error && <Note tone="err">{errText(spend.error, 'Gider okunamadı.')}</Note>}
      {spend.isLoading && <p className="text-[12px] text-canvas-muted">Logo'dan okunuyor…</p>}
      {s && s.configured && (
        <div className="mt-2 flex flex-col gap-3">
          <KpiRow>
            <Kpi label="Gerçekleşen" value={fmtMoney(s.total)} help={s.dataEnd ? `Veri ${fmtDay(s.dataEnd)} tarihine kadar` : 'Logo muhasebe'} info={<SqlInfo k={s.kaynaklar} alan="total" label="Gerçekleşen eğitim gideri" />} />
            <Kpi label="Bütçe" value={fmtMoney(s.budget?.amount)} help={s.budget ? `${s.budget.updatedBy ?? ''} · ${fmtDay(s.budget.updatedAt)}` : 'Girilmedi'} info={<SqlInfo k={s.kaynaklar} alan="budget" label="Eğitim bütçesi" />} />
            <Kpi label="Kullanım" value={pct(s.ratio)} help="Gerçekleşen ÷ bütçe" info={<SqlInfo k={s.kaynaklar} alan="ratio" label="Bütçe kullanımı" />} />
            <Kpi label="Hesap" value={String(s.accountCodes.length)} help={s.accountCodes.join(', ')} info={<SqlInfo k={s.kaynaklar} alan="accountCodes" label="Gider hesapları (ayar)" />} />
          </KpiRow>
          {s.months.length > 0 && <div className="text-[11px] font-semibold text-canvas-muted"><InfoLabel k={s.kaynaklar} alan="months" label="Ay ve hesap kırılımı">Ay ve hesap kırılımı</InfoLabel></div>}
          {s.months.length > 0 && (
            <div className="grid grid-cols-3 gap-1.5 sm:grid-cols-6 lg:grid-cols-12">
              {s.months.map((m) => (
                <div key={m.month} className="rounded-lg bg-white/80 px-2 py-1.5 text-center">
                  <div className="text-[10.5px] font-bold uppercase text-canvas-muted">{MONTHS[m.month - 1]}</div>
                  <div className="font-mono text-[11.5px] font-bold tabular-nums">{fmtMoney(m.amount)}</div>
                </div>
              ))}
            </div>
          )}
          {s.accounts.length > 0 && (
            <ul className="flex flex-col divide-y divide-slate-100 text-[12px]">
              {s.accounts.map((a) => (
                <li key={a.code} className="flex justify-between gap-2 py-1"><span className="min-w-0 truncate">{a.code} · {a.name}</span><b className="font-mono tabular-nums">{fmtMoney(a.amount)}</b></li>
              ))}
            </ul>
          )}
        </div>
      )}
      <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-end">
        <label className="flex flex-col gap-1 sm:w-[240px]">
          <span className={labelCls}>{year} bütçesi (₺)</span>
          <input className={field} inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder={s?.budget ? String(s.budget.amount) : 'ör. 250000'} />
        </label>
        <button type="button" className={btnPrimary} disabled={!amount.trim() || save.isPending} onClick={() => save.mutate()}>Bütçeyi kaydet</button>
        <button type="button" className={btnGhost} onClick={() => setShowAccounts((v) => !v)}>{showAccounts ? 'Hesap listesini kapat' : 'Aday gider hesapları'}</button>
      </div>
      {showAccounts && (
        <div className="mt-2">
          {accounts.isLoading && <p className="text-[12px] text-canvas-muted">Logo'dan okunuyor…</p>}
          {accounts.error && <Note tone="err">{errText(accounts.error, 'Hesaplar okunamadı.')}</Note>}
          {acc && (
            <ul className="flex flex-col divide-y divide-slate-100 text-[12px]">
              {acc.items.length === 0 && <li className="py-1 text-canvas-muted">Adında eğitim, seminer ya da kurs geçen gider hesabı bulunamadı.</li>}
              {acc.items.map((a) => (
                <li key={a.code} className="flex justify-between gap-2 py-1">
                  <span className="min-w-0">{a.code} · {a.name}</span>
                  {acc.selected.includes(a.code) && <Pill tone="ok">Seçili</Pill>}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </Block>
  );
}
