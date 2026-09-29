import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ENGINE_ENABLED } from '../engine';
import { Note, TableWrap, errText, td, th } from '../admin/ui';
import { Panel } from '../editorial/kit';
import SqlInfo from '../components/SqlInfo';
import { Explain } from '../components/Explain';
import { fmtDay, fmtInt, fmtPct, pazarApi } from './api';
import { DagitimTazelikLine } from '../stock/parts';

/** Pazar › Özet: dağıtımcı nabzı. Başarı Dağıtım kataloğunun görüntüleri arasındaki depo düşüşünden çıkış endeksi —
 *  kategori (TİMAŞ payıyla), yayınevi sırası, ay. Kitapçılara çıkıştır; okura satış ya da pazar payı diye yazılmaz. */

type Kirilim = 'kategori' | 'yayinevi' | 'ay';
const TABS: Array<[Kirilim, string]> = [['kategori', 'Kategori'], ['yayinevi', 'Yayınevi'], ['ay', 'Ay']];
const AYLAR = ['Oca', 'Şub', 'Mar', 'Nis', 'May', 'Haz', 'Tem', 'Ağu', 'Eyl', 'Eki', 'Kas', 'Ara'];
const ayAd = (ym: string) => `${AYLAR[Number(ym.slice(5, 7)) - 1] ?? ym.slice(5, 7)} ${ym.slice(0, 4)}`;

export default function DistributorPulse() {
  const [kirilim, setKirilim] = useState<Kirilim>('kategori');
  const [all, setAll] = useState(false);
  const q = useQuery({ queryKey: ['pazar', 'dagitim', 'summary'], queryFn: pazarApi.dagitimSummary, enabled: ENGINE_ENABLED, staleTime: 5 * 60_000 });
  const d = q.data;
  const kal = d?.kalibrasyon;
  const yay = d ? (all ? d.yayinevleri : d.yayinevleri.filter((y) => y.sira <= 15 || y.timas)) : [];

  return (
    <Panel>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="flex items-center gap-1 text-[15px] font-extrabold">
          Dağıtımcı nabzı
          <SqlInfo k={d?.kaynaklar} alan="kategoriler" label="Dağıtımcı nabzı" />
          <Explain label="Dağıtımcı nabzı" title="Bu rakam ne?">
            <span className="block">Başarı Dağıtım kataloğu her gün okunur; iki okuma arasında Başarı deposundaki stok düşüşü, o kitabın kitapçılara çıkışıdır.</span>
            <span className="block">Okura satış değildir, pazar payı değildir: tek dağıtımcıdır, arada gelip giden stok görünmez.</span>
            <span className="block">TİMAŞ payı, TİMAŞ grubunun kategorideki çıkış içindeki ağırlığıdır. {d?.timasNot}</span>
            {d?.timasMarkalar?.length ? <span className="block">Gruptaki markalar: {d.timasMarkalar.join(', ')}.</span> : null}
          </Explain>
        </h2>
        <div role="group" aria-label="Kırılım" className="flex gap-1 rounded-xl bg-slate-100 p-1">
          {TABS.map(([k, l]) => (
            <button
              key={k}
              type="button"
              aria-pressed={kirilim === k}
              onClick={() => setKirilim(k)}
              className={`min-h-11 rounded-lg px-2.5 text-[12px] font-extrabold transition-colors duration-150 sm:min-h-8 ${kirilim === k ? 'bg-white text-canvas-ink shadow-sm' : 'text-canvas-muted hover:text-canvas-ink'}`}
            >
              {l}
            </button>
          ))}
        </div>
      </div>
      {d && <div className="mt-2"><DagitimTazelikLine t={d.tazelik} /></div>}
      {d?.pencere && (
        <p className="mt-1 text-[11.5px] leading-snug text-canvas-muted">
          Başarı Dağıtım kataloğu, {fmtDay(d.pencere.bas)} – {fmtDay(d.pencere.son)} görüntüleri.
          {kal?.katsayi && kal.korelasyonCikis !== null
            ? ` TİMAŞ kitaplarında Logo sevkiyle sıralama tutarlılığı ${fmtPct(kal.korelasyonCikis * 100, 0)}; adet olarak endeks gerçeğin yaklaşık ${kal.katsayi.toLocaleString('tr-TR')}’te biri.`
            : ''}
        </p>
      )}
      {q.error && <Note tone="err">{errText(q.error, 'Dağıtımcı verisi okunamadı.')}</Note>}
      {q.isLoading && <p className="mt-2 text-[12.5px] text-canvas-muted">Dağıtımcı verisi okunuyor…</p>}
      {d && !d.pencere && <Note tone="info">Başarı kataloğundan henüz iki görüntü birikmedi; çıkış hesaplanamıyor.</Note>}
      {d?.pencere && (
        <div className="mt-2">
          <TableWrap>
            {kirilim === 'kategori' && (
              <>
                <thead>
                  <tr className="border-b border-slate-100">
                    <th className={th}>Kategori</th>
                    <th className={`${th} text-right`}>Çıkış endeksi</th>
                    <th className={`${th} text-right`}>Kategorinin payı</th>
                    <th className={`${th} text-right`}>TİMAŞ çıkışı</th>
                    <th className={`${th} text-right`}>TİMAŞ payı</th>
                  </tr>
                </thead>
                <tbody>
                  {d.kategoriler.map((r) => (
                    <tr key={r.kategori} className="border-b border-slate-50 last:border-0">
                      <td className={`${td} font-semibold`}>{r.kategori}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(r.cikis)}</td>
                      <td className={`${td} text-right font-mono tabular-nums text-canvas-muted`}>{fmtPct(r.kategoriPay)}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(r.timasCikis)}</td>
                      <td className={`${td} text-right font-mono tabular-nums font-bold`}>{fmtPct(r.timasPay)}</td>
                    </tr>
                  ))}
                  <tr className="bg-slate-50/80 font-bold">
                    <td className={td}>Toplam</td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(d.toplam)}</td>
                    <td className={td} />
                    <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(d.timasToplam)}</td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{d.toplam ? fmtPct((100 * (d.timasToplam ?? 0)) / d.toplam) : '—'}</td>
                  </tr>
                </tbody>
              </>
            )}
            {kirilim === 'yayinevi' && (
              <>
                <thead>
                  <tr className="border-b border-slate-100">
                    <th className={`${th} text-right`}>Sıra</th>
                    <th className={th}>Yayınevi</th>
                    <th className={`${th} text-right`}>Çıkış endeksi</th>
                    <th className={`${th} text-right`}>Toplam içindeki pay</th>
                  </tr>
                </thead>
                <tbody>
                  {yay.map((r) => (
                    <tr key={r.yayinevi} className={`border-b border-slate-50 last:border-0 ${r.timas ? 'bg-violet-50/60' : ''}`}>
                      <td className={`${td} text-right font-mono tabular-nums text-canvas-muted`}>{fmtInt(r.sira)}</td>
                      <td className={`${td} font-semibold`}>{r.yayinevi}{r.timas ? <span className="ml-1.5 text-[10.5px] font-extrabold uppercase tracking-wide text-canvas-violet">TİMAŞ</span> : null}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(r.cikis)}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{fmtPct(r.pay)}</td>
                    </tr>
                  ))}
                </tbody>
              </>
            )}
            {kirilim === 'ay' && (
              <>
                <thead>
                  <tr className="border-b border-slate-100">
                    <th className={th}>Ay</th>
                    <th className={`${th} text-right`}>Çıkış endeksi</th>
                    <th className={`${th} text-right`}>TİMAŞ çıkışı</th>
                    <th className={`${th} text-right`}>TİMAŞ payı</th>
                  </tr>
                </thead>
                <tbody>
                  {d.aylar.map((r) => (
                    <tr key={r.ay} className="border-b border-slate-50 last:border-0">
                      <td className={`${td} font-semibold`}>{ayAd(r.ay)}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(r.cikis)}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(r.timasCikis)}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{r.cikis ? fmtPct((100 * r.timasCikis) / r.cikis) : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </>
            )}
          </TableWrap>
          {kirilim === 'yayinevi' && d.yayinevleri.some((y) => y.sira > 15 && !y.timas) && (
            <button type="button" onClick={() => setAll((v) => !v)} className="mt-2 min-h-11 text-[12.5px] font-extrabold text-canvas-violet hover:underline sm:min-h-0">
              {all ? 'İlk 15 ve TİMAŞ markalarını göster' : 'Tümünü göster'}
            </button>
          )}
          <p className="mt-2 text-[11.5px] leading-snug text-canvas-muted">{d.not}</p>
        </div>
      )}
    </Panel>
  );
}
