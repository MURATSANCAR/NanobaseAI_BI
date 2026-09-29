import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Check, Sparkles, X } from 'lucide-react';
import { Note, TableWrap, btnGhost, btnPrimary, errText, field, label as labelCls, td, th } from '../../admin/ui';
import { Pager, useDebounced } from '../../editorial/kit';
import { fmtInt, fmtMoney, fmtPct, parseNum } from '../../budget/api';
import { setsApi, type SetsMeta } from './api';
import { MarginCell, Tone } from './parts';
import SqlInfo, { InfoLabel } from '../../components/SqlInfo';

/** Öneriler: B2C birlikte alım, aynı yazar ve aynı dizi kümeleri (kural), Zeki AI ad/tanıtım ve özel gün. Tavansız, sayfalı. */
export default function SuggestionsTab({ meta }: { meta: SetsMeta }) {
  const qc = useQueryClient();
  const nav = useNavigate();
  const [view, setView] = useState<'oneri' | 'cift'>('oneri');
  const [tur, setTur] = useState('');
  const [durum, setDurum] = useState('yeni');
  const [yas, setYas] = useState('');
  const [tema, setTema] = useState('');
  const [bmin, setBmin] = useState('');
  const [bmax, setBmax] = useState('');
  const [page, setPage] = useState(0);
  // Süzgeç metin olarak geciktirilir (nesne her çizimde yeni olurdu, gecikme hiç oturmazdı).
  const fKey = useDebounced(JSON.stringify({ yas: parseNum(yas), tema: tema.trim(), bmin: parseNum(bmin), bmax: parseNum(bmax) }), 350);
  const f = JSON.parse(fKey) as { yas: number | null; tema: string; bmin: number | null; bmax: number | null };
  const list = useQuery({
    queryKey: ['sets', 'suggestions', tur, durum, fKey, page],
    queryFn: () => setsApi.suggestions({ tur, durum, yas: f.yas, tema: f.tema, butce_min: f.bmin, butce_max: f.bmax, page }),
    placeholderData: keepPreviousData,
    enabled: view === 'oneri',
  });
  const adopt = useMutation({
    mutationFn: setsApi.adopt,
    onSuccess: (s) => {
      qc.invalidateQueries({ queryKey: ['sets'] });
      toast.success('Öneri set taslağına alındı.');
      nav(`/pazarlama/set-hediye/set/${encodeURIComponent(s.id)}`);
    },
    onError: (e) => toast.error(errText(e, 'Öneri taslağa alınamadı.') ?? ''),
  });
  const dismiss = useMutation({
    mutationFn: setsApi.dismiss,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['sets', 'suggestions'] }); toast.success('Öneri reddedildi.'); },
    onError: (e) => toast.error(errText(e, 'İşlem yapılamadı.') ?? ''),
  });
  const reset = () => setPage(0);
  const disc = list.data?.indirim;

  return (
    <>
      <section className="glass-panel flex flex-col gap-2 rounded-2xl p-3 shadow-glass-float sm:rounded-3xl sm:p-4">
        <div className="flex flex-wrap gap-2" role="group" aria-label="Görünüm">
          <button type="button" aria-pressed={view === 'oneri'} className={view === 'oneri' ? btnPrimary : btnGhost} onClick={() => setView('oneri')}>
            <Sparkles aria-hidden className="h-4 w-4" /> Set önerileri
          </button>
          <button type="button" aria-pressed={view === 'cift'} className={view === 'cift' ? btnPrimary : btnGhost} onClick={() => setView('cift')}>
            Birlikte alınan çiftler
          </button>
        </div>
        {view === 'oneri' && (
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-6">
            <label className="flex flex-col gap-1">
              <span className={labelCls}>Kaynak</span>
              <select className={field} value={tur} onChange={(e) => { setTur(e.target.value); reset(); }}>
                <option value="">Hepsi</option>
                {Object.entries(meta.suggestionTypes).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className={labelCls}>Durum</span>
              <select className={field} value={durum} onChange={(e) => { setDurum(e.target.value); reset(); }}>
                <option value="yeni">Yeni</option>
                <option value="benimsendi">Taslağa alınan</option>
                <option value="reddedildi">Reddedilen</option>
                <option value="">Hepsi</option>
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className={labelCls}>Yaş</span>
              <input className={`${field} font-mono`} inputMode="numeric" placeholder="ör. 8" value={yas} onChange={(e) => { setYas(e.target.value); reset(); }} />
            </label>
            <label className="flex flex-col gap-1">
              <span className={labelCls}>Tema / tür</span>
              <input className={field} placeholder="ör. bilim" value={tema} onChange={(e) => { setTema(e.target.value); reset(); }} />
            </label>
            <label className="flex flex-col gap-1">
              <span className={labelCls}>Liste toplamı en az</span>
              <input className={`${field} font-mono`} inputMode="decimal" value={bmin} onChange={(e) => { setBmin(e.target.value); reset(); }} />
            </label>
            <label className="flex flex-col gap-1">
              <span className={labelCls}>en çok</span>
              <input className={`${field} font-mono`} inputMode="decimal" value={bmax} onChange={(e) => { setBmax(e.target.value); reset(); }} />
            </label>
          </div>
        )}
        {view === 'oneri' && disc && (
          <p className="text-[11.5px] text-canvas-muted">
            Önerilen fiyat: {disc.indirim !== null
              ? <>mevcut {fmtInt(disc.n)} setin medyan indirimi ({fmtPct(disc.indirim)}) liste toplamına uygulanır.</>
              : <>mevcut setlerde yeterli örnek yok ({fmtInt(disc.n)}); liste toplamı önerilir, indirimi siz belirlersiniz.</>}
            <SqlInfo k={list.data?.kaynaklar} alan="indirim" label="Medyan indirim" className="ml-0.5" />
            {' '}Ad ve tanıtım Zeki AI taslağıdır; gerekçedeki sayılar sistemden gelir.
          </p>
        )}
      </section>

      {view === 'cift' ? <PairsView meta={meta} /> : (
        <>
          {list.error && <Note tone="err">{errText(list.error, 'Öneriler okunamadı.')}</Note>}
          {list.data && !list.data.items.length && (
            <Note tone="info">Bu süzgeçte öneri yok. Öneriler her gece yenilenir; birlikte alım çiftleri haftada bir okunur.</Note>
          )}
          <div className="grid gap-2.5 lg:grid-cols-2">
            {list.data?.items.map((s) => (
              <article key={s.id} className="glass-panel flex flex-col gap-2 rounded-2xl p-3 shadow-glass-float sm:rounded-3xl sm:p-4">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <h3 className="text-[15px] font-extrabold leading-snug">{s.ad}</h3>
                    <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[11px] text-canvas-muted">
                      <Tone tone="violet">{s.turAdi}</Tone>
                      {s.sezonAdi && <Tone tone="ok">{s.sezonAdi}</Tone>}
                      {(s.yasMin || s.yasMax) && <span>{s.yasMin ?? '?'}–{s.yasMax ?? '?'} yaş</span>}
                      {s.durum !== 'yeni' && <Tone tone="muted">{s.durumAdi}</Tone>}
                    </div>
                  </div>
                  <div className="text-right font-mono text-[12px] tabular-nums">
                    <div className="inline-flex items-center gap-0.5 font-bold">{fmtMoney(s.onerilenFiyat)}<SqlInfo k={list.data?.kaynaklar} alan="items[]" label="Önerilen fiyat, liste, indirim, bileşenler" /></div>
                    <div className="text-canvas-muted">liste {fmtMoney(s.listeToplami)} · {fmtPct(s.indirim)}</div>
                    {meta.me.canSeeCost && <MarginCell marj={s.marj} oran={s.marjOrani} floor={meta.settings.marginMinPct} />}
                  </div>
                </div>
                {s.aciklama && <p className="text-[12.5px] leading-snug">{s.aciklama}</p>}
                <p className="text-[12px] leading-snug text-canvas-muted">{s.gerekce}</p>
                <TableWrap>
                  <tbody>
                    {s.bilesenler.map((b) => (
                      <tr key={b.stok} className="border-b border-slate-50 last:border-0">
                        <td className={td}><span className="font-semibold">{b.ad ?? b.stok}</span><div className="text-[11px] text-canvas-muted">{b.stok}{b.yazar ? ` · ${b.yazar}` : ''}</div></td>
                        <td className={`${td} text-right font-mono tabular-nums`}>{fmtMoney(b.liste)}</td>
                        <td className={`${td} text-right font-mono tabular-nums`}>stok {fmtInt(b.stokAdet)}</td>
                        <td className={`${td} text-right font-mono tabular-nums`}>12 ay {fmtInt(b.son12Adet ?? null)}</td>
                      </tr>
                    ))}
                  </tbody>
                </TableWrap>
                {meta.me.canWrite && s.durum === 'yeni' && (
                  <div className="flex flex-wrap justify-end gap-2">
                    <button type="button" className={btnGhost} disabled={dismiss.isPending} onClick={() => dismiss.mutate(s.id)}>
                      <X aria-hidden className="h-4 w-4" /> Reddet
                    </button>
                    <button type="button" className={btnPrimary} disabled={adopt.isPending} onClick={() => adopt.mutate(s.id)}>
                      <Check aria-hidden className="h-4 w-4" /> Taslağa al
                    </button>
                  </div>
                )}
              </article>
            ))}
          </div>
          {list.data && (
            <Pager page={list.data.page} pageSize={list.data.pageSize} total={list.data.total} shown={list.data.items.length}
              loading={list.isLoading} fetching={list.isFetching} onPage={setPage} />
          )}
        </>
      )}
    </>
  );
}

function PairsView({ meta }: { meta: SetsMeta }) {
  const [q, setQ] = useState('');
  const [page, setPage] = useState(0);
  const dq = useDebounced(q.trim(), 300);
  const res = useQuery({ queryKey: ['sets', 'pairs', dq, page], queryFn: () => setsApi.pairs({ q: dq, page }), placeholderData: keepPreviousData });
  const m = res.data?.meta;
  return (
    <section className="flex flex-col gap-2">
      <label className="flex max-w-md flex-col gap-1">
        <span className={labelCls}>Kitap ara</span>
        <input className={field} value={q} placeholder="Kitap adı ya da stok kodu" onChange={(e) => { setQ(e.target.value); setPage(0); }} />
      </label>
      <p className="px-1 text-[11.5px] text-canvas-muted">
        Yalnız tüketici (B2C) siparişleri; bayi siparişi sepet sayılmaz. En az {meta.settings.basketMinOrders} siparişte birlikte geçen bütün çiftler
        {m?.donem ? ` (${m.donem[0]} – ${m.donem[1]})` : ''}. Birliktelik oranı 1'in üstündeyse iki kitap tesadüften sık birlikte alınıyor demektir.
      </p>
      {res.error && <Note tone="err">{errText(res.error, 'Çiftler okunamadı.')}</Note>}
      {res.data && (
        <>
          <TableWrap>
            <thead>
              <tr className="border-b border-slate-100">
                <th className={th}>Kitap A</th>
                <th className={th}>Kitap B</th>
                <th className={`${th} text-right`}><InfoLabel k={res.data.kaynaklar} alan="items[]">Birlikte sipariş</InfoLabel></th>
                <th className={`${th} text-right`}><InfoLabel k={res.data.kaynaklar} alan="items[]">Birliktelik oranı</InfoLabel></th>
              </tr>
            </thead>
            <tbody>
              {res.data.items.map((r) => (
                <tr key={`${r.a}|${r.b}`} className="border-b border-slate-50 last:border-0">
                  <td className={td}>{r.adA ?? r.a}<div className="text-[11px] text-canvas-muted">{r.a}</div></td>
                  <td className={td}>{r.adB ?? r.b}<div className="text-[11px] text-canvas-muted">{r.b}</div></td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(r.siparis)}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{r.lift === null ? '—' : r.lift.toLocaleString('tr-TR', { maximumFractionDigits: 1 })}</td>
                </tr>
              ))}
              {!res.data.items.length && <tr><td className={`${td} text-canvas-muted`} colSpan={4}>Çift yok ya da henüz okunmadı.</td></tr>}
            </tbody>
          </TableWrap>
          <Pager page={res.data.page} pageSize={res.data.pageSize} total={res.data.total} shown={res.data.items.length}
            loading={res.isLoading} fetching={res.isFetching} onPage={setPage} />
        </>
      )}
    </section>
  );
}
