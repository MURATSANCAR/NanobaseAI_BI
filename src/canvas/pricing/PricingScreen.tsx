import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { RefreshCw } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, btnGhost, errText, nf } from '../admin/ui';
import { Kpi, KpiRow } from '../editorial/kit';
import { Tabs } from '../editorial/freelance/shared';
import Frame from './Frame';
import { day, overviewKey, pct, pricingApi } from './api';
import CalcPane from './CalcPane';
import FormPane from './FormPane';
import AnalysesPane from './AnalysesPane';
import ActualsPane from './ActualsPane';
import BacklistPane from './BacklistPane';
import DataPane from './DataPane';
import SqlInfo from '../components/SqlInfo';

/**
 * Fiyatlama ve maliyet (M9). Bölüm ve açık kayıt adreste durur (?bolum=, ?kitap=, ?analiz=); bağlantı paylaşılabilir.
 * Rakamlar Logo'nun ve CRM'in salt okunur anlık görüntüsünden gelir (6 saatte bir ya da «Verileri yenile»).
 */

export type Section = 'form' | 'hesap' | 'analizler' | 'gerceklesen' | 'backlist' | 'veri';
const SECTIONS: Section[] = ['form', 'hesap', 'analizler', 'gerceklesen', 'backlist', 'veri'];

/** Veri sonu bu kadar günden eskiyse ekran Logo verisinin güncel olmadığını söyler. */
const STALE_DAYS = 3;

export default function PricingScreen() {
  const [params, setParams] = useSearchParams();
  const section = (SECTIONS.includes(params.get('bolum') as Section) ? params.get('bolum') : 'form') as Section;
  const qc = useQueryClient();
  const ov = useQuery({
    queryKey: overviewKey,
    queryFn: pricingApi.overview,
    enabled: ENGINE_ENABLED,
    // Görüntü hazırlanırken durum sık sorulur; hazırsa dakikada bir.
    refetchInterval: (q) => (q.state.data?.status.refreshing || !q.state.data?.measured ? 10_000 : 60_000),
  });
  const o = ov.data;
  const refresh = useMutation({
    mutationFn: pricingApi.refresh,
    onSuccess: () => qc.invalidateQueries({ queryKey: overviewKey }),
  });
  const go = (s: Section, extra: Record<string, string> = {}) => setParams({ bolum: s, ...extra });
  const m = o?.measured;

  return (
    <Frame
      title="Fiyatlama ve maliyet"
      lead="Maliyet formu: basım Excel'indeki Kitap Maliyet Formu'nun aynısı (kâğıt, baskı, kapak, cilt, telif, dolaylı gider). Fiyat analizi: baskı adedi senaryoları, başabaş, kapak fiyatı önerisi, kanal matrisi ve onay. Ayrıca Logo'dan gerçekleşen maliyet ve backlist fiyat revizyonu. Buradan CRM'e, Logo'ya ya da e-ticarete yazılmaz."
      source={m ? `Logo + CRM · veri sonu ${day(m.dataEnd)}` : 'Logo + CRM'}
      presence={o?.status.refreshing ? 'Veriler yenileniyor…' : m ? `Görüntü ${day(m.asOf)}` : 'Hazırlanıyor'}
    >
      {!ENGINE_ENABLED && <Note tone="warn">ZEKİ AI bağlantısı bu derlemede tanımlı değil.</Note>}
      {ov.error && <Note tone="err">{errText(ov.error, 'Özet okunamadı.')}</Note>}
      {o?.status.error && <Note tone="warn">{o.status.error}</Note>}
      {o && !m && (
        <Note tone="info">
          Logo ve CRM verisi ilk kez hazırlanıyor (baskı faturaları, satışlar, kanal iskontoları, kâğıt fiyatları). Bu birkaç dakika sürer;
          ekran kendiliğinden yenilenir.
        </Note>
      )}
      {m && m.warnings.length > 0 && <Note tone="warn">{m.warnings.join(' ')}</Note>}
      {m && staleDays(m.dataEnd) > STALE_DAYS && (
        <Note tone="warn">
          Logo verisi {day(m.dataEnd)} tarihinde bitiyor ({staleDays(m.dataEnd)} gün önce): kâğıt fiyatı, kur, baskı faturaları ve satışlar o güne kadar.
          Logo bağlantısı canlıya geçince veriler 6 saatte bir kendiliğinden yenilenir.
        </Note>
      )}

      {o && (
        <KpiRow>
          <Kpi
            label="Onayınızı bekleyen"
            value={nf.format(o.toApprove)}
            help={`${nf.format(o.counts.onayda ?? 0)} analiz onayda · ${nf.format(o.counts.onaylandi ?? 0)} onaylandı`}
            active={section === 'analizler'}
            onClick={() => go('analizler', { durum: 'onayda' })}
            info={<SqlInfo k={o.kaynaklar} alan="toApprove" label="Onayınızı bekleyen analizler" />}
          />
          <Kpi
            label="Ortalama kanal iskontosu"
            value={pct(m?.discount)}
            help={m ? `Son 12 ay kitap satışı, ${nf.format(m.channels.length)} müşteri grubu` : 'Ölçülüyor'}
            active={section === 'veri'}
            onClick={() => go('veri')}
            info={<SqlInfo k={o.kaynaklar} alan="measured.discount" label="Ortalama kanal iskontosu" />}
          />
          <Kpi
            label="Baskı faturası"
            value={m ? nf.format(m.printInvoices) : '—'}
            help={m ? `${nf.format(m.printedBooks)} kitabın matbaa faturası (2021'den)` : 'Ölçülüyor'}
            active={section === 'gerceklesen'}
            onClick={() => go('gerceklesen')}
            info={<SqlInfo k={o.kaynaklar} alan="measured.printInvoices" label="Baskı faturası sayısı" />}
          />
          <Kpi
            label="Veri sonu"
            value={m ? day(m.dataEnd) : '—'}
            help={m ? `Logo'daki son fatura · ${m.copies.map((c) => `${c.from.slice(0, 4)}–${c.last.slice(0, 4)}`).join(', ')}` : 'Ölçülüyor'}
            info={<SqlInfo k={o.kaynaklar} alan="measured.copies" label="Veri sonu ve Logo yıl kopyaları" />}
          />
        </KpiRow>
      )}

      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex min-w-0 flex-1 items-center gap-1">
          <div className="min-w-0 flex-1">
          <Tabs<Section>
            value={section}
            onChange={(s) => go(s)}
            items={[
              { key: 'form', label: 'Maliyet formu' },
              { key: 'hesap', label: 'Fiyat analizi' },
              { key: 'analizler', label: 'Analizler ve onay', badge: o?.toApprove || undefined },
              { key: 'gerceklesen', label: 'Gerçekleşen' },
              { key: 'backlist', label: 'Backlist revizyonu' },
              { key: 'veri', label: 'Veri ve varsayımlar' },
            ]}
          />
          </div>
          {!!o?.toApprove && <SqlInfo k={o.kaynaklar} alan="toApprove" label="«Analizler ve onay» sekmesindeki sayı" />}
        </div>
        {o?.me.canWrite && (
          <button type="button" className={btnGhost} disabled={refresh.isPending || o.status.refreshing} onClick={() => refresh.mutate()}>
            <RefreshCw aria-hidden className={`h-4 w-4 ${o.status.refreshing ? 'animate-spin' : ''}`} />
            {o.status.refreshing ? 'Yenileniyor…' : 'Verileri yenile'}
          </button>
        )}
      </div>
      {refresh.error && <Note tone="err">{errText(refresh.error, 'Yenileme başlatılamadı.')}</Note>}

      {!o ? (
        !ov.error && <Loading />
      ) : section === 'form' ? (
        <FormPane ov={o} />
      ) : section === 'hesap' ? (
        <CalcPane ov={o} />
      ) : section === 'analizler' ? (
        <AnalysesPane ov={o} />
      ) : section === 'gerceklesen' ? (
        <ActualsPane ready={!!m} />
      ) : section === 'backlist' ? (
        <BacklistPane ov={o} />
      ) : (
        <DataPane ov={o} />
      )}
    </Frame>
  );
}

/** Veri sonunun bugünden kaç gün önce olduğu. */
function staleDays(end: string | null | undefined): number {
  if (!end) return 0;
  const d = new Date(`${end.slice(0, 10)}T00:00:00Z`).getTime();
  return Number.isNaN(d) ? 0 : Math.floor((Date.now() - d) / 86_400_000);
}
