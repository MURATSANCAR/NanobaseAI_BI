import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ExternalLink, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { Note, Pill, btnGhost, btnPrimary, field } from '../../admin/ui';
import { Pager, Panel, useDebounced } from '../kit';
import { Field, Row, Sheet, day, errMsg, money, num } from '../contracts/ui';
import { lineTone, royaltyApi, type Meta, type Run } from './api';
import SqlInfo, { InfoLabel } from '../../components/SqlInfo';
import { EmptyHint, Explain, ExplainLabel } from '../../components/Explain';
import { TERM } from '../contracts/glossary';

/** Koşunun satırları: süzgeç (durum, istisna nedeni, arama), sayfalı liste ve satırın hesabı. */

export function RunLines({ run, meta, status, code, title }: { run: Run; meta: Meta; status?: string; code?: string; title?: string }) {
  const [q, setQ] = useState('');
  const [st, setSt] = useState(status ?? '');
  const [cd, setCd] = useState(code ?? '');
  const [page, setPage] = useState(0);
  const [open, setOpen] = useState<number | null>(null);
  const dq = useDebounced(q, 300);
  useEffect(() => setPage(0), [dq, st, cd, run.id]);
  useEffect(() => setCd(code ?? ''), [code]);
  const lines = useQuery({
    queryKey: ['royalty', 'lines', run.id, run.updatedAt, st, cd, dq, page],
    queryFn: () => royaltyApi.lines(run.id, { status: st, code: cd, q: dq, page }),
    placeholderData: keepPreviousData,
    enabled: run.status !== 'taslak',
  });
  const reasons = Object.entries(run.summary.reasons ?? {});
  const d = lines.data;
  return (
    <Panel>
      {title && (
        <h3 className="mb-2 flex items-center gap-1 text-[13px] font-extrabold">
          {title}
          <Explain label="Satır durumları">
            Her satır bir sözleşmedir. <b>Hesaplandı</b>: onaya hazır. <b>İstisna</b>: turuncu etiket kontrol edip gerekçesiyle kabul edilebilir, kırmızı etiket sözleşme
            düzeltilip yeniden hesaplatılmalı. <b>Hariç</b>: bu koşuda ödenmez. Satıra dokununca hesabı açılır.
          </Explain>
        </h3>
      )}
      <div className="grid gap-2 sm:grid-cols-3">
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Sözleşme, kitap ya da hak sahibi ara" aria-label="Ara" className={field} />
        {status === undefined && (
          <select aria-label="Durum" value={st} onChange={(e) => setSt(e.target.value)} className={field}>
            <option value="">Bütün satırlar</option>
            {Object.entries(meta.lineStatuses).map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </select>
        )}
        <select aria-label="İstisna nedeni" value={cd} onChange={(e) => setCd(e.target.value)} className={field}>
          <option value="">Bütün nedenler</option>
          {(reasons.length ? reasons.map(([k, n]) => [k, `${meta.exceptions[k]?.label ?? k} (${num(n, 0)})`]) : Object.entries(meta.exceptions).map(([k, v]) => [k, v.label])).map(([k, v]) => (
            <option key={k} value={k}>{v}</option>
          ))}
        </select>
      </div>
      {d && (
        <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11.5px] font-semibold text-canvas-muted">
          <InfoLabel k={d.kaynaklar} alan="items[]" label="Koşu satırları (durum, net)">Satırlar</InfoLabel>
          {reasons.length > 0 && <InfoLabel k={run.kaynaklar} alan="summary.reasons" label="İstisna nedeni seçeneğindeki sayılar">Neden sayıları</InfoLabel>}
        </div>
      )}
      {lines.error && <div className="mt-2"><Note tone="err">{errMsg(lines.error)}</Note></div>}
      {lines.isLoading && <p className="py-10 text-center text-[12.5px] text-canvas-muted">Okunuyor…</p>}
      {d && !d.items.length && (
        <div className="mt-3">
          {status === 'istisna' && !cd && !dq ? (
            <EmptyHint title="Bu koşuda istisna yok" why="Bütün sözleşmeler sorunsuz hesaplandı ya da hariç tutuldu; koşu onaya gönderilebilir." />
          ) : (
            <EmptyHint title="Bu süzgece uyan satır yok" why="Aramayı temizleyin ya da durum ve neden süzgeçlerini «Bütün» yapın." />
          )}
        </div>
      )}
      <ul className="mt-3 space-y-2">
        {d?.items.map((ln) => (
          <li key={ln.id}>
            <button type="button" onClick={() => setOpen(ln.id)}
              className="w-full rounded-2xl border border-slate-100 bg-white/80 p-3 text-left transition-transform duration-150 ease-out hover:bg-white active:scale-[0.98]">
              <div className="flex flex-wrap items-center gap-1.5">
                <Pill tone={lineTone(ln.status)}>{ln.statusLabel}</Pill>
                <span className="min-w-0 truncate text-[12.5px] font-extrabold">{ln.no}</span>
                {ln.statementId && <Pill tone="ok">Hakediş oluştu</Pill>}
                {ln.approvalError && <Pill tone="err">Onay hatası</Pill>}
                {ln.decision.kabul && <Pill tone="violet">Kabul edildi</Pill>}
                <span className="ml-auto font-mono text-[12.5px] font-bold tabular-nums">{ln.net != null ? money(ln.net, ln.currency) : '—'}</span>
              </div>
              <div className="mt-1 truncate text-[12px] text-canvas-muted">{ln.title} · {ln.parties.map((p) => p.name).join(', ') || 'taraf yok'}</div>
              {ln.status === 'istisna' && (
                <div className="mt-1 flex flex-wrap gap-1">
                  {ln.exceptions.map((e) => (
                    <Pill key={e.code} tone={e.acceptable ? 'warn' : 'err'}>{e.label}</Pill>
                  ))}
                </div>
              )}
              {ln.status === 'haric' && (
                <div className="mt-1 text-[11.5px] text-canvas-muted">
                  {ln.decision.haric ? `Hariç: ${ln.decision.haric.reason} (${ln.decision.haric.by})` : ln.decision.autoReason}
                </div>
              )}
            </button>
          </li>
        ))}
      </ul>
      {d && d.total > d.pageSize && (
        <>
          <div className="mt-3 text-[11.5px] font-semibold text-canvas-muted">
            <InfoLabel k={d.kaynaklar} alan="total" label="Süzgece uyan satır sayısı">Toplam</InfoLabel>
          </div>
          <Pager page={page} pageSize={d.pageSize} total={d.total} shown={d.items.length} loading={lines.isLoading} fetching={lines.isFetching} onPage={setPage} />
        </>
      )}
      {d && d.total <= d.pageSize && d.total > 0 && (
        <p className="mt-2 inline-flex items-center text-[11.5px] text-canvas-muted">
          {num(d.total, 0)} satır<SqlInfo k={d.kaynaklar} alan="total" label="Süzgece uyan satır sayısı" className="ml-0.5" />
        </p>
      )}
      {open != null && <LineSheet run={run} lineId={open} onClose={() => setOpen(null)} />}
    </Panel>
  );
}

function LineSheet({ run, lineId, onClose }: { run: Run; lineId: number; onClose: () => void }) {
  const qc = useQueryClient();
  const [reason, setReason] = useState('');
  const q = useQuery({ queryKey: ['royalty', 'line', run.id, lineId, run.updatedAt], queryFn: () => royaltyApi.line(run.id, lineId) });
  const act = useMutation({
    mutationFn: (action: 'haric' | 'geri-al' | 'kabul') => royaltyApi.decide(run.id, lineId, { action, reason }),
    onSuccess: () => {
      toast.success('Satır güncellendi.');
      setReason('');
      qc.invalidateQueries({ queryKey: ['royalty'] });
    },
    onError: (e) => toast.error(errMsg(e) ?? 'Kaydedilemedi.'),
  });
  const ln = q.data;
  const c = ln?.calc;
  const editable = run.status === 'hesaplandi' || (run.status === 'onayda' && !!ln?.approvalError && !ln.statementId);
  const acceptable = !!ln && ln.status === 'istisna' && ln.exceptions.length > 0 && ln.exceptions.every((e) => e.acceptable) && !!c;
  const undoable = !!ln && (!!ln.decision.haric || (!!ln.decision.auto && !ln.decision.autoUndone) || !!ln.decision.kabul);
  const contractKey = ln?.contractId ?? ln?.crmId ?? ln?.contractKey;
  return (
    <Sheet title={ln ? `${ln.no} — ${ln.title}` : 'Satır'} onClose={onClose} wide
      footer={ln && editable && run.status === 'hesaplandi' ? (
        <>
          {undoable && <button type="button" className={btnGhost} disabled={act.isPending} onClick={() => act.mutate('geri-al')}>Kararı geri al</button>}
          {ln.status !== 'haric' && <button type="button" className={btnGhost} disabled={act.isPending || !reason.trim()} onClick={() => act.mutate('haric')}>Hariç tut</button>}
          {acceptable && (
            <button type="button" className={btnPrimary} disabled={act.isPending || !reason.trim()} onClick={() => act.mutate('kabul')}>
              {act.isPending && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}
              İstisnayı kabul et
            </button>
          )}
        </>
      ) : ln && editable ? (
        <button type="button" className={btnGhost} disabled={act.isPending || !reason.trim()} onClick={() => act.mutate('haric')}>Hariç tut</button>
      ) : undefined}
    >
      {q.isLoading && <p className="py-8 text-center text-[12.5px] text-canvas-muted">Okunuyor…</p>}
      {q.error && <Note tone="err">{errMsg(q.error)}</Note>}
      {ln && (
        <div className="space-y-3">
          {contractKey && (
            <Link to={`/telif-sozlesme/${contractKey}?sekme=hakedis`} className="inline-flex min-h-11 items-center gap-1 text-[12px] font-bold text-canvas-violet hover:underline sm:min-h-0">
              <ExternalLink aria-hidden className="h-3.5 w-3.5" />
              Sözleşme sayfasını aç (düzeltmeyi orada yapın)
            </Link>
          )}
          {ln.approvalError && <Note tone="err">Onay: {ln.approvalError}</Note>}
          {ln.exceptions.length > 0 && (
            <ul className="space-y-1.5">
              {ln.exceptions.map((e) => (
                <li key={e.code}>
                  <Note tone={e.acceptable ? 'warn' : 'err'}>
                    <span className="font-extrabold">{e.label}</span>{e.detail ? ` — ${e.detail}` : ''}
                    <span className="block font-normal">{e.fix}</span>
                  </Note>
                </li>
              ))}
            </ul>
          )}
          {ln.decision.haric && <Note tone="info">Hariç tutuldu: {ln.decision.haric.reason} — {ln.decision.haric.by}</Note>}
          {ln.decision.auto && !ln.decision.autoUndone && !ln.decision.haric && <Note tone="info">Kendiliğinden hariç: {ln.decision.autoReason}</Note>}
          {ln.decision.kabul && <Note tone="info">Kabul edildi: {ln.decision.kabul.reason} — {ln.decision.kabul.by}</Note>}
          {c ? (
            <>
              <div className="flex items-center gap-1 text-[11px] font-bold uppercase tracking-wide text-canvas-muted">
                Satırın hesabı <SqlInfo k={ln.kaynaklar} alan="calc" label="Satırın hesabı (adet, matrah, telif, avans, stopaj, net)" />
              </div>
              <dl>
                <Row label="Dönem">{day(c.periodStart)} – {day(c.periodEnd)}</Row>
                <Row label="Net adet">{num(c.quantity, 0)}</Row>
                <Row label="Matrah" explain="Telif oranının uygulandığı tutar: net satış tutarı ya da adet × kapak fiyatı; hesaplama iskontosu varsa düşülmüş olarak.">{money(c.base)}</Row>
                <Row label="Brüt telif">{money(c.gross, c.currency)}{c.fx ? ` (kur ${num(c.fx.rate, 4)}, ${day(c.fx.on)}, ${c.fx.source})` : ''}</Row>
                {c.carryIn ? <Row label="Önceki dönemden devir">{money(c.carryIn, c.currency)}</Row> : null}
                {c.advance != null && <Row label="Avans">{money(c.advance, c.contractCurrency)} · önceden mahsup {money(c.advanceUsedBefore, c.contractCurrency)}</Row>}
                {c.advanceBasis && <Row label="Avans açılışı">{money(c.advanceBasis.opening, c.contractCurrency)} ({day(c.advanceBasis.openingOn)}{c.advanceBasis.openingBy ? `, ${c.advanceBasis.openingBy}` : ''})</Row>}
                <Row label="Avans mahsubu" explain={TERM.mahsup}>{money(c.advanceOffset, c.currency)}</Row>
                {c.advanceRemaining != null && <Row label="Kalan avans">{money(c.advanceRemaining, c.contractCurrency)}</Row>}
                <Row label="Stopaj" explain={TERM.stopaj}>{c.withholdingPct ? `%${num(c.withholdingPct)} · ` : ''}{money(c.withholding, c.currency)}</Row>
                <Row label="Ödenecek net">{money(c.net, c.currency)}</Row>
                {c.carryOut ? <Row label="Sonraki döneme devir" explain={TERM.devreden}>{money(c.carryOut, c.currency)}</Row> : null}
              </dl>
              <div className="overflow-x-auto rounded-2xl border border-slate-100">
                <table className="w-full min-w-[560px] text-[12px]">
                  <thead>
                    <tr className="text-left text-[11px] font-bold uppercase tracking-wide text-canvas-muted">
                      <th className="px-2 py-1.5">Kitap</th><th className="px-2 py-1.5">Hak sahibi</th>
                      <th className="px-2 py-1.5 text-right">Adet</th><th className="px-2 py-1.5 text-right"><ExplainLabel label="İade">Dönemde geri gelen adet; telif, iadeler düşülmüş net adetten hesaplanır.</ExplainLabel></th>
                      <th className="px-2 py-1.5 text-right">Matrah</th><th className="px-2 py-1.5 text-right">Oran</th>
                      <th className="px-2 py-1.5 text-right"><InfoLabel k={ln.kaynaklar} alan="calc" label="Kitap × hak sahibi satırları">Telif</InfoLabel></th>
                    </tr>
                  </thead>
                  <tbody>
                    {c.lines.map((x, i) => (
                      <tr key={i} className="border-t border-slate-100">
                        <td className="px-2 py-1.5">{x.book}<span className="block text-[11px] text-canvas-muted">{x.stockCode}</span></td>
                        <td className="px-2 py-1.5">{x.party} <span className="text-canvas-muted">%{num(x.share)}</span></td>
                        <td className="px-2 py-1.5 text-right font-mono tabular-nums">{num(x.quantity, 0)}</td>
                        <td className="px-2 py-1.5 text-right font-mono tabular-nums">{num(x.returns, 0)}</td>
                        <td className="px-2 py-1.5 text-right font-mono tabular-nums">{money(x.base)}</td>
                        <td className="px-2 py-1.5 text-right font-mono tabular-nums">
                          %{num(x.rate)}
                          {x.tiers && <span className="block text-[11px] text-canvas-muted">{x.tiers.map((t) => `${num(t.quantity, 0)}×%${num(t.rate)}`).join(' + ')}</span>}
                        </td>
                        <td className="px-2 py-1.5 text-right font-mono tabular-nums">{money(x.royalty)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {c.warnings.length > 0 && (
                <ul className="space-y-1">
                  {c.warnings.map((w) => (
                    <li key={w}><Note tone="info">{w}</Note></li>
                  ))}
                </ul>
              )}
            </>
          ) : (
            <Note tone="warn">Bu satırın hesabı yapılamadı; yukarıdaki nedeni sözleşme sayfasında düzeltip koşuyu yeniden hesaplatın.</Note>
          )}
          {editable && (
            <Field label="Gerekçe" hint="«Hariç tut» ve «İstisnayı kabul et» için gerekçe zorunludur; koşuda kimin yaptığıyla birlikte görünür.">
              <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={2} className={field} placeholder="ör. Yazarla dönem sonu ayrıca anlaşıldı" />
            </Field>
          )}
        </div>
      )}
    </Sheet>
  );
}
