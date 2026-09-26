import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowDownToLine, ArrowRight, Check, ChevronLeft, ChevronRight, CircleHelp, FileSearch, Loader2, RefreshCw, Search, ShieldCheck } from 'lucide-react';
import Shell, { ZoomStage } from '../stitch/Shell';
import { ENGINE_BASE, ENGINE_ENABLED } from '../engine';
import DeepAuditPanel, { type DeepAudit } from './DeepAuditPanel';
import SqlEvidence from './SqlEvidence';
import SearchSelect from '../components/SearchSelect';
import FindingReason from './FindingReason';
import { findingSummary, accountExplanation, balanceSignExplanation } from './findings';
import { accountingText, checkExplanations } from './presentation';
import './audit.css';

type Account = { accountRef: number; code: string; name: string; balance: string; debit: number; credit: number; lineCount: number; unexpectedSign: boolean };
type CheckResult = { sql?: string; sqlPurpose?: string; id: string; title: string; affected: number; amount: string | null; formula: string; origin: string; status: string };
type Ratio = { note: number; title: string; value: string | null; numerator: string; denominator: string; formula: string; status: string; reason?: string; correction?: string; days?: string | null; daysFormula?: string };
type Control = { kind: string; note: number | null; id: string; title: string; status: string; reason: string; correction?: string; accountPrefixes: string[]; accountRefs: number[]; requiredEvidence: string[]; components: Array<{ sql?: string; sqlPurpose?: string; id?: string; title: string; status: string; affected?: number; accountRefs?: number[]; amount?: string; debit?: string; credit?: string; balance?: string; lineCount?: number; rows?: number; accounts?: Record<string, string>; formula?: string; value?: string | null; numerator?: string; denominator?: string }> };
type SupportingEvidence = { status: string; limitations: string[]; unavailableDatasets: string[]; documentProfiles: Array<{documentType: number; paymentType: string; undocumented: number; noPayment: number; rows: number; missingNumber: number; missingDate: number}>; assetProfiles: Array<{bookType: number; method: number; month: number; rows: number; assetCount: number; missingAssetCard: number; periodDepreciation: string}> };
type Overview = { deepAudit?: DeepAudit; runId: string; supportingEvidence: SupportingEvidence; coverage: { items: Control[]; counts: Record<string, number>; kindCounts: Record<string, number>; coverageReason: string; references: Array<{title: string; url: string}> }; source: string; year: number; lastDate: string; computedAt: string; lineCount: number; debit: string; credit: string; accounts: Account[]; checks: CheckResult[]; ratios: Ratio[]; limitations: string[]; revision: string; sql: string[]; dbMs: number; truncated: boolean };
type DocumentPage = { total: number; items: Array<{documentRef: number; slipRef: number; lineRef: number; slipNo: string; documentType: number; documentNo: string; documentDate: string; paymentType: string; description: string; undocumented: number; noPayment: number}> };
type Detail = { items: Array<{ lineRef: number; slipRef: number; slipNo: string; date: string; debit: number; credit: number; description: string; documentNo: string }>; total: number; page: number; readAt: string; separateRead: boolean };
type RefreshStatus = { state: 'idle' | 'refreshing' | 'ready' | 'error'; runId?: string; computedAt?: string; startedAt?: string; message?: string; calculationUpdated: boolean };
const number = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 2 });
const money = (n: number | string) => `${number.format(Number(n))} ₺`;
const day = (s?: string) => s ? new Date(s).toLocaleDateString('tr-TR') : '—';
const norm = (s: string) => s.toLocaleLowerCase('tr-TR');
const statusLabels: Record<string, string> = { passed: 'Geçti', finding: 'İnceleme adayı', calculated: 'Hesaplandı', observed: 'Muhasebe gözlemi', needs_evidence: 'Kanıt gerekiyor', not_due: 'Dönemi gelmedi', unverified: 'Doğrulanamadı' };

type Review = { version: number; history: Array<{ version: number; state: string; owner: string; note: string; evidence: string[]; actor: string; at: string }> };
function ReviewPanel({ runId, controlId }: { runId: string; controlId: string }) {
  const path = `runs/${runId}/reviews/${controlId}`;
  const review = useQuery({ queryKey: ['audit-review', runId, controlId], queryFn: () => get<Review>(path), retry: false });
  const [note, setNote] = useState('');
  const [owner, setOwner] = useState('');
  const [evidence, setEvidence] = useState('');
  const [state, setState] = useState('in_review');
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');
  async function save() {
    setSaving(true); setMessage('');
    try {
      const response = await fetch(`${ENGINE_BASE}/api/v1/financial-audit/${path}`, { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, signal: AbortSignal.timeout(30000), body: JSON.stringify({ version: review.data?.version ?? 0, state, owner, note, evidence: evidence.split('\n').map(x => x.trim()).filter(Boolean) }) });
      const result = await response.json();
      if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'İnceleme kaydedilemedi.');
      setMessage(result.message); setNote(''); await review.refetch();
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Kayıt başarısız.'); }
    finally { setSaving(false); }
  }
  return <section className="audit-review"><h3>İnceleme çalışma kâğıdı</h3><p>Bu rapora bağlı notlar ve belge referansları saklanır. Kanıt eklemek kontrolü otomatik olarak geçirmez.</p>
    {review.error && <p role="alert">İnceleme geçmişi okunamadı.</p>}
    <label>Sorumlu<input value={owner} maxLength={100} onChange={e => setOwner(e.target.value)} placeholder="İncelemeyi takip eden kişi" /></label>
    <label>Durum<select value={state} onChange={e => setState(e.target.value)}><option value="open">Açık</option><option value="in_review">İnceleniyor</option><option value="evidence_supplied">Kanıt sunuldu</option></select></label>
    <label>İnceleme notu<textarea value={note} maxLength={4000} onChange={e => setNote(e.target.value)} placeholder="Ne incelendi, hangi fark bulundu, sıradaki işlem nedir?" /></label>
    <label>Belge referansları<textarea value={evidence} onChange={e => setEvidence(e.target.value)} placeholder="Her satıra bir belge numarası veya kurum içi bağlantı" /></label>
    <button className="audit-button" disabled={saving || !review.data || note.trim().length < 3 || (state === 'evidence_supplied' && !evidence.trim())} onClick={save}>{saving ? 'Kaydediliyor…' : 'İncelemeyi kaydet'}</button>
    {message && <p role="status">{message}</p>}
    <details><summary>İnceleme geçmişi ({review.data?.version ?? 0})</summary>{review.data?.history.slice().reverse().map(h => <article key={h.version}><b>{h.owner || h.actor} · {new Date(h.at).toLocaleString('tr-TR')}</b><p>{h.note}</p>{h.evidence.map((e, i) => <p key={i}>{e}</p>)}</article>)}</details>
  </section>;
}

async function get<T>(path: string, method = 'GET'): Promise<T> {
  if (!ENGINE_ENABLED) throw new Error('Bu kurulumda Logo bağlantısı tanımlı değil.');
  const response = await fetch(`${ENGINE_BASE}/api/v1/financial-audit/${path}`, { method, credentials: 'include', signal: AbortSignal.timeout(120000) });
  if (!response.ok) {
    if ([401, 403].includes(response.status)) throw new Error('Verileri görmek için oturum açmanız gerekiyor.');
    const body = await response.json().catch(() => null);
    throw new Error(typeof body?.detail === 'string' ? body.detail : 'Logo yanıt vermedi. Denetim doğrulanamadı.');
  }
  return response.json();
}

export default function FinancialAudit() {
  const queryClient = useQueryClient();
  const [tab, setTab] = useState('overview');
  const [search, setSearch] = useState('');
  const [kind, setKind] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');
  const [catalogPage, setCatalogPage] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const [account, setAccount] = useState<Account | null>(null);
  const [page, setPage] = useState(0);
  const [onlyFindings, setOnlyFindings] = useState(false);
  const [runChoice, setRunChoice] = useState('');
  const [documentAccount, setDocumentAccount] = useState('');
  const [documentPage, setDocumentPage] = useState(0);
  useEffect(() => {
    if (account) document.getElementById('audit-logo-detail')?.scrollIntoView({ block: 'start' });
  }, [account]);
  useEffect(() => {
    if (selected && tab === 'catalog' && window.innerWidth < 768) document.getElementById('audit-source-detail')?.scrollIntoView({ block: 'start' });
  }, [selected, tab]);
  const overview = useQuery({ queryKey: ['financial-audit', 2026, runChoice], queryFn: () => get<Overview>(runChoice ? `runs/${runChoice}` : 'overview?year=2026'), enabled: ENGINE_ENABLED, retry: false, staleTime: 120000, refetchOnWindowFocus: false });
  const refreshStatus = useQuery({ queryKey: ['audit-refresh-status'], queryFn: () => get<RefreshStatus>('refresh-status'), enabled: ENGINE_ENABLED, retry: false, refetchInterval: q => q.state.data?.state === 'refreshing' ? 2000 : 15000 });
  const refresh = useMutation({ mutationFn: () => get<RefreshStatus>('refresh', 'POST'), onSuccess: status => {
    queryClient.setQueryData(['audit-refresh-status'], status);
    setRunChoice('');
  }});
  useEffect(() => {
    if (!runChoice && refreshStatus.data?.runId && refreshStatus.data.runId !== overview.data?.runId) {
      void queryClient.invalidateQueries({ queryKey: ['financial-audit', 2026, ''], exact: true });
    }
  }, [runChoice, refreshStatus.data?.runId, overview.data?.runId, queryClient]);
  const runs = useQuery({ queryKey: ['financial-audit-runs', overview.data?.runId], queryFn: () => get<{ items: Array<{runId: string; computedAt: string}>; total: number }>('runs'), enabled: !!overview.data?.runId, retry: false });
  const runOptions = useMemo(() => (runs.data?.items ?? []).map(r => ({ value: r.runId, label: new Date(r.computedAt).toLocaleString('tr-TR') })), [runs.data]);
  const detail = useQuery({ queryKey: ['financial-audit-lines', overview.data?.runId, account?.accountRef, page], queryFn: () => get<Detail>(`lines?year=2026&account=${account!.accountRef}&page=${page}`), enabled: !!account, retry: false });
  const documents = useQuery({ queryKey: ['financial-audit-documents', overview.data?.runId, documentAccount, documentPage], queryFn: () => get<DocumentPage>(`documents?year=2026&page=${documentPage}${documentAccount ? `&main_account=${documentAccount}` : ''}`), enabled: tab === 'evidence', retry: false });
  const data = overview.data;
  // The internal analysis document is never requested by this screen.
  const source = useMemo(() => ({items: (data?.coverage.items ?? []).map(control => {
    const title = accountingText(control.title).replace(/\s*·\s*kaynak notu\s+\d+/giu, '').replace(/^\d+(?:\.\d+)+\s+/u, '');
    return {id:control.id, kind:control.kind, note:control.note, title, section:title, text:accountingText(control.reason)};
  })}), [data]);
  const controls = useMemo(() => new Map(data?.coverage?.items.map(c => [c.id, c]) ?? []), [data]);
  const catalogStatus = (id: string) => statusLabels[controls.get(id)?.status ?? 'unverified'] ?? 'Doğrulanamadı';
  const filtered = useMemo(() => source.items.filter(x => (kind === 'all' || x.kind === kind) && (statusFilter === 'all' || controls.get(x.id)?.status === statusFilter) && norm(`${x.title} ${x.text} ${x.section} ${x.note ?? ''}`).includes(norm(search))), [search, kind, source, statusFilter, controls]);
  const item = source.items.find(x => x.id === selected);
  const control = selected ? controls.get(selected) : undefined;
  const findings = data?.checks.filter(c => c.status === 'finding') ?? [];
  const accounts = data?.accounts.filter(a => (!onlyFindings || a.unexpectedSign) && norm(`${a.code} ${a.name}`).includes(norm(search))) ?? [];
  const openAccount = (a: Account) => { setAccount(a); setPage(0); };
  const tabs = [['overview', 'Denetim özeti'], ['discovery', 'Logo’da ne var?'], ['catalog', 'Kontrol kütüphanesi'], ['ledger', 'Logo kayıtları'], ['evidence', 'Dayanak veriler']];
  const refreshing = refresh.isPending || refreshStatus.data?.state === 'refreshing';
  const refreshButton = <button className="audit-button" disabled={refreshing || !ENGINE_ENABLED} onClick={() => refresh.mutate()}><RefreshCw size={16} className={refreshing ? 'animate-spin' : ''} />{refreshing ? 'Veriler yenileniyor' : 'Verileri yenile'}</button>;

  if (!data) return <Shell head={{ tenant: 'Timaş Yayınları', section: 'Finans & Risk', crumb: 'Finansal denetim', source: 'Logo · muhasebe', presence: 'Kayıtlı denetim raporu' }}><main className="audit-main"><div className="audit-page"><h1>Finansal denetim</h1><section className="audit-panel" aria-busy={overview.isFetching}><h2>{overview.isFetching ? 'Kayıtlı rapor açılıyor' : 'Rapor şu anda açılamadı'}</h2><p>{overview.isFetching ? 'Son tamamlanan hesaplama sunucudaki kayıttan getiriliyor.' : refreshStatus.data?.message || (overview.error instanceof Error ? overview.error.message : 'İlk rapor hazırlandığında burada otomatik gösterilecek.')}</p>{!overview.isFetching && <div className="audit-heading-actions"><button className="audit-button" onClick={() => overview.refetch()}>Raporu tekrar aç</button>{refreshButton}</div>}</section></div></main></Shell>;

  return <Shell head={{ tenant: 'Timaş Yayınları', section: 'Finans & Risk', crumb: 'Finansal denetim', source: 'Logo · muhasebe', presence: `Veri: ${day(data.lastDate)}` }}>
    <main className="audit-main">
      <ZoomStage><div className="audit-page">
        <header className="audit-heading">
          <div><div className="audit-eyebrow">FİNANS & RİSK / DENETİM MASASI</div><h1>Rakamların arkasını görün<span>.</span></h1><p>Finansal denetim · Genel görünümden hesaplamaya, hesaplamadan Logo kaydına.</p></div>
          <div className="audit-heading-actions">{refreshButton}<a className="audit-button" href={`${ENGINE_BASE}/api/v1/financial-audit/runs/${data.runId}/export`} download><ArrowDownToLine size={16} /> Raporu indir</a></div>
        </header>

        <section className="audit-hero">
          <div className="audit-hero-copy"><div className="audit-chip"><ShieldCheck size={14} /> KAYNAĞINA KADAR İZLENEBİLİR</div><h2>Her bulgunun<br /><em>bir dayanağı var.</em></h2><p>Ne kontrol edildi, nasıl hesaplandı, hangi kayıt etkili? Finans ekibiniz için tek bir çalışma alanı.</p><div className="audit-hero-meta"><span>2026 işlem dönemi</span><span>TRY / Türk lirası</span><span>Salt okunur</span></div></div>
          <div className="audit-orbit" aria-label="Denetim kapsamı"><div className="audit-orbit-core"><ShieldCheck size={30} /><strong>{data ? data.checks.length : '—'}</strong><span>temel kontrol</span></div><span className="audit-orbit-label">LOGO → HESAPLAMA → BULGU</span></div>
          <div className="audit-hero-side"><span className="audit-eyebrow">VERİNİN ZAMANI</span><strong>{day(data?.lastDate)}</strong><p>{`${number.format(data.lineCount)} hareket · ${number.format(data.accounts.length)} hesap`}</p><span className="audit-source-pill">2026 yedeği · canlı dönem değildir</span></div>
        </section>

        <div className="audit-message" role="status">{refreshing && <Loader2 size={16} className="animate-spin" />}<span><b>Son güncelleme: {new Date(data.computedAt).toLocaleString('tr-TR')}</b> · {refreshing ? 'Yeni hesaplama arka planda hazırlanıyor; mevcut raporu incelemeye devam edebilirsiniz.' : runChoice ? 'Arşivden seçtiğiniz rapor gösteriliyor.' : 'Son tamamlanan rapor gösteriliyor. Veriler saatlik olarak ve isteğiniz üzerine yenilenir.'}</span></div>
        {(overview.error || refresh.error || refreshStatus.error || refreshStatus.data?.state === 'error') && <div className="audit-message audit-warning" role="alert"><span>{refreshStatus.data?.state === 'error' ? refreshStatus.data.message : 'Güncel rapor kontrolü tamamlanamadı. Görüntülediğiniz son başarılı rapor korunuyor.'}</span><button className="audit-button" disabled={refreshing} onClick={() => refresh.mutate()}>Yenilemeyi tekrar dene</button></div>}

        <div className="audit-toolbar"><div className="audit-run-picker"><span aria-hidden>Çalışma raporu{runs.data ? ` · ${runs.data.total.toLocaleString('tr-TR')} kayıt` : ''}</span><SearchSelect label="Kaydedilmiş denetim raporu" placeholder="Son tamamlanan rapor" className="sm:w-64" value={runChoice} onChange={v => { setRunChoice(v); setSelected(null); setAccount(null); }} options={runOptions} /></div><span className="audit-badge">{runChoice ? 'Kaydedilmiş hesaplama · Logo hareket detayı ayrı okumadır' : 'Rapor ve inceleme notları arşivlenir'}</span></div>

        <nav className="audit-tabs" aria-label="Denetim bölümleri">{tabs.map(([id, title]) => <button key={id} aria-current={tab === id ? 'page' : undefined} onClick={() => { setTab(id); setSearch(''); }}>{title}{id === 'catalog' && <span>{source.items.length}</span>}</button>)}</nav>

        {tab === 'discovery' && <DeepAuditPanel key={data.runId} data={data.deepAudit} runId={data.runId} load={get} />}

        {tab === 'overview' && <>
          <section className="audit-discovery-link"><div><span className="audit-eyebrow">LOGO’DA NE VAR, NE EKSİK?</span><h2>Kaynakları birbirleriyle karşılaştırın.</h2><p>{data?.deepAudit ? `${data.deepAudit.checks.length} ek veri kontrolü · ${data.deepAudit.sources.length} kaynak alanı. Bulunan kayıtlar, farklar ve eksik dayanaklar birlikte.` : 'Fatura, banka, kredi ve belge kaynaklarının kapsamını inceleyin.'}</p></div><button className="audit-button" onClick={() => setTab('discovery')}>Veri kapsamını aç <ArrowRight size={16}/></button></section>
          <div className="audit-stats">
            <article><span>İnceleme gerektiren</span><strong className="audit-coral">{data ? findings.length : '—'}</strong><small>Bulgu üreten kontrol türü</small></article>
            <article><span>Kontrol geçti</span><strong className="audit-green">{data ? data.checks.filter(c => c.status === 'passed').length : '—'}</strong><small>Yalnız çalıştırılan kurallar içinde</small></article>
            <article><span>Hesaplanan oran</span><strong>{data ? data.ratios.filter(r => r.value !== null).length : '—'}</strong><small>Kapanış öncesi mizan · yorum gerektirir</small></article>
            <article><span>İnceleme kapsamı</span><strong>{source.items.length}</strong><small>Kontrol ve inceleme başlığı · başarı oranı değildir</small></article>
          </div>
          {data?.coverage && <section className="audit-panel audit-coverage"><div className="audit-section-head"><div><span className="audit-eyebrow">KAPSAM VE TAMAMLANMA</span><h2>Her maddenin durumu açık</h2></div></div><div className="audit-coverage-grid">{Object.entries(data.coverage.counts).map(([status, count]) => <button key={status} onClick={() => { setStatusFilter(status); setKind('all'); setCatalogPage(0); setTab('catalog'); }}><strong>{count}</strong><span>{statusLabels[status] ?? status}</span></button>)}</div><p>Hesaplanan sonuçlar ile belge ve inceleme bekleyen işler ayrı gösterilir.</p><small>Başlıklar aynı hesabı farklı açılardan ele alabilir; sayılar denetim başarı oranı değildir.</small></section>}
          <div className="audit-columns">
            <section className="audit-panel"><div className="audit-section-head"><div><span className="audit-eyebrow">ÖNCE ÖNEMLİ OLAN</span><h2>Kontrol sonuçları</h2></div><span className="audit-badge">Logo muhasebe</span></div>
              {!data && <p className="audit-empty">Sonuçlar için gerçek Logo verisinin okunması gerekiyor. Kontrol kütüphanesini inceleyebilirsiniz.</p>}
              {data?.checks.map(c => <details className="audit-check" key={c.id}><summary><span className={`audit-status-icon ${c.status}`} >{c.status === 'passed' ? <Check size={17} /> : <FileSearch size={17} />}</span><span className="audit-check-title"><strong>{accountingText(c.title)}</strong><small>{c.status === 'finding' ? `${number.format(c.affected)} kayıt/hesap inceleme adayı` : c.status === 'passed' ? 'Kontrol geçti' : 'Doğrulanamadı'}</small></span><ChevronRight size={16} /></summary><div className="audit-check-body">{c.status === 'finding' && <FindingReason explanation={findingSummary(c)} />}<p>{checkExplanations[c.id ?? ''] ?? accountingText(c.formula)}</p>{c.amount !== null && <p><b>Kontrol tutarı:</b> {money(c.amount)} <small>(tahmini kayıp veya vergi cezası değildir)</small></p>}<SqlEvidence sql={c.sql} description={c.sqlPurpose ?? 'Bu raporda kullanılan veri sorgusu.'} /><button className="audit-button" onClick={() => { setOnlyFindings(c.id === 'account-sign'); setTab('ledger'); setSearch(''); }}>Hesapları incele <ArrowRight size={14} /></button></div></details>)}
            </section>
            <aside className="audit-panel audit-insight"><span className="audit-eyebrow">DENETİMİN SINIRLARI</span><CircleHelp size={26} /><h2>Eksik kanıt,<br />olumlu sonuç değildir.</h2><p>Belge doğruluğu, fiili sayım, beyanname ve dış mutabakat gerektiren kontroller ayrıca incelenmelidir.</p><ul><li>Vergisel eşikler dönemine göre doğrulanmalı.</li><li>Hesaplama için gereken bilgi ve belgeler tamamlanmalı.</li><li>Çalıştırılmayan maddeler “geçti” sayılmaz.</li></ul><button className="audit-button" onClick={() => setTab('catalog')}>Kontrol kütüphanesine git <ArrowRight size={14} /></button></aside>
          </div>
          <section className="audit-panel"><div className="audit-section-head"><div><span className="audit-eyebrow">MALİ GÖRÜNÜM</span><h2>Rasyolar · hesaplama açık</h2></div><span className="audit-badge">Sektörel değerlendirme bekliyor</span></div><div className="audit-ratios">{data?.ratios.map(r => <details key={r.note}><summary><span>{r.title}</span><strong>{r.value === null ? '—' : number.format(Number(r.value))}<small> ×</small></strong></summary><p>{accountingText(r.formula)}</p><p>{money(r.numerator)} / {money(r.denominator)}</p>{r.days != null && <p><b>{number.format(Number(r.days))} gün</b> · {accountingText(r.daysFormula)}</p>}<p>{r.value === null ? accountingText(r.reason || 'Hesaplamanın böleni sıfır veya negatif ya da gerekli bilgi eksik; oran hesaplanamadı.') : 'Net hesap bakiyelerinden; kesin mali tablo görüşü değildir.'}</p><button onClick={() => { const found = source.items.find(x => x.note === r.note); setSelected(found?.id ?? null); setTab('catalog'); }} className="audit-text-button">Kontrol ayrıntısını gör →</button></details>)}</div></section>
          <details className="audit-panel"><summary>Hesaplama kapsamı ve kullanılan sorgular</summary>{data?.limitations.map(x => <p key={x}>{accountingText(x)}</p>)}<p>Rapor kimliği: {data?.runId ?? '—'}. Bu raporun hesaplama sonucu ve çalışma notları saklanır.</p><p>Son okuma: {data?.computedAt ? new Date(data.computedAt).toLocaleString('tr-TR') : '—'}. Sorgu süresi: {data ? `${data.dbMs} ms` : '—'}.</p><pre>{data?.sql.join('\n\n')}</pre></details>
        </>}

        {tab === 'catalog' && <>
          <div className="audit-message audit-warning"><FileSearch size={18} /><span><b>{source.items.length} kontrol ve inceleme başlığı.</b> Hesaplanan sonuçlar ve belge bekleyen incelemeler birlikte gösterilir. Başlık sayısı, tamamlanmış kontrol sayısı değildir.</span></div>
          <div className="audit-toolbar"><label className="audit-search"><Search size={17} /><input aria-label="Kontrol ara" value={search} placeholder="Hesap veya kontrol açıklamasında ara…" onChange={e => { setSearch(e.target.value); setCatalogPage(0); }} /></label><select aria-label="Kontrol türü" value={kind} onChange={e => { setKind(e.target.value); setCatalogPage(0); }}><option value="all">Tüm incelemeler</option><option value="analysis">Mali analiz</option><option value="control">Denetim kuralları</option><option value="checklist">İnceleme listeleri</option><option value="section">Hesap inceleme açıklamaları</option></select><select aria-label="Kontrol durumu" value={statusFilter} onChange={e => { setStatusFilter(e.target.value); setCatalogPage(0); }}><option value="all">Tüm durumlar</option>{Object.entries(statusLabels).map(([v, t]) => <option value={v} key={v}>{t}</option>)}</select></div>
          <div className="audit-catalog-layout"><section className="audit-panel"><div className="audit-section-head"><h2>Kontrol kütüphanesi</h2><span>{filtered.length} madde</span></div>{filtered.slice(catalogPage*20, (catalogPage+1)*20).map(x => <button className={`audit-catalog-item ${selected === x.id ? 'selected' : ''}`} key={x.id} onClick={() => setSelected(x.id)}><span className="audit-eyebrow">{x.kind === 'analysis' ? 'MALİ ANALİZ' : x.kind === 'control' ? 'DENETİM KURALI' : x.kind === 'section' ? 'HESAP İNCELEMESİ' : 'İNCELEME MADDESİ'}</span><strong>{x.title || x.section}</strong><span>{catalogStatus(x.id)}</span></button>)}{!filtered.length && <p>Aramanızla eşleşen madde yok.</p>}<div className="audit-pagination"><button aria-label="Önceki maddeler" disabled={catalogPage === 0} onClick={() => setCatalogPage(p => p-1)}><ChevronLeft size={18} /></button><span>{catalogPage+1} / {Math.max(1, Math.ceil(filtered.length/20))}</span><button aria-label="Sonraki maddeler" disabled={(catalogPage+1)*20 >= filtered.length} onClick={() => setCatalogPage(p => p+1)}><ChevronRight size={18} /></button></div></section>
            <aside id="audit-source-detail" className="audit-panel audit-source-detail">{item ? <><span className="audit-eyebrow">KONTROL AYRINTISI</span><h2>{accountingText(item.section)}</h2><span className={`audit-badge ${control?.status ?? ''}`}>{catalogStatus(item.id)}</span>
              {control && <div className="audit-control-result"><p>{accountingText(control.reason)}</p>

                {control.components.map((c, i) => <article className="audit-calculation" key={c.id ?? i}><h3>{accountingText(c.title)}</h3>{c.status === 'finding' && (c.id === 'balance-sign' ? <><p>Bu alt hesapların net bakiyesi, kontrolün tanımladığı beklenen yönün tersinde. Sınıflandırma veya kayıt hatası olup olmadığı belgeyle incelenmelidir.</p>{data.accounts.filter(a => c.accountRefs?.includes(a.accountRef)).map(a => <FindingReason key={a.accountRef} explanation={balanceSignExplanation(a)} />)}</> : <FindingReason explanation={findingSummary({id:c.id ?? '',status:c.status,affected:c.affected ?? null,amount:c.amount})} />)}{c.formula && <p>{checkExplanations[c.id ?? ''] ?? accountingText(c.formula)}</p>}{c.lineCount != null && <p>{number.format(c.lineCount)} hareket</p>}{c.debit != null && <p>Borç: <b>{money(c.debit)}</b> · Alacak: <b>{money(c.credit ?? 0)}</b><br />Net bakiye: <b>{money(c.balance ?? 0)}</b></p>}{c.accounts && Object.entries(c.accounts).map(([code, value]) => <p key={code}>{code}: <b>{money(value)}</b></p>)}{c.affected != null && <p>{c.affected} inceleme adayı{c.amount != null && <> · {money(c.amount)}</>}</p>}{c.rows != null && <p>{number.format(c.rows)} döviz alanı dolu satır</p>}{c.numerator != null && <p>{money(c.numerator)} / {money(c.denominator ?? 0)} = {c.value == null ? 'Doğrulanamadı' : number.format(Number(c.value))}</p>}{c.sql && <SqlEvidence sql={c.sql} description={c.sqlPurpose ?? 'Hesaplama için kullanılan kaynak sorgusu.'} />}</article>)}
                {control.requiredEvidence.length > 0 && <><h3>Tamamlamak için gereken kanıtlar</h3><ul>{control.requiredEvidence.map(e => <li key={e}>{e}</li>)}</ul></>}
                {item.note != null && ((item.note >= 43 && item.note <= 49) || (item.note >= 115 && item.note <= 123)) && <button className="audit-button" onClick={() => { setDocumentAccount(control.accountPrefixes.length === 1 && ['100','101','102','121','191','391'].includes(control.accountPrefixes[0]) ? control.accountPrefixes[0] : ''); setDocumentPage(0); setTab('evidence'); }}>Logo dayanak verilerini aç →</button>}<button className="audit-button" onClick={() => setTab('discovery')}>Bulunan kaynakları ve eksik dayanakları gör →</button><h3>Bu maddeye bağlı Logo hesapları</h3><div className="audit-linked-accounts">{data?.accounts.filter(a => control.accountRefs.includes(a.accountRef)).map(a => <button className="audit-button" key={a.accountRef} onClick={() => { setTab('ledger'); setSearch(a.code); setOnlyFindings(false); openAccount(a); }}>{a.code} · {a.name} →</button>)}{!control.accountRefs.length && <p>Bu maddeye özel hesap eşleşmesi yok; kaynak veya belge düzeyinde inceleme gerekiyor.</p>}</div>
                {data?.runId && <ReviewPanel key={`${data.runId}-${item.id}`} runId={data.runId} controlId={item.id} />}
              </div>}
              </> : <div className="audit-empty"><FileSearch size={30} /><h2>Bir kontrol seçin</h2><p>Kontrolün amacı, hesaplama yöntemi ve inceleme durumu burada görünür.</p></div>}</aside></div>
        </>}

        {tab === 'ledger' && <>
          <div className="audit-toolbar"><label className="audit-search"><Search size={17} /><input aria-label="Logo hesabı ara" value={search} onChange={e => setSearch(e.target.value)} placeholder="Hesap kodu veya adı…" /></label><label className="audit-toggle"><input type="checkbox" checked={onlyFindings} onChange={e => setOnlyFindings(e.target.checked)} /> Yalnız ters bakiyeler</label></div>
          <section className="audit-panel"><div className="audit-section-head"><h2>Logo hesapları</h2><span>{accounts.length} hesap</span></div><div className="audit-table-scroll"><table><thead><tr><th>Hesap</th><th>Borç</th><th>Alacak</th><th>Net bakiye</th><th>Hareket</th></tr></thead><tbody>{accounts.map(a => <tr key={a.accountRef}><td><button className="audit-account" onClick={() => openAccount(a)}><b>{a.code} · {a.name}</b>{a.unexpectedSign && <span>Hesap karakterine ters bakiye</span>}</button>{a.unexpectedSign && <FindingReason explanation={accountExplanation(a)} />}</td><td>{money(a.debit)}</td><td>{money(a.credit)}</td><td>{money(a.balance)}</td><td><button className="audit-text-button" onClick={() => openAccount(a)}>{number.format(a.lineCount)} satır →</button></td></tr>)}</tbody></table></div>{!accounts.length && <p className="audit-empty">{data ? 'Bu filtrede hesap bulunamadı.' : 'Hesapları göstermek için Logo verisi okunmalı.'}</p>}</section>
          {account && <section id="audit-logo-detail" className="audit-panel" aria-live="polite"><div className="audit-section-head"><div><span className="audit-eyebrow">LOGO HAREKET DETAYI</span><h2>{account.code} · {account.name}</h2></div><button className="audit-button" onClick={() => setAccount(null)}>Kapat</button></div>{account.unexpectedSign && <FindingReason explanation={accountExplanation(account)} />}<p>Bu detay ayrı bir kaynak okumasıdır. Fiş ve satır kimlikleri Logo kaydını bulmanız içindir.</p>{detail.isFetching && <p>Hareketler okunuyor…</p>}{detail.error && <p role="alert">{detail.error instanceof Error ? detail.error.message : 'Detay okunamadı.'}</p>}<div className="audit-table-scroll"><table><thead><tr><th>Tarih / fiş</th><th>Belge</th><th>Açıklama</th><th>Borç</th><th>Alacak</th><th>Kaynak kimliği</th></tr></thead><tbody>{detail.data?.items.map(l => <tr key={l.lineRef}><td>{day(l.date)}<br /><b>{l.slipNo}</b></td><td>{l.documentNo || '—'}</td><td>{l.description || '—'}</td><td>{money(l.debit)}</td><td>{money(l.credit)}</td><td>Fiş {l.slipRef}<br />Satır {l.lineRef}</td></tr>)}</tbody></table></div><div className="audit-pagination"><button aria-label="Önceki hareketler" disabled={!page || detail.isFetching} onClick={() => setPage(p => p-1)}><ChevronLeft size={18} /></button><span>{detail.data?.total ?? '—'} hareket · Sayfa {page+1}</span><button aria-label="Sonraki hareketler" disabled={!detail.data || (page+1)*50 >= detail.data.total || detail.isFetching} onClick={() => setPage(p => p+1)}><ChevronRight size={18} /></button></div></section>}
        </>}

        {tab === 'evidence' && <>
          <section className="audit-panel"><div className="audit-section-head"><div><span className="audit-eyebrow">LOGO E-DEFTER KAYNAĞI</span><h2>Belgeden muhasebe fişine</h2></div></div>
            <p>Bu liste ayrı kaynak okumasıdır. Belge türü kodları henüz sürüm sözlüğüyle doğrulanmadı; ödeme şekli Logo'daki özgün metindir.</p>
            <label className="audit-run-picker">Ana hesap<select aria-label="Belge ana hesabı" value={documentAccount} onChange={e => { setDocumentAccount(e.target.value); setDocumentPage(0); }}><option value="">Tüm belgeler</option>{['100','101','102','121','191','391'].map(c => <option key={c} value={c}>{c}</option>)}</select></label>
            {documents.isFetching && <p role="status">E-defter belge kayıtları okunuyor…</p>}{documents.error && <p role="alert">{documents.error instanceof Error ? documents.error.message : 'Belge kayıtları okunamadı.'}</p>}
            <div className="audit-table-scroll"><table><thead><tr><th>Fiş / kaynak</th><th>Belge tarihi / no</th><th>Tür kodu / ödeme</th><th>Açıklama</th><th>Kaynak bayrakları</th></tr></thead><tbody>{documents.data?.items.map(d => <tr key={d.documentRef}><td>{d.slipNo}<br />Belge {d.documentRef} · Fiş {d.slipRef}<br />{d.lineRef ? `Satır ${d.lineRef}` : 'Fiş başlığı belgesi'}</td><td>{day(d.documentDate)}<br />{d.documentNo || '—'}</td><td>{d.documentType}<br />{d.paymentType || '—'}</td><td>{d.description || '—'}</td><td>Belge yok: {d.undocumented}<br />Ödeme yok: {d.noPayment}</td></tr>)}</tbody></table></div>
            <div className="audit-pagination"><button aria-label="Önceki belgeler" disabled={!documentPage || documents.isFetching} onClick={() => setDocumentPage(p => p-1)}><ChevronLeft size={18} /></button><span>{documents.data?.total ?? '—'} belge · Sayfa {documentPage+1}</span><button aria-label="Sonraki belgeler" disabled={!documents.data || documents.isFetching || (documentPage+1)*50 >= documents.data.total} onClick={() => setDocumentPage(p => p+1)}><ChevronRight size={18} /></button></div>
          </section>
          <section className="audit-panel"><h2>Rapora kaydedilen belge profili</h2>{data?.supportingEvidence?.status === 'unverified' && <p role="alert">Destek kaynaklarının bir bölümü okunamadı; ilgili kontroller doğrulanamadı.</p>}<div className="audit-table-scroll"><table><thead><tr><th>Tür kodu</th><th>Ödeme şekli</th><th>Kaynak bayrakları</th><th>Belge sayısı</th><th>Eksik no / tarih</th></tr></thead><tbody>{data?.supportingEvidence?.documentProfiles.map((d,i) => <tr key={i}><td>{d.documentType}</td><td>{d.paymentType || '—'}</td><td>Belge yok {d.undocumented} · Ödeme yok {d.noPayment}</td><td>{number.format(d.rows)}</td><td>{d.missingNumber} / {d.missingDate}</td></tr>)}</tbody></table></div></section>
          <section className="audit-panel"><h2>Sabit kıymet hesap cetveli · 2026</h2><p>Her hesaplama grubu/yöntem/ay ayrı gösterilir. Grup ve yöntem kodlarının iş anlamı ile varlık–muhasebe eşlemesi doğrulanmadan toplam amortisman veya vergi uygunluğu sonucu verilmez.</p><div className="audit-table-scroll"><table><thead><tr><th>Grup / yöntem kodu</th><th>Ay</th><th>Cetvel satırı</th><th>Grup içi varlık</th><th>Kaynak dönem tutarı</th><th>Kart bağlantısı eksik</th></tr></thead><tbody>{data?.supportingEvidence?.assetProfiles.map((a,i) => <tr key={i}><td>{a.bookType} / {a.method}</td><td>{a.month}</td><td>{number.format(a.rows)}</td><td>{number.format(a.assetCount)}</td><td>{a.periodDepreciation == null ? '—' : money(a.periodDepreciation)}</td><td>{a.missingAssetCard}</td></tr>)}</tbody></table></div>{data?.supportingEvidence?.limitations.map(l => <p key={l}>{l}</p>)}</section>
        </>}

        <footer className="audit-footer"><span><ShieldCheck size={14} /> Logo kaynağına yazılmaz.</span><span>Kaynak → kontrol → hesaplama → kayıt</span></footer>
      </div></ZoomStage>
    </main>
  </Shell>;
}
