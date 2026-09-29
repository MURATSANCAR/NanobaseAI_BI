import { useState } from 'react';
import { Link } from 'react-router-dom';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ExternalLink, Loader2, Sparkles } from 'lucide-react';
import { toast } from 'sonner';
import { Note, Pill, btnGhost, btnPrimary, field } from '../../admin/ui';
import { Kpi, KpiRow, Panel, useDebounced } from '../kit';
import { Field, Row, Sheet, day, errMsg, money, num, stamp } from '../contracts/ui';
import { royaltyApi, type Meta, type Renewal } from './api';
import SqlInfo, { InfoLabel } from '../../components/SqlInfo';
import type { Kaynaklar } from '../../components/sqlInfo';
import { EmptyHint } from '../../components/Explain';

const STEP = 50;
const decisionTone = (d: string): 'ok' | 'warn' | 'err' | 'muted' | 'violet' =>
  d === 'yenile' ? 'ok' : d === 'birak' ? 'muted' : d === 'muzakere' ? 'violet' : 'warn';

/** Yenilemeler: bitişi yaklaşan (açılışta 90 gün) ya da geçmiş, süreli ve etkin CRM sözleşmeleri; karar portalda tutulur. */
export function Renewals({ meta }: { meta: Meta }) {
  const [days, setDays] = useState(90);
  const [overdue, setOverdue] = useState(false);
  const [decision, setDecision] = useState('');
  const [q, setQ] = useState('');
  const [shown, setShown] = useState(STEP);
  const [open, setOpen] = useState<Renewal | null>(null);
  const dq = useDebounced(q, 300);
  const list = useQuery({
    queryKey: ['royalty', 'renewals', days, overdue, decision, dq],
    queryFn: () => royaltyApi.renewals({ days, overdue, decision, q: dq }),
    placeholderData: keepPreviousData,
  });
  const d = list.data;
  const reset = () => setShown(STEP);
  return (
    <>
      {d && (
        <KpiRow>
          <Kpi label={overdue ? 'Bitişi geçmiş' : `${days} gün içinde biten`} value={num(d.total, 0)} help="Etkin ve süreli sözleşme (bütün türler)"
            explain={overdue ? "CRM'de etkin, süreli ve bitiş tarihi geçmiş sözleşmeler (bütün türler)." : "CRM'de etkin, süreli ve bitiş tarihi seçili gün sayısı içinde olan sözleşmeler (bütün türler)."}
            info={<SqlInfo k={d.kaynaklar} alan="total" label={overdue ? 'Bitişi geçmiş' : `${days} gün içinde biten`} />} />
          <Kpi label="Karar bekliyor" value={num(d.counts.bekliyor ?? 0, 0)} help="Yenile / bırak / müzakere girilmemiş"
            explain="Yenile, bırak ya da müzakere kararı henüz girilmemiş sözleşmeler. Karta dokununca liste bunlara süzülür."
            active={decision === 'bekliyor'} onClick={() => { setDecision((v) => (v === 'bekliyor' ? '' : 'bekliyor')); reset(); }}
            info={<SqlInfo k={d.kaynaklar} alan="counts" label="Karar bekliyor" />} />
          <Kpi label="Yenilenecek" value={num(d.counts.yenile ?? 0, 0)} help="Kararı verilmiş"
            explain="Kararı «yenile» girilmiş sözleşmeler. Portal CRM'e yazmaz; yenilenen sözleşme CRM'de elle güncellenir."  info={<SqlInfo k={d.kaynaklar} alan="counts" label="Yenilenecek" />} />
          <Kpi label="Müzakere" value={num(d.counts.muzakere ?? 0, 0)} help="Yeniden müzakere edilecek"
            explain="Şartları hak sahibiyle yeniden görüşülecek sözleşmeler."  info={<SqlInfo k={d.kaynaklar} alan="counts" label="Müzakere" />} />
        </KpiRow>
      )}
      <Panel>
        <div className="grid gap-2 sm:grid-cols-3">
          <select aria-label="Pencere" value={overdue ? 'gecmis' : String(days)} className={field}
            onChange={(e) => { const v = e.target.value; setOverdue(v === 'gecmis'); if (v !== 'gecmis') setDays(Number(v)); reset(); }}>
            {[30, 60, 90, 180, 365].map((n) => <option key={n} value={n}>{n} gün içinde bitenler</option>)}
            <option value="gecmis">Bitişi geçmiş olanlar</option>
          </select>
          <select aria-label="Karar" value={decision} onChange={(e) => { setDecision(e.target.value); reset(); }} className={field}>
            <option value="">Bütün kararlar</option>
            {Object.entries(meta.renewalDecisions).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <input value={q} onChange={(e) => { setQ(e.target.value); reset(); }} placeholder="Sözleşme, kitap, yazar ara" aria-label="Ara" className={field} />
        </div>
        {list.error && <div className="mt-2"><Note tone="err">{errMsg(list.error)}</Note></div>}
        {list.isLoading && <p className="py-10 text-center text-[12.5px] text-canvas-muted">CRM okunuyor…</p>}
        {d && !d.items.length && (
          <div className="mt-3">
            <EmptyHint title="Bu süzgece uyan sözleşme yok" why="Süreyi genişletin (ör. 180 gün), kararı «Bütün kararlar» yapın ya da aramayı temizleyin." />
          </div>
        )}
        {d && d.items.length > 0 && (
          <div className="mt-3 text-[11.5px] font-semibold text-canvas-muted">
            <InfoLabel k={d.kaynaklar} alan="items[]" label="Sözleşmeler (bitiş, kalan gün, karar)">{`${num(d.items.length, 0)} sözleşme`}</InfoLabel>
          </div>
        )}
        <ul className="mt-3 space-y-2">
          {d?.items.slice(0, shown).map((r) => (
            <li key={r.contractKey}>
              <button type="button" onClick={() => setOpen(r)}
                className="w-full rounded-2xl border border-slate-100 bg-white/80 p-3 text-left transition-transform duration-150 ease-out hover:bg-white active:scale-[0.98]">
                <div className="flex flex-wrap items-center gap-1.5">
                  <Pill tone={decisionTone(r.decision)}>{r.decisionLabel}</Pill>
                  <span className="min-w-0 truncate text-[12.5px] font-extrabold">{r.no}</span>
                  <span className="text-[11.5px] text-canvas-muted">{r.kind}</span>
                  {r.staleDecision && <Pill tone="muted">Eski karar (bitiş değişti)</Pill>}
                  <span className={`ml-auto text-[12px] font-bold ${r.daysLeft != null && r.daysLeft < 0 ? 'text-red-700' : ''}`}>
                    {day(r.end)}{r.daysLeft != null ? ` · ${r.daysLeft < 0 ? `${num(-r.daysLeft, 0)} gün geçti` : `${num(r.daysLeft, 0)} gün`}` : ''}
                  </span>
                </div>
                <div className="mt-1 truncate text-[12px] text-canvas-muted">{r.book || '—'} · {[r.author, r.translator].filter(Boolean).join(', ') || 'taraf yok'}</div>
              </button>
            </li>
          ))}
        </ul>
        {d && d.items.length > shown && (
          <div className="mt-3 flex items-center justify-between gap-2 text-[12px] text-canvas-muted">
            <span>{num(d.items.length, 0)} sözleşmenin {num(shown, 0)} tanesi gösteriliyor</span>
            <button type="button" className={btnGhost} onClick={() => setShown((n) => n + STEP)}>Daha fazla göster</button>
          </div>
        )}
      </Panel>
      {open && <RenewalSheet r={open} meta={meta} k={d?.kaynaklar} canDecide={!!d?.can.renewal} onClose={() => setOpen(null)} />}
    </>
  );
}

function RenewalSheet({ r, meta, k, canDecide, onClose }: { r: Renewal; meta: Meta; k?: Kaynaklar; canDecide: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const [decision, setDecision] = useState(r.decision === 'bekliyor' ? (r.suggestion?.decision ?? 'yenile') : r.decision);
  const [reason, setReason] = useState(r.reason ?? r.suggestion?.text ?? '');
  const [sug, setSug] = useState(r.suggestion);
  // Yeni öneride sorgu bilgisi önerinin cevabındadır; kayıtlı öneride listenin kaydındadır.
  const [sugK, setSugK] = useState<Kaynaklar | undefined>(undefined);
  const suggest = useMutation({
    mutationFn: () => royaltyApi.suggestRenewal(r.contractKey),
    onSuccess: (s) => {
      setSugK(s.kaynaklar);
      setSug({ ...s, at: new Date().toISOString() });
      if (!reason.trim() && s.text) setReason(s.text);
      if (r.decision === 'bekliyor' && s.decision) setDecision(s.decision);
    },
    onError: (e) => toast.error(errMsg(e) ?? 'Öneri alınamadı.'),
  });
  const save = useMutation({
    mutationFn: () => royaltyApi.decideRenewal(r.contractKey, { decision, reason, end: r.end, no: r.no }),
    onSuccess: () => {
      toast.success('Karar kaydedildi.');
      qc.invalidateQueries({ queryKey: ['royalty', 'renewals'] });
      onClose();
    },
    onError: (e) => toast.error(errMsg(e) ?? 'Kaydedilemedi.'),
  });
  return (
    <Sheet title={`${r.no ?? 'Sözleşme'} — yenileme`} onClose={onClose} wide
      footer={canDecide ? (
        <>
          <button type="button" className={btnGhost} onClick={onClose}>Vazgeç</button>
          <button type="button" className={btnPrimary} disabled={save.isPending || (decision !== 'bekliyor' && !reason.trim())} onClick={() => save.mutate()}>
            {save.isPending && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}
            Kararı kaydet
          </button>
        </>
      ) : undefined}>
      <div className="space-y-3">
        <Link to={`/telif-sozlesme/${r.contractKey}`} className="inline-flex min-h-11 items-center gap-1 text-[12px] font-bold text-canvas-violet hover:underline sm:min-h-0">
          <ExternalLink aria-hidden className="h-3.5 w-3.5" /> Sözleşme sayfasını aç
        </Link>
        <div className="flex items-center gap-1 text-[11px] font-bold uppercase tracking-wide text-canvas-muted">
          CRM sözleşme kartı <SqlInfo k={k} alan="items[]" label="Sözleşme (süre, yenilenme, imha, avans)" />
        </div>
        <dl>
          <Row label="Kitap">{r.book || '—'}{r.stockCode ? ` · ${r.stockCode}` : ''}</Row>
          <Row label="Taraflar">{[r.author, r.translator, r.illustrator].filter(Boolean).join(', ') || '—'}</Row>
          <Row label="Tür">{r.kind}{r.paymentType ? ` · ${r.paymentType}` : ''}</Row>
          <Row label="Süre">{day(r.start)} – {day(r.end)}</Row>
          {r.renewEvery != null && <Row label="Yenilenme sıklığı">{num(r.renewEvery, 0)} yıl</Row>}
          {(r.renewStart || r.renewEnd) && <Row label="Yenileme dönemi">{day(r.renewStart)} – {day(r.renewEnd)}</Row>}
          {r.unpublishedTermination && <Row label="Yayınlanmazsa fesih">{day(r.unpublishedTermination)}</Row>}
          {r.destroyMonths != null && <Row label="İmha süresi">{num(r.destroyMonths, 0)} ay</Row>}
          {r.reportPeriod != null && r.reportPeriod !== '' && <Row label="Rapor verme süresi">{String(r.reportPeriod)}</Row>}
          {r.advance ? <Row label="Avans (CRM)">{money(r.advance, r.currency)}</Row> : null}
          {r.decidedBy && <Row label="Karar">{r.decisionLabel} · {r.decidedBy}, {stamp(r.decidedAt)}</Row>}
        </dl>
        <Panel>
          <div className="flex flex-wrap items-center gap-2">
            <Sparkles aria-hidden className="h-4 w-4 text-canvas-violet" />
            <span className="text-[12.5px] font-extrabold">Zeki AI önerisi</span>
            <button type="button" className={`${btnGhost} ml-auto`} disabled={suggest.isPending} onClick={() => suggest.mutate()}>
              {suggest.isPending && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}
              {sug ? 'Yeniden öner' : 'Gerekçe önerisi al'}
            </button>
          </div>
          {sug ? (
            <div className="mt-2 space-y-1.5 text-[12.5px]">
              {sug.decision && (
                <div className="flex flex-wrap items-center">
                  Öneri:&nbsp;<b>{meta.renewalDecisions[sug.decision] ?? sug.decision}</b>{sug.probability != null ? ` (olasılık %${num(sug.probability * 100, 0)})` : ''}
                  {sugK ? <SqlInfo k={sugK} alan="probability" label="Zeki AI önerisi ve olguları" className="ml-0.5" />
                    : <SqlInfo k={k} alan="items[].suggestion" row={r.contractKey} label="Zeki AI önerisi ve olguları" className="ml-0.5" />}
                </div>
              )}
              {sug.text && <p className="leading-snug">{sug.text}</p>}
              <ul className="text-[11.5px] text-canvas-muted">
                {Object.entries(sug.inputs ?? {}).filter(([, v]) => v != null && v !== '').map(([k, v]) => <li key={k}>{k}: {String(v)}</li>)}
              </ul>
              <p className="text-[11px] text-canvas-muted">Rakamlar Logo satışından ve portal kayıtlarından; öneri karar değildir.</p>
            </div>
          ) : (
            <p className="mt-1 text-[12px] text-canvas-muted">Son 36 ay satış ve kalan avansla gerekçe taslağı yazar; kararı siz verirsiniz.</p>
          )}
        </Panel>
        {canDecide ? (
          <>
            <Field label="Karar">
              <select value={decision} onChange={(e) => setDecision(e.target.value)} className={field}>
                {Object.entries(meta.renewalDecisions).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </Field>
            <Field label="Gerekçe" hint="CRM'e yazılmaz; yenilenen sözleşme CRM'de elle güncellenir.">
              <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={3} className={field} />
            </Field>
          </>
        ) : (
          <Note tone="info">Yenileme kararı «Yenileme kararı» yetkisiyle girilir.</Note>
        )}
      </div>
    </Sheet>
  );
}
