import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { toast } from 'sonner';
import { RefreshCw } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Note, btnGhost, errText } from '../admin/ui';
import { Tabs } from '../budget/parts';
import { cnApi, fmtStamp } from './api';
import { CnFrame, DataAge } from './parts';
import CatalogList from './CatalogList';
import NewsletterList from './NewsletterList';
import Report from './Report';

type Tab = 'katalog' | 'bulten' | 'rapor';

/** M24 Katalog ve bülten — ilk açılış. Sekme adres çubuğunda (/katalog-bulten?sekme=bulten, /katalog-bulten/rapor). */
export default function CatalogNewsletterHome({ initial = 'katalog' }: { initial?: Tab }) {
  const qc = useQueryClient();
  const nav = useNavigate();
  const [params, setParams] = useSearchParams();
  const tab = (params.get('sekme') as Tab | null) ?? initial;
  const meta = useQuery({
    queryKey: ['cn', 'meta'],
    queryFn: cnApi.meta,
    enabled: ENGINE_ENABLED,
    refetchInterval: (q) => (q.state.data?.havuz.yenileniyor || (q.state.data && !q.state.data.havuz.okuma) ? 15_000 : false),
  });
  const refresh = useMutation({
    mutationFn: cnApi.refreshPool,
    onSuccess: (r) => {
      toast.success(r.started ? 'Kitap havuzu kaynaktan okunuyor; birkaç dakika sürer.' : 'Okuma zaten sürüyor.');
      qc.invalidateQueries({ queryKey: ['cn', 'meta'] });
    },
    onError: (e) => toast.error(errText(e, 'Yenileme başlatılamadı.') ?? ''),
  });
  const m = meta.data;
  const setTab = (t: Tab) => {
    if (t === 'rapor') nav('/katalog-bulten/rapor');
    else if (initial === 'rapor') nav(t === 'bulten' ? '/katalog-bulten?sekme=bulten' : '/katalog-bulten');
    else setParams(t === 'katalog' ? {} : { sekme: t }, { replace: true });
  };

  return (
    <CnFrame
      crumb="Katalog ve bülten"
      title="Katalog ve bülten"
      lead="Dönemsel kataloglar tek kitap verisinden kurulur: her kitabın neden katalogda olduğu yazar, fiyat ve stok basıma kadar izlenir. E-bülten segment sayısı izin kuralını delmez; portal toplu e-posta göndermez, kişi listesi vermez — onaylanan HTML şirketin e-posta aracından gönderilir."
      source={m?.havuz.okuma ? `Kitap havuzu ${fmtStamp(m.havuz.okuma)}` : 'CRM + Logo'}
      presence={m ? `${m.havuz.kitap.toLocaleString('tr-TR')} kitap` : '…'}
      aside={
        m?.me.canCatalog ? (
          <div className="flex flex-wrap items-center justify-end gap-2">
            <button type="button" className={btnGhost} disabled={refresh.isPending || m.havuz.yenileniyor} onClick={() => refresh.mutate()}>
              <RefreshCw aria-hidden className={`h-4 w-4 ${m.havuz.yenileniyor ? 'animate-spin' : ''}`} />
              {m.havuz.yenileniyor ? 'Kaynak okunuyor…' : 'Kaynaktan yenile'}
            </button>
          </div>
        ) : null
      }
    >
      {!ENGINE_ENABLED && <Note tone="warn">Veri bağlantısı bu derlemede tanımlı değil.</Note>}
      {meta.error && <Note tone="err">{errText(meta.error, 'Katalog ve bülten bilgisi açılamadı.')}</Note>}
      {m && !m.havuz.okuma && (
        <Note tone={m.havuz.hata ? 'err' : 'info'}>
          {m.havuz.hata ? `Kitap havuzu okunamadı: ${m.havuz.hata}` : 'Kitap havuzu ilk kez okunuyor (CRM kitap kartları, stok ve satış hızı). Birkaç dakika sürer; bu sayfa kendiliğinden yenilenir.'}
        </Note>
      )}
      {m?.havuz.okuma && <DataAge pool={m.havuz} />}
      {m?.sonKosu?.eposta === 'no_smtp' && <Note tone="warn">Sabah özeti gönderilemedi: e-posta ayarı yok (Yönetim → E-posta).</Note>}

      <Tabs<Tab>
        tabs={[
          { key: 'katalog', label: 'Kataloglar', badge: m?.bekleyen.katalogOnayda || null },
          { key: 'bulten', label: 'Bültenler', badge: m?.bekleyen.bultenOnayda || null },
          { key: 'rapor', label: 'Rapor' },
        ]}
        value={tab}
        onChange={setTab}
      />
      {m && tab === 'katalog' && <CatalogList meta={m} />}
      {m && tab === 'bulten' && <NewsletterList meta={m} />}
      {m && tab === 'rapor' && <Report />}
    </CnFrame>
  );
}
