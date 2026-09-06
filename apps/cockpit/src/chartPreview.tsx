// GEÇİCİ doğrulama sayfası — köprü lokalde yokken ResultChart'ı gerçek spec'lerle çizer.
import ReactDOM from 'react-dom/client';
import { ResultChart } from './components/ResultChart';
import type { WidgetSpec } from './lib/wren';
import './styles.css';

type Case = { name: string; widget: WidgetSpec; records: Record<string, unknown>[] };

const AY = ['2026-01','2026-02','2026-03','2026-04','2026-05','2026-06','2026-07','2026-08'];

const CASES: Case[] = [
  { name: 'kpi — tek skaler',
    widget: { id: '1', type: 'kpi', title: 'Ağustos 2026 net satış tutarı nedir', value_key: 'net_satis_tutari', format: 'number' },
    records: [{ net_satis_tutari: 922418666 }] },
  { name: 'multi_card — tek satır çok ölçü',
    widget: { id: '2', type: 'multi_card', title: '2026 satış özeti', label_key: 'label', value_key: 'value',
      data: { columns: ['label','value'], rows: [{ label: 'satis_tutari', value: 1_040_000_000 }, { label: 'iade_tutari', value: 117_600_000 }, { label: 'net_ciro', value: 922_400_000 }] } },
    records: [] },
  { name: 'line — aylık seri',
    widget: { id: '3', type: 'line', title: '2026 yılında aylık net satış tutarı nedir', x_key: 'ay', y_key: 'net_ciro', label_key: 'ay', value_key: 'net_ciro' },
    records: AY.map((ay, i) => ({ ay, net_ciro: 84e6 + Math.sin(i) * 26e6 + i * 5e6 })) },
  { name: 'pie — kanal kırılımı (4 satır)',
    widget: { id: '4', type: 'pie', title: 'Kanal bazında net ciro nedir', x_key: 'kanal', y_key: 'net_ciro', label_key: 'kanal', value_key: 'net_ciro' },
    records: [{ kanal: 'Bayi', net_ciro: 512e6 }, { kanal: 'E-ticaret', net_ciro: 214e6 }, { kanal: 'Kurumsal', net_ciro: 96e6 }, { kanal: 'Perakende', net_ciro: 41e6 }] },
  { name: 'bar — en çok iade alan 10 müşteri',
    widget: { id: '5', type: 'bar', title: 'En çok iade alan 10 müşteri kimler', x_key: 'musteri_unvani', y_key: 'iade_tutari', label_key: 'musteri_unvani', value_key: 'iade_tutari' },
    records: [
      'DR MAĞAZACILIK A.Ş.','KİTAPYURDU DAĞITIM','BKM KİTAP PAZARLAMA','İDEFİX İNTERNET','NEZİH KIRTASİYE',
      'REMZİ KİTABEVİ','ARKADAŞ YAYINCILIK','PANDORA KİTAP','TÜRK EĞİTİM DERNEĞİ','MİGROS TİCARET A.Ş.',
    ].map((musteri_unvani, i) => ({ musteri_unvani, iade_tutari: 4.2e6 - i * 3.4e5 })) },
  { name: 'bar — en çok satan kitaplar (adet, ₺ değil)',
    widget: { id: '6', type: 'bar', title: 'En çok satan 10 kitap hangileri (adet)', x_key: 'kitap', y_key: 'satilan_adet', label_key: 'kitap', value_key: 'satilan_adet' },
    records: ['Şu Çılgın Türkler','Kürk Mantolu Madonna','İnce Memed','Tutunamayanlar','Beyaz Kale','Serenad','Puslu Kıtalar Atlası','Simyacı']
      .map((kitap, i) => ({ kitap, satilan_adet: 41200 - i * 3600 })) },
];

function Board() {
  return (
    <div className="min-h-screen bg-page p-6">
      <h1 className="font-display text-[20px] font-semibold text-ink">ResultChart — spec doğrulaması</h1>
      <p className="mt-1 text-[12px] text-ink-muted">Solda dar panel (330px), sağda geniş panel (560px). Tipler backend'in ürettiği spec'lerle birebir.</p>
      <div className="mt-5 space-y-6">
        {CASES.map((c) => (
          <div key={c.name}>
            <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-ink-faint">{c.name}</div>
            <div className="flex flex-wrap items-start gap-4">
              <div className="w-[330px] rounded-2xl border border-line bg-white p-3">
                <p className="text-[13px] leading-snug">{c.widget.title}</p>
                <ResultChart widget={c.widget} records={c.records} />
              </div>
              <div className="w-[560px] rounded-2xl border border-line bg-white p-3">
                <p className="text-[13px] leading-snug">{c.widget.title}</p>
                <ResultChart widget={c.widget} records={c.records} wide />
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')!).render(<Board />);
