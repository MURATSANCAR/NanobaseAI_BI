import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import SqlInfo, { InfoLabel } from '../components/SqlInfo';
import { EmptyHint } from '../components/Explain';
import { toast } from 'sonner';
import { Copy, Plus, Trash2 } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, Pill, TableWrap, btnGhost, btnPrimary, errText, field, label as labelCls, td, th } from '../admin/ui';
import { Panel } from '../editorial/kit';
import Sheet from '../editorial/studio/reader/Sheet';
import { financeApi, fmtDay, fmtMoney, parseNum, type TaxItem, type TaxStatus } from './api';

/** Vergi takvimi: beyanlar elle girilir (dış veri; müşteri ortamında web okuması yok). Son güne 7 ve 2 gün kala
 *  muhasebeye e-posta hatırlatması gider. Tahmini ödeme girilirse 13 haftalık nakitte çıkış olur. */

const TONE: Record<TaxStatus, 'ok' | 'warn' | 'muted' | 'violet'> = { bekliyor: 'muted', hazirlaniyor: 'warn', hazir: 'violet', verildi: 'ok' };

type Draft = { beyan: string; donem: string; sonGun: string; sorumlu: string; durum: TaxStatus; tutar: string; not: string };
const EMPTY: Draft = { beyan: '', donem: '', sonGun: '', sorumlu: '', durum: 'bekliyor', tutar: '', not: '' };

function EditSheet({ item, open, statuses, onClose }: { item: TaxItem | null; open: boolean; statuses: Record<TaxStatus, string>; onClose: () => void }) {
  const qc = useQueryClient();
  const [d, setD] = useState<Draft>(EMPTY);
  useEffect(() => {
    if (!open) return;
    setD(item ? { beyan: item.beyan, donem: item.donem ?? '', sonGun: item.sonGun, sorumlu: item.sorumlu ?? '', durum: item.durum,
      tutar: item.tutar === null ? '' : item.tutar.toLocaleString('tr-TR'), not: item.not ?? '' } : EMPTY);
  }, [item, open]);
  const save = useMutation({
    mutationFn: () => {
      const tutar = d.tutar.trim() ? parseNum(d.tutar) : null;
      if (d.tutar.trim() && tutar === null) throw new Error('Tutar sayı olmalı.');
      const body = { beyan: d.beyan, donem: d.donem || null, sonGun: d.sonGun, sorumlu: d.sorumlu || null, durum: d.durum, tutar, not: d.not || null };
      return item ? financeApi.taxUpdate(item.id, body) : financeApi.taxCreate(body);
    },
    onSuccess: () => { toast.success('Beyan kaydedildi.'); qc.invalidateQueries({ queryKey: ['finance'] }); onClose(); },
    onError: (e) => toast.error(errText(e, 'Beyan kaydedilemedi; biraz sonra yeniden deneyin.') ?? ''),
  });
  const del = useMutation({
    mutationFn: () => financeApi.taxDelete(item!.id),
    onSuccess: () => { toast.success('Beyan silindi.'); qc.invalidateQueries({ queryKey: ['finance'] }); onClose(); },
    onError: (e) => toast.error(errText(e, 'Beyan silinemedi; biraz sonra yeniden deneyin.') ?? ''),
  });
  const set = (k: keyof Draft) => (e: { target: { value: string } }) => setD((x) => ({ ...x, [k]: e.target.value }));
  return (
    <Sheet open={open} modal onClose={onClose} title={item ? item.beyan : 'Yeni beyan'} subtitle="Son gün ve tahmini ödeme muhasebenin girdisidir; mevzuat günü sistem tarafından üretilmez.">
      <form className="flex flex-col gap-3" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        <label className="flex flex-col gap-1"><span className={labelCls}>Beyan</span><input className={field} value={d.beyan} onChange={set('beyan')} required placeholder="KDV beyannamesi" /></label>
        <div className="grid grid-cols-2 gap-2">
          <label className="flex flex-col gap-1"><span className={labelCls}>Dönem</span><input className={field} value={d.donem} onChange={set('donem')} placeholder="Ağustos 2026" /></label>
          <label className="flex flex-col gap-1"><span className={labelCls}>Son gün</span><input type="date" className={field} value={d.sonGun} onChange={set('sonGun')} required /></label>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <label className="flex flex-col gap-1"><span className={labelCls}>Sorumlu</span><input className={field} value={d.sorumlu} onChange={set('sorumlu')} placeholder="Ör. Muhasebe" /></label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Durum</span>
            <select className={field} value={d.durum} onChange={set('durum')}>
              {(Object.entries(statuses) as Array<[TaxStatus, string]>).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </label>
        </div>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Tahmini ödeme (isteğe bağlı)</span>
          <input inputMode="decimal" className={`${field} font-mono`} value={d.tutar} onChange={set('tutar')} placeholder="Ör. 250.000" />
          <span className="text-[11px] text-canvas-muted">Girerseniz son gün haftasında 13 haftalık nakit tablosuna çıkış olarak yazılır.</span>
        </label>
        <label className="flex flex-col gap-1"><span className={labelCls}>Not</span><textarea className={`${field} min-h-[72px]`} value={d.not} onChange={set('not')} /></label>
        <div className="flex flex-wrap justify-between gap-2">
          {item ? (
            <button type="button" className={`${btnGhost} text-red-700`} onClick={() => del.mutate()} disabled={del.isPending}>
              <Trash2 aria-hidden className="h-4 w-4" /> Beyanı sil
            </button>
          ) : <span />}
          <div className="flex gap-2">
            <button type="button" className={btnGhost} onClick={onClose}>Vazgeç</button>
            <button type="submit" className={btnPrimary} disabled={save.isPending}>Kaydet</button>
          </div>
        </div>
      </form>
    </Sheet>
  );
}

export default function TaxTab({ year, canEdit, statuses }: { year: number; canEdit: boolean; statuses: Record<TaxStatus, string> }) {
  const qc = useQueryClient();
  const [edit, setEdit] = useState<{ item: TaxItem | null } | null>(null);
  const q = useQuery({ queryKey: ['finance', 'tax', year], queryFn: () => financeApi.tax(year), enabled: ENGINE_ENABLED });
  const copy = useMutation({
    mutationFn: () => financeApi.taxCopy(year - 1, year),
    onSuccess: (r) => { toast.success(`${r.kopyalanan} beyan kopyalandı${r.atlanan ? `, ${r.atlanan} zaten vardı` : ''}. Günleri denetleyin.`); qc.invalidateQueries({ queryKey: ['finance', 'tax'] }); },
    onError: (e) => toast.error(errText(e, 'Geçen yılın takvimi kopyalanamadı; biraz sonra yeniden deneyin.') ?? ''),
  });
  if (q.isLoading) return <Loading />;
  if (q.error) return <Note tone="err">{errText(q.error, 'Vergi takvimi açılamadı; biraz sonra yeniden deneyin.')}</Note>;
  const d = q.data;
  if (!d) return null;
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <p className="min-w-0 flex-1 text-[12.5px] text-canvas-muted">
          Bugün {fmtDay(d.today)}. Son güne 7 ve 2 gün kala muhasebeye hatırlatma gider (Yönetim → teslim ayarlarında alıcılar).
        </p>
        {canEdit && (
          <>
            <button type="button" className={btnGhost} onClick={() => copy.mutate()} disabled={copy.isPending}>
              <Copy aria-hidden className="h-4 w-4" /> {year - 1} takvimini kopyala
            </button>
            <button type="button" className={btnPrimary} onClick={() => setEdit({ item: null })}>
              <Plus aria-hidden className="h-4 w-4" /> Beyan ekle
            </button>
          </>
        )}
      </div>
      {d.geciken.length > 0 && (
        <Note tone="err">
          {d.geciken.length} beyanın son günü geçti ve «verildi» işaretlenmedi.
          <SqlInfo k={d.kaynaklar} alan="geciken[]" label="Geciken beyan sayısı" className="ml-0.5" />
        </Note>
      )}
      {!d.items.length ? (
        <EmptyHint
          title={`${year} için beyan girilmemiş`}
          why={
            canEdit
              ? `Takvim elle girilir. «Beyan ekle» ile tek tek ekleyebilir ya da «${year - 1} takvimini kopyala» ile geçen yılınkini alıp günleri denetleyebilirsiniz.`
              : 'Takvim muhasebe tarafından elle girilir; henüz bu yıl için beyan eklenmemiş.'
          }
        />
      ) : (
        <Panel>
          <TableWrap>
            <thead>
              <tr>
                <th className={th}><InfoLabel k={d.kaynaklar} alan="items[].kalanGun" label="Son gün ve kalan gün">Son gün</InfoLabel></th>
                <th className={th}>Beyan</th>
                <th className={th}>Dönem</th>
                <th className={th}>Sorumlu</th>
                <th className={th}>Durum</th>
                <th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="items[].tutar">Tahmini ödeme</InfoLabel></th>
              </tr>
            </thead>
            <tbody>
              {d.items.map((t) => (
                <tr key={t.id} className={`border-t border-slate-100 ${canEdit ? 'cursor-pointer hover:bg-white' : ''} ${t.gecikti ? 'bg-red-50/60' : ''}`}
                  onClick={() => canEdit && setEdit({ item: t })}>
                  <td className={`${td} whitespace-nowrap`}>
                    <div className="font-semibold">{fmtDay(t.sonGun)}</div>
                    <div className={`text-[11px] ${t.gecikti ? 'font-bold text-red-700' : 'text-canvas-muted'}`}>
                      {t.durum === 'verildi' ? 'verildi' : t.gecikti ? `${-t.kalanGun} gün geçti` : `${t.kalanGun} gün kaldı`}
                    </div>
                  </td>
                  <td className={`${td} font-semibold`}>{t.beyan}{t.not && <div className="text-[11px] font-normal text-canvas-muted">{t.not}</div>}</td>
                  <td className={td}>{t.donem ?? '—'}</td>
                  <td className={td}>{t.sorumlu ?? '—'}</td>
                  <td className={td}><Pill tone={TONE[t.durum]}>{t.durumLabel}</Pill></td>
                  <td className={`${td} whitespace-nowrap text-right font-mono tabular-nums`}>{fmtMoney(t.tutar)}</td>
                </tr>
              ))}
            </tbody>
          </TableWrap>
        </Panel>
      )}
      <EditSheet item={edit?.item ?? null} open={!!edit} statuses={statuses} onClose={() => setEdit(null)} />
    </div>
  );
}
