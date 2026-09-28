import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, ChevronLeft, ChevronRight, Download, ExternalLink, Loader2, RefreshCw, Search, X } from 'lucide-react';
import { ENGINE_BASE, ENGINE_ENABLED } from '../engine';
import { call, dateTime, fmt, qs, seoApi } from './api';
import SeoLayout, { Failed, Loading, SeoInfo } from './SeoLayout';
import { useCan } from '../useAdmin';

const PAGE = 40;
type Action = 'yeni_baski_301' | 'yazar_301' | 'stokta_yok' | 'gone_410' | 'arama_verisi';
type Status = 'bekliyor' | 'onaylandi' | 'reddedildi';
type Row = {
  id: string;
  productId: string;
  link: string;
  url: string;
  name: string | null;
  reason: string;
  reasonLabel: string;
  label: string | null;
  active: boolean;
  impressions: number;
  clicks: number;
  action: Action;
  actionLabel: string;
  target: string | null;
  targetUrl: string | null;
  why: string;
  status: Status;
  chosenAction: Action | null;
  chosenTarget: string | null;
  decidedBy: string | null;
  decidedAt: string | null;
  note: string | null;
};
type Resp = {
  total: number;
  start: number;
  items: Row[];
  counts: { action: Partial<Record<Action, number>>; status: Partial<Record<Status, number>>; reason: Record<string, number> };
  actions: Record<Action, string>;
  reasons: Record<string, string>;
  searchedMin: number;
  lastBuilt: string | null;
  gsc: { start: string; end: string } | null;
};
const ORDER: Action[] = ['yeni_baski_301', 'yazar_301', 'stokta_yok', 'gone_410', 'arama_verisi'];
const TONE: Record<Action, string> = { yeni_baski_301: 'good', yazar_301: 'violet', stokta_yok: 'mid', gone_410: 'bad', arama_verisi: '' };
const STATUS: Record<Status, string> = { bekliyor: 'Bekliyor', onaylandi: 'Onaylandı', reddedildi: 'Reddedildi' };
const REDIRECTS: Action[] = ['yeni_baski_301', 'yazar_301'];

/** Satıştan kalkan kitap sayfaları: CRM'de bizim olmayan / çekilen / baskısı biten kitaplar ve T-soft'ta pasif olup hâlâ
 *  aranan sayfalar için 301, stokta yok ya da 410 önerisi. Karar yalnız kaydedilir; CSV ile panelden girilir. */
export default function SeoSunset() {
  const canExport = useCan('veri.disa-aktar');
  const canRun = useCan('seo.calistir');
  const qc = useQueryClient();
  const [action, setAction] = useState<Action | ''>('');
  const [status, setStatus] = useState<Status | ''>('bekliyor');
  const [q, setQ] = useState('');
  const [query, setQuery] = useState('');
  const [start, setStart] = useState(0);
  useEffect(() => {
    const t = setTimeout(() => setQuery(q), 300);
    return () => clearTimeout(t);
  }, [q]);
  useEffect(() => setStart(0), [action, status, query]);

  const me = useQuery({ queryKey: ['seo-me'], queryFn: seoApi.me, enabled: ENGINE_ENABLED, retry: false, staleTime: 300_000 });
  const list = useQuery({
    queryKey: ['seo-sunset', action, status, query, start],
    queryFn: () => call<Resp>(`sunset?${qs({ action, status, q: query, start, limit: PAGE })}`),
    enabled: ENGINE_ENABLED,
    retry: false,
    placeholderData: (p) => p,
  });
  const refresh = () => qc.invalidateQueries({ queryKey: ['seo-sunset'] });
  const rebuild = useMutation({ mutationFn: () => call<{ count: number }>('sunset/refresh', { method: 'POST' }), onSuccess: refresh });
  const d = list.data;
  const total = d?.total ?? 0;
  const canApprove = !!me.data?.canApprove;

  return (
    <SeoLayout k={list.data?.kaynaklar}
      path="/seo-geo/satistan-kalkan"
      crumb="Satıştan kalkan kitaplar"
      eyebrow="SEO & GEO · Satıştan kalkan kitaplar"
      title="Satıştan kalkan kitaplar"
      lead="Hakkı artık bizde olmayan, satıştan çekilen ya da baskısı biten kitapların sayfaları ve sitede kapalı olup hâlâ aranan sayfalar. Her biri için açık kurallarla öneri: yeni baskıya ya da yazar sayfasına yönlendirme, stokta yok olarak bırakma veya kalıcı kaldırma. Karar yalnız kaydedilir; siteye gönderilmez — CSV ile panelden girilir."
      actions={
        <>
          {canRun && (
            <button className="sg-button" onClick={() => rebuild.mutate()} disabled={rebuild.isPending}>
              {rebuild.isPending ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <RefreshCw size={16} aria-hidden />} Yeniden hesapla
            </button>
          )}
          {canExport && (
            <a className="sg-button" href={`${ENGINE_BASE}/api/v1/seo-geo/sunset/export.csv`}>
              <Download size={16} aria-hidden /> CSV indir
            </a>
          )}
        </>
      }
    >
      {list.isLoading && <Loading text="Sayfalar getiriliyor…" />}
      {list.error && <Failed error={list.error} />}
      {rebuild.error && <Failed error={rebuild.error} />}

      {d && (
        <>
          <section className="sg-kpis" aria-label="Özet">
            {ORDER.map((a) => (
              <div key={a} className="sg-kpi">
                <div className="sg-kpi-label">{d.actions[a]}</div>
                <div className="sg-kpi-value sg-mono">{fmt(d.counts.action[a] ?? 0)}</div>
                <div className="sg-kpi-note">{NOTE[a]}</div>
              </div>
            ))}
          </section>
          <p className="sg-banner">
            “Aranıyor”: son 28 günde en az {fmt(d.searchedMin)} Google gösterimi
            {d.gsc ? ` (${d.gsc.start} – ${d.gsc.end})` : ' — Search Console verisi yok, bütün sayfalar aranmıyor sayıldı'}. Son hesap {dateTime(d.lastBuilt)}.
            {' '}Nedenler: {Object.entries(d.counts.reason).map(([k, n]) => `${d.reasons[k] ?? k} ${fmt(n)}`).join(' · ') || '—'}
          <SeoInfo k={list.data?.kaynaklar} label="Neden sayıları" className="ml-1" />
          </p>

          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
            <div className="sg-filters" role="radiogroup" aria-label="Öneri">
              <button className="sg-filter" role="radio" aria-checked={!action} aria-pressed={!action} onClick={() => setAction('')}>
                Her öneri
              </button>
              {ORDER.map((a) => (
                <button key={a} className="sg-filter" role="radio" aria-checked={action === a} aria-pressed={action === a} onClick={() => setAction(a)}>
                  {d.actions[a]}
                </button>
              ))}
            </div>
            <div className="sg-filters" role="radiogroup" aria-label="Durum">
              {(['bekliyor', 'onaylandi', 'reddedildi', ''] as const).map((s) => (
                <button key={s || 'hepsi'} className="sg-filter" role="radio" aria-checked={status === s} aria-pressed={status === s} onClick={() => setStatus(s)}>
                  {s ? STATUS[s] : 'Her durum'} {s && <span className="sg-mono">{fmt(d.counts.status[s] ?? 0)}</span>}
                </button>
              ))}
            </div>
          </div>
          <label className="sg-search">
            <Search size={16} aria-hidden />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Kitap adı ya da adres" aria-label="Ara" />
          </label>
          {!canApprove && me.data && <p className="sg-banner">Onay yetkiniz yok; önerileri görebilirsiniz.</p>}

          {!d.items.length && (
            <div className="sg-empty">
              <h2>Kayıt yok</h2>
              <p>Bu süzgece uyan sayfa yok.</p>
            </div>
          )}
          <div className="sg-list">
            {d.items.map((r) => (
              <SunsetRow key={r.id} r={r} actions={d.actions} canApprove={canApprove} onDone={refresh} />
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
        </>
      )}
    </SeoLayout>
  );
}

const NOTE: Record<Action, string> = {
  yeni_baski_301: 'Aynı kitabın yaşayan başka ürünü var',
  yazar_301: 'Trafik yazar sayfasına taşınır',
  stokta_yok: 'Sayfa aranıyor ya da hedef yok; kalsın',
  gone_410: 'Hak bizde değil ve aranmıyor',
  arama_verisi: 'Aranıp aranmadığı bilinmiyor; karar veriye kalır',
};

function SunsetRow({ r, actions, canApprove, onDone }: { r: Row; actions: Record<Action, string>; canApprove: boolean; onDone: () => void }) {
  const [choice, setChoice] = useState<Action>(r.chosenAction ?? r.action);
  const [target, setTarget] = useState(r.chosenTarget ?? r.target ?? '');
  const decide = useMutation({
    mutationFn: (a: 'approve' | 'reject') =>
      call<Row>(`sunset/${encodeURIComponent(r.id)}/decide`, { method: 'POST', body: { action: a, choice, target: REDIRECTS.includes(choice) ? target : '' } }),
    onSuccess: onDone,
  });
  const pending = r.status === 'bekliyor';
  const site = r.url.slice(0, r.url.length - r.link.length);
  const needsTarget = REDIRECTS.includes(choice);
  return (
    <article className="sg-card" style={{ padding: 16 }}>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ minWidth: 0 }}>
          <div className="sg-item-name">{r.name || r.link}</div>
          <a className="sg-mono" href={r.url} target="_blank" rel="noreferrer" style={{ fontSize: 12, wordBreak: 'break-all' }}>
            /{r.link} <ExternalLink size={11} aria-hidden />
          </a>
        </div>
        <span style={{ display: 'inline-flex', gap: 6, flexWrap: 'wrap' }}>
          <span className="sg-chip">{r.reasonLabel}</span>
          {r.active && <span className="sg-chip bad">Sitede satışta</span>}
          <span className={`sg-chip ${TONE[r.action]}`}>{r.actionLabel}</span>
          <span className="sg-chip">{STATUS[r.status]}</span>
        </span>
      </div>
      <p style={{ margin: '8px 0', fontSize: 12.5, color: 'var(--sg-muted)' }}>
        <span className="sg-mono">{fmt(r.impressions)} gösterim · {fmt(r.clicks)} tıklama</span> · {r.why}
      </p>
      {pending && canApprove ? (
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          <select className="sg-search" value={choice} onChange={(e) => setChoice(e.target.value as Action)} aria-label="Eylem" style={{ flex: '0 1 240px', fontSize: 13, color: 'var(--sg-ink)' }}>
            {ORDER.map((a) => (
              <option key={a} value={a}>
                {actions[a]}
              </option>
            ))}
          </select>
          {needsTarget && (
            <label className="sg-search" style={{ flex: '1 1 240px' }}>
              <span className="sg-mono" style={{ fontSize: 11 }}>Hedef /</span>
              <input className="sg-mono" value={target} onChange={(e) => setTarget(e.target.value.replace(/^\/+/, ''))} placeholder="hedef adres" aria-label="Hedef adres" />
            </label>
          )}
          {needsTarget && target && (
            <a className="sg-button" href={`${site}${target}`} target="_blank" rel="noreferrer" aria-label="Hedefi aç">
              <ExternalLink size={14} aria-hidden />
            </a>
          )}
          <button className="sg-button primary" disabled={(needsTarget && !target) || decide.isPending} onClick={() => decide.mutate('approve')}>
            {decide.isPending && decide.variables === 'approve' ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <Check size={16} aria-hidden />} Onayla
          </button>
          <button className="sg-button danger" disabled={decide.isPending} onClick={() => decide.mutate('reject')}>
            <X size={16} aria-hidden /> Reddet
          </button>
        </div>
      ) : (
        <p style={{ margin: 0, fontSize: 12, color: 'var(--sg-muted)' }}>
          {r.status === 'onaylandi' && (
            <>
              Onaylanan: <b>{r.chosenAction ? actions[r.chosenAction] : '—'}</b>
              {r.chosenTarget ? ` → /${r.chosenTarget}` : ''} ·{' '}
            </>
          )}
          {r.target && pending ? `Önerilen hedef /${r.target} · ` : ''}
          {r.decidedBy ? `${r.decidedBy} · ${dateTime(r.decidedAt)}` : ''}
        </p>
      )}
      {decide.error && <div style={{ marginTop: 8 }}><Failed error={decide.error} /></div>}
    </article>
  );
}
