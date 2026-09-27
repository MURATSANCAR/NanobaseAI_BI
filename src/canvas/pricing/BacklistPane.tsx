import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, FilePlus2, Undo2 } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, Pill, TableWrap, btnGhost, btnPrimary, errText, field, fmtDate, label as labelCls, td, th } from '../admin/ui';
import { Panel, useDebounced } from '../editorial/kit';
import { STATUS_TONE, day, num, overviewKey, pct, pricingApi, tl0, tl2, type Overview, type Proposal } from './api';
import { NumField, Stat } from './parts';

/**
 * Backlist fiyat revizyonu: son baskının birim bedeli (matbaa + güncel kâğıt) kapak fiyatına göre yükselmiş kitaplar.
 * Hedef oran = son 12 ayda ilk baskısı yapılan kitapların ortanca oranı (bugünkü fiyatlama pratiği) ya da elle.
 * Toplu zam teklifi Mali İşler onayına gider; onaylansa da fiyat buradan CRM'e ya da e-ticarete yazılmaz.
 */
export default function BacklistPane({ ov }: { ov: Overview }) {
  const qc = useQueryClient();
  const [target, setTarget] = useState<number | null>(null);
  const [minSold, setMinSold] = useState<number | null>(1);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [title, setTitle] = useState('');
  const dt = useDebounced(target, 400);
  const dm = useDebounced(minSold, 400);
  const bl = useQuery({
    queryKey: ['pricing', 'backlist', dt, dm],
    queryFn: () => pricingApi.backlist({ target: dt, minSold: dm ?? 1 }),
    enabled: ENGINE_ENABLED && !!ov.measured,
    placeholderData: (p) => p,
  });
  const proposals = useQuery({ queryKey: ['pricing', 'proposals'], queryFn: pricingApi.proposals, enabled: ENGINE_ENABLED });
  const create = useMutation({
    mutationFn: () =>
      pricingApi.createProposal({ title: title.trim() || `Backlist fiyat revizyonu ${new Date().toLocaleDateString('tr-TR')}`, codes: [...picked], target: dt, minSold: dm ?? 1 }),
    onSuccess: () => {
      setPicked(new Set());
      setTitle('');
      qc.invalidateQueries({ queryKey: ['pricing', 'proposals'] });
    },
  });
  const rows = bl.data?.rows ?? [];
  const pickedRows = useMemo(() => rows.filter((r) => picked.has(r.code)), [rows, picked]);
  const toggle = (code: string) =>
    setPicked((p) => {
      const n = new Set(p);
      if (n.has(code)) n.delete(code);
      else n.add(code);
      return n;
    });

  if (!ov.measured) return <Note tone="info">Logo verisi hazırlanınca revizyon adayları burada görünür.</Note>;
  const d = bl.data;

  return (
    <div className="flex flex-col gap-3">
      <Panel>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <NumField
            label="Hedef maliyet / fiyat oranı"
            suffix="%"
            percent
            value={target ?? d?.measuredTarget ?? null}
            onChange={setTarget}
            hint={d?.measuredTarget != null ? `Ölçülen: son 12 ayın ${num(d.freshBooks)} yeni kitabında ortanca ${pct(d.measuredTarget)}` : 'Ölçülemedi — elle girin'}
          />
          <NumField label="Son iki yılda en az satış" suffix="adet" digits={0} value={minSold} onChange={setMinSold} hint="Hiç satmayan kitaba zam önerilmez" />
          <Stat label="Aday" value={d ? num(d.count) : '—'} note={d ? `${num(d.candidates)} kitabın son baskısı incelendi` : undefined} />
          <Stat label="Seçilen" value={num(picked.size)} note={pickedRows.length ? `Ortalama artış ${pct(pickedRows.reduce((s, r) => s + r.increase, 0) / pickedRows.length)}` : 'Tablodan işaretleyin'} />
        </div>
      </Panel>
      {bl.error && <Note tone="err">{errText(bl.error, 'Adaylar okunamadı.')}</Note>}
      {!d ? (
        !bl.error && <Loading />
      ) : d.rows.length === 0 ? (
        <p className="py-8 text-center text-[12.5px] text-canvas-muted">Bu hedef oranla revizyon adayı yok.</p>
      ) : (
        <TableWrap>
          <thead>
            <tr>
              <th className={th}>
                <input
                  type="checkbox"
                  aria-label="Hepsini seç"
                  className="h-4 w-4"
                  checked={picked.size > 0 && picked.size === d.rows.length}
                  onChange={(e) => setPicked(e.target.checked ? new Set(d.rows.map((r) => r.code)) : new Set())}
                />
              </th>
              <th className={th}>Kitap</th>
              <th className={th}>Son baskı</th>
              <th className={`${th} text-right`}>Baskı / adet</th>
              <th className={`${th} text-right`}>Kâğıt / adet</th>
              <th className={`${th} text-right`}>Maliyet / fiyat</th>
              <th className={`${th} text-right`}>Satış (2 yıl)</th>
              <th className={`${th} text-right`}>Kapak fiyatı</th>
              <th className={`${th} text-right`}>Önerilen</th>
              <th className={`${th} text-right`}>Artış</th>
            </tr>
          </thead>
          <tbody>
            {d.rows.map((r) => (
              <tr key={r.code} className={`border-t border-slate-100 ${picked.has(r.code) ? 'bg-canvas-violet/5' : ''}`}>
                <td className={td}>
                  <input type="checkbox" className="h-4 w-4" aria-label={`${r.name} seç`} checked={picked.has(r.code)} onChange={() => toggle(r.code)} />
                </td>
                <td className={td}>
                  <div className="font-bold">{r.name}</div>
                  <div className="text-[11px] text-canvas-muted">{[r.code, r.publisher, r.pages ? `${r.pages} s.` : null].filter(Boolean).join(' · ')}</div>
                </td>
                <td className={td}>
                  {day(r.lastPrintDate)}
                  <div className="text-[11px] text-canvas-muted">{num(r.lastPrintQty)} adet</div>
                </td>
                <td className={`${td} text-right tabular-nums`}>{tl2(r.printUnit)}</td>
                <td className={`${td} text-right tabular-nums`}>{tl2(r.paperUnit)}</td>
                <td className={`${td} text-right tabular-nums`}>{pct(r.ratio)}</td>
                <td className={`${td} text-right tabular-nums`}>{num(r.sold2y)}</td>
                <td className={`${td} text-right tabular-nums`}>{tl0(r.price)}</td>
                <td className={`${td} text-right tabular-nums font-bold`}>{tl0(r.proposed)}</td>
                <td className={`${td} text-right tabular-nums`}>{pct(r.increase)}</td>
              </tr>
            ))}
          </tbody>
        </TableWrap>
      )}
      <p className="px-1 text-[11px] leading-snug text-canvas-muted">
        Birim bedel = son matbaa faturasının adet başı tutarı + bugünkü kâğıt fiyatıyla kâğıt, kapak kartonu ve bandrol (sayfa, ebat, gramajdan). Önerilen fiyat bu
        bedeli hedef orana indiren en düşük kapak fiyatıdır (KDV dahil, 5 ₺'ye yukarı). Satış hızının fiyata tepkisi ölçülmedi: öneri maliyet tarafıdır.
      </p>

      {ov.me.canWrite && d && d.rows.length > 0 && (
        <Panel>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
            <label className="block min-w-0 flex-1">
              <span className={labelCls}>Teklif adı</span>
              <input className={`${field} mt-1`} value={title} placeholder="Ör. Ekim backlist zammı" onChange={(e) => setTitle(e.target.value)} />
            </label>
            <button type="button" className={btnPrimary} disabled={!picked.size || create.isPending} onClick={() => create.mutate()}>
              <FilePlus2 aria-hidden className="h-4 w-4" />
              {num(picked.size)} kitapla toplu zam teklifi oluştur
            </button>
          </div>
          <p className="mt-1 text-[11px] text-canvas-muted">Teklif sunucuda yeniden hesaplanıp dondurulur ve Mali İşler onayına düşer.</p>
          {create.error && <Note tone="err">{errText(create.error, 'Teklif oluşturulamadı.')}</Note>}
        </Panel>
      )}

      <ProposalList ov={ov} items={proposals.data?.items ?? []} />
    </div>
  );
}

function ProposalList({ ov, items }: { ov: Overview; items: Proposal[] }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState<string | null>(null);
  const [note, setNote] = useState('');
  const one = useQuery({ queryKey: ['pricing', 'proposal', open], queryFn: () => pricingApi.proposal(open!), enabled: ENGINE_ENABLED && !!open });
  const decide = useMutation({
    mutationFn: (decision: 'onay' | 'ret') => pricingApi.decideProposal(open!, { decision, note }),
    onSuccess: () => {
      setNote('');
      qc.invalidateQueries({ queryKey: ['pricing', 'proposals'] });
      qc.invalidateQueries({ queryKey: ['pricing', 'proposal', open] });
      qc.invalidateQueries({ queryKey: overviewKey });
    },
  });
  if (!items.length) return null;
  const p = one.data;
  const canDecide = ov.me.approve.mali && p?.status === 'onayda' && p.createdBy.toLowerCase() !== ov.me.user.toLowerCase();
  return (
    <section className="space-y-2">
      <h3 className="px-1 text-[14px] font-extrabold">Toplu zam teklifleri</h3>
      <TableWrap>
        <thead>
          <tr>
            <th className={th}>Teklif</th>
            <th className={th}>Durum</th>
            <th className={`${th} text-right`}>Kitap</th>
            <th className={th}>Hazırlayan</th>
            <th className={th}>Karar</th>
          </tr>
        </thead>
        <tbody>
          {items.map((x) => (
            <tr key={x.id} className={`cursor-pointer border-t border-slate-100 hover:bg-slate-50 ${open === x.id ? 'bg-canvas-violet/5' : ''}`} onClick={() => setOpen(open === x.id ? null : x.id)}>
              <td className={`${td} font-bold`}>{x.title}</td>
              <td className={td}>
                <Pill tone={STATUS_TONE[x.status]}>{x.statusLabel}</Pill>
              </td>
              <td className={`${td} text-right tabular-nums`}>{num(x.count)}</td>
              <td className={td}>
                {x.createdBy} · {fmtDate(x.createdAt)}
              </td>
              <td className={td}>{x.decidedBy ? `${x.decidedBy} · ${fmtDate(x.decidedAt)}${x.decisionNote ? ` · «${x.decisionNote}»` : ''}` : '—'}</td>
            </tr>
          ))}
        </tbody>
      </TableWrap>
      {open && p && (
        <Panel>
          <h4 className="text-[13px] font-extrabold">{p.title}</h4>
          <p className="text-[11.5px] text-canvas-muted">
            Hedef oran {pct(p.params.target)} · veri sonu {day(p.params.dataEnd)}
          </p>
          <div className="mt-2">
            <TableWrap>
              <thead>
                <tr>
                  <th className={th}>Kitap</th>
                  <th className={`${th} text-right`}>Birim bedel</th>
                  <th className={`${th} text-right`}>Şimdiki</th>
                  <th className={`${th} text-right`}>Önerilen</th>
                  <th className={`${th} text-right`}>Artış</th>
                </tr>
              </thead>
              <tbody>
                {(p.items ?? []).map((it) => (
                  <tr key={it.code} className="border-t border-slate-100">
                    <td className={td}>
                      {it.name}
                      <div className="text-[11px] text-canvas-muted">{it.code}</div>
                    </td>
                    <td className={`${td} text-right tabular-nums`}>{tl2(it.unit)}</td>
                    <td className={`${td} text-right tabular-nums`}>{tl0(it.price)}</td>
                    <td className={`${td} text-right tabular-nums font-bold`}>{tl0(it.proposed)}</td>
                    <td className={`${td} text-right tabular-nums`}>{pct(it.increase)}</td>
                  </tr>
                ))}
              </tbody>
            </TableWrap>
          </div>
          {canDecide && (
            <div className="mt-3 space-y-2">
              <textarea className={`${field} min-h-[64px]`} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Not (geri gönderirken zorunlu)" />
              <div className="flex flex-wrap gap-2">
                <button type="button" className={btnPrimary} disabled={decide.isPending} onClick={() => decide.mutate('onay')}>
                  <Check aria-hidden className="h-4 w-4" />
                  Mali İşler adına onayla
                </button>
                <button type="button" className={btnGhost} disabled={decide.isPending || !note.trim()} onClick={() => decide.mutate('ret')}>
                  <Undo2 aria-hidden className="h-4 w-4" />
                  Geri gönder
                </button>
              </div>
            </div>
          )}
          {p.status === 'onaylandi' && <div className="mt-2"><Note tone="ok">Onaylandı. Fiyatlar CRM'e ve satış kanallarına ayrıca girilir.</Note></div>}
          {decide.error && <Note tone="err">{errText(decide.error, 'Karar kaydedilemedi.')}</Note>}
        </Panel>
      )}
    </section>
  );
}
