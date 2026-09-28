import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Gauge, Loader2, RefreshCw } from 'lucide-react';
import { ENGINE_ENABLED, send, type SegmentStatus } from '../../engine';
import { Note, Pill, TableWrap, btn, btnGhost, errText, nf, td, th } from '../../admin/ui';
import { dateTime, num } from '../../format';
import { Panel } from '../kit';
import { CATEGORY, ProgressBar, SEVERITY, pct } from './parts';

/** ZEKİ kalite tahmini (M4): çevrilmiş segment başına 0–100 puan. Bir TAHMİNDİR, inceleyenin MQM puanı değildir.
 *  85 altı «şüpheli»; gerekçe yalnız alıntısı çeviride birebir geçiyorsa gösterilir. Hedef değişince puan «eski»
 *  olur ve bir sonraki tahminde yeniden sorulur. Uç: /api/v1/editorial/translation/jobs/:iş/qe. */

export type QeItem = {
  segmentId: string;
  no: number;
  chapter: number;
  words: number;
  status: SegmentStatus;
  score: number;
  category: string | null;
  severity: 'kucuk' | 'buyuk' | 'kritik' | null;
  reason: string | null;
  span: string | null;
  stale: boolean;
  suspect: boolean;
  at: string;
};
export type QeRun = {
  state: 'yok' | 'calisiyor' | 'bitti' | 'hata';
  note: string | null;
  done: number;
  total: number;
  chapter: number | null;
  startedBy: string | null;
  startedAt: string | null;
  finishedAt: string | null;
};
export type QeReport = {
  run: QeRun;
  threshold: number;
  items: QeItem[];
  lowest: Array<QeItem & { source: string; target: string }>;
  summary: {
    translated: number;
    scored: number;
    stale: number;
    missing: number;
    suspect: number;
    words: number;
    average: number | null;
    buckets: Array<{ from: number; to: number; label: string; segments: number; words: number }>;
    chapters: Array<{ no: number; title: string; scored: number; suspect: number; average: number | null }>;
  };
  canRun: boolean;
  categoryLabels: Record<string, string>;
  severityLabels: Record<string, string>;
};

const base = (id: string) => `/api/v1/editorial/translation/jobs/${encodeURIComponent(id)}/qe`;
export const qeApi = {
  get: (id: string) => send<QeReport>('GET', base(id), undefined, 60_000),
  start: (id: string, b: { chapter?: number | null; all?: boolean }) => send<{ segments: number; words: number }>('POST', base(id), b, 60_000),
};
/** İş anahtarının altında: segment kaydından sonra ['translation','job',iş] tazelenince eskime de tazelenir. */
export const qeKey = (jobId: string) => ['translation', 'job', jobId, 'qe'] as const;

export function useQe(jobId: string, enabled = true) {
  return useQuery({
    queryKey: qeKey(jobId),
    queryFn: () => qeApi.get(jobId),
    enabled: ENGINE_ENABLED && enabled && !!jobId,
    refetchInterval: (query) => (query.state.data?.run.state === 'calisiyor' ? 5000 : false),
  });
}

/** 85 altı (güncel ya da eski) — «ZEKİ şüpheli» süzgeci; eski puan çevirmen düzelttiyse satırda «eski» yazar. */
export const flagged = (i: QeItem | undefined, threshold = 85) => !!i && i.score < threshold;

const scoreTone = (s: number): 'err' | 'warn' | 'ok' => (s < 70 ? 'err' : s < 85 ? 'warn' : 'ok');

/** Satırdaki küçük puan: yalnız 85 altı. Hedef sonradan değiştiyse soluk ve «eski». */
export function QePill({ item, threshold = 85 }: { item: QeItem | undefined; threshold?: number }) {
  if (!flagged(item, threshold) || !item) return null;
  return item.stale ? (
    <Pill tone="muted">ZEKİ {item.score} · eski</Pill>
  ) : (
    <Pill tone={scoreTone(item.score)}>ZEKİ {item.score}</Pill>
  );
}

const DISCLAIMER = 'Tahmindir: inceleyenin MQM puanı yerine geçmez, yalnız bakılacak yeri gösterir.';

/** Çeviri masasının yan panelindeki bölüm: puan, kategori, alıntılı gerekçe, eskime. */
export function QeSection({ item, translated, threshold = 85 }: { item: QeItem | undefined; translated: boolean; threshold?: number }) {
  return (
    <section className="rounded-2xl border border-slate-100 bg-white/85 p-3">
      <h3 className="flex items-center gap-1.5 text-[12px] font-extrabold">
        <Gauge aria-hidden className="h-4 w-4 text-canvas-violet" />
        ZEKİ kalite tahmini
      </h3>
      <div className="mt-2 text-[12px] leading-snug">
        {!item ? (
          <p className="text-[11.5px] text-canvas-muted">{translated ? 'Bu segment henüz puanlanmadı.' : 'Çevrilip onaylanınca puanlanabilir.'}</p>
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-1.5">
              <span className={`font-mono text-[18px] font-bold tabular-nums ${item.stale ? 'text-canvas-muted' : ''}`}>{item.score}</span>
              <span className="text-[11px] text-canvas-muted">/ 100</span>
              {item.score < threshold && item.severity && <Pill tone={SEVERITY[item.severity]?.tone ?? 'muted'}>{SEVERITY[item.severity]?.label}</Pill>}
              {item.score < threshold && item.category && <span className="font-bold">{CATEGORY[item.category] ?? item.category}</span>}
              {item.score >= threshold && !item.stale && <Pill tone="ok">Sorun görmedi</Pill>}
            </div>
            {item.stale && (
              <p className="mt-1 text-[11.5px] font-semibold text-amber-700">Puan metnin önceki hâline ait; bir sonraki tahminde yeniden puanlanır.</p>
            )}
            {item.score < threshold &&
              (item.reason ? (
                <p className="mt-1">
                  {item.reason}
                  {item.span && (
                    <span className="mt-0.5 block text-[11.5px] text-canvas-muted">
                      Alıntı: <mark className="rounded bg-amber-100 px-0.5 text-canvas-ink">{item.span}</mark>
                    </span>
                  )}
                </p>
              ) : (
                <p className="mt-1 text-[11.5px] text-canvas-muted">Gerekçe gösterilmiyor: ZEKİ'nin alıntıladığı bölüm çeviride birebir bulunamadı.</p>
              ))}
            <p className="mt-1 text-[10.5px] text-canvas-muted">{dateTime(item.at)}</p>
          </>
        )}
        <p className="mt-1 text-[11px] text-canvas-muted">{DISCLAIMER}</p>
      </div>
    </section>
  );
}

/** Başlatma düğmesi + ilerleme + son çalıştırmanın notu. Düğme yalnız inceleyene / yöneticiye (sunucu `canRun`). */
export function QeStrip({ jobId, compact = false }: { jobId: string; compact?: boolean }) {
  const qc = useQueryClient();
  const q = useQe(jobId);
  const start = useMutation({
    mutationFn: (all: boolean) => qeApi.start(jobId, { all }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: qeKey(jobId) }),
  });
  const r = q.data;
  if (!r) return q.error ? <Note tone="err">{errText(q.error, 'Kalite tahmini okunamadı.')}</Note> : null;
  const s = r.summary;
  const running = r.run.state === 'calisiyor';
  const todo = s.missing;
  if (compact && !r.canRun && !running && !s.scored) return null;
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        {r.canRun && (todo > 0 || running) && (
          <button type="button" disabled={running || start.isPending} onClick={() => start.mutate(false)} className={`${btn} bg-canvas-violet text-white`}>
            {running || start.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Gauge aria-hidden className="h-4 w-4" />}
            {running ? 'Tahmin sürüyor…' : `ZEKİ ile kalite tahmini (${nf.format(todo)} segment)`}
          </button>
        )}
        {r.canRun && !running && todo === 0 && s.scored > 0 && !compact && (
          <button
            type="button"
            disabled={start.isPending}
            onClick={() => {
              if (window.confirm(`Güncel puanlar dahil ${nf.format(s.translated)} segment yeniden puanlansın mı? Model süresi harcar.`)) start.mutate(true);
            }}
            className={btnGhost}
          >
            <RefreshCw aria-hidden className="h-4 w-4" />
            Hepsini yeniden puanla
          </button>
        )}
        <span className="min-w-0 text-[11.5px] leading-snug text-canvas-muted">
          {s.scored > 0 ? (
            <>
              <span className="font-mono font-bold tabular-nums text-canvas-ink">{nf.format(s.suspect)}</span> segment {r.threshold} altında · kelimeyle ağırlıklı ortalama{' '}
              <span className="font-mono font-bold tabular-nums text-canvas-ink">{num(s.average, 1)}</span>
              {todo > 0 ? ` · ${nf.format(todo)} çevrilmiş segment puansız ya da eski` : ' · puanlar güncel'}
            </>
          ) : s.translated ? (
            `${nf.format(s.translated)} çevrilmiş segment henüz puanlanmadı.`
          ) : (
            'Çevrilmiş segment olunca puanlanabilir.'
          )}
        </span>
      </div>
      {running && (
        <div>
          <ProgressBar done={r.run.done} approved={0} total={r.run.total} label="Kalite tahmini ilerlemesi" />
          <p className="mt-1 text-[11.5px] text-canvas-muted">
            ZEKİ kalite tahmini: <span className="font-mono font-bold tabular-nums text-canvas-ink">%{pct(r.run.done, r.run.total)}</span> ({nf.format(r.run.done)} /{' '}
            {nf.format(r.run.total)} segment). Sayfadan ayrılabilirsiniz; tahmin arka planda sürer.
          </p>
        </div>
      )}
      {!compact && r.run.state === 'bitti' && r.run.note && <Note tone="ok">{r.run.note}</Note>}
      {r.run.state === 'hata' && r.run.note && <Note tone="err">{r.run.note}</Note>}
      {start.error && <Note tone="err">{errText(start.error, 'Kalite tahmini başlatılamadı.')}</Note>}
    </div>
  );
}

/** Çeviri yönetimi ekranındaki iş paneli bölümü. */
export function QeJobPanel({ jobId }: { jobId: string }) {
  return (
    <Panel>
      <h3 className="px-1 text-[13px] font-extrabold">ZEKİ kalite tahmini</h3>
      <p className="mt-0.5 px-1 text-[11.5px] leading-snug text-canvas-muted">
        ZEKİ çevrilmiş her segmenti kaynağıyla karşılaştırıp 0–100 arası puan verir (anlamın eksiksiz aktarılması ve akıcılık). 85 altı «şüpheli» sayılır;
        gerekçe yalnız alıntısı çeviride birebir geçiyorsa gösterilir. {DISCLAIMER} Başlatma model süresi harcar; işin inceleyeni ya da yöneticisi başlatır.
      </p>
      <div className="mt-2.5">
        <QeStrip jobId={jobId} />
      </div>
    </Panel>
  );
}

/** Kalite raporundaki panel: dağılım, kelimeyle ağırlıklı ortalama, bölüm özeti ve en düşük puanlı segmentler. */
export function QePanel({ jobId }: { jobId: string }) {
  const q = useQe(jobId);
  const r = q.data;
  if (!r) return q.error ? <Note tone="err">{errText(q.error, 'Kalite tahmini okunamadı.')}</Note> : null;
  const s = r.summary;
  const maxBucket = Math.max(1, ...s.buckets.map((b) => b.segments));
  return (
    <Panel>
      <div className="flex flex-wrap items-baseline justify-between gap-2 px-1">
        <h2 className="text-[13px] font-extrabold">ZEKİ kalite tahmini</h2>
        <Pill tone="violet">Tahmin · MQM değil</Pill>
      </div>
      <p className="mt-0.5 px-1 text-[11.5px] leading-snug text-canvas-muted">
        Her çevrilmiş segmente ZEKİ'nin verdiği 0–100 puan. Yukarıdaki MQM inceleme puanı insan incelemesinden hesaplanır; bu tahmin onun yerine geçmez,
        yalnız incelemede önce bakılacak segmentleri sıralar. Ortalama yalnız güncel puanlardan, segmentin kaynak kelime sayısıyla ağırlıklıdır.
      </p>
      <div className="mt-2.5">
        <QeStrip jobId={jobId} />
      </div>
      {s.scored > 0 && (
        <>
          <dl className="mt-3 grid grid-cols-2 gap-2 text-[11.5px] sm:grid-cols-4">
            <div>
              <dt className="text-canvas-muted">Ortalama (kelimeyle)</dt>
              <dd className="font-mono text-[18px] font-bold tabular-nums">{num(s.average, 1)}</dd>
            </div>
            <div>
              <dt className="text-canvas-muted">Puanlanan</dt>
              <dd className="font-mono text-[18px] font-bold tabular-nums">
                {nf.format(s.scored)} <span className="text-[11.5px] font-semibold text-canvas-muted">/ {nf.format(s.translated)}</span>
              </dd>
            </div>
            <div>
              <dt className="text-canvas-muted">{r.threshold} altı (şüpheli)</dt>
              <dd className="font-mono text-[18px] font-bold tabular-nums">{nf.format(s.suspect)}</dd>
            </div>
            <div>
              <dt className="text-canvas-muted">Puansız ya da eski</dt>
              <dd className="font-mono text-[18px] font-bold tabular-nums">{nf.format(s.missing)}</dd>
            </div>
          </dl>

          <h3 className="mt-3 px-1 text-[12px] font-extrabold">Dağılım (güncel puanlar)</h3>
          <ul className="mt-1.5 space-y-1.5">
            {s.buckets.map((b) => (
              <li key={b.label} className="grid grid-cols-[3.5rem_minmax(0,1fr)_auto] items-center gap-2 text-[11.5px]">
                <span className="font-mono font-bold tabular-nums">{b.label}</span>
                <span className="relative h-2 overflow-hidden rounded-full bg-slate-100" aria-hidden>
                  <span className="absolute inset-0 origin-left rounded-full bg-canvas-violet/70" style={{ transform: `scaleX(${b.segments / maxBucket})` }} />
                </span>
                <span className="text-right font-mono tabular-nums text-canvas-muted">
                  {nf.format(b.segments)} segment · {nf.format(b.words)} kelime
                </span>
              </li>
            ))}
          </ul>

          {s.chapters.length > 1 && (
            <div className="mt-3">
              <TableWrap>
                <table className="min-w-full text-[12px]">
                  <thead>
                    <tr>
                      <th className={th}>Bölüm</th>
                      <th className={`${th} text-right`}>Puanlanan</th>
                      <th className={`${th} text-right`}>Şüpheli</th>
                      <th className={`${th} text-right`}>Ortalama</th>
                    </tr>
                  </thead>
                  <tbody>
                    {s.chapters.map((c) => (
                      <tr key={c.no} className="border-t border-slate-100">
                        <td className={`${td} max-w-[280px]`}>
                          <span className="line-clamp-2 break-words">
                            {c.no}. {c.title}
                          </span>
                        </td>
                        <td className={`${td} text-right font-mono tabular-nums`}>{nf.format(c.scored)}</td>
                        <td className={`${td} text-right font-mono tabular-nums`}>{nf.format(c.suspect)}</td>
                        <td className={`${td} text-right font-mono tabular-nums`}>{num(c.average, 1)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </TableWrap>
            </div>
          )}

          {r.lowest.length > 0 && (
            <details className="mt-3 rounded-2xl border border-slate-100 bg-white/85 p-3">
              <summary className="cursor-pointer select-none text-[12px] font-extrabold">En düşük puanlı segmentler ({nf.format(r.lowest.length)})</summary>
              <ul className="mt-2 space-y-2">
                {r.lowest.map((i) => (
                  <li key={i.segmentId} className="text-[12px] leading-snug">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <Link to={`/ceviri/masam/${jobId}?segment=${i.segmentId}`} className="font-mono font-bold text-canvas-violet underline">
                        #{i.no}
                      </Link>
                      <Pill tone={scoreTone(i.score)}>ZEKİ {i.score}</Pill>
                      {i.category && <span className="font-bold">{CATEGORY[i.category] ?? i.category}</span>}
                    </div>
                    {i.reason && <p className="mt-0.5">{i.reason}</p>}
                    <p className="mt-0.5 text-canvas-muted">{i.source}</p>
                    <p className="font-semibold">{i.target}</p>
                  </li>
                ))}
              </ul>
            </details>
          )}
        </>
      )}
    </Panel>
  );
}
