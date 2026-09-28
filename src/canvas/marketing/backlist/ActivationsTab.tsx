import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Copy } from 'lucide-react';
import { ENGINE_ENABLED } from '../../engine';
import { Loading, Note, Pill, btnGhost, errText } from '../../admin/ui';
import { STATUS_TONE, fmtMoney, fmtShortDay } from '../api';
import { Block } from '../parts';
import SqlInfo from '../../components/SqlInfo';
import { blApi, type Activation, type BlMeta } from './api';

/** Açılmış backlist planları ve durumları. Plan ekranı çekirdeğinki (kanal ve bütçe, takvim, materyal, onay).
 *  «CRM'e işlenecek kampanya»: portal CRM'e yazmaz; kampanya adı, tarih ve ürünler kopyalanıp CRM'e ekip tarafından işlenir. */
export default function ActivationsTab({ meta }: { meta: BlMeta }) {
  const [archive, setArchive] = useState(false);
  const q = useQuery({ queryKey: ['bl', 'activations', archive], queryFn: () => blApi.activations(archive), enabled: ENGINE_ENABLED });
  const copy = async (p: Activation) => {
    const ends = p.lines.map((l) => l.bitis).filter(Boolean).sort();
    const text = [`Kampanya adı: ${p.baslik}`, `Başlangıç: ${p.yayinTarihi ?? '—'}`, `Bitiş: ${ends[ends.length - 1] ?? '—'}`,
      'Ürünler (stok kodu):', ...p.kitaplar.map((b) => `  ${b.stokKodu} · ${b.ad ?? ''}`), 'İskonto: karar fiyatlama ve satış ekibinde'].join('\n');
    try {
      await navigator.clipboard.writeText(text);
      toast.success('Kampanya bilgisi kopyalandı.');
    } catch {
      toast.error('Kopyalanamadı.');
    }
  };
  const d = q.data;

  return (
    <div className="flex flex-col gap-3">
      <label className="inline-flex min-h-11 items-center gap-2 px-1 text-[12.5px] font-semibold sm:min-h-9">
        <input type="checkbox" className="h-4 w-4" checked={archive} onChange={(e) => setArchive(e.target.checked)} />
        Arşivdeki sürümleri de göster
      </label>
      {q.isLoading && <Loading />}
      {q.error && <Note tone="err">{errText(q.error, 'Planlar açılamadı.')}</Note>}
      {d && !d.items.length && <Note tone="info">Henüz backlist aktivasyon planı yok. Fırsatlar ya da Gündem sekmesinde kitapları seçip plan açın.</Note>}
      {d?.items.map((p) => (
        <Block key={p.id} title={p.baslik} info={<SqlInfo k={d?.kaynaklar} alan="items[]" label="Plan bütçesi" />}
          help={<>{p.id} · sürüm {p.surum} · başlangıç {fmtShortDay(p.yayinTarihi)} · sahibi {p.sahip ?? '—'}{meta.me.canSeeBudget && p.butceToplam !== null ? ` · bütçe ${fmtMoney(p.butceToplam)}` : ''}</>}
          action={
            <div className="flex flex-wrap items-center gap-2">
              <Pill tone={STATUS_TONE[p.durum]}>{p.durumAdi}</Pill>
              {p.durum === 'onayli' && <button type="button" className={btnGhost} onClick={() => copy(p)}><Copy aria-hidden className="h-4 w-4" />CRM'e işlenecek kampanya</button>}
              <Link className={btnGhost} to={`/pazarlama/plan/${encodeURIComponent(p.id)}`}>Planı aç</Link>
            </div>
          }>
          <ul className="flex flex-wrap gap-1.5 text-[12px]">
            {p.kitaplar.map((b) => (
              <li key={b.stokKodu} className="rounded-lg bg-white/80 px-2 py-1" title={b.gerekce ?? undefined}>
                <strong>{b.ad ?? b.stokKodu}</strong> <span className="text-canvas-muted">· {b.rolAdi}</span>
              </li>
            ))}
          </ul>
        </Block>
      ))}
    </div>
  );
}
