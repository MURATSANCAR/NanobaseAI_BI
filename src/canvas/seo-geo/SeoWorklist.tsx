import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowRight, ChevronLeft, ChevronRight, Download, FileSpreadsheet, History, Loader2, RefreshCw, Search } from 'lucide-react';
import { ENGINE_BASE, ENGINE_ENABLED } from '../engine';
import { call, dateTime, fmt, qs } from './api';
import SeoLayout, { Failed, Loading, SeoInfo } from './SeoLayout';
import { useCan } from '../useAdmin';
import { xlsxUrl } from '../components/excel';
import { EmptyHint, Explain } from '../components/Explain';

const PAGE = 40;
type Owner = 'tsoft' | 'telif' | 'icerik' | 'bt' | 'yayin' | 'seo';
type Status = 'yeni' | 'yapiliyor' | 'bitti' | 'yoksay';
type View = 'gruplu' | 'tek';
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
  status: Status | 'karisik';
  statusLabel: string;
  /** Gruplu görünüm: ürün/kişi başına çoğalan işler tek satırda (ör. «Hak eksik — Timaş Çocuk»). */
  isGroup?: boolean;
  statusCounts?: Partial<Record<Status, number>>;
  assignee: string | null;
  note: string | null;
  updatedBy: string | null;
  updatedAt: string | null;
  firstSeen: string | null;
};
type Resp = {
  total: number;
  itemTotal: number;
  view: View;
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
const STATUS_TONE: Record<Status | 'karisik', string> = { yeni: 'violet', yapiliyor: 'mid', bitti: 'good', yoksay: '', karisik: '' };
const impactText = (n: number) => fmt(n, 1);

/** Tek iş listesi: bütün SEO & GEO ekranlarının ürettiği işler, sorumluya göre ve etkiye göre sıralı. Kaynak bir işi artık
 *  üretmiyorsa iş kendiliğinden kapanır. Hiçbir şey siteye/CRM'e gönderilmez; ekran kimin nerede ne yapacağını söyler. */
export default function SeoWorklist() {
  const canRun = useCan('seo.calistir');
  const canExport = useCan('veri.disa-aktar');
  const qc = useQueryClient();
  const [owner, setOwner] = useState<Owner | ''>('');
  const [status, setStatus] = useState<StatusFilter>('acik');
  const [view, setView] = useState<View>('gruplu');
  const [source, setSource] = useState('');
  const [q, setQ] = useState('');
  const [query, setQuery] = useState('');
  const [start, setStart] = useState(0);
  const [showLog, setShowLog] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setQuery(q), 300);
    return () => clearTimeout(t);
  }, [q]);
  useEffect(() => setStart(0), [owner, status, source, query, view]);

  const filters = { owner, status, source, q: query };
  const list = useQuery({
    queryKey: ['seo-worklist', owner, status, source, query, start, view],
    queryFn: () => call<Resp>(`worklist?${qs({ ...filters, view, start, limit: PAGE })}`, { timeout: 180_000 }),
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
    <SeoLayout k={list.data?.kaynaklar}
      path="/seo-geo/is-listesi"
      crumb="İş listesi"
      eyebrow="SEO & GEO · İş listesi"
      title="Tek iş listesi"
      lead="Bütün SEO ve GEO ekranlarının çıkardığı işler tek sırada: kim yapacak, ne kadar önemli, nereden geldi. Biriminizin işlerini süzün, «Ekrana git» ile ayrıntıya bakın, durumu ve atanan kişiyi yazın. Hiçbir şey siteye ya da CRM’e gönderilmez."
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
            <>
              <a className="sg-button" href={`${ENGINE_BASE}/api/v1/seo-geo/worklist/export.csv?${qs(filters)}`}>
                <Download size={16} aria-hidden /> CSV indir
              </a>
              <a className="sg-button" href={xlsxUrl(`${ENGINE_BASE}/api/v1/seo-geo/worklist/export.csv?${qs(filters)}`)}>
                <FileSpreadsheet size={16} aria-hidden /> Excel indir
              </a>
            </>
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
              <p style={{ margin: 0, fontSize: 12.5, color: 'var(--sg-muted)' }}>Kartlar her birimin açık işlerini gösterir; bir karta dokunun, liste o birime süzülsün.</p>
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
                <span style={{ display: 'inline-flex', alignItems: 'center' }}>
                  <Explain label="Durum ve görünüm" title="Durumlar ve görünüm">
                    «Açık»: yeni ve yapılıyor işler. «Yok sayıldı»: yapılmayacağına karar verilen iş. Kaynak ekran bir işi artık göstermiyorsa iş kendiliğinden kapanır. «Gruplu»: aynı türden ürün ya da kişi işleri tek satırda toplanır; «Tek tek» hepsini ayrı gösterir.
                  </Explain>
                </span>
                <div className="sg-filters" role="radiogroup" aria-label="Görünüm">
                  <button className="sg-filter" role="radio" aria-checked={view === 'gruplu'} aria-pressed={view === 'gruplu'} onClick={() => setView('gruplu')}>
                    Gruplu
                  </button>
                  <button className="sg-filter" role="radio" aria-checked={view === 'tek'} aria-pressed={view === 'tek'} onClick={() => setView('tek')}>
                    Tek tek
                  </button>
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
                Etki puanı işin önem derecesini, kitabın satışını, Google’daki gösterimini ve tahmini ek tıklamayı (gruplu işlerde kayıt sayısını da) birleştirir; büyük değerler aşırı baskın olmasın diye her biri sıkıştırılarak (logaritmik) eklenir. Büyük puanlı işi önce yapın.{' '}
                {d.builtAt ? `Liste ${dateTime(d.builtAt)} tarihinde toplandı; ${fmt(Math.round(d.cacheSeconds / 60))} dakikadan eskiyse arka planda yenilenir.` : ''}
                {d.building ? ' Yeni liste şu an toplanıyor.' : ''}
              </p>

              {!d.ready && (
                <div className="sg-empty">
                  <h2>Liste hazırlanıyor <SeoInfo k={list.data?.kaynaklar} label="Liste hazırlanıyor" /></h2>
                  <p>Bütün ekranların işleri ilk kez toplanıyor; birkaç dakika sürebilir. Bu sayfa açık kalırsa liste hazır olunca kendiliğinden gelir.</p>
                </div>
              )}
              {d.buildError && <p className="sg-banner err">Son toplama tamamlanamadı: {d.buildError}</p>}
              {d.ready && !d.items.length && (
                <EmptyHint
                  title="Bu süzgece uyan iş yok"
                  why={status === 'acik' && !owner && !source && !query ? 'Açık iş kalmadı; bütün işler bitti ya da yok sayıldı.' : 'Birim, durum, kaynak ya da arama süzgecini gevşetin.'}
                />
              )}
              {d.ready && d.items.length > 0 && (
                <p style={{ margin: '0 0 8px', fontSize: 12.5, color: 'var(--sg-muted)' }}>
                  {d.view === 'gruplu' ? `${fmt(d.total)} satır; içinde ${fmt(d.itemTotal)} iş. Aynı türden ürün ya da kişi işleri tek satırda toplandı.` : `${fmt(d.total)} iş.`}
                </p>
              )}
              <div className="sg-list">
                {d.items.map((it) => (
                  <WorkRow key={it.key} it={it} canEdit={canRun} statuses={d.statuses} onDone={refresh} statusFilter={status} />
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

function WorkRow({ it, canEdit, statuses, onDone, statusFilter = '' }: { it: Item; canEdit: boolean; statuses: Record<Status, string>; onDone: () => void; statusFilter?: StatusFilter }) {
  const [open, setOpen] = useState(false);
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
            {it.isGroup &&
              Object.entries(it.statusCounts ?? {}).map(([k, n]) => (
                <span key={k} className="sg-chip">
                  {statuses[k as Status] ?? k} {fmt(n ?? 0)}
                </span>
              ))}
          </div>
        </div>
        <div style={{ textAlign: 'right' }} title={it.impactBasis}>
          <div className="sg-kpi-label">Etki</div>
          <div className="sg-mono" style={{ fontSize: 22, fontWeight: 700 }}>{impactText(it.impact)}</div>
        </div>
      </div>
      <p style={{ margin: '8px 0 4px', fontSize: 13, overflowWrap: 'anywhere' }}>{it.detail}</p>
      <p className="sg-mono" style={{ margin: '0 0 10px', fontSize: 11.5, color: 'var(--sg-muted)', overflowWrap: 'anywhere' }}>
        Etki hesabı: {it.impactBasis}
      </p>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
        <Link className="sg-button" to={it.link}>
          Ekrana git <ArrowRight size={14} aria-hidden />
        </Link>
        {it.isGroup && (
          <button className="sg-button" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
            {open ? 'İşleri gizle' : `İşleri göster (${fmt(it.count ?? 0)})`}
          </button>
        )}
        {canEdit ? (
          <>
            <select
              className="sg-search"
              value={it.status}
              onChange={(e) => {
                const next = e.target.value as Status;
                if (it.isGroup && !window.confirm(`Bu durum gruptaki ${fmt(it.count ?? 0)} işin hepsine yazılacak. Devam edilsin mi?`)) return;
                save.mutate(next);
              }}
              disabled={save.isPending}
              aria-label="Durum"
              style={{ flex: '0 1 160px', fontSize: 13, color: 'var(--sg-ink)' }}
            >
              {it.status === 'karisik' && (
                <option value="karisik" disabled>
                  Karışık
                </option>
              )}
              {(Object.keys(statuses) as Status[]).map((s) => (
                <option key={s} value={s}>
                  {statuses[s]}
                </option>
              ))}
            </select>
            <label className="sg-search" style={{ flex: '1 1 160px' }}>
              <input value={assignee} onChange={(e) => setAssignee(e.target.value)} placeholder="Atanan kişi (kullanıcı adı)" aria-label="Atanan kişi" maxLength={120} />
            </label>
            <label className="sg-search" style={{ flex: '2 1 220px' }}>
              <input
                value={note}
                onChange={(e) => setNote(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && dirty && it.status !== 'karisik' && save.mutate(it.status)}
                placeholder="Not, ör. site yöneticisine iletildi"
                aria-label="Not"
                maxLength={1000}
              />
            </label>
            {dirty && (
              <button className="sg-button primary" onClick={() => it.status !== 'karisik' && save.mutate(it.status)} disabled={save.isPending || it.status === 'karisik'}>
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
      {it.isGroup && open && <GroupItems gkey={it.key} canEdit={canEdit} statuses={statuses} onDone={onDone} statusFilter={statusFilter} />}
    </article>
  );
}

/** Grubun içindeki işler: süzgeçteki duruma göre, etkiye göre sıralı, sayfalı. */
function GroupItems({ gkey, canEdit, statuses, onDone, statusFilter }: { gkey: string; canEdit: boolean; statuses: Record<Status, string>; onDone: () => void; statusFilter: StatusFilter }) {
  const [start, setStart] = useState(0);
  const qc = useQueryClient();
  const g = useQuery({
    queryKey: ['seo-worklist-group', gkey, statusFilter, start],
    queryFn: () => call<{ total: number; start: number; items: Item[] }>(`worklist/group/${encodeURIComponent(gkey)}?${qs({ status: statusFilter, start, limit: 20 })}`),
    enabled: ENGINE_ENABLED,
    retry: false,
    placeholderData: (p) => p,
  });
  const done = () => {
    qc.invalidateQueries({ queryKey: ['seo-worklist-group', gkey] });
    onDone();
  };
  if (g.isLoading) return <Loading text="İşler getiriliyor…" />;
  if (g.error) return <Failed error={g.error} />;
  const d = g.data;
  if (!d) return null;
  return (
    <div style={{ display: 'grid', gap: 10, marginTop: 12 }}>
      {d.items.map((c) => (
        <WorkRow key={c.key} it={c} canEdit={canEdit} statuses={statuses} onDone={done} />
      ))}
      {d.total > 20 && (
        <div className="sg-pager">
          <button className="sg-button" disabled={start === 0} onClick={() => setStart(Math.max(0, start - 20))} aria-label="Önceki sayfa">
            <ChevronLeft size={16} aria-hidden />
          </button>
          <span className="sg-mono">
            {fmt(start + 1)}–{fmt(Math.min(d.total, start + 20))} / {fmt(d.total)}
          </span>
          <button className="sg-button" disabled={start + 20 >= d.total} onClick={() => setStart(start + 20)} aria-label="Sonraki sayfa">
            <ChevronRight size={16} aria-hidden />
          </button>
        </div>
      )}
    </div>
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
          <h2>Geçmiş boş <SeoInfo k={log.data?.kaynaklar} label="Geçmiş boş" /></h2>
          <p>Henüz kapanan ya da durumu değişen iş yok. Bir işin durumunu değiştirdiğinizde burada kaydı görünür.</p>
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
