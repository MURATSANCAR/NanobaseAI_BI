import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Plus, Trash2 } from 'lucide-react';
import { Note, TableWrap, btnGhost, btnPrimary, errText, field, label as labelCls, td, th } from '../../admin/ui';
import { Kpi, KpiRow, Pager, useDebounced } from '../../editorial/kit';
import Sheet from '../../editorial/studio/reader/Sheet';
import { fmtInt, fmtMoney, fmtPct, fmtShort, parseNum } from '../../budget/api';
import { STATUS_TONE, addItem, setsApi, type ItemInput, type SetsMeta } from './api';
import { MarginCell, Tone } from './parts';
import BookPicker from './BookPicker';
import SqlInfo, { InfoLabel } from '../../components/SqlInfo';

/** Setler sekmesi: mevcut (CRM) + önerilen + taslak setlerin tamamı, tavansız ve sayfalı. */
export default function SetsTab({ meta }: { meta: SetsMeta }) {
  const [q, setQ] = useState('');
  const [durum, setDurum] = useState('');
  const [tur, setTur] = useState('');
  const [sort, setSort] = useState('ciro');
  const [page, setPage] = useState(0);
  const [creating, setCreating] = useState(false);
  const dq = useDebounced(q.trim(), 300);
  const list = useQuery({
    queryKey: ['sets', 'list', dq, durum, tur, sort, page],
    queryFn: () => setsApi.list({ q: dq, durum, tur, sort, page }),
    placeholderData: keepPreviousData,
  });
  const s = list.data?.summary;
  const floor = meta.settings.marginMinPct;

  return (
    <>
      {s && (
        <KpiRow>
          <Kpi label="Set" value={fmtInt(s.toplam)} help={`${fmtInt(s.satista)} satışta · ${fmtInt(s.oneri)} taslak/öneri`}
            active={durum === ''} onClick={() => { setDurum(''); setPage(0); }} info={<SqlInfo k={list.data?.kaynaklar} alan="summary" label="Set" />} />
          <Kpi label="Son 12 ayda satışsız" value={fmtInt(s.satissiz)} help="Satıştaki setlerden net satışı olmayanlar"
            active={sort === 'adet' && durum === 'satista'} onClick={() => { setDurum('satista'); setSort('adet'); setPage(0); }} info={<SqlInfo k={list.data?.kaynaklar} alan="summary" label="Son 12 ayda satışsız" />} />
          <Kpi label="Marj bilinmiyor" value={fmtInt(s.marjBilinmiyor)} help={meta.me.canSeeCost ? 'Bir bileşende maliyet yok' : 'Maliyeti görme yetkiniz yok'} info={<SqlInfo k={list.data?.kaynaklar} alan="summary" label="Marj bilinmiyor" />} />
          <Kpi label="Onay / kart bekleyen" value={`${fmtInt(s.onayda)} / ${fmtInt(s.kartBekliyor)}`} help="Onay bekleyen · onaylı, CRM kartı açılmamış"
            active={durum === 'onayda,kart-bekliyor'} onClick={() => { setDurum('onayda,kart-bekliyor'); setPage(0); }} info={<SqlInfo k={list.data?.kaynaklar} alan="summary" label="Onay / kart bekleyen" />} />
        </KpiRow>
      )}

      <section className="glass-panel rounded-2xl p-3 shadow-glass-float sm:rounded-3xl sm:p-4">
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-[1fr_160px_160px_160px_auto]">
          <label className="col-span-2 flex flex-col gap-1 sm:col-span-1">
            <span className={labelCls}>Ara</span>
            <input className={field} placeholder="Set adı ya da stok kodu" value={q} onChange={(e) => { setQ(e.target.value); setPage(0); }} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Durum</span>
            <select className={field} value={durum} onChange={(e) => { setDurum(e.target.value); setPage(0); }}>
              <option value="">Hepsi</option>
              {Object.entries(meta.statuses).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              <option value="onayda,kart-bekliyor">Onay ya da kart bekleyen</option>
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Tür</span>
            <select className={field} value={tur} onChange={(e) => { setTur(e.target.value); setPage(0); }}>
              <option value="">Hepsi</option>
              {Object.entries(meta.types).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Sıra</span>
            <select className={field} value={sort} onChange={(e) => { setSort(e.target.value); setPage(0); }}>
              <option value="ciro">Son 12 ay ciro</option>
              <option value="adet">Son 12 ay adet</option>
              <option value="marj">Marj oranı (düşük önce)</option>
              <option value="indirim">İndirim</option>
              <option value="durum">Durum</option>
              <option value="ad">Ad</option>
              <option value="yeni">En yeni</option>
            </select>
          </label>
          {meta.me.canWrite && (
            <button type="button" className={`${btnPrimary} col-span-2 self-end sm:col-span-1`} onClick={() => setCreating(true)}>
              <Plus aria-hidden className="h-4 w-4" />
              Yeni set
            </button>
          )}
        </div>
      </section>

      {list.error && <Note tone="err">{errText(list.error, 'Setler okunamadı.')}</Note>}
      {list.data && (
        <section>
          <TableWrap>
            <thead>
              <tr className="border-b border-slate-100">
                <th className={th}>Set</th>
                <th className={th}>Durum</th>
                <th className={`${th} text-right`}><InfoLabel k={list.data.kaynaklar} alan="items[]">Bileşen</InfoLabel></th>
                <th className={`${th} text-right`}><InfoLabel k={list.data.kaynaklar} alan="items[]">Set fiyatı</InfoLabel></th>
                <th className={`${th} text-right`}><InfoLabel k={list.data.kaynaklar} alan="items[]">Liste toplamı</InfoLabel></th>
                <th className={`${th} text-right`}><InfoLabel k={list.data.kaynaklar} alan="items[]">İndirim</InfoLabel></th>
                {meta.me.canSeeCost && <th className={`${th} text-right`}><InfoLabel k={list.data.kaynaklar} alan="items[]">Marj</InfoLabel></th>}
                <th className={`${th} text-right`}><InfoLabel k={list.data.kaynaklar} alan="items[]">Stok</InfoLabel></th>
                <th className={`${th} text-right`}><InfoLabel k={list.data.kaynaklar} alan="items[]">12 ay adet</InfoLabel></th>
                <th className={`${th} text-right`}><InfoLabel k={list.data.kaynaklar} alan="items[]">12 ay ciro</InfoLabel></th>
              </tr>
            </thead>
            <tbody>
              {list.data.items.map((r) => (
                <tr key={r.id} className="border-b border-slate-50 last:border-0 hover:bg-slate-50/60">
                  <td className={td}>
                    <Link to={`/pazarlama/set-hediye/set/${encodeURIComponent(r.id)}`} className="font-bold text-canvas-ink hover:text-canvas-violet hover:underline">
                      {r.ad}
                    </Link>
                    <div className="text-[11px] text-canvas-muted">{r.stokKodu ?? r.id} · {r.turAdi} · {r.kaynakAdi}{r.sezonAdi ? ` · ${r.sezonAdi}` : ''}</div>
                  </td>
                  <td className={td}><Tone tone={STATUS_TONE[r.durum]}>{r.durumAdi}</Tone></td>
                  <td className={`${td} text-right font-mono tabular-nums`}>
                    {fmtInt(r.bilesenSayisi)}
                    {r.bilesenStokMin !== null && r.bilesenStokMin <= 0 && <div className="text-[11px] font-bold text-red-700">stoksuz bileşen</div>}
                  </td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtMoney(r.setFiyati)}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>
                    {fmtMoney(r.listeToplami)}
                    {r.eksikFiyat > 0 && <div className="text-[11px] text-amber-800">{r.eksikFiyat} fiyatsız</div>}
                  </td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtPct(r.indirim)}</td>
                  {meta.me.canSeeCost && <td className={`${td} text-right`}><MarginCell marj={r.marj} oran={r.marjOrani} floor={floor} /></td>}
                  <td className={`${td} text-right font-mono tabular-nums`}>{r.stokKodu ? fmtInt(r.stok) : '—'}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{r.stokKodu ? fmtInt(r.son12Adet) : '—'}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{r.stokKodu ? fmtShort(r.son12Ciro) : '—'}</td>
                </tr>
              ))}
              {!list.data.items.length && (
                <tr><td className={`${td} text-canvas-muted`} colSpan={10}>Bu süzgeçte set yok.</td></tr>
              )}
            </tbody>
          </TableWrap>
          <Pager page={list.data.page} pageSize={list.data.pageSize} total={list.data.total} shown={list.data.items.length}
            loading={list.isLoading} fetching={list.isFetching} onPage={setPage} />
          <p className="mt-2 px-1 text-[11.5px] text-canvas-muted">
            Satış: Logo faturalı satır, iade düşülmüş, setin kendi stok koduyla ({list.data.window[0]} – {list.data.window[1]}). Set cirosu bileşen kitapların
            tek satışına eklenmez. Liste fiyatı: {meta.settings.listPriceSource === 'logo' ? 'Logo satış listesi' : 'CRM kitap kartı'} (KDV dahil).
          </p>
        </section>
      )}
      <NewSetSheet open={creating} meta={meta} onClose={() => setCreating(false)} />
    </>
  );
}

function NewSetSheet({ open, meta, onClose }: { open: boolean; meta: SetsMeta; onClose: () => void }) {
  const qc = useQueryClient();
  const nav = useNavigate();
  const [ad, setAd] = useState('');
  const [tur, setTur] = useState('tematik');
  const [price, setPrice] = useState('');
  const [items, setItems] = useState<ItemInput[]>([]);
  const [names, setNames] = useState<Record<string, string>>({});
  const create = useMutation({
    mutationFn: () => setsApi.create({ ad: ad.trim(), tur, bilesenler: items, setFiyati: parseNum(price) }),
    onSuccess: (s) => {
      qc.invalidateQueries({ queryKey: ['sets'] });
      toast.success('Set taslağı açıldı.');
      onClose();
      setAd(''); setItems([]); setPrice('');
      nav(`/pazarlama/set-hediye/set/${encodeURIComponent(s.id)}`);
    },
    onError: (e) => toast.error(errText(e, 'Set açılamadı.') ?? ''),
  });
  return (
    <Sheet open={open} modal onClose={onClose} title="Yeni set taslağı" subtitle="Taslak portalda durur; onaylanınca CRM'de açılacak kart listesi çıkar.">
      <div className="flex flex-col gap-3 text-[13px]">
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Set adı</span>
          <input className={field} value={ad} onChange={(e) => setAd(e.target.value)} />
        </label>
        <div className="grid grid-cols-2 gap-2">
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Tür</span>
            <select className={field} value={tur} onChange={(e) => setTur(e.target.value)}>
              {Object.entries(meta.types).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Set fiyatı (KDV dahil)</span>
            <input className={`${field} font-mono`} inputMode="decimal" value={price} onChange={(e) => setPrice(e.target.value)} placeholder="Sonra da girilebilir" />
          </label>
        </div>
        <BookPicker onPick={(b) => { setItems((x) => addItem(x, b.stok)); setNames((n) => ({ ...n, [b.stok]: b.ad ?? b.stok })); }} />
        {items.length > 0 && (
          <ul className="flex flex-col gap-1">
            {items.map((i) => (
              <li key={i.stok} className="flex items-center gap-2 rounded-xl bg-slate-50 px-3 py-1.5">
                <span className="min-w-0 flex-1 truncate font-semibold">{names[i.stok] ?? i.stok}</span>
                <input aria-label="Adet" className={`${field} w-20 font-mono`} inputMode="numeric" value={String(i.adet)}
                  onChange={(e) => setItems((x) => x.map((y) => (y.stok === i.stok ? { ...y, adet: Math.max(1, Number(e.target.value) || 1) } : y)))} />
                <button type="button" aria-label="Çıkar" className={btnGhost} onClick={() => setItems((x) => x.filter((y) => y.stok !== i.stok))}>
                  <Trash2 aria-hidden className="h-4 w-4" />
                </button>
              </li>
            ))}
          </ul>
        )}
        <div className="flex flex-wrap justify-end gap-2">
          <button type="button" className={btnGhost} onClick={onClose}>Vazgeç</button>
          <button type="button" className={btnPrimary} disabled={!ad.trim() || !items.length || create.isPending} onClick={() => create.mutate()}>
            Taslağı aç
          </button>
        </div>
      </div>
    </Sheet>
  );
}
