import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Calculator, CheckCheck, ChevronLeft, Loader2, Plus, Send, Undo2, X } from 'lucide-react';
import { toast } from 'sonner';
import { Note, Pill, btnGhost, btnPrimary, field } from '../../admin/ui';
import { Kpi, KpiRow, ModuleFrame, Panel } from '../kit';
import { RunNotePanel } from './Drafts';
import { NumInput } from '../contracts/TermsForm';
import { Field, Sheet, Tabs, day, errMsg, money, num, stamp } from '../contracts/ui';
import { Advances } from './Advances';
import { PartyStatements, PaymentList } from './PartyStatements';
import { Renewals } from './Renewals';
import { RunLines } from './RunLines';
import { metaOptions, royaltyApi, runTone, type Meta, type Run } from './api';
import SqlInfo from '../../components/SqlInfo';

/** M54 Telif dönemi: dönem koşusu (M6'nın hesabıyla bütün satıştan ödemeli sözleşmeler), istisnalar, iki gözlü onay,
 *  hak sahibi beyannamesi, ödeme listesi, avans portföyü ve yenilemeler. CRM'e, Logo'ya ve bankaya yazılmaz. */

type Tab = 'kosu' | 'istisna' | 'hak-sahipleri' | 'odeme' | 'avans' | 'yenileme';
const BUSY = new Set(['hesaplaniyor', 'onaylaniyor']);

export default function RoyaltyScreen() {
  const [params, setParams] = useSearchParams();
  const tab = (params.get('sekme') as Tab) || 'kosu';
  const runParam = params.get('kosu');
  const setMany = (kv: Record<string, string | null>) => setParams((p) => {
    const n = new URLSearchParams(p);
    for (const [k, v] of Object.entries(kv)) {
      if (v) n.set(k, v);
      else n.delete(k);
    }
    return n;
  }, { replace: true });
  const set = (k: string, v: string | null) => setMany({ [k]: v });
  const [creating, setCreating] = useState(false);
  const meta = useQuery(metaOptions());
  const runs = useQuery({ queryKey: ['royalty', 'runs'], queryFn: royaltyApi.runs });
  const list = runs.data?.items ?? [];
  const runId = runParam || list.find((r) => r.status !== 'iptal')?.id || list[0]?.id || null;
  const run = useQuery({
    queryKey: ['royalty', 'run', runId],
    queryFn: () => royaltyApi.run(runId!),
    enabled: !!runId,
    refetchInterval: (q) => (q.state.data && BUSY.has(q.state.data.status) ? 3000 : false),
  });
  const m = meta.data;
  const r = run.data;
  const can = m?.can;
  const err = errMsg(meta.error || runs.error, 'Telif dönemi okunamadı.');
  const needsRun = tab === 'kosu' || tab === 'istisna' || tab === 'hak-sahipleri' || tab === 'odeme';

  return (
    <ModuleFrame
      route="/telif-donem"
      crumb="Telif dönemi"
      title="Telif dönemi"
      lead="Satıştan ödemeli bütün sözleşmelerin dönem telifi tek koşuda hesaplanır; yalnız istisnalarla uğraşırsınız. Onaylanan koşu sözleşmelerin hakedişini ve ödeme takvimini oluşturur. CRM'e, Logo'ya ve bankaya hiçbir şey yazılmaz."
      source="Logo satışı + CRM sözleşmeleri"
      presence={r ? `${r.no} · ${r.statusLabel}` : 'Kaynak: Logo ve CRM'}
      aside={
        <div className="flex flex-wrap items-center justify-start gap-1.5 lg:justify-end">
          {list.length > 0 && (
            <select aria-label="Koşu" value={runId ?? ''} onChange={(e) => set('kosu', e.target.value)} className={`${field} w-auto max-w-full`}>
              {list.map((x) => (
                <option key={x.id} value={x.id}>{x.no} · {x.label} · {x.statusLabel}</option>
              ))}
            </select>
          )}
          {can?.run && (
            <button type="button" className={btnPrimary} onClick={() => setCreating(true)}>
              <Plus aria-hidden className="h-4 w-4" />
              Yeni koşu
            </button>
          )}
        </div>
      }
    >
      <div className="px-1">
        <Link to="/telif-sozlesme" className="inline-flex min-h-11 items-center gap-1 text-[12px] font-bold text-canvas-violet hover:underline sm:min-h-0">
          <ChevronLeft aria-hidden className="h-4 w-4" />
          Sözleşmeler
        </Link>
      </div>
      {err && <Note tone="err">{err}</Note>}
      {(meta.isLoading || runs.isLoading) && <p className="py-10 text-center text-[12.5px] text-canvas-muted">Okunuyor…</p>}
      {m && r && <RunHeader run={r} meta={m} />}
      {m && (
        <Tabs
          value={tab}
          onChange={(t) => set('sekme', t)}
          items={[
            { id: 'kosu', label: 'Koşu' },
            { id: 'istisna', label: 'İstisnalar', count: r?.summary.counts?.istisna },
            { id: 'hak-sahipleri', label: 'Hak sahipleri' },
            { id: 'odeme', label: 'Ödeme listesi' },
            { id: 'avans', label: 'Avans' },
            { id: 'yenileme', label: 'Yenilemeler' },
          ]}
        />
      )}
      {m && needsRun && !runId && !runs.isLoading && (
        <Panel>
          <div className="py-8 text-center">
            <p className="text-[13px] font-extrabold">Henüz telif dönemi koşusu yok</p>
            <p className="mt-1 text-[12.5px] text-canvas-muted">Önerilen dönem {day(m.defaultPeriod.start)} – {day(m.defaultPeriod.end)}.</p>
            {can?.run && (
              <button type="button" className={`${btnPrimary} mt-3`} onClick={() => setCreating(true)}>
                <Plus aria-hidden className="h-4 w-4" /> Koşu aç
              </button>
            )}
          </div>
        </Panel>
      )}
      {m && r && tab === 'kosu' && <Summary run={r} meta={m} onReason={(code) => setMany({ sekme: 'istisna', neden: code })} />}
      {m && r && tab === 'kosu' && <RunNotePanel key={r.id} run={r} />}
      {m && r && tab === 'kosu' && r.status !== 'taslak' && <RunLines run={r} meta={m} title="Bütün satırlar" />}
      {m && r && tab === 'istisna' && (
        r.status === 'taslak' ? <Panel><p className="py-8 text-center text-[12.5px] text-canvas-muted">Koşu henüz hesaplanmadı.</p></Panel>
          : <RunLines key={params.get('neden') ?? ''} run={r} meta={m} status="istisna" code={params.get('neden') ?? ''} />
      )}
      {m && r && tab === 'hak-sahipleri' && <PartyStatements run={r} can={m.can} />}
      {m && r && tab === 'odeme' && <PaymentList run={r} can={m.can} />}
      {m && tab === 'avans' && <Advances meta={m} />}
      {m && tab === 'yenileme' && <Renewals meta={m} />}
      {creating && m && <NewRunSheet meta={m} onClose={() => setCreating(false)} onCreated={(id) => set('kosu', id)} />}
    </ModuleFrame>
  );
}

function Summary({ run, meta, onReason }: { run: Run; meta: Meta; onReason: (code: string) => void }) {
  const s = run.summary;
  const k = run.kaynaklar;
  const totals = Object.entries(s.totals ?? {});
  if (run.status === 'taslak' && !s.lines) {
    return <Panel><p className="py-6 text-center text-[12.5px] text-canvas-muted">Koşu açıldı; «Hesapla» ile kapsamdaki bütün sözleşmeler okunur ve hesaplanır.</p></Panel>;
  }
  return (
    <>
      <KpiRow>
        <Kpi label="Kapsam" value={num(s.lines ?? 0, 0)} help={`CRM ${num(s.crmScope ?? 0, 0)}${s.portalOnly ? ` + portal ${num(s.portalOnly, 0)}` : ''} sözleşme`}
          info={<SqlInfo k={k} alan="summary.lines" label="Kapsam" />} />
        <Kpi label="Hesaplandı" value={num(s.counts?.hesaplandi ?? 0, 0)} help="Onaya hazır" info={<SqlInfo k={k} alan="summary.counts" label="Hesaplandı" />} />
        <Kpi label="İstisna" value={num(s.counts?.istisna ?? 0, 0)} help={s.counts?.istisna ? 'Çözülmeden onaya gitmez' : 'Yok'}
          info={<SqlInfo k={k} alan="sayac.istisna" label="İstisna (İstisnalar sekmesinin rozeti)" />} />
        <Kpi label="Hariç" value={num(s.counts?.haric ?? 0, 0)} help="Gerekçesiyle ya da dönem dışı" info={<SqlInfo k={k} alan="summary.counts" label="Hariç" />} />
      </KpiRow>
      {totals.length > 0 && (
        <KpiRow>
          {totals.map(([cur, t]) => (
            <Kpi key={cur} label={`Ödenecek (${meta.currencies[cur] ?? cur})`} value={money(t.net, cur)}
              help={`Brüt ${money(t.gross, cur)} · avans ${money(t.advance, cur)} · stopaj ${money(t.withholding, cur)} · ${num(t.count ?? 0, 0)} sözleşme`}
              info={<SqlInfo k={k} alan="summary.totals" label={`Ödenecek (${cur})`} />} />
          ))}
        </KpiRow>
      )}
      {Object.keys(s.reasons ?? {}).length > 0 && (
        <Panel>
          <h3 className="mb-2 flex items-center gap-1 text-[13px] font-extrabold">İstisnalar nedene göre <SqlInfo k={k} alan="summary.reasons" label="İstisnalar nedene göre" /></h3>
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(s.reasons ?? {}).map(([code, n]) => (
              <button key={code} type="button" onClick={() => onReason(code)}
                className="inline-flex min-h-11 items-center gap-1.5 rounded-xl bg-white/80 px-3 text-[12px] font-bold transition-transform duration-150 ease-out hover:bg-white active:scale-[0.97] sm:min-h-9">
                {meta.exceptions[code]?.label ?? code}
                <span className="rounded-md bg-slate-100 px-1.5 font-mono text-[11px] tabular-nums">{num(n, 0)}</span>
              </button>
            ))}
          </div>
        </Panel>
      )}
    </>
  );
}

type Action = 'submit' | 'reject' | 'cancel' | 'fx' | null;

function RunHeader({ run, meta }: { run: Run; meta: Meta }) {
  const qc = useQueryClient();
  const [action, setAction] = useState<Action>(null);
  const me = meta.me.username;
  const refresh = () => qc.invalidateQueries({ queryKey: ['royalty'] });
  const onErr = (e: unknown) => toast.error(errMsg(e) ?? 'İşlem tamamlanamadı.');
  const compute = useMutation({ mutationFn: () => royaltyApi.compute(run.id), onSuccess: () => { toast.success('Hesap başladı; ilerleme burada görünür.'); refresh(); }, onError: onErr });
  const approve = useMutation({ mutationFn: () => royaltyApi.approve(run.id), onSuccess: () => { toast.success('Onay başladı; hakedişler oluşturuluyor.'); refresh(); }, onError: onErr });
  const withdraw = useMutation({ mutationFn: () => royaltyApi.withdraw(run.id), onSuccess: refresh, onError: onErr });
  const busy = BUSY.has(run.status);
  const p = run.progress;
  const selfBlocked = me === run.preparedBy || me === run.submittedBy;
  const foreign = Object.entries(run.summary.fx ?? {});
  return (
    <Panel>
      <div className="flex flex-wrap items-center gap-2">
        <Pill tone={runTone(run.status)}>{run.statusLabel}</Pill>
        <span className="text-[13px] font-extrabold">{run.no} · {run.label}</span>
        {run.dataEnd && <span className="text-[11.5px] text-canvas-muted">Logo satışı {day(run.dataEnd)} gününe kadar</span>}
        <div className="ml-auto flex flex-wrap gap-1.5">
          {meta.can.run && (run.status === 'taslak' || run.status === 'hesaplandi') && (
            <>
              <button type="button" className={btnGhost} onClick={() => setAction('fx')}>Kur</button>
              <button type="button" className={run.status === 'taslak' ? btnPrimary : btnGhost} disabled={compute.isPending} onClick={() => compute.mutate()}>
                {compute.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Calculator aria-hidden className="h-4 w-4" />}
                {run.status === 'taslak' ? 'Hesapla' : 'Yeniden hesapla'}
              </button>
            </>
          )}
          {meta.can.run && run.status === 'hesaplandi' && (
            <button type="button" className={btnPrimary} onClick={() => setAction('submit')}>
              <Send aria-hidden className="h-4 w-4" /> Onaya gönder
            </button>
          )}
          {meta.can.run && run.status === 'onayda' && (
            <button type="button" className={btnGhost} disabled={withdraw.isPending} onClick={() => withdraw.mutate()}>
              <Undo2 aria-hidden className="h-4 w-4" /> Geri çek
            </button>
          )}
          {meta.can.approve && run.status === 'onayda' && (
            <>
              <button type="button" className={btnGhost} disabled={selfBlocked} onClick={() => setAction('reject')}>Geri gönder</button>
              <button type="button" className={btnPrimary} disabled={selfBlocked || approve.isPending} onClick={() => approve.mutate()}
                title={selfBlocked ? 'Hesaplatan ya da gönderen onaylayamaz' : undefined}>
                {approve.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <CheckCheck aria-hidden className="h-4 w-4" />}
                {run.error ? 'Onayı sürdür' : 'Onayla'}
              </button>
            </>
          )}
          {meta.can.run && ['taslak', 'hesaplandi', 'onayda'].includes(run.status) && (
            <button type="button" className={btnGhost} onClick={() => setAction('cancel')} aria-label="Koşuyu iptal et">
              <X aria-hidden className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>
      {busy && (
        <div className="mt-3 flex items-center gap-2 text-[12.5px]">
          <Loader2 aria-hidden className="h-4 w-4 animate-spin text-canvas-violet" />
          <span className="font-semibold">{p.step ?? 'Çalışıyor'}</span>
          {p.total ? <span className="font-mono tabular-nums text-canvas-muted">{num(p.done ?? 0, 0)} / {num(p.total, 0)}</span> : null}
          {p.total ? <SqlInfo k={run.kaynaklar} alan="progress" label="İlerleme" /> : null}
        </div>
      )}
      {meta.can.approve && run.status === 'onayda' && selfBlocked && (
        <div className="mt-2"><Note tone="info">Bu koşuyu siz hesaplattınız ya da onaya gönderdiniz; onayı başka bir kişi verir.</Note></div>
      )}
      {run.error && <div className="mt-2"><Note tone={run.status === 'hesaplandi' && run.error.startsWith('Geri') ? 'warn' : 'err'}>{run.error}</Note></div>}
      {run.summary.dataIncomplete && <div className="mt-2"><Note tone="warn">Logo satışı dönem sonuna ulaşmıyor ({day(run.dataEnd)}); dönemin sonrası eksik okunmuş olabilir.</Note></div>}
      {(run.summary.missingYears?.length ?? 0) > 0 && <div className="mt-2"><Note tone="warn">Logo'da şu yılların satış görünümü yok: {run.summary.missingYears!.join(', ')}.</Note></div>}
      {foreign.length > 0 && (
        <p className="mt-2 text-[11.5px] text-canvas-muted">
          Kur: {foreign.map(([c, f]) => (f ? `${c} ${num(f.rate, 4)} (${f.source}, ${day(f.on)})` : `${c} bulunamadı`)).join(' · ')}
          <SqlInfo k={run.kaynaklar} alan="summary.fx" label="Dönem sonu kuru" className="ml-0.5" />
        </p>
      )}
      {meta.withholdingPct == null && <p className="mt-1 text-[11.5px] text-canvas-muted">Varsayılan stopaj oranı tanımlı değil; stopaj yalnız sözleşmesinde oran olanlarda hesaplanır.</p>}
      <p className="mt-1 text-[11.5px] text-canvas-muted">
        Açan {run.createdBy}, {stamp(run.createdAt)}
        {run.preparedBy ? ` · hesaplatan ${run.preparedBy}, ${stamp(run.computedAt)}` : ''}
        {run.submittedBy ? ` · gönderen ${run.submittedBy}` : ''}
        {run.approvedBy && run.status === 'onayli' ? ` · onaylayan ${run.approvedBy}, ${stamp(run.approvedAt)}` : ''}
      </p>
      {action && action !== 'fx' && <RunActionSheet run={run} action={action} onClose={() => setAction(null)} />}
      {action === 'fx' && <FxSheet run={run} meta={meta} onClose={() => setAction(null)} />}
    </Panel>
  );
}

function RunActionSheet({ run, action, onClose }: { run: Run; action: 'submit' | 'reject' | 'cancel'; onClose: () => void }) {
  const qc = useQueryClient();
  const [note, setNote] = useState('');
  const [ack, setAck] = useState(false);
  const incomplete = !!run.summary.dataIncomplete;
  const go = useMutation({
    mutationFn: () => (action === 'submit' ? royaltyApi.submit(run.id, { note, acceptDataEnd: ack })
      : action === 'reject' ? royaltyApi.reject(run.id, note) : royaltyApi.cancel(run.id, note)),
    onSuccess: () => {
      toast.success(action === 'submit' ? 'Onaya gönderildi.' : action === 'reject' ? 'Geri gönderildi.' : 'Koşu iptal edildi.');
      qc.invalidateQueries({ queryKey: ['royalty'] });
      onClose();
    },
    onError: (e) => toast.error(errMsg(e) ?? 'İşlem tamamlanamadı.'),
  });
  const title = action === 'submit' ? 'Onaya gönder' : action === 'reject' ? 'Geri gönder' : 'Koşuyu iptal et';
  const needNote = action !== 'submit' ? run.status !== 'taslak' || action === 'reject' : incomplete;
  return (
    <Sheet title={title} onClose={onClose}
      footer={
        <>
          <button type="button" className={btnGhost} onClick={onClose}>Vazgeç</button>
          <button type="button" className={btnPrimary} disabled={go.isPending || (needNote && !note.trim()) || (action === 'submit' && incomplete && !ack)} onClick={() => go.mutate()}>
            {go.isPending && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}
            {title}
          </button>
        </>
      }>
      <div className="space-y-3">
        {action === 'submit' && (
          <Note tone="info">Onaylayan kişi sizden ve koşuyu hesaplatandan farklı olmalı. Onayda her sözleşmenin hakedişi ve ödeme takvimi satırı oluşur; onaylı koşu değişmez.</Note>
        )}
        {action === 'submit' && incomplete && (
          <label className="flex items-start gap-2 text-[12.5px]">
            <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} className="mt-0.5 h-5 w-5 shrink-0 accent-canvas-violet" />
            <span>Logo satışı {day(run.dataEnd)} gününe kadar; dönem {day(run.periodEnd)} bitiyor. Eksik veriyle göndermeyi onaylıyorum (sonradan gelen satış sonraki dönemin hesabına girer).</span>
          </label>
        )}
        <Field label={needNote ? 'Gerekçe' : 'Not (isteğe bağlı)'}>
          <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={3} className={field} />
        </Field>
      </div>
    </Sheet>
  );
}

function FxSheet({ run, meta, onClose }: { run: Run; meta: Meta; onClose: () => void }) {
  const qc = useQueryClient();
  const [fx, setFx] = useState<Record<string, number | null>>({ ...(run.options.fx ?? {}) });
  const save = useMutation({
    mutationFn: () => royaltyApi.options(run.id, { fx }),
    onSuccess: () => {
      toast.success('Kur kaydedildi; yeniden hesaplatınca geçerli olur.');
      qc.invalidateQueries({ queryKey: ['royalty'] });
      onClose();
    },
    onError: (e) => toast.error(errMsg(e) ?? 'Kaydedilemedi.'),
  });
  return (
    <Sheet title="Dönem sonu kuru" onClose={onClose}
      footer={
        <>
          <button type="button" className={btnGhost} onClick={onClose}>Vazgeç</button>
          <button type="button" className={btnPrimary} disabled={save.isPending} onClick={() => save.mutate()}>Kaydet</button>
        </>
      }>
      <div className="space-y-3">
        <Note tone="info">Boş bırakılan para biriminde {day(run.periodEnd)} günü (ya da önceki iş günü) TCMB döviz alış kuru okunur. Okunamazsa o para birimindeki sözleşmeler istisna olur.</Note>
        <div className="grid gap-3 sm:grid-cols-2">
          {Object.keys(meta.currencies).filter((c) => c !== 'TRY').map((c) => (
            <Field key={c} label={`${meta.currencies[c]} (1 birim = TL)`}>
              <NumInput value={fx[c] ?? null} onChange={(v) => setFx((s) => ({ ...s, [c]: v }))} />
            </Field>
          ))}
        </div>
      </div>
    </Sheet>
  );
}

function NewRunSheet({ meta, onClose, onCreated }: { meta: Meta; onClose: () => void; onCreated: (id: string) => void }) {
  const qc = useQueryClient();
  const [start, setStart] = useState(meta.defaultPeriod.start);
  const [end, setEnd] = useState(meta.defaultPeriod.end);
  const [note, setNote] = useState('');
  const go = useMutation({
    mutationFn: async () => {
      const r = await royaltyApi.create({ periodStart: start, periodEnd: end, note });
      return royaltyApi.compute(r.id).catch(() => r);
    },
    onSuccess: (r) => {
      toast.success(`${r.no} açıldı; hesap başladı.`);
      qc.invalidateQueries({ queryKey: ['royalty'] });
      onCreated(r.id);
      onClose();
    },
    onError: (e) => toast.error(errMsg(e) ?? 'Koşu açılamadı.'),
  });
  return (
    <Sheet title="Yeni telif dönemi koşusu" onClose={onClose}
      footer={
        <>
          <button type="button" className={btnGhost} onClick={onClose}>Vazgeç</button>
          <button type="button" className={btnPrimary} disabled={go.isPending || !start || !end} onClick={() => go.mutate()}>
            {go.isPending && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}
            Aç ve hesapla
          </button>
        </>
      }>
      <div className="space-y-3">
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Dönem başı" hint="Ayın ilk günü">
            <input type="date" value={start} onChange={(e) => setStart(e.target.value)} className={field} />
          </Field>
          <Field label="Dönem sonu" hint="Ayın son günü; bugünden önce">
            <input type="date" value={end} onChange={(e) => setEnd(e.target.value)} className={field} />
          </Field>
        </div>
        <Field label="Not">
          <input value={note} onChange={(e) => setNote(e.target.value)} className={field} />
        </Field>
        <p className="text-[11.5px] text-canvas-muted">
          Kapsam: CRM'de yürürlükteki satıştan / satıştan kademeli ödemeli Telif Alış sözleşmeleri (durum kodları {meta.scope.statuses.join(', ')})
          ve portalda açılmış yürürlükteki satıştan ödemeli sözleşmeler. Hiçbiri sessizce düşmez: her biri hesaplandı, istisna ya da hariç olarak listelenir.
        </p>
      </div>
    </Sheet>
  );
}
