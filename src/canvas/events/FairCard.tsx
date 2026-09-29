import { useEffect, useState, type ReactNode } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { BadgeCheck, FileChartColumn, Pencil, Trash2, CircleX } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import SqlInfo from '../components/SqlInfo';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText, field } from '../admin/ui';
import { Tabs, AskSheet } from '../budget/parts';
import { STATUS_TONE, evApi, fmtDay, fmtMoney, fmtRange, type FairDetail, type Meta } from './api';
import { Block, DaysLeft, EventsFrame, PrepBar } from './parts';
import FairForm from './FairForm';
import FairBooks from './FairBooks';
import { FairAuthors, FairCosts, FairTasks } from './FairOps';

/** Fuar kartı: özet · kitaplar ve adetler · görevler · gider · yazar programı. Sonuç ayrı sayfada (/sonuc). */

type Tab = 'ozet' | 'kitaplar' | 'gorevler' | 'gider' | 'yazarlar';

export default function FairCard() {
  const { id = '' } = useParams();
  const qc = useQueryClient();
  const nav = useNavigate();
  const [params, setParams] = useSearchParams();
  const tab = (params.get('sekme') as Tab) || 'ozet';
  const meta = useQuery({ queryKey: ['ev', 'meta'], queryFn: evApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const q = useQuery({ queryKey: ['ev', 'fair', id], queryFn: () => evApi.fair(id), enabled: ENGINE_ENABLED && !!id });
  const [edit, setEdit] = useState(false);
  const [ask, setAsk] = useState<null | 'approve' | 'cancel' | 'delete'>(null);

  const put = (d: FairDetail) => {
    qc.setQueryData(['ev', 'fair', id], d);
    qc.invalidateQueries({ queryKey: ['ev', 'calendar'] });
    qc.invalidateQueries({ queryKey: ['ev', 'upcoming'] });
  };
  const run = useMutation({
    mutationFn: async (fn: () => Promise<FairDetail>) => fn(),
    onSuccess: (d) => put(d),
    onError: (e) => toast.error(errText(e, 'İşlem yapılamadı.') ?? ''),
  });
  const remove = useMutation({
    mutationFn: () => evApi.remove(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['ev'] });
      toast.success('Kart silindi.');
      nav('/etkinlikler');
    },
    onError: (e) => toast.error(errText(e, 'Kart silinemedi.') ?? ''),
  });

  const m = meta.data;
  const f = q.data;
  const setTab = (t: Tab) => {
    const p = new URLSearchParams(params);
    if (t === 'ozet') p.delete('sekme');
    else p.set('sekme', t);
    setParams(p, { replace: true });
  };
  const late = f?.tasks.filter((t) => t.late).length ?? 0;
  const short = f?.bookList.filter((b) => b.stockShort).length ?? 0;
  const canApprove = !!m && !!f && m.me.canApprove && f.status === 'aday' && f.createdBy !== m.me.username;

  const aside = f && m ? (
    <div className="flex flex-wrap gap-2 lg:justify-end">
      <Link to={`/etkinlikler/fuar/${encodeURIComponent(f.id)}/sonuc`} className={btnPrimary}>
        <FileChartColumn aria-hidden className="h-4 w-4" />
        Sonuç raporu
      </Link>
      {m.me.canEdit && (
        <button type="button" className={btnGhost} onClick={() => setEdit(true)}>
          <Pencil aria-hidden className="h-4 w-4" />
          Düzenle
        </button>
      )}
      {canApprove && (
        <button type="button" className={btnGhost} onClick={() => setAsk('approve')}>
          <BadgeCheck aria-hidden className="h-4 w-4" />
          Katılımı onayla
        </button>
      )}
      {m.me.canEdit && f.status !== 'iptal' && (
        <button type="button" className={btnGhost} onClick={() => setAsk('cancel')}>
          <CircleX aria-hidden className="h-4 w-4" />
          İptal et
        </button>
      )}
      {m.me.canEdit && f.status === 'iptal' && (
        <button type="button" className={btnGhost} onClick={() => run.mutate(() => evApi.update(f.id, { status: 'aday' }))}>İptali geri al</button>
      )}
      {m.me.canEdit && f.status !== 'onayli' && (
        <button type="button" className={`${btnGhost} !text-red-700`} onClick={() => setAsk('delete')} aria-label="Kartı sil">
          <Trash2 aria-hidden className="h-4 w-4" />
        </button>
      )}
    </div>
  ) : null;

  return (
    <EventsFrame
      crumb="Fuar ve etkinlik"
      title={f?.name ?? 'Fuar kartı'}
      lead={f ? `Bu fuarın hazırlığı: götürülecek kitaplar ve adetler, görevler, gider ve yazar programı. Katılım kararı ve bütçe onay ister. ${fmtRange(f.startsOn, f.endsOn)} · ${[f.venue, f.city].filter(Boolean).join(', ') || 'yer girilmedi'} · ${f.kindLabel}` : undefined}
      source={`Logo ${m?.settings.channel ?? 'FUAR'} kanalı · CRM`}
      presence={f ? (f.status === 'onayli' ? f.phaseLabel : f.statusLabel) : '…'}
      detail={f?.name}
      back={{ to: '/etkinlikler', label: 'Takvim' }}
      aside={aside}
      nav={false}
    >
      {q.isLoading && <Loading />}
      {q.error && <Note tone="err">{errText(q.error, 'Kart açılamadı.')}</Note>}
      {f && m && (
        <>
          {f.status === 'aday' && (
            <Note tone="warn">
              Katılım kararı ve bütçe onayı bekleniyor. Onay yetkisi olan, kartı açandan başka biri onaylar.
            </Note>
          )}
          <div className="grid grid-cols-2 gap-2.5 lg:grid-cols-4 lg:gap-4">
            <Stat label="Başlangıca" info={<SqlInfo k={f.kaynaklar} alan="daysLeft" label="Başlangıca" />} value={<DaysLeft days={f.phase === 'suruyor' ? 0 : f.daysLeft} />} help={f.phase === 'bitti' ? 'Fuar bitti' : fmtDay(f.startsOn)} />
            <Stat label="Hazırlık" info={<SqlInfo k={f.kaynaklar} alan="tasksDone" label="Hazırlık" />} value={<PrepBar prep={f.prep} late={late} />} help={`${f.tasksDone}/${f.tasksTotal} görev${late ? ` · ${late} gecikti` : ''}`} />
            <Stat label="Gider / bütçe" info={<SqlInfo k={f.kaynaklar} alan="costTotal" label="Gider / bütçe" />} value={<span className="font-mono text-[18px] font-bold tabular-nums">{fmtMoney(f.costTotal)}</span>} help={`Bütçe ${fmtMoney(f.budgetPlanned)}`} />
            <Stat label="Kitap" info={<SqlInfo k={f.kaynaklar} alan="bookList" label="Kitap" />} value={<span className="font-mono text-[18px] font-bold tabular-nums">{f.bookList.length}</span>} help={short ? `${short} kitapta stok yetersiz` : 'Planlanan liste'} />
          </div>

          <Tabs<Tab>
            tabs={[
              { key: 'ozet', label: 'Özet' },
              { key: 'kitaplar', label: 'Kitaplar ve adetler', badge: short || null },
              { key: 'gorevler', label: 'Görevler', badge: late || null },
              { key: 'gider', label: 'Gider' },
              { key: 'yazarlar', label: 'Yazar programı', badge: f.authors.filter((a) => a.conflicts.length).length || null },
            ]}
            value={tab}
            onChange={setTab}
          />

          {tab === 'ozet' && <Summary f={f} m={m} onSave={(b) => run.mutate(() => evApi.update(f.id, b))} busy={run.isPending} />}
          {tab === 'kitaplar' && <FairBooks f={f} m={m} onChange={put} />}
          {tab === 'gorevler' && <FairTasks f={f} m={m} onChange={put} />}
          {tab === 'gider' && <FairCosts f={f} m={m} onChange={put} />}
          {tab === 'yazarlar' && <FairAuthors f={f} m={m} onChange={put} />}

          <FairForm open={edit} meta={m} initial={f} busy={run.isPending} onClose={() => setEdit(false)}
            onSave={(b) => run.mutate(() => evApi.update(f.id, b), {
              onSuccess: (d) => {
                setEdit(false);
                if (d.reopened) toast.warning('Tarih ya da bütçe değişti; kart yeniden karar bekliyor.');
                else toast.success('Kaydedildi.');
              },
            })} />
          <AskSheet open={ask === 'approve'} title="Katılımı ve bütçeyi onayla"
            message={<>«{f.name}» için katılım kararı ve {fmtMoney(f.budgetPlanned)} planlanan bütçe onaylanacak.</>}
            confirm="Onayla" input="Not (isteğe bağlı)" busy={run.isPending} onClose={() => setAsk(null)}
            onConfirm={(t) => run.mutate(() => evApi.approve(f.id, t || undefined), { onSuccess: () => { setAsk(null); toast.success('Onaylandı.'); } })} />
          <AskSheet open={ask === 'cancel'} title="Kartı iptal et" danger
            message={<>«{f.name}» iptal edilir; takvimde ve hatırlatmalarda görünmez. Sonra geri alınabilir.</>}
            confirm="İptal et" busy={run.isPending} onClose={() => setAsk(null)}
            onConfirm={() => run.mutate(() => evApi.update(f.id, { status: 'iptal' }), { onSuccess: () => setAsk(null) })} />
          <AskSheet open={ask === 'delete'} title="Kartı sil" danger
            message={<>«{f.name}» kartı; kitap listesi, görevleri, giderleri, fişleri ve yazar programıyla birlikte kalıcı olarak silinir.</>}
            confirm="Kalıcı olarak sil" busy={remove.isPending} onClose={() => setAsk(null)} onConfirm={() => remove.mutate()} />
        </>
      )}
    </EventsFrame>
  );
}

function Stat({ label, value, help, info }: { label: string; value: ReactNode; help: string; info?: ReactNode }) {
  return (
    <div className="glass-panel min-w-0 rounded-2xl p-3.5 shadow-glass-float sm:rounded-3xl sm:p-4">
      <div className="flex items-center gap-1 text-[11px] font-bold uppercase tracking-wide text-canvas-muted">{label}{info}</div>
      <div className="mt-1.5 flex min-h-7 items-center">{value}</div>
      <div className="mt-1 truncate text-[11.5px] leading-snug text-canvas-muted">{help}</div>
    </div>
  );
}

/** Özet: kartın bilgileri + bağlı CRM etkinlikleri + fuar carileri (sonuç raporu bu carilerin satışını sayar). */
function Summary({ f, m, onSave, busy }: { f: FairDetail; m: Meta; onSave: (b: { crmEventIds?: string[]; logoClientCodes?: string[] }) => void; busy: boolean }) {
  const [pickEvents, setPickEvents] = useState(false);
  const [pickClients, setPickClients] = useState(false);
  const pad = (iso: string, d: number) => new Date(Date.UTC(+iso.slice(0, 4), +iso.slice(5, 7) - 1, +iso.slice(8, 10) + d)).toISOString().slice(0, 10);
  const ev = useQuery({
    queryKey: ['ev', 'crm-window', f.startsOn, f.endsOn],
    queryFn: () => evApi.crmEvents({ frm: pad(f.startsOn, -7), to: pad(f.endsOn, 7) }),
    enabled: ENGINE_ENABLED && (pickEvents || f.crmEventIds.length > 0),
  });
  const clients = useQuery({ queryKey: ['ev', 'clients'], queryFn: evApi.clients, enabled: ENGINE_ENABLED && (pickClients || f.logoClientCodes.length > 0), staleTime: 10 * 60_000 });
  const [evSel, setEvSel] = useState<string[]>(f.crmEventIds);
  const [clSel, setClSel] = useState<string[]>(f.logoClientCodes);
  const [clQ, setClQ] = useState('');
  useEffect(() => setEvSel(f.crmEventIds), [f.crmEventIds]);
  useEffect(() => setClSel(f.logoClientCodes), [f.logoClientCodes]);
  const linked = (ev.data?.items ?? []).filter((e) => f.crmEventIds.includes(e.id));
  const clientName = new Map((clients.data?.items ?? []).map((c) => [c.kod, c.ad]));

  return (
    <div className="grid grid-cols-1 gap-3 lg:grid-cols-2 lg:gap-4">
      <Block title="Kart" info={<SqlInfo k={f.kaynaklar} alan="budgetPlanned" label="Kart ve bütçe" />}>
        <dl className="grid grid-cols-[minmax(0,140px)_minmax(0,1fr)] gap-x-3 gap-y-1.5 text-[12.5px]">
          <dt className="text-canvas-muted">Durum</dt>
          <dd><Pill tone={STATUS_TONE[f.status]}>{f.status === 'onayli' ? `Onaylı · ${f.phaseLabel}` : f.statusLabel}</Pill></dd>
          <dt className="text-canvas-muted">Karar</dt>
          <dd>{f.approvedBy ? `${f.approvedBy} · ${fmtDay(f.approvedAt)}${f.decisionNote ? ` — ${f.decisionNote}` : ''}` : '—'}</dd>
          <dt className="text-canvas-muted">Sorumlu</dt>
          <dd>{f.owner ?? '—'}</dd>
          <dt className="text-canvas-muted">Planlanan bütçe</dt>
          <dd className="font-mono tabular-nums">{fmtMoney(f.budgetPlanned)}</dd>
          <dt className="text-canvas-muted">Stant</dt>
          <dd className="whitespace-pre-line break-words">{f.standInfo || '—'}</dd>
          <dt className="text-canvas-muted">Geçen yılın fuarı</dt>
          <dd>{f.prev ? <Link className="font-bold text-canvas-violet hover:underline" to={`/etkinlikler/fuar/${encodeURIComponent(f.prev.id)}`}>{f.prev.name}</Link> : 'bağlı değil (aynı günlerin geçen yılı)'}</dd>
          <dt className="text-canvas-muted">Not</dt>
          <dd className="whitespace-pre-line break-words">{f.note || '—'}</dd>
          <dt className="text-canvas-muted">Açan</dt>
          <dd>{f.createdBy}</dd>
        </dl>
      </Block>

      <div className="flex min-w-0 flex-col gap-3 lg:gap-4">
        <Block title="Fuar carileri (Logo)"
          help={`Cari, Logo'daki müşteri hesabıdır. Sonuç raporu ve kitap önerisi, fuardaki satışın faturalandığı bu carilerin «${m.settings.channel}» kanalı satışını sayar. Boşsa aynı günlerdeki bütün ${m.settings.channel} kanalı satışı sayılır.`}
          action={m.me.canEdit ? <button type="button" className={btnGhost} onClick={() => setPickClients((v) => !v)}>{pickClients ? 'Kapat' : 'Cari seç'}</button> : undefined}>
          {f.logoClientCodes.length === 0 && !pickClients && <p className="text-[12.5px] text-canvas-muted">Cari bağlanmadı; sonuç, aynı günlerdeki bütün fuar kanalı satışıyla hesaplanır. Fuardaki satışın faturalandığı Logo carisini «Cari seç» ile bağlayın.</p>}
          {!pickClients && f.logoClientCodes.length > 0 && (
            <ul className="flex flex-wrap gap-1.5">
              {f.logoClientCodes.map((c) => <li key={c}><Pill tone="violet">{c}{clientName.get(c) ? ` · ${clientName.get(c)}` : ''}</Pill></li>)}
            </ul>
          )}
          {pickClients && (
            <div className="flex flex-col gap-2">
              {clients.isLoading && <Loading />}
              {clients.error && <Note tone="err">{errText(clients.error, 'Cari listesi okunamadı.')}</Note>}
              {clients.data && (
                <>
                  <input className={field} value={clQ} placeholder="Kod ya da ad" onChange={(e) => setClQ(e.target.value)} />
                  <ul className="max-h-[320px] overflow-y-auto rounded-xl border border-slate-100 bg-white/80">
                    {clients.data.items.filter((c) => !clQ || `${c.kod} ${c.ad ?? ''}`.toLocaleLowerCase('tr').includes(clQ.toLocaleLowerCase('tr'))).map((c) => (
                      <li key={c.kod}>
                        <label className="flex min-h-11 cursor-pointer items-center gap-2 px-3 py-1.5 text-[12.5px] hover:bg-slate-50">
                          <input type="checkbox" className="h-4 w-4" checked={clSel.includes(c.kod)}
                            onChange={(e) => setClSel((s) => (e.target.checked ? [...s, c.kod] : s.filter((x) => x !== c.kod)))} />
                          <span className="font-mono text-[11.5px]">{c.kod}</span>
                          <span className="min-w-0 flex-1 truncate">{c.ad}</span>
                          {c.pasif && <Pill tone="muted">pasif</Pill>}
                        </label>
                      </li>
                    ))}
                  </ul>
                  <div className="flex justify-end gap-2">
                    <span className="mr-auto self-center text-[11.5px] text-canvas-muted">{clSel.length} cari seçili · {clients.data.items.length} {clients.data.channel} carisi</span>
                    <button type="button" className={btnPrimary} disabled={busy} onClick={() => { onSave({ logoClientCodes: clSel }); setPickClients(false); }}>Kaydet</button>
                  </div>
                </>
              )}
            </div>
          )}
        </Block>

        <Block title="Bağlı CRM etkinlikleri"
          help="Katılımcı, satılan adet ve CRM'deki gider sonuç raporuna bu kayıtlardan gelir. CRM kaydı yalnız okunur."
          action={m.me.canEdit ? <button type="button" className={btnGhost} onClick={() => setPickEvents((v) => !v)}>{pickEvents ? 'Kapat' : 'Etkinlik bağla'}</button> : undefined}>
          {f.crmEventIds.length === 0 && !pickEvents && <p className="text-[12.5px] text-canvas-muted">Bağlı CRM etkinliği yok. CRM'de bu fuar için açılmış etkinlik kaydı varsa bağlayın; katılımcı ve satılan adet sonuca oradan gelir.</p>}
          {!pickEvents && f.crmEventIds.length > 0 && (
            <ul className="flex flex-col gap-1 text-[12.5px]">
              {f.crmEventIds.map((i) => {
                const e = linked.find((x) => x.id === i);
                return <li key={i} className="truncate">{e ? `${fmtDay(e.baslangic)} · ${e.ad ?? e.tip} · ${e.durumAdi}` : ev.isLoading ? 'okunuyor…' : `${i} (tarih aralığı dışında)`}</li>;
              })}
            </ul>
          )}
          {pickEvents && (
            <div className="flex flex-col gap-2">
              <p className="text-[11.5px] text-canvas-muted">Fuar günlerinin 7 gün öncesi ve sonrası: {ev.data?.total ?? '…'} kayıt.</p>
              {ev.isLoading && <Loading />}
              {ev.error && <Note tone="err">{errText(ev.error, 'CRM etkinlikleri okunamadı.')}</Note>}
              <ul className="max-h-[320px] overflow-y-auto rounded-xl border border-slate-100 bg-white/80">
                {(ev.data?.items ?? []).map((e) => (
                  <li key={e.id}>
                    <label className="flex min-h-11 cursor-pointer items-center gap-2 px-3 py-1.5 text-[12.5px] hover:bg-slate-50">
                      <input type="checkbox" className="h-4 w-4" checked={evSel.includes(e.id)}
                        onChange={(x) => setEvSel((s) => (x.target.checked ? [...s, e.id] : s.filter((y) => y !== e.id)))} />
                      <span className="w-16 shrink-0 font-mono text-[11px]">{fmtDay(e.baslangic).split(' ').slice(0, 2).join(' ')}</span>
                      <span className="min-w-0 flex-1 truncate">{e.ad || e.tip}</span>
                      <span className="hidden shrink-0 text-[11px] text-canvas-muted sm:inline">{e.tip}</span>
                    </label>
                  </li>
                ))}
              </ul>
              {(ev.data?.total ?? 0) > (ev.data?.items.length ?? 0) && (
                <p className="text-[11px] text-canvas-muted">İlk {ev.data?.items.length} kayıt gösteriliyor; aradığınız yoksa «CRM etkinlikleri» bölümünden arayın.</p>
              )}
              <div className="flex justify-end">
                <button type="button" className={btnPrimary} disabled={busy} onClick={() => { onSave({ crmEventIds: evSel }); setPickEvents(false); }}>Kaydet</button>
              </div>
            </div>
          )}
        </Block>
      </div>
    </div>
  );
}
