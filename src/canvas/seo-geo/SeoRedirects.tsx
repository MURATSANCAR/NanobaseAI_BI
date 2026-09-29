import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, ChevronLeft, ChevronRight, Download, ExternalLink, FileSpreadsheet, Loader2, Search, X } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { fmt, seoApi, type Confidence, type Redirect } from './api';
import SeoLayout, { Failed, Loading } from './SeoLayout';
import { useCan } from '../useAdmin';
import { xlsxUrl } from '../components/excel';
import { EmptyHint, Explain } from '../components/Explain';
import { Term } from './terms';

const PAGE = 40;
const CONF: Array<{ id: Confidence; label: string; tone: string }> = [
  { id: 'kesin', label: 'Kesin', tone: 'good' },
  { id: 'yüksek', label: 'Yüksek', tone: 'good' },
  { id: 'orta', label: 'Orta — kontrol edin', tone: 'mid' },
  { id: 'yok', label: 'Eşleşme yok', tone: 'bad' },
];
const STATUS: Record<Redirect['status'], string> = { bekliyor: 'Bekliyor', onaylandi: 'Onaylandı', reddedildi: 'Reddedildi' };
/** Güven düzeyinin nasıl verildiği (eşleştirme kuralları; ilk tutan kazanır). */
const CONF_WHY: Record<Confidence, string> = {
  kesin: 'Eski adreste ISBN var ve o ISBN’li kitap sitede satışta; yönlendirme aynı kitaba gider.',
  yüksek: 'Aynı adlı kitabın yeni baskısı, aynı adlı yazar sayfası ya da adresin kelimelerinin büyük kısmı hedefte de geçiyor.',
  orta: 'Yalnız iki kelime ya da yazım benzerliği tutuyor; hedefi açıp doğru sayfa olduğuna bakın.',
  yok: 'Güvenilir bir hedef bulunamadı; hedef adresi sizin yazmanız gerekir.',
};

/** Anasayfaya giden 301 yönlendirmeleri: her biri için doğru hedef önerisi, gerekçesi ve alternatifleri. Karar yalnız
 *  kaydedilir; T-soft'a yazılmaz. Onaylananlar CSV olarak indirilip T-soft panelinden elle girilir. */
export default function SeoRedirects() {
  const canExport = useCan('veri.disa-aktar');
  const qc = useQueryClient();
  const [confidence, setConfidence] = useState<Confidence | ''>('');
  const [status, setStatus] = useState<'' | Redirect['status']>('bekliyor');
  const [q, setQ] = useState('');
  const [query, setQuery] = useState('');
  const [start, setStart] = useState(0);
  useEffect(() => {
    const t = setTimeout(() => setQuery(q), 300);
    return () => clearTimeout(t);
  }, [q]);
  useEffect(() => setStart(0), [confidence, status, query]);

  const me = useQuery({ queryKey: ['seo-me'], queryFn: seoApi.me, enabled: ENGINE_ENABLED, retry: false, staleTime: 300_000 });
  const list = useQuery({
    queryKey: ['seo-redirects', confidence, status, query, start],
    queryFn: () => seoApi.redirects({ confidence, status, q: query, start, limit: PAGE }),
    enabled: ENGINE_ENABLED,
    retry: false,
    placeholderData: (p) => p,
  });
  const refresh = () => qc.invalidateQueries({ queryKey: ['seo-redirects'] });
  const bulk = useMutation({ mutationFn: seoApi.approveRedirects, onSuccess: refresh });
  const counts = list.data?.counts ?? {};
  const count = (c: string, s = '') =>
    Object.entries(counts)
      .filter(([k]) => k.startsWith(`${c}|`) && (!s || k.endsWith(`|${s}`)))
      .reduce((a, [, n]) => a + n, 0);
  const total = list.data?.total ?? 0;
  const canApprove = !!me.data?.canApprove;

  return (
    <SeoLayout k={list.data?.kaynaklar}
      path="/seo-geo/yonlendirmeler"
      crumb="Yönlendirmeler"
      eyebrow="SEO & GEO · 301 yönlendirmeleri"
      title="Anasayfaya giden yönlendirmeler"
      lead={<>Silinen sayfaların eski adresi anasayfaya gidiyorsa Google bunu «yumuşak 404» (boş sayfa) sayar ve eski adresin değeri kaybolur. Her eski adres için yaşayan en doğru sayfa önerilir; siz onaylar ya da hedefi düzeltirsiniz. <Term k="redirect" /> Karar yalnız kaydedilir; onaylananları CSV olarak indirip T-soft paneline elle girin.</>}
      actions={
        canExport && (
          <>
            <a className="sg-button" href={seoApi.redirectCsvUrl()}>
              <Download size={16} aria-hidden /> Onaylananları indir (CSV)
            </a>
            <a className="sg-button" href={xlsxUrl(seoApi.redirectCsvUrl())}>
              <FileSpreadsheet size={16} aria-hidden /> Onaylananları indir (Excel)
            </a>
          </>
        )
      }
    >
      <section className="sg-kpis" aria-label="Özet">
        {CONF.map((c) => (
          <div key={c.id} className="sg-kpi">
            <div className="sg-kpi-label">{c.label} <Explain label={`Güven: ${c.label}`}>{CONF_WHY[c.id]}</Explain></div>
            <div className="sg-kpi-value sg-mono">{fmt(count(c.id))}</div>
            <div className="sg-kpi-note">
              {fmt(count(c.id, 'bekliyor'))} bekliyor · {fmt(count(c.id, 'onaylandi'))} onaylandı
            </div>
          </div>
        ))}
      </section>

      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
        <div className="sg-filters" role="radiogroup" aria-label="Güven">
          <button className="sg-filter" role="radio" aria-checked={!confidence} aria-pressed={!confidence} onClick={() => setConfidence('')}>
            Tümü
          </button>
          {CONF.map((c) => (
            <button key={c.id} className="sg-filter" role="radio" aria-checked={confidence === c.id} aria-pressed={confidence === c.id} onClick={() => setConfidence(c.id)}>
              {c.label}
            </button>
          ))}
        </div>
        <div className="sg-filters" role="radiogroup" aria-label="Durum">
          {(['bekliyor', 'onaylandi', 'reddedildi', ''] as const).map((s) => (
            <button key={s || 'hepsi'} className="sg-filter" role="radio" aria-checked={status === s} aria-pressed={status === s} onClick={() => setStatus(s)}>
              {s ? STATUS[s] : 'Her durum'}
            </button>
          ))}
        </div>
      </div>

      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
        <label className="sg-search">
          <Search size={16} aria-hidden />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Eski ya da hedef adres ara" aria-label="Adres ara" />
        </label>
        {canApprove && (
          <>
            <button className="sg-button" disabled={bulk.isPending || !count('kesin', 'bekliyor')} onClick={() => bulk.mutate('kesin')}>
              <Check size={16} aria-hidden /> Kesin eşleşmelerin hepsini onayla ({fmt(count('kesin', 'bekliyor'))})
            </button>
            <button className="sg-button" disabled={bulk.isPending || !count('yüksek', 'bekliyor')} onClick={() => bulk.mutate('yüksek')}>
              <Check size={16} aria-hidden /> Yüksek güvenlilerin hepsini onayla ({fmt(count('yüksek', 'bekliyor'))})
            </button>
          </>
        )}
      </div>
      {bulk.error && <Failed error={bulk.error} />}
      {!canApprove && me.data && <p className="sg-banner">Onay yetkiniz yok; önerileri görebilirsiniz. Yetki: Yönetim → SEO & GEO → Onay verebilenler.</p>}

      {list.isLoading && <Loading text="Yönlendirmeler getiriliyor…" />}
      {list.error && <Failed error={list.error} />}
      {list.data && !list.data.items.length && (
        <EmptyHint
          title={Object.keys(counts).length ? 'Bu süzgece uyan yönlendirme yok' : 'Henüz yönlendirme okunmadı'}
          why={Object.keys(counts).length ? 'Güven ya da durum süzgecini değiştirin; «Bekliyor» boşsa bütün yönlendirmelere karar verilmiş demektir.' : 'Anasayfaya giden yönlendirmeler T-soft’tan bir sonraki okumada (her gece) gelir.'}
        />
      )}
      <div className="sg-list">
        {list.data?.items.map((r) => (
          <Row key={r.id} r={r} canApprove={canApprove} onDone={refresh} />
        ))}
      </div>
      {total > PAGE && (
        <div className="sg-pager">
          <button className="sg-button" disabled={start === 0} onClick={() => setStart(Math.max(0, start - PAGE))} aria-label="Önceki sayfa">
            <ChevronLeft size={16} aria-hidden />
          </button>
          <span className="sg-mono">
            {fmt(start + 1)}–{fmt(Math.min(total, start + PAGE))} / {fmt(total)}
          </span>
          <button className="sg-button" disabled={start + PAGE >= total} onClick={() => setStart(start + PAGE)} aria-label="Sonraki sayfa">
            <ChevronRight size={16} aria-hidden />
          </button>
        </div>
      )}
    </SeoLayout>
  );
}

function Row({ r, canApprove, onDone }: { r: Redirect; canApprove: boolean; onDone: () => void }) {
  const [target, setTarget] = useState(r.chosen ?? r.target ?? '');
  const decide = useMutation({
    mutationFn: (action: 'approve' | 'reject') => seoApi.decideRedirect(r.id, { action, target }),
    onSuccess: onDone,
  });
  const tone = CONF.find((c) => c.id === r.confidence)?.tone ?? '';
  const site = r.url.slice(0, r.url.length - r.link.length);
  return (
    <article className="sg-card" style={{ padding: 16 }}>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between' }}>
        <a className="sg-mono" href={r.url} target="_blank" rel="noreferrer" style={{ fontSize: 12, wordBreak: 'break-all' }}>
          /{r.link} <ExternalLink size={11} aria-hidden />
        </a>
        <span style={{ display: 'inline-flex', gap: 6 }}>
          <span className={`sg-chip ${tone}`}>{CONF.find((c) => c.id === r.confidence)?.label}</span>
          <span className="sg-chip">{STATUS[r.status]}</span>
        </span>
      </div>
      <p style={{ margin: '8px 0', fontSize: 12.5, color: 'var(--sg-muted)' }}>
        Şu an gittiği yer → <span className="sg-mono">{r.current || 'anasayfa'}</span>{r.reason && <> · Neden bu öneri: {r.reason}</>}
      </p>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
        <label className="sg-search" style={{ flex: '1 1 280px' }}>
          <span className="sg-mono" style={{ fontSize: 11 }}>Yeni hedef /</span>
          <input
            className="sg-mono"
            value={target}
            onChange={(e) => setTarget(e.target.value.replace(/^\/+/, ''))}
            placeholder="hedef adres (ör. yazar-adi); öneriler için dokunun"
            aria-label="Hedef adres"
            list={`alt-${r.id}`}
            disabled={r.status !== 'bekliyor'}
          />
          <datalist id={`alt-${r.id}`}>
            {r.alternatives.map((a) => (
              <option key={a.link} value={a.link}>{`${a.type} · %${Math.round(a.score * 100)}`}</option>
            ))}
          </datalist>
        </label>
        {target && (
          <a className="sg-button" href={`${site}${target}`} target="_blank" rel="noreferrer" aria-label="Hedefi aç">
            <ExternalLink size={14} aria-hidden />
          </a>
        )}
        {r.status === 'bekliyor' && canApprove && (
          <>
            <button className="sg-button primary" disabled={!target || decide.isPending} onClick={() => decide.mutate('approve')}>
              {decide.isPending && decide.variables === 'approve' ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <Check size={16} aria-hidden />}
              Onayla
            </button>
            <button className="sg-button danger" disabled={decide.isPending} onClick={() => decide.mutate('reject')}>
              <X size={16} aria-hidden /> Reddet
            </button>
          </>
        )}
        {r.status !== 'bekliyor' && (
          <span style={{ fontSize: 12, color: 'var(--sg-muted)' }}>
            {r.decidedBy} · {r.decidedAt ? new Date(r.decidedAt).toLocaleString('tr-TR') : ''}
          </span>
        )}
      </div>
      {decide.error && <div style={{ marginTop: 8 }}><Failed error={decide.error} /></div>}
    </article>
  );
}
