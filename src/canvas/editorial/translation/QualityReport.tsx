import { Link, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Download, NotebookPen } from 'lucide-react';
import { ENGINE_ENABLED, translationApi, type QualityReport as Report } from '../../engine';
import { Loading, Note, Pill, TableWrap, btnGhost, errText, fmtDate, nf, td, th } from '../../admin/ui';
import { dateTime, num } from '../../format';
import { useCan } from '../../useAdmin';
import { Kpi, KpiRow, ModuleFrame, Panel } from '../kit';
import { CATEGORY, ProgressBar, SEVERITY, StagePill, pair, paceText, pct } from './parts';

/** Kalite raporu (M4): işin gerçek kayıtlarından. MQM inceleme puanı (onaylanan kelimelere göre hata ağırlığı),
 *  inceleyenin düzeltme oranı, otomatik denetim bulguları, terim uyumu, bölüm ve gün gün ilerleme. */

function Mqm({ r }: { r: Report }) {
  const sev = Object.keys(SEVERITY);
  const cats = Object.keys(r.categoryLabels);
  const totals = sev.map((s) => cats.reduce((a, c) => a + (r.mqm.categories[c]?.[s] ?? 0), 0));
  return (
    <Panel>
      <h2 className="px-1 text-[13px] font-extrabold">İnceleme hataları (MQM)</h2>
      <p className="mt-0.5 px-1 text-[11.5px] leading-snug text-canvas-muted">
        Puan = (1 − ceza / incelenen kelime) × 100. Ağırlıklar: küçük {r.mqm.weights.kucuk}, büyük {r.mqm.weights.buyuk}, kritik {r.mqm.weights.kritik}. Toplam ceza{' '}
        {nf.format(r.mqm.penalty)}, incelenen {nf.format(r.mqm.reviewedWords)} kelime.
      </p>
      <div className="mt-2">
        <TableWrap>
          <table className="min-w-full text-[12px]">
            <thead>
              <tr>
                <th className={th}>Kategori</th>
                {sev.map((s) => (
                  <th key={s} className={`${th} text-right`}>
                    {SEVERITY[s].label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {cats.map((c) => (
                <tr key={c} className="border-t border-slate-100">
                  <td className={td}>{r.categoryLabels[c]}</td>
                  {sev.map((s) => (
                    <td key={s} className={`${td} text-right font-mono tabular-nums`}>
                      {nf.format(r.mqm.categories[c]?.[s] ?? 0)}
                    </td>
                  ))}
                </tr>
              ))}
              <tr className="border-t border-slate-200 font-bold">
                <td className={td}>Toplam</td>
                {totals.map((n, i) => (
                  <td key={i} className={`${td} text-right font-mono tabular-nums`}>
                    {nf.format(n)}
                  </td>
                ))}
              </tr>
            </tbody>
          </table>
        </TableWrap>
      </div>
      {r.errorList.length > 0 && (
        <details className="mt-3 rounded-2xl border border-slate-100 bg-white/85 p-3">
          <summary className="cursor-pointer select-none text-[12px] font-extrabold">Bütün hatalar ({nf.format(r.errorList.length)})</summary>
          <ul className="mt-2 space-y-2">
            {r.errorList.map((e) => (
              <li key={e.id} className="text-[12px] leading-snug">
                <div className="flex flex-wrap items-center gap-1.5">
                  <Link to={`/ceviri/masam/${r.id}?segment=${e.segmentId}`} className="font-mono font-bold text-canvas-violet underline">
                    #{e.segmentNo}
                  </Link>
                  <span className="font-bold">{CATEGORY[e.category] ?? e.category}</span>
                  <Pill tone={SEVERITY[e.severity]?.tone ?? 'muted'}>{SEVERITY[e.severity]?.label ?? e.severity}</Pill>
                  <span className="text-[11px] text-canvas-muted">
                    {e.by} · {dateTime(e.at)}
                  </span>
                </div>
                {e.note && <p className="mt-0.5">{e.note}</p>}
                <p className="mt-0.5 text-canvas-muted">{e.source}</p>
                <p className="font-semibold">{e.target}</p>
              </li>
            ))}
          </ul>
        </details>
      )}
    </Panel>
  );
}

function Checks({ r }: { r: Report }) {
  const codes = Object.entries(r.checks.byCode).sort((a, b) => b[1] - a[1]);
  return (
    <Panel>
      <h2 className="px-1 text-[13px] font-extrabold">Otomatik denetim</h2>
      <p className="mt-0.5 px-1 text-[11.5px] leading-snug text-canvas-muted">
        Modelsiz kurallar: sayı, terim karşılığı, yasak karşılık, son noktalama, parantez/tırnak, bağlantı, boşluk, kaynağın kopyası, aynı cümlenin farklı çevirisi, olağan dışı uzunluk. {nf.format(r.checks.segments)} segmentte uyarı var.
      </p>
      {!codes.length ? (
        <p className="mt-2 px-1 text-[12px] font-semibold text-emerald-700">Çevrilmiş segmentlerde uyarı yok.</p>
      ) : (
        <ul className="mt-2 flex flex-wrap gap-1.5">
          {codes.map(([c, n]) => (
            <li key={c}>
              <Pill tone="warn">
                {r.checks.labels[c] ?? c}: {nf.format(n)}
              </Pill>
            </li>
          ))}
        </ul>
      )}
      {r.checks.items.length > 0 && (
        <details className="mt-3 rounded-2xl border border-slate-100 bg-white/85 p-3">
          <summary className="cursor-pointer select-none text-[12px] font-extrabold">Uyarılı segmentler ({nf.format(r.checks.items.length)})</summary>
          <ul className="mt-2 space-y-2">
            {r.checks.items.map((f) => (
              <li key={f.id} className="text-[12px] leading-snug">
                <Link to={`/ceviri/masam/${r.id}?segment=${f.id}`} className="font-mono font-bold text-canvas-violet underline">
                  #{f.no}
                </Link>{' '}
                {f.issues.map((i, k) => (
                  <span key={k} className="mr-1.5">
                    <span className="font-bold">{r.checks.labels[i.code] ?? i.code}:</span> {i.text}
                  </span>
                ))}
                <p className="mt-0.5 text-canvas-muted">{f.source}</p>
                <p className="font-semibold">{f.target}</p>
              </li>
            ))}
          </ul>
        </details>
      )}
    </Panel>
  );
}

function Terms({ r }: { r: Report }) {
  if (!r.terms.items.length) return null;
  return (
    <Panel>
      <h2 className="px-1 text-[13px] font-extrabold">Terim uyumu</h2>
      <p className="mt-0.5 px-1 text-[11.5px] leading-snug text-canvas-muted">Onaylı terimin geçtiği çevrilmiş segmentlerde karşılığı hedefte var mı. Uymayanlar üstte.</p>
      <div className="mt-2">
        <TableWrap>
          <table className="min-w-full text-[12px]">
            <thead>
              <tr>
                <th className={th}>Terim</th>
                <th className={th}>Karşılık</th>
                <th className={`${th} text-right`}>Geçtiği</th>
                <th className={`${th} text-right`}>Uyan</th>
              </tr>
            </thead>
            <tbody>
              {r.terms.items.map((t) => (
                <tr key={t.source} className="border-t border-slate-100">
                  <td className={`${td} font-semibold`}>{t.source}</td>
                  <td className={td}>{t.target}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{nf.format(t.uses)}</td>
                  <td className={`${td} text-right font-mono tabular-nums ${t.ok < t.uses ? 'font-bold text-amber-700' : ''}`}>{nf.format(t.ok)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableWrap>
      </div>
    </Panel>
  );
}

function Chapters({ r }: { r: Report }) {
  return (
    <Panel>
      <h2 className="px-1 text-[13px] font-extrabold">Bölümler</h2>
      <div className="mt-2">
        <TableWrap>
          <table className="min-w-full text-[12px]">
            <thead>
              <tr>
                <th className={th}>Bölüm</th>
                <th className={`${th} text-right`}>Kelime</th>
                <th className={`${th} min-w-[120px]`}>İlerleme</th>
                <th className={`${th} text-right`}>Uyarı</th>
                <th className={`${th} text-right`}>Hata</th>
                <th className={`${th} text-right`}>MQM</th>
              </tr>
            </thead>
            <tbody>
              {r.chapters.map((c) => (
                <tr key={c.no} className="border-t border-slate-100">
                  <td className={`${td} max-w-[280px]`}>
                    <span className="line-clamp-2 break-words">
                      {c.no}. {c.title}
                    </span>
                  </td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{nf.format(c.words)}</td>
                  <td className={td}>
                    <ProgressBar done={c.done} approved={c.approved} total={c.words} label={`${c.title} ilerleme`} />
                    <span className="mt-0.5 block font-mono text-[10.5px] tabular-nums text-canvas-muted">
                      %{pct(c.done, c.words)} · %{pct(c.approved, c.words)} onaylı
                    </span>
                  </td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{nf.format(c.issues)}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{nf.format(c.errors)}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{c.mqm == null ? '—' : num(c.mqm, 1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableWrap>
      </div>
    </Panel>
  );
}

function Daily({ r }: { r: Report }) {
  if (!r.daily.length) return null;
  return (
    <Panel>
      <h2 className="px-1 text-[13px] font-extrabold">Gün gün ilerleme (kelime)</h2>
      <div className="mt-2 grid gap-3 xl:grid-cols-2">
        <TableWrap>
          <table className="min-w-full text-[12px]">
            <thead>
              <tr>
                <th className={th}>Gün</th>
                <th className={`${th} text-right`}>Çevrildi</th>
                <th className={`${th} text-right`}>Onaylandı</th>
                <th className={`${th} text-right`}>Geri alındı</th>
              </tr>
            </thead>
            <tbody>
              {[...r.daily].reverse().map((d) => (
                <tr key={d.date} className="border-t border-slate-100">
                  <td className={td}>{fmtDate(d.date)}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{nf.format(d.cevrildi)}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{nf.format(d.onaylandi)}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{nf.format(d.geri)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableWrap>
        <TableWrap>
          <table className="min-w-full text-[12px]">
            <thead>
              <tr>
                <th className={th}>Kişi</th>
                <th className={`${th} text-right`}>Çevirdiği</th>
                <th className={`${th} text-right`}>Onayladığı</th>
                <th className={`${th} text-right`}>Geri aldığı</th>
              </tr>
            </thead>
            <tbody>
              {r.people.map((p) => (
                <tr key={p.username} className="border-t border-slate-100">
                  <td className={td}>{p.username}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{nf.format(p.cevrildi)}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{nf.format(p.onaylandi)}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{nf.format(p.geri)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableWrap>
      </div>
    </Panel>
  );
}

export default function QualityReport() {
  const { jobId = '' } = useParams();
  const canExport = useCan('veri.disa-aktar');
  const q = useQuery({ queryKey: ['translation', 'quality', jobId], queryFn: () => translationApi.quality(jobId), enabled: ENGINE_ENABLED && !!jobId });
  const r = q.data;
  const termPct = r && r.terms.uses ? pct(r.terms.ok, r.terms.uses) : null;
  return (
    <ModuleFrame
      route="/ceviri"
      crumb="Kalite raporu"
      title={r ? r.title : 'Kalite raporu'}
      lead="İşin segment, inceleme ve ilerleme kayıtlarından hesaplanır; tahmin ya da örnek veri yoktur. Segment numarasına tıklayınca çeviri masasında o segment açılır."
      source={r ? pair(r) : 'Çeviri masası'}
      presence="Kaynak: çeviri kayıtları"
      aside={
        <div className="flex flex-wrap gap-1.5 lg:justify-end">
          <Link to={`/ceviri?is=${jobId}`} className={btnGhost}>
            Çeviri işi
          </Link>
          <Link to={`/ceviri/masam/${jobId}`} className={btnGhost}>
            <NotebookPen aria-hidden className="h-4 w-4" />
            Çeviri masası
          </Link>
          {canExport && (
            <a href={translationApi.qualityCsvUrl(jobId)} className={btnGhost}>
              <Download aria-hidden className="h-4 w-4" />
              CSV
            </a>
          )}
        </div>
      }
    >
      {!ENGINE_ENABLED && <Note tone="warn">ZEKİ AI bağlantısı bu derlemede tanımlı değil.</Note>}
      {q.error && <Note tone="err">{errText(q.error, 'Kalite raporu okunamadı.')}</Note>}
      {q.isLoading && (
        <Panel>
          <Loading />
        </Panel>
      )}
      {r && (
        <>
          <KpiRow>
            <Kpi
              label="İnceleme puanı (MQM)"
              value={r.mqm.score == null ? '—' : num(r.mqm.score, 1)}
              help={r.mqm.reviewedWords ? `${nf.format(r.mqm.reviewedWords)} kelime incelendi · ${nf.format(r.mqm.errors)} hata` : 'Henüz onaylanan segment yok'}
            />
            <Kpi
              label="İnceleyen düzeltmesi"
              value={r.edits.rate == null ? '—' : `%${num(r.edits.rate, 1)}`}
              help={r.edits.reviewed ? `${nf.format(r.edits.segments)} / ${nf.format(r.edits.reviewed)} onaylı segment değişti` : 'Henüz onaylanan segment yok'}
            />
            <Kpi label="Otomatik uyarı" value={nf.format(r.checks.segments)} help={`${nf.format(r.segments.cevrildi + r.segments.onaylandi + r.segments.taslak)} yazılı segmentte`} />
            <Kpi label="Terim uyumu" value={termPct == null ? '—' : `%${termPct}`} help={r.terms.uses ? `${nf.format(r.terms.ok)} / ${nf.format(r.terms.uses)} kullanım` : 'Onaylı terim geçmedi'} />
          </KpiRow>

          <Panel>
            <div className="flex flex-wrap items-start justify-between gap-2">
              <p className="text-[12px] text-canvas-muted">
                {r.author ? `${r.author} · ` : ''}
                {r.translator ? `çevirmen ${r.translatorName || r.translator}` : 'çevirmen atanmadı'}
                {r.reviewer ? ` · inceleyen ${r.reviewerName || r.reviewer}` : ''}
                {r.dueDate ? ` · teslim ${fmtDate(r.dueDate)}` : ''}
                {r.completedAt ? ` · bitti ${fmtDate(r.completedAt)}` : ''}
              </p>
              <StagePill stage={r.stage} />
            </div>
            <div className="mt-2.5">
              <ProgressBar done={r.words.done} approved={r.words.approved} total={r.words.total} label="İş ilerlemesi" />
            </div>
            <p className="mt-1.5 text-[12px] leading-snug text-canvas-muted">
              <span className="font-mono font-bold tabular-nums text-canvas-ink">
                {nf.format(r.words.done)} / {nf.format(r.words.total)}
              </span>{' '}
              kelime çevrildi, <span className="font-mono font-bold tabular-nums text-canvas-ink">{nf.format(r.words.approved)}</span> onaylı. {paceText(r, r.pace)}
            </p>
          </Panel>

          <div className="grid gap-3 xl:grid-cols-2 xl:items-start xl:gap-4">
            <Mqm r={r} />
            <Checks r={r} />
          </div>
          <Chapters r={r} />
          <Terms r={r} />
          <Daily r={r} />
        </>
      )}
    </ModuleFrame>
  );
}
