import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, Loader2, Sparkles, Undo2, X } from 'lucide-react';
import { ENGINE_ENABLED, deskApi, type ChapterDetail, type ChapterRow, type Suggestion, type TextMetrics, type Work } from '../engine';
import { Loading, Note, Pill, btn, btnGhost, errText, nf } from '../admin/ui';
import { num } from '../format';
import { Kpi, KpiRow, ModuleFrame, Panel } from './kit';
import { UploadButton, WorkList, useWorks } from './WorkPicker';

/** M3 Metin İşleme ve Redaksiyon. Metin dosyası yüklenir, bölümlere ayrılır, ölçülür; model yazım ve üslup
 *  önerisi çıkarır, editör kabul/ret eder. Kabul edilen öneri metne işlenir ve ilk hâle göre farkta görünür. */

const STATUS: Record<ChapterRow['status'], { label: string; tone: 'ok' | 'warn' | 'muted' }> = {
  bekliyor: { label: 'Bekliyor', tone: 'muted' },
  islemde: { label: 'İşlemde', tone: 'warn' },
  onaylandi: { label: 'Onaylandı', tone: 'ok' },
};

function Metrics({ m }: { m: TextMetrics }) {
  const rows: Array<[string, string]> = [
    ['Okunabilirlik (Ateşman)', m.atesman == null ? '—' : `${num(m.atesman, 1)}${m.band ? ` · ${m.band}` : ''}`],
    ['Cümle başına kelime', num(m.wordsPerSentence, 1)],
    ['Kelime başına hece', num(m.syllablesPerWord, 2)],
    ['Kelime · cümle · paragraf', `${nf.format(m.words)} · ${nf.format(m.sentences)} · ${nf.format(m.paragraphs)}`],
  ];
  return (
    <dl className="grid grid-cols-2 gap-x-3 gap-y-2 text-[12px]">
      {rows.map(([k, v]) => (
        <div key={k}>
          <dt className="text-[11px] leading-snug text-canvas-muted">{k}</dt>
          <dd className="font-mono font-bold tabular-nums">{v}</dd>
        </div>
      ))}
    </dl>
  );
}

function SuggestionCard({ s, onDecide, busy }: { s: Suggestion; onDecide: (d: 'kabul' | 'red') => void; busy: boolean }) {
  const decided = s.status !== 'bekliyor';
  return (
    <li className={`rounded-2xl border p-3 text-[12.5px] ${decided ? 'border-slate-100 bg-slate-50/70' : 'border-slate-100 bg-white/85'}`}>
      <div className="flex flex-wrap items-center gap-1.5">
        <Pill tone={s.kind === 'yazim' ? 'violet' : 'warn'}>{s.kind === 'yazim' ? 'Yazım' : 'Üslup'}</Pill>
        {s.status === 'kabul' && <Pill tone="ok">Uygulandı</Pill>}
        {s.status === 'red' && <Pill tone="muted">Yok sayıldı</Pill>}
        {s.decidedBy && <span className="text-[11px] text-canvas-muted">{s.decidedBy}</span>}
      </div>
      <p className="mt-1.5 leading-snug">
        <span className="rounded bg-canvas-coral/10 px-1 line-through decoration-canvas-coral/60">{s.original}</span>{' '}
        <span className="rounded bg-canvas-mint/10 px-1 font-semibold">{s.appliedText || s.suggestion}</span>
      </p>
      {s.reason && <p className="mt-1 text-[11.5px] leading-snug text-canvas-muted">{s.reason}</p>}
      {!decided && (
        <div className="mt-2 flex gap-1.5">
          <button type="button" disabled={busy} onClick={() => onDecide('kabul')} className={`${btn} bg-canvas-mint/15 text-emerald-700`}>
            <Check aria-hidden className="h-4 w-4" />
            Kabul et
          </button>
          <button type="button" disabled={busy} onClick={() => onDecide('red')} className={btnGhost}>
            <X aria-hidden className="h-4 w-4" />
            Yok say
          </button>
        </div>
      )}
    </li>
  );
}

function Diff({ d }: { d: ChapterDetail }) {
  if (!d.diff.length) return null;
  return (
    <details className="mt-3 rounded-2xl border border-slate-100 bg-white/85 p-3">
      <summary className="cursor-pointer select-none text-[12px] font-extrabold">İlk hâlden farkı</summary>
      <p className="mt-2 whitespace-pre-wrap text-[12.5px] leading-relaxed">
        {d.diff.map((o, i) =>
          o.op === 'eq' ? (
            <span key={i}>{o.text}</span>
          ) : o.op === 'del' ? (
            <del key={i} className="bg-canvas-coral/10 decoration-canvas-coral/60">
              {o.text}
            </del>
          ) : (
            <ins key={i} className="bg-canvas-mint/15 font-semibold no-underline">
              {o.text}
            </ins>
          ),
        )}
      </p>
    </details>
  );
}

function ChapterPane({ chapterId, onChanged }: { chapterId: string; onChanged: () => void }) {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ['editorial', 'chapter', chapterId],
    queryFn: () => deskApi.chapter(chapterId),
    enabled: ENGINE_ENABLED,
    // Denetim arka planda koşuyor: bitene kadar kendi kendine tazelenir.
    refetchInterval: (query) => (query.state.data?.reviewState === 'calisiyor' ? 4000 : false),
  });
  const d = q.data;
  const refresh = async () => {
    await qc.invalidateQueries({ queryKey: ['editorial', 'chapter', chapterId] });
    onChanged();
  };
  const review = useMutation({ mutationFn: () => deskApi.review(chapterId), onSuccess: refresh });
  const decide = useMutation({ mutationFn: (v: { id: string; d: 'kabul' | 'red' }) => deskApi.decide(v.id, v.d), onSuccess: refresh });
  const approve = useMutation({ mutationFn: (v: boolean) => deskApi.approve(chapterId, v), onSuccess: refresh });
  const err = errText(q.error || review.error || decide.error || approve.error, 'Bölüm okunamadı.');

  if (!d) return <Panel>{err ? <Note tone="err">{err}</Note> : <Loading />}</Panel>;
  const pending = d.suggestions.filter((s) => s.status === 'bekliyor');
  const working = d.reviewState === 'calisiyor';

  return (
    <Panel>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h2 className="break-words text-[17px] font-extrabold leading-tight tracking-tight">
            {d.no}. {d.title}
          </h2>
          <p className="mt-0.5 text-[11.5px] text-canvas-muted">
            {STATUS[d.status].label}
            {d.approvedBy ? ` · ${d.approvedBy}` : ''}
          </p>
        </div>
        <div className="flex flex-wrap gap-1.5">
          <button type="button" disabled={working || review.isPending || d.status === 'onaylandi'} onClick={() => review.mutate()} className={`${btn} bg-canvas-violet text-white`}>
            {working || review.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Sparkles aria-hidden className="h-4 w-4" />}
            {working ? 'Denetleniyor…' : 'ZEKİ ile denetle'}
          </button>
          {d.status === 'onaylandi' ? (
            <button type="button" disabled={approve.isPending} onClick={() => approve.mutate(false)} className={btnGhost}>
              <Undo2 aria-hidden className="h-4 w-4" />
              Onayı geri al
            </button>
          ) : (
            <button type="button" disabled={approve.isPending || pending.length > 0} onClick={() => approve.mutate(true)} className={`${btn} bg-canvas-mint/15 text-emerald-700`}>
              <Check aria-hidden className="h-4 w-4" />
              Bölümü onayla
            </button>
          )}
        </div>
      </div>

      {err && (
        <div className="mt-2">
          <Note tone="err">{err}</Note>
        </div>
      )}
      {d.reviewState === 'hata' && d.reviewNote && (
        <div className="mt-2">
          <Note tone="err">Denetim tamamlanamadı: {d.reviewNote}</Note>
        </div>
      )}
      {d.reviewState === 'bitti' && d.reviewNote && (
        <div className="mt-2">
          <Note tone="info">{d.reviewNote}</Note>
        </div>
      )}
      {pending.length > 0 && d.status !== 'onaylandi' && (
        <div className="mt-2">
          <Note tone="warn">{nf.format(pending.length)} öneri karar bekliyor; karar verilmeden bölüm onaylanamaz.</Note>
        </div>
      )}

      <div className="mt-3 rounded-2xl border border-slate-100 bg-white/85 p-3">
        <Metrics m={d.metrics} />
        {d.metrics.longSentences.length > 0 && (
          <details className="mt-2.5">
            <summary className="cursor-pointer select-none text-[11.5px] font-bold text-canvas-muted">
              {nf.format(d.metrics.longSentences.length)} uzun cümle ({d.metrics.longLimit}+ kelime)
            </summary>
            <ul className="mt-1.5 space-y-1 text-[12px] leading-snug">
              {d.metrics.longSentences.map((s, i) => (
                <li key={i} className="text-canvas-muted">
                  <span className="font-mono font-bold tabular-nums text-canvas-ink">{s.words}</span> {s.text}
                </li>
              ))}
            </ul>
          </details>
        )}
      </div>

      {d.suggestions.length > 0 && (
        <ul className="mt-3 space-y-2">
          {d.suggestions.map((s) => (
            <SuggestionCard key={s.id} s={s} busy={decide.isPending} onDecide={(dec) => decide.mutate({ id: s.id, d: dec })} />
          ))}
        </ul>
      )}
      {!d.suggestions.length && d.reviewState === 'yok' && (
        <p className="mt-3 text-[12.5px] leading-snug text-canvas-muted">Bu bölüm henüz denetlenmedi. “ZEKİ ile denetle” yazım ve üslup önerilerini çıkarır; her öneriye siz karar verirsiniz.</p>
      )}

      <Diff d={d} />

      <details className="mt-3 rounded-2xl border border-slate-100 bg-white/85 p-3">
        <summary className="cursor-pointer select-none text-[12px] font-extrabold">Bölüm metni</summary>
        <p className="mt-2 max-h-96 overflow-y-auto whitespace-pre-wrap text-[12.5px] leading-relaxed">{d.text}</p>
      </details>
    </Panel>
  );
}

export default function RedactionScreen() {
  const qc = useQueryClient();
  const works = useWorks();
  const [workId, setWorkId] = useState<string | null>(null);
  const [chapterId, setChapterId] = useState<string | null>(null);
  const items = works.data?.items ?? [];

  useEffect(() => {
    if (!workId && items.length) setWorkId(items[0].id);
  }, [workId, items]);

  const detail = useQuery({
    queryKey: ['editorial', 'chapters', workId],
    queryFn: () => deskApi.chapters(workId as string),
    enabled: ENGINE_ENABLED && !!workId,
  });
  const chapters = detail.data?.chapters ?? [];
  useEffect(() => {
    if (chapters.length && !chapters.some((c) => c.id === chapterId)) setChapterId(chapters[0].id);
    if (!chapters.length) setChapterId(null);
  }, [chapters, chapterId]);

  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ['editorial', 'chapters', workId] });
    void qc.invalidateQueries({ queryKey: ['editorial', 'works'] });
  };
  const w: Work | undefined = detail.data?.work ?? items.find((x) => x.id === workId);
  const approved = chapters.filter((c) => c.status === 'onaylandi').length;
  const pending = chapters.reduce((a, c) => a + c.pending, 0);
  const err = errText(works.error || detail.error, 'Eser dosyaları okunamadı.');

  return (
    <ModuleFrame
      route="/redaksiyon"
      code="M3"
      crumb="Redaksiyon"
      title="Metin işleme ve redaksiyon"
      lead="Metin dosyası yüklenir, bölümlere ayrılır ve ölçülür; ZEKİ yazım ve üslup önerisi çıkarır, kararı editör verir. Kabul edilen öneri metne işlenir; ilk hâl saklanır."
      source={w ? w.title : 'Editoryal masa'}
    >
      {!ENGINE_ENABLED && <Note tone="warn">Zeki AI bağlantısı bu derlemede tanımlı değil.</Note>}
      {err && <Note tone="err">{err}</Note>}

      {w && chapters.length > 0 && (
        <KpiRow>
          <Kpi label="Bölüm" value={nf.format(chapters.length)} help={detail.data?.versions.length ? `Metin sürümü ${detail.data.versions[0].version}` : ''} />
          <Kpi label="Onaylanan" value={nf.format(approved)} help={`${nf.format(chapters.length - approved)} bölüm sürüyor`} />
          <Kpi label="Karar bekleyen öneri" value={nf.format(pending)} help="Kabul ya da ret bekliyor" />
          <Kpi label="Kelime" value={nf.format(chapters.reduce((a, c) => a + c.words, 0))} help="Güncel metin" />
        </KpiRow>
      )}

      <div className="grid gap-3 lg:grid-cols-[minmax(0,340px)_minmax(0,1fr)] lg:items-start lg:gap-4">
        <div className="space-y-3 lg:space-y-4">
          <WorkList
            works={items}
            selected={workId}
            onSelect={(id) => {
              setWorkId(id);
              setChapterId(null);
            }}
            progress={(x) => (x.manuscript ? `${nf.format(x.chapters.approved)}/${nf.format(x.chapters.total)} bölüm onaylı` : 'Metin yüklenmedi')}
          />

          {w && (
            <Panel>
              <h2 className="px-1 text-[13px] font-extrabold">Metin dosyası</h2>
              <p className="mt-1 px-1 text-[11.5px] leading-snug text-canvas-muted">
                DOCX, PDF ya da TXT. Yeni yükleme yeni sürüm açar ve bölümleri baştan kurar.
              </p>
              <div className="mt-2">
                <UploadButton workId={w.id} kind="manuscript" accept=".docx,.pdf,.txt,.md" onDone={refresh}>
                  Metin yükle
                </UploadButton>
              </div>
              {detail.data?.versions.length ? (
                <ul className="mt-2.5 space-y-1 text-[11.5px]">
                  {detail.data.versions.map((v) => (
                    <li key={v.id} className="flex items-baseline justify-between gap-2">
                      <a href={deskApi.fileUrl(v.id)} className="min-w-0 truncate font-semibold text-canvas-violet underline">
                        v{v.version} · {v.filename}
                      </a>
                      <span className="shrink-0 font-mono text-[11px] tabular-nums text-canvas-muted">{v.report.chapters ?? 0} bölüm</span>
                    </li>
                  ))}
                </ul>
              ) : null}
            </Panel>
          )}

          {chapters.length > 0 && (
            <Panel>
              <h2 className="px-1 text-[13px] font-extrabold">Bölümler</h2>
              <ul className="mt-2 space-y-1.5">
                {chapters.map((c) => (
                  <li key={c.id}>
                    <button
                      type="button"
                      onClick={() => setChapterId(c.id)}
                      aria-pressed={chapterId === c.id}
                      className={`w-full rounded-xl border px-2.5 py-2 text-left text-[12px] transition-colors duration-150 ${
                        chapterId === c.id ? 'border-canvas-violet bg-white' : 'border-slate-100 bg-white/85 hover:bg-white'
                      }`}
                    >
                      <span className="flex items-start justify-between gap-2">
                        <span className="min-w-0 break-words font-semibold leading-snug">
                          {c.no}. {c.title}
                        </span>
                        <Pill tone={STATUS[c.status].tone}>{STATUS[c.status].label}</Pill>
                      </span>
                      <span className="mt-0.5 block text-[11px] text-canvas-muted">
                        {nf.format(c.words)} kelime
                        {c.atesman != null ? ` · okunabilirlik ${num(c.atesman, 0)}` : ''}
                        {c.pending ? ` · ${nf.format(c.pending)} öneri bekliyor` : ''}
                        {c.reviewState === 'calisiyor' ? ' · denetleniyor' : ''}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </Panel>
          )}
        </div>

        {chapterId ? (
          <ChapterPane chapterId={chapterId} onChanged={refresh} />
        ) : (
          <Panel>
            <p className="py-10 text-center text-[12.5px] leading-snug text-canvas-muted">
              {w ? 'Bu eserde henüz metin yok. Soldan bir DOCX, PDF ya da TXT yükleyin.' : 'Soldan bir eser dosyası seçin ya da yeni bir tane açın.'}
            </p>
          </Panel>
        )}
      </div>
    </ModuleFrame>
  );
}
