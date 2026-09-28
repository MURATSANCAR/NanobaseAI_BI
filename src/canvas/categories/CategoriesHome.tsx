import { Link } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';
import { Loading, Note, Pill, errText } from '../admin/ui';
import { Kpi, KpiRow, Panel } from '../editorial/kit';
import { fmtDay, fmtInt, fmtPct, STATUS_TONE, TREE_TONE, type Overview, type ProfileStatus } from './api';
import { FillBar, ROOT } from './parts';
import SqlInfo from '../components/SqlInfo';
import { kaynakOf } from '../components/kaynakOf';

/** Özet: katalog sayacı, profil durumu, alan doluluğu, tutarsızlıklar, bana düşenler, ağaç ve CRM farkı. */
export default function CategoriesHome({ overview, loading, error }: { overview?: Overview; loading: boolean; error: unknown }) {
  if (loading) return <Loading />;
  if (error) return <Note tone="err">{errText(error, 'Özet açılamadı.')}</Note>;
  if (!overview) return null;
  const o = overview;
  if (!o.activeBooks) {
    return (
      <Note tone="info">
        CRM kitap kartları henüz okunmadı. «Kaynakları yenile» ile CRM, Logo satışları ve site kategorileri okunur (birkaç dakika sürer);
        gece turu her gün kendiliğinden okur.
      </Note>
    );
  }
  const approved = o.status.onayli ?? 0;
  const rules = Object.entries(o.findings.byRule).sort((a, b) => b[1] - a[1]);
  return (
    <div className="flex flex-col gap-3 lg:gap-4">
      <KpiRow>
        <Kpi info={<SqlInfo k={kaynakOf(o)} alan="_hepsi" label="Aktif kitap" />} label="Aktif kitap" value={fmtInt(o.activeBooks)} help={`CRM'de etkin kitap kartı · ${fmtInt(o.placed)} kitabın ağaçta yeri var`} />
        <Kpi info={<SqlInfo k={kaynakOf(o)} alan="_hepsi" label="Onaylı profil" />} label="Onaylı profil" value={fmtInt(approved)} help={`${fmtPct(approved, o.activeBooks)} · taslak ${fmtInt(o.status.taslak)}, kısmi ${fmtInt(o.status.kismi)}`} />
        <Kpi info={<SqlInfo k={kaynakOf(o)} alan="_hepsi" label="Satıştaki kitap" />} label="Satıştaki kitap" value={fmtPct(o.sellingApproved, o.selling)} help={`${fmtInt(o.selling)} satıştaki kitabın onaylı kategorisi olanı (hedef: tamamı)`} />
        <Kpi info={<SqlInfo k={kaynakOf(o)} alan="_hepsi" label="Açık tutarsızlık" />} label="Açık tutarsızlık" value={fmtInt(o.findings.open)} help={`${rules.length} kuralda · CRM'e işlenecek ${fmtInt(o.crmDiff.rows)} satır`} />
      </KpiRow>

      <div className="grid gap-3 lg:grid-cols-[1.2fr_1fr] lg:gap-4">
        <Panel>
          <div className="flex items-baseline justify-between gap-2">
            <h2 className="flex items-center gap-1 text-[15px] font-extrabold">Alan doluluğu (CRM)<SqlInfo k={kaynakOf(o)} alan="_hepsi" label="Alan doluluğu (CRM)" /></h2>
            <span className="text-[11.5px] font-semibold text-canvas-muted">{fmtInt(o.activeBooks)} aktif kitapta</span>
          </div>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            {o.fill.map((f) => <FillBar key={f.key} label={f.label} filled={f.filled} total={f.total} />)}
          </div>
          <p className="mt-3 text-[11.5px] leading-snug text-canvas-muted">
            Çoka-çok bağlar: ürün kategorisi {fmtInt(o.links.urunkategorisi)}, raf {fmtInt(o.links.raf)}, sergilenecek {fmtInt(o.links.sergilenecek)},
            tema {fmtInt(o.links.tema)}, anahtar kelime {fmtInt(o.links.anahtarkelime)}, tür {fmtInt(o.links.tur)}. Site: {fmtInt(o.tsoft.products ?? 0)} ürün,
            {' '}{fmtInt(o.tsoft.categories)} kategori{o.tsoft.syncedAt ? ` (SEO eşitlemesi ${fmtDay(o.tsoft.syncedAt)})` : ' (SEO eşitlemesi yok)'}.
          </p>
        </Panel>

        <div className="flex flex-col gap-3 lg:gap-4">
          <Panel>
            <h2 className="flex items-center gap-1 text-[15px] font-extrabold">Bana düşenler<SqlInfo k={kaynakOf(o)} alan="_hepsi" label="Bana düşenler" /></h2>
            <p className="mt-1 text-[12.5px] leading-snug text-canvas-muted">
              {o.mine.pending
                ? <>Editörü ya da yayın yönetmeni olduğunuz <strong className="text-canvas-ink">{fmtInt(o.mine.pending)}</strong> kitapta karar bekleyen öneri var.</>
                : 'Kararınızı bekleyen öneri yok.'}
            </p>
            <Link to={`${ROOT}/kuyruk?sahip=ben&durum=taslak,kismi`} className="mt-2 inline-flex items-center gap-1 text-[12.5px] font-extrabold text-canvas-violet hover:underline">
              Kuyruğumu aç <ArrowRight aria-hidden className="h-3.5 w-3.5" />
            </Link>
          </Panel>
          <Panel>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="flex items-center gap-1 text-[15px] font-extrabold">Kategori ağacı<SqlInfo k={kaynakOf(o)} alan="_hepsi" label="Kategori ağacı" /></h2>
              {o.tree.inForce ? <Pill tone={TREE_TONE.yururlukte}>Yürürlükte v{o.tree.inForce.version}</Pill> : <Pill tone="warn">Yürürlükte ağaç yok</Pill>}
              {o.tree.draft && <Pill tone={TREE_TONE[o.tree.draft.status]}>{o.tree.draft.statusLabel} v{o.tree.draft.version}</Pill>}
            </div>
            <p className="mt-1 text-[12.5px] leading-snug text-canvas-muted">
              {o.tree.inForce
                ? <>{o.tree.inForce.approvedBy} onayladı, {fmtDay(o.tree.inForce.approvedAt)}. Kitapların {fmtPct(o.placed, o.activeBooks)}'i CRM sınıflamalarıyla ağaca yerleşiyor.</>
                : 'Ağaç onaylanınca kitaplar CRM sınıflamalarıyla ağaca yerleşir ve gece turu profil önerisi üretmeye başlar.'}
            </p>
            <Link to={`${ROOT}/agac`} className="mt-2 inline-flex items-center gap-1 text-[12.5px] font-extrabold text-canvas-violet hover:underline">
              Ağacı aç <ArrowRight aria-hidden className="h-3.5 w-3.5" />
            </Link>
          </Panel>
          <Panel>
            <h2 className="flex items-center gap-1 text-[15px] font-extrabold">CRM'e işlenecek fark<SqlInfo k={kaynakOf(o)} alan="_hepsi" label="CRM'e işlenecek fark" /></h2>
            <p className="mt-1 text-[12.5px] leading-snug text-canvas-muted">
              {fmtInt(o.crmDiff.books)} kitapta {fmtInt(o.crmDiff.rows)} satır{o.crmDiff.stale ? <>, <strong className="text-red-700">{fmtInt(o.crmDiff.stale)}'i bekliyor</strong></> : ''}.
            </p>
            <Link to={`${ROOT}/crm-farki`} className="mt-2 inline-flex items-center gap-1 text-[12.5px] font-extrabold text-canvas-violet hover:underline">
              Listeyi aç <ArrowRight aria-hidden className="h-3.5 w-3.5" />
            </Link>
          </Panel>
        </div>
      </div>

      <div className="grid gap-3 lg:grid-cols-2 lg:gap-4">
        <Panel>
          <h2 className="flex items-center gap-1 text-[15px] font-extrabold">Profil durumu<SqlInfo k={kaynakOf(o)} alan="_hepsi" label="Profil durumu" /></h2>
          <ul className="mt-2 flex flex-wrap gap-2">
            {(Object.keys(o.statusLabels) as ProfileStatus[]).map((s) => (
              <li key={s}>
                <Link to={`${ROOT}/kuyruk?durum=${s}`} className="inline-flex items-center gap-1.5 rounded-xl bg-white/80 px-2.5 py-1.5 text-[12px] font-bold transition-transform duration-150 ease-out active:scale-[0.97]">
                  <Pill tone={STATUS_TONE[s]}>{o.statusLabels[s]}</Pill>
                  <span className="font-mono tabular-nums">{fmtInt(o.status[s])}</span>
                </Link>
              </li>
            ))}
          </ul>
        </Panel>
        <Panel>
          <h2 className="flex items-center gap-1 text-[15px] font-extrabold">Tutarsızlıklar<SqlInfo k={kaynakOf(o)} alan="_hepsi" label="Tutarsızlıklar" /></h2>
          {rules.length === 0 ? (
            <p className="mt-1 text-[12.5px] text-canvas-muted">Açık tutarsızlık yok.</p>
          ) : (
            <ul className="mt-2 divide-y divide-slate-100">
              {rules.map(([k, n]) => (
                <li key={k}>
                  <Link to={`${ROOT}/tutarsizlik?kural=${k}`} className="flex min-h-11 items-center justify-between gap-2 py-1.5 text-[12.5px] font-semibold hover:text-canvas-violet">
                    <span className="min-w-0 truncate">{o.findings.labels[k] ?? k}</span>
                    <span className="shrink-0 font-mono tabular-nums">{fmtInt(n)}</span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
    </div>
  );
}
