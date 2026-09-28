import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowRight, ChevronLeft, ChevronRight, Download, History, Loader2, RefreshCw, Search } from 'lucide-react';
import { ENGINE_BASE, ENGINE_ENABLED } from '../engine';
import { call, dateTime, fmt, qs } from './api';
import SeoLayout, { Failed, Loading } from './SeoLayout';
import { useCan } from '../useAdmin';

const PAGE = 40;
type Owner = 'tsoft' | 'telif' | 'icerik' | 'bt' | 'yayin' | 'seo';
type Status = 'yeni' | 'yapiliyor' | 'bitti' | 'yoksay';
type StatusFilter = Status | 'acik' | '';
type Item = {
  key: string;
  ref: string;
  source: string;
  sourceLabel: string;
  owner: Owner;
  ownerLabel: string;
  title: string;
  detail: string;
  severity: 'kritik' | 'yüksek' | 'orta' | 'düşük';
  impact: number;
  impactBasis: string;
  link: string;
  productId: string | null;
  count: number | null;
  status: Status;
  statusLabel: string;
  assignee: string | null;
  note: string | null;
  updatedBy: string | null;
  updatedAt: string | null;
  firstSeen: string | null;
};
type Resp = {
  total: number;
  start: number;
  items: Item[];
  counts: { owner: Partial<Record<Owner, number>>; status: Partial<Record<Status, number>>; source: Record<string, number> };
  summary: Record<Owner, { open: number; doing: number; done: number; impact: number }>;
  owners: Record<Owner, string>;
  statuses: Record<Status, string>;
  sources: Record<string, string>;
  errors: Record<string, string>;
  errorLabels: Record<string, string>;
  builtAt: string | null;
  cacheSeconds: number;
  ready: boolean;
  building: boolean;
  buildError: string | null;
};
type LogResp = {
  total: number;
  start: number;
  items: Array<{ key: string; sourceLabel: string; ownerLabel: string; title: string; event: string; eventLabel: string; statusLabel: string | null; assignee: string | null; note: string | null; by: string | null; at: string; closedAt: string | null }>;
};

const OWNERS: Owner[] = ['tsoft', 'telif', 'icerik', 'bt', 'yayin', 'seo'];
const SHORT: Record<Owner, string> = { tsoft: 'T-soft', telif: 'Telif', icerik: 'İçerik', bt: 'BT', yayin: 'Yayın', seo: 'SEO' };
const STATUS_FILTERS: Array<{ id: StatusFilter; label: string }> = [
  { id: 'acik', label: 'Açık' },
  { id: 'yeni', label: 'Yeni' },
  { id: 'yapiliyor', label: 'Yapılıyor' },
  { id: 'bitti', label: 'Bitti' },
  { id: 'yoksay', label: 'Yok sayıldı' },
  { id: '', label: 'Hepsi' },
];
const SEV_TONE: Record<Item['severity'], string> = { kritik: 'bad', yüksek: 'mid', orta: '', düşük: 'good' };
const STATUS_TONE: Record<Status, string> = { yeni: 'violet', yapiliyor: 'mid', bitti: 'good', yoksay: '' };
const impactText = (n: number) => fmt(n, 1);

/** Tek iş listesi: bütün SEO & GEO ekranlarının ürettiği işler, sorumluya göre ve etkiye göre sıralı. Kaynak bir işi artık
 *  üretmiyorsa iş kendiliğinden kapanır. Hiçbir şey siteye/CRM'e gönderilmez; ekran kimin nerede ne yapacağını söyler. */
export default function SeoWorklist() {
  const canRun = useCan('seo.calistir');
  const canExport = useCan('veri.disa-aktar');
  const qc = useQueryClient();
  const [owner, setOwner] = useState<Owner | ''>('');
  const [status, setStatus] = useState<StatusFilter>('acik');
  const [source, setSource] = useState('');
  const [q, setQ] = useState('');
  const [query, setQuery] = useState('');
  const [start, setStart] = useState(0);
  const [showLog, setShowLog] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setQuery(q), 300);
    return () => clearTimeout(t);
  }, [q]);
  useEffect(() => setStart(0), [owner, status, source, query]);

  const filters = { owner, status, source, q: query };
  const list = useQuery({
    queryKey: ['seo-worklist', owner, status, source, query, start],
    queryFn: () => call<Resp>(`worklist?${qs({ ...filters, start, limit: PAGE })}`, { timeout: 180_000 }),
    enabled: ENGINE_ENABLED,
    retry: false,
    placeholderData: (p) => p,
    // Liste arka planda toplanırken ekran bekletilmez; bitince kendiliğinden gelir.
    refetchInterval: (s) => (s.state.data && (s.state.data.building || !s.state.data.ready) ? 10_000 : false),
  });
  const refresh = () => qc.invalidateQueries({ queryKey: ['seo-worklist'] });
  const rebuild = useMutation({
    mutationFn: () => call<Resp>(`worklist?${qs({ ...filters, start: 0, limit: PAGE, refresh: 1 })}`),
    onSuccess: refresh,
  });
  const d = list.data;
  const total = d?.total ?? 0;

  return (
    <SeoLayout
      path="/seo-geo/is-listesi"
      crumb="İş listesi"
      eyebrow="SEO & GEO · İş listesi"
      title="Tek iş listesi"
      lead="Bütün SEO & GEO ekranlarının çıkardığı işler tek listede: kim yapacak, ne kadar önemli, nerede. Sıra satış ve Google verisiyle hesaplanan etkiye göre; her işin yanında hesabı yazılı. Kaynak ekran bir işi artık göstermiyorsa iş kendiliğinden kapanır. Hiçbir şey siteye ya da CRM'e gönderilmez."
      actions={
        <>
          <button className="sg-button" onClick={() => setShowLog((v) => !v)} aria-pressed={showLog}>
            <History size={16} aria-hidden /> {showLog ? 'Listeye dön' : 'Geçmiş'}
          </button>
          {canRun && (
            <button className="sg-button" onClick={() => rebuild.mutate()} disabled={rebuild.isPending}>
              {rebuild.isPending ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <RefreshCw size={16} aria-hidden />} Yeniden topla
            </button>
          )}
          {canExport && (
            <a className="sg-button" href={`${ENGINE_BASE}/api/v1/seo-geo/worklist/export.csv?${qs(filters)}`}>
              <Download size={16} aria-hidden /> CSV indir
            </a>
          )}
        </>
      }
    >
      {rebuild.error && <Failed error={rebuild.error} />}
      {showLog ? (
        <WorklistLog />
      ) : (
        <>
          {list.isLoading && <Loading text="İşler bütün ekranlardan toplanıyor…" />}
          {list.error && <Failed error={list.error} />}
          {d && (
            <>
              <section className="sg-kpis" aria-label="Sorumlu başına açık işler">
                {OWNERS.map((o) => {
                  const s = d.summary[o];
                  const on = owner === o;
                  return (
                    <button
                      key={o}
                      className="sg-kpi"
                      onClick={() => setOwner(on ? '' : o)}
                      aria-pressed={on}
                      style={{ textAlign: 'left', font: 'inherit', cursor: 'pointer', border: `2px solid ${on ? '#5b3fd6' : 'transparent'}` }}
                    >
                      <div className="sg-kpi-label">{d.owners[o]}</div>
                      <div className="sg-kpi-value sg-mono">{fmt(s?.open ?? 0)}</div>
                      <div className="sg-kpi-note">
                        açık · {fmt(s?.doing ?? 0)} yapılıyor · {fmt(s?.done ?? 0)} bitti
                      </div>
                    </button>
                  );
                })}
              </section>

              {Object.keys(d.errors).length > 0 && (
                <p className="sg-banner err">
                  Şu kaynaklar okunamadı; işleri bu turda listede yok ama kapatılmadı:{' '}
                  {Object.entries(d.errors)
                    .map(([k, m]) => `${d.errorLabels[k] ?? k} (${m})`)
                    .join(' · ')}
                </p>
              )}

              <div className="sg-filters" role="radiogroup" aria-label="Sorumlu">
                <button className="sg-filter" role="radio" aria-checked={!owner} aria-pressed={!owner} onClick={() => setOwner('')}>
                  Hepsi <span className="sg-mono">{fmt(Object.values(d.counts.owner).reduce((a, b) => a + (b ?? 0), 0))}</span>
                </button>
                {OWNERS.map((o) => (
                  <button key={o} className="sg-filter" role="radio" aria-checked={owner === o} aria-pressed={owner === o} onClick={() => setOwner(o)}>
                    {SHORT[o]} <span className="sg-mono">{fmt(d.counts.owner[o] ?? 0)}</span>
                  </button>
                ))}
              </div>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                <div className="sg-filters" role="radiogroup" aria-label="Durum">
                  {STATUS_FILTERS.map((s) => (
                    <button key={s.id || 'hepsi'} className="sg-filter" role="radio" aria-checked={status === s.id} aria-pressed={status === s.id} onClick={() => setStatus(s.id)}>
                      {s.label}
                      {s.id && s.id !== 'acik' && <span className="sg-mono"> {fmt(d.counts.status[s.id] ?? 0)}</span>}
                    </button>
                  ))}
                </div>
                <select className="sg-search" value={source} onChange={(e) => setSource(e.target.value)} aria-label="Kaynak ekran" style={{ flex: '0 1 280px', fontSize: 13, color: 'var(--sg-ink)' }}>
                  <option value="">Bütün kaynaklar</option>
                  {Object.entries(d.sources).map(([k, label]) => (
                    <option key={k} value={k}>
                      {label} ({fmt(d.counts.source[k] ?? 0)})
                    </option>
                  ))}
                </select>
              </div>
              <label className="sg-search">
                <Search size={16} aria-hidden />
                <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="İş, kitap ya da kişi ara" aria-label="Ara" />
              </label>
              <p className="sg-banner">
                Etki puanı = önem derecesi + satış adedi + Google gösterimi + tahmini ek tıklama (+ gruplu işlerde kayıt sayısı), her biri logaritmik.{' '}
                {d.builtAt ? `Liste ${dateTime(d.builtAt)} tarihinde toplandı; ${fmt(Math.round(d.cacheSeconds / 60))} dakikadan eskiyse arka planda yenilenir.` : ''}
                {d.building ? ' Yeni liste şu an toplanıyor.' : ''}
              </p>

              {!d.ready && (
                <div className="sg-empty">
                  <h2>Liste hazırlanıyor</h2>
                  <p>Bütün ekranların işleri ilk kez toplanıyor; birkaç dakika sürebilir. Bu sayfa açık kalırsa liste hazır olunca kendiliğinden gelir.</p>
                </div>
              )}
              {d.buildError && <p className="sg-banner err">Son toplama tamamlanamadı: {d.buildError}</p>}
              {d.ready && !d.items.length && (
                <div className="sg-empty">
                  <h2>İş yok</h2>
                  <p>Bu süzgece uyan açık iş kalmadı.</p>
                </div>
              )}
              <div className="sg-list">
                {d.items.map((it) => (
                  <WorkRow key={it.key} it={it} canEdit={canRun} statuses={d.statuses} onDone={refresh} />
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
        </>
      )}
    </SeoLayout>
  );
}

function WorkRow({ it, canEdit, statuses, onDone }: { it: Item; canEdit: boolean; statuses: Record<Status, string>; onDone: () => void }) {
  const [assignee, setAssignee] = useState(it.assignee ?? '');
  const [note, setNote] = useState(it.note ?? '');
  useEffect(() => {
    setAssignee(it.assignee ?? '');
    setNote(it.note ?? '');
  }, [it.assignee, it.note]);
  const save = useMutation({
    mutationFn: (status: Status) =>
      call<{ status: Status }>(`worklist/${encodeURIComponent(it.key)}/status`, { method: 'POST', body: { status, assignee, note } }),
    onSuccess: onDone,
  });
  const dirty = assignee !== (it.assignee ?? '') || note !== (it.note ?? '');
  return (
    <article className="sg-card" style={{ padding: 16 }}>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'flex-start', justifyContent: 'space-between' }}>
        <div style={{ minWidth: 0, flex: '1 1 320px' }}>
          <div className="sg-item-name" style={{ overflowWrap: 'anywhere' }}>{it.title}</div>
          <div style={{ display: 'inline-flex', gap: 6, flexWrap: 'wrap', marginTop: 6 }}>
            <span className="sg-chip violet">{it.ownerLabel}</span>
            <span className="sg-chip">{it.sourceLabel}</span>
            <span className={`sg-chip ${SEV_TONE[it.severity]}`}>{it.severity}</span>
            <span className={`sg-chip ${STATUS_TONE[it.status]}`}>{it.statusLabel}</span>
          </div>
        </div>
        <div style={{ textAlign: 'right' }} title={it.impactBasis}>
          <div className="sg-kpi-label">Etki</div>
          <div className="sg-mono" style={{ fontSize: 22, fontWeight: 700 }}>{impactText(it.impact)}</div>
        </div>
      </div>
      <p style={{ margin: '8px 0 4px', fontSize: 13, overflowWrap: 'anywhere' }}>{it.detail}</p>
      <p className="sg-mono" style={{ margin: '0 0 10px', fontSize: 11.5, color: 'var(--sg-muted)', overflowWrap: 'anywhere' }}>
        Puan: {it.impactBasis}
      </p>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
        <Link className="sg-button" to={it.link}>
          Ekrana git <ArrowRight size={14} aria-hidden />
        </Link>
        {canEdit ? (
          <>
            <select
              className="sg-search"
              value={it.status}
              onChange={(e) => save.mutate(e.target.value as Status)}
              disabled={save.isPending}
              aria-label="Durum"
              style={{ flex: '0 1 160px', fontSize: 13, color: 'var(--sg-ink)' }}
            >
              {(Object.keys(statuses) as Status[]).map((s) => (
                <option key={s} value={s}>
                  {statuses[s]}
                </option>
              ))}
            </select>
            <label className="sg-search" style={{ flex: '1 1 160px' }}>
              <input value={assignee} onChange={(e) => setAssignee(e.target.value)} placeholder="Atanan kişi (AD adı)" aria-label="Atanan kişi" maxLength={120} />
            </label>
            <label className="sg-search" style={{ flex: '2 1 220px' }}>
              <input
                value={note}
                onChange={(e) => setNote(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && dirty && save.mutate(it.status)}
                placeholder="Not"
                aria-label="Not"
                maxLength={1000}
              />
            </label>
            {dirty && (
              <button className="sg-button primary" onClick={() => save.mutate(it.status)} disabled={save.isPending}>
                {save.isPending ? <Loader2 size={16} className="animate-spin" aria-hidden /> : null} Kaydet
              </button>
            )}
          </>
        ) : (
          (it.assignee || it.note) && (
            <span style={{ fontSize: 12.5, color: 'var(--sg-muted)' }}>
              {it.assignee ? `Atanan: ${it.assignee}` : ''} {it.note ? `· ${it.note}` : ''}
            </span>
          )
        )}
      </div>
      <p style={{ margin: '8px 0 0', fontSize: 11.5, color: 'var(--sg-muted)' }}>
        İlk görülme {dateTime(it.firstSeen)}
        {it.updatedBy ? ` · son değişiklik ${it.updatedBy}, ${dateTime(it.updatedAt)}` : ''}
      </p>
      {save.error && <div style={{ marginTop: 8 }}><Failed error={save.error} /></div>}
    </article>
  );
}

function WorklistLog() {
  const [start, setStart] = useState(0);
  const log = useQuery({
    queryKey: ['seo-worklist-log', start],
    queryFn: () => call<LogResp>(`worklist/log?${qs({ start, limit: PAGE })}`),
    enabled: ENGINE_ENABLED,
    retry: false,
    placeholderData: (p) => p,
  });
  const d = log.data;
  return (
    <>
      {log.isLoading && <Loading text="Geçmiş getiriliyor…" />}
      {log.error && <Failed error={log.error} />}
      {d && !d.items.length && (
        <div className="sg-empty">
          <h2>Geçmiş boş</h2>
          <p>Henüz kapanan ya da durumu değişen iş yok.</p>
        </div>
      )}
      {d && d.items.length > 0 && (
        <div className="sg-table-wrap">
          <table className="sg-table">
            <thead>
              <tr>
                <th>Tarih</th>
                <th>Olay</th>
                <th>İş</th>
                <th>Sorumlu</th>
                <th>Durum</th>
                <th>Kim</th>
              </tr>
            </thead>
            <tbody>
              {d.items.map((r, i) => (
                <tr key={`${r.key}-${r.at}-${i}`}>
                  <td className="sg-mono">{dateTime(r.at)}</td>
                  <td>{r.eventLabel}</td>
                  <td style={{ overflowWrap: 'anywhere' }}>
                    {r.title}
                    <div style={{ fontSize: 11.5, color: 'var(--sg-muted)' }}>{r.sourceLabel}{r.note ? ` · ${r.note}` : ''}</div>
                  </td>
                  <td>{r.ownerLabel}</td>
                  <td>{r.statusLabel ?? '—'}{r.assignee ? ` · ${r.assignee}` : ''}</td>
                  <td>{r.by ?? 'Sistem'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {d && d.total > PAGE && (
        <div className="sg-pager">
          <button className="sg-button" disabled={start === 0} onClick={() => setStart(Math.max(0, start - PAGE))} aria-label="Önceki sayfa">
            <ChevronLeft size={16} aria-hidden />
          </button>
          <span className="sg-mono">
            {fmt(start + 1)}–{fmt(Math.min(d.total, start + PAGE))} / {fmt(d.total)}
          </span>
          <button className="sg-button" disabled={start + PAGE >= d.total} onClick={() => setStart(start + PAGE)} aria-label="Sonraki sayfa">
            <ChevronRight size={16} aria-hidden />
          </button>
        </div>
      )}
    </>
  );
}
