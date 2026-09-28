import { useState } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { AlertTriangle, FileText, Loader2, Pencil, RefreshCw, Share2, Sparkles } from 'lucide-react';
import { ENGINE_ENABLED } from '../../engine';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText, field, label as labelCls } from '../../admin/ui';
import Sheet from '../../editorial/studio/reader/Sheet';
import { AskSheet } from '../../budget/parts';
import { fmtDay, fmtStamp } from '../api';
import { Block, MarketingFrame } from '../parts';
import SqlInfo from '../../components/SqlInfo';
import { FIELD_SOURCE, FOY_TONE, fieldText, isMonth, monthApi, monthLabel, type Foy, type FoyField } from './api';

/** Tek föy: telefonda önce önizleme (bayide gösterilen yüz) ve «Paylaş / PDF», sonra alanlar ve kaynakları, onay. */

const money = (v: unknown) =>
  typeof v === 'number' ? `${new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 2 }).format(v)} TL` : '—';

function Preview({ f }: { f: Foy }) {
  const v = Object.fromEntries(f.alanlar.map((a) => [a.key, a.deger])) as Record<string, unknown>;
  const args = Array.isArray(v.argumanlar) ? (v.argumanlar as string[]) : fieldText(v.argumanlar).split('\n').filter(Boolean);
  return (
    <article className="rounded-2xl bg-white p-4 shadow-glass-float">
      <div className="flex items-start justify-between gap-2 text-[10.5px] font-bold uppercase tracking-wide text-canvas-muted">
        <span>Satış föyü · {monthLabel(f.donem)}</span>
        {f.durum !== 'onayli' || f.eski ? <span className="text-red-700">Taslak</span> : <span className="text-emerald-700">Onaylı</span>}
      </div>
      <h2 className="mt-1 break-words text-[20px] font-extrabold leading-tight tracking-tight">{(v.ad as string) ?? f.stokKodu}</h2>
      <p className="text-[13px] font-semibold">{(v.yazar as string) ?? '—'}</p>
      <p className="text-[11.5px] text-canvas-muted">{[v.yayinevi, v.kitaplik, v.dizi].filter(Boolean).join(' · ') || '—'}</p>
      <div className="mt-3 rounded-xl bg-canvas-violet/10 px-3 py-2">
        <div className="flex items-center gap-1 text-[10.5px] font-bold uppercase tracking-wide text-canvas-violet">Tavsiye edilen satış fiyatı (KDV dahil)<SqlInfo k={f.kaynaklar} alan="alanlar[]" label="Föy fiyatı ve künye" /></div>
        <div className="font-mono text-[20px] font-extrabold tabular-nums">{money(v.fiyat)}</div>
      </div>
      <dl className="mt-3 grid grid-cols-[96px_1fr] gap-x-2 gap-y-1 text-[12px]">
        {([['Yayın', fmtDay((v.yayinTarihi as string) ?? null)], ['Hedef kitle', v.hedefKitle], ['Barkod', v.barkod], ['Sayfa', v.sayfa], ['Ebat', v.ebat], ['Cilt', v.cilt]] as const).map(([k, x]) => (
          <div key={k} className="contents">
            <dt className="text-canvas-muted">{k}</dt>
            <dd className="min-w-0 break-words font-semibold">{fieldText(x) || '—'}</dd>
          </div>
        ))}
      </dl>
      {args.length > 0 && (
        <>
          <h3 className="mt-3 text-[12px] font-extrabold">Neden satılır</h3>
          <ul className="mt-1 list-disc pl-5 text-[12.5px] leading-snug">{args.map((a) => <li key={a}>{a}</li>)}</ul>
        </>
      )}
      {!!v.tanitim && (
        <>
          <h3 className="mt-3 text-[12px] font-extrabold">Tanıtım</h3>
          <p className="mt-1 whitespace-pre-line text-[12.5px] leading-snug">{fieldText(v.tanitim)}</p>
        </>
      )}
    </article>
  );
}

type Ask = null | 'submit' | 'approve' | 'reject' | 'refresh';

export default function FoyScreen() {
  const { stok = '' } = useParams();
  const [params] = useSearchParams();
  const qc = useQueryClient();
  const ay = isMonth(params.get('ay')) ? (params.get('ay') as string) : undefined;
  const [edit, setEdit] = useState<FoyField | null>(null);
  const [value, setValue] = useState('');
  const [ask, setAsk] = useState<Ask>(null);
  const [sharing, setSharing] = useState(false);

  const meta = useQuery({ queryKey: ['mkt', 'meta'], queryFn: monthApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const foy = useQuery({ queryKey: ['mkt', 'foy1', stok, ay], queryFn: () => monthApi.foy(stok, ay), enabled: ENGINE_ENABLED && !!stok });
  const f = foy.data;
  const me = meta.data?.me;
  const donem = f?.donem ?? ay ?? '';
  const put = (x: Foy) => { qc.setQueryData(['mkt', 'foy1', stok, ay], x); qc.invalidateQueries({ queryKey: ['mkt', 'foy'] }); };

  const save = useMutation({
    mutationFn: () => monthApi.foySave(stok, donem, { [edit!.key]: edit!.key === 'argumanlar' ? value.split('\n').map((s) => s.trim()).filter(Boolean) : value.trim() || null }),
    onSuccess: (x) => { put(x); setEdit(null); toast.success('Alan kaydedildi.'); },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  const args = useMutation({
    mutationFn: () => monthApi.foyArgs(stok, donem),
    onSuccess: (x) => { put(x); toast.success('Zeki AI argüman taslağı yazıldı; gözden geçirin.'); },
    onError: (e) => toast.error(errText(e, 'Taslak yazılamadı.') ?? ''),
  });
  const act = useMutation({
    mutationFn: async ({ kind, text }: { kind: Exclude<Ask, null>; text: string }) => {
      if (kind === 'submit') return monthApi.foySubmit(stok, donem);
      if (kind === 'refresh') return monthApi.foyRefresh(stok, donem);
      if (kind === 'reject') return monthApi.foyReject(stok, donem, text);
      return monthApi.foyApprove(stok, donem, { not: text || undefined, kabul: !!f?.engelleyen && !!text });
    },
    onSuccess: (x, { kind }) => {
      put(x);
      setAsk(null);
      toast.success({ submit: 'Föy onaya gönderildi.', approve: 'Föy onaylandı.', reject: 'Föy gerekçesiyle geri gönderildi.', refresh: 'Föy CRM\'den yenilendi.' }[kind]);
    },
    onError: (e) => toast.error(errText(e, 'İşlem yapılamadı.') ?? ''),
  });

  async function share() {
    if (!f) return;
    const url = monthApi.foyPdfUrl(f.stokKodu, f.donem);
    setSharing(true);
    try {
      const res = await fetch(url, { credentials: 'include' });
      if (!res.ok) throw new Error('PDF alınamadı.');
      const file = new File([await res.blob()], `foy-${f.stokKodu}.pdf`, { type: 'application/pdf' });
      if (navigator.canShare?.({ files: [file] })) {
        await navigator.share({ files: [file], title: `Satış föyü · ${f.stokKodu}` });
        return;
      }
      window.open(url, '_blank', 'noopener');
    } catch (e) {
      if ((e as Error).name !== 'AbortError') window.open(url, '_blank', 'noopener');
    } finally {
      setSharing(false);
    }
  }

  const argsField = f?.alanlar.find((a) => a.key === 'argumanlar');
  const crmArgs = !!argsField?.kaynak?.startsWith('crm:') && !!fieldText(argsField.deger);
  const mine = !!f && !!me && [f.gonderen, f.guncelleyen].some((u) => (u ?? '').toLowerCase() === me.username.toLowerCase());

  return (
    <MarketingFrame
      crumb="Satış föyleri"
      title={(f?.alanlar.find((a) => a.key === 'ad')?.deger as string) ?? stok}
      source={f ? `${f.stokKodu} · sürüm ${f.surum}` : stok}
      presence={f ? f.durumAdi : '…'}
      back={{ to: `/pazarlama/foy${donem ? `?ay=${donem}` : ''}`, label: 'Satış föyleri' }}
    >
      {foy.error && <Note tone="err">{errText(foy.error, 'Föy açılamadı.')}</Note>}
      {foy.isLoading && <Loading />}
      {f && me && (
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:gap-4">
          <div className="flex w-full shrink-0 flex-col gap-2 lg:sticky lg:top-0 lg:w-[400px]">
            <Preview f={f} />
            <div className="grid grid-cols-2 gap-2">
              <button type="button" className={btnPrimary} onClick={share} disabled={sharing}>
                {sharing ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Share2 aria-hidden className="h-4 w-4" />}Paylaş
              </button>
              <a className={btnGhost} href={monthApi.foyPdfUrl(f.stokKodu, f.donem)} target="_blank" rel="noopener noreferrer">
                <FileText aria-hidden className="h-4 w-4" />PDF
              </a>
            </div>
          </div>

          <div className="flex min-w-0 flex-1 flex-col gap-3">
            <div className="flex flex-wrap items-center gap-2 px-1">
              <Pill tone={FOY_TONE[f.durum]}>{f.durumAdi}</Pill>
              {f.eski && <Pill tone="err">CRM'de değişti: yenileyin</Pill>}
              <span className="text-[12px] font-semibold text-canvas-muted">
                {f.onaylayan ? `Onaylayan ${f.onaylayan} (${fmtStamp(f.onayZamani)})` : f.gonderen ? `${f.gonderen} onaya gönderdi` : 'Onay bekliyor değil'}
              </span>
              <div className="ml-auto flex flex-wrap gap-2">
                {me.canFoyWrite && <button type="button" className={btnGhost} onClick={() => setAsk('refresh')}><RefreshCw aria-hidden className="h-4 w-4" />CRM'den yenile</button>}
                {me.canFoyWrite && f.durum === 'taslak' && <button type="button" className={btnGhost} onClick={() => setAsk('submit')} disabled={f.eksikler.length > 0}>Onaya gönder</button>}
                {me.canFoyApprove && f.durum !== 'onayli' && !mine && <button type="button" className={btnGhost} onClick={() => setAsk('reject')}>Geri gönder</button>}
                {me.canFoyApprove && f.durum !== 'onayli' && !mine && <button type="button" className={btnPrimary} onClick={() => setAsk('approve')} disabled={f.eksikler.length > 0}>Onayla</button>}
              </div>
            </div>
            {f.gerekce && f.durum === 'taslak' && <Note tone="warn">Geri gönderildi: {f.gerekce}</Note>}
            {mine && me.canFoyApprove && f.durum !== 'onayli' && <Note tone="info">Bu föyü siz hazırladınız ya da gönderdiniz; onayı başka bir yetkili verir.</Note>}
            {f.eksikler.length > 0 && <Note tone="warn">Eksik alanlar: {f.eksikler.map((k) => meta.data?.monthly?.foyFields[k] ?? k).join(', ')}. Eksik föy onaylanmaz.</Note>}
            {f.uyumsuzluk.map((m) => (
              <Note key={m.tur} tone={m.bilgi ? 'info' : 'err'}>
                <span className="inline-flex items-start gap-1.5">
                  <AlertTriangle aria-hidden className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                  <span>
                    {m.ad}
                    {m.tur === 'fiyat-logo' && <> — CRM {money(m.crm)}, Logo {money(m.logo)}</>}
                    {m.tur === 'fiyat-taslak' && <> — KDV dahil {money(m.crm)}, föy taslak {money(m.taslak)}</>}
                    {m.tur === 'fiyat-uzeri' && <> — KDV dahil {money(m.crm)}, kapak fiyatı {money(m.uzeri)}</>}
                    {m.tur === 'barkod-isbn' && <> — barkod {String(m.barkod)}, ISBN {String(m.isbn)}</>}
                    {m.not && <span className="block text-[11px] font-normal opacity-80">{m.not}</span>}
                  </span>
                  <SqlInfo k={f.kaynaklar} alan="uyumsuzluk[]" label={m.ad} />
                </span>
              </Note>
            ))}
            {f.onayNotu && <Note tone="info">Onay notu: {f.onayNotu}</Note>}

            <Block title="Alanlar" help="Her alanın kaynağı yanında: CRM kitap kartı, Zeki AI ya da elle. Elle düzeltme CRM yenilemesinde korunur; CRM'e yazılmaz (onaydan sonra «CRM'e işlenecek» listesine düşer)."
              info={<SqlInfo k={f.kaynaklar} alan="alanlar[]" label="Föy alanları" />}>
              <ul className="flex flex-col divide-y divide-slate-100">
                {f.alanlar.map((a) => (
                  <li key={a.key} className="flex items-start gap-2 py-2">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">{a.ad}</span>
                        <Pill tone={a.kaynak === 'elle' ? 'violet' : a.kaynak === 'zeki' ? 'warn' : a.kaynak ? 'muted' : 'err'}>{FIELD_SOURCE(a.kaynak)}</Pill>
                        {f.zorunlu.includes(a.key) && <span className="text-[10.5px] font-semibold text-canvas-muted">zorunlu</span>}
                      </div>
                      <p className="mt-0.5 line-clamp-4 whitespace-pre-line break-words text-[12.5px] leading-snug">
                        {a.key === 'fiyat' ? money(a.deger) : fieldText(a.deger) || '—'}
                      </p>
                    </div>
                    {me.canFoyWrite && a.key !== 'kapak' && (
                      <button type="button" aria-label={`${a.ad} düzelt`} className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-slate-100 transition-transform duration-150 ease-out hover:bg-slate-200 active:scale-[0.97] sm:h-9 sm:w-9"
                        onClick={() => { setEdit(a); setValue(fieldText(a.deger)); }}>
                        <Pencil aria-hidden className="h-4 w-4" />
                      </button>
                    )}
                  </li>
                ))}
              </ul>
              {me.canFoyWrite && !crmArgs && (
                <button type="button" className={`${btnGhost} mt-2`} onClick={() => args.mutate()} disabled={args.isPending || !meta.data?.modelReady}>
                  {args.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Sparkles aria-hidden className="h-4 w-4" />}
                  Zeki AI satış argümanı taslağı
                </button>
              )}
              {me.canFoyWrite && !crmArgs && !meta.data?.modelReady && <p className="mt-1 text-[11px] text-canvas-muted">Zeki AI modeli bu kurulumda bağlı değil; argümanları elle yazın.</p>}
            </Block>

            {!!f.crmTodo?.length && (
              <Block title="CRM'e işlenecek" help="Portal CRM'e yazmaz. Onaylı föyde elle ya da Zeki AI ile gelen bu metinleri CRM kitap kartına sizin ekibiniz işler.">
                <ul className="flex flex-col gap-2 text-[12px]">
                  {f.crmTodo.map((t) => (
                    <li key={t.alan} className="rounded-xl bg-white/70 p-2">
                      <div className="font-bold">{t.ad} <span className="font-mono text-[11px] text-canvas-muted">({t.alan})</span></div>
                      <p className="mt-0.5 whitespace-pre-line">{t.deger}</p>
                    </li>
                  ))}
                </ul>
              </Block>
            )}
          </div>
        </div>
      )}

      <Sheet open={!!edit} modal onClose={() => setEdit(null)} title={edit ? `${edit.ad} düzelt` : ''} subtitle="Boş bırakıp kaydederseniz alan CRM'deki değerine döner.">
        {edit && (
          <div className="flex flex-col gap-3">
            <label className="flex flex-col gap-1">
              <span className={labelCls}>{edit.key === 'argumanlar' ? 'Her satır bir madde' : 'Değer'}</span>
              {['tanitim', 'ozet', 'argumanlar'].includes(edit.key)
                ? <textarea className={`${field} min-h-[160px]`} value={value} onChange={(e) => setValue(e.target.value)} />
                : <input className={field} inputMode={edit.key === 'fiyat' || edit.key === 'sayfa' ? 'decimal' : undefined} type={edit.key === 'yayinTarihi' ? 'date' : 'text'} value={value} onChange={(e) => setValue(e.target.value)} />}
            </label>
            {f?.durum === 'onayli' && <Note tone="warn">Föy onaylı: düzeltme yeni sürümü taslak olarak açar, yeniden onay gerekir.</Note>}
            <div className="flex justify-end gap-2">
              <button type="button" className={btnGhost} onClick={() => setEdit(null)}>Vazgeç</button>
              <button type="button" className={btnPrimary} disabled={save.isPending} onClick={() => save.mutate()}>Kaydet</button>
            </div>
          </div>
        )}
      </Sheet>

      <AskSheet
        open={ask !== null}
        busy={act.isPending}
        title={{ submit: 'Onaya gönder', approve: 'Föyü onayla', reject: 'Geri gönder', refresh: 'CRM\'den yenile', '': '' }[ask ?? '']}
        message={
          ask === 'submit' ? 'Föy satış müdürünün onayına düşer; onayı sizden başka bir yetkili verir.'
            : ask === 'approve' ? (f?.engelleyen ? 'Föyde uyumsuzluk var. Onaylamak için gerekçeyi yazın (uyumsuzluk kabul edilir ve kayda geçer).' : 'Föy onaylanır ve aylık pakete girer.')
            : ask === 'reject' ? 'Föy gerekçenizle taslağa döner.'
            : 'Alanlar CRM kitap kartından yeniden okunur; elle düzeltilenler korunur. Onaylı föy yeni sürüm olarak taslağa döner.'
        }
        confirm={{ submit: 'Onaya gönder', approve: 'Onayla', reject: 'Geri gönder', refresh: 'Yenile', '': '' }[ask ?? '']}
        input={ask === 'reject' ? 'Gerekçe' : ask === 'approve' ? (f?.engelleyen ? 'Uyumsuzluğu kabul gerekçesi' : 'Not (isteğe bağlı)') : undefined}
        required={ask === 'reject' || (ask === 'approve' && !!f?.engelleyen)}
        onClose={() => setAsk(null)}
        onConfirm={(text) => ask && act.mutate({ kind: ask, text })}
      />
    </MarketingFrame>
  );
}
