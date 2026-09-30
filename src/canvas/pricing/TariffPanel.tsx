import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { RotateCcw, Save } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Note, TableWrap, btnGhost, btnPrimary, errText, fmtDate, td, th } from '../admin/ui';
import { Panel } from '../editorial/kit';
import SqlInfo, { type FieldHelp } from '../components/SqlInfo';
import { day, num, pricingApi, type Tariff } from './api';
import { NumField, Select } from './parts';

/** Matbaa ve malzeme fiyat listesi: basım Excel'indeki fiyatların portaldaki hâli. Değiştirmek «Fiyat analizi hazırlama» ister. */

const PRICE_LABELS: Record<string, string> = {
  tekRenkKalip: 'Tek renk kalıp (forma başı)', renkliKalip: 'Renkli kalıp (renk başı)', 'Kabartma Lak-50x70': 'Kabartma lak', 'Lokal Lak-50x70': 'Lokal lak',
  'Simli Lak-50x70': 'Simli lak', 'DİSPERSİYON LAK': 'Dispersiyon lak', SELOFAN: 'Selofan (m²)', gofre: 'Gofre', yaldiz: 'Yaldız', sogukBaski: 'Soğuk baskı',
  ayracIscilik: 'Ayraç / afiş işçilik', somizIscilik: 'Şömiz işçilik', tekliVakum: 'Tekli vakumlu paket', gren: 'Gren uygulama', ozelKesimTbk: 'Özel kesim (TBK)',
  ozelKesimRadius: 'Özel kesim (radius)', sertKapakIplikDikis: 'Sert kapak iplik dikiş (forma)', sertKapakFormaHarman: 'Sert kapak forma harman (forma)',
  amerikanCiltForma: 'Amerikan cilt (forma)', telDikisForma: 'Tel dikiş (forma)', iplikDikis: 'İplik dikiş (forma)', boardPenceresiz: 'Board book penceresiz (sayfa)',
  boardPencereli: 'Board book pencereli (sayfa)', boardBristolMukavva: 'Board book bristol+mukavva (sayfa)', harmanlama: 'Harmanlama ve kutulama',
};
const FIRE_LABELS: Record<string, string> = {
  ic: 'İç kâğıt', renkli: 'Renkli sayfa', kapak: 'Kapak', yanKagit: 'Yan kâğıt', somiz: 'Şömiz', ayrac: 'Ayraç / afiş', mukavva: 'Mukavva', ciltBezi: 'Cilt bezi', digerKagit: 'Diğer tabaka',
};
const help = (ne: string, extra: Partial<FieldHelp> = {}): FieldHelp => ({ ne, nereden: 'İlk hâli basım Excel\'inden (14.09.2026); burada değiştirilir, değişiklik kaydına yazılır.', ...extra });
const i = (h: FieldHelp, label: string) => <SqlInfo k={null} alan="" label={label} help={h} />;

export default function TariffPanel() {
  const qc = useQueryClient();
  const setup = useQuery({ queryKey: ['pricing', 'form', 'setup', ''], queryFn: () => pricingApi.formSetup(null), enabled: ENGINE_ENABLED });
  const [t, setT] = useState<Tariff | null>(null);
  useEffect(() => {
    if (setup.data && !t) setT(setup.data.tariff);
  }, [setup.data, t]);
  const save = useMutation({
    mutationFn: (reset: boolean) => (reset ? pricingApi.saveTariff({ reset: true }) : pricingApi.saveTariff(t!)),
    onSuccess: (out) => {
      setT(out);
      qc.invalidateQueries({ queryKey: ['pricing', 'form'] });
      qc.invalidateQueries({ queryKey: ['pricing', 'compare'] });
    },
  });
  const can = !!setup.data?.canWrite;
  if (setup.error) return <Note tone="err">{errText(setup.error, 'Fiyat listesi okunamadı.')}</Note>;
  if (!t) return null;
  const up = (p: Partial<Tariff>) => setT({ ...t, ...p });
  const dirty = JSON.stringify(t) !== JSON.stringify(setup.data?.tariff);

  return (
    <Panel>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="flex items-center gap-1.5 text-[14px] font-extrabold">
            Matbaa ve malzeme fiyat listesi
            <SqlInfo k={setup.data?.kaynaklar} alan="tariff" label="Matbaa ve malzeme fiyat listesi"
              help={help('Kitap hesabının kullandığı birim fiyatlar: Logo\'da alışı olmayan kâğıdın ton fiyatı, kalıp ve kapak işlemleri, cilt işçiliği, fire payları, dolaylı gider oranı ve yayınevi vadeli iskontoları.', { excel: 'Excel\'in sağ tarafındaki tablolar: M9:Q35 (kâğıt), L42:X76 (matbaa kalemleri), L79:V203 (ebat), S7:T27 (iskonto).' })} />
          </h3>
          <p className="mt-0.5 text-[11.5px] text-canvas-muted">
            {t.isDefault ? 'Basım Excel\'lerindeki fiyatlar (14.09.2026) kullanılıyor.' : `Son değişiklik ${t.updatedBy ?? '—'} · ${fmtDate(t.updatedAt)}.`} Kâğıt fiyatı Logo alışından gelir; buradaki ton fiyatı yalnız
            Logo'da son 6 ayda alışı olmayan kâğıtta kullanılır.
          </p>
        </div>
        {can && (
          <div className="flex flex-wrap gap-2">
            <button type="button" className={btnGhost} disabled={save.isPending || t.isDefault} onClick={() => save.mutate(true)}>
              <RotateCcw aria-hidden className="h-4 w-4" /> İlk fiyatlara dön
            </button>
            <button type="button" className={btnPrimary} disabled={save.isPending || !dirty} onClick={() => save.mutate(false)}>
              <Save aria-hidden className="h-4 w-4" /> {save.isPending ? 'Kaydediliyor…' : 'Fiyat listesini kaydet'}
            </button>
          </div>
        )}
      </div>
      {!can && <p className="mt-1 text-[11.5px] text-canvas-muted">Fiyat listesini değiştirmek «Fiyat analizi hazırlama» yetkisi ister.</p>}
      {save.error && <div className="mt-2"><Note tone="err">{errText(save.error, 'Kaydedilemedi.')}</Note></div>}

      <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6">
        <div className="col-span-2 sm:col-span-3 xl:col-span-2">
          <Select<'logo' | 'elle'>
            label="Kur"
            disabled={!can}
            value={t.kurKaynak ?? 'logo'}
            onChange={(v) => up({ kurKaynak: v })}
            options={[
              { value: 'logo', label: 'Logo faturalarından' },
              { value: 'elle', label: 'Elle girilen kur' },
            ]}
            info={i(help('Bütün hesapların (kitap hesabı, eski kitap karşılaştırması) kullandığı dolar ve euro kuru. «Logo faturalarından»: Logo\'da o dövizle kesilen en son günün faturalarındaki kur; o dövizle fatura yoksa yandaki kur. «Elle girilen kur»: her zaman yandaki kur.', { excel: 'J56, J57.' }), 'Kur')}
            hint={logoKurText(setup.data?.logoKur)}
          />
        </div>
        <NumField label={t.kurKaynak === 'elle' ? '1 dolar (elle)' : '1 dolar (Logo\'da yoksa)'} suffix="₺" digits={4} disabled={!can} value={t.kur.USD} onChange={(v) => up({ kur: { ...t.kur, USD: v ?? t.kur.USD } })}
          info={i(help('Kur «Elle» seçiliyse bütün hesaplarda kullanılan dolar kuru; «Logo» seçiliyse yalnız Logo\'da dolar faturası yokken.', { excel: 'J56.' }), '1 dolar')} />
        <NumField label={t.kurKaynak === 'elle' ? '1 euro (elle)' : '1 euro (Logo\'da yoksa)'} suffix="₺" digits={4} disabled={!can} value={t.kur.EUR} onChange={(v) => up({ kur: { ...t.kur, EUR: v ?? t.kur.EUR } })}
          info={i(help('Kur «Elle» seçiliyse bütün hesaplarda kullanılan euro kuru; «Logo» seçiliyse yalnız Logo\'da euro faturası yokken.', { excel: 'J57.' }), '1 euro')} />
        <NumField label="Vade farkı (aylık)" suffix="%" disabled={!can} value={t.vade.oran} onChange={(v) => up({ vade: { ...t.vade, oran: v ?? 0 } })}
          info={i(help('Logo\'da alışı olmayan kâğıdın ton fiyatına eklenen vade farkı: aylık oran × vade süresi (5 × 6 = %30).', { excel: 'P7 (oran), P8 (süre), Q8 (fark).' }), 'Vade farkı')} />
        <NumField label="Vade süresi" suffix="ay" digits={0} disabled={!can} value={t.vade.ay} onChange={(v) => up({ vade: { ...t.vade, ay: v ?? 0 } })}
          info={i(help('Kâğıt ödemesinin vadesi (ay).', { excel: 'P8.' }), 'Vade süresi')} />
        <NumField label="Dolaylı gider" suffix="%" disabled={!can} value={t.dolayli} onChange={(v) => up({ dolayli: v ?? 0 })}
          info={i(help('Yeni kitapta dolaylı gider kutusuna gelen oran.', { excel: 'I41 (çoğu dosyada 90).' }), 'Dolaylı gider')} />
        <NumField label="Kapak ücreti bölünür" suffix="baskı" digits={0} disabled={!can} value={t.kapakBolen} onChange={(v) => up({ kapakBolen: v ?? 1 })}
          info={i(help('Kapak/çizim ücretinin kaç baskıya paylaştırıldığı (yeni kitaptaki varsayılan).', { excel: 'J33 = Y33 ÷ 3.' }), 'Kapak ücreti bölünür')} />
      </div>

      <details className="group mt-3">
        <summary className="min-h-11 cursor-pointer text-[12.5px] font-bold text-canvas-violet sm:min-h-0">Kâğıt ve malzeme fiyatları ({t.papers.length})</summary>
        <div className="mt-2">
          <TableWrap>
            <thead>
              <tr>
                <th className={th}>Malzeme</th>
                <th className={`${th} text-right`}>Fiyat</th>
                <th className={th}>Birim</th>
              </tr>
            </thead>
            <tbody>
              {t.papers.map((p, idx) => (
                <tr key={p.name} className="border-t border-slate-100">
                  <td className={td}>{p.name}</td>
                  <td className={`${td} w-40 text-right`}>
                    <NumField label="" value={p.base} disabled={!can} onChange={(v) => up({ papers: t.papers.map((x, j) => (j === idx ? { ...x, base: v ?? 0 } : x)) })} />
                  </td>
                  <td className={`${td} text-[12px] text-canvas-muted`}>{p.cur === 'USD' ? '$' : '€'} / {p.unit === 'ton' ? 'ton' : 'adet (tabaka)'}</td>
                </tr>
              ))}
            </tbody>
          </TableWrap>
        </div>
      </details>

      <details className="group mt-2">
        <summary className="min-h-11 cursor-pointer text-[12.5px] font-bold text-canvas-violet sm:min-h-0">Matbaa kalemleri ({Object.keys(PRICE_LABELS).length})</summary>
        <p className="mt-1 text-[11.5px] text-canvas-muted">«Fiyat»: sabit ya da birim bedel. «Ek bedel»: 1.000 adet/tabaka başına ek (kalıpta 3.000 adet üstü her 1.000 için).</p>
        <div className="mt-2">
          <TableWrap>
            <thead>
              <tr>
                <th className={th}>Kalem</th>
                <th className={`${th} text-right`}>Fiyat (₺)</th>
                <th className={`${th} text-right`}>Ek bedel (₺)</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(PRICE_LABELS).filter(([k]) => t.prices[k]).map(([k, label]) => (
                <tr key={k} className="border-t border-slate-100">
                  <td className={td}>{label}</td>
                  <td className={`${td} w-36`}>
                    <NumField label="" value={t.prices[k].m} disabled={!can} onChange={(v) => up({ prices: { ...t.prices, [k]: { ...t.prices[k], m: v ?? 0 } } })} />
                  </td>
                  <td className={`${td} w-36`}>
                    <NumField label="" value={t.prices[k].n} disabled={!can} onChange={(v) => up({ prices: { ...t.prices, [k]: { ...t.prices[k], n: v ?? 0 } } })} />
                  </td>
                </tr>
              ))}
            </tbody>
          </TableWrap>
        </div>
      </details>

      <details className="group mt-2">
        <summary className="min-h-11 cursor-pointer text-[12.5px] font-bold text-canvas-violet sm:min-h-0">Fire payları ve yayınevi iskontoları</summary>
        <div className="mt-2 grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-5">
          {Object.entries(t.fire).map(([k, v]) => (
            <NumField key={k} label={`Fire · ${FIRE_LABELS[k] ?? k}`} suffix="adet" digits={0} disabled={!can} value={v} onChange={(x) => up({ fire: { ...t.fire, [k]: x ?? 0 } })} />
          ))}
        </div>
        <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-5">
          {Object.entries(t.publishers).map(([k, v]) => (
            <NumField key={k} label={k} suffix="%" disabled={!can} value={v} onChange={(x) => up({ publishers: { ...t.publishers, [k]: x ?? 0 } })} />
          ))}
        </div>
        <p className="mt-2 text-[11px] text-canvas-muted">Ebat tablosu ({num(t.trims.length)} ebat) ve klişe fiyatları basım Excel'inden olduğu gibi alınır.</p>
      </details>
    </Panel>
  );
}

/** Logo'daki son döviz faturalarının kuru (seçimin altında bilgi olarak). */
function logoKurText(k: Partial<Record<'USD' | 'EUR', { rate: number; date: string | null }>> | undefined): string {
  const f = (c: 'USD' | 'EUR', sym: string) => (k?.[c] ? `1 ${sym} = ${k[c]!.rate.toLocaleString('tr-TR', { maximumFractionDigits: 4 })} ₺ (${day(k[c]!.date)})` : null);
  const parts = [f('USD', '$'), f('EUR', '€')].filter(Boolean);
  return parts.length ? `Logo: ${parts.join(' · ')}` : 'Logo\'da döviz faturası yok.';
}
