import { useState } from 'react';
import { BookText, GraduationCap, Megaphone, ShoppingBag, Share2 } from 'lucide-react';
import { Loading, Note, errText } from '../../../admin/ui';
import { Panel } from '../../kit';
import { press } from '../shared';
import BackCoverTab from './BackCoverTab';
import GuideTab from './GuideTab';
import ProductTab from './ProductTab';
import SocialTab from './SocialTab';
import { useMarketing, useMarketingRefresh, type MarketingView } from './api';

/** Stüdyonun «Pazarlama» bölümü: arka kapak yazısı, e-ticaret ürün sayfası, sosyal medya görselleri, öğretmen okuma
 *  kılavuzu. Metinleri Zeki AI kitabın kendi metninden yazar; her çıktı editör onayı ister (kim onayladı kaydedilir),
 *  onaysız çıktı indirilemez, kapağa uygulanamaz, SEO'ya gitmez. Sekme değişimi anlıktır (hareket yok). */

type Tab = 'back' | 'product' | 'social' | 'guide';
const TABS: [Tab, string, typeof BookText][] = [
  ['back', 'Arka kapak', BookText], ['product', 'Ürün sayfası', ShoppingBag],
  ['social', 'Sosyal medya', Share2], ['guide', 'Öğretmen kılavuzu', GraduationCap],
];

function done(v: MarketingView, t: Tab): boolean {
  if (t === 'back') return !!v.back_cover.approved;
  if (t === 'product') return !!v.product.approved;
  if (t === 'social') return v.social.items.some((x) => x.approved);
  return !!v.guide.approved;
}

export default function MarketingKit({ jobId }: { jobId: string }) {
  const [tab, setTab] = useState<Tab>('back');
  const q = useMarketing(jobId);
  const refresh = useMarketingRefresh(jobId);
  const v = q.data;

  return (
    <Panel>
      <div id="pazarlama" className="flex min-w-0 flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="min-w-0">
            <h2 className="flex items-center gap-2 text-[16px] font-extrabold"><Megaphone className="h-5 w-5 text-canvas-violet" aria-hidden />Pazarlama</h2>
            <p className="text-[12px] text-canvas-muted">Arka kapak yazısı, ürün sayfası, sosyal medya görselleri ve öğretmen kılavuzu. Hepsi editör onayıyla.</p>
          </div>
        </div>
        <div role="tablist" aria-label="Pazarlama kiti" className="-mx-1 flex gap-1.5 overflow-x-auto px-1 pb-1">
          {TABS.map(([k, t, Icon]) => (
            <button key={k} type="button" role="tab" id={`mk-tab-${k}`} aria-selected={tab === k} aria-controls={`mk-panel-${k}`}
              onClick={() => setTab(k)}
              className={`inline-flex min-h-10 shrink-0 items-center gap-1.5 rounded-xl border px-3 text-[13px] font-bold ${press} ${tab === k ? 'border-canvas-violet bg-violet-50 text-canvas-violet' : 'border-slate-200 bg-white/70 text-canvas-ink'}`}>
              <Icon className="h-4 w-4" aria-hidden />{t}
              {v && done(v, k) && <span className="h-2 w-2 rounded-full bg-emerald-500" aria-label="onaylı" />}
            </button>
          ))}
        </div>
        <div role="tabpanel" id={`mk-panel-${tab}`} aria-labelledby={`mk-tab-${tab}`} className="min-w-0">
          {!v ? (q.error ? <Note tone="info">{errText(q.error, 'Pazarlama kiti okunamadı.')}</Note> : <Loading />)
            : tab === 'back' ? <BackCoverTab jobId={jobId} v={v} refresh={refresh} />
            : tab === 'product' ? <ProductTab jobId={jobId} v={v} refresh={refresh} />
            : tab === 'social' ? <SocialTab jobId={jobId} v={v} refresh={refresh} />
            : <GuideTab jobId={jobId} v={v} refresh={refresh} />}
        </div>
      </div>
    </Panel>
  );
}
