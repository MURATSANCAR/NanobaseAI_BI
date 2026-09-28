import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ArrowDown, ArrowUp, Download, FileText, Package, Plus, Sparkles, Star, Trash2 } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText, field, label as labelCls } from '../admin/ui';
import { Kpi, KpiRow, Pager } from '../editorial/kit';
import { AskSheet } from '../budget/parts';
import {
  EMPTY_FILTERS, STATUS_TONE, cnApi, fmtDay, fmtInt, fmtMoney, fmtMonths, fmtStamp,
  type Catalog, type CatalogItem, type Filters, type Job, type Meta,
} from './api';
import { AlertList, Block, CnFrame, DataAge } from './parts';
import SqlInfo from '../components/SqlInfo';

type ItemEdit = { crmKitapId: string; oneCikan?: boolean; sayfa?: string | null; gerekce?: string; metin?: string | null };
const toEdit = (k: CatalogItem): ItemEdit => ({ crmKitapId: k.crmKitapId, oneCikan: k.oneCikan, sayfa: k.sayfa });

/** Katalog düzenleme: süzgeç ve öneri, kitap listesi (sıra, öne çıkan, sayfa ipucu, metin), canlı fiyat/stok uyarıları,
 *  onay akışı ve tasarımcı paketi. Sıralama telefonda da çalışsın diye yukarı/aşağı düğmeleriyle. */
export default function CatalogEditor() {
  const { id = '' } = useParams();
  const nav = useNavigate();
  const qc = useQueryClient();
  const meta = useQuery({ queryKey: ['cn', 'meta'], queryFn: cnApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const cat = useQuery({ queryKey: ['cn', 'catalog', id], queryFn: () => cnApi.catalog(id), enabled: ENGINE_ENABLED && !!id });
  const [ask, setAsk] = useState<null | 'reject' | 'delete'>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [perPage, setPerPage] = useState<number | null>(null);
  const m = meta.data;
  const c = cat.data;
  const editable = !!(c && m?.me.canCatalog && c.durum === 'taslak');
  const put = (d: Catalog) => qc.setQueryData(['cn', 'catalog', id], d);

  const items = useMutation({
    mutationFn: (list: ItemEdit[]) => cnApi.setItems(id, list),
    onSuccess: (d) => { put(d); qc.invalidateQueries({ queryKey: ['cn', 'suggest', id] }); qc.invalidateQueries({ queryKey: ['cn', 'catalogs'] }); },
    onError: (e) => toast.error(errText(e, 'Liste kaydedilemedi.') ?? ''),
  });
  const accept = useMutation({
    mutationFn: ({ book, tur }: { book: string; tur: string }) => cnApi.accept(id, book, tur),
    onSuccess: put,
    onError: (e) => toast.error(errText(e, 'Uyarı kapatılamadı.') ?? ''),
  });
  const action = useMutation({
    mutationFn: ({ act, note }: { act: string; note?: string }) => cnApi.catalogAction(id, act, note),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['cn'] }); toast.success('Katalog güncellendi.'); setAsk(null); },
    onError: (e) => toast.error(errText(e, 'İşlem yapılamadı.') ?? ''),
  });
  const remove = useMutation({
    mutationFn: () => cnApi.deleteCatalog(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['cn'] }); nav('/katalog-bulten'); },
    onError: (e) => toast.error(errText(e, 'Silinemedi.') ?? ''),
  });
  const zeki = useMutation({
    mutationFn: () => cnApi.zeki(id, { metin: true, gerekce: true }),
    onSuccess: (j) => { setJob(j); toast.success('Zeki AI metin ve gerekçe yazıyor.'); },
    onError: (e) => toast.error(errText(e, 'Zeki AI işi başlatılamadı.') ?? ''),
  });
  const jobQ = useQuery({
    queryKey: ['cn', 'job', job?.id],
    queryFn: () => cnApi.job(job!.id),
    enabled: !!job && (job.durum === 'bekliyor' || job.durum === 'calisiyor'),
    refetchInterval: 3000,
  });
  useEffect(() => {
    const j = jobQ.data;
    if (!j || j.durum === job?.durum && j.adim === job?.adim) return;
    setJob(j);
    if (j.durum === 'bitti') {
      qc.invalidateQueries({ queryKey: ['cn', 'catalog', id] });
      const s = j.sonuc ?? {};
      toast.success(`Zeki AI bitti: ${s.metin ?? 0} metin, ${s.gerekce ?? 0} gerekçe; denetimde düşen cümle ${s.dusen ?? 0}.`);
    } else if (j.durum === 'hata') toast.error(j.hata ?? 'Zeki AI işi hata verdi.');
  }, [jobQ.data]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!ENGINE_ENABLED) return <CnFrame crumb="Katalog" title="Katalog" source="—" presence="—"><Note tone="warn">Veri bağlantısı tanımlı değil.</Note></CnFrame>;
  const list = c?.kitaplar ?? [];
  const save = (next: ItemEdit[]) => items.mutate(next);
  const edits = list.map(toEdit);
  const move = (i: number, d: -1 | 1) => {
    const next = [...edits];
    const j = i + d;
    if (j < 0 || j >= next.length) return;
    [next[i], next[j]] = [next[j], next[i]];
    save(next);
  };
  const patch = (i: number, p: Partial<ItemEdit>) => save(edits.map((e, k) => (k === i ? { ...e, ...p } : e)));
  const pp = perPage ?? m?.ayarlar.pdfSayfa ?? 6;

  return (
    <CnFrame
      crumb="Katalog"
      title={c?.baslik ?? 'Katalog'}
      lead={c ? `${c.turAdi}${c.donem ? ` · ${c.donem}` : ''}${c.tema ? ` · ${c.tema}` : ''} · fiyat: ${c.fiyatKaynagiAdi}` : undefined}
      source={c?.havuz?.okuma ? `Kitap havuzu ${fmtStamp(c.havuz.okuma)}` : 'CRM + Logo'}
      presence={c ? `${c.ozet.kitap} kitap` : '…'}
      back={{ to: '/katalog-bulten', label: 'Kataloglar' }}
      aside={c && m ? (
        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap items-center justify-end gap-2">
            <Pill tone={STATUS_TONE[c.durum] ?? 'muted'}>{c.durumAdi}</Pill>
            {c.onaylayan && <span className="text-[11.5px] text-canvas-muted">onaylayan {c.onaylayan}</span>}
          </div>
          <div className="flex flex-wrap justify-end gap-2">
            {m.me.canCatalog && c.durum === 'taslak' && <button type="button" className={btnPrimary} disabled={action.isPending || !list.length} onClick={() => action.mutate({ act: 'submit' })}>Onaya gönder</button>}
            {m.me.canCatalog && c.durum === 'onayda' && <button type="button" className={btnGhost} onClick={() => action.mutate({ act: 'withdraw' })}>Geri çek</button>}
            {m.me.canApprove && c.durum === 'onayda' && c.gonderen !== m.me.username && (
              <>
                <button type="button" className={btnPrimary} onClick={() => action.mutate({ act: 'approve' })}>Onayla</button>
                <button type="button" className={btnGhost} onClick={() => setAsk('reject')}>Geri gönder</button>
              </>
            )}
            {m.me.canCatalog && c.durum === 'onayli' && <button type="button" className={btnPrimary} onClick={() => action.mutate({ act: 'publish' })}>Yayında işaretle</button>}
            {m.me.canCatalog && ['onayli', 'yayinda', 'arsiv'].includes(c.durum) && <button type="button" className={btnGhost} onClick={() => action.mutate({ act: 'reopen' })}>Taslağa geri al</button>}
            {m.me.canCatalog && ['taslak', 'onayli', 'yayinda'].includes(c.durum) && <button type="button" className={btnGhost} onClick={() => action.mutate({ act: 'archive' })}>Arşivle</button>}
            {m.me.canCatalog && c.durum === 'taslak' && (
              <button type="button" className={btnGhost} aria-label="Kataloğu sil" onClick={() => setAsk('delete')}><Trash2 aria-hidden className="h-4 w-4" /></button>
            )}
          </div>
        </div>
      ) : null}
    >
      {cat.error && <Note tone="err">{errText(cat.error, 'Katalog açılamadı.')}</Note>}
      {cat.isLoading && <Loading />}
      {c && (
        <>
          {c.not && c.durum === 'taslak' && <Note tone="warn">Geri gönderme gerekçesi: {c.not}</Note>}
          {!c.havuz && <Note tone="info">Kitap havuzu okunuyor; uyarılar son kayıtlı hâliyle gösteriliyor.</Note>}
          <DataAge pool={c.havuz} />
          <KpiRow>
            <Kpi label="Kitap" value={fmtInt(c.ozet.kitap)} help={`${c.ozet.oneCikan} öne çıkan`} info={<SqlInfo k={c.kaynaklar} alan="ozet" label="Kitap" />} />
            <Kpi label="Kritik uyarılı kitap" value={fmtInt(c.ozet.uyariliKitap)} help="Fiyat değişti, stok kritik, satıştan kalktı ya da CRM'de kart yok" info={<SqlInfo k={c.kaynaklar} alan="kitaplar[].uyarilar" label="Kritik uyarılı kitap" />} />
            <Kpi label="Fiyatı olmayan" value={fmtInt(c.ozet.fiyatsiz)} help="Seçilen fiyat kaynağında fiyat yok" info={<SqlInfo k={c.kaynaklar} alan="ozet" label="Fiyatı olmayan" />} />
            <Kpi label="Kapağı eksik" value={fmtInt(c.ozet.kapaksiz)} help="CRM'de ve web sitesinde kapak bağlantısı yok" info={<SqlInfo k={c.kaynaklar} alan="ozet" label="Kapağı eksik" />} />
          </KpiRow>

          {m?.me.canExport && (
            <Block title="Tasarımcı paketi ve önizleme" help="Paket: Excel, kapak bağlantıları, tanıtım metinleri ve sayfa düzeni notu. PDF basit önizlemedir; baskıya hazır katalog tasarımcıda dizilir.">
              <div className="flex flex-wrap items-end gap-2">
                <a className={btnPrimary} href={cnApi.packageUrl(id)}><Package aria-hidden className="h-4 w-4" />Tasarım paketi</a>
                <a className={btnGhost} href={cnApi.xlsxUrl(id)}><Download aria-hidden className="h-4 w-4" />Excel</a>
                <label className="flex flex-col gap-1">
                  <span className={labelCls}>Sayfa başına kitap</span>
                  <select className={`${field} w-auto`} value={pp} onChange={(e) => setPerPage(Number(e.target.value))}>
                    {[1, 2, 4, 6, 8, 9, 12].map((n) => <option key={n} value={n}>{n}</option>)}
                  </select>
                </label>
                <a className={btnGhost} href={cnApi.pdfUrl(id, pp)}><FileText aria-hidden className="h-4 w-4" />PDF önizleme</a>
              </div>
            </Block>
          )}

          {editable && m && <Settings c={c} meta={m} />}

          <Block
            info={<SqlInfo k={c.kaynaklar} alan="kitaplar[]" label="Fiyat, stok ve satış hızı" />}
            title="Katalogdaki kitaplar"
            help="Fiyat ve stok bugünkü veriyle hesaplanır; kitabın eklendiği andaki fiyat dayanaktır. «Yeni fiyatı kabul et» dayanağı günceller."
            action={editable && m?.modelVar && list.length > 0 ? (
              <button type="button" className={btnGhost} disabled={zeki.isPending || job?.durum === 'calisiyor' || job?.durum === 'bekliyor'} onClick={() => zeki.mutate()}>
                <Sparkles aria-hidden className="h-4 w-4" />
                {job && (job.durum === 'calisiyor' || job.durum === 'bekliyor') ? (job.adim ?? 'Zeki AI çalışıyor…') : 'Zeki AI: metin ve gerekçe'}
              </button>
            ) : undefined}
          >
            {list.length === 0 && <p className="py-4 text-[12.5px] text-canvas-muted">Henüz kitap yok. Aşağıdaki önerilerden ekleyin.</p>}
            <ol className="flex flex-col gap-2">
              {list.map((k, i) => (
                <ItemRow key={k.crmKitapId} k={k} i={i} n={list.length} editable={editable} busy={items.isPending || accept.isPending}
                  onMove={move} onPatch={patch} onRemove={() => save(edits.filter((_, x) => x !== i))}
                  onAccept={(tur) => accept.mutate({ book: k.crmKitapId, tur })} canAccept={!!m?.me.canCatalog && c.durum !== 'arsiv'} />
              ))}
            </ol>
          </Block>

          {editable && m && <SuggestPanel id={id} c={c} onAdd={(add) => save([...edits, ...add])} busy={items.isPending} />}
        </>
      )}
      <AskSheet open={ask === 'reject'} title="Geri gönder" message="Katalog hazırlayana gerekçeyle geri gider." confirm="Geri gönder" input="Gerekçe" required
        busy={action.isPending} onClose={() => setAsk(null)} onConfirm={(t) => action.mutate({ act: 'reject', note: t })} />
      <AskSheet open={ask === 'delete'} title="Kataloğu sil" message="Taslak katalog ve kitap listesi silinir." confirm="Sil" danger
        busy={remove.isPending} onClose={() => setAsk(null)} onConfirm={() => remove.mutate()} />
    </CnFrame>
  );
}

function ItemRow({ k, i, n, editable, busy, onMove, onPatch, onRemove, onAccept, canAccept }: {
  k: CatalogItem; i: number; n: number; editable: boolean; busy: boolean; canAccept: boolean;
  onMove: (i: number, d: -1 | 1) => void; onPatch: (i: number, p: Partial<ItemEdit>) => void; onRemove: () => void; onAccept: (tur: string) => void;
}) {
  const [page, setPage] = useState(k.sayfa ?? '');
  const [text, setText] = useState(k.metin ?? '');
  useEffect(() => { setPage(k.sayfa ?? ''); setText(k.metin ?? ''); }, [k.sayfa, k.metin]);
  const priceChanged = k.fiyat !== null && k.fiyatDayanak !== null && Math.abs(k.fiyat - k.fiyatDayanak) >= 0.005;
  return (
    <li className={`rounded-2xl border bg-white/80 p-3 ${k.kritik ? 'border-red-200' : 'border-slate-100'}`}>
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start">
        <div className="flex shrink-0 items-center gap-1 sm:flex-col">
          <span className="w-8 text-center font-mono text-[13px] font-bold tabular-nums">{k.sira}</span>
          {editable && (
            <>
              <button type="button" className="grid h-9 w-9 place-items-center rounded-lg bg-slate-100 transition-transform duration-150 ease-out active:scale-[0.97] disabled:opacity-40"
                aria-label="Yukarı taşı" disabled={busy || i === 0} onClick={() => onMove(i, -1)}><ArrowUp aria-hidden className="h-4 w-4" /></button>
              <button type="button" className="grid h-9 w-9 place-items-center rounded-lg bg-slate-100 transition-transform duration-150 ease-out active:scale-[0.97] disabled:opacity-40"
                aria-label="Aşağı taşı" disabled={busy || i === n - 1} onClick={() => onMove(i, 1)}><ArrowDown aria-hidden className="h-4 w-4" /></button>
            </>
          )}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            {k.oneCikan && <Star aria-label="Öne çıkan" className="h-4 w-4 fill-amber-400 text-amber-500" />}
            <span className="break-words text-[14px] font-extrabold">{k.ad ?? k.stokKodu}</span>
            <span className="text-[12px] text-canvas-muted">{k.yazar}</span>
          </div>
          <div className="mt-0.5 flex flex-wrap gap-x-3 gap-y-0.5 text-[11.5px] text-canvas-muted">
            <span className="font-mono">{k.stokKodu}</span>
            {k.marka && <span>{k.marka}</span>}
            {k.hedef && <span>{k.hedef}{k.yasBas || k.yasBit ? ` ${k.yasBas ?? '…'}–${k.yasBit ?? '…'} yaş` : ''}</span>}
          </div>
          <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 font-mono text-[12px] tabular-nums">
            <span>Fiyat {fmtMoney(k.fiyat)}{priceChanged && <span className="text-red-700"> (dayanak {fmtMoney(k.fiyatDayanak)})</span>}</span>
            <span>Stok {fmtInt(k.stokAdet)} · {k.satisYok ? 'son 12 ayda satış yok' : fmtMonths(k.stokAy)}</span>
            {k.yillik !== null && <span>12 ay {fmtInt(k.yillik)} adet</span>}
          </div>
          <AlertList alerts={k.uyarilar} onAccept={canAccept ? onAccept : undefined} busy={busy} />
          {(k.gerekceZeki || k.gerekce) && (
            <p className="mt-1.5 text-[11.5px] leading-snug text-canvas-ink/80">
              <b>Neden katalogda:</b> {k.gerekceZeki ?? k.gerekce}
              {k.gerekceZeki && <span className="text-canvas-muted"> (Zeki AI; olgular: {k.gerekce})</span>}
            </p>
          )}
          <details className="mt-1.5">
            <summary className="inline-flex min-h-8 cursor-pointer items-center text-[11.5px] font-bold text-canvas-violet">
              Katalog metni {k.metin ? `(${k.metinKaynagi === 'zeki' ? 'Zeki AI' : 'elle'})` : k.metinVar ? '(CRM kısa bilgi kullanılır)' : '(yok)'}
            </summary>
            {editable ? (
              <textarea className={`${field} mt-1 min-h-[88px]`} value={text} onChange={(e) => setText(e.target.value)}
                onBlur={() => text !== (k.metin ?? '') && onPatch(i, { metin: text || null })}
                placeholder="Boş bırakılırsa CRM'deki kısa bilgi kullanılır." />
            ) : (
              <p className="mt-1 whitespace-pre-wrap text-[12px] leading-snug">{k.metin ?? '—'}</p>
            )}
          </details>
        </div>
        {editable && (
          <div className="flex shrink-0 flex-wrap items-end gap-2 sm:w-[220px] sm:flex-col sm:items-stretch">
            <button type="button" className={btnGhost} disabled={busy} aria-pressed={k.oneCikan} onClick={() => onPatch(i, { oneCikan: !k.oneCikan })}>
              <Star aria-hidden className={`h-4 w-4 ${k.oneCikan ? 'fill-amber-400 text-amber-500' : ''}`} />
              {k.oneCikan ? 'Öne çıkan' : 'Öne çıkar'}
            </button>
            <label className="flex min-w-0 flex-1 flex-col gap-1">
              <span className={labelCls}>Sayfa ipucu</span>
              <input className={field} value={page} placeholder="Kapak içi, s. 4…" onChange={(e) => setPage(e.target.value)}
                onBlur={() => page !== (k.sayfa ?? '') && onPatch(i, { sayfa: page || null })} />
            </label>
            <button type="button" className={btnGhost} disabled={busy} onClick={onRemove}><Trash2 aria-hidden className="h-4 w-4" />Çıkar</button>
          </div>
        )}
      </div>
    </li>
  );
}

function Settings({ c, meta }: { c: Catalog; meta: Meta }) {
  const qc = useQueryClient();
  const [f, setF] = useState<Filters>({ ...EMPTY_FILTERS, ...c.suzgec });
  const [head, setHead] = useState({ baslik: c.baslik, tur: c.tur, donem: c.donem ?? '', tema: c.tema ?? '', fiyatKaynagi: c.fiyatKaynagi });
  const save = useMutation({
    mutationFn: () => cnApi.updateCatalog(c.id, { ...head, suzgec: f }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['cn', 'catalog', c.id] }); qc.invalidateQueries({ queryKey: ['cn', 'suggest', c.id] }); toast.success('Kaydedildi.'); },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  const num = (v: string) => (v.trim() === '' ? null : Number(v));
  const toggle = (arr: string[], v: string) => (arr.includes(v) ? arr.filter((x) => x !== v) : [...arr, v]);
  return (
    <Block title="Katalog bilgisi ve öneri süzgeci" help="Süzgeç öneri listesini daraltır; hedef kitle, yaş, marka ve anahtar sözcük sert süzgeçtir, özel gün puana eklenir.">
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        <label className="flex flex-col gap-1 sm:col-span-2"><span className={labelCls}>Katalog adı</span>
          <input className={field} value={head.baslik} onChange={(e) => setHead({ ...head, baslik: e.target.value })} /></label>
        <label className="flex flex-col gap-1"><span className={labelCls}>Tür</span>
          <select className={field} value={head.tur} onChange={(e) => setHead({ ...head, tur: e.target.value })}>
            {Object.entries(meta.turler).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select></label>
        <label className="flex flex-col gap-1"><span className={labelCls}>Fiyat kaynağı</span>
          <select className={field} value={head.fiyatKaynagi} onChange={(e) => setHead({ ...head, fiyatKaynagi: e.target.value })}>
            {Object.entries(meta.fiyatKaynaklari).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select></label>
        <label className="flex flex-col gap-1"><span className={labelCls}>Dönem</span>
          <input className={field} value={head.donem} onChange={(e) => setHead({ ...head, donem: e.target.value })} /></label>
        <label className="flex flex-col gap-1"><span className={labelCls}>Tema</span>
          <input className={field} value={head.tema} onChange={(e) => setHead({ ...head, tema: e.target.value })} /></label>
        <label className="flex flex-col gap-1"><span className={labelCls}>Yaş (en az)</span>
          <input className={field} inputMode="numeric" value={f.yasMin ?? ''} onChange={(e) => setF({ ...f, yasMin: num(e.target.value) })} /></label>
        <label className="flex flex-col gap-1"><span className={labelCls}>Yaş (en çok)</span>
          <input className={field} inputMode="numeric" value={f.yasMax ?? ''} onChange={(e) => setF({ ...f, yasMax: num(e.target.value) })} /></label>
        <label className="flex flex-col gap-1"><span className={labelCls}>Marka</span>
          <select className={field} value={f.marka[0] ?? ''} onChange={(e) => setF({ ...f, marka: e.target.value ? [e.target.value] : [] })}>
            <option value="">Hepsi</option>
            {meta.markalar.map((x) => <option key={x} value={x}>{x}</option>)}
          </select></label>
        <label className="flex flex-col gap-1"><span className={labelCls}>Anahtar sözcük</span>
          <input className={field} value={f.anahtar ?? ''} placeholder="tür, Kitaplık, ad…" onChange={(e) => setF({ ...f, anahtar: e.target.value || null })} /></label>
        <label className="flex flex-col gap-1 sm:col-span-2"><span className={labelCls}>Özel gün</span>
          <select className={field} value={f.ozelGun ?? ''} onChange={(e) => setF({ ...f, ozelGun: e.target.value || null })}>
            <option value="">Yok</option>
            {meta.ozelGunler.map((d) => <option key={d.key} value={d.key}>{d.ad} · {d.kitapSayisi} kitap{d.baslangic ? ` · ${fmtDay(d.baslangic)}` : ''}</option>)}
          </select></label>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-2 text-[12.5px]">
        <span className={labelCls}>Hedef kitle</span>
        {meta.hedefler.map((h) => (
          <label key={h} className="inline-flex min-h-9 items-center gap-1.5">
            <input type="checkbox" className="h-4 w-4" checked={f.hedef.includes(h)} onChange={() => setF({ ...f, hedef: toggle(f.hedef, h) })} />{h}
          </label>
        ))}
        <label className="inline-flex min-h-9 items-center gap-1.5">
          <input type="checkbox" className="h-4 w-4" checked={f.yalnizOzelGun} disabled={!f.ozelGun} onChange={(e) => setF({ ...f, yalnizOzelGun: e.target.checked })} />Yalnız özel güne bağlı
        </label>
        <label className="inline-flex min-h-9 items-center gap-1.5">
          <input type="checkbox" className="h-4 w-4" checked={f.yalnizYeni} onChange={(e) => setF({ ...f, yalnizYeni: e.target.checked })} />Yalnız yeni ({meta.ayarlar.yeniAy} ay)
        </label>
        <button type="button" className={`${btnPrimary} ml-auto`} disabled={save.isPending || !head.baslik.trim()} onClick={() => save.mutate()}>Kaydet</button>
      </div>
    </Block>
  );
}

function SuggestPanel({ id, c, onAdd, busy }: { id: string; c: Catalog; onAdd: (add: ItemEdit[]) => void; busy: boolean }) {
  const [page, setPage] = useState(0);
  const [on, setOn] = useState(false);
  const q = useQuery({
    queryKey: ['cn', 'suggest', id, page],
    queryFn: () => cnApi.suggest(id, page),
    enabled: on,
    placeholderData: keepPreviousData,
  });
  const d = q.data;
  const w = Object.entries(c.suzgec).some(([, v]) => (Array.isArray(v) ? v.length : !!v));
  return (
    <Block
      info={<SqlInfo k={d?.kaynaklar} alan="items[]" label="Aday puanı, fiyat ve stok" />}
      title="Önerilen kitaplar"
      help="Puan: satış hızı, stok ay sayısı, yenilik ve (seçildiyse) özel gün bağı; her satırda gerekçe yazar. Satıştan kalkmış ve stoku olmayan kitap önerilmez, sayısı aşağıda."
      action={!on ? <button type="button" className={btnPrimary} onClick={() => setOn(true)}>Önerileri getir</button> : undefined}
    >
      {!on && <p className="text-[12px] text-canvas-muted">{w ? 'Kayıtlı süzgeçle öneri listesi hazırlanır.' : 'Süzgeç yok: bütün havuz puanlanır.'}</p>}
      {q.error && <Note tone="err">{errText(q.error, 'Öneri listesi hazırlanamadı.')}</Note>}
      {on && q.isLoading && <Loading />}
      {d && (
        <>
          <div className="mb-2 flex flex-wrap items-center gap-2 text-[12px] text-canvas-muted">
            <span className="font-mono tabular-nums">{fmtInt(d.total)} aday</span>
            {Object.entries(d.elenen).map(([k, v]) => <span key={k}>· {fmtInt(v)} {k} (önerilmedi)</span>)}
            {d.items.length > 0 && (
              <button type="button" className={`${btnGhost} ml-auto`} disabled={busy}
                onClick={() => onAdd(d.items.map((x) => ({ crmKitapId: x.id, gerekce: x.gerekce })))}>
                <Plus aria-hidden className="h-4 w-4" />Bu sayfadakilerin hepsini ekle ({d.items.length})
              </button>
            )}
          </div>
          <ul className="flex flex-col gap-1.5">
            {d.items.map((x) => (
              <li key={x.id} className="flex flex-col gap-1.5 rounded-xl border border-slate-100 bg-white/80 p-2.5 sm:flex-row sm:items-center">
                <span className="w-12 shrink-0 font-mono text-[13px] font-bold tabular-nums text-canvas-violet">{x.puan.toLocaleString('tr-TR')}</span>
                <div className="min-w-0 flex-1">
                  <div className="break-words text-[13px] font-bold">{x.ad} <span className="font-normal text-canvas-muted">{x.yazar}</span></div>
                  <div className="text-[11.5px] leading-snug text-canvas-muted">{x.gerekce || '—'}</div>
                </div>
                <div className="flex shrink-0 items-center gap-3 font-mono text-[12px] tabular-nums">
                  <span>{fmtMoney(x.fiyat)}</span>
                  <button type="button" className={btnGhost} disabled={busy} onClick={() => onAdd([{ crmKitapId: x.id, gerekce: x.gerekce }])}>
                    <Plus aria-hidden className="h-4 w-4" />Ekle
                  </button>
                </div>
              </li>
            ))}
          </ul>
          <Pager page={page} pageSize={d.pageSize} total={d.total} shown={d.items.length} loading={q.isLoading} fetching={q.isFetching} onPage={setPage} />
        </>
      )}
    </Block>
  );
}
