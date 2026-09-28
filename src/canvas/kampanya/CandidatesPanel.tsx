import { useState } from 'react';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Loader2, Plus } from 'lucide-react';
import { Note, TableWrap, btnPrimary, errText, field, label as labelCls, td, th } from '../admin/ui';
import { Panel, Pager, useDebounced } from '../editorial/kit';
import { fmtDay, fmtInt, fmtMoney, fmtPct } from '../budget/api';
import { kampanyaApi, type Overview } from './api';

/** Aday kitaplar: kural süzgeci (stok fazlası, yavaşlama, sezon; hak, maliyet, marj koşulları) ve rakamlı gerekçe.
 *  Kampanya içinden açılırsa seçilenler o kampanyaya eklenir; ayrı sekmede taslak bir kampanya seçilir. */
export default function CandidatesPanel({ ov, campaignId, onAdded }: { ov: Overview; campaignId?: string; onAdded?: () => void }) {
  const qc = useQueryClient();
  const [rules, setRules] = useState<string[]>(ov.varsayilanKurallar);
  const [q, setQ] = useState('');
  const [page, setPage] = useState(0);
  const [picked, setPicked] = useState<Record<string, string>>({});
  const [target, setTarget] = useState(campaignId ?? '');
  const dq = useDebounced(q.trim(), 300);
  const list = useQuery({
    queryKey: ['kampanya', 'candidates', campaignId ?? target, rules.join(','), dq, page],
    queryFn: () => kampanyaApi.candidates({ campaign_id: campaignId ?? (target || undefined), kurallar: rules.join(','), q: dq, page }),
    placeholderData: keepPreviousData,
  });
  const drafts = useQuery({
    queryKey: ['kampanya', 'list', 'taslak-hedef'],
    queryFn: () => kampanyaApi.list({ durum: 'taslak' }),
    enabled: !campaignId && ov.me.canEdit,
  });
  const add = useMutation({
    mutationFn: () => kampanyaApi.addItems(campaignId ?? target, Object.entries(picked).map(([stok, gerekce]) => ({ stok, gerekce }))),
    onSuccess: (c) => {
      qc.invalidateQueries({ queryKey: ['kampanya'] });
      const n = Object.keys(picked).length - (c.bulunamayan?.length ?? 0);
      toast.success(`${n} kitap eklendi.`);
      setPicked({});
      onAdded?.();
    },
    onError: (e) => toast.error(errText(e, 'Kitaplar eklenemedi.') ?? ''),
  });
  const toggleRule = (k: string) => {
    setRules((r) => (r.includes(k) ? r.filter((x) => x !== k) : [...r, k]));
    setPage(0);
  };
  const d = list.data;
  const count = Object.keys(picked).length;
  const canAdd = ov.me.canEdit && !!(campaignId ?? target) && count > 0;

  return (
    <Panel>
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap gap-1.5" role="group" aria-label="Kurallar">
          {Object.entries(ov.kurallar).map(([k, v]) => (
            <button key={k} type="button" aria-pressed={rules.includes(k)} onClick={() => toggleRule(k)}
              className={`inline-flex min-h-11 items-center rounded-xl px-3 text-[12px] font-extrabold transition-transform duration-150 ease-out active:scale-[0.97] sm:min-h-9 ${
                rules.includes(k) ? 'bg-canvas-violet text-white' : 'bg-slate-100 text-canvas-ink hover:bg-slate-200'}`}>
              {v}
            </button>
          ))}
        </div>
        {d && (
          <p className="text-[11.5px] leading-snug text-canvas-muted">
            Stok fazlası: stok son {d.esikler.hizAy} ayın satışıyla {fmtInt(d.esikler.stokAy)} aydan uzun yeter · yavaşlama: son {d.esikler.hizAy} ay önceki {d.esikler.hizAy} aya göre
            en az %{d.esikler.dususPct} düştü · sezon: kampanya ile bitişinden {d.esikler.sezonOncesiGun} gün sonrası arasındaki özel güne bağlı
            {d.sezonlar.length ? ` (${d.sezonlar.join(', ')})` : ''}. Sinyallerden biri yeter; hak, maliyet ve marj seçildiyse şarttır
            {rules.includes('marj') ? ` (marj %${Math.round(d.esikler.indirim * 100)} indirimle hesaplanır)` : ''}. Logo verisi {fmtDay(d.dataEnd)} tarihine kadar.
          </p>
        )}
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-[1fr_260px_auto]">
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Ara</span>
            <input className={field} value={q} onChange={(e) => { setQ(e.target.value); setPage(0); }} placeholder="Kitap adı, yazar ya da stok kodu" />
          </label>
          {!campaignId && ov.me.canEdit && (
            <label className="flex flex-col gap-1">
              <span className={labelCls}>Eklenecek kampanya</span>
              <select className={field} value={target} onChange={(e) => { setTarget(e.target.value); setPage(0); }}>
                <option value="">Taslak kampanya seçin</option>
                {(drafts.data?.items ?? []).map((c) => <option key={c.id} value={c.id}>{c.ad}</option>)}
              </select>
            </label>
          )}
          {ov.me.canEdit && (
            <div className="flex items-end">
              <button type="button" className={`${btnPrimary} w-full`} disabled={!canAdd || add.isPending} onClick={() => add.mutate()}>
                {add.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Plus aria-hidden className="h-4 w-4" />}
                {count ? `${count} kitabı ekle` : 'Seçilenleri ekle'}
              </button>
            </div>
          )}
        </div>
        {list.error && <Note tone="err">{errText(list.error, 'Adaylar hesaplanamadı.')}</Note>}
        <div>
          <TableWrap>
            <thead>
              <tr>
                {ov.me.canEdit && <th className={th}><span className="sr-only">Seç</span></th>}
                <th className={th}>Kitap</th>
                <th className={`${th} text-right`}>Stok</th>
                <th className={`${th} text-right`}>Stok yeter</th>
                <th className={`${th} text-right`}>Satış (son / önceki)</th>
                <th className={`${th} text-right`}>Liste</th>
                {rules.includes('marj') && <th className={`${th} text-right`}>Marj</th>}
                <th className={th}>Neden aday</th>
              </tr>
            </thead>
            <tbody>
              {(d?.items ?? []).map((c) => {
                const on = c.stok in picked;
                return (
                  <tr key={c.stok} className={`border-t border-slate-100 ${on ? 'bg-canvas-violet/5' : ''}`}>
                    {ov.me.canEdit && (
                      <td className={td}>
                        <input type="checkbox" className="h-5 w-5" aria-label={`${c.ad ?? c.stok} seç`} checked={on}
                          onChange={() => setPicked((p) => {
                            const n = { ...p };
                            if (on) delete n[c.stok];
                            else n[c.stok] = c.gerekce;
                            return n;
                          })} />
                      </td>
                    )}
                    <td className={td}>
                      <div className="font-semibold">{c.ad ?? c.stok}</div>
                      <div className="text-[11px] text-canvas-muted">{[c.yazar, c.stok].filter(Boolean).join(' · ')}</div>
                    </td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(c.stokAdet)}</td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{c.stokAy === null ? 'satış yok' : `${fmtInt(c.stokAy)} ay`}</td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(c.adetSon)} / {fmtInt(c.adetOnceki)}</td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{fmtMoney(c.liste)}</td>
                    {rules.includes('marj') && <td className={`${td} text-right font-mono tabular-nums`}>{fmtPct(c.marjOrani)}</td>}
                    <td className={`${td} text-[12px] leading-snug`}>{c.gerekce}</td>
                  </tr>
                );
              })}
            </tbody>
          </TableWrap>
          <Pager page={page} pageSize={d?.pageSize ?? 50} total={d?.total ?? 0} shown={d?.items.length ?? 0}
            loading={list.isLoading} fetching={list.isFetching} onPage={setPage} />
        </div>
      </div>
    </Panel>
  );
}
