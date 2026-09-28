import { useEffect, useRef, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ArrowLeft, Download, Loader2, Trash2, Upload } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, Pill, Section, TableWrap, btnGhost, btnPrimary, errText, field, label, td, th } from '../admin/ui';
import { Kpi, KpiRow, Panel } from '../editorial/kit';
import { fmtDay, fmtInt, readersApi, type ImportDetail } from './api';
import { ROOT, useMeta } from './parts';

/** Etkinlik/fuar katılımcı dosyası: yükle → kolon eşle → eşleştir (eşleşti / yeni / geçersiz / izin eksik). */
export default function Imports() {
  const { pathname } = useLocation();
  const rest = pathname.replace(/\/+$/, '').slice(`${ROOT}/yuklemeler`.length).replace(/^\//, '');
  return rest ? <ImportScreen id={decodeURIComponent(rest)} /> : <ImportList />;
}

function ImportList() {
  const meta = useMeta();
  const nav = useNavigate();
  const qc = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const q = useQuery({ queryKey: ['readers', 'imports'], queryFn: readersApi.imports, enabled: ENGINE_ENABLED });
  const up = useMutation({
    mutationFn: (f: File) => readersApi.upload(f),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ['readers', 'imports'] });
      nav(`${ROOT}/yuklemeler/${r.id}`);
    },
    onError: (e) => toast.error(errText(e, 'Dosya yüklenemedi.') ?? ''),
  });
  const s = meta.data?.settings;
  return (
    <Section
      title="Etkinlik ve fuar yüklemeleri"
      help={`CSV ya da Excel (en çok ${s?.fileMaxMb ?? 20} MB). Kişi satırları ${s?.importRetentionDays ?? 30} gün sonra silinir; sayılar kalır. Dosyadaki izin kolonu bilgi amaçlıdır, İYS izni yerine geçmez.`}
      action={meta.data?.me.canImport ? (
        <>
          <input ref={input} type="file" accept=".csv,.txt,.xlsx" className="sr-only" aria-label="Dosya seç"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) up.mutate(f); e.target.value = ''; }} />
          <button type="button" className={btnPrimary} disabled={up.isPending} onClick={() => input.current?.click()}>
            {up.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Upload aria-hidden className="h-4 w-4" />}Dosya yükle
          </button>
        </>
      ) : undefined}
    >
      {q.isLoading && <Loading />}
      {q.error && <Note tone="err">{errText(q.error, 'Yüklemeler açılamadı.')}</Note>}
      {q.data && q.data.items.length === 0 && <Note tone="info">Henüz yükleme yok.</Note>}
      <ul className="flex flex-col gap-2">
        {q.data?.items.map((i) => (
          <li key={i.id}>
            <Link to={`${ROOT}/yuklemeler/${i.id}`} className="flex flex-col gap-1 rounded-2xl border border-slate-100 bg-white/80 p-3 transition-colors duration-150 hover:bg-white sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0">
                <div className="truncate text-[13px] font-extrabold">{i.eventName ?? i.fileName}</div>
                <div className="text-[11.5px] text-canvas-muted">{i.fileName} · {i.uploadedBy} · {fmtDay(i.at)}{i.eventDate ? ` · etkinlik ${fmtDay(i.eventDate)}` : ''}</div>
              </div>
              <div className="flex flex-wrap gap-1 text-[11.5px]">
                {i.status === 'yuklendi' && <Pill tone="warn">Eşleştirme bekliyor</Pill>}
                {i.status === 'silindi' && <Pill tone="muted">Satırlar silindi</Pill>}
                <Pill tone="muted">{fmtInt(i.rows)} satır</Pill>
                {i.status !== 'yuklendi' && <><Pill tone="ok">{fmtInt(i.matched)} eşleşti</Pill><Pill tone="violet">{fmtInt(i.new)} yeni</Pill><Pill tone="warn">{fmtInt(i.missingConsent)} izin eksik</Pill></>}
              </div>
            </Link>
          </li>
        ))}
      </ul>
    </Section>
  );
}

function ImportScreen({ id }: { id: string }) {
  const meta = useMeta();
  const qc = useQueryClient();
  const [filter, setFilter] = useState('');
  const [page, setPage] = useState(0);
  const q = useQuery({ queryKey: ['readers', 'import', id, filter, page], queryFn: () => readersApi.importDetail(id, filter, page), enabled: ENGINE_ENABLED });
  const d = q.data;
  const [mapping, setMapping] = useState<Record<string, number | null>>({});
  const [eventName, setEventName] = useState('');
  const [eventDate, setEventDate] = useState(new Date().toISOString().slice(0, 10));
  useEffect(() => {
    if (d) {
      setMapping(d.mapping);
      if (d.eventName) setEventName(d.eventName);
      if (d.eventDate) setEventDate(d.eventDate);
    }
    // Yalnız yükleme değişince doldurulur; sayfa/filtre değişimi eşlemeyi sıfırlamaz.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [d?.id, d?.status]);
  const confirm = useMutation({
    mutationFn: () => readersApi.confirm(id, { mapping, eventName, eventDate }),
    onSuccess: (r) => {
      toast.success(`${fmtInt(r.matched)} eşleşti, ${fmtInt(r.new)} yeni, ${fmtInt(r.missingConsent)} izin eksik.`);
      qc.invalidateQueries({ queryKey: ['readers'] });
    },
    onError: (e) => toast.error(errText(e, 'Eşleştirilemedi.') ?? ''),
  });
  const csv = useMutation({ mutationFn: () => readersApi.crmCsv(id), onError: (e) => toast.error(errText(e, 'Liste alınamadı.') ?? '') });
  const purge = useMutation({
    mutationFn: () => readersApi.purgeImport(id),
    onSuccess: () => { toast.success('Kişi satırları silindi; sayılar kaldı.'); qc.invalidateQueries({ queryKey: ['readers'] }); },
    onError: (e) => toast.error(errText(e, 'Silinemedi.') ?? ''),
  });
  if (q.isLoading) return <Loading />;
  if (q.error) return <Note tone="err">{errText(q.error, 'Yükleme açılamadı.')}</Note>;
  if (!d) return null;
  const me = meta.data?.me;
  const canImport = !!me?.canImport && d.status !== 'silindi';
  const mine = !!me && d.uploadedBy.toLowerCase() === me.username.toLowerCase();
  return (
    <div className="flex flex-col gap-3 lg:gap-4">
      <Link to={`${ROOT}/yuklemeler`} className="inline-flex items-center gap-1 px-1 text-[12.5px] font-extrabold text-canvas-violet hover:underline">
        <ArrowLeft aria-hidden className="h-3.5 w-3.5" /> Yüklemeler
      </Link>
      <div>
        <h2 className="text-xl font-extrabold tracking-tight">{d.eventName ?? d.fileName}</h2>
        <p className="text-[12px] text-canvas-muted">{d.fileName} · {d.uploadedBy} · {fmtDay(d.at)} · satırlar {fmtDay(d.purgeAfter)} tarihinde silinir</p>
      </div>
      {d.status !== 'yuklendi' && (
        <KpiRow>
          <Kpi label="Eşleşti" value={fmtInt(d.matched)} help="Okur kaydı bulundu; etkinlik zaman çizelgesine yazıldı" />
          <Kpi label="Yeni" value={fmtInt(d.new)} help="CRM'de yok; CRM'e işlenecek listede" />
          <Kpi label="İzin eksik" value={fmtInt(d.missingConsent)} help="Eşleşen ama e-posta izni İYS'de olmayan" />
          <Kpi label="Geçersiz / tekrar" value={`${fmtInt(d.rejected)} / ${fmtInt(d.duplicates)}`} help="E-posta ve cep telefonu yok / dosyada ikinci kez" />
        </KpiRow>
      )}

      {canImport && (
        <Panel>
          <h2 className="text-[15px] font-extrabold">{d.status === 'yuklendi' ? 'Kolonları eşleyin' : 'Eşlemeyi değiştirip yeniden eşleştir'}</h2>
          <p className="mt-0.5 text-[11.5px] text-canvas-muted">Eşleştirme e-posta, yoksa cep telefonuyla yapılır. Başlıklardan tahmin edildi; kontrol edin.</p>
          <div className="mt-2 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            {Object.entries(d.roles).map(([role, text]) => (
              <div key={role}>
                <label className={label} htmlFor={`rol-${role}`}>{text}</label>
                <select id={`rol-${role}`} className={field} value={mapping[role] ?? ''}
                  onChange={(e) => setMapping((m) => ({ ...m, [role]: e.target.value === '' ? null : Number(e.target.value) }))}>
                  <option value="">—</option>
                  {d.headers.map((h, i) => <option key={i} value={i}>{h}</option>)}
                </select>
              </div>
            ))}
          </div>
          <div className="mt-2 grid gap-2 sm:grid-cols-[2fr_1fr]">
            <div>
              <label className={label} htmlFor="etkinlik-ad">Etkinlik adı</label>
              <input id="etkinlik-ad" className={field} value={eventName} onChange={(e) => setEventName(e.target.value)} placeholder="Örn. 2026 İstanbul Kitap Fuarı imza günü" />
            </div>
            <div>
              <label className={label} htmlFor="etkinlik-tarih">Tarih</label>
              <input id="etkinlik-tarih" type="date" className={field} value={eventDate} onChange={(e) => setEventDate(e.target.value)} />
            </div>
          </div>
          <button type="button" className={`${btnPrimary} mt-2`} disabled={confirm.isPending || eventName.trim().length < 3 || (mapping.eposta == null && mapping.telefon == null)} onClick={() => confirm.mutate()}>
            {confirm.isPending && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}Eşleştir
          </button>
        </Panel>
      )}

      <div className="flex flex-wrap items-center gap-2">
        {['', 'eslesti', 'yeni', 'gecersiz', 'tekrar'].map((s) => (
          <button key={s} type="button" aria-pressed={filter === s} onClick={() => { setFilter(s); setPage(0); }}
            className={`min-h-11 rounded-xl px-3 text-[12px] font-extrabold transition-colors duration-150 sm:min-h-8 ${filter === s ? 'bg-canvas-violet text-white' : 'bg-slate-100 hover:bg-slate-200'}`}>
            {s ? `${meta.data?.importRowStatuses[s] ?? s} (${fmtInt(d.byStatus[s] ?? 0)})` : `Hepsi (${fmtInt(d.rows)})`}
          </button>
        ))}
        <span className="ml-auto flex flex-wrap gap-2">
          {d.new > 0 && d.status === 'eslesti' && me?.canExport && (mine || me.canPersonal) && (
            <button type="button" className={btnGhost} disabled={csv.isPending} onClick={() => csv.mutate()}>
              <Download aria-hidden className="h-4 w-4" />CRM'e işlenecek yeni kişiler
            </button>
          )}
          {canImport && (
            <button type="button" className={btnGhost} disabled={purge.isPending} onClick={() => purge.mutate()}>
              <Trash2 aria-hidden className="h-4 w-4" />Kişi satırlarını şimdi sil
            </button>
          )}
        </span>
      </div>

      {d.status === 'silindi' ? <Note tone="info">Kişi satırları saklama süresi sonunda silindi; yalnız sayılar duruyor.</Note> : (
        <RowsTable d={d} personal={!!me?.canPersonal} />
      )}
      {d.total > d.pageSize && (
        <div className="flex items-center justify-between gap-2 text-[12px] font-semibold text-canvas-muted">
          <span>{fmtInt(d.page * d.pageSize + 1)}–{fmtInt(Math.min(d.total, (d.page + 1) * d.pageSize))} / {fmtInt(d.total)}</span>
          <div className="flex gap-1">
            <button type="button" className={btnGhost} disabled={page === 0} onClick={() => setPage((p) => p - 1)}>Önceki</button>
            <button type="button" className={btnGhost} disabled={(page + 1) * d.pageSize >= d.total} onClick={() => setPage((p) => p + 1)}>Sonraki</button>
          </div>
        </div>
      )}
    </div>
  );
}

function RowsTable({ d, personal }: { d: ImportDetail; personal: boolean }) {
  return (
    <TableWrap>
      <thead>
        <tr>
          <th className={th}>Satır</th><th className={th}>Durum</th>{personal && <th className={th}>Ad</th>}
          <th className={th}>E-posta</th><th className={th}>Telefon</th><th className={th}>İl</th><th className={th}>Okur</th>
        </tr>
      </thead>
      <tbody>
        {d.items.map((r) => (
          <tr key={r.row} className="border-t border-slate-100">
            <td className={`${td} font-mono tabular-nums`}>{r.row}</td>
            <td className={td}>
              <span className="flex flex-wrap gap-1">
                <Pill tone={r.status === 'eslesti' ? 'ok' : r.status === 'yeni' ? 'violet' : r.status === 'bekliyor' ? 'muted' : 'warn'}>{r.statusLabel}</Pill>
                {r.missingConsent && <Pill tone="warn">İzin eksik</Pill>}
              </span>
            </td>
            {personal && <td className={td}>{r.name ?? '—'}</td>}
            <td className={`${td} break-all`}>{r.email ?? '—'}</td>
            <td className={`${td} whitespace-nowrap`}>{r.phone ?? '—'}</td>
            <td className={td}>{r.city ?? '—'}</td>
            <td className={td}>{r.readerId ? <Link className="font-mono text-canvas-violet hover:underline" to={`${ROOT}/kisi/${r.readerId}`}>{r.readerId}</Link> : '—'}</td>
          </tr>
        ))}
      </tbody>
    </TableWrap>
  );
}
