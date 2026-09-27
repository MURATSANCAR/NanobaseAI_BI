import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { FileText, Loader2 } from 'lucide-react';
import { download } from '../board/export';
import { EngineAuthError, proofingApi, type ProofReasonCode, type ProofVerdict, type ProofingCheck, type ProofingFinding, type ProofingReport, type ProofingSeverity } from '../engine';
import { Loading, Note, Pill, btnGhost, nf } from '../admin/ui';
import { Panel } from './kit';
import { ProofEvidence, ProofEvidenceSheet, SEVERITY, SEVERITY_ORDER, findingKey, inheritedLabel, sevOf, type Decide, type ScrollCue } from './ProofEvidence';
import { carriedFromOf, isCarriedReject, isPending, severityCounts } from './proofCarry';

/** M5: ZEKİ AI'ın kitabın metninde koştuğu otomatik son okuma denetimleri ve bulguları.
 *  Rapor köprüden kitap adıyla gelir; burada gösterim, yerel süzme ve editörün bulguya kararı vardır.
 *
 *  Liste sayfaya göre gruplu; bir bulguya (ya da sayfa başlığına) tıklamak kanıt panelini açar: sayfanın
 *  görseli, işaretli yer, alıntı, öneri ve karar düğmeleri oradadır. Karar («Doğru» / «Yanlış alarm» +
 *  gerekçe) insanın veri kaydıdır: kitabı düzeltmez, yalnız bulguya iliştirilir ve kuralın isabetini besler.
 *
 *  Varsayılan süzgeç: yalnız uyarı + hata, karar verilmişler gizli — editör açılışta bekleyen işi görür.
 *
 *  Aynı kitapta hatırlama: yeniden okumada aynı bulgu önceki okumadaki kararı alır (kart servisi eşler, yazmaz).
 *  Önceki okumada «yanlış alarm» denmiş bulgu listede görünmez ve sayaçlara girmez («N bulgu … gizlendi» notu);
 *  «karar verilenler» süzgecinde «önceki okumada yanlış alarm» rozetiyle durur ve «Geri al» ile tek dokunuşta listeye döner.
 *  «Doğru» denmiş olan listede kalır, «önceki okumada doğru» işaretiyle. */

/** WARN + ERROR: KPI ve özet satırındaki "ciddi" sayısı. */
export const seriousCount = (r: ProofingReport | undefined) => (r ? r.checks.reduce((n, c) => n + c.serious, 0) : 0);

const DESKTOP = '(min-width: 1024px)';
function useDesktop() {
  const [wide, setWide] = useState(() => typeof window !== 'undefined' && window.matchMedia(DESKTOP).matches);
  useEffect(() => {
    const mq = window.matchMedia(DESKTOP);
    const on = () => setWide(mq.matches);
    mq.addEventListener('change', on);
    return () => mq.removeEventListener('change', on);
  }, []);
  return wide;
}

const hoverable = '[@media(hover:hover)]:hover:bg-slate-200';

/** Süzme çipi: seçili olan mürekkep, diğerleri açık gri; sağında sayım rozeti. Basılınca hafif küçülür (btn ile aynı his). */
function Chip({ active, onClick, count, tone, children, title }: { active: boolean; onClick: () => void; count?: number; tone?: 'warn' | 'err' | 'ok' | 'muted'; children: ReactNode; title?: string }) {
  const badge = active ? 'bg-white/20 text-white' : { warn: 'bg-amber-100 text-amber-800', err: 'bg-red-100 text-red-700', ok: 'bg-emerald-100 text-emerald-700', muted: 'bg-slate-200/80 text-canvas-ink' }[tone ?? 'muted'];
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      title={title}
      className={`inline-flex min-h-8 max-w-full items-center gap-1.5 rounded-lg px-2 py-1 text-[11.5px] font-bold transition-transform duration-150 ease-out active:scale-[0.97] ${
        active ? 'bg-canvas-ink text-white' : `bg-slate-100 text-canvas-ink ${hoverable}`
      }`}
    >
      <span className="min-w-0 truncate">{children}</span>
      {count !== undefined && <span className={`shrink-0 rounded-md px-1 font-mono text-[10.5px] tabular-nums ${badge}`}>{nf.format(count)}</span>}
    </button>
  );
}

/** Denetim özeti tek satır çip: etiket · ciddi/toplam · isabet %. Tıklamak o denetime süzer. */
function CheckChip({ c, active, onClick }: { c: ProofingCheck; active: boolean; onClick: () => void }) {
  const failed = c.status === 'FAILED';
  const p = c.precision;
  const rateTone = p ? (p.rate >= 0.8 ? 'text-emerald-700' : p.rate >= 0.5 ? 'text-amber-800' : 'text-red-700') : 'text-canvas-muted';
  return (
    <button
      type="button"
      aria-pressed={active}
      disabled={failed && c.findings === 0}
      onClick={onClick}
      title={
        (failed ? `Denetim koşamadı${c.error ? `: ${c.error}` : ''}` : p ? `İsabet: ${nf.format(p.accepted)} doğru / ${nf.format(p.accepted + p.rejected)} karar` : 'Henüz karar yok') +
        (c.hidden ? ` · ${nf.format(c.hidden)} bulgu önceki okumadaki kararla gizli` : '')
      }
      className={`inline-flex min-h-8 max-w-full items-center gap-1.5 rounded-lg border px-2 py-1 text-[11.5px] transition-transform duration-150 ease-out active:scale-[0.97] disabled:opacity-60 disabled:active:scale-100 ${
        active ? 'border-canvas-ink bg-canvas-ink text-white' : `border-slate-200 bg-white/85 text-canvas-ink ${hoverable}`
      }`}
    >
      <span className="min-w-0 truncate font-bold">{c.label}</span>
      {failed ? (
        <span className={`shrink-0 rounded-md px-1 text-[10.5px] font-bold ${active ? 'bg-white/20' : 'bg-red-100 text-red-700'}`}>koşamadı</span>
      ) : (
        <span className={`shrink-0 font-mono text-[10.5px] tabular-nums ${active ? 'text-white/80' : c.serious > 0 ? 'text-amber-800' : 'text-canvas-muted'}`}>
          {nf.format(c.serious)}/{nf.format(c.findings)}
        </span>
      )}
      <span className={`shrink-0 font-mono text-[10.5px] tabular-nums ${active ? 'text-white/80' : rateTone}`}>{p ? `%${Math.round(p.rate * 100)}` : '—'}</span>
    </button>
  );
}

type Row = { key: string; n: number; f: ProofingFinding };

type Group = { page: number | null; rows: Row[] };

function FindingRow({ r, active, onPick, rowRef, onUndo, busy }: { r: Row; active: boolean; onPick: () => void; rowRef?: (el: HTMLButtonElement | null) => void; onUndo?: () => void; busy?: boolean }) {
  const { f, n } = r;
  const sev = sevOf(f);
  const d = f.decision;
  // Önceki okumada «doğru» denmiş bulgu bekleyen iş gibi durur (soluklaşmaz); öbür kararlılar soluk.
  const dim = d && !(d.inherited && d.verdict === 'ACCEPT');
  return (
    <li className="flex flex-col gap-1 sm:flex-row sm:items-stretch sm:gap-1.5">
      <button
        ref={rowRef}
        type="button"
        aria-current={active ? 'true' : undefined}
        onClick={onPick}
        className={`grid min-w-0 flex-1 grid-cols-[auto_minmax(0,1fr)] gap-x-2 rounded-xl border px-2.5 py-2 text-left text-[12.5px] transition-[background-color,box-shadow] duration-150 ease-out ${
          active ? 'border-canvas-violet/50 bg-canvas-violet/[0.06] shadow-[inset_2px_0_0_0_#7C5CFF]' : `border-slate-100 bg-white/85 [@media(hover:hover)]:hover:bg-slate-50 ${dim ? 'opacity-70' : ''}`
        }`}
      >
        <span className={`mt-0.5 font-mono text-[11px] font-extrabold tabular-nums ${active ? 'text-canvas-violet' : 'text-canvas-muted'}`}>{n}</span>
        <span className="min-w-0">
          <span className="flex flex-wrap items-center gap-1.5">
            <Pill tone={sev.tone}>{sev.label}</Pill>
            <span className="min-w-0 truncate text-[11px] text-canvas-muted">{f.label}</span>
            {d && !d.inherited && <Pill tone={d.verdict === 'ACCEPT' ? 'ok' : 'muted'}>{d.verdict === 'ACCEPT' ? 'Doğru' : 'Yanlış alarm'}</Pill>}
            {d?.inherited && d.verdict === 'ACCEPT' && <Pill tone="ok">önceki okumada doğru</Pill>}
            {d?.inherited && d.verdict === 'REJECT' && <Pill tone="violet">önceki okumada yanlış alarm</Pill>}
          </span>
          <span className="mt-0.5 line-clamp-2 break-words font-semibold leading-snug">{f.message}</span>
          {f.quote && <span className="mt-0.5 block truncate text-[11.5px] text-canvas-ink/70">“{f.quote}”</span>}
        </span>
      </button>
      {onUndo && (
        <button
          type="button"
          onClick={onUndo}
          disabled={busy}
          title={`Önceki okumanın kararı bu bulguya uygulanmaz; bulgu yeniden listeye girer (${inheritedLabel(f)}).`}
          className={`${btnGhost} shrink-0 self-end px-3 text-[11.5px] sm:self-auto`}
        >
          Geri al
        </button>
      )}
    </li>
  );
}

export function ProofFindings({
  report,
  loading,
  error,
  picker,
  idle,
}: {
  report: ProofingReport | undefined;
  loading: boolean;
  error: string | null;
  /** Rapor bir esere değil doğrudan motordaki kitaba bağlıyken üstte gösterilen kitap seçici. */
  picker?: ReactNode;
  /** Sorgu çalışmıyorken (kitap seçilmemiş) gösterilen metin; verilmezse yükleniyor, null ise hiçbir şey gösterilir. */
  idle?: string | null;
}) {
  const qc = useQueryClient();
  const desktop = useDesktop();
  const [check, setCheck] = useState<string | null>(null);
  // Varsayılan: hata + uyarı açık, bilgi kapalı; karar verilmişler gizli.
  const [sev, setSev] = useState<Set<ProofingSeverity>>(() => new Set(['ERROR', 'WARN']));
  const [showDecided, setShowDecided] = useState(false);
  const [activeKey, setActiveKey] = useState<string | null>(null);
  /** Sayfa başlığına tıklanınca sayfa açılır, bulgu seçilmez; bu durumda panelde o sayfanın ilk bulgusu gösterilir. */
  const [activePage, setActivePage] = useState<number | null | undefined>(undefined);
  /** Her seçimde artan kaydırma isteği: panel işaret kutusunu görünür alana getirir. Klavyeyle anlık. */
  const [cue, setCue] = useState<ScrollCue>({ seq: 0, instant: false });
  const bookId = report?.bookId ?? null;

  // Karar yazma: kim olduğu oturumdan gelir; tekrar basmak yeni karar yazar. Kaydedilince rapor yeniden okunur (karar + isabet birlikte gelir).
  const decideM = useMutation({
    mutationFn: (v: { findingId: string; verdict: ProofVerdict | 'CLEAR'; reasonCode?: ProofReasonCode; note?: string; carriedFrom?: string }) =>
      proofingApi.decide({ bookId: bookId as string, ...v }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['editorial', 'proofing'] }),
  });
  const decide: Decide | null = bookId ? (findingId, verdict, reasonCode, note, carriedFrom) => decideM.mutateAsync({ findingId, verdict, reasonCode, note, carriedFrom }) : null;
  const [undoErr, setUndoErr] = useState<string | null>(null);
  /** Taşınan «yanlış alarm»ı geri al: bulgu kararsız kalır ve listeye döner. */
  const undo = (f: ProofingFinding) => {
    if (!decide || !f.id) return;
    setUndoErr(null);
    decide(f.id, 'CLEAR', undefined, undefined, carriedFromOf(f)).catch((e: unknown) =>
      setUndoErr(e instanceof EngineAuthError ? 'Oturum gerekli.' : e instanceof Error ? e.message : 'Geri alınamadı.'),
    );
  };

  const findings = report?.findings ?? [];
  const keyed = useMemo(() => findings.map((f, i) => ({ key: findingKey(f, i), f })), [findings]);
  // Sayaçlar önceki okumada «yanlış alarm» denmiş (taşınan) bulguları saymaz; kaçının gizlendiği ayrıca yazılır.
  const sevCounts = useMemo(() => severityCounts(findings), [findings]);
  const hiddenCount = useMemo(() => findings.filter(isCarriedReject).length, [findings]);
  const decidedCount = useMemo(() => findings.filter((f) => !isPending(f)).length, [findings]);

  const shown = useMemo(
    () => keyed.filter(({ f }) => (!check || f.check === check) && sev.has(f.severity) && (showDecided || isPending(f))),
    [keyed, check, sev, showDecided],
  );

  /** Sayfaya göre gruplar; sayfasızlar en üstte «Kitap geneli». Grup içi sıra: ciddiyet, sonra rapor sırası. Numara grup içinde. */
  const groups = useMemo<Group[]>(() => {
    const byPage = new Map<number | null, Row[]>();
    for (const r of shown) {
      const list = byPage.get(r.f.page) ?? [];
      list.push({ ...r, n: 0 });
      byPage.set(r.f.page, list);
    }
    const pages = [...byPage.keys()].sort((a, b) => (a === null ? -1 : b === null ? 1 : a - b));
    return pages.map((page) => {
      const rows = (byPage.get(page) ?? []).sort((a, b) => SEVERITY_ORDER.indexOf(a.f.severity) - SEVERITY_ORDER.indexOf(b.f.severity));
      return { page, rows: rows.map((r, i) => ({ ...r, n: i + 1 })) };
    });
  }, [shown]);
  const flat = useMemo(() => groups.flatMap((g) => g.rows), [groups]);

  // Panelin sayfası: seçili bulgunun sayfası; bulgu yoksa başlıktan açılan sayfa.
  const activeRow = activeKey ? (flat.find((r) => r.key === activeKey) ?? keyed.find((k) => k.key === activeKey)) : undefined;
  const panelPage: number | null | undefined = activeRow ? activeRow.f.page : activePage;
  const panelOpen = panelPage !== undefined;
  /** Paneldeki işaretler: o sayfanın süzgeçten geçen bulguları; seçili bulgu süzgeç dışında kaldıysa (örn. az önce karar verildi) yine gösterilir. */
  const marks = useMemo<Row[]>(() => {
    if (!panelOpen) return [];
    const g = groups.find((x) => x.page === panelPage);
    const rows = g ? [...g.rows] : [];
    if (activeRow && !rows.some((r) => r.key === activeRow.key)) rows.push({ key: activeRow.key, f: activeRow.f, n: rows.length + 1 });
    return rows;
  }, [panelOpen, panelPage, groups, activeRow]);

  const rowEls = useRef(new Map<string, HTMLButtonElement>());
  const lastIndex = useRef(0);
  const openedFrom = useRef<HTMLElement | null>(null);

  const pick = useCallback((key: string) => {
    setActiveKey(key);
    setActivePage(undefined);
    setCue((c) => ({ seq: c.seq + 1, instant: false }));
  }, []);
  const openPage = (page: number | null) => {
    setActiveKey(null);
    setActivePage(page);
    setCue((c) => ({ seq: c.seq + 1, instant: false }));
  };
  const close = useCallback(() => {
    setActiveKey(null);
    setActivePage(undefined);
    const el = openedFrom.current;
    openedFrom.current = null;
    if (el && document.contains(el)) el.focus({ preventScroll: true });
  }, []);

  useEffect(() => {
    const i = flat.findIndex((r) => r.key === activeKey);
    if (i >= 0) lastIndex.current = i;
  }, [flat, activeKey]);

  // Klavye: ↑/↓ bulgular arasında (seçili bulgu süzgeçten çıktıysa kaldığı yerden), Esc kapatır. Yazı alanlarında devre dışı.
  useEffect(() => {
    if (!panelOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.defaultPrevented) return;
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT' || t.isContentEditable)) return;
      if (e.key === 'Escape') {
        e.preventDefault();
        close();
        return;
      }
      if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
      if (!flat.length) return;
      e.preventDefault();
      const cur = flat.findIndex((r) => r.key === activeKey);
      let next: number;
      if (cur >= 0) next = Math.min(Math.max(cur + (e.key === 'ArrowDown' ? 1 : -1), 0), flat.length - 1);
      else if (activeKey) next = Math.min(lastIndex.current, flat.length - 1); // seçili bulgu artık listede değil: kaldığı sıradan devam
      else {
        const g = groups.find((x) => x.page === panelPage); // sayfa başlığından açıldı: o sayfanın ilk bulgusu
        next = g && g.rows.length ? flat.indexOf(g.rows[0]) : 0;
      }
      const key = flat[next].key;
      setActiveKey(key);
      setActivePage(undefined);
      setCue((c) => ({ seq: c.seq + 1, instant: true }));
      rowEls.current.get(key)?.scrollIntoView({ block: 'nearest' });
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [panelOpen, flat, groups, activeKey, panelPage, close]);

  // Rapor değişince (başka kitap) panel kapanır.
  useEffect(() => {
    setActiveKey(null);
    setActivePage(undefined);
  }, [bookId]);

  const panelProps = { bookId, bookTitle: report?.bookTitle ?? null, page: panelPage ?? null, marks, activeKey: activeRow?.key ?? null, onPick: pick, onClose: close, decide, busy: decideM.isPending, cue };

  let body: ReactNode;
  if (error) body = <Note tone="err">{error}</Note>;
  else if (loading) body = <Loading />;
  else if (!report) body = idle === undefined ? <Loading /> : idle ? <Empty>{idle}</Empty> : null;
  else if (!report.configured) body = <Empty>ZEKİ AI motor bağlantısı tanımlı değil; otomatik son okuma bu kurulumda kapalı.</Empty>;
  else if (!report.bookId) body = <Empty>Bu eser motorda henüz okunmamış. Kitap adı motordaki adla birebir eşleşmeli.</Empty>;
  else if (!report.checks.length) body = <Empty>Eser okunmuş, denetimler henüz koşmamış. Motor sırası gelince burada görünür.</Empty>;
  else
    body = (
      <>
        <div className="mt-2 flex flex-wrap gap-1.5" role="group" aria-label="Denetimler">
          {report.checks.map((c) => (
            <CheckChip key={c.name} c={c} active={check === c.name} onClick={() => setCheck(check === c.name ? null : c.name)} />
          ))}
        </div>
        {report.checks.some((c) => c.status === 'FAILED' && c.error) && (
          <div className="mt-1.5">
            <Note tone="err">
              Koşamayan denetim var:{' '}
              {report.checks
                .filter((c) => c.status === 'FAILED')
                .map((c) => `${c.label}${c.error ? ` (${c.error})` : ''}`)
                .join('; ')}
            </Note>
          </div>
        )}

        {findings.length === 0 ? (
          <div className="mt-3">
            <Note tone="ok">Denetimler koştu, bulgu yok.</Note>
          </div>
        ) : (
          <div className={`mt-3 ${desktop && panelOpen ? 'grid grid-cols-[minmax(0,5fr)_minmax(0,6fr)] items-start gap-3' : ''}`}>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Süzgeç">
                {SEVERITY_ORDER.filter((s) => sevCounts[s] > 0).map((s) => (
                  <Chip
                    key={s}
                    active={sev.has(s)}
                    count={sevCounts[s]}
                    tone={SEVERITY[s].tone}
                    onClick={() =>
                      setSev((prev) => {
                        const next = new Set(prev);
                        if (next.has(s)) next.delete(s);
                        else next.add(s);
                        return next;
                      })
                    }
                  >
                    {SEVERITY[s].label}
                  </Chip>
                ))}
                <span aria-hidden className="mx-0.5 h-5 w-px bg-slate-200" />
                <Chip active={showDecided} count={decidedCount} tone="ok" onClick={() => setShowDecided((v) => !v)} title="Karar verilmiş bulguları göster/gizle">
                  karar verilenler
                </Chip>
                {check && (
                  <Chip active onClick={() => setCheck(null)} title="Denetim süzgecini kaldır">
                    {report.checks.find((c) => c.name === check)?.label ?? check} ×
                  </Chip>
                )}
                <span className="ml-auto whitespace-nowrap font-mono text-[11px] tabular-nums text-canvas-muted">
                  {nf.format(shown.length)} / {nf.format(findings.length)} bulgu
                </span>
              </div>

              {hiddenCount > 0 && (
                <p className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11.5px] leading-snug text-canvas-muted">
                  <span>
                    {nf.format(hiddenCount)} bulgu önceki okumadaki «yanlış alarm» kararıyla gizlendi; sayılara girmez.
                  </span>
                  {!showDecided && (
                    <button type="button" onClick={() => setShowDecided(true)} className="font-bold text-canvas-violet underline-offset-2 [@media(hover:hover)]:hover:underline">
                      göster
                    </button>
                  )}
                </p>
              )}
              {undoErr && (
                <div className="mt-1.5">
                  <Note tone="err">{undoErr}</Note>
                </div>
              )}

              {flat.length === 0 ? (
                <p className="py-6 text-center text-[12.5px] leading-snug text-canvas-muted">
                  Bu süzgeçte bulgu yok.
                  {!showDecided && decidedCount > 0 ? ' Karar verilenler gizli.' : ''}
                  {!sev.has('INFO') && sevCounts.INFO > 0 ? ' Bilgi düzeyi gizli.' : ''}
                </p>
              ) : (
                <div className="mt-2 space-y-3">
                  {groups.map((g) => {
                    const pageActive = panelOpen && panelPage === g.page;
                    return (
                      <section key={g.page ?? 'book'} aria-label={g.page === null ? 'Kitap geneli' : `Sayfa ${g.page}`}>
                        <button
                          type="button"
                          onClick={(e) => {
                            openedFrom.current = e.currentTarget;
                            openPage(g.page);
                          }}
                          aria-pressed={pageActive}
                          className={`flex w-full items-baseline gap-2 rounded-lg px-2 py-1 text-left transition-[background-color] duration-150 ease-out ${pageActive ? 'bg-canvas-violet/10' : '[@media(hover:hover)]:hover:bg-slate-100'}`}
                        >
                          <span className={`text-[12px] font-extrabold ${pageActive ? 'text-canvas-violet' : ''}`}>{g.page === null ? 'Kitap geneli' : `s. ${nf.format(g.page)}`}</span>
                          <span className="font-mono text-[11px] tabular-nums text-canvas-muted">
                            {nf.format(g.rows.length)} bulgu{g.page !== null && bookId ? ' · sayfayı aç' : ''}
                          </span>
                        </button>
                        <ul className="mt-1 space-y-1">
                          {g.rows.map((r) => (
                            <FindingRow
                              key={r.key}
                              r={r}
                              active={activeRow?.key === r.key}
                              onUndo={isCarriedReject(r.f) && decide ? () => undo(r.f) : undefined}
                              busy={decideM.isPending}
                              rowRef={(el) => {
                                if (el) rowEls.current.set(r.key, el);
                                else rowEls.current.delete(r.key);
                              }}
                              onPick={() => {
                                openedFrom.current = rowEls.current.get(r.key) ?? null;
                                pick(r.key);
                              }}
                            />
                          ))}
                        </ul>
                      </section>
                    );
                  })}
                </div>
              )}
            </div>

            {panelOpen && (desktop ? <ProofEvidence {...panelProps} /> : <ProofEvidenceSheet {...panelProps} />)}
          </div>
        )}
      </>
    );

  return (
    <Panel>
      <div className="flex flex-wrap items-center justify-between gap-2 px-1">
        <h2 className="text-[13px] font-extrabold">ZEKİ AI son okuma</h2>
        {bookId && report?.checks.length ? <WordExport bookId={bookId} /> : null}
      </div>
      <p className="mt-1 px-1 text-[11.5px] leading-snug text-canvas-muted">
        ZEKİ AI, kitabın metnini okuyup otomatik denetimleri koşar; bulgular yalnız öneridir, kontrol listesini etkilemez. Bulguya tıklayın: sayfa ve işaretli yer açılır, kararı oradan verirsiniz. Karar bulguya iliştirilir ve kuralın isabetini ölçer; kitabı değiştirmez.
        {report?.bookTitle ? ` Eşleşen kitap: ${report.bookTitle}.` : ''}
      </p>
      {picker ? <div className="mt-2">{picker}</div> : null}
      <div className="mt-2">{body}</div>
    </Panel>
  );
}

/** Bulgular kitabın metnine Word yorumu olarak işlenmiş .docx; redaksiyon Word'de yapılır. */
function WordExport({ bookId }: { bookId: string }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const run = async () => {
    setBusy(true);
    setErr(null);
    try {
      const { blob, name } = await proofingApi.exportDocx(bookId);
      download(name, blob);
    } catch (e) {
      setErr(e instanceof EngineAuthError ? 'Oturum gerekli.' : e instanceof Error ? e.message : 'Word dosyası üretilemedi.');
    } finally {
      setBusy(false);
    }
  };
  return (
    <span className="flex items-center gap-2">
      {err && <span className="text-[11px] text-red-700">{err}</span>}
      <button
        type="button"
        onClick={() => void run()}
        disabled={busy}
        title="Bulgular metne Word yorumu olarak işlenir; yanlış alarm denenler aktarılmaz."
        className="inline-flex min-h-8 items-center gap-1.5 rounded-lg bg-slate-100 px-2.5 py-1 text-[11.5px] font-bold text-canvas-ink transition-transform duration-150 ease-out active:scale-[0.97] disabled:opacity-60 [@media(hover:hover)]:hover:bg-slate-200"
      >
        {busy ? <Loader2 aria-hidden className="h-3.5 w-3.5 animate-spin" /> : <FileText aria-hidden className="h-3.5 w-3.5" />}
        {busy ? 'Hazırlanıyor…' : "Word'e aktar"}
      </button>
    </span>
  );
}

function Empty({ children }: { children: ReactNode }) {
  return <p className="py-6 text-center text-[12.5px] leading-snug text-canvas-muted">{children}</p>;
}
