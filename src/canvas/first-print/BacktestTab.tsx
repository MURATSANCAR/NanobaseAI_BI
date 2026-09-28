import { useState } from 'react';
import { CartesianGrid, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ReferenceLine } from 'recharts';
import { Note, Pill, TableWrap, td, th } from '../admin/ui';
import SqlCode from '../management/SqlCode';
import { Box, Segmented, TierPill } from './parts';
import SqlInfo from '../components/SqlInfo';
import { fmtUnits, monthName, pct, type Backtest, type Metrics, type PrintRules, type Summary } from './api';

/** Geçmiş sınama: geçmişte çıkmış kitaplar, çıkıştan 2 ay önceki veriyle tahmin edilip gerçekleşenle karşılaştırılır.
 *  Hata oranı olduğu gibi gösterilir; iki basit yöntemle (son 12 ayın ortancası, yalnız CRM emsali) yan yana. */

const ROWS: Array<{ key: keyof Metrics; label: string; hint: string; fmt: (v: number) => string; better: 'low' | 'high' | 'one' }> = [
  { key: 'mdape', label: 'Tipik sapma', hint: 'Tahminle gerçekleşen arasındaki farkın ortancası (gerçekleşene göre)', fmt: (v) => pct(v), better: 'low' },
  { key: 'within25', label: '±%25 içinde', hint: 'Gerçekleşenin tahminin %80–125\'i arasında kaldığı kitap oranı', fmt: (v) => pct(v), better: 'high' },
  { key: 'within50', label: '±%50 içinde', hint: 'Gerçekleşenin tahminin %67–150\'si arasında kaldığı kitap oranı', fmt: (v) => pct(v), better: 'high' },
  { key: 'within2x', label: '2 kat içinde', hint: 'Gerçekleşenin tahminin yarısı ile iki katı arasında kaldığı kitap oranı', fmt: (v) => pct(v), better: 'high' },
  { key: 'wape', label: 'Toplam adette sapma', hint: 'Bütün kitapların farklarının toplamı ÷ gerçekleşen toplam (çok satanlar ağır basar)', fmt: (v) => pct(v), better: 'low' },
  { key: 'bias', label: 'Yön (gerçekleşen ÷ tahmin, ortanca)', hint: '1\'in üstü: tahmin eksik kalıyor; altı: fazla', fmt: (v) => v.toLocaleString('tr-TR', { maximumFractionDigits: 2 }), better: 'one' },
];

function MetricsTable({ bt }: { bt: Backtest }) {
  const cols: Array<{ key: 'model' | 'naive' | 'emsal'; label: string }> = [
    { key: 'model', label: 'Emsal puanlı tahmin (kural)' },
    { key: 'emsal', label: 'Yalnız CRM emsalleri' },
    { key: 'naive', label: 'Son 12 ayın ortancası' },
  ];
  return (
    <TableWrap>
      <thead>
        <tr className="border-b border-slate-100">
          <th className={th}>Ölçü</th>
          {cols.map((c) => <th key={c.key} className={`${th} text-right`}>{c.label}</th>)}
        </tr>
      </thead>
      <tbody>
        {ROWS.map((r) => (
          <tr key={r.key} className="border-b border-slate-50 last:border-0">
            <td className={td}>
              <div className="font-bold">{r.label}</div>
              <div className="text-[11px] text-canvas-muted">{r.hint}</div>
            </td>
            {cols.map((c) => {
              const m = bt[c.key];
              return (
                <td key={c.key} className={`${td} text-right font-mono tabular-nums ${c.key === 'model' ? 'font-bold' : ''}`}>
                  {m ? r.fmt(m[r.key] as number) : '—'}
                </td>
              );
            })}
          </tr>
        ))}
        <tr>
          <td className={td}><div className="font-bold">Kitap sayısı</div></td>
          {cols.map((c) => <td key={c.key} className={`${td} text-right font-mono tabular-nums`}>{fmtUnits(bt[c.key]?.n)}</td>)}
        </tr>
      </tbody>
    </TableWrap>
  );
}

function Scatterplot({ bt }: { bt: Backtest }) {
  const data = bt.samples.filter((x) => x.actual > 0 && x.forecast > 0).map((x) => ({ x: x.forecast, y: x.actual, name: x.name }));
  const max = Math.max(10, ...data.map((d) => Math.max(d.x, d.y)));
  return (
    <div className="h-72 w-full" role="img" aria-label="Tahmin ve gerçekleşen satış, kitap başına; köşegen tam isabet">
      <ResponsiveContainer width="100%" height="100%">
        <ScatterChart margin={{ left: 0, right: 12, top: 8, bottom: 8 }}>
          <CartesianGrid stroke="#e5e7eb" strokeDasharray="3 3" />
          <XAxis type="number" dataKey="x" name="Tahmin" scale="log" domain={[1, max]} tick={{ fontSize: 10 }} tickFormatter={(v: number) => fmtUnits(v)} allowDataOverflow />
          <YAxis type="number" dataKey="y" name="Gerçekleşen" scale="log" domain={[1, max]} tick={{ fontSize: 10 }} width={52} tickFormatter={(v: number) => fmtUnits(v)} allowDataOverflow />
          <ReferenceLine segment={[{ x: 1, y: 1 }, { x: max, y: max }]} stroke="#7C5CFF" strokeDasharray="4 4" />
          <Tooltip
            cursor={{ strokeDasharray: '3 3' }}
            content={({ payload }) => {
              const p = payload?.[0]?.payload as { x: number; y: number; name: string } | undefined;
              if (!p) return null;
              return (
                <div className="rounded-xl border border-slate-100 bg-white px-3 py-2 text-[12px] shadow-canvas-card">
                  <div className="font-bold">{p.name}</div>
                  <div>Tahmin {fmtUnits(p.x)} · Gerçekleşen {fmtUnits(p.y)}</div>
                </div>
              );
            }}
          />
          <Scatter data={data} fill="#7C5CFF" fillOpacity={0.35} isAnimationActive={false} />
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  );
}

function PrintRulesTable({ pr }: { pr: PrintRules }) {
  return (
    <>
      <TableWrap>
        <thead>
          <tr className="border-b border-slate-100">
            <th className={th}>Baskı adedi</th>
            <th className={`${th} text-right`}>Ortanca adet</th>
            <th className={`${th} text-right`}>6 ayda tükenen</th>
            <th className={`${th} text-right`}>12 ayda tükenen</th>
            <th className={`${th} text-right`}>12. ay sonunda elde kalan</th>
          </tr>
        </thead>
        <tbody>
          {pr.rules.map((r) => (
            <tr key={r.id} className="border-b border-slate-50 last:border-0">
              <td className={td}>
                <span className="font-bold">{r.label}</span>
                {r.id === pr.recommended && <span className="ml-2 align-middle"><Pill tone="violet">önerilen</Pill></span>}
              </td>
              <td className={`${td} text-right font-mono tabular-nums`}>{fmtUnits(r.medianPrint)}</td>
              <td className={`${td} text-right font-mono tabular-nums`}>{pct(r.stockout6)}</td>
              <td className={`${td} text-right font-mono tabular-nums`}>{pct(r.stockout12)}</td>
              <td className={`${td} text-right font-mono tabular-nums`}>{pct(r.leftover12)}</td>
            </tr>
          ))}
          {pr.theirs && (
            <tr>
              <td className={td}>
                <span className="font-bold">Yayınevinin gerçek ilk baskısı</span>
                <div className="text-[11px] text-canvas-muted">yalnız tek baskılı {fmtUnits(pr.theirs.n)} kitap</div>
              </td>
              <td className={`${td} text-right font-mono tabular-nums`}>{fmtUnits(pr.theirs.medianPrint)}</td>
              <td className={`${td} text-right font-mono tabular-nums`}>{pct(pr.theirs.stockout6)}</td>
              <td className={`${td} text-right font-mono tabular-nums`}>{pct(pr.theirs.stockout12)}</td>
              <td className={`${td} text-right font-mono tabular-nums`}>{pct(pr.theirs.leftover12)}</td>
            </tr>
          )}
        </tbody>
      </TableWrap>
      <p className="mt-2 text-[11.5px] leading-snug text-canvas-muted">
        Yayınevinin satırı olduğundan iyi görünür: CRM ilk baskı adedini yalnız hiç yeniden basılmamış kitapta verir; tükenip yeniden basılan
        kitaplar bu satıra giremez. Adil karşılaştırma için tükenen kitapların da ilk baskı adedi gerekir. Öneri, 6 aylık baz satışı asgari sayıp
        iyimser senaryoya göre basar: tükenme ile elde kalan arasında denge. Kitap 12. aydan sonra da sattığı için elde kalan çoğunlukla sonraki
        ayların stokudur.
      </p>
    </>
  );
}

export default function BacktestTab({ s }: { s: Summary }) {
  const [h, setH] = useState<'6' | '12'>('6');
  const bt = s.backtest?.[h];
  const bt6 = s.backtest?.['6'];
  const pr = s.backtest?.print;
  if (!bt) return <Note tone="info">Geçmiş sınama henüz yok.</Note>;
  const m = bt.model;
  return (
    <div className="flex flex-col gap-3 lg:gap-4">
      <Box
        info={<SqlInfo k={s.kaynaklar} alan="backtest" label="Tahmin ne kadar tutuyor" />}
        title="Tahmin ne kadar tutuyor"
        help={`${monthName(bt.from)} ile ${monthName(bt.to)} arasında çıkan her kitap, çıkışından 2 ay önceki veriyle (o gün baskı kararı verilirken bilinenle) tahmin edildi ve ilk ${bt.horizon} ayda gerçekten satılanla karşılaştırıldı. Ayarlar yalnız 2021 ortası–2023 sonu kitaplarıyla seçildi; buradaki kitaplar ayar seçiminde kullanılmadı.`}
        action={<Segmented label="Ufuk" value={h} onChange={setH} options={[{ key: '6', label: 'İlk 6 ay' }, { key: '12', label: 'İlk 12 ay' }]} />}
      >
        {m && (
          <p className="mb-3 max-w-[80ch] text-[13px] leading-relaxed">
            Tahmin, kitapların yarısında gerçekleşenden <b>{pct(m.mdape)}</b>'den az saptı; kitapların <b>{pct(m.within25)}</b>'inde sapma
            ±%25 içinde, <b>{pct(m.within2x)}</b>'inde iki katın içinde kaldı. %80 güven aralığı gerçekleşeni kitapların <b>{pct(bt.coverage80)}</b>'inde
            içine aldı. Yeni bir kitabın satışı özünde belirsizdir: tek bir sayı yerine aralığa ve senaryolara bakın; kitap çıktıktan sonra ilk ayların
            satışıyla tahmin hızla daralır (aşağıda).
          </p>
        )}
        <MetricsTable bt={bt} />
      </Box>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2 lg:gap-4">
        <Box info={<SqlInfo k={s.kaynaklar} alan="backtest" label="Kitap kitap tahmin ve gerçekleşen" />} title="Kitap kitap tahmin ve gerçekleşen" help="Her nokta bir kitap; kesik çizgi tam isabet. Eksenler logaritmik.">
          <Scatterplot bt={bt} />
        </Box>
        <Box info={<SqlInfo k={s.kaynaklar} alan="backtest" label="İlk baskı bu kadar yapılsaydı" />} title="İlk baskı bu kadar yapılsaydı" help="12 ayı gözlenmiş sınama kitapları: ilk 6 / 12 ayda satışın baskıyı aştığı (tükenen) kitap oranı ve 12. ay sonunda elde kalan payın ortancası.">
          {pr ? <PrintRulesTable pr={pr} /> : <p className="text-[12px] text-canvas-muted">Henüz yok.</p>}
        </Box>
      </div>

      {h === '6' && bt6?.revise && (
        <Box info={<SqlInfo k={s.kaynaklar} alan="backtest" label="Kitap çıktıktan sonra: revize tahmin" />} title="Kitap çıktıktan sonra: revize tahmin" help="Gerçekleşen ilk ay(lar) + emsallerin aynı aydan 6. aya büyümesi. Aynı sınama kitapları.">
          <TableWrap>
            <thead>
              <tr className="border-b border-slate-100">
                <th className={th}>Ne zaman</th>
                <th className={`${th} text-right`}>Tipik sapma</th>
                <th className={`${th} text-right`}>±%25 içinde</th>
                <th className={`${th} text-right`}>2 kat içinde</th>
              </tr>
            </thead>
            <tbody>
              <tr className="border-b border-slate-50">
                <td className={td}>Çıkıştan önce</td>
                <td className={`${td} text-right font-mono tabular-nums`}>{pct(bt6.model?.mdape)}</td>
                <td className={`${td} text-right font-mono tabular-nums`}>{pct(bt6.model?.within25)}</td>
                <td className={`${td} text-right font-mono tabular-nums`}>{pct(bt6.model?.within2x)}</td>
              </tr>
              {Object.entries(bt6.revise).map(([k, v]) => (
                <tr key={k} className="border-b border-slate-50 last:border-0">
                  <td className={td}>İlk {k} ay gerçekleşince</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{pct(v?.mdape)}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{pct(v?.within25)}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{pct(v?.within2x)}</td>
                </tr>
              ))}
            </tbody>
          </TableWrap>
        </Box>
      )}

      {bt.byTier && (
        <Box info={<SqlInfo k={s.kaynaklar} alan="backtest" label="Güven düzeyine göre" />} title="Güven düzeyine göre" help="Güven düzeyi emsallerin gücünden gelir (CRM emsali, aynı yazar, aynı dizi). Düşük güvenli tahmine tek başına dayanmayın.">
          <TableWrap>
            <thead>
              <tr className="border-b border-slate-100">
                <th className={th}>Güven</th>
                <th className={`${th} text-right`}>Kitap</th>
                <th className={`${th} text-right`}>Tipik sapma</th>
                <th className={`${th} text-right`}>2 kat içinde</th>
                <th className={`${th} text-right`}>Aralık tuttu</th>
              </tr>
            </thead>
            <tbody>
              {(['yuksek', 'orta', 'dusuk'] as const).map((t) => {
                const v = bt.byTier?.[t];
                if (!v) return null;
                return (
                  <tr key={t} className="border-b border-slate-50 last:border-0">
                    <td className={td}><TierPill tier={t} /></td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{fmtUnits(v.n)}</td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{pct(v.mdape)}</td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{pct(v.within2x)}</td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{pct(v.coverage80)}</td>
                  </tr>
                );
              })}
            </tbody>
          </TableWrap>
        </Box>
      )}

      <Box info={<SqlInfo k={s.kaynaklar} alan="backtest" label="Yıllara göre" />} title="Yıllara göre" help="Çıkış yılına göre tipik sapma ve kitap sayısı.">
        <TableWrap>
          <thead>
            <tr className="border-b border-slate-100">
              <th className={th}>Çıkış yılı</th>
              <th className={`${th} text-right`}>Kitap</th>
              <th className={`${th} text-right`}>Tipik sapma</th>
              <th className={`${th} text-right`}>±%50 içinde</th>
              <th className={`${th} text-right`}>Yön</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(bt.byYear).map(([y, v]) => (
              <tr key={y} className="border-b border-slate-50 last:border-0">
                <td className={td}>{y}</td>
                <td className={`${td} text-right font-mono tabular-nums`}>{fmtUnits(v?.n)}</td>
                <td className={`${td} text-right font-mono tabular-nums`}>{pct(v?.mdape)}</td>
                <td className={`${td} text-right font-mono tabular-nums`}>{pct(v?.within50)}</td>
                <td className={`${td} text-right font-mono tabular-nums`}>{v ? v.bias.toLocaleString('tr-TR', { maximumFractionDigits: 2 }) : '—'}</td>
              </tr>
            ))}
          </tbody>
        </TableWrap>
      </Box>

      <Box info={<SqlInfo k={s.kaynaklar} alan="backtest" label="Nasıl hesaplandı" />} title="Nasıl hesaplandı" help="Formüller ve kaynak sorgular.">
        <ul className="mb-3 space-y-1.5 text-[12.5px] leading-snug">
          {s.formulas.map((f) => (
            <li key={f.name}><b>{f.name}:</b> {f.text}</li>
          ))}
          {s.notes.map((n) => <li key={n} className="text-canvas-muted">{n}</li>)}
        </ul>
        <div className="flex flex-col gap-2">
          {s.sources.map((src) => (
            <details key={src.id} className="rounded-xl border border-slate-100 bg-white/70 px-3 py-2">
              <summary className="cursor-pointer text-[12.5px] font-bold">
                {src.title} <span className="font-normal text-canvas-muted">· {src.connection === 'logo' ? 'Logo' : 'CRM'}{src.rows !== null ? ` · ${fmtUnits(src.rows)} satır` : ''}</span>
              </summary>
              <p className="mt-1 text-[12px] text-canvas-muted">{src.description}</p>
              {src.sql ? (
                <div className="mt-2 overflow-x-auto"><SqlCode sql={src.sql} label={src.title} /></div>
              ) : (
                <p className="mt-1 text-[12px] text-canvas-muted">Sorgu, ilk okumadan sonra çalışan hâliyle (yıl görünümleri yerinde) görünür.</p>
              )}
            </details>
          ))}
        </div>
      </Box>
    </div>
  );
}
