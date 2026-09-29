import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { BellRing, ChevronDown, Search, X } from 'lucide-react';
import { ENGINE_ENABLED, type IntakeCard } from '../../engine';
import { intakeBoardOptions } from '../queries';
import { Note, btnGhost, errText, field, nf } from '../../admin/ui';
import { dateTime, stamp } from '../../format';
import { ModuleFrame, Panel, useDebounced } from '../kit';
import { ProjectCard, TodoGroups, waitingText } from './parts';
import { FACETS, NONE, activeCount, facetOptions, matches, readFilters, withFilter, withoutFilters, type Facet, type IntakeFilters } from './filters';
import MailApplicationsBox from '../../mailbox/ApplicationsBox';
import SqlInfo from '../../components/SqlInfo';
import { kaynakOf } from '../../components/kaynakOf';
import { EmptyHint, Explain } from '../../components/Explain';

/** Yazar giriş süreci: müşterinin 9 adımı üç evrede. Her kart bir CRM projesi; sütunda en uzun bekleyen üstte. */

const STEP_PAGE = 30;


function Column({ no, title, lead, steps, cards, onClear }: { no: number; title: string; lead: string; steps: string[]; cards: IntakeCard[]; onClear?: () => void }) {
  const [shown, setShown] = useState(STEP_PAGE);
  return (
    <Panel>
      <div className="flex items-center justify-between gap-2">
        <h2 className="flex min-w-0 items-center gap-2 text-[15px] font-extrabold tracking-tight">
          <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-canvas-violet/10 font-mono text-[12px] text-canvas-violet">{no}</span>
          {title}
        </h2>
        <span className="shrink-0 font-mono text-[12px] font-bold tabular-nums text-canvas-muted">{nf.format(cards.length)} proje</span>
      </div>
      <p className="mt-1 text-[12px] text-canvas-muted">{lead}</p>
      <p className="mt-0.5 text-[11px] leading-snug text-canvas-muted">{steps.join(' · ')}</p>
      {cards.length === 0 ? (
        <div className="mt-3">
          <EmptyHint
            title={onClear ? 'Süzgece uyan proje yok' : 'Bu evrede proje yok'}
            why={onClear ? 'Bu evrede seçtiğiniz süzgeçlere uyan proje yok. Bir süzgeci kaldırın ya da hepsini temizleyin.' : 'Şu an bu evrenin adımlarında bekleyen proje bulunmuyor.'}
            action={
              onClear && (
                <button type="button" className={btnGhost} onClick={onClear}>
                  Süzgeçleri temizle
                </button>
              )
            }
          />
        </div>
      ) : (
        <ul className="mt-3 space-y-2">
          {cards.slice(0, shown).map((c) => (
            <ProjectCard key={c.id} c={c} showEditor={no === 1} />
          ))}
        </ul>
      )}
      {cards.length > shown && (
        <button type="button" className={`${btnGhost} mt-3 w-full`} onClick={() => setShown((n) => n + STEP_PAGE)}>
          {nf.format(Math.min(STEP_PAGE, cards.length - shown))} proje daha göster ({nf.format(cards.length - shown)} kaldı)
        </button>
      )}
    </Panel>
  );
}

function Folded({ title, cards }: { title: string; cards: IntakeCard[] }) {
  const [open, setOpen] = useState(false);
  const [shown, setShown] = useState(STEP_PAGE);
  if (!cards.length) return null;
  return (
    <Panel>
      <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open} className="flex w-full items-center justify-between gap-2 text-left">
        <span className="text-[13.5px] font-extrabold">
          {title} <span className="font-mono font-semibold tabular-nums text-canvas-muted">({nf.format(cards.length)})</span>
        </span>
        <ChevronDown aria-hidden className={`h-4 w-4 shrink-0 text-canvas-muted transition-transform duration-200 ease-out ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <>
          <ul className="mt-3 grid gap-2 md:grid-cols-2 xl:grid-cols-3">
            {cards.slice(0, shown).map((c) => (
              <ProjectCard key={c.id} c={c} />
            ))}
          </ul>
          {cards.length > shown && (
            <button type="button" className={`${btnGhost} mt-3 w-full`} onClick={() => setShown((n) => n + STEP_PAGE)}>
              {nf.format(cards.length - shown)} proje daha var, göster
            </button>
          )}
        </>
      )}
    </Panel>
  );
}

export function TodoStrip({ todo, all = false }: { todo: IntakeCard[]; all?: boolean }) {
  if (!todo.length) return null;
  if (all)
    return (
      <section className="rounded-2xl border border-amber-200 bg-amber-50/90 p-3 sm:rounded-3xl sm:p-4">
        <h2 className="flex items-center gap-2 text-[14px] font-extrabold text-amber-900">
          <BellRing aria-hidden className="h-4 w-4" />
          Editörlerin bekleyen işleri: {nf.format(todo.length)}
        </h2>
        <p className="mt-0.5 text-[11.5px] text-amber-900/80">Yönetici görünümü. Editörün adına tıklayın, işleri açılır.</p>
        <div className="mt-2">
          <TodoGroups todo={todo} />
        </div>
      </section>
    );
  return (
    <section className="rounded-2xl border border-amber-200 bg-amber-50/90 p-3 sm:rounded-3xl sm:p-4">
      <h2 className="flex items-center gap-2 text-[14px] font-extrabold text-amber-900">
        <BellRing aria-hidden className="h-4 w-4" />
        Sizi bekleyen {nf.format(todo.length)} iş
      </h2>
      <ul className="mt-2 space-y-1.5">
        {todo.map((c) => (
          <li key={c.id}>
            <Link
              to={`/yazar-giris/${c.id}`}
              className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5 rounded-xl bg-white/90 px-3 py-2 text-[12.5px] transition-transform duration-150 ease-out hover:bg-white active:scale-[0.99]"
            >
              <span className="min-w-0 break-words">
                <b className="font-extrabold">{c.name || 'Adsız proje'}</b>
                <span className="text-canvas-muted"> — {c.line.charAt(0).toLocaleLowerCase('tr') + c.line.slice(1)}</span>
              </span>
              <span className={`shrink-0 font-mono text-[11.5px] tabular-nums ${c.late ? 'font-bold text-red-700' : 'text-canvas-muted'}`}>
                {waitingText(c)}
                {c.late ? ', gecikti' : ''}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** Süzgecin ekrandaki adı, «hepsi» ve «boş» seçeneğinin sözü. */
const FACET_TEXT: Record<Facet, { label: string; all: string; none: string }> = {
  brand: { label: 'Marka', all: 'Bütün markalar', none: 'Marka girilmemiş' },
  editor: { label: 'Editör', all: 'Bütün editörler', none: 'Editör atanmamış' },
  step: { label: 'Adım', all: 'Bütün adımlar', none: 'Adım yok' },
  type: { label: 'Proje türü', all: 'Bütün proje türleri', none: 'Tür girilmemiş' },
  year: { label: 'Başvuru yılı', all: 'Bütün yıllar', none: 'Tarih yok' },
};

function FacetSelect({
  facet,
  cards,
  f,
  stepTitle,
  onChange,
}: {
  facet: Facet;
  cards: IntakeCard[];
  f: IntakeFilters;
  stepTitle: (no: number) => string;
  onChange: (v: string) => void;
}) {
  const t = FACET_TEXT[facet];
  const opts = facetOptions(cards, f, facet);
  const name = (v: string) => (v === NONE ? t.none : facet === 'step' ? `${v}. ${stepTitle(Number(v))}` : v);
  const on = !!f[facet];
  return (
    <label className="block min-w-0">
      <span className="mb-0.5 block px-0.5 text-[11px] font-bold text-canvas-muted">{t.label}</span>
      <select
        value={f[facet]}
        onChange={(e) => onChange(e.target.value)}
        className={`${field} truncate ${on ? 'border-canvas-violet bg-canvas-violet/5 text-canvas-violet' : ''}`}
      >
        <option value="">{t.all}</option>
        {opts.map((o) => (
          <option key={o.value} value={o.value}>
            {name(o.value)} ({nf.format(o.count)})
          </option>
        ))}
      </select>
    </label>
  );
}

export default function IntakeBoardScreen() {
  const board = useQuery(intakeBoardOptions());
  const [params, setParams] = useSearchParams();
  const f = useMemo(() => readFilters(params), [params]);
  const [text, setText] = useState(f.q);
  const [phase, setPhase] = useState(1);
  const q = useDebounced(text.trim(), 200);
  const d = board.data;

  const set = (key: keyof IntakeFilters, value: string | boolean) => setParams((p) => withFilter(p, key, value), { replace: true });
  const clear = () => {
    setText('');
    setParams((p) => withoutFilters(p), { replace: true });
  };
  // Aramanın yazılan hâli adrese gecikmeyle gider; adres dışarıdan değişirse (temizle, geri tuşu) kutu da değişir.
  useEffect(() => {
    if (q !== f.q) set('q', q);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q]);
  useEffect(() => {
    if (f.q !== q) setText(f.q);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [f.q]);

  // Telefonda tek evre görünür: adım seçilince o adımın evresine geçilir, yoksa boş sütun görülürdü.
  const stepPhase = d?.phases.find((ph) => ph.steps.some((s) => String(s.no) === f.step))?.no;
  useEffect(() => {
    if (stepPhase) setPhase(stepPhase);
  }, [stepPhase]);

  const items = useMemo(() => d?.items ?? [], [d]);
  const filtered = useMemo(() => items.filter((c) => matches(c, f)), [items, f]);
  const completed = useMemo(() => (d?.completed ?? []).filter((c) => matches(c, f)), [d, f]);
  const closed = useMemo(() => (d?.closed ?? []).filter((c) => matches(c, f)), [d, f]);
  const active = activeCount(f);
  const stepTitle = (no: number) => d?.steps.find((s) => s.no === no)?.title ?? '';
  const lateCount = items.filter((c) => c.late && matches(c, f, 'late')).length;
  const mineCount = items.filter((c) => c.mine && matches(c, f, 'mine')).length;
  const facetName = (k: Facet) => (f[k] === NONE ? FACET_TEXT[k].none : k === 'step' ? `${f[k]}. ${stepTitle(Number(f[k]))}` : f[k]);
  // Açık süzgeçlerin çipleri: dokununca yalnız o süzgeç kalkar.
  const chips: Array<{ key: keyof IntakeFilters; text: string; off: string | boolean }> = [
    ...(f.q ? [{ key: 'q' as const, text: `Arama: ${f.q}`, off: '' }] : []),
    ...FACETS.filter((k) => f[k]).map((k) => ({ key: k, text: `${FACET_TEXT[k].label}: ${facetName(k)}`, off: '' })),
    ...(f.late ? [{ key: 'late' as const, text: 'Yalnız gecikenler', off: false }] : []),
    ...(f.mine ? [{ key: 'mine' as const, text: 'Yalnız benimkiler', off: false }] : []),
  ];
  const removeChip = (key: keyof IntakeFilters, off: string | boolean) => {
    if (key === 'q') setText('');
    set(key, off);
  };

  const err = errText(board.error, 'Süreç okunamadı.');
  const lead = d?.since
    ? `${dateTime(d.since)} sonrası açılan yeni ve yenileme projeleri. Veriler CRM'den kendiliğinden gelir, beş dakikada bir tazelenir.`
    : "Başvurudan stok kartına 9 adım. Veriler CRM'den kendiliğinden gelir.";

  const search = (
    <label className="relative block">
      <span className="sr-only">Kitap, yazar ya da editör ara</span>
      <Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-canvas-muted" />
      <input type="search" value={text} onChange={(e) => setText(e.target.value)} placeholder="Kitap, yazar ya da editör ara" className={`${field} pl-9`} />
    </label>
  );

  return (
    <ModuleFrame
      route="/yazar-giris"
      crumb="Yazar giriş süreci"
      title="Yazar giriş süreci"
      lead={lead}
      source={d?.updatedAt ? `Son okuma ${stamp(d.updatedAt * 1000)}` : 'Kaynak: CRM projeleri'}
      aside={search}
    >
      {!ENGINE_ENABLED && <Note tone="warn">Zeki AI bağlantısı bu kurulumda tanımlı değil; ekrandaki bilgiler okunamaz. Sistem yöneticinize haber verin.</Note>}
      {err && <Note tone="err">{err}</Note>}
      {d?.error && <Note tone="warn">{d.error}</Note>}
      {d?.loading && <Note tone="info">CRM ilk kez okunuyor; birkaç dakika sürebilir. Ekran kendiliğinden yenilenecek.</Note>}

      {d && !d.loading && (
        <div className="flex justify-end px-1 text-[11.5px] text-canvas-muted">
          <span className="inline-flex items-center gap-1">
            Proje, bekleyen iş ve gecikme sayıları
            <SqlInfo k={kaynakOf(d)} alan="_hepsi" label="Yazar giriş panosu" />
          </span>
        </div>
      )}
      {d && <TodoStrip todo={d.todo} all={d.todoScope === 'all'} />}
      <MailApplicationsBox />

      {d && !d.loading && (
        <section aria-label="Süzgeçler" className="space-y-2 px-1">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
            {FACETS.map((k) => (
              <FacetSelect key={k} facet={k} cards={items} f={f} stepTitle={stepTitle} onChange={(v) => set(k, v)} />
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-2 text-[12px]">
            <button type="button" aria-pressed={f.late} onClick={() => set('late', !f.late)} className={`${btnGhost} ${f.late ? 'ring-2 ring-canvas-violet' : ''}`}>
              Yalnız gecikenler ({nf.format(lateCount)})
            </button>
            <button type="button" aria-pressed={f.mine} onClick={() => set('mine', !f.mine)} className={`${btnGhost} ${f.mine ? 'ring-2 ring-canvas-violet' : ''}`}>
              Yalnız benimkiler ({nf.format(mineCount)})
            </button>
            <span className="inline-flex items-center gap-1 text-canvas-muted">
              Kart altındaki çizgi
              <Explain label="İlerleme çizgisi">
                9 adımın her biri bir parçadır; evreler arasında boşluk vardır. Yeşil biten adım, mor şu anki adım, kırmızımsı gecikmiş şu anki adım, gri henüz gelinmemiş adımdır.
              </Explain>
            </span>
            <span className="text-canvas-muted">
              Gecikme: bir adımda {nf.format(d.lateDays)} günden uzun bekleme.
              {d.lastBoard && <> Son kurul {dateTime(d.lastBoard)}.</>}
            </span>
          </div>
          {active > 0 && (
            <div className="flex flex-wrap items-center gap-1.5 rounded-2xl bg-canvas-violet/5 px-2.5 py-2 text-[12px]">
              <span className="mr-1 font-semibold">
                Süzgece uyan: <b className="font-mono tabular-nums">{nf.format(filtered.length)}</b> süren
                {completed.length > 0 && (
                  <>
                    , <b className="font-mono tabular-nums">{nf.format(completed.length)}</b> tamamlanan
                  </>
                )}
                {closed.length > 0 && (
                  <>
                    , <b className="font-mono tabular-nums">{nf.format(closed.length)}</b> kapanan
                  </>
                )}{' '}
                proje
              </span>
              {chips.map((c) => (
                <button
                  key={c.key}
                  type="button"
                  onClick={() => removeChip(c.key, c.off)}
                  aria-label={`${c.text} süzgecini kaldır`}
                  className="inline-flex min-h-9 max-w-full items-center gap-1 rounded-full bg-white px-2.5 py-1 font-semibold text-canvas-violet shadow-sm ring-1 ring-canvas-violet/20 transition-transform duration-150 ease-out active:scale-[0.97] sm:min-h-0"
                >
                  <span className="min-w-0 truncate">{c.text}</span>
                  <X aria-hidden className="h-3.5 w-3.5 shrink-0" />
                </button>
              ))}
              <button type="button" onClick={clear} className="min-h-9 px-1.5 font-extrabold text-canvas-violet underline-offset-2 hover:underline sm:min-h-0">
                Süzgeçleri temizle
              </button>
            </div>
          )}
        </section>
      )}

      {d && !d.loading && (
        <>
          {/* Telefonda tek sütun: evre seçiciyle. */}
          <div className="grid grid-cols-3 gap-1 rounded-2xl bg-slate-100 p-1 lg:hidden" role="tablist" aria-label="Evre">
            {d.phases.map((ph) => (
              <button
                key={ph.no}
                type="button"
                role="tab"
                aria-selected={phase === ph.no}
                onClick={() => setPhase(ph.no)}
                className={`min-h-11 rounded-xl px-2 text-[12px] font-extrabold transition-colors duration-150 ${
                  phase === ph.no ? 'bg-canvas-violet text-white shadow-md' : 'text-canvas-ink'
                }`}
              >
                {ph.title} <span className="font-mono tabular-nums">{nf.format(filtered.filter((c) => c.phase === ph.no).length)}</span>
              </button>
            ))}
          </div>
          <div className="grid gap-3 lg:grid-cols-3 lg:items-start lg:gap-4">
            {d.phases.map((ph) => (
              <div key={ph.no} className={phase === ph.no ? '' : 'hidden lg:block'}>
                <Column
                  no={ph.no}
                  title={ph.title}
                  lead={ph.lead}
                  steps={ph.steps.map((s) => s.title)}
                  cards={filtered.filter((c) => c.phase === ph.no)}
                  onClear={active > 0 ? clear : undefined}
                />
              </div>
            ))}
          </div>
          <Folded title="Tamamlanan projeler" cards={completed} />
          <Folded title="Reddedilen ve iptal edilen projeler" cards={closed} />
          {!d.audit && (
            <p className="px-1 text-[11px] text-canvas-muted">
              Editör atama ve rapor tarihleri CRM değişiklik kaydından okunamadı; bu adımlarda bekleme bir önceki bilinen tarihten sayılıyor.
            </p>
          )}
        </>
      )}
    </ModuleFrame>
  );
}
