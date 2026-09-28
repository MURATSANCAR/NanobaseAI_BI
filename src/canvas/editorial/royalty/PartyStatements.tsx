import { useEffect, useState } from 'react';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Download, FileArchive, Loader2, Send, Undo2 } from 'lucide-react';
import { toast } from 'sonner';
import { Note, Pill, btnGhost, btnPrimary, field } from '../../admin/ui';
import { Kpi, KpiRow, Pager, Panel, useDebounced } from '../kit';
import { Field, Sheet, day, errMsg, money, num, stamp } from '../contracts/ui';
import { download, royaltyApi, runPath, type Caps, type Party, type Run } from './api';

/** Hak sahipleri: onaylı koşudan yazar başına birleşik beyanname. Gönderimi insan kendi e-postasıyla yapar; burada
 *  «gönderildi» kaydı tutulur (ilk sürümde sistemden dış gönderim yok). */

export function PartyStatements({ run, can }: { run: Run; can: Caps }) {
  const qc = useQueryClient();
  const [q, setQ] = useState('');
  const [status, setStatus] = useState('');
  const [page, setPage] = useState(0);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [sending, setSending] = useState<Party[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const dq = useDebounced(q, 300);
  useEffect(() => setPage(0), [dq, status, run.id]);
  const list = useQuery({
    queryKey: ['royalty', 'parties', run.id, run.updatedAt, dq, status, page],
    queryFn: () => royaltyApi.parties(run.id, { q: dq, status, page }),
    placeholderData: keepPreviousData,
    enabled: run.status === 'onayli',
  });
  const undo = useMutation({
    mutationFn: (key: string) => royaltyApi.markSent(run.id, { keys: [key], undo: true }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['royalty', 'parties'] }),
    onError: (e) => toast.error(errMsg(e) ?? 'Kaydedilemedi.'),
  });
  if (run.status !== 'onayli') {
    return <Panel><p className="py-8 text-center text-[12.5px] text-canvas-muted">Beyannameler koşu onaylanınca hazırlanır.</p></Panel>;
  }
  const d = list.data;
  const get = async (key: string, path: string) => {
    setBusy(key);
    try {
      await download(path);
    } catch (e) {
      toast.error(errMsg(e) ?? 'Dosya indirilemedi.');
    } finally {
      setBusy(null);
    }
  };
  const toggle = (k: string) => setPicked((s) => {
    const n = new Set(s);
    if (n.has(k)) n.delete(k);
    else n.add(k);
    return n;
  });
  const pickedItems = (d?.items ?? []).filter((p) => picked.has(p.key));
  return (
    <>
      {d && (
        <KpiRow>
          <Kpi label="Hak sahibi" value={num(d.all, 0)} help="Onaylı sözleşmelerin tarafları" />
          <Kpi label="Gönderildi" value={num(d.sent, 0)} help={d.all ? `%${num((d.sent / d.all) * 100, 0)} tamamlandı` : '—'} />
          <Kpi label="Bekleyen" value={num(d.all - d.sent, 0)} help="Beyannamesi henüz gönderilmedi" />
        </KpiRow>
      )}
      <Panel>
        <div className="flex flex-wrap items-center gap-2">
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Hak sahibi ara" aria-label="Hak sahibi ara" className={`${field} sm:max-w-xs`} />
          <select aria-label="Gönderim durumu" value={status} onChange={(e) => setStatus(e.target.value)} className={`${field} sm:w-auto`}>
            <option value="">Hepsi</option>
            <option value="hazir">Gönderilmedi</option>
            <option value="gonderildi">Gönderildi</option>
          </select>
          {can.notify && (
            <div className="ml-auto flex flex-wrap gap-1.5">
              <button type="button" className={btnGhost} disabled={busy === 'zip'} onClick={() => get('zip', `${runPath(run.id)}/statements.zip`)}>
                {busy === 'zip' ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <FileArchive aria-hidden className="h-4 w-4" />}
                Bütün beyannameler
              </button>
              <button type="button" className={btnPrimary} disabled={!pickedItems.length} onClick={() => setSending(pickedItems)}>
                <Send aria-hidden className="h-4 w-4" />
                Gönderildi işaretle{pickedItems.length ? ` (${pickedItems.length})` : ''}
              </button>
            </div>
          )}
        </div>
        {!can.notify && <div className="mt-2"><Note tone="info">Beyanname indirme ve e-posta adresi «Telif beyannamesi» yetkisiyle açılır.</Note></div>}
        {list.error && <div className="mt-2"><Note tone="err">{errMsg(list.error)}</Note></div>}
        {list.isLoading && <p className="py-10 text-center text-[12.5px] text-canvas-muted">Okunuyor…</p>}
        {d && !d.items.length && <p className="py-10 text-center text-[12.5px] text-canvas-muted">Bu süzgece uyan hak sahibi yok.</p>}
        <ul className="mt-3 space-y-2">
          {d?.items.map((p) => (
            <li key={p.key} className="rounded-2xl border border-slate-100 bg-white/80 p-3">
              <div className="flex flex-wrap items-center gap-2">
                {can.notify && (
                  <input type="checkbox" aria-label={`${p.name} seç`} checked={picked.has(p.key)} onChange={() => toggle(p.key)}
                    className="h-5 w-5 shrink-0 accent-canvas-violet" />
                )}
                <span className="min-w-0 truncate text-[13px] font-extrabold">{p.name}</span>
                <Pill tone={p.status === 'gonderildi' ? 'ok' : 'warn'}>{p.status === 'gonderildi' ? 'Gönderildi' : 'Gönderilmedi'}</Pill>
                <span className="text-[11.5px] text-canvas-muted">{p.contracts} sözleşme{p.email ? ` · ${p.email}` : p.hasEmail ? '' : ' · e-posta yok'}</span>
                {can.notify && (
                  <button type="button" className={`${btnGhost} ml-auto`} disabled={busy === p.key}
                    onClick={() => get(p.key, `${runPath(run.id)}/parties/${encodeURIComponent(p.key)}/statement.docx`)}>
                    {busy === p.key ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Download aria-hidden className="h-4 w-4" />}
                    Beyanname
                  </button>
                )}
              </div>
              <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-[12px]">
                {Object.entries(p.totals).map(([cur, t]) => (
                  <span key={cur}>Ödenecek <b className="font-mono tabular-nums">{money(t.net, cur)}</b> <span className="text-canvas-muted">(brüt {money(t.gross, cur)}, avans {money(t.advance, cur)}, stopaj {money(t.withholding, cur)})</span></span>
                ))}
              </div>
              {p.status === 'gonderildi' && (
                <div className="mt-1 flex flex-wrap items-center gap-2 text-[11.5px] text-canvas-muted">
                  {stamp(p.sentAt)} · {p.sentBy} · {p.channel === 'eposta' ? 'e-posta' : p.channel}{p.note ? ` · ${p.note}` : ''}
                  {can.notify && (
                    <button type="button" className="inline-flex min-h-11 items-center gap-1 font-bold text-canvas-violet hover:underline sm:min-h-0" onClick={() => undo.mutate(p.key)}>
                      <Undo2 aria-hidden className="h-3.5 w-3.5" /> Geri al
                    </button>
                  )}
                </div>
              )}
            </li>
          ))}
        </ul>
        {d && d.total > d.pageSize && (
          <Pager page={page} pageSize={d.pageSize} total={d.total} shown={d.items.length} loading={list.isLoading} fetching={list.isFetching} onPage={setPage} />
        )}
      </Panel>
      {sending && <SentSheet run={run} parties={sending} onClose={() => { setSending(null); setPicked(new Set()); }} />}
    </>
  );
}

function SentSheet({ run, parties, onClose }: { run: Run; parties: Party[]; onClose: () => void }) {
  const qc = useQueryClient();
  const [channel, setChannel] = useState('eposta');
  const [note, setNote] = useState('');
  const save = useMutation({
    mutationFn: () => royaltyApi.markSent(run.id, { keys: parties.map((p) => p.key), channel, note }),
    onSuccess: (r) => {
      toast.success(`${r.updated} beyanname gönderildi olarak işaretlendi.`);
      qc.invalidateQueries({ queryKey: ['royalty', 'parties'] });
      onClose();
    },
    onError: (e) => toast.error(errMsg(e) ?? 'Kaydedilemedi.'),
  });
  return (
    <Sheet title="Gönderim kaydı" onClose={onClose}
      footer={
        <>
          <button type="button" className={btnGhost} onClick={onClose}>Vazgeç</button>
          <button type="button" className={btnPrimary} disabled={save.isPending} onClick={() => save.mutate()}>
            {save.isPending && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}
            Kaydet
          </button>
        </>
      }>
      <div className="space-y-3">
        <Note tone="info">Portal yazara e-posta göndermez. Beyannameyi kendi e-postanızla gönderdikten sonra burada işaretleyin.</Note>
        <p className="text-[12.5px]">{parties.map((p) => p.name).join(', ')} · {run.no} ({day(run.periodStart)} – {day(run.periodEnd)})</p>
        <Field label="Kanal">
          <select value={channel} onChange={(e) => setChannel(e.target.value)} className={field}>
            <option value="eposta">E-posta</option>
            <option value="posta">Posta</option>
            <option value="elden">Elden</option>
          </select>
        </Field>
        <Field label="Not">
          <input value={note} onChange={(e) => setNote(e.target.value)} className={field} />
        </Field>
      </div>
    </Sheet>
  );
}

/** Ödeme listesi (muhasebe): hak sahibi × sözleşme; CSV ve stopaj özeti. Bankaya ve Logo'ya gönderim yok. */
export function PaymentList({ run, can }: { run: Run; can: Caps }) {
  const [busy, setBusy] = useState<string | null>(null);
  const q = useQuery({ queryKey: ['royalty', 'payments', run.id, run.updatedAt], queryFn: () => royaltyApi.payments(run.id), enabled: run.status === 'onayli' && can.payments });
  if (run.status !== 'onayli') {
    return <Panel><p className="py-8 text-center text-[12.5px] text-canvas-muted">Ödeme listesi koşu onaylanınca hazırlanır.</p></Panel>;
  }
  if (!can.payments) return <Panel><Note tone="info">Ödeme listesi «Telif ödeme listesi» yetkisiyle açılır (muhasebe).</Note></Panel>;
  const get = async (name: string) => {
    setBusy(name);
    try {
      await download(`${runPath(run.id)}/${name}`);
    } catch (e) {
      toast.error(errMsg(e) ?? 'Dosya indirilemedi.');
    } finally {
      setBusy(null);
    }
  };
  const rows = (q.data?.items ?? []).filter((r) => r.net > 0);
  return (
    <>
      {q.data && (
        <KpiRow>
          {Object.entries(q.data.totals).map(([cur, t]) => (
            <Kpi key={cur} label={`Ödenecek (${cur})`} value={money(t.net, cur)} help={`${t.payees} ödeme · stopaj ${money(t.withholding, cur)}`} />
          ))}
        </KpiRow>
      )}
      <Panel>
        <div className="flex flex-wrap items-center gap-2">
          <p className="min-w-0 flex-1 text-[12px] text-canvas-muted">Ödeme Logo'da yapılır; ödendi bilgisi sözleşmenin ödeme takviminden girilir. IBAN portalda tutulmaz, dosyada muhasebe doldurur.</p>
          {can.export && (
            <>
              <button type="button" className={btnGhost} disabled={busy === 'payments.csv'} onClick={() => get('payments.csv')}>
                {busy === 'payments.csv' ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Download aria-hidden className="h-4 w-4" />}
                Ödeme listesi
              </button>
              <button type="button" className={btnGhost} disabled={busy === 'withholding.csv'} onClick={() => get('withholding.csv')}>
                {busy === 'withholding.csv' ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Download aria-hidden className="h-4 w-4" />}
                Stopaj özeti
              </button>
            </>
          )}
        </div>
        {q.error && <div className="mt-2"><Note tone="err">{errMsg(q.error)}</Note></div>}
        {q.isLoading && <p className="py-10 text-center text-[12.5px] text-canvas-muted">Okunuyor…</p>}
        {q.data && (
          <div className="mt-3 overflow-x-auto rounded-2xl border border-slate-100 bg-white/80">
            <table className="w-full min-w-[720px] text-[12px]">
              <thead>
                <tr className="text-left text-[11px] font-bold uppercase tracking-wide text-canvas-muted">
                  <th className="px-3 py-2">Hak sahibi</th><th className="px-3 py-2">Sözleşme</th>
                  <th className="px-3 py-2 text-right">Brüt</th><th className="px-3 py-2 text-right">Avans</th>
                  <th className="px-3 py-2 text-right">Stopaj</th><th className="px-3 py-2 text-right">Net</th><th className="px-3 py-2">Vade</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={i} className="border-t border-slate-100">
                    <td className="px-3 py-2 font-semibold">{r.party}</td>
                    <td className="px-3 py-2">{r.contractNo}<span className="block text-[11px] text-canvas-muted">{r.contract}</span></td>
                    <td className="px-3 py-2 text-right font-mono tabular-nums">{money(r.gross, r.currency)}</td>
                    <td className="px-3 py-2 text-right font-mono tabular-nums">{money(r.advance, r.currency)}</td>
                    <td className="px-3 py-2 text-right font-mono tabular-nums">{money(r.withholding, r.currency)}</td>
                    <td className="px-3 py-2 text-right font-mono font-bold tabular-nums">{money(r.net, r.currency)}</td>
                    <td className="px-3 py-2">{day(r.dueOn)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {q.data && <p className="mt-2 text-[11.5px] text-canvas-muted">{num(rows.length, 0)} ödeme satırı; ödenecek tutarı olmayanlar (avans mahsubu, devir) listede yok, beyannamede görünür.</p>}
      </Panel>
    </>
  );
}
