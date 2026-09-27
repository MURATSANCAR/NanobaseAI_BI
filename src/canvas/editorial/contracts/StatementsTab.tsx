import { useMemo, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Calculator, Download, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { Note, Pill, btnGhost, btnPrimary, field } from '../../admin/ui';
import { Panel } from '../kit';
import { contractApi, downloadDocx, type Calc, type Detail, type Meta, type Statement } from './api';
import { NumInput } from './TermsForm';
import { Field, day, errMsg, money, num, stamp } from './ui';

/** Hakediş: dönem seçilir → Logo satışı (ya da girilen baskı adedi) ile hesaplanır → taslak kaydedilir →
 *  onaylanınca ödeme takvimine düşer. Onaylı hakediş değişmez; iptal edilip yeniden hesaplanır. */

const monthStart = (ym: string) => `${ym}-01`;
const monthEnd = (ym: string) => {
  const [y, m] = ym.split('-').map(Number);
  const last = new Date(Date.UTC(y, m, 0)).getUTCDate();
  return `${ym}-${String(last).padStart(2, '0')}`;
};

function CalcView({ c }: { c: Calc }) {
  const cur = c.currency;
  return (
    <div className="space-y-3">
      {c.warnings.length > 0 && (
        <ul className="space-y-1">
          {c.warnings.map((w) => (
            <li key={w}><Note tone="warn">{w}</Note></li>
          ))}
        </ul>
      )}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {[
          ['Adet', num(c.quantity, 0)],
          ['Brüt telif', money(c.gross, cur)],
          ['Avanstan düşülen', money(c.advanceOffset, cur)],
          ['Ödenecek net', money(c.net, cur)],
        ].map(([l, v]) => (
          <div key={l} className="rounded-2xl border border-slate-100 bg-white p-2.5">
            <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">{l}</div>
            <div className="mt-0.5 font-mono text-[15px] font-bold tabular-nums">{v}</div>
          </div>
        ))}
      </div>
      <div className="text-[11.5px] leading-relaxed text-canvas-muted">
        Matrah {money(c.base, 'TRY')}{c.fx ? ` · kur ${num(c.fx.rate, 4)} (${day(c.fx.on)}${c.fx.source ? `, ${c.fx.source}` : ''}) · TL karşılığı ${money(c.grossTry, 'TRY')}` : ''}
        {c.advance ? ` · avans ${money(c.advance, c.contractCurrency)}, önceki dönemlerde düşülen ${money(c.advanceUsedBefore, cur)}, kalan ${money(c.advanceRemaining, cur)}` : ''}
        {c.withholdingPct ? ` · stopaj %${num(c.withholdingPct)} = ${money(c.withholding, cur)}` : ''}
        {c.carryOut ? ` · sonraki döneme devreden ${money(c.carryOut, cur)}` : ''}
        {c.source ? ` · kaynak: ${c.source}` : ''}
        {c.dataEnd ? ` · Logo verisi ${day(c.dataEnd)} gününe kadar` : ''}
      </div>
      <div className="overflow-x-auto rounded-2xl border border-slate-100 bg-white">
        <table className="w-full min-w-[640px] text-[12px]">
          <thead>
            <tr className="border-b border-slate-100 text-left text-[11px] font-bold uppercase tracking-wide text-canvas-muted">
              <th className="px-2.5 py-2">Kitap</th>
              <th className="px-2.5 py-2">Taraf</th>
              <th className="px-2.5 py-2 text-right">Adet</th>
              <th className="px-2.5 py-2 text-right">Matrah</th>
              <th className="px-2.5 py-2 text-right">Oran</th>
              <th className="px-2.5 py-2 text-right">Telif</th>
            </tr>
          </thead>
          <tbody>
            {c.lines.map((ln, i) => (
              <tr key={i} className="border-b border-slate-100 align-top last:border-0">
                <td className="px-2.5 py-2">
                  <div className="font-semibold">{ln.book}</div>
                  <div className="font-mono text-[10.5px] text-canvas-muted">{ln.stockCode} · {ln.source}{ln.returns ? ` · iade ${num(ln.returns, 0)}` : ''}</div>
                </td>
                <td className="px-2.5 py-2">{ln.party}{ln.share !== 100 ? <span className="text-canvas-muted"> · %{num(ln.share)}</span> : null}</td>
                <td className="px-2.5 py-2 text-right font-mono tabular-nums">{num(ln.quantity, 0)}</td>
                <td className="px-2.5 py-2 text-right font-mono tabular-nums">{money(ln.base, 'TRY')}</td>
                <td className="px-2.5 py-2 text-right font-mono tabular-nums">
                  %{num(ln.rate)}
                  {ln.tiers && <div className="text-[10.5px] text-canvas-muted">{ln.tiers.map((t) => `${num(t.quantity, 0)}×%${num(t.rate)}`).join(' + ')}</div>}
                </td>
                <td className="px-2.5 py-2 text-right font-mono font-bold tabular-nums">
                  {money(ln.royaltyCurrency ?? ln.royalty, ln.royaltyCurrency != null ? cur : 'TRY')}
                </td>
              </tr>
            ))}
            {!c.lines.length && (
              <tr>
                <td colSpan={6} className="px-2.5 py-6 text-center text-canvas-muted">Hesaplanacak satır yok.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function StatementCard({ s, canFinance }: { s: Statement; canFinance: boolean }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const done = () => {
    qc.invalidateQueries({ queryKey: ['contracts'] });
  };
  const approve = useMutation({ mutationFn: () => contractApi.statementApprove(s.id), onSuccess: () => { toast.success('Hakediş onaylandı; ödeme takvimine eklendi.'); done(); }, onError: (e) => toast.error(errMsg(e) ?? 'Onaylanamadı.') });
  const cancel = useMutation({ mutationFn: (note?: string) => contractApi.statementCancel(s.id, note), onSuccess: done, onError: (e) => toast.error(errMsg(e) ?? 'İptal edilemedi.') });
  const download = async () => {
    try {
      const missing = await downloadDocx(`/statements/${encodeURIComponent(s.id)}/document.docx`);
      if (missing.length) toast.warning(`Belgede doldurulamayan alan: ${missing.join(', ')}`);
    } catch (e) {
      toast.error(errMsg(e) ?? 'Belge indirilemedi.');
    }
  };
  return (
    <li className="rounded-2xl border border-slate-100 bg-white/85 p-3 text-[12.5px]">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-extrabold">{day(s.periodStart)} – {day(s.periodEnd)}</span>
        <Pill tone={s.status === 'onaylandi' ? 'ok' : s.status === 'iptal' ? 'muted' : 'warn'}>{s.statusLabel}</Pill>
        <span className="font-mono font-bold tabular-nums">net {money(s.net, s.currency)}</span>
        <span className="text-[11.5px] text-canvas-muted">
          brüt {money(s.gross, s.currency)} · {s.approvedBy ? `onay ${stamp(s.approvedAt)} ${s.approvedBy}` : `${stamp(s.createdAt)} ${s.createdBy}`}
        </span>
      </div>
      {s.note && <p className="mt-1 whitespace-pre-wrap text-[11.5px] text-canvas-muted">{s.note}</p>}
      <div className="mt-2 flex flex-wrap gap-1.5">
        <button type="button" className={btnGhost} onClick={() => setOpen((v) => !v)} aria-expanded={open}>{open ? 'Ayrıntıyı gizle' : 'Ayrıntı'}</button>
        <button type="button" className={btnGhost} onClick={download}>
          <Download aria-hidden className="h-4 w-4" />
          Bildirim (Word)
        </button>
        {canFinance && s.status === 'taslak' && (
          <button type="button" className={btnPrimary} disabled={approve.isPending} onClick={() => window.confirm(`Net ${money(s.net, s.currency)} onaylanıp ödeme takvimine eklensin mi?`) && approve.mutate()}>
            {approve.isPending && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}
            Onayla
          </button>
        )}
        {canFinance && s.status !== 'iptal' && (
          <button
            type="button"
            className={btnGhost}
            disabled={cancel.isPending}
            onClick={() => {
              const note = s.status === 'onaylandi' ? window.prompt('Onaylı hakedişin iptal gerekçesi (zorunlu):', '') : '';
              if (note === null || (s.status === 'onaylandi' && !note.trim())) return;
              if (s.status === 'taslak' && !window.confirm('Taslak hakediş iptal edilsin mi?')) return;
              cancel.mutate(note || undefined);
            }}
          >
            İptal et
          </button>
        )}
      </div>
      {open && <div className="mt-3"><CalcView c={s.calc} /></div>}
    </li>
  );
}

export default function StatementsTab({ d, meta }: { d: Detail; meta: Meta }) {
  const qc = useQueryClient();
  const t = d.terms;
  const royalty = meta.salesBased.includes(t.paymentType) || meta.printBased.includes(t.paymentType);
  const printBased = meta.printBased.includes(t.paymentType);
  const needPrice = printBased || t.basis === 'brut';
  const approved = useMemo(() => new Set(d.statements.filter((s) => s.status === 'onaylandi').map((s) => s.periodStart)), [d.statements]);
  const next = d.periods.find((p) => !approved.has(p.periodStart) && p.periodEnd < new Date().toISOString().slice(0, 10)) ?? d.periods[d.periods.length - 1];
  const [from, setFrom] = useState(next?.periodStart.slice(0, 7) ?? '');
  const [to, setTo] = useState(next?.periodEnd.slice(0, 7) ?? '');
  const [prints, setPrints] = useState<Record<string, number | null>>({});
  const [prices, setPrices] = useState<Record<string, number | null>>(() =>
    Object.fromEntries(t.books.filter((b) => b.stockCode && b.listPrice != null).map((b) => [b.stockCode as string, b.listPrice ?? null])),
  );
  const [fxRate, setFxRate] = useState<number | null>(null);
  const [note, setNote] = useState('');
  const [calc, setCalc] = useState<Calc | null>(null);
  const input = () => ({ periodStart: monthStart(from), periodEnd: monthEnd(to), prints, listPrices: prices, fxRate });
  const preview = useMutation({ mutationFn: () => contractApi.preview(d.key, input()), onSuccess: setCalc });
  const save = useMutation({
    mutationFn: () => contractApi.statementSave(d.key, { ...input(), note }),
    onSuccess: () => {
      toast.success('Hakediş taslağı kaydedildi.');
      setCalc(null);
      setNote('');
      qc.invalidateQueries({ queryKey: ['contracts'] });
    },
  });
  const books = t.books.filter((b) => b.stockCode);

  if (!royalty)
    return (
      <Panel>
        <p className="py-6 text-center text-[12.5px] text-canvas-muted">
          «{meta.paymentTypes[t.paymentType] ?? t.paymentType}» sözleşmede dönemsel hakediş hesaplanmaz; tutar ödeme takviminden izlenir.
        </p>
      </Panel>
    );

  return (
    <div className="space-y-3">
      {d.can.finance && d.status !== 'iptal' && (
        <Panel>
          <h3 className="text-[13px] font-extrabold">Hakediş hesapla</h3>
          <p className="mt-0.5 text-[11.5px] text-canvas-muted">
            {meta.salesBased.includes(t.paymentType) ? 'Satış Logo\'dan kitabın stok koduyla, faturalı satırlardan okunur; iadeler düşülür. ' : ''}
            {printBased ? 'Baskı adedi kaynakta tutulmuyor; dönemde basılan adedi girin. ' : ''}
            Dönem ay başında başlar, ay sonunda biter.
          </p>
          <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Field label="İlk ay">
              <input type="month" value={from} onChange={(e) => setFrom(e.target.value)} className={field} />
            </Field>
            <Field label="Son ay">
              <input type="month" value={to} onChange={(e) => setTo(e.target.value)} className={field} />
            </Field>
            {d.periods.length > 0 && (
              <Field label="Sözleşme dönemi" wide>
                <select
                  className={field}
                  value=""
                  onChange={(e) => {
                    const p = d.periods.find((x) => x.periodStart === e.target.value);
                    if (p) {
                      setFrom(p.periodStart.slice(0, 7));
                      setTo(p.periodEnd.slice(0, 7));
                    }
                  }}
                >
                  <option value="">Dönemden seç…</option>
                  {[...d.periods].reverse().map((p) => (
                    <option key={p.periodStart} value={p.periodStart}>
                      {day(p.periodStart)} – {day(p.periodEnd)}{approved.has(p.periodStart) ? ' · onaylı' : ''}
                    </option>
                  ))}
                </select>
              </Field>
            )}
          </div>
          {t.currency !== 'TRY' && (
            <div className="mt-3 max-w-xs">
              <Field label={`Kur (1 ${meta.currencies[t.currency] ?? t.currency} = ? TL)`} hint="Boş bırakılırsa dönem sonundaki TCMB döviz alış kuru kullanılır.">
                <NumInput value={fxRate} onChange={setFxRate} suffix="₺" />
              </Field>
            </div>
          )}
          {(needPrice || printBased) && books.length > 0 && (
            <ul className="mt-3 space-y-2">
              {books.map((b) => (
                <li key={b.stockCode} className="grid gap-2 rounded-xl border border-slate-100 bg-white p-2 sm:grid-cols-[minmax(0,1fr)_160px_160px]">
                  <div className="min-w-0 self-center text-[12.5px] font-semibold">
                    {b.title} <span className="font-mono text-[11px] font-normal text-canvas-muted">{b.stockCode}</span>
                  </div>
                  {printBased ? <NumInput value={prints[b.stockCode!] ?? null} onChange={(v) => setPrints({ ...prints, [b.stockCode!]: v })} placeholder="Basılan adet" suffix="ad." /> : <span className="hidden sm:block" />}
                  {needPrice && <NumInput value={prices[b.stockCode!] ?? null} onChange={(v) => setPrices({ ...prices, [b.stockCode!]: v })} placeholder="Kapak fiyatı" suffix="₺" />}
                </li>
              ))}
            </ul>
          )}
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <button type="button" className={btnGhost} disabled={!from || !to || preview.isPending} onClick={() => preview.mutate()}>
              {preview.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Calculator aria-hidden className="h-4 w-4" />}
              {preview.isPending ? 'Logo okunuyor…' : 'Hesapla'}
            </button>
            {preview.isPending && <span className="text-[11.5px] text-canvas-muted">Uzun dönemlerde bir iki dakika sürebilir.</span>}
          </div>
          {preview.error && <div className="mt-3"><Note tone="err">{errMsg(preview.error)}</Note></div>}
          {calc && (
            <div className="mt-3 space-y-3">
              <CalcView c={calc} />
              <Field label="Not (isteğe bağlı)">
                <input value={note} onChange={(e) => setNote(e.target.value)} className={field} />
              </Field>
              <div className="flex justify-end">
                <button type="button" className={btnPrimary} disabled={save.isPending} onClick={() => save.mutate()}>
                  {save.isPending && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}
                  Taslak olarak kaydet
                </button>
              </div>
              {save.error && <Note tone="err">{errMsg(save.error)}</Note>}
            </div>
          )}
        </Panel>
      )}
      <Panel>
        <h3 className="mb-2 text-[13px] font-extrabold">Hakedişler</h3>
        {!d.statements.length && <p className="py-4 text-center text-[12.5px] text-canvas-muted">Kayıtlı hakediş yok.</p>}
        <ul className="space-y-2">
          {d.statements.map((s) => (
            <StatementCard key={s.id} s={s} canFinance={d.can.finance} />
          ))}
        </ul>
      </Panel>
    </div>
  );
}
