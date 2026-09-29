import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ArrowRight, Check, ChevronLeft, ChevronRight, Database, FileSearch, CircleHelp } from 'lucide-react';

import SqlEvidence from './SqlEvidence';
import FindingReason from './FindingReason';
import { findingSummary, rowExplanation } from './findings';
import { accountingText, checkExplanations } from './presentation';
import { ExceptionClusters, ExplainFinding } from './AuditAssist';
import SqlInfo, { InfoLabel } from '../components/SqlInfo';
import type { Kaynaklar } from '../components/sqlInfo';
import ColName from '../components/ColName';
import { readableName } from '../components/readableName';

export type DeepCheck = { sqlResultColumns?: {tested: string; affected: string}; sql?: string; id: string; title: string; status: string; affected: number | null; tested: number | null; formula: string; limitation: string };
export type DeepAudit = {
  asOf: string; revision: string; status: string; checks: DeepCheck[];
  sources: Array<{ id: string; title: string; status: string; records: number | null; found: string; missing: string; why: string; nextStep: string }>;
  datasets: Record<string, Array<Record<string, string | number | null>>>;
  errors: Record<string, string>; limitations: string[];
};
type Exceptions = { kaynaklar?: Kaynaklar; sql?: string; items: Array<Record<string, string | number | null>>; total: number; page: number; readAt: string; asOf: string; separateRead: boolean };
const number = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 2 });
const labels: Record<string, string> = {
  sourceRef: 'Kaynak kaydı', documentNo: 'Belge / fiş', date: 'İşlem tarihi', clientRef: 'Cari kartı', transactionType: 'İşlem türü',
  accountRef: 'Muhasebe hesabı kimliği', accountCode: 'Muhasebe hesabı', slipRef: 'Muhasebe fişi', posted: 'Aktarım işareti',
  amount: 'Kaynak tutarı', vat: 'KDV', foundSlip: 'Bulunan fiş', cancelledSlip: 'Fiş iptal işareti', ledgerDate: 'Muhasebe tarihi',
  expected: 'Alt modül toplamı', actual: 'Muhasebe / karşı kaynak toplamı', difference: 'Fark', invoiceCount: 'Fatura sayısı',
  sourceCount: 'Kaynak hareketi', lineCount: 'Satır sayısı', firstDate: 'İlk tarih', lastDate: 'Son tarih', slipNo: 'Fiş numarası',
  direction: 'Borç / alacak kodu', bankAccountRef: 'Banka hesabı kimliği', directLineRef: 'Doğrudan satır kimliği', foundLine: 'Bulunan satır',
  cancelledLine: 'Satır iptal işareti', foundAccount: 'Bulunan hesap', currency: 'Para birimi kodu', balance: 'Gün sonu bakiye',
  type: 'Kaynak türü kodu', rows: 'Kayıt sayısı', unposted: 'Aktarılmamış', year: 'Yıl', month: 'Ay', bankLinked: 'Bankaya bağlı',
  missingCredit: 'Kredi kartı eksik', principal: 'Kaynak plan tutarı', interest: 'Kaynak faiz tutarı', documentType: 'Belge türü kodu',
  state: 'Kayıtlı durum kodu', dueByCutoff: 'Kesim tarihine kadar vadesi gelen', afterCutoff: 'Kesimden ileri tarihli', journalCount: 'Yevmiye sayısı',
  missingCustomsNumber: 'Gümrük no eksik', missingCustomsDate: 'Gümrük tarihi eksik', withPayload: 'İçeriği olan',
  addressNotes: 'Adres notu başlangıcı', pdfSignatures: 'PDF başlangıcı', xmlSignatures: 'XML başlangıcı',
};
const datasetTitles: Record<string,string> = { invoiceTypes: 'Fatura türleri ve aktarım durumu', taxPeriods: 'Bulunan beyannamelerin dönemleri',
  loanSchedule: 'Kredi planı ve ödeme satırları · para birimleri ayrı', chequeStates: 'Çek/senet son durum ve vade profili',
  stockSlips: 'Stok fişleri · ileri tarihler ayrı', ebookPeriods: 'Kayıtlı e-defter dönemleri', exportDocuments: 'Dış ticaret belge kapsamı',
  attachments: 'Belge deposu · içerik başlangıçları' };
const numericAmounts = new Set(['amount','vat','expected','actual','difference','balance','principal','interest']);
function value(key: string, v: string | number | null) {
  if (v == null) return '—';
  if (/Date$|^date$/.test(key) && /^\d{4}-\d{2}-\d{2}/.test(String(v))) return new Date(String(v)).toLocaleDateString('tr-TR');
  if (numericAmounts.has(key)) return number.format(Number(v));
  return String(v);
}
function Rows({ rows, checkId, k, alan }: { rows: Array<Record<string, string | number | null>>; checkId?: string; k?: Kaynaklar; alan?: string }) {
  const columns = rows.length ? Object.keys(rows[0]).filter(k => k !== 'totalRows' && k !== 'sourceModule') : [];
  return <div className="audit-table-scroll"><table><thead><tr>{checkId && <th>Bulgu açıklaması</th>}{columns.map((c, i) => <th key={c}>{i === 0 && alan ? <InfoLabel k={k} alan={alan} label="Kaynak kayıtları">{labels[c] ?? readableName(c)}</InfoLabel> : labels[c] ?? <ColName name={c} />}</th>)}</tr></thead><tbody>{rows.map((r,i) => <tr key={i}>{checkId && <td className="audit-reason-cell"><FindingReason explanation={rowExplanation(checkId,r)} /></td>}{columns.map(c => <td key={c}>{value(c,r[c])}</td>)}</tr>)}</tbody></table></div>;
}

export default function DeepAuditPanel({ data, runId, load, canDetail = true, k }: { data?: DeepAudit; runId?: string; load: <T>(path: string) => Promise<T>; /** «Denetim ayrıntısı» rolde yoksa istisna satırları açılmaz. */ canDetail?: boolean; /** Raporun sorgu bilgisi. */ k?: Kaynaklar }) {
  const [selected, setSelected] = useState('');
  const [page, setPage] = useState(0);
  const details = useQuery({ queryKey: ['audit-exceptions',runId,selected,page],
    queryFn: () => load<Exceptions>(`runs/${runId}/exceptions/${selected}?page=${page}`),
    enabled: !!runId && !!selected, retry: false });
  useEffect(() => { if (selected) document.getElementById('audit-exceptions')?.scrollIntoView({ block: 'start', behavior: 'smooth' }); }, [selected]);
  const check=data?.checks.find(c => c.id===selected);
  if (!data) return <section className="audit-panel"><h2>Bu raporda derin kaynak taraması yok</h2><p>Eski raporlar sonradan değiştirilmez. Yeni karşılaştırmaları görmek için çalışma raporundan “Son tamamlanan rapor”u seçin.</p></section>;
  return <>
    <section className="audit-discovery-hero">
      <div><span className="audit-eyebrow">VERİNİN GÜCÜ, KANITIN SINIRI</span><h2>Logo’da bulunanları çalıştırıyoruz.<br /><em>Eksik dayanağı görünür kılıyoruz.</em></h2>
      <p>Bir kayıt bulunması, kontrolün tamamlandığı anlamına gelmez. Her alanda ne bulunduğunu, hangi karşılaştırmanın çalıştığını ve neyin eksik kaldığını görebilirsiniz.</p></div>
      <div className="audit-discovery-counts"><strong>{data.checks.length}</strong><span>ek veri kontrolü <SqlInfo k={k} alan="deepAudit.checks[]" label="Ek veri kontrolleri" /></span><strong>{data.sources.length}</strong><span>kaynak alanı incelendi <SqlInfo k={k} alan="deepAudit.sources[]" label="İncelenen kaynak alanları" /></span></div>
    </section>
    {!!Object.keys(data.errors).length && <div className="audit-message audit-warning" role="alert">Bazı kaynak sorguları tamamlanamadı. Bu alanlar “okunamadı” olarak işaretlendi; kayıt yok veya kontrol geçti sayılmadı.</div>}
    <section className="audit-panel"><div className="audit-section-head"><div><span className="audit-eyebrow">AYNI OLAY, İKİ KAYNAK</span><h2>Logo içi karşılaştırmalar</h2></div><span className="audit-badge">Kesim: {new Date(data.asOf).toLocaleDateString('tr-TR')}</span></div>
      <div className="audit-deep-checks">{data.checks.map(c => <article key={c.id} className={`audit-deep-check ${c.status}`}>
        <span className={`audit-status-icon ${c.status}`}>{c.status==='passed' ? <Check size={17}/> : <FileSearch size={17}/>}</span>
        <div><h3>{c.title}</h3><p>{c.tested == null ? 'Kaynak okunamadı' : `${number.format(c.tested)} kayıt / grup değerlendirildi`} <SqlInfo k={k} alan="deepAudit.checks[]" row={c.id} label={c.title} /></p>
          {c.status === 'finding' && <FindingReason explanation={findingSummary(c)} />}{c.status === 'finding' && runId && <ExplainFinding runId={runId} checkId={c.id} />}<details><summary>Nasıl kontrol ediliyor?</summary><p>{checkExplanations[c.id] ?? accountingText(c.formula)}</p><p>{accountingText(c.limitation)}</p></details><SqlEvidence sql={c.sql} description={`Rapor hazırlanırken çalıştırılan sorgudur. İncelenen kayıt sayısı: ${c.sqlResultColumns?.tested ?? 'rows'}; bu kontrolün bulgu sayısı: ${c.sqlResultColumns?.affected ?? 'eski raporda belirtilmemiş'}. Aynı sorgu birden fazla kontrolü hesaplayabilir.`} title="Kontrolün SQL sorgusu" /></div>
        <button className="audit-button" disabled={!canDetail || c.affected == null || c.status==='unverified'} onClick={() => {setSelected(c.id);setPage(0);}}>
          {c.affected == null || c.status==='unverified' ? 'Doğrulanamadı' : c.affected ? `${number.format(c.affected)} inceleme adayı` : 'Fark bulunmadı'} <ArrowRight size={14}/>
        </button>
      </article>)}</div>
    </section>
    {check && <section id="audit-exceptions" className="audit-panel audit-exceptions" aria-live="polite"><div className="audit-section-head"><h2>{check.title}</h2><button className="audit-button" onClick={() => setSelected('')}>Detayı kapat</button></div>
      <p>{checkExplanations[check.id] ?? accountingText(check.formula)}</p><p>Detay aynı dönem sınırıyla ayrı bir kaynak okumasıdır. Tutarlar aksi belirtilmedikçe TL’dir; farklar toplanmış zarar veya ceza değildir.</p>
      {runId && canDetail && <ExceptionClusters key={check.id} runId={runId} checkId={check.id} />}
      {details.isFetching && <p role="status">Kaynak kayıtları okunuyor…</p>}{details.error && <p role="alert">{details.error instanceof Error ? details.error.message : 'Kayıtlar okunamadı.'}</p>}
      {details.data && <SqlEvidence sql={details.data.sql} description={`Aşağıdaki ${details.data.items.length} kaydı getiren, çalıştırılmış sorgudur. Sayfa ${page+1}; toplam ${details.data.total} bulgu. Raporun hesaplama anından ayrı bir okumadır.`} />}
      {details.data && (details.data.items.length ? <Rows rows={details.data.items} checkId={check.id} k={details.data.kaynaklar} alan="items[]" /> : <p>Bu sayfada inceleme adayı bulunmadı.</p>)}
      <div className="audit-pagination"><button aria-label="Önceki bulgular" disabled={!page || details.isFetching} onClick={() => setPage(p => p-1)}><ChevronLeft size={18}/></button><span>{details.data?.total ?? '—'} kayıt · Sayfa {page+1} <SqlInfo k={details.data?.kaynaklar} alan="total" label="Bulgu sayısı" /></span><button aria-label="Sonraki bulgular" disabled={!details.data || details.isFetching || (page+1)*50>=details.data.total} onClick={() => setPage(p=>p+1)}><ChevronRight size={18}/></button></div>
    </section>}
    <section><div className="audit-section-head"><div><span className="audit-eyebrow">NE VAR, NE EKSİK?</span><h2>Kontrolü tamamlamak için gerekenler</h2></div></div>
      <div className="audit-source-cards">{data.sources.map(s => <article key={s.id} className={`audit-source-card ${s.status}`}>
        <div className="audit-source-card-head"><Database size={20}/><span>{s.status==='unavailable' ? 'Kaynak okunamadı' : s.status==='missing' ? 'Bu dönem için bulunamadı' : 'Logo kaydı bulundu'}</span></div>
        <h3>{s.title}</h3><div className="audit-source-count">{s.records == null ? '—' : number.format(s.records)}<small> kayıt</small> <SqlInfo k={k} alan="deepAudit.sources[]" row={s.id} label={s.title} /></div><p>{accountingText(s.found)}</p>
        <div className="audit-evidence-gap"><CircleHelp size={17}/><div><b>Eksik dayanak</b><p>{accountingText(s.missing)}</p></div></div>
        <details><summary>Neden önemli?</summary><p>{accountingText(s.why)}</p></details><div className="audit-source-next"><b>Tamamlamak için</b><p>{accountingText(s.nextStep)}</p></div>
      </article>)}</div>
    </section>
    <section className="audit-panel"><h2>Bulunan kayıtların kapsamı</h2><p>Kodlar kaynakta saklanan değerlerdir; doğrulanmamış kodlar iş durumuna çevrilmez. Plan/ödeme, para birimi ve dönemler birbirine eklenmez.</p>
      {Object.entries(datasetTitles).map(([key,title]) => <details className="audit-dataset" key={key}><summary>{title}</summary>{data.datasets[key]?.length ? <Rows rows={data.datasets[key]} k={k} alan={`deepAudit.datasets.${key}`} /> : <p>{data.errors[key] ?? 'Bu kapsamda kayıt bulunmadı.'}</p>}</details>)}
      {data.limitations.map(l => <p key={l}>{accountingText(l)}</p>)}
    </section>
  </>;
}
