import { useState } from 'react';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Sparkles } from 'lucide-react';
import { ENGINE_ENABLED } from '../../engine';
import { Loading, Note, Pill, TableWrap, btnGhost, errText, field, label as labelCls, td, th } from '../../admin/ui';
import { Kpi, KpiRow, Pager, Panel, useDebounced } from '../../editorial/kit';
import { fmtDay, fmtInt, fmtPct } from '../../budget/api';
import { Tabs } from '../../budget/parts';
import { BookCell, Chips, ExportLink } from '../platformKit';
import { trendyolApi } from './api';
import { TrendyolData, TrendyolFrame, tl, useTrendyolMeta } from './parts';

function Range({ bas, bit, onChange }: { bas: string; bit: string; onChange: (b: string, e: string) => void }) {
  return (
    <div className="grid grid-cols-2 gap-2">
      <label className="flex flex-col gap-1"><span className={labelCls}>Başlangıç</span><input type="date" className={field} value={bas} onChange={(e) => onChange(e.target.value, bit)} /></label>
      <label className="flex flex-col gap-1"><span className={labelCls}>Bitiş</span><input type="date" className={field} value={bit} onChange={(e) => onChange(bas, e.target.value)} /></label>
    </div>
  );
}

function OrdersList({ bas, bit, q, canExport }: { bas: string; bit: string; q: string; canExport: boolean }) {
  const [durum, setDurum] = useState('');
  const [page, setPage] = useState(0);
  const r = useQuery({ queryKey: ['trendyol', 'orders', durum, bas, bit, q, page], queryFn: () => trendyolApi.orders({ durum, bas, bit, q, page }), enabled: ENGINE_ENABLED, placeholderData: keepPreviousData });
  const d = r.data;
  return (
    <>
      {d && (
        <KpiRow>
          <Kpi label="Paket" value={fmtInt(d.paketSayisi)} help={d.aralik.bas ? `${fmtDay(d.aralik.bas)} – ${fmtDay(d.aralik.bit)}` : 'Sipariş dosyası yok'} />
          <Kpi label="Adet" value={fmtInt(d.adet)} help="Paket satırlarının toplamı" />
          <Kpi label="Tutar" value={tl(d.tutar)} help="Dosyadaki faturalanacak tutar" />
          <Kpi label="Geciken" value={fmtInt(d.geciken)} help="Termin geçti, kargoya verilmedi" />
        </KpiRow>
      )}
      <Panel>
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <Chips value={durum} onChange={(v) => { setDurum(v); setPage(0); }}
            items={[{ key: '', label: 'Hepsi' }, { key: 'geciken', label: 'Geciken', count: d?.geciken }, ...Object.entries(d?.durumlar ?? {}).map(([k, v]) => ({ key: k, label: k, count: v.paket }))]} />
          <ExportLink show={canExport} href={trendyolApi.exportUrl('siparisler', { durum, bas, bit, q })} />
        </div>
        {r.error && <Note tone="err">{errText(r.error, 'Siparişler açılamadı.')}</Note>}
        {r.isLoading ? <Loading /> : d && (
          <>
            <TableWrap>
              <thead><tr><th className={th}>Paket</th><th className={th}>Kitap</th><th className={`${th} text-right`}>Adet</th><th className={th}>Durum</th><th className={th}>Termin</th></tr></thead>
              <tbody>
                {d.items.map((x) => (
                  <tr key={`${x.paketId}-${x.barkod}`} className="border-t border-slate-100">
                    <td className={td}><div className="font-mono text-[12px]">{x.paketId}</div><div className="text-[11px] text-canvas-muted">{fmtDay(x.tarih)}</div></td>
                    <td className={td}><BookCell name={x.ad} code={x.stokKodu} sub={x.barkod} /></td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(x.adet)}</td>
                    <td className={td}>{x.durum ?? '—'}{x.kargoFirma && <div className="text-[11px] text-canvas-muted">{x.kargoFirma}</div>}</td>
                    <td className={td}>{fmtDay(x.termin)} {x.gecikti && <Pill tone="err">Gecikti</Pill>}</td>
                  </tr>
                ))}
              </tbody>
            </TableWrap>
            <Pager page={d.page} pageSize={d.pageSize} total={d.total} shown={d.items.length} loading={r.isLoading} fetching={r.isFetching} onPage={setPage} />
          </>
        )}
      </Panel>
    </>
  );
}

function ClaimsList({ bas, bit, q, canExport, canDraft }: { bas: string; bit: string; q: string; canExport: boolean; canDraft: boolean }) {
  const qc = useQueryClient();
  const [sinif, setSinif] = useState('');
  const [page, setPage] = useState(0);
  const r = useQuery({ queryKey: ['trendyol', 'claims', sinif, bas, bit, q, page], queryFn: () => trendyolApi.claims({ sinif, bas, bit, q, page }), enabled: ENGINE_ENABLED, placeholderData: keepPreviousData });
  const run = useMutation({
    mutationFn: trendyolApi.classify,
    onSuccess: (o) => {
      qc.invalidateQueries({ queryKey: ['trendyol', 'claims'] });
      toast.success(`Kural: ${o.kural}, Zeki AI: ${o.zeki}, emin değil: ${o.eminDegil}${o.kalan ? `, sıradaki tura kalan: ${o.kalan}` : ''}.`);
    },
    onError: (e) => toast.error(errText(e, 'Sınıflama yapılamadı.') ?? ''),
  });
  const d = r.data;
  return (
    <>
      <Panel>
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <Chips value={sinif} onChange={(v) => { setSinif(v); setPage(0); }}
            items={[{ key: '', label: 'Hepsi' }, ...Object.entries(d?.siniflar ?? {}).map(([k, v]) => ({ key: k, label: k, count: v.talep }))]} />
          <div className="flex gap-2">
            {canDraft && !!d?.sinifsiz && (
              <button type="button" className={btnGhost} onClick={() => run.mutate()} disabled={run.isPending}>
                <Sparkles aria-hidden className="h-4 w-4" />
                Nedenleri sınıfla ({d.sinifsiz})
              </button>
            )}
            <ExportLink show={canExport} href={trendyolApi.exportUrl('iadeler', { sinif, bas, bit, q })} />
          </div>
        </div>
        <p className="mb-2 text-[12px] text-canvas-muted">Sınıf önce kuraldan (anahtar sözcük), kural karar veremezse Zeki AI'ın kapalı listeden seçimiyle; emin olmadığı talep sınıfsız kalır.</p>
        {r.error && <Note tone="err">{errText(r.error, 'İadeler açılamadı.')}</Note>}
        {r.isLoading ? <Loading /> : d && (
          <>
            <TableWrap>
              <thead><tr><th className={th}>Talep</th><th className={th}>Kitap</th><th className={th}>Neden</th><th className={th}>Sınıf</th></tr></thead>
              <tbody>
                {d.items.map((x) => (
                  <tr key={`${x.talepId}-${x.barkod}`} className="border-t border-slate-100">
                    <td className={td}><div className="font-mono text-[12px]">{x.talepId}</div><div className="text-[11px] text-canvas-muted">{fmtDay(x.tarih)}</div></td>
                    <td className={td}><BookCell name={x.ad} code={x.stokKodu} sub={x.barkod} /></td>
                    <td className={`${td} max-w-[42ch] text-[12px]`}>{x.neden ?? '—'}{x.aciklama && <div className="text-canvas-muted">{x.aciklama}</div>}</td>
                    <td className={td}>
                      {x.sinif ?? <span className="text-canvas-muted">{x.yontem === 'emin-degil' ? 'Emin değil' : 'Sınıflanmadı'}</span>}
                      {x.yontem && <div className="text-[11px] text-canvas-muted">{x.yontem === 'kural' ? 'kural' : x.yontem === 'zeki' ? `Zeki AI ${fmtPct(x.olasilik, 0)}` : ''}</div>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </TableWrap>
            <Pager page={d.page} pageSize={d.pageSize} total={d.total} shown={d.items.length} loading={r.isLoading} fetching={r.isFetching} onPage={setPage} />
          </>
        )}
      </Panel>
      {d && d.kitaplar.length > 0 && (
        <Panel>
          <h2 className="text-[15px] font-extrabold">Kitap bazında iade</h2>
          <p className="mb-2 text-[12px] text-canvas-muted">Oran = iade adedi ÷ aynı aralıkta sipariş dosyasındaki adet (sipariş dosyası yoksa boş).</p>
          <TableWrap>
            <thead><tr><th className={th}>Kitap</th><th className={`${th} text-right`}>İade</th><th className={`${th} text-right`}>Sipariş</th><th className={`${th} text-right`}>Oran</th></tr></thead>
            <tbody>
              {d.kitaplar.map((b) => (
                <tr key={b.barkod} className="border-t border-slate-100">
                  <td className={td}><BookCell name={b.ad} code={b.stokKodu} sub={b.barkod} /></td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(b.iadeAdet)}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(b.satisAdet)}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtPct(b.oran)}</td>
                </tr>
              ))}
            </tbody>
          </TableWrap>
        </Panel>
      )}
    </>
  );
}

export default function TrendyolOrders() {
  const meta = useTrendyolMeta();
  const m = meta.data;
  const [tab, setTab] = useState<'siparis' | 'iade'>('siparis');
  const [bas, setBas] = useState('');
  const [bit, setBit] = useState('');
  const [text, setText] = useState('');
  const q = useDebounced(text, 300);
  return (
    <TrendyolFrame
      title="Sipariş ve iade"
      lead="Bekleyen ve geciken paketler, iade nedenleri ve kitap bazında iade oranı. Alıcı adı, adres ve telefon dosyadan içeri alınmaz."
      aside={
        <div className="flex flex-col gap-2">
          <Range bas={bas} bit={bit} onChange={(b, e) => { setBas(b); setBit(e); }} />
          <input className={field} placeholder="Kitap, barkod, paket ya da talep no" value={text} onChange={(e) => setText(e.target.value)} />
        </div>
      }
    >
      <TrendyolData meta={m} />
      <Tabs value={tab} onChange={setTab} tabs={[{ key: 'siparis', label: 'Siparişler' }, { key: 'iade', label: 'İadeler' }]} />
      {tab === 'siparis'
        ? <OrdersList bas={bas} bit={bit} q={q} canExport={!!m?.me.canExport} />
        : <ClaimsList bas={bas} bit={bit} q={q} canExport={!!m?.me.canExport} canDraft={!!m?.me.canDraft} />}
    </TrendyolFrame>
  );
}
