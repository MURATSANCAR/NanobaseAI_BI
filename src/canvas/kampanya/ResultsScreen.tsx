import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Loader2, RefreshCw, Sparkles, Trash2 } from 'lucide-react';
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Note, TableWrap, btnGhost, btnPrimary, errText, field, label as labelCls, td, th } from '../admin/ui';
import { Kpi, KpiRow, Panel } from '../editorial/kit';
import { fmtDay, fmtInt, fmtMoney, fmtPct } from '../budget/api';
import { kampanyaApi, type Campaign, type Donem, type Overview } from './api';

/** Kampanya sonucu: önce / kampanya / sonra dönemleri (Logo, günlük), kitap kitap satış, Zeki AI özeti ve öğrenim kaydı. */

const DONEM = { once: 'Önceki eşit dönem', kampanya: 'Kampanya', sonra: 'Sonrası' } as const;
const COLOR = { once: '#94a3b8', kampanya: '#7C5CFF', sonra: '#cbd5e1' } as const;

export default function ResultsScreen({ c, ov }: { c: Campaign; ov: Overview }) {
  const qc = useQueryClient();
  const res = useQuery({ queryKey: ['kampanya', 'results', c.id], queryFn: () => kampanyaApi.results(c.id) });
  const refresh = useMutation({
    mutationFn: () => kampanyaApi.refreshResults(c.id),
    onSuccess: (r) => { qc.setQueryData(['kampanya', 'results', c.id], r); toast.success('Sonuç Logo’dan okundu.'); },
    onError: (e) => toast.error(errText(e, 'Sonuç okunamadı.') ?? ''),
  });
  const summary = useMutation({
    mutationFn: () => kampanyaApi.summary(c.id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['kampanya', 'results', c.id] }); toast.success('Özet yazıldı.'); },
    onError: (e) => toast.error(errText(e, 'Özet yazılamadı.') ?? ''),
  });
  const [ozet, setOzet] = useState('');
  const [tur, setTur] = useState('');
  const learn = useMutation({
    mutationFn: () => kampanyaApi.addLearning(c.id, { ozet: ozet.trim(), tur: tur.trim() || undefined }),
    onSuccess: () => { setOzet(''); setTur(''); qc.invalidateQueries({ queryKey: ['kampanya'] }); toast.success('Öğrenim kaydedildi.'); },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  const drop = useMutation({
    mutationFn: kampanyaApi.removeLearning,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['kampanya'] }),
    onError: (e) => toast.error(errText(e, 'Silinemedi.') ?? ''),
  });
  const r = res.data;
  const readable = ['onaylandi', 'yurutuluyor', 'bitti'].includes(c.durum);

  if (!readable) return <Note tone="info">Sonuç kampanya onaylandıktan sonra Logo’dan okunur.</Note>;
  if (res.error) return <Note tone="err">{errText(res.error, 'Sonuç açılamadı.')}</Note>;
  if (!r) return <Panel><div className="py-8 text-center text-[12px] text-canvas-muted">Yükleniyor…</div></Panel>;
  const k = r.donemler.kampanya;
  const o = r.donemler.once;

  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-[12px] font-semibold text-canvas-muted">Logo verisi {fmtDay(r.logoKesim)} tarihine kadar · günlük (saatlik değil).</span>
        {ov.me.canEdit && (
          <button type="button" className={btnGhost} disabled={refresh.isPending} onClick={() => refresh.mutate()}>
            {refresh.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <RefreshCw aria-hidden className="h-4 w-4" />}
            Logo’dan yeniden oku
          </button>
        )}
      </div>
      {r.notlar.map((n, i) => <Note key={i} tone="info">{n}</Note>)}
      <KpiRow>
        <Kpi label="Günlük satış (kampanya)" value={k?.gunlukAdet === null || k?.gunlukAdet === undefined ? '—' : fmtInt(k.gunlukAdet)}
          help={`Önceki dönem ${o?.gunlukAdet === null || o?.gunlukAdet === undefined ? '—' : fmtInt(o.gunlukAdet)} · ${r.degisim.satis === null ? 'değişim yok' : `${r.degisim.satis.toLocaleString('tr-TR', { maximumFractionDigits: 2 })} kat`}`} />
        <Kpi label="Kampanya satışı" value={fmtInt(k?.adet)} help={`${fmtMoney(k?.tutar)} net · ${k ? `${k.gun}/${k.gunToplam} gün okundu` : ''}`} />
        <Kpi label="İade oranı" value={fmtPct(k?.iadeOrani)} help={`Önceki ${fmtPct(o?.iadeOrani)}${r.degisim.iadePuan !== null ? ` · ${r.degisim.iadePuan >= 0 ? '+' : ''}${(r.degisim.iadePuan * 100).toFixed(1).replace('.', ',')} puan` : ''}`} />
        <Kpi label="Gerçekleşen marj" value={k?.marjOrani === null || k?.marjOrani === undefined ? '—' : fmtPct(k.marjOrani)}
          help={`Maliyeti girilmiş satışlardan (${fmtPct(k?.maliyetKapsami)} kapsam) · önceki ${fmtPct(o?.marjOrani)}`} />
      </KpiRow>
      {r.crmEtki && (
        <Note tone="info">CRM’de bu bayi kampanyasına bağlı {fmtInt(r.crmEtki.siparis)} sipariş, {fmtInt(r.crmEtki.adet)} adet, kampanya indirimi {fmtMoney(r.crmEtki.indirim)}.</Note>
      )}
      {r.crmEtkiHata && <Note tone="warn">CRM etkisi okunamadı: {r.crmEtkiHata}</Note>}
      {r.seri.length > 0 && (
        <Panel>
          <h2 className="mb-2 text-[15px] font-extrabold tracking-tight">Günlük satış (adet)</h2>
          <div className="h-56 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={r.seri.map((x) => ({ ...x, [x.donem]: x.adet }))} margin={{ top: 4, right: 4, left: -18, bottom: 0 }}>
                <CartesianGrid vertical={false} stroke="#e2e8f0" />
                <XAxis dataKey="gun" tickFormatter={(v: string) => v.slice(8, 10) + '.' + v.slice(5, 7)} tick={{ fontSize: 10 }} minTickGap={16} />
                <YAxis tick={{ fontSize: 10 }} allowDecimals={false} />
                <Tooltip formatter={(v) => (typeof v === 'number' ? fmtInt(v) : '—')} labelFormatter={(v) => fmtDay(String(v))} />
                {(Object.keys(DONEM) as (keyof typeof DONEM)[]).map((d) => (
                  <Bar key={d} dataKey={d} name={DONEM[d]} stackId="a" fill={COLOR[d]} isAnimationActive={false} />
                ))}
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Panel>
      )}
      <Panel>
        <h2 className="mb-2 text-[15px] font-extrabold tracking-tight">Dönemler</h2>
        <TableWrap>
          <thead>
            <tr>
              <th className={th}>Dönem</th>
              <th className={`${th} text-right`}>Gün (okunan)</th>
              <th className={`${th} text-right`}>Satış</th>
              <th className={`${th} text-right`}>Günlük</th>
              <th className={`${th} text-right`}>İade</th>
              <th className={`${th} text-right`}>Net tutar</th>
              <th className={`${th} text-right`}>Marj</th>
            </tr>
          </thead>
          <tbody>
            {(Object.keys(DONEM) as (keyof typeof DONEM)[]).map((d) => {
              const x: Donem | undefined = r.donemler[d];
              if (!x) return null;
              return (
                <tr key={d} className="border-t border-slate-100">
                  <td className={td}><div className="font-semibold">{DONEM[d]}</div><div className="text-[11px] text-canvas-muted">{fmtDay(x.bas)} – {fmtDay(x.bit)}</div></td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{x.gun}/{x.gunToplam}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(x.adet)}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(x.gunlukAdet)}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(x.iade)}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtMoney(x.tutar)}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{x.marjOrani === null ? 'hesaplanamaz' : fmtPct(x.marjOrani)}</td>
                </tr>
              );
            })}
          </tbody>
        </TableWrap>
      </Panel>
      {r.kitaplar.length > 0 && (
        <Panel>
          <h2 className="mb-2 text-[15px] font-extrabold tracking-tight">Kitap kitap</h2>
          <TableWrap>
            <thead>
              <tr>
                <th className={th}>Kitap</th>
                <th className={`${th} text-right`}>İndirim</th>
                <th className={`${th} text-right`}>Önce</th>
                <th className={`${th} text-right`}>Kampanya</th>
                <th className={`${th} text-right`}>Sonra</th>
                <th className={`${th} text-right`}>İade</th>
                <th className={`${th} text-right`}>Değişim</th>
              </tr>
            </thead>
            <tbody>
              {r.kitaplar.map((b) => (
                <tr key={b.stok} className="border-t border-slate-100">
                  <td className={td}><div className="font-semibold">{b.ad ?? b.stok}</div><div className="text-[11px] text-canvas-muted">{b.stok}</div></td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtPct(b.indirim, 0)}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(b.onceAdet)}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(b.kampanyaAdet)}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(b.sonraAdet)}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(b.kampanyaIade)}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{b.degisim === null ? '—' : `${b.degisim.toLocaleString('tr-TR', { maximumFractionDigits: 2 })} kat`}</td>
                </tr>
              ))}
            </tbody>
          </TableWrap>
        </Panel>
      )}
      <Panel>
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-[15px] font-extrabold tracking-tight">Zeki AI özeti</h2>
          {ov.me.canCopy && r.seri.length > 0 && (
            <button type="button" className={btnGhost} disabled={summary.isPending} onClick={() => summary.mutate()}>
              {summary.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Sparkles aria-hidden className="h-4 w-4" />}
              {r.ozet ? 'Yeniden yaz' : 'Özet yaz'}
            </button>
          )}
        </div>
        {r.ozet ? (
          <>
            <p className="whitespace-pre-line text-[13px] leading-relaxed">{r.ozet}</p>
            <p className="mt-1 text-[11px] text-canvas-muted">Rakamlar yukarıdaki tablodan; kaynağı olmayan rakam içeren cümle atılır. {fmtDay(r.ozetAt)}</p>
          </>
        ) : (
          <p className="text-[12px] text-canvas-muted">Kampanya bitip Logo verisi bitişe ulaşınca özet gece kendiliğinden yazılır.</p>
        )}
      </Panel>
      <Panel>
        <h2 className="mb-2 text-[15px] font-extrabold tracking-tight">Öğrenim</h2>
        <ul className="flex flex-col gap-2">
          {r.ogrenimler.map((l) => (
            <li key={l.id} className="rounded-xl bg-white/80 px-3 py-2.5">
              <div className="flex flex-wrap items-center justify-between gap-2 text-[11.5px] font-semibold text-canvas-muted">
                <span>{l.yazan} · {fmtDay(l.tarih)}{l.tur ? ` · ${l.tur}` : ''} · satış {l.satisDegisimi === null ? '—' : `${l.satisDegisimi.toLocaleString('tr-TR', { maximumFractionDigits: 2 })} kat`}</span>
                {(l.yazan === ov.me.username || ov.me.admin) && (
                  <button type="button" className={btnGhost} aria-label="Öğrenimi sil" onClick={() => drop.mutate(l.id)} disabled={drop.isPending}>
                    <Trash2 aria-hidden className="h-4 w-4" />
                  </button>
                )}
              </div>
              <p className="mt-1 whitespace-pre-line text-[12.5px] leading-snug">{l.ozet}</p>
            </li>
          ))}
        </ul>
        {c.durum === 'bitti' && ov.me.canEdit ? (
          <form className="mt-3 flex flex-col gap-2" onSubmit={(e) => { e.preventDefault(); if (ozet.trim()) learn.mutate(); }}>
            <label className="flex flex-col gap-1">
              <span className={labelCls}>Ne öğrendik</span>
              <textarea className={field} rows={3} value={ozet} onChange={(e) => setOzet(e.target.value)}
                placeholder="Örn. hikâye kitaplarında %30 indirim satışı artırdı, iade değişmedi; stok iki kitapta yetmedi" />
            </label>
            <label className="flex flex-col gap-1 sm:w-[260px]">
              <span className={labelCls}>Tür (isteğe bağlı)</span>
              <input className={field} value={tur} onChange={(e) => setTur(e.target.value)} placeholder="Örn. flaş indirim" />
            </label>
            <button type="submit" className={`${btnPrimary} self-start`} disabled={!ozet.trim() || learn.isPending}>Öğrenimi kaydet</button>
            <p className="text-[11px] text-canvas-muted">İndirim, satış ve iade değişimi sonuçtan kendiliğinden yazılır; sonraki kampanyanın tükenme tahmini bu kayıtları kullanır.</p>
          </form>
        ) : (
          c.durum !== 'bitti' && <p className="mt-2 text-[12px] text-canvas-muted">Öğrenim kampanya bitince yazılır.</p>
        )}
      </Panel>
    </>
  );
}
