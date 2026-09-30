import type { ReactNode } from 'react';
import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Loader2, RefreshCw, Search } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { FLAG_LABEL, RIGHTS_LABEL, RIGHTS_TONE, dateTime, fmt, seoApi, type CrmFilter, type CrmRights } from './api';
import CrmPanel from './CrmPanel';
import SeoLayout, { Failed, Loading, SeoInfo } from './SeoLayout';
import { useCan } from '../useAdmin';
import { EmptyHint, Explain } from '../components/Explain';
import SeoPager from './SeoPager';

const PAGE = 40;
const RIGHTS_ORDER: CrmRights[] = ['eksik', 'incele', 'yok', 'var', 'koruma_disi', 'set', 'kitap_degil'];

/** Haklar ve CRM: T-soft'ta satıştaki kitapların CRM kartı, internette gösterim hakkı ve yayın durumu.
 *  Google Kitaplar önizlemesi, tadımlık PDF ve SEO önceliği bu bilgiye bağlıdır. CRM'e yazılmaz. */
export default function SeoRights() {
  // Okuma/tarama/ölçüm başlatmak «SEO eşitleme ve ölçüm» ister; rolde yoksa düğme çıkmaz.
  const canRun = useCan('seo.calistir');
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const filter = (params.get('suzgec') ?? '') as CrmFilter | '';
  const selected = params.get('urun') ?? '';
  const [q, setQ] = useState('');
  const [query, setQuery] = useState('');
  const [start, setStart] = useState(0);

  useEffect(() => {
    const t = setTimeout(() => setQuery(q), 300);
    return () => clearTimeout(t);
  }, [q]);
  useEffect(() => setStart(0), [filter, query]);

  const list = useQuery({
    queryKey: ['seo-crm', filter, query, start],
    queryFn: () => seoApi.crm({ filter, q: query, start, limit: PAGE }),
    enabled: ENGINE_ENABLED,
    retry: false,
    placeholderData: (prev) => prev,
    refetchInterval: (s) => (s.state.data?.summary.state.running ? 10000 : false),
  });
  const read = useMutation({ mutationFn: seoApi.crmSync, onSuccess: () => qc.invalidateQueries({ queryKey: ['seo-crm'] }) });
  const detail = useQuery({
    queryKey: ['seo-product', selected],
    queryFn: () => seoApi.product(selected),
    enabled: ENGINE_ENABLED && !!selected,
    retry: false,
  });

  const set = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    if (key === 'suzgec') next.delete('urun');
    setParams(next, { replace: true });
  };

  const s = list.data?.summary;
  const items = list.data?.items ?? [];
  const total = list.data?.total ?? 0;
  const flagged = Object.values(s?.flags ?? {}).reduce((a, n) => a + (n ?? 0), 0);
  const running = !!s?.state.running;

  return (
    <SeoLayout k={detail.data?.kaynaklar}
      path="/seo-geo/crm-haklar"
      crumb="Haklar ve CRM"
      eyebrow="SEO & GEO · CRM kitap kartı"
      title="Haklar ve CRM"
      lead="Sitede satıştaki her kitabın CRM kartı: kitabın bir bölümünü internette gösterme hakkı (Google Kitaplar önizlemesi, tadımlık PDF), yayın durumu ve SEO’ya kaynak olabilecek bilgiler. CRM’den yalnız okunur; buradaki hak durumu bir ön elemedir, kesin söz telif birimindedir."
      actions={
        canRun && <button className="sg-button" onClick={() => read.mutate()} disabled={read.isPending || running}>
          {running ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <RefreshCw size={16} aria-hidden />}
          {running ? 'CRM okunuyor (1–2 dk)' : 'CRM’den yeniden oku'}
        </button>
      }
    >
      {list.isLoading && <Loading text="CRM kartları getiriliyor…" />}
      {list.error && <Failed error={list.error} />}
      {read.error && <Failed error={read.error} />}
      {s?.state.error && <p className="sg-banner err">Son CRM okuması başarısız: {s.state.error}</p>}

      {s && !s.books && !running && (
        <EmptyHint
          title="CRM henüz okunmadı"
          why={canRun ? '«CRM’den yeniden oku»ya basın ya da gece okumasını bekleyin. CRM’den yalnız okunur; CRM’de hiçbir şey değişmez.' : 'Gece okuması bittiğinde kitaplar burada listelenir. CRM’de hiçbir şey değişmez.'}
        />
      )}

      {s && s.books > 0 && (
        <>
          <section className="sg-kpis" aria-label="Özet">
            <Kpi label="Satıştaki kitap" value={fmt(s.products)} note={`CRM kartıyla eşleşmeyen ${fmt(s.unmatched)} · son okuma ${dateTime(s.lastRead)}`} info={<SeoInfo k={detail.data?.kaynaklar} label="Satıştaki kitap" />}
              explain="T-soft’ta satışta olan kitap sayısı. Barkodu CRM’deki bir kitap kartıyla eşleşmeyenler ayrıca sayılır; onların hak durumu bilinmez." />
            <Kpi label="Hak var" value={fmt(s.rights?.var)} note="Bütün telif alış sözleşmelerinde internet hakkı" tone="good" info={<SeoInfo k={detail.data?.kaynaklar} label="Hak var" />}
              explain="Kitaba bağlı ve yürürlükte olan bütün telif alış sözleşmeleri internette gösterime izin veriyor." />
            <Kpi label="Hak eksik ya da incelenmeli" value={fmt((s.rights?.eksik ?? 0) + (s.rights?.incele ?? 0))} note={`Eksik ${fmt(s.rights?.eksik)} · hak notu var ${fmt(s.rights?.incele)}`} tone="bad" info={<SeoInfo k={detail.data?.kaynaklar} label="Hak eksik ya da incelenmeli" />}
              explain="Eksik: yürürlükteki sözleşmelerden en az birinde internette gösterim hakkı yok. İncelenmeli: sözleşmede hakla ilgili not var, telif birimi bakmalı." />
            <Kpi label="Sözleşme kaydı yok" value={fmt(s.rights?.yok)} note="CRM’de yürürlükte telif alış sözleşmesi bağlı değil" info={<SeoInfo k={detail.data?.kaynaklar} label="Sözleşme kaydı yok" />}
              explain="CRM’de kitaba bağlı telif alış sözleşmesi yok ya da hiçbiri yürürlükte değil (süresi dolmuş, feshedilmiş)." />
            <Kpi label="Bizim değil / çekildi" value={fmt(flagged)} note="CRM yayın durumu; sitede hâlâ satışta" tone={flagged ? 'bad' : undefined} info={<SeoInfo k={detail.data?.kaynaklar} label="Bizim değil / çekildi" />}
              explain="CRM’deki yayın durumuna göre artık bizim olmayan, satıştan çekilen, geri istenen, hakları devredilen ya da iptal edilen ama sitede hâlâ satışta görünen kitaplar." />
          </section>

          <div className="sg-filters" role="toolbar" aria-label="Süzgeç">
            <Chip on={!filter} onClick={() => set('suzgec', '')} label="Tümü" n={s.products} />
            <Chip on={filter === 'durum'} onClick={() => set('suzgec', filter === 'durum' ? '' : 'durum')} label="Bizim değil / çekildi" n={flagged} />
            {RIGHTS_ORDER.map((r) => (
              <Chip key={r} on={filter === r} onClick={() => set('suzgec', filter === r ? '' : r)} label={RIGHTS_LABEL[r]} n={s.rights?.[r]} />
            ))}
            <Chip on={filter === 'eslesmedi'} onClick={() => set('suzgec', filter === 'eslesmedi' ? '' : 'eslesmedi')} label="CRM’de eşleşmeyen" n={s.unmatched} />
            <Chip on={filter === 'onizleme'} onClick={() => set('suzgec', filter === 'onizleme' ? '' : 'onizleme')} label="Tadımlık PDF var" n={s.preview} />
            <Chip on={filter === 'video'} onClick={() => set('suzgec', filter === 'video' ? '' : 'video')} label="Videosu var" n={s.video} />
          </div>

          <p style={{ margin: '-6px 0 0', fontSize: 12, color: 'var(--sg-muted)', display: 'flex', alignItems: 'center', gap: 4, flexWrap: 'wrap' }}>
            Bir süzgece dokunun, yalnız o durumdaki kitaplar listelensin.
            <Explain label="Hak durumları" title="Hak durumları ne demek?">
              «Koruma dışı eser»: telif süresi dolmuş, sözleşme gerekmez. «Set»: kendi sözleşmesi yok, hak içindeki kitaplara göre değerlendirilir. «Kitap değil»: CRM’de kitap olarak kayıtlı değil, telif sorusu aranmaz. «CRM’de eşleşmeyen»: barkodu hiçbir CRM kartıyla eşleşmedi.
            </Explain>
          </p>

          <div className="sg-audit">
            <section className="sg-card" aria-label="Kitaplar">
              <label className="sg-search" style={{ marginBottom: 12 }}>
                <Search size={16} aria-hidden />
                <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Kitap adı, ürün kodu ya da yayınevi" aria-label="Kitap ara" />
              </label>
              {list.data && !items.length && (
                <EmptyHint title="Bu süzgece uyan kitap yok" why="Aramayı kısaltın ya da üstteki süzgeçlerden «Tümü»nü seçin." />
              )}
              <div className="sg-list">
                {items.map((p) => (
                  <button key={p.id} className="sg-item" aria-current={selected === p.id} onClick={() => set('urun', p.id)}>
                    {p.image ? <img src={p.image} alt="" loading="lazy" /> : <span className="sg-noimg" aria-hidden />}
                    <span style={{ minWidth: 0 }}>
                      <span className="sg-item-name">{p.name || p.code}</span>
                      <span className="sg-item-meta sg-mono">
                        {fmt(p.sales)} satış{p.crm?.previewPdf ? ' · tadımlık PDF' : ''}{p.crm?.video ? ' · video' : ''}
                      </span>
                    </span>
                    <span className="sg-item-side">
                      {p.crm ? (
                        <span className={`sg-chip ${RIGHTS_TONE[p.crm.rights]}`}>{RIGHTS_LABEL[p.crm.rights]}</span>
                      ) : (
                        <span className="sg-chip">CRM’de yok</span>
                      )}
                      {p.crm?.statusFlag && <span className="sg-chip bad">{FLAG_LABEL[p.crm.statusFlag]}</span>}
                    </span>
                  </button>
                ))}
              </div>
              <SeoPager start={start} total={total} size={PAGE} onChange={setStart} />
            </section>

            <section aria-label="Seçilen kitap">
              {!selected && (
                <EmptyHint
                  title="Listeden bir kitap seçin"
                  why="Seçtiğiniz kitabın telif sözleşmeleri, internette gösterim hakkı ve CRM’deki SEO bilgileri burada açılır."
                />
              )}
              {selected && detail.isLoading && <Loading text="Kitap açılıyor…" />}
              {selected && detail.error && <Failed error={detail.error} />}
              {detail.data && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                  <CrmPanel book={detail.data.crm} tsoft={{ words: detail.data.details.words, hasMeta: !!detail.data.current.SeoDescription }} />
                  <Link className="sg-button" style={{ alignSelf: 'flex-start' }} to={`/seo-geo/urun-denetimi?urun=${encodeURIComponent(detail.data.id)}`}>
                    Bu kitabı Ürün denetiminde aç
                  </Link>
                </div>
              )}
            </section>
          </div>
        </>
      )}
    </SeoLayout>
  );
}

function Kpi({ label, value, note, tone, info, explain }: { label: string; value: string; note: string; tone?: 'good' | 'bad'; info?: ReactNode; explain?: ReactNode }) {
  return (
    <div className="sg-kpi">
      <div className="sg-kpi-label">{label}{info ? <> {info}</> : null}{explain ? <> <Explain label={label}>{explain}</Explain></> : null}</div>
      <div className="sg-kpi-value sg-mono" style={tone ? { color: tone === 'good' ? '#0f7a51' : '#c2361b' } : undefined}>{value}</div>
      <div className="sg-kpi-note">{note}</div>
    </div>
  );
}

function Chip({ on, onClick, label, n }: { on: boolean; onClick: () => void; label: string; n: number | undefined }) {
  return (
    <button className="sg-filter" aria-pressed={on} onClick={onClick}>
      {label} <span className="sg-mono">{fmt(n ?? 0)}</span>
    </button>
  );
}
