import { useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Plus } from 'lucide-react';
import { ENGINE_ENABLED } from '../../engine';
import { Note, btnPrimary, errText, nf } from '../../admin/ui';
import { Kpi, KpiRow } from '../../editorial/kit';
import Frame from './Frame';
import SqlInfo from '../../components/SqlInfo';
import { creativeApi } from './api';
import RequestsBoard from './RequestsBoard';
import AssetLibrary from './AssetLibrary';
import BrandKit from './BrandKit';
import NewRequestSheet from './NewRequestSheet';
import { useCreativeMeta } from './useMeta';

/** M19 Pazarlama görsel ve metin: talep panosu, onaylı varlık arşivi, marka kiti. Sekme, süzgeç ve «yeni talep»
 *  adres çubuğunda durur (?sekme=, ?durum=, ?yeni=1); bağlantı paylaşılabilir. Sekme değişimi anlıktır. */

const TABS = [
  { key: 'talepler', label: 'Talepler' },
  { key: 'arsiv', label: 'Arşiv' },
  { key: 'marka', label: 'Marka kiti' },
] as const;
type Tab = (typeof TABS)[number]['key'];

export default function CreativeHome() {
  const [params, setParams] = useSearchParams();
  const tab: Tab = (TABS.find((t) => t.key === params.get('sekme'))?.key ?? 'talepler') as Tab;
  const update = useCallback(
    (next: Record<string, string | null>) => {
      const p = new URLSearchParams(params);
      for (const [k, v] of Object.entries(next)) {
        if (v) p.set(k, v);
        else p.delete(k);
      }
      setParams(p, { replace: true });
    },
    [params, setParams],
  );
  const meta = useCreativeMeta();
  const sum = useQuery({ queryKey: ['creative', 'summary'], queryFn: creativeApi.summary, enabled: ENGINE_ENABLED, refetchInterval: 60_000 });
  const s = sum.data;
  const me = meta.data?.me;
  const err = errText(meta.error || sum.error, 'Ekran okunamadı.');

  const aside = (
    <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
      <div className="grid flex-1 grid-cols-3 gap-1 rounded-2xl bg-slate-100 p-1" role="tablist" aria-label="Görünüm">
        {TABS.map((t) => (
          <button key={t.key} type="button" role="tab" aria-selected={tab === t.key}
            onClick={() => update({ sekme: t.key === 'talepler' ? null : t.key, sayfa: null, q: null })}
            className={`min-h-11 rounded-xl px-2 text-[12px] font-extrabold transition-colors duration-150 sm:min-h-9 ${
              tab === t.key ? 'bg-canvas-violet text-white shadow-md' : 'text-canvas-ink hover:bg-white/70'}`}>
            {t.label}
          </button>
        ))}
      </div>
      {me?.talep && (
        <button type="button" className={btnPrimary} onClick={() => update({ yeni: '1' })}>
          <Plus className="h-4 w-4" aria-hidden />Yeni talep
        </button>
      )}
    </div>
  );

  return (
    <Frame
      crumb="Görsel ve metin"
      title="Görsel ve metin"
      source="Stüdyo pazarlama kiti + CRM kitap kartı"
      lead="Sosyal medya, reklam, site ve e-bülten için görsel ve metin talepleri. Görsel tek tasarımdan bütün boyutlarda hazırlanır, metinler Zeki AI taslağıdır. Görsel önce tasarım, sonra mesaj onayı alır; onaylı paketi indirip kanala siz yüklersiniz, hiçbir yere kendiliğinden gönderilmez."
      aside={aside}
    >
      {!ENGINE_ENABLED && <Note tone="warn">Veri bağlantısı kurulu değil; bu ekran şu an veri gösteremez. Sistem yöneticinize haber verin.</Note>}
      {err && <Note tone="err">{err}</Note>}
      <KpiRow>
        <Kpi label="Yeni talep" value={s ? nf.format(s.yeniTalep) : '—'} help="Son 24 saatte açılan" onClick={() => update({ sekme: null, durum: 'talep' })}
          info={<SqlInfo k={s?.kaynaklar} alan="yeniTalep" label="Yeni talep" />}
          explain="Son 24 saatte açılmış, henüz üretime alınmamış görsel ve metin talepleri. Karta dokunursanız pano bu taleplere süzülür." />
        <Kpi label="Tasarım onayı" value={s?.tasarimBekleyen != null ? nf.format(s.tasarimBekleyen) : '—'}
          help={s?.tasarimBekleyen == null ? 'Rolünüzde tasarım onayı yok' : 'Onay bekleyen görsel'} onClick={() => update({ sekme: null, durum: 'tasarim-onayi' })}
          info={<SqlInfo k={s?.kaynaklar} alan="tasarimBekleyen" label="Tasarım onayı" />}
          explain="Görselin tasarım yönünden (yerleşim, renk, marka kurallarına uygunluk) onay bekleyen talepler. Bu onayı yalnız tasarım onay yetkisi olan kişi verir." />
        <Kpi label="Mesaj onayı" value={s?.mesajBekleyen != null ? nf.format(s.mesajBekleyen) : '—'}
          help={s?.mesajBekleyen == null ? 'Rolünüzde mesaj onayı yok' : 'Onay bekleyen görsel ve metin'} onClick={() => update({ sekme: null, durum: 'mesaj-onayi' })}
          info={<SqlInfo k={s?.kaynaklar} alan="mesajBekleyen" label="Mesaj onayı" />}
          explain="İçeriğin söylediği şey yönünden son onayı bekleyen görsel ve metinler. Görsel buraya tasarım onayından sonra gelir; aynı kişi bir görsele iki onayı birden veremez." />
        <Kpi label="Termini yakın" value={s ? nf.format(s.terminiYaklasan.length) : '—'} help="2 gün ya da daha az kalan, onaysız" onClick={() => update({ sekme: null, durum: null })}
          info={<SqlInfo k={s?.kaynaklar} alan="terminiYaklasan" label="Termini yakın" />}
          explain="Teslim tarihine (termin) 2 gün ya da daha az kalmış ve henüz onaylanmamış talepler." />
      </KpiRow>

      {tab === 'talepler' && <RequestsBoard params={params} update={update} due={s?.terminiYaklasan ?? []} />}
      {tab === 'arsiv' && <AssetLibrary params={params} update={update} />}
      {tab === 'marka' && <BrandKit canEdit={!!me?.marka} />}

      <NewRequestSheet open={params.get('yeni') === '1'} onClose={() => update({ yeni: null })} />
    </Frame>
  );
}
