import { useEffect, useState } from 'react';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Plus, Search } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, Pill, TableWrap, btnGhost, btnPrimary, errText, field, label as labelCls, td, th } from '../admin/ui';
import { Pager, Panel, useDebounced } from '../editorial/kit';
import Sheet from '../editorial/studio/reader/Sheet';
import { budgetApi, fmtDay, fmtInt, fmtMoney, fmtPct, parseNum, type BookTarget, type Plan } from './api';
import { NumField, RatioBar, StatePill } from './parts';
import { InfoLabel } from '../components/SqlInfo';
import type { Kaynaklar } from '../components/sqlInfo';
import { EmptyHint, Explain as TermHint } from '../components/Explain';

const SORTS = [
  ['ciro', 'Hedef ciro'],
  ['adet', 'Hedef adet'],
  ['sapma', 'En büyük açık'],
  ['ad', 'Kitap adı'],
] as const;

const METHOD: Record<string, string> = {
  gecmis: 'Taban dönemin satışı',
  tahmin: 'Zeki AI tahminleme (12 aylık satış)',
  kohort: 'Aynı yayınevinin yeni kitap ortalaması',
  elle: 'Elle eklendi',
};

function Explain({ b }: { b: BookTarget }) {
  const o = b.oneri as Record<string, number | string | null | undefined>;
  const rows: Array<[string, string]> = [['Yöntem', METHOD[String(o.yontem)] ?? '—']];
  if (o.yontem === 'gecmis' || o.yontem === 'tahmin') {
    rows.push(['Taban dönem satışı', `${fmtInt(Number(o.gecmisAdet ?? 0))} adet · ${fmtMoney(Number(o.gecmisCiro ?? 0))}`]);
    if (o.tahminAdet !== null && o.tahminAdet !== undefined) rows.push(['Zeki AI tahminleme (12 ay, temel)', `${fmtInt(Number(o.tahminAdet))} adet`]);
    const band = (b.oneri as { tahminBandi?: { p10: number | null; p50: number | null; p90: number | null; aralik: boolean } | null }).tahminBandi;
    if (band?.aralik) rows.push(['Tahmin aralığı (12 ay)', `muhafazakâr ${fmtInt(Number(band.p10))} · temel ${fmtInt(Number(band.p50))} · iyimser ${fmtInt(Number(band.p90))} adet`]);
    if (o.tahminKantil && o.tahminKantil !== 'p50') rows.push(['Senaryo tabanı', o.tahminKantil === 'p10' ? 'Tahminin alt sınırı (muhafazakâr)' : 'Tahminin üst sınırı (iyimser)']);
  }
  if (o.yontem === 'kohort') {
    rows.push(['Kaynak', String(o.kaynak ?? '—')]);
    rows.push(['Satışta ay başına', `${Number(o.aySatis ?? 0).toLocaleString('tr-TR', { maximumFractionDigits: 1 })} adet`]);
    rows.push(['Bu yıl satışta', `${o.satisAyi ?? '—'} ay`]);
  }
  if (o.hacim !== undefined) rows.push(['Hacim büyümesi', fmtPct(Number(o.hacim))]);
  if (o.fiyat !== undefined) rows.push(['Fiyat artışı', fmtPct(Number(o.fiyat))]);
  if (o.birimFiyat !== undefined) rows.push(['Net birim fiyat', fmtMoney(Number(o.birimFiyat))]);
  if (o.marjKaynak) rows.push(['Marj kaynağı', String(o.marjKaynak)]);
  if (o.adet !== undefined) rows.push(['Veriden hesaplanan öneri', `${fmtInt(Number(o.adet))} adet · ${fmtMoney(Number(o.ciro))} · marj ${fmtPct(o.marj === null ? null : Number(o.marj))}`]);
  return (
    <dl className="grid grid-cols-[minmax(120px,40%)_1fr] gap-x-3 gap-y-1.5 text-[12.5px]">
      {rows.map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="text-canvas-muted">{k}</dt>
          <dd className="font-semibold">{v}</dd>
        </div>
      ))}
    </dl>
  );
}

function BookSheet({ plan, book, editable, onClose, k }: { plan: Plan; book: BookTarget | null; editable: boolean; onClose: () => void; k?: Kaynaklar }) {
  const qc = useQueryClient();
  const [adet, setAdet] = useState('');
  const [ciro, setCiro] = useState('');
  const [marj, setMarj] = useState('');
  const [note, setNote] = useState('');
  useEffect(() => {
    if (!book) return;
    setAdet(String(book.adet));
    setCiro(book.ciro.toLocaleString('tr-TR', { maximumFractionDigits: 2 }));
    setMarj(book.marj === null ? '' : (book.marj * 100).toLocaleString('tr-TR', { maximumFractionDigits: 1 }));
    setNote(book.note ?? '');
  }, [book]);
  const save = useMutation({
    mutationFn: () => {
      const a = parseNum(adet);
      const c = parseNum(ciro);
      const m = parseNum(marj);
      if (a === null || c === null) throw new Error('Adet ve ciro sayı olmalı.');
      return budgetApi.updateBook(plan.id, book!.stokKodu, { adet: a, ciro: c, marj: m === null ? null : m / 100, note });
    },
    onSuccess: () => {
      toast.success('Hedef kaydedildi.');
      qc.invalidateQueries({ queryKey: ['budget'] });
      onClose();
    },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  const remove = useMutation({
    mutationFn: () => budgetApi.deleteBook(plan.id, book!.stokKodu),
    onSuccess: () => {
      toast.success('Kitap plandan çıkarıldı.');
      qc.invalidateQueries({ queryKey: ['budget'] });
      onClose();
    },
    onError: (e) => toast.error(errText(e, 'Çıkarılamadı.') ?? ''),
  });
  const t = book?.izleme;
  return (
    <Sheet open={!!book} onClose={onClose} modal title={book?.ad || book?.stokKodu || ''}
      subtitle={book ? `${book.stokKodu} · ${book.segmentLabel}${book.yayinevi ? ` · ${book.yayinevi}` : ''}${book.ilkYayin ? ` · ilk yayın ${fmtDay(book.ilkYayin)}` : ''}` : undefined}>
      {book && (
        <div className="flex flex-col gap-4">
          {t && (
            <section className="rounded-2xl bg-slate-50 p-3">
              <div className="mb-2 flex items-center justify-between gap-2">
                <h4 className="text-[13px] font-extrabold"><InfoLabel k={k} alan="items[].izleme.gercekCiro" label="Kitabın gerçekleşmesi">Gerçekleşme</InfoLabel></h4>
                <StatePill state={t.durum} />
              </div>
              <RatioBar ratio={book.ciro > 0 ? t.oranCiro : t.oranAdet} state={t.durum} />
              <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-[12px]">
                <dt className="text-canvas-muted"><InfoLabel k={k} alan="items[].izleme.beklenenCiro">Beklenen (bugüne)</InfoLabel></dt>
                <dd className="text-right font-mono tabular-nums">{fmtMoney(t.beklenenCiro)} · {fmtInt(t.beklenenAdet)} ad.</dd>
                <dt className="text-canvas-muted">Gerçekleşen</dt>
                <dd className="text-right font-mono tabular-nums">{fmtMoney(t.gercekCiro)} · {fmtInt(t.gercekAdet)} ad.</dd>
                <dt className="text-canvas-muted"><InfoLabel k={k} alan="items[].izleme.gercekMarj">Gerçek marj</InfoLabel></dt>
                <dd className="text-right font-mono tabular-nums">{t.gercekMarj === null ? 'maliyet kaydı yok' : fmtPct(t.gercekMarj)}</dd>
              </dl>
            </section>
          )}
          <section>
            <h4 className="mb-2 text-[13px] font-extrabold"><InfoLabel k={k} alan="items[].oneri" label="Hedef önerisi">Hedef nasıl önerildi</InfoLabel></h4>
            <Explain b={book} />
            {book.elle && <p className="mt-2 text-[11.5px] text-canvas-muted">Elle düzeltildi: {book.editedBy}{book.editedAt ? `, ${fmtDay(book.editedAt)}` : ''}. Yeniden hesaplamada korunur.</p>}
          </section>
          {editable ? (
            <section className="flex flex-col gap-3">
              <h4 className="text-[13px] font-extrabold">Hedefi düzelt</h4>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                <NumField id="b-adet" label="Net adet" value={adet} onChange={setAdet} />
                <NumField id="b-ciro" label="Net ciro" value={ciro} onChange={setCiro} suffix="₺" />
                <NumField id="b-marj" label="Brüt marj" value={marj} onChange={setMarj} suffix="%" help="Boş: marj hedefi yok" />
              </div>
              <label className="flex flex-col gap-1">
                <span className={labelCls}>Not</span>
                <input className={field} value={note} maxLength={500} onChange={(e) => setNote(e.target.value)} placeholder="Neden değişti (isteğe bağlı)" />
              </label>
              <div className="flex flex-wrap justify-between gap-2">
                <button type="button" className={`${btnGhost} text-red-700`} onClick={() => remove.mutate()} disabled={remove.isPending}>Plandan çıkar</button>
                <button type="button" className={btnPrimary} onClick={() => save.mutate()} disabled={save.isPending}>Kaydet</button>
              </div>
            </section>
          ) : (
            <section className="grid grid-cols-3 gap-2 text-center">
              {[['Net adet', fmtInt(book.adet)], ['Net ciro', fmtMoney(book.ciro)], ['Brüt marj', fmtPct(book.marj)]].map(([name, v]) => (
                <div key={name} className="rounded-xl bg-slate-50 p-2">
                  <div className={labelCls}><InfoLabel k={k} alan="items[].ciro" label={`Hedef · ${name}`}>{name}</InfoLabel></div>
                  <div className="mt-0.5 font-mono text-[13px] font-bold tabular-nums">{v}</div>
                </div>
              ))}
            </section>
          )}
        </div>
      )}
    </Sheet>
  );
}

function AddSheet({ plan, open, onClose }: { plan: Plan; open: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const [code, setCode] = useState('');
  const [adet, setAdet] = useState('');
  const [ciro, setCiro] = useState('');
  const [marj, setMarj] = useState('');
  const add = useMutation({
    mutationFn: () => {
      const a = parseNum(adet);
      const c = parseNum(ciro);
      const m = parseNum(marj);
      if (!code.trim()) throw new Error('Stok kodu boş olamaz.');
      if (a === null || c === null) throw new Error('Adet ve ciro sayı olmalı.');
      return budgetApi.addBook(plan.id, { stokKodu: code.trim(), adet: a, ciro: c, marj: m === null ? null : m / 100 });
    },
    onSuccess: () => {
      toast.success('Kitap plana eklendi.');
      qc.invalidateQueries({ queryKey: ['budget'] });
      setCode(''); setAdet(''); setCiro(''); setMarj('');
      onClose();
    },
    onError: (e) => toast.error(errText(e, 'Eklenemedi.') ?? ''),
  });
  return (
    <Sheet open={open} onClose={onClose} modal title="Kitap ekle" subtitle="Öneride olmayan bir kitaba hedef koyun (ör. taban dönemde satmamış ya da CRM'de henüz yayın tarihi olmayan kitap).">
      <div className="flex flex-col gap-3">
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Stok kodu</span>
          <input className={field} value={code} onChange={(e) => setCode(e.target.value)} placeholder="Logo / CRM stok kodu, ör. 15201.01.4529" />
        </label>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <NumField id="a-adet" label="Net adet" value={adet} onChange={setAdet} />
          <NumField id="a-ciro" label="Net ciro" value={ciro} onChange={setCiro} suffix="₺" />
          <NumField id="a-marj" label="Brüt marj" value={marj} onChange={setMarj} suffix="%" />
        </div>
        <div className="flex justify-end">
          <button type="button" className={btnPrimary} onClick={() => add.mutate()} disabled={add.isPending}>Ekle</button>
        </div>
      </div>
    </Sheet>
  );
}

export default function TargetsTab({ plan, editable, trackable, durum, onDurum }: {
  plan: Plan; editable: boolean; trackable: boolean; durum: string; onDurum: (d: string) => void;
}) {
  const [text, setText] = useState('');
  const [segment, setSegment] = useState('');
  const [yayinevi, setYayinevi] = useState('');
  const [sort, setSort] = useState('ciro');
  const [page, setPage] = useState(0);
  const [open, setOpen] = useState<BookTarget | null>(null);
  const [adding, setAdding] = useState(false);
  const q = useDebounced(text.trim(), 300);
  useEffect(() => setPage(0), [q, segment, yayinevi, sort, durum, plan.id]);

  const list = useQuery({
    queryKey: ['budget', 'books', plan.id, segment, q, yayinevi, sort, page, durum],
    queryFn: () => budgetApi.books(plan.id, { segment, q, yayinevi, sort, page, durum }),
    enabled: ENGINE_ENABLED,
    placeholderData: keepPreviousData,
  });
  const data = list.data;
  const track = trackable && !!data?.izleme.asof;

  return (
    <Panel>
      <div className="mb-3 grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-[1fr_160px_220px_170px_170px_auto]">
        <label className="relative flex items-center">
          <Search aria-hidden className="pointer-events-none absolute left-3 h-4 w-4 text-canvas-muted" />
          <input className={`${field} pl-9`} value={text} onChange={(e) => setText(e.target.value)} placeholder="Kitap adı ya da stok kodu" aria-label="Kitap ara" />
        </label>
        <select className={field} value={segment} onChange={(e) => setSegment(e.target.value)} aria-label="Segment">
          <option value="">Bütün kitaplar</option>
          <option value="yeni">Yeni kitap</option>
          <option value="backlist">Backlist</option>
        </select>
        <select className={field} value={yayinevi} onChange={(e) => setYayinevi(e.target.value)} aria-label="Yayınevi">
          <option value="">Bütün yayınevleri</option>
          {(data?.yayinevleri ?? []).map((y) => <option key={y} value={y}>{y}</option>)}
        </select>
        <select className={field} value={sort} onChange={(e) => setSort(e.target.value)} aria-label="Sıralama">
          {SORTS.filter(([k]) => k !== 'sapma' || track).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
        </select>
        {track ? (
          <select className={field} value={durum} onChange={(e) => onDurum(e.target.value)} aria-label="Durum">
            <option value="">Bütün durumlar</option>
            <option value="sapma">Sapma (eşik altı)</option>
            <option value="izle">İzlenmeli</option>
            <option value="iyi">Hedefte</option>
            <option value="baslamadi">Başlamadı</option>
          </select>
        ) : <span className="hidden lg:block" />}
        {editable && (
          <button type="button" className={btnGhost} onClick={() => setAdding(true)}>
            <Plus aria-hidden className="h-4 w-4" />
            Kitap ekle
          </button>
        )}
      </div>

      {list.isLoading ? <Loading /> : list.error ? <Note tone="err">{errText(list.error, 'Hedefler okunamadı; biraz sonra yeniden deneyin.')}</Note> : !data?.items.length ? (
        <EmptyHint title="Bu süzgeçle kitap yok" why="Aramayı temizleyin ya da segment, yayınevi ve durum seçimlerini «tümü»ne alın." />
      ) : (
        <TableWrap>
          <thead>
            <tr>
              <th className={th}>Kitap</th>
              <th className={th}>Segment</th>
              <th className={`${th} text-right`}><InfoLabel k={data.kaynaklar} alan="items[].adet">Hedef adet</InfoLabel></th>
              <th className={`${th} text-right`}><InfoLabel k={data.kaynaklar} alan="items[].ciro">Hedef ciro</InfoLabel></th>
              <th className={`${th} text-right`}><InfoLabel k={data.kaynaklar} alan="items[].marj">Marj</InfoLabel></th>
              {track && (
                <>
                  <th className={`${th} text-right`}>
                    <span className="inline-flex items-center gap-1">
                      <InfoLabel k={data.kaynaklar} alan="items[].izleme.beklenenCiro">Beklenen</InfoLabel>
                      <TermHint label="Beklenen">Yıllık hedefin, veri son gününe kadar gerçekleşmiş olması gereken kısmı; planın dayandığı geçmiş dönemin aylık satış dağılımına göre hesaplanır.</TermHint>
                    </span>
                  </th>
                  <th className={`${th} text-right`}><InfoLabel k={data.kaynaklar} alan="items[].izleme.gercekCiro">Gerçekleşen</InfoLabel></th>
                  <th className={th}><InfoLabel k={data.kaynaklar} alan="items[].izleme.oranCiro">Oran</InfoLabel></th>
                </>
              )}
            </tr>
          </thead>
          <tbody>
            {data.items.map((b) => (
              <tr key={b.stokKodu} onClick={() => setOpen(b)} className="cursor-pointer border-t border-slate-100 hover:bg-slate-50/80">
                <td className={`${td} max-w-[340px]`}>
                  <button type="button" className="text-left" onClick={(e) => { e.stopPropagation(); setOpen(b); }}>
                    <span className="block font-semibold leading-snug">{b.ad || b.stokKodu}</span>
                    <span className="block text-[11px] text-canvas-muted">{b.stokKodu}{b.yayinevi ? ` · ${b.yayinevi}` : ''}{b.elle ? ' · elle' : ''}</span>
                  </button>
                </td>
                <td className={td}><Pill tone={b.segment === 'yeni' ? 'violet' : 'muted'}>{b.segmentLabel}</Pill></td>
                <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(b.adet)}</td>
                <td className={`${td} text-right font-mono tabular-nums`}>{fmtMoney(b.ciro)}</td>
                <td className={`${td} text-right font-mono tabular-nums`}>{fmtPct(b.marj)}</td>
                {track && b.izleme && (
                  <>
                    <td className={`${td} text-right font-mono tabular-nums`}>{fmtMoney(b.izleme.beklenenCiro)}</td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{fmtMoney(b.izleme.gercekCiro)}</td>
                    <td className={td}>
                      <div className="flex items-center gap-2">
                        <RatioBar ratio={b.ciro > 0 ? b.izleme.oranCiro : b.izleme.oranAdet} state={b.izleme.durum} threshold={data.izleme.esik ?? 0.8} />
                        <StatePill state={b.izleme.durum} />
                      </div>
                    </td>
                  </>
                )}
              </tr>
            ))}
          </tbody>
        </TableWrap>
      )}
      {data && (
        <Pager page={page} pageSize={data.pageSize} total={data.total} shown={data.items.length} loading={list.isLoading}
          fetching={list.isFetching} onPage={setPage} />
      )}
      <BookSheet plan={plan} book={open} editable={editable} onClose={() => setOpen(null)} k={data?.kaynaklar} />
      <AddSheet plan={plan} open={adding} onClose={() => setAdding(false)} />
    </Panel>
  );
}
