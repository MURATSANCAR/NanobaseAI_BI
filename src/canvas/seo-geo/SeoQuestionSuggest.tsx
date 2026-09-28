import type { ReactNode } from 'react';
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, ChevronLeft, ChevronRight, Loader2, Plus, RefreshCw, X } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { call, dateTime, fmt, qs } from './api';
import SeoLayout, { Failed, Loading, SeoInfo } from './SeoLayout';
import { useCan } from '../useAdmin';

const PAGE = 40;
type Source = 'arama' | 'tema' | 'sezon';
type Status = 'öneri' | 'eklendi' | 'reddedildi';
type Basis = {
  query?: string;
  impressions?: number;
  clicks?: number;
  position?: number;
  books?: number | null;
  theme?: string;
  age?: string;
  genre?: string;
  audience?: string;
  day?: string;
  date?: string | null;
  daysUntil?: number | null;
};
type Item = {
  id: string;
  text: string;
  source: Source;
  sourceLabel: string;
  basis: Basis;
  score: number;
  impressions: number | null;
  books: number | null;
  status: Status;
  questionId: string | null;
  decidedBy: string | null;
  decidedAt: string | null;
};
type RunState = { running: boolean; startedAt: string | null; finishedAt: string | null; error: string | null; crmError: string | null };
type Resp = {
  total: number;
  start: number;
  items: Item[];
  counts: Record<Source, Record<Status, number>>;
  sources: Record<Source, string>;
  minBooks: number;
  lastRefresh: string | null;
  state: RunState;
  gsc: boolean;
  crm: boolean;
};

const SOURCES: Array<[Source, string]> = [
  ['arama', 'Aramalar'],
  ['tema', 'Tema/yaş'],
  ['sezon', 'Sezon'],
];
const STATUSES: Array<[Status, string]> = [
  ['öneri', 'Bekleyen'],
  ['eklendi', 'Eklenen'],
  ['reddedildi', 'Reddedilen'],
];

/** İzlenen soru önerileri: yapay zekâ görünürlüğü ölçümüne eklenecek okur soruları. Search Console aramalarından,
 *  CRM tema/yaş bilgisinden ve özel günlerden kodla üretilir; eklenen soru her hafta yapay zekâ motorlarına sorulur. */
export default function SeoQuestionSuggest() {
  const canRun = useCan('seo.calistir');
  const qc = useQueryClient();
  const [source, setSource] = useState<Source>('arama');
  const [status, setStatus] = useState<Status>('öneri');
  const [start, setStart] = useState(0);
  useEffect(() => setStart(0), [source, status]);

  const list = useQuery({
    queryKey: ['seo-qsuggest', source, status, start],
    queryFn: () => call<Resp>(`qsuggest?${qs({ source, status, start, limit: PAGE })}`),
    enabled: ENGINE_ENABLED,
    retry: false,
    placeholderData: (p) => p,
    refetchInterval: (s) => (s.state.data?.state.running ? 5000 : false),
  });
  const done = () => qc.invalidateQueries({ queryKey: ['seo-qsuggest'] });
  const refresh = useMutation({ mutationFn: () => call('qsuggest/refresh', { method: 'POST' }), onSuccess: done });
  const decide = useMutation({
    mutationFn: ({ id, action }: { id: string; action: 'accept' | 'reject' }) => call(`qsuggest/${id}/${action}`, { method: 'POST' }),
    onSuccess: () => {
      done();
      qc.invalidateQueries({ queryKey: ['seo-questions'] });
    },
  });

  const d = list.data;
  const running = !!d?.state.running;
  const total = d?.total ?? 0;
  const pending = d ? SOURCES.reduce((a, [s]) => a + (d.counts[s]?.['öneri'] ?? 0), 0) : 0;

  return (
    <SeoLayout k={list.data?.kaynaklar}
      path="/seo-geo/soru-onerileri"
      crumb="Soru önerileri"
      eyebrow="SEO & GEO · Yapay zekâ görünürlüğü"
      title="Soru önerileri"
      lead="Yapay zekâ görünürlüğünü ölçmek için izlenecek okur soruları. Öneriler Google aramalarındaki soru biçimli sorgulardan, CRM’deki tema ve yaş bilgisinden ve özel günlerden kodla üretilir; yalnız satıştaki kitaplarımızın cevap olabileceği sorular önerilir. Eklenen soru, izlenen sorulara yazılır ve düzenli olarak ölçülür."
      actions={
        <>
          <Link className="sg-button" to="/seo-geo/ai-gorunurluk">
            İzlenen sorular
          </Link>
          {canRun && (
            <button className="sg-button primary" onClick={() => refresh.mutate()} disabled={refresh.isPending || running}>
              {running ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <RefreshCw size={16} aria-hidden />}
              {running ? 'Öneriler hazırlanıyor' : 'Önerileri yenile'}
            </button>
          )}
        </>
      }
    >
      {list.isLoading && <Loading text="Öneriler getiriliyor…" />}
      {list.error && <Failed error={list.error} />}
      {refresh.error && <Failed error={refresh.error} />}
      {decide.error && <Failed error={decide.error} />}
      {d?.state.error && <p className="sg-banner err">Son yenileme başarısız: {d.state.error}</p>}
      {d?.state.crmError && <p className="sg-banner">CRM tema/yaş bilgisi okunamadı; önceki okuma kullanıldı. ({d.state.crmError})</p>}

      {d && (
        <>
          <section className="sg-kpis" aria-label="Özet">
            <Kpi label="Bekleyen öneri" value={fmt(pending)} note={d.lastRefresh ? `Son yenileme ${dateTime(d.lastRefresh)}` : 'Henüz yenilenmedi'} info={<SeoInfo k={list.data?.kaynaklar} label="Bekleyen öneri" />} />
            {SOURCES.map(([s, label]) => (
              <Kpi key={s} label={label} value={fmt(d.counts[s]?.['öneri'] ?? 0)} note={`${fmt(d.counts[s]?.eklendi ?? 0)} eklendi · ${fmt(d.counts[s]?.reddedildi ?? 0)} reddedildi`} info={<SeoInfo k={list.data?.kaynaklar} label={label} />} />
            ))}
          </section>
          {!d.gsc && <p className="sg-banner">Search Console verisi henüz okunmadı; arama kaynaklı öneri çıkmaz.</p>}
          {!d.crm && <p className="sg-banner">CRM bağlantısı tanımlı değil; tema/yaş önerileri son okunan bilgiyle üretilir.</p>}

          <div className="sg-filters" role="tablist" aria-label="Kaynak">
            {SOURCES.map(([s, label]) => (
              <button key={s} className="sg-filter" role="tab" aria-selected={source === s} aria-pressed={source === s} onClick={() => setSource(s)}>
                {label} <span className="sg-mono">{fmt(d.counts[s]?.[status] ?? 0)}</span>
              </button>
            ))}
          </div>
          <div className="sg-filters" role="radiogroup" aria-label="Durum">
            {STATUSES.map(([s, label]) => (
              <button key={s} className="sg-filter" role="radio" aria-checked={status === s} aria-pressed={status === s} onClick={() => setStatus(s)}>
                {label} <span className="sg-mono">{fmt(d.counts[source]?.[s] ?? 0)}</span>
              </button>
            ))}
          </div>

          {source === 'tema' && (
            <p className="sg-banner ok">Tema/yaş sorusu yalnız satıştaki en az {fmt(d.minBooks)} kitabımız o birleşime uyuyorsa önerilir.</p>
          )}

          {!d.items.length && (
            <div className="sg-empty">
              <h2>Öneri yok</h2>
              <p>{status === 'öneri' ? 'Bu kaynakta bekleyen öneri kalmadı. Öneriler her gece yenilenir.' : 'Bu durumda soru yok.'}</p>
            </div>
          )}
          <div className="sg-list">
            {d.items.map((it) => (
              <article key={it.id} className="sg-card" style={{ padding: 14, display: 'flex', flexDirection: 'column', gap: 8 }}>
                <div className="sg-item-name" style={{ WebkitLineClamp: 'unset' }}>{it.text}</div>
                <BasisLine it={it} />
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
                  {it.status === 'öneri' && canRun && (
                    <>
                      <button
                        className="sg-button primary"
                        disabled={decide.isPending}
                        onClick={() => decide.mutate({ id: it.id, action: 'accept' })}
                      >
                        <Plus size={14} aria-hidden /> Ekle
                      </button>
                      <button className="sg-button" disabled={decide.isPending} onClick={() => decide.mutate({ id: it.id, action: 'reject' })}>
                        <X size={14} aria-hidden /> Reddet
                      </button>
                    </>
                  )}
                  {it.status === 'eklendi' && (
                    <span className="sg-chip good">
                      <Check size={12} aria-hidden /> İzlenen sorulara eklendi{it.decidedBy ? ` · ${it.decidedBy}` : ''}
                    </span>
                  )}
                  {it.status === 'reddedildi' && (
                    <span className="sg-chip">Reddedildi{it.decidedBy ? ` · ${it.decidedBy}` : ''}</span>
                  )}
                  {it.decidedAt && <span className="sg-item-meta">{dateTime(it.decidedAt)}</span>}
                </div>
              </article>
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

function BasisLine({ it }: { it: Item }) {
  const b = it.basis;
  const chips: string[] = [];
  if (it.source === 'arama') {
    if (b.query) chips.push(`Arama: “${b.query}”`);
    chips.push(`${fmt(b.impressions ?? 0)} gösterim (28 gün)`);
    if (b.position) chips.push(`ortalama sıra ${fmt(b.position, 1)}`);
    chips.push(b.books == null ? 'genel soru' : `${fmt(b.books)} kitabımız uyuyor`);
  } else if (it.source === 'tema') {
    if (b.age) chips.push(`Yaş: ${b.age}`);
    if (b.theme) chips.push(`Tema: ${b.theme}`);
    if (b.genre) chips.push(`Tür: ${b.genre}`);
    if (b.audience) chips.push(`Okur: ${b.audience}`);
    chips.push(`${fmt(b.books ?? 0)} satıştaki kitap`);
  } else {
    if (b.day) chips.push(b.day);
    if (b.date) chips.push(b.daysUntil != null ? `${dateOnly(b.date)} · ${fmt(b.daysUntil)} gün sonra` : dateOnly(b.date));
    else chips.push('tarih bilinmiyor');
    chips.push(`${fmt(b.books ?? 0)} bağlı kitap`);
  }
  return (
    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
      {chips.map((c) => (
        <span key={c} className="sg-chip" style={{ whiteSpace: 'normal' }}>
          {c}
        </span>
      ))}
    </div>
  );
}

function dateOnly(iso: string) {
  const [y, m, d] = iso.split('-');
  return d && m && y ? `${d}.${m}.${y}` : iso;
}

function Kpi({ label, value, note, info }: { label: string; value: string; note: string; info?: ReactNode }) {
  return (
    <div className="sg-kpi">
      <div className="sg-kpi-label">{label}{info ? <> {info}</> : null}</div>
      <div className="sg-kpi-value sg-mono">{value}</div>
      <div className="sg-kpi-note">{note}</div>
    </div>
  );
}
