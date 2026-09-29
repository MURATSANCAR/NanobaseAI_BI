import { useCallback, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { CheckCheck, Download, ExternalLink, EyeOff, FileSpreadsheet, RotateCcw } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, btnGhost, btnPrimary, errText, field, label as labelCls } from '../admin/ui';
import Sheet from '../editorial/studio/reader/Sheet';
import { Block, Empty, FieldFrame, Stat } from '../field/parts';
import { fmtDay } from '../field/api';
import { barHeights, musteriApi, type Finding } from './api';
import { SubNav } from './parts';
import { RunNotes, useMusteriMeta } from './CustomersHome';
import SqlInfo from '../components/SqlInfo';
import { xlsxUrl } from '../components/excel';
import { Explain } from '../components/Explain';

/** CRM veri sağlığı: Logo bağı olmayan, olası tekrar, kanalı eksik, sahipsiz / ortak hesaba ait cari kayıtları, izin
 *  çelişkileri ve (yalnız yetkiliye) güvenlik bulguları. Portal CRM'e yazmaz: bulgu «CRM'de düzeltildi» diye işaretlenir,
 *  ertesi gece taramada koşul kalkmışsa doğrulanır, kalkmamışsa yeniden açılır. İşaretlemek 2 dokunuş. */

const STATES = [
  { key: 'acik-hepsi', label: 'Açık' },
  { key: 'crmde_duzeltildi', label: 'Doğrulama bekleyen' },
  { key: 'dogrulandi', label: 'Doğrulandı' },
  { key: 'kapandi', label: 'Kendiliğinden kapandı' },
  { key: 'yoksay', label: 'Yok sayıldı' },
];
const ONEM_TONE = { yuksek: 'bg-red-50 text-red-700', orta: 'bg-amber-50 text-amber-800', dusuk: 'bg-slate-100 text-canvas-ink' } as const;

export default function DataHealthScreen() {
  const [params, setParams] = useSearchParams();
  const qc = useQueryClient();
  const meta = useMusteriMeta();
  const m = meta.data;
  const tur = params.get('tur') ?? '';
  const durum = params.get('durum') ?? 'acik-hepsi';
  const onem = params.get('onem') ?? '';
  const q = params.get('q') ?? '';
  const p = Number(params.get('p') ?? '1') || 1;
  const [search, setSearch] = useState(q);
  const [ignore, setIgnore] = useState<Finding | null>(null);
  const [reason, setReason] = useState('');

  const update = useCallback(
    (next: Record<string, string | null>) => {
      const u = new URLSearchParams(params);
      for (const [k, v] of Object.entries(next)) {
        if (v) u.set(k, v);
        else u.delete(k);
      }
      if (!('p' in next)) u.delete('p');
      setParams(u, { replace: true });
    },
    [params, setParams],
  );

  const h = useQuery({
    queryKey: ['musteri', 'health', tur, durum, onem, q, p],
    queryFn: () => musteriApi.health({ tur, durum, onem, q, p, size: 50 }),
    enabled: ENGINE_ENABLED && !!m?.run.asof,
    placeholderData: keepPreviousData,
  });
  const hist = useQuery({ queryKey: ['musteri', 'score-history'], queryFn: () => musteriApi.scoreHistory(365), enabled: ENGINE_ENABLED && !!m?.run.asof });
  const mark = useMutation({
    mutationFn: (b: { id: string; durum: 'crmde_duzeltildi' | 'yoksay' | 'acik'; not?: string }) => musteriApi.mark(b.id, { durum: b.durum, not: b.not }),
    onSuccess: (r) => {
      toast.success(r.durum === 'crmde_duzeltildi' ? 'İşaretlendi; ertesi gece taramada doğrulanacak.' : r.durum === 'yoksay' ? 'Yok sayıldı' : 'Yeniden açıldı');
      setIgnore(null);
      setReason('');
      void qc.invalidateQueries({ queryKey: ['musteri', 'health'] });
    },
    onError: (e) => toast.error(errText(e, 'İşaretlenemedi.') ?? 'İşaretlenemedi.'),
  });

  const d = h.data;
  const err = errText(meta.error ?? h.error, 'Veri sağlığı açılamadı.');
  const openCount = (t: string) => (d?.sayilar[t]?.acik ?? 0) + (d?.sayilar[t]?.crmde_duzeltildi ?? 0);
  const points = hist.data?.items ?? [];
  const heights = barHeights(points.map((x) => x.puan));
  const delta = d?.puan && d.onceki ? Math.round((d.puan.puan - d.onceki.puan) * 10) / 10 : null;

  return (
    <FieldFrame
      crumb="CRM veri sağlığı"
      title="CRM veri sağlığı"
      lead="CRM'deki cari kayıtlarından raporları eksik ya da yanlış gösterenler (Logo bağı olmayan, tekrar olabilecek, sahipsiz kayıtlar) ve izin çelişkileri. Düzeltmeyi CRM'de siz yaparsınız; portal ertesi gece kontrol eder."
      source={d?.tarih ? `Tarama ${fmtDay(d.tarih)} · CRM` : 'CRM'}
      presence={d?.puan ? `Puan ${d.puan.puan}` : 'Veri sağlığı'}
      back={{ to: '/musteri-iliskileri', label: 'Özet' }}
    >
      <SubNav meta={m} />
      {err && <Note tone="err">{err}</Note>}
      {(meta.isLoading || h.isLoading) && <Loading />}
      {m && <RunNotes meta={m} />}
      {d && m && (
        <>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Stat
              label="Veri sağlığı puanı"
              info={<SqlInfo k={d.kaynaklar} alan="puan" label="Veri sağlığı puanı" />}
              value={d.puan ? `${d.puan.puan.toLocaleString('tr-TR')} / 100` : '—'}
              help={delta === null ? 'Bulgusu olmayan etkin cari payı' : `Önceki taramaya göre ${delta > 0 ? '+' : ''}${delta.toLocaleString('tr-TR')}`}
              tone={delta !== null && delta < 0 ? 'warn' : undefined}
              explain="Etkin CRM carilerinden hiçbir bulgusu olmayanların payı (100 üzerinden). Bulgular CRM'de düzeltildikçe puan yükselir."
            />
            <Stat label="Etkin CRM carisi" info={<SqlInfo k={d.kaynaklar} alan="puan" label="Etkin CRM carisi" />} value={(d.puan?.etkin ?? 0).toLocaleString('tr-TR')} />
            <Stat label="Bulgulu cari" info={<SqlInfo k={d.kaynaklar} alan="puan" label="Bulgulu cari" />} value={(d.puan?.bulgulu ?? 0).toLocaleString('tr-TR')} />
            <Stat label="Zeki AI kararı bekleyen" info={<SqlInfo k={d.kaynaklar} alan="zeki" label="Karar bekleyen çift" />} value={String(d.zeki?.waiting ?? 0)} help="Olası tekrar çifti; her gece sırayla sorulur" explain="Aynı firma olabileceği düşünülen iki cari kaydı. Zeki AI her gece sırayla «aynı firma / farklı / belirsiz» kararı verir; sonuç bulgulara yansır." />
          </div>

          {points.length > 1 && (
            <Block title="Puanın seyri" help="Her gece taramasının puanı." action={<SqlInfo k={hist.data?.kaynaklar} alan="items" label="Puanın seyri" />}>
              <div role="img" aria-label={`Veri sağlığı puanı, son ${points.length} tarama`} className="flex h-16 items-end gap-[2px]">
                {points.map((x, i) => (
                  <div key={x.tarih} title={`${fmtDay(x.tarih)}: ${x.puan}`} className="min-w-[2px] flex-1 rounded-t bg-canvas-violet/60" style={{ height: `${Math.max(4, heights[i] * 100)}%` }} />
                ))}
              </div>
            </Block>
          )}

          <div className="-mx-1 overflow-x-auto px-1">
            <div className="flex w-max min-w-full gap-1 rounded-2xl bg-slate-100 p-1" role="tablist" aria-label="Bulgu türü">
              {[{ key: '', label: 'Hepsi' }, ...m.healthTypes].map((t) => (
                <button
                  key={t.key || 'hepsi'}
                  type="button"
                  role="tab"
                  aria-selected={tur === t.key}
                  onClick={() => update({ tur: t.key || null })}
                  className={`inline-flex min-h-11 shrink-0 items-center gap-1.5 whitespace-nowrap rounded-xl px-3 text-[12.5px] font-extrabold transition-colors duration-150 sm:min-h-9 ${
                    tur === t.key ? 'bg-canvas-violet text-white shadow-md' : 'text-canvas-ink hover:bg-white/70'
                  }`}
                >
                  {t.label}
                  {t.key && openCount(t.key) > 0 && (
                    <span className={`rounded-md px-1.5 py-0.5 font-mono text-[10.5px] tabular-nums ${tur === t.key ? 'bg-white/20' : 'bg-white text-canvas-ink'}`}>
                      {openCount(t.key).toLocaleString('tr-TR')}
                    </span>
                  )}
                </button>
              ))}
            </div>
          </div>

          <form
            className="grid grid-cols-2 gap-2 sm:grid-cols-4"
            onSubmit={(e) => {
              e.preventDefault();
              update({ q: search.trim() || null });
            }}
          >
            <label className="col-span-2 flex flex-col gap-1">
              <span className={labelCls}>Ara</span>
              <input className={field} value={search} placeholder="Unvan, cari kodu, CRM kimliği" enterKeyHint="search" onChange={(e) => setSearch(e.target.value)} onBlur={() => update({ q: search.trim() || null })} />
            </label>
            <div className="flex min-w-0 flex-col gap-1">
              <span className={`${labelCls} inline-flex items-center gap-1`}>
                <label htmlFor="musteri-bulgu-durum">Durum</label>
                <Explain label="Bulgu durumları">Açık: henüz düzeltilmedi. Doğrulama bekleyen: «CRM'de düzeltildi» dediniz, ertesi gece kontrol edilecek. Doğrulandı: düzeltme görüldü. Kendiliğinden kapandı: sorun ortadan kalktı. Yok sayıldı: gerekçeyle bırakıldı.</Explain>
              </span>
              <select id="musteri-bulgu-durum" className={field} value={durum} onChange={(e) => update({ durum: e.target.value === 'acik-hepsi' ? null : e.target.value })}>
                {STATES.map((s) => (
                  <option key={s.key} value={s.key}>
                    {s.label}
                  </option>
                ))}
              </select>
            </div>
            <label className="flex min-w-0 flex-col gap-1">
              <span className={labelCls}>Önem</span>
              <select className={field} value={onem} onChange={(e) => update({ onem: e.target.value || null })}>
                <option value="">Hepsi</option>
                <option value="yuksek">Yüksek</option>
                <option value="orta">Orta</option>
                <option value="dusuk">Düşük</option>
              </select>
            </label>
          </form>

          <div className="flex flex-wrap items-center justify-between gap-2 px-1 text-[12px] text-canvas-muted">
            <span>{d.total.toLocaleString('tr-TR')} bulgu</span>
            {m.me.canExport && (
              <>
                <a className={`${btnGhost} !min-h-9`} href={musteriApi.healthCsvUrl({ tur, durum, onem, q })}>
                  <Download aria-hidden className="h-4 w-4" />
                  CRM'de düzeltilecekleri indir (CSV)
                </a>
                <a className={`${btnGhost} !min-h-9`} href={xlsxUrl(musteriApi.healthCsvUrl({ tur, durum, onem, q }))}>
                  <FileSpreadsheet aria-hidden className="h-4 w-4" />
                  Excel indir
                </a>
              </>
            )}
          </div>

          {d.items.length === 0 ? (
            <Empty title="Bu süzgece uyan bulgu yok">{durum === 'acik-hepsi' && !tur && !onem && !q ? 'Açık bulgu kalmadı; CRM kayıtları temiz görünüyor.' : 'Bulgu türünü «Hepsi»ne alın ya da durum, önem ve aramayı değiştirin.'}</Empty>
          ) : (
            <ul className={`flex flex-col gap-2 ${h.isPlaceholderData ? 'opacity-60' : ''}`}>
              {d.items.map((f) => (
                <li key={f.id} className="rounded-2xl border border-slate-100 bg-white/85 p-3">
                  <div className="flex flex-wrap items-center gap-1.5 text-[11px] font-bold">
                    <span className={`rounded-md px-1.5 py-0.5 ${ONEM_TONE[f.onem]}`}>{f.onemAd}</span>
                    <span className="uppercase tracking-wide text-canvas-muted">{f.turAd}</span>
                    <span className="text-canvas-muted">· {f.durumAd}</span>
                    {f.olasilik !== null && <span className="text-canvas-muted">· olasılık %{Math.round(f.olasilik * 100)}</span>}
                  </div>
                  <div className="mt-1 min-w-0 truncate text-[13.5px] font-extrabold">
                    {f.ad || (f.varlik === 'contact' ? 'Kişi kaydı' : f.varlik === 'sistem' ? 'Sistem' : 'Cari')}
                    {f.code ? <span className="ml-1.5 font-mono text-[11.5px] font-bold text-canvas-muted">{f.code}</span> : null}
                  </div>
                  <p className="mt-0.5 break-words text-[12.5px] leading-snug">{f.ozet}</p>
                  {f.not && <p className="mt-1 break-words text-[12px] leading-snug text-amber-800">{f.not}</p>}
                  <div className="mt-1 text-[11px] text-canvas-muted">
                    İlk {fmtDay(f.ilk)} · son {fmtDay(f.son)}
                    {f.isaretleyen ? ` · işaretleyen ${f.isaretleyen}` : ''}
                    {f.varlik !== 'sistem' ? <span className="break-all"> · CRM {f.kayit}</span> : null}
                  </div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {f.crmLink && (
                      <a className={`${btnGhost} !min-h-9`} href={f.crmLink} target="_blank" rel="noreferrer">
                        <ExternalLink aria-hidden className="h-4 w-4" />
                        CRM'de aç
                      </a>
                    )}
                    {m.me.canMark && f.durum === 'acik' && (
                      <>
                        <button type="button" className={`${btnPrimary} !min-h-9`} disabled={mark.isPending} onClick={() => mark.mutate({ id: f.id, durum: 'crmde_duzeltildi' })}>
                          <CheckCheck aria-hidden className="h-4 w-4" />
                          CRM'de düzeltildi
                        </button>
                        <button type="button" className={`${btnGhost} !min-h-9`} onClick={() => setIgnore(f)}>
                          <EyeOff aria-hidden className="h-4 w-4" />
                          Yok say
                        </button>
                      </>
                    )}
                    {m.me.canMark && (f.durum === 'yoksay' || f.durum === 'crmde_duzeltildi') && (
                      <button type="button" className={`${btnGhost} !min-h-9`} disabled={mark.isPending} onClick={() => mark.mutate({ id: f.id, durum: 'acik' })}>
                        <RotateCcw aria-hidden className="h-4 w-4" />
                        Geri al
                      </button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
          {d.pages > 1 && (
            <div className="flex items-center justify-center gap-2 py-2">
              <button type="button" className={btnGhost} disabled={d.page <= 1} onClick={() => update({ p: String(d.page - 1) })}>
                Önceki
              </button>
              <span className="font-mono text-[12px] tabular-nums">
                {d.page} / {d.pages}
              </span>
              <button type="button" className={btnGhost} disabled={d.page >= d.pages} onClick={() => update({ p: String(d.page + 1) })}>
                Sonraki
              </button>
            </div>
          )}

          {(d.veriDurumu || d.crmKanal) && (
            <Block title="CRM alan kullanımı" help="Kişi kaydındaki «Veri durumu» alanının doluluğu ve etkin carilerin firma kanalı dağılımı.">
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                {d.veriDurumu && (
                  <ul className="text-[12.5px]">
                    {Object.entries(d.veriDurumu).map(([k, v]) => (
                      <li key={k} className="flex justify-between gap-3 border-b border-slate-100 py-1 last:border-0">
                        <span>{VERI_DURUMU[k] ?? k}</span>
                        <span className="font-mono font-bold tabular-nums">{v.toLocaleString('tr-TR')}</span>
                      </li>
                    ))}
                  </ul>
                )}
                {d.crmKanal && (
                  <ul className="text-[12.5px]">
                    {Object.entries(d.crmKanal)
                      .sort((a, b) => b[1] - a[1])
                      .map(([k, v]) => (
                        <li key={k} className="flex justify-between gap-3 border-b border-slate-100 py-1 last:border-0">
                          <span>{k}</span>
                          <span className="font-mono font-bold tabular-nums">{v.toLocaleString('tr-TR')}</span>
                        </li>
                      ))}
                  </ul>
                )}
              </div>
            </Block>
          )}
        </>
      )}
      <Sheet open={!!ignore} modal onClose={() => setIgnore(null)} title="Yok say" subtitle={ignore?.ozet ?? ''}>
        <form
          className="flex flex-col gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (ignore && reason.trim()) mark.mutate({ id: ignore.id, durum: 'yoksay', not: reason.trim() });
          }}
        >
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Gerekçe</span>
            <textarea className={`${field} min-h-[88px]`} value={reason} maxLength={500} placeholder="Örn. İki kayıt aynı firmanın ayrı şubeleri." onChange={(e) => setReason(e.target.value)} />
          </label>
          <div className="flex justify-end gap-2">
            <button type="button" className={btnGhost} onClick={() => setIgnore(null)}>
              Vazgeç
            </button>
            <button type="submit" className={btnPrimary} disabled={!reason.trim() || mark.isPending}>
              Yok say
            </button>
          </div>
        </form>
      </Sheet>
    </FieldFrame>
  );
}

const VERI_DURUMU: Record<string, string> = {
  '1': 'Kontrol edildi',
  '2': 'Kontrol edilecek',
  '3': 'Silinebilir',
  '4': 'Veri kalitesi yetersiz',
  bos: 'Boş',
};
