import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Download, Loader2, Sparkles, Trash2 } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, TableWrap, btnGhost, btnPrimary, errText, field, label as labelCls, td, th } from '../admin/ui';
import { Kpi, KpiRow, Panel, Pager, useDebounced } from '../editorial/kit';
import { fmtDay, fmtInt, fmtMoney, fmtPct, fmtShort, parseNum } from '../budget/api';
import { NumField, Tabs } from '../budget/parts';
import { FileDrop } from '../components/FileDrop';
import { MB } from '../components/fileDropRules';
import { channelsApi, coverageText, type ChannelDetail, type ChannelsMeta, type Simulation, type WithK, type YM } from './api';
import { ChannelsFrame, DataBar, Facts, PeriodPicker, deltaTone, signedPct, useChannelsMeta, usePeriod } from './parts';
import SqlInfo, { InfoLabel } from '../components/SqlInfo';
import type { Kaynaklar } from '../components/sqlInfo';

/** M42 kanal detayı (/kanallar/:platform): aylık eğri, cariler, kitap ve iade listeleri, hedef ↔ gerçekleşen, iskonto
 * simülasyonu (marj yetkisi), panel dosyası (kanalın sattığı adet). */

const CRM_ORDER_TYPES: Record<string, string> = { '9': 'Pazaryeri', '14': 'Amazon konsinye', '8': 'B2C', '1': 'B2B', '3': 'Standart' };

function MonthlyChart({ d, k }: { d: ChannelDetail; k?: Kaynaklar }) {
  const data = d.aylik.map((m) => ({ ay: m.ayAdi.slice(0, 3), [String(d.period.yil)]: m.buYil ? Math.round(m.buYil.netCiro) : null, [String(d.period.yil - 1)]: m.gecenYil ? Math.round(m.gecenYil.netCiro) : null }));
  return (
    <Panel>
      <h2 className="flex items-center gap-1 text-[15px] font-extrabold">Ay ay net ciro (kanala satış − iade) <SqlInfo k={k} alan="aylik" label="Ay ay net ciro" /></h2>
      <p className="mb-2 text-[12px] text-canvas-muted">{d.period.kismiAy ? `Son ay ${fmtDay(d.period.veriSonu)} tarihine kadar.` : 'Seçilen aya kadar.'}</p>
      <div className="h-[240px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
            <CartesianGrid vertical={false} stroke="#e2e8f0" />
            <XAxis dataKey="ay" tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
            <YAxis tickFormatter={(v: number) => fmtShort(v)} tick={{ fontSize: 11 }} width={56} tickLine={false} axisLine={false} />
            <Tooltip formatter={(v) => (typeof v === 'number' ? fmtMoney(v) : '—')} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Bar dataKey={String(d.period.yil - 1)} fill="#c4b5fd" radius={[4, 4, 0, 0]} isAnimationActive={false} />
            <Bar dataKey={String(d.period.yil)} fill="#6d28d9" radius={[4, 4, 0, 0]} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </Panel>
  );
}

function BookLists({ platform, p, meta }: { platform: string; p: YM; meta: ChannelsMeta }) {
  const [tab, setTab] = useState<'kitaplar' | 'iadeler'>('kitaplar');
  const [q, setQ] = useState('');
  const [sort, setSort] = useState('netCiro');
  const [page, setPage] = useState(0);
  const dq = useDebounced(q, 300);
  const books = useQuery({
    queryKey: ['channels', 'books', platform, p.yil, p.ay, dq, sort, page],
    queryFn: () => channelsApi.books(platform, { ...p, q: dq, sort, page }),
    enabled: ENGINE_ENABLED && tab === 'kitaplar',
    placeholderData: keepPreviousData,
  });
  const returns = useQuery({
    queryKey: ['channels', 'returns', platform, p.yil, p.ay, page],
    queryFn: () => channelsApi.returns(platform, { ...p, aylar: 3, page }),
    enabled: ENGINE_ENABLED && tab === 'iadeler',
    placeholderData: keepPreviousData,
  });
  const cur = tab === 'kitaplar' ? books : returns;
  const data = cur.data;
  const margin = meta.me.canMargin;
  return (
    <Panel>
      <div className="mb-2 flex flex-wrap items-end justify-between gap-2">
        <Tabs tabs={[{ key: 'kitaplar', label: 'Kitaplar' }, { key: 'iadeler', label: 'Son 3 ayda iade' }] as const} value={tab} onChange={(k) => { setTab(k); setPage(0); }} />
        {meta.me.canExport && (
          <a className={btnGhost} href={channelsApi.exportUrl(tab, { ...p, platform, q: dq || undefined, aylar: 3 })} download>
            <Download aria-hidden className="h-4 w-4" />
            Excel
          </a>
        )}
      </div>
      {tab === 'kitaplar' ? (
        <div className="mb-2 grid grid-cols-1 gap-2 sm:grid-cols-[1fr_200px]">
          <input className={field} placeholder="Kitap adı ya da stok kodu" value={q} onChange={(e) => { setQ(e.target.value); setPage(0); }} aria-label="Kitap ara" />
          <select className={field} value={sort} onChange={(e) => { setSort(e.target.value); setPage(0); }} aria-label="Sıralama">
            <option value="netCiro">Net ciroya göre</option>
            <option value="netAdet">Net adede göre</option>
            <option value="iadeAdet">İade adedine göre</option>
            <option value="iadeOrani">İade oranına göre</option>
            {margin && <option value="marj">Marja göre</option>}
          </select>
        </div>
      ) : (
        returns.data && <p className="mb-2 text-[12px] text-canvas-muted">{returns.data.aralik.bas} – {returns.data.aralik.bit} arası kanaldan dönen adet; sevkiyat adedini düzeltmek için.</p>
      )}
      {cur.isLoading ? <Loading /> : cur.error ? <Note tone="err">{errText(cur.error, 'Liste okunamadı.')}</Note> : !data?.items.length ? (
        <Note tone="info">Kayıt yok.</Note>
      ) : (
        <TableWrap>
          <thead>
            <tr>
              <th className={th}><InfoLabel k={data.kaynaklar} alan="items" label={tab === 'kitaplar' ? 'Kanalın kitapları' : 'Son 3 ayda iade'}>Kitap</InfoLabel></th>
              <th className={`${th} text-right`}><InfoLabel k={data.kaynaklar} alan="items">Kanala satış</InfoLabel></th>
              <th className={`${th} text-right`}><InfoLabel k={data.kaynaklar} alan="items">İade</InfoLabel></th>
              <th className={`${th} text-right`}><InfoLabel k={data.kaynaklar} alan="items">Net adet</InfoLabel></th>
              <th className={`${th} text-right`}><InfoLabel k={data.kaynaklar} alan="items">Net ciro</InfoLabel></th>
              <th className={`${th} text-right`}><InfoLabel k={data.kaynaklar} alan="items">İade oranı</InfoLabel></th>
              {margin && <th className={`${th} text-right`}><InfoLabel k={data.kaynaklar} alan="items">Brüt marj</InfoLabel></th>}
              {margin && <th className={`${th} text-right`}><InfoLabel k={data.kaynaklar} alan="items">Maliyetsiz adet</InfoLabel></th>}
            </tr>
          </thead>
          <tbody>
            {data.items.map((b) => (
              <tr key={b.stokKodu} className="border-t border-slate-100">
                <td className={`${td} max-w-[320px]`}>
                  <div className="font-semibold">{b.ad || b.stokKodu}</div>
                  <div className="font-mono text-[11px] text-canvas-muted">{b.stokKodu}</div>
                </td>
                <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(b.satisAdet)}</td>
                <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(b.iadeAdet)}</td>
                <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(b.netAdet)}</td>
                <td className={`${td} text-right font-mono tabular-nums`}>{fmtMoney(b.netCiro)}</td>
                <td className={`${td} text-right font-mono tabular-nums`}>{fmtPct(b.iadeOrani)}</td>
                {margin && <td className={`${td} text-right font-mono tabular-nums`}>{fmtPct(b.marj ?? null)}</td>}
                {margin && <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(b.maliyetsizAdet)}</td>}
              </tr>
            ))}
          </tbody>
        </TableWrap>
      )}
      {data && (
        <Pager page={data.page} pageSize={data.pageSize} total={data.total} shown={data.items.length} loading={cur.isLoading} fetching={cur.isFetching} onPage={setPage} />
      )}
    </Panel>
  );
}

function TargetsBlock({ d, yil }: { d: ChannelDetail; yil?: number }) {
  const q = useQuery({ queryKey: ['channels', 'targets', yil], queryFn: () => channelsApi.targets(yil), enabled: ENGINE_ENABLED });
  const crm = d.hedef;
  const m46 = q.data?.m46?.platformlar?.[d.platform];
  return (
    <Panel>
      <h2 className="flex items-center gap-1 text-[15px] font-extrabold">Hedef ↔ gerçekleşen <SqlInfo k={q.data?.kaynaklar} alan="crm" label="Hedef ↔ gerçekleşen" /></h2>
      <div className="mt-2 grid grid-cols-1 gap-3 md:grid-cols-2">
        <div className="rounded-xl bg-white/70 p-3">
          <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">CRM satış hedefi (adet)</div>
          {crm ? (
            <>
              <div className="mt-1 font-mono text-[24px] font-bold tabular-nums">{fmtPct(crm.oran, 0)}</div>
              <Facts rows={[['Bölge', crm.bolgeler.join(', ')], ['Yıllık hedef', fmtInt(crm.yillik)], ['Bugüne beklenen', fmtInt(crm.beklenen)], ['Gerçekleşen net adet', fmtInt(crm.gerceklesen)]]} />
            </>
          ) : (
            <p className="mt-1 text-[12px] text-canvas-muted">Bu platforma bağlı CRM hedef bölgesi yok. Bölge ↔ platform eşlemesi Cari eşleme ekranındadır.</p>
          )}
        </div>
        <div className="rounded-xl bg-white/70 p-3">
          <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Bütçeden türetilen kanal hedefi</div>
          {q.isLoading ? <Loading /> : m46 ? (
            <>
              <div className="mt-1 font-mono text-[24px] font-bold tabular-nums">{fmtPct(m46.oran, 0)}</div>
              <Facts rows={[['Yıllık hedef (adet)', fmtInt(m46.hedefAdet)], ['Yıllık hedef (ciro)', fmtMoney(m46.hedefCiro)], ['Bugüne beklenen', fmtInt(m46.beklenenAdet)], ['Gerçekleşen net adet', fmtInt(m46.gerceklesenAdet)]]} />
              <p className="mt-1 text-[11px] leading-snug text-canvas-muted">{q.data?.m46?.yontem}. Bütçede kanal kırılımı yoktur; bu bir paylaştırmadır.</p>
            </>
          ) : (
            <p className="mt-1 text-[12px] text-canvas-muted">{q.data?.m46?.hata ?? (q.data?.m46?.plan === null ? `${yil ?? ''} için yürürlükte bütçe planı yok.` : 'Bu platform için geçen yıl satışı yok.')}</p>
          )}
        </div>
      </div>
    </Panel>
  );
}

function Simulator({ d, p, meta }: { d: ChannelDetail; p: YM; meta: ChannelsMeta }) {
  const qc = useQueryClient();
  const [puan, setPuan] = useState('2');
  const [hacim, setHacim] = useState('0');
  const [res, setRes] = useState<(Simulation & WithK) | null>(null);
  const sim = useMutation({
    mutationFn: (yorum: boolean) => channelsApi.simulate({ platform: d.platform, ...p, iskontoPuan: parseNum(puan) ?? 0, hacimYuzde: parseNum(hacim) ?? 0, yorum }),
    onSuccess: setRes,
    onError: (e) => toast.error(errText(e, 'Simülasyon yapılamadı.') ?? ''),
  });
  const save = useMutation({
    mutationFn: () => channelsApi.addDiscountSuggestion({ platform: d.platform, ...p, iskontoPuan: parseNum(puan) ?? 0, hacimYuzde: parseNum(hacim) ?? 0, yorum: res?.yorum ?? null }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['channels', 'suggestions'] });
      toast.success('İskonto önerisi taslak olarak kaydedildi; kararı başka bir yetkili verir.');
    },
    onError: (e) => toast.error(errText(e, 'Öneri kaydedilemedi.') ?? ''),
  });
  const row = (label: string, a: string, b: string) => (
    <tr className="border-t border-slate-100"><td className={td}>{label}</td><td className={`${td} text-right font-mono tabular-nums`}>{a}</td><td className={`${td} text-right font-mono tabular-nums`}>{b}</td></tr>
  );
  return (
    <Panel>
      <h2 className="flex items-center gap-1 text-[15px] font-extrabold">İskonto simülasyonu {res && <SqlInfo k={res.kaynaklar} alan="once" label="İskonto simülasyonu" />}</h2>
      <p className="mb-2 text-[12px] text-canvas-muted">«İskontoyu şu kadar puan değiştirirsem marj ne olur?» Dönem ortalamasıyla hesaplanır; hiçbir yere yazılmaz. Marj yalnız maliyeti girilmiş satırlardan.</p>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
        <NumField id="sim-puan" label="İskonto değişimi" suffix="puan" value={puan} onChange={setPuan} help="Artı: kanala daha çok iskonto" />
        <NumField id="sim-hacim" label="Adet değişimi (isteğe bağlı)" suffix="%" value={hacim} onChange={setHacim} />
        <div className="flex gap-2">
          <button type="button" className={btnPrimary} onClick={() => sim.mutate(false)} disabled={sim.isPending}>
            {sim.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : null}
            Hesapla
          </button>
          {meta.modelReady && (
            <button type="button" className={btnGhost} onClick={() => sim.mutate(true)} disabled={sim.isPending} title="Zeki AI kısa yorum ekler (rakamlar hesaptan)">
              <Sparkles aria-hidden className="h-4 w-4" />
              Yorumla
            </button>
          )}
        </div>
      </div>
      {res && (
        <div className="mt-3 flex flex-col gap-2">
          <TableWrap>
            <thead><tr><th className={th}></th><th className={`${th} text-right`}><InfoLabel k={res.kaynaklar} alan="once">Bugün</InfoLabel></th><th className={`${th} text-right`}><InfoLabel k={res.kaynaklar} alan="sonra">Senaryo</InfoLabel></th></tr></thead>
            <tbody>
              {row('İskonto oranı', fmtPct(res.once.iskontoOrani), fmtPct(res.sonra.iskontoOrani))}
              {row('Net satış', fmtMoney(res.once.netSatis), fmtMoney(res.sonra.netSatis))}
              {row('Net ciro (iade sonrası)', fmtMoney(res.once.netCiro), fmtMoney(res.sonra.netCiro))}
              {row('Brüt kâr (maliyetli satırlar)', fmtMoney(res.once.brutKar), fmtMoney(res.sonra.brutKar))}
              {row('Brüt marj', fmtPct(res.once.marj), fmtPct(res.sonra.marj))}
            </tbody>
          </TableWrap>
          <p className="text-[12.5px] font-semibold">
            Brüt kâr farkı <span className={deltaTone(res.fark.brutKar)}>{fmtMoney(res.fark.brutKar)}</span>
            {res.basabasHacim !== null && <> · aynı brüt kâr için adet {signedPct(res.basabasHacim)} değişmeli</>}
          </p>
          <p className="text-[11.5px] text-canvas-muted">{res.varsayim} Maliyetli ciro payı {fmtPct(res.maliyetKapsami, 0)}.</p>
          {res.yorum && <Note tone="info"><strong>Zeki AI:</strong> {res.yorum}</Note>}
          {meta.me.canSuggest && (
            <div>
              <button type="button" className={btnGhost} onClick={() => save.mutate()} disabled={save.isPending}>Öneri olarak kaydet</button>
            </div>
          )}
        </div>
      )}
    </Panel>
  );
}

function ExtraCost({ d, meta }: { d: ChannelDetail; meta: ChannelsMeta }) {
  const qc = useQueryClient();
  const cur = meta.extraCosts[d.platform];
  const [v, setV] = useState(cur !== undefined ? String(cur * 100).replace('.', ',') : '');
  const save = useMutation({
    mutationFn: () => {
      const n = parseNum(v);
      return channelsApi.setExtraCost(d.platform, n === null ? null : n / 100);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['channels'] });
      toast.success('Ek kanal maliyeti kaydedildi.');
    },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  return (
    <div className="flex flex-col gap-2 rounded-xl bg-white/70 p-3 sm:flex-row sm:items-end">
      <div className="flex-1">
        <NumField id="ek-maliyet" label="Ek kanal maliyeti (komisyon, kargo, reklam)" suffix="%" value={v} onChange={setV}
          help="Logo'da kanal bazında ayrışmıyor; finans girer. Net cironun yüzdesi. Boş: hesaba katılmaz." />
      </div>
      <button type="button" className={btnGhost} onClick={() => save.mutate()} disabled={save.isPending}>Kaydet</button>
    </div>
  );
}

function Imports({ d, meta }: { d: ChannelDetail; meta: ChannelsMeta }) {
  const qc = useQueryClient();
  const [bas, setBas] = useState('');
  const [bit, setBit] = useState('');
  const [open, setOpen] = useState<string | null>(d.imports[0]?.id ?? null);
  const up = useMutation({
    mutationFn: (f: File) => channelsApi.importFile(d.platform, f, bas || undefined, bit || undefined),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ['channels', 'channel', d.platform] });
      setOpen(r.id);
      toast.success(`${r.satir.toLocaleString('tr-TR')} satır yüklendi, ${r.eslesen.toLocaleString('tr-TR')}'i kitaba bağlandı.`);
    },
    onError: (e) => toast.error(errText(e, 'Dosya yüklenemedi.') ?? ''),
  });
  const del = useMutation({
    mutationFn: (id: string) => channelsApi.deleteImport(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['channels', 'channel', d.platform] });
      setOpen(null);
    },
  });
  const detail = useQuery({ queryKey: ['channels', 'import', open], queryFn: () => channelsApi.importDetail(open!), enabled: ENGINE_ENABLED && !!open });
  return (
    <Panel>
      <h2 className="text-[15px] font-extrabold">Kanalın sattığı (panel dosyası)</h2>
      <p className="mb-2 text-[12px] text-canvas-muted">
        Platform panelinden indirilen satış raporu (Excel/CSV): kanalın son tüketiciye sattığı adet ve kanal stoğu, TİMAŞ'ın aynı dönemde kanala sattığıyla yan yana.
        Yalnız ürün, adet, tutar ve stok kolonları alınır; müşteri adı, adres gibi kolonlar içeri alınmaz.
      </p>
      {/* Yükleme her zaman görünür; yetkisi olmayan kişi kilitli alanı ve gereken yetkiyi görür. */}
      <div className="mb-3 grid grid-cols-1 gap-2 sm:grid-cols-[minmax(0,180px)_minmax(0,180px)_minmax(0,1fr)] sm:items-start">
        <label className="flex flex-col gap-1"><span className={labelCls}>Dönem başı (isteğe bağlı)</span><input type="date" className={field} value={bas} onChange={(e) => setBas(e.target.value)} /></label>
        <label className="flex flex-col gap-1"><span className={labelCls}>Dönem sonu (isteğe bağlı)</span><input type="date" className={field} value={bit} onChange={(e) => setBit(e.target.value)} /></label>
        <FileDrop
          size="sm"
          title="Panel dosyası yükle"
          accept=".xlsx,.csv"
          maxBytes={25 * MB}
          feature="kanal.yukle"
          allowed={meta.me.canImport}
          busy={up.isPending}
          onPick={(f) => up.mutate(f)}
        />
      </div>
      {!d.imports.length ? <Note tone="info">Bu platform için yüklenmiş panel dosyası yok. Platform panelinden indirdiğiniz satış raporunu yukarıdaki alana bırakın.</Note> : (
        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap gap-1.5">
            {d.imports.map((r) => (
              <button key={r.id} type="button" onClick={() => setOpen(r.id)}
                className={`min-h-9 rounded-lg px-2.5 text-[12px] font-bold transition-colors duration-150 ${open === r.id ? 'bg-canvas-violet text-white' : 'bg-slate-100'}`}>
                {r.dosya || 'dosya'} · {fmtDay(r.tarih)}
              </button>
            ))}
          </div>
          {detail.isLoading ? <Loading /> : detail.data && (
            <>
              <p className="text-[12px] text-canvas-muted">
                {detail.data.donemBas ?? '—'} – {detail.data.donemBit ?? '—'} · {detail.data.satir} satır, {detail.data.eslesmeyen} satır kitaba bağlanamadı
                {detail.data.kolonlar.kisiselOlabilir?.length ? ` · içeri alınmayan kolonlar: ${detail.data.kolonlar.kisiselOlabilir.join(', ')}` : ''}
                · kanala satış ayları {detail.data.kanalaSatisAylari.join(', ') || '—'}
                <SqlInfo k={detail.data.kaynaklar} alan="satir" label="Panel dosyası satırları" className="ml-1" />
              </p>
              <TableWrap>
                <thead><tr><th className={th}>Kitap</th><th className={`${th} text-right`}><InfoLabel k={detail.data.kaynaklar} alan="items">Kanalın sattığı</InfoLabel></th><th className={`${th} text-right`}><InfoLabel k={detail.data.kaynaklar} alan="items">TİMAŞ'ın kanala sattığı</InfoLabel></th><th className={`${th} text-right`}><InfoLabel k={detail.data.kaynaklar} alan="items">Oran</InfoLabel></th><th className={`${th} text-right`}><InfoLabel k={detail.data.kaynaklar} alan="items">Kanal stoğu</InfoLabel></th></tr></thead>
                <tbody>
                  {detail.data.items.map((x) => (
                    <tr key={x.stokKodu} className="border-t border-slate-100">
                      <td className={td}><div className="font-semibold">{x.ad || x.stokKodu}</div><div className="font-mono text-[11px] text-canvas-muted">{x.stokKodu}</div></td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(x.kanalSatis)}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(x.kanalaSatis)}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{fmtPct(x.oran, 0)}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{x.kanalStok === null ? '—' : fmtInt(x.kanalStok)}</td>
                    </tr>
                  ))}
                </tbody>
              </TableWrap>
              {meta.me.canImport && (
                <div>
                  <button type="button" className={btnGhost} onClick={() => open && del.mutate(open)} disabled={del.isPending}>
                    <Trash2 aria-hidden className="h-4 w-4" />
                    Bu yüklemeyi sil
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </Panel>
  );
}

export default function Channel() {
  const { platform = '' } = useParams();
  const meta = useChannelsMeta();
  const m = meta.data;
  const { yil, ay, set } = usePeriod(m);
  const p: YM = { yil, ay };
  const q = useQuery({
    queryKey: ['channels', 'channel', platform, yil, ay],
    queryFn: () => channelsApi.channel(platform, p),
    enabled: ENGINE_ENABLED && !!m && !!yil && !!m.years.length,
  });
  const d = q.data;
  const canMargin = !!m?.me.canMargin;
  const label = d?.label ?? m?.platforms.find((x) => x.key === platform)?.label ?? platform;
  return (
    <ChannelsFrame
      back
      title={label}
      detail={label}
      lead="Kanala satış, iskonto, iade ve marj; kitap bazında alım ve iade, hedef gerçekleşmesi. Rakamlar Logo faturalı satırlarından, onaylı cari eşlemesiyle."
      aside={<PeriodPicker meta={m} yil={yil} ay={ay} onChange={set} />}
    >
      <DataBar meta={m} yil={yil} />
      {q.error && <Note tone="err">{errText(q.error, 'Kanal açılamadı.')}</Note>}
      {q.isLoading && <Loading />}
      {d && m && (
        <>
          <KpiRow>
            <Kpi label="Net ciro" value={`${fmtShort(d.donem.netCiro)} ₺`} help={`Geçen yıla göre ${signedPct(d.degisim)} · ${d.period.yil} Ocak–${d.period.ayAdi}`}
              info={<SqlInfo k={d.kaynaklar} alan="donem" label="Net ciro" />} />
            <Kpi label="İskonto oranı" value={fmtPct(d.donem.iskontoOrani)} help={`Geçen yıl ${fmtPct(d.gecenYil?.iskontoOrani ?? null)}`}
              info={<SqlInfo k={d.kaynaklar} alan="donem" label="İskonto oranı" />} />
            <Kpi label="İade oranı" value={fmtPct(d.donem.iadeOrani)} help={`Adette ${fmtPct(d.donem.iadeAdetOrani)} · geçen yıl ${fmtPct(d.gecenYil?.iadeOrani ?? null)}`}
              info={<SqlInfo k={d.kaynaklar} alan="donem" label="İade oranı" />} />
            {canMargin ? (
              <Kpi label="Brüt marj" value={fmtPct(d.donem.marj ?? null)} help={`İade sonrası ${fmtPct(d.donem.iadeSonrasiMarj ?? null)}${d.donem.katkiMarj !== undefined ? ` · ek maliyet sonrası ${fmtPct(d.donem.katkiMarj ?? null)}` : ''}`}
                info={<SqlInfo k={d.kaynaklar} alan="donem" label="Brüt marj" />} />
            ) : (
              <Kpi label="Net adet" value={fmtShort(d.donem.netAdet)} help={`Kanala satış ${fmtShort(d.donem.satisAdet)} · iade ${fmtShort(d.donem.iadeAdet)}`}
                info={<SqlInfo k={d.kaynaklar} alan="donem" label="Net adet" />} />
            )}
          </KpiRow>
          {canMargin && (
            <Note tone="info">
              <SqlInfo k={d.kaynaklar} alan="donem" label="Maliyet kapsamı" className="mr-1" />
              {coverageText(d.donem)} (maliyetsiz ciro {fmtMoney(d.donem.maliyetsizCiro)}).
              {d.donem.m9 ? <> Birim maliyet modülüyle tamamlanınca marj {fmtPct(d.donem.m9.marj)} (kapsam {fmtPct(d.donem.m9.kapsam, 0)}); {d.donem.m9.bilinmeyenKitap} kitabın birim maliyeti bilinmiyor ({fmtMoney(d.donem.m9.bilinmeyenCiro)}).</> : !d.m9Bagli ? ' Birim maliyet modülü bu kurulumda bağlı değil.' : ''}
            </Note>
          )}
          <MonthlyChart d={d} k={d.kaynaklar} />
          <Panel>
            <h2 className="flex items-center gap-1 text-[15px] font-extrabold">Cariler <SqlInfo k={d.kaynaklar} alan="cariler" label="Platformun carileri" /></h2>
            <p className="mb-2 text-[12px] text-canvas-muted">Bu platforma eşlenen Logo carileri ve kanal kodları. CRM sipariş sayısı son {d.crmSiparisGun ?? '—'} gün.</p>
            <TableWrap>
              <thead><tr><th className={th}>Cari</th><th className={th}>Kanal kodu</th><th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="cariler">Net ciro</InfoLabel></th><th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="cariler">İade oranı</InfoLabel></th><th className={th}><InfoLabel k={d.kaynaklar} alan="cariler">CRM siparişi</InfoLabel></th></tr></thead>
              <tbody>
                {d.cariler.map((c) => (
                  <tr key={c.grup} className="border-t border-slate-100">
                    <td className={td}><div className="font-semibold">{c.ad}</div><div className="font-mono text-[11px] text-canvas-muted">{c.grup}</div></td>
                    <td className={td}>{c.kanal ?? '—'}</td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{fmtMoney(c.donem.netCiro)}</td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{fmtPct(c.donem.iadeOrani)}</td>
                    <td className={`${td} text-[11.5px]`}>{c.crmSiparis ? Object.entries(c.crmSiparis).map(([k, v]) => `${CRM_ORDER_TYPES[k] ?? `Tip ${k}`}: ${v}`).join(' · ') : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </TableWrap>
          </Panel>
          <BookLists platform={platform} p={p} meta={m} />
          {platform !== 'eslenmemis' && <TargetsBlock d={d} yil={d.period.yil} />}
          {canMargin && platform !== 'eslenmemis' && (
            <>
              <Simulator d={d} p={p} meta={m} />
              <ExtraCost d={d} meta={m} />
            </>
          )}
          {platform !== 'eslenmemis' && <Imports key={d.platform} d={d} meta={m} />}
        </>
      )}
    </ChannelsFrame>
  );
}
