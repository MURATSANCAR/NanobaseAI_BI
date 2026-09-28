import { useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Loader2, Upload } from 'lucide-react';
import { ENGINE_ENABLED } from '../../engine';
import { Loading, Note, Pill, TableWrap, btnGhost, btnPrimary, errText, field, td, th } from '../../admin/ui';
import { Kpi, KpiRow, Pager, Panel, useDebounced } from '../../editorial/kit';
import { fmtInt, fmtPct, fmtShort } from '../../budget/api';
import { channelsApi } from '../api';
import { signedPct } from '../parts';
import { BookCell, ExportLink } from '../platformKit';
import { amazonApi, type Candidate } from './api';
import { AmazonData, AmazonFrame, money, tl, useAmazonMeta } from './parts';

const CRM_TYPES: Record<string, string> = { '14': 'Amazon Konsinye' };
const CAND: Record<Candidate['durum'], { label: string; tone: 'ok' | 'warn' | 'muted' | 'violet' | 'err' }> = {
  onayli: { label: 'Amazon olarak onaylı', tone: 'ok' },
  aday: { label: 'Aday — onay bekliyor', tone: 'violet' },
  bekliyor: { label: 'Eşleme listesinde', tone: 'muted' },
  'listede-yok': { label: 'Eşleme listesinde yok', tone: 'warn' },
  'baska-platform': { label: 'Başka platforma bağlı', tone: 'muted' },
};

function Accounts({ canMap }: { canMap: boolean }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['amazon', 'accounts'], queryFn: amazonApi.accounts, enabled: ENGINE_ENABLED });
  const add = useMutation({
    mutationFn: (kod: string) => amazonApi.addAccount(kod),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['amazon', 'accounts'] });
      toast.success('Cari eşleme listesine aday olarak eklendi; onay Cari eşleme ekranında.');
    },
    onError: (e) => toast.error(errText(e, 'Eklenemedi.') ?? ''),
  });
  const d = q.data;
  return (
    <Panel>
      <h2 className="text-[15px] font-extrabold">Amazon carileri</h2>
      <p className="mb-2 text-[12px] text-canvas-muted">Logo'da unvanında {d?.desenler?.join(', ') ?? '—'} geçen cariler ve eşleme durumu. Karne ve konsinye yalnız onaylı carileri sayar.</p>
      {q.isLoading ? <Loading /> : !d?.adayCariler.length ? <Note tone="info">{d?.okundu ? 'Bu adla cari bulunmadı.' : '«Veriyi yenile» Logo carilerini okur.'}</Note> : (
        <TableWrap>
          <thead><tr><th className={th}>Cari</th><th className={th}>Kanal kodu</th><th className={th}>Eşleme</th><th className={th} /></tr></thead>
          <tbody>
            {d.adayCariler.map((c) => (
              <tr key={c.cariKodu} className="border-t border-slate-100">
                <td className={td}><div className="font-semibold">{c.unvan ?? '—'}</div><div className="font-mono text-[11px] text-canvas-muted">{c.cariKodu}</div></td>
                <td className={td}>{c.kanal || '—'}</td>
                <td className={td}><Pill tone={CAND[c.durum].tone}>{CAND[c.durum].label}</Pill></td>
                <td className={`${td} text-right`}>
                  {canMap && (c.durum === 'listede-yok' || c.durum === 'bekliyor') && (
                    <button type="button" className={btnGhost} disabled={add.isPending} onClick={() => add.mutate(c.cariKodu)}>Aday olarak ekle</button>
                  )}
                  {c.durum === 'aday' && <Link className="text-[12px] font-bold text-canvas-violet hover:underline" to="/kanallar/eslesme">Onaya git</Link>}
                </td>
              </tr>
            ))}
          </tbody>
        </TableWrap>
      )}
      {d?.toptan.cariSatirlari && d.toptan.cariSatirlari.length > 0 && (
        <div className="mt-3">
          <h3 className="mb-1 text-[13px] font-extrabold">Onaylı carilerde faturalı satış ({d.toptan.period?.yil} Ocak–{d.toptan.period?.ayAdi})</h3>
          <TableWrap>
            <thead><tr><th className={th}>Cari</th><th className={`${th} text-right`}>Net ciro</th><th className={`${th} text-right`}>Net adet</th><th className={th}>CRM siparişi (son {d.toptan.crmSiparisGun ?? '—'} gün)</th></tr></thead>
            <tbody>
              {d.toptan.cariSatirlari.map((c) => (
                <tr key={c.grup} className="border-t border-slate-100">
                  <td className={td}><div className="font-semibold">{c.ad}</div><div className="font-mono text-[11px] text-canvas-muted">{c.grup}</div></td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{tl(c.netCiro)}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(c.netAdet)}</td>
                  <td className={`${td} text-[11.5px]`}>{c.crmSiparis ? Object.entries(c.crmSiparis).map(([k, v]) => `${CRM_TYPES[k] ?? `Tip ${k}`}: ${v}`).join(' · ') : '—'}</td>
                </tr>
              ))}
            </tbody>
          </TableWrap>
        </div>
      )}
    </Panel>
  );
}

function Books({ canExport }: { canExport: boolean }) {
  const [page, setPage] = useState(0);
  const [text, setText] = useState('');
  const q = useDebounced(text, 300);
  const r = useQuery({ queryKey: ['amazon', 'books', q, page], queryFn: () => amazonApi.books({ q, page }), enabled: ENGINE_ENABLED, placeholderData: keepPreviousData, retry: false });
  const d = r.data;
  return (
    <Panel>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-[15px] font-extrabold">Amazon'a faturalanan kitaplar</h2>
        <div className="flex gap-2">
          <input className={`${field} sm:w-64`} placeholder="Kitap ya da stok kodu" value={text} onChange={(e) => setText(e.target.value)} />
          <ExportLink show={canExport} href={amazonApi.exportUrl('kitaplar', { q })} />
        </div>
      </div>
      {r.error ? <Note tone="info">{errText(r.error, 'Liste açılamadı.')}</Note> : r.isLoading ? <Loading /> : d && (
        <>
          <TableWrap>
            <thead><tr><th className={th}>Kitap</th><th className={`${th} text-right`}>Sevk (faturalı)</th><th className={`${th} text-right`}>İade</th><th className={`${th} text-right`}>Net adet</th><th className={`${th} text-right`}>Net ciro</th></tr></thead>
            <tbody>
              {d.items.map((x) => (
                <tr key={x.stokKodu} className="border-t border-slate-100">
                  <td className={td}><BookCell name={x.ad} code={x.stokKodu} /></td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(x.satisAdet)}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(x.iadeAdet)}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(x.netAdet)}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{tl(x.netCiro)}</td>
                </tr>
              ))}
            </tbody>
          </TableWrap>
          <Pager page={d.page} pageSize={d.pageSize} total={d.total} shown={d.items.length} loading={r.isLoading} fetching={r.isFetching} onPage={setPage} />
        </>
      )}
    </Panel>
  );
}

/** Amazon satıcı panelinden indirilen satış raporu: M42'nin panel dosyası yüklemesiyle (platform = amazon). */
function SalesReport({ canImport }: { canImport: boolean }) {
  const qc = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const list = useQuery({ queryKey: ['channels', 'imports', 'amazon'], queryFn: () => channelsApi.imports('amazon'), enabled: ENGINE_ENABLED, retry: false });
  const up = useMutation({
    mutationFn: (f: File) => channelsApi.importFile('amazon', f),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ['channels', 'imports', 'amazon'] });
      toast.success(`${fmtInt(r.satir)} satır yüklendi, ${fmtInt(r.eslesen)}'i kitaba bağlandı.`);
    },
    onError: (e) => toast.error(errText(e, 'Dosya yüklenemedi.') ?? ''),
  });
  return (
    <Panel>
      <h2 className="text-[15px] font-extrabold">Amazon'un sattığı (panel raporu)</h2>
      <p className="mb-2 text-[12px] text-canvas-muted">
        Satıcı panelinden indirilen satış raporu (Excel/CSV): Amazon'un son tüketiciye sattığı adet ve kanal stoğu. Karşılaştırma kanal karnesinin Amazon sayfasında.
        Müşteri kolonları içeri alınmaz.
      </p>
      {canImport && (
        <>
          <input ref={input} type="file" accept=".xlsx,.csv" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (f) up.mutate(f); e.target.value = ''; }} />
          <button type="button" className={btnPrimary} onClick={() => input.current?.click()} disabled={up.isPending}>
            {up.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Upload aria-hidden className="h-4 w-4" />}
            Rapor yükle
          </button>
        </>
      )}
      {list.data && (
        <p className="mt-2 text-[12px] text-canvas-muted">
          {list.data.items.length ? `${list.data.items.length} yükleme; son: ${list.data.items[0].dosya ?? '—'}.` : 'Henüz yükleme yok.'}{' '}
          <Link to="/kanallar/amazon" className="font-bold text-canvas-violet hover:underline">Kanal sayfasında aç</Link>
        </p>
      )}
    </Panel>
  );
}

export default function AmazonHome() {
  const meta = useAmazonMeta();
  const m = meta.data;
  const q = useQuery({ queryKey: ['amazon', 'overview'], queryFn: amazonApi.overview, enabled: ENGINE_ENABLED });
  const d = q.data;
  const y = d?.yurtdisi;
  return (
    <AmazonFrame
      title="Amazon ve yurtdışı"
      lead="Amazon carilerine faturalı satış, konsinyede kalan, yurtdışı kanal satışı ve satılmış yabancı haklar. Rakamlar Logo ve CRM'den; Amazon hesabına hiçbir şey gönderilmez."
    >
      <AmazonData meta={m} />
      {m && <Note tone="info">{m.api.neden}</Note>}
      {q.error && <Note tone="err">{errText(q.error, 'Özet açılamadı.')}</Note>}
      {q.isLoading && <Loading />}
      {d && (
        <>
          <KpiRow>
            <Kpi label="Amazon net ciro" value={d.toptan.donem ? `${fmtShort(d.toptan.donem.netCiro)} ₺` : '—'}
              help={d.toptan.donem ? `${d.toptan.period?.yil} · geçen yıla göre ${signedPct(d.toptan.degisim)} · iade ${fmtPct(d.toptan.donem.iadeOrani)}` : (d.toptan.neden ?? '—')} />
            <Kpi label="Konsinyede kalan" value={d.konsinye ? fmtInt(d.konsinye.kalan) : '—'} help={d.konsinye ? `${fmtInt(d.konsinye.kitap)} kitap · faturalanmamış sevk ${fmtInt(d.konsinye.sevk)} − iade ${fmtInt(d.konsinye.iade)}` : 'Henüz okunmadı'} />
            <Kpi label="Yurtdışı net ciro" value={y?.netCiro !== undefined ? `${fmtShort(y.netCiro)} ₺` : '—'}
              help={y?.hata ?? (y?.yil ? `${y.yil} · ${fmtInt(y.ulkeSayisi ?? 0)} ülke · geçen yıl aynı dönem ${fmtShort(y.gecenYilAyniDonem ?? 0)} ₺` : 'Henüz okunmadı')} />
            <Kpi label="Satılmış yabancı hak" value={d.haklar ? fmtInt(d.haklar.kitap) : '—'} help={d.haklar ? `${fmtInt(d.haklar.sozlesme)} Telif Satış sözleşmesi` : 'CRM okunmadı'} />
          </KpiRow>
          {y?.dovizToplam && Object.keys(y.dovizToplam).length > 0 && (
            <Note tone="info">
              Döviz cinsinden yurtdışı net: {Object.entries(y.dovizToplam).map(([k, v]) => money(v, k)).join(' · ')} (fatura kuruyla). Bu yıl döviz faturası: {fmtInt(y.dovizFatura?.toplam ?? 0)} (satış {fmtInt(y.dovizFatura?.satis ?? 0)}).
            </Note>
          )}
          {d.crm.siparis && (
            <Note tone="info">CRM Amazon Konsinye siparişi (tip {d.crm.tip}): {Object.entries(d.crm.siparis).map(([k, v]) => `${k}: ${fmtInt(v)}`).join(' · ')}.</Note>
          )}
          {d.crm.ulkeHatasi && <Note tone="warn">{d.crm.ulkeHatasi}</Note>}
          <Accounts canMap={!!m?.me.canMap} />
          <Books canExport={!!m?.me.canExport} />
          <SalesReport canImport={!!m?.me.canImport} />
        </>
      )}
    </AmazonFrame>
  );
}
