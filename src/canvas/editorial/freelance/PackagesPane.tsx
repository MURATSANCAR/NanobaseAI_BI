import { useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { toast } from 'sonner';
import { Check, ChevronDown, Download, ExternalLink, FolderPlus, Link2, Loader2, Plus, Search, Sparkles, Trash2, Upload, Wand2, X } from 'lucide-react';
import { editorialSearchApi, freelanceApi, type FlPackage, type FlSuggestion, type FlTask, type FlTaskInput } from '../../engine';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText, field } from '../../admin/ui';
import { Panel, useDebounced } from '../kit';
import { ThreadView } from './MessagesPane';
import SqlInfo from '../../components/SqlInfo';
import type { Kaynaklar } from '../../components/sqlInfo';
import { ConfirmButton, Empty, FieldBox, TASK_STATUS, day, editNum, parseNum, q2, roleLabel, stamp, tl, todayIso, useFlRefresh, type FlCtx } from './shared';
import { FileDrop } from '../../components/FileDrop';
import { MB } from '../../components/fileDropRules';

/** İş paketleri: bir kitabın bir işi (ör. 24 iç illüstrasyon), görevlere bölünür, görevler kişilere dağıtılır. */

export default function PackagesPane({ ctx }: { ctx: FlCtx }) {
  const [params, setParams] = useSearchParams();
  const open = params.get('paket');
  const creating = params.get('yeni') === 'paket';
  const reviewOnly = params.get('durum') === 'inceleme';
  const [text, setText] = useState('');
  const [status, setStatus] = useState('acik');
  const q = useDebounced(text.trim(), 250);
  const list = useQuery({ queryKey: ['fl', 'packages', q, status], queryFn: () => freelanceApi.packages({ q, status }), placeholderData: (p) => p });
  const items = (list.data?.items ?? []).filter((p) => !reviewOnly || p.counts.teslim > 0);

  const patch = (fn: (n: URLSearchParams) => void) => {
    const next = new URLSearchParams(params);
    fn(next);
    setParams(next, { replace: true });
  };
  const setOpen = (id: string | null) =>
    patch((n) => {
      n.delete('yeni');
      if (id) n.set('paket', id);
      else n.delete('paket');
    });

  return (
    <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_minmax(0,760px)] xl:items-start xl:gap-4">
      <Panel>
        <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_130px_auto]">
          <label className="relative block">
            <span className="sr-only">Paket ara</span>
            <Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-canvas-muted" />
            <input type="search" value={text} onChange={(e) => setText(e.target.value)} placeholder="Paket ya da kitap adı" className={`${field} pl-9`} />
          </label>
          <select aria-label="Durum" value={status} onChange={(e) => setStatus(e.target.value)} className={field}>
            <option value="acik">Açık</option>
            <option value="kapandi">Kapandı</option>
            <option value="iptal">İptal</option>
            <option value="">Hepsi</option>
          </select>
          {ctx.canManage && (
            <button type="button" className={btnPrimary} onClick={() =>
                patch((n) => {
                  n.set('yeni', 'paket');
                  n.delete('paket');
                })
              }>
              <FolderPlus aria-hidden className="h-4 w-4" />
              Yeni iş paketi
            </button>
          )}
        </div>
        {reviewOnly && (
          <div className="mt-2 flex items-center justify-between gap-2 rounded-xl bg-amber-50 px-3 py-2 text-[12px] font-semibold text-amber-800">
            Yalnız teslim incelemesi bekleyen paketler
            <button type="button" className="font-extrabold hover:underline" onClick={() => patch((n) => n.delete('durum'))}>
              Süzgeci kaldır
            </button>
          </div>
        )}
        {list.error && <Note tone="err">{errText(list.error, 'Paketler okunamadı.')}</Note>}
        {list.data && !items.length && (
          <Empty>{q || status !== 'acik' || reviewOnly ? 'Bu süzgece uyan paket yok.' : 'Açık iş paketi yok. «Yeni iş paketi» ile bir kitabın işini açıp görevlere bölün.'}</Empty>
        )}
        {list.data && items.length > 0 && (
          <p className="mt-3 flex flex-wrap items-center gap-x-1 gap-y-0.5 text-[11.5px] text-canvas-muted">
            <span className="font-mono tabular-nums">{nf.format(items.length)}</span> paket
            <SqlInfo k={list.data.kaynaklar} alan="total" label="Paket sayısı" />
            <span aria-hidden>·</span> satırdaki görev, tutar ve sayılar
            <SqlInfo k={list.data.kaynaklar} alan="items[]" label="İş paketleri" />
            <span aria-hidden>·</span> okunmamış
            <SqlInfo k={list.data.kaynaklar} alan="items[].unread" label="Okunmamış ileti" />
          </p>
        )}
        <ul className="mt-2 space-y-2">
          {items.map((p) => {
            const done = p.counts.onaylandi;
            const pctDone = p.tasks ? Math.round((done / p.tasks) * 100) : 0;
            return (
              <li key={p.id}>
                <button
                  type="button"
                  onClick={() => setOpen(p.id)}
                  aria-pressed={open === p.id}
                  className={`w-full rounded-2xl border px-3 py-2.5 text-left text-[12.5px] transition-[border-color,background-color,transform] duration-150 ease-out active:scale-[0.99] ${
                    open === p.id ? 'border-canvas-violet bg-white' : 'border-slate-100 bg-white/85 hover:bg-white'
                  }`}
                >
                  <span className="flex items-start justify-between gap-2">
                    <span className="min-w-0">
                      <span className="block break-words font-extrabold leading-snug">{p.title}</span>
                      <span className="block text-[11px] text-canvas-muted">
                        {[p.bookTitle, roleLabel(ctx.roles, p.role), p.due && `termin ${day(p.due)}`].filter(Boolean).join(' · ')}
                      </span>
                    </span>
                    <span className="flex shrink-0 items-center gap-1">
                      {p.unread > 0 && <span className="rounded-full bg-canvas-coral px-1.5 font-mono text-[10.5px] font-bold leading-5 text-white">{p.unread}</span>}
                      {p.late > 0 && <Pill tone="err">{p.late} geciken</Pill>}
                      {p.counts.teslim > 0 && <Pill tone="warn">{p.counts.teslim} inceleme</Pill>}
                      {p.counts.atanmadi > 0 && <Pill tone="muted">{p.counts.atanmadi} atanmadı</Pill>}
                    </span>
                  </span>
                  <span className="mt-2 flex items-center gap-2">
                    <span className="h-1.5 min-w-0 flex-1 overflow-hidden rounded-full bg-slate-100" aria-hidden>
                      <span className="block h-full rounded-full bg-canvas-mint" style={{ width: `${pctDone}%` }} />
                    </span>
                    <span className="shrink-0 font-mono text-[11px] tabular-nums text-canvas-muted">
                      {done}/{p.tasks} · {tl(p.amount)}
                    </span>
                  </span>
                  {p.people.length > 0 && <span className="mt-1 block truncate text-[11px] text-canvas-muted">{p.people.join(', ')}</span>}
                </button>
              </li>
            );
          })}
        </ul>
      </Panel>
      {(creating || open) && (
        <div className="order-first xl:order-none">
          {creating ? <PackageForm ctx={ctx} onDone={(id) => setOpen(id)} onCancel={() => setOpen(null)} /> : <PackageDetail ctx={ctx} id={open as string} onClose={() => setOpen(null)} />}
        </div>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ yeni paket

type Line = { title: string; units: string; unitPrice: string; effortHours: string; start: string; due: string };
const num = parseNum;

function splitLines(base: string, total: number, parts: number, due: string, price: string, hoursPer: number): Line[] {
  const n = Math.max(1, Math.min(50, Math.floor(parts)));
  const each = Math.floor(total / n);
  let rest = total - each * n;
  return Array.from({ length: n }, (_, i) => {
    const u = each + (rest-- > 0 ? 1 : 0);
    return { title: n > 1 ? `${base} — ${i + 1}/${n}` : base, units: String(u), unitPrice: price, effortHours: String(Math.round(u * hoursPer * 10) / 10), start: '', due };
  });
}

function BookPicker({ value, onPick }: { value: string; onPick: (title: string, id: string) => void }) {
  const [text, setText] = useState(value);
  const [focus, setFocus] = useState(false);
  const q = useDebounced(text.trim(), 350);
  const res = useQuery({ queryKey: ['fl', 'book-pick', q], queryFn: () => editorialSearchApi.search(q, 'kitap'), enabled: focus && q.length >= 2 && q !== value, staleTime: 60_000 });
  return (
    <div className="relative">
      <input
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          onPick(e.target.value, '');
        }}
        onFocus={() => setFocus(true)}
        onBlur={() => window.setTimeout(() => setFocus(false), 150)}
        className={field}
        placeholder="CRM'deki kitap adı ya da yeni kitap"
        autoComplete="off"
      />
      {focus && q.length >= 2 && q !== value && (res.data?.books.length ?? 0) > 0 && (
        <ul className="absolute left-0 right-0 top-full z-30 mt-1 max-h-56 overflow-y-auto rounded-xl border border-slate-100 bg-white shadow-canvas-card">
          {res.data?.books.slice(0, 10).map((b) => (
            <li key={b.id}>
              <button
                type="button"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => {
                  setText(b.title || '');
                  onPick(b.title || '', b.id);
                  setFocus(false);
                }}
                className="w-full px-3 py-2 text-left text-[12px] hover:bg-slate-50"
              >
                <span className="font-bold">{b.title}</span>
                {b.note && <span className="ml-1 text-canvas-muted">{b.note}</span>}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function PackageForm({ ctx, onDone, onCancel }: { ctx: FlCtx; onDone: (id: string) => void; onCancel: () => void }) {
  const refresh = useFlRefresh();
  const [title, setTitle] = useState('');
  const [book, setBook] = useState({ title: '', id: '' });
  const [role, setRole] = useState(ctx.roles[0]?.key ?? '');
  const [due, setDue] = useState('');
  const [brief, setBrief] = useState('');
  const [total, setTotal] = useState('');
  const [parts, setParts] = useState('1');
  const [price, setPrice] = useState('');
  const [lines, setLines] = useState<Line[]>([]);
  const [error, setError] = useState<string | null>(null);
  const r = ctx.roles.find((x) => x.key === role);
  const unit = r?.unit ?? 'iş';

  const save = useMutation({
    mutationFn: () =>
      freelanceApi.createPackage({
        title,
        role,
        due: due || undefined,
        bookTitle: book.title || undefined,
        bookId: book.id || undefined,
        brief,
        tasks: lines.map<FlTaskInput>((l) => ({
          title: l.title,
          units: num(l.units),
          unit,
          unitPrice: l.unitPrice ? num(l.unitPrice) : 0,
          effortHours: l.effortHours ? num(l.effortHours) : undefined,
          start: l.start || undefined,
          due: l.due || due || undefined,
        })),
      }),
    onSuccess: (p) => {
      toast.success(`«${p.title}» açıldı; görevleri şimdi dağıtabilirsiniz.`);
      refresh();
      onDone(p.id);
    },
    onError: (e) => setError(errText(e, 'Paket açılamadı.')),
  });
  const setLine = (i: number, k: keyof Line, v: string) => setLines((ls) => ls.map((l, j) => (j === i ? { ...l, [k]: v } : l)));
  const sum = lines.reduce((a, l) => a + (num(l.units) || 0) * (num(l.unitPrice) || 0), 0);

  return (
    <Panel>
      <form
        className="grid gap-3 text-[12.5px]"
        onSubmit={(e) => {
          e.preventDefault();
          setError(null);
          save.mutate();
        }}
      >
        <div className="flex items-start justify-between gap-2">
          <h2 className="text-[17px] font-extrabold leading-tight tracking-tight">Yeni iş paketi</h2>
          <button type="button" onClick={onCancel} aria-label="Formu kapat" className={`${btnGhost} px-2.5`}>
            <X aria-hidden className="h-4 w-4" />
          </button>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <FieldBox label="Paket adı *">
            <input required value={title} onChange={(e) => setTitle(e.target.value)} className={field} placeholder="İç illüstrasyonlar" />
          </FieldBox>
          <FieldBox label="Kitap">
            <BookPicker value={book.title} onPick={(t, id) => setBook({ title: t, id })} />
          </FieldBox>
          <FieldBox label="İş rolü *">
            <select value={role} onChange={(e) => setRole(e.target.value)} className={field}>
              {ctx.roles.map((x) => (
                <option key={x.key} value={x.key}>
                  {x.label}
                </option>
              ))}
            </select>
          </FieldBox>
          <FieldBox label="Paket termini">
            <input type="date" min={todayIso()} value={due} onChange={(e) => setDue(e.target.value)} className={field} />
          </FieldBox>
        </div>
        <FieldBox label="Açıklama (serbest çalışana giden bildirimde yer alır)">
          <textarea value={brief} onChange={(e) => setBrief(e.target.value)} rows={3} className={field} placeholder="Ebat, teknik, renk, referans, teslim biçimi…" />
        </FieldBox>

        <fieldset className="rounded-xl bg-slate-50 p-2.5">
          <legend className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Görevlere böl</legend>
          <div className="mt-1 grid grid-cols-2 gap-2 sm:grid-cols-[1fr_1fr_1fr_auto] sm:items-end">
            <FieldBox label={`Toplam (${unit})`}>
              <input value={total} onChange={(e) => setTotal(e.target.value)} className={field} inputMode="decimal" placeholder="24" />
            </FieldBox>
            <FieldBox label="Kaç parça">
              <input value={parts} onChange={(e) => setParts(e.target.value)} className={field} inputMode="numeric" />
            </FieldBox>
            <FieldBox label={`Birim ücret (₺/${unit})`}>
              <input value={price} onChange={(e) => setPrice(e.target.value)} className={field} inputMode="decimal" />
            </FieldBox>
            <button
              type="button"
              className={`${btnGhost} bg-white`}
              disabled={!title.trim() || !(num(total) > 0)}
              onClick={() => setLines(splitLines(title.trim(), num(total), num(parts) || 1, due, price, r?.hoursPerUnit ?? 1))}
            >
              <Wand2 aria-hidden className="h-4 w-4" />
              Böl
            </button>
          </div>
          <p className="mt-1.5 text-[11px] text-canvas-muted">Tahmini süre {r ? `${q2(r.hoursPerUnit)} saat/${unit}` : ''} varsayımıyla doldurulur; her satırda değiştirilebilir.</p>
        </fieldset>

        <div>
          <div className="flex items-center justify-between gap-2">
            <span className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Görevler ({lines.length})</span>
            <button type="button" className={`${btnGhost} min-h-9 px-2.5`} onClick={() => setLines((ls) => [...ls, { title: title.trim() || 'Görev', units: '1', unitPrice: price, effortHours: String(r?.hoursPerUnit ?? 1), start: '', due }])}>
              <Plus aria-hidden className="h-4 w-4" />
              Satır
            </button>
          </div>
          {!lines.length && <p className="mt-1 text-[12px] text-canvas-muted">«Böl» ile görevleri oluşturun ya da satır ekleyin.</p>}
          <ul className="mt-1.5 space-y-2">
            {lines.map((l, i) => (
              <li key={i} className="grid grid-cols-2 gap-1.5 rounded-xl border border-slate-100 bg-white p-2 sm:grid-cols-[minmax(0,1fr)_70px_90px_70px_130px_auto]">
                <input aria-label="Görev adı" value={l.title} onChange={(e) => setLine(i, 'title', e.target.value)} className={`${field} col-span-2 sm:col-span-1`} />
                <input aria-label={`Miktar (${unit})`} title={`Miktar (${unit})`} value={l.units} onChange={(e) => setLine(i, 'units', e.target.value)} className={field} inputMode="decimal" />
                <input aria-label="Birim ücret" title="Birim ücret (₺)" value={l.unitPrice} onChange={(e) => setLine(i, 'unitPrice', e.target.value)} className={field} inputMode="decimal" placeholder="₺" />
                <input aria-label="Tahmini saat" title="Tahmini saat" value={l.effortHours} onChange={(e) => setLine(i, 'effortHours', e.target.value)} className={field} inputMode="decimal" />
                <input aria-label="Termin" type="date" value={l.due} onChange={(e) => setLine(i, 'due', e.target.value)} className={field} />
                <button type="button" aria-label="Satırı kaldır" onClick={() => setLines((ls) => ls.filter((_, j) => j !== i))} className={`${btnGhost} min-h-9 px-2`}>
                  <Trash2 aria-hidden className="h-4 w-4" />
                </button>
              </li>
            ))}
          </ul>
          {lines.length > 0 && <p className="mt-2 text-right font-mono text-[12px] font-bold tabular-nums">Toplam {tl(sum)} (KDV hariç)</p>}
        </div>

        {error && <Note tone="err">{error}</Note>}
        <div className="flex flex-wrap justify-end gap-2">
          <button type="button" className={btnGhost} onClick={onCancel}>
            Vazgeç
          </button>
          <button type="submit" className={btnPrimary} disabled={save.isPending || !title.trim() || !lines.length}>
            {save.isPending && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}
            Paketi aç
          </button>
        </div>
      </form>
    </Panel>
  );
}

// ------------------------------------------------------------------ paket ayrıntısı

function PackageDetail({ ctx, id, onClose }: { ctx: FlCtx; id: string; onClose: () => void }) {
  const refresh = useFlRefresh();
  const pkg = useQuery({ queryKey: ['fl', 'package', id], queryFn: () => freelanceApi.package(id) });
  const [selected, setSelected] = useState<string[]>([]);
  const [openTask, setOpenTask] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const status = useMutation({
    mutationFn: (s: 'acik' | 'kapandi' | 'iptal') => freelanceApi.updatePackage(id, { status: s }),
    onSuccess: () => {
      toast.success('Paket güncellendi.');
      refresh();
    },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.')),
  });

  if (pkg.error) return <Panel><Note tone="err">{errText(pkg.error, 'Paket okunamadı.')}</Note></Panel>;
  if (!pkg.data) return <Panel><Loading /></Panel>;
  const p = pkg.data;
  const live = p.tasks.filter((t) => t.status !== 'iptal');
  const selectable = (t: FlTask) => ctx.canManage && p.status === 'acik' && ['atanmadi', 'atandi', 'calisiyor'].includes(t.status);
  const toggle = (tid: string) => setSelected((s) => (s.includes(tid) ? s.filter((x) => x !== tid) : [...s, tid]));
  const allUnassigned = live.filter((t) => t.status === 'atanmadi').map((t) => t.id);
  const total = live.reduce((a, t) => a + t.amount, 0);

  return (
    <div className="grid gap-3">
      <Panel>
        <div className="text-[12.5px]">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <h2 className="break-words text-[18px] font-extrabold leading-tight tracking-tight">{p.title}</h2>
              <p className="mt-0.5 text-[12px] text-canvas-muted">
                {[p.bookTitle, roleLabel(ctx.roles, p.role), p.due && `termin ${day(p.due)}`, `açan ${p.owner}`].filter(Boolean).join(' · ')}
              </p>
            </div>
            <div className="flex shrink-0 items-center gap-1.5">
              {p.status !== 'acik' && <Pill tone={p.status === 'iptal' ? 'err' : 'ok'}>{p.status === 'iptal' ? 'İptal' : 'Kapandı'}</Pill>}
              <button type="button" onClick={onClose} aria-label="Paketi kapat" className={`${btnGhost} px-2.5`}>
                <X aria-hidden className="h-4 w-4" />
              </button>
            </div>
          </div>
          {p.brief && <p className="mt-2 max-h-40 overflow-y-auto whitespace-pre-line rounded-xl bg-slate-50 px-3 py-2 leading-snug">{p.brief}</p>}
          <div className="mt-3 grid grid-cols-3 gap-2">
            <Mini label="Görev" value={`${live.filter((t) => t.status === 'onaylandi').length}/${live.length} bitti`} info={<SqlInfo k={p.kaynaklar} alan="toplam" label="Görev sayısı" />} />
            <Mini label="Toplam" value={tl(total)} info={<SqlInfo k={p.kaynaklar} alan="toplam" label="Paket toplamı" />} />
            <Mini label="Tahmini" value={`${q2(live.reduce((a, t) => a + t.effortHours, 0))} saat`} info={<SqlInfo k={p.kaynaklar} alan="toplam" label="Tahmini saat" />} />
          </div>
          {ctx.canManage && (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {p.status === 'acik' && (
                <>
                  <button type="button" className={btnGhost} onClick={() => setAdding((v) => !v)}>
                    <Plus aria-hidden className="h-4 w-4" />
                    Görev ekle
                  </button>
                  <ConfirmButton confirm="Kapatılsın mı?" onConfirm={() => status.mutate('kapandi')}>
                    Paketi kapat
                  </ConfirmButton>
                  <ConfirmButton confirm="İptal edilsin mi? Bitmemiş görevler iptal olur." onConfirm={() => status.mutate('iptal')}>
                    İptal et
                  </ConfirmButton>
                </>
              )}
              {p.status !== 'acik' && (
                <button type="button" className={btnGhost} onClick={() => status.mutate('acik')}>
                  Yeniden aç
                </button>
              )}
            </div>
          )}
          {adding && <AddTasks ctx={ctx} p={p} onDone={() => setAdding(false)} />}
        </div>
      </Panel>

      {selected.length > 0 && <Distribute ctx={ctx} p={p} taskIds={selected} onDone={() => setSelected([])} />}

      <Panel>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="inline-flex items-center gap-1 text-[13px] font-extrabold">
            Görevler
            <SqlInfo k={p.kaynaklar} alan="tasks[]" label="Görevler: miktar, ücret, tutar" />
          </h3>
          {ctx.canManage && p.status === 'acik' && allUnassigned.length > 0 && (
            <button type="button" className={btnGhost} onClick={() => setSelected(allUnassigned)}>
              <Sparkles aria-hidden className="h-4 w-4" />
              Atanmamış {allUnassigned.length} görevi dağıt
            </button>
          )}
        </div>
        <ul className="mt-2 space-y-1.5">
          {p.tasks.map((t) => (
            <li key={t.id} className={`rounded-2xl border ${openTask === t.id ? 'border-canvas-violet bg-white' : 'border-slate-100 bg-white/85'} ${t.status === 'iptal' ? 'opacity-60' : ''}`}>
              <div className="flex items-center gap-2 px-2.5 py-2">
                {selectable(t) ? (
                  <input type="checkbox" aria-label={`${t.title} seç`} checked={selected.includes(t.id)} onChange={() => toggle(t.id)} className="h-5 w-5 shrink-0 accent-canvas-violet" />
                ) : (
                  <span className="w-5 shrink-0" />
                )}
                <button type="button" onClick={() => setOpenTask(openTask === t.id ? null : t.id)} aria-expanded={openTask === t.id} className="flex min-w-0 flex-1 items-center gap-2 text-left">
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[12.5px] font-bold">{t.title}</span>
                    <span className="block truncate text-[11px] text-canvas-muted">
                      {[t.personName ?? 'Atanmadı', `${q2(t.units)} ${t.unit}`, tl(t.amount), t.due && `termin ${day(t.due)}`].filter(Boolean).join(' · ')}
                    </span>
                  </span>
                  <Pill tone={t.late ? 'err' : TASK_STATUS[t.status].tone}>{t.late ? 'Gecikti' : TASK_STATUS[t.status].label}</Pill>
                  <ChevronDown aria-hidden className={`h-4 w-4 shrink-0 text-canvas-muted transition-transform duration-200 ease-out ${openTask === t.id ? 'rotate-180' : ''}`} />
                </button>
              </div>
              {openTask === t.id && <TaskPanel ctx={ctx} p={p} t={t} />}
            </li>
          ))}
        </ul>
      </Panel>

      <Panel>
        <ThreadView ctx={ctx} threadId={`p:${p.id}`} compact />
      </Panel>
    </div>
  );
}

function Mini({ label, value, info }: { label: string; value: string; info?: React.ReactNode }) {
  return (
    <div className="rounded-xl bg-slate-50 px-2.5 py-2">
      <div className="flex items-center justify-between gap-1 text-[10.5px] font-bold uppercase tracking-wide text-canvas-muted">
        <span className="min-w-0 truncate">{label}</span>
        {info}
      </div>
      <div className="mt-0.5 truncate font-mono text-[13px] font-bold tabular-nums">{value}</div>
    </div>
  );
}

function AddTasks({ ctx, p, onDone }: { ctx: FlCtx; p: FlPackage; onDone: () => void }) {
  const refresh = useFlRefresh();
  const r = ctx.roles.find((x) => x.key === p.role);
  const [t, setT] = useState({ title: '', units: '', unitPrice: '', effortHours: '', due: p.due ?? '' });
  const add = useMutation({
    mutationFn: () =>
      freelanceApi.addTasks(p.id, [
        { title: t.title, units: num(t.units), unitPrice: t.unitPrice ? num(t.unitPrice) : 0, effortHours: t.effortHours ? num(t.effortHours) : undefined, due: t.due || undefined },
      ]),
    onSuccess: () => {
      toast.success('Görev eklendi.');
      refresh();
      onDone();
    },
    onError: (e) => toast.error(errText(e, 'Eklenemedi.')),
  });
  return (
    <form
      className="mt-3 grid grid-cols-2 gap-1.5 rounded-xl bg-slate-50 p-2.5 sm:grid-cols-[minmax(0,1fr)_80px_90px_80px_130px_auto]"
      onSubmit={(e) => {
        e.preventDefault();
        add.mutate();
      }}
    >
      <input required aria-label="Görev adı" placeholder="Görev adı" value={t.title} onChange={(e) => setT({ ...t, title: e.target.value })} className={`${field} col-span-2 sm:col-span-1`} />
      <input required aria-label={`Miktar (${r?.unit})`} placeholder={r?.unit} value={t.units} onChange={(e) => setT({ ...t, units: e.target.value })} className={field} inputMode="decimal" />
      <input aria-label="Birim ücret" placeholder="₺/birim" value={t.unitPrice} onChange={(e) => setT({ ...t, unitPrice: e.target.value })} className={field} inputMode="decimal" />
      <input aria-label="Tahmini saat" placeholder="saat" value={t.effortHours} onChange={(e) => setT({ ...t, effortHours: e.target.value })} className={field} inputMode="decimal" />
      <input aria-label="Termin" type="date" value={t.due} onChange={(e) => setT({ ...t, due: e.target.value })} className={field} />
      <button type="submit" className={btnPrimary} disabled={add.isPending}>
        Ekle
      </button>
    </form>
  );
}

// ------------------------------------------------------------------ toplu dağıtım

function Distribute({ ctx, p, taskIds, onDone }: { ctx: FlCtx; p: FlPackage; taskIds: string[]; onDone: () => void }) {
  const refresh = useFlRefresh();
  const [picks, setPicks] = useState<Record<string, string>>({});
  const [notify, setNotify] = useState(true);
  const [suggestions, setSuggestions] = useState<FlSuggestion[] | null>(null);
  const [suggestK, setSuggestK] = useState<Kaynaklar | undefined>(undefined);
  const people = useQuery({ queryKey: ['fl', 'people', '', p.role, 'aktif'], queryFn: () => freelanceApi.people({ role: p.role, status: 'aktif' }) });
  const tasks = p.tasks.filter((t) => taskIds.includes(t.id));
  const unassigned = tasks.filter((t) => t.status === 'atanmadi').map((t) => t.id);

  const suggest = useMutation({
    mutationFn: () => freelanceApi.suggest(unassigned),
    onSuccess: (r) => {
      setSuggestions(r.items);
      setSuggestK(r.kaynaklar);
      setPicks((cur) => {
        const next = { ...cur };
        r.items.forEach((s) => {
          if (s.suggested) next[s.taskId] = s.suggested;
        });
        return next;
      });
      const none = r.items.filter((s) => !s.suggested).length;
      if (none) toast.warning(`${none} görev için uygun boş kapasite bulunamadı; kişiyi elle seçin.`);
    },
    onError: (e) => toast.error(errText(e, 'Öneri alınamadı.')),
  });
  const assign = useMutation({
    mutationFn: () => freelanceApi.assign(Object.entries(picks).filter(([tid, pid]) => taskIds.includes(tid) && pid).map(([taskId, personId]) => ({ taskId, personId: personId === '-' ? null : personId })), notify),
    onSuccess: (r) => {
      const mail = r.mail ? ` · ${r.mail.gonderildi} e-posta gönderildi${r.mail.diger ? `, ${r.mail.diger} gönderilemedi` : ''}` : '';
      toast.success(`${r.assigned} görev atandı${mail}.`);
      refresh();
      onDone();
    },
    onError: (e) => toast.error(errText(e, 'Atama yapılamadı.')),
  });
  const setAll = (pid: string) => setPicks(Object.fromEntries(taskIds.map((t) => [t, pid])));
  const byTask = useMemo(() => Object.fromEntries((suggestions ?? []).map((s) => [s.taskId, s])), [suggestions]);
  const ready = taskIds.some((t) => picks[t]);

  return (
    <Panel>
      <div className="text-[12.5px]">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="inline-flex items-center gap-1 text-[13px] font-extrabold">
            {taskIds.length} görevi dağıt
            {suggestions && <SqlInfo k={suggestK} alan="items[]" label="Kapasiteye göre öneri" />}
          </h3>
          <div className="flex flex-wrap gap-1.5">
            {unassigned.length > 0 && (
              <button type="button" className={btnGhost} onClick={() => suggest.mutate()} disabled={suggest.isPending}>
                {suggest.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Sparkles aria-hidden className="h-4 w-4" />}
                Kapasiteye göre öner
              </button>
            )}
            <button type="button" className={`${btnGhost} px-2.5`} onClick={onDone} aria-label="Seçimi bırak">
              <X aria-hidden className="h-4 w-4" />
            </button>
          </div>
        </div>
        <FieldBox label="Hepsini tek kişiye" className="mt-2">
          <div className="flex min-w-0 items-center gap-1">
          <select className={`${field} min-w-0 flex-1`} value="" onChange={(e) => e.target.value && setAll(e.target.value)}>
            <option value="">Kişi seçin…</option>
            {people.data?.items.map((x) => (
              <option key={x.id} value={x.id}>
                {x.name} · {x.stats.active} süren iş
              </option>
            ))}
            <option value="-">Atamayı geri al</option>
          </select>
          <SqlInfo k={people.data?.kaynaklar} alan="items[].stats" label="Kişi başına süren iş" />
          </div>
        </FieldBox>
        <ul className="mt-2 space-y-1.5">
          {tasks.map((t) => {
            const s = byTask[t.id];
            const chosen = s?.candidates.find((c) => c.personId === picks[t.id]);
            return (
              <li key={t.id} className="grid gap-1.5 rounded-xl bg-slate-50 p-2 sm:grid-cols-[minmax(0,1fr)_240px] sm:items-center">
                <span className="min-w-0">
                  <span className="block truncate font-bold">{t.title}</span>
                  <span className="block truncate text-[11px] text-canvas-muted">
                    {q2(t.effortHours)} saat · {t.start ? `${day(t.start)} – ` : ''}
                    {day(t.due)}
                    {t.personName ? ` · şimdi ${t.personName}` : ''}
                  </span>
                  {chosen && <span className={`block text-[11px] ${chosen.fits ? 'text-emerald-700' : 'text-amber-700'}`}>{chosen.reason}</span>}
                  {s?.note && !chosen && <span className="block text-[11px] text-amber-700">{s.note}</span>}
                </span>
                <select aria-label={`${t.title} kime`} className={field} value={picks[t.id] ?? ''} onChange={(e) => setPicks({ ...picks, [t.id]: e.target.value })}>
                  <option value="">Değiştirme</option>
                  {s?.candidates.length ? (
                    <optgroup label="Öneri sırasıyla">
                      {s.candidates.map((c) => (
                        <option key={c.personId} value={c.personId}>
                          {c.fits ? '✓ ' : '! '}
                          {c.name} · {q2(Math.max(c.freeHours, 0))} sa boş
                        </option>
                      ))}
                    </optgroup>
                  ) : null}
                  <optgroup label="Bu roldeki herkes">
                    {people.data?.items.map((x) => (
                      <option key={x.id} value={x.id}>
                        {x.name}
                      </option>
                    ))}
                  </optgroup>
                  {t.personId && <option value="-">Atamayı geri al</option>}
                </select>
              </li>
            );
          })}
        </ul>
        {people.data && !people.data.items.length && <Note tone="warn">Bu rolde kayıtlı aktif kişi yok. Önce Kişiler bölümünden kayıt açın.</Note>}
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
          <label className="inline-flex items-center gap-2 text-[12px] font-semibold">
            <input type="checkbox" checked={notify} onChange={(e) => setNotify(e.target.checked)} className="h-5 w-5 accent-canvas-violet" />
            Atanan kişiye e-postayla bildir
          </label>
          <button type="button" className={btnPrimary} disabled={!ready || assign.isPending} onClick={() => assign.mutate()}>
            {assign.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Check aria-hidden className="h-4 w-4" />}
            Atamayı kaydet
          </button>
        </div>
        {notify && !ctx.ov.email.configured && <p className="mt-1 text-right text-[11px] text-amber-700">E-posta ayarı girilmemiş: bildirim yazışmaya kaydedilir, gönderilmez.</p>}
      </div>
    </Panel>
  );
}

// ------------------------------------------------------------------ görev: düzenleme, teslim, karar

function TaskPanel({ ctx, p, t }: { ctx: FlCtx; p: FlPackage; t: FlTask }) {
  const refresh = useFlRefresh();
  const editable = ctx.canManage && !t.payoutId && ['atanmadi', 'atandi', 'calisiyor', 'revizyon'].includes(t.status);
  const [e, setE] = useState({ units: editNum(t.units), unitPrice: editNum(t.unitPrice), effortHours: editNum(t.effortHours), start: t.start ?? '', due: t.due ?? '' });
  const dirty =
    parseNum(e.units) !== t.units || parseNum(e.unitPrice) !== t.unitPrice || parseNum(e.effortHours) !== t.effortHours || e.start !== (t.start ?? '') || e.due !== (t.due ?? '');
  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) => freelanceApi.updateTask(t.id, body),
    onSuccess: () => {
      toast.success('Görev güncellendi.');
      refresh();
    },
    onError: (err) => toast.error(errText(err, 'Kaydedilemedi.')),
  });
  const del = useMutation({
    mutationFn: () => freelanceApi.deleteTask(t.id),
    onSuccess: () => {
      toast.success('Görev silindi.');
      refresh();
    },
    onError: (err) => toast.error(errText(err, 'Silinemedi.')),
  });
  const awaiting = t.deliveries?.find((d) => d.decision === 'bekliyor');
  const canDeliver = ctx.canManage && ['atandi', 'calisiyor', 'revizyon'].includes(t.status);

  return (
    <div className="border-t border-slate-100 px-3 pb-3 pt-2 text-[12.5px]">
      {editable ? (
        <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-5">
          <FieldBox label={`Miktar (${t.unit})`}>
            <input value={e.units} onChange={(x) => setE({ ...e, units: x.target.value })} className={field} inputMode="decimal" />
          </FieldBox>
          <FieldBox label="Birim ücret (₺)">
            <input value={e.unitPrice} onChange={(x) => setE({ ...e, unitPrice: x.target.value })} className={field} inputMode="decimal" />
          </FieldBox>
          <FieldBox label="Tahmini saat">
            <input value={e.effortHours} onChange={(x) => setE({ ...e, effortHours: x.target.value })} className={field} inputMode="decimal" />
          </FieldBox>
          <FieldBox label="Başlangıç">
            <input type="date" value={e.start} onChange={(x) => setE({ ...e, start: x.target.value })} className={field} />
          </FieldBox>
          <FieldBox label="Termin">
            <input type="date" value={e.due} onChange={(x) => setE({ ...e, due: x.target.value })} className={field} />
          </FieldBox>
        </div>
      ) : (
        <p className="text-[12px] text-canvas-muted">
          {q2(t.units)} {t.unit} × {tl(t.unitPrice)} = <b className="text-canvas-ink">{tl(t.amount)}</b> · {q2(t.effortHours)} saat · {day(t.start)} – {day(t.due)}
          {t.payoutId ? ' · hakedişe girdi' : ''}
          <SqlInfo k={p.kaynaklar} alan="tasks[]" label="Görev tutarı" className="ml-0.5" />
        </p>
      )}
      {ctx.canManage && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {editable && dirty && (
            <button type="button" className={btnPrimary} disabled={save.isPending} onClick={() => save.mutate({ units: parseNum(e.units), unitPrice: parseNum(e.unitPrice) || 0, effortHours: parseNum(e.effortHours), start: e.start || null, due: e.due || null })}>
              Kaydet
            </button>
          )}
          {t.status === 'atandi' && (
            <button type="button" className={btnGhost} onClick={() => save.mutate({ status: 'calisiyor' })}>
              Çalışıyor olarak işaretle
            </button>
          )}
          {['atandi', 'calisiyor', 'revizyon'].includes(t.status) && (
            <ConfirmButton confirm="Görev iptal edilsin mi?" onConfirm={() => save.mutate({ status: 'iptal' })}>
              Görevi iptal et
            </ConfirmButton>
          )}
          {t.status === 'iptal' && p.status === 'acik' && (
            <button type="button" className={btnGhost} onClick={() => save.mutate({ status: 'atanmadi' })}>
              Yeniden aç
            </button>
          )}
          {t.status === 'atanmadi' && (
            <ConfirmButton confirm="Silinsin mi?" onConfirm={() => del.mutate()}>
              <Trash2 aria-hidden className="h-4 w-4" />
              Sil
            </ConfirmButton>
          )}
        </div>
      )}

      {canDeliver && <DeliveryForm taskId={t.id} />}
      {awaiting && ctx.canManage && <Decision deliveryId={awaiting.id} hasEmail={!!t.personEmail} />}

      {!!t.deliveries?.length && (
        <ul className="mt-3 space-y-1.5">
          {t.deliveries.map((d) => (
            <li key={d.id} className="rounded-xl bg-slate-50 px-2.5 py-2">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-[11.5px] font-bold">Sürüm {d.version}</span>
                <Pill tone={d.decision === 'kabul' ? 'ok' : d.decision === 'revizyon' ? 'warn' : 'muted'}>
                  {d.decision === 'kabul' ? 'Kabul' : d.decision === 'revizyon' ? 'Revizyon istendi' : 'İnceleme bekliyor'}
                </Pill>
                <span className="text-[11px] text-canvas-muted">
                  {stamp(d.uploadedAt)} · {d.uploadedBy}
                </span>
                <span className="ml-auto flex gap-1.5">
                  {d.filename && (
                    <a href={freelanceApi.deliveryUrl(d.id)} className="inline-flex items-center gap-1 text-[11.5px] font-bold text-canvas-violet hover:underline">
                      <Download aria-hidden className="h-3.5 w-3.5" />
                      {d.filename}
                    </a>
                  )}
                  {d.link && (
                    <a href={d.link} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-1 text-[11.5px] font-bold text-canvas-violet hover:underline">
                      <ExternalLink aria-hidden className="h-3.5 w-3.5" />
                      Bağlantı
                    </a>
                  )}
                </span>
              </div>
              {d.note && <p className="mt-1 whitespace-pre-line text-[12px]">{d.note}</p>}
              {d.decisionNote && (
                <p className="mt-1 whitespace-pre-line text-[12px] text-amber-800">
                  {d.decidedBy}: {d.decisionNote}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function DeliveryForm({ taskId }: { taskId: string }) {
  const refresh = useFlRefresh();
  const [mode, setMode] = useState<'dosya' | 'baglanti'>('dosya');
  const [link, setLink] = useState('');
  const [note, setNote] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const send = useMutation({
    mutationFn: () => (mode === 'dosya' && file ? freelanceApi.deliverFile(taskId, file, note) : freelanceApi.deliverLink(taskId, link, note)),
    onSuccess: (r) => {
      toast.success(`Teslim kaydedildi (sürüm ${r.version}); inceleme bekliyor.`);
      setLink('');
      setNote('');
      setFile(null);
      refresh();
    },
    onError: (e) => toast.error(errText(e, 'Teslim kaydedilemedi.')),
  });
  return (
    <form
      className="mt-3 grid gap-2 rounded-xl border border-dashed border-slate-200 p-2.5"
      onSubmit={(e) => {
        e.preventDefault();
        send.mutate();
      }}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Teslim al</span>
        <div className="flex gap-1 rounded-lg bg-slate-100 p-0.5">
          {(
            [
              ['dosya', 'Dosya', Upload],
              ['baglanti', 'Bağlantı', Link2],
            ] as const
          ).map(([k, l, Icon]) => (
            <button key={k} type="button" aria-pressed={mode === k} onClick={() => setMode(k)} className={`inline-flex min-h-8 items-center gap-1 rounded-md px-2 text-[11.5px] font-bold ${mode === k ? 'bg-white shadow-sm' : 'text-canvas-muted'}`}>
              <Icon aria-hidden className="h-3.5 w-3.5" />
              {l}
            </button>
          ))}
        </div>
      </div>
      {mode === 'dosya' ? (
        <>
          <FileDrop
            size="sm"
            title={file ? 'Başka dosya seç' : 'Teslim dosyasını seç'}
            hint="Daha büyük dosya için «Bağlantı» ile paylaşım adresi verin."
            maxBytes={200 * MB}
            picked={file}
            onPick={setFile}
          />
        </>
      ) : (
        <input value={link} onChange={(e) => setLink(e.target.value)} className={field} inputMode="url" placeholder="https://… (WeTransfer, Drive…)" />
      )}
      <input value={note} onChange={(e) => setNote(e.target.value)} className={field} placeholder="Not (isteğe bağlı)" />
      <div className="flex justify-end">
        <button type="submit" className={btnPrimary} disabled={send.isPending || (mode === 'dosya' ? !file : !link.trim())}>
          {send.isPending && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}
          Teslimi kaydet
        </button>
      </div>
    </form>
  );
}

function Decision({ deliveryId, hasEmail }: { deliveryId: string; hasEmail: boolean }) {
  const refresh = useFlRefresh();
  const [note, setNote] = useState('');
  const [notify, setNotify] = useState(hasEmail);
  const decide = useMutation({
    mutationFn: (d: 'kabul' | 'revizyon') => freelanceApi.decide(deliveryId, d, note, notify),
    onSuccess: (r, d) => {
      toast.success(d === 'kabul' ? 'Teslim kabul edildi; iş ödenecekler listesine düştü.' : 'Revizyon istendi.');
      if (r.mail && r.mail !== 'gonderildi') toast.warning('Bildirim yazışmaya kaydedildi ama e-posta gönderilemedi.');
      setNote('');
      refresh();
    },
    onError: (e) => toast.error(errText(e, 'Karar kaydedilemedi.')),
  });
  return (
    <div className="mt-3 grid gap-2 rounded-xl bg-amber-50 p-2.5">
      <span className="text-[11px] font-bold uppercase tracking-wide text-amber-800">Son teslimi incele</span>
      <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2} className={field} placeholder="Revizyon için ne düzeltilecek? (kabulde isteğe bağlı not)" />
      <div className="flex flex-wrap items-center justify-between gap-2">
        {hasEmail ? (
          <label className="inline-flex items-center gap-2 text-[12px] font-semibold">
            <input type="checkbox" checked={notify} onChange={(e) => setNotify(e.target.checked)} className="h-5 w-5 accent-canvas-violet" />
            Kararı e-postayla bildir
          </label>
        ) : (
          <span className="text-[11px] text-canvas-muted">Kişinin e-postası yok; bildirim gitmez.</span>
        )}
        <div className="flex gap-1.5">
          <button type="button" className={btnGhost} disabled={decide.isPending || !note.trim()} onClick={() => decide.mutate('revizyon')} title={!note.trim() ? 'Önce düzeltilecekleri yazın' : undefined}>
            Revizyon iste
          </button>
          <button type="button" className={btnPrimary} disabled={decide.isPending} onClick={() => decide.mutate('kabul')}>
            <Check aria-hidden className="h-4 w-4" />
            Kabul et
          </button>
        </div>
      </div>
    </div>
  );
}
