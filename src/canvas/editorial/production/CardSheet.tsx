import { useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { BadgeCheck, BookImage, BookOpen, CalendarPlus, ClipboardList, Trash2 } from 'lucide-react';
import { ENGINE_ENABLED } from '../../engine';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText, field, label, nf } from '../../admin/ui';
import Sheet from '../studio/reader/Sheet';
import SqlInfo from '../../components/SqlInfo';
import { productionApi, type Milestone, type ProdDetail, type Suggestion } from './api';
import { Chain, POINTS, SOURCE_LABEL, STAGE_TONE, daysText, fmtDay, fmtMoney, fmtUnit, invalidateProduction, useProductionMeta } from './shared';

/** Üretim kartı: takvim (plan / gerçekleşen / kaynak), matbaa seçim raporu, Logo'da gerçekleşen, baskı dosyaları,
 *  kalite ve notlar. CRM'e yazılmaz; burada girilen her şey portal kaydıdır ve kimin girdiği yazar. */

function Block({ title, action, children }: { title: string; action?: ReactNode; children: ReactNode }) {
  return (
    <section className="mt-4 first:mt-1">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">{title}</h3>
        {action}
      </div>
      <div className="mt-1.5">{children}</div>
    </section>
  );
}

const today = () => new Date().toLocaleDateString('en-CA', { timeZone: 'Europe/Istanbul' });

function useWrite(id: string) {
  const qc = useQueryClient();
  const done = (msg: string) => {
    toast.success(msg);
    return invalidateProduction(qc);
  };
  const fail = (e: unknown) => toast.error(errText(e, 'Kaydedilemedi.') ?? 'Kaydedilemedi.');
  return {
    entry: useMutation({
      mutationFn: (b: Parameters<typeof productionApi.addEntry>[1]) => productionApi.addEntry(id, b),
      onSuccess: () => done('Kaydedildi.'),
      onError: fail,
    }),
    del: useMutation({ mutationFn: (rid: string) => productionApi.deleteEntry(rid), onSuccess: () => done('Silindi.'), onError: fail }),
    quote: useMutation({
      mutationFn: (b: Parameters<typeof productionApi.addQuote>[1]) => productionApi.addQuote(id, b),
      onSuccess: () => done('Teklif kaydedildi.'),
      onError: fail,
    }),
    delQuote: useMutation({ mutationFn: (rid: string) => productionApi.deleteQuote(rid), onSuccess: () => done('Teklif silindi.'), onError: fail }),
    approve: useMutation({
      mutationFn: (b: { printer: string; note?: string }) => productionApi.approve(id, b),
      onSuccess: () => done('Matbaa onaylandı.'),
      onError: fail,
    }),
  };
}

function Timeline({ c, canWrite }: { c: ProdDetail; canWrite: boolean }) {
  const w = useWrite(c.id);
  const [editing, setEditing] = useState<Milestone | null>(null);
  const [day, setDay] = useState(today());
  const [note, setNote] = useState('');
  const basis =
    c.planBasis === 'yayin'
      ? `Plan, hedef yayın tarihinden (${fmtDay(c.publication)}) geriye doğru.`
      : c.planBasis === 'crm'
        ? "Plan CRM takviminden: üretime teslim tarihi ve baskı ayı (ayın sonuna kadar); depo girişi Logo'daki planlanan girişten."
        : c.planBasis === 'logo'
          ? "Plan Logo'daki planlanan depo girişinden."
          : 'Plan yok: hedef yayın tarihi girilince takvim kurulur.';
  return (
    <>
      <ol className="space-y-1.5">
        {POINTS.map((p) => {
          const a = c.actual[p.key];
          const plan = c.plan[p.key];
          const late = c.delays.find((d) => d.milestone === p.key);
          return (
            <li key={p.key} className={`rounded-xl border px-3 py-2 ${late ? 'border-rose-200 bg-rose-50/60' : 'border-slate-100 bg-white/85'}`}>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-[12.5px] font-bold">{p.label}</span>
                {a ? (
                  <span className="inline-flex items-center gap-1.5">
                    <span className="font-mono text-[12.5px] font-bold tabular-nums">{a.day ? fmtDay(a.day) : 'tarihsiz'}</span>
                    <Pill tone={a.source === 'portal' ? 'violet' : 'ok'}>{SOURCE_LABEL[a.source]}</Pill>
                  </span>
                ) : late ? (
                  <Pill tone="err">
                    {daysText(late.days)} gecikme · {late.level === 'yonetici' ? 'yöneticide' : 'sorumluda'}
                  </Pill>
                ) : (
                  <span className="text-[11.5px] text-canvas-muted">bekleniyor</span>
                )}
              </div>
              <div className="mt-0.5 flex flex-wrap items-center justify-between gap-2 text-[11.5px] text-canvas-muted">
                <span>Plan: {plan ? fmtDay(plan) : '—'}</span>
                {a?.source === 'portal' && a.by && <span>{a.by} girdi</span>}
                {!a && canWrite && editing !== p.key && (
                  <button type="button" className="font-bold text-canvas-violet underline" onClick={() => { setEditing(p.key); setDay(today()); setNote(''); }}>
                    Gerçekleşti, tarih gir
                  </button>
                )}
              </div>
              {editing === p.key && (
                <form
                  className="mt-2 grid gap-1.5 sm:grid-cols-[160px_minmax(0,1fr)_auto]"
                  onSubmit={(e) => {
                    e.preventDefault();
                    w.entry.mutate({ kind: 'gercek', milestone: p.key, day, note: note || undefined }, { onSuccess: () => setEditing(null) });
                  }}
                >
                  <input type="date" className={field} value={day} max={today()} required aria-label={`${p.label} tarihi`} onChange={(e) => setDay(e.target.value)} />
                  <input className={field} value={note} placeholder="Not (isteğe bağlı)" aria-label="Not" onChange={(e) => setNote(e.target.value)} />
                  <div className="flex gap-1.5">
                    <button type="submit" className={btnPrimary} disabled={w.entry.isPending}>
                      Kaydet
                    </button>
                    <button type="button" className={btnGhost} onClick={() => setEditing(null)}>
                      Vazgeç
                    </button>
                  </div>
                </form>
              )}
            </li>
          );
        })}
      </ol>
      <p className="mt-2 text-[11.5px] leading-snug text-canvas-muted">{basis} CRM ya da Logo'da tarih varsa o geçerlidir; portal kaydı yalnız boşu doldurur.</p>
      {canWrite && <PublicationForm c={c} />}
    </>
  );
}

function PublicationForm({ c }: { c: ProdDetail }) {
  const w = useWrite(c.id);
  const [day, setDay] = useState(c.publication ?? '');
  return (
    <form
      className="mt-2 flex flex-wrap items-end gap-1.5"
      onSubmit={(e) => {
        e.preventDefault();
        w.entry.mutate({ kind: 'yayin', day });
      }}
    >
      <label className="min-w-[160px] flex-1 sm:flex-none">
        <span className={label}>Hedef yayın tarihi</span>
        <input type="date" className={`${field} mt-1`} value={day} required onChange={(e) => setDay(e.target.value)} />
      </label>
      <button type="submit" className={btnGhost} disabled={w.entry.isPending || !day || day === c.publication}>
        <CalendarPlus aria-hidden className="h-4 w-4" />
        Takvimi buna göre kur
      </button>
    </form>
  );
}

function SuggestionRow({ s, approved, canApprove, onApprove, busy }: { s: Suggestion; approved: boolean; canApprove: boolean; onApprove: () => void; busy: boolean }) {
  return (
    <li className="rounded-xl border border-slate-100 bg-white/85 px-3 py-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="min-w-0 break-words text-[12.5px] font-extrabold">{s.printer}</span>
        <span className="inline-flex items-center gap-1.5">
          <span className="font-mono text-[13px] font-bold tabular-nums">{s.score}</span>
          <span className="text-[10.5px] text-canvas-muted">/ 100</span>
          {approved && <Pill tone="ok">Onaylı</Pill>}
        </span>
      </div>
      <p className="mt-0.5 text-[11.5px] leading-snug text-canvas-muted">{s.why.join(' · ') || 'Geçmiş kaydı az.'}</p>
      {s.quote && (
        <p className="mt-0.5 text-[11.5px]">
          Teklif: {s.quote.unitPrice !== null ? `${fmtUnit(s.quote.unitPrice)} / adet` : ''}
          {s.quote.totalPrice !== null ? ` · toplam ${fmtMoney(s.quote.totalPrice)}` : ''}
          {s.quote.deliveryDay ? ` · teslim ${fmtDay(s.quote.deliveryDay)}` : ''}
        </p>
      )}
      {canApprove && !approved && (
        <button type="button" className={`${btnGhost} mt-1.5`} disabled={busy} onClick={onApprove}>
          <BadgeCheck aria-hidden className="h-4 w-4" />
          Bu matbaayı onayla
        </button>
      )}
    </li>
  );
}

function PrinterBlock({ c, canWrite, canApprove }: { c: ProdDetail; canWrite: boolean; canApprove: boolean }) {
  const meta = useProductionMeta();
  const w = useWrite(c.id);
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ printer: '', unitPrice: '', totalPrice: '', deliveryDay: '', note: '' });
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  return (
    <>
      {c.approval && (
        <Note tone="ok">
          Prodüksiyon onayı: <b>{c.approval}</b>
        </Note>
      )}
      {c.suggestions.length === 0 ? (
        <p className="text-[12px] text-canvas-muted">Öneri için geçmiş matbaa kaydı ya da teklif yok.</p>
      ) : (
        <ul className="mt-1.5 space-y-1.5">
          {c.suggestions.map((s) => (
            <SuggestionRow
              key={s.printer}
              s={s}
              approved={c.approval === s.printer}
              canApprove={canApprove}
              busy={w.approve.isPending}
              onApprove={() => w.approve.mutate({ printer: s.printer })}
            />
          ))}
        </ul>
      )}
      {c.quotes.length > 0 && (
        <ul className="mt-2 space-y-1">
          {c.quotes.map((q) => (
            <li key={q.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-slate-50 px-2.5 py-1.5 text-[11.5px]">
              <span className="min-w-0">
                <b>{q.printer}</b> · {q.unitPrice !== null ? `${fmtUnit(q.unitPrice)}/adet` : fmtMoney(q.totalPrice)}
                {q.deliveryDay ? ` · teslim ${fmtDay(q.deliveryDay)}` : ''} · {q.byName}
              </span>
              {canWrite && (
                <button type="button" aria-label="Teklifi sil" className="inline-flex h-9 w-9 items-center justify-center rounded-lg text-canvas-muted hover:bg-slate-200" onClick={() => w.delQuote.mutate(q.id)}>
                  <Trash2 aria-hidden className="h-4 w-4" />
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      {canWrite && !open && (
        <button type="button" className={`${btnGhost} mt-2`} onClick={() => setOpen(true)}>
          <ClipboardList aria-hidden className="h-4 w-4" />
          Teklif ekle
        </button>
      )}
      {canWrite && open && (
        <form
          className="mt-2 grid gap-1.5 rounded-xl border border-slate-100 bg-white/85 p-2.5 sm:grid-cols-2"
          onSubmit={(e) => {
            e.preventDefault();
            w.quote.mutate(f, {
              onSuccess: () => {
                setOpen(false);
                setF({ printer: '', unitPrice: '', totalPrice: '', deliveryDay: '', note: '' });
              },
            });
          }}
        >
          <label className="sm:col-span-2">
            <span className={label}>Matbaa</span>
            <input className={`${field} mt-1`} list="uretim-matbaalar" value={f.printer} required onChange={set('printer')} />
            <datalist id="uretim-matbaalar">
              {(meta.data?.printers ?? []).map((p) => (
                <option key={p} value={p} />
              ))}
            </datalist>
          </label>
          <label>
            <span className={label}>Birim fiyat (₺)</span>
            <input className={`${field} mt-1`} inputMode="decimal" value={f.unitPrice} onChange={set('unitPrice')} />
          </label>
          <label>
            <span className={label}>Toplam (₺)</span>
            <input className={`${field} mt-1`} inputMode="decimal" value={f.totalPrice} onChange={set('totalPrice')} />
          </label>
          <label>
            <span className={label}>Teslim tarihi</span>
            <input type="date" className={`${field} mt-1`} value={f.deliveryDay} onChange={set('deliveryDay')} />
          </label>
          <label>
            <span className={label}>Kapasite / not</span>
            <input className={`${field} mt-1`} value={f.note} onChange={set('note')} />
          </label>
          <div className="flex gap-1.5 sm:col-span-2">
            <button type="submit" className={btnPrimary} disabled={w.quote.isPending}>
              Kaydet
            </button>
            <button type="button" className={btnGhost} onClick={() => setOpen(false)}>
              Vazgeç
            </button>
          </div>
        </form>
      )}
    </>
  );
}

function QualityBlock({ c, canWrite }: { c: ProdDetail; canWrite: boolean }) {
  const w = useWrite(c.id);
  const [note, setNote] = useState('');
  const current = c.entries.find((e) => e.kind === 'kalite');
  return (
    <>
      {current ? (
        <p className="text-[12px]">
          <Pill tone={current.value === 'sorun' ? 'err' : 'ok'}>{current.valueLabel}</Pill> <span className="text-canvas-muted">{current.byName}, {fmtDay(current.at)}</span>
          {current.note && <span className="mt-0.5 block">{current.note}</span>}
        </p>
      ) : (
        <p className="text-[12px] text-canvas-muted">Kalite sonucu girilmedi.</p>
      )}
      {canWrite && c.actual.depo && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          <input className={`${field} min-w-[200px] flex-1`} value={note} placeholder="Sorun varsa bir cümle" aria-label="Kalite notu" onChange={(e) => setNote(e.target.value)} />
          <button type="button" className={btnGhost} disabled={w.entry.isPending} onClick={() => w.entry.mutate({ kind: 'kalite', value: 'sorunsuz', note: note || undefined })}>
            Sorunsuz
          </button>
          <button type="button" className={btnGhost} disabled={w.entry.isPending} onClick={() => w.entry.mutate({ kind: 'kalite', value: 'sorun', note })}>
            Sorun var
          </button>
        </div>
      )}
    </>
  );
}

function NotesBlock({ c, canWrite, me, admin }: { c: ProdDetail; canWrite: boolean; me: string; admin: boolean }) {
  const w = useWrite(c.id);
  const [note, setNote] = useState('');
  return (
    <>
      {canWrite && (
        <form
          className="flex gap-1.5"
          onSubmit={(e) => {
            e.preventDefault();
            w.entry.mutate({ kind: 'not', note }, { onSuccess: () => setNote('') });
          }}
        >
          <input className={`${field} flex-1`} value={note} placeholder="Not ekle" aria-label="Not" onChange={(e) => setNote(e.target.value)} />
          <button type="submit" className={btnPrimary} disabled={!note.trim() || w.entry.isPending}>
            Ekle
          </button>
        </form>
      )}
      {c.entries.length === 0 ? (
        <p className="mt-1.5 text-[12px] text-canvas-muted">Portal kaydı yok.</p>
      ) : (
        <ul className="mt-2 space-y-1">
          {c.entries.map((e) => (
            <li key={e.id} className="flex items-start justify-between gap-2 rounded-lg bg-slate-50 px-2.5 py-1.5 text-[11.5px]">
              <span className="min-w-0 break-words">
                <b>{e.kindLabel}</b>
                {e.milestoneLabel ? ` · ${e.milestoneLabel}` : ''}
                {e.day ? ` · ${fmtDay(e.day)}` : ''}
                {e.valueLabel ? ` · ${e.valueLabel}` : ''}
                {e.note ? ` — ${e.note}` : ''}
                <span className="block text-canvas-muted">
                  {e.byName} · {fmtDay(e.at)}
                </span>
              </span>
              {(e.by === me || admin) && canWrite && (
                <button type="button" aria-label="Kaydı sil" className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-canvas-muted hover:bg-slate-200" onClick={() => w.del.mutate(e.id)}>
                  <Trash2 aria-hidden className="h-4 w-4" />
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

export default function CardSheet({ id, onClose }: { id: string | null; onClose: () => void }) {
  const meta = useProductionMeta();
  const q = useQuery({ queryKey: ['production', 'card', id], queryFn: () => productionApi.card(id as string), enabled: ENGINE_ENABLED && !!id });
  const c = q.data;
  const me = meta.data?.me;
  const canWrite = !!me?.canWrite;
  const canApprove = !!me?.canApprove;
  const err = errText(q.error, 'Üretim kartı okunamadı.');
  const title = c ? c.bookTitle || c.name || 'Üretim kartı' : 'Üretim kartı';
  return (
    <Sheet
      open={!!id}
      onClose={onClose}
      wide
      title={title}
      subtitle={
        c ? (
          <span className="inline-flex flex-wrap items-center gap-1.5">
            <span className={`inline-flex items-center rounded-md px-1.5 py-0.5 text-[11px] font-bold ${STAGE_TONE[c.stage]}`}>{c.stageLabel}</span>
            {[c.cardKind, c.printNo ? `${c.printNo}. baskı` : null, c.qty ? `${nf.format(c.qty)} adet` : null, c.idno, c.kind].filter(Boolean).join(' · ')}
          </span>
        ) : undefined
      }
    >
      {err && <Note tone="err">{err}</Note>}
      {q.isLoading && <Loading />}
      {c && (
        <>
          <div className="rounded-2xl border border-slate-100 bg-white/85 p-3">
            <Chain card={c} />
          </div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {c.bookId && (
              <Link to={`/kitap/${c.bookId}`} className={btnGhost}>
                <BookOpen aria-hidden className="h-4 w-4" />
                Kitap 360
              </Link>
            )}
          </div>
          <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1.5 text-[12px] sm:grid-cols-3">
            {(
              [
                ['Matbaa', c.printer ?? '—'],
                ['CRM aşaması', c.crmStatus ?? '—'],
                ['Öncelik', c.priority ?? '—'],
                ['Sorumlu editör', c.editor ?? '—'],
                ['Grafiker', c.designer ?? '—'],
                ['Bandrol', c.bandrol ?? '—'],
                ['Kesin adet', c.qty !== null ? nf.format(c.qty) : '—', 'qty'],
                ['Depoya giren', c.logoQty !== null ? `${nf.format(c.logoQty)} adet` : '—', 'logoQty'],
                ['Satış fiyatı', fmtMoney(c.coverPrice), 'coverPrice'],
                ['Baskı bedeli', fmtMoney(c.price), 'price'],
                ['Adet başı baskı', fmtUnit(c.unitPrice), 'unitPrice'],
                ['Faturalanan adet', c.costQty !== null ? nf.format(c.costQty) : '—', 'costQty'],
              ] as Array<[string, string, string?]>
            ).map(([k, v, alan]) => (
              <div key={k} className="min-w-0">
                <dt className="flex items-center gap-1 text-[10.5px] font-bold uppercase tracking-wide text-canvas-muted">
                  {k}
                  {alan && <SqlInfo k={c.kaynaklar} alan={alan} label={k} />}
                </dt>
                <dd className="break-words font-semibold">{v}</dd>
              </div>
            ))}
          </dl>
          {c.waiting && (
            <div className="mt-2">
              <Note tone="warn">Üretimde beklemede: {c.waiting}</Note>
            </div>
          )}

          <Block title="Üretim takvimi" action={<SqlInfo k={c.kaynaklar} alan="delays" label="Üretim takvimi ve gecikme" />}>
            <Timeline c={c} canWrite={canWrite} />
          </Block>

          <Block
            title="Matbaa seçim raporu"
            action={
              <span className="inline-flex items-center gap-1 text-[11px] text-canvas-muted">
                puan <SqlInfo k={c.kaynaklar} alan="suggestions[]" label="Matbaa seçim raporu" />
                {c.quotes.length > 0 && (
                  <>
                    · teklifler <SqlInfo k={c.kaynaklar} alan="quotes[]" label="Matbaa teklifleri" />
                  </>
                )}
              </span>
            }
          >
            <PrinterBlock c={c} canWrite={canWrite} canApprove={canApprove} />
          </Block>

          <Block title="Baskı dosyaları">
            {c.studio.length === 0 ? (
              <p className="text-[12px] text-canvas-muted">Kitap tasarımında bu kitaba bağlı iş yok.</p>
            ) : (
              <ul className="space-y-1">
                {c.studio.map((s) => (
                  <li key={s.job}>
                    <Link to={`/kitap-tasarim/${s.job}`} className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-slate-50 px-2.5 py-2 text-[12px] hover:bg-slate-100">
                      <span className="inline-flex min-w-0 items-center gap-1.5 font-semibold">
                        <BookImage aria-hidden className="h-4 w-4 shrink-0" />
                        <span className="truncate">{s.title || 'Kitap tasarım işi'}</span>
                      </span>
                      <Pill tone={s.ready ? 'ok' : 'muted'}>{s.status}</Pill>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Block>

          <Block
            title="Logo'da gerçekleşen"
            action={
              <span className="inline-flex items-center gap-1 text-[11px] text-canvas-muted">
                {(c.logoOrders.length > 0 || c.logoReceipts.length > 0) && (
                  <>
                    emir ve girişler <SqlInfo k={c.kaynaklar} alan="logoOrders[]" label="Logo üretim emri ve giriş fişleri" />
                  </>
                )}
                {c.logoCosts.length > 0 && (
                  <>
                    {' '}· faturalar <SqlInfo k={c.kaynaklar} alan="logoCosts[]" label="Logo matbaa baskı faturaları" />
                  </>
                )}
              </span>
            }
          >
            {c.logoOrders.length === 0 && c.logoCosts.length === 0 ? (
              <p className="text-[12px] text-canvas-muted">Logo'da bu karta bağlanan üretim emri ya da baskı faturası yok.</p>
            ) : (
              <ul className="space-y-1 text-[12px]">
                {c.logoOrders.map((o) => (
                  <li key={`o${o.no}`} className="rounded-lg bg-slate-50 px-2.5 py-1.5">
                    <b>Üretim emri {o.no}</b> · {fmtDay(o.date)} · {o.planned !== null ? nf.format(o.planned) : '—'} adet
                    {o.status ? ` · ${o.status}` : ''}
                    <span className="block text-[11px] text-canvas-muted">
                      {c.logoMatch === 'no' ? 'Üretim numarasıyla eşlendi' : 'Stok kodu ve tarihle eşlendi (emirde üretim numarası yok)'}
                    </span>
                  </li>
                ))}
                {c.logoReceipts.map((r, i) => (
                  <li key={`r${r.no}-${i}`} className={`rounded-lg px-2.5 py-1.5 ${r.planned ? 'bg-slate-50 text-canvas-muted' : 'bg-emerald-50'}`}>
                    <b>{r.planned ? 'Planlanan depo girişi' : 'Depo girişi'} {r.no}</b> · {fmtDay(r.date)} · {r.qty !== null ? nf.format(r.qty) : '—'} adet
                  </li>
                ))}
                {c.logoCosts.map((x, i) => (
                  <li key={`c${x.no}-${i}`} className="rounded-lg bg-sky-50 px-2.5 py-1.5">
                    <b>Baskı faturası {x.no}</b> · {fmtDay(x.date)} · {x.supplier ?? '—'} · {x.qty !== null ? nf.format(x.qty) : '—'} adet ·{' '}
                    {fmtMoney(x.total)}
                  </li>
                ))}
              </ul>
            )}
          </Block>

          <Block title="Kalite">
            <QualityBlock c={c} canWrite={canWrite} />
          </Block>

          <Block title="Notlar ve kayıtlar">
            <NotesBlock c={c} canWrite={canWrite} me={me?.username ?? ''} admin={!!me?.admin} />
          </Block>

          <Block title="CRM'deki bütün tarihler">
            <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-[11.5px] sm:grid-cols-3">
              {c.crmDates.map((d) => (
                <div key={d.key} className="min-w-0">
                  <dt className={d.plan ? 'text-canvas-violet' : 'text-canvas-muted'}>{d.label}</dt>
                  <dd className="font-mono tabular-nums">{d.day ? fmtDay(d.day) : '—'}</dd>
                </div>
              ))}
            </dl>
          </Block>
        </>
      )}
    </Sheet>
  );
}
