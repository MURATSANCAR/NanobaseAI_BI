import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, Loader2, Sparkles, Trash2, Undo2, X } from 'lucide-react';
import { ENGINE_ENABLED, deskApi, type ChapterDetail, type ChapterRow, type DeskFile, type Suggestion, type TextMetrics, type Work } from '../engine';
import { Loading, Note, Pill, btn, btnGhost, errText, nf } from '../admin/ui';
import { dateTime, num } from '../format';
import { Kpi, KpiRow, ModuleFrame, Panel } from './kit';
import { WorkInfo, WorkList, WorkUpload, fmtBytes, useWorks } from './WorkPicker';
import { FileDrop } from '../components/FileDrop';
import SqlInfo from '../components/SqlInfo';
import { kaynakOf } from '../components/kaynakOf';
import { ExplainLabel } from '../components/Explain';

/** M3 Metin İşleme ve Redaksiyon. Metin dosyası yüklenir, kitabın kendi bölümlerine ayrılır (yapı bulunamazsa
 *  «parça» denir, ZEKI-44), ölçülür; model yazım ve üslup önerisi çıkarır, editör kabul/ret eder. Kabul edilen öneri
 *  metne işlenir ve ilk hâle göre farkta görünür. Eser adı/yazarı düzeltilir, yanlış dosya kaldırılır ya da
 *  değiştirilir (ZEKI-45). */

/** Ekrandaki birim: kitabın bölümleri bulunduysa «bölüm», bulunamadıysa dürüstçe «parça». */
type Unit = { one: string; One: string; many: string; Many: string; all: string; numbered: boolean };
const UNITS: Record<'bolum' | 'parca', Unit> = {
  bolum: { one: 'bölüm', One: 'Bölüm', many: 'bölüm', Many: 'Bölümler', all: 'bölümlerin', numbered: true },
  // Parçanın adı numarasını ve sayfa aralığını zaten taşır («Parça 3 · s. 41–58»).
  parca: { one: 'parça', One: 'Parça', many: 'parça', Many: 'Parçalar', all: 'parçaların', numbered: false },
};
const unitOf = (f: DeskFile | null | undefined): Unit => UNITS[f?.report.unit === 'parca' ? 'parca' : 'bolum'];

/** Metnin nasıl ayrıldığı (köprü: editorial_desk_structure.py). */
const HOW: Record<string, string> = {
  outline: "Bölümler PDF'in içindekiler işaretlerinden alındı.",
  typography: 'Bölümler başlıkların yazı boyutundan bulundu.',
  toc: 'Bölümler kitabın içindekiler sayfasından bulundu.',
  styles: 'Bölümler Word başlık stillerinden alındı.',
  markdown: 'Bölümler metindeki başlık işaretlerinden alındı.',
  pattern: '«Bölüm» diye başlayan başlık satırlarından ayrıldı.',
  pieces: 'Kitapta bölüm yapısı bulunamadı; metin yaklaşık eşit büyüklükte parçalara ayrıldı.',
};

const STATUS: Record<ChapterRow['status'], { label: string; tone: 'ok' | 'warn' | 'muted' }> = {
  bekliyor: { label: 'Bekliyor', tone: 'muted' },
  islemde: { label: 'İşlemde', tone: 'warn' },
  onaylandi: { label: 'Onaylandı', tone: 'ok' },
};

function Metrics({ m }: { m: TextMetrics }) {
  const rows: Array<[string, string, string?]> = [
    [
      'Okunabilirlik',
      m.atesman == null ? '—' : `${num(m.atesman, 1)}${m.band ? ` · ${m.band}` : ''}`,
      'Türkçe metinler için okunabilirlik puanı (Ateşman ölçüsü): kelime ve cümle uzunluğundan hesaplanır. Puan yükseldikçe metin kolay okunur.',
    ],
    ['Cümle başına kelime', num(m.wordsPerSentence, 1)],
    ['Kelime başına hece', num(m.syllablesPerWord, 2)],
    ['Kelime · cümle · paragraf', `${nf.format(m.words)} · ${nf.format(m.sentences)} · ${nf.format(m.paragraphs)}`],
  ];
  return (
    <dl className="grid grid-cols-2 gap-x-3 gap-y-2 text-[12px]">
      {rows.map(([k, v, hint]) => (
        <div key={k}>
          <dt className="text-[11px] leading-snug text-canvas-muted">{hint ? <ExplainLabel label={k}>{hint}</ExplainLabel> : k}</dt>
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

function ChapterPane({ chapterId, onChanged, unit }: { chapterId: string; onChanged: () => void; unit: Unit }) {
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
  const err = errText(q.error || review.error || decide.error || approve.error, `${unit.One} okunamadı.`);

  if (!d) return <Panel>{err ? <Note tone="err">{err}</Note> : <Loading />}</Panel>;
  const pending = d.suggestions.filter((s) => s.status === 'bekliyor');
  const working = d.reviewState === 'calisiyor';

  return (
    <Panel>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h2 className="break-words text-[17px] font-extrabold leading-tight tracking-tight">
            {unit.numbered ? `${d.no}. ${d.title}` : d.title}
            <SqlInfo k={kaynakOf(q.data)} alan="_hepsi" label={`${unit.One} metin ölçüleri ve öneriler`} className="ml-1" />
          </h2>
          <p className="mt-0.5 text-[11.5px] text-canvas-muted">
            {STATUS[d.status].label}
            {d.approvedBy ? ` · ${d.approvedBy}` : ''}
          </p>
        </div>
        <div className="flex flex-wrap gap-1.5">
          <button type="button" disabled={working || review.isPending || d.status === 'onaylandi'} onClick={() => review.mutate()} className={`${btn} bg-canvas-violet text-white`}>
            {working || review.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Sparkles aria-hidden className="h-4 w-4" />}
            {working ? 'Denetleniyor…' : 'Zeki AI ile denetle'}
          </button>
          {d.status === 'onaylandi' ? (
            <button type="button" disabled={approve.isPending} onClick={() => approve.mutate(false)} className={btnGhost}>
              <Undo2 aria-hidden className="h-4 w-4" />
              Onayı geri al
            </button>
          ) : (
            <button type="button" disabled={approve.isPending || pending.length > 0} onClick={() => approve.mutate(true)} className={`${btn} bg-canvas-mint/15 text-emerald-700`}>
              <Check aria-hidden className="h-4 w-4" />
              {unit.numbered ? 'Bölümü onayla' : 'Parçayı onayla'}
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
          <Note tone="warn">{nf.format(pending.length)} öneri karar bekliyor; karar verilmeden {unit.one} onaylanamaz.</Note>
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
        <p className="mt-3 text-[12.5px] leading-snug text-canvas-muted">Bu {unit.one} henüz denetlenmedi. «Zeki AI ile denetle» yazım ve üslup önerilerini çıkarır; her öneriyi siz kabul eder ya da yok sayarsınız.</p>
      )}

      <Diff d={d} />

      <details className="mt-3 rounded-2xl border border-slate-100 bg-white/85 p-3">
        <summary className="cursor-pointer select-none text-[12px] font-extrabold">{unit.One} metni</summary>
        <p className="mt-2 max-h-96 overflow-y-auto whitespace-pre-wrap text-[12.5px] leading-relaxed">{d.text}</p>
      </details>
    </Panel>
  );
}

/** Eser dosyası paneli (ZEKI-45): ad/yazar düzeltme, etkin metin sürümü, dosyayı değiştirme (yeni sürüm) ve
 *  kaldırma. Kaldırma silmez: sürüm, dosya ve kararlar iz olarak kalır; etkin sürüm bir öncekine döner. */
function WorkFilePanel({
  work,
  versions,
  activeId,
  onChanged,
}: {
  work: Work;
  versions: DeskFile[];
  activeId: string | null;
  onChanged: () => void;
}) {
  const qc = useQueryClient();
  const [confirm, setConfirm] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const active = versions.find((v) => v.id === activeId) ?? null;
  const fallback = versions.find((v) => v.id !== activeId && !v.removedAt) ?? null;
  const others = versions.filter((v) => v.id !== activeId);
  const unit = unitOf(active);
  useEffect(() => setConfirm(false), [work.id, activeId]);
  useEffect(() => setNotice(null), [work.id]);
  const remove = useMutation({
    mutationFn: (id: string) => deskApi.removeFile(id),
    onSuccess: async (r) => {
      setConfirm(false);
      setNotice(
        r.activeVersion
          ? `${nf.format(r.version)}. sürüm kaldırıldı; ${nf.format(r.activeVersion)}. sürüm yeniden etkin.`
          : `${nf.format(r.version)}. sürüm kaldırıldı; eserde etkin metin kalmadı. Yeni dosya yükleyebilirsiniz.`,
      );
      await qc.invalidateQueries({ queryKey: ['editorial'] });
      onChanged();
    },
  });

  return (
    <Panel>
      <h2 className="px-1 text-[13px] font-extrabold">Eser bilgileri</h2>
      <div className="mt-2">
        <WorkInfo work={work} />
      </div>

      <div className="mt-3 border-t border-slate-100 pt-3">
        <h3 className="px-1 text-[12.5px] font-extrabold">Metin dosyası</h3>
        {active ? (
          <div className="mt-2 rounded-2xl border border-slate-100 bg-white/85 p-3 text-[12px]">
            <a href={deskApi.fileUrl(active.id)} className="block break-words font-semibold text-canvas-violet underline">
              {active.filename}
            </a>
            <p className="mt-0.5 text-[11px] leading-snug text-canvas-muted">
              {nf.format(active.version)}. sürüm · {fmtBytes(active.bytes)} · {nf.format(active.report.chapters ?? 0)} {unit.many} · {active.uploadedBy} ·{' '}
              {dateTime(active.uploadedAt)}
            </p>
            {active.report.structure ? (
              <p className="mt-1 text-[11.5px] leading-snug text-canvas-ink">{HOW[active.report.structure] ?? ''}</p>
            ) : (
              <p className="mt-1 text-[11.5px] leading-snug text-canvas-ink">
                Bu sürüm eski yöntemle ayrıldı; bölümler kitabınkiyle uyuşmayabilir. Kaldırıp aynı dosyayı yeniden yüklerseniz kitabın
                kendi bölümlerine göre ayrılır.
              </p>
            )}
            <div className="mt-2.5 flex flex-wrap items-start gap-1.5">
              <FileDrop<{ version: number }>
                size="button"
                accept=".docx,.pdf,.txt,.md"
                title="Dosyayı değiştir"
                run={(f) => deskApi.uploadManuscript(work.id, f)}
                onDone={async (r) => {
                  setNotice(`Yeni dosya ${nf.format(r.version)}. sürüm olarak yüklendi; önceki sürüm geçmişte duruyor.`);
                  await qc.invalidateQueries({ queryKey: ['editorial'] });
                  onChanged();
                }}
              />
              {!confirm && (
                <button type="button" className={btnGhost} onClick={() => setConfirm(true)}>
                  <Trash2 aria-hidden className="h-4 w-4" />
                  Kaldır
                </button>
              )}
            </div>
            {confirm && (
              <div className="mt-2.5 rounded-xl border border-canvas-coral/30 bg-canvas-coral/[0.06] p-2.5" role="group" aria-label="Kaldırma onayı">
                <p className="text-[12px] leading-snug">
                  {nf.format(active.version)}. sürüm kaldırılsın mı?{' '}
                  {fallback
                    ? `${nf.format(fallback.version)}. sürüm ve onun ${unit.many} kararları yeniden etkin olur.`
                    : 'Eserde etkin metin kalmaz; yeni dosya yükleyebilirsiniz.'}{' '}
                  Dosya ve bu sürümdeki kararlar silinmez, geçmişte «kaldırıldı» diye durur.
                </p>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  <button
                    type="button"
                    disabled={remove.isPending}
                    onClick={() => remove.mutate(active.id)}
                    className={`${btn} bg-canvas-coral/15 text-canvas-coral`}
                  >
                    {remove.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Trash2 aria-hidden className="h-4 w-4" />}
                    Evet, kaldır
                  </button>
                  <button type="button" className={btnGhost} disabled={remove.isPending} onClick={() => setConfirm(false)}>
                    Vazgeç
                  </button>
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="mt-2">
            <FileDrop<{ version: number }>
              size="sm"
              accept=".docx,.pdf,.txt,.md"
              title="Metin dosyası yükle"
              hint={`«${work.title}» için metin yüklenir; kitabın bölümlerine göre ayrılır.`}
              run={(f) => deskApi.uploadManuscript(work.id, f)}
              onDone={async (r) => {
                setNotice(`Metin ${nf.format(r.version)}. sürüm olarak yüklendi.`);
                await qc.invalidateQueries({ queryKey: ['editorial'] });
                onChanged();
              }}
            />
          </div>
        )}
        {remove.error && (
          <div className="mt-2">
            <Note tone="err">{errText(remove.error, 'Sürüm kaldırılamadı.')}</Note>
          </div>
        )}
        {notice && (
          <div className="mt-2">
            <Note tone="ok">{notice}</Note>
          </div>
        )}
        {others.length > 0 && (
          <details className="mt-2.5 px-1">
            <summary className="cursor-pointer select-none text-[11.5px] font-bold text-canvas-muted">
              Önceki sürümler ({nf.format(others.length)})
            </summary>
            <ul className="mt-1.5 space-y-1.5 text-[11.5px]">
              {others.map((v) => (
                <li key={v.id} className="min-w-0">
                  <a
                    href={deskApi.fileUrl(v.id)}
                    className={`block break-words font-semibold underline ${v.removedAt ? 'text-canvas-muted line-through decoration-canvas-muted/60' : 'text-canvas-violet'}`}
                  >
                    {nf.format(v.version)}. sürüm · {v.filename}
                  </a>
                  <span className="text-[11px] text-canvas-muted">
                    {v.removedAt ? `Kaldırıldı · ${v.removedBy ?? ''} · ${dateTime(v.removedAt)}` : `${nf.format(v.report.chapters ?? 0)} ${unitOf(v).many}`}
                  </span>
                </li>
              ))}
            </ul>
          </details>
        )}
      </div>
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
  const versions = detail.data?.versions ?? [];
  const activeId = detail.data ? (detail.data.activeFileId ?? versions.find((v) => !v.removedAt)?.id ?? null) : null;
  const unit = unitOf(versions.find((v) => v.id === activeId));
  const approved = chapters.filter((c) => c.status === 'onaylandi').length;
  const pending = chapters.reduce((a, c) => a + c.pending, 0);
  const err = errText(works.error || detail.error, 'Eser dosyaları okunamadı.');

  return (
    <ModuleFrame
      route="/redaksiyon"
      crumb="Redaksiyon"
      title="Metin işleme ve redaksiyon"
      lead="Eser metnini yükleyin; kitabın kendi bölümlerine ayrılır ve ölçülür. Zeki AI yazım ve üslup önerisi çıkarır, kararı siz verirsiniz. Kabul edilen öneri metne işlenir, ilk hâl saklanır."
      source={w ? w.title : 'Editoryal masa'}
    >
      {!ENGINE_ENABLED && <Note tone="warn">Zeki AI bağlantısı bu kurulumda tanımlı değil; ekrandaki bilgiler okunamaz. Sistem yöneticinize haber verin.</Note>}
      {err && <Note tone="err">{err}</Note>}

      {/* Birincil eylem: metin yükleme. Liste boşken de burada; bırakılan dosya eser dosyasını adından açar. */}
      <WorkUpload
        kind="manuscript"
        works={items}
        selected={workId}
        onUploaded={(id) => {
          setWorkId(id);
          setChapterId(null);
        }}
      />

      {w && chapters.length > 0 && (
        <KpiRow>
          <Kpi info={<SqlInfo k={kaynakOf(detail.data)} alan="_hepsi" label={unit.One} />} explain={unit.one === 'parça' ? 'Kitapta bölüm yapısı bulunamadı; metin yaklaşık eşit büyüklükte parçalara ayrıldı. Yeni sürüm yüklenince baştan ayrılır.' : 'Yüklenen metnin kitabın kendi bölüm yapısına göre ayrıldığı bölüm sayısı. Yeni sürüm yüklenince bölümler baştan kurulur.'} label={unit.One} value={nf.format(chapters.length)} help={activeId ? `Metnin ${nf.format(versions.find((v) => v.id === activeId)?.version ?? 0)}. sürümü` : ''} />
          <Kpi info={<SqlInfo k={kaynakOf(detail.data)} alan="_hepsi" label="Onaylanan" />} explain={`Editörün onayladığı ${unit.many} sayısı. Karar bekleyen önerisi olan ${unit.one} onaylanamaz.`} label="Onaylanan" value={nf.format(approved)} help={`${nf.format(chapters.length - approved)} ${unit.one} sürüyor`} />
          <Kpi info={<SqlInfo k={kaynakOf(detail.data)} alan="_hepsi" label="Karar bekleyen öneri" />} explain={`Zeki AI'ın çıkardığı, henüz kabul edilmemiş ya da yok sayılmamış yazım ve üslup önerileri; bütün ${unit.all} toplamı.`} label="Karar bekleyen öneri" value={nf.format(pending)} help="Kabul ya da ret bekliyor" />
          <Kpi info={<SqlInfo k={kaynakOf(detail.data)} alan="_hepsi" label="Kelime" />} explain="Güncel metnin kelime sayısı; kabul edilen öneriler dahil." label="Kelime" value={nf.format(chapters.reduce((a, c) => a + c.words, 0))} help="Güncel metin" />
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
            progress={(x) => (x.manuscript ? `${nf.format(x.chapters.approved)}/${nf.format(x.chapters.total)} ${unitOf(x.manuscript).one} onaylı` : 'Metin yüklenmedi')}
          />

          {w && <WorkFilePanel work={w} versions={versions} activeId={activeId} onChanged={refresh} />}

          {chapters.length > 0 && (
            <Panel>
              <h2 className="px-1 text-[13px] font-extrabold">{unit.Many}</h2>
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
                          {unit.numbered ? `${c.no}. ${c.title}` : c.title}
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
          <ChapterPane chapterId={chapterId} onChanged={refresh} unit={unit} />
        ) : (
          <Panel>
            <p className="py-10 text-center text-[12.5px] leading-snug text-canvas-muted">
              {w
                ? 'Bu eserde henüz metin yok. Üstteki yükleme alanına DOCX, PDF ya da TXT bırakın.'
                : 'Üstteki yükleme alanına metin dosyasını bırakın; eser dosyası adından açılır. Var olan bir eser için soldan seçin.'}
            </p>
          </Panel>
        )}
      </div>
    </ModuleFrame>
  );
}
