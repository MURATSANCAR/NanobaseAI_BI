import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { Archive, Check, Pencil, RotateCcw, Undo2 } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, Pill, TableWrap, btnGhost, btnPrimary, errText, field, fmtDate, label as labelCls, td, th } from '../admin/ui';
import { Sheet } from '../editorial/assign/parts';
import { Tabs } from '../editorial/freelance/shared';
import { STATUS_TONE, num, overviewKey, pct, pricingApi, tl0, tl2, type Analysis, type AnalysisStatus, type ApproverRole, type Overview } from './api';
import { Stat } from './parts';
import SqlInfo, { InfoLabel } from '../components/SqlInfo';

type Filter = 'onayda' | 'taslak' | 'onaylandi' | 'reddedildi' | 'hepsi' | 'arsiv';

/** Kaydedilen analizler ve onay akışı. Onaya giden sonuç dondurulur; imzalar o sürüme aittir. */
export default function AnalysesPane({ ov }: { ov: Overview }) {
  const [params, setParams] = useSearchParams();
  const filter = ((params.get('durum') as Filter) || 'hepsi') as Filter;
  const open = params.get('kayit');
  const list = useQuery({
    queryKey: ['pricing', 'analyses', filter],
    queryFn: () => pricingApi.analyses({ status: filter === 'hepsi' ? '' : filter }),
    enabled: ENGINE_ENABLED,
  });
  const setOpen = (id: string | null) => setParams({ bolum: 'analizler', durum: filter, ...(id ? { kayit: id } : {}) });

  return (
    <div className="flex flex-col gap-3">
      <Tabs<Filter>
        value={filter}
        onChange={(f) => setParams({ bolum: 'analizler', durum: f })}
        items={[
          { key: 'hepsi', label: 'Güncel' },
          { key: 'onayda', label: 'Onay bekliyor', badge: ov.counts.onayda || undefined },
          { key: 'taslak', label: 'Taslak' },
          { key: 'reddedildi', label: 'Geri gönderilen' },
          { key: 'onaylandi', label: 'Onaylanan' },
          { key: 'arsiv', label: 'Arşiv' },
        ]}
      />
      {list.error && <Note tone="err">{errText(list.error, 'Liste okunamadı.')}</Note>}
      {!list.data ? (
        !list.error && <Loading />
      ) : list.data.items.length === 0 ? (
        <p className="py-10 text-center text-[12.5px] text-canvas-muted">Bu durumda analiz yok. «Kitap hesabı»ndan bir kitabın hesabını kaydedin.</p>
      ) : (
        <TableWrap>
          <thead>
            <tr>
              <th className={th}>Kitap</th>
              <th className={th}>Aşama</th>
              <th className={th}>Durum</th>
              <th className={`${th} text-right`}><InfoLabel k={list.data?.kaynaklar} alan="items[]">Adet</InfoLabel></th>
              <th className={`${th} text-right`}><InfoLabel k={list.data?.kaynaklar} alan="items[]">Kapak fiyatı</InfoLabel></th>
              <th className={`${th} text-right`}><InfoLabel k={list.data?.kaynaklar} alan="items[]">Birim maliyet</InfoLabel></th>
              <th className={`${th} text-right`}><InfoLabel k={list.data?.kaynaklar} alan="items[]">Marj</InfoLabel></th>
              <th className={th}>İmzalar</th>
              <th className={th}>Son değişiklik</th>
            </tr>
          </thead>
          <tbody>
            {list.data.items.map((a) => (
              <tr key={a.id} className="cursor-pointer border-t border-slate-100 hover:bg-slate-50" onClick={() => setOpen(a.id)}>
                <td className={td}>
                  <button type="button" className="text-left font-bold text-canvas-violet hover:underline" onClick={() => setOpen(a.id)}>
                    {a.title}
                  </button>
                  <div className="text-[11px] text-canvas-muted">{[a.stockCode, a.createdBy].filter(Boolean).join(' · ')}</div>
                </td>
                <td className={td}>{a.stage === 'kesin' ? 'Kesin' : 'Tahmini'}</td>
                <td className={td}>
                  <Pill tone={STATUS_TONE[a.status]}>{a.statusLabel}</Pill>
                </td>
                <td className={`${td} text-right tabular-nums`}>{num(a.chosenQty)}</td>
                <td className={`${td} text-right tabular-nums`}>{tl0(a.chosenPrice)}</td>
                <td className={`${td} text-right tabular-nums`}>{tl2(a.summary?.unitCost)}</td>
                <td className={`${td} text-right tabular-nums`}>{pct(a.summary?.margin)}</td>
                <td className={td}>
                  {a.required.map((r) => {
                    const s = a.approvals.find((x) => x.role === r.role);
                    return (
                      <span key={r.role} className="mr-1 inline-block">
                        <Pill tone={!s ? 'muted' : s.decision === 'onay' ? 'ok' : 'err'}>{r.label}</Pill>
                      </span>
                    );
                  })}
                </td>
                <td className={td}>{fmtDate(a.updatedAt ?? a.createdAt)}</td>
              </tr>
            ))}
          </tbody>
        </TableWrap>
      )}
      <Sheet open={!!open} onOpenChange={(o) => !o && setOpen(null)} title="Fiyat analizi">
        {open && <AnalysisDetail id={open} ov={ov} onClose={() => setOpen(null)} />}
      </Sheet>
    </div>
  );
}

function AnalysisDetail({ id, ov, onClose }: { id: string; ov: Overview; onClose: () => void }) {
  const qc = useQueryClient();
  const [, setParams] = useSearchParams();
  const q = useQuery({ queryKey: ['pricing', 'analysis', id], queryFn: () => pricingApi.analysis(id), enabled: ENGINE_ENABLED });
  const [note, setNote] = useState('');
  const done = (a: Analysis) => {
    qc.setQueryData(['pricing', 'analysis', id], a);
    qc.invalidateQueries({ queryKey: ['pricing', 'analyses'] });
    qc.invalidateQueries({ queryKey: overviewKey });
    setNote('');
  };
  const decide = useMutation({
    mutationFn: (v: { role: ApproverRole; decision: 'onay' | 'ret' }) => pricingApi.decide(id, { ...v, note, version: q.data!.version }),
    onSuccess: done,
  });
  const act = useMutation({
    mutationFn: (k: 'withdraw' | 'archive') => (k === 'withdraw' ? pricingApi.withdraw(id) : pricingApi.archive(id)),
    onSuccess: done,
  });
  const a = q.data;
  if (q.error) return <Note tone="err">{errText(q.error, 'Analiz okunamadı.')}</Note>;
  if (!a) return <Loading />;
  const s = a.result?.summary;
  const signable = (a.status === 'onayda' ? a.required : []).filter(
    (r) => ov.me.approve[r.role] && !a.approvals.some((x) => x.role === r.role),
  );
  // Onaya gönderen imzalayamaz, bir kişi aynı sürümde tek rol adına karar verir (sunucu da denetler).
  const me = ov.me.user.toLowerCase();
  const iSigned = me === (a.submittedBy ?? '').toLowerCase() || a.approvals.some((x) => x.by.toLowerCase() === me);
  const editable: AnalysisStatus[] = ['taslak', 'reddedildi'];

  return (
    <div className="space-y-4">
      <div>
        <div className="flex flex-wrap items-center gap-2">
          <Pill tone={STATUS_TONE[a.status]}>{a.statusLabel}</Pill>
          <span className="text-[12px] text-canvas-muted">
            {a.stageLabel} · sürüm {a.version}
          </span>
        </div>
        <h3 className="mt-1 text-[17px] font-extrabold leading-snug">{a.title}</h3>
        <p className="text-[12px] text-canvas-muted">
          Hazırlayan {a.createdBy}
          {a.submittedBy ? ` · onaya gönderen ${a.submittedBy}, ${fmtDate(a.submittedAt)}` : ''}
        </p>
      </div>

      {s ? (
        <div className="grid grid-cols-2 gap-2">
          <Stat info={<SqlInfo k={a.kaynaklar} alan="result" label="Kapak fiyatı" />} label="Kapak fiyatı" value={tl0(s.price)} note={`Öneri ${tl0(s.recommended)} · alt sınır ${tl0(s.floor)}`} />
          <Stat info={<SqlInfo k={a.kaynaklar} alan="result" label="Baskı adedi" />} label="Baskı adedi" value={num(s.qty)} note={`Toplam maliyet ${tl0(s.totalCost)}`} />
          <Stat info={<SqlInfo k={a.kaynaklar} alan="result" label="Birim maliyet" />} label="Birim maliyet" value={tl2(s.unitCost)} />
          <Stat info={<SqlInfo k={a.kaynaklar} alan="result" label="Başabaş" />} label="Başabaş" value={s.breakeven != null ? `${num(s.breakeven)} adet` : '—'} note={`Marj ${pct(s.margin)} (hedef ${pct(s.targetMargin)})`} />
        </div>
      ) : (
        <Note tone="info">
          Taslak: seçilen adet {num(a.chosenQty)}, kapak fiyatı {tl0(a.chosenPrice)}. Rakamlar onaya gönderilince dondurulur.
        </Note>
      )}
      {a.result?.dataEnd && <p className="text-[11px] text-canvas-muted">Dondurulan hesabın Logo veri sonu: {a.result.dataEnd}.</p>}

      <section>
        <h4 className={labelCls}>İmzalar</h4>
        <ul className="mt-1 space-y-1">
          {a.required.map((r) => {
            const x = a.approvals.find((y) => y.role === r.role);
            return (
              <li key={r.role} className="flex flex-wrap items-center gap-2 text-[12.5px]">
                <Pill tone={!x ? 'muted' : x.decision === 'onay' ? 'ok' : 'err'}>{r.label}</Pill>
                {x ? (
                  <span>
                    {x.decision === 'onay' ? 'Onayladı' : 'Geri gönderdi'} — {x.by}, {fmtDate(x.at)}
                    {x.note ? ` · «${x.note}»` : ''}
                  </span>
                ) : (
                  <span className="text-canvas-muted">bekleniyor</span>
                )}
              </li>
            );
          })}
        </ul>
        {a.history.length > a.approvals.length && (
          <details className="mt-2 text-[12px]">
            <summary className="cursor-pointer font-bold text-canvas-violet">Önceki sürümlerin kararları</summary>
            <ul className="mt-1 space-y-0.5 text-canvas-muted">
              {a.history
                .filter((h) => h.version !== a.version)
                .map((h) => (
                  <li key={h.id}>
                    Sürüm {h.version}: {h.roleLabel} {h.decision === 'onay' ? 'onayladı' : 'geri gönderdi'} — {h.by}, {fmtDate(h.at)}
                    {h.note ? ` · «${h.note}»` : ''}
                  </li>
                ))}
            </ul>
          </details>
        )}
      </section>

      {signable.length > 0 && !iSigned && (
        <section className="space-y-2 rounded-2xl border border-slate-100 p-3">
          <h4 className={labelCls}>Kararınız</h4>
          <textarea
            className={`${field} min-h-[72px]`}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Not (geri gönderirken zorunlu)"
          />
          <div className="flex flex-wrap gap-2">
            {signable.map((r) => (
              <button key={r.role} type="button" className={btnPrimary} disabled={decide.isPending} onClick={() => decide.mutate({ role: r.role, decision: 'onay' })}>
                <Check aria-hidden className="h-4 w-4" />
                {r.label} adına onayla
              </button>
            ))}
            <button
              type="button"
              className={btnGhost}
              disabled={decide.isPending || !note.trim()}
              onClick={() => decide.mutate({ role: signable[0].role, decision: 'ret' })}
            >
              <Undo2 aria-hidden className="h-4 w-4" />
              {signable[0].label} adına geri gönder
            </button>
          </div>
          {decide.error && <Note tone="err">{errText(decide.error, 'Karar kaydedilemedi.')}</Note>}
        </section>
      )}
      {a.status === 'onaylandi' && (
        <Note tone="ok">Onaylandı. Kapak fiyatını CRM kitap kartına ve satış kanallarına ayrıca girin; buradan CRM'e yazılmaz.</Note>
      )}

      <div className="flex flex-wrap gap-2 border-t border-slate-100 pt-3">
        <button
          type="button"
          className={btnGhost}
          onClick={() => {
            onClose();
            setParams({ bolum: 'hesap', analiz: a.id, ...(a.stockCode ? { kitap: a.stockCode } : {}) });
          }}
        >
          <Pencil aria-hidden className="h-4 w-4" />
          {editable.includes(a.status) ? 'Hesabı aç ve düzenle' : 'Hesabı aç'}
        </button>
        {ov.me.canWrite && ['onayda', 'onaylandi', 'reddedildi'].includes(a.status) && (
          <button type="button" className={btnGhost} disabled={act.isPending} onClick={() => act.mutate('withdraw')}>
            <RotateCcw aria-hidden className="h-4 w-4" />
            Taslağa al (imzalar düşer)
          </button>
        )}
        {ov.me.canWrite && a.status !== 'onayda' && a.status !== 'arsiv' && (
          <button type="button" className={btnGhost} disabled={act.isPending} onClick={() => act.mutate('archive')}>
            <Archive aria-hidden className="h-4 w-4" />
            Arşive al
          </button>
        )}
      </div>
      {act.error && <Note tone="err">{errText(act.error, 'İşlem yapılamadı.')}</Note>}
    </div>
  );
}
