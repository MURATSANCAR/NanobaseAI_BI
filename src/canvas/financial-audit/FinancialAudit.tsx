import { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ArrowDownToLine, ArrowRight, BookOpen, Check, ChevronLeft, ChevronRight, CircleHelp, FileSearch, Loader2, Search, ShieldCheck } from 'lucide-react';
import Shell, { ZoomStage } from '../stitch/Shell';
import { railFor } from '../stitch/screens';
import { ENGINE_BASE, ENGINE_ENABLED } from '../engine';
import './audit.css';

type Source = { title: string; sha256: string; pageCount: number; items: Array<{ id: string; kind: string; title: string; section: string; note: number | null; page: number; endPage: number; text: string }>; pages: Array<{ page: number; text: string }> };
const emptySource: Source = { title: 'Elektronik Defter Denetimi Analiz Dokümanı', sha256: '', pageCount: 241, items: [], pages: [] };

type Account = { accountRef: number; code: string; name: string; balance: string; debit: number; credit: number; lineCount: number; unexpectedSign: boolean };
type CheckResult = { id: string; title: string; affected: number; amount: string | null; formula: string; origin: string; status: string };
type Ratio = { note: number; title: string; value: string | null; numerator: string; denominator: string; formula: string; status: string; reason?: string };
type Overview = { source: string; year: number; lastDate: string; computedAt: string; lineCount: number; debit: string; credit: string; accounts: Account[]; checks: CheckResult[]; ratios: Ratio[]; limitations: string[]; revision: string; sql: string[]; dbMs: number; truncated: boolean };
type Detail = { items: Array<{ lineRef: number; slipRef: number; slipNo: string; date: string; debit: number; credit: number; description: string; documentNo: string }>; total: number; page: number; readAt: string; separateRead: boolean };
const number = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 2 });
const money = (n: number | string) => `${number.format(Number(n))} ₺`;
const day = (s?: string) => s ? new Date(s).toLocaleDateString('tr-TR') : '—';
const norm = (s: string) => s.toLocaleLowerCase('tr-TR');

async function get<T>(path: string): Promise<T> {
  if (!ENGINE_ENABLED) throw new Error('Bu kurulumda Logo bağlantısı tanımlı değil.');
  const response = await fetch(`${ENGINE_BASE}/api/v1/financial-audit/${path}`, { credentials: 'include', signal: AbortSignal.timeout(120000) });
  if (!response.ok) {
    if ([401, 403].includes(response.status)) throw new Error('Verileri görmek için oturum açmanız gerekiyor.');
    const body = await response.json().catch(() => null);
    throw new Error(typeof body?.detail === 'string' ? body.detail : 'Logo yanıt vermedi. Denetim doğrulanamadı.');
  }
  return response.json();
}

function download(name: string, value: unknown) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: 'application/json;charset=utf-8' }));
  const a = document.createElement('a'); a.href = url; a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export default function FinancialAudit() {
  const catalog = useQuery({ queryKey: ['financial-audit-catalog'], queryFn: () => get<Source>('catalog'), enabled: ENGINE_ENABLED, staleTime: 3600000, retry: false });
  const source = catalog.data ?? emptySource;
  const [tab, setTab] = useState('overview');
  const [search, setSearch] = useState('');
  const [kind, setKind] = useState('all');
  const [catalogPage, setCatalogPage] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const [account, setAccount] = useState<Account | null>(null);
  const [page, setPage] = useState(0);
  const [onlyFindings, setOnlyFindings] = useState(false);
  const [sourcePage, setSourcePage] = useState(41);
  useEffect(() => {
    if (account) document.getElementById('audit-logo-detail')?.scrollIntoView({ block: 'start' });
  }, [account]);
  useEffect(() => {
    if (selected && tab === 'catalog' && window.innerWidth < 768) document.getElementById('audit-source-detail')?.scrollIntoView({ block: 'start' });
  }, [selected, tab]);
  const overview = useQuery({ queryKey: ['financial-audit', 2026], queryFn: () => get<Overview>('overview?year=2026'), enabled: ENGINE_ENABLED, retry: false, staleTime: 120000 });
  const detail = useQuery({ queryKey: ['financial-audit-lines', account?.accountRef, page], queryFn: () => get<Detail>(`lines?year=2026&account=${account!.accountRef}&page=${page}`), enabled: !!account, retry: false });
  const data = overview.data;
  const catalogStatus = (note: number | null) => {
    const ratio = data?.ratios.find(r => r.note === note);
    return ratio?.value != null ? 'Hesaplandı · eşik değerlendirmesi bekliyor' : ratio?.reason || 'Tanım incelemesi gerekiyor';
  };
  const filtered = useMemo(() => source.items.filter(x => (kind === 'all' || x.kind === kind) && norm(`${x.title} ${x.text} ${x.section} ${x.note ?? ''}`).includes(norm(search))), [search, kind, source]);
  const item = source.items.find(x => x.id === selected);
  const findings = data?.checks.filter(c => c.status === 'finding') ?? [];
  const accounts = data?.accounts.filter(a => (!onlyFindings || a.unexpectedSign) && norm(`${a.code} ${a.name}`).includes(norm(search))) ?? [];
  const openAccount = (a: Account) => { setAccount(a); setPage(0); };
  const tabs = [['overview', 'Denetim özeti'], ['catalog', 'Kontrol kütüphanesi'], ['ledger', 'Logo kayıtları'], ['source', 'Kaynak belge']];

  return <Shell head={{ tenant: 'Timaş Yayınları', section: 'Finans & Risk', crumb: 'Finansal Denetim', source: 'Logo · muhasebe', presence: data ? `Veri: ${day(data.lastDate)}` : 'Veri bekleniyor' }} rail={railFor('/finansal-denetim')}>
    <main className="audit-main">
      <ZoomStage><div className="audit-page">
        <header className="audit-heading">
          <div><div className="audit-eyebrow">FİNANS & RİSK / DENETİM MASASI</div><h1>Rakamların arkasını görün<span>.</span></h1><p>Finansal Denetim · Genel görünümden hesaplamaya, hesaplamadan Logo kaydına.</p></div>
          <button className="audit-button" disabled={!data} onClick={() => download('finansal-denetim-2026.json', { ...data, sourceHash: source.sha256, sourceCoverage: 'Taslak; tüm maddeler uygulanmadı', exportedAt: new Date().toISOString() })}><ArrowDownToLine size={16} /> Raporu indir</button>
        </header>

        <section className="audit-hero">
          <div className="audit-hero-copy"><div className="audit-chip"><ShieldCheck size={14} /> KAYNAĞINA KADAR İZLENEBİLİR</div><h2>Her bulgunun<br /><em>bir dayanağı var.</em></h2><p>Ne kontrol edildi, nasıl hesaplandı, hangi kayıt etkili? Finans ekibiniz için tek bir çalışma alanı.</p><div className="audit-hero-meta"><span>2026 işlem dönemi</span><span>TRY / Türk lirası</span><span>Salt okunur</span></div></div>
          <div className="audit-orbit" aria-label="Denetim kapsamı"><div className="audit-orbit-core"><ShieldCheck size={30} /><strong>{data ? data.checks.length : '—'}</strong><span>otomatik kontrol</span></div><span className="audit-orbit-label">LOGO → HESAPLAMA → BULGU</span></div>
          <div className="audit-hero-side"><span className="audit-eyebrow">VERİNİN ZAMANI</span><strong>{day(data?.lastDate)}</strong><p>{data ? `${number.format(data.lineCount)} hareket · ${number.format(data.accounts.length)} hesap` : overview.isFetching ? 'Logo muhasebe kayıtları okunuyor…' : 'Logo verisi henüz okunamadı.'}</p><span className="audit-source-pill">2026 yedeği · canlı dönem değildir</span></div>
        </section>

        {overview.isFetching && <div className="audit-message" role="status"><Loader2 size={16} className="animate-spin" /> Gerçek Logo kaynağı okunuyor; sonuç hazır olunca burada görünecek.</div>}
        {(overview.error || !ENGINE_ENABLED) && <div className="audit-message audit-warning" role="alert">{overview.error instanceof Error ? overview.error.message : 'Logo bağlantısı tanımlı değil.'} <strong>DOĞRULANAMADI</strong><button className="audit-button" onClick={() => overview.refetch()}>Tekrar dene</button></div>}
        {catalog.isFetching && <div className="audit-message" role="status">Kaynak belge ve kontrol kütüphanesi yükleniyor…</div>}
        {catalog.error && <div className="audit-message audit-warning" role="alert">Kaynak belge okunamadı. <button className="audit-button" onClick={() => catalog.refetch()}>Kaynağı tekrar yükle</button></div>}

        <nav className="audit-tabs" aria-label="Denetim bölümleri">{tabs.map(([id, title]) => <button key={id} aria-current={tab === id ? 'page' : undefined} onClick={() => { setTab(id); setSearch(''); }}>{title}{id === 'catalog' && <span>{source.items.length}</span>}</button>)}</nav>

        {tab === 'overview' && <>
          <div className="audit-stats">
            <article><span>İnceleme gerektiren</span><strong className="audit-coral">{data ? findings.length : '—'}</strong><small>Bulgu üreten kontrol türü</small></article>
            <article><span>Kontrol geçti</span><strong className="audit-green">{data ? data.checks.filter(c => c.status === 'passed').length : '—'}</strong><small>Yalnız çalıştırılan kurallar içinde</small></article>
            <article><span>Hesaplanan oran</span><strong>{data ? data.ratios.filter(r => r.value !== null).length : '—'}</strong><small>Ham mizan · eşik hükmü verilmez</small></article>
            <article><span>Kaynak kapsamı</span><strong>{source.pageCount}<small> sayfa</small></strong><small>Kontrol çıkarımı taslak; kapsam onayı bekliyor</small></article>
          </div>
          <div className="audit-columns">
            <section className="audit-panel"><div className="audit-section-head"><div><span className="audit-eyebrow">ÖNCE ÖNEMLİ OLAN</span><h2>Kontrol sonuçları</h2></div><span className="audit-badge">Logo muhasebe</span></div>
              {!data && <p className="audit-empty">Sonuçlar için gerçek Logo verisinin okunması gerekiyor. Kontrol kütüphanesini inceleyebilirsiniz.</p>}
              {data?.checks.map(c => <details className="audit-check" key={c.id}><summary><span className={`audit-status-icon ${c.status}`} >{c.status === 'passed' ? <Check size={17} /> : <FileSearch size={17} />}</span><span className="audit-check-title"><strong>{c.title}</strong><small>{c.status === 'finding' ? `${number.format(c.affected)} kayıt/hesap inceleme adayı` : c.status === 'passed' ? 'Kontrol geçti' : 'Doğrulanamadı'}</small></span><ChevronRight size={16} /></summary><div className="audit-check-body"><p>{c.formula}</p>{c.amount !== null && <p><b>Kontrol tutarı:</b> {money(c.amount)} <small>(tahmini kayıp veya vergi cezası değildir)</small></p>}<p>{c.origin}</p><button className="audit-button" onClick={() => { setOnlyFindings(c.id === 'account-sign'); setTab('ledger'); setSearch(''); }}>Hesapları incele <ArrowRight size={14} /></button></div></details>)}
            </section>
            <aside className="audit-panel audit-insight"><span className="audit-eyebrow">DENETİMİN SINIRLARI</span><CircleHelp size={26} /><h2>Eksik kanıt,<br />olumlu sonuç değildir.</h2><p>Belgedeki vergi kuralları 2020 tarihli. Belge doğruluğu, fiili sayım, beyanname ve dış mutabakat gerektiren maddeler ayrıca incelenmeli.</p><ul><li>Vergisel eşikler dönemine göre doğrulanmalı.</li><li>Kaynak formüllerindeki çelişkiler çözülmeli.</li><li>Çalıştırılmayan maddeler “geçti” sayılmaz.</li></ul><button className="audit-button" onClick={() => setTab('catalog')}>Kontrol kütüphanesine git <ArrowRight size={14} /></button></aside>
          </div>
          <section className="audit-panel"><div className="audit-section-head"><div><span className="audit-eyebrow">MALİ GÖRÜNÜM</span><h2>Rasyolar · hesaplama açık</h2></div><span className="audit-badge">Sektörel değerlendirme bekliyor</span></div><div className="audit-ratios">{data?.ratios.map(r => <details key={r.note}><summary><span>{r.title}</span><strong>{r.value === null ? '—' : number.format(Number(r.value))}<small> ×</small></strong></summary><p>{r.formula}</p><p>{money(r.numerator)} / {money(r.denominator)}</p><p>{r.value === null ? (r.reason || 'Payda sıfır/negatif veya veri eksik; hesaplanamadı.') : 'Net hesap bakiyelerinden; kesin mali tablo görüşü değildir.'}</p><button onClick={() => { const found = source.items.find(x => x.note === r.note); setSelected(found?.id ?? null); setTab('catalog'); }} className="audit-text-button">Kaynak tanımını gör →</button></details>)}</div></section>
          <details className="audit-panel"><summary>Hesaplama kapsamı ve teknik iz</summary>{data?.limitations.map(x => <p key={x}>{x}</p>)}<p>Son okuma: {data?.computedAt ? new Date(data.computedAt).toLocaleString('tr-TR') : '—'}. Sorgu süresi: {data ? `${data.dbMs} ms` : '—'}.</p><pre>{data?.sql.join('\n\n')}</pre></details>
        </>}

        {tab === 'catalog' && <>
          <div className="audit-message audit-warning"><BookOpen size={18} /><span><b>{source.items.length} kaynak maddesi çıkarıldı.</b> Numarasız açıklamalar kaynak belge sekmesinde korunuyor. Bu liste taslaktır; tüm kontrol maddelerinin eksiksiz ayrıştırıldığı veya uygulandığı henüz doğrulanmadı.</span></div>
          <div className="audit-toolbar"><label className="audit-search"><Search size={17} /><input aria-label="Kontrol ara" value={search} placeholder="Hesap, kontrol veya kaynak metninde ara…" onChange={e => { setSearch(e.target.value); setCatalogPage(0); }} /></label><select aria-label="Kontrol türü" value={kind} onChange={e => { setKind(e.target.value); setCatalogPage(0); }}><option value="all">Tüm kaynak maddeleri</option><option value="analysis">Mali analiz</option><option value="control">Denetim kuralları</option><option value="checklist">İnceleme listeleri</option></select><button className="audit-button" onClick={() => download('finansal-denetim-kontrol-katalogu.json', source)}>Kataloğu indir <ArrowDownToLine size={15} /></button></div>
          <div className="audit-catalog-layout"><section className="audit-panel"><div className="audit-section-head"><h2>Kontrol kütüphanesi</h2><span>{filtered.length} madde</span></div>{filtered.slice(catalogPage*20, (catalogPage+1)*20).map(x => <button className={`audit-catalog-item ${selected === x.id ? 'selected' : ''}`} key={x.id} onClick={() => setSelected(x.id)}><span className="audit-eyebrow">{x.kind === 'analysis' ? 'MALİ ANALİZ' : x.kind === 'control' ? 'DENETİM KURALI' : 'İNCELEME MADDESİ'} · s. {x.page}</span><strong>{x.title || x.section}</strong><span>{x.note ? `Kaynak notu ${x.note}` : x.section} · {catalogStatus(x.note)}</span></button>)}{!filtered.length && <p>Aramanızla eşleşen madde yok.</p>}<div className="audit-pagination"><button aria-label="Önceki maddeler" disabled={catalogPage === 0} onClick={() => setCatalogPage(p => p-1)}><ChevronLeft size={18} /></button><span>{catalogPage+1} / {Math.max(1, Math.ceil(filtered.length/20))}</span><button aria-label="Sonraki maddeler" disabled={(catalogPage+1)*20 >= filtered.length} onClick={() => setCatalogPage(p => p+1)}><ChevronRight size={18} /></button></div></section>
            <aside id="audit-source-detail" className="audit-panel audit-source-detail">{item ? <><span className="audit-eyebrow">KAYNAK DETAYI · s. {item.page}–{item.endPage}</span><h2>{item.section}</h2><span className="audit-badge">{catalogStatus(item.note)}</span><p className="audit-source-text">{item.text}</p><button className="audit-button" onClick={() => { setSourcePage(item.page); setTab('source'); }}>Sayfanın tamamını oku <ArrowRight size={14} /></button></> : <div className="audit-empty"><FileSearch size={30} /><h2>Bir kontrol seçin</h2><p>Özgün metin, kaynak sayfa ve uygulama durumu burada görünür.</p></div>}</aside></div>
        </>}

        {tab === 'ledger' && <>
          <div className="audit-toolbar"><label className="audit-search"><Search size={17} /><input aria-label="Logo hesabı ara" value={search} onChange={e => setSearch(e.target.value)} placeholder="Hesap kodu veya adı…" /></label><label className="audit-toggle"><input type="checkbox" checked={onlyFindings} onChange={e => setOnlyFindings(e.target.checked)} /> Yalnız ters bakiyeler</label></div>
          <section className="audit-panel"><div className="audit-section-head"><h2>Logo hesapları</h2><span>{accounts.length} hesap</span></div><div className="audit-table-scroll"><table><thead><tr><th>Hesap</th><th>Borç</th><th>Alacak</th><th>Net bakiye</th><th>Hareket</th></tr></thead><tbody>{accounts.map(a => <tr key={a.accountRef}><td><button className="audit-account" onClick={() => openAccount(a)}><b>{a.code} · {a.name}</b>{a.unexpectedSign && <span>Hesap karakterine ters bakiye</span>}</button></td><td>{money(a.debit)}</td><td>{money(a.credit)}</td><td>{money(a.balance)}</td><td><button className="audit-text-button" onClick={() => openAccount(a)}>{number.format(a.lineCount)} satır →</button></td></tr>)}</tbody></table></div>{!accounts.length && <p className="audit-empty">{data ? 'Bu filtrede hesap bulunamadı.' : 'Hesapları göstermek için Logo verisi okunmalı.'}</p>}</section>
          {account && <section id="audit-logo-detail" className="audit-panel" aria-live="polite"><div className="audit-section-head"><div><span className="audit-eyebrow">LOGO HAREKET DETAYI</span><h2>{account.code} · {account.name}</h2></div><button className="audit-button" onClick={() => setAccount(null)}>Kapat</button></div><p>Bu detay ayrı bir kaynak okumasıdır. Fiş ve satır kimlikleri Logo kaydını bulmanız içindir.</p>{detail.isFetching && <p>Hareketler okunuyor…</p>}{detail.error && <p role="alert">{detail.error instanceof Error ? detail.error.message : 'Detay okunamadı.'}</p>}<div className="audit-table-scroll"><table><thead><tr><th>Tarih / fiş</th><th>Belge</th><th>Açıklama</th><th>Borç</th><th>Alacak</th><th>Kaynak kimliği</th></tr></thead><tbody>{detail.data?.items.map(l => <tr key={l.lineRef}><td>{day(l.date)}<br /><b>{l.slipNo}</b></td><td>{l.documentNo || '—'}</td><td>{l.description || '—'}</td><td>{money(l.debit)}</td><td>{money(l.credit)}</td><td>Fiş {l.slipRef}<br />Satır {l.lineRef}</td></tr>)}</tbody></table></div><div className="audit-pagination"><button aria-label="Önceki hareketler" disabled={!page || detail.isFetching} onClick={() => setPage(p => p-1)}><ChevronLeft size={18} /></button><span>{detail.data?.total ?? '—'} hareket · Sayfa {page+1}</span><button aria-label="Sonraki hareketler" disabled={!detail.data || (page+1)*50 >= detail.data.total || detail.isFetching} onClick={() => setPage(p => p+1)}><ChevronRight size={18} /></button></div></section>}
        </>}

        {tab === 'source' && <section className="audit-panel"><div className="audit-section-head"><div><span className="audit-eyebrow">12 HAZİRAN 2020 · {source.pageCount} SAYFA</span><h2>{source.title}</h2></div><label>Sayfa <input className="audit-page-input" type="number" min={1} max={source.pageCount} value={sourcePage} onChange={e => setSourcePage(Math.max(1, Math.min(source.pageCount, Number(e.target.value) || 1)))} /></label></div><div className="audit-message audit-warning">Kaynak numaralandırması: 88 numaralı not yok; 115 üç kez, 143 ve 160 ikişer kez kullanılmış. Formüller ve mevzuat ifadeleri özgün belge metnidir; doğrulanmış güncel kural sayılmaz.</div><pre className="audit-original">{source.pages[sourcePage-1]?.text}</pre><div className="audit-pagination"><button disabled={sourcePage === 1} onClick={() => setSourcePage(p => p-1)} aria-label="Önceki kaynak sayfa"><ChevronLeft size={18} /></button><span>{sourcePage} / {source.pageCount}</span><button disabled={sourcePage === source.pageCount} onClick={() => setSourcePage(p => p+1)} aria-label="Sonraki kaynak sayfa"><ChevronRight size={18} /></button></div></section>}
        <footer className="audit-footer"><span><ShieldCheck size={14} /> Logo kaynağına yazılmaz.</span><span>Kaynak → kontrol → hesaplama → kayıt</span></footer>
      </div></ZoomStage>
    </main>
  </Shell>;
}
