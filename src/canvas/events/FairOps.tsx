import { useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Camera, Check, Receipt, Trash2, TriangleAlert } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Note, Pill, btnGhost, btnPrimary, errText, field, label as labelCls } from '../admin/ui';
import { useDebounced } from '../editorial/kit';
import { evApi, fileToBase64, fmtMoney, fmtShort, fmtSlot, parseNum, type FairDetail, type Meta } from './api';
import { Block, DaysLeft } from './parts';

/** Fuar kartının iş sekmeleri: görevler (telefonda tek dokunuşla işaret), gider (tür + tutar + fiş fotoğrafı) ve yazar
 *  programı (CRM yazarı + saat; başka kartta aynı yazarın çakışan saati uyarılır). */

function useRun(onChange: (d: FairDetail) => void, ok?: string) {
  return useMutation({
    mutationFn: async (fn: () => Promise<FairDetail>) => fn(),
    onSuccess: (d) => {
      onChange(d);
      if (ok) toast.success(ok);
    },
    onError: (e) => toast.error(errText(e, 'İşlem yapılamadı.') ?? ''),
  });
}

export function FairTasks({ f, m, onChange }: { f: FairDetail; m: Meta; onChange: (d: FairDetail) => void }) {
  const run = useRun(onChange);
  const [title, setTitle] = useState('');
  const [due, setDue] = useState('');
  const [owner, setOwner] = useState('');
  const edit = m.me.canEdit && f.status !== 'iptal';
  const me = m.me.username;

  return (
    <Block title="Görevler" help="Son tarihe göre sıralı. Size atanan görevi yetkiniz olmasa da işaretleyebilirsiniz.">
      <ul className="flex flex-col divide-y divide-slate-100">
        {f.tasks.map((t) => {
          const canTick = (edit || t.owner === me) && f.status !== 'iptal';
          return (
            <li key={t.id} className="flex items-center gap-2 py-1.5">
              <button type="button" role="checkbox" aria-checked={t.done} aria-label={`${t.title}: ${t.done ? 'yapıldı' : 'yapılmadı'}`}
                disabled={!canTick || run.isPending} onClick={() => run.mutate(() => evApi.patchTask(f.id, t.id, { done: !t.done }))}
                className={`inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border transition-[transform,background-color] duration-150 ease-out active:scale-[0.95] sm:h-9 sm:w-9 ${
                  t.done ? 'border-emerald-500 bg-emerald-500 text-white' : 'border-slate-300 bg-white text-transparent hover:border-emerald-400'
                } disabled:opacity-60`}>
                <Check aria-hidden className="h-4 w-4" />
              </button>
              <div className="min-w-0 flex-1">
                <div className={`text-[13px] font-bold ${t.done ? 'text-canvas-muted line-through' : ''}`}>{t.title}</div>
                <div className="text-[11px] text-canvas-muted">
                  {t.dueOn ? fmtShort(t.dueOn) : 'tarihsiz'}{t.owner ? ` · ${t.owner}` : ''}{t.done && t.doneBy ? ` · ${t.doneBy} işaretledi` : ''}
                </div>
              </div>
              {!t.done && t.dueOn && <DaysLeft days={t.daysLeft} doneLabel="gecikti" />}
              {edit && (
                <button type="button" aria-label={`${t.title} görevini sil`} onClick={() => run.mutate(() => evApi.removeTask(f.id, t.id))}
                  className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-slate-400 hover:bg-red-50 hover:text-red-700">
                  <Trash2 aria-hidden className="h-4 w-4" />
                </button>
              )}
            </li>
          );
        })}
      </ul>
      {f.tasks.length === 0 && <p className="py-3 text-[12.5px] text-canvas-muted">Görev yok.</p>}
      {edit && (
        <form className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-[minmax(0,1fr)_160px_160px_auto] sm:items-end"
          onSubmit={(e) => {
            e.preventDefault();
            if (!title.trim()) return;
            run.mutate(() => evApi.addTask(f.id, { title: title.trim(), dueOn: due || null, owner: owner.trim() || null }), {
              onSuccess: () => { setTitle(''); setDue(''); setOwner(''); },
            });
          }}>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Yeni görev</span>
            <input className={field} value={title} onChange={(e) => setTitle(e.target.value)} placeholder="ör. Afiş baskısı onayı" />
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Son tarih</span>
            <input type="date" className={field} value={due} onChange={(e) => setDue(e.target.value)} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Sorumlu</span>
            <input className={field} value={owner} autoCapitalize="none" placeholder={f.owner ?? ''} onChange={(e) => setOwner(e.target.value)} />
          </label>
          <button type="submit" className={btnPrimary} disabled={!title.trim() || run.isPending}>Ekle</button>
        </form>
      )}
    </Block>
  );
}

export function FairCosts({ f, m, onChange }: { f: FairDetail; m: Meta; onChange: (d: FairDetail) => void }) {
  const run = useRun(onChange);
  const [kind, setKind] = useState('stant');
  const [amount, setAmount] = useState('');
  const [note, setNote] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const edit = m.me.canEdit && f.status !== 'iptal';
  const n = parseNum(amount);
  const tooBig = !!file && file.size > m.settings.receiptMaxMb * 1024 * 1024;

  const submit = async () => {
    if (!n || n <= 0 || tooBig) return;
    let receipt: { type: string; dataBase64: string } | null = null;
    if (file) {
      try {
        receipt = { type: file.type || 'application/octet-stream', dataBase64: await fileToBase64(file) };
      } catch (e) {
        toast.error(errText(e, 'Fiş okunamadı.') ?? '');
        return;
      }
    }
    run.mutate(() => evApi.addCost(f.id, { kind, amount, note: note.trim() || undefined, receipt }), {
      onSuccess: () => {
        setAmount('');
        setNote('');
        setFile(null);
        if (fileRef.current) fileRef.current.value = '';
        toast.success('Gider eklendi.');
      },
    });
  };

  return (
    <div className="grid grid-cols-1 gap-3 lg:grid-cols-5 lg:gap-4">
      <div className="lg:col-span-3">
        <Block title="Giderler" help={`Toplam ${fmtMoney(f.costTotal)} · planlanan bütçe ${fmtMoney(f.budgetPlanned)}. CRM etkinlik kaydındaki gider sonuç raporunda ayrıca eklenir.`}>
          {f.costs.length === 0 && <p className="py-3 text-[12.5px] text-canvas-muted">Gider girilmedi.</p>}
          <ul className="flex flex-col divide-y divide-slate-100">
            {f.costs.map((c) => (
              <li key={c.id} className="flex items-center gap-2 py-2 text-[12.5px]">
                <div className="min-w-0 flex-1">
                  <div className="font-bold">{c.kindLabel}{c.note ? <span className="font-normal text-canvas-muted"> · {c.note}</span> : null}</div>
                  <div className="text-[11px] text-canvas-muted">{c.by} · {c.at ? fmtShort(c.at.slice(0, 10)) : ''}</div>
                </div>
                {c.hasReceipt && (
                  <a href={evApi.receiptUrl(f.id, c.id)} target="_blank" rel="noreferrer" className="inline-flex min-h-9 items-center gap-1 rounded-lg px-2 text-[11.5px] font-bold text-canvas-violet hover:bg-canvas-violet/5">
                    <Receipt aria-hidden className="h-3.5 w-3.5" />Fiş
                  </a>
                )}
                <span className="shrink-0 font-mono font-bold tabular-nums">{fmtMoney(c.amount)}</span>
                {edit && (
                  <button type="button" aria-label="Gideri sil" onClick={() => run.mutate(() => evApi.removeCost(f.id, c.id))}
                    className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-slate-400 hover:bg-red-50 hover:text-red-700">
                    <Trash2 aria-hidden className="h-4 w-4" />
                  </button>
                )}
              </li>
            ))}
          </ul>
          {Object.keys(f.costByKind).length > 1 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {Object.entries(f.costByKind).map(([k, v]) => <Pill key={k} tone="muted">{m.costKinds[k] ?? k} {fmtMoney(v)}</Pill>)}
            </div>
          )}
        </Block>
      </div>
      {edit && (
        <div className="lg:col-span-2">
          <Block title="Gider ekle" help="Tür ve tutar yeter; fişin fotoğrafını çekip ekleyebilirsiniz.">
            <form className="flex flex-col gap-2" onSubmit={(e) => { e.preventDefault(); void submit(); }}>
              <div className="grid grid-cols-2 gap-2">
                <label className="flex flex-col gap-1">
                  <span className={labelCls}>Tür</span>
                  <select className={field} value={kind} onChange={(e) => setKind(e.target.value)}>
                    {Object.entries(m.costKinds).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                  </select>
                </label>
                <label className="flex flex-col gap-1">
                  <span className={labelCls}>Tutar (₺)</span>
                  <input inputMode="decimal" className={`${field} font-mono tabular-nums`} value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="ör. 12.500" />
                </label>
              </div>
              <label className="flex flex-col gap-1">
                <span className={labelCls}>Not</span>
                <input className={field} value={note} onChange={(e) => setNote(e.target.value)} />
              </label>
              <label className={`${btnGhost} cursor-pointer`}>
                <Camera aria-hidden className="h-4 w-4" />
                {file ? file.name : 'Fiş fotoğrafı (isteğe bağlı)'}
                <input ref={fileRef} type="file" accept="image/*,application/pdf" capture="environment" className="sr-only"
                  onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
              </label>
              {tooBig && <Note tone="err">Fiş {m.settings.receiptMaxMb} MB'tan büyük.</Note>}
              {amount.trim() !== '' && (n === null || n <= 0) && <Note tone="err">Tutar sıfırdan büyük bir sayı olmalı.</Note>}
              <button type="submit" className={btnPrimary} disabled={!n || n <= 0 || tooBig || run.isPending}>Gideri ekle</button>
            </form>
          </Block>
        </div>
      )}
    </div>
  );
}

export function FairAuthors({ f, m, onChange }: { f: FairDetail; m: Meta; onChange: (d: FairDetail) => void }) {
  const run = useMutation({
    mutationFn: async (fn: () => Promise<FairDetail>) => fn(),
    onSuccess: (d) => {
      onChange(d);
      if (d.newConflicts?.length) toast.warning(`Bu yazarın aynı saatte başka programı var: ${d.newConflicts.map((c) => c.fair).join(', ')}`);
    },
    onError: (e) => toast.error(errText(e, 'İşlem yapılamadı.') ?? ''),
  });
  const [q, setQ] = useState('');
  const dq = useDebounced(q, 300);
  const [pick, setPick] = useState<{ id: string | null; ad: string } | null>(null);
  const [start, setStart] = useState(`${f.startsOn}T14:00`);
  const [end, setEnd] = useState(`${f.startsOn}T16:00`);
  const [note, setNote] = useState('');
  const hits = useQuery({ queryKey: ['ev', 'authors', dq], queryFn: () => evApi.authors(dq), enabled: ENGINE_ENABLED && dq.trim().length >= 2 && !pick });
  const edit = m.me.canEdit && f.status !== 'iptal';

  return (
    <div className="grid grid-cols-1 gap-3 lg:grid-cols-5 lg:gap-4">
      <div className="lg:col-span-3">
        <Block title="Yazar programı" help={<>İmza günü ve söyleşi saatleri. Yazarla randevu ve görüşme kaydı <Link className="font-bold text-canvas-violet hover:underline" to="/yazar-iliskileri">Yazar ilişkileri</Link> ekranında.</>}>
          {f.authors.length === 0 && <p className="py-3 text-[12.5px] text-canvas-muted">Program yok.</p>}
          <ul className="flex flex-col divide-y divide-slate-100">
            {f.authors.map((a) => (
              <li key={a.id} className="flex items-start gap-2 py-2 text-[12.5px]">
                <div className="min-w-0 flex-1">
                  <div className="font-bold">{a.name}{!a.contactId && <span className="ml-1 font-normal text-canvas-muted">(CRM'de eşleşmedi)</span>}</div>
                  <div className="text-[11px] text-canvas-muted">{fmtSlot(a.slotStart)}{a.slotEnd ? ` – ${a.slotEnd.slice(11, 16)}` : ''}{a.note ? ` · ${a.note}` : ''}</div>
                  {a.conflicts.map((c) => (
                    <div key={`${c.fairId}${c.slotStart}`} className="mt-1 flex items-center gap-1 text-[11px] font-bold text-amber-800">
                      <TriangleAlert aria-hidden className="h-3.5 w-3.5" />
                      Çakışma: <Link className="underline" to={`/etkinlikler/fuar/${encodeURIComponent(c.fairId)}?sekme=yazarlar`}>{c.fair}</Link> {fmtSlot(c.slotStart)}
                    </div>
                  ))}
                </div>
                {edit && (
                  <button type="button" aria-label={`${a.name} programını sil`} onClick={() => run.mutate(() => evApi.removeAuthor(f.id, a.id))}
                    className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-slate-400 hover:bg-red-50 hover:text-red-700">
                    <Trash2 aria-hidden className="h-4 w-4" />
                  </button>
                )}
              </li>
            ))}
          </ul>
        </Block>
      </div>
      {edit && (
        <div className="lg:col-span-2">
          <Block title="Programa yazar ekle">
            <form className="flex flex-col gap-2" onSubmit={(e) => {
              e.preventDefault();
              const name = pick?.ad ?? q.trim();
              if (!name) return;
              run.mutate(() => evApi.addAuthor(f.id, { name, contactId: pick?.id ?? null, slotStart: start || null, slotEnd: end || null, note: note.trim() || null }), {
                onSuccess: () => { setPick(null); setQ(''); setNote(''); },
              });
            }}>
              <label className="relative flex flex-col gap-1">
                <span className={labelCls}>Yazar (CRM)</span>
                {pick ? (
                  <span className="flex items-center justify-between gap-2 rounded-xl border border-canvas-violet/40 bg-canvas-violet/5 px-3 py-2 text-[12.5px] font-bold">
                    {pick.ad}
                    <button type="button" className="text-[11.5px] font-bold text-canvas-violet hover:underline" onClick={() => setPick(null)}>Değiştir</button>
                  </span>
                ) : (
                  <input className={field} value={q} placeholder="Ad yazın" onChange={(e) => setQ(e.target.value)} />
                )}
                {!pick && dq.trim().length >= 2 && hits.data && (
                  <ul className="absolute left-0 right-0 top-full z-30 mt-1 max-h-[260px] overflow-y-auto rounded-xl border border-slate-200 bg-white shadow-lg">
                    {hits.data.items.map((h) => (
                      <li key={h.id}>
                        <button type="button" className="flex min-h-11 w-full items-center px-3 text-left text-[12.5px] hover:bg-slate-50" onClick={() => setPick({ id: h.id, ad: h.ad })}>{h.ad}</button>
                      </li>
                    ))}
                    {hits.data.items.length === 0 && <li className="px-3 py-2 text-[12px] text-canvas-muted">CRM'de eşleşen yazar yok; ad olduğu gibi kaydedilir.</li>}
                    {hits.data.total > hits.data.shown && <li className="px-3 py-2 text-[11px] text-canvas-muted">{hits.data.total} eşleşmenin ilk {hits.data.shown}'i.</li>}
                  </ul>
                )}
              </label>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                <label className="flex flex-col gap-1">
                  <span className={labelCls}>Başlangıç</span>
                  <input type="datetime-local" className={field} value={start} onChange={(e) => setStart(e.target.value)} />
                </label>
                <label className="flex flex-col gap-1">
                  <span className={labelCls}>Bitiş</span>
                  <input type="datetime-local" className={field} value={end} min={start || undefined} onChange={(e) => setEnd(e.target.value)} />
                </label>
              </div>
              <label className="flex flex-col gap-1">
                <span className={labelCls}>Not</span>
                <input className={field} value={note} onChange={(e) => setNote(e.target.value)} placeholder="ör. imza günü, söyleşi salonu" />
              </label>
              <button type="submit" className={btnPrimary} disabled={(!pick && !q.trim()) || (!!end && !!start && end < start) || run.isPending}>Ekle</button>
            </form>
          </Block>
        </div>
      )}
    </div>
  );
}
