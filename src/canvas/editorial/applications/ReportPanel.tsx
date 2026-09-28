import { useState, type ReactNode } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { RefreshCw } from 'lucide-react';
import { ENGINE_ENABLED } from '../../engine';
import { Note, Pill, btnGhost, btnPrimary, label, nf } from '../../admin/ui';
import { Panel } from '../kit';
import { fmtDay } from '../authors/shared';
import { applicationsApi, type BoardReport, type Market } from './api';
import { errMsg, invalidateApps } from './shared';
import { EvaluationView } from './EvaluationPanel';
import SqlInfo from '../../components/SqlInfo';
import { kaynakOf } from '../../components/kaynakOf';

/** Yayın Kurulu Raporu: YAZAR · KİTAP · KATEGORİ · 1 yıllık satış tahmini (kötümser / baz / iyimser) · editör
 *  değerlendirmesi · katalog örtüşmesi. Rapor üretildiği anın dondurulmuş hâlidir; «Yeniden üret» tazeler. */

const monthFmt = new Intl.DateTimeFormat('tr-TR', { month: 'long', year: 'numeric', timeZone: 'UTC' });
const month = (d: string) => monthFmt.format(new Date(`${d}T12:00:00Z`));

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="border-t border-slate-100 pt-3 first:border-t-0 first:pt-0">
      <h3 className="text-[11px] font-extrabold uppercase tracking-wide text-canvas-violet">{title}</h3>
      <div className="mt-1.5 space-y-2 text-[12.5px] leading-snug">{children}</div>
    </section>
  );
}

function Text({ k, v }: { k: string; v: string | null | undefined }) {
  if (!v) return null;
  return (
    <div>
      <div className={label}>{k}</div>
      <p className="mt-0.5 whitespace-pre-line">{v}</p>
    </div>
  );
}

function Scenario({ k, v, help, strong }: { k: string; v: number | null; help: string; strong?: boolean }) {
  return (
    <div className={`rounded-2xl px-3 py-2.5 ${strong ? 'bg-canvas-violet/10 ring-1 ring-canvas-violet/30' : 'bg-slate-50'}`}>
      <div className="text-[10.5px] font-bold uppercase tracking-wide text-canvas-muted">{k}</div>
      <div className="font-mono text-[22px] font-extrabold tabular-nums">{v == null ? '—' : nf.format(v)}</div>
      <div className="text-[11px] text-canvas-muted">{help}</div>
    </div>
  );
}

/** İlk 12 ayın ortanca aylık satışı: tek dizi, tek renk, taban çizgisine oturan ince çubuklar. */
function Curve({ m }: { m: Market }) {
  const max = Math.max(1, ...m.curve);
  return (
    <figure>
      <figcaption className="text-[11.5px] text-canvas-muted">Yayından sonraki ilk 12 ay — ay başına ortanca net satış (adet)</figcaption>
      <div className="mt-2 flex h-28 items-end gap-1" role="img" aria-label={m.curve.map((v, i) => `${i + 1}. ay ${nf.format(v)}`).join(', ')}>
        {m.curve.map((v, i) => (
          <div key={i} className="group relative flex h-full flex-1 flex-col justify-end" title={`${i + 1}. ay: ${nf.format(v)} adet`}>
            <span className="block rounded-t-[4px] bg-canvas-violet/80 transition-colors duration-150 group-hover:bg-canvas-violet" style={{ height: `${Math.max(0, (v / max) * 100)}%`, minHeight: v > 0 ? 2 : 0 }} />
          </div>
        ))}
      </div>
      <div className="mt-1 flex gap-1 text-center font-mono text-[10px] tabular-nums text-canvas-muted">
        {m.curve.map((_, i) => (
          <span key={i} className="flex-1">
            {i + 1}
          </span>
        ))}
      </div>
    </figure>
  );
}

function Channels({ m }: { m: Market }) {
  const max = Math.max(1, ...m.channels.map((c) => Math.abs(c.qty)));
  if (!m.channels.length) return <p className="text-canvas-muted">Son 36 ayda satış yok.</p>;
  return (
    <ul className="space-y-1.5">
      {m.channels.map((c) => (
        <li key={c.name} className="grid grid-cols-[minmax(0,9rem)_minmax(0,1fr)_auto] items-center gap-2" title={`${c.name}: ${nf.format(c.qty)} adet`}>
          <span className="truncate text-[12px] font-semibold">{c.name}</span>
          <span className="h-2 rounded-full bg-slate-100">
            <span className="block h-2 rounded-full bg-canvas-violet/80" style={{ width: `${(Math.max(0, c.qty) / max) * 100}%` }} />
          </span>
          <span className="font-mono text-[11.5px] tabular-nums">
            {nf.format(c.qty)}
            {c.share != null && <span className="text-canvas-muted"> · %{String(c.share).replace('.', ',')}</span>}
          </span>
        </li>
      ))}
    </ul>
  );
}

function MarketView({ m }: { m: Market }) {
  const [all, setAll] = useState(false);
  const shown = all ? m.list : m.list.slice(0, 10);
  return (
    <>
      <p className="text-[12px] text-canvas-muted">
        Benzer kitaplar: <b className="text-canvas-ink">{m.categoryName}</b> kitaplığında ilk yayını {month(m.window.from)} – {month(m.window.to)} öncesi
        olan {nf.format(m.books)} kitap; {nf.format(m.withSales)} tanesinin Logo'da satışı var
        {m.withoutSales > 0 && ` (${nf.format(m.withoutSales)} kitapta satış görülmedi, senaryoya girmedi)`}. İlk yıl = yayın ayı dahil 12 ay, iadeler düşülmüş.
      </p>
      <div className="grid gap-2 sm:grid-cols-3">
        <Scenario k="Kötümser" v={m.scenarios.kotumser} help="İlk yıl satışının 1. çeyreği" />
        <Scenario k="Baz" v={m.scenarios.baz} help="Ortanca kitap" strong />
        <Scenario k="İyimser" v={m.scenarios.iyimser} help="3. çeyrek" />
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Curve m={m} />
        <div>
          <div className="text-[11.5px] text-canvas-muted">Kanal kırılımı — bu kitapların son 36 ayı ({nf.format(m.last36)} adet)</div>
          <div className="mt-2">
            <Channels m={m} />
          </div>
        </div>
      </div>
      {m.list.length > 0 && (
        <div>
          <div className={label}>Benzer kitaplar (ilk yıl net satış)</div>
          <div className="mt-1 max-w-full overflow-x-auto overscroll-x-contain rounded-xl border border-slate-100">
            <table className="w-full min-w-[520px] text-[12px]">
              <thead>
                <tr className="bg-slate-50 text-left text-[10.5px] font-bold uppercase tracking-wide text-canvas-muted">
                  <th className="px-2.5 py-1.5">Kitap</th>
                  <th className="px-2.5 py-1.5">Dizi</th>
                  <th className="px-2.5 py-1.5">İlk yayın</th>
                  <th className="px-2.5 py-1.5 text-right">İlk yıl</th>
                </tr>
              </thead>
              <tbody>
                {shown.map((b) => (
                  <tr key={b.code} className="border-t border-slate-100">
                    <td className="px-2.5 py-1.5">
                      <span className="font-semibold">{b.title}</span>
                      {b.author && <span className="text-canvas-muted"> · {b.author}</span>}
                    </td>
                    <td className="px-2.5 py-1.5 text-canvas-muted">{b.series ?? '—'}</td>
                    <td className="whitespace-nowrap px-2.5 py-1.5 font-mono tabular-nums">{fmtDay(b.firstPublish)}</td>
                    <td className="px-2.5 py-1.5 text-right font-mono tabular-nums">{b.sold ? nf.format(b.firstYear) : 'satış yok'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {m.list.length > 10 && (
            <button type="button" className={`${btnGhost} mt-2`} onClick={() => setAll((v) => !v)}>
              {all ? 'İlk 10 kitabı göster' : `Bütün ${nf.format(m.list.length)} kitabı göster`}
            </button>
          )}
        </div>
      )}
      <p className="text-[11px] text-canvas-muted">Kaynak: {m.source}. Hesap {fmtDay(m.computedAt)} tarihli.</p>
    </>
  );
}

export function BoardReportView({ r }: { r: BoardReport }) {
  const a = r.author;
  const b = r.book;
  const m = r.market;
  return (
    <div className="space-y-3">
      {r.problems.length > 0 && (
        <Note tone="warn">
          {r.problems.map((p) => (
            <span key={p} className="block">
              {p}
            </span>
          ))}
        </Note>
      )}
      <Section title="Yazar">
        <p className="text-[14px] font-extrabold">
          {a.name}
          {a.agency && <span className="text-[12px] font-semibold text-canvas-muted"> · Ajans: {a.agency}</span>}
        </p>
        <Text k="Biyografi" v={a.bio} />
        <Text k="Uzmanlık" v={a.expertise} />
        <Text k="Yayıncılık geçmişi" v={a.history} />
        {a.crm && (
          <div className="rounded-xl bg-slate-50 px-2.5 py-2">
            <div className={label}>Yayınevimizdeki geçmişi (CRM)</div>
            <p className="mt-0.5">
              {nf.format(a.crm.works.length)} eser katılımı
              {a.crm.roles.length > 0 && ` (${a.crm.roles.map((x) => `${x.role} ${x.count}`).join(', ')})`} · {nf.format(a.crm.contracts)} sözleşme ·{' '}
              {nf.format(a.crm.projects)} proje
            </p>
            {a.crm.works.length > 0 && (
              <p className="mt-0.5 text-[11.5px] text-canvas-muted">
                {a.crm.works
                  .slice(0, 12)
                  .map((w) => w.title)
                  .filter(Boolean)
                  .join(' · ')}
                {a.crm.works.length > 12 && ` · +${a.crm.works.length - 12}`}
              </p>
            )}
          </div>
        )}
      </Section>
      <Section title="Kitap">
        <p className="text-[14px] font-extrabold">{b.title}</p>
        <p className="text-[11.5px] text-canvas-muted">
          {[b.no, b.audience && `Hedef kitle: ${b.audience}${b.ageFrom != null || b.ageTo != null ? ` (${b.ageFrom ?? ''}–${b.ageTo ?? ''} yaş)` : ''}`, `${nf.format(b.pages)} sayfa (tahmini)`, b.genre, `${b.channel}, ${fmtDay(b.receivedOn)}`]
            .filter(Boolean)
            .join(' · ')}
        </p>
        <Text k="Özet" v={b.summary} />
        <Text k="Yayınevi notu" v={b.publisherNote} />
      </Section>
      <Section title="Kategori ve baskı">
        <div className="grid gap-2 sm:grid-cols-3">
          <div>
            <div className={label}>Kategori</div>
            <p className="mt-0.5 font-semibold">{r.category.name ?? 'Seçilmedi'}</p>
          </div>
          <div>
            <div className={label}>Seri önerisi</div>
            <p className="mt-0.5 font-semibold">
              {r.category.seriesSuggestion
                ? `${r.category.seriesSuggestion.name}`
                : r.category.applicantSeries ?? '—'}
            </p>
            <p className="text-[11px] text-canvas-muted">
              {r.category.seriesSuggestion
                ? `En çok satan çeyrekteki ${r.category.seriesSuggestion.of} kitabın ${r.category.seriesSuggestion.count}'i bu dizide`
                : r.category.applicantSeries
                  ? 'Başvurudaki seri bilgisi'
                  : 'Veri yok'}
              {r.category.seriesSuggestion && r.category.applicantSeries && ` · başvuruda: ${r.category.applicantSeries}`}
            </p>
          </div>
          <div>
            <div className={label}>İlk baskı önerisi</div>
            <p className="mt-0.5 font-mono text-[18px] font-extrabold tabular-nums">{r.category.printRun?.suggested ? nf.format(r.category.printRun.suggested) : '—'}</p>
            {r.category.printRun && <p className="text-[11px] text-canvas-muted">{r.category.printRun.basis}</p>}
          </div>
        </div>
      </Section>
      <Section title="1 yıllık satış tahmini">{m ? <MarketView m={m} /> : <p className="text-canvas-muted">Kategori seçilmediği için hesaplanmadı.</p>}</Section>
      <Section title="Editör değerlendirmesi">{r.evaluation ? <EvaluationView e={r.evaluation} /> : <p className="text-canvas-muted">Rapor üretildiğinde tamamlanmış editör raporu yoktu.</p>}</Section>
      {r.overlap && (
        <Section title="Katalog örtüşmesi">
          {r.overlap.length === 0 ? (
            <p className="text-canvas-muted">Başlıkla örtüşen katalog kaydı bulunmadı.</p>
          ) : (
            <ul className="space-y-1">
              {r.overlap.map((x) => (
                <li key={x.id ?? x.title} className="flex flex-wrap items-baseline justify-between gap-x-2">
                  <span className="min-w-0 break-words">
                    <b>{x.title}</b>
                    <span className="text-canvas-muted">{[x.author, x.category].filter(Boolean).map((t) => ` · ${t}`).join('')}</span>
                  </span>
                  <span className="flex shrink-0 items-center gap-1.5 text-[11px] text-canvas-muted">
                    {x.ownWork && <Pill tone="violet">Yazarın eseri</Pill>}
                    {x.firstPublish ? fmtDay(x.firstPublish) : ''}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Section>
      )}
      <p className="text-[11px] text-canvas-muted">Rapor {fmtDay(r.generatedAt)} tarihinde üretildi.</p>
    </div>
  );
}

export default function ReportPanel({ appId, canWrite, status }: { appId: string; canWrite: boolean; status: string }) {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ['applications', 'report', appId],
    queryFn: () => applicationsApi.report(appId),
    enabled: ENGINE_ENABLED,
    refetchInterval: (query) => (query.state.data?.status === 'hazirlaniyor' ? 4000 : false),
  });
  const run = useMutation({
    mutationFn: (refresh: boolean) => applicationsApi.startReport(appId, refresh),
    onSuccess: async () => {
      toast.success('Rapor hazırlanıyor', { description: 'Logo satışları okunuyor; birkaç dakika sürebilir.' });
      await invalidateApps(qc);
    },
    onError: (e) => toast.error(errMsg(e, 'Rapor başlatılamadı.')),
  });
  const d = q.data;
  const busy = d?.status === 'hazirlaniyor' || run.isPending;
  const early = status === 'yeni' || status === 'degerlendirmede';
  return (
    <Panel>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="flex items-center gap-1 text-[15px] font-extrabold">
            Yayın Kurulu Raporu
            {d?.content && <SqlInfo k={kaynakOf(d)} alan="_hepsi" label="Pazar raporunun rakamları" />}
          </h2>
          <p className="text-[11.5px] text-canvas-muted">
            {d?.status === 'hazir' && d.finishedAt ? `Son üretim ${fmtDay(d.finishedAt)}` : early ? 'Kurula çıkarılınca kendiliğinden üretilir.' : 'Kurula çıkarılınca kendiliğinden üretilir; istenince yeniden üretilir.'}
          </p>
        </div>
        {canWrite && (
          <button type="button" className={d?.status ? btnGhost : btnPrimary} disabled={busy} onClick={() => run.mutate(d?.status === 'hazir')}>
            <RefreshCw aria-hidden className={`h-4 w-4 ${busy ? 'animate-spin' : ''}`} />
            {busy ? 'Hazırlanıyor…' : d?.status ? 'Yeniden üret' : 'Raporu üret'}
          </button>
        )}
      </div>
      <div className="mt-3">
        {q.error && <Note tone="err">{errMsg(q.error, 'Rapor okunamadı.')}</Note>}
        {d?.status === 'hazirlaniyor' && <p className="text-[12.5px] text-canvas-muted">CRM'den benzer kitaplar, Logo'dan satışları okunuyor…</p>}
        {d?.status === 'hata' && <Note tone="err">{d.error ?? 'Rapor üretilemedi.'}</Note>}
        {d?.content && <BoardReportView r={d.content} />}
        {d && d.status === null && <p className="text-[12.5px] text-canvas-muted">Henüz rapor üretilmedi.</p>}
      </div>
    </Panel>
  );
}
