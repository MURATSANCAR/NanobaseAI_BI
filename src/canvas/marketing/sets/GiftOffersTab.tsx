import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Building2, Plus } from 'lucide-react';
import { Note, TableWrap, btnGhost, btnPrimary, errText, field, label as labelCls, td, th } from '../../admin/ui';
import { Pager, useDebounced } from '../../editorial/kit';
import Sheet from '../../editorial/studio/reader/Sheet';
import { fmtDay, fmtInt, fmtMoney, parseNum } from '../../budget/api';
import { OFFER_TONE, setsApi, type Account, type SetsMeta } from './api';
import { Tone } from './parts';

/** Kurumsal teklifler: firma (CRM) + kişi sayısı + kişi başı bütçe → seçenekler (kod), mektup (ZEKİ AI), onay, PDF. */
export default function GiftOffersTab({ meta }: { meta: SetsMeta }) {
  const [durum, setDurum] = useState('');
  const [q, setQ] = useState('');
  const [page, setPage] = useState(0);
  const [creating, setCreating] = useState(false);
  const dq = useDebounced(q.trim(), 300);
  const list = useQuery({
    queryKey: ['sets', 'offers', durum, dq, page],
    queryFn: () => setsApi.offers({ durum, q: dq, page }),
    placeholderData: keepPreviousData,
  });
  return (
    <>
      <section className="glass-panel rounded-2xl p-3 shadow-glass-float sm:rounded-3xl sm:p-4">
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-[1fr_200px_auto]">
          <label className="col-span-2 flex flex-col gap-1 sm:col-span-1">
            <span className={labelCls}>Ara</span>
            <input className={field} placeholder="Firma ya da teklif no" value={q} onChange={(e) => { setQ(e.target.value); setPage(0); }} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Durum</span>
            <select className={field} value={durum} onChange={(e) => { setDurum(e.target.value); setPage(0); }}>
              <option value="">Hepsi</option>
              {Object.entries(meta.offerStatuses).map(([k, v]) => (
                <option key={k} value={k}>{v}{list.data ? ` (${(list.data.summary as Record<string, number>)[k] ?? 0})` : ''}</option>
              ))}
            </select>
          </label>
          {meta.me.canWrite && (
            <button type="button" className={`${btnPrimary} self-end`} onClick={() => setCreating(true)}>
              <Plus aria-hidden className="h-4 w-4" /> Yeni teklif
            </button>
          )}
        </div>
        <p className="mt-2 text-[11.5px] text-canvas-muted">
          Seçenekleri sistem hesaplar (stoğu kişi sayısına yeten, kademe indirimi sonrası bütçeye sığan set, paket ve kitaplar); mektubu ZEKİ AI taslak
          yazar, satış düzeltir. Onaydan sonra PDF indirilir; kuruma gönderimi satış yapar. Kurumsal satış fırsatı açıldıysa teklif oraya bağlanır.
        </p>
      </section>
      {list.error && <Note tone="err">{errText(list.error, 'Teklifler okunamadı.')}</Note>}
      {list.data && (
        <section>
          <TableWrap>
            <thead>
              <tr className="border-b border-slate-100">
                <th className={th}>Teklif</th>
                <th className={th}>Durum</th>
                <th className={`${th} text-right`}>Kişi</th>
                <th className={`${th} text-right`}>Kişi başı bütçe</th>
                <th className={`${th} text-right`}>Seçenek</th>
                <th className={th}>Geçerlilik</th>
                <th className={th}>Hazırlayan</th>
              </tr>
            </thead>
            <tbody>
              {list.data.items.map((o) => (
                <tr key={o.id} className="border-b border-slate-50 last:border-0 hover:bg-slate-50/60">
                  <td className={td}>
                    <Link to={`/pazarlama/set-hediye/teklif/${encodeURIComponent(o.id)}`} className="font-bold hover:text-canvas-violet hover:underline">{o.firmaAdi ?? o.firmaId}</Link>
                    <div className="text-[11px] text-canvas-muted">{o.id}{o.sezon ? ` · ${o.sezon}` : ''}</div>
                  </td>
                  <td className={td}><Tone tone={OFFER_TONE[o.durum]}>{o.durumAdi}</Tone></td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(o.adet)}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtMoney(o.kisiBasiButce)}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{o.secili.length} / {o.secenekler.length}</td>
                  <td className={td}>
                    {fmtDay(o.gecerlilik)}
                    {o.gunKaldi !== null && o.gunKaldi !== undefined && o.gunKaldi >= 0 && o.gunKaldi <= 7 && <div className="text-[11px] font-bold text-amber-800">{o.gunKaldi} gün kaldı</div>}
                  </td>
                  <td className={td}>{o.hazirlayan ?? '—'}</td>
                </tr>
              ))}
              {!list.data.items.length && <tr><td className={`${td} text-canvas-muted`} colSpan={7}>Teklif yok.</td></tr>}
            </tbody>
          </TableWrap>
          <Pager page={list.data.page} pageSize={list.data.pageSize} total={list.data.total} shown={list.data.items.length}
            loading={list.isLoading} fetching={list.isFetching} onPage={setPage} />
        </section>
      )}
      <NewOfferSheet open={creating} meta={meta} onClose={() => setCreating(false)} />
    </>
  );
}

function NewOfferSheet({ open, meta, onClose }: { open: boolean; meta: SetsMeta; onClose: () => void }) {
  const qc = useQueryClient();
  const nav = useNavigate();
  const [q, setQ] = useState('');
  const [acc, setAcc] = useState<Account | null>(null);
  const [adet, setAdet] = useState('');
  const [butce, setButce] = useState('');
  const [sezon, setSezon] = useState('');
  const dq = useDebounced(q.trim(), 350);
  const found = useQuery({ queryKey: ['sets', 'accounts', dq], queryFn: () => setsApi.accounts(dq), enabled: open && !acc && dq.length >= 2 });
  const history = useQuery({ queryKey: ['sets', 'history', acc?.id], queryFn: () => setsApi.history(acc!.id), enabled: !!acc });
  const create = useMutation({
    mutationFn: () => setsApi.createOffer({ firmaId: acc!.id, adet: parseNum(adet) ?? 0, kisiBasiButce: parseNum(butce) ?? 0, sezon: sezon || undefined }),
    onSuccess: (o) => {
      qc.invalidateQueries({ queryKey: ['sets', 'offers'] });
      toast.success('Teklif taslağı hazır.');
      onClose();
      nav(`/pazarlama/set-hediye/teklif/${encodeURIComponent(o.id)}`);
    },
    onError: (e) => toast.error(errText(e, 'Teklif hazırlanamadı.') ?? ''),
  });
  const ok = !!acc && (parseNum(adet) ?? 0) >= 1 && (parseNum(butce) ?? 0) > 0;
  return (
    <Sheet open={open} modal onClose={onClose} title="Kurumsal hediye teklifi" subtitle="Firma CRM'den seçilir; seçenekler stok ve bütçeye göre hesaplanır.">
      <div className="flex flex-col gap-3 text-[13px]">
        {acc ? (
          <div className="flex items-center gap-2 rounded-xl bg-slate-50 px-3 py-2">
            <Building2 aria-hidden className="h-4 w-4 text-canvas-violet" />
            <span className="min-w-0 flex-1 truncate font-bold">{acc.unvan}</span>
            <button type="button" className={btnGhost} onClick={() => setAcc(null)}>Değiştir</button>
          </div>
        ) : (
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Firma (CRM)</span>
            <input className={field} placeholder="Unvan ya da cari kodu" value={q} onChange={(e) => setQ(e.target.value)} />
            {found.data && (
              <ul className="max-h-56 overflow-y-auto overscroll-contain rounded-xl border border-slate-100 bg-white/90">
                {found.data.items.map((a) => (
                  <li key={a.id}>
                    <button type="button" className="flex min-h-11 w-full flex-col items-start px-3 py-1.5 text-left transition-colors duration-150 hover:bg-slate-50 active:bg-slate-100"
                      onClick={() => setAcc(a)}>
                      <span className="font-semibold">{a.unvan}</span>
                      <span className="text-[11px] text-canvas-muted">{a.kod ?? 'cari kodu yok'}</span>
                    </button>
                  </li>
                ))}
                {!found.data.items.length && <li className="px-3 py-2 text-[12px] text-canvas-muted">Firma bulunamadı.</li>}
                {found.data.total > found.data.items.length && (
                  <li className="px-3 py-2 text-[11px] text-canvas-muted">{found.data.total.toLocaleString('tr-TR')} firmadan ilk {found.data.items.length} tanesi; aramayı daraltın.</li>
                )}
              </ul>
            )}
          </label>
        )}
        {acc && history.data && history.data.items.length > 0 && (
          <div className="rounded-xl bg-slate-50 px-3 py-2 text-[12px]">
            <div className="font-bold">CRM'deki hediye talepleri</div>
            {history.data.items.map((h, i) => (
              <div key={i} className="text-canvas-muted">{h.no ?? '—'} · {fmtDay(h.tarih)} · {fmtMoney(h.toplam ?? h.hediyeTutari)} · {h.durum}</div>
            ))}
          </div>
        )}
        <div className="grid grid-cols-2 gap-2">
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Kişi sayısı</span>
            <input className={`${field} font-mono`} inputMode="numeric" value={adet} onChange={(e) => setAdet(e.target.value)} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Kişi başı bütçe (KDV dahil)</span>
            <input className={`${field} font-mono`} inputMode="decimal" value={butce} onChange={(e) => setButce(e.target.value)} />
          </label>
        </div>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Vesile (isteğe bağlı)</span>
          <select className={field} value={sezon} onChange={(e) => setSezon(e.target.value)}>
            <option value="">—</option>
            {meta.seasons.filter((s) => s.gunKaldi !== null && s.gunKaldi <= 366).map((s) => <option key={s.id} value={s.ad}>{s.ad} · {fmtDay(s.sonraki)}</option>)}
          </select>
        </label>
        {meta.giftTiers.length > 0 && (
          <p className="text-[11.5px] text-canvas-muted">Adet kademeleri: {meta.giftTiers.map((t) => `${t.adet}+ %${(t.indirim * 100).toLocaleString('tr-TR')}`).join(' · ')} (teklifte değiştirilebilir).</p>
        )}
        <div className="flex flex-wrap justify-end gap-2">
          <button type="button" className={btnGhost} onClick={onClose}>Vazgeç</button>
          <button type="button" className={btnPrimary} disabled={!ok || create.isPending} onClick={() => create.mutate()}>Seçenekleri hesapla</button>
        </div>
      </div>
    </Sheet>
  );
}
