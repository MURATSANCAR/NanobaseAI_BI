import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Download } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import SqlInfo from '../components/SqlInfo';
import { Explain } from '../components/Explain';
import { Note, Pill, TableWrap, btnGhost, errText, field, label as labelCls, td, th } from '../admin/ui';
import { KpiRow, Kpi, Panel } from '../editorial/kit';
import { STAGE_TONE, fmtDay, fmtInt, fmtMoney, inflApi, today, type Agg, type Meta, type Report } from './api';
import { InflFrame, useMeta } from './parts';

/** Kampanya ve kişi raporu: dönemdeki işbirlikleri, erişim, etkileşim; ücret yetkisi olana harcama ve etkileşim başı
 *  maliyet (CPE). CRM pazarlama bütçe modülündeki «Influencer» kayıtları ayrı satırdır, portal kayıtlarıyla toplanmaz. */
export default function CollabReport() {
  const meta = useMeta();
  const [params, setParams] = useSearchParams();
  const t = today();
  const frm = params.get('bas') ?? `${t.slice(0, 8)}01`;
  const to = params.get('bit') ?? t;
  const set = (k: string, v: string) => {
    const p = new URLSearchParams(params);
    if (v) p.set(k, v);
    else p.delete(k);
    setParams(p, { replace: true });
  };
  const q = useQuery({ queryKey: ['influencers', 'report', frm, to], queryFn: () => inflApi.report(frm, to), enabled: ENGINE_ENABLED && !!frm && !!to });
  const [by, setBy] = useState<'people' | 'books'>('people');
  const m = meta.data;
  const r = q.data;
  return (
    <InflFrame
      title="İşbirliği raporu"
      lead="Seçilen dönemdeki işbirliklerinin sonucu: kaç paylaşım yapıldı, ne kadar ilgi gördü, ne kadar harcandı. Bir iş, yayın gününe (yoksa planlanan yayın ya da kayıt gününe) göre döneme girer; vazgeçilen işler sayılmaz."
      aside={m?.me.canExport ? <a href={inflApi.reportUrl(frm, to)} className={btnGhost}><Download aria-hidden className="h-4 w-4" /> Excel indir</a> : undefined}
    >
      <Panel>
        <div className="grid grid-cols-2 gap-2 sm:w-[420px]">
          <label className="flex flex-col gap-1"><span className={labelCls}>Başlangıç</span><input type="date" className={field} value={frm} onChange={(e) => set('bas', e.target.value)} /></label>
          <label className="flex flex-col gap-1"><span className={labelCls}>Bitiş</span><input type="date" className={field} value={to} onChange={(e) => set('bit', e.target.value)} /></label>
        </div>
      </Panel>
      {q.error && <Note tone="err">{errText(q.error, 'Rapor okunamadı.')}</Note>}
      {q.isLoading && <Panel><div className="py-8 text-center text-[12px] text-canvas-muted">Yükleniyor…</div></Panel>}
      {r && m && (
        <>
          <KpiRow>
            <Kpi label="İşbirliği" value={fmtInt(r.total.collabs)} help={`${r.total.published} yayında`} info={<SqlInfo k={r.kaynaklar} alan="total" label="İşbirliği" />} />
            <Kpi label="Etkileşim" value={fmtInt(r.total.engagement)} help={`erişim ${fmtInt(r.total.reach)}`} info={<SqlInfo k={r.kaynaklar} alan="total" label="Etkileşim" />}
              explain="Paylaşımların aldığı beğeni, yorum, paylaşım ve kaydetme toplamı; işbirliği kartına girilen sayılardan gelir. Alt satırdaki erişim, paylaşımı gören kişi sayısıdır." />
            <Kpi label="Harcama" value={r.total.spend !== null ? fmtMoney(r.total.spend) : '—'} help={r.total.spend !== null ? 'KDV hariç ücret toplamı' : 'ücretler yetkiyle görünür'} info={<SqlInfo k={r.kaynaklar} alan="total" label="Harcama" />} />
            <Kpi label="Etkileşim başı maliyet" value={r.total.cpe !== null ? fmtMoney(r.total.cpe) : '—'} help={r.total.disclosureMissing ? `${r.total.disclosureMissing} yayında yasal etiket işaretlenmedi` : 'yasal etiket eksiği yok'} info={<SqlInfo k={r.kaynaklar} alan="total" label="Etkileşim başı maliyet" />}
              explain="Harcamanın etkileşime bölümü: bir beğeni, yorum ya da paylaşım için ortalama kaç lira ödendiği. Düşük olması daha verimli demektir. Tabloda «EBM» diye kısaltılır." />
          </KpiRow>
          <CrmSpend r={r} />
          <Panel>
            <div className="mb-2 flex items-center gap-1">
              <SqlInfo k={r.kaynaklar} alan={by} label={by === 'people' ? 'Kişi bazında' : 'Kitap bazında'} />
              {(['people', 'books'] as const).map((k) => (
                <button key={k} type="button" aria-pressed={by === k} onClick={() => setBy(k)}
                  className={`min-h-10 rounded-xl px-3 text-[12.5px] font-extrabold sm:min-h-8 ${by === k ? 'bg-canvas-violet text-white' : 'bg-slate-100'}`}>
                  {k === 'people' ? 'Kişi bazında' : 'Kitap bazında'}
                </button>
              ))}
            </div>
            <AggTable rows={by === 'people' ? r.people.map((x) => ({ key: x.personId, name: x.name, link: `/isbirlikleri/kisi/${x.personId}`, a: x }))
              : r.books.map((x) => ({ key: x.crmBookId ?? x.bookTitle ?? '', name: x.bookTitle ?? 'Kitap', link: x.crmBookId ? `/isbirlikleri/aday/${x.crmBookId}` : null, a: x }))}
              fee={m.me.canSeeFee} />
          </Panel>
          <Panel>
            <h2 className="mb-2 flex items-center gap-1 text-[13px] font-extrabold">İşbirlikleri<SqlInfo k={r.kaynaklar} alan="items" label="İşbirlikleri" /></h2>
            <Items r={r} meta={m} />
          </Panel>
        </>
      )}
    </InflFrame>
  );
}

function CrmSpend({ r }: { r: Report }) {
  if (r.crm === null) return null;
  if ('hata' in r.crm) return <Note tone="warn">CRM pazarlama bütçe modülü okunamadı: {r.crm.hata}</Note>;
  return (
    <Note tone="info">
      <SqlInfo k={r.kaynaklar} alan="crm" label="CRM influencer harcaması" /> CRM pazarlama bütçe modülünde bu dönemde «Influencer» mecrasına {r.crm.kayit} kayıt, toplam {fmtMoney(r.crm.toplam)} var. Ayrı kaynaktır; aynı iş iki yerde kayıtlı olabileceği için portal harcamasıyla toplanmaz.
    </Note>
  );
}

function AggTable({ rows, fee }: { rows: Array<{ key: string; name: string; link: string | null; a: Agg }>; fee: boolean }) {
  if (!rows.length) return <div className="py-6 text-center text-[12.5px] text-canvas-muted">Bu dönemde kayıt yok.</div>;
  return (
    <TableWrap>
      <table className="w-full min-w-[620px] text-[12.5px]">
        <thead><tr><th className={th}>Ad</th><th className={th}>İşbirliği</th><th className={th}>Yayında</th><th className={th}>Erişim</th><th className={th}>Etkileşim</th>{fee && <th className={th}>Harcama</th>}{fee && <th className={th}><span className="inline-flex items-center gap-1">EBM<Explain label="EBM" title="Etkileşim başı maliyet">Harcamanın etkileşime bölümü: bir etkileşim için ortalama kaç lira ödendiği.</Explain></span></th>}</tr></thead>
        <tbody>
          {rows.map((x) => (
            <tr key={x.key} className="border-t border-slate-100">
              <td className={td}>{x.link ? <Link to={x.link} className="font-bold hover:underline">{x.name}</Link> : x.name}</td>
              <td className={`${td} font-mono tabular-nums`}>{x.a.collabs}</td>
              <td className={`${td} font-mono tabular-nums`}>{x.a.published}</td>
              <td className={`${td} font-mono tabular-nums`}>{fmtInt(x.a.reach)}</td>
              <td className={`${td} font-mono tabular-nums`}>{fmtInt(x.a.engagement)}</td>
              {fee && <td className={`${td} font-mono tabular-nums`}>{fmtMoney(x.a.spend)}</td>}
              {fee && <td className={`${td} font-mono tabular-nums`}>{fmtMoney(x.a.cpe)}</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </TableWrap>
  );
}

function Items({ r, meta }: { r: Report; meta: Meta }) {
  if (!r.items.length) return <div className="py-6 text-center text-[12.5px] text-canvas-muted">Bu dönemde işbirliği yok. Dönemi genişletmeyi deneyin.</div>;
  return (
    <TableWrap>
      <table className="w-full min-w-[760px] text-[12.5px]">
        <thead><tr><th className={th}>Gün</th><th className={th}>No</th><th className={th}>Kişi</th><th className={th}>Kitap</th><th className={th}>Aşama</th><th className={th}>Yasal etiket</th><th className={th}>Etkileşim</th>{meta.me.canSeeFee && <th className={th}>Ücret</th>}</tr></thead>
        <tbody>
          {r.items.map((c) => (
            <tr key={c.id} className="border-t border-slate-100">
              <td className={`${td} font-mono`}>{fmtDay(c.periodDay)}</td>
              <td className={td}><Link to={`/isbirlikleri?is=${c.id}`} className="font-mono hover:underline">{c.code}</Link></td>
              <td className={td}>{c.personName}</td>
              <td className={td}>{c.bookTitle}</td>
              <td className={td}><Pill tone={STAGE_TONE[c.stage]}>{c.stageLabel}</Pill></td>
              <td className={td}>{c.disclosureOk === true ? 'var' : c.disclosureOk === false ? 'yok' : '—'}</td>
              <td className={`${td} font-mono tabular-nums`}>{fmtInt(c.engagement)}</td>
              {meta.me.canSeeFee && <td className={`${td} font-mono tabular-nums`}>{fmtMoney(c.fee)}</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </TableWrap>
  );
}
